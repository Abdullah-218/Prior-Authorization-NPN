"""
Policy Evidence Retrieval Tool
================================

Confidence-gated RAG retrieval over policy_chunks. This is the tool the
Policy Evidence Agent will call once the LangGraph agent layer exists —
built and proven standalone first, so the confidence-gating logic is
verified before any agent wraps it.

Retrieval order matches the "structured metadata first, then semantic"
requirement: an optional payer/jurisdiction/policy_type filter narrows the
candidate set via a plain SQL WHERE clause, then cosine similarity ranks
within that set — never a blind vector search across every policy.

Confidence thresholds are empirical, measured against this project's real
corpus (23 CMS NCDs), not picked arbitrarily:
  distance <= 0.35   HIGH   — genuinely on-topic (e.g. "home blood glucose
                              monitor" -> NCD-40.2, distance 0.28)
  distance <= 0.50   MEDIUM — thematically related, not a precise hit (e.g.
                              "diabetes management" -> NCD-40.3, 0.45)
  distance >  0.50   LOW    — do not present as evidence (e.g. "diabetic
                              foot care" against this corpus, 0.58+ — the
                              corpus has nothing on this, and the top match
                              is a coincidental keyword overlap, not real
                              guidance)

Usage:
    from rag.retrieval import retrieve_policy_evidence
    result = retrieve_policy_evidence("home blood glucose monitor coverage")
"""
import os

import psycopg2
from dotenv import load_dotenv
from pgvector.psycopg2 import register_vector
from sentence_transformers import SentenceTransformer

load_dotenv()

EMBEDDING_MODEL = "all-MiniLM-L6-v2"
PRIVATE_PAYER_GROUP = ["Aetna", "Cigna", "UnitedHealthcare"]

HIGH_CONFIDENCE_MAX_DISTANCE = 0.35
MEDIUM_CONFIDENCE_MAX_DISTANCE = 0.50

MAX_PER_SECTION = 3

STAGE1_MAX_CANDIDATE_POLICIES = 3  # covers the observed 2-relevant-policy case (Aetna knee + Cigna TKA) with headroom for a 3rd

STAGE2_MAX_CHUNKS_PER_POLICY = 8  # was 50 — still covers a well-structured policy's most relevant sections; a genuinely huge policy's long tail was never the strongest evidence anyway (distance-sorted)
DEFAULT_MAX_TOTAL_CHUNKS = 18  # was 60 — the real, binding cap on total evidence-payload token cost per LLM call

STAGE1_RELATIVE_MARGIN = 0.10

POLICY_EVIDENCE_UNAVAILABLE_MESSAGE = (
    "No policy evidence was found that confidently covers this request. "
    "This system does not fabricate a coverage rule it doesn't actually have — "
    "it routes to human review instead."
)

_model = None


def _get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model


def _get_connection():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    register_vector(conn)
    return conn


def get_plan_payer(plan_id):
    """
    Resolves an insurance_plans.planId (e.g. "PLAN001") to its payerName
    (e.g. "Medicare"), OR to PRIVATE_PAYER_GROUP when the plan's stored
    payerName is the "Private" sentinel (a consolidated Silver/Gold/Premium
    plan not tied to one specific payer brand — see PRIVATE_PAYER_GROUP's
    comment). This is the deterministic half of policy-type-aware
    retrieval — which payer's (or payers') policies even apply to a
    request is a fact looked up from the patient's actual plan, never
    something an LLM decides or is trusted to remember to filter by.
    Returns None if the plan doesn't exist (caller should treat that as
    "no payer scope, proceed cautiously" rather than silently searching
    everything).
    """
    conn = _get_connection()
    cur = conn.cursor()
    try:
        cur.execute('SELECT "payerName" FROM insurance_plans WHERE "planId" = %s', (plan_id,))
        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()
    if not row:
        return None
    return PRIVATE_PAYER_GROUP if row[0] == "Private" else row[0]

TIER_COST_SHARE_PERCENT = {
    "SILVER": 60,
    "GOLD": 80,
    "PREMIUM": 95,
}


def get_plan_tier(plan_id):
    """
    Resolves an insurance_plans.planId to its cost-sharing tier (e.g.
    "GOLD"), or None for Medicare/any plan with no tier set. Purely for
    the Companion Agent's informational note — see TIER_COST_SHARE_PERCENT.
    """
    conn = _get_connection()
    cur = conn.cursor()
    try:
        cur.execute('SELECT tier FROM insurance_plans WHERE "planId" = %s', (plan_id,))
        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()
    return row[0] if row and row[0] else None


def get_policy_status(policy_id):
    """
    Resolves a policies.policyId (e.g. "AETNA-BARIATRIC-0157") to its
    status (e.g. "ACTIVE"). Used by the Rule/Score Engine's policy_active
    feature — every ingested policy is ACTIVE today (no inactive/
    deprecated policy exists in the corpus yet), but this looks it up for
    real rather than hardcoding True, so it stays correct once that
    changes. Returns None if the policy doesn't exist.
    """
    conn = _get_connection()
    cur = conn.cursor()
    try:
        cur.execute('SELECT status FROM policies WHERE "policyId" = %s', (policy_id,))
        row = cur.fetchone()
    finally:
        cur.close()
        conn.close()
    return row[0] if row else None


def retrieve_policy_evidence(query, payer=None, jurisdiction=None, policy_type=None, max_total_chunks=DEFAULT_MAX_TOTAL_CHUNKS):
    """
    Structured, confidence-gated retrieval. Never invents evidence and
    never silently presents a weak match as a real one.

    Two-stage (2026-08-20+, see STAGE1_MAX_CANDIDATE_POLICIES's comment
    above for why): stage 1 identifies which few policies are actually
    relevant; stage 2 pulls deeply from just those, instead of one flat
    cap shared across the entire payer-group union. max_total_chunks is a
    final safety ceiling on the merged, distance-sorted result — it only
    ever trims the rare case where several large policies are ALL
    genuinely relevant to one query, never the common single-policy case.

    Returns:
    {
      "policyFound": bool,
      "confidence": "HIGH" | "MEDIUM" | "LOW" | "NONE",
      "evidence": [ {policyId, policyName, section, text, distance}, ... ],
      "message": str | None,  # user/Companion-Agent-facing text — only set when policyFound is False
      "reason": str | None,   # technical detail for logs/audit — only set when policyFound is False
    }
    """
    model = _get_model()
    embedding = model.encode(query, normalize_embeddings=True).tolist()

    conn = _get_connection()
    cur = conn.cursor()
    try:
        where_clauses, params = [], []
        if payer:
            # payer is a list for a consolidated Private-tier plan (see
            # PRIVATE_PAYER_GROUP) — searches the union of every real
            # private payer's corpus. A plain string (e.g. "Medicare")
            # still does exact equality, unchanged.
            if isinstance(payer, (list, tuple)):
                where_clauses.append("pc.payer = ANY(%s)")
                params.append(list(payer))
            else:
                where_clauses.append("pc.payer = %s")
                params.append(payer)
        if jurisdiction:
            where_clauses.append("pc.jurisdiction = %s")
            params.append(jurisdiction)
        if policy_type:
            where_clauses.append('p."policyType" = %s')
            params.append(policy_type)
        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        # ─── Stage 1: which policy/policies are actually relevant? ──────────
        # Cheap — one GROUP BY over the same distance calc, ranking each
        # DISTINCT policy by its own single closest chunk.
        cur.execute(
            f'''SELECT p."policyId", MIN(pc.embedding <=> %s::vector) AS best_distance
                FROM policy_chunks pc
                JOIN policies p ON p.id = pc."policyId"
                {where_sql}
                GROUP BY p."policyId"
                ORDER BY best_distance ASC
                LIMIT %s''',
            [embedding] + params + [STAGE1_MAX_CANDIDATE_POLICIES],
        )
        candidate_policies = cur.fetchall()

        if not candidate_policies:
            return {
                "policyFound": False,
                "confidence": "NONE",
                "evidence": [],
                "message": POLICY_EVIDENCE_UNAVAILABLE_MESSAGE,
                "reason": "No policy chunks matched the given filters — payer/jurisdiction/policy_type may be too narrow, or the corpus has no coverage in this area at all.",
            }

        best_distance = candidate_policies[0][1]

        candidate_policy_ids = [
            row[0] for row in candidate_policies if row[1] <= best_distance + STAGE1_RELATIVE_MARGIN
        ]

        cur.execute(
            '''WITH scored AS (
                    SELECT p."policyId", p."policyName", pc.section, pc."chunkText",
                           pc.embedding <=> %s::vector AS distance
                    FROM policy_chunks pc
                    JOIN policies p ON p.id = pc."policyId"
                    WHERE p."policyId" = ANY(%s)
                ),
                section_ranked AS (
                    SELECT *, ROW_NUMBER() OVER (
                        PARTITION BY "policyId", section ORDER BY distance ASC
                    ) AS section_rank
                    FROM scored
                ),
                policy_ranked AS (
                    SELECT *, ROW_NUMBER() OVER (
                        PARTITION BY "policyId" ORDER BY distance ASC
                    ) AS policy_rank
                    FROM section_ranked
                    WHERE section_rank <= %s
                )
                SELECT "policyId", "policyName", section, "chunkText", distance
                FROM policy_ranked
                WHERE policy_rank <= %s
                ORDER BY distance ASC
                LIMIT %s''',
            [embedding, candidate_policy_ids, MAX_PER_SECTION, STAGE2_MAX_CHUNKS_PER_POLICY, max_total_chunks],
        )
        rows = cur.fetchall()
    finally:
        cur.close()
        conn.close()

    if best_distance <= HIGH_CONFIDENCE_MAX_DISTANCE:
        confidence = "HIGH"
    elif best_distance <= MEDIUM_CONFIDENCE_MAX_DISTANCE:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    evidence = [
        {"policyId": r[0], "policyName": r[1], "section": r[2], "text": r[3], "distance": round(r[4], 4)}
        for r in rows
    ]

    if confidence == "LOW":
        return {
            "policyFound": False,
            "confidence": "LOW",
            "evidence": evidence,
            "message": POLICY_EVIDENCE_UNAVAILABLE_MESSAGE,
            "reason": (
                f"Best match distance {best_distance:.3f} exceeds the confidence threshold "
                f"({MEDIUM_CONFIDENCE_MAX_DISTANCE}) — nothing in the corpus genuinely covers this."
            ),
        }

    return {"policyFound": True, "confidence": confidence, "evidence": evidence, "message": None, "reason": None}
