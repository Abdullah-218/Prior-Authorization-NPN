"""
Policy Score Correlation Correction (item #3, 2026-08-20)
=============================================================
Fixes the documented train/inference gap for policy_score (see
coverage_reasoning_agent.py's module docstring and
docs/PROGRESS_TRACKER.md's "what's next for accuracy" discussion).

THE ACTUAL GAP, precisely (found by reading ml/generate_dataset.py
directly rather than trusting the old docstring's framing):
_estimate_policy_score()'s FORMULA is an EXACT reproduction of the
training generator's formula, not an approximation of it — both are
`100*(0.5+0.5*relevance) - 40*(not diagnosis_supported), clipped [0,100]`.
The real gap is one level up, in what "relevance" MEANS in each case:

  - Training: rag_relevance = policy_quality + tiny_jitter(std=0.04) —
    policy_quality is an abstract Beta-distributed "quality" latent that
    is ALSO reused directly in label generation (0.35 weight in the
    approve-probability formula). Because rag_relevance is a near-exact
    copy of policy_quality (std=0.04 jitter is tiny relative to a Beta
    distribution's typical spread), policy_score ends up artificially,
    tightly entangled with the label through this shared cause.
  - Inference: relevance_score comes from REAL RAG cosine-distance
    retrieval — a genuinely different kind of measurement (semantic
    textual match between query and policy text), not a proxy for
    "abstract deservingness." documentation_score/clinical_evidence_score
    don't have this problem: their training-time simulation (ratio of
    matched/required, ratio of passed/total) is the SAME computational
    TYPE as what Document/Clinical Agent compute for real at inference
    (a ratio over real vs. simulated underlying counts) — only
    policy_score's training-time input had no inference-time analog.

WHY THIS SCRIPT, NOT A FULL DATASET REGENERATION:
ml/generate_dataset.py's own POLICIES import (`from policy_corpus import
...`) has been missing from this codebase since before this session (see
that file's own 2026-08-19 note) — full regeneration would require
reconstructing an entire synthetic policy corpus (required documents,
clinical criteria, category/plan-type resolution rules) from nothing,
which is fabricating the dataset's structural ground truth, not fixing
one identified flaw in it. This script instead corrects the ONE real
existing dataset (ml_training_set.csv, 9,028 real rows already in
production use) precisely and losslessly:

  1. Recover the original per-row rag_relevance EXACTLY from policy_score
     + diagnosis_supported. The generator's formula is invertible with
     zero information loss: for diagnosis_supported==1, policy_score
     ranges over [50,100] (rag_relevance in [0,1] never triggers the
     outer clip); for diagnosis_supported==0, policy_score ranges over
     [10,60] (same). Verified against all 9,028 rows: recovered values
     land exactly in [0,1], confirming the inversion is exact, not an
     approximation.
  2. Blend the recovered value with fresh, independent randomness —
     modeling that a REAL RAG relevance signal is a genuinely useful but
     NOISY, PARTIAL proxy for true policy match quality, not a near-exact
     copy of whatever "deservingness" a label-generation process used.
     60% original signal / 40% independent noise is a judgment call
     (documented as such, not claimed to be empirically derived — there
     is no real outcomes dataset yet to calibrate the "correct" split
     against, see the Phase 4/"open feedback loop" discussion) chosen to
     preserve genuine signal (a well-matched, well-documented request
     SHOULD still tend to retrieve better) while meaningfully reducing
     the artificial near-determinism the original 0.04-std jitter left
     in place.
  3. Recompute policy_score with the EXACT SAME original formula — only
     this one upstream input changes, nothing about the formula, the
     other 3 features, the labels, or the train/val/test/holdout splits.

Usage:
    python3 ml/fix_policy_score_correlation.py
    # writes ml/data/processed/ml_training_set_corrected.csv
    # (original ml_training_set.csv is untouched)
"""
import numpy as np
import pandas as pd

import config

SEED = 20260820  # fixed, dated seed — reproducible, distinct from the generator's own seeds (42, 7)
ORIGINAL_SIGNAL_WEIGHT = 0.60
INDEPENDENT_NOISE_WEIGHT = 0.40
JITTER_STD = 0.03


def recover_rag_relevance(policy_score, diagnosis_supported):
    """Exact inverse of generate_dataset.py's policy_score formula."""
    offset = np.where(diagnosis_supported == 1, 50, 10)
    return (policy_score - offset) / 50


def recompute_policy_score(rag_relevance, diagnosis_supported):
    """Exact reproduction of generate_dataset.py's forward formula."""
    score = 100 * (0.5 + 0.5 * rag_relevance)
    score = np.where(diagnosis_supported == 0, score - 40, score)
    return np.clip(score, 0, 100).round(1)


def main():
    rng = np.random.default_rng(SEED)

    df = pd.read_csv(config.ML_TRAINING_SET_PATH)
    n = len(df)

    rag_relevance_recovered = recover_rag_relevance(df["policy_score"].to_numpy(), df["diagnosis_supported"].to_numpy())
    out_of_range = ((rag_relevance_recovered < -1e-9) | (rag_relevance_recovered > 1 + 1e-9)).sum()
    assert out_of_range == 0, f"Inversion produced {out_of_range} out-of-[0,1] values — formula assumption violated, do not proceed."

    independent_noise = rng.beta(2, 2, size=n)
    jitter = rng.normal(0, JITTER_STD, size=n)
    rag_relevance_corrected = np.clip(
        ORIGINAL_SIGNAL_WEIGHT * rag_relevance_recovered + INDEPENDENT_NOISE_WEIGHT * independent_noise + jitter,
        0, 1,
    )

    policy_score_corrected = recompute_policy_score(rag_relevance_corrected, df["diagnosis_supported"].to_numpy())

    # ---- report the actual effect, honestly, before/after ----
    df_before = df.copy()
    df_after = df.copy()
    df_after["policy_score"] = policy_score_corrected

    def label_gap(frame):
        # mean policy_score for APPROVE rows minus mean for PEND rows —
        # a simple, interpretable measure of how strongly policy_score by
        # itself separates the two classes.
        approve_mean = frame.loc[frame["label"] == "APPROVE", "policy_score"].mean()
        pend_mean = frame.loc[frame["label"] == "PEND", "policy_score"].mean()
        return approve_mean, pend_mean, approve_mean - pend_mean

    before = label_gap(df_before)
    after = label_gap(df_after)
    corr_before = df_before["policy_score"].corr((df_before["label"] == "APPROVE").astype(int))
    corr_after = df_after["policy_score"].corr((df_after["label"] == "APPROVE").astype(int))

    print("=== policy_score vs. label separation, before vs. after ===")
    print(f"BEFORE — APPROVE mean: {before[0]:.2f}  PEND mean: {before[1]:.2f}  gap: {before[2]:.2f}  point-biserial r: {corr_before:.3f}")
    print(f"AFTER  — APPROVE mean: {after[0]:.2f}  PEND mean: {after[1]:.2f}  gap: {after[2]:.2f}  point-biserial r: {corr_after:.3f}")
    print()
    print("=== policy_score distribution, before vs. after ===")
    print(pd.DataFrame({"before": df_before["policy_score"], "after": df_after["policy_score"]}).describe().round(2))

    out_path = config.DATA_DIR / "ml_training_set_corrected.csv"
    df_after.to_csv(out_path, index=False)
    print(f"\nWrote corrected dataset -> {out_path}")
    print(f"Original untouched at -> {config.ML_TRAINING_SET_PATH}")


if __name__ == "__main__":
    main()
