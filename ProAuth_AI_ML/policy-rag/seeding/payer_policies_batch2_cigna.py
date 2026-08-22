"""
Private Payer Policy Ingestion — Cigna Batch 2
=================================================

Second batch of real, current, publicly-accessible Cigna coverage
policies/guidelines — source=PUBLIC_PAYER_POLICY. Cigna publishes some
Coverage Policies directly (cignaforhcp.cigna.com / static.cigna.com) and
routes several utilization-management categories through eviCore (Cigna's
UM partner, evicore.com). Both were checked for each of the 10 requested
categories. Each PDF was fetched directly and re-extracted with
`pdftotext -layout` (the same discipline as `ingest_payer_policies.py`),
then hand-curated into the policy/criteria structure below. The text
below is the payer's own words — bullet/outline structure was flattened
into prose (colons/semicolons in place of nested bullets) but no wording
was paraphrased, summarized, or invented. Two of the ten requested
categories (outpatient dialysis/ESRD services, and home oxygen therapy)
were searched but no distinct, current, standalone Cigna/eviCore public
coverage bulletin could be verified for them — see the module's ingest
report; they are intentionally omitted from POLICIES below rather than
approximated from an adjacent document.

Source documents:
  Bariatric Surgery and Procedures, Cigna Medical Coverage Policy Number
    0051, effective 07/15/2026
    https://static.cigna.com/assets/chcp/pdf/coveragePolicies/medical/mm_0051_coveragepositioncriteria_bariatric_surgery.pdf

  Lumbar Fusion (Arthrodesis) Guidelines, CMM-609, published by eviCore
    (Cigna's UM partner), V2.0.2025, effective 12/18/2025
    https://www.evicore.com/sites/default/files/clinical-guidelines/2025-11/Cigna%20CMM-609%20Lumbar%20Fusion_Final_V2.0.2025_Eff12.18.2025_pub11.18.2025.pdf

  Weight Loss – Glucagon-Like Peptide-1 Agonists Prior Authorization
    Policy (covers Wegovy/semaglutide, Zepbound/tirzepatide, Saxenda/
    liraglutide, Foundayo/orforglipron), Cigna National Formulary
    Coverage Policy cnf_684, review date 07/09/2025, most recent revision
    04/15/2026
    https://static.cigna.com/assets/chcp/pdf/coveragePolicies/cnf/cnf_684_coveragepositioncriteria_weight_loss_glp1_agonists_pa.pdf

  Spinal Cord and Dorsal Root Ganglion Stimulation, CMM-211, published
    by eviCore (Cigna's UM partner), effective 07/01/2025
    https://www.evicore.com/sites/default/files/clinical-guidelines/2025-03/Cigna_Spinal%20Cord%20and%20Dorsal%20Root%20Ganglion%20Stimulation%20(CMM-211)_FINAL_V1.0.2025_pub03.19.2025.pdf

  Preface to the Imaging Guidelines (general advanced-imaging prior
    authorization requirements — applies across Cigna's eviCore-managed
    CT/MRI/PET imaging guidelines), V2.0.2025, effective 05/15/2025
    https://www.evicore.com/sites/default/files/clinical-guidelines/2025-03/Cigna_Preface%20to%20the%20Imaging%20Guidelines_V2.0.2025_Eff05.15.2025_pub03.28.2025.pdf

  Diabetes – Continuous Glucose Monitoring Systems Prior Authorization
    Policy, Cigna National Formulary Coverage Policy cnf_676, review date
    01/21/2026
    https://static.cigna.com/assets/chcp/pdf/coveragePolicies/cnf/cnf_676_coveragepositioncriteria_diabetes_continuous_glucose_monitoring_systems_pa.pdf

  Cardiac Imaging Guidelines (Diagnostic Left/Right Heart Catheterization
    and Planned/Staged Percutaneous Coronary Intervention sections,
    CD-7.3 through CD-7.6), published by eviCore (Cigna's UM partner),
    V2.0.2025, effective 10/01/2025
    https://www.evicore.com/sites/default/files/clinical-guidelines/2025-09/Cigna_Cardiac%20Imaging%20Guidelines_V2.0.2025_Eff10.01.2025_pub09.17.2025.pdf

  CMM-311: Knee Replacement/Arthroplasty, published by eviCore (Cigna's
    UM partner), V2.0.2025, effective 03/07/2026
    https://www.evicore.com/sites/default/files/clinical-guidelines/2025-11/Cigna_CMM-311%20Knee%20Replacement%20Arthroplasty_V2.0.2025_Eff03.07.2026_Pub11.21.2025.pdf

  CMM-313: Hip Replacement/Arthroplasty, published by eviCore (Cigna's
    UM partner), V2.0.2025, effective 03/07/2026
    https://www.evicore.com/sites/default/files/clinical-guidelines/2025-11/Cigna_CMM-313%20Hip%20Replacement%20Arthro_V2.0.2025_Eff03.07.2026_Pub11.21.2025.pdf

Usage:
    This module only defines POLICIES; it does not ingest. To load these
    into the database, import POLICIES into ingest_payer_policies.py's
    flow (or extend that script), following the same chunk/embed/insert
    logic already defined there.
"""

CIGNA_BARIATRIC_COVERED = """Bariatric surgery for the treatment of obesity in an adult (age >= 18 years) using a covered procedure is considered medically necessary when ALL of the following criteria are met: EITHER BMI (Body Mass Index) >=35 kg/m2 (class 2 obesity) (BMI >=27.5 kg/m2 in Asians, when ethnicity is confirmed by provider attestation); or BMI 30-34.9 kg/m2 (class 1 obesity) (BMI 25-27.4 kg/m2 in Asians, when ethnicity is confirmed by provider attestation) with at least one clinically significant obesity-related comorbidity, including but not limited to: mechanical arthropathy in a weight-bearing joint (symptomatic degenerative joint disease in a weight bearing joint); diabetes mellitus; poorly controlled hypertension (systolic blood pressure at least 140 mm Hg or diastolic blood pressure 90 mm Hg or greater, despite optimal medical management); hyperlipidemia; coronary artery disease; lower extremity lymphatic or venous obstruction; obstructive sleep apnea; pulmonary hypertension; evidence of fatty liver disease (i.e., metabolic dysfunction-associated steatotic liver disease [MASLD; previously termed nonalcoholic fatty liver disease (NAFLD)] or metabolic dysfunction-associated steatohepatitis [MASH; previously termed nonalcoholic steatohepatitis (NASH)]); or gastroesophageal reflux disease (GERD) refractory to medical therapy. AND a thorough multidisciplinary evaluation within the previous 12 months which includes ALL of the following: a description of the proposed procedure(s); documentation of failure of weight loss by medical management; unequivocal clearance for bariatric surgery by a mental health provider; a nutritional evaluation by a physician, physician assistant, nurse practitioner or registered dietician.

When the specific medical necessity criteria noted above for bariatric surgery for an adult have been met, ANY of the following open or laparoscopic bariatric surgical procedures for the treatment of obesity is considered medically necessary: vertical band gastroplasty; adjustable silicone gastric banding (e.g., LAP-BAND, REALIZE); sleeve gastrectomy as a stand-alone or staged procedure; Roux-en-Y gastric bypass (roux limb less than 150 cm); Roux-en-Y gastric bypass (roux limb greater than 150 cm); biliopancreatic diversion with duodenal switch (BPD/DS); biliopancreatic diversion (BPD) without DS; single-anastomosis duodenal-ileal bypass with sleeve gastrectomy (SADI-S) (i.e. loop duodenal switch); and endoscopic sleeve gastroplasty. Adjustment of a silicone gastric banding is considered medically necessary to control the rate of weight loss and/or treat symptoms secondary to gastric restriction following a medically necessary adjustable silicone gastric banding procedure."""

CIGNA_BARIATRIC_NON_COVERED = """The following bariatric surgical procedures for the treatment of obesity, when performed alone or in conjunction with another bariatric surgical procedure, are considered not medically necessary: gastric electrical stimulation (GES) or gastric pacing; and vagus nerve stimulation.

The following bariatric surgical procedures for the treatment of obesity, when performed alone or in conjunction with another bariatric surgical procedure, are considered experimental, investigational or unproven: band over bypass; band over sleeve; Fobi-Pouch (limiting proximal gastric pouch); intestinal bypass (jejunoileal bypass); intragastric balloon (e.g., Orbera, ReShape, Obalon); laparoscopic greater curvature plication; mini-gastric bypass/One Anastomosis Gastric Bypass (OAGB)/loop gastric bypass; endoscopic bariatric surgery procedures, including but not limited to Natural Orifice Transluminal Endoscopic Surgery (NOTES), restorative obesity surgery endoluminal (ROSE), StomaphyX, duodenojejunal bypass liner (e.g., Endobarrier), and transoral gastroplasty (e.g., TOGA); Transoral Outlet Reduction (TORe); Roux-en-Y gastric bypass combined with simultaneous gastric banding; stomach aspiration therapy (e.g., AspireAssist); and vagus nerve blocking (e.g., Maestro)."""

CIGNA_LUMBAR_FUSION_COVERED = """Lumbar fusion with decompression (indirect or direct) is considered medically necessary when performed for ANY of the following conditions when ALL of the associated criteria are met:

Actual Instability: the individual is a candidate for lumbar decompression or corpectomy per CMM-608: Lumbar Decompression; imaging shows degenerative spondylolisthesis without spondylolysis with either dynamic segmental instability on flexion-extension plain X-rays or comparison of a supine and upright image with a difference in translational alignment between vertebrae greater than 3 mm between views, or Meyerding Grade II or higher spondylolisthesis; or spondylolisthesis with spondylolysis (e.g. Isthmic Spondylolisthesis) with Meyerding Grade I or II spondylolisthesis (anterolisthesis) and plain X-rays supporting progression of anterolisthesis, or Meyerding Grade III or higher spondylolisthesis (anterolisthesis) with 50% or more anterior slippage or plain X-rays supporting progression of anterolisthesis, or progressive spinal pain without confirmatory imaging showing progression of spondylolisthesis, or multi-level spondylolysis on plain X-rays; or post-operative instability created by the disruption of the posterior elements due to facet joint excision that exceeds 50% bilaterally or 75% or more of a single facet; or pars fracture; or previous lumbar spinal decompression that resulted in iatrogenic spondylolisthesis. Criteria exception: when instability is created and/or identified intra-operatively, the above imaging criteria are NOT required. Documentation of nicotine-free status is also required, with the individual being a never-smoker, or having refrained from smoking, use of smokeless tobacco products, and/or nicotine replacement therapy for at least six (6) weeks prior to planned surgery as evidenced by blood cotinine lab results of <=10 ng/mL.

Anticipated Iatrogenic Instability: the individual is a candidate for lumbar decompression or corpectomy per CMM-608: Lumbar Decompression; anticipated iatrogenic instability is created by disruption of the posterior elements due to facet joint excision that exceeds 50% bilaterally or 75% or more of a single facet during spinal decompression, or created by removal of the pars interarticularis that requires fusion to stabilize, or created by decompression for Meyerding Grade I or higher spondylolisthesis with foraminal stenosis, or created by complete or partial corpectomy (i.e., removal of at least one-third of the vertebral body, not for resection of osteophytes alone); with the same nicotine-free documentation required as above.

Adult Degenerative Spinal Deformity: the individual is a candidate for lumbar decompression or corpectomy per CMM-608: Lumbar Decompression; imaging findings include coronal plane deformity (Cobb angle greater than 30 degrees, asymmetric disk collapse causing symptomatic foraminal narrowing, or coronal imbalance causing head and trunk shift off the midline) or sagittal imbalance (sagittal vertebral axis measurement greater than 8 cm, or pelvic incidence-lumbar lordosis greater than 15 degrees); with the same nicotine-free documentation required as above.

Initial Disc Herniation: the individual is a candidate for an initial primary lumbar discectomy; advanced imaging shows a primary extraforaminal disc herniation at L5-S1 in which a far lateral approach is not feasible because of the presence of the iliac wings, or a primary foraminal disc herniation for which facet resection is necessary to retrieve the disc which will result in iatrogenic instability, or a primary disc herniation in the lumbar spine that is at the level of the spinal cord (i.e., low lying conus medullaris); with the same nicotine-free documentation required as above.

Recurrent Disc Herniation: the individual is a candidate for repeat lumbar discectomy; imaging shows evidence of anterolisthesis at the requested level(s) that results in dynamic segmental instability on flexion-extension plain X-rays or comparison of a supine and upright image with a difference in translational alignment between vertebrae greater than 3 mm between views, or Meyerding Grade II or higher spondylolisthesis; with the same nicotine-free documentation required as above."""

CIGNA_LUMBAR_FUSION_NON_COVERED = """Lumbar fusion performed without meeting the criteria in the General Guidelines section (when applicable for urgent/emergent conditions) and the criteria in the applicable procedure-specific section(s) -- pediatric spinal deformity; fusion with decompression; fusion without decompression; adjacent segment disease; fusion following failed disc arthroplasty; or repeat fusion -- is considered not medically necessary. Lumbar osteotomy performed without meeting the corresponding General Guidelines and procedure-specific criteria is likewise considered not medically necessary. Lumbar fusion and/or osteotomy performed for ANY of the following sole indications is considered not medically necessary: disc herniation in the absence of a primary extraforaminal disc herniation at L5-S1 in which a far lateral approach is not feasible because of the presence of the iliac wings, a primary foraminal disc herniation for which facet resection is necessary to retrieve the disc which will result in iatrogenic instability, or a primary disc herniation in the lumbar spine that is at the level of the spinal cord (i.e., low lying conus medullaris); multi-level degenerative disc disease without instability; neurocompressive pathology; facet joint disorders without instability; initial discectomy/laminectomy without instability; an adjunct to primary decompression of central and/or lateral recess stenosis in the absence of instability, spondylolisthesis, or an actual or anticipated bony resection that will result in iatrogenic instability; or spondylolysis without spondylolisthesis.

Experimental, Investigational, or Unproven (EIU): ALL of the following devices/procedures are considered experimental, investigational, or unproven (not an all-inclusive list): pre-sacral interbody fusion including AxiaLIF; minimally invasive lumbar spinal fusions using direct visualization via endoscopy (endoscopic fusion) or indirect visualization (e.g., percutaneous fusion); anterior interbody fusion or implantation of intervertebral body fusion devices using a laparoscopic approach; device/implant not FDA approved; dynamic (intervertebral) stabilization (e.g., Dynesys, Stabilimax NZ); interlaminar lumbar instrumented fusion (e.g., ILIF); interspinous and interlaminar distraction devices; interspinous fixation/posterior non-pedicle supplemental fixation devices for spinal fusion (e.g., Affix, Aspen Spinous Process Fixation System, Coflex-F); personalized anterior and lateral body interbody cage (implantable) (e.g., Aprevo); least invasive lumbar decompression interbody fusion (e.g., LINDIF); isolated facet fusion, with or without instrumentation, including allograft bone graft substitutes used exclusively as stand-alone stabilization devices (e.g., TruFuse [any level], NuFix [any level]); and total facet arthroplasty."""

CIGNA_GLP1_WEIGHTLOSS_COVERED = """Wegovy injection and Wegovy HD injection (semaglutide) are covered as medically necessary for Weight Loss in an Adult with Overweight or Obesity: Initial Therapy is approved for 8 months if the patient meets ALL of the following: patient is >= 18 years of age; patient has engaged in a trial of behavioral modification and dietary restriction for at least 3 months; patient meets ONE of the following -- at baseline, patient had a BMI >= 30 kg/m2, OR patient meets BOTH of the following: at baseline, patient had a BMI >= 27 kg/m2, AND at baseline, patient had, or patient currently has, at least ONE of the following weight-related comorbidities: hypertension, type 2 diabetes, dyslipidemia, obstructive sleep apnea, cardiovascular disease, knee osteoarthritis, asthma, chronic obstructive pulmonary disease, metabolic dysfunction-associated steatotic liver disease/non-alcoholic fatty liver disease, polycystic ovarian syndrome, or coronary artery disease; and the medication will be used concomitantly with behavioral modification and a reduced-calorie diet. A patient currently receiving Wegovy injection, Wegovy HD injection, or Wegovy tablet is approved for 1 year if the patient meets ALL of the following: patient is >= 18 years of age; patient meets the same BMI/comorbidity criteria as above; patient has lost >= 5% of baseline body weight; and the medication will be used concomitantly with behavioral modification and a reduced-calorie diet.

Wegovy injection and Wegovy tablet are also covered for Major Adverse Cardiovascular Event(s) Risk Reduction in a Patient with Established Cardiovascular Disease with Overweight or Obesity: approved for 1 year if the patient meets ALL of the following: patient is >= 18 years of age; at baseline, patient had a BMI >= 27 kg/m2; patient has had a prior myocardial infarction, OR a prior stroke (not including a transient ischemic attack), OR a history of symptomatic peripheral arterial disease as evidenced by intermittent claudication with ankle-brachial index < 0.85, peripheral arterial revascularization procedure, or amputation due to atherosclerotic disease; the medication will be used in combination with optimized pharmacotherapy for established cardiovascular disease; and the medication will be used concomitantly with behavioral modification and a reduced-calorie diet.

Zepbound (tirzepatide) is covered as medically necessary for Weight Loss in an Adult with Overweight or Obesity, on the same Initial Therapy (8 months) and continuation (1 year, >= 5% weight loss) criteria as Wegovy above. Zepbound is separately covered for Obstructive Sleep Apnea, Moderate to Severe, in a Patient with Obesity: Initial Therapy is approved for 1 year if the patient meets ALL of the following: patient is >= 18 years of age; at baseline, patient had a BMI >= 30 kg/m2; patient has had a sleep study showing a diagnosis of moderate to severe obstructive sleep apnea with an apnea-hypopnea index >= 15 events per hour (a diagnosis of moderate OSA is an apnea-hypopnea index of >= 15 events per hour and a diagnosis of severe OSA is an apnea-hypopnea index >= 30 events per hour); the patient does NOT have central sleep apnea or Cheyne Stokes respiration; and the medication will be used concomitantly with behavioral modification and a reduced-calorie diet. A patient currently receiving Zepbound for OSA is approved for continuation if the patient meets ALL of the following: patient is >= 18 years of age; at baseline, patient had a BMI >= 30 kg/m2; and patient has completed >= 1 year of therapy with Zepbound and has lost >= 10% of baseline body weight."""

CIGNA_CGM_COVERED = """Continuous glucose monitoring (CGM) systems (Dexcom G6, Dexcom G7, Eversense 365, Freestyle Libre, Freestyle Libre 2, Freestyle Libre 3, Freestyle Libre 2 Plus, Freestyle Libre 3 Plus, Freestyle Libre 14 day, Guardian 3, Guardian 4, MiniMed Instinct, Simplera, and Simplera Sync) are covered as medically necessary when the following criteria are met for FDA-approved indications: for Diabetes, approve for 1 year if the patient meets ONE of the following (A or B): (A) patient is using an insulin regimen (this includes patients on a basal insulin regimen, basal and prandial insulin regimen, prandial insulin regimen, or continuous subcutaneous insulin infusion / insulin pump); OR (B) patient is taking a medication for glycemic control other than insulin AND meets ONE of the following: Initial Therapy is approved if the patient had a level 2 hypoglycemia event (blood glucose value < 54 mg/dL) in the past 6 months, OR a level 3 hypoglycemia event (a severe event characterized by altered mental and/or physical status requiring assistance for treatment of hypoglycemia, irrespective of glucose level) in the past 6 months; a patient currently receiving a CGM system is approved if the patient had a level 2 or level 3 hypoglycemia event in the 6 months prior to the initial CGM prescription. For Diabetes in a Pregnant Patient (type 1 diabetes, type 2 diabetes, or gestational diabetes), approve for 9 months."""

CIGNA_CGM_NON_COVERED = """Continuous glucose monitoring (CGM) systems (Dexcom G6, Dexcom G7, Eversense 365, Freestyle Libre, Freestyle Libre 2, Freestyle Libre 3, Freestyle Libre 2 Plus, Freestyle Libre 3 Plus, Freestyle Libre 14 day, Guardian 3, Guardian 4, MiniMed Instinct, Simplera, and Simplera Sync) are considered not medically necessary for ANY other use(s); criteria will be updated as new published data are available."""

CIGNA_SCS_COVERED = """A short-term trial (i.e., greater than 48 hours) spinal cord stimulation (i.e., non-high-frequency or high-frequency [HF10 SCS]) is considered medically necessary for the treatment of chronic, intractable pain secondary to failed back surgery syndrome (FBSS) with intractable neuropathic leg pain (after prior surgery in the same spinal region) when ALL of the following criteria are met: there has been a failure of at least six (6) consecutive months of physician-supervised conservative medical management (e.g., pharmacotherapy, physical therapy, cognitive behavioral therapy, or activity lifestyle modification); surgical intervention is not indicated or the individual does not wish to proceed with spinal surgery; an attestation by a behavioral health provider (i.e., a face-to-face or virtual assessment with or without psychological questionnaires and/or psychological testing) reveals no evidence of an inadequately controlled mental and/or behavioral health conditions/issues (e.g., substance use disorders, depression, or psychosis) that would impact perception of pain, and/or negatively impact the success of a SCS or contraindicate placement of the device. If the initial short-term trial fails, a repeat trial is considered not medically necessary.

Permanent implantation of a spinal cord stimulator (i.e., non-high-frequency or high-frequency [HF10 SCS]) is considered medically necessary when BOTH of the following criteria are met: the individual must meet ALL criteria for the short-term trial spinal cord stimulation (SCS) as noted above; and there has been at least a 50% reduction in pain during a short-term trial of SCS.

A short-term trial (i.e., greater than 48 hours) of a non-high-frequency dorsal column spinal cord stimulator (SCS) is considered medically necessary for the treatment of chronic, intractable pain secondary to complex regional pain syndrome (CRPS)/reflex sympathetic dystrophy (RSD) only of the upper and lower extremities when ALL of the following criteria are met: limited to only the extremities and not to the head/face/neck, trunk, perineum/pelvis, or abdominal viscera; and diagnosis of CRPS/RSD as evidenced by continuing pain which is disproportionate to any inciting event, with the individual reporting at least ONE symptom in THREE of four diagnostic categories."""

CIGNA_SCS_NON_COVERED = """Spinal cord stimulation (high-frequency or non-high-frequency) placed without meeting the requirements listed in the Definitions, the General Guidelines, and the Indications sections is considered not medically necessary. Replacement of a functioning non-high-frequency dorsal column SCS with a high-frequency SCS is considered not medically necessary. A high-frequency spinal cord stimulator (SCS) is considered not medically necessary for ANY other indication, including complex regional pain syndrome (CRPS)/reflex sympathetic dystrophy (RSD). A high-frequency or non-high-frequency dorsal column SCS is considered not medically necessary for ANY other indication including, but not limited to, the following conditions: post-amputation pain (phantom limb pain); post-herpetic neuralgia; peripheral neuropathy (e.g., chronic intractable pain from diabetic sensory neuropathy); dysesthesias involving the lower extremities secondary to spinal cord injury; abdominal/pelvic visceral pain; chronic cervical or lumbar radiculopathy without prior spinal surgery; chronic cervical, thoracic, or lumbar axial pain without prior spinal surgery; failed cervical and/or thoracic spinal surgery with intractable neuropathic pain in arm(s) or trunk; abdominal pain related to celiac artery compression syndrome; and neuropathic pain associated with Multiple Sclerosis. Generator modes other than tonic-low and high-frequency (e.g., burst-stimulation) are considered not medically necessary. Replacement of a dorsal column spinal cord stimulator (SCS) with a dorsal root ganglion (DRG) stimulator is considered not medically necessary. Dorsal root ganglion (DRG) stimulation is considered not medically necessary for ALL indications except as noted above in Replacement."""

CIGNA_IMAGING_PA_COVERED = """These evidence-based, proprietary clinical guidelines evaluate a range of advanced imaging and procedures, including CT, MRI, PET, Gastrointestinal Endoscopy, as well as Cardiac, and musculoskeletal interventions. Cigna and eviCore reserve the right to change and update the guidelines; the guidelines undergo a formal review annually and are based on current evidence supported by major national and international association and society guidelines and criteria, peer-reviewed literature, major treatises, as well as practicing academic and community-based physicians. These guidelines are not intended to supersede or replace sound medical judgment, but instead should facilitate the identification of the most appropriate imaging or other designated procedure given the individual's clinical condition; physician judgment can override the guidelines in certain clinical circumstances. Medical Benefit Plan coverage and eligibility issues may take precedence over these clinical guidelines. State and federal legislation may need to be considered in the review of advanced imaging requests (e.g., various state and federal breast density laws, Texas HB 1290 Coronary Calcium CT Law).

Adequate clinical information that must be submitted to eviCore in order to establish medical necessity for advanced imaging or other designated procedures includes, but is not limited to: pertinent clinical evaluation that should include a recent detailed history, physical examination since the onset or change in symptoms, and/or laboratory and prior imaging studies. Condition-specific guideline sections may describe additional clinical information which is required for a pertinent clinical evaluation; the Spine and Musculoskeletal guidelines require x-ray studies from when the current episode of symptoms started or changed. Advanced imaging or other designated procedures should not be ordered prior to clinical evaluation of an individual by the physician treating the individual, which may include referral to a consultant specialist who will make further treatment decisions. Other meaningful technological contact (telehealth visit, telephone or video call, electronic mail or messaging) since the onset or change in symptoms by an established individual can serve as a pertinent clinical evaluation, though some conditions may require a face-to-face evaluation as discussed in the applicable condition-specific guideline sections. A recent clinical evaluation may be unnecessary if the individual is undergoing a guideline-supported, scheduled follow-up imaging or other designated procedural evaluation, with exceptions due to routine surveillance indications addressed in the applicable condition-specific guideline sections. The evidence-based approach to determine the most appropriate procedure for each individual requires submission of medical records pertinent to the requested imaging or other designated procedures. Individuals who are 18 years old or younger should be imaged according to the Pediatric Imaging Guidelines if discussed in the condition-specific guideline sections; any conditions not specifically discussed in the Pediatric Imaging Guidelines should be imaged according to the General Imaging Guidelines; individuals who are >18 years old should be imaged according to the General Imaging Guidelines, except where directed otherwise by a specific guideline section."""

CIGNA_CARDIAC_CATH_COVERED = """Diagnostic Left Heart Catheterization (LHC) is indicated for individuals in acute settings or with active unstable angina, and should be handled as medical emergencies. LHC may be indicated for new onset, accelerating, or worsening ischemic symptoms suggestive of acute coronary syndrome (ACS) occurring at rest, or with minimal exertion resolving with rest, including: cardiac chest pain (typical angina) with or without new onset, evolving ischemic EKG changes; or symptoms consistent with the known angina pattern in an individual with a history of CABG or PCI.

Diagnostic Left Heart Catheterization (LHC) is indicated in individuals with established Coronary Artery Disease (CAD) post revascularization by percutaneous coronary intervention (PCI) or coronary artery bypass graft surgery (CABG) when there is documentation of one of the following: new, recurrent, or worsening ischemic symptoms similar to prior ischemic episode; new, recurrent, or worsening likely anginal symptoms; new, recurrent, or worsening symptoms of chest pain, exertional dyspnea, or exertional fatigue AND intermediate or high-risk findings on non-invasive stress testing; new left ventricular systolic dysfunction (left ventricular ejection fraction <50%); worsening left ventricular systolic dysfunction (decline in left ventricular ejection fraction >=10%); new or worsened congestive heart failure; ventricular fibrillation; or sustained ventricular tachycardia.

For stable symptomatic suspected or established coronary artery disease, LHC with coronary arteriography is indicated when there is documentation of one of the following: new onset, persistent, or worsening of likely anginal symptoms with symptomatic failure of, or worsening during, a 12 week trial of optimal medical therapy (OMT) including anti-platelet therapy, statin and/or other lipid-lowering therapy, anti-anginal therapy, and anti-hypertensive therapy; new onset, persistent, or worsening of likely anginal symptoms with established CAD (or age >=50 years and/or >=2 CAD risk factors: diabetes mellitus, smoking, family history of premature CAD, hypertension, dyslipidemia) and likely anginal symptoms at a low level of exercise or at rest despite optimal medical therapy; LHC may be indicated irrespective of OMT for symptomatic individuals with high-risk findings on Coronary CT Angiography (left main coronary artery stenosis >=40%; proximal or mid left anterior descending coronary artery stenosis >=70%; proximal or mid double-vessel major epicardial stenosis >=60%; proximal or mid triple-vessel major epicardial stenosis >=50%; or CT-FFR measured <=0.8); or high-risk findings on non-invasive stress testing (cardiac chest pain induced by exercise treadmill testing or dobutamine stress testing; myocardial perfusion imaging with >=10% reversible ischemic burden; stress echo with at least 3 segments of inducible ischemia; exercise treadmill testing inducing at least 2.5 mm downsloping ST-depression or 3 mm horizontal ST-depression in two leads; or ventricular tachycardia of at least 3 consecutive beats induced by exercise treadmill test). LHC is medically necessary if coronary artery disease is the suspected etiology for new or worsened congestive heart failure, new or worsening left ventricular systolic dysfunction, or ventricular fibrillation/sustained ventricular tachycardia.

Planned (Staged) Coronary Interventions applies to individuals with clinically stable symptoms if there is documentation of a recent diagnostic catheterization finding of a significant lesion that was not intervened as part of the initial procedure and the documentation explicitly states that a subsequent procedure will be performed for planned/staged PCI of that lesion. The CPT codes for percutaneous coronary interventions (PCI) include contrast injection, angiography, road-mapping, and fluoroscopic guidance; vessel measurement; and angiography following coronary angioplasty, stent placement, and atherectomy -- separate codes for these services should not be assigned in addition to the PCI code(s) because the services are already included."""

CIGNA_CARDIAC_CATH_NON_COVERED = """Diagnostic left heart catheterization to screen for coronary artery disease (CAD) in asymptomatic individuals who are not anticipating other cardiac procedures is not considered medically necessary. A repeat diagnostic left heart catheterization is not medically necessary when the individual is undergoing a planned staged percutaneous coronary intervention: diagnostic coronary angiogram is required only once prior to the interventional procedure, and a repeat diagnostic coronary angiogram does not add to the findings of the initial diagnostic coronary angiogram and moreover carries cardiac and extra-cardiac risks including coronary artery injury and myocardial infarction, vascular access site bleeding, ischemic stroke, and contrast-mediated acute kidney injury."""

CIGNA_TKA_COVERED = """Total knee replacement is considered medically necessary for ANY of the following conditions when ALL of the associated criteria have been met:

Fracture of Distal Femur: imaging shows a fracture of the distal femur (trochlea, condyles); and conservative management or surgical fixation is not considered a reasonable option.

Osteoarthritis (OA) or Avascular Necrosis (AVN): imaging or arthroscopic findings show severe unicompartmental (medial, lateral, or patellofemoral), bicompartmental, or tricompartmental osteoarthritis as evidenced by Kellgren-Lawrence Grade III or IV radiographic findings, Outerbridge Classification Grade IV arthroscopic findings AND not a candidate for joint sparing procedure, or Modified Outerbridge Classification Grade IV MRI findings AND not a candidate for joint sparing procedure; or avascular necrosis (AVN) of the femoral condyles and/or proximal tibia. Symptoms include BOTH function-limiting pain at short distances (e.g., walking less than one-quarter mile, limiting activity to two city blocks, the equivalent to walking the length of a shopping mall) for at least three (3) months duration, and loss of knee function which interferes with the ability to carry out age-appropriate activities of daily living and/or demands of employment. Failure of provider-directed non-surgical management for at least three (3) months duration is required (criteria exception: the medical record must clearly document why provider-directed non-surgical management is not appropriate). It is incumbent on the surgeon to preoperatively optimize reasonably modifiable medical and behavioral health comorbidities."""

CIGNA_TKA_NON_COVERED = """Total knee replacement is considered not medically necessary for ANY other indication, condition, or when ANY of the following are present: joint instability (due to a lack of collateral ligament integrity) that is not amenable to surgical correction (e.g., specialized implant, constrained implant, or a hinge implant); >30 degrees of fixed varus deformity that is not amenable to surgical correction; >30 degrees of fixed valgus deformity that is not amenable to surgical correction; individuals undergoing dialysis; active local or systemic infection; or vascular insufficiency (defined as ankle brachial index of <0.5), significant muscular atrophy of the leg, or neuromuscular disease that is severe enough to compromise implant stability or post-operative recovery. Based on lack of scientific evidence of efficacy and safety, the following are considered experimental, investigational, or unproven: bicompartmental knee arthroplasty (modular or monolithic/nonmodular); and bi-unicompartmental knee arthroplasty."""

CIGNA_THA_COVERED = """Total hip replacement is considered medically necessary for ANY of the following conditions when ALL of the associated criteria have been met:

Femoral Head/Neck Fracture: imaging shows a fracture of the femoral head or femoral neck; and conservative management or surgical fixation is not considered a reasonable option.

Osteoarthritis, Avascular Necrosis (AVN), Inflammatory Arthritis: imaging shows Tonnis Grade 2-3 osteoarthritis, avascular necrosis with collapse of the femoral head, or inflammatory arthritis affecting BOTH the femoral head and the acetabulum with joint space narrowing. Symptoms include BOTH function-limiting pain at short distances (e.g., walking less than one-quarter mile, limiting activity to two city blocks, the equivalent to walking the length of a shopping mall) for at least three (3) months duration (criteria exception: three months of function-limiting pain is not required when the medical record clearly documents why provider-directed non-surgical management is inappropriate), and loss of hip function which interferes with the ability to carry out age-appropriate activities of daily living and/or demands of employment. Failure of provider-directed non-surgical management for at least three (3) months duration is required (criteria exception: three months of provider-directed non-surgical management is not required when the medical record clearly documents why provider-directed non-surgical management is inappropriate). It is incumbent on the surgeon to preoperatively optimize reasonably modifiable medical and behavioral health comorbidities."""

CIGNA_THA_NON_COVERED = """Total hip replacement is considered not medically necessary for ANY other indication, condition, or when ANY of the following are present: active local or systemic infection; vascular insufficiency, significant muscular atrophy of the leg, or neuromuscular disease severe enough to compromise implant stability or post-operative recovery; or individuals undergoing dialysis."""

POLICIES = [
    {
        "policyId": "CIGNA-BARIATRIC-2026",
        "policyName": "Bariatric Surgery and Procedures",
        "policyType": "Medical Coverage Policy",
        "payerName": "Cigna",
        "effectiveDate": "2026-07-15",
        "documentPath": "https://static.cigna.com/assets/chcp/pdf/coveragePolicies/medical/mm_0051_coveragepositioncriteria_bariatric_surgery.pdf",
        "criteria": [
            ("COVERED_INDICATIONS", CIGNA_BARIATRIC_COVERED, "Coverage Policy — Initial Bariatric Surgical Procedures (Adults)"),
            ("NON_COVERED_INDICATIONS", CIGNA_BARIATRIC_NON_COVERED, "Coverage Policy — Not Medically Necessary / Experimental, Investigational or Unproven"),
        ],
    },
    {
        "policyId": "CIGNA-LUMBAR-FUSION-2025",
        "policyName": "Lumbar Fusion (Arthrodesis) Guidelines",
        "policyType": "Coverage Guideline",
        "payerName": "Cigna",
        "effectiveDate": "2025-12-18",
        "documentPath": "https://www.evicore.com/sites/default/files/clinical-guidelines/2025-11/Cigna%20CMM-609%20Lumbar%20Fusion_Final_V2.0.2025_Eff12.18.2025_pub11.18.2025.pdf",
        "criteria": [
            ("COVERED_INDICATIONS", CIGNA_LUMBAR_FUSION_COVERED, "CMM-609.4: Lumbar Fusion (Arthrodesis) with Decompression (Indirect or Direct)"),
            ("NON_COVERED_INDICATIONS", CIGNA_LUMBAR_FUSION_NON_COVERED, "CMM-609.9: Non-Indications"),
        ],
    },
    {
        "policyId": "CIGNA-GLP1-WEIGHTLOSS-2026",
        "policyName": "Weight Loss – Glucagon-Like Peptide-1 Agonists Prior Authorization Policy",
        "policyType": "Prior Authorization Policy",
        "payerName": "Cigna",
        "effectiveDate": "2026-04-15",
        "documentPath": "https://static.cigna.com/assets/chcp/pdf/coveragePolicies/cnf/cnf_684_coveragepositioncriteria_weight_loss_glp1_agonists_pa.pdf",
        "criteria": [
            ("COVERED_INDICATIONS", CIGNA_GLP1_WEIGHTLOSS_COVERED, "III/V: Wegovy injection and Zepbound — Weight Loss, MACE Risk Reduction, and OSA Criteria"),
        ],
    },
    {
        "policyId": "CIGNA-SCS-2025",
        "policyName": "Spinal Cord and Dorsal Root Ganglion Stimulation",
        "policyType": "Coverage Guideline",
        "payerName": "Cigna",
        "effectiveDate": "2025-07-01",
        "documentPath": "https://www.evicore.com/sites/default/files/clinical-guidelines/2025-03/Cigna_Spinal%20Cord%20and%20Dorsal%20Root%20Ganglion%20Stimulation%20(CMM-211)_FINAL_V1.0.2025_pub03.19.2025.pdf",
        "criteria": [
            ("COVERED_INDICATIONS", CIGNA_SCS_COVERED, "CMM-211: Indications — Failed Back Surgery Syndrome and CRPS/RSD"),
            ("NON_COVERED_INDICATIONS", CIGNA_SCS_NON_COVERED, "CMM-211: Non-Indications — Not Medically Necessary"),
        ],
    },
    {
        "policyId": "CIGNA-IMAGING-PA-2025",
        "policyName": "Preface to the Imaging Guidelines",
        "policyType": "Coverage Guideline",
        "payerName": "Cigna",
        "effectiveDate": "2025-05-15",
        "documentPath": "https://www.evicore.com/sites/default/files/clinical-guidelines/2025-03/Cigna_Preface%20to%20the%20Imaging%20Guidelines_V2.0.2025_Eff05.15.2025_pub03.28.2025.pdf",
        "criteria": [
            ("COVERED_INDICATIONS", CIGNA_IMAGING_PA_COVERED, "Preface-1.1 Guideline Development / Preface-2.1 Benefits and Coverage Policies / Preface-3.1 Clinical Documentation and Age Considerations"),
        ],
    },
    {
        "policyId": "CIGNA-CGM-2026",
        "policyName": "Diabetes – Continuous Glucose Monitoring Systems Prior Authorization Policy",
        "policyType": "Prior Authorization Policy",
        "payerName": "Cigna",
        "effectiveDate": "2026-01-21",
        "documentPath": "https://static.cigna.com/assets/chcp/pdf/coveragePolicies/cnf/cnf_676_coveragepositioncriteria_diabetes_continuous_glucose_monitoring_systems_pa.pdf",
        "criteria": [
            ("COVERED_INDICATIONS", CIGNA_CGM_COVERED, "Coverage Criteria — FDA-Approved Indications"),
            ("NON_COVERED_INDICATIONS", CIGNA_CGM_NON_COVERED, "Conditions Not Covered"),
        ],
    },
    {
        "policyId": "CIGNA-CARDIAC-CATH-2025",
        "policyName": "Cardiac Imaging Guidelines — Diagnostic Heart Catheterization and Percutaneous Coronary Intervention",
        "policyType": "Coverage Guideline",
        "payerName": "Cigna",
        "effectiveDate": "2025-10-01",
        "documentPath": "https://www.evicore.com/sites/default/files/clinical-guidelines/2025-09/Cigna_Cardiac%20Imaging%20Guidelines_V2.0.2025_Eff10.01.2025_pub09.17.2025.pdf",
        "criteria": [
            ("COVERED_INDICATIONS", CIGNA_CARDIAC_CATH_COVERED, "CD-7.3.1/7.3.2/7.3.3 Diagnostic Left Heart Catheterization; CD-7.6 Planned (Staged) Coronary Interventions"),
            ("NON_COVERED_INDICATIONS", CIGNA_CARDIAC_CATH_NON_COVERED, "CD-7.3.3 / CD-7.6 — Not Medically Necessary"),
        ],
    },
    {
        "policyId": "CIGNA-TKA-2026",
        "policyName": "CMM-311: Knee Replacement/Arthroplasty — Total Knee Replacement",
        "policyType": "Coverage Guideline",
        "payerName": "Cigna",
        "effectiveDate": "2026-03-07",
        "documentPath": "https://www.evicore.com/sites/default/files/clinical-guidelines/2025-11/Cigna_CMM-311%20Knee%20Replacement%20Arthroplasty_V2.0.2025_Eff03.07.2026_Pub11.21.2025.pdf",
        "criteria": [
            ("COVERED_INDICATIONS", CIGNA_TKA_COVERED, "Total Knee Replacement Indications (CMM.JT.IN.311)"),
            ("NON_COVERED_INDICATIONS", CIGNA_TKA_NON_COVERED, "Total Knee Replacement Non-Indications (CMM.JT.NI.311)"),
        ],
    },
    {
        "policyId": "CIGNA-THA-2026",
        "policyName": "CMM-313: Hip Replacement/Arthroplasty — Total Hip Replacement",
        "policyType": "Coverage Guideline",
        "payerName": "Cigna",
        "effectiveDate": "2026-03-07",
        "documentPath": "https://www.evicore.com/sites/default/files/clinical-guidelines/2025-11/Cigna_CMM-313%20Hip%20Replacement%20Arthro_V2.0.2025_Eff03.07.2026_Pub11.21.2025.pdf",
        "criteria": [
            ("COVERED_INDICATIONS", CIGNA_THA_COVERED, "Total Hip Replacement Indications (CMM.JT.IN.313)"),
            ("NON_COVERED_INDICATIONS", CIGNA_THA_NON_COVERED, "Total Hip Replacement Non-Indications (CMM.JT.NI.313)"),
        ],
    },
]
