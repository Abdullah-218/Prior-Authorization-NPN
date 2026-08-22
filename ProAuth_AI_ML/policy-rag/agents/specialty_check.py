"""
Provider Specialty Check — deterministic fast path
======================================================

Ported from the old rule engine's R501 ("Provider-Procedure Compatibility",
ProAuth_AI_BackEnd/src/rules/evaluators/providerCompatibilityEvaluator.js) —
same SPECIALTY_MAP, same keyword-matching logic. Keep the two in sync by
hand; there's no shared-code path across the Node/Python boundary.

This is the FAST, FREE, GROUNDED path only — a real keyword match against
a hand-curated map, no LLM call spent re-deriving something already known.
It does NOT feed the ML model directly (the trained model's 10 fixed
features never included a standalone specialty_match input — confirmed
via the pickle's own feature_names_in_). Instead, when this module
returns a confident status ("compatible" | "unusual" | "general_practice"),
clinical_evidence_agent.py folds it into the clinicalCriteria checklist as
"specialty_match", where it contributes to clinicalEvidenceScore like any
other criterion — which DOES feed the ML feature vector (per explicit
instruction, 2026-08-19: "the coverage reasoning agent should also see
... speciality match to contribute to the ML input"). When this module
returns None ("unknown_specialty" — the map doesn't cover this specialty
at all), clinical_evidence_agent.py defers to an LLM judgment instead of
silently dropping the signal — see that module's evaluate_clinical_criteria().

Usage:
    from agents.specialty_check import check_provider_specialty
    note = check_provider_specialty("Orthopedics", "lumbar spine MRI")
"""

# Configurable specialty -> compatible treatment keywords. Mirror
# providerCompatibilityEvaluator.js's SPECIALTY_MAP exactly.
SPECIALTY_MAP = {
    "orthopedics": ["mri", "x-ray", "arthroscopy", "physical therapy", "spine", "joint", "fracture", "bone", "knee", "lumbar", "surgery"],
    "cardiology": ["ecg", "echo", "cardiac", "heart", "angiogram", "stent", "pacemaker", "catheterization", "holter"],
    "endocrinology": ["insulin", "metformin", "ozempic", "semaglutide", "liraglutide", "diabetes", "thyroid", "glucose", "hba1c"],
    "rheumatology": ["methotrexate", "biologic", "adalimumab", "etanercept", "infliximab", "dmard", "arthritis", "lupus"],
    "oncology": ["chemotherapy", "immunotherapy", "radiation", "tumor", "cancer", "biopsy"],
    "neurology": ["mri brain", "ct head", "eeg", "seizure", "migraine", "neuropathy", "ms", "parkinson"],
    "dermatology": ["dupilumab", "biologics", "psoriasis", "eczema", "skin", "topical"],
    "pulmonology": [
        "inhaler", "spirometry", "ct chest", "asthma", "copd", "bronchoscopy",
        "cpap", "bipap", "sleep apnea", "sleep study", "polysomnography", "positive airway pressure",
        # Lung cancer screening (NCD-210.14 LDCT) — found live (2026-08-21):
        # a real Pulmonology-ordered "Low dose CT lung cancer screening"
        # request hard-FAILed specialty_match (no keyword overlap at all)
        # instead of getting the LLM's more generous clinical judgment,
        # because a KNOWN-but-incompletely-covered specialty skips the LLM
        # entirely (see _resolve_specialty_match) — worse than being
        # unrecognized. Pulmonology is a standard, common ordering
        # specialty for LDCT screening.
        "lung cancer screening", "low dose ct", "ldct", "lung nodule", "pulmonary nodule", "lung cancer",
    ],
    "gastroenterology": ["colonoscopy", "endoscopy", "ibd", "crohn", "colitis", "hepatitis"],
    "nephrology": ["dialysis", "renal", "kidney", "creatinine"],
    "psychiatry": ["antidepressant", "antipsychotic", "ssri", "snri", "lithium", "therapy"],
    "general practice": [],
    "internal medicine": [],
}


def _compatible_keywords(specialty):
    lower = (specialty or "").lower()
    for key, keywords in SPECIALTY_MAP.items():
        if key in lower:
            return keywords
    return None  # unknown specialty — don't penalize


def check_provider_specialty(provider_specialty, requested_service):
    """
    Returns a small dict describing specialty/service compatibility, or
    None when there's nothing meaningful to say (no specialty given, or
    the specialty isn't in the reference map — same "don't penalize the
    unknown" stance as R501). status is one of:
      "compatible" | "unusual" | "unknown_specialty" | "general_practice"
    Never raises, never touches policy/clinical/ML state.
    """
    if not provider_specialty or not requested_service:
        return None

    keywords = _compatible_keywords(provider_specialty)
    if keywords is None:
        return {"status": "unknown_specialty", "providerSpecialty": provider_specialty, "requestedService": requested_service}

    if len(keywords) == 0:
        return {"status": "general_practice", "providerSpecialty": provider_specialty, "requestedService": requested_service}

    service_lower = requested_service.lower()
    matched = [kw for kw in keywords if kw in service_lower]

    if matched:
        return {
            "status": "compatible",
            "providerSpecialty": provider_specialty,
            "requestedService": requested_service,
            "matchedKeywords": matched,
        }

    return {
        "status": "unusual",
        "providerSpecialty": provider_specialty,
        "requestedService": requested_service,
    }
