import { DataTypes } from 'sequelize';

// ─── InsurancePlan ────────────────────────────────────────────────────────────
export function defineInsurancePlan(sequelize) {
  return sequelize.define(
    'InsurancePlan',
    {
      id:           { type: DataTypes.STRING, primaryKey: true, allowNull: false },
      planId:       { type: DataTypes.STRING, allowNull: false, unique: true }, // e.g. "PLAN001"
      planName:     { type: DataTypes.STRING, allowNull: false },
      payerName:    { type: DataTypes.STRING, allowNull: false },
      coverageType: { type: DataTypes.STRING, allowNull: true }, // e.g. "Medicare", "Commercial", "Medicaid"
      tier:         { type: DataTypes.STRING, allowNull: true },
      jurisdiction: { type: DataTypes.STRING, allowNull: true }, // e.g. "US", "US-CA"
      active:       { type: DataTypes.BOOLEAN, defaultValue: true },
    },
    {
      tableName: 'insurance_plans',
      timestamps: true,
      indexes: [
        { fields: ['planId'], name: 'idx_insurance_plans_plan_id', unique: true },
      ],
    }
  );
}

// ─── Policy ───────────────────────────────────────────────────────────────────

export const POLICY_SOURCE = {
  CMS: 'CMS',                             // real CMS NCD/LCD, via api.coverage.cms.gov
  PUBLIC_PAYER_POLICY: 'PUBLIC_PAYER_POLICY', // real, publicly published payer medical policy PDF
  SYNTHETIC_POLICY: 'SYNTHETIC_POLICY',   // prototype/demo fixture — not a real policy
};

export function definePolicy(sequelize) {
  return sequelize.define(
    'Policy',
    {
      id:             { type: DataTypes.STRING, primaryKey: true, allowNull: false },
      policyId:       { type: DataTypes.STRING, allowNull: false, unique: true }, // e.g. "POL001" or the real NCD/LCD id
      policyName:     { type: DataTypes.STRING, allowNull: false },
      policyType:     { type: DataTypes.STRING, allowNull: true }, // e.g. "NCD", "LCD", "Payer Medical Policy"
      source:         { type: DataTypes.ENUM(...Object.values(POLICY_SOURCE)), allowNull: false },
      payerName:      { type: DataTypes.STRING, allowNull: true },
      jurisdiction:   { type: DataTypes.STRING, allowNull: true },
      effectiveDate:  { type: DataTypes.DATEONLY, allowNull: true },
      expirationDate: { type: DataTypes.DATEONLY, allowNull: true },
      documentPath:   { type: DataTypes.STRING, allowNull: true }, // original source PDF/URL
      status:         { type: DataTypes.STRING, defaultValue: 'ACTIVE' }, // ACTIVE | RETIRED | DRAFT
    },
    {
      tableName: 'policies',
      timestamps: true,
      indexes: [
        { fields: ['policyId'], name: 'idx_policies_policy_id', unique: true },
        { fields: ['payerName'], name: 'idx_policies_payer' },
        { fields: ['jurisdiction'], name: 'idx_policies_jurisdiction' },
      ],
    }
  );
}

// ─── PolicyVersion ────────────────────────────────────────────────────────────
// A policy's text/criteria can change over time; every AuthorizationEvaluation
// that used a policy should be able to point at exactly which version it saw
// (auditability — "which policy version was used?").
export function definePolicyVersion(sequelize) {
  return sequelize.define(
    'PolicyVersion',
    {
      id:             { type: DataTypes.STRING, primaryKey: true, allowNull: false },
      policyId:       { type: DataTypes.STRING, allowNull: false },
      version:        { type: DataTypes.STRING, allowNull: false }, // e.g. "1.0", "2024-03"
      effectiveDate:  { type: DataTypes.DATEONLY, allowNull: true },
      expirationDate: { type: DataTypes.DATEONLY, allowNull: true },
      documentHash:   { type: DataTypes.STRING, allowNull: true }, // sha256 of the ingested source doc, for change detection
    },
    {
      tableName: 'policy_versions',
      timestamps: true,
      updatedAt: false, // versions are immutable once created
      indexes: [
        { fields: ['policyId'], name: 'idx_policy_versions_policy_id' },
      ],
    }
  );
}

// ─── PolicyCriterion ──────────────────────────────────────────────────────────
// Structured, queryable coverage/medical-necessity requirements — what the
// Coverage Reasoning Agent compares evidence against, criterion by criterion.
export function definePolicyCriterion(sequelize) {
  return sequelize.define(
    'PolicyCriterion',
    {
      id:             { type: DataTypes.STRING, primaryKey: true, allowNull: false },
      policyId:       { type: DataTypes.STRING, allowNull: false },
      criterionType:  { type: DataTypes.STRING, allowNull: true }, // e.g. "DIAGNOSIS", "PRIOR_TREATMENT", "DOCUMENTATION"
      criterionText:  { type: DataTypes.TEXT,   allowNull: false }, // human-readable requirement text
      requirement:    { type: DataTypes.TEXT,   allowNull: true },  // structured/coded form where available (ICD/CPT lists, etc.)
      sourceSection:  { type: DataTypes.STRING, allowNull: true },  // page/section reference in the source document
    },
    {
      tableName: 'policy_criteria',
      timestamps: true,
      updatedAt: false,
      indexes: [
        { fields: ['policyId'], name: 'idx_policy_criteria_policy_id' },
      ],
    }
  );
}

// ─── PolicyChunk ──────────────────────────────────────────────────────────────
// RAG retrieval unit. Metadata columns are duplicated onto the chunk itself
// (not just reachable via the Policy join) specifically so retrieval can
// filter by payer/jurisdiction/date in the SAME query as the vector
// similarity search — the "structured metadata first, then semantic search"
// requirement, not two separate round trips.
export function definePolicyChunk(sequelize) {
  return sequelize.define(
    'PolicyChunk',
    {
      id:              { type: DataTypes.STRING, primaryKey: true, allowNull: false },
      policyId:        { type: DataTypes.STRING, allowNull: false },
      policyVersionId: { type: DataTypes.STRING, allowNull: true },
      chunkText:       { type: DataTypes.TEXT,   allowNull: false },
      embedding:       { type: DataTypes.VECTOR(384), allowNull: true }, // null until the ingestion pipeline embeds it
      section:         { type: DataTypes.STRING, allowNull: true },
      pageNumber:      { type: DataTypes.INTEGER, allowNull: true },
      payer:           { type: DataTypes.STRING, allowNull: true },
      jurisdiction:    { type: DataTypes.STRING, allowNull: true },
      effectiveDate:   { type: DataTypes.DATEONLY, allowNull: true },
      expirationDate:  { type: DataTypes.DATEONLY, allowNull: true },
      documentName:    { type: DataTypes.STRING, allowNull: true },
      source:          { type: DataTypes.ENUM(...Object.values(POLICY_SOURCE)), allowNull: false },
    },
    {
      tableName: 'policy_chunks',
      timestamps: true,
      updatedAt: false,
      indexes: [
        { fields: ['policyId'], name: 'idx_policy_chunks_policy_id' },
        { fields: ['payer'], name: 'idx_policy_chunks_payer' },
        { fields: ['jurisdiction'], name: 'idx_policy_chunks_jurisdiction' },
        // HNSW index for cosine-similarity search — built once chunks exist;
        // harmless (just unused) on an empty table until the ingestion
        // pipeline populates it.
        { fields: ['embedding'], name: 'idx_policy_chunks_embedding_hnsw', using: 'hnsw', operator: 'vector_cosine_ops' },
      ],
    }
  );
}
