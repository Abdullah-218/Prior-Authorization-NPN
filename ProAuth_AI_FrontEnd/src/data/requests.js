// Shared, module-level, mutable store — every service in src/services/
// (dashboardService, patientService) already reads and mutates this SAME
// array reference in place. Keeping that pattern (not
// introducing a parallel store) means those services need no changes for
// reads; only how this array gets populated changes: real backend data
// via replaceRequests(), not hardcoded demo rows.
export const requests = [];

export function replaceRequests(list) {
  requests.length = 0;
  requests.push(...list);
}

export function upsertRequest(request) {
  const index = requests.findIndex(item => item.id === request.id);
  if (index === -1) requests.push(request);
  else requests[index] = { ...requests[index], ...request };
}
