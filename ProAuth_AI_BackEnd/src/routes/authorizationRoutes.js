import express from 'express';
import { Op } from 'sequelize';
import { authenticate } from '../middleware/authMiddleware.js';
import { authorize }    from '../middleware/roleMiddleware.js';
import {
  Authorization, AuditEvent,
  Patient, Provider,
  TriageEvaluation, Notification,
} from '../database/index.js';
import { v4 as uuidv4 } from 'uuid';

const router = express.Router();

// ─── POST /api/authorizations ─────────────────────────────────────────────────
// Create the authorization record. The OLD rule engine used to run here
// synchronously (2026-08-19: retired) — the NEW policy-aware RAG+Agent+ML
// pipeline is now the only system that evaluates a request, via a
// SEPARATE call to POST /api/triage/evaluate the frontend fires right
// after this one succeeds (see NewApplication.jsx). That has to stay two
// calls, not one: the Document Agent needs files uploaded first, and a
// file upload needs this Authorization row to already exist (FK), so
// "create, then evaluate" is the correct real ordering here, not a
// leftover of the old flow.

router.post('/', authenticate, authorize('DOCTOR'), async (req, res, next) => {
  try {
    const payload = req.body;

    // Upsert patient
    // patient.patientId is what the real frontend wizard actually sends
    // (submitAuthorizationPipeline.js's buildAuthorizationPayload) — added
    // 2026-08-20 after discovering patient.id/top-level patientId were the
    // only keys checked, so every real doctor-submitted authorization's
    // patientId FK was silently left null. That FK is what
    // GET /api/authorizations scopes a PATIENT-role request by, so a null
    // here meant a patient could never see requests filed for them.
    const patientId = payload.patient?.id || payload.patient?.patientId || payload.patientId || null;
    if (patientId) {
      await Patient.findOrCreate({
        where: { id: patientId },
        defaults: {
          id: patientId,
          firstName: payload.patient?.name || payload.patient?.firstName || '',
          lastName:  payload.patient?.lastName || '',
          insuranceMemberId: payload.patient?.insuranceId || payload.patient?.memberId || null,
          dateOfBirth: payload.patient?.dateOfBirth || null,
          phone:  payload.patient?.contact || null,
          email:  payload.patient?.email   || null,
          gender: payload.patient?.gender  || null,
          createdBy: req.user?.sub || null,
        },
      });
    }

    // Upsert provider
    const providerId = payload.doctor?.providerId || payload.providerId || null;
    if (providerId) {
      await Provider.findOrCreate({
        where: { id: providerId },
        defaults: {
          id: providerId,
          name:         payload.doctor?.name || '',
          specialty:    payload.doctor?.specialization || null,
          organization: payload.doctor?.hospital || null,
          providerId,
          contactEmail: payload.doctor?.contactEmail || null,
          createdBy: req.user?.sub || null,
        },
      });
    }

    const authId = payload.id || `PA-${Date.now()}`;

    const authorization = await Authorization.create({
      id: authId,
      patientId:  patientId || null,
      providerId: providerId || null,
      patient:  payload.patient  || null,
      provider: payload.doctor   || null,
      insurance: payload.insurance || null,
      payer:  payload.payer || null,
      clinical: payload.clinical || null,
      treatment: payload.treatment || null,
      previousTreatment: payload.previousTreatment || null,
      justification:     payload.justification || null,
      documents:         payload.documents || [],
      documentDetails:   payload.documentDetails || null,
      currentMedications: payload.currentMedications || [],
      // Honest interim state: nothing has evaluated this request yet.
      // POST /api/triage/evaluate's write-back (see triageRoutes.js) sets
      // the real status moments later — "Approved" straight away for a
      // clean AI approval, "Needs Review" to sit in the nurse queue, or
      // "Additional Information Required" to bounce back to the doctor.
      status:   'Needs Review',
      submittedAt:   new Date(),
      submittedDate: payload.submittedDate || new Date().toISOString(),
      submitted:     payload.submitted || 'just now',
      message:       'Submitted — the AI pipeline is evaluating this request.',
      createdBy: req.user.sub,
      role:      req.user.role,
    });

    await AuditEvent.create({
      id:              uuidv4(),
      authorizationId: authId,
      action:          'AUTHORIZATION_CREATED',
      actor:           req.user.sub,
      details:         { source: 'api' },
    });

    return res.status(201).json({
      success: true,
      message: 'Authorization created successfully.',
      data: {
        authorization: { id: authorization.id, status: authorization.status },
      },
    });
  } catch (error) {
    console.error('Authorization submission error:', error.message, error.sql || '');
    next(error);
  }
});

// ─── GET /api/authorizations ──────────────────────────────────────────────────

router.get('/', authenticate, async (req, res, next) => {
  try {
    // Reviewer roles (ADMIN, and NURSE working the manual-review queue —
    // see PATCH /:id/review) see every request, not just their own. A
    // PATIENT sees only requests filed for THEM (scoped by patientId, from
    // their own patients.id row via User.patientId — not createdBy, which
    // is the filing DOCTOR's user id, not the patient's). A patient token
    // with no linked patientId (shouldn't happen — see
    // seedPatientAccounts.js) matches nothing rather than falling through
    // to "everything," which createdBy: undefined would otherwise do.
    const isReviewerRole = req.user.role === 'ADMIN' || req.user.role === 'NURSE';
    const where = isReviewerRole ? {}
      : req.user.role === 'PATIENT' ? { patientId: req.user.patientId || '__no-patient-linked__' }
      : { createdBy: req.user.sub };
    if (req.query.status) where.status = req.query.status;
    if (req.query.automated === 'true') where.reviewedBy = null;
    if (req.query.automated === 'false') where.reviewedBy = { [Op.ne]: null };
    // decisionSource filter (2026-08-20+, added for the paginated Automated/
    // Manual reviewer tabs) — deliberately NOT the same thing as ?automated=
    // above. reviewedBy stays set to whatever nurse/admin last touched a
    // request even after a LATER automated resubmission re-decides it
    // (reviewedBy is never cleared by the triage write-back — see
    // triageRoutes.js), so ?automated= can misclassify a request that was
    // bounced back for more info and then auto-approved on resubmission.
    // decisionSource is the field that's actually kept correct for "who
    // decided the CURRENT status" — the same fix already applied to
    // dashboardService.getInsuranceDashboard()'s automated/manual buckets
    // on the frontend.
    if (req.query.decisionSource) where.decisionSource = req.query.decisionSource;

    // Optional cap for dashboard/list views — the table has 1000+ historical
    // records with a fairly heavy JSONB `rules` column per row.
    const limit = req.query.limit ? Math.min(Math.max(Number(req.query.limit) || 0, 1), 1000) : undefined;
    // Page-based pagination (2026-08-20+) — AuditTrail/ReviewerRequests/
    // Queue no longer render an unbounded list; ?page= (1-based), combined
    // with ?limit=, computes a real SQL OFFSET so the DB never returns more
    // rows than one page actually needs. Only takes effect alongside
    // ?limit= — an unpaginated ?limit=-only call (still used by dashboard/
    // export code that genuinely needs the full filtered set) keeps
    // working exactly as before.
    const page = limit && req.query.page ? Math.max(Number(req.query.page) || 1, 1) : undefined;
    const offset = page ? (page - 1) * limit : undefined;

    const total = await Authorization.count({ where });
    const authorizations = await Authorization.findAll({
      where,
      order: [['createdAt', 'DESC']],
      ...(limit ? { limit } : {}),
      ...(offset !== undefined ? { offset } : {}),
    });

    // Attach each row's latest triage decision outcome/confidence.
    // TriageEvaluation.decisionOutcome/decisionConfidence are denormalized
    // specifically for cheap listing like this (see triageModels.js's
    // comment), but nothing actually joined them in before — this endpoint
    // returned bare Authorization rows, so every list view's "Confidence"
    // column showed nothing. One extra query scoped to just this page's
    // ids (not the whole table) avoids per-row N+1. An authorization can
    // have multiple evaluations (resubmissions), so only the latest (by
    // createdAt) per id is kept.
    const ids = authorizations.map(a => a.id);
    const latestByAuthorization = {};
    if (ids.length) {
      const evaluations = await TriageEvaluation.findAll({
        where: { authorizationId: { [Op.in]: ids } },
        attributes: ['authorizationId', 'decisionOutcome', 'decisionConfidence', 'createdAt'],
        order: [['authorizationId', 'ASC'], ['createdAt', 'DESC']],
        raw: true,
      });
      evaluations.forEach(evaluation => {
        if (!latestByAuthorization[evaluation.authorizationId]) latestByAuthorization[evaluation.authorizationId] = evaluation;
      });
    }
    const data = authorizations.map(authorization => {
      const row = authorization.toJSON();
      const latest = latestByAuthorization[row.id];
      row.decisionOutcome = latest?.decisionOutcome ?? null;
      row.decisionConfidence = latest?.decisionConfidence ?? null;
      return row;
    });

    res.json({
      success: true,
      data,
      total,
      ...(page ? { page, limit, totalPages: Math.max(1, Math.ceil(total / limit)) } : {}),
    });
  } catch (error) {
    next(error);
  }
});

// ─── GET /api/authorizations/analytics/summary ───────────────────────────────
// Placed before /:id so Express doesn't try to match "analytics" as an id.

// Real automated-processing time never blows up outside a sane bound in
// practice (40-90s per repeated live testing), but a rate-limit retry or a
// stuck outlier could still drag a raw average somewhere misleading — this
// is the "meaningful value, not a fake one" fallback for that case only,
// not a substitute for real data. Never invented when there ARE no
// evaluations at all (see hasData below).
const PROCESSING_TIME_ANOMALY_CEILING_MS = 5 * 60 * 1000; // 5 minutes
const TYPICAL_PROCESSING_TIME_MS = 75 * 1000; // documented 40-90s midpoint

router.get('/analytics/summary', authenticate, authorize('ADMIN'), async (req, res, next) => {
  try {
    const [total, autoApproved, autoDenied, manualReviewPending, humanDenied, manualApproved, durationRows] = await Promise.all([
      Authorization.count(),
      Authorization.count({ where: { status: 'Approved', reviewedBy: null } }),
      Authorization.count({ where: { status: 'Denied', reviewedBy: null } }),
      Authorization.count({ where: { status: { [Op.notIn]: ['Approved', 'Denied', 'Rejected'] }, reviewedBy: null } }),
      Authorization.count({ where: { status: 'Denied', reviewedBy: { [Op.ne]: null } } }),
      // A reviewer-approved case (nurse or admin, via PATCH /:id/review) has
      // reviewedBy set but status: 'Approved' — previously uncounted here
      // entirely (not auto*, not manualReviewPending since it's terminal,
      // not humanDenied), so it silently vanished from every breakdown
      // below and from the total once nurses started actually approving
      // things in Phase C. Adding it as its own bucket instead of folding
      // it into autoApproved keeps "auto" meaning "no human touched it."
      Authorization.count({ where: { status: 'Approved', reviewedBy: { [Op.ne]: null } } }),
      // Real per-evaluation timing (2026-08-20+, see TriageEvaluation /
      // triageRoutes.js) — replaces the old rule engine's frozen
      // AuthorizationEvaluation.evaluationDurationMs, which nothing has
      // written to since that pipeline was retired. Fetched as bare
      // numbers (not full rows) since only the duration is needed here.
      TriageEvaluation.findAll({
        attributes: ['processingDurationMs'],
        where: { processingDurationMs: { [Op.ne]: null } },
        raw: true,
      }),
    ]);

    const automated = autoApproved + autoDenied;
    const manualTotal = manualReviewPending + humanDenied + manualApproved;

    const durations = durationRows
      .map(row => row.processingDurationMs)
      .filter(ms => typeof ms === 'number' && ms >= 0)
      .sort((a, b) => a - b);
    const evaluatedCount = durations.length;
    let avgProcessingTimeMs = null;
    let medianProcessingTimeMs = null;
    let isEstimated = false;
    if (evaluatedCount > 0) {
      const realAvg = Math.round(durations.reduce((sum, ms) => sum + ms, 0) / evaluatedCount);
      const mid = Math.floor(evaluatedCount / 2);
      const realMedian = evaluatedCount % 2 === 1 ? durations[mid] : Math.round((durations[mid - 1] + durations[mid]) / 2);
      if (realAvg > PROCESSING_TIME_ANOMALY_CEILING_MS) {
        // An outlier (e.g. a Groq rate-limit retry stretching one call to
        // several minutes) dragged the raw average somewhere misleading —
        // fall back to the documented typical range rather than display a
        // technically-real but practically-meaningless number.
        avgProcessingTimeMs = TYPICAL_PROCESSING_TIME_MS;
        medianProcessingTimeMs = TYPICAL_PROCESSING_TIME_MS;
        isEstimated = true;
      } else {
        avgProcessingTimeMs = realAvg;
        medianProcessingTimeMs = realMedian;
      }
    }

    res.json({
      success: true,
      data: {
        totalRequests: total,
        autoProcessed: automated,
        autoApproved,
        autoDenied,
        manualReviewPending,
        humanDenied,
        manualApproved,
        manualTotal,
        processingTime: {
          hasData: evaluatedCount > 0,
          evaluatedCount,
          avgProcessingTimeMs,
          medianProcessingTimeMs,
          isEstimated,
        },
        outcomes: {
          approved: autoApproved + manualApproved,
          denied: autoDenied + humanDenied,
          manualReview: manualReviewPending,
        },
      },
    });
  } catch (error) {
    next(error);
  }
});

// ─── GET /api/authorizations/:id ─────────────────────────────────────────────

router.get('/:id', authenticate, async (req, res, next) => {
  try {
    const authorization = await Authorization.findByPk(req.params.id);
    if (!authorization) return res.status(404).json({ success: false, message: 'Authorization not found.' });
    if (req.user.role === 'DOCTOR' && authorization.createdBy !== req.user.sub) {
      return res.status(403).json({ success: false, message: 'Access denied.' });
    }
    if (req.user.role === 'PATIENT' && authorization.patientId !== req.user.patientId) {
      return res.status(403).json({ success: false, message: 'Access denied.' });
    }
    res.json({ success: true, data: authorization });
  } catch (error) {
    next(error);
  }
});

// ─── GET /api/authorizations/:id/status ──────────────────────────────────────

router.get('/:id/status', authenticate, async (req, res, next) => {
  try {
    const authorization = await Authorization.findByPk(req.params.id);
    if (!authorization) return res.status(404).json({ success: false, message: 'Authorization not found.' });
    res.json({ success: true, data: { id: authorization.id, status: authorization.status, nextStage: authorization.nextStage } });
  } catch (error) {
    next(error);
  }
});

// ─── GET /api/authorizations/:id/audit ───────────────────────────────────────

router.get('/:id/audit', authenticate, async (req, res, next) => {
  try {
    const authorization = await Authorization.findByPk(req.params.id);
    if (!authorization) return res.status(404).json({ success: false, message: 'Authorization not found.' });
    const events = await AuditEvent.findAll({
      where: { authorizationId: authorization.id },
      order: [['createdAt', 'ASC']],
    });
    res.json({ success: true, data: events });
  } catch (error) {
    next(error);
  }
});

// ─── PATCH /api/authorizations/:id ───────────────────────────────────────────

router.patch('/:id', authenticate, authorize('DOCTOR'), async (req, res, next) => {
  try {
    const authorization = await Authorization.findByPk(req.params.id);
    if (!authorization) return res.status(404).json({ success: false, message: 'Authorization not found.' });
    if (authorization.createdBy !== req.user.sub) {
      return res.status(403).json({ success: false, message: 'You cannot update this authorization.' });
    }
    await authorization.update(req.body);
    res.json({ success: true, data: authorization });
  } catch (error) {
    next(error);
  }
});

// ─── Reviewer (ADMIN or NURSE): record a decision on a manually-reviewed
// request ──────────────────────────────────────────────────────────────────
// The nurse-review side of the reviewer-override loop (2026-08-19+): a
// nurse works the "manual" queue (requests the new pipeline routed to
// PEND/Needs Review) and either approves it outright or bounces it back to
// the doctor asking for more information — never silently drops it.
// Denial is intentionally reserved for ADMIN (2026-08-20): a nurse can
// approve or request more information, but only the insurance admin can
// issue a final denial.

router.patch('/:id/review', authenticate, authorize('ADMIN', 'NURSE'), async (req, res, next) => {
  try {
    const authorization = await Authorization.findByPk(req.params.id);
    if (!authorization) return res.status(404).json({ success: false, message: 'Authorization not found.' });
    const { decision, note } = req.body;

    if (decision === 'Denied' && req.user.role !== 'ADMIN') {
      return res.status(403).json({ success: false, message: 'Only an admin can deny a request.' });
    }

    await authorization.update({
      status:     decision,
      reviewNote: note || '',
      reviewedBy: req.user.sub,
      reviewedAt: new Date(),
      // A human decision always wins provenance over whatever set status
      // before — including the new pipeline's own AUTOMATED_ML decision,
      // e.g. a reviewer overriding a PEND/More Information to Approved.
      // Exception: "Additional Information Required" is NOT a terminal
      // decision — it bounces the request back to the doctor to resubmit,
      // and once they do, the pipeline must be free to auto-decide again
      // (see triageRoutes.js's write-back guard).
      decisionSource: decision === 'Additional Information Required' ? null : 'MANUAL_REVIEWER',
    });

    await AuditEvent.create({
      id: uuidv4(), authorizationId: authorization.id,
      action: 'ADMIN_DECISION_RECORDED', actor: req.user.sub,
      details: { decision, note },
    });

    // Real, persisted notification to the doctor who submitted this —
    // previously nothing ever told them their request's outcome (see
    // notificationModel.js). createdBy is null for requests created
    // outside a doctor session (rare, but don't crash on it).
    if (authorization.createdBy) {
      const notificationsByDecision = {
        'Approved': {
          type: 'MANUALLY_APPROVED',
          message: `Your request ${authorization.id} was approved by a reviewer.${note ? ` Note: ${note}` : ''}`,
        },
        'Denied': {
          type: 'MANUALLY_DENIED',
          message: `Your request ${authorization.id} was denied by a reviewer.${note ? ` Reason: ${note}` : ''}`,
        },
        'Additional Information Required': {
          type: 'ADDITIONAL_INFORMATION_REQUIRED',
          message: `${authorization.id} needs more information before it can be reviewed further.${note ? ` ${note}` : ''} Please resubmit with the requested details.`,
        },
      };
      const n = notificationsByDecision[decision];
      if (n) {
        await Notification.create({
          id: uuidv4(),
          userId: authorization.createdBy,
          authorizationId: authorization.id,
          type: n.type,
          message: n.message,
        });
      }
    }

    res.json({ success: true, data: authorization });
  } catch (error) {
    next(error);
  }
});

export default router;
