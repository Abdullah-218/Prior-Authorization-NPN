import { apiClient } from './apiClient';

// GET /api/priority/queue — ADMIN/NURSE only (backend-enforced). Ranks
// every currently-pending ("Needs Review") authorization; see
// ProAuth_AI_ML/priority_intelligence/README.md.
export const priorityApi = {
  async getQueue() {
    return apiClient.get('/priority/queue');
  },
};
