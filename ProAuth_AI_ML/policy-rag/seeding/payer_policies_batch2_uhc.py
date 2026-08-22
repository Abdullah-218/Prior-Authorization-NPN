"""
UnitedHealthcare Policy Ingestion — Batch 2
=============================================

Real, current, publicly-accessible UnitedHealthcare Commercial and
Individual Exchange policy documents — source=PUBLIC_PAYER_POLICY (not
CMS, not synthetic). Each PDF was fetched directly from uhcprovider.com
with curl and re-extracted with `pdftotext -layout` (same approach used
in ingest_payer_policies.py — WebFetch's summarizer is lossy on these
PDFs). The text below is the payer's own words, unedited, taken verbatim
from each document's "Coverage Rationale" section (or, for the pharmacy
program, its "Coverage Criteria" section).

This batch covers 5 of the 10 requested categories. The other 5 were
investigated and explicitly SKIPPED — see the note at the bottom of this
docstring for why. In every skipped case, UnitedHealthcare's own public
commercial policy document exists but explicitly delegates the actual
medical-necessity criteria to a licensed InterQual® guideline that is
not reproduced in the public document and is not itself publicly
accessible — so there was no real, complete, payer-authored
covered-indications text to extract without fabricating or paraphrasing
from a source we could not read.

Source documents (5 verified):
  UHC: Implanted Electrical Stimulator for the Spinal Cord — Commercial and
       Individual Exchange Medical Policy, Policy Number 2026T0567DD,
       effective 01/01/2026
       https://www.uhcprovider.com/content/dam/provider/docs/public/policies/comm-medical-drug/implanted-electrical-stimulator-spinal-cord.pdf

  UHC: Continuous Glucose Monitoring and Insulin Delivery for Managing
       Diabetes — Commercial and Individual Exchange Medical Policy,
       Policy Number 2026T0347XX, effective 08/01/2026
       https://www.uhcprovider.com/content/dam/provider/docs/public/policies/comm-medical-drug/continuous-glucose-monitoring-insulin-delivery-managing-diabetes.pdf

  UHC: Magnetic Resonance Imaging (MRI) and Computed Tomography (CT) Scan —
       Site of Service, Commercial and Individual Exchange Medical Policy,
       Policy Number MP.13.19, effective 01/01/2026
       https://www.uhcprovider.com/content/dam/provider/docs/public/policies/comm-medical-drug/mri-ct-scan-site-of-service.pdf

  UHC: Plans with Weight Loss/Appetite Suppression Medication Coverage —
       UnitedHealthcare Pharmacy Clinical Pharmacy Program, Prior
       Authorization/Notification, Program Number 2026 P 1114-21,
       effective 07/01/2026
       https://www.uhcprovider.com/content/dam/provider/docs/public/prior-auth/drugs-pharmacy/commercial/r-z/PA-Notification-Weight-Loss.pdf

  UHC: Interspinous Fusion and Decompression Devices — Commercial and
       Individual Exchange Medical Policy, Policy Number 2026T0638H,
       effective 01/01/2026
       https://www.uhcprovider.com/content/dam/provider/docs/public/policies/comm-medical-drug/interspinous-fusion-decompression-devices.pdf

Categories investigated and SKIPPED (no complete payer-authored
covered-indications text found — see final report for detail):
  1. CPAP / positive airway pressure therapy — both the "Obstructive and
     Central Sleep Apnea Treatment" policy (2026T0525UU) and the "Durable
     Medical Equipment..." policy (MP.009.35) state PAP devices are
     "considered medically necessary in certain clinical scenarios" and
     then delegate entirely to InterQual® CP: Durable Medical Equipment,
     Noninvasive Airway Assistive Devices — no named covered indications
     appear in UHC's own text, only narrow non-covered/unproven carve-outs.
  2. Spinal fusion (general lumbar) — "Spinal Fusion and Decompression"
     (2026T0639I) likewise delegates entirely to InterQual®; only the
     unproven-procedures list (dynamic stabilization, facet joint
     replacement, etc.) is in UHC's own words. (A narrower, genuinely
     self-contained spinal-fusion policy — interspinous fixation devices —
     was found and IS included above.)
  7. Cardiac catheterization / PCI — no standalone UHC commercial medical
     policy exists; PCI review is routed through the Cardiology Prior
     Authorization program (InterQual-based) or, for Oxford only, an
     eviCore arrangement — neither publishes payer-authored covered-
     indications text.
  8. Outpatient dialysis / ESRD — no standalone current commercial medical
     policy found; the previously indexed "Home Hemodialysis" URL now
     404s, and the commercial policy index page lists no ESRD/dialysis
     medical-necessity policy.
  9. Home oxygen therapy — no standalone commercial medical policy exists;
     the DME/Orthotics general policy (MP.009.35) mentions oxygen only as
     an example of a covered supply item (tubing/mask) and in clinical-
     evidence citations for other conditions, never as its own coverage
     rationale.
  10. Total knee/hip replacement (arthroplasty) — both "Surgery of the Hip"
      (2026T0503JJ) and "Surgery of the Knee" (2026T0553II) delegate TJR
      medical necessity entirely to InterQual®; only narrow FAI/cartilage-
      repair exclusion language is in UHC's own words.

Usage:
    This file only defines POLICIES for reference by ingest_payer_policies.py
    or an equivalent loader — it does not perform ingestion itself.
"""

UHC_SCS_COVERED = """Implanted electrical spinal cord stimulators are proven and medically necessary for treating the following conditions in certain circumstances when performed according to U.S. Food and Drug Administration (FDA) labeled indications, contraindications, warnings, and precautions: Complex regional pain syndrome (CRPS); Painful diabetic neuropathy; Failed back surgery syndrome.

Dorsal root ganglion (DRG) stimulation is proven and medically necessary for treating the following condition in certain circumstances when performed according to U.S. Food and Drug Administration (FDA) labeled indications, contraindications, warnings, and precautions: Complex regional pain syndrome (CRPS I, CPRS II).

Note: Coverage of a replacement battery/generator for a previously implanted electrical stimulator is appropriate when the individual's existing battery/generator is malfunctioning, cannot be repaired, and is no longer under warranty."""

UHC_SCS_NON_COVERED = """Implanted electrical spinal cord stimulators are unproven and not medically necessary for treating the following conditions due to insufficient evidence of efficacy: Chronic intractable back pain without prior spine surgery; Refractory angina pectoris.

Dorsal root ganglion (DRG) stimulation is unproven and not medically necessary for treating all other conditions due to insufficient evidence of efficacy."""

UHC_CGM_COVERED = """Insulin Delivery: When used according to U.S. Food and Drug Administration (FDA)-labeled indications, contraindications, warnings, and precautions, external continuous subcutaneous insulin infusion pumps (including Omnipod) are proven and medically necessary in certain circumstances.

External continuous subcutaneous insulin infusion pumps are medically necessary for managing individuals with diabetes due to causes, other than type 1, type 2, or gestational diabetes, that require intensive insulin therapy (insulin treated at least three times a day). Examples include but are not limited to cystic fibrosis-related diabetes, posttransplant diabetes, and diabetes following pancreatic surgery.

Short-Term Continuous Glucose Monitoring (3-14 Days): Short-term continuous glucose monitoring (CGM) use by a health care provider for diagnostic purposes is proven and medically necessary for managing individuals with diabetes.

Long-Term Continuous Glucose Monitoring (Greater Than 14 Days): Coverage criteria noted below must be met whether the request comes through the UnitedHealthcare prior authorization process (type 2 or gestational diabetes) or a contracted supplier (type 1 diabetes). Duration of approved authorization: Initial CGM authorization will be for up to 6 months; Reauthorization will be for up to 12 months.

Nonimplantable Continuous Glucose Monitoring — Intensive Insulin Therapy: When used according to FDA-labeled indications, contraindications, warnings, and precautions, initial long-term CGM use is proven and medically necessary in certain circumstances. For continued long-term use, CGM is proven and medically necessary when all the following criteria are met: Device is used according to FDA-labeled indications, contraindications, warnings, and precautions; Medical necessity clinical coverage criteria are met; Individual is assessed by a provider every 6 months for adherence to the prescribed CGM regimen and treatment plan.

Nonintensive Diabetes Therapy: Initial long-term CGM is medically necessary for managing individuals with diabetes on a nonintensive treatment plan (e.g., basal insulin and/or oral medications) who have a history of a level 3 hypoglycemic event or recurrent (more than one) level 2 hypoglycemic events that persist despite multiple (more than one) attempts to adjust medication(s) and/or modify the diabetes treatment plan. Continued long-term CGM is medically necessary for managing individuals with diabetes on a nonintensive treatment plan (e.g., basal insulin and/or oral medications) when all the following criteria are met: Clinical criteria for initial use noted above were met at initiation of CGM; Individual is assessed by a provider every 6 months for adherence to the prescribed CGM regimen and treatment plan.

Implantable Continuous Glucose Monitoring: Initial long-term CGM using an implantable glucose sensor (e.g., Eversense) is medically necessary for managing individuals with diabetes when all the following criteria are met: Device is used according to FDA-labeled indications, contraindications, warnings, and precautions; Age >= 18 years; One of the following: Individual requires intensive insulin therapy (insulin treated at least three times a day or insulin pump); or Individual has a history of a level 3 hypoglycemic event or recurrent (more than one) level 2 hypoglycemic events that persist despite multiple (more than one) attempts to adjust medication(s) and/or modify the diabetes treatment plan.

Continued long-term CGM using an implantable glucose sensor (e.g., Eversense) is medically necessary for managing individuals with diabetes when all the following criteria are met: Individual continues to require intensive insulin therapy (insulin treated at least three times a day or insulin pump) or clinical criteria for initial use noted above were met at initiation of CGM for Hypoglycemia; Individual is assessed by a provider every 6 months for adherence to the prescribed CGM regimen and treatment plan."""

UHC_CGM_NON_COVERED = """The following devices are unproven and not medically necessary for managing individuals with diabetes due to insufficient evidence of efficacy: Implantable insulin pumps; Nonprogrammable transdermal insulin delivery systems (e.g., V-Go).

Long-term CGM is unproven and not medically necessary for managing individuals with diabetes on a nonintensive treatment plan (e.g., basal insulin and/or oral medications) for all other indications.

The use of a noninvasive CGM device is unproven and not medically necessary for managing individuals with diabetes due to insufficient evidence of efficacy."""

UHC_MRI_CT_SOS_COVERED = """A magnetic resonance imaging (MRI) or computed tomography (CT) imaging procedure in the hospital outpatient department is considered medically necessary for individuals who meet any of the following criteria: Are participating in a clinical trial that requires a specific imaging protocol or equipment not available in a freestanding facility; Are scheduled for the MRI/CT imaging procedure within 24 hours of a hospital specialist appointment at the same hospital-based facility where the procedure is requested; Have a known allergy to a contrast agent used for the procedure; Have a known chronic disease undergoing active treatment, when direct comparison to prior studies requires the same imaging protocol or equipment obtained at the same hospital-based facility where the procedure is requested; Have a systemic cancer on active treatment, when restaging studies require the same imaging protocol or equipment used for prior studies obtained at the same hospital-based facility where the procedure is requested; Pre-procedure imaging which is done within 24 hours of the interventional or surgical procedure and is an integral part of the planned procedure; Require obstetrical observation; Require perinatology services; Under 18 years of age.

An MRI/CT imaging procedure in the hospital outpatient department is also considered medically necessary when there are no geographically accessible appropriate alternative sites for the individual to undergo the procedure, including but not limited to the following: Moderate or deep sedation or general anesthesia is required for the procedure and a freestanding facility providing such sedation is not available; or The equipment for the size of the individual is not available; or Open MRI is required because the member has a documented diagnosis of claustrophobia and/or severe anxiety which is not available in a freestanding facility.

An MRI/CT imaging procedure in the hospital outpatient department is considered medically necessary when imaging in a physician's office or freestanding imaging center would reasonably be expected to delay care and adversely impact health outcome.

Note: Authorization is not required for procedures performed in an emergency room, observation unit, urgent care center, or during an inpatient stay."""

UHC_MRI_CT_SOS_NON_COVERED = """All other MRI/CT imaging procedures at a hospital-based imaging department or facility are considered not medically necessary. This includes but is not limited to imaging for: Cancer screening; Initial diagnosis and/or initial staging for suspected or known cancer; Non-cancerous musculoskeletal conditions; Surveillance of cancer in remission with no clinical suspicion for change in disease status."""

UHC_GLP1_WEIGHT_LOSS_COVERED = """This is an optional program that is put in place for clients or businesses that have elected to cover weight loss products with Prior Authorization/Notification. It is also designed to meet regulatory requirements for coverage of weight loss medications in California, New Mexico, North Dakota Essential Health Benefits (EHB) and New York.

Initial Authorization — benzphetamine, Contrave, diethylpropion, phentermine, phendimetrazine, Qsymia, Saxenda, Wegovy injection, Wegovy tablet, Xenical or Zepbound (includes both brand and generic versions and all formulations of the listed products unless otherwise noted) will be approved based on all of the following criteria:

One of the following: Treatment is being requested for appetite suppression or weight loss; or Wegovy injection or tablet is being requested for risk reduction of major adverse cardiovascular events with established cardiovascular disease (i.e., prior myocardial infarction, ischemic or hemorrhagic stroke, or peripheral arterial disease); or Wegovy injection is being requested for treatment of metabolic dysfunction-associated steatohepatitis (MASH) [formerly known as nonalcoholic steatohepatitis (NASH)] with moderate to advanced liver fibrosis (i.e., fibrosis stage F2 or F3); or Zepbound is being requested for moderate to severe obstructive sleep apnea.

And one of the following: Patient is >= 12 years of age (for Qsymia, Saxenda, Wegovy injection and Xenical); or Patient is > 16 years of age (for all other medications).

And: Used as an adjunct to lifestyle modification (e.g., dietary or caloric restriction, exercise, behavioral support, community-based program).

And one of the following: Body Mass Index (BMI) >= 30 kg/m2 or for pediatric patients a BMI > 95th percentile; or both of the following: BMI >= 27 kg/m2 and Patient has a weight-related comorbidity (e.g., dyslipidemia, hypertension, type 2 diabetes, sleep apnea); or Wegovy injection is being requested for treatment of MASH.

Authorization duration: benzphetamine, diethylpropion, phendimetrazine, phentermine: 3 months. Contrave, Qsymia or Saxenda: 4 months. Wegovy injection or tablet: 5 months. Xenical or Zepbound: 6 months.

Imcivree (setmelanotide) will be approved based on all of the following criteria: One of the following: Diagnosis of obesity is due to POMC, PCSK1, or LEPR gene deficiency confirmed with genetic testing interpreted as pathogenic, likely pathogenic, or of uncertain significance; or Diagnosis of Bardet-Biedl syndrome. And one of the following: Adult patient with BMI >= 30 kg/m2; or Pediatric patient with weight > 95th percentile for age on growth chart assessment. And: Patient is currently enrolled in or has history of a weight loss management program. Authorization will be issued for 6 months.

Vykat XR (diazoxide choline) will be approved based on all of the following criteria: Diagnosis of hyperphagia associated with Prader-Willi Syndrome; Prader-Willi Syndrome is confirmed by genetic testing; Patient is at least 4 years of age and older. Authorization will be issued for 12 months.

Reauthorization — benzphetamine, Contrave, diethylpropion, phentermine, phendimetrazine, Qsymia, Saxenda, Wegovy injection or tablet, Xenical or Zepbound will be approved based on both of the following criteria: One of the following: Weight loss of >= 3% of baseline body weight for Qsymia; or Weight loss of >= 4% of baseline body weight for Saxenda; or for Wegovy: (for Wegovy injection requested for MASH) documentation of positive clinical response and patient has not progressed to cirrhosis, or (for Wegovy injection or tablet requested for weight loss/CV risk reduction) weight loss of >= 5% of baseline body weight; or Weight loss of >= 5% of baseline body weight for all other appetite suppressants. And: Continuation of lifestyle modification. Authorization for Contrave, Qsymia, Saxenda, Wegovy injection or tablet, Xenical or Zepbound will be issued for 12 months. Authorization for benzphetamine, diethylpropion, phentermine or phendimetrazine will be issued for 6 months.

Imcivree reauthorization will be approved based on one of the following criteria: If on therapy for less than 12 months, documentation of a positive clinical response defined as weight loss >= 5% of baseline weight; or if on therapy for >= 12 months, documentation of a positive clinical response defined as >= 10% weight loss from baseline. Authorization will be issued for 12 months.

Vykat XR reauthorization will be approved based on the following criterion: Documentation of positive clinical response to Vykat XR therapy. Authorization will be issued for 12 months.

Note: Medications for the purpose of weight loss are typically a benefit exclusion; this program applies to plans that have elected to cover weight loss products with Prior Authorization/Notification. Refer to Nonformulary Wegovy and Nonformulary Zepbound criteria for plans that do not cover weight loss medications."""

UHC_INTERSPINOUS_FUSION_COVERED = """Interspinous fixation (fusion) devices are proven and medically necessary when performed according to U.S. Food and Drug Administration (FDA) labeled indications, contraindications, warnings, and precautions and all of the following criteria are met: Back pain of discogenic origin, with degeneration of the disc confirmed by history and radiographic studies; No more than grade 1 spondylolisthesis; Used with an interbody cage as an adjunct to fusion at a single level in the lumbar spine (L1-S1)."""

UHC_INTERSPINOUS_FUSION_NON_COVERED = """Interspinous decompression and interlaminar stabilization systems (without fusion) for the treatment of spine pain or spinal stenosis are unproven and not medically necessary due to insufficient evidence of efficacy."""

POLICIES = [
    {
        "policyId": "UHC-SCS-2026",
        "policyName": "Implanted Electrical Stimulator for the Spinal Cord — Commercial and Individual Exchange Medical Policy",
        "policyType": "Commercial Medical Policy",
        "payerName": "UnitedHealthcare",
        "effectiveDate": "2026-01-01",
        "documentPath": "https://www.uhcprovider.com/content/dam/provider/docs/public/policies/comm-medical-drug/implanted-electrical-stimulator-spinal-cord.pdf",
        "criteria": [
            ("COVERED_INDICATIONS", UHC_SCS_COVERED, "Coverage Rationale"),
            ("NON_COVERED_INDICATIONS", UHC_SCS_NON_COVERED, "Coverage Rationale"),
        ],
    },
    {
        "policyId": "UHC-CGM-2026",
        "policyName": "Continuous Glucose Monitoring and Insulin Delivery for Managing Diabetes — Commercial and Individual Exchange Medical Policy",
        "policyType": "Commercial Medical Policy",
        "payerName": "UnitedHealthcare",
        "effectiveDate": "2026-08-01",
        "documentPath": "https://www.uhcprovider.com/content/dam/provider/docs/public/policies/comm-medical-drug/continuous-glucose-monitoring-insulin-delivery-managing-diabetes.pdf",
        "criteria": [
            ("COVERED_INDICATIONS", UHC_CGM_COVERED, "Coverage Rationale"),
            ("NON_COVERED_INDICATIONS", UHC_CGM_NON_COVERED, "Coverage Rationale"),
        ],
    },
    {
        "policyId": "UHC-MRI-CT-SOS-2026",
        "policyName": "Magnetic Resonance Imaging (MRI) and Computed Tomography (CT) Scan — Site of Service, Commercial and Individual Exchange Medical Policy",
        "policyType": "Commercial Medical Policy",
        "payerName": "UnitedHealthcare",
        "effectiveDate": "2026-01-01",
        "documentPath": "https://www.uhcprovider.com/content/dam/provider/docs/public/policies/comm-medical-drug/mri-ct-scan-site-of-service.pdf",
        "criteria": [
            ("COVERED_INDICATIONS", UHC_MRI_CT_SOS_COVERED, "Coverage Rationale"),
            ("NON_COVERED_INDICATIONS", UHC_MRI_CT_SOS_NON_COVERED, "Coverage Rationale"),
        ],
    },
    {
        "policyId": "UHC-GLP1-WEIGHT-LOSS-2026",
        "policyName": "Plans with Weight Loss/Appetite Suppression Medication Coverage",
        "policyType": "Clinical Pharmacy Program — Prior Authorization/Notification",
        "payerName": "UnitedHealthcare",
        "effectiveDate": "2026-07-01",
        "documentPath": "https://www.uhcprovider.com/content/dam/provider/docs/public/prior-auth/drugs-pharmacy/commercial/r-z/PA-Notification-Weight-Loss.pdf",
        "criteria": [
            ("COVERED_INDICATIONS", UHC_GLP1_WEIGHT_LOSS_COVERED, "Coverage Criteria"),
        ],
    },
    {
        "policyId": "UHC-INTERSPINOUS-FUSION-2026",
        "policyName": "Interspinous Fusion and Decompression Devices — Commercial and Individual Exchange Medical Policy",
        "policyType": "Commercial Medical Policy",
        "payerName": "UnitedHealthcare",
        "effectiveDate": "2026-01-01",
        "documentPath": "https://www.uhcprovider.com/content/dam/provider/docs/public/policies/comm-medical-drug/interspinous-fusion-decompression-devices.pdf",
        "criteria": [
            ("COVERED_INDICATIONS", UHC_INTERSPINOUS_FUSION_COVERED, "Coverage Rationale"),
            ("NON_COVERED_INDICATIONS", UHC_INTERSPINOUS_FUSION_NON_COVERED, "Coverage Rationale"),
        ],
    },
]
