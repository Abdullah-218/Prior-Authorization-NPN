import { apiClient } from './apiClient';

export const triageApi = {
  async evaluate(payload) {
    return apiClient.post('/triage/evaluate', payload);
  },
  async getEvaluations(authorizationId) {
    return apiClient.get(`/triage/evaluations/${encodeURIComponent(authorizationId)}`);
  },
  // Most recent evaluation only — every page that renders a decision only
  // ever shows the latest (see old frontend's PolicyTriageReport usage).
  async getLatestEvaluation(authorizationId) {
    const evaluations = await triageApi.getEvaluations(authorizationId);
    return evaluations?.[0] || null;
  },
};
