import test from 'node:test';
import assert from 'node:assert/strict';
import { evaluateAuthorization } from '../src/services/medicalNecessityService.js';

test('evaluates a complete authorization request and returns a proceed recommendation', () => {
  const request = {
    diagnosisCode: 'M51.26',
    diagnosisDescription: 'Lumbar disc disorder',
    procedureCode: 'CPT 72148',
    medicationCode: null,
    urgency: 'routine',
    clinicalJustification: 'Conservative therapy failed and imaging confirms diagnosis.',
    patient: {
      name: 'Maria Rodriguez',
      age: 52,
      gender: 'female',
      insuranceMemberId: 'INS001',
    },
    provider: {
      name: 'Dr. Sarah Johnson',
      specialty: 'Orthopedics',
      organization: 'City Medical Center',
    },
    treatmentHistory: [{ treatmentName: 'Physical therapy', response: 'Failed' }],
    documents: [{ documentType: 'clinical_notes' }],
  };

  const result = evaluateAuthorization(request);

  assert.equal(result.recommendation, 'PROCEED_TO_ML');
  assert.equal(result.eligibleForML, true);
  assert.ok(result.ruleComplianceScore >= 0.75);
  assert.ok(Array.isArray(result.evaluations));
});

test('requests more information when essential fields are missing', () => {
  const request = {
    diagnosisCode: '',
    diagnosisDescription: '',
    procedureCode: '',
    medicationCode: null,
    urgency: 'routine',
    clinicalJustification: '',
    patient: { name: 'Jane Doe' },
    provider: { name: 'Dr. X' },
    treatmentHistory: [],
    documents: [],
  };

  const result = evaluateAuthorization(request);

  assert.equal(result.recommendation, 'REQUEST_INFORMATION');
  assert.equal(result.eligibleForML, false);
  assert.ok(result.ruleComplianceScore < 0.6);
});
