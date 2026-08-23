import { apiClient } from './apiClient';

// Exact contract proven by the old frontend's admin/ReviewApplication.jsx
// (PATCH /api/authorizations/:id/review, {decision, note}) — decision is
// one of "Approved" | "Denied" | "Additional Information Required". The
// backend itself rejects "Denied" from a NURSE role (2026-08-20 change),
// so this module doesn't need to re-gate that client-side.
export const reviewApi = {
  async recordDecision(authorizationId, decision, note) {
    return apiClient.patch(`/authorizations/${encodeURIComponent(authorizationId)}/review`, { decision, note });
  },
};
