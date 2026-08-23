/**
 * Triage Evaluation — persists the NEW policy-aware agents+RAG+ML
 * pipeline's full result (policy-rag/main.py's POST /triage response),
 * one row per call to POST /api/triage/evaluate.
 *
 * Before this model existed, a triage evaluation lived only in the HTTP
 * response — refresh the page and it was gone, no audit trail, no way to
 * look up "what did we decide on this request and why" after the fact.
 * This is the load-bearing piece the rest of the roadmap (reviewer
 * override loop, MongoDB thread continuity, model retraining) depends on
 * — none of that is possible if decisions aren't stored anywhere first.
 *
 * Deliberately NOT the same table as the old rule engine's
 * AuthorizationEvaluation (models.js) — that one has a fixed numeric
 * schema matching XGBoost's 35-field payload; this pipeline's shape
 * (policy evidence, clinical criteria, document evidence, a 10-feature ML
 * vector, an LLM explanation) is a different, evolving contract, so each
 * evidence stage is stored as JSONB rather than flattened into named
 * columns that would need a migration every time an agent's output shape
 * changes.
 */
import { DataTypes } from 'sequelize';
import { encryptField, decryptField, encryptJson, decryptJson } from '../utils/fieldEncryption.js';

// Same transparent-encryption pattern as database/index.js's Authorization
// model — see that file's comment for the full reasoning. policyEvidence
// and documentEvidence are deliberately NOT in scope (coverage/checklist
// data, not clinical content) per the approved plan; decisionOutcome/
// decisionConfidence/requestedService/planId/threadId stay plaintext
// since they're used for listing/joins/memoization lookups.
function encryptedJsonbField(fieldName) {
  return {
    type: DataTypes.JSONB,
    get() { return decryptJson(this.getDataValue(fieldName)); },
    set(value) { this.setDataValue(fieldName, encryptJson(value)); },
  };
}

export function defineTriageEvaluation(sequelize) {
  return sequelize.define(
    'TriageEvaluation',
    {
      id:               { type: DataTypes.STRING, primaryKey: true, allowNull: false },
      // Nullable: the endpoint doesn't strictly require an authorizationId
      // (e.g. ad-hoc testing), but the live frontend flow always sends the
      // real Authorization id, created moments earlier in the same submit().
      authorizationId:  { type: DataTypes.STRING, allowNull: true },
      requestedService: DataTypes.STRING,
      // TEXT (widened from the original VARCHAR(255) by the encryption
      // migration) — an encrypted envelope is longer than the plaintext
      // diagnosis it replaces, and 255 chars is not a safe bound for that.
      diagnosis: {
        type: DataTypes.TEXT,
        get() { return decryptField(this.getDataValue('diagnosis')); },
        set(value) { this.setDataValue('diagnosis', encryptField(value)); },
      },
      planId:           DataTypes.STRING,
      threadId:         DataTypes.STRING,
      // Denormalized off decision.{outcome,confidence} for cheap listing/
      // filtering without unpacking the JSONB decision column.
      decisionOutcome:     DataTypes.STRING,
      decisionConfidence:  DataTypes.FLOAT,
      decision:             encryptedJsonbField('decision'),
      policyEvidence:       DataTypes.JSONB,
      clinicalEvidence:     encryptedJsonbField('clinicalEvidence'),
      clinicalCriteriaEval: encryptedJsonbField('clinicalCriteriaEval'),
      documentEvidence:     DataTypes.JSONB,
      mlFeatures:           encryptedJsonbField('mlFeatures'),
      explanation:          encryptedJsonbField('explanation'),
      // Which LLM-calling stages were reused from this thread's prior
      // MongoDB checkpoint vs. actually recomputed (see policy-rag/
      // triage_graph.py's memoization layer) — kept in the audit trail so
      // "why didn't the evidence change on this resubmission" is always
      // answerable, not just visible in the live response.
      memoization:          DataTypes.JSONB,
      evaluatedBy:          DataTypes.STRING,
      // Real automated-processing timing (2026-08-20+, replaces the old
      // rule engine's frozen AuthorizationEvaluation.evaluationDurationMs,
      // which nothing has written to since that pipeline was retired).
      // Measures ONLY the automated evaluation itself — request received
      // through RAG + Agents + gates + ML producing APPROVE/PEND/
      // MORE_INFORMATION — never any later human nurse/admin review time,
      // which happens through a completely separate route (PATCH
      // /:id/review) at an arbitrary later time. Set together in
      // triageRoutes.js around the runTriage() call.
      processingStartedAt:   { type: DataTypes.DATE, allowNull: true },
      processingCompletedAt: { type: DataTypes.DATE, allowNull: true },
      processingDurationMs:  { type: DataTypes.INTEGER, allowNull: true },
    },
    {
      tableName: 'triage_evaluations',
      timestamps: true,
      indexes: [
        { fields: ['authorizationId'], name: 'idx_triage_evaluations_authorization_id' },
      ],
    }
  );
}
