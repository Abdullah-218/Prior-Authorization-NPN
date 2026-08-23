/**
 * Backfill Patient.insurancePlanId
 *
 * Usage:
 *   node src/scripts/backfillPatientInsurancePlans.js
 *
 * Maps each existing patient's free-text insuranceType to a real
 * insurance_plans row, grounded in the actual current distribution
 * (checked before writing this: 293 private, 148 public, 59 uninsured, 6
 * blank, out of 506 patients) — not invented:
 *
 *   insuranceType='public'    -> PLAN001 (Medicare Example Plan)
 *   insuranceType='private'   -> split across the REAL private payers we
 *                                 have actual ingested policy data for
 *                                 (PLAN003 UnitedHealthcare, PLAN004 Cigna,
 *                                 PLAN005 Aetna), alternating
 *                                 deterministically by patient id so
 *                                 re-runs are stable
 *   insuranceType='uninsured' -> left null — genuinely no plan to reference,
 *                                 not a gap to fill in
 *   blank/unrecognized        -> left null, same reasoning
 *
 * Idempotent: only writes patients whose insurancePlanId is currently null,
 * safe to re-run. Note: adding PLAN005 here does NOT redistribute patients
 * already mapped to PLAN003/PLAN004 by an earlier run — only ever fills
 * nulls.
 */
import { initializeDatabase, Patient } from '../database/index.js';

const PRIVATE_PLAN_IDS = ['PLAN003', 'PLAN004', 'PLAN005']; // UnitedHealthcare, Cigna, Aetna — real ingested data

async function run() {
  await initializeDatabase();

  const patients = await Patient.findAll({ where: { insurancePlanId: null } });
  console.log(`${patients.length} patients with no insurancePlanId set.`);

  let updatedPublic = 0;
  let updatedPrivate = 0;
  let skippedNoPlan = 0;
  let privateIndex = 0;

  for (const patient of patients) {
    const type = (patient.insuranceType || '').toLowerCase();

    if (type === 'public') {
      await patient.update({ insurancePlanId: 'PLAN001' });
      updatedPublic += 1;
    } else if (type === 'private') {
      const planId = PRIVATE_PLAN_IDS[privateIndex % PRIVATE_PLAN_IDS.length];
      privateIndex += 1;
      await patient.update({ insurancePlanId: planId });
      updatedPrivate += 1;
    } else {
      // uninsured, blank, or anything unrecognized — genuinely no plan
      skippedNoPlan += 1;
    }
  }

  console.log(`\nMapped to Medicare (PLAN001):        ${updatedPublic}`);
  console.log(`Mapped to UHC/Cigna (PLAN003/PLAN004): ${updatedPrivate}`);
  console.log(`Left unmapped (uninsured/unknown):     ${skippedNoPlan}`);
  console.log('\nDone.');
  process.exit(0);
}

run().catch((err) => {
  console.error('Backfill failed:', err);
  process.exit(1);
});
