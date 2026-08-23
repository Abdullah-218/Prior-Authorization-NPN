/**
 * Triage Routes — the NEW policy-aware agents+RAG+ML pipeline, exposed
 * over the Node API. This is the ONLY system that evaluates a request
 * (2026-08-19+ — the old rule engine + XGBoost model was retired; see
 * authorizationRoutes.js's POST / comment).
 */
import express from 'express';
import { v4 as uuidv4 } from 'uuid';
import { authenticate } from '../middleware/authMiddleware.js';
import { authorize } from '../middleware/roleMiddleware.js';
import { runTriage } from '../services/triageService.js';
import { TriageEvaluation, AuditEvent, Authorization, Notification } from '../database/index.js';

const router = express.Router();

// Same status vocabulary StatusBadge.jsx / ReviewApplication.jsx already
// use for the OLD rule engine's PATCH /:id/review — reusing it (rather
// than inventing APPROVE/PEND/MORE_INFORMATION as new status strings)
// means every existing status-driven UI (dashboards, badges, filters)
// understands an automated triage decision without any changes.
// MORE_INFORMATION -> the SAME "Additional Information Required" string a
// nurse's manual request-more-info decision uses (PATCH /:id/review) — one
// vocabulary for "the doctor needs to act and resubmit," whether the AI's
// own deterministic gate or a human nurse is the one asking.
const TRIAGE_OUTCOME_TO_STATUS = {
  APPROVE: 'Approved',
  PEND: 'Needs Review',
  MORE_INFORMATION: 'Additional Information Required',
};

// ─── POST /api/triage/evaluate ─────────────────────────────────────────────
// Runs a request through Policy Agent + Clinical Agent + the deterministic
// aggregator + the trained ML Triage Model + the Companion Agent, and
// returns the full evidence trail alongside the decision and its
// plain-language explanation. Also persists the full result (evaluation +
// audit trail) — see TriageEvaluation's docstring for why that matters.

router.post('/evaluate', authenticate, authorize('ADMIN', 'DOCTOR'), async (req, res, next) => {
  try {
    // The Authorization ID doubles as the LangGraph thread_id whenever
    // one isn't explicitly given — this is what makes the Python
    // pipeline's MongoDB checkpoint memoization actually work (see
    // policy-rag/triage_graph.py's module docstring): every evaluation of
    // the SAME PA request, including every resubmission, shares one
    // checkpoint history instead of each call starting a fresh, unrelated
    // thread. Set here (not in every frontend call site) so it's
    // impossible to forget.
    const requestBody = {
      ...req.body,
      threadId: req.body.threadId || req.body.authorizationId || undefined,
    };
    // Real automated-processing timing (2026-08-20+) — brackets exactly
    // the automated pipeline (RAG + Agents + gates + ML), never any later
    // human review time, which is a separate route entirely (PATCH
    // /:id/review). See TriageEvaluation's docstring.
    const processingStartedAt = new Date();
    const result = await runTriage(requestBody);
    const processingCompletedAt = new Date();
    const processingDurationMs = processingCompletedAt.getTime() - processingStartedAt.getTime();
    const evaluationId = uuidv4();

    // Persisting must never take down the feature itself — the doctor
    // still needs to see a real evaluation even if the audit-trail write
    // fails for some unrelated DB reason. Logged loudly (not swallowed)
    // since a silent persistence failure would look identical to success.
    try {
      const decision = result.decision || {};
      const authorizationId = req.body.authorizationId || null;

      await TriageEvaluation.create({
        id: evaluationId,
        authorizationId,
        requestedService: req.body.requestedService || null,
        diagnosis: req.body.diagnosis || null,
        planId: req.body.planId || null,
        threadId: requestBody.threadId || null,
        decisionOutcome: decision.outcome || null,
        decisionConfidence: decision.confidence ?? null,
        decision,
        policyEvidence: result.policyEvidence || null,
        clinicalEvidence: result.clinicalEvidence || null,
        clinicalCriteriaEval: result.clinicalCriteriaEval || null,
        documentEvidence: result.documentEvidence || null,
        mlFeatures: result.mlFeatures || null,
        explanation: result.explanation || null,
        memoization: result.memoization || null,
        evaluatedBy: req.user.sub,
        processingStartedAt,
        processingCompletedAt,
        processingDurationMs,
      });

      if (authorizationId) {
        await AuditEvent.create({
          id: uuidv4(),
          authorizationId,
          action: 'TRIAGE_EVALUATION_COMPLETED',
          actor: req.user.sub,
          details: { evaluationId, decision: decision.outcome, confidence: decision.confidence },
        });

        // Closes the loop this pipeline was missing entirely: its own
        // decision now actually becomes the Authorization's real status —
        // an ML APPROVE goes straight to "Approved" (no human needed), a
        // PEND becomes a real "Needs Review" a nurse will see in their
        // queue, MORE_INFORMATION bounces straight back to the doctor.
        // Gated on decisionSource, not reviewedBy — a nurse's "Additional
        // Information Required" decision resets decisionSource to null
        // (see PATCH /:id/review) specifically so THIS automated write-back
        // can fire again once the doctor resubmits with better evidence.
        // Only a human's terminal decision (decisionSource ===
        // 'MANUAL_REVIEWER', i.e. Approved/Denied) permanently blocks it.
        const targetStatus = TRIAGE_OUTCOME_TO_STATUS[decision.outcome];
        if (targetStatus) {
          const authorization = await Authorization.findByPk(authorizationId);
          if (authorization && authorization.decisionSource !== 'MANUAL_REVIEWER') {
            await authorization.update({
              status: targetStatus,
              decisionSource: 'AUTOMATED_ML',
              message: result.explanation?.summary || authorization.message,
            });

            // Only APPROVE and MORE_INFORMATION are directly actionable by
            // the doctor right now (celebrate, or go fix something) — PEND
            // just means "sitting in the nurse's queue," nothing for the
            // doctor to do yet, so no notification for that one.
            if (authorization.createdBy && decision.outcome !== 'PEND') {
              const messages = {
                APPROVE: `Great news — your request ${authorizationId} was automatically approved.`,
                MORE_INFORMATION: `${authorizationId} needs more information before it can proceed. ${result.explanation?.summary || ''} Please resubmit with the requested details.`,
              };
              await Notification.create({
                id: uuidv4(),
                userId: authorization.createdBy,
                authorizationId,
                type: decision.outcome === 'APPROVE' ? 'AUTO_APPROVED' : 'ADDITIONAL_INFORMATION_REQUIRED',
                message: messages[decision.outcome],
              });
            }
          }
        }
      }
    } catch (persistErr) {
      console.error('[TriageRoutes] Failed to persist triage evaluation:', persistErr.message);
    }

    res.json({ success: true, data: { ...result, evaluationId } });
  } catch (error) {
    if (error.message?.includes('are required')) {
      // Same real-world bounce-back the old rule engine's mandatory-field
      // hard block used to give (2026-08-19+ fix) — the request genuinely
      // can't be evaluated without these fields, so it goes back to the
      // doctor as "Additional Information Required" instead of leaving the
      // Authorization silently stuck at whatever status it had before.
      // Same decisionSource-gated precedent as the write-back on a real
      // MORE_INFORMATION decision above: a human's terminal decision
      // (MANUAL_REVIEWER) still wins over this.
      const authorizationId = req.body.authorizationId || null;
      if (authorizationId) {
        try {
          const authorization = await Authorization.findByPk(authorizationId);
          if (authorization && authorization.decisionSource !== 'MANUAL_REVIEWER') {
            await authorization.update({
              status: 'Additional Information Required',
              decisionSource: 'AUTOMATED_ML',
              message: `${error.message} Please resubmit with the requested details.`,
            });

            await AuditEvent.create({
              id: uuidv4(),
              authorizationId,
              action: 'TRIAGE_EVALUATION_INCOMPLETE',
              actor: req.user.sub,
              details: { reason: error.message },
            });

            if (authorization.createdBy) {
              await Notification.create({
                id: uuidv4(),
                userId: authorization.createdBy,
                authorizationId,
                type: 'ADDITIONAL_INFORMATION_REQUIRED',
                message: `${authorizationId} needs more information before it can be evaluated: ${error.message} Please resubmit with the requested details.`,
              });
            }
          }
        } catch (persistErr) {
          console.error('[TriageRoutes] Failed to record incomplete-evaluation write-back:', persistErr.message);
        }
      }
      return res.status(400).json({ success: false, message: error.message });
    }
    next(error);
  }
});

// ─── GET /api/triage/evaluations/:authorizationId ──────────────────────────
// The actual payoff of persisting the above — look up what this pipeline
// decided on a given request and why, after the fact. Most recent first.

router.get('/evaluations/:authorizationId', authenticate, authorize('ADMIN', 'NURSE', 'DOCTOR', 'PATIENT'), async (req, res, next) => {
  try {
    // DOCTOR/PATIENT only ever see evaluations for their own authorization
    // (same ownership rule as GET /api/authorizations/:id) — ADMIN/NURSE
    // are reviewer roles and stay unrestricted.
    if (req.user.role === 'DOCTOR' || req.user.role === 'PATIENT') {
      const authorization = await Authorization.findByPk(req.params.authorizationId);
      if (!authorization) return res.status(404).json({ success: false, message: 'Authorization not found.' });
      const owns = req.user.role === 'DOCTOR' ? authorization.createdBy === req.user.sub : authorization.patientId === req.user.patientId;
      if (!owns) return res.status(403).json({ success: false, message: 'Access denied.' });
    }

    const evaluations = await TriageEvaluation.findAll({
      where: { authorizationId: req.params.authorizationId },
      order: [['createdAt', 'DESC']],
    });
    res.json({ success: true, data: evaluations });
  } catch (error) {
    next(error);
  }
});

export default router;
