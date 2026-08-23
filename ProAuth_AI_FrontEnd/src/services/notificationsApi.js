import { apiClient } from './apiClient';

// GET /api/notifications is auto-scoped to the logged-in user (see
// notificationRoutes.js) — real rows created at actual workflow events
// (automated approval, a nurse/admin decision, a resubmission request),
// not the frontend's previous 100%-mocked notifications.
export const notificationsApi = {
  async list() {
    return apiClient.get('/notifications');
  },
  async markRead(id) {
    return apiClient.patch(`/notifications/${encodeURIComponent(id)}/read`);
  },
};
