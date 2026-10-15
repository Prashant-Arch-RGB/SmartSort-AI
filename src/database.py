"""
src/database.py — SQLite schema initialisation and CRUD helpers.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).parent.parent
DB_PATH = ROOT / "smartsort.db"

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS scan_sessions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    root_path  TEXT    NOT NULL,
    started_at TEXT    NOT NULL,
    finished_at TEXT,
    total_files INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS scanned_files (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   INTEGER REFERENCES scan_sessions(id),
    filepath     TEXT    NOT NULL,
    filename     TEXT    NOT NULL,
    extension    TEXT    NOT NULL DEFAULT '',
    size_bytes   INTEGER NOT NULL DEFAULT 0,
    sha256       TEXT    NOT NULL DEFAULT '',
    category     TEXT    NOT NULL DEFAULT 'Other',
    confidence   REAL    NOT NULL DEFAULT 0.0,
    reason       TEXT    NOT NULL DEFAULT '',
    status       TEXT    NOT NULL DEFAULT 'pending',
    suggested_dest TEXT  NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS operation_batches (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   INTEGER REFERENCES scan_sessions(id),
    executed_at  TEXT NOT NULL,
    source_root  TEXT NOT NULL DEFAULT '',
    dest_root    TEXT NOT NULL DEFAULT '',
    total        INTEGER DEFAULT 0,
    moved        INTEGER DEFAULT 0,
    skipped      INTEGER DEFAULT 0,
    failed       INTEGER DEFAULT 0,
    dry_run      INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS file_operations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id    INTEGER REFERENCES operation_batches(id),
    filepath_src TEXT NOT NULL,
    filepath_dst TEXT NOT NULL,
    filename    TEXT NOT NULL DEFAULT '',
    category    TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'moved',
    executed_at TEXT NOT NULL,
    undone      INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS feedback (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    filepath     TEXT NOT NULL,
    filename     TEXT NOT NULL,
    category     TEXT NOT NULL,
    extracted_text TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL
);
"""


# Migrations: columns added after initial release
_MIGRATIONS = [
    "ALTER TABLE operation_batches ADD COLUMN executed_at TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE operation_batches ADD COLUMN source_root TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE operation_batches ADD COLUMN dest_root   TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE operation_batches ADD COLUMN skipped     INTEGER DEFAULT 0",
    "ALTER TABLE operation_batches ADD COLUMN failed      INTEGER DEFAULT 0",
    "ALTER TABLE operation_batches ADD COLUMN dry_run     INTEGER DEFAULT 0",
    "ALTER TABLE file_operations   ADD COLUMN filepath_src TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE file_operations   ADD COLUMN filepath_dst TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE file_operations   ADD COLUMN filename    TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE file_operations   ADD COLUMN category    TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE file_operations   ADD COLUMN status      TEXT NOT NULL DEFAULT 'moved'",
    "ALTER TABLE file_operations   ADD COLUMN executed_at TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE file_operations   ADD COLUMN undone      INTEGER DEFAULT 0",
]


def init_db(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Open (or create) the SQLite DB and ensure schema exists."""
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    for statement in _SCHEMA.strip().split(";"):
        stmt = statement.strip()
        if stmt:
            conn.execute(stmt)
    # Apply migrations idempotently — ignore "duplicate column" errors
    for migration in _MIGRATIONS:
        try:
            conn.execute(migration)
        except Exception:
            pass
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Scan session helpers
# ---------------------------------------------------------------------------

def create_scan_session(conn: sqlite3.Connection, root_path: str) -> int:
    cur = conn.execute(
        "INSERT INTO scan_sessions (root_path, started_at) VALUES (?, ?)",
        (root_path, datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()
    return cur.lastrowid


def finish_scan_session(conn: sqlite3.Connection, session_id: int, total_files: int) -> None:
    conn.execute(
        "UPDATE scan_sessions SET finished_at=?, total_files=? WHERE id=?",
        (datetime.now().isoformat(timespec="seconds"), total_files, session_id),
    )
    conn.commit()


def insert_scanned_file(conn: sqlite3.Connection, data: dict) -> int:
    cur = conn.execute(
        """INSERT INTO scanned_files
           (session_id, filepath, filename, extension, size_bytes, sha256,
            category, confidence, reason, status, suggested_dest)
           VALUES (:session_id,:filepath,:filename,:extension,:size_bytes,
                   :sha256,:category,:confidence,:reason,:status,:suggested_dest)""",
        data,
    )
    conn.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# Operation / batch helpers
# ---------------------------------------------------------------------------

def create_batch(
    conn: sqlite3.Connection,
    session_id: Optional[int],
    source_root: str,
    dest_root: str,
    dry_run: bool = False,
) -> int:
    cur = conn.execute(
        """INSERT INTO operation_batches
           (session_id, executed_at, source_root, dest_root, dry_run)
           VALUES (?, ?, ?, ?, ?)""",
        (session_id, datetime.now().isoformat(timespec="seconds"),
         source_root, dest_root, int(dry_run)),
    )
    conn.commit()
    return cur.lastrowid


def finish_batch(
    conn: sqlite3.Connection,
    batch_id: int,
    total: int,
    moved: int,
    skipped: int,
    failed: int,
) -> None:
    conn.execute(
        "UPDATE operation_batches SET total=?, moved=?, skipped=?, failed=? WHERE id=?",
        (total, moved, skipped, failed, batch_id),
    )
    conn.commit()


def insert_file_operation(
    conn: sqlite3.Connection,
    batch_id: int,
    src: str,
    dst: str,
    filename: str,
    category: str,
    status: str = "moved",
) -> int:
    cur = conn.execute(
        """INSERT INTO file_operations
           (batch_id, filepath_src, filepath_dst, filename, category, status, executed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (batch_id, src, dst, filename, category, status,
         datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()
    return cur.lastrowid


def mark_operation_undone(conn: sqlite3.Connection, op_id: int) -> None:
    conn.execute("UPDATE file_operations SET undone=1 WHERE id=?", (op_id,))
    conn.commit()


# ---------------------------------------------------------------------------
# Feedback helpers
# ---------------------------------------------------------------------------

def save_feedback(
    conn: sqlite3.Connection,
    filepath: str,
    filename: str,
    category: str,
    extracted_text: str = "",
) -> None:
    conn.execute(
        """INSERT INTO feedback (filepath, filename, category, extracted_text, created_at)
           VALUES (?, ?, ?, ?, ?)""",
        (filepath, filename, category, extracted_text,
         datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()


def get_all_feedback(conn: sqlite3.Connection) -> list:
    rows = conn.execute(
        "SELECT filename, category, extracted_text FROM feedback"
    ).fetchall()
    return [dict(r) for r in rows]
