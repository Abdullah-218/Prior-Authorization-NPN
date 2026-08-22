# ProAuth AI

> **AI-assisted prior authorization for healthcare — evidence-grounded, policy-aware, explainable, and human-reviewed.**

ProAuth AI automates the evidence-gathering and risk-triage steps of medical prior authorization (PA) requests, while keeping every approval, denial, and edge case under deterministic safety rules and final human review. It combines retrieval-augmented policy lookup, a small team of specialized agents, a trained decision model, and a priority-ranking system — wired into a real multi-role web application backed by PostgreSQL, MongoDB, and AWS.


ProAuth AI is a full-stack healthcare prior-authorization platform that combines **RAG-based policy retrieval, specialized AI agents, machine-learning decision intelligence, pending-case prioritization, LangGraph orchestration, PostgreSQL/pgvector, MongoDB checkpointing, and a multi-role web application**.

---

## Table of Contents

1. [Problem Statement](#problem-statement)
2. [Solution](#solution)
3. [Objectives](#objectives)
4. [Core Design Principle](#core-design-principle)
5. [System Architecture](#system-architecture)
6. [End-to-End Workflow](#end-to-end-workflow)
7. [Agentic Intelligence](#agentic-intelligence)
8. [Policy Retrieval — RAG](#policy-retrieval--rag)
9. [ML Decision Intelligence](#ml-decision-intelligence)
10. [Priority Intelligence](#priority-intelligence)
11. [Application Roles](#application-roles)
12. [Data Architecture](#data-architecture)
13. [Data Security](#data-security)
14. [Technology Stack](#technology-stack)
15. [Project Structure](#project-structure)
16. [Deployment](#deployment)
17. [Testing](#testing)

---

# Problem Statement

Prior authorization is the approval a health insurer requires before certain treatments, procedures, or medications are covered.

Traditional prior-authorization workflows can be:

- **Slow** — requests may wait for manual policy and clinical review.
- **Inconsistent** — outcomes can depend heavily on individual reviewer interpretation.
- **Opaque** — providers and patients may not understand which criteria or evidence affected a request.
- **Evidence-heavy** — reviewers must cross-reference policy requirements with clinical records and submitted documents.
- **Difficult to prioritize** — pending cases may remain in submission order even when urgency or SLA pressure changes.

ProAuth AI addresses these challenges by bringing policy retrieval, evidence extraction, structured evaluation, machine learning, and reviewer prioritization into a single workflow.

---

# Solution

ProAuth AI provides an evidence-grounded prior-authorization pipeline.

A doctor submits an authorization request with clinical information and supporting documents. The system then:

1. Identifies the applicable coverage policy.
2. Retrieves relevant policy evidence using RAG.
3. Extracts and evaluates clinical information.
4. Checks required documentation.
5. Assembles structured evidence and policy criteria.
6. Uses the trained ML decision model for requests that reach model evaluation.
7. Produces an explainable recommendation:
   - **APPROVE**
   - **PEND**
   - **MORE INFORMATION**
8. Sends pending cases to a separate priority-intelligence pipeline.
9. Ranks pending cases for nurses using an XGBoost ranking model.
10. Provides human reviewers with evidence, reasoning, policy context, and prioritization information.

The goal is not to replace clinical or insurance reviewers. The goal is to reduce repetitive evidence-gathering work and make human review faster, more consistent, and more explainable.

---

# Objectives

- Reduce the time required to evaluate prior-authorization requests.
- Ground authorization evaluation in actual payer policy evidence.
- Separate evidence gathering from final ML decision intelligence.
- Make recommendations explainable and auditable.
- Identify missing clinical or administrative evidence.
- Prioritize pending cases according to urgency, clinical risk, and SLA pressure.
- Maintain a human-review workflow for cases requiring manual attention.
- Protect sensitive clinical and decision data.
- Provide separate interfaces for doctors, nurses, insurance administrators, and patients.

---

# Core Design Principle

## Agents Gather Evidence. Models Provide Intelligence.

ProAuth AI deliberately separates **evidence gathering**, **orchestration**, and **machine-learning decisions**.

AI agents are responsible for tasks such as:

- Retrieving policy evidence.
- Extracting clinical facts.
- Evaluating policy criteria.
- Producing explanations.
- Coordinating queue prioritization.

The ML models operate on structured numerical features produced by these stages.

```text
Policy Evidence
      +
Clinical Evidence
      +
Documentation Evidence
      +
Structured Reasoning
      ↓
Machine Learning
      ↓
Authorization Recommendation
```

For pending requests:

```text
Pending Case
      ↓
Queue Features
      ↓
XGBoost Ranking Model
      ↓
Safety-aware Priority Score
      ↓
Nurse Review Queue
```

---

# System Architecture

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PROAUTH AI PLATFORM                                 │
└─────────────────────────────────────────────────────────────────────────────┘

                         USER APPLICATIONS
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  ┌───────────┐
│      DOCTOR      │  │      NURSE       │  │ INSURANCE ADMIN  │  │  PATIENT  │
│                  │  │                  │  │                  │  │           │
│ Submit PA        │  │ Review Queue     │  │ Analytics        │  │ View PA   │
│ Upload Evidence  │  │ Prioritize Cases │  │ Policy Explorer  │  │ Status    │
│ Track Requests   │  │ Review Evidence  │  │ Audit Trail      │  │ Documents │
└────────┬─────────┘  └────────┬─────────┘  └────────┬─────────┘  └─────┬─────┘
         │                     │                     │                  │
         └─────────────────────┴─────────────────────┴──────────────────┘
                                       │
                                  REST APIs
                                       │
                         ┌─────────────▼─────────────┐
                         │    NODE.JS / EXPRESS      │
                         │                           │
                         │ Auth · Authorizations     │
                         │ Documents · Reviews       │
                         │ Queue · Audit · Analytics  │
                         └─────────────┬─────────────┘
                                       │
                              ┌────────▼────────┐
                              │  PYTHON TRIAGE  │
                              │    FASTAPI      │
                              └────────┬─────────┘
                                       │
                              ┌────────▼─────────┐
                              │    LANGGRAPH     │
                              │  ORCHESTRATION   │
                              └────────┬─────────┘
                                       │
              ┌────────────────────────┼─────────────────────────┐
              │                        │                         │
      ┌───────▼───────┐      ┌────────▼────────┐      ┌────────▼────────┐
      │  POLICY/RAG   │      │ CLINICAL AGENT  │      │ DOCUMENT AGENT  │
      │   EVIDENCE    │      │                 │      │                 │
      └───────┬───────┘      └────────┬────────┘      └────────┬────────┘
              │                       │                        │
              └───────────────────────┼────────────────────────┘
                                      │
                              ┌───────▼────────┐
                              │    REASONING   │
                              │    ASSEMBLY    │
                              └───────┬────────┘
                                      │
                              ┌───────▼────────┐
                              │  ML DECISION   │
                              │    MODEL       │
                              └───────┬────────┘
                                      │
                              APPROVE / PEND /
                              MORE INFORMATION
                                      │
                                      ▼
                              ┌───────────────┐
                              │   COMPANION   │
                              │   EXPLANATION │
                              └───────────────┘


                    POLICY EVIDENCE STORAGE
┌─────────────────────────────────────────────────────────────────────────────┐
│ PostgreSQL 17 + pgvector                                                    │
│                                                                             │
│ Structured application data + policy corpus + vector embeddings             │
└─────────────────────────────────────────────────────────────────────────────┘

                    AGENT STATE / CHECKPOINTING
┌─────────────────────────────────────────────────────────────────────────────┐
│ MongoDB Atlas                                                               │
│                                                                             │
│ LangGraph checkpoints · request context · resubmission state · thread state │
└─────────────────────────────────────────────────────────────────────────────┘


                    PENDING QUEUE INTELLIGENCE
┌─────────────────────────────────────────────────────────────────────────────┐
│ Priority Intelligence Service                                               │
│                                                                             │
│ LangGraph Priority Agent → Feature Computation → XGBoost Ranker             │
│ → Safety-aware ranking → Nurse Queue                                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

# End-to-End Workflow

## 1. Authorization Submission

A doctor submits:

- Patient information
- Diagnosis / ICD-10 information
- Requested treatment or procedure
- Clinical justification
- Provider information
- Insurance information
- Treatment urgency
- Place of service
- Supporting documents

The authorization is stored in PostgreSQL.

## 2. Policy Identification

The Policy Evidence Agent determines which coverage policy applies to the request.

The policy becomes the central source of truth for downstream evaluation.

```text
Authorization
      ↓
Policy Identification
      ↓
Applicable Policy
```

## 3. RAG Policy Retrieval

The RAG layer searches the policy corpus stored in PostgreSQL with pgvector.

```text
Policy Documents
      ↓
Text Chunking
      ↓
Embedding Model
      ↓
Vector Embeddings
      ↓
PostgreSQL + pgvector
      ↓
Semantic Similarity Search
      ↓
Relevant Policy Chunks
```

Retrieved evidence is passed to the Policy Evidence Agent.

## 4. Clinical and Documentation Evaluation

The Clinical Evidence Agent extracts clinical facts and evaluates them against the policy criteria.

The Document Agent checks which required document types are available.

## 5. Structured Reasoning

The Coverage Reasoning Agent combines policy, clinical, and documentation evidence into the structured feature representation required by the ML model.

## 6. ML Decision

The Logistic Regression model evaluates requests that reach model evaluation and produces the authorization recommendation and confidence.

## 7. Explanation

The Companion Agent generates a human-readable explanation from the already-established evidence and decision.

## 8. Pending Queue

When a request is `PEND`, it enters the separate Priority Intelligence pipeline.

```text
PEND
 ↓
Priority Agent
 ↓
Queue Features
 ↓
XGBoost Ranker
 ↓
Priority Score
 ↓
Nurse Queue
```

---

# Agentic Intelligence

| Agent | Purpose | LLM | Main Responsibility |
|---|---|---:|---|
| **Policy Evidence Agent** | Policy intelligence | Yes | Retrieves and interprets policy evidence |
| **Clinical Evidence Agent** | Clinical intelligence | Yes | Extracts clinical facts and evaluates policy criteria |
| **Document Agent** | Documentation intelligence | No | Checks submitted documents against requirements |
| **Coverage Reasoning Agent** | Evidence assembly | No | Builds structured decision features and evaluation state |
| **Companion Agent** | Explainability | Yes | Generates human-readable evidence-grounded explanations |
| **Priority Agent** | Queue intelligence | No | Coordinates pending-case ranking using XGBoost |

## Policy Evidence Agent

The Policy Evidence Agent:

1. Receives authorization context.
2. Uses the RAG retrieval tool.
3. Retrieves relevant policy evidence.
4. Identifies the applicable policy.
5. Extracts coverage information.
6. Identifies named clinical criteria.
7. Identifies required documentation.
8. Returns structured policy evidence.

## Clinical Evidence Agent

The Clinical Evidence Agent:

- Extracts diagnosis information.
- Interprets clinical justification.
- Evaluates diagnosis support.
- Evaluates named policy criteria.
- Produces structured PASS / FAIL / UNKNOWN results.
- Calculates clinical evidence metrics.

## Document Agent

The Document Agent checks whether evidence required by the policy has been submitted.

```text
Policy requires:
✓ Clinical Notes
✓ Prescription
✓ Laboratory Report

Submitted:
✓ Clinical Notes
✓ Prescription
✗ Laboratory Report
```

## Coverage Reasoning Agent

The Coverage Reasoning Agent is the deterministic assembly layer.

It receives policy, clinical, and documentation evidence and converts them into the structured representation required by the decision model.

## Companion Agent

The Companion Agent runs after decision intelligence has produced an outcome.

It converts structured results into understandable language for users and does not override the underlying decision.

---

# Policy Retrieval — RAG

## Vector Store

The project uses:

**PostgreSQL 17 + pgvector**

The vector store is integrated into the primary PostgreSQL environment.

## Embedding Pipeline

```text
Policy Document
      ↓
Text Extraction
      ↓
Chunking
      ↓
Sentence Transformer
      ↓
384-dimensional Embedding
      ↓
pgvector
```

Embedding model:

```text
sentence-transformers/all-MiniLM-L6-v2
```

## Retrieval Pipeline

```text
Authorization
      ↓
Payer / Coverage Context
      ↓
Vector Search
      ↓
Cosine Similarity
      ↓
Top Policy Chunks
      ↓
Policy Evidence Agent
```

The retrieved chunks provide evidence for policy interpretation rather than relying solely on the LLM's pretrained knowledge.

---

# ML Decision Intelligence

The primary triage model is a:

**Logistic Regression classifier**

implemented using a scikit-learn pipeline with standardization.

The model uses four structured features:

| Feature | Description |
|---|---|
| `policy_score` | How strongly the retrieved policy evidence applies to the request |
| `documentation_score` | Proportion of required documents available |
| `clinical_evidence_score` | Proportion of policy clinical criteria satisfied |
| `diagnosis_supported` | Whether the diagnosis is supported by the policy |

```text
Policy Agent
     │
     └── policy_score

Document Agent
     │
     └── documentation_score

Clinical Agent
     │
     ├── clinical_evidence_score
     └── diagnosis_supported

             ↓
      Feature Vector
             ↓
     Logistic Regression
             ↓
       ML Confidence
             ↓
     APPROVE / PEND
```

The model is intentionally bounded to a small, auditable feature set.

---

# Priority Intelligence

A separate ML system is used for pending-case prioritization.

It does **not** make the original authorization decision.

Its purpose is:

> **Determine which pending authorization should be reviewed first.**

## Priority Workflow

```text
PEND Authorization
       ↓
Priority Agent
       ↓
Validate Queue Case
       ↓
Calculate Queue Features
       ↓
XGBoost Ranker
       ↓
Safety-aware Priority
       ↓
Priority Tier + Reasons
       ↓
Nurse Dashboard
```

## Priority Agent

The Priority Agent is implemented as a separate LangGraph workflow.

It coordinates:

1. Validation
2. Feature preparation
3. ML ranking
4. Safety handling
5. Priority tier generation
6. Human-readable reason generation

It does not make LLM calls.

## XGBoost Priority Ranker

The priority model is an:

**XGBoost Ranker (`rank:ndcg`)**

It ranks PEND cases relative to one another.

### Nine features

| Feature | Source |
|---|---|
| `policy_score` | Original triage evaluation |
| `documentation_score` | Original triage evaluation |
| `clinical_evidence_score` | Original triage evaluation |
| `num_criteria_missing` | Original triage evaluation |
| `hours_pending` | Calculated from submission time |
| `sla_pressure` | Calculated from waiting time and SLA |
| `urgency_weight` | Treatment urgency |
| `care_setting_weight` | Place of service |
| `clinical_risk_weight` | Derived clinical risk |

Some queue values are recalculated because waiting time and SLA pressure change while a case remains pending.

## Priority Safety Handling

The XGBoost prediction is combined with deterministic safety handling:

| Condition | Minimum Priority |
|---|---:|
| Emergency | 90 |
| SLA breached | 88 |
| SLA breach imminent | 80 |

The final queue is automatically organized for nurses.

---

# Application Roles

| Role | Responsibilities |
|---|---|
| **Doctor** | Submit authorization requests, upload evidence, track request status |
| **Nurse** | Review prioritized PEND cases, inspect evidence, approve or request additional information |
| **Insurance Admin** | Review authorizations, analytics, audit trail, policy intelligence |
| **Patient** | View personal requests, status, decisions, and documents |

---

# Data Architecture

```text
                         PROAUTH AI
                              │
             ┌────────────────┴────────────────┐
             │                                 │
       PostgreSQL                         MongoDB Atlas
             │                                 │
     Application Data                 LangGraph State
     Policy Corpus                    Checkpoints
     pgvector                         Thread Context
     Authorization Data               Resubmission State
     Triage Evaluations
```

## PostgreSQL

PostgreSQL is the primary application database.

It stores:

- Users
- Patients
- Providers
- Insurance information
- Authorization requests
- Documents and metadata
- Triage evaluations
- Review information
- Audit information
- Policy information
- Policy chunks
- Vector embeddings
- Other application entities

The application uses:

```text
PostgreSQL 17
+
Sequelize
+
pgvector
```

## Vectorized Policy Data

```text
Policy
│
├── Policy Metadata
├── Chunk 1 ──→ 384-d vector
├── Chunk 2 ──→ 384-d vector
├── Chunk 3 ──→ 384-d vector
├── Chunk 4 ──→ 384-d vector
└── ...
```

The vectors allow the RAG layer to find policy passages semantically related to an authorization request.

## MongoDB Atlas

MongoDB Atlas is used for LangGraph state and checkpointing.

It supports:

- LangGraph checkpoints
- Agent state
- Evidence trails
- Request continuity
- Resubmission handling
- Context-aware processing

Request-level identifiers such as:

```text
authorization_id
thread_id
```

allow the system to maintain processing context.

## Resubmission and Context-Aware Processing

```text
Initial Authorization
        │
        ├── authorization_id
        └── thread_id
              │
              ▼
        Agent Processing
              │
              ▼
        Decision / PEND
              │
              ▼
      Additional Evidence
              │
              ▼
        Resubmission
              │
              ▼
      Context-aware Processing
```

---

# Data Security

Clinical and decision information is encrypted at rest using:

**AES-256-GCM**

Sensitive fields include information such as:

- Diagnosis
- ICD-10 information
- Clinical justification
- Current medications
- Clinical evidence
- Clinical criteria evaluation
- ML features
- Decision explanation

Additional security mechanisms include:

- PostgreSQL/RDS storage encryption
- TLS in transit
- bcrypt password hashing
- JWT authentication
- Role-based application access

Encryption at rest is one security layer and does not by itself constitute complete regulatory compliance.

---

# Technology Stack

| Layer | Technology |
|---|---|
| Frontend | React, Vite |
| Visualization | react-three-fiber |
| Backend | Node.js, Express |
| ORM | Sequelize |
| Triage API | Python, FastAPI |
| Workflow Orchestration | LangGraph |
| LLM | Groq |
| LLM Model | `openai/gpt-oss-120b` |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` |
| Vector Search | PostgreSQL + pgvector |
| Primary Database | PostgreSQL 17 |
| Agent State | MongoDB Atlas |
| Decision ML | scikit-learn Logistic Regression |
| Priority ML | XGBoost Ranker |
| Authentication | JWT + bcrypt |
| Cloud | AWS |
| Containers | ECS Fargate |
| Database Hosting | Amazon RDS |
| Model Artifacts | Amazon S3 |
| Load Balancing | Application Load Balancer |
| Infrastructure | AWS Copilot |

---

# Project Structure

```text
Practice_CTS/
│
├── ProAuth_AI_FrontEnd/
│   └── React/Vite applications
│       ├── Doctor
│       ├── Nurse
│       ├── Insurance Admin
│       └── Patient
│
├── ProAuth_AI_BackEnd/
│   └── Node.js / Express API
│       ├── Authentication
│       ├── Authorizations
│       ├── Documents
│       ├── Reviews
│       ├── Queue
│       ├── Analytics
│       └── Audit
│
├── ProAuth_AI_ML/
│   │
│   ├── policy-rag/
│   │   ├── agents/
│   │   │   ├── Policy Agent
│   │   │   ├── Clinical Agent
│   │   │   ├── Document Agent
│   │   │   ├── Coverage Reasoning
│   │   │   └── Companion Agent
│   │   ├── rag/
│   │   │   └── pgvector retrieval
│   │   ├── ml/
│   │   │   └── Logistic Regression model
│   │   └── triage_graph.py
│   │
│   └── priority_intelligence/
│       ├── agent/
│       │   └── Priority LangGraph
│       ├── ranker.py
│       ├── safety.py
│       └── tiers.py
│
├── copilot/
│   └── AWS service manifests
│
├── iam/
│   └── IAM policies
│
└── DEPLOYMENT.md
```

---

# Deployment

ProAuth AI is designed for AWS deployment using AWS Copilot.

```text
                         AWS
                          │
              ┌───────────▼───────────┐
              │ Application Load       │
              │ Balancer               │
              └───────────┬───────────┘
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
        ▼                 ▼                 ▼
   Frontend           Backend          ML Services
   ECS Fargate        ECS Fargate      ECS Fargate
        │                 │                 │
        └─────────────────┼─────────────────┘
                          │
                 ┌────────▼────────┐
                 │ Amazon RDS       │
                 │ PostgreSQL       │
                 └─────────────────┘

                 Amazon S3
                      │
               Model Artifacts

              SSM Parameter Store
                      │
                   Secrets
```

Deployment components include:

- AWS ECS Fargate
- Amazon RDS PostgreSQL
- Amazon S3
- Application Load Balancer
- AWS Copilot
- SSM Parameter Store
- IAM policies

---

# Local Development

## Prerequisites

- Node.js
- Python 3.11+
- Docker
- PostgreSQL
- MongoDB Atlas connection
- Groq API key

## 1. Start PostgreSQL

```bash
cd ProAuth_AI_BackEnd
docker compose up -d
```

## 2. Start Backend

```bash
cd ProAuth_AI_BackEnd

npm install

cp .env.example .env

npm run dev
```

## 3. Start Triage Service

```bash
cd ProAuth_AI_ML/policy-rag

python3 -m venv .venv

.venv/bin/pip install -r requirements.txt

.venv/bin/python3 -m uvicorn main:app --host 0.0.0.0 --port 8002
```

Configure:

```text
GROQ_AGENT_API_KEY
DATABASE_URL
MONGODB_URI
```

## 4. Start Frontend

```bash
cd ProAuth_AI_FrontEnd

npm install

npm run dev
```

---

# Testing

Run the triage tests:

```bash
cd ProAuth_AI_ML/policy-rag

.venv/bin/python3 -m pytest tests/test_gates_unit.py -q
```

Integration scenarios are available in:

```text
tests/test_triage_integration.py
```

---

# Complete Workflow

```text
                         DOCTOR
                           │
                           ▼
                 AUTHORIZATION REQUEST
                           │
                           ▼
                 POLICY IDENTIFICATION
                           │
                           ▼
                    RAG RETRIEVAL
                           │
                           ▼
                    POLICY EVIDENCE
                           │
             ┌─────────────┼─────────────┐
             │             │             │
             ▼             ▼             ▼
        POLICY AGENT   CLINICAL AGENT  DOCUMENT AGENT
             │             │             │
             └─────────────┼─────────────┘
                           │
                           ▼
                 COVERAGE REASONING
                           │
                           ▼
                  FEATURE GENERATION
                           │
                           ▼
                 LOGISTIC REGRESSION
                           │
                    ┌──────┴──────┐
                    ▼             ▼
                 APPROVE          PEND
                    │             │
                    │             ▼
                    │       PRIORITY AGENT
                    │             │
                    │             ▼
                    │       XGBOOST RANKER
                    │             │
                    │             ▼
                    │      PRIORITIZED QUEUE
                    │             │
                    │             ▼
                    │           NURSE
                    │
                    ▼
              COMPANION AGENT
                    │
                    ▼
          EXPLAINABLE AI OUTPUT
```

---

# ProAuth AI Philosophy

### 1. Ground decisions in policy evidence

Retrieve relevant policy information before interpreting coverage.

### 2. Separate evidence from decision intelligence

Specialized agents gather and structure evidence, while trained ML models operate on bounded, structured inputs.

### 3. Keep humans in the loop

Cases requiring additional evidence, clinical judgment, or reviewer attention remain visible to human reviewers, while the priority-intelligence system helps determine **which pending case deserves attention first**.

---

## ProAuth AI

**Evidence-grounded prior authorization intelligence for faster, more transparent healthcare authorization workflows.**
