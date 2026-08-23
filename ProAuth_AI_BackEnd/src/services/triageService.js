/**
 * Triage Service (client)
 *
 * Calls the NEW policy-aware agents+RAG+ML pipeline
 * (ProAuth_AI_ML/policy-rag/main.py's POST /triage) over HTTP. This is the
 * "Node/HTTP integration" piece from the project README's pending-work
 * list — before this, the pipeline was reachable only as a standalone
 * Python module.
 *
 * Deliberately separate from mlPredictionService.js: that calls the OLD,
 * already-deployed XGBoost service on a 35-field payload and is explicitly
 * NOT part of this pipeline (see ProAuth_AI_ML/README.md). Nothing here
 * replaces or touches that flow.
 */
import { env } from '../config/env.js';

/**
 * Runs a request through the full evidence -> ML decision -> explanation
 * pipeline. Throws on failure (unlike mlPredictionService's null-on-failure
 * convention) — callers decide how to surface a down triage service, since
 * unlike the rule-engine's ML step, this endpoint IS the feature being
 * called, not a step with an established manual-review fallback.
 */
export async function runTriage(request) {
  const {
    requestedService,
    diagnosis,
    planId,
    secondaryDiagnosis,
    icd10Code,
    clinicalJustification,
    patientFacts,
    documentEvidence,
    attachedDocuments,
    requestContext,
    threadId,
    providerSpecialty,
  } = request;

  if (!requestedService || !diagnosis) {
    throw new Error('requestedService and diagnosis are required.');
  }

  const controller = new AbortController();
  // 60s was too tight — live-reproduced 2026-08-20: a real request that
  // reached document-evidence + full clinical-criteria grading (more
  // sequential Groq calls than the happy-path scenarios this was tuned
  // against) took >60s and got aborted here, surfacing as a false-negative
  // 500 even though the Python pipeline was still working correctly (its
  // own log showed the call completing normally after Node had already
  // given up). 120s gave real multi-agent tool-calling requests headroom —
  // then 150s, live-reproduced again 2026-08-21: policy_evidence_agent.py
  // now does one corrective retry when its own final answer contradicts
  // the confidence-gated retrieval result it was just given (see that
  // file's evaluate_policy_evidence docstring), an extra Groq round-trip
  // that pushed a real, legitimately-still-working request past 120s.
  // Phase 4's other half — coordinated Groq resilience (2026-08-20, see
  // docs/PROGRESS_TRACKER.md §9.9) — is done on the Python side: every
  // agent-level Groq call now degrades to a safe, explained PEND on a
  // rate-limit/connection failure instead of crashing, so this timeout's
  // job narrows to genuinely slow-but-still-working calls, not Groq
  // outages (those now return a normal 200 well before this, or a clean
  // 503 from the pipeline's own defensive backstop — never a bare abort).
  const timeout = setTimeout(() => controller.abort(), 150000);

  try {
    const response = await fetch(`${env.triageServiceUrl}/triage`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        requestedService,
        diagnosis,
        planId: planId || null,
        secondaryDiagnosis: secondaryDiagnosis || null,
        icd10Code: icd10Code || null,
        clinicalJustification: clinicalJustification || null,
        patientFacts: patientFacts || null,
        documentEvidence: documentEvidence || null,
        attachedDocuments: attachedDocuments || null,
        requestContext: requestContext || null,
        threadId: threadId || null,
        // NOT informational-only, despite how that might read — it grounds
        // Clinical Agent's specialty_match criterion (specialty_check.py /
        // clinical_evidence_agent.py), which contributes to
        // clinical_evidence_score like any other criterion and can hard-gate
        // to PEND (coverage_reasoning_agent.py's specialtyMismatchFlagged).
        providerSpecialty: providerSpecialty || null,
      }),
      signal: controller.signal,
    }).finally(() => clearTimeout(timeout));

    if (!response.ok) {
      // Prefer the Python service's own clean, structured error body
      // (2026-08-20 — coordinated Groq resilience: the pipeline's
      // defensive backstop and per-agent fallbacks now return a real
      // {"detail": {"message": "..."}} JSON body instead of letting a
      // raw traceback fall through) over dumping raw response text,
      // which used to include a chunk of Python stack trace straight
      // into the doctor/reviewer-facing error.
      const text = await response.text().catch(() => '');
      let message = text.slice(0, 500);
      try {
        const parsed = JSON.parse(text);
        message = parsed?.detail?.message || parsed?.message || message;
      } catch {
        // Not JSON — keep the raw (truncated) text as the fallback message.
      }
      throw new Error(`Triage service returned ${response.status}: ${message}`);
    }

    return await response.json();
  } catch (err) {
    if (err.name === 'AbortError') {
      throw new Error('Triage service timed out.');
    }
    throw err;
  }
}
