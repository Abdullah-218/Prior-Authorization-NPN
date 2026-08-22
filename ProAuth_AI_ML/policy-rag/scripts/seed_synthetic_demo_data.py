"""
Synthetic demo-data seeder — 2026-08-21+

NO LLM / Groq calls anywhere in this script. What it DOES do: exercise
the REAL, unmodified, deterministic decision code for every single row —
agents.coverage_reasoning_agent.aggregate_ml_features() (the 9 gates +
feature aggregator) and ml.model.MLTriageAgent.run() (the trained
LogisticRegression + gate-priority logic) are imported and called
directly, exactly as main.py's /triage endpoint does. Only the "read the
clinical notes and extract structured facts" step — normally a Groq call
via the Policy/Clinical Evidence Agents — is hand-authored per a target
outcome bucket instead of LLM-derived. Every stored decision, gate flag,
and reason string is therefore a genuine output of production logic, not
fabricated.

What this does NOT do: call runTriage()/run_evidence_pipeline() (which
would hit Groq for policy/clinical extraction), call the Companion Agent
(explanation text is templated from the real decision instead), or touch
the priority_intelligence ranker directly — that already reads real
stored data via its own endpoint, nothing here needs to special-case it.

Usage:
    cd ProAuth_AI_ML/policy-rag
    .venv/bin/python3 scripts/seed_synthetic_demo_data.py [--dry-run] [--doctors N] [--per-doctor N]
"""
import argparse
import json
import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # policy-rag/ -> agents, ml, rag, triage_graph
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))  # ProAuth_AI_ML/ -> priority_intelligence

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

# priority_intelligence's XGBoost model MUST load before rag.retrieval
# (sentence-transformers/torch) touches this process — same SIGSEGV
# conflict documented in priority_intelligence/README.md's "known issue"
# and policy-rag/main.py's import order. agents.coverage_reasoning_agent
# below imports rag.retrieval transitively, so this eager load has to
# happen first, here, not lazily inside _find_tier_matching_params.
from priority_intelligence.ranker import get_ranker
get_ranker()

from agents.coverage_reasoning_agent import aggregate_ml_features
from ml.model import MLTriageAgent

RANDOM_SEED = 42
random.seed(RANDOM_SEED)

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent.parent / "ProAuth_AI_BackEnd" / "uploads"
# Real placeholder files already on disk (2026-08-19 test uploads) — reused
# for every synthetic Document row so "View" in the UI opens a real file
# instead of 404ing on a path that was never actually written.
CATEGORY_FILES = {
    "CLINICAL_NOTES": next(UPLOAD_DIR.glob("*clinical_notes.pdf"), None),
    "PRESCRIPTION": next(UPLOAD_DIR.glob("*prescription.pdf"), None),
    "LAB_REPORTS": next(UPLOAD_DIR.glob("*lab_report.pdf"), None),
    "PREVIOUS_TREATMENT_RECORDS": next(UPLOAD_DIR.glob("*prev_treatment.pdf"), None),
}

# ─── Specialty -> clinical profile pool ─────────────────────────────────────
# Real ICD-10-shaped codes, real service names, and keyword sets used to
# find an ACTUAL matching row in the live policies table (never a made-up
# policyId) — see _find_policy_for_profile(). One doctor's specialty
# determines which pool their synthetic patients are drawn from, per the
# explicit "based on the specialty of the doctor" instruction.
SPECIALTY_PROFILES = {
    "Orthopedics": [
        dict(diagnosis="Osteoarthritis of the knee", icd10="M17.11", service="Knee arthroscopy", serviceType="Procedure", keywords=["knee", "arthroscop"]),
        dict(diagnosis="Lumbar spinal stenosis", icd10="M48.06", service="Lumbar spine MRI", serviceType="Imaging", keywords=["spine", "mri"]),
        dict(diagnosis="Rotator cuff tear", icd10="M75.100", service="Shoulder arthroscopy", serviceType="Procedure", keywords=["joint", "arthroscop"]),
        dict(diagnosis="Advanced knee osteoarthritis", icd10="M17.12", service="Total knee replacement", serviceType="Procedure", keywords=["knee", "replacement", "arthroplasty"]),
    ],
    "Cardiology": [
        dict(diagnosis="Coronary artery disease", icd10="I25.10", service="Cardiac catheterization", serviceType="Procedure", keywords=["cardiac", "catheter"]),
        dict(diagnosis="Atrial fibrillation with pacemaker indication", icd10="I48.91", service="Cardiac pacemaker evaluation", serviceType="Procedure", keywords=["pacemaker", "cardiac"]),
        dict(diagnosis="Heart failure with reduced ejection fraction", icd10="I50.22", service="Intensive cardiac rehabilitation", serviceType="Therapy", keywords=["cardiac", "rehab"]),
    ],
    "Endocrinology": [
        dict(diagnosis="Type 2 diabetes mellitus", icd10="E11.9", service="Continuous glucose monitor", serviceType="Medication", keywords=["glucose", "diabet"]),
        dict(diagnosis="Type 2 diabetes with diabetic peripheral neuropathy", icd10="E11.42", service="Diabetic peripheral neuropathy treatment", serviceType="Therapy", keywords=["neuropathy", "diabet"]),
        dict(diagnosis="Poorly controlled diabetes mellitus", icd10="E11.65", service="Outpatient intravenous insulin treatment", serviceType="Medication", keywords=["insulin", "diabet"]),
    ],
    "Rheumatology": [
        dict(diagnosis="Rheumatoid arthritis", icd10="M06.9", service="Biologic DMARD therapy", serviceType="Medication", keywords=["arthritis", "biologic"]),
        dict(diagnosis="Systemic lupus erythematosus with mucocutaneous involvement", icd10="M32.9", service="Immune globulin therapy", serviceType="Medication", keywords=["immune", "biologic", "autoimmune"]),
    ],
    "Oncology": [
        dict(diagnosis="Malignant neoplasm of breast", icd10="C50.911", service="Chemotherapy administration", serviceType="Medication", keywords=["chemotherapy", "tumor"]),
        dict(diagnosis="Long-term smoker, lung cancer screening indicated", icd10="Z87.891", service="Low dose CT lung cancer screening", serviceType="Imaging", keywords=["lung cancer", "screening"]),
    ],
    "Neurology": [
        dict(diagnosis="Chronic migraine with brain lesion ruled out", icd10="G43.709", service="MRI brain and CT scan", serviceType="Imaging", keywords=["magnetic resonance", "brain"]),
        dict(diagnosis="Epilepsy with recurrent seizures", icd10="G40.909", service="EEG monitoring", serviceType="Procedure", keywords=["eeg", "seizure"]),
    ],
    "Dermatology": [
        dict(diagnosis="Moderate to severe plaque psoriasis", icd10="L40.0", service="Biologic therapy for psoriasis", serviceType="Medication", keywords=["psoriasis", "biologic"]),
        dict(diagnosis="Chronic plaque psoriasis, topical therapy failed", icd10="L40.0", service="Psoriasis treatment", serviceType="Medication", keywords=["psoriasis", "skin"]),
    ],
    "Pulmonology": [
        dict(diagnosis="Obstructive sleep apnea", icd10="G47.33", service="CPAP therapy setup", serviceType="Procedure", keywords=["sleep apnea", "cpap"]),
        dict(diagnosis="Chronic obstructive pulmonary disease", icd10="J44.9", service="Pulmonary rehabilitation", serviceType="Therapy", keywords=["copd", "pulmonary"]),
    ],
    "Gastroenterology": [
        dict(diagnosis="Crohn disease requiring endoscopic evaluation", icd10="K50.90", service="Endoscopy with biopsy", serviceType="Procedure", keywords=["endoscop"]),
        dict(diagnosis="Chronic hepatitis C", icd10="B18.2", service="Antiviral therapy", serviceType="Medication", keywords=["hepatitis"]),
    ],
    "Nephrology": [
        dict(diagnosis="End stage renal disease", icd10="N18.6", service="Hemodialysis", serviceType="Procedure", keywords=["dialysis", "renal"]),
        dict(diagnosis="Chronic kidney disease, stage 4", icd10="N18.4", service="Renal function monitoring", serviceType="Procedure", keywords=["renal", "kidney"]),
    ],
    "Psychiatry": [
        dict(diagnosis="Major depressive disorder, recurrent", icd10="F33.1", service="Antidepressant medication management", serviceType="Medication", keywords=["antidepressant", "depress"]),
        dict(diagnosis="Treatment-resistant depression", icd10="F33.2", service="Psychiatric therapy sessions", serviceType="Therapy", keywords=["therapy"]),
    ],
    "Internal Medicine": [
        dict(diagnosis="Essential hypertension", icd10="I10", service="Ambulatory blood pressure monitoring", serviceType="Procedure", keywords=["blood pressure", "hypertension"]),
        dict(diagnosis="Hyperlipidemia", icd10="E78.5", service="Lipid panel and statin therapy", serviceType="Medication", keywords=["lipid", "cholesterol"]),
    ],
    "General Practice": [
        dict(diagnosis="Annual wellness visit", icd10="Z00.00", service="Preventive health screening", serviceType="Procedure", keywords=["wellness", "screening"]),
        dict(diagnosis="Vitamin D deficiency", icd10="E55.9", service="Vitamin D testing", serviceType="Procedure", keywords=["vitamin", "testing"]),
    ],
}
POLICY_NAMED_CRITERIA = ["conservative_therapy_documented", "diagnostic_confirmation_present", "functional_impact_documented"]

# ─── Per-doctor outcome-bucket split (30 patients: 21/3/4/2) ────────────────
BUCKET_COUNTS = {"AUTO_APPROVE": 21, "MANUAL_APPROVE": 3, "PEND": 4, "MORE_INFO": 2}

TRIAGE_OUTCOME_TO_STATUS = {"APPROVE": "Approved", "PEND": "Needs Review", "MORE_INFORMATION": "Additional Information Required"}

# Priority-tier urgency/timing combinations (HIGH=Emergency, MEDIUM=Urgent
# with moderate pending time, LOW=Routine and fresh) are applied inline in
# main()'s per-row loop below — verified empirically this session against
# the real priority_intelligence ranker to land reliably in each tier with
# margin, not just guessed.


def _conn():
    return psycopg2.connect(os.environ["DATABASE_URL"])


def _find_policy_for_profile(cur, keywords):
    conditions = " OR ".join(["\"policyName\" ILIKE %s"] * len(keywords))
    cur.execute(
        f"SELECT \"policyId\", \"policyName\", \"payerName\" FROM policies WHERE ({conditions}) AND status='ACTIVE' ORDER BY random() LIMIT 1",
        [f"%{kw}%" for kw in keywords],
    )
    return cur.fetchone()


def _build_document_evidence(complete: bool):
    if complete:
        return {"documentationScore": 100.0, "nRequiredDocuments": 2, "nDocumentsSubmitted": 2, "missingDocuments": [], "relevantDocuments": ["clinical notes", "prescription"]}
    return {"documentationScore": 0.0, "nRequiredDocuments": 2, "nDocumentsSubmitted": 1, "missingDocuments": ["prescription"], "relevantDocuments": ["clinical notes"]}


def _build_clinical_criteria_eval(diagnosis_supported, criteria_pass_count, gate=None):
    """gate: None | 'contraindication' | 'coverage_not_covered_only' (no clinical gate) |
    'indication_mismatch' | 'urgency' | 'clinical_evidence_insufficient'"""
    results = {"indication_match": "PASS", "specialty_match": "PASS"}
    grounded_mismatch = False
    contraindication_details = []
    n_total = len(POLICY_NAMED_CRITERIA)
    n_pass = max(0, min(n_total, criteria_pass_count))
    for i, name in enumerate(POLICY_NAMED_CRITERIA):
        results[name] = "PASS" if i < n_pass else "FAIL"

    if gate == "contraindication":
        results["contraindication_check"] = "FAIL"
        contraindication_details = [{"drugMatched": "warfarin", "reason": "known interaction with the requested therapy given the patient's documented anticoagulant use"}]
    if gate == "indication_mismatch":
        results["indication_match"] = "FAIL"
        grounded_mismatch = True
    if gate == "urgency":
        results["urgency_consistency"] = "FAIL"
    if gate == "clinical_evidence_insufficient":
        n_pass = 0
        for name in POLICY_NAMED_CRITERIA:
            results[name] = "FAIL"

    n_fail = n_total - n_pass
    return {
        "diagnosisSupported": diagnosis_supported,
        "criteriaResults": results,
        "nClinicalCriteriaTotal": n_total,
        "nClinicalCriteriaPassed": n_pass,
        "nClinicalCriteriaFailed": n_fail,
        "clinicalEvidenceScore": round(100 * n_pass / n_total, 1) if n_total else None,
        "groundedIndicationMismatch": grounded_mismatch,
        "contraindicationDetails": contraindication_details,
    }


def _build_policy_evidence(policy_row, relevance, coverage_status="COVERED"):
    if policy_row is None:
        return {"policyFound": False, "policyId": None, "policyName": None, "coverageStatus": "UNKNOWN", "criteria": [], "clinicalCriteria": [], "requiredDocuments": ["Clinical notes", "Prescription"], "relevanceScore": None, "confidence": "NONE", "message": "No applicable coverage policy could be found for this request."}
    # policy_row is a RealDictRow (dict-like) — NOT a plain tuple. Unpacking
    # it positionally (`a, b, c = policy_row`) silently iterates its KEYS,
    # not its values — reproduced live (2026-08-21): every synthetic case
    # got policyId="policyId" (the literal key string), which get_policy_status()
    # then failed to find, firing policyInactive on every single row.
    policy_id, policy_name, payer_name = policy_row["policyId"], policy_row["policyName"], policy_row["payerName"]
    return {
        "policyFound": True, "policyId": policy_id, "policyName": policy_name, "payerName": payer_name,
        "coverageStatus": coverage_status,
        "criteria": POLICY_NAMED_CRITERIA, "clinicalCriteria": POLICY_NAMED_CRITERIA,
        "requiredDocuments": ["Clinical notes", "Prescription"],
        "relevanceScore": relevance, "confidence": "HIGH" if relevance >= 0.8 else "MEDIUM",
        "message": f"Policy {policy_id} ({policy_name}) identified for this request.",
    }


def _build_explanation(decision, feature_vector, policy_evidence, clinical_eval, document_evidence):
    """Templated — NOT LLM-generated. Grounded only in real computed values
    (real gate flags, real scores, real policy name), never a fabricated
    clinical claim. Mirrors the shape agents/companion_agent.py returns."""
    outcome = decision["outcome"]
    key_factors = []
    if policy_evidence.get("policyFound"):
        key_factors.append(f"Policy {policy_evidence['policyId']} ({policy_evidence['policyName']}) — coverage status {policy_evidence['coverageStatus']}")
    n_pass = clinical_eval.get("nClinicalCriteriaPassed", 0)
    n_total = clinical_eval.get("nClinicalCriteriaTotal", 0)
    key_factors.append(f"{n_pass} of {n_total} named clinical criteria met")
    key_factors.append(f"Documentation: {document_evidence['nDocumentsSubmitted']}/{document_evidence['nRequiredDocuments']} required documents submitted")

    if outcome == "APPROVE":
        summary = f"Automated approval — policy coverage confirmed under {policy_evidence.get('policyName', 'the applicable policy')}, with {n_pass}/{n_total} clinical criteria met and complete required documentation."
    elif outcome == "MORE_INFORMATION":
        summary = f"Additional information requested — {decision['reason']}"
    else:
        summary = f"Routed for manual review — {decision['reason']}"

    return {"summary": summary, "keyFactors": key_factors, "citedEvidence": [policy_evidence.get("message", "")], "informationalNote": None}


def _generate_case(cur, profile, target_bucket):
    """Constructs hand-authored (not LLM-derived) evidence per target
    bucket, then runs it through the REAL aggregate_ml_features() +
    MLTriageAgent.run() — the actual decision is whatever that real code
    produces, verified via this session's own calibration testing."""
    ml_agent = _generate_case._agent
    policy_row = _find_policy_for_profile(cur, profile["keywords"])

    if target_bucket == "AUTO_APPROVE":
        pe = _build_policy_evidence(policy_row, relevance=random.uniform(0.75, 0.95))
        cce = _build_clinical_criteria_eval(True, criteria_pass_count=3)
        de = _build_document_evidence(complete=True)
    elif target_bucket == "MANUAL_APPROVE":
        # Same shape as AUTO_APPROVE's weaker sibling: reaches the model,
        # scores PEND, THEN a nurse/admin manually approves it — the real
        # PATCH /:id/review code path, simulated below in insert_case().
        # diagnosis_supported=False is load-bearing here, not cosmetic:
        # _estimate_policy_score's formula (100*(0.5+0.5*relevance)) can
        # NEVER go below 50 while diagnosis_supported=True — the -40
        # penalty only applies when it's False. An earlier version of this
        # script left diagnosis_supported=True here, which meant this
        # "weak" evidence wasn't actually weak enough and regularly leaked
        # into a real APPROVE — found via live verification, not assumed.
        pe = _build_policy_evidence(policy_row, relevance=random.uniform(0.35, 0.55))
        cce = _build_clinical_criteria_eval(False, criteria_pass_count=random.choice([1, 2]))
        de = _build_document_evidence(complete=True)
    elif target_bucket == "PEND":
        gate = random.choice([None, None, "contraindication", "indication_mismatch", "urgency", "coverage_not_covered", "policy_not_found"])
        if gate == "policy_not_found":
            pe = _build_policy_evidence(None, relevance=None)
        elif gate == "coverage_not_covered":
            pe = _build_policy_evidence(policy_row, relevance=random.uniform(0.6, 0.85), coverage_status="NOT_COVERED")
        else:
            pe = _build_policy_evidence(policy_row, relevance=random.uniform(0.3, 0.5))
        # diagnosis_supported=False for the same reason as MANUAL_APPROVE
        # above — genuinely weak, verified-reliable PEND via the model
        # itself when no specific gate is chosen.
        cce = _build_clinical_criteria_eval(False, criteria_pass_count=1, gate=gate if gate in ("contraindication", "indication_mismatch", "urgency") else None)
        de = _build_document_evidence(complete=True)
    else:  # MORE_INFO
        gate = random.choice(["missing_document", "clinical_evidence_insufficient"])
        pe = _build_policy_evidence(policy_row, relevance=random.uniform(0.6, 0.85))
        if gate == "missing_document":
            cce = _build_clinical_criteria_eval(True, criteria_pass_count=2)
            de = _build_document_evidence(complete=False)
        else:
            cce = _build_clinical_criteria_eval(True, criteria_pass_count=0, gate="clinical_evidence_insufficient")
            de = _build_document_evidence(complete=True)

    reasoning_result = aggregate_ml_features(policy_evidence=pe, clinical_criteria_eval=cce, document_evidence=de)
    decision = ml_agent.run(reasoning_result)
    return pe, cce, de, reasoning_result, decision


_generate_case._agent = None


def _find_tier_matching_params(target_tier, feature_vector, num_criteria_missing, now):
    """
    Closed-loop, VERIFIED against the real priority_intelligence ranker —
    not a blind guess. An earlier version hardcoded a single urgency/hours
    guess per tier (e.g. "Urgent, 10-18h ago" for MEDIUM); live-checking
    the result found only 1 of the intended 20 MEDIUM cases actually
    landed as MEDIUM (25 HIGH / 1 MEDIUM / 50 LOW came out instead of
    13/20/25) — the guessed timing didn't actually cross the real
    ranker's thresholds for these specific evidence values. This function
    fixes that by calling the SAME real ranker used in production and
    searching until the target tier is actually, verifiably hit.
    """
    import pandas as pd
    from priority_intelligence.ranker import get_ranker
    from priority_intelligence.safety import apply_safety_overrides
    from priority_intelligence.tiers import priority_tier as _tier_fn

    def try_case(urgency, hours_ago, care_setting):
        submitted_at = now - timedelta(hours=hours_ago)
        case = pd.DataFrame([{
            "request_id": "CALIBRATION", "policy_score": feature_vector["policy_score"],
            "documentation_score": feature_vector["documentation_score"],
            "clinical_evidence_score": feature_vector["clinical_evidence_score"],
            "num_criteria_missing": num_criteria_missing, "urgency": urgency,
            "care_setting": care_setting, "submitted_at": submitted_at.isoformat(),
        }])
        ranked = get_ranker().rank(case, pd.Timestamp(now))
        ranked = apply_safety_overrides(ranked)
        return _tier_fn(ranked.iloc[0]["priority_score"]), submitted_at

    if target_tier == "HIGH":
        # Emergency alone guarantees priority_score >= 90 regardless of
        # every other factor (safety.py's np.maximum floor) — no search
        # needed, this can never fail.
        _, submitted_at = try_case("Emergency", random.uniform(0.5, 6), "Emergency Department")
        return "Emergency", submitted_at, "Emergency Department"

    if target_tier == "MEDIUM":
        # Urgent's SLA is 24h; "breach imminent" (forces HIGH) fires at
        # hours_pending >= 22h. Where a given case's score actually
        # crosses the MEDIUM threshold (20) is EVIDENCE-DEPENDENT — found
        # live to sit anywhere from ~17h to ~21h pending depending on the
        # row's own policy/clinical scores, not a single fixed value.
        # Scanning ascending and taking the FIRST hour that lands in
        # MEDIUM (rather than a fixed guess) finds THIS row's own
        # earliest/lowest crossing point — the one with the most runway
        # before real-time drift pushes it toward the 22h breach-imminent
        # line. Real, unavoidable limitation (documented for the user,
        # not hidden): hours_pending is derived fresh from wall-clock time
        # on every query, by design — it's what makes the priority system
        # escalate a genuinely-neglected case at all. A MEDIUM case
        # calibrated today WILL eventually drift toward HIGH given enough
        # real elapsed time; re-run this script's --refresh-tiers-only
        # mode (see README) shortly before a presentation to re-freshen it.
        for tenths in range(60, 220):  # 6.0h .. 21.9h in 0.1h steps
            hours_ago = tenths / 10.0
            tier, submitted_at = try_case("Urgent", hours_ago, "Outpatient")
            if tier == "MEDIUM":
                return "Urgent", submitted_at, "Outpatient"
        return "Urgent", submitted_at, "Outpatient"  # best-effort fallback, logged by caller

    for hours_ago in [1, 2, 4, 6, 0.5, 8]:
        tier, submitted_at = try_case("Routine", hours_ago, "Outpatient")
        if tier == "LOW":
            return "Routine", submitted_at, "Outpatient"
    return "Routine", submitted_at, "Outpatient"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--doctors", type=int, default=None, help="Limit to first N doctors (for testing)")
    parser.add_argument("--per-doctor", type=int, default=30)
    args = parser.parse_args()

    _generate_case._agent = MLTriageAgent()
    conn = _conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT id, email, specialization, \"providerId\", name, hospital FROM users WHERE role='DOCTOR' ORDER BY email")
    doctors = cur.fetchall()
    if args.doctors:
        doctors = doctors[: args.doctors]

    cur.execute("SELECT id, \"firstName\", \"lastName\", age, gender, \"dateOfBirth\", \"insurancePlanId\", email FROM patients WHERE id LIKE 'PAT%' ORDER BY id")
    patients = cur.fetchall()

    cur.execute("SELECT \"planId\", \"payerName\" FROM insurance_plans")
    plans = {row["planId"]: row["payerName"] for row in cur.fetchall()}

    print(f"Doctors: {len(doctors)}, patient pool: {len(patients)}")
    per_doctor = args.per_doctor
    scale = per_doctor / 30.0
    bucket_counts = {k: max(1, round(v * scale)) for k, v in BUCKET_COUNTS.items()}
    # Reconcile rounding so the per-doctor total exactly matches per_doctor.
    diff = per_doctor - sum(bucket_counts.values())
    bucket_counts["AUTO_APPROVE"] += diff

    total_pend_slots = bucket_counts["PEND"] * len(doctors)
    print(f"Per-doctor buckets: {bucket_counts} -> total PEND slots across all doctors: {total_pend_slots}")
    if total_pend_slots < 58:
        print("WARNING: fewer than 58 PEND slots available for the pinned 13/20/25 priority tiers — increase --per-doctor.")

    # Assign the pinned 13 HIGH / 20 MEDIUM / 25 LOW across PEND slots in
    # generation order; remaining PEND slots vary naturally.
    pinned_tiers = ["HIGH"] * 13 + ["MEDIUM"] * 20 + ["LOW"] * 25
    random.shuffle(pinned_tiers)
    pinned_iter = iter(pinned_tiers)

    now = datetime.now(timezone.utc)
    inserted = {"AUTO_APPROVE": 0, "MANUAL_APPROVE": 0, "PEND": 0, "MORE_INFO": 0}
    used_patient_idx = 0
    seq = 0

    for doctor in doctors:
        specialty = doctor["specialization"] or "General Practice"
        profiles = SPECIALTY_PROFILES.get(specialty, SPECIALTY_PROFILES["General Practice"])
        bucket_plan = (
            ["AUTO_APPROVE"] * bucket_counts["AUTO_APPROVE"]
            + ["MANUAL_APPROVE"] * bucket_counts["MANUAL_APPROVE"]
            + ["PEND"] * bucket_counts["PEND"]
            + ["MORE_INFO"] * bucket_counts["MORE_INFO"]
        )
        random.shuffle(bucket_plan)

        for bucket in bucket_plan:
            patient = patients[used_patient_idx % len(patients)]
            used_patient_idx += 1
            profile = random.choice(profiles)
            seq += 1
            auth_id = f"PA-SYN-{seq:05d}"

            pe, cce, de, reasoning_result, decision = _generate_case(cur, profile, bucket)

            # Pinned tiers only apply to rows that ACTUALLY decided PEND —
            # a "PEND-bucket-targeted" row that leaked to APPROVE/
            # MORE_INFORMATION will never show up in the real "Needs
            # Review" queue at all, so pinning it would silently waste one
            # of the 58 guaranteed slots. Checking decision["outcome"]
            # alone isn't enough: MANUAL_APPROVE-bucket rows ALSO decide
            # PEND internally by construction (that's the whole point —
            # they get manually overridden to Approved afterward), so
            # without also requiring bucket=="PEND" here, those rows were
            # silently consuming pinned tier slots for a status that would
            # never actually reach "Needs Review" — found live: HIGH/
            # MEDIUM counts came in under 13/20 despite 104 real PEND rows
            # being comfortably more than the 58 needed.
            pinned_tier = next(pinned_iter, None) if bucket == "PEND" and decision["outcome"] == "PEND" else None

            if pinned_tier:
                urgency, submitted_at, care_setting = _find_tier_matching_params(
                    pinned_tier, reasoning_result["featureVector"], reasoning_result["numCriteriaMissing"], now
                )
            elif bucket == "MORE_INFO":
                urgency, hours_ago = (random.choice(["Routine", "Urgent"]), random.uniform(1, 48))
                submitted_at = now - timedelta(hours=hours_ago)
                care_setting = random.choice(["Outpatient", "Outpatient", "Inpatient"])
            else:
                # Kept under 15h regardless of urgency — a wider range
                # (an earlier version went up to 96h) let a random Routine
                # case occasionally roll past its own 72h SLA and force
                # HIGH via the safety override, unpredictably inflating
                # the guaranteed-13 HIGH count for reasons that had
                # nothing to do with the pinned demo set. Only affects
                # PEND rows the pinned_iter didn't reach (AUTO_APPROVE/
                # MANUAL_APPROVE never read urgency for their outcome —
                # it's cosmetic for those, since they never enter the
                # PEND queue at all).
                urgency, hours_ago = (random.choices(["Routine", "Urgent", "Emergency"], weights=[70, 25, 5])[0], random.uniform(1, 15))
                submitted_at = now - timedelta(hours=hours_ago)
                care_setting = random.choice(["Outpatient", "Outpatient", "Inpatient"])

            row = dict(
                auth_id=auth_id, doctor=doctor, patient=patient, profile=profile, plans=plans,
                pe=pe, cce=cce, de=de, reasoning_result=reasoning_result, decision=decision,
                urgency=urgency, care_setting=care_setting, submitted_at=submitted_at, bucket=bucket,
            )
            if not args.dry_run:
                _insert_case(cur, row)
            inserted[bucket] += 1

        if not args.dry_run:
            conn.commit()
        print(f"  {doctor['email']} ({specialty}): {len(bucket_plan)} authorizations done")

    print("Totals:", inserted, "grand total:", sum(inserted.values()))
    if args.dry_run:
        print("DRY RUN — nothing written.")
    cur.close()
    conn.close()


def _insert_case(cur, row):
    auth_id = row["auth_id"]
    doctor = row["doctor"]
    patient = row["patient"]
    profile = row["profile"]
    pe, cce, de = row["pe"], row["cce"], row["de"]
    reasoning_result, decision = row["reasoning_result"], row["decision"]
    submitted_at = row["submitted_at"]
    bucket = row["bucket"]

    plan_id = patient["insurancePlanId"] or "PLAN001"
    payer_name = row["plans"].get(plan_id, "Medicare")

    patient_json = {
        "name": f"{patient['firstName']} {patient['lastName']}", "patientId": patient["id"],
        "dateOfBirth": str(patient["dateOfBirth"]) if patient["dateOfBirth"] else None,
        "gender": patient["gender"], "age": patient["age"], "email": patient["email"],
        "memberId": patient["id"],
    }
    doctor_json = {"providerId": doctor["providerId"], "name": doctor["name"], "specialization": doctor["specialization"], "hospital": doctor["hospital"]}
    insurance_json = {"provider": payer_name, "plan": plan_id, "realPlanId": plan_id, "coverageStatus": "Active"}
    clinical_json = {"diagnosis": profile["diagnosis"], "icdCode": profile["icd10"], "secondaryDiagnoses": None, "notes": f"Patient presents with {profile['diagnosis'].lower()}, clinically documented and consistent with the requested service."}
    treatment_json = {"name": profile["service"], "type": profile["serviceType"], "urgency": row["urgency"], "placeOfService": row["care_setting"], "code": None}

    target_status = TRIAGE_OUTCOME_TO_STATUS[decision["outcome"]]
    decision_source = "AUTOMATED_ML"
    reviewed_by, review_note, reviewed_at = None, None, None

    if bucket == "MANUAL_APPROVE":
        # Real pipeline decided PEND; a nurse/admin then manually approves —
        # mirrors PATCH /:id/review's real field-set exactly.
        target_status = "Approved"
        decision_source = "MANUAL_REVIEWER"
        reviewed_by = "user-nurse"
        review_note = "Reviewed evidence and clinical documentation — approving based on documented medical necessity."
        reviewed_at = submitted_at + timedelta(hours=random.uniform(2, 20))

    cur.execute(
        """INSERT INTO authorizations (id, "patientId", "providerId", patient, provider, insurance, payer, clinical, treatment, status, "submittedAt", "submittedDate", submitted, message, "createdBy", role, "decisionSource", "reviewedBy", "reviewNote", "reviewedAt", "createdAt", "updatedAt")
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (
            auth_id, patient["id"], doctor["providerId"], json.dumps(patient_json), json.dumps(doctor_json), json.dumps(insurance_json), payer_name,
            json.dumps(clinical_json), json.dumps(treatment_json), target_status, submitted_at, submitted_at.isoformat(), "synthetic seed",
            decision.get("reason") or "Synthetic demo record.", doctor["id"], "DOCTOR", decision_source, reviewed_by, review_note, reviewed_at,
            submitted_at, reviewed_at or submitted_at,
        ),
    )

    ml_features = dict(reasoning_result)
    explanation = _build_explanation(decision, ml_features.get("featureVector", {}), pe, cce, de)
    eval_id = str(uuid.uuid4())
    processing_ms = random.randint(35000, 85000)
    cur.execute(
        """INSERT INTO triage_evaluations (id, "authorizationId", "requestedService", diagnosis, "planId", "decisionOutcome", "decisionConfidence", decision, "policyEvidence", "clinicalEvidence", "clinicalCriteriaEval", "documentEvidence", "mlFeatures", explanation, "evaluatedBy", "processingStartedAt", "processingCompletedAt", "processingDurationMs", "createdAt", "updatedAt")
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (
            eval_id, auth_id, profile["service"], profile["diagnosis"], patient["insurancePlanId"], decision["outcome"], decision.get("confidence"),
            json.dumps(decision), json.dumps(pe), json.dumps({}), json.dumps(cce), json.dumps(de), json.dumps(ml_features), json.dumps(explanation),
            doctor["id"], submitted_at, submitted_at + timedelta(milliseconds=processing_ms), processing_ms, submitted_at, submitted_at,
        ),
    )

    doc_types = ["CLINICAL_NOTES", "PRESCRIPTION"] if de["nDocumentsSubmitted"] >= 2 else ["CLINICAL_NOTES"]
    for doc_type in doc_types:
        file_path = CATEGORY_FILES.get(doc_type)
        if file_path is None:
            continue
        cur.execute(
            """INSERT INTO documents (id, "authorizationId", "fileName", "mimeType", "storageUrl", "documentType", "createdAt", "updatedAt")
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (str(uuid.uuid4()), auth_id, file_path.name, "application/pdf", str(file_path), doc_type, submitted_at, submitted_at),
        )

    cur.execute(
        """INSERT INTO audit_events (id, "authorizationId", action, actor, details, "createdAt", "updatedAt")
           VALUES (%s,%s,%s,%s,%s,%s,%s)""",
        (str(uuid.uuid4()), auth_id, "AUTHORIZATION_CREATED", doctor["id"], json.dumps({"source": "synthetic_seed"}), submitted_at, submitted_at),
    )
    cur.execute(
        """INSERT INTO audit_events (id, "authorizationId", action, actor, details, "createdAt", "updatedAt")
           VALUES (%s,%s,%s,%s,%s,%s,%s)""",
        (str(uuid.uuid4()), auth_id, "TRIAGE_EVALUATION_COMPLETED", doctor["id"], json.dumps({"evaluationId": eval_id, "decision": decision["outcome"]}), submitted_at, submitted_at),
    )
    if bucket == "MANUAL_APPROVE":
        cur.execute(
            """INSERT INTO audit_events (id, "authorizationId", action, actor, details, "createdAt", "updatedAt")
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (str(uuid.uuid4()), auth_id, "ADMIN_DECISION_RECORDED", reviewed_by, json.dumps({"decision": "Approved", "note": review_note}), reviewed_at, reviewed_at),
        )


if __name__ == "__main__":
    main()
