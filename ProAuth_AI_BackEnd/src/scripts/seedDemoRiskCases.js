import fs from 'fs';
import path from 'path';
import { v4 as uuidv4 } from 'uuid';
import {
  sequelize, Patient, Provider, User, InsurancePlan,
  Authorization, Document, AuditEvent, TriageEvaluation,
} from '../database/index.js';

const casesPath = '/private/tmp/claude-501/-Users-abdullah-Learning-Projects-Practice-CTS/704b7794-d9d4-4133-99cf-f4dc866722be/scratchpad/seed_cases_computed.json';
const cases = JSON.parse(fs.readFileSync(casesPath, 'utf-8'));

const uploadDir = path.resolve('/Users/abdullah/Learning Projects/Practice_CTS/ProAuth_AI_BackEnd/uploads');
fs.mkdirSync(uploadDir, { recursive: true });

const SERVICE_TYPE_BY_LABEL = {
  'CPAP therapy for obstructive sleep apnea': 'Procedure',
  'Diagnostic cardiac catheterization': 'Procedure',
  'Bariatric surgery - sleeve gastrectomy': 'Procedure',
  'Low dose CT lung cancer screening': 'Imaging',
  'Elective cosmetic rhinoplasty for aesthetic appearance': 'Procedure',
};

async function writeDoc(authorizationId, category, docType, text, createdAt) {
  const fname = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}-${category}.txt`;
  const fpath = path.join(uploadDir, fname);
  fs.writeFileSync(fpath, text);
  const doc = await Document.create({
    id: uuidv4(),
    authorizationId,
    fileName: fname,
    mimeType: 'text/plain',
    storageUrl: fpath,
    documentType: docType,
    createdAt,
    updatedAt: createdAt,
  }, { silent: true });
  return doc;
}

async function seedCase(c, idx) {
  const patient = await Patient.findByPk(c.patient);
  const provider = await Provider.findByPk(c.provider);
  const plan = await InsurancePlan.findOne({ where: { planId: c.plan } });
  const user = await User.findOne({ where: { providerId: c.provider } });

  const submittedAt = new Date(c.submitted_at);
  const authorizationId = `PA-SEED-${Date.now()}-${idx}`;

  const decisionReason = c.decision.reason;

  const authorization = await Authorization.create({
    id: authorizationId,
    patientId: patient.id,
    providerId: provider.id,
    patient: {
      name: `${patient.firstName} ${patient.lastName}`,
      age: patient.age,
      dateOfBirth: patient.dateOfBirth,
      gender: patient.gender,
      contact: patient.phone,
      email: patient.email,
      patientId: patient.id,
      insuranceId: patient.insuranceMemberId,
    },
    doctor: {
      name: provider.name,
      specialization: provider.specialty,
      hospital: provider.organization,
      providerId: provider.providerId,
    },
    insurance: {
      provider: plan.payerName,
      plan: plan.planName,
      memberId: patient.insuranceMemberId,
      coverageStatus: 'Active',
      policyNumber: plan.planId,
      authorizationType: plan.coverageType,
      realPlanId: plan.planId,
    },
    payer: plan.payerName,
    clinical: {
      diagnosis: c.diagnosis,
      primaryDiagnosis: c.diagnosis,
      icdCode: c.icd10,
      secondaryDiagnoses: null,
      symptoms: null,
      duration: null,
      notes: c.justification,
    },
    treatment: {
      type: SERVICE_TYPE_BY_LABEL[c.service] || 'Procedure',
      name: c.service,
      code: c.code,
      urgency: c.urgency,
      requestedDate: null,
      placeOfService: c.care_setting,
    },
    justification: { medicalNecessity: c.justification },
    documents: [],
    documentDetails: {},
    currentMedications: [],
    status: 'Needs Review',
    createdBy: user.id,
    role: 'DOCTOR',
    decisionSource: 'AUTOMATED_ML',
    message: decisionReason,
    submittedAt,
    createdAt: submittedAt,
    updatedAt: submittedAt,
  }, { silent: true });

  await writeDoc(authorizationId, 'clinical_notes', 'CLINICAL_NOTES',
    `CLINICAL NOTES\n\n${c.justification}`, submittedAt);
  await writeDoc(authorizationId, 'prescription', 'PRESCRIPTION',
    `PRESCRIPTION\n\nOrder for: ${c.service}\nDiagnosis: ${c.diagnosis} (${c.icd10})`, submittedAt);

  await AuditEvent.create({
    id: uuidv4(),
    authorizationId,
    action: 'AUTHORIZATION_CREATED',
    actor: user.id,
    details: { seeded: true },
    createdAt: submittedAt,
    updatedAt: submittedAt,
  }, { silent: true });

  const evaluationId = uuidv4();
  const explanation = {
    summary: c.decision.reason.startsWith('Deterministic')
      ? c.decision.reason.replace(/^Deterministic( safety)? gate:\s*/i, '').replace(/\s*ML model was not invoked\.?$/i, '')
      : c.decision.reason,
    keyFactors: Object.entries(c.clinical_criteria_eval.criteriaResults).map(([k, v]) => `${k} ${v}`),
    citedEvidence: c.policy_evidence.policyName ? [c.policy_evidence.policyName] : [],
    informationalNote: null,
  };

  await TriageEvaluation.create({
    id: evaluationId,
    authorizationId,
    requestedService: c.service,
    diagnosis: c.diagnosis,
    planId: c.plan,
    threadId: authorizationId,
    decisionOutcome: c.decision.outcome,
    decisionConfidence: c.decision.confidence,
    decision: c.decision,
    policyEvidence: c.policy_evidence,
    clinicalEvidence: {
      extractedFacts: {},
      factSources: [],
      notes: 'Seeded directly for demo purposes — real deterministic gates/scoring applied, LLM extraction not re-run.',
    },
    clinicalCriteriaEval: c.clinical_criteria_eval,
    documentEvidence: c.document_evidence,
    mlFeatures: c.ml_features,
    explanation,
    memoization: { policyEvidenceReused: false, clinicalEvidenceReused: false, clinicalCriteriaEvalReused: false },
    evaluatedBy: user.id,
    processingStartedAt: submittedAt,
    processingCompletedAt: new Date(submittedAt.getTime() + 4200),
    processingDurationMs: 4200,
    createdAt: submittedAt,
    updatedAt: submittedAt,
  }, { silent: true });

  console.log(`Seeded ${authorizationId} — ${patient.firstName} ${patient.lastName} — ${c.service} — ${c.decision.outcome} (${c.id})`);
  return authorizationId;
}

async function main() {
  await sequelize.authenticate();
  const ids = [];
  for (let i = 0; i < cases.length; i++) {
    ids.push(await seedCase(cases[i], i));
  }
  console.log('\nAll seeded authorization IDs:', ids);
  await sequelize.close();
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
