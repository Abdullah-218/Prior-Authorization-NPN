"""
Clinical Agent
================

Extracts structured clinical facts from the request itself — NOT from any
patient-history database (there is no Synthea or similar data source in
this architecture; see project memory "prior-auth architecture" for the
correction history). Its only inputs are fields already present in the
PA request payload: primary diagnosis, secondary diagnosis, ICD-10 code,
and the doctor's free-text clinical justification.

Its job is exactly what coverage_reasoning_agent.py needed a real source
for: patient_facts. Previously that was hand-typed in test fixtures for
lack of a real producer — this agent generates it for real, by reading
the diagnosis codes plus whatever the doctor actually wrote in the
justification text and extracting the concrete facts asserted there
(e.g. "BMI of 42 kg/m^2 and a 5-year history of type 2 diabetes" ->
{"bmi": 42, "comorbidities": ["type 2 diabetes"]}).

Same pattern as coverage_reasoning_agent.py: single direct Groq call, no
tools (there is nothing to retrieve — this is pure extraction from given
text), _validate_output/_fallback_result never-trust-raw-JSON discipline.

extractedFacts is intentionally free-form key->value, not a fixed schema
— same reasoning as patient_facts itself throughout this project:
different diagnoses need different facts, and hardcoding a fixed
vocabulary here would just be hardcoded rules by another name.

The single most important rule this agent follows: under-extraction is
always safer than over-extraction. A fact that isn't clearly stated or
directly, unambiguously inferable from the given text must NOT appear in
extractedFacts — its absence is exactly what makes Coverage Reasoning
Agent correctly report the corresponding criterion as MISSING rather than
silently assuming a favorable fact that was never actually established.

Usage:
    from agents.clinical_evidence_agent import extract_clinical_evidence
    result = extract_clinical_evidence(
        primary_diagnosis="morbid obesity",
        icd10_code="E66.01",
        clinical_justification="Patient has BMI of 42 kg/m^2 and a 5-year "
            "history of type 2 diabetes mellitus...",
    )

This module also exposes a second, later-stage function:
evaluate_clinical_criteria(). Extraction (above) only needs the request
itself, so it runs in parallel with the Policy Evidence Agent. But scoring
the extracted facts against a named clinical checklist needs that
checklist's names, and only the Policy Evidence Agent produces those
(policy_evidence["clinicalCriteria"]) — so this second function runs one
stage later, after both branches of the parallel fan-out have completed
(see triage_graph.py). It feeds the ML feature aggregator
(coverage_reasoning_agent.py's aggregate_ml_features) with
diagnosisSupported, per-criterion PASS/FAIL, and clinicalEvidenceScore.

evaluate_clinical_criteria makes ONE deliberate, narrow exception to this
project's "absence != false" rule: a named criterion with no supporting
extracted fact is scored FAIL, not MISSING/UNKNOWN. This is safe only
because it's scoped to this specific checklist — the ML model's trained
schema (n_clinical_criteria_passed/failed) has exactly two buckets, no
third "not yet demonstrated" bucket to put it in, and defaulting an
undemonstrated criterion to FAIL only ever pushes the request toward more
scrutiny (a lower clinicalEvidenceScore), never toward a false approval.
extract_clinical_evidence's own fact extraction above is NOT part of this
exception and keeps the full absence-means-unknown rule.
"""
import json
import os
import re
import time

from dotenv import load_dotenv
from groq import APIConnectionError, APITimeoutError, InternalServerError, RateLimitError

from groq_key_pool import get_pooled_client

from .contraindication_lookup import check_known_contraindications, has_notable_risk_facts
from .drug_reference_lookup import find_drug_reference, indication_match_strength
from .specialty_check import check_provider_specialty

load_dotenv()


def _get_client():
    return get_pooled_client()


# Transient failures only — a real BadRequestError/AuthenticationError/etc.
# won't be fixed by retrying, so those still propagate immediately to the
# caller's existing except block. Found live (2026-08-22): a 429 with the
# API's own message saying "try again in 217.5ms" hit neither of this
# module's two Groq call sites having any retry for an API-level failure
# (only the separate invalid-JSON retry existed) — the whole criteria
# checklist force-FAILed, and the raw error text (billing upsell copy
# included) leaked into what's supposed to be clinical reasoning notes,
# for a case whose actual evidence was clean and complete. One short,
# fixed backoff before a single retry is enough for exactly that class of
# failure; if the retry also fails, callers fall back exactly as before.
# RateLimitError is still listed here even though the pooled client
# (groq_key_pool.get_pooled_client(), see _get_client() above) already
# rotates to a fresh key and retries internally on a 429 — by the time a
# RateLimitError reaches this except block, every pooled key is already
# exhausted for today, so this retry is a last-resort double-check after
# a short pause, not the primary defense against rate limits.
_TRANSIENT_GROQ_ERRORS = (RateLimitError, APIConnectionError, APITimeoutError, InternalServerError)
_TRANSIENT_RETRY_BACKOFF_SECONDS = 0.75


def _create_with_retry(client, **kwargs):
    try:
        return client.chat.completions.create(**kwargs)
    except _TRANSIENT_GROQ_ERRORS:
        time.sleep(_TRANSIENT_RETRY_BACKOFF_SECONDS)
        return client.chat.completions.create(**kwargs)


SYSTEM_PROMPT = """You are the Clinical Agent for a prior-authorization triage system.

You do not decide whether a request is approved, denied, or sent for review, and you do not look up any patient history database — none exists in this system. Your only inputs are the primary diagnosis, secondary diagnosis, ICD-10 code, and the doctor's free-text clinical justification submitted with this specific request. Your only job: extract the concrete clinical facts the doctor has already asserted in that text, as structured key-value data.

Rules:
- Only extract a fact if the given text states it directly, or makes it directly and unambiguously inferable. Never infer, estimate, guess, or "fill in" a plausible-sounding value that isn't actually grounded in what was written.
- If the text doesn't mention something, do NOT include it in extractedFacts at all. Do not use null, false, 0, or "unknown" as a placeholder value for something simply not mentioned — just omit the key entirely. A missing key is what allows downstream evaluation to correctly treat it as "not established," which is the honest and safe outcome; inventing a value (even a cautious-sounding one) is worse than leaving it out.
- Use clear, conventional keys for each fact (e.g. "bmi", "comorbidities", "smoking_status", "prior_treatment_attempted") — snake_case, specific to what was actually stated, not generic. Numeric facts should be extracted as numbers, not strings. A fact that's a list of items (e.g. comorbidities) should be a JSON array.
- Diagnostic tests, studies, or exams the doctor states were performed (e.g. a sleep study/polysomnography, biopsy, imaging study, lab panel, stress test) are their OWN extractable fact, separate from any numeric finding they produced — extract both that the test was performed and its stated result (e.g. "sleep_study_performed": true, "sleep_study_type": "polysomnography (PSG)", "sleep_study_result": "positive for OSA"), in addition to any specific numeric value mentioned (e.g. "ahi": 28) as its own separate fact. A phrase like "polysomnography-confirmed OSA" or "biopsy-confirmed malignancy" states BOTH that a specific diagnostic test occurred AND that it returned a positive/confirmatory result — do not let it collapse into only the adjacent numeric or descriptive fact. Many coverage criteria specifically require confirmation via a named test, and that requires its own explicit, gradeable fact — not just a modifier folded into a different fact's value.
- For every fact you extract, cite the exact quoted text (or a very close paraphrase) from the clinical justification that supports it, in factSources.
- Do not draw any conclusion about whether these facts satisfy any policy or coverage requirement — you have no visibility into what any policy requires, and it is not your job to reason about that.

Respond with ONLY a single JSON object (no prose, no markdown fences, no explanation outside the JSON) matching exactly this schema:

{
  "extractedFacts": { "<fact_key>": <value> },
  "factSources": [ { "fact": string, "quotedText": string } ],
  "notes": string
}

notes is optional context for a human reviewer (e.g. ambiguous phrasing you deliberately did not extract a fact from) — never a conclusion or recommendation."""


def _is_valid_json(raw):
    try:
        json.loads(raw)
        return True
    except (json.JSONDecodeError, TypeError):
        return False


def _validate_output(raw):
    """
    Never trust raw LLM JSON blindly — same principle as every other
    agent in this project. Falls back to an honest empty extraction (not
    a fabricated fact) for malformed output.
    """
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return _fallback_result("Agent did not return valid JSON.")

    extracted_facts = parsed.get("extractedFacts")
    if not isinstance(extracted_facts, dict):
        extracted_facts = {}

    raw_sources = parsed.get("factSources")
    fact_sources = []
    if isinstance(raw_sources, list):
        for item in raw_sources:
            if not isinstance(item, dict):
                continue
            fact_sources.append({
                "fact": item.get("fact") if isinstance(item.get("fact"), str) else "",
                "quotedText": item.get("quotedText") if isinstance(item.get("quotedText"), str) else "",
            })

    return {
        "extractedFacts": extracted_facts,
        "factSources": fact_sources,
        "notes": parsed.get("notes") if isinstance(parsed.get("notes"), str) else "",
    }


def _fallback_result(reason):
    return {
        "extractedFacts": {},
        "factSources": [],
        "notes": reason,
        "agentError": reason,
    }


def extract_clinical_evidence(primary_diagnosis, secondary_diagnosis=None, icd10_code=None, clinical_justification=None, model=None):
    """
    Single direct Groq call — no tool loop, same as coverage_reasoning_agent.py,
    since this is pure extraction from given text rather than retrieval.
    Never raises for "nothing to extract" (e.g. no justification text given)
    — that's a valid, honest empty result, not an error.
    """
    if not (clinical_justification or "").strip():
        return {
            "extractedFacts": {},
            "factSources": [],
            "notes": "No clinical justification text was provided — nothing to extract from.",
        }

    client = _get_client()
    model = model or os.environ.get("GROQ_AGENT_MODEL", "openai/gpt-oss-120b")

    user_content = (
        f"Primary diagnosis: {primary_diagnosis}\n"
        f"Secondary diagnosis: {secondary_diagnosis or '(none provided)'}\n"
        f"ICD-10 code: {icd10_code or '(none provided)'}\n\n"
        f"Clinical justification (doctor's own words):\n{clinical_justification}"
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    # Whole call wrapped (2026-08-20 — coordinated Groq resilience, see
    # docs/PROGRESS_TRACKER.md §9.9): a raw API failure (rate limit,
    # connection error, etc.) used to propagate uncaught and crash the
    # whole /triage call. Companion Agent and _llm_judge_contraindication
    # already degrade gracefully this way — this brings extraction in
    # line instead of being an odd one out. An empty extraction here is
    # the same honest "nothing confirmed" result this function already
    # returns for "no justification text given" — downstream criteria
    # grading correctly treats it as FAIL, not a fabricated pass.
    try:
        response = _create_with_retry(
            client,
            model=model,
            messages=messages,
            temperature=0.1,
        )
        content = response.choices[0].message.content
        if not _is_valid_json(content):
            # One deterministic retry before falling back to an empty
            # extraction — same fix as item #39 (policy_evidence_agent.py,
            # 2026-08-20), extended here the same day since all three
            # Groq-calling agents in this project shared the identical
            # no-retry gap. A malformed-JSON glitch shouldn't silently degrade
            # a real extraction to nothing.
            retry_response = client.chat.completions.create(model=model, messages=messages, temperature=0)
            content = retry_response.choices[0].message.content
    except Exception as exc:  # noqa: BLE001 - genuine network/API failure, not a validation case
        return _fallback_result(f"Groq API call failed: {exc}")

    return _validate_output(content)


CRITERIA_SYSTEM_PROMPT = """You are the Clinical Agent for a prior-authorization triage system, now evaluating one specific named clinical checklist.

You do not decide whether a request is approved, denied, or sent for review. You are given: (1) a short list of named clinical criteria this policy requires, (2) the policy evidence that produced them, and (3) the concrete facts already extracted from this request's clinical justification. Your only job: for EACH named criterion, decide PASS or FAIL.

Rules:
- PASS only if a specific extracted fact affirmatively satisfies the criterion.
- FAIL otherwise — including when no extracted fact addresses the criterion at all. This checklist has no third status: a criterion nothing was extracted for is FAIL, not "unknown" or "not applicable", even though nothing contradicts it either. This is a deliberate, narrow rule specific to this checklist, not a general assumption that unmentioned things are false.
- Never fabricate a fact that wasn't given to you in the extracted facts.
- Also judge diagnosisSupported: does this request's diagnosis (primary OR secondary, if given) fall within what the policy evidence indicates this policy actually covers? Judge this from the policy evidence and diagnosis alone — it is independent of the criteria checklist.
- You may be given an "indication_match" criterion. If FDA label indications text is provided for it, ground your PASS/FAIL judgment in that text specifically (does the diagnosis fall within the drug's labeled indications?). If instead you're told no FDA label was found (likely a procedure, not a medication), judge it from the diagnosis and policy evidence context alone, using the same FAIL-if-not-demonstrated rule as every other criterion.
- You may be given a "specialty_match" criterion — this happens whenever a fixed reference table couldn't confirm a match (either it doesn't recognize the specialty at all, or it does but didn't happen to list a keyword covering this exact service), so your clinical knowledge is the only way to judge it. A table's failure to confirm a match is NOT evidence against one — do not treat "the table found nothing" as grounds for FAIL by itself. PASS if it's clinically plausible or common for a provider in the given specialty to request this diagnosis/treatment (specialties commonly overlap, and many entirely standard pairings won't share an obvious keyword — be generous, not literal). FAIL only if this specialty is genuinely unusual for this diagnosis/service on real clinical grounds (e.g. a dermatologist requesting a cardiac catheterization). If you cannot form any clear judgment either way, FAIL — the same conservative default used for every other criterion.
- You may be given an "urgency_consistency" criterion — this only happens when the request claims non-routine urgency (Urgent/Emergency). PASS only if the claimed urgency is genuinely consistent with the diagnosis and clinical justification (a true emergent/urgent clinical picture). FAIL if the claimed urgency looks inflated or inconsistent with what's actually described — e.g. "Emergency" claimed for a routine, elective, non-acute request. This is a scrutiny check, not a formality: be skeptical of an urgency claim the clinical narrative doesn't actually support.
- You may be given a "contraindication_check" criterion — this only happens when the extracted patient facts include a notable safety flag (pregnancy, renal/hepatic impairment, pediatric/elderly age, breastfeeding) that this system's small hard-coded contraindication table did not already recognize as a match for the requested drug/treatment. PASS only if you can determine with reasonable clinical confidence that the requested treatment is NOT contraindicated given that patient fact. FAIL if it is a genuine, clinically-recognized contraindication or dangerous combination, OR if you cannot determine with confidence that it's safe — unlike a merely uncertain judgment elsewhere, do not give this one the benefit of the doubt.

Respond with ONLY a single JSON object (no prose, no markdown fences, no explanation outside the JSON) matching exactly this schema:

{
  "diagnosisSupported": boolean,
  "criteriaResults": { "<criterion_name>": "PASS" | "FAIL" },
  "rationale": string
}

criteriaResults must have exactly one entry per criterion name given to you, no more, no fewer, using the exact same criterion name strings you were given as keys. rationale is 1-3 sentences citing the specific facts/evidence used — never a decision or recommendation."""


def _finalize_criteria_result(
    criteria_results, diagnosis_supported, notes, contraindication_details=None, grounded_indication_mismatch=False
):
    total = len(criteria_results)
    passed = sum(1 for status in criteria_results.values() if status == "PASS")
    failed = total - passed
    return {
        "diagnosisSupported": diagnosis_supported,
        "criteriaResults": criteria_results,
        "nClinicalCriteriaTotal": total,
        "nClinicalCriteriaPassed": passed,
        "nClinicalCriteriaFailed": failed,
        # Deterministic — computed here in plain code, not asked of the
        # LLM, same discipline as coverage_reasoning_agent.py's _summarize().
        "clinicalEvidenceScore": round(100 * passed / total, 1) if total > 0 else None,
        "notes": notes,
        # Populated only when the deterministic contraindication table
        # (see contraindication_lookup.py) actually matched — the LLM-graded
        # path's reasoning lives in `notes`/rationale instead, same as every
        # other LLM-graded criterion. Read by coverage_reasoning_agent.py
        # and cited in ml/model.py's safety-gate reason when it fires.
        "contraindicationDetails": contraindication_details or [],
        # True only for a GROUNDED indication_match FAIL (real FDA-label
        # zero-overlap, or a genuine LLM judgment against real policy
        # evidence) — never the policy_invalid fallback's default-FAIL.
        # See evaluate_clinical_criteria's docstring. Read by
        # coverage_reasoning_agent.py's indicationMismatchFlagged gate.
        "groundedIndicationMismatch": grounded_indication_mismatch,
    }


def _resolve_indication_match(requested_service, diagnosis, icd10_code, secondary_diagnosis=None):
    """
    Deterministic ONLY where the FDA label gives a STRONG match (see
    drug_reference_lookup.py) — that's real, grounded confirmation, so no
    LLM call is spent re-deriving it. Anything less certain (weak match,
    no match, or the service isn't in the FDA reference DB at all — most
    procedures) is deferred to the LLM-graded checklist instead, still
    grounded in whatever FDA text is available.

    Checked against BOTH primary and secondary diagnosis (2026-08-19+,
    found via review — secondary_diagnosis was already collected and
    reached extract_clinical_evidence's fact extraction, but this
    function, the one that actually judges indication_match, never saw
    it at all): a drug requested primarily to manage one condition can be
    on-label for a secondary one instead (e.g. requested for pain control,
    but the patient's secondary diagnosis is the drug's actual labeled
    indication) — checking only the primary diagnosis would wrongly grade
    indication_match FAIL, and per the indication-mismatch gate
    (2026-08-19+), a grounded FAIL now hard-gates straight to PEND. Takes
    whichever diagnosis gives the STRONGER match — a real match against
    either is real, grounded confirmation.

    Returns (deterministic_status_or_None, drug_reference_or_None, strength).
    strength is "NONE" when requested_service wasn't given at all.
    """
    if not requested_service:
        return None, None, "NONE"
    drug_reference = find_drug_reference(requested_service)
    strength = indication_match_strength(drug_reference, diagnosis, icd10_code)
    if strength != "STRONG" and secondary_diagnosis:
        secondary_strength = indication_match_strength(drug_reference, secondary_diagnosis)
        # STRONG > WEAK > NONE — take the better of the two, never worse.
        if secondary_strength == "STRONG" or (secondary_strength == "WEAK" and strength == "NONE"):
            strength = secondary_strength
    if strength == "STRONG":
        return "PASS", drug_reference, strength
    return None, drug_reference, strength


def _resolve_contraindication(requested_service, extracted_facts):
    """
    Deterministic ONLY (see contraindication_lookup.py) — a match in the
    small hand-curated table is grounded, high-confidence confirmation of a
    real, established contraindication, so it's trusted outright with no
    LLM call, same "a real match needs no LLM" precedent as
    indication_match's STRONG-match fast path.

    Returns (status_or_None, matches). status is "FAIL" when the table
    matches — never "PASS": this table only ever asserts danger, it has no
    basis to assert safety for combinations it doesn't cover. matches is
    always [] when status is None.
    """
    matches = check_known_contraindications(requested_service, extracted_facts)
    return ("FAIL", matches) if matches else (None, [])


CONTRAINDICATION_SYSTEM_PROMPT = """You are a clinical safety checker for a prior-authorization triage system.

You are given a requested drug/treatment and a specific patient fact that could matter for safety (e.g. pregnancy, renal/hepatic impairment, pediatric/elderly age, breastfeeding). This drug+fact combination is NOT in this system's small hard-coded contraindication table, so your clinical judgment is the only check being run. Judge ONLY whether this specific combination is a genuine, clinically-recognized contraindication or requires significant caution — do not comment on anything else about the request.

Be skeptical: answer contraindicated=true if there is a real, specific, clinically-grounded safety concern, OR if you cannot determine with reasonable confidence that the combination is safe. Do not give this the benefit of the doubt — an uncertain case should route to a human reviewer, not be waved through.

Respond with ONLY a single JSON object (no prose, no markdown fences):
{
  "contraindicated": boolean,
  "reason": string
}
reason is 1-2 sentences citing the specific drug and patient fact and why (or, if not contraindicated, a brief note that none was found). Never fabricate a fact you weren't given."""


def _llm_judge_contraindication(requested_service, diagnosis, extracted_facts, model=None):
    """
    Dedicated, POLICY-INDEPENDENT safety judgment (2026-08-19+, per
    explicit instruction: "what happens with an unseen test case" — the
    hard-coded contraindication_lookup.py table covers ~18 well-established
    combinations; this is what has to catch everything else, via genuine
    clinical reasoning instead of a static list). Only called when
    has_notable_risk_facts() is True and the deterministic table found no
    match — a real notable risk fact exists, so it's worth a dedicated
    Groq call regardless of whether an insurance policy was found for this
    request, unlike indication_match/specialty_match which genuinely do
    depend on policy context. This is the fix for the gap where an
    LLM-deferred contraindication_check used to be silently dropped
    whenever policy_evidence had no policy — a genuinely unseen drug
    (which is exactly the case with NO policy in a narrow corpus) is
    precisely the case this needs to still catch.

    Never raises — a call failure degrades to "no contraindication found"
    (same fail-open-on-infrastructure-failure precedent as every other
    agent's fallback path in this project; the caller's own deterministic
    gates and the ML model's normal scoring still apply on top of this).
    """
    try:
        client = _get_client()
        model = model or os.environ.get("GROQ_AGENT_MODEL", "openai/gpt-oss-120b")
        user_content = (
            f"Requested drug/treatment: {requested_service}\n"
            f"Diagnosis: {diagnosis}\n"
            f"Extracted patient facts: {json.dumps(extracted_facts, indent=2)}"
        )
        messages = [
            {"role": "system", "content": CONTRAINDICATION_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
        response = client.chat.completions.create(model=model, messages=messages, temperature=0.1)
        content = response.choices[0].message.content
        if not _is_valid_json(content):
            # One retry before defaulting to "not contraindicated" — that
            # default is the LESS safe direction for a safety check (a
            # real contraindication would be silently waved through), so a
            # transient JSON glitch shouldn't get to clear one without at
            # least one more attempt.
            retry_response = client.chat.completions.create(model=model, messages=messages, temperature=0)
            content = retry_response.choices[0].message.content
        parsed = json.loads(content)
        contraindicated = bool(parsed.get("contraindicated"))
        reason = parsed.get("reason") if isinstance(parsed.get("reason"), str) else ""
        return contraindicated, reason
    except Exception:  # noqa: BLE001 - genuine network/API/parse failure, not a validation case
        return False, ""


def _resolve_specialty_match(provider_specialty, requested_service):
    """
    Deterministic fast path for a CONFIRMED match only (same keyword map
    as the old rule engine's R501, see specialty_check.py) — a real,
    grounded PASS costs no LLM call. Never resolves a deterministic FAIL
    (changed 2026-08-21, see below) — only PASS or "defer to the LLM".

    Returns None (defer) in what used to be treated as three different
    cases, now unified into one: (a) nothing to judge at all (no specialty
    or no requested service given), (b) "unknown_specialty" — the
    specialty isn't in the reference map at all, a real gap in a
    hand-curated table, or (c) "unusual" — the specialty IS in the map but
    none of its keywords matched this requested service. (c) used to
    return a deterministic FAIL, which turned out to be actively worse
    than being unrecognized: found live (2026-08-21), a Pulmonology
    request for "Low dose CT lung cancer screening" hard-failed
    specialty_match — a textbook-standard ordering specialty for LDCT
    lung screening — purely because pulmonology's keyword list (sleep
    apnea/asthma/COPD terms) had no overlap with this specific service's
    wording, skipping the LLM's more generous clinical judgment entirely.
    A fixed keyword list can confirm a match with high confidence when one
    exists (low false-positive risk), but its ABSENCE proves nothing —
    only that this particular list didn't anticipate this phrasing (high
    false-negative risk, and unlike "unknown", it grows with every
    specialty/service combo nobody thought to add a keyword for). So (b)
    and (c) are now handled identically: both defer to the LLM's real
    clinical judgment (see evaluate_clinical_criteria's llm_criteria
    wiring) instead of letting a table's silence stand in for evidence.
    """
    if not provider_specialty or not requested_service:
        return None
    result = check_provider_specialty(provider_specialty, requested_service)
    if result is None:
        return None
    status = result["status"]
    if status in ("compatible", "general_practice"):
        return "PASS"
    return None  # "unusual" or "unknown_specialty" — both deferred to the LLM


# Recognizes policy-agent-named criteria shaped like "age_50_77" (NCD-
# 210.14's real LDCT eligibility criterion) — used ONLY to decide whether
# patientAge belongs in the Companion Agent's informational_context (see
# age_criterion_was_graded below), NOT to grade PASS/FAIL. An earlier
# version of this fix used this same regex to deterministically resolve
# PASS/FAIL by parsing criterion NAMES — replaced (2026-08-21) because
# that only covers policy phrasing someone thought to hardcode a pattern
# for; see evaluate_clinical_criteria's patient_age handling below for the
# actual fix, which feeds the real fact into the general LLM-graded path
# instead. This regex surviving as a footnote heuristic is lower-stakes:
# worst case a wrong guess mis-labels one explanatory note, not a real
# PASS/FAIL.
_AGE_RANGE_CRITERION_RE = re.compile(r"^age(?:[_\s-]|\d).*?(\d{1,3}).*?(\d{1,3})", re.IGNORECASE)


def age_criterion_was_graded(criteria_results, patient_age):
    """
    True when clinical_criteria_eval's criteriaResults contains at least
    one age-range-shaped criterion name — a heuristic signal that age
    genuinely contributed to
    clinical_evidence_score / the decision this call. Used by main.py to
    decide whether patientAge belongs in the Companion Agent's
    informational_context: same "don't describe a real decision input as
    a non-factor" precedent already applied to urgency/providerSpecialty
    (see TriageRequest.requestContext's docstring in main.py). Found live
    (2026-08-21): right after adding the age resolver above, a request
    whose age_50_77-shaped criterion PASSed and helped drive an APPROVE
    still got told "Patient age 61 — informational only, did not affect
    this decision" in the same explanation that separately named "age"
    among the criteria that passed — a direct, visible contradiction.
    """
    if patient_age is None or not criteria_results:
        return False
    return any(_AGE_RANGE_CRITERION_RE.search(name or "") for name in criteria_results)


# Only a claimed non-routine urgency is worth judging at all — "Routine"
# (or unset) is the unremarkable default, nothing to verify or reward.
NON_ROUTINE_URGENCY_VALUES = {"urgent", "emergency", "emergent", "stat"}


def _fallback_criteria_result(reason, clinical_criteria):
    """
    diagnosisSupported is left as None (genuinely unknown) rather than
    forced to a bool here — collapsing that into the ML model's required
    0/1 is deliberately left to the aggregator (coverage_reasoning_agent.py),
    the one place allowed to apply that last-mile default, so the
    substitution is visible in its own output rather than silently made
    here. criteriaResults IS forced to FAIL per item, per this function's
    own narrow absence-is-FAIL rule (see module docstring) — nothing was
    confirmed, so nothing counts as passed.
    """
    result = _finalize_criteria_result({c: "FAIL" for c in clinical_criteria}, None, reason)
    result["agentError"] = reason
    return result


def _validate_criteria_output(raw, clinical_criteria):
    """
    Never trust raw LLM JSON blindly. Forces exactly one PASS/FAIL entry
    per criterion actually given (ignoring extra keys the model might add,
    defaulting a missing/invalid status to FAIL) — the caller's criteria
    list, not the model's own JSON keys, is the source of truth for which
    criteria exist.
    """
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return _fallback_criteria_result("Agent did not return valid JSON.", clinical_criteria)

    raw_results = parsed.get("criteriaResults")
    raw_results = raw_results if isinstance(raw_results, dict) else {}

    criteria_results = {}
    for criterion in clinical_criteria:
        status = raw_results.get(criterion)
        criteria_results[criterion] = status if status in ("PASS", "FAIL") else "FAIL"

    diagnosis_supported_raw = parsed.get("diagnosisSupported")
    diagnosis_supported = diagnosis_supported_raw if isinstance(diagnosis_supported_raw, bool) else None
    notes = parsed.get("rationale") if isinstance(parsed.get("rationale"), str) else ""

    return _finalize_criteria_result(criteria_results, diagnosis_supported, notes)


def evaluate_clinical_criteria(clinical_criteria, policy_evidence, extracted_facts, diagnosis,
                                requested_service=None, provider_specialty=None, icd10_code=None,
                                urgency=None, secondary_diagnosis=None, patient_age=None, model=None):
    """
    Runs at the fan-in stage, after both Policy Evidence Agent and
    extract_clinical_evidence have completed (see triage_graph.py) — it
    needs Policy Agent's own named clinicalCriteria list as input, which
    is exactly why it can't run in the earlier parallel branch. Never
    raises for "nothing to evaluate against" (no policy found) — that's a
    valid, honest empty/degraded result routed through
    _fallback_criteria_result, same discipline as every other agent's
    short-circuit in this project.

    requested_service / icd10_code: used ONLY to ground indication_match
    against the real drug_references (FDA label) table — see
    drug_reference_lookup.py. A strong FDA-label match resolves
    indication_match deterministically (no LLM call needed for that item);
    otherwise it's added to the LLM-graded checklist, grounded in whatever
    FDA text is available (or diagnosis/policy context alone if the
    service isn't a medication at all, e.g. most procedures). Per explicit
    instruction (2026-08-19), a FAILED indication_match also forces
    diagnosisSupported to False — a treatment whose own confirmed
    indication doesn't cover this diagnosis genuinely undermines whether
    the diagnosis is supported, independent of what the policy text says.

    provider_specialty: grounds specialty_match. Tried deterministically
    first against the same specialty/service keyword map as the old rule
    engine's R501 (see specialty_check.py) — a real match costs no LLM
    call. When that map doesn't recognize the given specialty at all
    ("unknown_specialty"), specialty_match is added to the LLM-graded
    checklist instead of being silently dropped, so an unusual/unrecognized
    specialty still gets a real clinical judgment rather than no signal at
    all (per explicit instruction, 2026-08-19). Unlike indication_match, a
    FAILED specialty_match does NOT affect diagnosisSupported — a
    mismatched requesting specialty says nothing about whether the
    diagnosis itself is valid; it only lowers clinicalEvidenceScore as its
    own checklist item.

    urgency: grounds urgency_consistency, added to the LLM checklist ONLY
    when a non-routine urgency is actually claimed (see
    NON_ROUTINE_URGENCY_VALUES) — "give more importance to TRUE urgent
    cases" (per explicit instruction) means a genuine, clinically-plausible
    urgent/emergent claim earns a real PASS on the checklist, raising
    clinicalEvidenceScore like any other criterion, rather than urgency
    sitting outside scoring as pure metadata. The inverse also matters: an
    inflated/inconsistent urgency claim ("fishy") FAILs this criterion,
    which coverage_reasoning_agent.py additionally treats as a hard gate
    (urgencyFlagged) — routed straight to PEND for nurse review, same
    "don't let a suspicious signal just dilute into a score" precedent as
    missingRequiredEvidence. A claimed Routine urgency (or none at all)
    adds no criterion at all — nothing to verify or reward there.

    patient_age: merged into extracted_facts (as "patient_age") before any
    grading happens, added 2026-08-21 after live testing showed a real
    61-year-old FAILing NCD-210.14's age_50_77 criterion with "age not
    documented" purely because this value was previously wired as
    informational-only (see companion_agent.py) and never reached criteria
    grading at all — extract_clinical_evidence() only parses the doctor's
    free-text justification, which had no reason to restate an age nobody
    asked for. Deliberately NOT a deterministic resolver keyed off
    criterion NAME patterns (a same-day earlier version of this fix
    matched e.g. "age_50_77" via regex, replaced for being exactly the
    kind of narrow hardcoding this project is trying to move away from) —
    feeding the real fact into the general LLM-graded checklist instead
    covers any age-shaped criterion in any policy's own wording, the same
    way pack-years/smoking-status/every other fact-grounded criterion
    already works, with no bespoke per-criterion code to maintain.

    Contraindication safety gate (2026-08-19+): grounds contraindication_check,
    resolved BEFORE the policy_invalid short-circuit below (unlike
    indication_match/specialty_match's LLM-deferred forms, which the
    policy_invalid path force-FAILs) — a known-dangerous drug/patient-state
    combination must gate the request regardless of whether a policy was
    even found. First tried deterministically against a small hand-curated
    table (contraindication_lookup.py) — a real match is trusted outright,
    no LLM call needed. When the table has no entry but the extracted facts
    still contain a notable safety flag (pregnancy, renal/hepatic
    impairment, pediatric/elderly age, breastfeeding — see
    has_notable_risk_facts()), the judgment is deferred to the LLM instead
    of silently treating the request as cleared — genuinely POLICY-
    INDEPENDENT (2026-08-19+, later revision): when a policy WAS found, this
    rides along with the normal criteria-grading LLM call below; when no
    policy was found, it gets its OWN dedicated call via
    _llm_judge_contraindication instead of being silently dropped — a
    genuinely unseen drug (not in either the hardcoded table or this
    corpus's policies) is exactly the case that most needs a real judgment,
    not the case to skip one. Never forced to FAIL just because no policy
    exists — that would flood PEND with false positives on every routine
    request that merely mentions "pregnant"; only an actual LLM verdict of
    "contraindicated" fails it. A FAILED contraindication_check does NOT
    affect diagnosisSupported (same precedent as specialty_match) — it is a
    pure safety gate, surfaced via coverage_reasoning_agent.py's
    contraindicationFlagged, consumed by
    ml/model.py before the ML model ever runs.

    Indication-mismatch safety gate (2026-08-19+, added after live testing
    reproduced it 3 times — semaglutide for allergic rhinitis, gene therapy
    against a policy that only covers allogeneic HSCT for sickle cell
    disease — both auto-APPROVED around 0.50 probability, just over the
    0.426 threshold): the ML model's 4 features blend indication_match's
    signal into diagnosis_supported (one bit) and clinical_evidence_score
    (a percentage), both of which a strong policy_score/documentation_score
    can outweigh. A GROUNDED indication_match FAIL — never a default — now
    hard-gates to PEND the same way contraindication_check does, surfaced
    as groundedIndicationMismatch below. "Grounded" is deliberately narrow,
    to avoid flooding PEND with corpus-coverage gaps (most drugs simply
    aren't in this project's small FDA reference table or policy corpus,
    and that absence alone must NOT read as evidence of mismatch): it only
    fires when (a) a real FDA label WAS found and shares zero diagnosis
    keyword overlap (indication_match_strength "NONE", not just "WEAK" —
    same STRONG-needs-no-LLM precedent, just the negative direction), or
    (b) the LLM was actually invoked (a policy was found) and it judged
    indication_match FAIL from real retrieved evidence. It deliberately
    does NOT fire on the policy_invalid fallback's default-FAIL bucket
    below — a request with no matching policy AND no FDA reference has no
    grounded evidence of mismatch, only an absence of evidence for either
    verdict, so gating it would punish corpus gaps, not real mismatches.
    """
    extracted_facts = dict(extracted_facts or {})
    clinical_criteria = list(clinical_criteria or [])
    policy_evidence = policy_evidence or {}

    # Real, structured patient age (Authorization.patient.age ->
    # requestContext.patient_age), merged into the SAME free-form fact
    # dict extract_clinical_evidence() populates from free text —
    # "patient_age" is exactly the key name contraindication_lookup.py's
    # _looks_like_age_field already recognizes, so this also strengthens
    # the pediatric/elderly contraindication safety check below, for free.
    # Deliberately NOT a bespoke deterministic PASS/FAIL resolver keyed off
    # criterion NAME patterns (an earlier version of this fix matched e.g.
    # "age_50_77" via regex) — that only covers policy phrasing someone
    # thought to anticipate. Feeding the real fact into the SAME general-
    # purpose LLM grading path every other criterion already goes through
    # (see CRITERIA_SYSTEM_PROMPT's "PASS only if a specific extracted
    # fact affirmatively satisfies the criterion" rule) covers any
    # age-shaped criterion in any policy's own wording, with no per-case
    # name-matching rule to maintain. Never overwrites a value
    # extract_clinical_evidence already pulled from the free text itself.
    if patient_age is not None:
        try:
            extracted_facts.setdefault("patient_age", int(patient_age))
        except (TypeError, ValueError):
            pass

    indication_status, drug_reference, indication_strength = _resolve_indication_match(
        requested_service, diagnosis, icd10_code, secondary_diagnosis
    )
    specialty_status = _resolve_specialty_match(provider_specialty, requested_service)
    contraindication_status, contraindication_matches = _resolve_contraindication(requested_service, extracted_facts)

    deterministic_results = {}
    det_notes = []
    llm_criteria = list(clinical_criteria)
    # Set True only by a GROUNDED indication_match FAIL — see docstring's
    # "Indication-mismatch safety gate" section for exactly what counts.
    grounded_indication_mismatch = False

    if requested_service:
        if indication_status == "PASS":
            deterministic_results["indication_match"] = "PASS"
            det_notes.append(f"indication_match: PASS (strong FDA-label match for '{requested_service}').")
        elif indication_strength == "NONE" and drug_reference is not None:
            # A real FDA label exists for this drug and shares ZERO
            # diagnosis-keyword overlap — grounded, high-confidence
            # evidence of mismatch, trusted outright like the STRONG-match
            # PASS case above (no LLM needed), just the opposite verdict.
            deterministic_results["indication_match"] = "FAIL"
            grounded_indication_mismatch = True
            det_notes.append(
                f"indication_match: FAIL (FDA label for '{requested_service}' shares no overlap with diagnosis '{diagnosis}')."
            )
        else:
            llm_criteria.append("indication_match")

    if specialty_status is not None:
        deterministic_results["specialty_match"] = specialty_status
        det_notes.append(
            f"specialty_match: {specialty_status} (provider specialty '{provider_specialty}' "
            f"vs. requested service '{requested_service}')."
        )
    elif provider_specialty and requested_service:
        # Both inputs are present but _resolve_specialty_match couldn't
        # confirm a PASS — either the specialty isn't in the reference
        # table at all, or it is but no keyword matched this service (see
        # that function's docstring for why the latter is deliberately NOT
        # trusted as a deterministic FAIL). Either way, defer to the LLM's
        # real clinical judgment rather than a table's silence.
        llm_criteria.append("specialty_match")

    if (urgency or "").strip().lower() in NON_ROUTINE_URGENCY_VALUES:
        llm_criteria.append("urgency_consistency")

    if contraindication_status == "FAIL":
        deterministic_results["contraindication_check"] = "FAIL"
        det_notes.append(
            "contraindication_check: FAIL — " + "; ".join(m["reason"] for m in contraindication_matches)
        )
    elif requested_service and has_notable_risk_facts(extracted_facts):
        llm_criteria.append("contraindication_check")

    policy_invalid = bool(policy_evidence.get("agentError")) or not policy_evidence.get("policyFound")

    if policy_invalid:
        # No policy context to check the POLICY-derived criteria or an
        # unconfirmed indication_match against — same absence-is-FAIL
        # discipline as before. Deterministic results (which don't depend
        # on policy evidence at all) are still merged in rather than
        # discarded just because retrieval failed — this is what lets the
        # contraindication table's own FAIL survive even when no policy was
        # found (see evaluate_clinical_criteria's docstring). An LLM-deferred
        # contraindication_check is the one exception left OUT of the plain
        # force-FAIL bucket below: force-failing every request that merely
        # mentions a risk keyword (e.g. "pregnant") with no confirmed danger
        # would flood PEND with false positives the table was never
        # confident about to begin with — instead it gets its OWN dedicated,
        # policy-independent LLM judgment (see _llm_judge_contraindication),
        # since a genuinely unseen drug is exactly the case with no policy
        # in this narrow corpus, and that's precisely the case a real
        # safety net has to still cover.
        fallback_llm_criteria = [c for c in llm_criteria if c != "contraindication_check"]
        criteria_results = {c: "FAIL" for c in fallback_llm_criteria}
        criteria_results.update(deterministic_results)

        if "contraindication_check" in llm_criteria:
            contraindicated, llm_reason = _llm_judge_contraindication(requested_service, diagnosis, extracted_facts)
            if contraindicated:
                criteria_results["contraindication_check"] = "FAIL"
                reason_text = llm_reason or "LLM judged a clinically-recognized contraindication."
                contraindication_matches = contraindication_matches + [{
                    "drugMatched": requested_service, "factMatched": None,
                    "severity": "LLM_JUDGED", "reason": reason_text,
                }]
                det_notes.append(f"contraindication_check: FAIL (LLM, no policy) — {reason_text}")
            else:
                criteria_results["contraindication_check"] = "PASS"

        diagnosis_supported = False if criteria_results.get("indication_match") == "FAIL" else None
        reason = "Not evaluated: upstream policy evidence agent reported an error or found no policy to check against."
        notes = reason + (" " + " ".join(det_notes) if det_notes else "")
        result = _finalize_criteria_result(
            criteria_results, diagnosis_supported, notes, contraindication_matches, grounded_indication_mismatch
        )
        result["agentError"] = reason
        return result

    client = _get_client()
    model = model or os.environ.get("GROQ_AGENT_MODEL", "openai/gpt-oss-120b")

    fda_context = ""
    if "indication_match" in llm_criteria:
        if drug_reference:
            fda_context = (
                f"\n\nFDA label indications text for '{requested_service}' "
                f"(generic: {drug_reference.get('genericName')}, brand: {drug_reference.get('brandName')}):\n"
                f"{(drug_reference.get('indications') or '')[:1500]}"
            )
        else:
            fda_context = (
                f"\n\nNo FDA drug label found for '{requested_service}' — it is likely a procedure, not a "
                f"medication, or simply not in the reference database. Judge indication_match from the "
                f"diagnosis and policy evidence context alone."
            )

    specialty_context = ""
    if "specialty_match" in llm_criteria:
        specialty_context = (
            f"\n\nProvider specialty: {provider_specialty}\n"
            f"Requested service/treatment: {requested_service}\n"
            f"A fixed reference table could not confirm this as a match (either the specialty isn't "
            f"in it at all, or it is but didn't happen to list a keyword for this exact service), so "
            f"judge specialty_match from your own clinical knowledge — is it plausible/common for a "
            f"provider in this specialty to be requesting this diagnosis/treatment? A table's failure "
            f"to confirm a match is not evidence against one — many entirely standard specialty/"
            f"service pairings won't literally share a keyword."
        )

    urgency_context = ""
    if "urgency_consistency" in llm_criteria:
        urgency_context = (
            f"\n\nClaimed urgency: {urgency}\n"
            f"Judge urgency_consistency from your clinical knowledge: is this urgency level "
            f"genuinely consistent with the diagnosis and clinical justification given? Be "
            f"skeptical — PASS only for a claim the clinical picture actually supports, FAIL if "
            f"it looks inflated or inconsistent (e.g. 'Emergency' for a routine, non-acute request)."
        )

    contraindication_context = ""
    if "contraindication_check" in llm_criteria:
        contraindication_context = (
            f"\n\nThe extracted patient facts include at least one notable safety flag "
            f"(pregnancy, renal/hepatic impairment, pediatric/elderly age, or breastfeeding) "
            f"that this system's small hard-coded contraindication table did not already "
            f"recognize as a match for '{requested_service}'. Judge contraindication_check from "
            f"your clinical knowledge: is this treatment a genuine, clinically-recognized "
            f"contraindication or dangerous combination given these specific patient facts? Be "
            f"skeptical — FAIL if it is a real concern, OR if you cannot determine with "
            f"reasonable confidence that it's safe (do not give this one the benefit of the doubt)."
        )

    user_content = (
        f"Diagnosis: {diagnosis}\n"
        f"Secondary diagnosis: {secondary_diagnosis or '(none provided)'}\n\n"
        f"Named clinical criteria to evaluate (evaluate ALL of these, nothing else):\n"
        f"{json.dumps(llm_criteria, indent=2)}\n\n"
        f"Policy evidence this checklist came from:\n{json.dumps(policy_evidence, indent=2)}\n\n"
        f"Facts already extracted from this request's clinical justification:\n{json.dumps(extracted_facts, indent=2)}"
        f"{fda_context}"
        f"{specialty_context}"
        f"{urgency_context}"
        f"{contraindication_context}"
    )

    messages = [
        {"role": "system", "content": CRITERIA_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    # Whole call wrapped (2026-08-20 — coordinated Groq resilience, see
    # docs/PROGRESS_TRACKER.md §9.9): a raw API failure used to propagate
    # uncaught and crash the whole /triage call. Falls back to the SAME
    # shape _validate_criteria_output's own invalid-JSON path already
    # produces (llm_criteria all FAIL, deterministic_results still merged
    # in below) — a Groq outage degrades this checklist the same honest
    # way a malformed response already does, not a new failure mode.
    try:
        response = _create_with_retry(
            client,
            model=model,
            messages=messages,
            temperature=0.1,
        )
        content = response.choices[0].message.content
        if not _is_valid_json(content):
            # Same one-retry fix as extract_clinical_evidence() above — a
            # malformed-JSON glitch here would otherwise force-FAIL every
            # criterion via _fallback_criteria_result, for a reason unrelated
            # to actual clinical evidence.
            retry_response = client.chat.completions.create(model=model, messages=messages, temperature=0)
            content = retry_response.choices[0].message.content
        llm_result = _validate_criteria_output(content, llm_criteria)
    except Exception as exc:  # noqa: BLE001 - genuine network/API failure, not a validation case
        llm_result = _fallback_criteria_result(f"Groq API call failed: {exc}", llm_criteria)

    criteria_results = dict(llm_result["criteriaResults"])
    criteria_results.update(deterministic_results)

    diagnosis_supported = llm_result["diagnosisSupported"]
    if criteria_results.get("indication_match") == "FAIL":
        diagnosis_supported = False
        if "indication_match" in llm_criteria:
            # The LLM was genuinely asked (policy evidence was found and
            # shown to it) and judged FAIL from real retrieved evidence —
            # grounded, same as the deterministic NONE-strength case above.
            grounded_indication_mismatch = True

    notes = llm_result["notes"]
    if det_notes:
        notes = (notes + " " if notes else "") + " ".join(det_notes)

    return _finalize_criteria_result(
        criteria_results, diagnosis_supported, notes, contraindication_matches, grounded_indication_mismatch
    )
