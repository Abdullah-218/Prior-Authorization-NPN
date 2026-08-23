import { requests } from '../data/requests';
import { attachTriageResult } from './requestMapper';

// A PATIENT-role GET /api/authorizations is already scoped server-side to
// just this patient's own rows (authorizationRoutes.js filters by
// req.user.patientId) — so unlike the old mock version, there's no
// ownerId-based filtering to do here at all; requests[] IS this patient's
// own list once useLiveRequests() has populated it. userId params are kept
// on the exported functions only so ReadonlyViews.jsx's call sites don't
// need to change shape.
function toReadonlyRequest(request) {
  if (!request) return null;
  const result = request.resultDetail;
  return {
    ...request,
    // No real per-authorization "policyId"/"policy effective date" concept
    // exists on an Authorization row (that's a RAG policy-corpus concept,
    // not a member-facing one) — planId is the closest real equivalent;
    // effective date is left blank rather than invented.
    policyId: request.planId,
    policyEffective: '',
    decision: result?.headline || request.prediction || request.status,
    decisionExplanation: result?.whyText || result?.headlineNote || 'A decision explanation will appear once the AI evaluation completes.',
    missingInformation: result?.missingEvidenceText || null,
    stage: result ? 'Decision' : 'Evidence analysis',
  };
}

export const authorizationService = {
  getReadonlySummary() {
    const readonlyRequests = requests.map(toReadonlyRequest);
    const todayRequests = readonlyRequests.filter(request => request.date?.startsWith('Today'));
    return {
      requestsToday: todayRequests.length,
      approved: readonlyRequests.filter(request => request.status === 'Approved').length,
      nurseReview: readonlyRequests.filter(request => request.prediction === 'Nurse review').length,
      moreInformation: readonlyRequests.filter(request => request.prediction === 'More information').length,
      requests: readonlyRequests,
      pipeline: readonlyRequests[0]
        ? { completed: readonlyRequests[0].stage === 'Decision' ? 6 : 4, inProgress: readonlyRequests[0].stage === 'Decision' ? 0 : 1, currentStage: readonlyRequests[0].stage }
        : { completed: 0, inProgress: 0, currentStage: null },
    };
  },
  getReadonlyAuthorization(_userId, requestId) {
    const request = requests.find(item => item.id === requestId);
    return request ? toReadonlyRequest(request) : null;
  },
  // Re-derives the readonly view (decision/decisionExplanation/etc.) after
  // a lazily-fetched triage evaluation attaches resultDetail — same
  // fallback pattern as ResultPage.jsx/ReviewerAuthorization.jsx, needed
  // because GET /api/authorizations' list response never includes
  // resultDetail on its own.
  toReadonlyWithEvaluation(readonlyRequest, evaluation) {
    return toReadonlyRequest(attachTriageResult(readonlyRequest, evaluation));
  },
  // Most recent request only — used by the single-record category pages
  // (Profile, My Policy, Diagnosis, My Request, Decision, Documents,
  // Timeline). Backend already returns createdAt DESC, so requests[0] is
  // the latest; see ReadonlyDashboard for the full history list.
  getReadonlyRecord() {
    return requests[0] ? toReadonlyRequest(requests[0]) : null;
  },
  getReadonlyAnalytics() {
    return { requestsToday: 128, approved: 76, nurseReview: 31, moreInformation: 21 };
  },
};
