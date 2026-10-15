"""
src/extractors.py — Text extraction from various file formats.

Supports: plain text, CSV, PDF (via PyMuPDF), DOCX (via python-docx).
Optional OCR via pytesseract (must be installed separately).
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Tuple

# ---------------------------------------------------------------------------
# Availability flags
# ---------------------------------------------------------------------------
try:
    import fitz  # PyMuPDF
    _FITZ_OK = True
except ImportError:
    _FITZ_OK = False

try:
    import docx  # python-docx
    _DOCX_OK = True
except ImportError:
    _DOCX_OK = False

try:
    import pytesseract
    from PIL import Image as PILImage
    _TESSERACT_OK = True
except ImportError:
    _TESSERACT_OK = False


def tesseract_status() -> str:
    if _TESSERACT_OK:
        try:
            pytesseract.get_tesseract_version()
            return "available"
        except Exception:
            return "not_found"
    return "not_installed"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def extract_text(
    path: Path,
    max_file_size_mb: float = 50.0,
    ocr_enabled: bool = False,
) -> Tuple[str, str]:
    """
    Extract textual content from *path*.

    Returns
    -------
    (text, note) where *text* is the extracted string (possibly empty) and
    *note* is a human-readable explanation (empty string on full success).

    The caller receives an empty *text* if:
    - The file exceeds *max_file_size_mb* (note contains "too large / limit").
    - The format is not supported.
    - Extraction raises an error.
    """
    try:
        size_mb = path.stat().st_size / 1_048_576
    except OSError:
        return "", "Cannot stat file."

    if size_mb > max_file_size_mb:
        return "", f"File too large ({size_mb:.1f} MB); limit is {max_file_size_mb} MB."

    ext = path.suffix.lower()

    # ── Plain text / CSV ────────────────────────────────────────────────────
    if ext in (".txt", ".md", ".rst", ".log", ".ini", ".cfg", ".toml",
               ".yaml", ".yml", ".json", ".xml", ".html", ".htm",
               ".sh", ".bat", ".ps1", ".env"):
        return _read_text_file(path)

    if ext == ".csv":
        return _read_csv(path)

    # ── PDF ─────────────────────────────────────────────────────────────────
    if ext == ".pdf":
        if _FITZ_OK:
            return _read_pdf(path, ocr_enabled=ocr_enabled)
        return "", "PyMuPDF not installed; PDF text extraction unavailable."

    # ── DOCX ────────────────────────────────────────────────────────────────
    if ext in (".docx", ".doc"):
        if _DOCX_OK:
            return _read_docx(path)
        return "", "python-docx not installed; DOCX extraction unavailable."

    # ── Unsupported ─────────────────────────────────────────────────────────
    return "", f"Unsupported format: {ext}"


# ---------------------------------------------------------------------------
# Format-specific helpers
# ---------------------------------------------------------------------------

def _read_text_file(path: Path) -> Tuple[str, str]:
    for enc in ("utf-8", "latin-1", "cp1252"):
        try:
            text = path.read_text(encoding=enc, errors="replace")
            return text[:50_000], ""
        except OSError as e:
            return "", str(e)
    return "", "Could not decode file."


def _read_csv(path: Path) -> Tuple[str, str]:
    try:
        with path.open(encoding="utf-8", errors="replace", newline="") as f:
            reader = csv.reader(f)
            lines = []
            for i, row in enumerate(reader):
                lines.append(" ".join(row))
                if i >= 500:
                    break
        return " ".join(lines), ""
    except Exception as e:
        return "", f"CSV read error: {e}"


def _read_pdf(path: Path, ocr_enabled: bool = False) -> Tuple[str, str]:
    try:
        doc = fitz.open(str(path))
        parts = []
        for page in doc:
            parts.append(page.get_text())
        text = " ".join(parts)
        doc.close()

        if not text.strip() and ocr_enabled and _TESSERACT_OK:
            return _ocr_pdf(path)

        return text[:50_000], ""
    except Exception as e:
        return "", f"PDF read error: {e}"


def _read_docx(path: Path) -> Tuple[str, str]:
    try:
        document = docx.Document(str(path))
        text = " ".join(p.text for p in document.paragraphs if p.text.strip())
        return text[:50_000], ""
    except Exception as e:
        return "", f"DOCX read error: {e}"


def _ocr_pdf(path: Path) -> Tuple[str, str]:
    """Fallback OCR for image-only PDFs."""
    try:
        doc = fitz.open(str(path))
        parts = []
        for page in doc:
            pix = page.get_pixmap(dpi=150)
            img = PILImage.open(io.BytesIO(pix.tobytes("png")))
            parts.append(pytesseract.image_to_string(img))
        doc.close()
        return " ".join(parts)[:50_000], "ocr"
    except Exception as e:
        return "", f"OCR error: {e}"
