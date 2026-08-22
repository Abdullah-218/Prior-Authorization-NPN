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

# A patient's PRIVATE-tier plan (Silver/Gold/Premium — see insurance_plans'
# "tier" column) is deliberately NOT tied to one specific real payer brand.
# Per explicit decision (2026-08-19): treat "Private" as one consolidated
# policy type whose retrieval scope is the UNION of every real private
# payer we've ingested, rather than scoping to a single payer and risking
# an honest "no evidence found" purely because THAT ONE payer happens to
# have no public bulletin for the requested category (a real, observed gap
# — e.g. UnitedHealthcare defers ~5 categories entirely to a licensed
# InterQual guideline with no public criteria text). Widening the scope to
# "any of our real private payers" still only ever surfaces genuine,
# grounded policy text — never Medicare, never a fabricated "combined"
# document — it just stops one payer's documentation gap from masking
# another payer's real, applicable coverage answer.
PRIVATE_PAYER_GROUP = ["Aetna", "Cigna", "UnitedHealthcare"]

HIGH_CONFIDENCE_MAX_DISTANCE = 0.35
MEDIUM_CONFIDENCE_MAX_DISTANCE = 0.50

# Caps how many candidates a single policy SECTION can supply within
# stage 2's per-policy pull (see below). Without this, a section that
# happens to be chunked more finely than its siblings within the SAME
# policy would systematically win every nearest-neighbor slot on any
# query that's merely topically adjacent — not because it's actually the
# better match, but because it has more, sharper candidates in the race.
# Mostly a defensive backstop now that items #40-42 (2026-08-20) fixed
# every policy's own sections down to ~1 chunk each in the normal case —
# kept for any future policy that isn't yet as well-structured.
MAX_PER_SECTION = 3

# Two-stage retrieval (2026-08-20+ — see docs/PROGRESS_TRACKER.md §9.8): a
# NEW bottleneck surfaced immediately after items #40-42 fixed
# MAX_PER_SECTION's starvation bug — every policy is now finely chunked
# (up to 46 real, independent chunks for one policy, e.g. Aetna knee
# arthroplasty), but the old single-stage query's flat `top_k` cap on the
# ENTIRE payer-group union meant one large, genuinely-relevant policy
# could crowd out most of its OWN branches just to stay under that shared
# ceiling — live-verified: a "total knee arthroplasty" query filled 11 of
# 16 slots from Aetna's 46-chunk policy alone, leaving ~35 of its own real
# criteria unreachable, not because they're irrelevant but because top_k
# ran out of room. Raising top_k globally would fix this but pays a token
# cost on EVERY query, including the common single-small-policy case that
# was never broken. Two-stage retrieval instead scales cost with how much
# a SPECIFIC query actually needs:
#   Stage 1 — identify WHICH policy/policies are actually relevant (cheap:
#   one GROUP BY query, ranks policies by their own best-matching chunk).
#   Stage 2 — pull DEEPLY from just those few policies (up to
#   STAGE2_MAX_CHUNKS_PER_POLICY each), not a flat cap shared by every
#   irrelevant policy in the corpus too.
# Confidence gating is UNCHANGED — still computed from the single best
# chunk distance found, exactly as before; only how many chunks get
# assembled around that best match changes.
STAGE1_MAX_CANDIDATE_POLICIES = 3  # covers the observed 2-relevant-policy case (Aetna knee + Cigna TKA) with headroom for a 3rd

# Lowered from 50/60 (2026-08-21, found live): the account this pipeline
# runs against has an 8000 TPM per-request cap, and a real query hitting
# these old caps genuinely returned 60 chunks (measured: ~7.3K chars of
# raw evidence text, ~18K chars once serialized as the tool-result JSON
# the Policy Evidence Agent sends back to Groq) — comfortably enough on
# its own, combined with the system prompt/tool schema/conversation
# overhead, to trip a real 413 "Request too large" on the very first LLM
# call, before any grading even happens. That failure isn't cosmetic: it
# cascades into clinicalCriteriaEval force-failing every criterion
# ("upstream policy evidence agent reported an error") and the decision
# routing to PEND on a false "no policy found," even though real,
# on-topic evidence was retrieved and simply never got interpreted.
# 60->60/60*18=~18 total chunks keeps the evidence payload to roughly a
# third of its old size — comfortably under budget even with the
# corrective retry in policy_evidence_agent.py added the same day, which
# re-sends this same payload once more when the LLM's own answer
# contradicts it. distance-sorted ordering is unchanged, so this only
# ever trims the LEAST relevant tail of an already-ranked result — the
# top, most on-topic evidence a query would have surfaced anyway is what
# survives.
STAGE2_MAX_CHUNKS_PER_POLICY = 8  # was 50 — still covers a well-structured policy's most relevant sections; a genuinely huge policy's long tail was never the strongest evidence anyway (distance-sorted)
DEFAULT_MAX_TOTAL_CHUNKS = 18  # was 60 — the real, binding cap on total evidence-payload token cost per LLM call

# Taking a fixed top-N candidate policies alone isn't enough — live-tested
# and found real noise: for "CPAP therapy for obstructive sleep apnea",
# rank 3 was AETNA-BARIATRIC-0157 (delta +0.151 from the #1 match) purely
# because sleep apnea is mentioned there as a bariatric-surgery
# comorbidity; for "multigene hereditary cancer panel testing", rank 3 was
# AETNA-SPINAL-CORD-STIM-0194 (delta +0.474) — genuinely unrelated, just
# closer than the corpus's other unrelated policies. Both would otherwise
# have contributed up to 50 chunks of pure noise into the Policy Agent's
# context. A relative margin from the SINGLE best match found filters
# these correctly: real second/third matches sit within ~0.01-0.04 of the
# best (e.g. Cigna TKA vs. Aetna knee arthroplasty, delta +0.007), while
# every observed false positive sits at +0.15 or beyond — even a
# plausible-seeming adjacent policy (Aetna HIP arthroplasty for a KNEE
# query, delta +0.173) is correctly excluded, since cross-joint evidence
# genuinely shouldn't inform a knee-specific decision despite the two
# policies' similar structure/language. 0.10 sits comfortably in the gap
# between both classes across all three cases tested.
STAGE1_RELATIVE_MARGIN = 0.10

# The user-facing explanation for POLICY_EVIDENCE_UNAVAILABLE — this is
# deliberately framed as a trust feature, not an apology. When this comes up
# live (and it will — no corpus covers every diagnosis), the honest framing
# is a differentiator: the system won't fabricate a coverage rule it doesn't
# actually have, it routes to human review instead. That's the whole point
# of grounding recommendations in retrieved evidence rather than just asking
# an LLM "should this be approved?" — see `reason` on the same result for
# the technical detail (distance/threshold), meant for logs/audit, not for
# display to a doctor or reviewer.
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


# Cost-share is DISPLAY-ONLY (2026-08-20, explicit instruction): "these
# should not affect the Agent working or ML scores — these should be as
# informational in explanation companion agent." Never read by the ML
# model, coverage_reasoning_agent.py's featureVector, or any gate — wired
# ONLY into main.py's informational_context, same non-decision-input
# lane as patient age. A static, non-payer-specific approximation (this
# system has no real per-plan benefit-design data to ground a precise
# figure), intentionally not a per-service/per-payer real number, so it's
# always phrased as an estimate, never cited as if it came from a policy.
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
        # Relative-margin filter — see STAGE1_RELATIVE_MARGIN's comment for
        # the real false-positive cases this excludes (an unrelated policy
        # that merely ranked 2nd/3rd-closest among everything else, not a
        # genuine match for this query).
        candidate_policy_ids = [
            row[0] for row in candidate_policies if row[1] <= best_distance + STAGE1_RELATIVE_MARGIN
        ]

        # ─── Stage 2: pull deeply from just those few policies ──────────────
        # MAX_PER_SECTION still applies defensively (a genuinely under-split
        # section shouldn't be able to dominate its own policy's budget),
        # plus a new per-policy cap so ONE huge policy can't crowd out a
        # smaller-but-still-genuinely-relevant sibling from the same query.
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
            # Still returned for transparency/debugging — callers MUST NOT
            # treat this as a real answer given policyFound is False.
            "evidence": evidence,
            "message": POLICY_EVIDENCE_UNAVAILABLE_MESSAGE,
            "reason": (
                f"Best match distance {best_distance:.3f} exceeds the confidence threshold "
                f"({MEDIUM_CONFIDENCE_MAX_DISTANCE}) — nothing in the corpus genuinely covers this."
            ),
        }

    return {"policyFound": True, "confidence": confidence, "evidence": evidence, "message": None, "reason": None}
