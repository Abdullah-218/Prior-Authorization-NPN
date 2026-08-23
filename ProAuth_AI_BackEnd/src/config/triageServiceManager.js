/**
 * Triage Service Manager
 *
 * Same auto-start-or-reuse pattern as mlServiceManager.js, but for the NEW
 * policy-aware agents+RAG+ML pipeline (ProAuth_AI_ML/policy-rag/main.py) —
 * a separate process/port from the old ML service, which this one does not
 * replace or depend on.
 *
 * If the triage service fails to start or dies, the backend keeps running —
 * triageService.js treats an unreachable triage service as a clear error
 * response rather than crashing the request path.
 */
import { spawn } from 'child_process';
import { env } from './env.js';

let triageProcess = null;

async function isTriageServiceHealthy() {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 1500);
    const response = await fetch(`${env.triageServiceUrl}/health`, { signal: controller.signal })
      .finally(() => clearTimeout(timeout));
    return response.ok;
  } catch {
    return false;
  }
}

export async function startTriageService() {
  if (!env.triageServiceAutoStart) {
    console.log('⏭️  Triage service auto-start disabled (TRIAGE_SERVICE_AUTO_START=false).');
    return;
  }

  if (await isTriageServiceHealthy()) {
    console.log(`✅ Triage service already running at ${env.triageServiceUrl} — reusing it.`);
    return;
  }

  const port = new URL(env.triageServiceUrl).port || '8002';
  console.log(`🚀 Starting triage service: ${env.triageServicePythonBin} -m uvicorn main:app --port ${port}`);
  console.log(`   (cwd: ${env.triageServiceDir})`);

  triageProcess = spawn(
    env.triageServicePythonBin,
    ['-m', 'uvicorn', 'main:app', '--port', port],
    { cwd: env.triageServiceDir, stdio: 'inherit' }
  );

  triageProcess.on('error', (err) => {
    console.error('❌ Failed to start triage service:', err.message);
    console.error(`   Check TRIAGE_SERVICE_DIR (${env.triageServiceDir}) and TRIAGE_SERVICE_PYTHON_BIN (${env.triageServicePythonBin}) in .env.`);
    triageProcess = null;
  });

  triageProcess.on('exit', (code) => {
    if (code !== null && code !== 0) {
      console.error(`⚠️  Triage service exited unexpectedly (code ${code}). New requests will fail until it's restarted.`);
    }
    triageProcess = null;
  });
}

// Only kills the process if we spawned it — a reused already-running
// service (started outside this backend) is left alone.
export function stopTriageService() {
  if (triageProcess) {
    triageProcess.kill();
    triageProcess = null;
  }
}
