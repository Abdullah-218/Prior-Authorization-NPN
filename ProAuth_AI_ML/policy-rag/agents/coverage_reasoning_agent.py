"""
Coverage Reasoning Agent — ML Feature Aggregator
===================================================

Repurposed: this used to be an LLM agent producing an open-ended
PASS/FAIL/MISSING/UNKNOWN assessment of policy criteria (see git history
for that version). It is now something else entirely — a deterministic
aggregator, zero LLM calls, zero network calls beyond the existing
get_policy_status() DB lookup, that assembles Policy Agent + Clinical
Agent + Document Agent output into a full 10-feature vector. It replaces
what rule_score_engine.py used to attempt (built before the real model's
feature schema was known, now retired) and mirrors the collaborator's own
PolicyReasoningAgent ("Agent 4") sketch — wired to this project's real
agent output shapes and its real get_policy_status() check instead of a
hardcoded stub.

Like the Rule/Score Engine before it, this stays consistent with "agents
never decide" (see project memory): it never outputs a triage decision,
only the feature vector and nine deterministic hard gates —
missingRequiredEvidence, clinicalEvidenceInsufficient, urgencyFlagged,
contraindicationFlagged, indicationMismatchFlagged, policyNotFound,
coverageNotCovered, policyInactive, and specialtyMismatchFlagged
(2026-08-20+, see clinical_evidence_agent.py's contraindication_check /
groundedIndicationMismatch / _resolve_specialty_match) — the ML model's
own wrapper (ml/model.py) reads to decide whether to even call the model
at all.

FEATURE_COLUMNS below still lists all 10 features the FIRST trained
model (a RandomForest, retired 2026-08-19+) used — kept because
featureVectorOrdered is still genuinely useful diagnostic context (the
Companion Agent's explanation and the UI's transparency panel both use
it) even though the CURRENT model (ml/model.py, a LogisticRegression) was
deliberately trained on only 4 of these 10 (see that module's docstring)
and reads them by NAME from `featureVector` (the dict form below), not
by position from this ordered list. Both forms are computed from the
exact same underlying values either way, so nothing here needed to
change when the model did.

Formulas for num_criteria_total/passed/failed/missing were verified
against all rows of the collaborator's ml_training_set.csv before being
adopted here — 100% exact match. _estimate_policy_score's FORMULA is an
EXACT reproduction of the training generator's formula (verified by
reading ml/generate_dataset.py directly, 2026-08-20) — not an
approximation of it, contrary to this docstring's own prior claim. The
real, now-CORRECTED gap (item #3, see ml/fix_policy_score_correlation.py
and docs/PROGRESS_TRACKER.md's "what's next for accuracy" discussion) was
one level up: training's `rag_relevance` input was a near-exact copy
(0.04-std jitter) of an abstract "quality" latent that was ALSO reused
directly in label generation, so policy_score ended up artificially,
tightly entangled with the training label through that shared cause —
unlike documentation_score/clinical_evidence_score, whose training-time
simulation (matched/required, passed/total ratios) is the same
computational TYPE as what Document/Clinical Agent compute for real at
inference. The model has since been retrained on a corrected dataset
where that entanglement is diluted to a more realistic level (60% original
signal / 40% independent noise, a documented judgment call, not an
empirically-derived split — no real outcomes feedback loop exists yet to
calibrate against). This function's formula itself needed NO code change;
only the training data and the resulting model artifact did.

document_evidence is optional and defaults to an honest "nothing
submitted yet" shape when the Document Agent (still blocked on
file-storage plumbing — see project memory) hasn't run: this correctly
makes missingRequiredEvidence come out True, which is the accurate state
of the world today, not a bug to hide behind a fabricated positive score.

Forced-default note: the ML model's numeric features have no "unknown"
bucket — diagnosis_supported is a plain 0/1, and every score feature must
be a real number for the model's predict_proba() to accept the vector at
all. When an upstream agent honestly reports None (genuinely
undetermined), THIS function is the one place allowed to collapse that
into the model's required value, always in the conservative direction (0
/ 0.0 — the direction that can only ever push a request toward more
scrutiny, never toward a false approval) — and it always records the
substitution in `notes` so it's visible, not silent.

Usage:
    from agents.coverage_reasoning_agent import aggregate_ml_features
    features = aggregate_ml_features(policy_evidence, clinical_criteria_eval,
                                      document_evidence=None)
"""
from rag.retrieval import get_policy_status

# The first trained model's (RandomForest, retired) full feature set —
# still computed in this order for featureVectorOrdered's diagnostic
# value. The CURRENT model (ml/model.py) reads its own (smaller) feature
# list by name from its own artifact, not from this constant.
FEATURE_COLUMNS = [
    "policy_score",
    "documentation_score",
    "clinical_evidence_score",
    "diagnosis_supported",
    "n_clinical_criteria_passed",
    "n_clinical_criteria_failed",
    "n_documents_submitted",
    "num_criteria_passed",
    "num_criteria_failed",
    "num_criteria_missing",
]


def _estimate_policy_score(relevance_score, diagnosis_supported):
    """
    100 * (0.5 + 0.5 * relevance), then -40 if the diagnosis isn't
    supported, clamped to [0, 100] — an EXACT reproduction of
    ml/generate_dataset.py's training-time formula (item #3, 2026-08-20;
    see module docstring for the real gap this formula was wrongly
    blamed for, now corrected at the training-data level instead).
    """
    if relevance_score is None:
        relevance_score = 0.5  # no retrieval signal at all — neutral midpoint, not 0
    score = 100.0 * (0.5 + 0.5 * relevance_score)
    if not diagnosis_supported:
        score -= 40.0
    return round(max(0.0, min(100.0, score)), 1)


def _default_document_evidence(required_documents):
    """
    Honest "nothing submitted yet" default for when Document Agent hasn't
    run (still blocked — see project memory). Every required document is
    reported missing, not zero-and-silent — that's the true state of the
    world until real upload plumbing exists.

    An EMPTY required_documents list is a different situation, not a
    smaller version of the same one: with nothing required, there is
    nothing to be missing, so documentation is vacuously complete (100),
    not 0 — 0 would falsely claim total non-compliance for a checklist
    that has zero items on it. This mirrors the convention
    missingRequiredEvidence's own gate already uses (`n_required_docs > 0
    and ...` — an empty requirement list can't fail it either). Verified
    against ml_training_set.csv that n_required_documents is never 0 in
    training data (always 2-6) — this exact case is genuinely unseen by
    the model, so there's no "correct" trained answer to match; vacuous
    completeness is the honest one.
    """
    required_documents = required_documents or []
    return {
        "documentationScore": 100.0 if not required_documents else 0.0,
        "nRequiredDocuments": len(required_documents),
        "nDocumentsSubmitted": 0,
        "missingDocuments": list(required_documents),
        "relevantDocuments": [],
    }


def aggregate_ml_features(policy_evidence, clinical_criteria_eval, document_evidence=None):
    """
    Pure Python. Never raises on merely-incomplete upstream data — an
    upstream agentError/policyFound:false produces an explicit
    aggregatorError alongside a clearly-degraded feature vector, not a
    crash and not a silently-plausible fake one. featureVectorOrdered
    never contains None: every score feature that could come back
    undetermined is given a conservative default here (see module
    docstring's "Forced-default note"), so the vector is always safe to
    hand straight to the trained model.
    """
    policy_evidence = policy_evidence or {}
    clinical_criteria_eval = clinical_criteria_eval or {}
    required_documents = policy_evidence.get("requiredDocuments") or []
    document_evidence = document_evidence or _default_document_evidence(required_documents)

    notes = []
    aggregator_error = None
    if policy_evidence.get("agentError") or not policy_evidence.get("policyFound"):
        aggregator_error = "No confident policy evidence to aggregate against — feature vector is degraded/default."

    policy_id = policy_evidence.get("policyId")
    policy_active = get_policy_status(policy_id) == "ACTIVE" if policy_id else False
    # Eighth deterministic gate (2026-08-20+, same audit pass as
    # coverageNotCovered above — found before it ever fired live, since
    # every policy in today's corpus happens to be ACTIVE with no
    # expiration date set, per a live DB check; still a real, not
    # hypothetical, risk given policies.status/expirationDate exist as
    # real columns and PolicyVersion exists as a real table for exactly
    # the "this policy got superseded" case). policy_active was already
    # computed here and folded into num_criteria_passed's COUNT, but a
    # count that ML never even receives (only 4 of the 10 aggregator
    # features are trained on) — a superseded/expired policy record could
    # still drive an APPROVE off policy_score/documentation_score/
    # clinical_evidence_score alone, the same shape of gap as items #35
    # and #36. Only fires when a policy WAS actually identified
    # (policyFound + a real policy_id) but its own DB record isn't
    # currently ACTIVE — a missing policy_id is policyNotFound's case, not
    # this one.
    policy_inactive = bool(policy_id) and bool(policy_evidence.get("policyFound")) and not policy_active

    diagnosis_supported = clinical_criteria_eval.get("diagnosisSupported")
    if diagnosis_supported is None:
        notes.append("diagnosisSupported was undetermined upstream — defaulted to False (not supported), the conservative direction.")
        diagnosis_supported = False

    relevance_score = policy_evidence.get("relevanceScore")
    policy_score = _estimate_policy_score(relevance_score, diagnosis_supported)

    documentation_score = document_evidence.get("documentationScore")
    if documentation_score is None:
        notes.append("documentationScore was undetermined upstream — defaulted to 0.0, the conservative direction.")
        documentation_score = 0.0

    clinical_evidence_score = clinical_criteria_eval.get("clinicalEvidenceScore")
    if clinical_evidence_score is None:
        notes.append("clinicalEvidenceScore was undetermined upstream (no named clinical criteria to evaluate) — defaulted to 0.0, the conservative direction.")
        clinical_evidence_score = 0.0

    n_clinical_total = clinical_criteria_eval.get("nClinicalCriteriaTotal") or 0
    n_clinical_passed = clinical_criteria_eval.get("nClinicalCriteriaPassed") or 0
    n_clinical_failed = clinical_criteria_eval.get("nClinicalCriteriaFailed") or 0

    # Isolates the POLICY'S OWN named checklist (e.g. "bmi_35_or_higher",
    # "obesity_related_comorbidity_present") from criteriaResults, which
    # also contains meta-criteria (indication_match, specialty_match,
    # urgency_consistency, contraindication_check) that aren't part of
    # what the policy itself asked to be checked — see
    # clinical_evidence_insufficient below for why this split matters.
    policy_named_criteria = policy_evidence.get("clinicalCriteria") or []
    criteria_results_all = clinical_criteria_eval.get("criteriaResults") or {}
    n_policy_criteria_total = sum(1 for c in policy_named_criteria if c in criteria_results_all)
    n_policy_criteria_passed = sum(
        1 for c in policy_named_criteria if criteria_results_all.get(c) == "PASS"
    )

    n_required_docs = document_evidence.get("nRequiredDocuments") or 0
    n_documents_submitted = document_evidence.get("nDocumentsSubmitted") or 0
    missing_documents = document_evidence.get("missingDocuments") or []

    # ---- Agent 4's exact composite formulas — verified 100% against all
    # 43,584 rows of ml_training_set.csv (num_criteria_total/passed/failed
    # via direct comparison; num_criteria_missing via len(missing_documents)
    # once the CSV's ';' delimiter, not ',', is used to split it). ----
    num_criteria_total = 1 + n_clinical_total + n_required_docs + 1
    num_criteria_passed = (
        (1 if diagnosis_supported else 0) + n_clinical_passed + n_documents_submitted + (1 if policy_active else 0)
    )
    num_criteria_missing = len(missing_documents)
    num_criteria_failed = (0 if diagnosis_supported else 1) + n_clinical_failed

    # CHANGED (2026-08-19+, per explicit instruction): required documents
    # are now a fixed baseline of exactly 2 (Clinical notes, Prescription —
    # see document_agent.py; policy-specific documents are optional and no
    # longer counted here at all). With only 2 truly compulsory items, "at
    # least half missing" (the old formula, calibrated for a variable
    # 2-6-item list) would let ONE of the two slide through unflagged —
    # not what "compulsory" means for a fixed pair. Any missing baseline
    # document now gates. Computed BEFORE the ML model runs; a request
    # failing this never reaches the model at all (see ml/model.py's
    # MLTriageAgent.run()).
    missing_required_evidence = n_required_docs > 0 and documentation_score < 100.0

    # Fifth deterministic gate (2026-08-19+, found live: a bariatric surgery
    # request with a one-line justification — "Patient wants weight loss
    # surgery," no BMI/comorbidity/prior-treatment facts at all — FAILed
    # every one of the policy's own 3 named clinical criteria, yet still
    # auto-APPROVED at 81.1%, because indication_match trivially passes
    # (obesity IS a covered indication for bariatric surgery — the mismatch
    # gate above can't catch this, the treatment IS appropriate in kind,
    # just clinically undocumented) and policy_score/documentation_score
    # carried the rest). Same root cause as the indication-mismatch gate —
    # the model's 4 blended features can't reliably veto on "zero of the
    # policy's own checklist items were demonstrated." Absence of a stated
    # fact is never proof it's untrue (see clinical_evidence_agent.py's
    # "under-extraction is safer" rule) — so this reads as "ask the doctor
    # for the missing clinical detail," MORE_INFORMATION, same actionable-
    # by-doctor class as missingRequiredEvidence, not a PEND/denial verdict
    # this system has no grounds to make. Originally fired only when EVERY
    # policy-named criterion failed, on the theory that partial evidence
    # is exactly what clinical_evidence_score already exists to weigh —
    # found live (2026-08-22) that this doesn't actually hold: a CPAP
    # request with only "Patient has sleep apnea, recommend CPAP" (no
    # AHI/RDI value, no sleep study) correctly FAILed the policy's two
    # decisive named criteria (ahi_rdi_threshold_met,
    # positive_sleep_study_documented) — 1 of 3 policy criteria passed,
    # not 0 — yet clinical_evidence_score still landed at 60% (3 of 5,
    # diluted by indication_match/specialty_match, which pass almost
    # automatically) and the request auto-APPROVED at 93.4% confidence.
    # Widened from "==0" to "a minority passed" so a policy's own decisive
    # criteria failing can't be masked by two near-universal meta-criteria
    # passing alongside them. Deliberately still keyed on
    # n_policy_criteria_passed/total (this gate's own inputs, computed
    # just above) rather than clinical_evidence_score itself — that score
    # is one of the 4 features the deployed ML model was actually trained
    # on, so changing ITS formula would silently skew every prediction
    # against a model calibrated on the old distribution; this gate runs
    # before the model ever sees that feature; a tie (exactly half passed)
    # does not fire, and none of the meta-criteria are included in this
    # count, so a 1-of-3 or 2-of-5 case doesn't just barely dodge it.
    clinical_evidence_insufficient = (
        n_policy_criteria_total > 0 and n_policy_criteria_passed < n_policy_criteria_total / 2
    )

    # Second deterministic gate, same precedent as missingRequiredEvidence
    # (2026-08-19+): a claimed non-routine urgency that Clinical Agent's
    # urgency_consistency check FAILed is treated as "fishy", not just a
    # lower score — routed straight to PEND for nurse review before the ML
    # model ever runs, same "don't let a suspicious signal just dilute
    # into a probability" reasoning. Only fires when urgency_consistency
    # was actually evaluated at all (a claimed Routine/unset urgency never
    # adds this criterion — see clinical_evidence_agent.py).
    urgency_flagged = clinical_criteria_eval.get("criteriaResults", {}).get("urgency_consistency") == "FAIL"

    # Third deterministic gate (2026-08-19+): a known-dangerous drug +
    # patient-state combination (Clinical Agent's contraindication_check,
    # see clinical_evidence_agent.py / contraindication_lookup.py) is a
    # safety concern, not a scoring concern — routed straight to PEND for
    # nurse review before the ML model ever runs, same "don't let a
    # suspicious signal just dilute into a probability" reasoning as
    # urgencyFlagged above. Only fires when contraindication_check was
    # actually evaluated (deterministic table match, or an LLM judgment on
    # a notable-but-unmatched risk fact) — never fabricated here.
    contraindication_flagged = clinical_criteria_eval.get("criteriaResults", {}).get("contraindication_check") == "FAIL"

    # Ninth deterministic gate (2026-08-20+, user-requested): a specialty
    # mismatch used to only dilute clinical_evidence_score like any other
    # criterion (see clinical_evidence_agent.py's _resolve_specialty_match)
    # — a dermatologist requesting a complex cardiac procedure could still
    # slip through to an automatic ML decision if the rest of the evidence
    # scored well enough. That is now a hard review gate, same tier as
    # urgencyFlagged/contraindicationFlagged: FAIL routes straight to PEND
    # (nurse/reviewer queue) before the ML model ever runs, never an
    # automatic denial. specialty_match is only present in criteriaResults
    # when there was something to judge at all (a real specialty + service
    # given) and the reference table or LLM fallback reached PASS/FAIL —
    # "unknown_specialty"/no-specialty cases add nothing here, so they
    # correctly never fire this gate (see specialty_check.py).
    specialty_mismatch_flagged = clinical_criteria_eval.get("criteriaResults", {}).get("specialty_match") == "FAIL"

    # Fourth deterministic gate (2026-08-19+, added after live testing
    # reproduced 3 auto-APPROVEs of a genuine indication mismatch around
    # 0.50 probability — just over the 0.426 threshold: the model's 4
    # blended features can't reliably veto on a single failed criterion the
    # way a direct gate can). Reads clinical_criteria_eval's own
    # groundedIndicationMismatch flag rather than re-deriving it from
    # criteriaResults — that flag is deliberately narrow (a real FDA-label
    # zero-overlap or genuine LLM judgment only, never the policy-not-found
    # fallback's default-FAIL), see clinical_evidence_agent.py's docstring
    # for why a looser rule here would flood PEND with corpus-coverage gaps.
    indication_mismatch_flagged = bool(clinical_criteria_eval.get("groundedIndicationMismatch"))

    # Seventh deterministic gate (2026-08-20+, found in the same audit pass
    # as policyNotFound above, before it was ever hit live): Policy Agent's
    # own coverageStatus verdict was computed and shown to the reviewer/
    # Companion Agent but never actually consulted by any gate. This is NOT
    # redundant with indicationMismatchFlagged — a request can be clinically
    # correct (indication_match PASS, e.g. a strong FDA-label match resolved
    # deterministically, no LLM call at all) while the POLICY still excludes
    # it for an unrelated reason (cosmetic-purpose exclusion, step-therapy
    # not captured as a named clinicalCriteria item, experimental
    # categorization, plan-design exclusion). Whenever indication_match IS
    # LLM-graded, the LLM is shown the full policy_evidence JSON (including
    # coverageStatus) as context, so an excluded case usually also fails
    # indication_match and gets caught there — but whenever it resolves
    # deterministically instead (bypassing the LLM call for that criterion
    # entirely), coverageStatus is silently never looked at again. Only
    # fires when a policy was actually found (coverageStatus is UNKNOWN,
    # not NOT_COVERED, whenever policyFound is false — see
    # policy_evidence_agent.py's schema), so this never overlaps with
    # policyNotFound above.
    coverage_not_covered = policy_evidence.get("coverageStatus") == "NOT_COVERED"

    criteria_table = {
        "diagnosis_supported": "PASS" if diagnosis_supported else "FAIL",
        **clinical_criteria_eval.get("criteriaResults", {}),
        "policy_active": "PASS" if policy_active else "FAIL",
    }
    for doc in missing_documents:
        criteria_table[f"document::{doc}"] = "MISSING"
    for doc in document_evidence.get("relevantDocuments", []):
        criteria_table[f"document::{doc}"] = "PASS"

    feature_vector = {
        "policy_score": policy_score,
        "documentation_score": documentation_score,
        "clinical_evidence_score": clinical_evidence_score,
        "diagnosis_supported": int(diagnosis_supported),
        "n_clinical_criteria_passed": n_clinical_passed,
        "n_clinical_criteria_failed": n_clinical_failed,
        "n_documents_submitted": n_documents_submitted,
        "num_criteria_passed": num_criteria_passed,
        "num_criteria_failed": num_criteria_failed,
        "num_criteria_missing": num_criteria_missing,
    }

    result = {
        "criteriaTable": criteria_table,
        "missingDocuments": missing_documents,
        # Policy-named documents beyond the fixed baseline (Clinical notes,
        # Prescription) are OPTIONAL now (2026-08-19+, see
        # document_agent.py) — never counted toward missingRequiredEvidence,
        # surfaced here purely for a reviewer/Companion Agent to see what
        # the policy additionally asked for and whether it showed up.
        "optionalDocuments": document_evidence.get("optionalDocuments") or {},
        "missingRequiredEvidence": missing_required_evidence,
        "clinicalEvidenceInsufficient": clinical_evidence_insufficient,
        "urgencyFlagged": urgency_flagged,
        "contraindicationFlagged": contraindication_flagged,
        "contraindicationDetails": clinical_criteria_eval.get("contraindicationDetails") or [],
        "specialtyMismatchFlagged": specialty_mismatch_flagged,
        "indicationMismatchFlagged": indication_mismatch_flagged,
        # Sixth deterministic gate (2026-08-20+, found live: a Medicare +
        # plain-Metformin request with no matching policy in the corpus
        # still auto-APPROVED at 91.1% confidence). Root cause: when no
        # policy is found, clinical_criteria_eval falls back to grading
        # only the 2 generic meta-criteria (indication_match,
        # specialty_match) — NOT the policy's own named checklist, which
        # doesn't exist here — and those 2 trivially PASS for almost any
        # request, producing a misleadingly perfect clinical_evidence_score
        # of 100. clinicalEvidenceInsufficient can never catch this
        # specific case: it only fires when n_policy_criteria_total > 0,
        # which is structurally 0 whenever there's no policy to name
        # criteria from. `aggregatorError` above already detects exactly
        # this condition (policyFound false / agentError) but was — until
        # this fix — purely informational, never wired into any gate, so
        # the degraded feature vector could still reach the model. This
        # directly restores the architecture's own documented principle
        # (see docs/PROJECT_SPEC.md §28 / the original design brief): "no
        # policy found" must mean PEND for nurse review, never a model
        # guess dressed up as a real decision.
        "policyNotFound": bool(aggregator_error),
        "coverageNotCovered": coverage_not_covered,
        "policyInactive": policy_inactive,
        "numCriteriaTotal": num_criteria_total,
        "numCriteriaPassed": num_criteria_passed,
        "numCriteriaMissing": num_criteria_missing,
        "numCriteriaFailed": num_criteria_failed,
        "featureVector": feature_vector,
        # Ordered list matching FEATURE_COLUMNS, ready for the ML model.
        "featureVectorOrdered": [feature_vector[c] for c in FEATURE_COLUMNS],
        "notes": notes,
    }
    if aggregator_error:
        result["aggregatorError"] = aggregator_error
    return result
