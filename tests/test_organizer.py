"""
test_organizer.py — Tests for safe file movement, conflict detection, and undo.
"""

import pytest
import shutil
from pathlib import Path

from src.organizer import (
    generate_plan,
    execute_plan,
    undo_operation,
    build_destination_path,
    resolve_conflict,
)
from src.scanner import FileRecord
from src.database import init_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    db_file = tmp_path / "test.db"
    return init_db(db_path=db_file)


@pytest.fixture
def source_dir(tmp_path):
    src = tmp_path / "source"
    src.mkdir()
    (src / "document.txt").write_text("Hello world", encoding="utf-8")
    (src / "photo.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 10)
    (src / "code.py").write_text("print('hi')", encoding="utf-8")
    return src


@pytest.fixture
def dest_dir(tmp_path):
    d = tmp_path / "organized"
    d.mkdir()
    return d


def make_record(filepath: Path, category: str = "Work") -> FileRecord:
    return FileRecord(
        filepath=filepath,
        filename=filepath.name,
        extension=filepath.suffix.lower(),
        size_bytes=filepath.stat().st_size,
        category=category,
    )


# ---------------------------------------------------------------------------
# build_destination_path
# ---------------------------------------------------------------------------

def test_build_destination_path_structure(tmp_path):
    rec = FileRecord(
        filepath=tmp_path / "report.pdf",
        filename="report.pdf",
        extension=".pdf",
        size_bytes=100,
        category="Work",
    )
    dest = build_destination_path(rec, tmp_path / "organized")
    assert dest == tmp_path / "organized" / "Work" / "report.pdf"


def test_build_destination_sanitizes_category(tmp_path):
    rec = FileRecord(
        filepath=tmp_path / "file.txt",
        filename="file.txt",
        extension=".txt",
        size_bytes=10,
        category="My/Special:Category",
    )
    dest = build_destination_path(rec, tmp_path / "organized")
    # Should not contain / or : in path
    assert "/" not in dest.name
    assert ":" not in str(dest.parent.name)


# ---------------------------------------------------------------------------
# resolve_conflict
# ---------------------------------------------------------------------------

def test_resolve_conflict_no_conflict(tmp_path):
    path = tmp_path / "file.txt"
    resolved = resolve_conflict(path)
    assert resolved == path


def test_resolve_conflict_with_existing(tmp_path):
    path = tmp_path / "file.txt"
    path.write_text("original")
    resolved = resolve_conflict(path)
    assert resolved != path
    assert resolved.parent == path.parent
    assert not resolved.exists()


def test_resolve_conflict_multiple(tmp_path):
    path = tmp_path / "file.txt"
    path.write_text("original")
    (tmp_path / "file_(1).txt").write_text("copy 1")
    resolved = resolve_conflict(path)
    assert resolved.name == "file_(2).txt"


# ---------------------------------------------------------------------------
# generate_plan
# ---------------------------------------------------------------------------

def test_generate_plan_creates_proposals(source_dir, dest_dir):
    records = [make_record(source_dir / "document.txt", "Work")]
    proposals = generate_plan(records, dest_dir, source_dir)
    assert len(proposals) == 1
    assert proposals[0].dst_dir == dest_dir / "Work"
    assert proposals[0].src_path == source_dir / "document.txt"


def test_generate_plan_detects_conflict(source_dir, dest_dir):
    # Pre-create the destination file
    (dest_dir / "Work").mkdir()
    (dest_dir / "Work" / "document.txt").write_text("existing")

    records = [make_record(source_dir / "document.txt", "Work")]
    proposals = generate_plan(records, dest_dir, source_dir)
    assert proposals[0].conflict is True
    assert "exists" in proposals[0].conflict_reason.lower()
    # Destination should have been renamed
    assert proposals[0].dst_path.name != "document.txt"


def test_generate_plan_allows_dest_inside_source(source_dir):
    """Destination that is a subdirectory of source is now allowed."""
    nested_dest = source_dir / "organized"
    nested_dest.mkdir()

    records = [make_record(source_dir / "document.txt", "Work")]
    proposals = generate_plan(records, nested_dest, source_dir)
    # All proposals should be approved — subdirectory destinations are permitted
    assert all(p.approved for p in proposals)


def test_generate_plan_applies_category_overrides(source_dir, dest_dir):
    records = [make_record(source_dir / "document.txt", "Work")]
    overrides = {str(source_dir / "document.txt"): "Finance"}
    proposals = generate_plan(records, dest_dir, source_dir, overrides)
    assert proposals[0].dst_dir == dest_dir / "Finance"


# ---------------------------------------------------------------------------
# execute_plan — successful move
# ---------------------------------------------------------------------------

def test_execute_plan_moves_file(source_dir, dest_dir, db):
    records = [make_record(source_dir / "document.txt", "Work")]
    proposals = generate_plan(records, dest_dir, source_dir)
    result = execute_plan(proposals, db, session_id=None, dry_run=False)
    assert result.moved == 1
    assert result.failed == 0
    assert (dest_dir / "Work" / "document.txt").exists()
    assert not (source_dir / "document.txt").exists()


def test_execute_plan_dry_run_no_changes(source_dir, dest_dir, db):
    records = [make_record(source_dir / "document.txt", "Work")]
    proposals = generate_plan(records, dest_dir, source_dir)
    result = execute_plan(proposals, db, session_id=None, dry_run=True)
    assert result.moved == 1
    assert result.dry_run is True
    # File should NOT have moved
    assert (source_dir / "document.txt").exists()
    assert not (dest_dir / "Work" / "document.txt").exists()


def test_execute_plan_skips_unapproved(source_dir, dest_dir, db):
    records = [make_record(source_dir / "document.txt", "Work")]
    proposals = generate_plan(records, dest_dir, source_dir)
    proposals[0].approved = False
    result = execute_plan(proposals, db, session_id=None, dry_run=False)
    assert result.skipped == 1
    assert result.moved == 0
    assert (source_dir / "document.txt").exists()


def test_execute_plan_fails_when_src_missing(db, tmp_path):
    # Use a source_root that does NOT contain dest_dir
    source_root = tmp_path / "source"
    source_root.mkdir()
    dest = tmp_path / "dest"
    dest.mkdir()

    ghost_path = source_root / "ghost.txt"
    record = FileRecord(
        filepath=ghost_path,
        filename="ghost.txt",
        extension=".txt",
        size_bytes=0,
        category="Work",
    )
    proposals = generate_plan([record], dest, source_root)
    result = execute_plan(proposals, db, session_id=None, dry_run=False)
    assert result.failed == 1


def test_execute_plan_does_not_overwrite(source_dir, dest_dir, db):
    """Even after re-plan, if destination appears just before move, fail gracefully."""
    records = [make_record(source_dir / "document.txt", "Work")]
    proposals = generate_plan(records, dest_dir, source_dir)
    # Manually plant the destination file between plan and execute
    (dest_dir / "Work").mkdir(parents=True, exist_ok=True)
    (dest_dir / "Work" / "document.txt").write_text("already here")
    # Restore the original proposal dst to the pre-existing path to test guard
    proposals[0].dst_path = dest_dir / "Work" / "document.txt"

    result = execute_plan(proposals, db, session_id=None, dry_run=False)
    assert result.failed == 1
    # Original file must still be there
    assert (source_dir / "document.txt").exists()


# ---------------------------------------------------------------------------
# Undo
# ---------------------------------------------------------------------------

def test_undo_restores_file(source_dir, dest_dir, db):
    records = [make_record(source_dir / "document.txt", "Work")]
    proposals = generate_plan(records, dest_dir, source_dir)
    result = execute_plan(proposals, db, session_id=None, dry_run=False)
    assert result.moved == 1

    # Get the op_id
    op_row = db.execute(
        "SELECT id FROM file_operations WHERE status='moved' LIMIT 1"
    ).fetchone()
    assert op_row is not None
    op_id = op_row["id"]

    success, msg = undo_operation(db, op_id)
    assert success, msg
    assert (source_dir / "document.txt").exists()
    assert not (dest_dir / "Work" / "document.txt").exists()


def test_undo_conflict_prompts_alternative(source_dir, dest_dir, db):
    """If original location is re-occupied, undo should fail with an explanation."""
    records = [make_record(source_dir / "document.txt", "Work")]
    proposals = generate_plan(records, dest_dir, source_dir)
    execute_plan(proposals, db, session_id=None, dry_run=False)

    # Re-create a file at the original location
    (source_dir / "document.txt").write_text("a new file appeared here")

    op_row = db.execute(
        "SELECT id FROM file_operations WHERE status='moved' LIMIT 1"
    ).fetchone()
    assert op_row is not None

    success, msg = undo_operation(db, op_row["id"])
    assert not success
    assert "occupied" in msg.lower() or "already" in msg.lower()


def test_undo_with_alternative_dest(source_dir, dest_dir, db, tmp_path):
    """If original location occupied, alternative dest should work."""
    records = [make_record(source_dir / "document.txt", "Work")]
    proposals = generate_plan(records, dest_dir, source_dir)
    execute_plan(proposals, db, session_id=None, dry_run=False)

    (source_dir / "document.txt").write_text("new file at original location")
    alt_restore = tmp_path / "restore_here" / "document.txt"

    op_row = db.execute(
        "SELECT id FROM file_operations WHERE status='moved' LIMIT 1"
    ).fetchone()
    success, msg = undo_operation(db, op_row["id"], str(alt_restore))
    assert success, msg
    assert alt_restore.exists()


def test_undo_already_undone_fails(source_dir, dest_dir, db):
    records = [make_record(source_dir / "document.txt", "Work")]
    proposals = generate_plan(records, dest_dir, source_dir)
    execute_plan(proposals, db, session_id=None, dry_run=False)

    op_row = db.execute(
        "SELECT id FROM file_operations WHERE status='moved' LIMIT 1"
    ).fetchone()
    op_id = op_row["id"]

    undo_operation(db, op_id)
    success, msg = undo_operation(db, op_id)
    assert not success


def test_undo_nonexistent_op(db):
    success, msg = undo_operation(db, 99999)
    assert not success
    assert "not found" in msg.lower()
