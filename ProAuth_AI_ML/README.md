# ProAuth AI — ML / RAG / Agent Pipeline

Status snapshot as of **2026-08-19**. This covers only `ProAuth_AI_ML/` (the RAG + agent + ML triage pipeline). It does not re-document the Node backend or React frontend beyond how they integrate with this service.

Architecture rule this entire pipeline is built around: **agents never decide.** Every agent/RAG/rule-lookup component in this folder only gathers, structures, or scores evidence. The single trained ML model (`policy-rag/ml/model.py`) is the only component that ever outputs APPROVE / PEND / MORE_INFORMATION.

---

## 1. What's actually implemented

### 1.1 Data layer (real, not synthetic)

| Source | Table | Live count | Notes |
|---|---|---|---|
| CMS Coverage API (`api.coverage.cms.gov`) | `policies` (source=`CMS`) | 316 | Real National Coverage Determinations, ingested via `seeding/ingest_cms_ncd.py` |
| Payer PDFs/HTML (UHC, Cigna, Aetna) | `policies` (source=`PUBLIC_PAYER_POLICY`) | 28 (4 per payer × ~2 categories + 1 initial batch) | Hand-extracted real bulletins (`pdftotext`), not paraphrased — see `seeding/ingest_payer_policies*.py` / `seeding/payer_policies_batch2_*.py` for exact source URLs and effective dates |
| Both, chunked + embedded | `policy_chunks` | 1,418 | `all-MiniLM-L6-v2`, 384-dim, pgvector |
| FDA drug labels | `drug_references` | 54 | Queried directly by `agents/drug_reference_lookup.py` for grounded `indication_match` |
| Test-fixture plans | `insurance_plans` | 16 (1 Medicare, 4 UHC, 4 Cigna, 4 Aetna, 3 Private-tier) | `Private` is a sentinel resolved to the union of UHC+Cigna+Aetna (`retrieval.py::PRIVATE_PAYER_GROUP`) |

**Verified this session** (raw SQL count + full corpus audit): zero empty/missing chunks, ingestion pipeline itself is not the source of any retrieval gaps.

### 1.2 RAG retrieval (`policy-rag/rag/retrieval.py`)
- Structured pre-filter (payer/jurisdiction/policy_type) via plain SQL `WHERE`, **then** pgvector cosine-distance ranking — never a blind vector search across the whole corpus.
- Confidence-gated: distance ≤0.35 → HIGH, ≤0.50 → MEDIUM, else treated as **not found** and never shown to any agent as evidence (`POLICY_EVIDENCE_UNAVAILABLE_MESSAGE`). Thresholds were empirically measured against this real corpus, not guessed.
- `MAX_PER_SECTION=3` stops a finely-chunked exclusion list from crowding out a sparser-but-relevant covered-indications section.
- `top_k=16` (raised from 8 this session after a live bug — see §3).
- Payer scoping is 100% deterministic, resolved from the patient's actual `insurance_plans` row before any LLM call — the LLM never chooses or sees the scope.

### 1.3 Agent pipeline (`policy-rag/agents/`, orchestrated by `triage_graph.py`)

| Agent | Real LLM call? | Role | Output |
|---|---|---|---|
| Policy Evidence Agent | Yes — genuine Groq tool-calling loop (bounded 5 iterations) | Finds applicable policy, extracts named criteria | `policyFound`, `coverageStatus`, `criteria[]`, `clinicalCriteria[]`, `requiredDocuments[]`, `confidence` |
| Clinical Agent — extraction | Yes — single Groq call | Extracts structured facts from the doctor's free-text justification (under-extraction is the safety default) | `extractedFacts{}`, `factSources[]` |
| Clinical Agent — criteria grading | Mixed — deterministic lookups first, LLM only for what those can't resolve | Grades each named criterion PASS/FAIL, including 4 built-in safety/context criteria | `criteriaResults{}`, `clinicalEvidenceScore`, `groundedIndicationMismatch`, `contraindicationDetails[]` |
| Document Agent | No — pure keyword/rule matching + local OCR | Verifies uploaded files against a fixed baseline (Clinical notes + Prescription only) | `documentationScore`, `missingDocuments[]`, `optionalDocuments{}` |
| Coverage Reasoning Agent | No — pure deterministic aggregator (repurposed from an old LLM agent) | Merges everything into the ML feature vector + 5 hard gates | `featureVector{}`, 5 gate booleans |
| ML Triage Model | No — trained sklearn Pipeline | **The only decision-maker** | `outcome`, `confidence`, `probaApprove` |
| Companion Agent | Yes — single Groq call, runs after the decision exists | Plain-language explanation, never re-decides | `summary`, `keyFactors[]`, `citedEvidence[]` |

### 1.4 Deterministic safety gates (checked in this order, before the ML model ever runs)
1. `contraindicationFlagged` — 18-rule hardcoded table (`agents/contraindication_lookup.py`) + a dedicated policy-independent LLM safety judgment for anything the table doesn't cover.
2. `indicationMismatchFlagged` — grounded FDA-label zero-overlap or a real LLM judgment against retrieved policy evidence.
3. `missingRequiredEvidence` — Clinical notes + Prescription are now the only compulsory documents.
4. `clinicalEvidenceInsufficient` — fires when the policy named specific criteria and **zero** were demonstrated.
5. `urgencyFlagged` — a claimed Urgent/Emergency request the LLM judged clinically implausible.

All five were added, offline-tested, and live-verified this session after being found via real auto-approval failures (semaglutide for allergic rhinitis, gene therapy against a sickle-cell-only policy, bariatric surgery with a one-line justification — all originally cleared around 0.42–0.81 confidence before these gates existed).

### 1.5 ML model (`policy-rag/ml/model.py`)
- scikit-learn `Pipeline` (StandardScaler + LogisticRegression), artifact at `policy-rag/ml/models/proauth_best_model.pkl`.
- Reported metrics (from the artifact itself): 85.07% test accuracy, 82.89% holdout accuracy, ROC AUC 0.9369 / 0.9099, decision threshold 0.453 (not a hardcoded 0.5 — read from the artifact). Retrained 2026-08-20 (item #3/#45, see `docs/PROGRESS_TRACKER.md` §9.10) to correct an over-correlated `policy_score` training input; prior metrics were 85.38%/83.33%/0.9383/0.9154.
- Trained on only 4 of the 10 features the aggregator computes (`policy_score`, `documentation_score`, `clinical_evidence_score`, `diagnosis_supported`) — a deliberate choice per `ml/generate_dataset.py`, not an oversight.
- Training data: **synthetic**, generated by `ml/generate_dataset.py` (9,028 rows in `ml/data/processed/ml_training_set.csv`), not real historical PA outcomes. Full regeneration is currently blocked (a `policy_corpus.py` dependency is missing from this codebase); `ml/fix_policy_score_correlation.py` corrects the existing dataset in place instead, without needing that dependency.

### 1.6 Node backend / frontend integration
- `policy-rag/main.py` (FastAPI, port 8002) wraps the graph + ML model + Companion Agent into one `/triage` endpoint the Node backend calls.
- MongoDB (`MongoDBSaver`) checkpoints every evaluation per Authorization ID — resubmissions reuse unchanged prior-stage output instead of re-spending Groq calls.
- Empty-field / validation failures now correctly write `Additional Information Required` back to the Authorization with an audit event and notification (fixed this session — previously silent).
- Frontend's `NewApplication.jsx` now forwards Previous Treatment History and Alternative Treatments fields into the triage payload (fixed this session — was previously silently dropped, an entire wizard section never reached the pipeline).

---

## 2. Overall completion assessment

| Layer | Status | Notes |
|---|---|---|
| Data ingestion pipeline | **Functional, narrow** | Real sources, zero fabrication, but 344 policies covers a sliver of real-world coverage determinations |
| RAG retrieval | **Functional, tuned** | Confidence gating and ranking verified against real failure cases this session |
| Agent pipeline | **Functional for demo scope** | All 5 safety gates live-verified; generalization to unseen drugs now works via the LLM fallback, not just the static table |
| ML model | **Functional, synthetic-trained** | Real metrics, but never seen a real PA outcome; no retraining/monitoring pipeline exists |
| Backend/frontend integration | **Functional end-to-end** | Verified live across Medicare + Silver/Gold/Premium test cases this session |
| Production/real-world readiness | **Not started** | No FHIR/X12 interoperability, no regulatory compliance work (CMS-0057-F), no auth hardening, no load testing — see prior conversation for the full breakdown |

This is a working, internally-consistent **prototype/demo-scale system** with genuinely real data sources and a defensible safety-gate architecture — not yet a production PA platform.

---

## 3. Known errors / issues to fix next

1. **sklearn version mismatch (live, currently happening).** `requirements.txt` pins `scikit-learn==1.8.0` to match what the pickled model was trained with, but the actual `.venv` has `1.9.0` installed — every `/triage` call currently logs 3× `InconsistentVersionWarning` (`StandardScaler`, `LogisticRegression`, `Pipeline`). Not yet causing wrong output, but is completely unverified — should either reinstall the pinned version in the venv or retrain and re-export the artifact against whatever version is actually running.

2. **Single Groq API key is a reliability single point of failure.** Observed live this session (see `/tmp/backend2.log`): two consecutive `/api/triage/evaluate` calls hit the Node backend's 60-second timeout and returned 500 while waiting on Groq rate-limit backoff. There is no retry/circuit-breaker around any Groq call in any agent — a transient 429 or slow response currently just fails the whole triage request.

3. **No API authentication on the triage service itself.** `policy-rag/main.py`'s FastAPI app has no auth check on `/triage` — it's presumably only reachable inside the docker network today, but there's nothing in code enforcing that.

4. **Policy corpus breadth is the biggest functional gap.** 344 policies across essentially 2 procedure categories (bariatric surgery, sleep-disordered breathing) for the 3 private payers, plus general CMS NCDs. Any diagnosis/procedure outside what's been hand-ingested correctly returns "no policy found" (honest, not a bug) but that means most real-world requests would get a degraded/gated result today, not a real evaluation.

5. **`drug_references` table has only 54 drugs.** Most real drug names won't resolve via `find_drug_reference()`, so `indication_match` falls through to the LLM-graded path for the large majority of medication requests rather than the grounded deterministic path.

6. **Test coverage is thin.** Only one test file exists (`policy-rag/tests/test_triage_graph.py`). No unit tests for the contraindication table, drug reference matching, specialty matching, or the ML model wrapper's gate-ordering logic — all of this session's verification was manual/live testing, not an automated regression suite.

7. **ML model has no retraining/monitoring pipeline.** It was trained once on synthetic data (`generate_dataset.py`). Nothing tracks prediction drift, nothing retrains on real outcomes (there aren't any yet), and there's no model card / bias audit.

8. **`policy_score`'s train/inference gap is a documented but real approximation, not a true value.** `coverage_reasoning_agent.py::_estimate_policy_score` stands in for a "hidden latent variable" that existed only in the synthetic training generator — live requests can never reproduce the actual training-time formula, only approximate it.

9. **Two separate Groq keys exist across the two runtimes** (`GROQ_AGENT_API_KEY` here vs. the Node backend's `GROQ_API_KEY`, originally for the now-retired rule engine). Worth confirming whether `GROQ_API_KEY` and its call sites in the Node backend are genuinely still used for anything, or are dead code left over from the retired pipeline.

---

## 4. Hardcoded parts that should become dynamic

| What | Where | Why it matters |
|---|---|---|
| 18-rule contraindication table | `agents/contraindication_lookup.py::KNOWN_CONTRAINDICATIONS` | Fast/free/trusted-outright, but a real product needs a licensed drug-interaction source (First Databank, Micromedex) or an admin-editable DB table — a hand-maintained Python list can't scale past a demo set, and every new rule requires a code change + redeploy |
| Specialty → treatment keyword map | `agents/specialty_check.py::SPECIALTY_MAP` | Duplicated **by hand** in two languages/repos (Node's `providerCompatibilityEvaluator.js` and this Python module) — no single source of truth, they will eventually drift out of sync silently |
| Document category keywords + fixed upload categories | `agents/document_agent.py::CATEGORY_KEYWORDS`, `BASELINE_REQUIRED_DOCUMENTS` | Tightly, invisibly coupled to the frontend's fixed Step 7 upload fields (`NewApplication.jsx`) — adding a real-world document type requires coordinated hand-edits in at least 2 places with no shared schema |
| Private-payer group | `rag/retrieval.py::PRIVATE_PAYER_GROUP = ["Aetna","Cigna","UnitedHealthcare"]` | Which real payers count as "Private tier" is a hardcoded list, not read from any config or DB — onboarding a new payer means a code change |
| RAG confidence thresholds | `rag/retrieval.py::HIGH_CONFIDENCE_MAX_DISTANCE`, `MEDIUM_CONFIDENCE_MAX_DISTANCE` | Empirically tuned to the current 1,418-chunk corpus and `all-MiniLM-L6-v2` — will silently miscalibrate if the corpus grows substantially or the embedding model changes, with no re-validation process |
| `top_k=16`, `MAX_ITERATIONS=5` | `agents/policy_evidence_agent.py` | Magic numbers tuned to today's corpus size (found live via one specific failure case) — no monitoring to catch when the corpus outgrows them again |
| Groq model name fallback string | Repeated literal `"openai/gpt-oss-120b"` in 4 different agent files | Should be one shared constant/config value, not copy-pasted per file |
| Model's feature list | `ml/config.py::FEATURES` duplicates `ml/model.py`'s `self.artifact["features"]` | Two independent sources of truth for the same 4-feature list — a retrain that changes features must be updated in both places by hand |
| `_estimate_policy_score` formula | `agents/coverage_reasoning_agent.py` | Hand-tuned constants (`0.5 + 0.5*relevance`, `-40` penalty) standing in for a value the model never actually sees at inference time — see issue §3.8 |
| Checkpoint staleness window | `triage_graph.py::STALE_CHECKPOINT_MAX_AGE = 90 days` | Fixed constant, not configurable per deployment |
| Indication-match strength thresholds | `agents/drug_reference_lookup.py::indication_match_strength` (≥2 keywords = STRONG, 1 = WEAK) | A simple keyword-count heuristic against FDA label text, not calibrated against any real outcome data |
| Non-routine urgency values | `agents/clinical_evidence_agent.py::NON_ROUTINE_URGENCY_VALUES` | Fixed set (`urgent`, `emergency`, `emergent`, `stat`) |
| Fixed 5 upload categories | Frontend Step 7 + `document_agent.py` | The set of document types the whole system can even recognize is fixed at exactly 5, hardcoded on both ends |

---

## 5. Suggested next steps (priority order)

1. Fix the sklearn version mismatch (§3.1) — quick, low-risk, currently silently unverified in every live prediction.
2. Add retry/backoff or a circuit breaker around Groq calls (§3.2) — this caused real, reproducible 500s this session.
3. Widen the policy corpus (§3.4) and drug reference table (§3.5) — the single biggest lever on how often the system gives a real evaluation instead of a degraded/gated one.
4. Move the contraindication table and specialty map into a DB-backed, admin-editable source (§4) — removes the biggest "hardcoded" risk and the Node/Python duplication problem in one move.
5. Build a minimal automated regression suite covering the 5 gates + both deterministic lookups (§3.6) — everything verified so far was manual/live testing.
6. Add basic auth to the triage service (§3.3) before this is exposed anywhere beyond a private network.