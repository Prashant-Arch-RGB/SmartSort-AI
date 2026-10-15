"""
src/config.py — Application configuration, category definitions, and settings helpers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path(__file__).parent.parent
MODELS_DIR = ROOT / "models"
DATA_DIR = ROOT / "data"
MODEL_PATH = MODELS_DIR / "classifier.joblib"
TRAINING_DATA_PATH = DATA_DIR / "training_data.csv"

# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------
DEFAULT_CATEGORIES = [
    "Documents",
    "Images",
    "Videos",
    "Audio",
    "Archives",
    "Code",
    "Finance",
    "Work",
    "Education",
    "Personal",
    "Other",
]

# Extension → category mapping (used as fast pre-classifier)
EXTENSION_MAP: Dict[str, str] = {
    # Documents
    ".pdf": "Documents", ".doc": "Documents", ".docx": "Documents",
    ".odt": "Documents", ".rtf": "Documents", ".txt": "Documents",
    ".md": "Documents", ".rst": "Documents", ".tex": "Documents",
    # Images
    ".jpg": "Images", ".jpeg": "Images", ".png": "Images",
    ".gif": "Images", ".bmp": "Images", ".tiff": "Images",
    ".tif": "Images", ".svg": "Images", ".webp": "Images",
    ".heic": "Images", ".ico": "Images",
    # Videos
    ".mp4": "Videos", ".avi": "Videos", ".mkv": "Videos",
    ".mov": "Videos", ".wmv": "Videos", ".flv": "Videos",
    ".webm": "Videos", ".m4v": "Videos",
    # Audio
    ".mp3": "Audio", ".wav": "Audio", ".flac": "Audio",
    ".aac": "Audio", ".ogg": "Audio", ".wma": "Audio",
    ".m4a": "Audio", ".opus": "Audio",
    # Archives
    ".zip": "Archives", ".tar": "Archives", ".gz": "Archives",
    ".bz2": "Archives", ".7z": "Archives", ".rar": "Archives",
    ".xz": "Archives", ".iso": "Archives",
    # Code
    ".py": "Code", ".js": "Code", ".ts": "Code", ".jsx": "Code",
    ".tsx": "Code", ".html": "Code", ".htm": "Code", ".css": "Code",
    ".java": "Code", ".cpp": "Code", ".c": "Code", ".h": "Code",
    ".cs": "Code", ".go": "Code", ".rs": "Code", ".rb": "Code",
    ".php": "Code", ".sh": "Code", ".bat": "Code", ".ps1": "Code",
    ".json": "Code", ".xml": "Code", ".yaml": "Code", ".yml": "Code",
    ".toml": "Code", ".ini": "Code", ".cfg": "Code", ".env": "Code",
    ".sql": "Code", ".r": "Code", ".m": "Code",
    # Finance
    ".xls": "Finance", ".xlsx": "Finance", ".csv": "Finance",
    ".ods": "Finance",
    # Personal
    ".vcf": "Personal", ".ics": "Personal",
}

# Settings keys with defaults
SETTINGS_DEFAULTS: Dict[str, str] = {
    "theme": "dark",
    "default_dest_dir": "",
    "recursive_scan": "true",
    "excluded_extensions": ".tmp,.log,.ds_store,.thumbs",
    "excluded_paths": "__pycache__,.git,node_modules,.venv",
    "confidence_threshold": "0.55",
    "ocr_enabled": "false",
    "dry_run": "false",
    "max_file_size_mb": "50",
}


# ---------------------------------------------------------------------------
# Settings helpers (operate on an open sqlite3 connection)
# ---------------------------------------------------------------------------

def load_settings(conn) -> Dict[str, str]:
    """Load all settings from DB, falling back to defaults."""
    settings = dict(SETTINGS_DEFAULTS)
    try:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        for key, value in rows:
            settings[key] = value
    except Exception:
        pass
    return settings


def save_setting(conn, key: str, value: str) -> None:
    """Upsert a single setting value."""
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()


def get_category_for_extension(ext: str) -> Optional[str]:
    """Return the default category for a file extension, or None."""
    return EXTENSION_MAP.get(ext.lower())
