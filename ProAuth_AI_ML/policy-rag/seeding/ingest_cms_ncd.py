"""
CMS NCD Policy Ingestion Pipeline
==================================

Pulls real National Coverage Determinations from the free CMS Coverage API
(api.coverage.cms.gov — no API key needed as of Feb 2024, verified live
against the actual endpoints before building this), cleans and chunks the
text, embeds it locally (sentence-transformers, no external API), and
writes Policy / PolicyCriterion / PolicyChunk rows straight into Postgres
via raw SQL.

Raw SQL, not an ORM: this script doesn't own the schema — the Node backend
(ProAuth_AI_BackEnd/src/database) does, via Sequelize's sync(). Column
names below match exactly what Sequelize created (camelCase, quoted).

Every row written here is source='CMS' — real Medicare coverage policy,
not synthetic fixture data (contrast with seedInsurancePlans.js's
SYNTHETIC_POLICY rows).

Usage:
    pip install -r policy-rag/requirements.txt
    python policy-rag/seeding/ingest_cms_ncd.py             # full corpus — every active NCD (~316)
    python policy-rag/seeding/ingest_cms_ncd.py --curated    # just the hand-picked demo set (~29), fast iteration
"""
import html
import os
import re
import sys
import uuid

import psycopg2
import requests
from dotenv import load_dotenv
from pgvector.psycopg2 import register_vector
from sentence_transformers import SentenceTransformer

from ingest_payer_policies import section_chunk_rows

load_dotenv()

CMS_API_BASE = "https://api.coverage.cms.gov/v1"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"  # 384-dim — must match policy_chunks.embedding's vector(384)


def fetch_all_active_ncd_targets():
    """
    Every currently-active NCD, straight from CMS — not a hand-picked
    subset. Retired NCDs are excluded (no longer in effect; presenting them
    as current policy would be actively wrong). Confirmed live: 345 total,
    316 active, 29 retired, single page (no pagination needed at this size).
    """
    resp = requests.get(
        f"{CMS_API_BASE}/reports/national-coverage-ncd",
        params={"page-num": 1, "page-size": 500},
        headers={"Accept": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    items = resp.json()["data"]
    active = [item for item in items if "retired" not in item["title"].lower()]
    return [(item["document_id"], item["document_version"]) for item in active]


# Hand-picked, real NCDs relevant to prior-authorization demo scenarios
# (imaging, surgery, DME, screening, cardiac) — verified live against the
# CMS API before picking these, not guessed. Kept as a fast --curated mode
# for iterating on the pipeline itself without a 15+ minute full run.
# (document_id, document_version) -> /v1/data/ncd?ncdid=X&ncdver=Y
CURATED_NCD_TARGETS = [
    (57, 5),    # 100.1   Bariatric Surgery for Treatment of Co-Morbid Conditions Related to Morbid Obesity
    (226, 3),   # 240.4   Continuous Positive Airway Pressure (CPAP) Therapy for Obstructive Sleep Apnea
    (256, 2),   # 150.3   Bone (Mineral) Density Studies
    (245, 3),   # 50.3    Cochlear Implantation
    (281, 7),   # 210.3   Colorectal Cancer Screening Tests
    (176, 2),   # 220.1   Computed Tomography
    (364, 2),   # 210.14  Lung Cancer Screening with Low Dose Computed Tomography (LDCT)
    # Chapter 40 — diabetes (added after testing showed the corpus had zero
    # real diabetes coverage; the closest match without these was a passing
    # mention of diabetes as a bariatric-surgery comorbidity, not actual
    # diabetes guidance — see the retrieval test that prompted adding these).
    (92, 1),    # 40.3    Closed-Loop Blood Glucose Control Device (CBGCD)
    (251, 1),   # 40.1    Diabetes Outpatient Self-Management Training
    (222, 2),   # 40.2    Home Blood Glucose Monitors
    (133, 1),   # 40.4    Insulin Syringe
    (334, 1),   # 40.7    Outpatient Intravenous Insulin Treatment
    (38, 4),    # 40.5    Treatment of Obesity
    # Broader spread — surgery, preventive, imaging, device, and one
    # deliberately ambiguous case (gender dysphoria — CMS has no single
    # national coverage position, decided locally/case-by-case) so example
    # scenarios aren't all clean-cut yes/no.
    (373, 1),   # 30.3.3   Acupuncture for Chronic Lower Back Pain (cLBP)
    (70, 3),    # 260.1    Adult Liver Transplantation
    (64, 1),    # 140.2    Breast Reconstruction Following Mastectomy
    (342, 2),   # 210.4.1  Counseling to Prevent Tobacco Use
    (123, 1),   # 230.9    Cryosurgery of Prostate
    (368, 1),   # 140.9    Gender Dysphoria and Gender Reassignment Surgery
    (112, 3),   # 260.9    Heart Transplants
    (348, 1),   # 210.11   Intensive Behavioral Therapy for Cardiovascular Disease
    (331, 4),   # 220.6.17 Positron Emission Tomography (FDG) for Oncologic Conditions
    (230, 3),   # 160.18   Vagus Nerve Stimulation (VNS)
    # Cardiac — added after testing showed "heart attack" queries had
    # nothing to retrieve. There's no NCD for acute MI treatment itself
    # (standard emergency care, no special national policy needed), but
    # these adjacent/downstream interventions are exactly what a real
    # post-MI prior-auth request would actually be about.
    (110, 5),   # 20.4     Implantable Cardioverter Defibrillators (ICDs)
    (339, 1),   # 20.10.1  Intensive Cardiac Rehabilitation (ICR) Programs
    (201, 11),  # 20.7     Percutaneous Transluminal Angioplasty (PTA)
]


def clean_html(raw):
    """
    CMS text is double HTML-entity-escaped (&amp;lt; -> &lt; -> <).

    Real structural tags (<p>, <li>, <br>) are converted to blank-line
    paragraph breaks BEFORE the generic tag-strip below (2026-08-20 — CMS
    chunker fix, item #42 follow-up, see docs/PROGRESS_TRACKER.md §9.7).
    CMS's raw HTML genuinely has this structure — e.g. one NCD's covered
    indications list both numbered AND lettered sub-criteria via nested
    <ol>/<li> — but the OLD blanket `\\s+ -> " "` collapse below destroyed
    every boundary, leaving the whole "Indications and Limitations" text
    as one un-splittable blob no matter how many distinct criteria it
    actually specified. chunk_text()'s paragraph/enumerated-list detection
    (already proven on the private-payer corpus) needs real `\\n\\n`
    breaks to work with; this is what restores them. Nested lettered
    sub-items become their own top-level paragraph rather than staying
    nested under their parent numbered item — same "flatten rather than
    strand a qualifying clause" conservatism chunk_text()'s own enumerated-
    list detector already uses elsewhere, not a new tradeoff.
    """
    if not raw:
        return ""
    text = html.unescape(html.unescape(raw))
    text = re.sub(r"</?(p|li|br)\b[^>]*>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t\r]+", " ", text)   # collapse horizontal whitespace only
    text = re.sub(r" *\n *", "\n", text)    # trim spaces around each newline, WITHOUT merging separate newlines together
    text = re.sub(r"\n{3,}", "\n\n", text)  # 3+ newlines -> exactly one clean paragraph break
    return text.strip()


def split_covered_sections(text):
    """
    Splits on the Medicare NCD manual's own standard heading convention
    ("...Nationally Covered Indications" / "...Nationally Non-Covered
    Indications"). Returns (covered_text, non_covered_text, matched) —
    when matched is False, covered_text is the full cleaned text and the
    caller stores it as a single generic criterion instead of pretending
    it was actually split.
    """
    if not text:
        return "", "", False

    covered_marker = re.search(r"Nationally\s+Covered\s+Indications", text, re.IGNORECASE)
    noncovered_marker = re.search(r"Nationally\s+Non-?[Cc]overed\s+Indications", text, re.IGNORECASE)

    if covered_marker and noncovered_marker and noncovered_marker.start() > covered_marker.start():
        covered = text[covered_marker.end():noncovered_marker.start()].strip(" .:—-")
        non_covered = text[noncovered_marker.end():].strip(" .:—-")
        return covered, non_covered, True

    return text, "", False


def fetch_ncd(ncdid, ncdver):
    resp = requests.get(f"{CMS_API_BASE}/data/ncd", params={"ncdid": ncdid, "ncdver": ncdver}, timeout=30)
    resp.raise_for_status()
    return resp.json()["data"][0]


_DATE_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$|^\d{4}-\d{2}-\d{2}$")


def clean_date(value):
    """
    CMS's effective_date field isn't always an actual date — some
    longstanding NCDs (e.g. 40.4, Insulin Syringe) have it hold a free-text
    explanation instead ("This is a longstanding national coverage
    determination..."). Only pass through values that actually look like a
    date; everything else becomes NULL rather than a SQL error.
    """
    if not value or not _DATE_RE.match(value.strip()):
        return None
    return value.strip()


def upsert_policy(cur, ncdid, doc):
    display_id = doc["document_display_id"]
    policy_id_str = f"NCD-{display_id}"
    cur.execute(
        '''INSERT INTO policies (id, "policyId", "policyName", "policyType", source, "payerName",
                                  jurisdiction, "effectiveDate", "documentPath", status, "createdAt", "updatedAt")
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now(), now())
           ON CONFLICT ("policyId") DO UPDATE SET
             "policyName" = EXCLUDED."policyName",
             "effectiveDate" = EXCLUDED."effectiveDate",
             "updatedAt" = now()
           RETURNING id''',
        (
            str(uuid.uuid4()), policy_id_str, doc["title"], "NCD", "CMS", "Medicare", "US",
            clean_date(doc.get("effective_date")),
            f"https://www.cms.gov/medicare-coverage-database/details/ncd-details.aspx?NCDId={ncdid}",
            "ACTIVE",
        ),
    )
    return cur.fetchone()[0], policy_id_str


def store_criteria(cur, policy_uuid, indications_text):
    cur.execute('DELETE FROM policy_criteria WHERE "policyId" = %s', (policy_uuid,))
    covered, non_covered, matched = split_covered_sections(indications_text)
    if not covered:
        return 0

    rows = [("COVERED_INDICATIONS" if matched else "COVERAGE_CRITERIA", covered)]
    if matched and non_covered:
        rows.append(("NON_COVERED_INDICATIONS", non_covered))

    for criterion_type, text in rows:
        cur.execute(
            '''INSERT INTO policy_criteria (id, "policyId", "criterionType", "criterionText", "sourceSection", "createdAt")
               VALUES (%s,%s,%s,%s,%s, now())''',
            (str(uuid.uuid4()), policy_uuid, criterion_type, text[:4000], "Indications and Limitations"),
        )
    return len(rows)


def store_chunks(cur, model, policy_uuid, title, effective_date, doc):
    cur.execute('DELETE FROM policy_chunks WHERE "policyId" = %s', (policy_uuid,))

    sections = [
        ("Item/Service Description", clean_html(doc.get("item_service_description"))),
        ("Indications and Limitations", clean_html(doc.get("indications_limitations"))),
        ("Reasons for Denial", clean_html(doc.get("reasons_for_denial"))),
    ]
    # Reuses the private-payer corpus's chunk_text() (2026-08-20 — same
    # MAX_PER_SECTION=3 bug class confirmed present here too, see item #41
    # in docs/IMPLEMENTATION_PLAN.md) instead of this file's old plain
    # word-count splitter, which had no enumerated-list awareness at all.
    # Every independent list item / criteria paragraph gets its own
    # section suffix, same as the payer corpus, so the cap can't silently
    # exclude a real NCD criterion.
    chunk_rows = []
    for label, text in sections:
        chunk_rows.extend(section_chunk_rows(text, label))
    if not chunk_rows:
        return 0

    embeddings = model.encode([c[1] for c in chunk_rows], normalize_embeddings=True)
    for (label, chunk_text_val), emb in zip(chunk_rows, embeddings):
        cur.execute(
            '''INSERT INTO policy_chunks
               (id, "policyId", "chunkText", embedding, section, payer, jurisdiction,
                "effectiveDate", "documentName", source, "createdAt")
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())''',
            (
                str(uuid.uuid4()), policy_uuid, chunk_text_val, emb.tolist(), label,
                "Medicare", "US", clean_date(effective_date), title, "CMS",
            ),
        )
    return len(chunk_rows)


def main():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL not set (add it to ProAuth_AI_ML/.env)")

    curated_mode = "--curated" in sys.argv
    if curated_mode:
        targets = CURATED_NCD_TARGETS
        print(f"Curated mode — {len(targets)} hand-picked NCDs.")
    else:
        print("Fetching the full active NCD list from CMS...")
        targets = fetch_all_active_ncd_targets()
        print(f"Full corpus mode — {len(targets)} active NCDs. This will take a while; progress prints every 10.")

    conn = psycopg2.connect(database_url)
    register_vector(conn)
    cur = conn.cursor()

    print(f"Loading embedding model {EMBEDDING_MODEL} (local — first run downloads it, then cached)...")
    model = SentenceTransformer(EMBEDDING_MODEL)

    succeeded, failed = 0, []
    total_criteria, total_chunks = 0, 0

    for i, (ncdid, ncdver) in enumerate(targets, 1):
        try:
            doc = fetch_ncd(ncdid, ncdver)
            policy_uuid, policy_id_str = upsert_policy(cur, ncdid, doc)
            n_criteria = store_criteria(cur, policy_uuid, clean_html(doc.get("indications_limitations")))
            n_chunks = store_chunks(cur, model, policy_uuid, doc["title"], doc.get("effective_date"), doc)
            conn.commit()
            succeeded += 1
            total_criteria += n_criteria
            total_chunks += n_chunks
            if curated_mode:
                print(f"{policy_id_str}: {doc['title']}  ->  {n_criteria} criteria, {n_chunks} chunks")
            elif i % 10 == 0 or i == len(targets):
                print(f"  [{i}/{len(targets)}] {succeeded} ingested, {len(failed)} failed so far...")
        except Exception as exc:  # noqa: BLE001 — one bad record must not kill a 15-minute run
            conn.rollback()
            failed.append((ncdid, ncdver, str(exc)))
            print(f"  ! ncdid={ncdid} ncdver={ncdver} failed: {exc}")

    cur.close()
    conn.close()

    print(f"\nDone. {succeeded} policies ingested ({total_criteria} criteria, {total_chunks} chunks).")
    if failed:
        print(f"{len(failed)} failed and were skipped:")
        for ncdid, ncdver, err in failed:
            print(f"  - ncdid={ncdid} ncdver={ncdver}: {err}")


if __name__ == "__main__":
    main()
