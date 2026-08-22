"""
ML Triage Model — wraps the trained artifact and applies it, after the
deterministic gates coverage_reasoning_agent.py already computed
(contraindicationFlagged, indicationMismatchFlagged, missingRequiredEvidence,
clinicalEvidenceInsufficient, urgencyFlagged) have cleared a request. Per
the architecture: this is the ONE place a triage decision is actually made
(see project memory "agents never decide").

Model artifact (2026-08-19+): models/proauth_best_model.pkl — replaces
the earlier RandomForest trained on all 10 aggregator features. This one
is a LogisticRegression inside a scikit-learn Pipeline (StandardScaler +
LogisticRegression), trained on 4 of the aggregator's 10 computed
features — policy_score, documentation_score, clinical_evidence_score,
diagnosis_supported — a DELIBERATE design choice by the training
pipeline (see generate_dataset.py's docstring: "the model has to learn
from the aggregates, not reverse-engineer a deterministic formula"), not
an accidental subset. Real, measured metrics carried in the artifact
itself: 85.07% test accuracy, 82.89% holdout accuracy, ROC AUC
0.9369 / 0.9099, meets_80pct_accuracy_target: True. (Retrained 2026-08-20,
item #3/#45 — see coverage_reasoning_agent.py's docstring and
docs/PROGRESS_TRACKER.md §9.10: same 4 features/formula, corrected
training data, so policy_score is no longer artificially over-weighted;
prior metrics were 85.38%/83.33%/0.9383/0.9154, still comfortably above
the 80% target either way.)

Unlike the old artifact (a bare sklearn estimator, fed a positional
feature list), this one is a DICT — {"model", "features",
"decision_threshold", "classes", ...} — carrying its own decision
threshold (0.453, not a hardcoded 0.5) and its own class labels. Reading
these FROM the artifact rather than hardcoding them means a future
retrain never silently drifts out of sync with the serving code here.

coverage_reasoning_agent.py still computes and exposes all 10 features
(featureVector / featureVectorOrdered) — genuinely useful context for
the Companion Agent's explanation and the UI's transparency panel — this
module simply reads only the 4 this particular artifact's `features`
list names, via plain dict lookup, same pattern as ml/predict.py.
"""
import os
import pickle

import pandas as pd

MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "proauth_best_model.pkl")


class MLTriageAgent:
    def __init__(self, model_path: str = MODEL_PATH):
        with open(model_path, "rb") as f:
            self.artifact = pickle.load(f)
        self.model = self.artifact["model"]
        self.features = self.artifact["features"]
        self.decision_threshold = self.artifact["decision_threshold"]
        self.classes = self.artifact["classes"]  # {"0": "PEND", "1": "APPROVE"}

    def run(self, reasoning_result: dict) -> dict:
        # Checked FIRST, ahead of missingRequiredEvidence — a known-dangerous
        # drug/patient-state combination needs a nurse's eyes regardless of
        # whether the paperwork happens to be complete; asking the doctor
        # for more documents would be the wrong message here. See
        # coverage_reasoning_agent.py's contraindicationFlagged and
        # clinical_evidence_agent.py's contraindication_check (2026-08-19+).
        if reasoning_result.get("contraindicationFlagged"):
            details = reasoning_result.get("contraindicationDetails") or []
            detail_text = "; ".join(d.get("reason", "") for d in details if d.get("reason"))
            return {
                "outcome": "PEND",
                "confidence": None,
                "reason": "Deterministic safety gate: " + (
                    detail_text if detail_text
                    else "the Clinical Agent judged a known drug/patient-state contraindication."
                ) + " ML model was not invoked.",
            }

        # Checked second, same audit pass (2026-08-20+): the policy Policy
        # Agent identified is not currently ACTIVE in this system's own
        # records (superseded/expired — see coverage_reasoning_agent.py's
        # policyInactive). A found-but-inactive policy is not real coverage
        # grounding, the same reasoning as coverageNotCovered/policyNotFound
        # below — currently latent in the live corpus (every policy today
        # happens to be ACTIVE) but a real risk given policies.status/
        # expirationDate and the PolicyVersion table exist for exactly this.
        if reasoning_result.get("policyInactive"):
            return {
                "outcome": "PEND",
                "confidence": None,
                "reason": "Deterministic gate: the identified policy is not currently active "
                          "(superseded or expired). ML model was not invoked.",
            }

        # Checked third, same priority tier as contraindication (2026-08-20+,
        # found in an audit for gates missing the same way policyNotFound
        # was): Policy Agent's own coverageStatus verdict said NOT_COVERED —
        # a direct payer exclusion, not an inferred clinical judgment, and
        # at least as authoritative as a contraindication. See
        # coverage_reasoning_agent.py's coverageNotCovered docstring for why
        # this is NOT redundant with indicationMismatchFlagged below (a
        # deterministically-resolved indication_match never re-consults
        # policy_evidence, so an excluded-but-clinically-correct request can
        # slip past that gate specifically).
        if reasoning_result.get("coverageNotCovered"):
            return {
                "outcome": "PEND",
                "confidence": None,
                "reason": "Deterministic gate: the applicable policy explicitly does not cover "
                          "this service (coverageStatus: NOT_COVERED). ML model was not invoked.",
            }

        # Checked third, same priority tier as contraindication — a
        # GROUNDED indication mismatch (see coverage_reasoning_agent.py's
        # indicationMismatchFlagged / clinical_evidence_agent.py's
        # groundedIndicationMismatch) means the request is asking for a
        # treatment that doesn't match either its own FDA-labeled
        # indication or the retrieved policy's actual covered indication —
        # a correctness problem the model's 4 blended features have
        # already been shown (live testing, 2026-08-19) to not reliably
        # veto on: semaglutide for allergic rhinitis and gene therapy
        # against a policy that only covers allogeneic HSCT both cleared
        # the 0.426 threshold around 0.50 probability despite
        # diagnosis_supported being 0. Gating here, before the model runs,
        # is the same "don't let a known problem dilute into a
        # probability" fix already applied to contraindication/urgency.
        if reasoning_result.get("indicationMismatchFlagged"):
            return {
                "outcome": "PEND",
                "confidence": None,
                "reason": "Deterministic gate: the requested treatment's indication does not match "
                          "the diagnosis (grounded FDA-label or policy-evidence mismatch). "
                          "ML model was not invoked.",
            }

        # Sixth gate (2026-08-20+, found live): no applicable coverage
        # policy could be found at all, so nothing downstream — including
        # the "criteria" that DID pass — was actually graded against a
        # real policy requirement (see coverage_reasoning_agent.py's
        # policyNotFound for the exact failure this closes: a Medicare +
        # plain-Metformin request with no matching policy still
        # auto-APPROVED at 91.1% confidence off two trivially-passing
        # generic meta-criteria). Checked before missingRequiredEvidence /
        # clinicalEvidenceInsufficient since without a policy, "the right
        # documents were submitted" and "the named criteria passed" are
        # both meaningless — there's no criteria to check evidence
        # against in the first place.
        if reasoning_result.get("policyNotFound"):
            return {
                "outcome": "PEND",
                "confidence": None,
                "reason": "Deterministic gate: no applicable coverage policy could be found for "
                          "this request, so coverage criteria cannot be established. "
                          "ML model was not invoked.",
            }

        if reasoning_result["missingRequiredEvidence"]:
            return {
                "outcome": "MORE_INFORMATION",
                "confidence": None,
                "reason": "Deterministic policy gate: required evidence missing "
                          "(Clinical notes and/or Prescription were not submitted). "
                          "ML model was not invoked.",
            }

        # Same actionable-by-doctor precedent as missingRequiredEvidence
        # above, just for clinical FACTS instead of documents (2026-08-19+,
        # found live: a bariatric surgery request with a one-line
        # justification failed all 3 of the policy's own named criteria yet
        # still auto-APPROVED at 81%). See coverage_reasoning_agent.py's
        # clinical_evidence_insufficient for exactly what this requires.
        if reasoning_result.get("clinicalEvidenceInsufficient"):
            return {
                "outcome": "MORE_INFORMATION",
                "confidence": None,
                "reason": "Deterministic gate: none of the policy's specific clinical criteria "
                          "could be confirmed from the justification given (e.g. no BMI, "
                          "comorbidity, or prior-treatment facts stated). ML model was not invoked.",
            }

        # Same precedent as the missing-evidence gate above (2026-08-19+):
        # a claimed urgency Clinical Agent judged inconsistent with the
        # actual clinical picture routes straight to PEND for nurse
        # review, never reaching the model — a suspicious signal like
        # this shouldn't just dilute into a probability score.
        if reasoning_result.get("urgencyFlagged"):
            return {
                "outcome": "PEND",
                "confidence": None,
                "reason": "Deterministic gate: the claimed urgency was judged inconsistent "
                          "with the clinical evidence given. ML model was not invoked.",
            }

        # Ninth deterministic gate (2026-08-20+, user-requested): the
        # requesting provider's specialty doesn't clearly match the
        # requested service (e.g. a dermatologist requesting a complex
        # cardiac procedure) — see coverage_reasoning_agent.py's
        # specialtyMismatchFlagged. This is a review trigger, NOT a safety
        # veto or a denial: it routes to PEND (the same nurse/reviewer queue
        # every other PEND lands in) so a human can judge whether the
        # mismatch is legitimate (e.g. a generalist covering for a
        # specialist) before anything is decided either way. The ML model
        # is never invoked for this request.
        if reasoning_result.get("specialtyMismatchFlagged"):
            return {
                "outcome": "PEND",
                "confidence": None,
                "reason": "Deterministic gate: the requesting provider's specialty does not "
                          "clearly match the requested service — pending manual review. "
                          "ML model was not invoked.",
            }

        feature_vector = reasoning_result["featureVector"]
        row = {name: feature_vector[name] for name in self.features}
        x = pd.DataFrame([row])

        proba_approve = float(self.model.predict_proba(x)[0, 1])
        outcome = "APPROVE" if proba_approve >= self.decision_threshold else "PEND"

        return {
            "outcome": outcome,
            "confidence": round(proba_approve if outcome == "APPROVE" else 1 - proba_approve, 3),
            "probaApprove": round(proba_approve, 3),
            "reason": f"ML triage model ({self.artifact.get('model_name', 'unknown')}), trained on "
                      f"{len(self.features)} policy/clinical/documentation features "
                      f"(test accuracy {self.artifact.get('test_accuracy_pct', '—')}%, "
                      f"holdout accuracy {self.artifact.get('holdout_accuracy_pct', '—')}%).",
        }
