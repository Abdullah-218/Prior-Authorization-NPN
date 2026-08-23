/**
 * Insurance Plan Seed Script
 *
 * Usage:
 *   node src/scripts/seedInsurancePlans.js
 *
 * Seeds the insurance_plans table with the real payers this system has
 * actual ingested policy data for. Every policy behind these plans is
 * source: CMS or PUBLIC_PAYER_POLICY — real, cited, publicly-accessible
 * coverage documents. There is no synthetic/invented policy data in this
 * system (see policy-rag/ingest_cms_ncd.py for Medicare NCDs and
 * policy-rag/ingest_payer_policies.py for private payer policies).
 *
 * A patient holds exactly one of two policy TYPES (2026-08-19 decision):
 *   1. MEDICARE (public) — PLAN001
 *   2. PRIVATE — one plan per cost-sharing tier (Silver/Gold/Premium),
 *      payerName "Private" rather than a specific brand. Retrieval for a
 *      Private plan searches the UNION of every real private payer we've
 *      ingested (Aetna/Cigna/UnitedHealthcare — see policy-rag/retrieval.py's
 *      PRIVATE_PAYER_GROUP), not one payer's corpus alone. This is a
 *      deliberate simplification: real payer documentation coverage is
 *      genuinely uneven (e.g. UnitedHealthcare defers ~5 categories
 *      entirely to a licensed InterQual guideline with no public criteria
 *      text — a real, observed gap, not hypothetical), so scoping a demo
 *      patient to exactly one brand risks an honest "no evidence found"
 *      purely from that brand's documentation gap rather than a genuine
 *      absence of coverage. Widening to the union still only ever returns
 *      real, grounded policy text from a real payer — never fabricated,
 *      never Medicare — it just stops one payer's gap from hiding another
 *      payer's real, applicable answer.
 *
 * The previous payer-branded plans (PLAN003/004/005, PLAN010-018) are
 * DELETED below (2026-08-20 — previously just retired via active: false;
 * see git history for that version). Confirmed safe to delete outright:
 * every patient was moved onto one of the 4 plans below first (see
 * reassignPatientInsurance.js, run before this script), so no FK reference
 * to a retired plan remains, and RAG retrieval never depended on these
 * rows existing in the first place — PRIVATE_PAYER_GROUP
 * (policy-rag/rag/retrieval.py) is a hardcoded Python list, not derived
 * from this table, so the Private tier's combined Aetna/Cigna/
 * UnitedHealthcare corpus is untouched by removing these rows.
 *
 * Idempotent: uses findOrCreate, safe to re-run.
 */
import { v4 as uuidv4 } from 'uuid';
import { initializeDatabase, InsurancePlan } from '../database/index.js';

const PLANS = [
  {
    planId: 'PLAN001',
    planName: 'Medicare insurance Plan',
    payerName: 'Medicare',
    coverageType: 'MEDICARE',
    jurisdiction: 'US',
  },

  // ─── Private — one consolidated plan per cost-sharing tier ───────────────
  ...['Silver', 'Gold', 'Premium'].map((tier, tierIdx) => ({
    planId: `PLAN0${20 + tierIdx}`,
    planName: `Private - ${tier} Plan`,
    payerName: 'Private',
    coverageType: 'PRIVATE',
    tier: tier.toUpperCase(),
    jurisdiction: 'US',
  })),
];

// Superseded by the consolidated Private plans above — deleted, not just
// deactivated (see module docstring for why that's safe now).
const RETIRED_PLAN_IDS = [
  'PLAN003', 'PLAN004', 'PLAN005',
  'PLAN010', 'PLAN011', 'PLAN012',
  'PLAN013', 'PLAN014', 'PLAN015',
  'PLAN016', 'PLAN017', 'PLAN018',
];

async function run() {
  await initializeDatabase();

  for (const planData of PLANS) {
    const [plan, created] = await InsurancePlan.findOrCreate({
      where: { planId: planData.planId },
      defaults: { id: uuidv4(), ...planData, active: true },
    });
    if (!created) {
      // findOrCreate only applies defaults on insert — re-running this
      // script after renaming/retyping a plan (e.g. standardizing
      // coverageType) wouldn't otherwise pick up the change.
      await plan.update({
        planName: planData.planName,
        payerName: planData.payerName,
        coverageType: planData.coverageType,
        tier: planData.tier || null,
        active: true,
      });
    }
    console.log(`${created ? '✅ Created' : '⏭️  Updated'} — insurance plan ${plan.planId}: ${plan.planName}`);
  }

  for (const planId of RETIRED_PLAN_IDS) {
    const count = await InsurancePlan.destroy({ where: { planId } });
    if (count > 0) console.log(`🗑️  Deleted — insurance plan ${planId} (retired, no longer referenced)`);
  }

  console.log('\nDone.');
  process.exit(0);
}

run().catch((err) => {
  console.error('Seed failed:', err);
  process.exit(1);
});
