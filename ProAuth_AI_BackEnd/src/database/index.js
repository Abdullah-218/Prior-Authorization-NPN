import { Sequelize, DataTypes } from 'sequelize';
import bcrypt from 'bcryptjs';
import pgvector from 'pgvector/sequelize';
import { env } from '../config/env.js';
import { encryptJson, decryptJson } from '../utils/fieldEncryption.js';
import {
  defineDrugReference,
  defineAuthorizationEvaluation,
} from './models.js';

// Transparent field-level encryption for the clinical-content columns
// scoped by the encryption plan (2026-08-22) — everything else on this
// model (patient/provider/insurance identity JSONB, status, createdBy,
// etc.) is deliberately left plaintext, since it's either non-clinical
// or needed for row-level access control / reviewer queues. Encrypted
// value is stored as a JSON *string* inside the JSONB column (Postgres
// JSONB can hold a bare string) — no column type change needed. Existing
// rows were migrated in place by scripts/migrateEncryptClinicalData.js
// BEFORE this getter/setter was added (running it after would have tried
// to decrypt still-plaintext data).
function encryptedJsonbField(fieldName) {
  return {
    type: DataTypes.JSONB,
    get() { return decryptJson(this.getDataValue(fieldName)); },
    set(value) { this.setDataValue(fieldName, encryptJson(value)); },
  };
}
import {
  defineInsurancePlan,
  definePolicy,
  definePolicyVersion,
  definePolicyCriterion,
  definePolicyChunk,
} from './policyModels.js';
import { defineTriageEvaluation } from './triageModels.js';
import { defineNotification } from './notificationModel.js';

const isSqlite = env.databaseUrl?.startsWith('sqlite');

// Registers DataTypes.VECTOR (and the cosineDistance/l2Distance query
// helpers) on the Sequelize class — must run before any model definition
// that uses DataTypes.VECTOR. No-op-safe under the sqlite dev fallback:
// PolicyChunk's embedding column requires Postgres + the vector extension
// either way, so a sqlite run just never issues vector queries against it.
pgvector.registerTypes(Sequelize);

const sequelize = new Sequelize(env.databaseUrl, {
  dialect: isSqlite ? 'sqlite' : 'postgres',
  logging: env.sqlLogging ? console.log : false,
  pool: isSqlite ? undefined : { max: 10, min: 0, idle: 10000 },
  dialectOptions:
    env.databaseSsl && !isSqlite
      ? { ssl: { require: true, rejectUnauthorized: false } }
      : {},
});

// ─── Existing models ──────────────────────────────────────────────────────────

const User = sequelize.define(
  'User',
  {
    id:             { type: DataTypes.STRING, primaryKey: true, allowNull: false },
    name:           { type: DataTypes.STRING, allowNull: false },
    email:          { type: DataTypes.STRING, allowNull: false, unique: true },
    password:       { type: DataTypes.STRING, allowNull: false },
    role:           { type: DataTypes.STRING, allowNull: false, defaultValue: 'DOCTOR' },
    hospital:       { type: DataTypes.STRING, allowNull: true },
    specialization: { type: DataTypes.STRING, allowNull: true },
    providerId:     { type: DataTypes.STRING, allowNull: true },
    // PATIENT-role accounts only (2026-08-20+) — links a login account to
    // its own patients.id row, the same way providerId links a DOCTOR
    // account to a Provider row. Resolved once at login/register time into
    // the JWT payload (see authRoutes.js) so every authorized request can
    // scope by it without an extra lookup.
    patientId:      { type: DataTypes.STRING, allowNull: true },
  },
  { tableName: 'users', timestamps: true }
);

const Patient = sequelize.define(
  'Patient',
  {
    id:               { type: DataTypes.STRING, primaryKey: true, allowNull: false },
    firstName:        DataTypes.STRING,
    lastName:         DataTypes.STRING,
    insuranceMemberId: DataTypes.STRING,
    dateOfBirth:      DataTypes.STRING,
    phone:            DataTypes.STRING,
    email:            DataTypes.STRING,
    gender:           DataTypes.STRING,
    age:              DataTypes.INTEGER,
    chronicConditionCount:    { type: DataTypes.INTEGER, defaultValue: 0 },
    previousMedicationsCount: { type: DataTypes.INTEGER, defaultValue: 0 },
    insuranceType:    DataTypes.STRING, // 'private' | 'public' | 'uninsured'
    coverageActive:   { type: DataTypes.BOOLEAN, defaultValue: true },
    policyNumber:     DataTypes.STRING,
    // The patient's actual insurance plan — previously this was picked
    // fresh from a dropdown on every single authorization with nothing
    // persisted, so the same patient could end up with a different plan
    // selected next time and there was no single source of truth. Nullable:
    // uninsured/unknown patients legitimately have no plan to reference.
    insurancePlanId:  { type: DataTypes.STRING, allowNull: true },
    createdBy:        DataTypes.STRING,
  },
  { tableName: 'patients', timestamps: true }
);

const Provider = sequelize.define(
  'Provider',
  {
    id:           { type: DataTypes.STRING, primaryKey: true, allowNull: false },
    name:         DataTypes.STRING,
    specialty:    DataTypes.STRING,
    organization: DataTypes.STRING,
    providerId:   DataTypes.STRING,
    contactEmail: DataTypes.STRING,
    createdBy:    DataTypes.STRING,
  },
  { tableName: 'providers', timestamps: true }
);

const Authorization = sequelize.define(
  'Authorization',
  {
    id:          { type: DataTypes.STRING, primaryKey: true, allowNull: false },
    patientId:   DataTypes.STRING,
    providerId:  DataTypes.STRING,
    patient:     DataTypes.JSONB,
    provider:    DataTypes.JSONB,
    insurance:   DataTypes.JSONB,
    payer:       DataTypes.STRING,
    clinical:    encryptedJsonbField('clinical'),
    treatment:   encryptedJsonbField('treatment'),
    previousTreatment:    encryptedJsonbField('previousTreatment'),
    justification:        encryptedJsonbField('justification'),
    documents:            DataTypes.JSONB,
    documentDetails:      DataTypes.JSONB,
    currentMedications:   encryptedJsonbField('currentMedications'),
    status:      DataTypes.STRING,
    risk:        DataTypes.STRING,
    // Rule engine scores stored back on the authorization
    ruleComplianceScore:      DataTypes.FLOAT,
    evidenceScore:            DataTypes.FLOAT,
    dataCompletenessScore:    DataTypes.FLOAT,
    ruleEvaluationConfidence: DataTypes.FLOAT,
    nextStage:   DataTypes.STRING,
    submittedAt: DataTypes.DATE,
    submittedDate: DataTypes.STRING,
    submitted:   DataTypes.STRING,
    message:     DataTypes.TEXT,
    createdBy:   DataTypes.STRING,
    role:        DataTypes.STRING,
    rules:       DataTypes.JSONB,       // legacy + new engine result
    additionalInformation: DataTypes.JSONB,
    appeal:      DataTypes.JSONB,
    // Admin review decision (written by PATCH /:id/review) — these columns were
    // previously missing, so the route was silently dropping them on .update().
    reviewedBy:  DataTypes.STRING,
    reviewNote:  DataTypes.TEXT,
    reviewedAt:  DataTypes.DATE,
    // Who last set `status` to its current value — 'AUTOMATED_ML' (the new
    // policy-rag pipeline's own APPROVE/PEND/MORE_INFORMATION decision,
    // written by triageRoutes.js) or 'MANUAL_REVIEWER' (a human override
    // via PATCH /:id/review). Null means status was set by the OLD rule
    // engine only — this column didn't exist before the new pipeline
    // started writing back to `status` (2026-08-19+). Distinct from
    // `reviewedBy` (which the OLD rule-engine flow's analytics dashboard
    // already reads as its own automated/manual signal) — this one is
    // specific to the new pipeline's provenance so both systems' history
    // stays legible side by side.
    decisionSource: { type: DataTypes.STRING, allowNull: true },
  },
  { tableName: 'authorizations', timestamps: true }
);

const Document = sequelize.define(
  'Document',
  {
    id:             { type: DataTypes.STRING, primaryKey: true, allowNull: false },
    authorizationId: DataTypes.STRING,
    fileName:       DataTypes.STRING,
    mimeType:       DataTypes.STRING,
    storageUrl:     DataTypes.STRING,
    // One of the fixed upload categories NewApplication.jsx's Step 7
    // offers (CLINICAL_NOTES | PRESCRIPTION | LAB_REPORTS | IMAGING_REPORT
    // | PREVIOUS_TREATMENT_RECORDS) — the Document Agent's category
    // matching (policy-rag/document_agent.py's CATEGORY_KEYWORDS) needs
    // this to know which required document a given file could satisfy.
    documentType:   { type: DataTypes.STRING, allowNull: true },
  },
  { tableName: 'documents', timestamps: true }
);

const AuditEvent = sequelize.define(
  'AuditEvent',
  {
    id:             { type: DataTypes.STRING, primaryKey: true, allowNull: false },
    authorizationId: DataTypes.STRING,
    action:         DataTypes.STRING,
    actor:          DataTypes.STRING,
    details:        DataTypes.JSONB,
  },
  { tableName: 'audit_events', timestamps: true }
);

// ─── New models ───────────────────────────────────────────────────────────────

const DrugReference            = defineDrugReference(sequelize);
const AuthorizationEvaluation  = defineAuthorizationEvaluation(sequelize);

// ─── Insurance / policy models ─────────────────────────────────────────────────

const InsurancePlan   = defineInsurancePlan(sequelize);
const Policy          = definePolicy(sequelize);
const PolicyVersion   = definePolicyVersion(sequelize);
const PolicyCriterion = definePolicyCriterion(sequelize);
const PolicyChunk     = definePolicyChunk(sequelize);

// ─── Triage pipeline models ─────────────────────────────────────────────────

const TriageEvaluation = defineTriageEvaluation(sequelize);
const Notification     = defineNotification(sequelize);

// ─── Associations ─────────────────────────────────────────────────────────────

User.hasMany(Authorization,   { foreignKey: 'createdBy' });
Authorization.belongsTo(User, { foreignKey: 'createdBy' });
Patient.hasMany(Authorization,   { foreignKey: 'patientId' });
Authorization.belongsTo(Patient, { foreignKey: 'patientId' });
Provider.hasMany(Authorization,   { foreignKey: 'providerId' });
Authorization.belongsTo(Provider, { foreignKey: 'providerId' });
Authorization.hasMany(Document, { foreignKey: 'authorizationId' });
Document.belongsTo(Authorization, { foreignKey: 'authorizationId' });
Authorization.hasMany(AuditEvent, { foreignKey: 'authorizationId' });
AuditEvent.belongsTo(Authorization, { foreignKey: 'authorizationId' });
Authorization.hasMany(TriageEvaluation, { foreignKey: 'authorizationId' });
TriageEvaluation.belongsTo(Authorization, { foreignKey: 'authorizationId' });
User.hasMany(Notification, { foreignKey: 'userId' });
Notification.belongsTo(User, { foreignKey: 'userId' });

// New associations
Authorization.hasMany(AuthorizationEvaluation,  { foreignKey: 'authorizationId' });
AuthorizationEvaluation.belongsTo(Authorization, { foreignKey: 'authorizationId' });

// Insurance / policy associations. InsurancePlan is deliberately NOT
// FK-linked to Policy — which policy applies to a given plan is resolved at
// query time (matching payer/jurisdiction/service against policy_criteria),
// not a fixed 1:many list declared up front. A real plan can be governed by
// several policies, and one policy can apply across several plans from the
// same payer.
Policy.hasMany(PolicyVersion,   { foreignKey: 'policyId', as: 'versions' });
PolicyVersion.belongsTo(Policy, { foreignKey: 'policyId' });
// Explicit alias — Sequelize's auto-pluralizer doesn't know "Criterion" ->
// "Criteria" and would otherwise produce "PolicyCriterions".
Policy.hasMany(PolicyCriterion,   { foreignKey: 'policyId', as: 'criteria' });
PolicyCriterion.belongsTo(Policy, { foreignKey: 'policyId' });
Policy.hasMany(PolicyChunk,   { foreignKey: 'policyId' });
PolicyChunk.belongsTo(Policy, { foreignKey: 'policyId' });
PolicyVersion.hasMany(PolicyChunk,   { foreignKey: 'policyVersionId' });
PolicyChunk.belongsTo(PolicyVersion, { foreignKey: 'policyVersionId' });

// Patient.insurancePlanId stores InsurancePlan.planId (the business key,
// e.g. "PLAN001") rather than the internal uuid — deliberately, since
// that's what the frontend dropdown, the API, and the Python agent's
// get_plan_payer()/evaluate_policy_evidence() already use as the plan
// identifier everywhere else. targetKey overrides Sequelize's default
// (which would otherwise assume the FK targets InsurancePlan.id).
InsurancePlan.hasMany(Patient,   { foreignKey: 'insurancePlanId', sourceKey: 'planId' });
Patient.belongsTo(InsurancePlan, { foreignKey: 'insurancePlanId', targetKey: 'planId' });

// ─── DB lifecycle ─────────────────────────────────────────────────────────────

export async function connectDatabase() {
  await sequelize.authenticate();
  if (env.nodeEnv === 'development') console.log('✅ PostgreSQL connection established.');
}

// Must run before syncDatabase() — PolicyChunk's embedding column is typed
// `vector`, which only exists once this extension is installed. No-op under
// the sqlite dev fallback, where PolicyChunk isn't usable anyway.
export async function ensureVectorExtension() {
  if (isSqlite) return;
  await sequelize.query('CREATE EXTENSION IF NOT EXISTS vector;');
  if (env.nodeEnv === 'development') console.log('✅ pgvector extension ready.');
}

export async function syncDatabase() {
  await sequelize.sync({ force: false, alter: true });
  if (env.nodeEnv === 'development') console.log('✅ Database schema synced.');
}

export async function seedDemoData() {
  const [doctorExists, adminExists, nurseExists] = await Promise.all([
    User.findOne({ where: { email: 'doctor@hospital.com' } }),
    User.findOne({ where: { email: 'admin@insurance.com' } }),
    User.findOne({ where: { email: 'nurse@insurance.com' } }),
  ]);

  if (!doctorExists) {
    await User.create({
      id: 'user-doctor',
      name: 'Dr. Sarah Johnson',
      email: 'doctor@hospital.com',
      password: bcrypt.hashSync('doctor123', 10),
      role: 'DOCTOR',
      hospital: 'City Medical Center',
      specialization: 'Orthopedics',
      providerId: 'DOC001',
    });
  }
  if (!adminExists) {
    await User.create({
      id: 'user-admin',
      name: 'CTS Health Insurance',
      email: 'admin@insurance.com',
      password: bcrypt.hashSync('admin123', 10),
      role: 'ADMIN',
    });
  }
  // Nurse reviewer — works PEND requests the triage pipeline routed for
  // human review (approve, or ask the doctor for more information). See
  // authorizationRoutes.js's PATCH /:id/review and the "manual" queue.
  if (!nurseExists) {
    await User.create({
      id: 'user-nurse',
      name: 'Nurse Emily Carter',
      email: 'nurse@insurance.com',
      password: bcrypt.hashSync('nurse123', 10),
      role: 'NURSE',
    });
  }
}

export async function initializeDatabase() {
  await connectDatabase();
  if (!env.skipDbSync) {
    await ensureVectorExtension();
    await syncDatabase();
  } else {
    if (env.nodeEnv === 'development') console.log('⏭️ Skipping automatic DB sync (SKIP_DB_SYNC=true).');
  }
  await seedDemoData();
}

export {
  sequelize,
  User, Patient, Provider, Authorization,
  Document, AuditEvent,
  DrugReference, AuthorizationEvaluation,
  InsurancePlan, Policy, PolicyVersion, PolicyCriterion, PolicyChunk,
  TriageEvaluation, Notification,
};
export { POLICY_SOURCE } from './policyModels.js';
