/**
 * One-time migration: encrypts existing plaintext clinical/decision data
 * in place. Deliberately raw `pg`, NOT the Sequelize models — the models
 * are about to get decrypt-on-read getters (models.js/triageModels.js),
 * and running this migration through them would try to decrypt data
 * that's still plaintext at the moment this script runs. Sequence:
 *   1. Run this script (raw SQL, encrypts existing rows in place).
 *   2. Only THEN add the getters/setters to the models.
 *   3. Restart the backend.
 *
 * Idempotent/safely re-runnable: any value that's already a `v1.` envelope
 * is skipped, so a re-run (e.g. after a partial failure) only touches rows
 * that still need it.
 *
 * Scope matches the approved plan exactly:
 *   authorizations: clinical, treatment, previousTreatment, justification, currentMedications
 *   triage_evaluations: decision, clinicalEvidence, clinicalCriteriaEval, explanation, mlFeatures, diagnosis
 * Everything else (patient identity/insurance JSONB, audit_events, documents) is
 * explicitly out of scope per the approved plan.
 */
import { Client } from 'pg';
import { encryptField, encryptJson } from '../src/utils/fieldEncryption.js';
import { env } from '../src/config/env.js';

const JSONB_COLUMNS = {
  authorizations: ['clinical', 'treatment', 'previousTreatment', 'justification', 'currentMedications'],
  triage_evaluations: ['decision', 'clinicalEvidence', 'clinicalCriteriaEval', 'explanation', 'mlFeatures'],
};

const STRING_COLUMNS = {
  triage_evaluations: ['diagnosis'],
};

function isAlreadyEncrypted(value) {
  return typeof value === 'string' && value.startsWith('v1.');
}

async function migrateJsonbColumn(client, table, column) {
  const { rows } = await client.query(`SELECT id, "${column}" AS val FROM ${table}`);
  let migrated = 0, skippedNull = 0, skippedAlready = 0;
  for (const row of rows) {
    const { id, val } = row;
    if (val === null) { skippedNull += 1; continue; }
    if (isAlreadyEncrypted(val)) { skippedAlready += 1; continue; }
    const encrypted = encryptJson(val);
    await client.query(`UPDATE ${table} SET "${column}" = to_jsonb($1::text) WHERE id = $2`, [encrypted, id]);
    migrated += 1;
  }
  console.log(`  ${table}.${column}: ${migrated} encrypted, ${skippedNull} null (skipped), ${skippedAlready} already encrypted (skipped)`);
}

async function migrateStringColumn(client, table, column) {
  const { rows } = await client.query(`SELECT id, "${column}" AS val FROM ${table}`);
  let migrated = 0, skippedNull = 0, skippedAlready = 0;
  for (const row of rows) {
    const { id, val } = row;
    if (val === null) { skippedNull += 1; continue; }
    if (isAlreadyEncrypted(val)) { skippedAlready += 1; continue; }
    const encrypted = encryptField(val);
    await client.query(`UPDATE ${table} SET "${column}" = $1 WHERE id = $2`, [encrypted, id]);
    migrated += 1;
  }
  console.log(`  ${table}.${column}: ${migrated} encrypted, ${skippedNull} null (skipped), ${skippedAlready} already encrypted (skipped)`);
}

async function main() {
  if (!process.env.DATA_ENCRYPTION_KEY) {
    throw new Error('DATA_ENCRYPTION_KEY not set in the environment — this script needs it to actually encrypt anything.');
  }
  const client = new Client({ connectionString: env.databaseUrl });
  await client.connect();
  console.log('Connected. Starting migration (idempotent — safe to re-run).\n');

  // triage_evaluations.diagnosis is VARCHAR(255) today — widen to TEXT first
  // so an encrypted envelope (longer than the plaintext diagnosis) can never
  // be truncated. Cheap, instant, metadata-only change in Postgres — no data
  // rewrite needed for a varchar->text widen.
  await client.query('ALTER TABLE triage_evaluations ALTER COLUMN diagnosis TYPE TEXT');
  console.log('Widened triage_evaluations.diagnosis to TEXT.\n');

  for (const [table, columns] of Object.entries(JSONB_COLUMNS)) {
    console.log(`${table} (JSONB columns):`);
    for (const column of columns) await migrateJsonbColumn(client, table, column);
  }
  for (const [table, columns] of Object.entries(STRING_COLUMNS)) {
    console.log(`${table} (string columns):`);
    for (const column of columns) await migrateStringColumn(client, table, column);
  }

  await client.end();
  console.log('\nMigration complete.');
}

main().catch(err => { console.error('Migration failed:', err); process.exit(1); });
