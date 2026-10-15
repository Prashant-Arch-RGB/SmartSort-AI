"""
src/trainer.py — ML model training and retrain-from-feedback.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict

from src.config import MODEL_PATH, TRAINING_DATA_PATH, DEFAULT_CATEGORIES

logger = logging.getLogger(__name__)


def _build_pipeline():
    """Return a fresh TF-IDF + LogisticRegression pipeline."""
    from sklearn.pipeline import Pipeline
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression

    return Pipeline([
        ("tfidf", TfidfVectorizer(
            max_features=20_000,
            ngram_range=(1, 2),
            sublinear_tf=True,
            min_df=1,
        )),
        ("clf", LogisticRegression(
            max_iter=1000,
            C=5.0,
            solver="lbfgs",
            multi_class="multinomial",
        )),
    ])


def train_from_csv(csv_path: Path = TRAINING_DATA_PATH) -> Dict:
    """
    Train classifier from a CSV file with columns: text, category.
    Saves model to MODEL_PATH and returns metrics dict.
    """
    import pandas as pd
    import joblib
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score

    if not csv_path.exists():
        raise FileNotFoundError(f"Training data not found: {csv_path}")

    df = pd.read_csv(csv_path)
    df = df.dropna(subset=["text", "category"])
    df = df[df["category"].isin(DEFAULT_CATEGORIES)]

    if len(df) < 10:
        raise ValueError(f"Too few training samples: {len(df)}")

    X = df["text"].astype(str).tolist()
    y = df["category"].tolist()

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y if len(set(y)) > 1 else None
    )

    pipeline = _build_pipeline()
    pipeline.fit(X_train, y_train)

    y_pred = pipeline.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, str(MODEL_PATH))
    logger.info("Model trained. Accuracy: %.1f%% — saved to %s", accuracy * 100, MODEL_PATH)

    return {"accuracy": accuracy, "total_samples": len(df)}


def retrain_from_feedback(conn) -> Dict:
    """
    Retrain the model by augmenting the base training data with saved feedback.
    Returns metrics dict or {"skipped": True, "reason": ...}.
    """
    import pandas as pd
    import joblib
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score
    from src.database import get_all_feedback

    feedback = get_all_feedback(conn)
    if not feedback:
        return {"skipped": True, "reason": "No feedback saved yet."}

    fb_df = pd.DataFrame(feedback)
    fb_df = fb_df.rename(columns={"extracted_text": "text"})
    fb_df = fb_df[["text", "category"]]
    fb_df = fb_df[fb_df["category"].isin(DEFAULT_CATEGORIES)]
    fb_df = fb_df[fb_df["text"].str.strip() != ""]

    if len(fb_df) < 5:
        return {"skipped": True, "reason": f"Only {len(fb_df)} usable feedback sample(s). Need at least 5."}

    # Combine with base training data if available
    if TRAINING_DATA_PATH.exists():
        base_df = pd.read_csv(TRAINING_DATA_PATH).dropna(subset=["text", "category"])
        base_df = base_df[base_df["category"].isin(DEFAULT_CATEGORIES)]
        combined = pd.concat([base_df, fb_df], ignore_index=True)
    else:
        combined = fb_df

    X = combined["text"].astype(str).tolist()
    y = combined["category"].tolist()

    if len(set(y)) < 2:
        return {"skipped": True, "reason": "Need at least 2 categories to train."}

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )

    pipeline = _build_pipeline()
    pipeline.fit(X_train, y_train)

    y_pred = pipeline.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, str(MODEL_PATH))
    logger.info("Model retrained from feedback. Accuracy: %.1f%%", accuracy * 100)

    return {"accuracy": accuracy, "total_samples": len(combined)}
