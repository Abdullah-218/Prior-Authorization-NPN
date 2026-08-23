import { authorizationApi } from './authorizationApi';
import { mapAuthorizationRowToRequest } from './requestMapper';
import { replaceRequests } from '../data/requests';

// Pulls real authorizations (already role-scoped server-side) and
// replaces the shared requests[] array in place — see data/requests.js
// for why mutating that one shared array, rather than a parallel store,
// is what lets the existing dashboardService/patientService code work
// unmodified.
export async function loadRequests() {
  const rows = await authorizationApi.getAuthorizations();
  replaceRequests(rows.map(mapAuthorizationRowToRequest));
}
