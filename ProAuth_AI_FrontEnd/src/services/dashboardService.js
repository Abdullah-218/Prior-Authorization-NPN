import { requests } from '../data/requests';
import { patientService } from './patientService';

export const dashboardService = {
  getDoctorDashboard(userId) {
    const ownRequests = requests.filter(request => request.ownerId === userId);
    const sevenDaysAgo = Date.now() - 7 * 24 * 60 * 60 * 1000;
    return {
      requests: ownRequests,
      approvedRequests: ownRequests.filter(request => request.status === 'Approved'),
      moreInformationRequests: ownRequests.filter(request => request.status === 'Additional Information Required' || request.prediction === 'More information'),
      // approvalType only tracks WHO decided (automated vs. a human
      // reviewer) — same distinction getInsuranceDashboard() below already
      // relies on, scoped here to just this doctor's own requests for
      // their dashboard's activity breakdown.
      automatedApprovals: ownRequests.filter(request => request.status === 'Approved' && request.approvalType === 'automated'),
      manualApprovals: ownRequests.filter(request => request.status === 'Approved' && request.approvalType === 'manual'),
      needsReviewRequests: ownRequests.filter(request => request.status === 'Needs Review'),
      requestsThisWeek: ownRequests.filter(request => request.submittedAtRaw && new Date(request.submittedAtRaw).getTime() >= sevenDaysAgo),
      patients: patientService.getPatients(userId)
    };
  },
  getNurseDashboard() {
    return { requests: requests.filter(request => request.prediction === 'Nurse review' || request.status === 'Needs Review') };
  },
  getInsuranceDashboard() {
    // approvalType only tracks WHO decided (automated vs. a human reviewer),
    // not WHAT they decided — a manually DENIED request also has
    // approvalType 'manual', and an automated PEND/MORE_INFORMATION also
    // has approvalType 'automated'. Every bucket below pairs approvalType
    // with the actual status so "Automated Approved" and "Manually
    // approved" only ever contain real approvals, never a mix of
    // approvals/denials/still-pending requests.
    // "Needs Review" is the only status genuinely awaiting an admin
    // decision — "Additional Information Required" has already been
    // routed back to the doctor to resubmit (see triageRoutes.js /
    // authorizationRoutes.js's decisionSource reset on that outcome), and
    // "Denied"/"Approved" are terminal, so none of those belong in the
    // admin's actionable pending queue.
    return {
      requests,
      automatedApprovals: requests.filter(request => request.status === 'Approved' && request.approvalType === 'automated'),
      manualApprovals: requests.filter(request => request.status === 'Approved' && request.approvalType === 'manual'),
      pendingCases: requests.filter(request => request.status === 'Needs Review'),
      deniedRequests: requests.filter(request => request.status === 'Denied' || request.status === 'Rejected')
    };
  },
  getUserDashboard(userId) {
    return { requests: requests.filter(request => request.ownerId === userId) };
  }
};
