/**
 * Clinical Data Seed Script
 *
 * Usage:
 *   node src/scripts/seedClinicalData.js
 *
 * - Seeds 25 doctors (Provider + matching User login) across 13 specialties
 * - Seeds 500 patients (PAT001-PAT500) with insurance/demographic fields
 * - Idempotent: uses findOrCreate, safe to re-run
 */
import bcrypt from 'bcryptjs';
import { initializeDatabase, Provider, User, Patient, sequelize } from '../database/index.js';

const DOCTOR_PASSWORD = 'doctor123';

// ─── Doctor data ────────────────────────────────────────────────────────────

const DOCTOR_NAMES = [
  'Sarah Johnson', 'Michael Thomas', 'Emily Davis', 'Robert Chen', 'Linda Martinez',
  'James Anderson', 'Patricia Wilson', 'David Lee', 'Barbara Clark', 'William Rodriguez',
  'Jennifer Lewis', 'Richard Walker', 'Susan Hall', 'Joseph Young', 'Karen Allen',
  'Charles King', 'Nancy Wright', 'Thomas Scott', 'Lisa Green', 'Christopher Baker',
  'Betty Adams', 'Daniel Nelson', 'Margaret Carter', 'Paul Mitchell', 'Sandra Perez',
];

// 12 specialties x 2 + General Practice x 1 = 25 (matches SPECIALTY_MAP in
// providerCompatibilityEvaluator.js so R501 has real mismatches to catch)
const SPECIALTIES = [
  'Orthopedics', 'Orthopedics',
  'Cardiology', 'Cardiology',
  'Endocrinology', 'Endocrinology',
  'Rheumatology', 'Rheumatology',
  'Oncology', 'Oncology',
  'Neurology', 'Neurology',
  'Dermatology', 'Dermatology',
  'Pulmonology', 'Pulmonology',
  'Gastroenterology', 'Gastroenterology',
  'Nephrology', 'Nephrology',
  'Psychiatry', 'Psychiatry',
  'Internal Medicine', 'Internal Medicine',
  'General Practice',
];

const HOSPITALS = [
  { name: 'City Medical Center',          slug: 'citymedical' },
  { name: 'Metro Hospital',               slug: 'metrohospital' },
  { name: 'Heart Care Hospital',          slug: 'heartcare' },
  { name: 'Lakeside Clinic',              slug: 'lakesideclinic' },
  { name: 'Grand Valley Medical Center',  slug: 'grandvalley' },
  { name: 'Sunrise Health Center',        slug: 'sunrisehealth' },
  { name: 'Riverside General Hospital',   slug: 'riversidegeneral' },
  { name: 'Parkview Medical Institute',   slug: 'parkviewmedical' },
];

function buildDoctors() {
  return DOCTOR_NAMES.map((fullName, i) => {
    const providerId = `DOC${String(i + 1).padStart(3, '0')}`;
    const specialty   = SPECIALTIES[i];
    const hospital    = HOSPITALS[i % HOSPITALS.length];
    const [firstName, lastName] = fullName.split(' ');
    const contactEmail = `${firstName.toLowerCase()}.${lastName.toLowerCase()}@${hospital.slug}.com`;

    return {
      providerId,
      name: `Dr. ${fullName}`,
      specialty,
      organization: hospital.name,
      contactEmail,
    };
  });
}

async function seedDoctors() {
  const doctors = buildDoctors();
  const hashedPassword = bcrypt.hashSync(DOCTOR_PASSWORD, 10);

  let providersCreated = 0;
  let usersCreated = 0;

  for (const doc of doctors) {
    const [, providerCreated] = await Provider.findOrCreate({
      where: { id: doc.providerId },
      defaults: {
        id: doc.providerId,
        name: doc.name,
        specialty: doc.specialty,
        organization: doc.organization,
        providerId: doc.providerId,
        contactEmail: doc.contactEmail,
        createdBy: 'system-seed',
      },
    });
    if (providerCreated) providersCreated++;

    const [, userCreated] = await User.findOrCreate({
      where: { email: doc.contactEmail },
      defaults: {
        id: `user-${doc.providerId.toLowerCase()}`,
        name: doc.name,
        email: doc.contactEmail,
        password: hashedPassword,
        role: 'DOCTOR',
        hospital: doc.organization,
        specialization: doc.specialty,
        providerId: doc.providerId,
      },
    });
    if (userCreated) usersCreated++;
  }

  console.log(`✅ Doctors seeded — providers created: ${providersCreated}, users created: ${usersCreated} (total doctors: ${doctors.length})`);
  return doctors;
}

// ─── Patient data ───────────────────────────────────────────────────────────

const MALE_FIRST_NAMES = [
  'James', 'John', 'Robert', 'Michael', 'William', 'David', 'Richard', 'Joseph',
  'Thomas', 'Charles', 'Daniel', 'Matthew', 'Anthony', 'Mark', 'Steven', 'Andrew',
  'Kenneth', 'George', 'Joshua', 'Kevin', 'Brian', 'Edward', 'Ronald', 'Timothy',
  'Jason', 'Jeffrey', 'Ryan', 'Jacob', 'Gary', 'Nicholas',
];
const FEMALE_FIRST_NAMES = [
  'Mary', 'Patricia', 'Jennifer', 'Linda', 'Elizabeth', 'Barbara', 'Susan', 'Jessica',
  'Sarah', 'Karen', 'Nancy', 'Lisa', 'Margaret', 'Betty', 'Sandra', 'Ashley',
  'Emily', 'Donna', 'Michelle', 'Carol', 'Amanda', 'Melissa', 'Deborah', 'Stephanie',
  'Rebecca', 'Laura', 'Sharon', 'Cynthia', 'Kathleen', 'Amy',
];
const LAST_NAMES = [
  'Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis',
  'Rodriguez', 'Martinez', 'Hernandez', 'Lopez', 'Gonzalez', 'Wilson', 'Anderson',
  'Thomas', 'Taylor', 'Moore', 'Jackson', 'Martin', 'Lee', 'Perez', 'Thompson',
  'White', 'Harris', 'Sanchez', 'Clark', 'Ramirez', 'Lewis', 'Robinson', 'Walker',
  'Young', 'Allen', 'King', 'Wright', 'Scott', 'Green', 'Baker', 'Adams', 'Nelson',
];

const PATIENT_COUNT = 500;

function randomInt(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

function pick(arr) {
  return arr[randomInt(0, arr.length - 1)];
}

// Skews low (most patients have few chronic conditions / prior meds)
function skewedLow(max) {
  return Math.floor(Math.random() * Math.random() * (max + 1));
}

function weightedInsuranceType() {
  const r = Math.random();
  if (r < 0.55) return 'private';
  if (r < 0.85) return 'public';
  return 'uninsured';
}

function buildPatient(i) {
  const idNum = String(i).padStart(3, '0');
  const gender = Math.random() < 0.5 ? 'Male' : 'Female';
  const firstName = gender === 'Male' ? pick(MALE_FIRST_NAMES) : pick(FEMALE_FIRST_NAMES);
  const lastName = pick(LAST_NAMES);

  const age = randomInt(18, 85);
  const birthYear = new Date().getFullYear() - age;
  const birthMonth = String(randomInt(1, 12)).padStart(2, '0');
  const birthDay = String(randomInt(1, 28)).padStart(2, '0');

  const insuranceType = weightedInsuranceType();
  const coverageActive = insuranceType === 'uninsured' ? false : Math.random() < 0.9;

  return {
    id: `PAT${idNum}`,
    firstName,
    lastName,
    gender,
    age,
    dateOfBirth: `${birthYear}-${birthMonth}-${birthDay}`,
    phone: `+1-555-${String(randomInt(1000000, 9999999))}`,
    email: `${firstName.toLowerCase()}.${lastName.toLowerCase()}${i}@example.com`,
    insuranceMemberId: `INS-${idNum}`,
    policyNumber: `POL-${100000 + i}`,
    insuranceType,
    coverageActive,
    chronicConditionCount: skewedLow(5),
    previousMedicationsCount: skewedLow(8),
    createdBy: 'system-seed',
  };
}

async function seedPatients() {
  const existing = await Patient.count();
  if (existing >= PATIENT_COUNT) {
    console.log(`⏭️  Patients already seeded (${existing} present). Skipping.`);
    return;
  }

  let created = 0;
  for (let i = 1; i <= PATIENT_COUNT; i++) {
    const patient = buildPatient(i);
    const [, wasCreated] = await Patient.findOrCreate({
      where: { id: patient.id },
      defaults: patient,
    });
    if (wasCreated) created++;

    if (i % 100 === 0) {
      console.log(`  Progress: ${i} / ${PATIENT_COUNT} processed (created: ${created})`);
    }
  }

  console.log(`✅ Patients seeded — created: ${created} (total requested: ${PATIENT_COUNT})`);
}

// ─── Main ───────────────────────────────────────────────────────────────────

console.log('🚀 ProAuth AI — Clinical Data Seed (25 doctors + 500 patients)\n');

initializeDatabase()
  .then(async () => {
    await seedDoctors();
    await seedPatients();

    const totalProviders = await Provider.count();
    const totalPatients = await Patient.count();
    console.log(`\n📊 Totals — providers: ${totalProviders}, patients: ${totalPatients}`);
  })
  .then(() => {
    console.log('✅ Done. Closing database connection.');
    return sequelize.close();
  })
  .catch((err) => {
    console.error('❌ Seed failed:', err.message);
    process.exit(1);
  });
