"""
Drug Reference Lookup — indication match, grounded in real FDA label data
=============================================================================

Ported from ProAuth_AI_BackEnd/src/services/drugReferenceService.js's
findDrugReference() (search priority) and
src/rules/evaluators/diagnosisTreatmentEvaluator.js's R101 (strong/weak
match logic) — same drug_references table (real FDA label data imported
by the Node backend), queried directly since this Python pipeline already
connects to the same Postgres DB (see retrieval.py's get_policy_status()
for the same direct-query precedent).

This is deliberately NOT an LLM guess: indication match is either
confirmed against real FDA indications text, or it isn't — same "ground
truth over plausible-sounding text" discipline as the rest of this
project. When no strong match can be established this way,
clinical_evidence_agent.py's evaluate_clinical_criteria() folds
indication_match into its normal LLM-graded checklist instead (grounded
in whatever FDA text IS available, or diagnosis/policy context alone if
the drug isn't in the reference DB at all — e.g. most procedures).

Usage:
    from agents.drug_reference_lookup import find_drug_reference, indication_match_strength
    drug_ref = find_drug_reference("Ozempic")
    strength = indication_match_strength(drug_ref, diagnosis="type 2 diabetes", icd_code="E11.9")
"""
import json
import os
import re

import psycopg2
from dotenv import load_dotenv

load_dotenv()


def _normalize(text):
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _get_connection():
    return psycopg2.connect(os.environ["DATABASE_URL"])


def _row_to_dict(row):
    return {"genericName": row[0], "brandName": row[1], "indications": row[2]}


def find_drug_reference(treatment_name):
    """
    Same 5-tier search priority as findDrugReference() in the Node
    backend: exact generic -> exact brand -> active-ingredient contains ->
    partial ILIKE (first significant word) -> partial ILIKE (any
    significant word). Returns None if nothing matches (e.g. the
    requested service is a procedure, not a medication — genuinely not an
    error).
    """
    normalized = _normalize(treatment_name)
    if not normalized:
        return None

    conn = _get_connection()
    cur = conn.cursor()
    try:
        cur.execute('SELECT "genericName","brandName","indications" FROM drug_references WHERE "genericName" = %s LIMIT 1', (normalized,))
        row = cur.fetchone()
        if row:
            return _row_to_dict(row)

        cur.execute('SELECT "genericName","brandName","indications" FROM drug_references WHERE "brandName" = %s LIMIT 1', (normalized,))
        row = cur.fetchone()
        if row:
            return _row_to_dict(row)

        words = [w for w in normalized.split(" ") if len(w) > 3]

        for word in words:
            cur.execute(
                'SELECT "genericName","brandName","indications" FROM drug_references WHERE "activeIngredients" @> %s::jsonb LIMIT 1',
                (json.dumps([word]),),
            )
            row = cur.fetchone()
            if row:
                return _row_to_dict(row)

        if words and len(words[0]) >= 4:
            like = f"%{words[0]}%"
            cur.execute(
                'SELECT "genericName","brandName","indications" FROM drug_references '
                'WHERE "genericName" ILIKE %s OR "brandName" ILIKE %s ORDER BY "genericName" ASC LIMIT 1',
                (like, like),
            )
            row = cur.fetchone()
            if row:
                return _row_to_dict(row)

        for word in words[1:]:
            if len(word) < 4:
                continue
            like = f"%{word}%"
            cur.execute(
                'SELECT "genericName","brandName","indications" FROM drug_references '
                'WHERE "genericName" ILIKE %s OR "brandName" ILIKE %s ORDER BY "genericName" ASC LIMIT 1',
                (like, like),
            )
            row = cur.fetchone()
            if row:
                return _row_to_dict(row)

        return None
    finally:
        cur.close()
        conn.close()


def indication_match_strength(drug_reference, diagnosis, icd_code=None):
    """
    Same strong/weak/none logic as R101: >=2 matched diagnosis keywords in
    the FDA indications text, or an exact ICD-10 mention, is STRONG.
    Exactly one matched keyword is WEAK. Returns "STRONG" | "WEAK" | "NONE".
    drug_reference=None (not found in the reference DB) also returns "NONE".
    """
    if not drug_reference:
        return "NONE"

    indications_text = (drug_reference.get("indications") or "").lower()
    if not indications_text:
        return "NONE"

    diag_norm = _normalize(diagnosis)
    icd_norm = (icd_code or "").lower()

    diag_words = [w for w in diag_norm.split(" ") if len(w) > 3]
    matched_terms = [w for w in diag_words if w in indications_text]
    icd_match = bool(icd_norm) and icd_norm in indications_text

    if len(matched_terms) >= 2 or icd_match:
        return "STRONG"
    if len(matched_terms) == 1:
        return "WEAK"
    return "NONE"
