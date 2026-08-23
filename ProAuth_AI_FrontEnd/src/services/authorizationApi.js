import { apiClient } from './apiClient';

// Real implementation of the shape this module always declared (its own
// prior comment: "Mock contract mirroring the future Express API. Replace
// internals with apiClient calls when the backend is available.") — the
// backend is available now.
export const authorizationApi = {
  async getAuthorizations() {
    // GET /api/authorizations is already scoped server-side by role
    // (DOCTOR sees only their own createdBy rows; ADMIN/NURSE see all) —
    // no query params needed here for that.
    return apiClient.get('/authorizations');
  },
  // Server-side paginated fetch (2026-08-20+) — for the 3 list pages
  // (AuditTrail's event log, ReviewerRequests, Queue) that used to render
  // every matching row in one unbounded list. Returns the full envelope
  // (rows + total + totalPages), not just the array, since a pager needs
  // those. decisionSource ('AUTOMATED_ML' | 'MANUAL_REVIEWER') is used
  // instead of the older ?automated= flag — see authorizationRoutes.js's
  // GET / comment for why ?automated= (reviewedBy-based) can misclassify a
  // request after certain resubmission sequences.
  async getAuthorizationsPage({ status, decisionSource, page = 1, limit = 10 } = {}) {
    const query = new URLSearchParams();
    if (status) query.set('status', status);
    if (decisionSource) query.set('decisionSource', decisionSource);
    query.set('page', String(page));
    query.set('limit', String(limit));
    const payload = await apiClient.getWithMeta(`/authorizations?${query.toString()}`);
    return {
      rows: payload.data,
      total: payload.total ?? payload.data.length,
      totalPages: payload.totalPages ?? 1,
      page: payload.page ?? page,
    };
  },
  async getAuthorizationById(id) {
    return apiClient.get(`/authorizations/${encodeURIComponent(id)}`);
  },
  async createAuthorization(payload) {
    // Backend's response only echoes back {authorization: {id, status}},
    // not the full row (see authorizationRoutes.js POST /) — callers that
    // need the full record shape should merge this with what they sent.
    const result = await apiClient.post('/authorizations', payload);
    return result.authorization;
  },
  // PATCH /:id is DOCTOR-only and only succeeds against the doctor's own
  // authorization (authorizationRoutes.js checks createdBy) — merges
  // req.body onto the row via Sequelize .update(), so pass only the
  // fields you actually want to change. Returns the full updated row.
  async updateAuthorization(id, patch) {
    return apiClient.patch(`/authorizations/${encodeURIComponent(id)}`, patch);
  },
};
