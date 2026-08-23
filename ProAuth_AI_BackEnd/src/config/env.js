import dotenv from 'dotenv';
import path from 'path';
import { fileURLToPath } from 'url';

dotenv.config();

const __dirname = path.dirname(fileURLToPath(import.meta.url));
// ProAuth_AI_BackEnd/src/config -> ProAuth_AI_BackEnd -> Practice_CTS -> ProAuth_AI_ML (sibling project)
const defaultMlServiceDir = path.resolve(__dirname, '../../../ProAuth_AI_ML');

// DATABASE_URL wins if set (local dev, docker-compose). Otherwise, build one
// from discrete DATABASE_HOST/PORT/NAME/USER/PASSWORD — this is what the RDS
// Copilot addon injects (host/name/user as plain env vars, password as a
// Secrets Manager-backed secret), since there's no single connection-string
// secret to reference directly.
function resolveDatabaseUrl() {
  if (process.env.DATABASE_URL) return process.env.DATABASE_URL;
  if (process.env.DATABASE_HOST) {
    const host = process.env.DATABASE_HOST;
    const port = process.env.DATABASE_PORT || '5432';
    const name = process.env.DATABASE_NAME || 'postgres';
    const user = encodeURIComponent(process.env.DATABASE_USER || 'postgres');
    const password = encodeURIComponent(process.env.DATABASE_PASSWORD || '');
    return `postgresql://${user}:${password}@${host}:${port}/${name}`;
  }
  return 'sqlite::memory:';
}

export const env = {
  port: Number(process.env.PORT || 5001),
  nodeEnv: process.env.NODE_ENV || 'development',
  databaseUrl: resolveDatabaseUrl(),
  jwtSecret: process.env.JWT_SECRET || 'change_me',
  jwtExpiresIn: process.env.JWT_EXPIRES_IN || '1d',
  // Comma-separated list of allowed frontend origins for CORS. Unset ->
  // reflect any origin (local dev only); set it in production so the API
  // doesn't accept credentialed requests from arbitrary origins.
  frontendUrl: process.env.FRONTEND_URL || '',
  // The policy-aware agents+RAG+ML triage pipeline (ProAuth_AI_ML/policy-rag/main.py) —
  // the only evaluation pipeline this backend calls (the old ml-model-1
  // XGBoost service and its config were removed 2026-08-20, retired).
  triageServiceUrl: process.env.TRIAGE_SERVICE_URL || 'http://localhost:8002',
  triageServiceAutoStart: process.env.TRIAGE_SERVICE_AUTO_START !== 'false',
  triageServiceDir: process.env.TRIAGE_SERVICE_DIR || path.join(defaultMlServiceDir, 'policy-rag'),
  triageServicePythonBin: process.env.TRIAGE_SERVICE_PYTHON_BIN || path.join(defaultMlServiceDir, 'policy-rag', '.venv', 'bin', 'python3'),
  // Whether to require SSL for the Postgres connection. Defaults to on in
  // production (matches managed DBs like RDS) but is independently
  // overridable — a plain `postgres` container/image doesn't speak SSL, so
  // containerized non-RDS setups must set DATABASE_SSL=false explicitly.
  databaseSsl: process.env.DATABASE_SSL
    ? process.env.DATABASE_SSL === 'true'
    : process.env.NODE_ENV === 'production',
  sqlLogging: process.env.SQL_LOGGING === 'true',
  skipDbSync: process.env.SKIP_DB_SYNC === 'true',
};
