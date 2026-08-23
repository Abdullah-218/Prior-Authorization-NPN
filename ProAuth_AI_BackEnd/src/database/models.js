/**
 * New Sequelize models for the rule engine pipeline.
 * Imported by database/index.js and used throughout the service layer.
 */
import { DataTypes } from 'sequelize';

// ─── DrugReference ────────────────────────────────────────────────────────────
export function defineDrugReference(sequelize) {
  return sequelize.define(
    'DrugReference',
    {
      id: { type: DataTypes.STRING, primaryKey: true, allowNull: false },
      externalId: { type: DataTypes.STRING, allowNull: true },       // FDA spl id
      setId:      { type: DataTypes.STRING, allowNull: true, unique: true }, // FDA set_id
      genericName:  { type: DataTypes.TEXT,   allowNull: true },
      brandName:    { type: DataTypes.TEXT,   allowNull: true },
      activeIngredients: { type: DataTypes.JSONB, allowNull: true }, // string[]
      productType:  { type: DataTypes.STRING, allowNull: true },
      route:        { type: DataTypes.STRING, allowNull: true },
      indications:  { type: DataTypes.TEXT,   allowNull: true },
      contraindications:    { type: DataTypes.TEXT, allowNull: true },
      warnings:             { type: DataTypes.TEXT, allowNull: true },
      adverseReactions:     { type: DataTypes.TEXT, allowNull: true },
      drugInteractions:     { type: DataTypes.TEXT, allowNull: true },
      dosageInformation:    { type: DataTypes.TEXT, allowNull: true },
      pregnancyInformation: { type: DataTypes.TEXT, allowNull: true },
      pediatricInformation: { type: DataTypes.TEXT, allowNull: true },
      geriatricInformation: { type: DataTypes.TEXT, allowNull: true },
      pharmClass:           { type: DataTypes.JSONB, allowNull: true }, // string[]
      rxcui:                { type: DataTypes.JSONB, allowNull: true }, // string[]
      source:               { type: DataTypes.STRING, defaultValue: 'FDA_LABEL' },
      sourceVersion:        { type: DataTypes.STRING, allowNull: true },
      sourceUpdatedAt:      { type: DataTypes.STRING, allowNull: true },
      // rawData intentionally omitted from frontend exposure
    },
    {
      tableName: 'drug_references',
      timestamps: true,
      indexes: [
        { fields: ['genericName'], name: 'idx_drug_ref_generic' },
        { fields: ['brandName'],   name: 'idx_drug_ref_brand' },
        { fields: ['setId'],       name: 'idx_drug_ref_setid' },
      ],
    }
  );
}

// ─── AuthorizationEvaluation ─────────────────────────────────────────────────
export function defineAuthorizationEvaluation(sequelize) {
  return sequelize.define(
    'AuthorizationEvaluation',
    {
      id: { type: DataTypes.STRING, primaryKey: true, allowNull: false },
      authorizationId:       { type: DataTypes.STRING, allowNull: false },
      evaluationVersion:     { type: DataTypes.INTEGER, defaultValue: 1 },
      ruleComplianceScore:   { type: DataTypes.FLOAT, allowNull: true },
      evidenceScore:         { type: DataTypes.FLOAT, allowNull: true },
      dataCompletenessScore: { type: DataTypes.FLOAT, allowNull: true },
      ruleEvaluationConfidence: { type: DataTypes.FLOAT, allowNull: true },
      confidenceFactors:     { type: DataTypes.JSONB, allowNull: true },
      passedWeight:          { type: DataTypes.FLOAT, allowNull: true },
      applicableWeight:      { type: DataTypes.FLOAT, allowNull: true },
      nextStage:             { type: DataTypes.STRING, allowNull: true },
      evaluationDurationMs:  { type: DataTypes.INTEGER, allowNull: true },
      rulesPassed:           { type: DataTypes.INTEGER, defaultValue: 0 },
      rulesFailed:           { type: DataTypes.INTEGER, defaultValue: 0 },
      warningsCount:         { type: DataTypes.INTEGER, defaultValue: 0 },
      missingInformationCount: { type: DataTypes.INTEGER, defaultValue: 0 },
      unknownRulesCount:     { type: DataTypes.INTEGER, defaultValue: 0 },
      criticalFlagsCount:    { type: DataTypes.INTEGER, defaultValue: 0 },
      // Groq LLM outputs
      llmUsed:               { type: DataTypes.BOOLEAN, defaultValue: false },
      llmNarrative:          { type: DataTypes.TEXT,    allowNull: true },
      llmAmbiguityResolutions: { type: DataTypes.JSONB, allowNull: true },
      evaluatedAt:           { type: DataTypes.DATE, defaultValue: DataTypes.NOW },
      // XGBoost ML prediction (ProAuth_AI_ML) — only set when the rule engine
      // routed the request to PROCEED_TO_ML
      mlDecision:              { type: DataTypes.STRING, allowNull: true }, // APPROVE | DENY | MANUAL REVIEW
      mlApproveProbability:    { type: DataTypes.FLOAT,  allowNull: true },
      mlDenyProbability:       { type: DataTypes.FLOAT,  allowNull: true },
      mlManualProbability:     { type: DataTypes.FLOAT,  allowNull: true },
      mlInferenceTimeMs:       { type: DataTypes.INTEGER, allowNull: true },
      totalProcessingTimeMs:   { type: DataTypes.INTEGER, allowNull: true },
    },
    {
      tableName: 'authorization_evaluations',
      timestamps: true,
      indexes: [
        { fields: ['authorizationId'], name: 'idx_auth_eval_auth_id' },
      ],
    }
  );
}
