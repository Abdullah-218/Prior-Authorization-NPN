# ProAuth AI

**AI-assisted prior authorization for healthcare — evidence-grounded, gate-protected, and always reviewed by a human.**

ProAuth AI automates the evidence-gathering and risk-triage steps of medical prior authorization (PA)
requests, while keeping every approval, denial, and edge case under deterministic safety rules and
final human review. It combines retrieval-augmented policy lookup, a small team of specialized
agents, a trained decision model, and a priority-ranking system — wired into a real multi-role
web application backed by PostgreSQL, MongoDB, and AWS.

---

## Table of Contents

1. [Problem Statement](#problem-statement)
2. [Solution](#solution)
3. [Objectives](#objectives)
4. [Core Design Principle: Agents Gather Evidence, the Model Decides](#core-design-principle-agents-gather-evidence-the-model-decides)
5. [System Architecture](#system-architecture)
6. [The Six-Agent Workflow](#the-six-agent-workflow)
7. [Deterministic Safety Gates](#deterministic-safety-gates)
8. [Policy Retrieval (RAG)](#policy-retrieval-rag)
9. [The Decision Model](#the-decision-model)
10. [Priority Intelligence (Queue Ranking)](#priority-intelligence-queue-ranking)
11. [Data Security](#data-security)
12. [Application Roles](#application-roles)
13. [Tech Stack](#tech-stack)
14. [Project Structure](#project-structure)
15. [Database](#database)
16. [Running Locally](#running-locally)
17. [Deployment (AWS)](#deployment-aws)
18. [Testing](#testing)
19. [Known Limitations](#known-limitations)

---

## Problem Statement

Prior authorization is the approval a health insurer requires before certain treatments, procedures,
or medications are covered. In practice it is one of the most friction-heavy parts of the healthcare
system:

- **Slow.** A request can sit for days waiting on a human reviewer to manually check it against a
  payer's coverage policy, cross-reference clinical documentation, and decide.
- **Inconsistent.** The same request can get different outcomes depending on which reviewer
  handles it and how carefully they read the policy that day.
- **Opaque.** Doctors and patients often get a denial with little explanation of which specific
  policy criterion wasn't met or what evidence would fix it.
- **Reviewer time is spent unevenly.** Every pending request waits in the same queue whether it's
  routine and low-risk or clinically urgent — nothing surfaces the case that actually needs
  attention first.
- **Volume keeps growing** while clinical staff time doesn't scale with it.

## Solution

ProAuth AI is a full-stack prior-authorization platform where a doctor submits a request and, within
the same session, receives an evidence-grounded triage outcome — **Approve**, **Pend for human
review**, or **More information needed** — instead of an opaque wait. Behind that outcome:

- A **retrieval layer** grounds every decision in the *actual* payer policy text, not a model's
  memorized guess at what a policy might say.
- A small **team of specialized agents** each independently gather one kind of evidence (policy
  coverage, clinical criteria, submitted documentation) so no single step is asked to do everything.
- **Deterministic safety gates** — plain code, not a model — catch known-dangerous or
  known-incomplete cases (drug contraindications, an inactive policy, a wrong specialty) and route
  them straight to a human, *before* any model prediction is even computed.
- A **trained classifier**, not an LLM, makes the actual approve/pend call for everything that
  clears the gates — bounded, auditable, and reproducible in a way a raw LLM judgment isn't.
- Every request that does land in a human queue is **automatically ranked by real urgency** — SLA
  pressure, clinical risk, how long it's been waiting — instead of sitting in submission order.
- The whole system runs behind **four real, role-specific applications** (Doctor, Nurse, Insurance
  Admin, Patient), each seeing exactly the workflow and data relevant to them.

## Objectives

- Cut the time between request submission and a defensible triage outcome from days to minutes for
  the majority of cases.
- Ground every automated recommendation in real, retrieved policy text and real submitted clinical
  evidence — never a model's unverified claim about what a policy says.
- Keep a human in the loop for every case that carries genuine ambiguity, risk, or missing
  information, instead of ever fully automating a denial.
- Give reviewers a queue that's ranked by actual urgency, not submission order.
- Protect clinical and decision data at rest, not just in transit.
- Make every automated decision explainable — which policy, which criteria, which evidence, in
  plain language, not a black-box score.

## Core Design Principle: Agents Gather Evidence, the Model Decides

This is the single most load-bearing architectural decision in the project: **the LLM-driven agents
never decide the outcome of a request.** Their job is to retrieve, extract, and structure evidence.
A separately trained classifier — with a fixed, bounded feature set and a calibrated decision
threshold — is the only thing that ever outputs APPROVE or PEND on the criteria the model actually
learned from. Deterministic code-level gates sit in front of the model entirely, so anything the
gates already know is unsafe or incomplete never reaches the model at all.

This separation exists on purpose: an LLM's judgment is fluent but not bounded or auditable in the
way a trained model's decision boundary is; letting an agent's prose reasoning silently become the
actual approve/deny call would make every decision unrepeatable and hard to defend. Every agent in
this system produces *evidence*. Only the model and the deterministic gates produce a *decision*.

## System Architecture

```
┌───────────────────────┐        ┌────────────────────────┐        ┌──────────────────────────────────┐
│   React Frontend        │       │   Node.js / Express API  │       │   Python Triage Service (FastAPI)  │
│                          │       │                          │       │                                    │
│  Doctor · Nurse ·        │◄─────►│  Auth · Authorizations   │◄─────►│  LangGraph orchestration           │
│  Insurance Admin ·       │  REST │  Documents · Review      │ REST  │  RAG retrieval + 5 agents           │
│  Patient (read-only)     │       │  Priority · Audit        │       │  Deterministic safety gates         │
└───────────────────────┘        └────────────┬─────────────┘        │  Trained decision model             │
                                                │                       │  Companion (explanation) agent      │
                                                │                       └───────────────┬────────────────────┘
                                  ┌─────────────┴─────────────┐                         │
                                  │   PostgreSQL 17 + pgvector  │◄────────────────────────┘
                                  │                              │        (policy corpus + embeddings,
                                  │   Clinical & decision JSONB   │         shared with the Node backend)
                                  │   columns encrypted at rest   │
                                  │   (AES-256-GCM)                │
                                  └───────────────────────────────┘

                                  ┌───────────────────────────────┐        ┌─────────────────────────────┐
                                  │   MongoDB Atlas                 │       │  Priority Intelligence       │
                                  │   LangGraph checkpoint state     │       │  Service (XGBoost ranker)    │
                                  │   (per-request evidence trail,   │       │  Ranks the human review      │
                                  │    resubmission memoization)     │       │  queue by real urgency       │
                                  └───────────────────────────────┘        └─────────────────────────────┘
```

Deployed on AWS via ECS Fargate (one service each for frontend/backend/ML), a shared Application
Load Balancer, RDS for PostgreSQL, and S3 for model artifacts — provisioned through AWS Copilot.

## The Six-Agent Workflow

A submitted request runs through six named agents across two services. Three call Groq (LLM
tool-calling / extraction); three are deterministic code, deliberately not LLM calls, even though
they're architecturally agents/graph nodes in their own right.

| # | Agent | Service | Calls an LLM? | Role |
|---|---|---|---|---|
| 1 | **Policy Evidence Agent** | Triage (LangGraph) | Yes (Groq, real tool-calling) | Retrieves the applicable payer policy via RAG, extracts its coverage status and named clinical criteria — grounded only in what retrieval actually returns, never the model's own medical knowledge |
| 2 | **Clinical Evidence Agent** | Triage (LangGraph) | Yes (Groq) | Extracts structured clinical facts from the doctor's diagnosis, ICD-10 code, and free-text justification; then scores those facts against the policy's named criteria (diagnosis-supported, per-criterion pass/fail) |
| 3 | **Document Agent** | Triage (LangGraph) | No — deterministic | Checks which required document types (clinical notes, prescription) were actually submitted; reports policy-named optional documents as informational context, never blocking |
| 4 | **Coverage Reasoning Agent** | Triage (LangGraph) | No — deterministic aggregator | Combines policy + clinical + document evidence into the model's feature vector and evaluates all nine safety gates, in priority order, *before* the model ever runs |
| 5 | **Companion Agent** | Triage (post-decision) | Yes (Groq) | Runs only *after* a decision already exists — writes the plain-language explanation citing the real evidence. Never re-evaluates or second-guesses the decision it's given |
| 6 | **Priority Agent** | Priority Intelligence (separate LangGraph) | No — deterministic orchestrator | Validates a newly-PEND case, invokes feature computation and the XGBoost ranking model, and applies the safety-floor overrides that produce the reviewer's ranked queue |

**Triage graph topology** (agents 1–4, real LangGraph edges):

```
        ┌────────────────────┐
   ┌───►│  Policy Evidence     │───────────────┐
   │    │  Agent (RAG + Groq)  │               │
 START  └────────────────────┘               ▼
   │                                  ┌──────────────────┐
   │    ┌────────────────────┐        │  Document Agent    │
   └───►│  Clinical Evidence   │───┐   │  (deterministic)   │
        │  Agent (Groq)        │   │   └─────────┬─────────┘
        └────────────────────┘   ▼             │
                          ┌────────────────┐    │
                          │ Clinical        │    │
                          │ Criteria Eval    │    │
                          │ (Groq)           │    │
                          └────────┬────────┘    │
                                   └───────┬──────┘
                                           ▼
                                ┌──────────────────────┐
                                │  Coverage Reasoning     │
                                │  Agent — 9 safety gates │
                                └───────────┬───────────┘
                                            ▼
                                           END
                          (ML decision model + Companion Agent run
                           sequentially after the graph completes)
```

Policy Evidence and Clinical Evidence run in parallel from the start (independent inputs); Clinical
Criteria Evaluation waits on both; Document Evidence only needs the policy's named requirements;
Coverage Reasoning waits on both branches before evaluating the gates and building the model's
feature vector.

## Deterministic Safety Gates

Nine gates run, in this exact priority order, before the trained model ever sees a request. Any gate
that fires routes the request straight to a human reviewer — the model is never invoked, and its
confidence is reported as `null` (not a low score — a real "the model didn't run" signal).

| # | Gate | Outcome |
|---|---|---|
| 1 | Contraindication flagged | PEND |
| 2 | Policy inactive | PEND |
| 3 | Coverage explicitly not covered | PEND |
| 4 | Indication mismatch (diagnosis doesn't support the request) | PEND |
| 5 | Policy not found | PEND |
| 6 | Required evidence missing (no clinical notes / prescription submitted) | MORE INFORMATION |
| 7 | Clinical evidence insufficient (majority of named criteria fail) | MORE INFORMATION |
| 8 | Urgency flagged | PEND |
| 9 | Specialty mismatch | PEND |

Only a request that clears all nine gates reaches the trained decision model.

## Policy Retrieval (RAG)

- **Vector store:** PostgreSQL + `pgvector` — the same database the rest of the app uses, not a
  separate vector database.
- **Embedding model:** `sentence-transformers/all-MiniLM-L6-v2` (384-dimensional).
- **Retrieval:** two-stage cosine-distance search, deterministically scoped to the patient's actual
  payer before any semantic search runs — a Commercial-plan patient's request can never retrieve a
  Medicare-only policy.
- **Confidence bands:** HIGH ≤ 0.35 cosine distance, MEDIUM ≤ 0.50, otherwise LOW/not found. This
  confidence is a hard backstop on `policyFound` — the retrieving agent's own LLM answer can never
  override what the actual retrieved distance says.

## The Decision Model

- **Type:** Logistic Regression (scikit-learn `Pipeline` with standardization), not an LLM.
- **Features (exactly four, fixed):** `policy_score`, `documentation_score`,
  `clinical_evidence_score`, `diagnosis_supported`.
- **Decision threshold:** cost-weighted (false-approve penalized 3× a false-pend), calibrated at
  **0.7305** — recalibrated from a naive 0.5 cutoff specifically to reduce false approvals, the
  costlier error class for a coverage decision.
- **Output:** `APPROVE` or `PEND`, with a real confidence score. A gate-routed PEND always reports
  `confidence: null` so the UI and audit trail can never conflate "the model was uncertain" with "the
  model never ran."

## Priority Intelligence (Queue Ranking)

A separate service ranks every PEND case in the human review queue — it does not re-decide anything,
it orders what a reviewer sees first.

- **Model:** XGBoost ranker (`rank:ndcg`), not the same model as the decision classifier.
- **Nine features:** four reused directly from the original triage evaluation
  (`policy_score`, `documentation_score`, `clinical_evidence_score`, `num_criteria_missing`) plus
  five computed fresh from live queue state (`hours_pending`, `sla_pressure`, `urgency_weight`,
  `care_setting_weight`, `clinical_risk_weight`).
- **Safety-floor overrides** — deterministic, not learned — guarantee a minimum priority score
  regardless of what the ranker predicts: **emergency ≥ 90**, **SLA breached ≥ 88**,
  **SLA breach imminent ≥ 80**.
- **Tiers:** HIGH ≥ 70, MEDIUM ≥ 20, otherwise LOW.
- **Re-ranking:** the same model is simply re-invoked with fresh inputs whenever a new case enters
  the queue or enough time passes that `hours_pending`/`sla_pressure` change — it is not
  continuously retrained.

## Data Security

Clinical content and AI decision detail are encrypted at rest with **AES-256-GCM**, applied
transparently at the application layer (Sequelize model getters/setters) so every existing route and
the entire frontend read and write plain JSON exactly as before — the database, not the application
code, is what changed.

**Encrypted:** `authorizations.{clinical, treatment, previousTreatment, justification,
currentMedications}` and `triage_evaluations.{decision, clinicalEvidence, clinicalCriteriaEval,
explanation, mlFeatures, diagnosis}` — the diagnosis, ICD-10 codes, free-text clinical justification,
and the AI's full decision/evidence trail.

**Deliberately left plaintext:** row-level access-control columns (`patientId`, `createdBy`),
reviewer/queue columns (`status`, `reviewedBy`, `decisionSource`), and general identity/insurance
JSONB (`patient`, `provider`, `insurance`) — administrative data, not clinical content, and in several
cases the exact columns row-level access control depends on staying queryable.

Additional layers: RDS storage encryption (provisioned at the infrastructure level), TLS in transit
to the database, and bcrypt-hashed credentials with JWT session tokens. Encryption at rest narrows
one specific risk — database or disk compromise — and does not by itself constitute full regulatory
compliance; see [Known Limitations](#known-limitations).

## Application Roles

| Role | What they do |
|---|---|
| **Doctor** | Submits new authorization requests, uploads supporting documents, tracks their own patients' request status and AI decisions |
| **Nurse** | Reviews the AI-ranked queue of PEND cases, approves or requests more information (cannot deny) |
| **Insurance Admin** | Full reviewer authority (approve/deny/request-info), analytics dashboard, audit trail, policy explorer |
| **Patient** | Read-only view of their own requests, diagnosis, decision, and documents — no reviewer actions |

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React, Vite, `react-three-fiber` (dashboard visualizations) |
| Backend API | Node.js, Express, Sequelize |
| Triage service | Python, FastAPI, LangGraph, scikit-learn |
| Priority service | Python, FastAPI, LangGraph, XGBoost |
| LLM | Groq (`openai/gpt-oss-120b`), real tool-calling |
| Primary database | PostgreSQL 17 + `pgvector` |
| Agent checkpoint store | MongoDB Atlas |
| Auth | JWT, bcrypt |
| Deployment | AWS ECS Fargate, RDS, S3, ALB — provisioned via AWS Copilot |

## Project Structure

```
Practice_CTS/
├── ProAuth_AI_FrontEnd/        React app — Doctor/Nurse/Insurance/Patient panels
├── ProAuth_AI_BackEnd/         Node/Express API, PostgreSQL models, auth, review workflow
├── ProAuth_AI_ML/
│   ├── policy-rag/             FastAPI triage service — RAG, agents, gates, decision model
│   │   ├── agents/               Policy/Clinical/Document/Coverage-Reasoning/Companion agents
│   │   ├── rag/                  pgvector retrieval
│   │   ├── ml/                   Trained decision model
│   │   └── triage_graph.py       LangGraph orchestration
│   └── priority_intelligence/  FastAPI priority service — XGBoost ranker
│       ├── agent/                Priority Agent (LangGraph)
│       ├── ranker.py, safety.py, tiers.py
├── copilot/                    AWS Copilot service manifests
├── iam/                        Deployment IAM policy
└── DEPLOYMENT.md                Full AWS deployment reference
```

## Database

15 tables in PostgreSQL, the two most central being:

- **`authorizations`** — one row per submitted request; patient/provider/insurance/clinical detail,
  mostly JSONB, encrypted where clinical.
- **`triage_evaluations`** — one row per automated evaluation; the full agent evidence trail plus
  the model's decision, encrypted where clinical/decision content.

No formal migration framework exists yet (`sequelize.sync({ alter: true })` on boot); the encryption
rollout was applied via a dedicated one-time migration script rather than relying on that mechanism.

## Running Locally

Requires Node.js, Python 3.11+, Docker (for PostgreSQL), and a Groq API key.

```bash
# 1. Database
cd ProAuth_AI_BackEnd && docker compose up -d

# 2. Backend
cd ProAuth_AI_BackEnd && npm install && cp .env.example .env   # fill in secrets
npm run dev

# 3. Triage service
cd ProAuth_AI_ML/policy-rag && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp ../.env.example ../.env   # fill in GROQ_AGENT_API_KEY, DATABASE_URL, MONGODB_URI
.venv/bin/python3 -m uvicorn main:app --host 0.0.0.0 --port 8002

# 4. Frontend
cd ProAuth_AI_FrontEnd && npm install && npm run dev
```

## Deployment (AWS)

Provisioned via AWS Copilot CLI — ECS Fargate for all three services behind a shared ALB, RDS for
PostgreSQL (storage-encrypted), S3 for the trained model artifact, secrets in SSM Parameter Store.
Full architecture, IAM policy, and step-by-step commands are in `DEPLOYMENT.md`.

## Testing

```bash
cd ProAuth_AI_ML/policy-rag && .venv/bin/python3 -m pytest tests/test_gates_unit.py -q
```

Unit tests cover all nine safety gates in isolation; integration scenarios in
`tests/test_triage_integration.py` exercise real, previously live-verified request/outcome pairs
against the actual pipeline.

