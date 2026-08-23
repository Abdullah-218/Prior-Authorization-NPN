import { requests } from '../data/requests';

function groupByPatient(ownRequests) {
  const byPatient = new Map();
  ownRequests.forEach(request => {
    const key = request.patientId || request.id;
    if (!byPatient.has(key)) byPatient.set(key, []);
    byPatient.get(key).push(request);
  });
  return byPatient;
}

// "Latest" must be resolved by actual timestamp, never by array position.
// patientRequests' order isn't a reliable proxy for chronological order:
// a bulk load (authorizationSync.js's loadRequests(), backend-sorted
// newest-first) and a single-item upsert (data/requests.js's
// upsertRequest(), which appends to the end) populate the shared array in
// OPPOSITE relative orders, so whichever end you trust depends on which
// path touched it last. Sorting explicitly here is what actually
// guarantees the "Clinical Decision"/"AI & ML Analysis" sections show the
// patient's actual most recent request instead of whichever one happened
// to land first/last in the array.
function sortByLatestFirst(patientRequests) {
  return [...patientRequests].sort((a, b) => new Date(b.submittedAtRaw || 0) - new Date(a.submittedAtRaw || 0));
}

function toPatientSummary(patientRequests) {
  const [latest] = sortByLatestFirst(patientRequests);
  return {
    patientId: latest.patientId || latest.id,
    patient: latest.patient,
    initials: latest.initials,
    dateOfBirth: latest.dateOfBirth,
    age: latest.age,
    sex: latest.sex,
    insuranceProvider: latest.insuranceProvider || 'Not specified',
    planName: latest.planName,
    memberId: latest.memberId,
    diagnosis: latest.diagnosis,
    activeRequests: patientRequests.length,
    latestStatus: latest.status,
    lastUpdated: latest.lastUpdated || latest.date,
    tone: latest.tone
  };
}

function buildPatientDetail(patientRequests) {
  if (!patientRequests.length) return null;
  const sorted = sortByLatestFirst(patientRequests);
  return { ...toPatientSummary(patientRequests), requests: sorted, latest: sorted[0] };
}

export const patientService = {
  getPatients(ownerId) {
    const ownRequests = requests.filter(request => request.ownerId === ownerId);
    return [...groupByPatient(ownRequests).values()].map(toPatientSummary);
  },
  getPatientById(ownerId, patientId) {
    const ownRequests = requests.filter(request => request.ownerId === ownerId);
    return buildPatientDetail(ownRequests.filter(request => (request.patientId || request.id) === patientId));
  },
  getAllPatients() {
    return [...groupByPatient(requests).values()].map(toPatientSummary);
  },
  getPatientByIdAnyOwner(patientId) {
    return buildPatientDetail(requests.filter(request => (request.patientId || request.id) === patientId));
  },
  // For roles scoped to an arbitrary pre-filtered request list (e.g. nurse: only
  // requests currently needing clinical review) rather than by ownerId or "all".
  getPatientsFromList(requestList) {
    return [...groupByPatient(requestList).values()].map(toPatientSummary);
  },
  getPatientByIdFromList(requestList, patientId) {
    return buildPatientDetail(requestList.filter(request => (request.patientId || request.id) === patientId));
  }
};
