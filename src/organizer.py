"""
src/organizer.py — Plan generation, file moves, undo.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.scanner import FileRecord
from src.database import (
    create_batch, finish_batch, insert_file_operation, mark_operation_undone,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Proposal:
    """A proposed file move."""
    record: FileRecord
    src_path: Path
    dst_path: Path
    conflict: bool = False
    conflict_reason: str = ""


@dataclass
class ExecuteResult:
    batch_id: int
    total: int
    moved: int
    skipped: int
    failed: int
    dry_run: bool
    details: List[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Plan generation
# ---------------------------------------------------------------------------

def generate_plan(
    records: List[FileRecord],
    dest_root: Path,
    source_root: Path,
    overrides: Optional[Dict[str, str]] = None,
    custom_ext_map: Optional[Dict[str, str]] = None,
) -> List[Proposal]:
    """
    Build a list of Proposal objects for moving files.

    Files are placed at: dest_root / category / filename.
    Duplicate filenames at the destination get a numeric suffix.

    Category resolution order (per file)
    -------------------------------------
    1. ``overrides`` dict (user correction in the current session).
    2. ``custom_ext_map`` (user-defined extension → category rules).
    3. Built-in ``EXTENSION_MAP`` / classifier result on the record.
    4. ``"Other"`` fallback.
    """
    from src.config import resolve_category

    overrides = overrides or {}
    custom_ext_map = custom_ext_map or {}
    proposals: List[Proposal] = []
    seen_dsts: Dict[str, int] = {}  # dst_path_str -> count (for dedup)

    for rec in records:
        # 1. Manual session override takes top priority
        if str(rec.filepath) in overrides:
            category = overrides[str(rec.filepath)]
        else:
            # 2+3+4: custom rule → built-in → "Other"
            category = resolve_category(rec.extension, custom_ext_map)
            # If the classifier produced a result and no custom/built-in rule
            # matched, keep the classifier's answer (it may be more specific).
            if category == "Other" and rec.category and rec.category != "Other":
                category = rec.category

        dst_dir = dest_root / category

        # Build a unique destination filename
        base_key = str(dst_dir / rec.filename).lower()
        count = seen_dsts.get(base_key, 0)
        if count == 0:
            dst_path = dst_dir / rec.filename
        else:
            stem = rec.filepath.stem
            suffix = rec.filepath.suffix
            dst_path = dst_dir / f"{stem}_{count}{suffix}"
        seen_dsts[base_key] = count + 1

        # Detect conflict: destination already exists on disk
        conflict = dst_path.exists()
        conflict_reason = "File already exists at destination." if conflict else ""

        # Also mark conflict if source == destination
        if rec.filepath.resolve() == dst_path.resolve():
            conflict = True
            conflict_reason = "Source and destination are the same file."

        proposals.append(
            Proposal(
                record=rec,
                src_path=rec.filepath,
                dst_path=dst_path,
                conflict=conflict,
                conflict_reason=conflict_reason,
            )
        )

    return proposals


# ---------------------------------------------------------------------------
# Plan execution
# ---------------------------------------------------------------------------

def execute_plan(
    proposals: List[Proposal],
    conn,
    session_id: Optional[int],
    dry_run: bool = False,
) -> ExecuteResult:
    """Move files according to *proposals*. Returns an ExecuteResult."""
    if not proposals:
        return ExecuteResult(batch_id=0, total=0, moved=0, skipped=0, failed=0,
                             dry_run=dry_run)

    # Determine source/dest roots from first proposal
    source_root = str(proposals[0].src_path.parent)
    dest_root = str(proposals[0].dst_path.parent.parent)

    batch_id = create_batch(conn, session_id, source_root, dest_root, dry_run)

    moved = skipped = failed = 0
    details: List[dict] = []

    for proposal in proposals:
        src = proposal.src_path
        dst = proposal.dst_path

        if proposal.conflict and dst.exists():
            skipped += 1
            status = "skipped"
            details.append({
                "filename": src.name,
                "src": str(src),
                "dst": str(dst),
                "status": status,
                "reason": proposal.conflict_reason,
            })
            insert_file_operation(conn, batch_id, str(src), str(dst),
                                  src.name, proposal.record.category or "Other",
                                  status)
            continue

        if dry_run:
            moved += 1
            status = "dry_run"
        else:
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
                moved += 1
                status = "moved"
            except Exception as exc:
                logger.error("Move failed %s → %s: %s", src, dst, exc)
                failed += 1
                status = "failed"

        details.append({
            "filename": src.name,
            "src": str(src),
            "dst": str(dst),
            "status": status,
        })
        insert_file_operation(conn, batch_id, str(src), str(dst),
                              src.name, proposal.record.category or "Other",
                              status)

    finish_batch(conn, batch_id, len(proposals), moved, skipped, failed)

    return ExecuteResult(
        batch_id=batch_id,
        total=len(proposals),
        moved=moved,
        skipped=skipped,
        failed=failed,
        dry_run=dry_run,
        details=details,
    )


# ---------------------------------------------------------------------------
# Undo
# ---------------------------------------------------------------------------

def undo_operation(
    conn,
    op_id: int,
    alternative_dest: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Move a file back to its original location (or *alternative_dest*).

    Returns (success, message).
    """
    row = conn.execute(
        "SELECT * FROM file_operations WHERE id=? AND undone=0",
        (op_id,),
    ).fetchone()

    if not row:
        return False, f"Operation {op_id} not found or already undone."

    src = Path(row["filepath_dst"])   # current location (where it was moved to)
    original = Path(row["filepath_src"])  # where it came from

    dest = Path(alternative_dest) if alternative_dest else original

    if not src.exists():
        return False, f"File not found at current location: {src}"

    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
        mark_operation_undone(conn, op_id)
        return True, f"Moved back: {src.name} → {dest}"
    except Exception as exc:
        logger.error("Undo failed for op %d: %s", op_id, exc)
        return False, f"Undo failed: {exc}"
