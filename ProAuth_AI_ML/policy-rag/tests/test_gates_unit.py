"""
Fast, Groq-free regression suite for the deterministic gate logic in
coverage_reasoning_agent.py::aggregate_ml_features() and
ml/model.py::MLTriageAgent.run(). This is the PRIMARY regression gate for
this project — no network calls, no Groq quota spent, runs in well under
a second.

Why this exists: on 2026-08-20, a live test found that a real signal
(policyFound:false) was computed by an agent but never wired into any
gate, letting a request with zero policy grounding auto-APPROVE at 91.1%
confidence (see docs/PROGRESS_TRACKER.md item #35). A deliberate audit for
the same bug shape then found two more (items #36 coverageNotCovered, #37
policyInactive) before either ever fired live. This suite exists so the
next instance of that bug shape — some agent starts computing a new
signal that should gate the decision but doesn't get wired in — is caught
by `pytest`, not by a doctor's request three days later.

Pattern per test: construct policy_evidence / clinical_criteria_eval /
document_evidence dicts by hand (bypassing the LLM entirely — these are
pure-Python unit tests of the deterministic aggregation + gate-checking
logic, not of what the LLM decides to extract), run them through
aggregate_ml_features() then MLTriageAgent.run(), and assert on the
resulting gate flags and final decision. Each gate gets both a
"fires correctly" case and a "does not false-positive on an adjacent,
legitimate case" case.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from agents.coverage_reasoning_agent import aggregate_ml_features
from ml.model import MLTriageAgent


@pytest.fixture(scope="module")
def ml_agent():
    # Loads the pickled model once for the whole test module — same
    # lifecycle as main.py's _get_ml_agent(), just without the FastAPI
    # process-caching wrapper.
    return MLTriageAgent()


def _baseline_policy_evidence(**overrides):
    """A policy that WAS found, is COVERED, and has no named criteria of
    its own — the simplest "gates should stay quiet" baseline. Individual
    tests override just the field(s) they're exercising."""
    base = {
        "policyFound": True,
        "policyId": "AETNA-BARIATRIC-0157",  # a real, ACTIVE policy in the live corpus
        "policyName": "Test Policy",
        "coverageStatus": "COVERED",
        "criteria": [],
        "clinicalCriteria": [],
        "requiredDocuments": [],
        "relevanceScore": 0.9,
    }
    base.update(overrides)
    return base


def _baseline_clinical_criteria_eval(**overrides):
    base = {
        "diagnosisSupported": True,
        "criteriaResults": {"indication_match": "PASS", "specialty_match": "PASS"},
        "nClinicalCriteriaTotal": 2,
        "nClinicalCriteriaPassed": 2,
        "nClinicalCriteriaFailed": 0,
        "clinicalEvidenceScore": 100,
        "groundedIndicationMismatch": False,
        "contraindicationDetails": [],
    }
    base.update(overrides)
    return base


def _baseline_document_evidence(**overrides):
    base = {
        "documentationScore": 100.0,
        "nRequiredDocuments": 2,
        "nDocumentsSubmitted": 2,
        "missingDocuments": [],
        "relevantDocuments": ["clinical notes", "prescription"],
    }
    base.update(overrides)
    return base


def _run(policy_evidence=None, clinical_criteria_eval=None, document_evidence=None):
    reasoning_result = aggregate_ml_features(
        policy_evidence or _baseline_policy_evidence(),
        clinical_criteria_eval or _baseline_clinical_criteria_eval(),
        document_evidence or _baseline_document_evidence(),
    )
    return reasoning_result


# ---------------------------------------------------------------------------
# Baseline: a fully clean request reaches the model and gets a real decision.
# ---------------------------------------------------------------------------

def test_clean_request_reaches_model_and_approves(ml_agent):
    reasoning_result = _run()
    for gate in (
        "contraindicationFlagged", "policyInactive", "coverageNotCovered",
        "indicationMismatchFlagged", "policyNotFound", "missingRequiredEvidence",
        "clinicalEvidenceInsufficient", "urgencyFlagged", "specialtyMismatchFlagged",
    ):
        assert reasoning_result[gate] is False, f"{gate} should not fire on the clean baseline"
    decision = ml_agent.run(reasoning_result)
    assert decision["outcome"] == "APPROVE"
    assert decision["confidence"] is not None


def test_model_driven_pend_below_threshold(ml_agent):
    # Reference case, empirically found 2026-08-20: mediocre-but-not-gated
    # evidence (all three continuous features at 50) genuinely PENDs from
    # the model itself, not from any gate — proves the model's own
    # threshold behavior still works, distinct from the 8 gate tests below.
    reasoning_result = {
        "contraindicationFlagged": False, "policyInactive": False, "coverageNotCovered": False,
        "indicationMismatchFlagged": False, "policyNotFound": False, "missingRequiredEvidence": False,
        "clinicalEvidenceInsufficient": False, "urgencyFlagged": False,
        "featureVector": {
            "policy_score": 50, "documentation_score": 50,
            "clinical_evidence_score": 50, "diagnosis_supported": 1,
        },
    }
    decision = ml_agent.run(reasoning_result)
    assert decision["outcome"] == "PEND"
    assert decision["probaApprove"] < 0.426  # the artifact's own decision_threshold


def test_model_driven_approve_above_threshold(ml_agent):
    reasoning_result = {
        "contraindicationFlagged": False, "policyInactive": False, "coverageNotCovered": False,
        "indicationMismatchFlagged": False, "policyNotFound": False, "missingRequiredEvidence": False,
        "clinicalEvidenceInsufficient": False, "urgencyFlagged": False,
        "featureVector": {
            "policy_score": 70, "documentation_score": 70,
            "clinical_evidence_score": 70, "diagnosis_supported": 1,
        },
    }
    decision = ml_agent.run(reasoning_result)
    assert decision["outcome"] == "APPROVE"
    assert decision["probaApprove"] >= 0.426


# ---------------------------------------------------------------------------
# Gate 1: contraindicationFlagged
# ---------------------------------------------------------------------------

def test_contraindication_flagged_gates_before_model(ml_agent):
    cce = _baseline_clinical_criteria_eval(
        criteriaResults={"indication_match": "PASS", "specialty_match": "PASS", "contraindication_check": "FAIL"},
        contraindicationDetails=[{"drugMatched": "warfarin", "reason": "known dangerous interaction"}],
    )
    reasoning_result = _run(clinical_criteria_eval=cce)
    assert reasoning_result["contraindicationFlagged"] is True
    decision = ml_agent.run(reasoning_result)
    assert decision["outcome"] == "PEND"
    # ml/model.py surfaces the detail's own `reason` text, not necessarily
    # the literal word "contraindication" — assert on the safety-gate
    # prefix (always present) plus the specific detail text we supplied.
    assert "deterministic safety gate" in decision["reason"].lower()
    assert "known dangerous interaction" in decision["reason"].lower()


def test_contraindication_pass_does_not_gate(ml_agent):
    cce = _baseline_clinical_criteria_eval(
        criteriaResults={"indication_match": "PASS", "specialty_match": "PASS", "contraindication_check": "PASS"},
    )
    reasoning_result = _run(clinical_criteria_eval=cce)
    assert reasoning_result["contraindicationFlagged"] is False


# ---------------------------------------------------------------------------
# Gate 2: policyInactive (item #37, added 2026-08-20)
# ---------------------------------------------------------------------------

def test_policy_inactive_gates_before_model(ml_agent):
    # A policyId that doesn't resolve to an ACTIVE row (get_policy_status
    # returns None for a nonexistent id, same as a real INACTIVE/EXPIRED
    # status would) — regression test for item #37.
    pe = _baseline_policy_evidence(policyId="FAKE-NONEXISTENT-POLICY-ID")
    reasoning_result = _run(policy_evidence=pe)
    assert reasoning_result["policyInactive"] is True
    decision = ml_agent.run(reasoning_result)
    assert decision["outcome"] == "PEND"
    assert "not currently active" in decision["reason"].lower()


def test_policy_active_does_not_gate(ml_agent):
    # AETNA-BARIATRIC-0157 is a real, ACTIVE policy in the live corpus.
    reasoning_result = _run()  # baseline already uses this policyId
    assert reasoning_result["policyInactive"] is False


# ---------------------------------------------------------------------------
# Gate 3: coverageNotCovered (item #36, added 2026-08-20)
# ---------------------------------------------------------------------------

def test_coverage_not_covered_gates_before_model_even_with_clean_criteria(ml_agent):
    # The exact shape of the bug this gate closes: a policy explicitly
    # excludes the service, but indication_match/specialty_match both
    # PASS (e.g. indication_match resolved deterministically via a strong
    # FDA-label match, never re-checking policy_evidence at all) and
    # groundedIndicationMismatch never fires. Before the fix, this
    # combination reached the model and auto-APPROVED.
    pe = _baseline_policy_evidence(coverageStatus="NOT_COVERED")
    reasoning_result = _run(policy_evidence=pe)
    assert reasoning_result["coverageNotCovered"] is True
    assert reasoning_result["indicationMismatchFlagged"] is False  # proves it's NOT redundant
    decision = ml_agent.run(reasoning_result)
    assert decision["outcome"] == "PEND"
    assert "not cover" in decision["reason"].lower()


@pytest.mark.parametrize("status", ["COVERED", "CONDITIONAL"])
def test_coverage_covered_or_conditional_does_not_gate(ml_agent, status):
    pe = _baseline_policy_evidence(coverageStatus=status)
    reasoning_result = _run(policy_evidence=pe)
    assert reasoning_result["coverageNotCovered"] is False


# ---------------------------------------------------------------------------
# Gate 4: indicationMismatchFlagged
# ---------------------------------------------------------------------------

def test_indication_mismatch_gates_before_model(ml_agent):
    cce = _baseline_clinical_criteria_eval(
        diagnosisSupported=False,
        criteriaResults={"indication_match": "FAIL", "specialty_match": "PASS"},
        groundedIndicationMismatch=True,
    )
    reasoning_result = _run(clinical_criteria_eval=cce)
    assert reasoning_result["indicationMismatchFlagged"] is True
    decision = ml_agent.run(reasoning_result)
    assert decision["outcome"] == "PEND"


def test_indication_mismatch_only_fires_when_grounded(ml_agent):
    # An indication_match FAIL that is NOT grounded (e.g. the
    # policy-not-found default-FAIL bucket) must not trip this gate —
    # that's what policyNotFound is for instead. Simulated here directly
    # via groundedIndicationMismatch=False despite a FAIL result.
    cce = _baseline_clinical_criteria_eval(
        criteriaResults={"indication_match": "FAIL", "specialty_match": "PASS"},
        groundedIndicationMismatch=False,
    )
    reasoning_result = _run(clinical_criteria_eval=cce)
    assert reasoning_result["indicationMismatchFlagged"] is False


# ---------------------------------------------------------------------------
# Gate 5: policyNotFound (item #35, added 2026-08-20 — the bug that
# triggered the whole audit)
# ---------------------------------------------------------------------------

def test_policy_not_found_gates_before_model(ml_agent):
    # The exact live-reproduced shape: no policy found, but the 2 generic
    # fallback criteria (indication_match, specialty_match) both trivially
    # PASS, producing a misleading clinical_evidence_score of 100.
    pe = {
        "policyFound": False, "policyId": None, "policyName": None,
        "coverageStatus": "UNKNOWN", "criteria": [], "clinicalCriteria": [],
        "requiredDocuments": [], "relevanceScore": 0.447,
    }
    cce = _baseline_clinical_criteria_eval(diagnosisSupported=None)
    reasoning_result = _run(policy_evidence=pe, clinical_criteria_eval=cce)
    assert reasoning_result["policyNotFound"] is True
    decision = ml_agent.run(reasoning_result)
    assert decision["outcome"] == "PEND"
    assert "no applicable coverage policy" in decision["reason"].lower()


def test_policy_found_does_not_trigger_not_found_gate(ml_agent):
    reasoning_result = _run()
    assert reasoning_result["policyNotFound"] is False


# ---------------------------------------------------------------------------
# Gate 6: missingRequiredEvidence
# ---------------------------------------------------------------------------

def test_missing_required_evidence_gates_before_model(ml_agent):
    de = _baseline_document_evidence(
        documentationScore=50.0, nDocumentsSubmitted=1, missingDocuments=["prescription"],
    )
    reasoning_result = _run(document_evidence=de)
    assert reasoning_result["missingRequiredEvidence"] is True
    decision = ml_agent.run(reasoning_result)
    assert decision["outcome"] == "MORE_INFORMATION"


def test_all_required_documents_present_does_not_gate(ml_agent):
    reasoning_result = _run()
    assert reasoning_result["missingRequiredEvidence"] is False


# ---------------------------------------------------------------------------
# Gate 7: clinicalEvidenceInsufficient
# ---------------------------------------------------------------------------

def test_clinical_evidence_insufficient_gates_before_model(ml_agent):
    # Policy names specific criteria of its own, and every single one
    # FAILs — distinct from missingRequiredEvidence (documents) and from
    # policyNotFound (no policy at all).
    pe = _baseline_policy_evidence(clinicalCriteria=["bmi_threshold_met", "comorbidity_documented"])
    cce = _baseline_clinical_criteria_eval(
        diagnosisSupported=True,
        criteriaResults={
            "bmi_threshold_met": "FAIL", "comorbidity_documented": "FAIL",
            "indication_match": "PASS", "specialty_match": "PASS",
        },
        clinicalEvidenceScore=50,
    )
    reasoning_result = _run(policy_evidence=pe, clinical_criteria_eval=cce)
    assert reasoning_result["clinicalEvidenceInsufficient"] is True
    decision = ml_agent.run(reasoning_result)
    assert decision["outcome"] == "MORE_INFORMATION"


def test_partial_named_criteria_pass_does_not_gate(ml_agent):
    # Only fires when ALL named criteria fail — one passing keeps the
    # request flowing normally (clinical_evidence_score already reflects
    # the partial evidence).
    pe = _baseline_policy_evidence(clinicalCriteria=["bmi_threshold_met", "comorbidity_documented"])
    cce = _baseline_clinical_criteria_eval(
        criteriaResults={
            "bmi_threshold_met": "PASS", "comorbidity_documented": "FAIL",
            "indication_match": "PASS", "specialty_match": "PASS",
        },
        clinicalEvidenceScore=75,
    )
    reasoning_result = _run(policy_evidence=pe, clinical_criteria_eval=cce)
    assert reasoning_result["clinicalEvidenceInsufficient"] is False


# ---------------------------------------------------------------------------
# Gate 8: urgencyFlagged
# ---------------------------------------------------------------------------

def test_urgency_flagged_gates_before_model(ml_agent):
    cce = _baseline_clinical_criteria_eval(
        criteriaResults={"indication_match": "PASS", "specialty_match": "PASS", "urgency_consistency": "FAIL"},
    )
    reasoning_result = _run(clinical_criteria_eval=cce)
    assert reasoning_result["urgencyFlagged"] is True
    decision = ml_agent.run(reasoning_result)
    assert decision["outcome"] == "PEND"


def test_no_urgency_claim_does_not_gate(ml_agent):
    reasoning_result = _run()  # baseline has no urgency_consistency criterion at all
    assert reasoning_result["urgencyFlagged"] is False


# ---------------------------------------------------------------------------
# Gate 9: specialtyMismatchFlagged (2026-08-20+, user-requested: a
# specialty mismatch must become a PENDING/manual-review gate, never an
# automatic denial and never something the ML model quietly scores around).
# ---------------------------------------------------------------------------

def test_specialty_mismatch_gates_before_model(ml_agent):
    cce = _baseline_clinical_criteria_eval(
        criteriaResults={"indication_match": "PASS", "specialty_match": "FAIL"},
    )
    reasoning_result = _run(clinical_criteria_eval=cce)
    assert reasoning_result["specialtyMismatchFlagged"] is True
    decision = ml_agent.run(reasoning_result)
    # Must route to manual review (PEND), never straight to a denial — this
    # is a review trigger, not a verdict.
    assert decision["outcome"] == "PEND"
    assert "specialty" in decision["reason"].lower()


def test_specialty_match_pass_does_not_gate(ml_agent):
    reasoning_result = _run()  # baseline already has specialty_match: PASS
    assert reasoning_result["specialtyMismatchFlagged"] is False
    decision = ml_agent.run(reasoning_result)
    assert decision["outcome"] == "APPROVE"


def test_unknown_specialty_does_not_gate(ml_agent):
    # No specialty_match key at all (e.g. an unrecognized specialty deferred
    # to the LLM, which itself never returned a verdict) — absence must not
    # be treated as a mismatch.
    cce = _baseline_clinical_criteria_eval(criteriaResults={"indication_match": "PASS"})
    reasoning_result = _run(clinical_criteria_eval=cce)
    assert reasoning_result["specialtyMismatchFlagged"] is False


# ---------------------------------------------------------------------------
# Gate priority order — confirms the exact sequence documented in
# ml/model.py, since a request that could trip MULTIPLE gates must always
# report the highest-priority one (contraindication first, safety above
# all else).
# ---------------------------------------------------------------------------

def test_contraindication_takes_priority_over_coverage_not_covered(ml_agent):
    pe = _baseline_policy_evidence(coverageStatus="NOT_COVERED")
    cce = _baseline_clinical_criteria_eval(
        criteriaResults={"indication_match": "PASS", "specialty_match": "PASS", "contraindication_check": "FAIL"},
        contraindicationDetails=[{"drugMatched": "test", "reason": "test contraindication"}],
    )
    reasoning_result = _run(policy_evidence=pe, clinical_criteria_eval=cce)
    assert reasoning_result["contraindicationFlagged"] is True
    assert reasoning_result["coverageNotCovered"] is True  # both are true...
    decision = ml_agent.run(reasoning_result)
    # ...but the reported reason must be the safety one, since it's checked first.
    assert "contraindication" in decision["reason"].lower() or "test contraindication" in decision["reason"].lower()
