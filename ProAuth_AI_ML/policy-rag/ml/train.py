"""
ProAuth AI — Leak-Safe Training Pipeline (v6)
=================================================
Follows the reference train.py's methodology exactly, extended to compare
two model families instead of assuming one, and to produce the full set of
visualizations + Power-BI business exports on top.

WHY THIS IS "LEAK-SAFE" — EVERY DECISION POINT AND WHAT NEVER TOUCHES IT
---------------------------------------------------------------------------
1. SPLITS ARE RESPECTED, NOT RE-CUT. generate_dataset.py already assigned
   train/val/test/holdout_category by PATIENT (a patient's rows all land
   in one split — see its `assign_split()`), except for `holdout_category`
   itself, which is carved out by SERVICE CATEGORY (Spinal Cord Stimulator)
   before that patient-level split ever happens. That means a patient can
   legitimately appear in both `holdout_category` and `train` — that's
   intentional (it's testing generalization to an unseen *category*, not
   an unseen *patient*), not a bug. What matters for leakage is that
   `train` / `val` / `test` are patient-disjoint from each other, which
   they are (checked below, at model-build time, and would raise if not).

2. GROUP-AWARE CROSS-VALIDATION. All hyperparameter search inside `train`
   uses `StratifiedGroupKFold(groups=patient_id)` — even though train/val/
   test are already disjoint by patient, a single patient can have MULTIPLE
   requests inside `train` itself (different service categories, different
   times). Plain StratifiedKFold could split one patient's requests across
   both the CV-fold-used-for-fitting and the CV-fold-used-for-scoring,
   which is a real (if subtle) leakage path when a patient's requests
   share any residual similarity. Grouping by patient closes that path.

3. THRESHOLD SELECTION HAPPENS ONLY ON VAL. The 0.5-cutoff is not assumed;
   the decision threshold is swept and chosen to maximize (F1, balanced
   accuracy, accuracy) on `val` predictions from a model that was fit on
   `train` only — `val` never contributes a single row to fitting at this
   stage.

4. FINAL REFIT ON train+val, FINAL EVAL ON test AND holdout_category ONCE.
   Once hyperparameters (from train-only CV) and threshold (from val-only
   sweep) are both locked in, the winning pipeline is refit on `train+val`
   combined (standard practice once selection is finished — nothing is
   selected using this refit). `test` and `holdout_category` are each
   scored exactly once, at the very end, and neither ever appears in any
   CV fold, any threshold sweep, or any model-selection comparison.

MODEL SELECTION: LOGISTIC REGRESSION VS. RANDOM FOREST
---------------------------------------------------------
The reference script's chosen final model is a regularized Logistic
Regression. Rather than assume that's still the right call on this data,
both it and a comparably regularized Random Forest are run through the
identical group-aware CV + val-evaluation procedure, and the winner is
picked by the same explicit, inspectable rule used before: reject any
candidate with a train-val gap > OVERFIT_GAP_MAX (overfitting) or train
accuracy < UNDERFIT_TRAIN_ACC_MIN (underfitting), then take the highest
val ROC-AUC among what's left. Whichever wins becomes the ONLY model
carried into threshold tuning / refit / final evaluation — this script
does not train-then-discard a second full pipeline downstream of that
point, matching "no need to train everything, choose wisely."
"""

import json
import pickle
import warnings

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedGroupKFold, GridSearchCV
from sklearn.metrics import (
    accuracy_score, balanced_accuracy_score, f1_score, roc_auc_score, roc_curve,
    precision_recall_curve, confusion_matrix, classification_report, average_precision_score,
)

import config

warnings.filterwarnings("ignore")
sns.set_theme(style="whitegrid", palette="deep")

# ---- palette: light, readable confusion-matrix colormap + brand accents ----
LIGHT_CMAP = sns.light_palette("#3B82C4", as_cmap=True)   # soft pastel blue, capped below (see vmax in plot_confusion_matrix)
BRAND = "#0B4F6C"
ACCENT = "#14B8A6"
GOOD = "#0F7A42"
WARN = "#9A6300"
BAD = "#B42318"


# =============================================================================
# 1. Load data, respecting the supplied split, verifying no patient leakage
#    across train/val/test
# =============================================================================
def load_data():
    df = pd.read_csv(config.ML_TRAINING_SET_PATH)
    assert df.columns[-1] == "split"

    train = df[df.split == config.SPLIT_TRAIN].copy()
    val = df[df.split == config.SPLIT_VAL].copy()
    test = df[df.split == config.SPLIT_TEST].copy()
    holdout = df[df.split == config.SPLIT_HOLDOUT_CATEGORY].copy()

    # Leakage guard: train/val/test must be patient-disjoint. holdout_category
    # is allowed to overlap patients with the others (see docstring point 1) --
    # it is carved out by SERVICE CATEGORY, not by patient, and is only ever
    # used for the final, single, untouched generalization check.
    for a_name, a in [("train", train), ("val", val), ("test", test)]:
        for b_name, b in [("train", train), ("val", val), ("test", test)]:
            if a_name >= b_name:
                continue
            overlap = set(a[config.GROUP_COLUMN]) & set(b[config.GROUP_COLUMN])
            assert not overlap, f"Patient leakage between {a_name} and {b_name}: {len(overlap)} shared patients"

    print(f"train={len(train)}  val={len(val)}  test={len(test)}  holdout_category={len(holdout)}")
    print("Leakage check passed: train/val/test are patient-disjoint.\n")
    return train, val, test, holdout


# =============================================================================
# 2. Candidates — both group-CV-tuned, both eligible; only one survives
#    past this stage.
# =============================================================================
def build_candidates():
    return {
        "LogisticRegression": (
            Pipeline([("scaler", StandardScaler()),
                      ("model", LogisticRegression(max_iter=5000, solver="liblinear", random_state=config.RANDOM_STATE))]),
            {"model__C": np.logspace(-3, 2, 20), "model__penalty": ["l1", "l2"]},
        ),
        "RandomForest": (
            Pipeline([("scaler", StandardScaler()),
                      ("model", RandomForestClassifier(random_state=config.RANDOM_STATE))]),
            {
                "model__n_estimators": [150, 300],
                "model__max_depth": [4, 6, 8],
                "model__min_samples_leaf": [5, 15, 30],
            },
        ),
    }


def run_model_selection(train, val):
    X_train, y_train = train[config.FEATURES], (train[config.TARGET] == "APPROVE").astype(int)
    X_val, y_val = val[config.FEATURES], (val[config.TARGET] == "APPROVE").astype(int)
    groups_train = train[config.GROUP_COLUMN]

    cv = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=config.RANDOM_STATE)

    results, fitted = [], {}
    for name, (pipe, grid) in build_candidates().items():
        search = GridSearchCV(pipe, grid, scoring="roc_auc", cv=cv, n_jobs=-1, refit=True)
        search.fit(X_train, y_train, groups=groups_train)
        best = search.best_estimator_

        train_pred = best.predict(X_train)
        val_pred = best.predict(X_val)
        val_proba = best.predict_proba(X_val)[:, 1]

        train_acc = accuracy_score(y_train, train_pred) * 100
        val_acc = accuracy_score(y_val, val_pred) * 100
        gap = train_acc - val_acc
        val_auc = roc_auc_score(y_val, val_proba)
        val_f1 = f1_score(y_val, val_pred)

        overfit = gap > config.OVERFIT_GAP_MAX
        underfit = train_acc < config.UNDERFIT_TRAIN_ACC_MIN
        verdict = "REJECT (overfit)" if overfit else ("REJECT (underfit)" if underfit else "OK")

        results.append({
            "model": name, "cv_best_roc_auc": round(search.best_score_, 4),
            "best_params": json.dumps(search.best_params_),
            "train_accuracy_pct": round(train_acc, 2), "val_accuracy_pct": round(val_acc, 2),
            "train_val_gap_pts": round(gap, 2), "val_roc_auc": round(val_auc, 4),
            "val_f1": round(val_f1, 4), "verdict": verdict,
        })
        fitted[name] = (best, search.best_params_)
        print(f"[{name:20s}] cv_auc={search.best_score_:.4f}  train_acc={train_acc:5.2f}  "
              f"val_acc={val_acc:5.2f}  gap={gap:5.2f}  val_auc={val_auc:.4f}  -> {verdict}")

    results_df = pd.DataFrame(results)
    return results_df, fitted


def select_winner(results_df, fitted):
    ok = results_df[results_df["verdict"] == "OK"]
    pool = ok if len(ok) else results_df
    pool = pool.sort_values("val_roc_auc", ascending=False)
    winner_row = pool.iloc[0]
    name = winner_row["model"]
    _, best_params = fitted[name]
    return name, best_params, winner_row


# =============================================================================
# 3. Threshold selection — val only
# =============================================================================
def select_threshold(model, val):
    X_val, y_val = val[config.FEATURES], (val[config.TARGET] == "APPROVE").astype(int)
    proba = model.predict_proba(X_val)[:, 1]
    rows = []
    for t in np.linspace(0.20, 0.80, 601):
        pred = (proba >= t).astype(int)
        rows.append((t, f1_score(y_val, pred), balanced_accuracy_score(y_val, pred), accuracy_score(y_val, pred)))
    threshold = max(rows, key=lambda z: (z[1], z[2], z[3]))[0]
    return float(threshold)


# =============================================================================
# 4. Visualizations
# =============================================================================
def plot_model_comparison(results_df):
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    x = np.arange(len(results_df))
    axes[0].bar(results_df["model"], results_df["val_roc_auc"], color=[BRAND, ACCENT])
    axes[0].set_ylim(0.5, 1.0)
    axes[0].set_title("Validation ROC-AUC by model (group-aware CV)")
    axes[0].set_ylabel("ROC-AUC")

    colors = [BAD if v > config.OVERFIT_GAP_MAX else GOOD for v in results_df["train_val_gap_pts"]]
    axes[1].bar(results_df["model"], results_df["train_val_gap_pts"], color=colors)
    axes[1].axhline(config.OVERFIT_GAP_MAX, color=BAD, linestyle="--", linewidth=1,
                     label=f"overfit threshold ({config.OVERFIT_GAP_MAX} pts)")
    axes[1].set_title("Train − Val accuracy gap (overfitting check)")
    axes[1].set_ylabel("Percentage points")
    axes[1].legend()
    plt.tight_layout()
    plt.savefig(config.VIZ_DIR / "01_model_comparison.png", dpi=150)
    plt.close()


def plot_confusion_matrix(y_true, y_pred, title, filename):
    """Light-colored confusion matrix, counts + row-normalized percentages."""
    cm = confusion_matrix(y_true, y_pred, labels=[1, 0])
    cm_pct = cm / cm.sum() * 100
    labels = np.array([[f"{cm[i, j]}\n({cm_pct[i, j]:.1f}%)" for j in range(2)] for i in range(2)])

    fig, ax = plt.subplots(figsize=(5.5, 5))
    sns.heatmap(cm, annot=labels, fmt="", cmap=LIGHT_CMAP, cbar=True, vmax=cm.max() * 1.8,
                xticklabels=["APPROVE", "PEND"], yticklabels=["APPROVE", "PEND"], ax=ax,
                annot_kws={"fontsize": 11, "color": "#0F1B2A", "fontweight": "600"}, linewidths=1.5, linecolor="white")
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Actual")
    ax.set_title(title)
    plt.tight_layout()
    plt.savefig(config.VIZ_DIR / filename, dpi=150)
    plt.close()
    return cm, cm_pct


def plot_roc_pr(y_true, y_proba, title_suffix, filename):
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    fpr, tpr, _ = roc_curve(y_true, y_proba)
    auc_val = roc_auc_score(y_true, y_proba)
    axes[0].plot(fpr, tpr, label=f"AUC = {auc_val:.3f}", linewidth=2, color=BRAND)
    axes[0].plot([0, 1], [0, 1], linestyle="--", color="gray", linewidth=1)
    axes[0].set_xlabel("False Positive Rate"); axes[0].set_ylabel("True Positive Rate")
    axes[0].set_title(f"ROC Curve — {title_suffix}"); axes[0].legend()

    prec, rec, _ = precision_recall_curve(y_true, y_proba)
    ap = average_precision_score(y_true, y_proba)
    axes[1].plot(rec, prec, label=f"AP = {ap:.3f}", linewidth=2, color=WARN)
    axes[1].set_xlabel("Recall"); axes[1].set_ylabel("Precision")
    axes[1].set_title(f"Precision-Recall Curve — {title_suffix}"); axes[1].legend()
    plt.tight_layout()
    plt.savefig(config.VIZ_DIR / filename, dpi=150)
    plt.close()


def plot_feature_importance(model, model_name, filename):
    clf = model.named_steps["model"]
    if hasattr(clf, "feature_importances_"):
        importances = clf.feature_importances_
        ylabel = "Importance (impurity-based)"
    elif hasattr(clf, "coef_"):
        importances = np.abs(clf.coef_[0])
        ylabel = "Importance (|coefficient|, standardized features)"
    else:
        return None
    order = np.argsort(importances)[::-1]
    fig, ax = plt.subplots(figsize=(7.5, 5.5))
    ax.bar(np.array(config.FEATURES)[order], importances[order], color=ACCENT)
    ax.set_ylabel(ylabel)
    ax.set_title(f"Feature Importance — {model_name}")
    plt.xticks(rotation=20, ha="right")
    plt.tight_layout()
    plt.savefig(config.VIZ_DIR / filename, dpi=150)
    plt.close()
    return {config.FEATURES[i]: float(importances[i]) for i in order}


def plot_split_accuracy_bars(train_acc, val_acc, test_acc, holdout_acc, model_name):
    fig, ax = plt.subplots(figsize=(7, 5.5))
    labels = ["Train", "Val", "Test", "Holdout\n(unseen category)"]
    vals = [train_acc, val_acc, test_acc, holdout_acc]
    bars = ax.bar(labels, vals, color=[BRAND, ACCENT, "#7C3AED", WARN])
    ax.axhline(config.TARGET_ACCURACY, color=BAD, linestyle="--", linewidth=1, label=f"{config.TARGET_ACCURACY:.0f}% target")
    for b in bars:
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 1.0, f"{b.get_height():.1f}%",
                 ha="center", fontsize=10, fontweight="600")
    ax.set_ylim(0, 100)
    ax.set_ylabel("Accuracy (%)")
    ax.set_title(f"Final model ({model_name}): Train / Val / Test / True Holdout")
    ax.legend()
    plt.tight_layout()
    plt.savefig(config.VIZ_DIR / "05_train_val_test_holdout_accuracy.png", dpi=150)
    plt.close()


def plot_score_distributions(train, val):
    pool = pd.concat([train, val])
    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    for ax, feat in zip(axes.flat, config.FEATURES):
        for label, color in [("APPROVE", GOOD), ("PEND", WARN)]:
            sns.kdeplot(pool[pool[config.TARGET] == label][feat], ax=ax, label=label, fill=True, alpha=0.3, color=color)
        ax.set_title(feat)
        ax.legend()
    plt.suptitle("Feature distributions by outcome (train + val)")
    plt.tight_layout()
    plt.savefig(config.VIZ_DIR / "06_feature_distributions_by_label.png", dpi=150)
    plt.close()


def plot_threshold_sweep(model, val):
    X_val, y_val = val[config.FEATURES], (val[config.TARGET] == "APPROVE").astype(int)
    proba = model.predict_proba(X_val)[:, 1]
    ts = np.linspace(0.20, 0.80, 601)
    f1s = [f1_score(y_val, (proba >= t).astype(int)) for t in ts]
    accs = [accuracy_score(y_val, (proba >= t).astype(int)) for t in ts]
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(ts, f1s, label="F1", color=BRAND, linewidth=2)
    ax.plot(ts, accs, label="Accuracy", color=ACCENT, linewidth=2)
    ax.axvline(0.5, color="gray", linestyle=":", linewidth=1, label="naive 0.5 cutoff")
    ax.set_xlabel("Decision threshold (approve_probability ≥ t)")
    ax.set_ylabel("Score")
    ax.set_title("Threshold sweep on validation set only")
    ax.legend()
    plt.tight_layout()
    plt.savefig(config.VIZ_DIR / "08_threshold_sweep.png", dpi=150)
    plt.close()


# =============================================================================
# Main
# =============================================================================
def main():
    train, val, test, holdout = load_data()

    print("=" * 100)
    print("MODEL SELECTION — LogisticRegression vs RandomForest, both group-aware-CV-tuned on train,")
    print("evaluated once on val (never on test/holdout at this stage)")
    print("=" * 100)
    results_df, fitted = run_model_selection(train, val)
    results_df.to_csv(config.REPORTS_DIR / "model_comparison.csv", index=False)
    plot_model_comparison(results_df)

    model_name, best_params, winner_row = select_winner(results_df, fitted)
    winner_model, _ = fitted[model_name]
    print(f"\nWINNER: {model_name}  (val_auc={winner_row['val_roc_auc']}, "
          f"gap={winner_row['train_val_gap_pts']} pts, verdict={winner_row['verdict']})")

    print("\nSelecting decision threshold on validation set only...")
    threshold = select_threshold(winner_model, val)
    print(f"Selected threshold: {threshold:.3f}")
    plot_threshold_sweep(winner_model, val)

    # ---- final refit on train+val, exactly matching reference's "dev" step ----
    print("\nRefitting winning model + hyperparameters on train+val (dev set)...")
    dev = pd.concat([train, val], ignore_index=True)
    X_dev, y_dev = dev[config.FEATURES], (dev[config.TARGET] == "APPROVE").astype(int)

    pipe_template, _ = build_candidates()[model_name]
    final_model = pipe_template.set_params(**best_params)
    final_model.fit(X_dev, y_dev)

    # ---- final, single, untouched evaluation on test + holdout_category ----
    X_test, y_test = test[config.FEATURES], (test[config.TARGET] == "APPROVE").astype(int)
    X_holdout, y_holdout = holdout[config.FEATURES], (holdout[config.TARGET] == "APPROVE").astype(int)

    train_pred_dev = (final_model.predict_proba(X_dev)[:, 1] >= threshold).astype(int)
    train_acc_dev = accuracy_score(y_dev, train_pred_dev) * 100  # train+val self-consistency check, not a generalization metric

    test_proba = final_model.predict_proba(X_test)[:, 1]
    test_pred = (test_proba >= threshold).astype(int)
    test_acc = accuracy_score(y_test, test_pred) * 100
    test_auc = roc_auc_score(y_test, test_proba)

    holdout_proba = final_model.predict_proba(X_holdout)[:, 1]
    holdout_pred = (holdout_proba >= threshold).astype(int)
    holdout_acc = accuracy_score(y_holdout, holdout_pred) * 100
    holdout_auc = roc_auc_score(y_holdout, holdout_proba)

    # for the 4-bar split chart, also report plain train-only and val-only accuracy
    # at the chosen threshold, using the ORIGINAL train-only-fitted candidate
    # (winner_model) purely for display -- the deployed artifact is final_model
    X_train_only, y_train_only = train[config.FEATURES], (train[config.TARGET] == "APPROVE").astype(int)
    X_val_only, y_val_only = val[config.FEATURES], (val[config.TARGET] == "APPROVE").astype(int)
    train_only_acc = accuracy_score(y_train_only, (winner_model.predict_proba(X_train_only)[:, 1] >= threshold).astype(int)) * 100
    val_only_acc = accuracy_score(y_val_only, (winner_model.predict_proba(X_val_only)[:, 1] >= threshold).astype(int)) * 100

    meets_target = test_acc >= config.TARGET_ACCURACY and holdout_acc >= config.TARGET_ACCURACY

    print(f"\nTest accuracy:              {test_acc:.2f}%   ROC-AUC: {test_auc:.4f}")
    print(f"Holdout-category accuracy:  {holdout_acc:.2f}%   ROC-AUC: {holdout_auc:.4f}  (Spinal Cord Stimulator, unseen)")
    print(f"Meets >{config.TARGET_ACCURACY:.0f}% accuracy target on BOTH: {meets_target}")

    report_test = classification_report(y_test, test_pred, target_names=["PEND", "APPROVE"])
    report_holdout = classification_report(y_holdout, holdout_pred, target_names=["PEND", "APPROVE"])
    print("\nTest classification report:\n", report_test)
    print("Holdout classification report:\n", report_holdout)

    with open(config.REPORTS_DIR / "classification_report.txt", "w") as f:
        f.write(f"WINNING MODEL: {model_name}\nBest params: {best_params}\nDecision threshold (val-selected): {threshold:.4f}\n\n")
        f.write(f"Train-only accuracy (display only): {train_only_acc:.2f}%\n")
        f.write(f"Val-only accuracy (display only):    {val_only_acc:.2f}%\n")
        f.write(f"Test accuracy:                       {test_acc:.2f}%\n")
        f.write(f"Holdout-category accuracy:            {holdout_acc:.2f}%\n\n")
        f.write("=== Test classification report ===\n" + report_test)
        f.write("\n=== Holdout-category classification report (Spinal Cord Stimulator, unseen) ===\n" + report_holdout)
        f.write(f"\nMeets >{config.TARGET_ACCURACY:.0f}% accuracy target on BOTH: {meets_target}\n")

    # ---- visualizations ----
    cm_test, cm_test_pct = plot_confusion_matrix(y_test, test_pred, f"Confusion Matrix — Test ({model_name})", "02_confusion_matrix_test.png")
    cm_holdout, cm_holdout_pct = plot_confusion_matrix(y_holdout, holdout_pred, f"Confusion Matrix — Holdout Category ({model_name})", "03_confusion_matrix_holdout.png")
    plot_roc_pr(y_test, test_proba, "Test", "04a_roc_pr_test.png")
    plot_roc_pr(y_holdout, holdout_proba, "Holdout Category", "04b_roc_pr_holdout.png")
    feat_importance = plot_feature_importance(final_model, model_name, "07_feature_importance.png")
    plot_split_accuracy_bars(train_only_acc, val_only_acc, test_acc, holdout_acc, model_name)
    plot_score_distributions(train, val)

    # ---- save artifact, matching reference predict.py's expected schema ----
    artifact = {
        "model": final_model,
        "model_name": model_name,
        "features": config.FEATURES,
        "target": config.TARGET,
        "classes": {"0": "PEND", "1": "APPROVE"},
        "decision_threshold": float(threshold),
        "best_params": best_params,
        "cv_best_roc_auc": float(winner_row["cv_best_roc_auc"]),
        "group_aware_training": True,
        "test_accuracy_pct": round(test_acc, 2),
        "test_roc_auc": round(test_auc, 4),
        "holdout_accuracy_pct": round(holdout_acc, 2),
        "holdout_roc_auc": round(holdout_auc, 4),
        "meets_80pct_accuracy_target": bool(meets_target),
    }
    with open(config.MODEL_PATH, "wb") as f:
        pickle.dump(artifact, f, protocol=pickle.HIGHEST_PROTOCOL)

    # predictions export for business_metrics.py / Power BI
    id_cols = ["request_id", "patient_id", "service_category", "cpt_code", "plan_type", "coverage_basis", "baseline_policy_id", "overlay_id"]
    test_out = test[id_cols + config.FEATURES].copy()
    test_out["y_true"] = y_test.values; test_out["y_pred"] = test_pred
    test_out["approve_probability"] = test_proba; test_out["split_role"] = "test"
    holdout_out = holdout[id_cols + config.FEATURES].copy()
    holdout_out["y_true"] = y_holdout.values; holdout_out["y_pred"] = holdout_pred
    holdout_out["approve_probability"] = holdout_proba; holdout_out["split_role"] = "holdout_category"
    pd.concat([test_out, holdout_out]).to_csv(config.REPORTS_DIR / "predictions_test_and_holdout.csv", index=False)

    with open(config.REPORTS_DIR / "run_summary.json", "w") as f:
        json.dump({
            "model_name": model_name, "best_params": best_params, "decision_threshold": threshold,
            "train_only_accuracy_pct": round(train_only_acc, 2), "val_only_accuracy_pct": round(val_only_acc, 2),
            "test_accuracy_pct": round(test_acc, 2), "test_roc_auc": round(test_auc, 4),
            "holdout_accuracy_pct": round(holdout_acc, 2), "holdout_roc_auc": round(holdout_auc, 4),
            "feature_importance": feat_importance,
            "confusion_matrix_test": cm_test.tolist(), "confusion_matrix_holdout": cm_holdout.tolist(),
            "meets_80pct_accuracy_target": bool(meets_target),
        }, f, indent=2)

    print(f"\nSaved model artifact -> {config.MODEL_PATH}")
    print(f"Saved reports -> {config.REPORTS_DIR}")
    print(f"Saved visualizations -> {config.VIZ_DIR}")


if __name__ == "__main__":
    main()
