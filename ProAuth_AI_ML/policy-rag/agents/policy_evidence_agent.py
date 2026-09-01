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

    result = retrieve_policy_evidence(args["query"], payer=payer)
    last_result_holder["result"] = result
    return json.dumps(result)


def _relevance_score_from(last_result_holder):
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
    try:
        for _ in range(MAX_ITERATIONS):
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=TOOLS,

                tool_choice="auto" if not tool_already_called else "none",
                temperature=0.1,
            )
            message = response.choices[0].message

            if not message.tool_calls:
                content = message.content
                if not _is_valid_json(content):
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
                    except Exception:  
                        pass

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
    except Exception as exc:
        return {
            **_fallback_result(f"Groq API call failed: {exc}"),
            "relevanceScore": _relevance_score_from(last_tool_result),
            "planId": plan_id,
            "payerScope": payer,
        }
