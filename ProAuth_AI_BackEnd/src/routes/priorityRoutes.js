/**
 * Priority Routes — nurse queue prioritization
 *
 * Downstream of the existing triage pipeline, never upstream of it: only
 * ranks requests the triage pipeline has ALREADY decided are PEND (status
 * 'Needs Review' — see triageRoutes.js's TRIAGE_OUTCOME_TO_STATUS). Does
 * not re-run any agent, does not touch the original decision. See
 * ProAuth_AI_ML/priority_intelligence/README.md.
 */
import express from 'express';
import { Op } from 'sequelize';
import { authenticate } from '../middleware/authMiddleware.js';
import { authorize } from '../middleware/roleMiddleware.js';
import { Authorization, TriageEvaluation } from '../database/index.js';
import { runPriorityRerank } from '../services/priorityService.js';

const router = express.Router();

// ─── GET /api/priority/queue ────────────────────────────────────────────
// Ranks every currently-pending ("Needs Review") authorization by nurse
// priority. Reviewer roles only (ADMIN/NURSE) — same access as the rest
// of the review queue.
router.get('/queue', authenticate, authorize('ADMIN', 'NURSE'), async (req, res, next) => {
  try {
    const pendingAuthorizations = await Authorization.findAll({
      where: { status: 'Needs Review' },
      order: [['createdAt', 'DESC']],
    });

    if (!pendingAuthorizations.length) {
      return res.json({ success: true, data: [] });
    }

    const authorizationIds = pendingAuthorizations.map((a) => a.id);
    // One query for every candidate evaluation, most-recent-first — the
    // Map below then keeps only the FIRST (= latest) evaluation seen per
    // authorization, giving "latest evaluation per authorization" without
    // an N+1 query per pending case.
    const evaluations = await TriageEvaluation.findAll({
      where: { authorizationId: { [Op.in]: authorizationIds } },
      order: [['createdAt', 'DESC']],
    });
    const latestEvaluationByAuthorization = new Map();
    for (const evaluation of evaluations) {
      if (!latestEvaluationByAuthorization.has(evaluation.authorizationId)) {
        latestEvaluationByAuthorization.set(evaluation.authorizationId, evaluation);
      }
    }

    // A "Needs Review" row with no triage evaluation on record shouldn't
    // normally happen, but isn't sent to the ranker with fabricated
    // scores if it does — it's surfaced separately instead, unranked but
    // never silently dropped from what the nurse sees.
    const cases = [];
    const unrankable = [];
    for (const authorization of pendingAuthorizations) {
      const evaluation = latestEvaluationByAuthorization.get(authorization.id);
      const featureVector = evaluation?.mlFeatures?.featureVector;
      if (!featureVector) {
        unrankable.push(authorization.id);
        continue;
      }
      cases.push({
        requestId: authorization.id,
        policyScore: featureVector.policy_score,
        documentationScore: featureVector.documentation_score,
        clinicalEvidenceScore: featureVector.clinical_evidence_score,
        numCriteriaMissing: evaluation.mlFeatures.numCriteriaMissing ?? 0,
        urgency: authorization.treatment?.urgency || '',
        careSetting: authorization.treatment?.placeOfService || '',
        submittedAt: authorization.submittedAt,
      });
    }

    const ranked = cases.length ? await runPriorityRerank(cases) : [];
    const rankedByAuthorization = new Map(ranked.map((r) => [r.authorizationId, r]));

    const data = [
      ...pendingAuthorizations
        .filter((a) => rankedByAuthorization.has(a.id))
        .map((a) => rankedByAuthorization.get(a.id))
        .sort((a, b) => a.queueRank - b.queueRank),
      ...unrankable.map((authorizationId) => ({
        authorizationId,
        priorityScore: null,
        priorityTier: null,
        queueRank: null,
        reasonCodes: ['No triage evaluation on record yet — cannot be ranked.'],
      })),
    ];

    res.json({ success: true, data });
  } catch (error) {
    next(error);
  }
});

export default router;
