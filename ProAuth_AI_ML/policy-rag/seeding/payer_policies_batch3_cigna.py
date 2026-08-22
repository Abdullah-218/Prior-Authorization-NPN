"""
Cigna Payer Policy Ingestion — Batch 3
=========================================

One additional real, current, publicly-accessible Cigna coverage policy
(published by EviCore, Cigna's UM partner — same sourcing pattern as the
existing CIGNA-CPAP entry in ingest_payer_policies.py and every Cigna
batch-2 entry), extending batch 2's nine entries. source=PUBLIC_PAYER_POLICY.
Fetched directly (unlike some Aetna pages this session, this PDF fetched
without blocking) and converted to text with `pdftotext -layout`. Text
below is the payer's own words, unedited, not paraphrased or summarized,
condensed from the full ~7-page document to the core, broadly-applicable
prior-authorization criteria (the general primary/supportive-treatment
rule, not the drug-by-drug NCCN cross-reference tables that make up most
of the document's remaining length) — same condensing convention used for
Aetna's spinal-fusion and UHC's genetic-testing entries in this corpus.

Source document:

  Oncology medications (chemotherapy / cancer drug prior authorization):
     Cigna Medical Coverage Policies – Medical Oncology: Oncology Medications
     Policy, V2.0.2026, effective 07/01/2026, published 03/20/2026 by EviCore
     https://www.evicore.com/sites/default/files/clinical-guidelines/2026-03/Cigna%20Oncology%20Medications%20Policy_V2.0.2026_Eff07.01.2026_Pub03.20.2026_0.pdf

Usage: same as payer_policies_batch2_cigna.py — data-only, merged into
ingest_payer_policies_batch2.py's BATCH_MODULES list.
"""

CIGNA_ONCOLOGY_COVERED = """All medications approved by the United States Food & Drug Administration (FDA) and used for the direct treatment of cancer are subject to governance within this policy. All hematopoietic growth factors, myeloprotective agents, erythroid maturation agents, fibroblast growth factor 23 inhibitors, antiemetic agents, bone modifying agents, somatostatin analogues, tryptophan hydroxylase inhibitors and otoprotectants for cisplatin induced hearing loss approved by the FDA and used for the supportive treatment of cancer are also subject to governance within this document.

EviCore recognizes all injectable, oral, and topical oncology medications listed for a specific oncologic direct treatment indication in the National Comprehensive Cancer Network (NCCN) Guidelines with Categories of Evidence and Consensus of 1, 2A, or 2B as evidence-based standards of care and medically necessary. This also includes alignment with the NCCN statement that any FDA-approved biosimilar is an appropriate substitute for any recommended systemic biologic therapy. All FDA-approved medications used for direct cancer treatment not currently addressed in the NCCN Guidelines will be recognized as medically necessary when used in accordance with the FDA indication. All drugs used for direct treatment of cancer require prior authorization unless listed as an exempted medication (hormonal agents including anastrozole, letrozole, tamoxifen; oral antimetabolites including oral methotrexate and oral 6-mercaptopurine; oral and injectable corticosteroids including dexamethasone and prednisone; select NSAIDs including celecoxib; select antimicrobials including doxycycline; and doxazosin mesylate).

EviCore acknowledges that not all medically necessary treatments will conform to NCCN Guidelines based on patient variability and unique clinical circumstances. Approximately 85% of primary treatment regimens authorized under the EviCore Medical Oncology solution have NCCN consensus support; the remaining regimen approvals primarily encompass rare cancers or subtypes not addressed by NCCN, or clinically appropriate exceptions based on individual patient and/or disease factors, evaluated using peer-reviewed scientific articles, clinical practice guidelines from professional or medical specialty societies, coverage policies of government or commercial payers, FDA indications, and clinical expertise of experienced board-certified oncology practitioners through real-time peer consultation.

Medications used as supportive care in cancer treatment — to prevent and treat clinical symptoms that result from primary cancer treatment medications or from the disease itself — are governed by this same NCCN Category 1/2A/2B medical-necessity standard. Uses that are not associated with treatment of cancer-related symptoms are outside the scope of this policy, as are all oncology medication uses related to stem cell or bone marrow transplantation (mobilization, harvest, transplant, supportive care, and graft-versus-host disease)."""

POLICIES = [
    {
        "policyId": "CIGNA-ONCOLOGY-MEDS-2026",
        "policyName": "Oncology Medications Policy (V2.0.2026)",
        "policyType": "Coverage Policy",
        "payerName": "Cigna",
        "effectiveDate": "2026-07-01",
        "documentPath": "https://www.evicore.com/sites/default/files/clinical-guidelines/2026-03/Cigna%20Oncology%20Medications%20Policy_V2.0.2026_Eff07.01.2026_Pub03.20.2026_0.pdf",
        "criteria": [
            ("COVERED_INDICATIONS", CIGNA_ONCOLOGY_COVERED, "Section 1/1a/1b/2: Primary and Supportive Cancer Treatment Medications"),
        ],
    },
]
