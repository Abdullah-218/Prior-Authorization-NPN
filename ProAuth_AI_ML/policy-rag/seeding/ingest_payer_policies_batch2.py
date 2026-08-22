"""
Private Payer Policy Ingestion — Batch 2
===========================================

Runs the same ingestion logic as ingest_payer_policies.py (reused directly
— chunk_text() and the upsert loop are not duplicated here) against the
combined POLICIES lists from payer_policies_batch2_<payer>.py — real
payer documents sourced separately per payer (Aetna/UHC/Cigna), each
module self-contained with its own citation docstring.

Missing batch files (a payer's sourcing not finished yet) are skipped with
a warning, not an error — this script is meant to be re-run as each
payer's batch file lands, idempotently (same ON CONFLICT upsert as the
original file).

Usage:
    python policy-rag/seeding/ingest_payer_policies_batch2.py
"""
import importlib
import os
import uuid

import psycopg2
from dotenv import load_dotenv
from pgvector.psycopg2 import register_vector
from sentence_transformers import SentenceTransformer

from ingest_payer_policies import section_chunk_rows

load_dotenv()

EMBEDDING_MODEL = "all-MiniLM-L6-v2"

BATCH_MODULES = [
    "payer_policies_batch2_aetna",
    "payer_policies_batch2_uhc",
    "payer_policies_batch2_cigna",
    # Batch 3 (2026-08-20+): one new category per payer not previously
    # covered (physical therapy, oncology drugs, hereditary-cancer genetic
    # testing) — see each module's own docstring for sourcing detail.
    "payer_policies_batch3_aetna",
    "payer_policies_batch3_cigna",
    "payer_policies_batch3_uhc",
]


def load_all_policies():
    all_policies = []
    for mod_name in BATCH_MODULES:
        try:
            mod = importlib.import_module(mod_name)
        except ModuleNotFoundError:
            print(f"  ! {mod_name} not found yet — skipping.")
            continue
        n = len(mod.POLICIES)
        print(f"  {mod_name}: {n} policies")
        all_policies.extend(mod.POLICIES)
    return all_policies


def main():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL not set (add it to ProAuth_AI_ML/.env)")

    print("Loading batch files...")
    policies = load_all_policies()
    if not policies:
        print("Nothing to ingest.")
        return

    conn = psycopg2.connect(database_url)
    register_vector(conn)
    cur = conn.cursor()

    print(f"\nLoading embedding model {EMBEDDING_MODEL}...")
    model = SentenceTransformer(EMBEDDING_MODEL)

    for policy in policies:
        cur.execute(
            '''INSERT INTO policies (id, "policyId", "policyName", "policyType", source, "payerName",
                                      jurisdiction, "effectiveDate", "documentPath", status, "createdAt", "updatedAt")
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now(), now())
               ON CONFLICT ("policyId") DO UPDATE SET
                 "policyName" = EXCLUDED."policyName", "updatedAt" = now()
               RETURNING id''',
            (
                str(uuid.uuid4()), policy["policyId"], policy["policyName"], policy["policyType"],
                "PUBLIC_PAYER_POLICY", policy["payerName"], "US", policy["effectiveDate"],
                policy["documentPath"], "ACTIVE",
            ),
        )
        policy_uuid = cur.fetchone()[0]

        cur.execute('DELETE FROM policy_criteria WHERE "policyId" = %s', (policy_uuid,))
        cur.execute('DELETE FROM policy_chunks WHERE "policyId" = %s', (policy_uuid,))

        chunk_rows = []
        for criterion_type, text, section in policy["criteria"]:
            cur.execute(
                '''INSERT INTO policy_criteria (id, "policyId", "criterionType", "criterionText", "sourceSection", "createdAt")
                   VALUES (%s,%s,%s,%s,%s, now())''',
                (str(uuid.uuid4()), policy_uuid, criterion_type, text[:4000], section),
            )
            # Each independent enumerated-list item / criteria paragraph
            # gets its own section suffix — see section_chunk_rows()'s and
            # chunk_text()'s docstrings (items #40/#41, 2026-08-20) for
            # why: MAX_PER_SECTION=3 otherwise lets only 3 of a policy's
            # real, independent criteria ever reach the Policy Agent, no
            # matter how many that policy's text actually specifies.
            chunk_rows.extend(section_chunk_rows(text, section))

        embeddings = model.encode([c[1] for c in chunk_rows], normalize_embeddings=True)
        for (section, chunk), emb in zip(chunk_rows, embeddings):
            cur.execute(
                '''INSERT INTO policy_chunks
                   (id, "policyId", "chunkText", embedding, section, payer, jurisdiction,
                    "effectiveDate", "documentName", source, "createdAt")
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())''',
                (
                    str(uuid.uuid4()), policy_uuid, chunk, emb.tolist(), section,
                    policy["payerName"], "US", policy["effectiveDate"], policy["policyName"], "PUBLIC_PAYER_POLICY",
                ),
            )
        conn.commit()
        print(f"{policy['policyId']}: {len(policy['criteria'])} criteria, {len(chunk_rows)} chunks")

    cur.close()
    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
