"""
Triage Service — HTTP entry point
====================================

The piece that was missing to make this whole pipeline reachable from the
live app: everything up to now (triage_graph.py's run_evidence_pipeline)
was a standalone Python module. This wraps it, MLTriageAgent (ml/model.py),
and the Companion Agent into one FastAPI service the Node backend can
call over HTTP — the "Node/HTTP integration" item from the project
README's pending-work list.

Per-request flow, exactly matching the architecture doc:
  run_evidence_pipeline()  -> policyEvidence + clinicalEvidence +
                               clinicalCriteriaEval + mlFeatures
                               (agents + RAG + deterministic aggregator —
                               never a decision)
  MLTriageAgent.run()      -> the ONE place a decision is made
  explain_decision()       -> plain-language explanation of that decision,
                               never a second opinion on it

ml/ is a REAL subpackage of policy-rag/ (2026-08-19+) — no sys.path
hack needed. The old ml-triage/ sibling directory (a RandomForest on all
10 aggregator features, reached via a sys.path insert into a directory
outside this package) was retired and deleted; ml/model.py's
LogisticRegression, trained on 4 of those 10 features, replaces it in
place — same MLTriageAgent class name/`.run()` contract, so nothing else
in this file needed to change beyond the import line below.

Run:
    cd ProAuth_AI_ML/policy-rag
    uvicorn main:app --host 0.0.0.0 --port 8002
"""
import sys
import traceback
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# priority_intelligence MUST be imported — and its XGBoost model loaded —
# before rag.retrieval (below) or anything that transitively imports it
# (triage_graph.py does, via policy_evidence_agent.py). Verified via
# direct reproduction (2026-08-21): unpickling this XGBoost model AFTER
# sentence_transformers/torch (rag.retrieval's embedding model) has
# already been imported into the process causes a hard SIGSEGV with no
# Python-level error at all — both bundle their own native OpenMP
# runtime, and whichever initializes first avoids the conflict; loading
# XGBoost second consistently crashed the whole service, loading it first
# consistently worked. get_ranker() forces the eager load right here,
# once, at process startup — not per-request — for exactly this reason.
# priority_intelligence is a sibling package under ProAuth_AI_ML/, not
# inside policy-rag/, hence the sys.path addition. See
# priority_intelligence/ranker.py's own docstring and README.md.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from priority_intelligence.ranker import get_ranker
get_ranker()
from priority_intelligence.api.main import router as priority_router

from ml.model import MLTriageAgent
from agents.clinical_evidence_agent import age_criterion_was_graded
from agents.companion_agent import explain_decision
from rag.retrieval import get_plan_tier, TIER_COST_SHARE_PERCENT
from triage_graph import run_evidence_pipeline

app = FastAPI(title="ProAuth AI Triage Service")
app.include_router(priority_router)

_ml_agent: Optional[MLTriageAgent] = None


def _get_ml_agent() -> MLTriageAgent:
    # Loads the pickle once per process, same lifecycle pattern as this
    # project's other cached clients (policy_evidence_agent.py's
    # _get_client(), retrieval.py's _get_model()).
    global _ml_agent
    if _ml_agent is None:
        _ml_agent = MLTriageAgent()
    return _ml_agent


class TriageRequest(BaseModel):
    requestedService: str
    diagnosis: str
    planId: Optional[str] = None
    secondaryDiagnosis: Optional[str] = None
    icd10Code: Optional[str] = None
    clinicalJustification: Optional[str] = None
    patientFacts: Optional[dict[str, Any]] = None
    # Manual override for Document Agent's output — see
    # triage_graph.py's run_evidence_pipeline docstring. Leave unset to
    # have Document Agent run for real against attachedDocuments below.
    documentEvidence: Optional[dict[str, Any]] = None
    # Files actually uploaded for this request (Node's /api/documents
    # persists these) — list of {"documentType", "storageUrl", "mimeType"}.
    # Feeds Document Agent's real OCR verification; ignored if
    # documentEvidence above is supplied instead.
    attachedDocuments: Optional[list[dict[str, Any]]] = None
    # requestContext carries urgency/patient_age (keys "urgency" /
    # "patient_age" or "age"). The model's 10 fixed features never include
    # age or urgency directly (adding either would require retraining) —
    # both instead flow in through Clinical Agent's criteria grading
    # (clinical_evidence_agent.py), then into clinical_evidence_score /
    # diagnosisSupported like any other criterion. urgency grounds
    # urgency_consistency (2026-08-19+): a genuine non-routine claim earns
    # a real PASS, a "fishy"/inconsistent one FAILs it AND hard-gates to
    # PEND (coverage_reasoning_agent.py's urgencyFlagged). patient_age
    # (2026-08-21+) is merged into extracted_facts before criteria grading
    # (evaluate_clinical_criteria) so any policy-named age criterion (e.g.
    # NCD-210.14's age_50_77) can be graded against the real value — added
    # after live testing showed a real 61-year-old FAILing that criterion
    # as "age not documented" while age sat unused in this field.
    # Both are still ALSO passed through to informational_context below
    # purely so the Companion Agent's explanation can mention the claimed
    # value by name, not because either is otherwise uninvolved in the
    # decision.
    requestContext: Optional[dict[str, Any]] = None
    threadId: Optional[str] = None
    # The requesting doctor's specialty. Unlike patient_age above, this
    # DOES contribute to the ML input — it flows into Clinical Agent's
    # specialty_match check (clinical_evidence_agent.py), which factors
    # into clinical_evidence_score like any other criterion.
    providerSpecialty: Optional[str] = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/triage")
def triage(req: TriageRequest):
    # Defensive backstop (2026-08-20 — coordinated Groq resilience, see
    # docs/PROGRESS_TRACKER.md §9.9): every agent-level Groq call site now
    # degrades gracefully on its own (a rate limit / connection failure
    # produces a safe, explained PEND through the existing gates, not a
    # crash — see policy_evidence_agent.py / clinical_evidence_agent.py).
    # This catches whatever's still left — a genuinely unexpected failure
    # elsewhere in the pipeline (e.g. a DB connectivity issue) — so the
    # doctor/Node ever sees a clean, honest 503 instead of a raw Python
    # traceback dumped as response text (previously the literal behavior
    # here: an uncaught exception → FastAPI's default 500 with the full
    # stack trace as the body, which Node then truncated and surfaced
    # straight to the reviewer).
    try:
        return _run_triage(req)
    except Exception as exc:  # noqa: BLE001 - final backstop, deliberately broad
        print(f"[main.py] /triage failed unexpectedly: {exc}")
        traceback.print_exc()
        raise HTTPException(
            status_code=503,
            detail={
                "error": "triage_service_unavailable",
                "message": "The AI evaluation pipeline hit an unexpected error and could not complete this request. Please try again shortly.",
            },
        ) from exc


def _run_triage(req: TriageRequest):
    evidence = run_evidence_pipeline(
        requested_service=req.requestedService,
        diagnosis=req.diagnosis,
        plan_id=req.planId,
        secondary_diagnosis=req.secondaryDiagnosis,
        icd10_code=req.icd10Code,
        clinical_justification=req.clinicalJustification,
        provider_specialty=req.providerSpecialty,
        patient_facts=req.patientFacts,
        document_evidence=req.documentEvidence,
        attached_documents=req.attachedDocuments,
        request_context=req.requestContext,
        thread_id=req.threadId,
    )

    ml_features = evidence.get("mlFeatures") or {}
    decision = _get_ml_agent().run(ml_features)

    # INFORMATIONAL ONLY (see TriageRequest.requestContext) — never
    # touches the model. providerSpecialty AND urgency are deliberately
    # NOT included here since both already contributed to
    # clinical_criteria_eval above (specialty_match / urgency_consistency)
    # — repeating either as an "informational" note would misleadingly
    # imply it didn't affect the decision. patientAge is conditionally
    # excluded the same way, per-request, below (see age_was_graded) —
    # unlike specialty/urgency it's only SOMETIMES a real decision input,
    # depending on whether this policy named an age-range criterion at
    # all. The Companion Agent can still
    # reference the claimed urgency through clinical_criteria_eval itself.
    context = req.requestContext or {}
    # Cost-share note (2026-08-20, user-requested — see
    # rag/retrieval.py's TIER_COST_SHARE_PERCENT docstring): informational
    # only, same non-decision lane as patientAge below. planId already
    # resolves to a payer via get_plan_payer() elsewhere in this pipeline;
    # this is a second, independent lookup of the same plan's cost-sharing
    # tier — deliberately NOT threaded into policy_evidence/ml_features/
    # coverage_reasoning, so it has no path to ever reach a gate or the
    # model.
    plan_tier = get_plan_tier(req.planId) if req.planId else None
    plan_cost_share_percent = TIER_COST_SHARE_PERCENT.get(plan_tier) if plan_tier else None
    # Same "don't call a real decision input informational" rule as
    # providerSpecialty/urgency above — but patient_age's relevance is
    # conditional on THIS policy actually naming an age-range criterion
    # (most don't), so it's checked per-request via age_criterion_was_graded
    # rather than excluded unconditionally. Found live (2026-08-21): right
    # after adding the age-range resolver, a PASSing age_50_77 criterion
    # still got called "informational only, did not affect this decision"
    # in the same explanation that named "age" among the passing criteria.
    patient_age_value = context.get("patient_age", context.get("age"))
    age_was_graded = age_criterion_was_graded(
        (evidence.get("clinicalCriteriaEval") or {}).get("criteriaResults"), patient_age_value
    )
    informational_context = {
        "patientAge": patient_age_value if not age_was_graded else None,
        "planCostShare": (
            f"{plan_tier.title()} plan — estimated to cover approximately {plan_cost_share_percent}% "
            f"of the allowed expense (patient responsible for the remainder). A general estimate, "
            f"not looked up from this patient's specific benefit document."
        ) if plan_cost_share_percent else None,
    }
    if not any(informational_context.values()):
        informational_context = None

    explanation = explain_decision(
        decision=decision,
        ml_features=ml_features,
        policy_evidence=evidence.get("policyEvidence"),
        clinical_evidence=evidence.get("clinicalEvidence"),
        clinical_criteria_eval=evidence.get("clinicalCriteriaEval"),
        informational_context=informational_context,
    )

    return {
        "policyEvidence": evidence.get("policyEvidence"),
        "clinicalEvidence": evidence.get("clinicalEvidence"),
        "clinicalCriteriaEval": evidence.get("clinicalCriteriaEval"),
        "documentEvidence": evidence.get("documentEvidence"),
        "mlFeatures": ml_features,
        "decision": decision,
        "explanation": explanation,
        # Transparency for the memoization layer (triage_graph.py) — which
        # LLM-calling stages actually ran this call vs. were reused from
        # this thread's prior checkpoint. Never a silent optimization.
        "memoization": {
            "policyEvidenceReused": bool(evidence.get("policyEvidenceReused")),
            "clinicalEvidenceReused": bool(evidence.get("clinicalEvidenceReused")),
            "clinicalCriteriaEvalReused": bool(evidence.get("clinicalCriteriaEvalReused")),
        },
    }
