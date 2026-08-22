"""
Real end-to-end integration tests against the LIVE triage service
(policy-rag/main.py, normally port 8002) — real Groq calls, real RAG
retrieval, real ML model. Opt-in only (see conftest.py): run with
`pytest --run-integration`.

Prerequisites (not started by this test file):
    1. Postgres+pgvector running with the real seeded corpus
       (docker compose up -d postgres, from ProAuth_AI_BackEnd/).
    2. This service running: `cd policy-rag && uvicorn main:app --port 8002`
       (or let the Node backend auto-spawn it — see
       ProAuth_AI_BackEnd/src/config/triageServiceManager.js).
    3. GROQ_AGENT_API_KEY set with quota available.

Scenarios are loaded from integration_scenarios.json — the SAME file
ProAuth_AI_BackEnd/tests/triage.integration.test.js reads, so a change to
expected behavior only needs updating in one place, and both the
Python-direct and Node-through-the-full-stack layers stay in sync.

This suite hits port 8002 DIRECTLY (the Python service on its own,
skipping the Node backend/auth layer) — that's the Node test file's job.
Together they cover: does the core pipeline decide correctly (this file),
and does the full stack (auth, persistence, the 60s→120s timeout, status
write-back) actually deliver that correctly to a real caller (the Node
file).
"""
import json
import os

import pytest
import requests

SCENARIOS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "integration_scenarios.json")
TRIAGE_URL = os.environ.get("TRIAGE_SERVICE_URL", "http://localhost:8002")

with open(SCENARIOS_PATH) as f:
    SCENARIOS = json.load(f)


def _service_reachable():
    try:
        r = requests.get(f"{TRIAGE_URL}/health", timeout=3)
        return r.status_code == 200
    except requests.RequestException:
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _service_reachable(), reason=f"triage service not reachable at {TRIAGE_URL}"),
]


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s["id"] for s in SCENARIOS])
def test_scenario(scenario):
    response = requests.post(f"{TRIAGE_URL}/triage", json=scenario["request"], timeout=150)
    assert response.status_code == 200, f"{scenario['id']}: {response.text[:500]}"

    body = response.json()
    decision = body.get("decision", {})
    ml_features = body.get("mlFeatures", {})

    assert decision.get("outcome") == scenario["expectedOutcome"], (
        f"{scenario['id']}: expected {scenario['expectedOutcome']}, got {decision.get('outcome')} "
        f"(reason: {decision.get('reason')})"
    )

    for gate_name, expected_value in scenario.get("expectedGates", {}).items():
        actual_value = ml_features.get(gate_name)
        assert actual_value == expected_value, (
            f"{scenario['id']}: gate {gate_name} expected {expected_value}, got {actual_value}"
        )

    # Baseline sanity: never a crash-shaped response, always structurally complete.
    assert "policyEvidence" in body
    assert "explanation" in body

    # The Companion Agent's OWN Groq call is independent of the decision
    # above (it runs strictly after, explains but never re-evaluates) and
    # can itself hit a transient failure (e.g. Groq rate/quota limits —
    # confirmed live 2026-08-20, see docs/PROGRESS_TRACKER.md item #6) and
    # degrade gracefully to an empty summary + agentError rather than
    # crashing the request. That's correct, tracked behavior, not a
    # decision-correctness bug this suite is meant to catch — so this test
    # only requires a real summary when the Companion Agent itself
    # actually succeeded.
    explanation = body["explanation"]
    if not explanation.get("agentError"):
        assert explanation.get("summary"), (
            f"{scenario['id']}: Companion Agent reported no error but returned an empty summary"
        )
