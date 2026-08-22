"""
Private Payer Policy Ingestion
=================================

Real, current, publicly-accessible private payer coverage policies —
UnitedHealthcare, Cigna, and Aetna — source=PUBLIC_PAYER_POLICY (not CMS,
not synthetic). Unlike the CMS pipeline, there's no clean JSON API for
payer policies; each payer publishes its own PDF/HTML with its own layout.
Each was fetched and verified directly (WebFetch's own text summarizer
choked on the PDFs — real content, just poorly parsed by that path — so
they were re-extracted properly with `pdftotext` and hand-curated into the
policy/criteria structure below). The text is the payer's own words,
unedited, not paraphrased or summarized.

Source documents:
  UHC:   Bariatric Surgery, Commercial and Individual Exchange Medical Policy,
         Policy Number 2026T0362RR, effective 05/01/2026
         https://www.uhcprovider.com/content/dam/provider/docs/public/policies/comm-medical-drug/bariatric-surgery.pdf
  Cigna: Sleep Disordered Breathing Diagnosis and Treatment Guidelines V1.0.2025,
         effective 06/01/2025, published by EviCore (Cigna's UM partner for this guideline)
         https://www.evicore.com/sites/default/files/clinical-guidelines/2025-02/Cigna_Sleep%20Disordered%20Breathing%20Diagnosis%20&%20Treatment%20Guidelines_V1.0.2025_Eff06.01.2025_pub02.21.25.pdf
  Aetna: Clinical Policy Bulletin 0157 — Obesity Surgery, last review 04/02/2024,
         effective 03/16/1997, next review 02/13/2025
         https://www.aetna.com/cpb/medical/data/100_199/0157.html
         (aetna.com blocks automated fetches directly; text pulled from the
         ASMBS professional-org mirror of the same live CPB page, then
         cross-checked against the bulletin's own header/number/dates)

Usage:
    python policy-rag/seeding/ingest_payer_policies.py
"""
import os
import re
import uuid

import psycopg2
from dotenv import load_dotenv
from pgvector.psycopg2 import register_vector
from sentence_transformers import SentenceTransformer

load_dotenv()

EMBEDDING_MODEL = "all-MiniLM-L6-v2"
CHUNK_MAX_WORDS = 220
CHUNK_OVERLAP_WORDS = 40
# A paragraph needs at least this many semicolon-delimited items after its
# lead-in colon before it's treated as an enumerated list rather than an
# ordinary sentence that happens to contain a semicolon or two.
MIN_LIST_ITEMS = 5


def chunk_text(text):
    """
    Splits policy text into embeddable chunks, paragraph by paragraph.
    Each paragraph is either an enumerated list (see _chunk_enumerated_list)
    or ordinary prose, chunked by a word-count sliding window.

    Payer policies routinely publish long "considered experimental /
    not covered" sections as ONE dense paragraph of 20-30+
    semicolon-separated items (e.g. Aetna CPB 0157's exclusion list). The
    plain word-count window used to swallow the whole paragraph into one
    or two chunks, so a query about any single item (e.g. "liposuction")
    got an embedding averaged across every other unrelated item in that
    chunk — diluted enough to fall below the confidence-gate threshold
    even though the source text explicitly addresses it. Splitting each
    list item into its own chunk (with the lead-in sentence kept as
    context) fixes that recall gap without touching the confidence
    thresholds themselves.

    Returns (chunk_text, is_list_item, paragraph_index) tuples
    (2026-08-20+ — item #40's audit, see docs/PROGRESS_TRACKER.md
    §9.5-9.7). Per-item splitting above was already correct on its own —
    the bug this exists to fix is one level up:
    retrieve_policy_evidence()'s MAX_PER_SECTION=3 cap applies PER
    SECTION, and every item from one enumerated list was being written
    back to the DB under the SAME section string as its siblings (e.g.
    Aetna CPB 0157's 39-item exclusion list, all sharing one "II.
    Experimental, Investigational, or Unproven" section) — so at most 3
    of e.g. 39 real, independent exclusion items could ever reach the
    Policy Agent for any given query, silently starving the rest.
    is_list_item tells the caller which chunks came from genuine,
    independent enumerated items — each gets its own unique section
    suffix, so the cap can never again exclude a real item. Plain
    word-count chunks (is_list_item=False) from a SINGLE-paragraph
    criterion are sequential/overlapping slices of the same continuous
    prose, not independent items, and deliberately keep sharing one
    section — competing them against each other for the cap is correct,
    not a bug.

    paragraph_index (1-based, follow-up audit, same day) exists for a
    DIFFERENT real shape of the same underlying bug: several policies
    (found auditing item #40's remaining smaller-scale sections) pack
    multiple wholly UNRELATED criteria as separate paragraphs into one
    criterion string — e.g. UHC's GLP-1 weight-loss policy has 12
    paragraphs, each governing a DIFFERENT drug (Wegovy, Zepbound,
    Imcivree, Vykat XR...) with its own independent authorization
    criteria — all sharing one "Coverage Criteria" section before this
    fix. The caller only suffixes by paragraph_index when a criterion's
    text actually has more than one paragraph, so single-paragraph
    criteria (the majority of the corpus, already correctly scoped) keep
    their exact existing section names — this only widens sectioning for
    the genuinely multi-paragraph cases.
    """
    text = text.strip()
    if not text:
        return []

    chunks = []
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    for idx, paragraph in enumerate(paragraphs, start=1):
        enumerated = _chunk_enumerated_list(paragraph)
        if enumerated:
            chunks.extend((chunk, True, idx) for chunk in enumerated)
        else:
            chunks.extend((chunk, False, idx) for chunk in _chunk_by_words(paragraph))
    return chunks


def section_chunk_rows(text, section):
    """
    chunk_text(text) + the section-suffixing every caller needs (see its
    docstring) — factored out once so ingest_payer_policies.py,
    ingest_payer_policies_batch2.py, and ingest_cms_ncd.py don't each
    duplicate the same paragraph/item counters. Returns a flat list of
    (final_section, chunk_text) rows, ready to embed and insert as-is.
    """
    chunks = chunk_text(text)
    num_paragraphs = max((p for _, _, p in chunks), default=0)
    item_counters = {}
    rows = []
    for chunk, is_list_item, para_idx in chunks:
        final_section = f"{section} — para {para_idx}" if num_paragraphs > 1 else section
        if is_list_item:
            item_counters[para_idx] = item_counters.get(para_idx, 0) + 1
            final_section = f"{final_section} — item {item_counters[para_idx]}"
        rows.append((final_section, chunk))
    return rows


def _chunk_by_words(text):
    words = text.split()
    if not words:
        return []
    chunks, start = [], 0
    while start < len(words):
        end = min(start + CHUNK_MAX_WORDS, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start = end - CHUNK_OVERLAP_WORDS
    return chunks


def _chunk_enumerated_list(paragraph):
    """
    Detects a lead-in sentence followed by a semicolon-delimited
    enumerated list — e.g. "Aetna considers the following ... unproven:
    item one; item two; ...; and item N." — and returns one chunk per
    item, each carrying the lead-in as trailing context so it keeps its
    "considered experimental/not covered" framing on its own. Returns
    None (falls back to word-count chunking) when the paragraph doesn't
    look like this shape, e.g. fewer than MIN_LIST_ITEMS items, so an
    ordinary sentence with one incidental semicolon isn't mistaken for a
    list.

    Item-first, lead-in-trailing — not the reverse. Measured empirically
    against this corpus: putting the ~25-word generic boilerplate lead-in
    BEFORE the item (e.g. "Aetna considers the following experimental,
    investigational, or unproven ...: liposuction (...)") buries the one
    word that actually matters under a long clause that's IDENTICAL
    across every item in the list, pulling the embedding toward "generic
    Aetna exclusion boilerplate" instead of "liposuction" specifically —
    distance 0.52-0.57 against a query for that exact item, i.e. below
    the confidence gate despite the source text explicitly covering it.
    Putting the item first and the lead-in after as trailing context
    dropped that same query to 0.40-0.43, comfortably inside MEDIUM
    confidence.
    """
    colon_idx = paragraph.find(": ")
    if colon_idx == -1:
        return None

    lead_in = paragraph[: colon_idx + 1].strip()
    rest = paragraph[colon_idx + 2:].strip()

    items = [item.strip(" .") for item in _split_top_level(rest, ";") if item.strip(" .")]
    if len(items) < MIN_LIST_ITEMS:
        return None

    # A genuine top-level list has independent, self-contained items. If
    # one of the first couple of items itself contains a colon, this
    # paragraph is really a nested/lettered outline (e.g. "1. ...: a. ...:
    # i. ...; or ii. ... in conjunction with ...: X; or Y") and the "first
    # colon" grabbed above is an outer scaffold marker, not the list's
    # real lead-in. Splitting flatly here would strand items with the
    # wrong context — or worse, silently drop a qualifying condition an
    # item depends on (e.g. "type 2 diabetes mellitus" split away from
    # the "BMI greater than 35 ... in conjunction with" clause it only
    # counts under). Falling back to word-count chunking at least keeps
    # the qualifying clause and the item together in the same chunk.
    if any(": " in item for item in items[:2]):
        return None

    lead_in_clause = lead_in.rstrip(":").strip()
    chunks = []
    for item in items:
        item = re.sub(r"^(and|or)\s+", "", item, flags=re.IGNORECASE)
        chunks.append(f"{item}. ({lead_in_clause})")
    return chunks


def _split_top_level(text, sep):
    """
    Splits text on `sep`, but never inside parentheses — e.g. "Liposuction
    (suction-assisted lipectomy; ultrasonic assisted liposuction)" must stay
    one item, not fracture into "Liposuction (suction-assisted lipectomy"
    and a dangling "ultrasonic assisted liposuction)". A naive
    str.split(sep) would butcher exactly this kind of parenthetical, which
    real payer policy text uses constantly.
    """
    parts, current, depth = [], [], 0
    for ch in text:
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth = max(0, depth - 1)
            current.append(ch)
        elif ch == sep and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return parts


UHC_BARIATRIC_COVERED = """The following bariatric surgical procedures are proven and medically necessary for treating obesity: Biliopancreatic diversion/biliopancreatic diversion with duodenal switch; Gastric bypass (includes robotic-assisted gastric bypass); Adjustable gastric banding (using open or laparoscopic approaches) for individuals >= 18 years of age; Sleeve gastrectomy (vertical sleeve gastrectomy).

In adults aged 18 years or older, bariatric surgery using one of the procedures identified above for treating obesity is proven and medically necessary when all the following criteria are met:

One of the following: Body Mass Index (BMI) of >= 40 kg/m2 (or BMI >= 37.5 kg/m2 in individuals of Asian descent); or BMI of >= 35 to 39.9 kg/m2 (or BMI >= 32.5-37.4 kg/m2 in individuals of Asian descent) in the presence of one or more of the following comorbidities: Insulin resistance or type 2 diabetes; or Cardiovascular disease (e.g., history of stroke and/or myocardial infarction, poorly controlled hypertension, coronary artery disease, hyperlipidemia); or History of cardiomyopathy; or Obstructive Sleep Apnea confirmed on polysomnography with an Apnea-Hypopnea Index or Respiratory Disturbance Index of >= 30; or Evidence of Metabolic Dysfunction-Associated Steatotic Liver Disease; or Idiopathic intracranial hypertension (pseudotumor cerebri).

And the individual must also meet the following criteria: Both of the following: Completion of a preoperative evaluation that includes a detailed weight history, along with dietary and physical activity patterns; and Psychosocial-behavioral evaluation by an individual professionally recognized as part of a behavioral health discipline, to provide screening and identification of risk factors or potential postoperative challenges that may contribute to a poor postoperative outcome. Or: Participation in a Multidisciplinary surgical preparatory regimen.

In adolescents aged 12 to 17 years, the bariatric surgical procedures are proven and medically necessary for treating obesity when all the following criteria are met: One of the following: Class III obesity; or Class II obesity in the presence of one or more comorbidities (insulin resistance or type 2 diabetes; poorly controlled hypertension; hyperlipidemia; Obstructive Sleep Apnea with AHI/RDI >= 30; Metabolic Dysfunction-Associated Steatotic Liver Disease; idiopathic intracranial hypertension). The individual must also receive an evaluation at or in consultation with a Multidisciplinary center focused on the surgical treatment of severe childhood obesity.

A planned two-stage procedure is proven and medically necessary when all the following criteria are met: Initial BMI of >= 50 kg/m2 prior to first-stage bariatric procedure; and Second stage occurs within 2 years following the primary bariatric surgery procedure; and Individual has been adherent to nutrition and exercise; and Individual meets medical necessity criteria listed above at the time of the second-stage procedure."""

UHC_BARIATRIC_NON_COVERED = """The following procedures are unproven and not medically necessary for treating obesity due to insufficient evidence of efficacy: Revisional Bariatric Surgery for any other indication than those listed in the covered indications; Bariatric surgery as the primary treatment for any condition other than obesity; Bariatric interventions for the treatment of obesity including but not limited to: Bariatric artery embolization; Gastric electrical stimulation with an implantable gastric stimulator; Laparoscopic greater curvature plication (total gastric vertical plication); Mini-gastric bypass/laparoscopic mini-gastric bypass/one-anastomosis gastric bypass; Silastic ring vertical gastric bypass; Single-anastomosis duodenal switch; Transoral endoscopic surgery including endoscopic sleeve gastroplasty (OverStitch), gastrointestinal liners, intragastric balloon, transoral outlet reduction (TORe), TransPyloric Shuttle device; Vagus nerve blocking (VBLOC)."""

CIGNA_CPAP_COVERED = """Initiation of HCPCS E0601 PAP therapy and establishing compliance requires ALL of the following: A positive diagnosis of OSA or central sleep apnea, as measured by HSAT or PSG; The individual and/or their caregiver have received instruction from the treating physician and supplier of the CPAP device and accessories in the proper use and care of the equipment; A compliance support plan between the treating physician and DME supplier has been established.

Authorization for equipment purchase requires: PAP device must be used >= 4 hours per night on 70% of nights during a consecutive thirty (30) day period anytime during the first three (3) months of initial usage; Individual has regular follow-up to evaluate symptoms.

Repeat initiation of APAP/CPAP HCPCS E0601 device after failing an initial trial period is medically necessary when a clinical evaluation by a provider has occurred to determine the etiology of the failure to respond to PAP therapy with a support plan to address these causes.

Extension of establishing compliance with E0601 requires ALL of the following: Individual history includes ONE of: failure to resolve symptoms or unimproved AHI during initial compliance period, OR inconsistent usage of device related to improper fit, lack of education, intolerance of PAP therapy, or device malfunction; Individual has received from the ordering physician or supplier of the PAP device in the past 30 days: instruction in proper use and care of equipment, mask refitting or adjustment if necessary, education for proper use of PAP accessories.

Replacement APAP/CPAP HCPCS E0601 device requires ALL of the following: Continued resolution of symptoms and improved AHI on therapy; Device had been consistently used >= 4 hours per night on 70% of nights; Device is not operating; DME supplier has physically evaluated the device and determined it is unable to be repaired; Device to be replaced is no longer covered under warranty.

Auto-adjusting positive airway pressure (APAP) repeat assessment (E0601 APAP Treatment for determining appropriate PAP pressure for individuals currently on fixed pressure CPAP) is medically necessary for ALL of the following: A positive diagnosis of OSA, as measured by HSAT or PSG; Attempted compliance with fixed CPAP (>= 4 hours per night on 70% of nights) has not adequately treated signs and symptoms of OSA; Persistent symptoms or unimproved AHI/RDI in individual currently on fixed CPAP therapy, with prior instruction in proper use, mask re-fitting, and accessory education already provided."""

AETNA_BARIATRIC_COVERED = """Open or laparoscopic short or long-limb Roux-en-Y gastric bypass (RYGB), open or laparoscopic sleeve gastrectomy, open or laparoscopic biliopancreatic diversion (BPD) with or without duodenal switch (DS), laparoscopic adjustable silicone gastric banding (LASGB), open or laparoscopic single anastomosis duodenal-ileal switch (SADI-S), OR open or laparoscopic sleeve gastrectomy with single anastomosis duodeno-ileal bypass (SIPS) is considered medically necessary when the selection criteria listed below are met:

1. Must meet either a (adults) or b (adolescents): a. For adults aged 18 years or older, presence of persistent severe obesity, documented in contemporaneous clinical records, defined as any of the following: i. Body mass index (BMI) exceeding 40 (or exceeding 37.5 for persons of Asian ancestry) measured prior to preoperative preparatory program; or ii. BMI greater than 35 (or exceeding 32.5 for persons of Asian ancestry) measured prior to preoperative preparatory program in conjunction with any of the following severe co-morbidities: clinically significant obstructive sleep apnea; or coronary heart disease, with objective documentation; or medically refractory hypertension (blood pressure greater than 140 mmHg systolic and/or 90 mmHg diastolic despite concurrent use of 3 anti-hypertensive agents of different classes); or type 2 diabetes mellitus; or nonalcoholic steatohepatitis (NASH). b. For adolescents who have completed bone growth (generally age of 13 in girls and age of 15 in boys), presence of obesity with BMI exceeding 40.

2. Member has attempted weight loss in the past without successful long-term weight reduction; and member has participated in an intensive multicomponent behavioral intervention designed to help participants achieve or maintain weight loss through a combination of dietary changes and increased physical activity. This intervention must be documented in the medical record, must be intensive (12 or more sessions on separate dates over any duration of time) and occur within 2 years prior to surgery, and must have components focusing on nutrition, physical activity, and behavioral modification.

3. Screening for obstructive sleep apnea (OSA), using a validated screening questionnaire, must be documented (not required for persons already diagnosed with OSA); and

4. For members who have an active substance abuse disorder, or have a history of eating disorder or severe psychiatric disturbance, or who are currently under the care of a psychologist/psychiatrist, pre-operative psychological clearance is necessary in order to exclude members who are unable to provide informed consent or who are unable to comply with the pre- and post-operative regimen.

Note: Most Aetna HMO and QPOS plans exclude coverage of surgical operations, procedures, or treatment of obesity unless approved by Aetna. Some Aetna plans entirely exclude coverage of surgical treatment of obesity. Please check benefit plan descriptions for details.

Bariatric Surgery Complications considered medically necessary: removal of a gastric band when recommended by the member's physician; surgery to correct complications from bariatric surgery such as obstruction, stricture, erosion, or band slippage; replacement of an adjustable band if there are complications that cannot be corrected with band manipulation or adjustments; and repeat bariatric surgery for members whose initial bariatric surgery was medically necessary and who have not had adequate success (sustained loss of more than 50% of excess body weight) 2 years following the primary procedure while compliant with a prescribed nutrition and exercise program."""

AETNA_BARIATRIC_NON_COVERED = """Aetna considers the following experimental, investigational, or unproven because the peer-reviewed medical literature shows them to be either unsafe or inadequately studied: adjunctive omentectomy to bariatric surgery; AspireAssist aspiration therapy; "band over bypass" or LASGB revision of prior Roux-en-Y gastric bypass (i.e., placement of a gastric band for the management of weight regain after Roux-en-Y gastric bypass); "band over sleeve" or LASGB revision of prior sleeve gastrectomy; bariatric and metabolic surgery as a treatment for rheumatoid arthritis; bariatric surgery as a treatment for idiopathic intracranial hypertension in persons not meeting medical necessity criteria for obesity surgery above; bariatric surgery as a treatment for infertility in persons not meeting medical necessity criteria for obesity surgery above; bariatric surgery as a treatment for type-2 diabetes in persons with a BMI less than 35; conversion of a sleeve gastrectomy to a Roux-en-Y gastric bypass for the treatment of bile reflux; conversion to sleeve gastrectomy for hypoglycemia post-RYGB; duodenal ileal switch for the treatment of gastroparesis; gastric bypass as a treatment for gastroparesis in persons not meeting medical necessity criteria for obesity surgery above; gastroplasty, more commonly known as "stomach stapling" (see below for clarification from vertical band gastroplasty); laparoscopic gastric diversion with gastro-jejunal reconstruction for the treatment of GERD with esophagitis; laparoscopic gastric plication (also known as laparoscopic greater curvature plication [LGCP]), with or without gastric banding; laparoscopic single-anastomosis duodeno-ileal bypass with gastric plication; LASGB, RYGB, and BPD/DS procedures not meeting the medical necessity criteria above; liposuction (suction-assisted lipectomy; ultrasonic assisted liposuction); loop gastric bypass; mini gastric bypass; natural orifice transoral endoscopic surgery (NOTES) techniques for bariatric surgery including, but may not be limited to, the following: endoscopic outlet reduction (transoral outlet reduction (TORe)) for treatment of weight gain after Roux-en-Y gastric bypass; gastrointestinal liners (endoscopic duodenal-jejunal bypass, endoscopic gastrointestinal bypass devices; e.g., EndoBarrier and the ValenTx Endo Bypass System); intragastric balloon (e.g., the Obalon Balloon System, and the ReShape Integrated Dual Balloon System); mini sleeve gastrectomy; restorative obesity surgery, endoluminal (ROSE) procedure for the treatment of weight regain after gastric bypass surgery; transoral gastroplasty (TG) (vertical sutured gastroplasty; endoluminal vertical gastroplasty; endoscopic sleeve gastroplasty); and use of any endoscopic closure device (Over the Scope clip [OTSC] system set, Apollo OverStitch endoscopic suturing system, StomaphyX endoluminal fastener and delivery system) in conjunction with NOTES; omentopexy during sleeve gastrectomy; open adjustable gastric banding; prophylactic mesh placement for prevention of incisional hernia after open bariatric surgery; prophylactic pyloroplasty via botulinum toxin injection following laparoscopic sleeve gastrectomy; revision of Roux-en-Y gastric bypass by distalization; Roux-en-Y gastric bypass as a treatment for gastroesophageal reflux in persons not meeting medical necessity criteria for obesity surgery; Roux-en-Y gastrojejunostomy for the treatment of persistent gastro-esophageal reflux disease following antireflux surgery in persons not meeting medical necessity criteria for obesity surgery above; sclerotherapy for the treatment of dilated gastrojejunostomy following bariatric surgery; silastic ring vertical gastric bypass (Fobi pouch); use of a coated stent for gastro-jejunal fistula following bariatric surgery; vagus nerve blocking (e.g., the VBLOC device, also known as the Maestro Implant or the Maestro Rechargeable System); and vertical banded gastroplasty (VBG), except in limited circumstances noted above (members at increased risk of adverse consequences of RYGB due to extensive adhesions, hepatic cirrhosis, inflammatory bowel disease, poorly controlled systemic disease, or radiation enteritis)."""

POLICIES = [
    {
        "policyId": "UHC-BARIATRIC-2026",
        "policyName": "Bariatric Surgery — Commercial and Individual Exchange Medical Policy",
        "policyType": "Commercial Medical Policy",
        "payerName": "UnitedHealthcare",
        "effectiveDate": "2026-05-01",
        "documentPath": "https://www.uhcprovider.com/content/dam/provider/docs/public/policies/comm-medical-drug/bariatric-surgery.pdf",
        "criteria": [
            ("COVERED_INDICATIONS", UHC_BARIATRIC_COVERED, "Coverage Rationale — Proven and Medically Necessary"),
            ("NON_COVERED_INDICATIONS", UHC_BARIATRIC_NON_COVERED, "Coverage Rationale — Unproven and Not Medically Necessary"),
        ],
    },
    {
        "policyId": "CIGNA-SLEEP-CPAP-2025",
        "policyName": "Sleep Disordered Breathing Diagnosis and Treatment Guidelines — Positive Airway Pressure Devices",
        "policyType": "Coverage Guideline",
        "payerName": "Cigna",
        "effectiveDate": "2025-06-01",
        "documentPath": "https://www.evicore.com/sites/default/files/clinical-guidelines/2025-02/Cigna_Sleep%20Disordered%20Breathing%20Diagnosis%20%26%20Treatment%20Guidelines_V1.0.2025_Eff06.01.2025_pub02.21.25.pdf",
        "criteria": [
            ("COVERED_INDICATIONS", CIGNA_CPAP_COVERED, "SL-4.2 Positive airway pressure devices"),
        ],
    },
    {
        "policyId": "AETNA-BARIATRIC-0157",
        "policyName": "Obesity Surgery — Clinical Policy Bulletin 0157",
        "policyType": "Clinical Policy Bulletin",
        "payerName": "Aetna",
        "effectiveDate": "1997-03-16",
        "documentPath": "https://www.aetna.com/cpb/medical/data/100_199/0157.html",
        "criteria": [
            ("COVERED_INDICATIONS", AETNA_BARIATRIC_COVERED, "I. Medical Necessity"),
            ("NON_COVERED_INDICATIONS", AETNA_BARIATRIC_NON_COVERED, "II. Experimental, Investigational, or Unproven"),
        ],
    },
]


def main():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL not set (add it to ProAuth_AI_ML/.env)")

    conn = psycopg2.connect(database_url)
    register_vector(conn)
    cur = conn.cursor()

    print(f"Loading embedding model {EMBEDDING_MODEL}...")
    model = SentenceTransformer(EMBEDDING_MODEL)

    for policy in POLICIES:
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
