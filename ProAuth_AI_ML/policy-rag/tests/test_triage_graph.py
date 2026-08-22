"""
Standalone end-to-end verification for triage_graph.py — run before any
Node/HTTP integration, same pattern used for every other piece of this
pipeline so far. Not pytest: prints results for manual eyeball review,
since these are LLM outputs (non-deterministic across runs) being checked
for reasonableness, not exact-match assertions.

This graph produces structured evidence and the ML feature aggregator's
ready-to-consume feature vector (mlFeatures.featureVectorOrdered) — no
triage decision. Each scenario's "expect" describes the shape of
clinicalCriteriaEval (PASS/FAIL per named criterion, diagnosisSupported)
and the resulting mlFeatures (10-value featureVectorOrdered,
missingRequiredEvidence gate), not an APPROVE/PEND/etc. outcome — that
decision is the separately-built ML Triage Model's job, downstream of
this graph's output.

Usage: cd policy-rag && python3 tests/test_triage_graph.py
"""
import json
import os
import sys

# tests/ is a subdirectory of policy-rag/ — triage_graph.py lives one
# level up, so it isn't found via the default "script's own directory"
# sys.path entry the way it was when this file lived at policy-rag/ root.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from triage_graph import run_evidence_pipeline

DEFAULT_REQUEST_CONTEXT = {
    "patient_age": 45,
    "patient_sex": "F",
    "service_type": "surgical",
    "provider_specialty": "bariatric surgery",
    "urgency": "routine",
    "care_setting": "outpatient",
}

SCENARIOS = [
    {
        # Real end-to-end extraction path: Clinical Agent reads this prose
        # and produces the facts, instead of them being hand-typed.
        "name": "Aetna bariatric surgery, full criteria set satisfied via real clinical justification text",
        "expect": "Clinical Agent extracts bmi/comorbidity/prior-treatment facts; most/all clinicalCriteria PASS; featureVectorOrdered has a non-trivial policy_score/clinical_evidence_score",
        "args": dict(
            requested_service="bariatric surgery",
            diagnosis="morbid obesity with type 2 diabetes",
            plan_id="PLAN005",
            icd10_code="E66.01",
            clinical_justification=(
                "Patient is a 45-year-old female with BMI of 42 kg/m^2 and a 5-year "
                "history of type 2 diabetes mellitus. She has completed a 6-month "
                "physician-supervised weight management program including dietary "
                "changes and increased physical activity (an intensive "
                "multicomponent behavioral intervention), without achieving "
                "sustained weight loss."
            ),
        ),
    },
    {
        "name": "Aetna bariatric surgery, same request, NO facts given",
        "expect": "clinicalCriteria items FAIL (nothing to demonstrate them), clinical_evidence_score low/0",
        "args": dict(
            requested_service="bariatric surgery",
            diagnosis="morbid obesity",
            plan_id="PLAN005",
            patient_facts={},
        ),
    },
    {
        "name": "Aetna liposuction (real exclusion)",
        "expect": "coverageStatus NOT_COVERED from Policy Agent; diagnosisSupported false; low policy_score",
        "args": dict(
            requested_service="liposuction",
            diagnosis="excess adiposity",
            plan_id="PLAN005",
            patient_facts={},
        ),
    },
    {
        "name": "Medicare LDCT lung cancer screening, full criteria set via real clinical justification text",
        "expect": "Clinical Agent extracts age/smoking/counseling facts; most/all clinicalCriteria PASS",
        "args": dict(
            requested_service="low dose CT lung cancer screening",
            diagnosis="high risk for lung cancer, tobacco use",
            plan_id="PLAN001",
            icd10_code="Z87.891",
            clinical_justification=(
                "Patient is a 61-year-old current smoker with a 30 pack-year "
                "smoking history, asymptomatic for lung cancer. An order for "
                "low-dose CT lung cancer screening has been placed, and the "
                "required shared decision-making counseling visit was completed "
                "and documented prior to this order."
            ),
        ),
    },
    {
        "name": "Cigna CPAP, AHI/compliance facts missing",
        "expect": "clinicalCriteria items FAIL for the missing facts specifically",
        "args": dict(
            requested_service="CPAP therapy",
            diagnosis="obstructive sleep apnea",
            plan_id="PLAN004",
            patient_facts={},
        ),
    },
    {
        "name": "Bogus plan_id — nothing to assess",
        "expect": "policyFound false, aggregatorError set, degraded-but-safe featureVectorOrdered (no crash), no Groq call spent on clinical_criteria_eval",
        "args": dict(
            requested_service="bariatric surgery",
            diagnosis="morbid obesity",
            plan_id="PLAN999",
            patient_facts={"bmi": 42},
        ),
    },
    {
        # Document Agent is still blocked on file-storage plumbing — this
        # proves the manual document_evidence override path works ahead of
        # that, same precedent as patient_facts before Clinical Agent existed.
        "name": "Aetna bariatric surgery, manual document_evidence override (all required docs submitted)",
        "expect": "missingRequiredEvidence false, documentation_score 100, num_criteria_missing 0",
        "args": dict(
            requested_service="bariatric surgery",
            diagnosis="morbid obesity with type 2 diabetes",
            plan_id="PLAN005",
            icd10_code="E66.01",
            clinical_justification=(
                "Patient is a 45-year-old female with BMI of 42 kg/m^2 and a 5-year "
                "history of type 2 diabetes mellitus, completed a 6-month "
                "physician-supervised weight management program without sustained "
                "weight loss."
            ),
            document_evidence={
                "documentationScore": 100.0,
                "nRequiredDocuments": 2,
                "nDocumentsSubmitted": 2,
                "missingDocuments": [],
                "relevantDocuments": ["weight management program records", "psychological evaluation"],
            },
        ),
    },
]

for scenario in SCENARIOS:
    print(f"\n{'=' * 70}\n{scenario['name']}  (expect: {scenario['expect']})\n{'=' * 70}")
    args = {"request_context": DEFAULT_REQUEST_CONTEXT, **scenario["args"]}
    result = run_evidence_pipeline(**args)
    print(json.dumps(result, indent=2))
    clinical_facts = result.get("clinicalEvidence", {}).get("extractedFacts", {})
    criteria_eval = result.get("clinicalCriteriaEval", {})
    features = result.get("mlFeatures", {})
    print(f"\n--> clinicalEvidence.extractedFacts: {clinical_facts}")
    print(f"--> clinicalCriteriaEval: {json.dumps(criteria_eval, indent=2)}")
    print(f"--> mlFeatures: {json.dumps(features, indent=2)}")
