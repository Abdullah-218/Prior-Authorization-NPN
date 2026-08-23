/**
 * Normalization utilities used throughout the rule engine.
 */

/**
 * Normalize a drug name for fuzzy matching:
 * lowercase, strip punctuation, collapse whitespace.
 */
export function normalizeDrugName(name) {
  if (!name) return '';
  return name
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * Normalize a diagnosis string similarly.
 */
export function normalizeDiagnosis(text) {
  if (!text) return '';
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * Extract the primary text value from an FDA field
 * (which may be an array or a plain string).
 */
export function extractFdaText(field) {
  if (!field) return '';
  if (Array.isArray(field)) return field.join(' ');
  return String(field);
}

/**
 * Normalize a request object so all downstream evaluators
 * work with consistent field names.
 *
 * The frontend sends fields nested as:
 *   patient, doctor, clinical, treatment, insurance, justification,
 *   previousTreatment, documentDetails, documents, currentMedications
 *
 * This normalizer flattens aliases and ensures every field used
 * by the rule engine has a consistent path.
 */
export function normalizeRequest(raw) {
  return {
    // ── Patient ──────────────────────────────────────────────
    patientId:      raw.patient?.id       || raw.patient?.patientId || raw.patientId || '',
    patientName:    raw.patient?.name     || raw.patientName || '',
    patientAge:     Number(raw.patient?.age || raw.patientAge || 0) || null,
    patientGender:  raw.patient?.gender   || raw.patientGender || '',
    insuranceId:    raw.patient?.insuranceId || raw.patient?.memberId || '',

    // ── Provider ─────────────────────────────────────────────
    providerName:     raw.doctor?.name || raw.provider?.name || raw.doctorName || '',
    providerSpecialty: raw.doctor?.specialization || raw.provider?.specialization
                       || raw.provider?.specialty || raw.specialization || '',
    providerId:       raw.doctor?.providerId || raw.provider?.id || raw.providerId || '',
    providerHospital: raw.doctor?.hospital || raw.provider?.organization || '',

    // ── Insurance ────────────────────────────────────────────
    insuranceProvider: raw.insurance?.provider || raw.payer || '',
    coverageStatus:    (raw.insurance?.coverageStatus || raw.coverageStatus || '').toLowerCase(),
    memberId:          raw.insurance?.memberId || raw.patient?.memberId || '',
    policyNumber:      raw.insurance?.policyNumber || '',

    // ── Clinical ─────────────────────────────────────────────
    diagnosis:     raw.clinical?.diagnosis || raw.clinical?.primaryDiagnosis || raw.primaryDiagnosis || '',
    icdCode:       raw.clinical?.icdCode   || raw.icdCode || '',
    clinicalNotes: raw.clinical?.notes     || raw.relevantMedicalHistory || '',
    diseaseSeverity: raw.clinical?.diseaseSeverity || raw.diseaseSeverity || '',
    secondaryDiagnoses: raw.clinical?.secondaryDiagnoses || '',

    // ── Treatment ────────────────────────────────────────────
    treatmentType: raw.treatment?.type  || raw.treatmentType || '',
    treatmentName: raw.treatment?.name  || raw.medicationName || raw.procedureName || '',
    treatmentCode: raw.treatment?.code  || raw.drugCode || raw.procedureCode || '',
    dosage:        raw.treatment?.dosage || raw.dosage || '',
    frequency:     raw.treatment?.frequency || raw.frequency || '',
    treatmentCost: raw.treatment?.cost != null && raw.treatment?.cost !== '' ? Number(raw.treatment.cost) : null,
    treatmentDurationDays: raw.treatment?.durationDays != null && raw.treatment?.durationDays !== ''
      ? Number(raw.treatment.durationDays) : null,

    // ── Justification ────────────────────────────────────────
    clinicalJustification: raw.justification?.medicalNecessity || raw.clinicalJustification || '',
    expectedBenefit:       raw.justification?.expectedBenefit  || raw.expectedBenefit || '',

    // ── Previous treatment ───────────────────────────────────
    previousTreatmentAttempted: raw.previousTreatment?.attempted || raw.previousTreatmentAttempted || '',
    previousTreatmentName:      raw.previousTreatment?.treatment || raw.previousTreatment || '',
    previousTreatmentFailed:    raw.previousTreatment?.failed    || raw.treatmentFailed || '',
    previousTreatmentResponse:  raw.previousTreatment?.response  || raw.treatmentResponse || '',

    // ── Documents ────────────────────────────────────────────
    documents: Array.isArray(raw.documents) ? raw.documents : [],
    documentDetails: {
      clinicalNotes:            raw.documentDetails?.clinicalNotes            || [],
      labReports:               raw.documentDetails?.labReports               || [],
      previousTreatmentRecords: raw.documentDetails?.previousTreatmentRecords || [],
      prescriptions:            raw.documentDetails?.prescriptions             || [],
      imagingReports:           raw.documentDetails?.imagingReports            || [],
    },

    // ── Current medications (for drug interaction check) ─────
    currentMedications: Array.isArray(raw.currentMedications) ? raw.currentMedications : [],

    // ── Raw reference for LLM ─────────────────────────────────
    _raw: raw,
  };
}
