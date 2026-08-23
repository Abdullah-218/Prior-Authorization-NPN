/**
 * Priority Service (client)
 *
 * Calls the priority-intelligence feature's /priority/rerank endpoint —
 * mounted as a router on the SAME Python service triageService.js already
 * talks to (ProAuth_AI_ML/policy-rag/main.py, port 8002), not a second
 * process. See ProAuth_AI_ML/priority_intelligence/README.md.
 *
 * Pure ranking, no LLM calls on the Python side — cheap and fast (pandas/
 * XGBoost only), so this is called fresh on every queue view rather than
 * cached; unlike runTriage() there's no expensive-call reason to memoize.
 */
import { env } from '../config/env.js';

/**
 * cases: array of {requestId, policyScore, documentationScore,
 * clinicalEvidenceScore, numCriteriaMissing, urgency, careSetting,
 * submittedAt} — camelCase Node-side shape; converted to the Python
 * side's snake_case contract here so callers don't need to know that
 * detail. Returns the ranked/tiered list, snake_case fields converted
 * back to camelCase for the rest of the Node app to consume normally.
 */
export async function runPriorityRerank(cases, now) {
  if (!cases.length) return [];

  const payload = {
    cases: cases.map((c) => ({
      request_id: c.requestId,
      outcome: 'PEND',
      policy_score: c.policyScore,
      documentation_score: c.documentationScore,
      clinical_evidence_score: c.clinicalEvidenceScore,
      num_criteria_missing: c.numCriteriaMissing,
      urgency: c.urgency,
      care_setting: c.careSetting,
      submitted_at: c.submittedAt,
    })),
    now: now || new Date().toISOString(),
  };

  const controller = new AbortController();
  // A pure pandas/XGBoost computation over a queue of PEND cases —
  // no LLM calls, no reason for this to ever take anywhere near as long
  // as runTriage()'s 120s. 15s is generous headroom, not a tuned limit.
  const timeout = setTimeout(() => controller.abort(), 15000);

  try {
    const response = await fetch(`${env.triageServiceUrl}/priority/rerank`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: controller.signal,
    }).finally(() => clearTimeout(timeout));

    if (!response.ok) {
      const text = await response.text().catch(() => '');
      let message = text.slice(0, 500);
      try {
        const parsed = JSON.parse(text);
        message = parsed?.detail?.message || parsed?.detail || parsed?.message || message;
      } catch {
        // Not JSON — keep the raw (truncated) text as the fallback message.
      }
      throw new Error(`Priority service returned ${response.status}: ${message}`);
    }

    const result = await response.json();
    return (result.cases || []).map((c) => ({
      authorizationId: c.request_id,
      priorityScore: c.priority_score,
      priorityTier: c.priority_tier,
      queueRank: c.queue_rank,
      reasonCodes: c.priority_reason_codes || [],
      hoursPending: c.hours_pending,
      isEmergency: Boolean(c.is_emergency),
      isSlaBreached: Boolean(c.is_sla_breached),
      isSlaBreachImminent: Boolean(c.is_sla_breach_imminent),
    }));
  } catch (err) {
    if (err.name === 'AbortError') {
      throw new Error('Priority service timed out.');
    }
    throw err;
  }
}
