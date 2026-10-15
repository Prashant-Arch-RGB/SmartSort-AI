"""
scripts/train_model.py — CLI: train the SmartSort AI classifier.

Run from the project root:
    python scripts/train_model.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on sys.path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.trainer import train_from_csv
from src.config import TRAINING_DATA_PATH, MODEL_PATH


def main() -> None:
    print("SmartSort AI — Training Classifier")
    print(f"  Training data : {TRAINING_DATA_PATH}")
    print(f"  Model output  : {MODEL_PATH}")
    print()

    if not TRAINING_DATA_PATH.exists():
        print(f"ERROR: Training data not found at {TRAINING_DATA_PATH}")
        print("       Make sure data/training_data.csv exists.")
        sys.exit(1)

    try:
        result = train_from_csv()
        accuracy = result["accuracy"]
        total = result["total_samples"]
        print(f"Training complete!")
        print(f"  Samples   : {total}")
        print(f"  Accuracy  : {accuracy:.1%}")
        print(f"  Saved to  : {MODEL_PATH}")
    except Exception as exc:
        print(f"ERROR: Training failed — {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
