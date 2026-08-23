import { apiClient } from './apiClient';

// GET /api/policies — the real, ingested CMS NCD + private-payer policy
// corpus the RAG layer retrieves against (347 real policies as of
// 2026-08-20), not a mock list.
export const policyApi = {
  async list(filters = {}) {
    const params = new URLSearchParams();
    if (filters.payerName) params.set('payerName', filters.payerName);
    if (filters.jurisdiction) params.set('jurisdiction', filters.jurisdiction);
    if (filters.status) params.set('status', filters.status);
    const query = params.toString();
    return apiClient.get(`/policies${query ? `?${query}` : ''}`);
  },
  // Full detail — versions + criteria (see backend's policyRoutes.js).
  async getById(id) {
    return apiClient.get(`/policies/${encodeURIComponent(id)}`);
  },
};
