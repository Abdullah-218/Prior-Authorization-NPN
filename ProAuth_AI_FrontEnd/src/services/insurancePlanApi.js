import { apiClient } from './apiClient';

// Real, active insurance plans — needed so the wizard can offer an actual
// insurance_plans.planId (e.g. "PLAN001"/"PLAN020") rather than a free-text
// string, since RAG retrieval is scoped by this real planId -> payer
// resolution (rag/retrieval.py's get_plan_payer()). A free-text plan ID
// wouldn't match anything, degrading every request to "no policy found."
export const insurancePlanApi = {
  async listActive() {
    return apiClient.get('/insurance-plans?active=true');
  },
};
