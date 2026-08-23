const readonlyPolicies = [
  { type: 'Medicare Advantage', area: 'Musculoskeletal imaging', effective: 'Jan 2026', status: 'Active', overview: 'Coverage guidance for diagnostic imaging requests.', coverage: 'Covered when clinical findings and treatment context support medical necessity.', diagnosis: 'Knee osteoarthritis and related qualifying diagnoses.', procedure: 'MRI lower extremity and comparable imaging services.', documentation: 'Clinical notes and relevant prior treatment records.', evidence: 'Relevant policy criteria retrieved for read-only review.' },
  { type: 'Commercial', area: 'Specialty medication', effective: 'Dec 2025', status: 'Active', overview: 'Coverage guidance for specialty medication requests.', coverage: 'Coverage depends on diagnosis, medication criteria, and submitted evidence.', diagnosis: 'Qualifying chronic and complex conditions.', procedure: 'Specialty medication services within plan scope.', documentation: 'Diagnosis documentation and supporting clinical evidence.', evidence: 'Policy evidence summary available for read-only review.' }
];

export const policyService = {
  getReadonlyPolicies() {
    return readonlyPolicies;
  }
};
