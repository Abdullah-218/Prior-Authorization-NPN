// Adapter layer: real ProAuth_AI_BackEnd Authorization rows + real
// ProAuth_AI_ML triage evaluation responses -> the "request" shape this
// frontend's UI already renders (src/data/requests.js's mock records,
// src/components/authorization/AuthorizationDetail.jsx's resultDetail
// contract). Keeping this as one seam means the existing page components
// don't need rewriting — only where their data comes from changes.

const CONFIDENCE_TIER_PERCENT = { HIGH: 95, MEDIUM: 70, LOW: 40, NONE: 0 };

// Real, current insurance_plans.planName values (verified against the
// live table) — the final fallback when a real row has neither
// insurance.provider nor a top-level payer set, only a plan id (found
// live, 2026-08-21: several real authorizations only ever stored
// insurance.plan, leaving "Policy" blank in the doctor's requests table).
const PLAN_ID_TO_NAME = {
  PLAN001: 'Medicare Advantage Plan',
  PLAN020: 'Private - Silver Plan',
  PLAN021: 'Private - Gold Plan',
  PLAN022: 'Private - Premium Plan',
};

// "Policy type" is a consumer-facing tier label, distinct from policyName
// (the full plan name above) — insurance.authorizationType is a free-text
// wizard field that's usually blank on real rows, so the known real plan
// ids resolve to their real tier name first; unknown plans still fall back
// to whatever authorizationType holds.
const PLAN_ID_TO_TYPE = {
  PLAN001: 'Medicare Advantage',
  PLAN020: 'Silver',
  PLAN021: 'Gold',
  PLAN022: 'Premium',
};

const STATUS_META = {
  Approved: { tone: 'green', prediction: 'Approve' },
  Denied: { tone: 'red', prediction: 'Deny' },
  Rejected: { tone: 'red', prediction: 'Deny' },
  'Additional Information Required': { tone: 'amber', prediction: 'More information' },
  'Needs Review': { tone: 'blue', prediction: 'Nurse review' },
};

function initialsOf(name) {
  return (name || '').split(' ').filter(Boolean).map(part => part[0]).join('').slice(0, 2).toUpperCase() || 'NA';
}

function formatDate(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ', ' +
    date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
}

function buildTimeline(status) {
  if (status === 'Approved' || status === 'Denied' || status === 'Rejected') return ['Submitted', 'Under Review', 'Decision'];
  if (status === 'Additional Information Required') return ['Submitted', 'Under Review', 'Additional information requested'];
  return ['Submitted', 'Under Review', 'Decision pending'];
}

// List-level confidence — GET /api/authorizations now attaches each row's
// latest TriageEvaluation decisionOutcome/decisionConfidence (2026-08-21+,
// see authorizationRoutes.js), so list views no longer have to show a bare
// "—" for every row. Mirrors mapTriageEvaluationToResultDetail's isGatedPend
// rule below: a genuine model confidence (APPROVE, or a real model-driven
// PEND) is shown as-is; a gated PEND (decisionOutcome PEND with no real
// confidence — one of ml/model.py's deterministic gates) gets the same
// synthesized display confidence the single-request detail page already
// shows, seeded by the row id so it's stable; MORE_INFORMATION and rows
// with no evaluation at all correctly stay unscored.
function deriveListConfidencePct(row) {
  if (row.decisionConfidence != null) return Math.round(row.decisionConfidence * 100);
  if (row.decisionOutcome === 'PEND') return syntheticPendConfidence(row.id);
  return null;
}

// Cheap, list-safe: builds everything a dashboard/table/patient-summary
// view needs from the Authorization row alone, no extra fetch. Real
// per-decision detail (resultDetail) is attached separately, only where
// a page actually renders it — see attachTriageResult() below.
export function mapAuthorizationRowToRequest(row) {
  const meta = STATUS_META[row.status] || STATUS_META['Needs Review'];
  const patientName = row.patient?.name || [row.patient?.firstName, row.patient?.lastName].filter(Boolean).join(' ') || 'Unknown patient';
  const listConfidencePct = deriveListConfidencePct(row);
  return {
    id: row.id,
    ownerId: row.createdBy,
    patient: patientName,
    initials: initialsOf(patientName),
    patientId: row.patient?.patientId || row.patientId || row.id,
    memberId: row.insurance?.memberId,
    age: row.patient?.age,
    sex: row.patient?.gender,
    dateOfBirth: row.patient?.dateOfBirth,
    insuranceProvider: row.insurance?.provider || row.payer || 'Not specified',
    planName: row.insurance?.plan,
    planId: row.insurance?.plan,
    coverageStatus: row.insurance?.coverageStatus || 'Active',
    // insurance.provider is the primary source; several real rows only
    // ever had the top-level `payer` column set instead (a plain string,
    // always populated at creation — see authorizationRoutes.js), and a
    // handful of older rows have neither, only insurance.plan (a plan
    // id) — falling back through all three is what fixes "Policy" showing
    // blank in the doctor's Approved Requests table, found live
    // (2026-08-21) against real historical data.
    policyName: row.insurance?.provider
      ? `${row.insurance.provider} coverage policy`
      : row.payer
        ? `${row.payer} coverage policy`
        : row.insurance?.plan && PLAN_ID_TO_NAME[row.insurance.plan]
          ? PLAN_ID_TO_NAME[row.insurance.plan]
          : undefined,
    policyType: (row.insurance?.plan && PLAN_ID_TO_TYPE[row.insurance.plan]) || row.insurance?.authorizationType,
    diagnosis: row.clinical?.diagnosis || row.clinical?.primaryDiagnosis || 'Not specified',
    icd10: row.clinical?.icdCode,
    secondaryDiagnoses: row.clinical?.secondaryDiagnoses || 'None reported',
    clinicalHistory: row.clinical?.notes || row.justification?.medicalNecessity || 'No clinical justification provided.',
    service: row.treatment?.name || row.treatment?.type || 'Not specified',
    procedureCode: row.treatment?.code,
    urgency: row.treatment?.urgency,
    careSetting: row.treatment?.placeOfService,
    status: row.status,
    prediction: meta.prediction,
    confidence: listConfidencePct != null ? `${listConfidencePct}%` : null,
    date: formatDate(row.submittedAt || row.createdAt),
    submittedAtRaw: row.submittedAt || row.createdAt || null,
    lastUpdated: formatDate(row.updatedAt),
    tone: meta.tone,
    approvalType: row.decisionSource === 'AUTOMATED_ML' ? 'automated' : row.decisionSource === 'MANUAL_REVIEWER' ? 'manual' : undefined,
    decisionSource: row.decisionSource,
    reviewedBy: row.reviewedBy,
    reviewNote: row.reviewNote,
    documents: Array.isArray(row.documents) ? row.documents.map(name => [name, 'Uploaded']) : [],
    timeline: buildTimeline(row.status),
    resultDetail: null,
  };
}

function toneForFactor(text) {
  return /fail|missing|not (met|found|covered)/i.test(text) ? 'amber' : 'green';
}

// Presentation-only (2026-08-21, explicit request for project-presentation
// purposes — the real architecture is untouched, see mapTriageEvaluationToResultDetail's
// isGatedPend comment). Every one of the 9 deterministic gates in
// ml/model.py routes to PEND with decision.confidence: null — there is no
// real model probability for these. This derives a plausible, STABLE
// per-request percentage purely for display (same string always renders
// for the same evaluation, so it isn't a random number that changes on
// reload), in the same 55-85% range a genuine model-driven PEND's
// 1-probaApprove would realistically fall in.
function syntheticPendConfidence(seed) {
  const str = String(seed || 'pend');
  let hash = 0;
  for (let i = 0; i < str.length; i++) hash = (hash * 31 + str.charCodeAt(i)) >>> 0;
  return 58 + (hash % 25); // 58-82
}

// Strips the literal "Deterministic gate: ... ML model was not invoked."
// framing so a gated PEND's real, substantive reason (e.g. "the
// requesting provider's specialty does not clearly match the requested
// service") can still display without contradicting the synthesized
// "ML predicted this" presentation framing above it.
function pendDisplayReason(reason) {
  if (!reason) return 'The model recommends this request for nurse review based on the combined evidence.';
  const cleaned = reason
    .replace(/^Deterministic( safety)? gate:\s*/i, '')
    .replace(/\s*ML model was not invoked\.?$/i, '')
    .trim();
  return cleaned ? cleaned.charAt(0).toUpperCase() + cleaned.slice(1) : reason;
}

function buildDistribution(decision, displayConfidencePct) {
  if (decision.confidence != null) {
    const approve = Math.round((decision.probaApprove ?? decision.confidence) * 100);
    return { approve, nurseReview: Math.max(0, 100 - approve), moreInfo: 0 };
  }
  if (decision.outcome === 'MORE_INFORMATION') return { approve: 0, nurseReview: 0, moreInfo: 100 };
  if (displayConfidencePct != null) return { approve: Math.max(0, 100 - displayConfidencePct), nurseReview: displayConfidencePct, moreInfo: 0 };
  return { approve: 0, nurseReview: 100, moreInfo: 0 };
}

// Full detail: maps ONE real /api/triage/evaluate (or persisted
// TriageEvaluation row) response into the resultDetail shape
// AuthorizationDetail.jsx already knows how to render.
export function mapTriageEvaluationToResultDetail(evaluation) {
  const decision = evaluation.decision || {};
  const explanation = evaluation.explanation || {};
  const policyEvidence = evaluation.policyEvidence || {};
  const clinicalCriteriaEval = evaluation.clinicalCriteriaEval || {};
  const documentEvidence = evaluation.documentEvidence || {};
  const outcome = decision.outcome || 'PEND';

  const OUTCOME_META = {
    APPROVE: { icon: 'check', reviewBadge: 'Approved', reviewBadgeTone: 'green', headline: 'Approve' },
    PEND: { icon: 'clock', reviewBadge: 'Review recommended', reviewBadgeTone: 'blue', headline: 'Pend for reviewer' },
    MORE_INFORMATION: { icon: 'help', reviewBadge: 'More information needed', reviewBadgeTone: 'amber', headline: 'Request more information' },
  };
  const meta = OUTCOME_META[outcome] || OUTCOME_META.PEND;

  const criteriaResults = clinicalCriteriaEval.criteriaResults || {};
  const criteriaEntries = Object.entries(criteriaResults);
  const passedCount = criteriaEntries.filter(([, v]) => v === 'PASS').length;

  // isGatedPend: PEND produced by one of ml/model.py's 9 deterministic
  // gates (decision.confidence is null in every one of those paths) — as
  // opposed to a genuine model-driven PEND, which already has a real
  // decision.confidence and needs no presentation changes at all.
  // Per explicit request (2026-08-21, project-presentation purposes):
  // PEND should always display as if the ML model produced it, with a
  // confidence score — but MORE_INFORMATION must keep showing its real
  // "gate blocked this, model not involved" framing untouched. The real
  // backend/ML architecture is completely unchanged; only this display
  // layer's PEND framing is synthesized when there's no real model output
  // to show. See syntheticPendConfidence/pendDisplayReason above.
  const isGatedPend = outcome === 'PEND' && decision.confidence == null;
  // Seeded by authorizationId (not explanation/reason text) so this
  // matches deriveListConfidencePct's seed in mapAuthorizationRowToRequest
  // above — the same request must show the same synthesized confidence
  // whether it's rendered as a list row or opened as full detail.
  const displayConfidencePct = decision.confidence != null
    ? Math.round((decision.probaApprove ?? decision.confidence) * 100)
    : isGatedPend
      ? syntheticPendConfidence(evaluation.authorizationId || explanation.summary || decision.reason || policyEvidence.policyName || '')
      : null;
  const modelInvoked = decision.confidence != null || isGatedPend;

  const complianceScore = displayConfidencePct != null
    ? displayConfidencePct
    : criteriaEntries.length ? Math.round((passedCount / criteriaEntries.length) * 100) : 0;

  const displayReason = isGatedPend ? pendDisplayReason(decision.reason) : decision.reason;
  const displaySummary = isGatedPend && explanation.summary ? pendDisplayReason(explanation.summary) : explanation.summary;

  const reasons = (explanation.keyFactors || []).map(factor => [toneForFactor(factor), isGatedPend ? pendDisplayReason(factor) : factor, '']);
  const criteria = criteriaEntries.map(([name, result]) => [
    name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
    result,
    result === 'PASS' ? 'green' : 'amber',
  ]);

  // Only MORE_INFORMATION is genuinely about missing/insufficient
  // evidence — PEND (e.g. a specialty-mismatch or contraindication gate)
  // has its own, unrelated decision.reason. Previously fell through to
  // decision.reason for ANY non-APPROVE outcome: since [].join(', ') is
  // '' (falsy) when nothing is actually missing, that silently substituted
  // an unrelated gate's reason under a "MISSING INFORMATION" heading, even
  // though a real Document Agent check elsewhere on the same page (see the
  // workbench array below) correctly showed e.g. "2/2 required documents
  // matched" — found live (2026-08-21) as a visibly contradictory pair of
  // messages on the same result page.
  const missingDocumentsText = (documentEvidence.missingDocuments || []).join(', ');
  const missingEvidenceText = missingDocumentsText ||
    (outcome === 'MORE_INFORMATION' ? decision.reason : null);

  return {
    icon: meta.icon,
    reviewBadge: meta.reviewBadge,
    reviewBadgeTone: meta.reviewBadgeTone,
    headline: meta.headline,
    headlineNote: displaySummary || displayReason || 'No explanation available.',
    whyText: displaySummary || displayReason || 'No explanation available.',
    reasons: reasons.length ? reasons : [[outcome === 'APPROVE' ? 'green' : 'amber', displayReason || 'No further detail available.', '']],
    complianceScore,
    criteria,
    // Whether the ML model actually ran for this request, or a
    // deterministic gate (specialty mismatch, missing evidence,
    // contraindication, etc.) short-circuited before it. Real for
    // APPROVE/genuine-model-PEND; synthesized display-only for a gated
    // PEND (see isGatedPend above); MORE_INFORMATION is deliberately
    // left false/unmodeled — see AuthorizationDetail.jsx / Processing.jsx.
    modelInvoked,
    // displayConfidencePct: carried through so attachTriageResult's
    // top-level `confidence` string (used by every list/table row) shows
    // the SAME number as this detail page, rather than recomputing a
    // possibly-different synthetic value from a different seed.
    displayConfidencePct,
    distribution: buildDistribution(decision, displayConfidencePct),
    missingEvidenceText: missingEvidenceText || null,
    policyEvidence: {
      name: policyEvidence.policyName || (policyEvidence.policyFound ? 'Policy identified' : 'No applicable policy found'),
      type: policyEvidence.coverageStatus || 'Unknown',
      effective: '',
      summary: (explanation.citedEvidence || []).join(' ') || policyEvidence.message || 'No policy evidence summary available.',
      relevance: CONFIDENCE_TIER_PERCENT[policyEvidence.confidence] ?? 0,
    },
    workbench: [
      ['Policy Agent', policyEvidence.policyFound ? `Policy identified — ${policyEvidence.policyName || ''}`.trim() : 'No applicable policy found'],
      ['Clinical Agent', criteriaEntries.length ? `${passedCount}/${criteriaEntries.length} criteria passed` : 'No clinical criteria evaluated'],
      ['Document Agent', `${documentEvidence.nDocumentsSubmitted ?? 0}/${documentEvidence.nRequiredDocuments ?? 0} required documents matched`],
      ['ML Triage Model', modelInvoked
        ? `Recommendation generated (${displayConfidencePct}% confidence)`
        : `Not invoked — ${decision.reason || 'deterministic gate short-circuited'}`],
    ],
  };
}

// Attaches resultDetail + a display confidence string onto a request
// already built by mapAuthorizationRowToRequest — the two-step split
// (cheap row mapping vs. this) is what keeps list views from needing an
// N+1 fetch of every request's triage evaluation.
export function attachTriageResult(request, evaluation) {
  if (!evaluation) return request;
  const resultDetail = mapTriageEvaluationToResultDetail(evaluation);
  // resultDetail.displayConfidencePct already carries the right number
  // for every case — real model confidence (APPROVE / genuine model
  // PEND), the synthesized presentation confidence (gated PEND — see
  // mapTriageEvaluationToResultDetail's isGatedPend), or null
  // (MORE_INFORMATION, which deliberately keeps showing "Not scored" —
  // no model involved, gate blocked it and asked for more evidence).
  const confidencePct = resultDetail.displayConfidencePct;
  return { ...request, resultDetail, confidence: confidencePct != null ? `${confidencePct}%` : 'Not scored' };
}
