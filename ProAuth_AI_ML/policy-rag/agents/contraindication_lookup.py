"""
Contraindication Lookup — deterministic fast path for known-dangerous
drug + patient-state pairings
=============================================================================

Small, hand-curated table of well-established, unambiguous contraindications
(teratogens in pregnancy, absolute renal/hepatic contraindications, etc.) —
NOT a general drug-interaction database (that would need a licensed source
like First Databank/Micromedex, out of scope here). A match in this table is
grounded, high-confidence evidence of real danger, so it's trusted outright.
Finding NO match here means "this table doesn't know," never "this
combination is safe" — that distinction is exactly why
clinical_evidence_agent.py's evaluate_clinical_criteria() still defers a
request with a notable but unmatched risk fact to an LLM judgment call
rather than silently treating it as cleared (see has_notable_risk_facts()
below).

Same "deterministic match needs no LLM" precedent as drug_reference_lookup.py's
STRONG indication match and specialty_check.py's keyword map.

Usage:
    from agents.contraindication_lookup import check_known_contraindications, has_notable_risk_facts
    matches = check_known_contraindications("methotrexate", {"pregnancy_status": "pregnant"})
"""
import re

# Each entry: drugKeywords matched against the requested service/drug name;
# factKeywords matched against the STRINGIFIED VALUES of extractedFacts (not
# the keys — Clinical Agent's fact keys are free-form, not a fixed
# vocabulary, see that module's docstring). A rule fires when both a drug
# keyword AND a fact keyword match. Deliberately narrow and well-established
# — expand carefully, a false entry here hard-gates real requests to PEND.
KNOWN_CONTRAINDICATIONS = [
    {
        "drugKeywords": ["methotrexate"],
        "factKeywords": ["pregnan"],
        "severity": "CRITICAL",
        "reason": "Methotrexate is a well-established teratogen — contraindicated in pregnancy.",
    },
    {
        "drugKeywords": ["warfarin", "coumadin"],
        "factKeywords": ["pregnan"],
        "severity": "CRITICAL",
        "reason": "Warfarin is a known teratogen (fetal warfarin syndrome) — contraindicated in pregnancy.",
    },
    {
        "drugKeywords": ["isotretinoin", "accutane"],
        "factKeywords": ["pregnan"],
        "severity": "CRITICAL",
        "reason": "Isotretinoin is a well-established teratogen — absolutely contraindicated in pregnancy.",
    },
    {
        "drugKeywords": ["lisinopril", "enalapril", "ramipril", "losartan", "valsartan"],
        "factKeywords": ["pregnan"],
        "severity": "CRITICAL",
        "reason": "ACE inhibitors/ARBs are contraindicated in pregnancy (fetal renal toxicity, especially 2nd/3rd trimester).",
    },
    {
        "drugKeywords": ["metformin"],
        "factKeywords": ["severe renal", "renal failure", "esrd", "end-stage renal", "dialysis"],
        "severity": "HIGH",
        "reason": "Metformin is contraindicated in severe renal impairment/end-stage renal disease due to lactic acidosis risk.",
    },
    {
        "drugKeywords": ["ibuprofen", "naproxen", "diclofenac", "celecoxib", "nsaid"],
        "factKeywords": ["severe renal", "renal failure", "esrd", "dialysis"],
        "severity": "HIGH",
        "reason": "NSAIDs are contraindicated in severe renal impairment — risk of further renal deterioration.",
    },
    {
        "drugKeywords": ["codeine", "tramadol"],
        "factKeywords": ["breastfeed", "breast-feed", "nursing infant", "lactat"],
        "severity": "HIGH",
        "reason": "Codeine/tramadol carry a boxed warning against use during breastfeeding due to infant respiratory depression risk.",
    },
    {
        "drugKeywords": ["codeine", "tramadol"],
        "factKeywords": ["pediatric", "infant", "child", "children", "neonate", "newborn"],
        "severity": "CRITICAL",
        "reason": "Codeine/tramadol carry an FDA boxed warning against use in children due to life-threatening respiratory depression risk.",
    },
    {
        "drugKeywords": ["atorvastatin", "simvastatin", "rosuvastatin", "lovastatin", "pravastatin", "statin"],
        "factKeywords": ["pregnan"],
        "severity": "CRITICAL",
        "reason": "Statins are contraindicated in pregnancy — cholesterol synthesis is essential for fetal development.",
    },
    {
        "drugKeywords": ["atorvastatin", "simvastatin", "rosuvastatin", "lovastatin", "pravastatin", "statin"],
        "factKeywords": ["active liver disease", "hepatic impairment", "liver failure", "cirrhosis"],
        "severity": "HIGH",
        "reason": "Statins are contraindicated in active liver disease/hepatic impairment due to hepatotoxicity risk.",
    },
    {
        "drugKeywords": ["valproate", "valproic acid", "divalproex"],
        "factKeywords": ["pregnan"],
        "severity": "CRITICAL",
        "reason": "Valproate is a well-established teratogen (neural tube defects) — contraindicated in pregnancy.",
    },
    {
        "drugKeywords": ["lithium"],
        "factKeywords": ["pregnan"],
        "severity": "HIGH",
        "reason": "Lithium is associated with fetal cardiac malformations (Ebstein's anomaly) — use in pregnancy requires specialist risk-benefit review.",
    },
    {
        "drugKeywords": ["tetracycline", "doxycycline", "minocycline"],
        "factKeywords": ["pregnan", "pediatric", "infant", "child", "children"],
        "severity": "HIGH",
        "reason": "Tetracyclines cause permanent tooth discoloration and bone growth effects in the fetus and in children under 8 — contraindicated in pregnancy and young children.",
    },
    {
        "drugKeywords": ["thalidomide"],
        "factKeywords": ["pregnan"],
        "severity": "CRITICAL",
        "reason": "Thalidomide is a classic, severe teratogen — absolutely contraindicated in pregnancy.",
    },
    {
        "drugKeywords": ["gadolinium"],
        "factKeywords": ["severe renal", "renal failure", "esrd", "end-stage renal", "dialysis"],
        "severity": "CRITICAL",
        "reason": "Gadolinium-based contrast is contraindicated in severe renal impairment/ESRD — risk of nephrogenic systemic fibrosis.",
    },
    {
        "drugKeywords": ["acetaminophen", "paracetamol", "tylenol"],
        "factKeywords": ["severe hepatic", "liver failure", "hepatic failure", "cirrhosis", "hepatic impairment"],
        "severity": "HIGH",
        "reason": "Acetaminophen requires strict dose limits or avoidance in severe hepatic impairment/liver failure due to hepatotoxicity risk.",
    },
    {
        "drugKeywords": ["aspirin"],
        "factKeywords": ["pediatric", "infant", "child", "children"],
        "severity": "CRITICAL",
        "reason": "Aspirin in children/adolescents with a viral illness is linked to Reye's syndrome — contraindicated in pediatric patients.",
    },
    {
        "drugKeywords": ["ciprofloxacin", "levofloxacin", "moxifloxacin", "fluoroquinolone"],
        "factKeywords": ["pediatric", "infant", "child", "children"],
        "severity": "HIGH",
        "reason": "Fluoroquinolones carry an established risk of tendon/cartilage injury in pediatric patients — generally avoided.",
    },
]

# Fact-value keywords that mark a patient-state detail as SAFETY-notable
# even when it doesn't hit a specific KNOWN_CONTRAINDICATIONS row — this is
# what triggers the LLM-deferred fallback so an uncovered drug+state
# combination isn't silently waved through just because our hard-coded
# table hasn't heard of it.
NOTABLE_RISK_KEYWORDS = [
    "pregnan", "breastfeed", "breast-feed", "nursing", "lactat",
    "renal", "kidney", "esrd", "dialysis",
    "hepatic", "liver", "cirrhosis",
    "pediatric", "infant", "child", "neonate", "newborn",
    "elderly", "geriatric",
]


def _normalize(text):
    return (text or "").strip().lower()


def _fact_values(extracted_facts):
    return [_normalize(str(v)) for v in (extracted_facts or {}).values() if v is not None]


def _looks_like_age_field(key):
    # Whole-token match on "age" after splitting on separators — a plain
    # substring check would false-positive on unrelated keys like
    # "dosage_mg" (contains "age").
    return "age" in re.split(r"[_\s-]+", key.lower())


def _age_derived_keywords(extracted_facts):
    """
    Age is almost always extracted by Clinical Agent as a NUMBER under a
    key like "age_years"/"patient_age" (per that module's own "numeric
    facts should be extracted as numbers" rule) — never as the literal
    word "pediatric" or "elderly". Scanning only fact VALUES as text would
    silently miss every age-based contraindication this way (confirmed
    live: "6-year-old" extracts as {"age_years": 6}, not a string
    containing "pediatric"). This derives the same signal from any
    numeric age-like field instead, so age-keyed rules (aspirin+pediatric,
    fluoroquinolones+pediatric, etc.) actually fire.
    """
    keywords = []
    for key, value in (extracted_facts or {}).items():
        if not _looks_like_age_field(key):
            continue
        try:
            age = float(value)
        except (TypeError, ValueError):
            continue
        if age < 18:
            keywords.append("pediatric")
        elif age >= 65:
            keywords.append("elderly")
    return keywords


NEGATIVE_VALUE_TOKENS = {"no", "false", "none", "negative", "denied", "denies", "not", "n/a", "na", "absent"}


def _is_affirmative(value):
    """
    True when a fact's value actually CONFIRMS whatever its key names,
    rather than denying it or being empty/unset. Booleans and numbers are
    straightforward (False/0 are denials, anything else affirms); a
    string value gets a crude whole-word negation scan so
    {"pregnant": "no"} or {"pregnancy_status": "not pregnant"} are
    correctly treated as denials, not confirmations — otherwise
    _key_derived_keywords below would read the KEY "pregnant" as an
    affirmative signal regardless of what the value actually said.
    """
    if isinstance(value, bool):
        return value is True
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if not normalized:
            return False
        tokens = re.split(r"[\s_-]+", normalized)
        return not any(t in NEGATIVE_VALUE_TOKENS for t in tokens)
    return bool(value)


def _key_derived_keywords(extracted_facts):
    """
    Some facts are extracted as boolean flags — e.g. {"pregnant": true},
    {"breastfeeding": true} — where the KEY carries the entire semantic
    meaning and the value is just a presence flag. A pure value scan (see
    _fact_values) sees only "true"/"false" and misses the signal
    completely (confirmed live, 2026-08-19: Clinical Agent extracted
    {"pregnant": true} for "12 weeks pregnant" text, and the
    contraindication table never fired — same root cause as
    _age_derived_keywords' numeric-age gap, just for booleans instead of
    numbers). Only derives a token when the paired value is actually
    affirmative (see _is_affirmative) — a denied fact must never read as
    a risk signal.
    """
    return [_normalize(key) for key, value in (extracted_facts or {}).items() if _is_affirmative(value)]


def _risk_tokens(extracted_facts):
    # Free-text fact values (catches "pregnant", "severe renal impairment",
    # etc. stated in words) PLUS age-derived synthetic tokens (numeric age
    # fields) PLUS key-derived tokens (boolean-flag facts like
    # {"pregnant": true}) — all matched the same way downstream (substring
    # containment), so no special-casing needed at the call sites below.
    return (
        _fact_values(extracted_facts)
        + _age_derived_keywords(extracted_facts)
        + _key_derived_keywords(extracted_facts)
    )


# Bounded negation check — NOT general negation-scope NLP, just the
# common clinical-documentation pattern of a denial word shortly before
# the term it negates ("not pregnant", "denies pregnancy", "no history of
# renal failure"). A plain substring check has no notion of this: "not
# pregnant" contains "pregnan" as a substring just like "pregnant" does.
# Only applied to free-text VALUES — _key_derived_keywords already has
# its own affirmative/negative handling for boolean-flag facts, since a
# key like "pregnant" has no surrounding words to scan at all.
_NEGATION_PREFIX = re.compile(r"\b(no|not|denies|denied|without|negative for)\b")


def _affirmed_match(token, keyword):
    """
    True if `keyword` appears in `token` and isn't immediately preceded
    (within a short window) by a negation word.
    """
    idx = token.find(keyword)
    if idx == -1:
        return False
    window = token[max(0, idx - 20):idx]
    return not _NEGATION_PREFIX.search(window)


def check_known_contraindications(requested_service, extracted_facts):
    """
    Returns a list of matched contraindication dicts (never None — empty
    list means no match). Each match: {drugMatched, factMatched, severity,
    reason}. A rule only fires when its drug keyword matches the requested
    service/drug name AND at least one risk token (an extracted-fact value,
    or an age-derived "pediatric"/"elderly" token — see _risk_tokens)
    contains one of its fact keywords.
    """
    service_norm = _normalize(requested_service)
    risk_tokens = _risk_tokens(extracted_facts)
    if not service_norm or not risk_tokens:
        return []

    matches = []
    for rule in KNOWN_CONTRAINDICATIONS:
        drug_matched = next((kw for kw in rule["drugKeywords"] if kw in service_norm), None)
        if not drug_matched:
            continue
        fact_matched = next(
            (kw for token in risk_tokens for kw in rule["factKeywords"] if _affirmed_match(token, kw)),
            None,
        )
        if fact_matched:
            matches.append({
                "drugMatched": drug_matched,
                "factMatched": fact_matched,
                "severity": rule["severity"],
                "reason": rule["reason"],
            })
    return matches


def has_notable_risk_facts(extracted_facts):
    """
    True when at least one risk token (an extracted-fact value, or an
    age-derived "pediatric"/"elderly" token — see _risk_tokens) mentions a
    safety-notable patient state (pregnancy, renal/hepatic impairment,
    pediatric/elderly age, breastfeeding) — independent of whether it
    matched a specific KNOWN_CONTRAINDICATIONS row. Used to decide whether
    an unmatched request is still worth an LLM's clinical judgment rather
    than silently treated as cleared.
    """
    risk_tokens = _risk_tokens(extracted_facts)
    return any(_affirmed_match(token, kw) for token in risk_tokens for kw in NOTABLE_RISK_KEYWORDS)
