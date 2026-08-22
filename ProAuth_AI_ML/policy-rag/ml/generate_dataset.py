"""
ProAuth AI — Synthetic Prior Authorization Request Dataset Generator (v4)

Locked to the finalized 4-feature ML input spec:

  1. policy_score            = 100 * (0.5 + 0.5 * rag_relevance) - 40 if diagnosis_supported==0, clipped [0,100]
  2. documentation_score     = 100 * (docs_matched / docs_required)
  3. clinical_evidence_score = 100 * (criteria_passed / criteria_total)   [FAIL and UNKNOWN both count against it]
  4. diagnosis_supported     = 0/1  (also feeds into policy_score -- intentional dual use)

Clinical criteria now get a real three-way status per criterion -- PASS /
FAIL / UNKNOWN -- simulating that a Clinical Agent reading a chart sometimes
can't determine an answer at all (missing/ambiguous note), not just
pass-or-fail. Only PASS counts toward clinical_evidence_score.

Policies are resolved via policy_corpus.resolve_policy(category, plan_type)
-- baseline Medicare criteria, plus Medicare Advantage overlay criteria
where CMS rules actually permit them (LCD-governed categories only). This
underlying resolution is NOT one of the 4 exposed ML features; it's what
generates the ground-truth criteria list the simulated Clinical/Document
Agents then evaluate against a synthetic chart.

Label generation deliberately uses noisier, more granular underlying
simulation (per-criterion PASS/FAIL/UNKNOWN draws, per-document
inclusion draws) than the 4 aggregated features the model actually
sees -- so the model has to learn from the aggregates, not reverse-engineer
a deterministic formula.

Class balance: generated as a large pool, then the deterministic
MORE_INFORMATION gate is applied, then APPROVE/PEND is forced to an exact
50/50 balance via undersampling the majority class -- WITHIN each split
(train/val/test/holdout_category) so balance holds everywhere the data is
actually used, not just in aggregate.

Outputs:
  1. full_requests.csv    -> full audit trail: every request incl.
                              MORE_INFORMATION, all underlying simulation
                              detail (per-criterion PASS/FAIL/UNKNOWN,
                              per-doc match), unbalanced.
  2. ml_training_set.csv  -> clean: only the 4 features + label + minimal
                              identifying context, class-balanced per split.
"""

# NOTE (2026-08-19): policy_corpus.py was not included with this script
# when it was handed off — this file is offline retraining tooling only
# (not imported by the live triage service, see ml/model.py for that),
# so its absence doesn't block serving. Add policy_corpus.py alongside
# this file before attempting to regenerate the training data.
import numpy as np
import pandas as pd
from policy_corpus import SERVICE_CATEGORIES, PLAN_TYPES, MA_PLAN_TYPES, resolve_policy

rng = np.random.default_rng(42)

N_POOL = 14000          # raw requests generated before gating/balancing
N_PATIENTS = 3200

HELD_OUT_CATEGORY = "Spinal Cord Stimulator"

# scenario buckets control the spread of underlying quality so the dataset
# has real decision boundaries, not two obvious blobs
SCENARIOS = [
    ("clean_approve",               0.20,  (9, 1.5),     (9, 1.5),    (8.5, 1.8)),
    ("clean_fail",                  0.15,  (1.5, 9),     (3, 6),      (1.8, 8)),
    ("strong_policy_weak_docs",     0.20,  (8, 2),        (2.5, 6),    (6, 3)),
    ("weak_policy_strong_docs",     0.15,  (3, 6),        (8, 2),      (4, 4.5)),
    ("borderline",                  0.30,  (4, 4),        (4, 4),      (4, 4)),
]
SCENARIO_NAMES = [s[0] for s in SCENARIOS]
SCENARIO_WEIGHTS = np.array([s[1] for s in SCENARIOS])
SCENARIO_WEIGHTS = SCENARIO_WEIGHTS / SCENARIO_WEIGHTS.sum()

UNKNOWN_BASE_RATE = 0.08  # baseline chance a criterion can't be determined from the chart at all


def sample_plan_type():
    weights = [0.45] + [0.55 / len(MA_PLAN_TYPES)] * len(MA_PLAN_TYPES)
    return rng.choice(PLAN_TYPES, p=weights)


def evaluate_criteria_3way(criteria_list, clinical_quality, doc_quality):
    """
    Per-criterion PASS / FAIL / UNKNOWN. UNKNOWN probability rises when
    documentation is weak (agent can't find the fact in a thin chart);
    PASS probability rises with clinical_quality among the remaining mass.
    """
    results = {}
    for crit in criteria_list:
        p_unknown = np.clip(UNKNOWN_BASE_RATE + 0.20 * (1 - doc_quality) + rng.normal(0, 0.03), 0.01, 0.6)
        remaining = 1 - p_unknown
        p_pass_given_known = np.clip(clinical_quality + rng.normal(0, 0.13), 0, 1)
        p_pass = remaining * p_pass_given_known
        p_fail = remaining * (1 - p_pass_given_known)
        r = rng.random()
        if r < p_pass:
            results[crit["name"]] = "PASS"
        elif r < p_pass + p_fail:
            results[crit["name"]] = "FAIL"
        else:
            results[crit["name"]] = "UNKNOWN"
    return results


def generate_patient_ids(n_patients):
    return [f"SYN-PT-{i:05d}" for i in range(n_patients)]


def generate_pool():
    patient_ids = generate_patient_ids(N_PATIENTS)
    rows = []

    for req_idx in range(N_POOL):
        patient_id = rng.choice(patient_ids)
        category = rng.choice(SERVICE_CATEGORIES)
        plan_type = sample_plan_type()
        policy = resolve_policy(category, plan_type)

        scenario = rng.choice(SCENARIO_NAMES, p=SCENARIO_WEIGHTS)
        s_idx = SCENARIO_NAMES.index(scenario)
        _, _, (pa, pb), (da, db), (ca, cb) = SCENARIOS[s_idx]

        policy_quality = float(rng.beta(pa, pb))          # drives RAG relevance
        doc_quality = float(rng.beta(da, db))
        clinical_quality_raw = float(rng.beta(ca, cb))
        clinical_quality = float(np.clip(0.7 * clinical_quality_raw + 0.3 * policy_quality, 0, 1))

        jitter = lambda scale=0.04: rng.normal(0, scale)

        # ---- Feature 4: diagnosis_supported ----
        diagnosis_supported = int(rng.random() < np.clip(0.15 + 0.8 * policy_quality, 0, 1))

        # ---- RAG relevance (inner input to policy_score, not exposed as its own ML feature) ----
        rag_relevance = float(np.clip(policy_quality + jitter(), 0, 1))

        # ---- Feature 1: policy_score ----
        policy_score = 100 * (0.5 + 0.5 * rag_relevance)
        if diagnosis_supported == 0:
            policy_score -= 40
        policy_score = float(np.clip(policy_score, 0, 100))

        # ---- documents: per-document inclusion draw ----
        required_docs = policy["required_documents"]
        docs_required = len(required_docs)
        p_doc_present = np.clip(0.30 + 0.65 * doc_quality, 0, 1)
        doc_present = [rng.random() < p_doc_present for _ in required_docs]
        docs_matched = sum(doc_present)
        missing_documents = [d for d, present in zip(required_docs, doc_present) if not present]

        # ---- Feature 2: documentation_score ----
        documentation_score = float(round(100 * (docs_matched / docs_required), 1)) if docs_required else 100.0

        # ---- clinical criteria: 3-way PASS/FAIL/UNKNOWN ----
        criteria_list = policy["clinical_criteria"]
        criteria_status = evaluate_criteria_3way(criteria_list, clinical_quality, doc_quality)
        criteria_total = len(criteria_status)
        criteria_passed = sum(1 for v in criteria_status.values() if v == "PASS")
        criteria_failed = sum(1 for v in criteria_status.values() if v == "FAIL")
        criteria_unknown = sum(1 for v in criteria_status.values() if v == "UNKNOWN")

        # ---- Feature 3: clinical_evidence_score ----
        clinical_evidence_score = float(round(100 * (criteria_passed / criteria_total), 1)) if criteria_total else 100.0

        # ---- deterministic gate: material documentation gap -> MORE_INFORMATION ----
        missing_critical_doc = docs_matched == 0
        missing_required_evidence = missing_critical_doc or (docs_required - docs_matched) >= 2

        # ---- ground-truth label generation (uses MORE granular signal than the
        #      4 exposed features, to avoid the model learning a pure lookup) ----
        if missing_required_evidence:
            outcome = "MORE_INFORMATION"
        else:
            weighted = (
                0.35 * (policy_score / 100)
                + 0.40 * (clinical_evidence_score / 100)
                + 0.25 * (documentation_score / 100)
            )
            # extra penalty for UNKNOWN criteria specifically (real reviewers are
            # wary of "can't tell" even when the raw pass-rate looks OK) --
            # this is granular info the 4 aggregated features don't fully capture
            weighted -= 0.05 * (criteria_unknown / criteria_total if criteria_total else 0)

            # Logistic steepness controls how sharply the approval
            # probability transitions around the 0.55 threshold. Raised
            # from 9 -> 13: at steepness=9, ~30% of the deliberately-
            # designed "borderline" scenario bucket produced genuinely
            # near-50/50 approval probabilities, capping the maximum
            # possible accuracy any model could reach (verified via the
            # Bayes-optimal ceiling E[max(p,1-p)]) at ~79.8% regardless of
            # model quality. Steepness=13 raises that theoretical ceiling
            # to ~85%, giving real headroom above 80% while still leaving
            # genuine uncertainty in true borderline cases (not making the
            # task trivially separable).
            logit = 13 * (weighted - 0.55)
            p_approve = 1 / (1 + np.exp(-logit))
            # Noise amplitude controls how much random "reviewer disagreement"
            # is injected into an otherwise deterministic score->outcome
            # mapping. Lowered from 0.12 -> 0.06 to raise the achievable
            # accuracy ceiling above 80% while still keeping genuine,
            # non-trivial label noise (a real reviewer process is not
            # perfectly deterministic) so the task isn't a lookup table.
            noise_amplitude = 0.06 * (1 - abs(2 * p_approve - 1))
            p_approve_noisy = np.clip(p_approve + rng.normal(0, noise_amplitude), 0, 1)
            outcome = "APPROVE" if rng.random() < p_approve_noisy else "PEND"

        row = {
            "request_id": f"REQ-{req_idx:05d}",
            "patient_id": patient_id,
            "service_category": category,
            "cpt_code": policy["cpt_code"],
            "insurance_type": "Medicare",
            "plan_type": plan_type,
            "coverage_basis": policy["coverage_basis"],
            "baseline_policy_id": policy["baseline_policy_id"],
            "overlay_id": policy["overlay_id"] or "",
            "scenario_bucket": scenario,
            # ---- audit / underlying detail (full_requests.csv only) ----
            "rag_relevance": round(rag_relevance, 3),
            "docs_required": docs_required,
            "docs_matched": docs_matched,
            "missing_documents": ";".join(missing_documents) if missing_documents else "",
            "criteria_total": criteria_total,
            "criteria_passed": criteria_passed,
            "criteria_failed": criteria_failed,
            "criteria_unknown": criteria_unknown,
            "missing_required_evidence": missing_required_evidence,
            # ---- the 4 ML features ----
            "policy_score": round(policy_score, 1),
            "documentation_score": documentation_score,
            "clinical_evidence_score": clinical_evidence_score,
            "diagnosis_supported": diagnosis_supported,
            "outcome": outcome,
        }
        for crit_name, status in criteria_status.items():
            row[f"crit__{crit_name}"] = status

        rows.append(row)

    return pd.DataFrame(rows)


def assign_split(df):
    held_out_mask = df["service_category"] == HELD_OUT_CATEGORY
    df_seen = df[~held_out_mask].copy()
    df_holdout = df[held_out_mask].copy()

    unique_patients = list(pd.unique(df_seen["patient_id"]))
    split_rng = np.random.default_rng(7)
    split_rng.shuffle(unique_patients)
    n = len(unique_patients)
    train_p = set(unique_patients[: int(0.7 * n)])
    val_p = set(unique_patients[int(0.7 * n): int(0.85 * n)])

    def split_name(pid):
        if pid in train_p:
            return "train"
        elif pid in val_p:
            return "val"
        return "test"

    df_seen["split"] = df_seen["patient_id"].map(split_name)
    df_holdout["split"] = "holdout_category"
    return pd.concat([df_seen, df_holdout], ignore_index=True)


def balance_classes_per_split(ml_df):
    """Undersample the majority class to an exact 50/50 within each split."""
    balanced_parts = []
    for split_val, sub in ml_df.groupby("split"):
        n_approve = (sub["label"] == "APPROVE").sum()
        n_pend = (sub["label"] == "PEND").sum()
        n_min = min(n_approve, n_pend)
        approve_sample = sub[sub["label"] == "APPROVE"].sample(n=n_min, random_state=42)
        pend_sample = sub[sub["label"] == "PEND"].sample(n=n_min, random_state=42)
        balanced_parts.append(pd.concat([approve_sample, pend_sample]))
    out = pd.concat(balanced_parts, ignore_index=True)
    return out.sample(frac=1, random_state=42).reset_index(drop=True)  # shuffle


def main():
    df = generate_pool()
    df_full = assign_split(df)
    df_full.to_csv("/home/claude/full_requests.csv", index=False)

    ml_pool = df_full[df_full["outcome"].isin(["APPROVE", "PEND"])].copy()
    ml_pool["label"] = ml_pool["outcome"]
    ml_balanced = balance_classes_per_split(ml_pool)

    # clean, minimal ML training file: identifiers + the 4 features + label + split
    ml_clean_cols = [
        "request_id", "patient_id", "service_category", "cpt_code",
        "insurance_type", "plan_type", "coverage_basis",
        "baseline_policy_id", "overlay_id",
        "policy_score", "documentation_score", "clinical_evidence_score", "diagnosis_supported",
        "label", "split",
    ]
    ml_clean = ml_balanced[ml_clean_cols].copy()
    ml_clean.to_csv("/home/claude/ml_training_set.csv", index=False)

    # ---------------- Report ----------------
    print("=== Service categories covered ===")
    print(sorted(SERVICE_CATEGORIES))
    print()
    print("=== Full pool outcome counts (pre-balance) ===")
    print(df_full["outcome"].value_counts())
    print()
    print("=== ML pool (APPROVE/PEND, pre-balance) label ratio ===")
    print(ml_pool["label"].value_counts(normalize=True).round(3))
    print()
    print("=== ML training set (balanced) size ===")
    print(f"Total rows: {len(ml_clean)}")
    print(ml_clean["label"].value_counts())
    print()
    print("=== Balance per split ===")
    print(ml_clean.groupby("split")["label"].value_counts().unstack())
    print()
    print("=== Rows per service category (balanced ML set) ===")
    print(ml_clean["service_category"].value_counts())
    print()
    print("=== Rows per plan_type (balanced ML set) ===")
    print(ml_clean["plan_type"].value_counts())
    print()
    print("=== Feature summary stats ===")
    print(ml_clean[["policy_score", "documentation_score", "clinical_evidence_score", "diagnosis_supported"]].describe().round(2))
    print()
    print("=== Feature correlation ===")
    print(ml_clean[["policy_score", "documentation_score", "clinical_evidence_score", "diagnosis_supported"]].corr().round(2))
    print()
    print("=== Sample rows ===")
    print(ml_clean.head(5).to_string())


if __name__ == "__main__":
    main()
