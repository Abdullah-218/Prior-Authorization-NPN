import { authorizationApi } from './authorizationApi';
import { documentsApi } from './documentsApi';
import { triageApi } from './triageApi';
import { mapAuthorizationRowToRequest, attachTriageResult } from './requestMapper';
import { upsertRequest } from '../data/requests';

// Mirrors triageRoutes.js's own TRIAGE_OUTCOME_TO_STATUS exactly — the
// backend writes this same status onto the Authorization row as part of
// POST /triage/evaluate's write-back, moments after POST /authorizations
// returned the pre-evaluation default ('Needs Review'). Re-deriving it
// here from the SAME response this call already has avoids either
// showing that stale default on the result page or firing a second
// GET just to read back what we already know.
const TRIAGE_OUTCOME_TO_STATUS = {
  APPROVE: 'Approved',
  PEND: 'Needs Review',
  MORE_INFORMATION: 'Additional Information Required',
};

// Same category -> Document Agent documentType mapping the old frontend
// proved works (document_agent.py's CATEGORY_KEYWORDS expects these
// exact values).
const DOCUMENT_TYPE_BY_CATEGORY = {
  clinicalNotes: 'CLINICAL_NOTES',
  labReports: 'LAB_REPORTS',
  previousTreatmentRecords: 'PREVIOUS_TREATMENT_RECORDS',
  prescriptions: 'PRESCRIPTION',
  imagingReports: 'IMAGING_REPORT',
};

function buildAuthorizationPayload(formData, user) {
  const patientName = `${formData.firstName} ${formData.lastName}`.trim() || 'Unnamed patient';
  return {
    patient: {
      name: patientName,
      age: formData.age || null,
      dateOfBirth: formData.dob || null,
      gender: formData.sex || null,
      contact: formData.phone || null,
      email: formData.email || null,
      patientId: formData.patientId || null,
      insuranceId: formData.memberId || null,
    },
    doctor: {
      name: user.name,
      specialization: user.specialization || null,
      hospital: user.hospital || null,
      providerId: user.providerId || null,
    },
    insurance: {
      provider: formData.insuranceProvider || null,
      plan: formData.planName || null,
      memberId: formData.memberId || null,
      coverageStatus: formData.coverageType || null,
      policyNumber: formData.planId || null,
      authorizationType: formData.policyType || null,
      // The REAL insurance_plans.planId (e.g. "PLAN021") — persisted here
      // (not just used transiently for this call's triage payload below)
      // so a later resubmission can re-scope RAG retrieval correctly
      // instead of falling back to `plan`, which is only ever a free-text
      // display name and was never a real, resolvable plan identifier.
      realPlanId: formData.realPlanId || null,
    },
    payer: formData.insuranceProvider || 'Pending payer selection',
    clinical: {
      diagnosis: formData.diagnosis || null,
      primaryDiagnosis: formData.diagnosis || null,
      icdCode: formData.icd10 || null,
      secondaryDiagnoses: formData.secondaryDiagnoses || null,
      symptoms: formData.symptoms || null,
      duration: formData.duration || null,
      notes: formData.clinicalJustification || null,
    },
    treatment: {
      type: formData.serviceType || null,
      name: formData.procedure || formData.serviceType || null,
      code: formData.procedureCode || null,
      urgency: formData.urgency || null,
      requestedDate: formData.requestedDate || null,
      placeOfService: formData.careSetting || null,
    },
    justification: { medicalNecessity: formData.clinicalJustification || null },
    documents: [],
    documentDetails: {},
    currentMedications: [],
  };
}

// planId here is the REAL insurance_plans.planId (e.g. "PLAN001") selected
// via the wizard's plan dropdown (formData.realPlanId) — NOT the free-text
// "Plan ID" field, which is just a member-facing label. RAG retrieval is
// scoped by this real value (rag/retrieval.py's get_plan_payer()); a
// free-text string wouldn't resolve to any payer.
function buildTriageRequestPayload(formData, user, authorizationId, attachedDocuments) {
  return {
    requestedService: formData.procedure || formData.serviceType || null,
    diagnosis: formData.diagnosis,
    planId: formData.realPlanId || null,
    secondaryDiagnosis: formData.secondaryDiagnoses || null,
    icd10Code: formData.icd10 || null,
    clinicalJustification: [formData.clinicalJustification, formData.symptoms && `Symptoms: ${formData.symptoms}`]
      .filter(Boolean).join('\n\n') || null,
    // The requesting DOCTOR's own specialty (not a form field — the
    // wizard doesn't collect one separately from the logged-in account).
    providerSpecialty: user.specialization || null,
    requestContext: {
      urgency: formData.urgency || null,
      patient_age: formData.age ? Number(formData.age) : null,
    },
    authorizationId,
    attachedDocuments,
  };
}

// Full real pipeline: create the authorization, upload any attached
// files, then run the real RAG+Agents+ML triage evaluation. Called from
// Processing.jsx's mount effect, since the triage call alone can take
// 40-90+ real seconds — the whole thing happens behind that page's
// animation rather than blocking the wizard's submit button.
export async function submitAuthorizationForTriage({ formData, files, user }) {
  const payload = buildAuthorizationPayload(formData, user);
  const created = await authorizationApi.createAuthorization(payload);
  const authorizationId = created.id;

  const uploads = Object.entries(files || {}).flatMap(([category, categoryFiles]) =>
    (categoryFiles || []).map(async file => {
      try {
        const doc = await documentsApi.upload(file, authorizationId, DOCUMENT_TYPE_BY_CATEGORY[category] || 'CLINICAL_NOTES');
        return { documentType: doc.documentType, storageUrl: doc.storageUrl, mimeType: doc.mimeType };
      } catch {
        return null; // one failed upload shouldn't abort the whole submission
      }
    })
  );
  const attachedDocuments = (await Promise.all(uploads)).filter(Boolean);

  const triageResult = await triageApi.evaluate(buildTriageRequestPayload(formData, user, authorizationId, attachedDocuments));

  // The backend's create response only echoes {id, status} back (see
  // authorizationApi.js), so the full "row" this maps from is the payload
  // we sent, merged with the real id/status/createdBy — the nested shape
  // is identical to what the backend actually stores. status uses the
  // POST-EVALUATION outcome (see TRIAGE_OUTCOME_TO_STATUS above), not
  // created.status, since that's always the pre-evaluation 'Needs Review'
  // default and would otherwise show a stale badge on the result page.
  const authorizationRow = {
    ...payload,
    id: authorizationId,
    status: TRIAGE_OUTCOME_TO_STATUS[triageResult.decision?.outcome] || created.status,
    createdBy: user.id,
    submittedAt: new Date().toISOString(),
  };
  const request = attachTriageResult(mapAuthorizationRowToRequest(authorizationRow), triageResult);
  upsertRequest(request);
  return { authorizationId, request };
}
