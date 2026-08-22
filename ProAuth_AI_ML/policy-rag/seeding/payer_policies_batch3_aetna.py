"""
Aetna Payer Policy Ingestion — Batch 3
=========================================

One additional real, current, publicly-accessible Aetna Clinical Policy
Bulletin, extending batch 2's ten entries. source=PUBLIC_PAYER_POLICY.
aetna.com's live page (https://www.aetna.com/cpb/medical/data/300_399/0325.html)
returned HTTP 403 to an automated fetch this session (same blocking behavior
documented for the original bariatric-surgery entry in
ingest_payer_policies.py, though inconsistent with batch 2's ten CPBs, which
fetched cleanly — access patterns evidently vary by page/session). Worked
around the same way as the original bariatric entry: a third-party archive
mirror of the live page
(https://theverdengroup.thunderstone.cloud/custom/Aetna%202/Physical%20Therapy%20-%20Medical%20Clinical%20Policy%20Bulletins%20_%20Aetna.pdf,
a dated capture showing "1/13/26, 10:08 PM" in its own header) was fetched
and converted to text with `pdftotext -layout`, then cross-checked against
the live page's own policy number (0325) and review-date metadata, which
were independently confirmed via web search before use. Text below is the
payer's own words, unedited, not paraphrased or summarized, reformatted
only by flattening the source's lettered/numbered outline into flowing
paragraphs — same convention as every other entry in this corpus.

Source document:

  Physical therapy:
     Clinical Policy Bulletin 0325 — Physical Therapy,
     last review 10/29/2025, effective 07/20/1999, next review 03/26/2026
     https://www.aetna.com/cpb/medical/data/300_399/0325.html

Usage: same as payer_policies_batch2_aetna.py — data-only, merged into
ingest_payer_policies_batch2.py's BATCH_MODULES list (which despite its
"batch2" filename is the generic loader for every batch, this one included).
"""

AETNA_PT_COVERED = """Aetna considers physical therapy (PT) medically necessary to significantly improve, develop or restore physical functions lost or impaired as a result of a disease, injury or surgical procedure, when the following criteria are met: the member's licensed health care practitioner has determined that the member's condition can improve significantly based on physical measures (e.g., active range of motion, strength, function or subjective report of pain level) within one month of the date that therapy begins, or the therapy services proposed must be necessary for the establishment of a safe and effective maintenance program that will be performed by the member without ongoing skilled therapy services, and these services must be proposed for the treatment of a specific illness or injury; and the PT services provided are intended to cover only episodes of therapy for situations where there must be a reasonable expectation that a member's condition will improve significantly in a reasonable and generally predictable period of time; and PT services must be performed by a duly licensed and certified, if applicable, PT provider, within the applicable scope of practice for the provider in their licensed jurisdiction; and the services provided must be of the complexity and nature to require that they are performed by a licensed professional therapist or provided under the supervision of a licensed ancillary person as permitted under state laws (physicians, as they are not licensed as physical therapists, may not directly supervise physical therapy assistants); and PT must be provided in accordance with an ongoing, written plan of care of sufficient detail and including appropriate objective and subjective data to demonstrate medical necessity.

Physical therapy in asymptomatic persons or in persons without an identifiable clinical condition is considered not medically necessary. Physical therapy in persons whose condition is neither regressing nor improving is considered not medically necessary. Once therapeutic benefit has been achieved, or a home exercise program could be used for further gains, continuing supervised physical therapy is not considered medically necessary.

Home-based physical therapy is considered medically necessary in selected cases based upon the member's needs, in order to address the member's functional performance and functional needs in the home environment, or as part of the transition from skilled therapy to a maintenance program. In Aetna HMO, QPOS, Health Network Only, and Health Network Option plans, such short-term physical therapy accumulates towards the 60-day limit or other applicable rehabilitation benefit limits."""

AETNA_PT_NON_COVERED = """The following physical therapy interventions are considered experimental, investigational, or unproven because the effectiveness of these approaches has not been established (not an all-inclusive list): adhesion removal physical therapy for bowel obstructions; Applied Functional Science; blood flow restriction therapy; Dynamic Movement Intervention; Kinesio taping/McConnell taping/taping for back pain, radicular pain syndromes, and other back-related conditions, for lower extremity spasticity, meralgia paresthetica, post-operative subacromial decompression, wrist injury, prevention of ankle sprains, and all other indications, and McConnell taping for knee pain, low back pain, and all other indications; "hands-free" ultrasound and low-frequency sound (infrasound); Hivamat therapy (deep oscillation therapy); Interactive Metronome program; low-dye strapping for the treatment of stress fracture of the ankle; MEDEK therapy; RomTech PortableConnect; strapping of the chest and/or hip for the treatment of pain and improvement of posture; ultrasound therapy for the treatment of Dupuytren's contracture; and virtual reality facilitated gait training.

Standard Aetna policies exclude coverage for educational training or services — physical therapy is not covered when provided in educational settings under plans with this exclusion. Sports rehabilitation — continued treatment for sports-related injuries to improve above and beyond normal ability to perform activities of daily living — is not covered because it is not considered treatment of disease; this includes but is not limited to organized team sports, martial arts, competitive weightlifting, and professional or amateur/hobby athletic and dance activities at a school or community setting."""

POLICIES = [
    {
        "policyId": "AETNA-PT-0325",
        "policyName": "Physical Therapy — Clinical Policy Bulletin 0325",
        "policyType": "Clinical Policy Bulletin",
        "payerName": "Aetna",
        "effectiveDate": "1999-07-20",
        "documentPath": "https://www.aetna.com/cpb/medical/data/300_399/0325.html",
        "criteria": [
            ("COVERED_INDICATIONS", AETNA_PT_COVERED, "I. Medical Necessity"),
            ("NON_COVERED_INDICATIONS", AETNA_PT_NON_COVERED, "II. Experimental, Investigational, or Unproven / III. Policy Limitations and Exclusions"),
        ],
    },
]
