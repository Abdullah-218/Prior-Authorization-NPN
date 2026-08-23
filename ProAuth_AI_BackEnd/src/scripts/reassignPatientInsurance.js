/**
 * Reassign Patient.insurancePlanId onto the 4 consolidated plans + normalize
 * demo emails (2026-08-20)
 *
 * Usage:
 *   node src/scripts/reassignPatientInsurance.js
 *
 * Run seedInsurancePlans.js FIRST so PLAN001/020/021/022 exist (their
 * names don't matter for this script — only their ids). This moves every
 * insured patient off the legacy payer-branded plans (PLAN003/004/005
 * etc., about to be deleted by seedInsurancePlans.js) onto one of the 4
 * plans this system actually supports selecting for new requests:
 *
 *   insuranceType='public'    -> PLAN001 (Medicare)
 *   insuranceType='private'   -> round-robin across PLAN020/021/022
 *                                 (Silver/Gold/Premium), deterministic by
 *                                 patient id sort order so re-runs are stable
 *   insuranceType='uninsured' -> left null — same reasoning as
 *                                 backfillPatientInsurancePlans.js: genuinely
 *                                 no plan to reference, not a gap to fill
 *   blank/unrecognized        -> left null, same reasoning
 *
 * Also normalizes every patient's email to "<patientId>@gmail.com" — the
 * originally-seeded name-based emails (firstname.lastname@example.com)
 * are harder to predict for manual testing than the id that's already the
 * natural lookup key.
 *
 * Not idempotent in the sense of "only fill gaps" (unlike
 * backfillPatientInsurancePlans.js) — it recomputes and overwrites every
 * patient's plan/email on every run. Safe to re-run against a stable
 * patient set; the private round-robin assignment is stable because it's
 * keyed off patient id sort order, not insertion order.
 */
import { initializeDatabase, Patient } from '../database/index.js';

const PRIVATE_TIER_PLAN_IDS = ['PLAN020', 'PLAN021', 'PLAN022']; // Silver, Gold, Premium

async function run() {
  await initializeDatabase();

  const patients = await Patient.findAll({ order: [['id', 'ASC']] });
  console.log(`${patients.length} patients total.`);

  let publicCount = 0;
  let privateCount = 0;
  let leftNull = 0;
  let privateIndex = 0;

  for (const patient of patients) {
    const type = (patient.insuranceType || '').toLowerCase();
    const updates = { email: `${patient.id}@gmail.com` };

    if (type === 'public') {
      updates.insurancePlanId = 'PLAN001';
      publicCount += 1;
    } else if (type === 'private') {
      updates.insurancePlanId = PRIVATE_TIER_PLAN_IDS[privateIndex % PRIVATE_TIER_PLAN_IDS.length];
      privateIndex += 1;
      privateCount += 1;
    } else {
      updates.insurancePlanId = null;
      leftNull += 1;
    }

    await patient.update(updates);
  }

  console.log(`\nMapped to Medicare (PLAN001):                ${publicCount}`);
  console.log(`Mapped to Silver/Gold/Premium (round-robin): ${privateCount}`);
  console.log(`Left unmapped (uninsured/unknown):           ${leftNull}`);
  console.log('\nDone.');
  process.exit(0);
}

run().catch((err) => {
  console.error('Reassignment failed:', err);
  process.exit(1);
});
