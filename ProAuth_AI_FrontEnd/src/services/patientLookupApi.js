import { apiClient } from './apiClient';

// GET /api/patients/:id is case-insensitive server-side (Op.iLike in
// patientRoutes.js), so no client-side normalization is needed. Returns
// the raw Patient row — including insurancePlanId, a foreign key into
// insurance_plans that is NOT guaranteed to point at a currently-active
// plan (most seeded patients reference legacy/inactive payer rows — see
// submitAuthorizationPipeline.js's handling of that mismatch).
export const patientLookupApi = {
  async getById(patientId) {
    return apiClient.get(`/patients/${encodeURIComponent(patientId)}`);
  },
};
