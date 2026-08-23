/**
 * Field-level encryption for clinical/decision data at rest — see the
 * plan at implementation time for the full scope/reasoning. AES-256-GCM
 * (authenticated — tampering is detected on decrypt, not just
 * confidentiality), a fresh random IV per value (never reused with the
 * same key), versioned envelope so a future key rotation can decrypt old
 * records under an old key while writing new ones under a new key.
 *
 * Deliberately kept independent of Sequelize/any model — this is a pure
 * string-in/string-out utility. models.js/triageModels.js wire it into
 * field getters/setters so encryption is transparent to every existing
 * route; nothing here knows about the database.
 */
import crypto from 'crypto';

const ALGORITHM = 'aes-256-gcm';
const IV_LENGTH = 12; // NIST-recommended length for GCM
const ENVELOPE_VERSION = 'v1';

let cachedKey = null;

function getKey() {
  if (cachedKey) return cachedKey;
  const keyB64 = process.env.DATA_ENCRYPTION_KEY;
  if (!keyB64) {
    throw new Error('DATA_ENCRYPTION_KEY not set — add it to ProAuth_AI_BackEnd/.env (32 random bytes, base64-encoded)');
  }
  const key = Buffer.from(keyB64, 'base64');
  if (key.length !== 32) {
    throw new Error(`DATA_ENCRYPTION_KEY must decode to exactly 32 bytes (256 bits) — got ${key.length}`);
  }
  cachedKey = key;
  return key;
}

// Encrypts a plain string. Passes null/undefined through unchanged so
// optional fields (many of these columns are legitimately null — e.g. no
// previous treatment on file) don't need special-casing at every call site.
export function encryptField(plaintext) {
  if (plaintext === null || plaintext === undefined) return plaintext;
  const key = getKey();
  const iv = crypto.randomBytes(IV_LENGTH);
  const cipher = crypto.createCipheriv(ALGORITHM, key, iv);
  const ciphertext = Buffer.concat([cipher.update(String(plaintext), 'utf8'), cipher.final()]);
  const authTag = cipher.getAuthTag();
  return `${ENVELOPE_VERSION}.${iv.toString('base64')}.${authTag.toString('base64')}.${ciphertext.toString('base64')}`;
}

// Decrypts a versioned envelope back to the original plain string. A
// value that isn't in envelope shape is returned as-is rather than
// thrown on — this is a deliberate defensive fallback for any row that
// somehow predates encryption, not an expected steady-state path.
export function decryptField(envelope) {
  if (envelope === null || envelope === undefined) return envelope;
  if (typeof envelope !== 'string' || !envelope.startsWith(`${ENVELOPE_VERSION}.`)) return envelope;

  const parts = envelope.split('.');
  if (parts.length !== 4) return envelope;
  const [, ivB64, tagB64, dataB64] = parts;

  const key = getKey();
  const iv = Buffer.from(ivB64, 'base64');
  const authTag = Buffer.from(tagB64, 'base64');
  const ciphertext = Buffer.from(dataB64, 'base64');

  const decipher = crypto.createDecipheriv(ALGORITHM, key, iv);
  decipher.setAuthTag(authTag);
  const plaintext = Buffer.concat([decipher.update(ciphertext), decipher.final()]);
  return plaintext.toString('utf8');
}

// JSON-object convenience wrappers for the JSONB columns (clinical,
// treatment, decision, mlFeatures, etc.) — stores the encrypted envelope
// as a JSON *string* value inside the JSONB column (Postgres JSONB can
// hold a bare string, not just objects/arrays), so no column type change
// (JSONB -> TEXT) is needed anywhere. Simpler and lower-risk than the
// type-change migration than originally scoped.
export function encryptJson(value) {
  if (value === null || value === undefined) return value;
  return encryptField(JSON.stringify(value));
}

export function decryptJson(envelope) {
  if (envelope === null || envelope === undefined) return envelope;
  const decrypted = decryptField(envelope);
  if (typeof decrypted !== 'string') return decrypted;
  try {
    return JSON.parse(decrypted);
  } catch {
    return decrypted; // defensive — shouldn't happen for real envelopes
  }
}
