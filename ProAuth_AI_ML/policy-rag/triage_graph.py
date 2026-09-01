import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, TypedDict

from dotenv import load_dotenv
from langgraph.checkpoint.mongodb import MongoDBSaver
from langgraph.graph import END, START, StateGraph
from pymongo import MongoClient

from agents.clinical_evidence_agent import evaluate_clinical_criteria, extract_clinical_evidence
from agents.coverage_reasoning_agent import aggregate_ml_features
from agents.document_agent import evaluate_document_evidence
from agents.policy_evidence_agent import evaluate_policy_evidence

load_dotenv()

CHECKPOINT_DB_NAME = "proauth_langgraph"

# A cached stage result older than this is never reused, regardless of
# whether its inputs still match — a safety net against reusing evidence
# from a genuinely stale prior run (e.g. a PA request left half-finished
# for months) rather than tuning for a specific expected resubmission
# window. Real resubmissions in this workflow happen within days.
STALE_CHECKPOINT_MAX_AGE = timedelta(days=90)


class TriageState(TypedDict, total=False):
    requestedService: str
    diagnosis: str
    secondaryDiagnosis: Optional[str]
    icd10Code: Optional[str]
    clinicalJustification: Optional[str]
    planId: Optional[str]
    providerSpecialty: Optional[str]
    patientFacts: dict[str, Any]
    requestContext: dict[str, Any]
    documentEvidence: Optional[dict[str, Any]]
    attachedDocuments: Optional[list[dict[str, Any]]]
    policyEvidence: dict[str, Any]
    clinicalEvidence: dict[str, Any]
    clinicalCriteriaEval: dict[str, Any]
    mlFeatures: dict[str, Any]
    # Set by policy_evidence_node / clinical_evidence_node when they reuse
    # a prior checkpoint's output instead of recomputing — read by
    # clinical_criteria_node, which must ONLY reuse ITS OWN prior result
    # when both its upstream dependencies were also reused (see that
    # node's docstring). Also surfaced in the final API response
    # (main.py) for transparency — never a silent optimization.
    policyEvidenceReused: bool
    clinicalEvidenceReused: bool
    clinicalCriteriaEvalReused: bool
    # The prior COMPLETED run's final channel_values for this thread_id
    # (or None), captured once in run_evidence_pipeline() before this run
    # starts — see module docstring for why it can't be queried live from
    # inside a node. Internal plumbing only; stripped before the pipeline
    # result is returned to callers.
    _previousState: Optional[dict[str, Any]]


def policy_evidence_node(state: TriageState) -> dict:
    # Reuse ONLY when every input this stage's output actually depends on
    # is unchanged from the last completed run of this SAME thread_id, and
    # that prior run genuinely found a policy (never reuse a degraded/
    # not-found result — that's exactly the case worth retrying, e.g. the
    # corpus may have grown since).
    prev = state.get("_previousState")
    if (
        prev
        and prev.get("requestedService") == state.get("requestedService")
        and prev.get("diagnosis") == state.get("diagnosis")
        and prev.get("planId") == state.get("planId")
        and (prev.get("policyEvidence") or {}).get("policyFound")
    ):
        return {"policyEvidence": prev["policyEvidence"], "policyEvidenceReused": True}

    result = evaluate_policy_evidence(
        requested_service=state["requestedService"],
        diagnosis=state["diagnosis"],
        plan_id=state.get("planId"),
    )
    return {"policyEvidence": result, "policyEvidenceReused": False}


def clinical_evidence_node(state: TriageState) -> dict:
    prev = state.get("_previousState")
    if (
        prev
        and prev.get("diagnosis") == state.get("diagnosis")
        and prev.get("secondaryDiagnosis") == state.get("secondaryDiagnosis")
        and prev.get("icd10Code") == state.get("icd10Code")
        and prev.get("clinicalJustification") == state.get("clinicalJustification")
        # Require clinicalEvidence to actually be present before trusting
        # it — a prior run that crashed mid-graph (e.g. an upstream Groq
        # error) can leave a partial checkpoint where this key was never
        # written at all. `not (None or {}).get("agentError")` is truthy
        # in that case too, which used to reach the `prev["clinicalEvidence"]`
        # index below and raise KeyError (found live, 2026-08-19+) — same
        # "require truthy before indexing" guard already used by
        # policy_evidence_node/clinical_criteria_node above.
        and prev.get("clinicalEvidence")
        and not prev["clinicalEvidence"].get("agentError")
    ):
        return {"clinicalEvidence": prev["clinicalEvidence"], "clinicalEvidenceReused": True}

    result = extract_clinical_evidence(
        primary_diagnosis=state["diagnosis"],
        secondary_diagnosis=state.get("secondaryDiagnosis"),
        icd10_code=state.get("icd10Code"),
        clinical_justification=state.get("clinicalJustification"),
    )
    return {"clinicalEvidence": result, "clinicalEvidenceReused": False}


def clinical_criteria_node(state: TriageState) -> dict:
    # Can only run after policy_evidence_node — it needs Policy Agent's own
    # named clinicalCriteria list, which is exactly why this is a separate
    # fan-in stage rather than part of the earlier parallel branch. Manually-
    # supplied patientFacts (useful for testing/edge cases) is merged in and
    # overrides on key collision, but Clinical Agent's extraction is the
    # default path — same precedent as before this node existed.
    clinical_evidence = state.get("clinicalEvidence") or {}
    merged_facts = {**clinical_evidence.get("extractedFacts", {}), **(state.get("patientFacts") or {})}
    policy_evidence = state["policyEvidence"]

    # This stage's real inputs are the (possibly just-reused) outputs of
    # BOTH upstream nodes plus a few direct fields — so it can only safely
    # reuse ITS OWN prior result when BOTH upstream nodes were themselves
    # reused this run (their fresh output, if either recomputed, could
    # differ from what THIS prior result was graded against) AND its own
    # direct inputs (specialty/urgency) are unchanged.
    prev = state.get("_previousState")
    upstream_unchanged = bool(state.get("policyEvidenceReused")) and bool(state.get("clinicalEvidenceReused"))
    if (
        prev
        and upstream_unchanged
        and prev.get("providerSpecialty") == state.get("providerSpecialty")
        and (prev.get("requestContext") or {}).get("urgency") == (state.get("requestContext") or {}).get("urgency")
        # patient_age is now merged into extracted_facts before grading
        # (evaluate_clinical_criteria) — a changed age on a resubmission
        # must not reuse a stale result graded against the old one.
        and (prev.get("requestContext") or {}).get("patient_age") == (state.get("requestContext") or {}).get("patient_age")
        and prev.get("clinicalCriteriaEval")
        and not prev["clinicalCriteriaEval"].get("agentError")
    ):
        return {"clinicalCriteriaEval": prev["clinicalCriteriaEval"], "clinicalCriteriaEvalReused": True}

    result = evaluate_clinical_criteria(
        clinical_criteria=policy_evidence.get("clinicalCriteria"),
        policy_evidence=policy_evidence,
        extracted_facts=merged_facts,
        diagnosis=state["diagnosis"],
        # Checked alongside the primary diagnosis for indication_match
        # (2026-08-19+) — a drug can be on-label for the secondary
        # diagnosis even when the primary one doesn't match, see
        # clinical_evidence_agent.py's _resolve_indication_match docstring.
        secondary_diagnosis=state.get("secondaryDiagnosis"),
        requested_service=state.get("requestedService"),
        provider_specialty=state.get("providerSpecialty"),
        icd10_code=state.get("icd10Code"),
        # A genuine urgency claim now contributes to clinical_evidence_score
        # (see clinical_evidence_agent.py's urgency_consistency criterion).
        urgency=(state.get("requestContext") or {}).get("urgency"),
        # Merged into extracted_facts before grading, so any policy-named
        # age criterion (e.g. NCD-210.14's age_50_77) can be graded against
        # the real value instead of hoping free text restates it.
        patient_age=(state.get("requestContext") or {}).get("patient_age"),
    )
    return {"clinicalCriteriaEval": result, "clinicalCriteriaEvalReused": False}


def document_evidence_node(state: TriageState) -> dict:
    # Runs after policy_evidence_node — needs its requiredDocuments list,
    # same fan-in reasoning as clinical_criteria_node. A caller-supplied
    # documentEvidence override (same manual-override precedent as
    # patientFacts before Clinical Agent existed) always wins over
    # running the agent; only runs it when nothing was supplied at all.
    if state.get("documentEvidence") is not None:
        return {}
    policy_evidence = state.get("policyEvidence") or {}
    result = evaluate_document_evidence(
        policy_evidence.get("requiredDocuments"),
        attached_documents=state.get("attachedDocuments"),
    )
    return {"documentEvidence": result}


def coverage_reasoning_node(state: TriageState) -> dict:
    # Repurposed: deterministic ML feature-vector aggregator now, not an
    # LLM agent — see coverage_reasoning_agent.py's module docstring.
    result = aggregate_ml_features(
        policy_evidence=state["policyEvidence"],
        clinical_criteria_eval=state["clinicalCriteriaEval"],
        document_evidence=state.get("documentEvidence"),
    )
    return {"mlFeatures": result}


_checkpointer = None


def _get_checkpointer():
    # Module-level singleton, same lifecycle pattern as this project's
    # other cached clients (policy_evidence_agent.py's _get_client(),
    # retrieval.py's _get_model()) — constructed once via a plain
    # MongoClient, not via MongoDBSaver.from_conn_string's context
    # manager (which force-closes on exit; a checkpointer needs to
    # outlive a single call).
    global _checkpointer
    if _checkpointer is None:
        mongodb_uri = os.environ.get("MONGODB_URI")
        if not mongodb_uri:
            raise RuntimeError("MONGODB_URI not set (add it to ProAuth_AI_ML/.env)")
        client = MongoClient(mongodb_uri)
        # db_name set explicitly — the real configured MONGODB_URI has no
        # database name embedded in its path, and MongoDBSaver doesn't
        # parse one out of the connection string on its own.
        _checkpointer = MongoDBSaver(client, db_name=CHECKPOINT_DB_NAME)
    return _checkpointer


def _get_previous_state(config):
    """
    Returns the full TriageState channel_values from the last COMPLETED
    run of this thread_id, or None if there isn't one (first-ever
    evaluation of this request, no thread_id given, the checkpoint is
    older than STALE_CHECKPOINT_MAX_AGE, or the checkpointer is
    unreachable for any reason). Never raises — a memoization miss just
    means "compute fresh," the same safe default as every other agent
    short-circuit in this project; it must never be the reason a request
    fails.
    """
    thread_id = (config or {}).get("configurable", {}).get("thread_id")
    if not thread_id:
        return None
    try:
        checkpoint_tuple = _get_checkpointer().get_tuple(config)
    except Exception:
        return None
    if checkpoint_tuple is None:
        return None

    checkpoint = checkpoint_tuple.checkpoint
    ts = checkpoint.get("ts")
    if ts:
        try:
            checkpoint_time = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) - checkpoint_time > STALE_CHECKPOINT_MAX_AGE:
                return None
        except (ValueError, TypeError):
            pass  # unparseable timestamp — don't let a formatting quirk block reuse

    return checkpoint.get("channel_values") or None


def build_triage_graph():
    graph = StateGraph(TriageState)
    graph.add_node("policy_evidence", policy_evidence_node)
    graph.add_node("clinical_evidence", clinical_evidence_node)
    graph.add_node("clinical_criteria_eval", clinical_criteria_node)
    graph.add_node("document_evidence", document_evidence_node)
    graph.add_node("coverage_reasoning", coverage_reasoning_node)
    # Parallel fan-out: policy_evidence and clinical_evidence (extraction)
    # both only need the original request, no dependency on each other.
    # LangGraph runs clinical_criteria_eval once both predecessors
    # complete — it needs policy_evidence's clinicalCriteria list AND
    # clinical_evidence's extracted facts. document_evidence only needs
    # policy_evidence's requiredDocuments list, so it can run right after
    # policy_evidence rather than waiting on clinical_evidence too.
    # coverage_reasoning (the aggregator) waits on BOTH
    # clinical_criteria_eval and document_evidence — it also reads
    # state["policyEvidence"] directly without a dedicated edge, since
    # LangGraph state is cumulative.
    graph.add_edge(START, "policy_evidence")
    graph.add_edge(START, "clinical_evidence")
    graph.add_edge("policy_evidence", "clinical_criteria_eval")
    graph.add_edge("clinical_evidence", "clinical_criteria_eval")
    graph.add_edge("policy_evidence", "document_evidence")
    graph.add_edge("clinical_criteria_eval", "coverage_reasoning")
    graph.add_edge("document_evidence", "coverage_reasoning")
    graph.add_edge("coverage_reasoning", END)
    return graph.compile(checkpointer=_get_checkpointer())


_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        _graph = build_triage_graph()
    return _graph


def run_evidence_pipeline(
    requested_service,
    diagnosis,
    plan_id=None,
    secondary_diagnosis=None,
    icd10_code=None,
    clinical_justification=None,
    provider_specialty=None,
    patient_facts=None,
    document_evidence=None,
    attached_documents=None,
    request_context=None,
    thread_id=None,
):
    """
    Thin, testable entry point — same shape callers use over HTTP (see
    policy-rag/main.py). Returns policyEvidence + clinicalEvidence +
    clinicalCriteriaEval + documentEvidence + mlFeatures (the aggregator's
    ready-to-consume ML feature vector) — never a triage decision.

    document_evidence: manual override for Document Agent's output
    (documentationScore, nRequiredDocuments, nDocumentsSubmitted,
    missingDocuments, relevantDocuments) — same precedent as patientFacts
    before Clinical Agent existed. Leave None to run document_agent.py for
    real against attached_documents.

    attached_documents: files actually uploaded for this request — list
    of {"documentType", "storageUrl", "mimeType"} as persisted by the Node
    backend's /api/documents endpoint. Feeds document_agent.py's real OCR
    verification; ignored entirely when document_evidence is supplied.

    provider_specialty: the requesting doctor's specialty. Feeds
    clinical_criteria_node's deterministic specialty_match check (see
    clinical_evidence_agent.py's _resolve_specialty_match) — contributes
    to clinical_evidence_score like any other checklist item, never a
    separate side-channel.

    thread_id: pass the Authorization's own ID (not a random uuid) so
    memoization actually works — every evaluation of the SAME PA request
    (initial submission + every resubmission) shares one checkpoint
    history, and the three LLM-calling stages skip themselves when their
    relevant inputs are unchanged since the prior run (see module
    docstring). Leave None (falls back to a fresh uuid4()) only for
    standalone/test calls that shouldn't participate in any thread's
    history at all — the result's policyEvidenceReused /
    clinicalEvidenceReused / clinicalCriteriaEvalReused flags report which
    stages actually ran fresh this call.
    """
    graph = _get_graph()
    thread_id = thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    # Captured ONCE, here, before graph.invoke() writes this run's own
    # first checkpoint — see module docstring for why querying the
    # checkpointer from inside a node instead would never actually find
    # the prior run (it would see this run's own in-progress checkpoint).
    previous_state = _get_previous_state(config)

    initial_state: TriageState = {
        "requestedService": requested_service,
        "diagnosis": diagnosis,
        "secondaryDiagnosis": secondary_diagnosis,
        "icd10Code": icd10_code,
        "clinicalJustification": clinical_justification,
        "planId": plan_id,
        "providerSpecialty": provider_specialty,
        "patientFacts": patient_facts or {},
        "documentEvidence": document_evidence,
        "attachedDocuments": attached_documents or [],
        "requestContext": request_context or {},
        "_previousState": previous_state,
    }
    result = graph.invoke(initial_state, config=config)
    result.pop("_previousState", None)  # internal plumbing only — never returned to callers
    return result


if __name__ == "__main__":
    import json

    result = run_evidence_pipeline(
        requested_service="bariatric surgery",
        diagnosis="morbid obesity with type 2 diabetes",
        plan_id="PLAN005",
        icd10_code="E66.01",
        clinical_justification=(
            "Patient has BMI of 42 kg/m^2 and a 5-year history of type 2 diabetes "
            "mellitus. She has completed a 6-month physician-supervised weight "
            "management program including dietary changes and increased physical "
            "activity, without achieving sustained weight loss."
        ),
        request_context={
            "patient_age": 45,
            "patient_sex": "F",
            "service_type": "surgical",
            "provider_specialty": "bariatric surgery",
            "urgency": "routine",
            "care_setting": "outpatient",
        },
    )
    print(json.dumps(result, indent=2))
