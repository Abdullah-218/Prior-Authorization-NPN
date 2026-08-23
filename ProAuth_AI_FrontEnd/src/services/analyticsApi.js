import { apiClient } from './apiClient';

// ADMIN-only on the backend (authorizationRoutes.js) — real counts across
// every authorization, not derived from whatever's in the client-side
// requests[] cache.
export const analyticsApi = {
  async getSummary() {
    return apiClient.get('/authorizations/analytics/summary');
  },
};
