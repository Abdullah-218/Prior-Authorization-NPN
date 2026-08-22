"""
Document Agent
================

Real implementation (2026-08-19+). Verifies documents the doctor actually
attached to this request against a required set.

CHANGED (2026-08-19+, per explicit instruction — matching policy-named
documents to the app's fixed upload categories was causing too many false
"missing"/stuck-in-review results in practice): ONLY the baseline set —
Clinical notes, Prescription — is REQUIRED now, for every request
regardless of what Policy Agent additionally names. Whatever the policy
names beyond that (e.g. "Sleep study report" for a CPAP request, "BMI
measurement record" for a bariatric request) is still evaluated and
reported back — submitted, missing, or with no matching upload category
at all — but purely as OPTIONAL/informational context for a reviewer.
It no longer counts toward nRequiredDocuments, documentationScore, or the
missingRequiredEvidence gate. This sidesteps the category-matching
fragility problem entirely for the one thing it was actually breaking:
a real, complete request stuck unable to ever satisfy a policy-named
requirement the app has no upload field for at all.

(Superseded design note, kept for history: an earlier version tried to
keep policy-specific documents required but excuse only the ones with no
matching category via an `unmatchedDocuments` bucket — see git history
around 2026-08-19. That still left every MATCHED-but-differently-phrased
policy document blocking real submissions whenever the category
detection guessed wrong, which kept recurring. Requiring only the fixed
baseline removes that whole class of failure.)

PRESENCE-ONLY (2026-08-19 instruction, unchanged): a required document
counts as submitted once a real file is on record for its matched
category — content is NOT required to be OCR-readable, and an empty file
still counts. OCR (document_ocr.py) still runs opportunistically and is
reported via unreadableFiles (informational — the Companion Agent can
still mention a file looked blank/corrupt), but it no longer flips a
document from submitted to missing.

Matching a free-text document name (baseline, or LLM-named from policy
text for the optional set) to an actual uploaded file requires knowing
which of the app's fixed upload categories it belongs to — see
CATEGORY_KEYWORDS. Separators are normalized before matching since
Policy Agent doesn't always return clean human-readable phrasing (e.g.
"sleep_study_report" instead of "Sleep study report").

Usage:
    from agents.document_agent import evaluate_document_evidence
    result = evaluate_document_evidence(
        required_documents=["Clinical notes", "Prescription", "Sleep study report"],
        attached_documents=[{"documentType": "PRESCRIPTION", "storageUrl": "/path/to/file.pdf"}],
    )
"""
import re

from .document_ocr import extract_text, is_readable

BASELINE_REQUIRED_DOCUMENTS = ["Clinical notes", "Prescription"]

# The fixed upload categories NewApplication.jsx's Step 7 actually offers
# a file input for -> keyword patterns used to recognize a required
# document's free-text name as belonging to that category. Keywords are
# deliberately narrow (substring match against the lowercased name) —
# a false-positive match would let an unrelated upload silently satisfy a
# real policy requirement.
CATEGORY_KEYWORDS = {
    "CLINICAL_NOTES": [
        "clinical note", "physician note", "office visit note", "progress note",
        "comorbidity", "co morbidity", "medical confirmation", "diagnosis confirmation",
        "physician certification", "certification of",
    ],
    "PRESCRIPTION": ["prescription", "medication order"],
    "LAB_REPORTS": [
        "lab report", "laboratory", "lab result", "lab work", "blood test",
        "bmi", "body mass index", "biopsy", "pathology",
    ],
    "IMAGING_REPORT": [
        "imaging", "mri", "ct scan", "x-ray", "xray", "ultrasound", "radiograph", "scan report",
        "sleep study", "polysomnography", "hsat", "psg",
    ],
    "PREVIOUS_TREATMENT_RECORDS": [
        "previous treatment", "prior treatment", "treatment record",
        "physician-supervised", "program record", "prior therapy", "step therapy",
        "weight loss", "weight management", "conservative treatment",
    ],
}


def _match_category(document_name):
    """
    Maps a document's free text to the one upload category it actually
    belongs to, or None if it matches none. Returns None rather than
    guessing the closest category — a wrong guess would let an unrelated
    file silently satisfy a requirement the app never gave the doctor a
    way to actually submit.

    Separators are normalized to spaces before matching — Policy Agent's
    system prompt asks for "short human-readable names" but doesn't
    always get snake_case-free output from the LLM (e.g.
    "sleep_study_report" instead of "Sleep study report"), and a plain
    substring check against a keyword like "sleep study" silently misses
    that even though it's obviously the same document.
    """
    name = re.sub(r"[_-]+", " ", document_name.strip().lower())
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in name for keyword in keywords):
            return category
    return None


def _evaluate_against_uploads(doc_names, by_category):
    """
    Shared matching logic for both the required (baseline) and optional
    (policy-specific) document sets — same category-matching/presence-only
    rules either way, just used for different purposes by the caller.
    Returns (submitted, missing, unmatched, unreadable_files).
    """
    submitted, missing, unmatched, unreadable_files = [], [], [], []
    for doc_name in doc_names:
        category = _match_category(doc_name)
        if category is None:
            unmatched.append(doc_name)
            continue

        files_for_category = by_category.get(category, [])
        if not files_for_category:
            missing.append(doc_name)
            continue

        # Presence-only (see module docstring) — a file on record for
        # this category satisfies the requirement regardless of content.
        submitted.append(doc_name)
        for f in files_for_category:
            path = f.get("storageUrl") or f.get("filePath")
            text = extract_text(path, f.get("mimeType"))
            if not is_readable(text):
                unreadable_files.append(path)
    return submitted, missing, unmatched, unreadable_files


def evaluate_document_evidence(required_documents, attached_documents=None):
    """
    required_documents: Policy Agent's named documents beyond the baseline
    (baseline is always evaluated too, regardless of what's passed here).
    These are now OPTIONAL — see module docstring — evaluated and reported
    under `optionalDocuments`, never affecting documentationScore or the
    missingRequiredEvidence gate.

    attached_documents: the files actually uploaded for this request —
    list of {"documentType": <category>, "storageUrl" or "filePath": str,
    "mimeType": str, ...}, as persisted by the Node backend's
    /api/documents endpoint. None/empty is a legitimate state (a request
    submitted with nothing attached), not an error.

    Returns: documentationScore/nRequiredDocuments/nDocumentsSubmitted/
    missingDocuments/relevantDocuments (baseline only — Clinical notes,
    Prescription), unmatchedDocuments (always [] now — the baseline
    always resolves to a real category, kept in the schema for backward
    compatibility with callers), optionalDocuments (the policy-named
    set's own submitted/missing/unmatched breakdown, informational only),
    unreadableFiles (informational, for the Companion Agent to mention),
    and isDummy: False.
    """
    policy_documents = [
        doc for doc in (required_documents or [])
        if doc.strip().lower() not in {b.lower() for b in BASELINE_REQUIRED_DOCUMENTS}
    ]
    attached_documents = attached_documents or []

    by_category = {}
    for doc in attached_documents:
        category = doc.get("documentType")
        if category:
            by_category.setdefault(category, []).append(doc)

    submitted, missing, unmatched, unreadable_files = _evaluate_against_uploads(
        BASELINE_REQUIRED_DOCUMENTS, by_category
    )
    opt_submitted, opt_missing, opt_unmatched, opt_unreadable = _evaluate_against_uploads(
        policy_documents, by_category
    )
    unreadable_files = unreadable_files + opt_unreadable

    n_required = len(BASELINE_REQUIRED_DOCUMENTS)
    n_submitted = len(submitted)
    documentation_score = round(100.0 * n_submitted / n_required, 1) if n_required else 100.0

    return {
        "documentationScore": documentation_score,
        "nRequiredDocuments": n_required,
        "nDocumentsSubmitted": n_submitted,
        "missingDocuments": missing,
        "relevantDocuments": submitted,
        "unmatchedDocuments": unmatched,
        "optionalDocuments": {
            "requested": policy_documents,
            "submitted": opt_submitted,
            "missing": opt_missing,
            "unmatched": opt_unmatched,
        },
        "unreadableFiles": unreadable_files,
        "isDummy": False,
    }
