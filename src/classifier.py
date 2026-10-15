"""
src/classifier.py — TF-IDF + Logistic Regression file classifier.

classify_batch() enriches FileRecord objects in-place with category,
confidence, and reason fields.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

from src.config import MODEL_PATH, DEFAULT_CATEGORIES, get_category_for_extension
from src.scanner import FileRecord
from src.extractors import extract_text

logger = logging.getLogger(__name__)

# Module-level model cache
_model = None


def _load_model():
    """Load model from disk into cache. Returns None if not found."""
    global _model
    if not MODEL_PATH.exists():
        return None
    try:
        import joblib
        _model = joblib.load(str(MODEL_PATH))
        logger.info("Classifier model loaded from %s", MODEL_PATH)
    except Exception as exc:
        logger.error("Failed to load model: %s", exc)
        _model = None
    return _model


def reload_model() -> None:
    """Force reload of the model from disk (call after retraining)."""
    global _model
    _model = None
    _load_model()


def model_status() -> str:
    """Return a human-readable model status string."""
    if MODEL_PATH.exists():
        return "loaded" if (_model is not None or _load_model() is not None) else "error"
    return "not_trained"


def _predict(text: str) -> tuple[str, float]:
    """
    Run the ML model on *text*. Returns (category, confidence).
    Falls back to ("Other", 0.0) if model unavailable.
    """
    global _model
    if _model is None:
        _load_model()
    if _model is None:
        return "Other", 0.0

    try:
        proba = _model.predict_proba([text])[0]
        idx = proba.argmax()
        return _model.classes_[idx], float(proba[idx])
    except Exception as exc:
        logger.warning("Prediction error: %s", exc)
        return "Other", 0.0


def classify_record(
    record: FileRecord,
    confidence_threshold: float = 0.55,
    max_file_size_mb: float = 50.0,
    ocr_enabled: bool = False,
) -> None:
    """Classify a single FileRecord in-place."""
    # 1. Fast path — extension rule
    ext_cat = get_category_for_extension(record.extension)

    # 2. Text extraction
    text, note = extract_text(
        record.filepath,
        max_file_size_mb=max_file_size_mb,
        ocr_enabled=ocr_enabled,
    )
    record.extracted_text = text

    # 3. ML prediction on text (if any)
    if text.strip():
        ml_cat, ml_conf = _predict(text)
    else:
        ml_cat, ml_conf = "Other", 0.0

    # 4. Decision logic
    if ml_conf >= confidence_threshold:
        # ML confident — use its prediction
        record.category = ml_cat
        record.confidence = ml_conf
        record.reason = "ml"
    elif ext_cat:
        # Extension rule wins when ML is unsure
        record.category = ext_cat
        record.confidence = 0.80
        record.reason = "extension"
    elif ml_conf > 0.0:
        # Weak ML signal
        record.category = ml_cat
        record.confidence = ml_conf
        record.reason = "ml_low"
    else:
        record.category = "Other"
        record.confidence = 0.0
        record.reason = "fallback"

    # Validate category
    if record.category not in DEFAULT_CATEGORIES:
        record.category = "Other"


def classify_batch(
    records: List[FileRecord],
    confidence_threshold: float = 0.55,
    max_file_size_mb: float = 50.0,
    ocr_enabled: bool = False,
) -> None:
    """Classify all records in *records* in-place."""
    # Ensure model is loaded once before the loop
    if _model is None:
        _load_model()

    for record in records:
        try:
            classify_record(
                record,
                confidence_threshold=confidence_threshold,
                max_file_size_mb=max_file_size_mb,
                ocr_enabled=ocr_enabled,
            )
        except Exception as exc:
            logger.warning("classify_record failed for %s: %s", record.filepath, exc)
            record.category = "Other"
            record.confidence = 0.0
            record.reason = "error"
