/**
 * Real end-to-end integration tests against the LIVE full stack — Node
 * backend (auth, persistence, the triageService.js HTTP client) calling
 * the real Python triage service, which makes real Groq calls. Opt-in
 * only: `npm run test:integration` (see package.json), NOT part of the
 * default `npm test` — a suite that spends real Groq quota and takes
 * 10-100s per scenario cannot be the default for routine runs (this
 * project already hit a real Groq daily-quota exhaustion twice from
 * testing alone; see ../../docs/PROGRESS_TRACKER.md §9.1/§9.2).
 *
 * Scenarios are loaded from
 * ../../ProAuth_AI_ML/policy-rag/tests/integration_scenarios.json — the
 * SAME file test_triage_integration.py reads, so the two layers
 * (Python-direct-to-the-triage-service, and this file's
 * through-the-full-Node-stack-with-auth) stay in sync from one source of
 * truth. This file's job specifically: prove auth/role-gating, request
 * persistence (TriageEvaluation), and the Node-side timeout/HTTP-client
 * layer work — not just that the core pipeline decides correctly (that's
 * the Python file's job).
 *
 * Prerequisites (not started by this test file):
 *   1. Postgres+pgvector running (docker compose up -d postgres).
 *   2. This backend running on :5001 with the triage service auto-spawned
 *      (npm run dev) or reachable separately on :8002.
 *   3. GROQ_AGENT_API_KEY set with quota available.
 *   4. The seeded demo doctor account (doctor@hospital.com/doctor123)
 *      present — created automatically by seedDemoData() on boot.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SCENARIOS_PATH = path.join(
  __dirname, '..', '..', 'ProAuth_AI_ML', 'policy-rag', 'tests', 'integration_scenarios.json',
);
const API_BASE = process.env.API_BASE_URL || 'http://localhost:5001/api';
const RUN_INTEGRATION = process.env.RUN_INTEGRATION_TESTS === 'true';

async function isBackendReachable() {
  try {
    const res = await fetch(`${API_BASE}/health`.replace('/api/health', '/health'));
    return res.ok;
  } catch {
    return false;
  }
}

async function loginAsDoctor() {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: 'doctor@hospital.com', password: 'doctor123' }),
  });
  if (!res.ok) throw new Error(`Login failed: ${res.status} ${await res.text()}`);
  const body = await res.json();
  return body.data.token;
}

const scenarios = JSON.parse(readFileSync(SCENARIOS_PATH, 'utf-8'));

// Reachability is checked once, synchronously-ish, before deciding
// whether to register real tests or a single explanatory skip — avoids
// each of the 6 scenario tests independently timing out against a
// service that was never going to answer.
const reachable = RUN_INTEGRATION ? await isBackendReachable() : false;

if (!RUN_INTEGRATION) {
  test('triage integration suite (skipped — pass RUN_INTEGRATION_TESTS=true to run; spends real Groq quota)', { skip: true }, () => {});
} else if (!reachable) {
  test(`triage integration suite (skipped — backend not reachable at ${API_BASE})`, { skip: true }, () => {});
} else {
  const token = await loginAsDoctor();

  for (const scenario of scenarios) {
    test(`triage scenario: ${scenario.id}`, async () => {
      const res = await fetch(`${API_BASE}/triage/evaluate`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(scenario.request),
      });

      assert.equal(res.status, 200, `${scenario.id}: ${await res.text()}`);
      const body = await res.json();
      assert.equal(body.success, true);

      const decision = body.data?.decision || {};
      assert.equal(
        decision.outcome,
        scenario.expectedOutcome,
        `${scenario.id}: expected ${scenario.expectedOutcome}, got ${decision.outcome} (reason: ${decision.reason})`,
      );

      const mlFeatures = body.data?.mlFeatures || {};
      for (const [gateName, expectedValue] of Object.entries(scenario.expectedGates || {})) {
        assert.equal(
          mlFeatures[gateName],
          expectedValue,
          `${scenario.id}: gate ${gateName} expected ${expectedValue}, got ${mlFeatures[gateName]}`,
        );
      }

      // Proves this went through the REAL full stack, not just the Python
      // service directly — an evaluationId means TriageEvaluation
      // persistence (triageRoutes.js) actually ran.
      assert.ok(body.data?.evaluationId, `${scenario.id}: missing evaluationId — persistence layer didn't run`);
    });
  }

  test('unauthenticated triage request is rejected', async () => {
    const res = await fetch(`${API_BASE}/triage/evaluate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(scenarios[0].request),
    });
    assert.equal(res.status, 401);
  });
}
