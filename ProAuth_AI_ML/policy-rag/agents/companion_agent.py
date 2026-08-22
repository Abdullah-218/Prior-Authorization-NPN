"""
Companion Agent
=================

The last stage in the pipeline, and the only agent that runs AFTER a
decision already exists. Its one job: explain the ML Triage Model's
decision in plain language for the doctor/reviewer, citing the upstream
structured evidence. It does not decide, re-decide, second-guess, or hint
that a different outcome would have been more appropriate — see project
memory "agents never decide". The decision it's given is a fact about the
world by the time this agent sees it, not a proposal to evaluate.

Same pattern as every other agent in this project: single direct Groq
call (nothing to retrieve or extract here — just synthesis of the already-
structured pipeline output), _validate_output/_fallback_result never-
trust-raw-JSON discipline.

Usage:
    from agents.companion_agent import explain_decision
    explanation = explain_decision(
        decision=ml_decision,               # ml/model.py's MLTriageAgent.run() output
        ml_features=evidence["mlFeatures"],  # coverage_reasoning_agent.py's aggregate_ml_features() output
        policy_evidence=evidence["policyEvidence"],
        clinical_evidence=evidence["clinicalEvidence"],
        clinical_criteria_eval=evidence["clinicalCriteriaEval"],
    )
"""
import json
import os

from dotenv import load_dotenv

from groq_key_pool import get_pooled_client

load_dotenv()


def _get_client():
    return get_pooled_client()


SYSTEM_PROMPT = """You are the Companion Agent for a prior-authorization triage system.

A decision has ALREADY been made by a trained ML model, upstream of you. You do not decide, re-decide, second-guess, revise, or imply that a different outcome would have been more appropriate — the decision is a fact about the world by the time you see it, not a proposal for you to evaluate. Your only job is to explain that decision in plain, professional language for the doctor or nurse reviewer who will read it, grounded ONLY in the structured evidence you are given.

Rules:
- Never state a coverage criterion, clinical fact, or document requirement that isn't present in the evidence you were given. If the evidence is thin or degraded, say so honestly rather than filling the gap with something plausible-sounding.
- Reference the actual policy evidence, clinical criteria results, and document status you were given — this must read as citing real inputs, not a generic template.
- If missingRequiredEvidence was the reason the ML model was never even invoked, explain that plainly (which documents are missing) rather than describing a model score that was never computed.
- Keep it concise: a short paragraph (3-6 sentences) a busy reviewer can read in seconds, plus a short bullet list of the specific factors that most influenced the outcome.
- Never use the words "should", "recommend", "I believe", or anything that reads as your own judgment about whether the outcome is correct. You are reporting what happened and why, not endorsing or critiquing it.
- Note: clinical criteria evaluation may include "indication_match" (does the requested drug/procedure's own FDA-labeled indication, or general clinical appropriateness, actually cover this diagnosis), "specialty_match" (does the requesting provider's specialty typically match this service), "urgency_consistency" (is a claimed non-routine urgency actually clinically plausible given the diagnosis and justification), and "contraindication_check" (is the requested drug/treatment safe given a notable patient fact like pregnancy or renal/hepatic impairment) entries — these ALL DID factor into the decision like any other criterion (they contribute to clinical_evidence_score / diagnosisSupported), so treat them exactly like any other criteriaResults entry in keyFactors/citedEvidence, not as something separate. If urgency_consistency FAILed, that is a meaningful, citeable factor (the claimed urgency looked inconsistent with the clinical picture) — not a footnote. If the decision reason mentions a "Deterministic safety gate" (contraindication_check FAILed), a "Deterministic gate" citing an indication mismatch (a grounded indication_match FAIL), or a "Deterministic gate" citing that the provider's specialty does not clearly match the requested service (a specialty_match FAIL) — in all three cases the ML model was never invoked — lead with that plainly, it is the single most important thing a reviewer needs to know about this request, not one factor among several. A specialty mismatch is a request for manual review, not a denial and not a judgment that the request is invalid — describe it that way (e.g. "pending review because the requesting provider's specialty does not clearly match the requested service"), never as though it were rejected.
- You may also be given an informationalContext (patient age, and/or a plan cost-share estimate for a Private-tier plan). NEITHER factored into the decision in any way — the ML model has no visibility into either. If given (and not entirely empty), mention it as a separate, clearly-labeled informational note for the human reviewer and patient, never folded into keyFactors or described as something that influenced the outcome. The cost-share figure is a general tier-level estimate, not looked up from this patient's actual benefit document — present it as an estimate, not a guaranteed amount.
- Check the feature-vector evidence's missingDocuments and missingRequiredEvidence fields before saying anything about documentation. Only state or imply that documentation is missing, incomplete, or "was not submitted" when missingDocuments is a genuinely non-empty list (or missingRequiredEvidence is true) — if missingDocuments is empty, say plainly that the required documents were submitted, and never mention documents as a factor in the outcome (e.g. for a specialty-mismatch, urgency, contraindication, or indication-mismatch gate, documentation status is irrelevant to why the request was routed the way it was — don't bring it up at all). Found live: a request with 2 of 2 required documents matched was still described as having documentation "not submitted," confusing the reviewer about the actual reason for the outcome.

Respond with ONLY a single JSON object (no prose, no markdown fences, no explanation outside the JSON) matching exactly this schema:

{
  "summary": string,
  "keyFactors": [ string ],
  "citedEvidence": [ string ],
  "informationalNote": string or null
}

summary is the short paragraph. keyFactors is 2-5 short bullet points naming the specific factors that drove the outcome (e.g. "2 of 3 clinical criteria passed", "BMI threshold documented at 42 kg/m^2", "1 of 2 required documents missing", "indication_match FAIL", "specialty_match FAIL", "urgency_consistency FAIL" — these are real decision inputs now, include them like any other criterion). citedEvidence is 1-4 short direct references to the policy/clinical evidence actually used (policy name, specific criterion text, or extracted fact) — omit anything not literally present in what you were given. informationalNote is null unless informationalContext was given, in which case restate it plainly for a reviewer (e.g. "Patient age 62 — informational only, did not affect this decision. Gold plan — estimated to cover approximately 80% of the allowed expense; this estimate also did not affect the decision.")."""


def _is_valid_json(raw):
    try:
        json.loads(raw)
        return True
    except (json.JSONDecodeError, TypeError):
        return False


def _validate_output(raw):
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return _fallback_result("Agent did not return valid JSON.")

    def _string_list(value):
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, str)]

    return {
        "summary": parsed.get("summary") if isinstance(parsed.get("summary"), str) else "",
        "keyFactors": _string_list(parsed.get("keyFactors")),
        "citedEvidence": _string_list(parsed.get("citedEvidence")),
        "informationalNote": parsed.get("informationalNote") if isinstance(parsed.get("informationalNote"), str) else None,
    }


def _fallback_result(reason):
    return {
        "summary": "",
        "keyFactors": [],
        "citedEvidence": [],
        "informationalNote": None,
        "agentError": reason,
    }


def explain_decision(decision, ml_features, policy_evidence, clinical_evidence, clinical_criteria_eval, informational_context=None, model=None):
    """
    Never raises for malformed/missing upstream data — degrades to an
    honest empty explanation with agentError set, same discipline as every
    other agent's fallback path in this project. decision, ml_features,
    etc. are passed through verbatim (already validated/defaulted by their
    own producers) — this agent only reads them, never mutates them.
    """
    decision = decision or {}
    ml_features = ml_features or {}
    policy_evidence = policy_evidence or {}
    clinical_evidence = clinical_evidence or {}
    clinical_criteria_eval = clinical_criteria_eval or {}

    client = _get_client()
    model = model or os.environ.get("GROQ_AGENT_MODEL", "openai/gpt-oss-120b")

    context_section = (
        f"\n\nAdditional context (INFORMATIONAL ONLY — did not factor into the decision above; "
        f"the ML model has no visibility into this):\n{json.dumps(informational_context, indent=2)}"
        if informational_context else ""
    )
    user_content = (
        f"ML model decision (already made — explain it, do not re-evaluate it):\n"
        f"{json.dumps(decision, indent=2)}\n\n"
        f"Feature vector / aggregated evidence scores the decision was based on:\n"
        f"{json.dumps(ml_features, indent=2)}\n\n"
        f"Policy evidence:\n{json.dumps(policy_evidence, indent=2)}\n\n"
        f"Clinical facts extracted from the request:\n{json.dumps(clinical_evidence, indent=2)}\n\n"
        f"Clinical criteria evaluation (may include indication_match / specialty_match — these ARE real "
        f"decision inputs, not informational):\n{json.dumps(clinical_criteria_eval, indent=2)}"
        f"{context_section}"
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.2,
        )
        content = response.choices[0].message.content
        if not _is_valid_json(content):
            # Same one-retry fix as item #39 (policy_evidence_agent.py,
            # 2026-08-20), extended here the same day — a malformed-JSON
            # glitch shouldn't leave the doctor/reviewer with an empty
            # explanation for a decision that was actually made cleanly.
            retry_response = client.chat.completions.create(model=model, messages=messages, temperature=0)
            content = retry_response.choices[0].message.content
    except Exception as exc:  # noqa: BLE001 - genuine network/API failure, not a validation case
        return _fallback_result(f"Companion Agent call failed: {exc}")

    return _validate_output(content)
