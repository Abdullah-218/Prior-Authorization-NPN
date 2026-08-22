"""
UnitedHealthcare Payer Policy Ingestion — Batch 3
====================================================

One additional real, current, publicly-accessible UHC medical policy,
extending batch 2's five entries. source=PUBLIC_PAYER_POLICY. Fetched
directly and converted to text with `pdftotext -layout`. Text below is
the payer's own words, unedited, not paraphrased or summarized, condensed
from the full 34-page document (most of which is CPT/HCPCS code tables)
to the core medical-necessity criteria — the personal-history and
family-history qualifying-criteria language, not every one of the
dozens of enumerated syndrome/histology sub-bullets, matching the
condensing convention already used elsewhere in this corpus (e.g. Aetna's
spinal-fusion entry: "only the lumbar spinal fusion indications... were
extracted").

Source document:

  Genetic testing for hereditary cancer:
     Genetic Testing for Hereditary Cancer — UnitedHealthcare Commercial
     and Individual Exchange Medical Policy, effective 07/01/2026
     https://www.uhcprovider.com/content/dam/provider/docs/public/policies/comm-medical-drug/genetic-testing-hereditary-cancer.pdf

RESTRUCTURED 2026-08-20 (item #40 fix — see docs/PROGRESS_TRACKER.md §9.5):
the original single-paragraph "COVERED_INDICATIONS" entry produced 9
policy_chunks all sharing ONE section label. rag/retrieval.py caps
results at MAX_PER_SECTION=3 per (policyId, section) pair, so only 3 of
those 9 chunks could ever reach the Policy Agent for any given query —
live-reproduced: a patient qualifying under "first/second-degree relative
with breast cancer diagnosed at age 50 or younger" was evaluated against
a completely different, non-matching branch ("first-degree relative with
2+ primary solid tumors") because that was the only one of the 9 that
made the top-3 cut for that query, producing an incorrect PEND for an
eligible patient. This wasn't a chunking failure — chunk_text()'s
enumerated-list splitter already correctly gave the "no personal history"
branch's 5 items their own chunks — it was a SECTION-granularity failure:
all 9 chunks (across 4 structurally distinct qualifying paragraphs)
competed for the same 3-chunk-per-section budget.

Fix: every one of the policy's 12 individually-checkable qualifying
criteria (still 100% the payer's own words — split, not reworded; the
"(...)" trailing context on each item follows the exact same convention
seeding/ingest_payer_policies.py's own _chunk_enumerated_list() already
uses elsewhere in this corpus) now gets its OWN distinct section label.
Each section's chunk pool is now well under MAX_PER_SECTION, so the
3-per-section cap can never again exclude a real qualifying branch — the
only remaining limit is the Policy Agent's top_k=16 across the whole
payer-group search, same as every other policy in this corpus.

Usage: same as payer_policies_batch2_uhc.py — data-only, merged into
ingest_payer_policies_batch2.py's BATCH_MODULES list.
"""

UHC_GENERAL_PROVISIONS = """Pretest genetic counseling is strongly recommended to inform persons being tested about the advantages and limitations of the test, as applied to a unique person. Single-gene testing and known mutation testing for familial cancer are proven and medically necessary."""

UHC_PERSONAL_HISTORY_BRCA_BREAST_65 = """For individuals with a personal history of a primary solid tumor: BRCA1/2 gene testing is proven and medically necessary for individuals with a personal history of breast cancer diagnosed at age 65 years or younger."""

# The panel-level "at least one of the following is met" list — personal
# history of a primary solid tumor. Lead sentence kept verbatim on every
# item as trailing context (same convention as
# seeding/ingest_payer_policies.py's _chunk_enumerated_list()), each item
# otherwise the payer's own unedited wording.
_UHC_PERSONAL_HISTORY_LEAD = "Genetic testing with a multigene hereditary cancer panel for individuals with a personal history of a primary solid tumor (excluding basal or squamous cell skin cancer) is proven and medically necessary when at least one of the following is met."

UHC_PERSONAL_HISTORY_CANCER_PROFILE = f"""the individual has a personal history of breast cancer diagnosed at age 50 or younger, metastatic breast cancer, multiple primary breast cancers, triple-negative breast cancer, ovarian cancer, pancreatic cancer, metastatic prostate cancer, a Lynch Syndrome-associated cancer, or at least two different primary solid tumors. ({_UHC_PERSONAL_HISTORY_LEAD})"""

UHC_PERSONAL_HISTORY_FAMILY_HISTORY = f"""the individual has a personal history of a primary solid tumor and a family history including at least one close blood relative with a Lynch Syndrome-associated cancer or a primary solid tumor diagnosed at age 40 or younger, or at least two close blood relatives on the same side of the family diagnosed with any primary solid tumor. ({_UHC_PERSONAL_HISTORY_LEAD})"""

UHC_PERSONAL_HISTORY_TUMOR_TESTING = f"""a pathogenic variant with clinical germline implications was detected in tumor tissue, or tumor testing demonstrated microsatellite instability or absence of mismatch repair proteins. ({_UHC_PERSONAL_HISTORY_LEAD})"""

UHC_PERSONAL_HISTORY_RISK_SCORE = f"""the individual has a Tyrer-Cuzick, BRCAPRO, or CanRisk score of 2.5% or greater for a BRCA1/2 pathogenic variant, or a PREMM5, MMRpro, or MMRpredict score of 2.5% or greater for a Lynch syndrome gene mutation. ({_UHC_PERSONAL_HISTORY_LEAD})"""

# No personal history of a primary solid tumor — same treatment.
_UHC_NO_PERSONAL_HISTORY_LEAD = "For individuals with no personal history of a primary solid tumor: genetic testing with a multigene hereditary cancer panel or BRCA1/2 testing is proven and medically necessary if at least one of the following is met."

UHC_NO_PERSONAL_HISTORY_RELATIVE_MULTIPLE_TUMORS = f"""at least one first-degree relative has a history of two or more different primary solid tumors, a Lynch Syndrome-associated cancer, or a neuroendocrine tumor. ({_UHC_NO_PERSONAL_HISTORY_LEAD})"""

UHC_NO_PERSONAL_HISTORY_RELATIVE_BREAST_OR_OTHER_CANCER = f"""at least one first- or second-degree relative has breast cancer diagnosed at age 50 or younger, triple-negative breast cancer, metastatic prostate cancer, ovarian cancer, or pancreatic cancer. ({_UHC_NO_PERSONAL_HISTORY_LEAD})"""

UHC_NO_PERSONAL_HISTORY_EXTENDED_FAMILY_PATTERN = f"""family history includes two or more second-degree relatives on the same side of the family with a Lynch Syndrome-associated cancer, two or more first- or second-degree relatives with renal cell carcinoma, at least three close blood relatives on the same side of the family with any primary solid tumor, or Ashkenazi Jewish ancestry with at least one close blood relative with a BRCA-related cancer. ({_UHC_NO_PERSONAL_HISTORY_LEAD})"""

UHC_NO_PERSONAL_HISTORY_COLORECTAL_POLYPOSIS = f"""a personal history of colorectal polyposis with at least 10 adenomas. ({_UHC_NO_PERSONAL_HISTORY_LEAD})"""

UHC_NO_PERSONAL_HISTORY_RISK_SCORE = f"""a Tyrer-Cuzick, BRCAPRO, or CanRisk score of 5% or greater for a BRCA1/2 pathogenic variant, or a PREMM5, MMRpro, or MMRpredict score of 5% or greater for a Lynch syndrome gene mutation. ({_UHC_NO_PERSONAL_HISTORY_LEAD})"""

UHC_PEDIATRIC_ONSET = """Genetic testing with a multigene hereditary cancer panel for individuals diagnosed with cancer at age 18 years or younger is proven and medically necessary."""

UHC_GENETIC_TESTING_NON_COVERED = """Multigene hereditary cancer panels are unproven and not medically necessary for all indications other than those specifically listed as medically necessary above. RNA panel testing for hereditary cancers is unproven and not medically necessary for all indications. Genetic testing for the purpose of polygenic risk scoring for hereditary cancers is unproven and not medically necessary for all indications. Whole-exome and whole-genome sequencing for the purpose of identifying hereditary cancer syndromes or hereditary cancer syndrome risk is unproven and not medically necessary."""

POLICIES = [
    {
        "policyId": "UHC-GENETIC-HEREDITARY-CANCER-2026",
        "policyName": "Genetic Testing for Hereditary Cancer — Commercial and Individual Exchange Medical Policy",
        "policyType": "Medical Policy",
        "payerName": "UnitedHealthcare",
        "effectiveDate": "2026-07-01",
        "documentPath": "https://www.uhcprovider.com/content/dam/provider/docs/public/policies/comm-medical-drug/genetic-testing-hereditary-cancer.pdf",
        "criteria": [
            ("GENERAL_PROVISIONS", UHC_GENERAL_PROVISIONS,
             "Coverage Rationale — General Testing Provisions"),
            ("COVERED_PERSONAL_HISTORY_BRCA_BREAST_65", UHC_PERSONAL_HISTORY_BRCA_BREAST_65,
             "Coverage Rationale — Personal History: BRCA Testing for Breast Cancer ≤65"),
            ("COVERED_PERSONAL_HISTORY_CANCER_PROFILE", UHC_PERSONAL_HISTORY_CANCER_PROFILE,
             "Coverage Rationale — Personal History Panel: Personal Cancer Profile"),
            ("COVERED_PERSONAL_HISTORY_FAMILY_HISTORY", UHC_PERSONAL_HISTORY_FAMILY_HISTORY,
             "Coverage Rationale — Personal History Panel: Family History of Lynch/Solid Tumor"),
            ("COVERED_PERSONAL_HISTORY_TUMOR_TESTING", UHC_PERSONAL_HISTORY_TUMOR_TESTING,
             "Coverage Rationale — Personal History Panel: Germline/Tumor Testing Findings"),
            ("COVERED_PERSONAL_HISTORY_RISK_SCORE", UHC_PERSONAL_HISTORY_RISK_SCORE,
             "Coverage Rationale — Personal History Panel: Risk Score Threshold"),
            ("COVERED_NO_PERSONAL_HISTORY_RELATIVE_MULTIPLE_TUMORS", UHC_NO_PERSONAL_HISTORY_RELATIVE_MULTIPLE_TUMORS,
             "Coverage Rationale — No Personal History: Relative With Multiple Primary Tumors"),
            ("COVERED_NO_PERSONAL_HISTORY_RELATIVE_BREAST_OR_OTHER_CANCER", UHC_NO_PERSONAL_HISTORY_RELATIVE_BREAST_OR_OTHER_CANCER,
             "Coverage Rationale — No Personal History: Relative With Early Breast/Other Cancer"),
            ("COVERED_NO_PERSONAL_HISTORY_EXTENDED_FAMILY_PATTERN", UHC_NO_PERSONAL_HISTORY_EXTENDED_FAMILY_PATTERN,
             "Coverage Rationale — No Personal History: Extended Family History Pattern"),
            ("COVERED_NO_PERSONAL_HISTORY_COLORECTAL_POLYPOSIS", UHC_NO_PERSONAL_HISTORY_COLORECTAL_POLYPOSIS,
             "Coverage Rationale — No Personal History: Colorectal Polyposis History"),
            ("COVERED_NO_PERSONAL_HISTORY_RISK_SCORE", UHC_NO_PERSONAL_HISTORY_RISK_SCORE,
             "Coverage Rationale — No Personal History: Risk Score Threshold"),
            ("COVERED_PEDIATRIC_ONSET", UHC_PEDIATRIC_ONSET,
             "Coverage Rationale — Pediatric-Onset Cancer"),
            ("NON_COVERED_INDICATIONS", UHC_GENETIC_TESTING_NON_COVERED,
             "Coverage Rationale — Unproven Indications"),
        ],
    },
]
