"""
Document OCR
==============

Local text extraction for uploaded documents — Tesseract via pytesseract,
never a cloud vision API (explicit decision, 2026-08-19: keep document
content off any third-party network call; the tesseract binary is already
installed on this machine). PDFs are rasterized page-by-page with
pdf2image (shells out to the locally-installed poppler `pdftoppm`) before
OCR, since Tesseract itself only reads images.

This module never raises — a corrupt file, an unsupported format, or a
blank scan is a normal real-world outcome for uploaded documents, not an
exceptional one. Callers (document_agent.py) treat empty/short output as
"content could not be confirmed", the same conservative-default
convention used everywhere else in this pipeline (see
coverage_reasoning_agent.py).
"""
import os

import pytesseract
from pdf2image import convert_from_path
from PIL import Image

# Below this length, OCR output is treated as noise/blank rather than
# real document content — a failed scan or a mostly-blank page still
# produces a handful of stray characters, not zero.
MIN_READABLE_CHARS = 20

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def extract_text(file_path, mime_type=None):
    """
    Returns extracted text (str), or "" if the file is missing, corrupt,
    or an unsupported format (e.g. .doc/.docx — no OCR path for those
    here). Never raises.
    """
    if not file_path or not os.path.exists(file_path):
        return ""

    ext = os.path.splitext(file_path)[1].lower()
    try:
        if ext == ".pdf":
            pages = convert_from_path(file_path, dpi=200)
            return "\n".join(pytesseract.image_to_string(page) for page in pages).strip()
        if ext in _IMAGE_EXTENSIONS:
            return pytesseract.image_to_string(Image.open(file_path)).strip()
        return ""
    except Exception:
        return ""


def is_readable(text):
    return bool(text) and len(text.strip()) >= MIN_READABLE_CHARS
