"""
Policy Evidence Agent
=======================

The first real agent in this system, and the reference implementation for
every agent that follows it: genuine Groq tool-calling (tools/tool_choice/
tool_calls, a real execute-and-respond loop), not text parsing pretending
to be tool use. Uses a SEPARATE Groq API key (GROQ_AGENT_API_KEY) from the
Node backend's rule-engine ambiguity resolution (GROQ_API_KEY), so agent
workloads don't compete with that for rate limit.

Role: identify whether a policy applies to a requested service, and if so,
extract its coverage criteria — grounded ONLY in what
retrieve_policy_evidence() actually returns. The agent has no built-in
policy knowledge and is explicitly instructed not to substitute its own
medical knowledge when the tool finds nothing.

Policy-type scoping is DETERMINISTIC, not something the LLM is trusted to
decide: the caller resolves the patient's actual insurance plan to a payer
(get_plan_payer()) and that payer is hard-injected into every tool call
this agent makes — the LLM's tool schema doesn't even expose a payer
parameter, so it has no way to search outside the patient's own plan's
policies. Without this, a Commercial-plan patient's request could
silently retrieve a Medicare policy that was never actually theirs to
begin with — this was a real bug, found and fixed, not a hypothetical.

Loop (per the project's tool-calling spec):
  1. Send messages + tool definitions to Groq (tool_choice="auto")
  2. Groq returns tool_calls
  3. Parse tool name + arguments
  4. Execute the local tool (retrieve_policy_evidence)
  5. Append the assistant tool-call message
  6. Append a role="tool" result, keyed to the tool_call_id
  7. Send the updated messages back to Groq
  8. Repeat while more tool_calls are requested
  9. Stop once Groq returns a final response with no tool_calls
  Bounded at MAX_ITERATIONS — never an unbounded loop.

Usage:
    from agents.policy_evidence_agent import evaluate_policy_evidence
    result = evaluate_policy_evidence(
        requested_service="CPAP therapy",
        diagnosis="obstructive sleep apnea",
    )
"""
import json
import os

from dotenv import load_dotenv

from groq_key_pool import get_pooled_client
from rag.retrieval import get_plan_payer, retrieve_policy_evidence

load_dotenv()

MAX_ITERATIONS = 5


def _get_client():
    return get_pooled_client()


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "retrieve_policy_evidence",
            "description": (
                "Search the Medicare policy knowledge base (National Coverage "
                "Determinations, ingested from the real CMS Coverage API) for "
                "coverage criteria relevant to a specific medical service, "
                "procedure, or drug and the diagnosis it's being requested for. "
                "Confidence-gated: when nothing in the corpus genuinely covers "
                "the topic, the result says so explicitly rather than returning "
                "a weak, misleading match."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Natural-language description combining the requested "
                            "service/procedure/drug and the diagnosis, e.g. "
                            "'CPAP therapy for obstructive sleep apnea' or "
                            "'bariatric surgery for morbid obesity with type 2 diabetes'."
                        ),
                    }
                },
                "required": ["query"],
            },
        },
    }
]

SYSTEM_PROMPT = """You are the Policy Evidence Agent for a prior-authorization triage system.

Your job: identify whether a policy applies to the requested service, and if one does, extract its coverage criteria.

You have NO built-in knowledge of specific coverage policy. You MUST call the retrieve_policy_evidence tool to search the actual policy knowledge base before answering. Never state a coverage criterion, threshold, or requirement that did not come from a tool result — that is fabrication, and this system exists specifically to avoid it.

IMPORTANT: the tool is automatically scoped to the patient's own insurance payer before it ever reaches you — you are only ever shown evidence from policies that actually apply to this patient's plan. You do not choose or control this scope, and you should never assume evidence from a different payer would apply just because none was found for this one.

Rules:
- Call retrieve_policy_evidence at least once. Do not answer from memory.
- If the tool returns policyFound: false, you MUST report policyFound: false in your final answer. Do not substitute your own general medical knowledge as if it were a policy citation — a plausible-sounding guess is worse than admitting no evidence was found.
- If the tool returns policyFound: true, you MUST report policyFound: true in your final answer too, at the SAME confidence level the tool returned. That decision is already made deterministically, from real semantic distance to the actual retrieved text — it is not yours to re-judge or second-guess, even if the evidence feels thin, generic, or not 100% certain to you. Your job at that point is only to extract the real policyId, policyName, coverageStatus, criteria, clinicalCriteria, and requiredDocuments from the evidence text the tool already gave you — not to independently decide whether the match counts.
- Call the tool once per distinct question. Do not repeatedly retry the same query hoping for a different result.
- Once you have the tool result, respond with ONLY a single JSON object (no prose, no markdown fences, no explanation outside the JSON) matching exactly this schema:

{
  "policyFound": boolean,
  "policyId": string or null,
  "policyName": string or null,
  "coverageStatus": "COVERED" | "CONDITIONAL" | "NOT_COVERED" | "UNKNOWN",
  "criteria": [ { "criterion": string, "source": string } ],
  "evidence": [ { "text": string, "source": string } ],
  "missingPolicyInformation": [ string ],
  "confidence": "HIGH" | "MEDIUM" | "LOW" | "NONE",
  "clinicalCriteria": [ string ],
  "requiredDocuments": [ string ]
}

coverageStatus meanings: COVERED = evidence describes indications that are met or a straightforward covered service; CONDITIONAL = covered only if specific criteria are satisfied (summarize them in criteria); NOT_COVERED = evidence explicitly excludes this; UNKNOWN = policyFound is false, or the evidence doesn't resolve to a clear status.

clinicalCriteria: 2-4 short snake_case names for the distinct clinical checklist items the evidence actually specifies (e.g. "bmi_threshold_met", "conservative_treatment_documented") — a condensed, named version of the same requirements already described in criteria, meant to be evaluated one-by-one downstream. Only name items genuinely grounded in the retrieved evidence. Return fewer than 4, or an empty list, when the evidence doesn't clearly break down into that many distinct checkable items — never pad to reach a target count.

Some policies split coverage into an INITIAL/first-time period and CONTINUED coverage after that period (e.g. "initially covered for 12 weeks to identify beneficiaries who benefit; subsequently covered only for those who benefited during that period"). Judge from the requested service and diagnosis you were given whether this specific request reads as a first-time/initial/new request (wording like "setup", "initial", "new prescription", or simply no indication of any prior therapy) versus a continuation/renewal/re-evaluation of therapy already underway. If it is a first-time request, do NOT name a clinicalCriteria item that can only be satisfied by evidence from a period of therapy that hasn't happened yet (a benefit-demonstration, adherence, or re-evaluation requirement that the policy text itself frames as applying to continued/renewed coverage) — that evidence cannot exist yet for a first-time request, and naming it as a checklist item would fail a well-documented initial request on a technicality it has no way to satisfy. Only include the criteria that actually govern the stage of care this specific request is at; still name the criteria that DO genuinely apply to an initial request (e.g. a diagnostic threshold, a positive confirming test) exactly as before.

requiredDocuments: 2-4 short human-readable names of the specific documents/records the evidence says must be submitted to support this request (e.g. "6-month physician-supervised weight management program records"). Same grounding rule as clinicalCriteria — an empty list is correct and expected when the evidence doesn't specify documentation requirements."""


def _execute_tool_call(tool_call, payer, last_result_holder):
    args = json.loads(tool_call.function.arguments)
    # payer is never taken from the LLM's tool arguments — the tool schema
    # doesn't even offer it as a parameter. It's injected here from the
    # patient's actual resolved plan, deterministically, every call.
    #
    # Two-stage retrieval (2026-08-20+ — see rag/retrieval.py's
    # STAGE1_MAX_CANDIDATE_POLICIES comment for the full history, including
    # the SUPERSEDED single flat top_k=16 this replaces): a single global
    # cap on the whole payer-group union let one large, genuinely-relevant
    # policy crowd out most of its OWN branches (confirmed live: Aetna's
    # 46-chunk knee-arthroplasty policy alone filled 11 of 16 slots for a
    # realistic query, leaving ~35 of its own real criteria unreachable).
    # retrieve_policy_evidence() now finds the right FEW policies first,
    # then pulls deeply from just those — defaults (no override needed
    # here) scale cost with what THIS query actually needs rather than
    # paying a flat token cost on every call, including the common
    # single-small-policy case that was never broken.
    result = retrieve_policy_evidence(args["query"], payer=payer)
    # Stashed so the caller can derive relevanceScore straight from the raw
    # cosine distance after the loop ends — deterministically, not by
    # asking the LLM to echo a number back (same "don't trust the LLM with
    # a value that's already computable" discipline as every other
    # deterministic figure in this project).
    last_result_holder["result"] = result
    return json.dumps(result)


def _relevance_score_from(last_result_holder):
    """
    evidence is already ORDER BY distance ASC (see retrieve_policy_evidence's
    SQL), so evidence[0] is the single best match found. 1 - distance turns
    "lower is better" cosine distance into a 0-1 "higher is better" score,
    matching the slide's "RAG relevance score (0-1)" framing.
    """
    evidence = (last_result_holder.get("result") or {}).get("evidence") or []
    if not evidence:
        return None
    return round(1 - evidence[0]["distance"], 3)


def _is_valid_json(raw):
    try:
        json.loads(raw)
        return True
    except (json.JSONDecodeError, TypeError):
        return False


def _validate_output(raw):
    """
    Never trust raw LLM JSON blindly — same principle as groqService.js's
    validation on the Node side. Falls back to an honest UNKNOWN/NONE
    result rather than propagating malformed or out-of-schema output.
    """
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return _fallback_result("Agent did not return valid JSON.")

    allowed_coverage_status = {"COVERED", "CONDITIONAL", "NOT_COVERED", "UNKNOWN"}
    allowed_confidence = {"HIGH", "MEDIUM", "LOW", "NONE"}

    def _string_list(value):
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, str)]

    return {
        "policyFound": bool(parsed.get("policyFound", False)),
        "policyId": parsed.get("policyId") if isinstance(parsed.get("policyId"), str) else None,
        "policyName": parsed.get("policyName") if isinstance(parsed.get("policyName"), str) else None,
        "coverageStatus": parsed.get("coverageStatus") if parsed.get("coverageStatus") in allowed_coverage_status else "UNKNOWN",
        "criteria": parsed.get("criteria") if isinstance(parsed.get("criteria"), list) else [],
        "evidence": parsed.get("evidence") if isinstance(parsed.get("evidence"), list) else [],
        "missingPolicyInformation": parsed.get("missingPolicyInformation") if isinstance(parsed.get("missingPolicyInformation"), list) else [],
        "confidence": parsed.get("confidence") if parsed.get("confidence") in allowed_confidence else "NONE",
        "clinicalCriteria": _string_list(parsed.get("clinicalCriteria")),
        "requiredDocuments": _string_list(parsed.get("requiredDocuments")),
    }


def _fallback_result(reason):
    return {
        "policyFound": False,
        "policyId": None,
        "policyName": None,
        "coverageStatus": "UNKNOWN",
        "criteria": [],
        "evidence": [],
        "missingPolicyInformation": [],
        "confidence": "NONE",
        "clinicalCriteria": [],
        "requiredDocuments": [],
        "relevanceScore": None,
        "agentError": reason,
    }


def evaluate_policy_evidence(requested_service, diagnosis, plan_id=None, model=None):
    """
    Runs the full tool-calling loop and returns a validated, structured
    result. Never raises for a "no policy found" outcome — that's a valid,
    honest result, not an error. Raises only for actual failures (bad API
    key, network error, exhausted iterations without a final answer).

    plan_id: the patient's insurance_plans.planId (e.g. "PLAN001"). Resolved
    to a payer BEFORE any Groq call, and that payer is hard-scoped into
    every retrieval the agent makes — see the module docstring for why this
    can't be left to the LLM. If plan_id doesn't resolve to a known plan,
    this deliberately does NOT fall back to an unscoped search across every
    payer's policies (that would defeat the entire point) — it returns an
    honest "can't determine applicable payer" result instead, without even
    spending a Groq call on it.
    """
    last_tool_result = {}

    payer = None
    if plan_id:
        payer = get_plan_payer(plan_id)
        if payer is None:
            return {
                **_fallback_result(f"Insurance plan '{plan_id}' was not found — cannot determine which payer's policies apply."),
                "planId": plan_id,
                "payerScope": None,
            }

    client = _get_client()
    model = model or os.environ.get("GROQ_AGENT_MODEL", "openai/gpt-oss-120b")

    # payer is a list for a consolidated Private-tier plan (get_plan_payer
    # expands the "Private" sentinel to PRIVATE_PAYER_GROUP) — the LLM is
    # never shown WHY it's a list, just the scope, same "deterministic,
    # not the LLM's call" discipline either way.
    payer_display = ", ".join(payer) if isinstance(payer, (list, tuple)) else payer
    plan_context = f"\nPatient's insurance payer (evidence is scoped to this payer only): {payer_display}" if payer else ""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Requested service/procedure/drug: {requested_service}\nDiagnosis: {diagnosis}{plan_context}",
        },
    ]

    tool_already_called = False

    # Whole loop wrapped (2026-08-20 — coordinated Groq resilience, see
    # docs/PROGRESS_TRACKER.md §9.9): a raw Groq API failure (rate limit,
    # connection error, transient 5xx — the SDK's own built-in retries
    # already handle short-lived cases; this catches what's left after
    # those are exhausted) used to propagate straight out of this
    # function, out of the LangGraph node, and crash the whole /triage
    # call as an unhandled 500. Companion Agent and
    # _llm_judge_contraindication already degrade gracefully this way;
    # this brings Policy Agent in line with that same pattern instead of
    # being the odd one out. Degrading here — same _fallback_result shape
    # as an invalid-JSON or "no policy found" result — means the request
    # still gets a real, explained decision (the existing policyNotFound
    # gate fires exactly as it does for any other missing-policy case),
    # not a crash. Never masks a REAL negative result: only an actual
    # exception from the API call itself lands here, never a valid
    # {"policyFound": false, ...} response.
    try:
        for _ in range(MAX_ITERATIONS):
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=TOOLS,
                # Forced to "none" once the real tool has already run — some
                # models, when instructed to output JSON while tools are still
                # offered, try to emit the final answer AS a tool call (e.g. a
                # phantom "JSON" function that isn't in TOOLS), which the API
                # rejects. This agent only ever needs one retrieval round, so
                # forcing plain content on the follow-up turn is correct here,
                # not just a workaround.
                tool_choice="auto" if not tool_already_called else "none",
                temperature=0.1,
            )
            message = response.choices[0].message

            if not message.tool_calls:
                content = message.content
                if not _is_valid_json(content):
                    # One deterministic retry before falling back to "no policy
                    # found" (item #39, found live 2026-08-20 — see
                    # docs/PROGRESS_TRACKER.md §9.5): Groq occasionally returns
                    # malformed JSON on the first attempt, and without a retry
                    # that single glitch was indistinguishable from a genuine
                    # negative result — a real, applicable policy (Aetna PT,
                    # CPB 0325) got reported as not found for a reason that had
                    # nothing to do with actual coverage. Same messages,
                    # temperature=0 for the retry (more deterministic than the
                    # original 0.1). Never retries a real result: a
                    # syntactically valid {"policyFound": false, ...} response
                    # is not "invalid JSON" and returns immediately above.
                    retry_response = client.chat.completions.create(
                        model=model,
                        messages=messages,
                        tools=TOOLS,
                        tool_choice="none",
                        temperature=0,
                    )
                    content = retry_response.choices[0].message.content

                parsed = _validate_output(content)
                tool_result = last_tool_result.get("result") or {}
                tool_policy_found = bool(tool_result.get("policyFound"))

                # Found live (2026-08-21): a literal, unambiguous match — the
                # tool's top evidence chunk was NCD-240.1's own "Item/Service
                # Description" defining Lung Volume Reduction Surgery, for a
                # direct LVRS request, at MEDIUM confidence — still got
                # reported as policyFound: false in the LLM's final answer.
                # retrieve_policy_evidence() already makes this decision
                # deterministically from real cosine distance (see its own
                # HIGH/MEDIUM/LOW gating) — it is not the LLM's to re-judge,
                # per the system prompt's rule above. When the LLM's answer
                # contradicts what its own tool call actually returned, give
                # it ONE corrective retry — explicitly telling it the tool
                # already confirmed a match — so it gets a real chance to
                # extract real criteria from real evidence instead of
                # silently discarding it. Same "one more chance before
                # falling back" precedent as the invalid-JSON retry above.
                if tool_policy_found and not parsed["policyFound"]:
                    correction = (
                        f"Your answer reported policyFound: false, but the retrieve_policy_evidence "
                        f"tool you called actually returned policyFound: true at "
                        f"{tool_result.get('confidence')} confidence. That confidence decision is "
                        f"already made deterministically from real semantic distance and is not "
                        f"yours to override — re-read the evidence already returned above and answer "
                        f"again with policyFound: true, extracting the real policyId, policyName, "
                        f"coverageStatus, criteria, clinicalCriteria, and requiredDocuments from it."
                    )
                    messages.append({"role": "assistant", "content": content})
                    messages.append({"role": "user", "content": correction})
                    try:
                        retry_response = client.chat.completions.create(
                            model=model,
                            messages=messages,
                            tools=TOOLS,
                            tool_choice="none",
                            temperature=0,
                        )
                        retry_content = retry_response.choices[0].message.content
                        if _is_valid_json(retry_content):
                            parsed = _validate_output(retry_content)
                    except Exception:  # noqa: BLE001 - genuine API failure, not a validation case
                        # The corrective retry re-sends the full evidence
                        # payload plus the correction message, which can push
                        # a request over a constrained account's per-request
                        # token cap (found live 2026-08-21: a real 413 "request
                        # too large" on an 8000 TPM tier). That failure must
                        # NOT propagate to the outer handler's pessimistic
                        # _fallback_result, which would silently discard the
                        # tool_policy_found=True fact already confirmed above
                        # — keep the original (uncorrected) extraction; the
                        # hard backstop below still forces policyFound/
                        # confidence correctly either way.
                        pass

                # policyFound/confidence are never left to the LLM's final
                # say either way, regardless of the retry's outcome — same
                # "don't trust the LLM with a value that's already
                # deterministically computable" discipline as
                # relevanceScore below. This is a hard backstop: even if the
                # LLM stubbornly repeats a contradicting answer, the tool's
                # own real result wins.
                parsed["policyFound"] = tool_policy_found
                if tool_result.get("confidence"):
                    parsed["confidence"] = tool_result["confidence"]

                return {
                    **parsed,
                    "relevanceScore": _relevance_score_from(last_tool_result),
                    "planId": plan_id,
                    "payerScope": payer,
                }

            messages.append(
                {
                    "role": "assistant",
                    "content": message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in message.tool_calls
                    ],
                }
            )

            for tool_call in message.tool_calls:
                if tool_call.function.name != "retrieve_policy_evidence":
                    tool_result = json.dumps({"error": f"Unknown tool: {tool_call.function.name}"})
                else:
                    tool_result = _execute_tool_call(tool_call, payer, last_tool_result)
                messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": tool_result})

            tool_already_called = True

        return {
            **_fallback_result(f"Exceeded {MAX_ITERATIONS} tool-calling iterations without a final answer."),
            "relevanceScore": _relevance_score_from(last_tool_result),
            "planId": plan_id,
            "payerScope": payer,
        }
    except Exception as exc:  # noqa: BLE001 - genuine network/API failure (rate limit, connection error, etc.), not a validation case
        return {
            **_fallback_result(f"Groq API call failed: {exc}"),
            "relevanceScore": _relevance_score_from(last_tool_result),
            "planId": plan_id,
            "payerScope": payer,
        }
