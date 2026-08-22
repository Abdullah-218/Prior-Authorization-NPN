# Priority Intelligence — PEND-only nurse queue prioritization

Adapted from a package a collaborator shared (`ProAuth_AI_Nurse_Priority_Agent_PEND_ONLY/`,
kept at the repo root as the original reference — not part of this system).
Only the actually-relevant `priority_agent/` subpackage was brought over;
the source folder's own rebuilt base triage model (`generate_dataset.py`,
`train.py`, `feature_selection.py`, `policy_corpus.py`, its own
`models/proauth_best_model.pkl`) was deliberately left out — it is a
separate, independent rebuild of the triage model we already have live in
`policy-rag/ml/model.py`, not something this feature needs or should touch.

## What this does

Downstream of the existing triage pipeline, never upstream of it. Once
`ml/model.py` has already decided a request is `PEND`, this ranks the
PEND queue so the nurse dashboard can show highest-priority cases first,
with a HIGH/MEDIUM/LOW tier and plain-language reasons per case.

`policy_score`, `documentation_score`, `clinical_evidence_score` are the
exact same 0-100 values `coverage_reasoning_agent.py` already computes on
every triage evaluation — no new agent output needed on that side.

## What was fixed to actually work on our real data (2026-08-21)

The trained model (`models/priority_ranker.joblib`, an XGBoost `XGBRanker`)
is kept as-shared, trained on the collaborator's own synthetic dataset —
retraining on our data was explicitly not required for this pass. What
WAS required, and fixed here, verified against 12 real PEND cases pulled
live from our own Postgres:

- **`features.py` — urgency/care_setting normalization.** Our real system
  stores `urgency` capitalized (`Routine`/`Urgent`/`Emergency`, from
  `NewAuthorization.jsx`'s Treatment step) while the source package's
  config is keyed lowercase. Worse: several real historical authorizations
  have **blank** urgency/care_setting entirely (confirmed live — 8 of 12
  real PEND cases had both blank). Previously this fell straight through
  `.map()` to `NaN` with no error, silently corrupting every derived
  feature. Now normalized with a safe, conservative default (`'routine'`,
  `'Outpatient'` — the least-urgent assumption, never inflating priority
  from missing data).
- **`features.py` — timezone handling.** Our `Authorization.submittedAt`
  is a real Postgres `TIMESTAMPTZ`, serialized timezone-AWARE; the source
  package's own convention (its `now`, its synthetic CSVs) is
  timezone-NAIVE. Pandas refuses to subtract aware from naive at all
  (raises, not silently wrong) — this crashed on every real case before
  being fixed. Both sides are now normalized to naive UTC before the
  subtraction, so it works with either real or synthetic input.
- **`ranker.py` / `safety.py` — score rescaling.** The raw XGBRanker output
  is NOT a 0-100 score — observed range is roughly `[-3.7, +3.3]`. The
  source package's own `safety.py` applied `np.maximum(raw_score, 0)`
  directly to that raw value, which meant **every** non-safety-overridden
  case collapsed to exactly 0 — the model's real (if narrow-band)
  differentiation between cases was destroyed before a tier decision
  could ever be made, making a genuine MEDIUM tier unreachable regardless
  of tier thresholds. Fixed by rescaling the raw score onto a fixed 0-100
  range (`RAW_SCORE_MIN`/`MAX` in `ranker.py`) BEFORE the safety floors
  are applied — verified this restores real differentiation (12 real
  cases now spread 4.6–17.3 instead of all landing on 0).
- **`tiers.py` (new) — HIGH/MEDIUM/LOW classification.** The source
  package only ever produced a continuous 0-100 score + rank position,
  never a discrete label. `MEDIUM_THRESHOLD=20` was calibrated from the
  actually-observed non-overridden score range (real cases topped out at
  17.3; a deliberately poor-evidence/moderate-pressure synthetic case hit
  26.3) — this is a small-sample calibration (12 live PEND cases at time
  of writing) and should be revisited once real queue volume is larger.
- **`priority_ranker.joblib` re-saved** under the currently-installed
  xgboost (3.2.0) to clear a pickle version-compatibility warning from the
  original artifact — same model, no retraining, just removes a future
  fragility risk.

## Verified working (see `tests/`)

7 tests pass, including 4 new ones added here:
`tests/test_real_data_integration.py` runs the fixed pipeline against
`tests/real_pend_sample.csv` (12 real PEND cases, pulled live from our
database, kept exactly as-extracted including their blank
urgency/care_setting) plus two injected synthetic cases (a clear
emergency, a clear "urgent + poor evidence, not yet SLA-breached"),
proving all three tiers — HIGH, MEDIUM, LOW — are actually reachable
together in one ranked call, not just in isolation:

```
rank=1  tier=HIGH    score=90.0  SYNTH-EMERGENCY             reasons=['Emergency request', 'SLA breach is imminent', 'Critical clinical risk']
rank=2  tier=MEDIUM  score=26.3  SYNTH-URGENT-POOR-EVIDENCE  reasons=['High clinical risk', '4 criteria missing']
rank=3  tier=LOW     score=17.3  PA-1787244854949            reasons=['High clinical risk']
...(11 more real cases, all correctly ranked LOW — none are genuinely urgent yet)
```

Run: `cd ProAuth_AI_ML && policy-rag/.venv/bin/python3 -m pytest priority_intelligence/tests/ -v`

## Required input per case (unchanged from source's integration contract)

`request_id`, `policy_score`, `documentation_score`, `clinical_evidence_score`,
`num_criteria_missing`, `urgency`, `care_setting`, `submitted_at`, `outcome` (must be `'PEND'`).

All 4 numeric scores + `num_criteria_missing` come from an authorization's
most recent `TriageEvaluation.mlFeatures`; `urgency`/`care_setting`/
`submitted_at` come from the `Authorization` row itself.

## Known issue: load order matters (fixed, but fragile if disturbed)

Loading this package's XGBoost model AFTER `rag.retrieval` (policy-rag's
sentence-transformers/torch embedding model) has already been imported
into the same process causes a hard SIGSEGV — no Python traceback, no
error response, the whole service just dies. Reproduced directly
(2026-08-21): calling `PriorityRanker()` standalone always worked; calling
it in a process that had already imported `rag.retrieval` crashed every
time; reversing the order fixed it. Both libraries bundle their own
native OpenMP runtime — this is a known class of macOS conflict between
XGBoost and PyTorch-based libraries in the same process, not anything
specific to our code.

Fixed by forcing an eager, singleton load: `policy-rag/main.py` imports
`priority_intelligence.ranker` and calls `get_ranker()` as the very FIRST
thing it does, before `rag.retrieval`/`triage_graph` are imported at all.
`api/main.py`'s route and `agent/graph.py` both call `get_ranker()` (the
cached singleton), never `PriorityRanker()` directly, so no code path
re-triggers a load after `rag.retrieval` is already in the process.

**If this ever gets mounted on a different service, or `main.py`'s import
order gets reshuffled, this WILL come back — the model must always be
loaded before any torch-based import touches the process.**

**Also applies to test runs**: `pytest priority_intelligence/tests/
policy-rag/tests/test_gates_unit.py` in one combined invocation crashes
the same way — pytest imports both test files into the same process, and
nothing enforces load order between them there. Run the two suites as
separate `pytest` invocations (each already does, and always has,
`cd ... && pytest ...` on its own) rather than combining them.

## Synthetic demo data (`policy-rag/scripts/seed_synthetic_demo_data.py`)

Generates 780 realistic authorizations (26 doctors x 30 patients each) —
NO LLM/Groq calls anywhere. Every decision/gate/reason is a genuine
output of the real `aggregate_ml_features()` + `MLTriageAgent.run()`,
called directly; only the "read the notes and extract facts" step
(normally an LLM call) is hand-authored per target outcome. Diagnoses are
drawn from real, existing policies in the corpus matching each doctor's
own specialty. Outcome split: 70% automated approve, 10% manual approve
(nurse/admin overrides a real PEND decision), 13.3% stay PEND, 6.7%
additional-information-required — verified to land exactly on those
numbers, not just targeted.

Also guarantees 13 HIGH / 20 MEDIUM / 25 LOW priority-tier cases always
present in the nurse queue (verified against the real priority ranker at
generation time, not guessed), with any additional real or naturally-
varying synthetic PEND cases landing wherever their own evidence/timing
genuinely computes. Re-run it (it clears its own `PA-SYN-*` rows first if
you delete and regenerate) to refresh the demo before a presentation —
see the script's own docstring for why the MEDIUM tier specifically needs
periodic refreshing (hours_pending grows with real wall-clock time by
design, so a MEDIUM case today will eventually drift toward HIGH).

## Not yet built

This folder is the ranking engine only — verified correct, not yet wired
into anything live:

- No Node backend endpoint gathers real PEND cases and calls this.
- Not mounted into any running FastAPI process (`api/main.py` exists,
  matching the source's shape, but nothing serves it yet — recommend
  mounting as additional routes on the existing `policy-rag` service
  rather than standing up a second Python process).
- No Nurse UI changes — `NurseReview.jsx`/`NursePatientDetail.jsx` don't
  show a priority tier or reason codes yet.
- No MongoDB persistence of priority-score history — not required for
  correctness (this graph is stateless/cheap, no LLM calls to memoize),
  but could be added later if there's a genuine need to show "this case's
  priority has been rising."

## Explicitly left out from the source folder

Its own rebuilt base triage model (top-level `generate_dataset.py`,
`train.py`, `feature_selection.py`, `policy_corpus.py`, `predict.py`,
`config.py`, `models/proauth_best_model.pkl`, `reports/`,
`visualizations/`, `data/processed/`) — a parallel, independent exploration
of the triage model we already have live and tested. Not reused, not
needed, and pulling it in would risk confusion with the real production
model for zero benefit.
