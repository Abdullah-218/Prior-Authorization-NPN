/**
 * Seed Patient Login Accounts
 *
 * Usage:
 *   node src/scripts/seedPatientAccounts.js
 *
 * Creates one PATIENT-role User account per row in patients — email is
 * already normalized to "<patientId>@gmail.com" (see
 * reassignPatientInsurance.js), password is the same shared demo password
 * every other seeded role uses ("patient123", matching doctor123/admin123/
 * nurse123). patientId links the login account to its real patients.id
 * row (see database/index.js's User model) — that's what
 * GET /api/authorizations scopes by for a PATIENT-role request, so a
 * patient only ever sees their own real authorizations.
 *
 * Uninsured/blank-plan patients still get a login account here — having
 * no insurance plan doesn't mean they have no authorization history to
 * view, and login is keyed by patient id, not by insurance status.
 *
 * Idempotent: findOrCreate keyed by patients.id (as "user-patient-<id>"),
 * safe to re-run — updates email/patientId on existing rows in case a
 * patient's email was normalized after this script last ran, but never
 * touches the password once created.
 */
import bcrypt from 'bcryptjs';
import { initializeDatabase, Patient, User } from '../database/index.js';

const DEMO_PASSWORD = 'patient123';

async function run() {
  await initializeDatabase();

  const patients = await Patient.findAll({ order: [['id', 'ASC']] });
  console.log(`${patients.length} patients found.`);

  let created = 0;
  let updated = 0;

  for (const patient of patients) {
    if (!patient.email) {
      console.log(`⚠️  Skipped ${patient.id} — no email on record.`);
      continue;
    }
    const name = `${patient.firstName || ''} ${patient.lastName || ''}`.trim() || patient.id;
    const [user, wasCreated] = await User.findOrCreate({
      where: { id: `user-patient-${patient.id}` },
      defaults: {
        id: `user-patient-${patient.id}`,
        name,
        email: patient.email,
        password: bcrypt.hashSync(DEMO_PASSWORD, 10),
        role: 'PATIENT',
        patientId: patient.id,
      },
    });
    if (wasCreated) {
      created += 1;
    } else if (user.email !== patient.email || user.patientId !== patient.id) {
      await user.update({ email: patient.email, patientId: patient.id, name });
      updated += 1;
    }
  }

  console.log(`\nCreated: ${created}`);
  console.log(`Updated (email/link drift): ${updated}`);
  console.log('\nDone.');
  process.exit(0);
}

run().catch((err) => {
  console.error('Seed failed:', err);
  process.exit(1);
});
