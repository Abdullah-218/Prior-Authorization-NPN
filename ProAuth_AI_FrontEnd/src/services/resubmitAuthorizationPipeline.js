import { authorizationApi } from './authorizationApi';
import { documentsApi } from './documentsApi';
import { triageApi } from './triageApi';
import { mapAuthorizationRowToRequest, attachTriageResult } from './requestMapper';
import { upsertRequest } from '../data/requests';

// Same category -> Document Agent documentType mapping as the new-request
// pipeline (document_agent.py's CATEGORY_KEYWORDS).
const DOCUMENT_TYPE_BY_CATEGORY = {
  clinicalNotes: 'CLINICAL_NOTES',
  labReports: 'LAB_REPORTS',
  previousTreatmentRecords: 'PREVIOUS_TREATMENT_RECORDS',
  prescriptions: 'PRESCRIPTION',
  imagingReports: 'IMAGING_REPORT',
};

const TRIAGE_OUTCOME_TO_STATUS = {
  APPROVE: 'Approved',
  PEND: 'Needs Review',
  MORE_INFORMATION: 'Additional Information Required',
};

// Real resubmit flow, ported from the old frontend's proven
// ResubmitApplication.jsx (same 4 real steps), adapted to this frontend's
// service layer: (1) append the doctor's new justification onto the
// original rather than replacing it, (2) upload any newly attached
// documents, (3) re-fetch the FULL document set on record — a single
// triage call has no memory of a prior call's uploads, so a resubmission
// must resend everything, not just what's new — (4) re-run the real
// pipeline. Only meaningful for a request currently sitting at
// "Additional Information Required" (routed back to the doctor), but not
// restricted to that status here — the backend's own PATCH/evaluate calls
// are the real guard.
export async function resubmitAuthorization({ authorization, additionalNotes, files }) {
  const authorizationId = authorization.id;
  const trimmedNotes = (additionalNotes || '').trim();

  if (trimmedNotes) {
    const priorJustification = authorization.justification?.medicalNecessity || '';
    await authorizationApi.updateAuthorization(authorizationId, {
      justification: {
        ...authorization.justification,
        medicalNecessity: [priorJustification, trimmedNotes].filter(Boolean).join('\n\n'),
      },
    });
  }

  const uploads = Object.entries(files || {}).flatMap(([category, categoryFiles]) =>
    (categoryFiles || []).map(file =>
      documentsApi.upload(file, authorizationId, DOCUMENT_TYPE_BY_CATEGORY[category] || 'CLINICAL_NOTES').catch(() => null)
    )
  );
  await Promise.all(uploads);

  const allDocuments = await documentsApi.listForAuthorization(authorizationId);
  const attachedDocuments = allDocuments.map(d => ({ documentType: d.documentType, storageUrl: d.storageUrl, mimeType: d.mimeType }));

  const combinedJustification = [authorization.justification?.medicalNecessity, trimmedNotes].filter(Boolean).join('\n\n');
  const triageResult = await triageApi.evaluate({
    requestedService: authorization.treatment?.name || authorization.treatment?.type || null,
    diagnosis: authorization.clinical?.diagnosis || null,
    // Real insurance_plans.planId, persisted at original submission time
    // (see submitAuthorizationPipeline.js) — a request created before that
    // fix won't have one, so this can legitimately be null; the pipeline's
    // own "no policy found" gate handles that honestly rather than this
    // code guessing at a substitute.
    planId: authorization.insurance?.realPlanId || null,
    secondaryDiagnosis: authorization.clinical?.secondaryDiagnoses || null,
    icd10Code: authorization.clinical?.icdCode || null,
    clinicalJustification: combinedJustification || null,
    providerSpecialty: authorization.provider?.specialization || null,
    requestContext: {
      urgency: authorization.treatment?.urgency || null,
      patient_age: authorization.patient?.age ? Number(authorization.patient.age) : null,
    },
    authorizationId,
    attachedDocuments,
  });

  const updatedRow = {
    ...authorization,
    justification: {
      ...authorization.justification,
      medicalNecessity: combinedJustification || authorization.justification?.medicalNecessity || null,
    },
    status: TRIAGE_OUTCOME_TO_STATUS[triageResult.decision?.outcome] || authorization.status,
  };
  const request = attachTriageResult(mapAuthorizationRowToRequest(updatedRow), triageResult);
  upsertRequest(request);
  // Same { authorizationId, request } shape submitAuthorizationForTriage
  // resolves — lets Processing.jsx drive both flows identically.
  return { authorizationId, request };
}
