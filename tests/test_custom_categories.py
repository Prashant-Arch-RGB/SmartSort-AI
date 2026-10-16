"""
tests/test_custom_categories.py
================================
Tests covering:

  1.  Data model — custom_categories and category_extensions tables
  2.  resolve_category() priority (custom > built-in > fallback)
  3.  Case-insensitive extension matching
  4.  Conflict resolution — duplicate ext across categories (last-write wins)
  5.  sanitize_category_name — strips illegal path chars
  6.  generate_plan — custom ext map overrides built-in category
  7.  generate_plan — files with unmapped extensions keep classifier result
  8.  generate_plan — name collision → numeric suffix
  9.  Missing destination folder is created automatically by execute_plan
  10. execute_plan — file moved into custom-category folder
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.database import (
    add_custom_category,
    delete_custom_category,
    get_custom_categories,
    get_custom_ext_map,
    init_db,
    rename_custom_category,
    set_extensions_for_category,
)
from src.config import resolve_category, sanitize_category_name
from src.organizer import generate_plan, execute_plan
from src.scanner import FileRecord


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    return init_db(db_path=tmp_path / "test.db")


@pytest.fixture
def src_dir(tmp_path):
    d = tmp_path / "source"
    d.mkdir()
    (d / "report.pdf").write_bytes(b"%PDF-1.4")
    (d / "budget.xlsx").write_bytes(b"PK fake xlsx")
    (d / "photo.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 8)
    (d / "script.py").write_text("print('hi')", encoding="utf-8")
    return d


@pytest.fixture
def dst_dir(tmp_path):
    d = tmp_path / "organized"
    d.mkdir()
    return d


def _rec(filepath: Path, category: str = "Other", ext: str = "") -> FileRecord:
    ext = ext or filepath.suffix.lower()
    return FileRecord(
        filepath=filepath,
        filename=filepath.name,
        extension=ext,
        size_bytes=filepath.stat().st_size if filepath.exists() else 0,
        category=category,
    )


# ===========================================================================
# 1. Data model
# ===========================================================================

class TestDataModel:

    def test_add_and_retrieve_category(self, db):
        """add_custom_category inserts a row; get_custom_categories returns it."""
        add_custom_category(db, "Work Documents", "#ff0000")
        cats = get_custom_categories(db)
        assert any(c["name"] == "Work Documents" for c in cats)

    def test_add_duplicate_name_raises(self, db):
        add_custom_category(db, "Dup")
        with pytest.raises(sqlite3.IntegrityError):
            add_custom_category(db, "Dup")

    def test_rename_category(self, db):
        add_custom_category(db, "OldName")
        ok = rename_custom_category(db, "OldName", "NewName")
        assert ok
        names = [c["name"] for c in get_custom_categories(db)]
        assert "NewName" in names
        assert "OldName" not in names

    def test_delete_category(self, db):
        add_custom_category(db, "Temp")
        ok = delete_custom_category(db, "Temp")
        assert ok
        names = [c["name"] for c in get_custom_categories(db)]
        assert "Temp" not in names

    def test_delete_nonexistent_returns_false(self, db):
        assert delete_custom_category(db, "DoesNotExist") is False

    def test_rename_nonexistent_returns_false(self, db):
        assert rename_custom_category(db, "Ghost", "NewGhost") is False

    def test_set_and_get_extensions(self, db):
        """set_extensions_for_category writes; get_custom_categories reads back."""
        add_custom_category(db, "Finance")
        set_extensions_for_category(db, "Finance", [".xls", ".xlsx", ".csv"])
        cats = get_custom_categories(db)
        fin = next(c for c in cats if c["name"] == "Finance")
        assert set(fin["extensions"]) == {".xls", ".xlsx", ".csv"}

    def test_extension_normalised_to_lowercase(self, db):
        """Extensions passed in uppercase/mixed are stored as lowercase."""
        add_custom_category(db, "NormTest")
        set_extensions_for_category(db, "NormTest", [".PDF", "DOCX", ".Xlsx"])
        cats = get_custom_categories(db)
        nt = next(c for c in cats if c["name"] == "NormTest")
        assert ".pdf" in nt["extensions"]
        assert ".docx" in nt["extensions"]
        assert ".xlsx" in nt["extensions"]

    def test_invalid_extension_is_skipped(self, db):
        """Extensions that are just a dot or contain spaces are silently skipped."""
        add_custom_category(db, "EdgeTest")
        set_extensions_for_category(db, "EdgeTest", [".", ".bad ext", ".ok"])
        cats = get_custom_categories(db)
        et = next(c for c in cats if c["name"] == "EdgeTest")
        assert et["extensions"] == [".ok"]

    def test_delete_cascades_extensions(self, db):
        """Deleting a category also removes all its extension mappings."""
        add_custom_category(db, "TempCat")
        set_extensions_for_category(db, "TempCat", [".zzz"])
        delete_custom_category(db, "TempCat")
        ext_map = get_custom_ext_map(db)
        assert ".zzz" not in ext_map

    def test_rename_cascades_to_extensions(self, db):
        """Renaming a category updates the foreign key in category_extensions."""
        add_custom_category(db, "Before")
        set_extensions_for_category(db, "Before", [".yyy"])
        rename_custom_category(db, "Before", "After")
        ext_map = get_custom_ext_map(db)
        assert ext_map.get(".yyy") == "After"


# ===========================================================================
# 2 & 3. resolve_category — priority and case-insensitivity
# ===========================================================================

class TestResolveCategory:

    def test_custom_overrides_builtin(self):
        """A custom rule beats the built-in EXTENSION_MAP."""
        custom = {".pdf": "Work Documents"}
        # .pdf is "Documents" in the built-in map
        assert resolve_category(".pdf", custom) == "Work Documents"

    def test_builtin_used_when_no_custom(self):
        assert resolve_category(".jpg", {}) == "Images"
        assert resolve_category(".mp3", {}) == "Audio"

    def test_fallback_for_unknown_extension(self):
        assert resolve_category(".xyz", {}) == "Other"

    def test_case_insensitive_ext(self):
        """Extension matching is case-insensitive."""
        custom = {".pdf": "MyCategory"}
        assert resolve_category(".PDF", custom) == "MyCategory"
        assert resolve_category(".Pdf", custom) == "MyCategory"

    def test_ext_without_leading_dot(self):
        """Extensions passed without a leading dot are handled gracefully."""
        assert resolve_category("jpg", {}) == "Images"

    def test_empty_custom_map_uses_builtin(self):
        assert resolve_category(".zip", None) == "Archives"


# ===========================================================================
# 4. Conflict resolution — duplicate ext across categories
# ===========================================================================

class TestExtensionConflict:

    def test_last_write_wins(self, db):
        """When .pdf is saved to Cat-A then Cat-B, the map shows Cat-B."""
        add_custom_category(db, "Cat-A")
        add_custom_category(db, "Cat-B")
        set_extensions_for_category(db, "Cat-A", [".pdf"])
        # Cat-B claims .pdf: should evict it from Cat-A
        set_extensions_for_category(db, "Cat-B", [".pdf"])
        ext_map = get_custom_ext_map(db)
        assert ext_map[".pdf"] == "Cat-B"

    def test_original_category_loses_ext(self, db):
        """After conflict resolution, Cat-A no longer lists .pdf."""
        add_custom_category(db, "Cat-A")
        add_custom_category(db, "Cat-B")
        set_extensions_for_category(db, "Cat-A", [".pdf"])
        set_extensions_for_category(db, "Cat-B", [".pdf"])
        cats = get_custom_categories(db)
        cat_a = next(c for c in cats if c["name"] == "Cat-A")
        assert ".pdf" not in cat_a["extensions"]


# ===========================================================================
# 5. sanitize_category_name
# ===========================================================================

class TestSanitize:

    def test_strips_path_separators(self):
        assert "/" not in sanitize_category_name("My/Category")
        assert "\\" not in sanitize_category_name("My\\Category")

    def test_strips_colon_and_star(self):
        result = sanitize_category_name("Cat:*name")
        assert ":" not in result
        assert "*" not in result

    def test_strips_leading_dot(self):
        assert not sanitize_category_name("..hidden").startswith(".")

    def test_empty_string_returns_custom(self):
        assert sanitize_category_name("") == "Custom"
        assert sanitize_category_name("   ") == "Custom"

    def test_max_length_64(self):
        long_name = "A" * 100
        assert len(sanitize_category_name(long_name)) <= 64


# ===========================================================================
# 6. generate_plan — custom ext map overrides built-in
# ===========================================================================

class TestGeneratePlanWithCustomMap:

    def test_custom_map_overrides_builtin_category(self, src_dir, dst_dir):
        """A .pdf mapped to 'Work Documents' should land in that folder."""
        rec = _rec(src_dir / "report.pdf", category="Documents")
        custom_map = {".pdf": "Work Documents"}
        proposals = generate_plan([rec], dst_dir, src_dir,
                                  custom_ext_map=custom_map)
        assert proposals[0].dst_path.parent == dst_dir / "Work Documents"

    def test_builtin_category_used_when_no_custom_rule(self, src_dir, dst_dir):
        """.jpg with empty custom map → built-in 'Images'."""
        rec = _rec(src_dir / "photo.jpg", category="Images")
        proposals = generate_plan([rec], dst_dir, src_dir, custom_ext_map={})
        assert proposals[0].dst_path.parent == dst_dir / "Images"

    def test_session_override_beats_custom_map(self, src_dir, dst_dir):
        """A manual session override takes priority over the custom extension rule."""
        pdf = src_dir / "report.pdf"
        rec = _rec(pdf, category="Documents")
        overrides = {str(pdf): "Personal"}
        custom_map = {".pdf": "Work Documents"}
        proposals = generate_plan([rec], dst_dir, src_dir,
                                  overrides=overrides,
                                  custom_ext_map=custom_map)
        assert proposals[0].dst_path.parent == dst_dir / "Personal"

    def test_classifier_result_kept_for_unmapped_ext(self, src_dir, dst_dir):
        """If neither custom map nor built-in covers an ext, use the classifier."""
        unknown = src_dir / "weird.zzz"
        unknown.write_text("something", encoding="utf-8")
        rec = _rec(unknown, category="Finance")  # classifier said Finance
        proposals = generate_plan([rec], dst_dir, src_dir, custom_ext_map={})
        assert proposals[0].dst_path.parent == dst_dir / "Finance"

    def test_fallback_to_other_when_nothing_matches(self, tmp_path, dst_dir):
        """No rule, no classifier result → 'Other'."""
        src = tmp_path / "source"
        src.mkdir()
        f = src / "noext"
        f.write_text("x")
        rec = FileRecord(filepath=f, filename="noext", extension="",
                         size_bytes=1, category="")
        proposals = generate_plan([rec], dst_dir, src, custom_ext_map={})
        assert proposals[0].dst_path.parent == dst_dir / "Other"


# ===========================================================================
# 8. Name collision → numeric suffix
# ===========================================================================

class TestNameCollision:

    def test_same_filename_different_number(self, src_dir, dst_dir):
        """Two records with the same filename get distinct suffixed destinations."""
        f1 = src_dir / "report.pdf"
        f2 = src_dir / "sub"
        f2.mkdir()
        f2 = f2 / "report.pdf"
        f2.write_bytes(b"%PDF-1.5")

        recs = [
            _rec(f1, category="Work"),
            _rec(f2, category="Work"),
        ]
        proposals = generate_plan(recs, dst_dir, src_dir)
        dst_names = [p.dst_path.name for p in proposals]
        assert len(set(dst_names)) == 2, "Expected two distinct destination filenames"


# ===========================================================================
# 9 & 10. execute_plan — missing folder creation + actual move
# ===========================================================================

class TestExecutePlan:

    def test_missing_category_folder_is_created(self, src_dir, dst_dir, db):
        """execute_plan creates the category subdirectory if it does not exist."""
        rec = _rec(src_dir / "report.pdf", category="Work")
        custom_map = {".pdf": "Work"}
        proposals = generate_plan([rec], dst_dir, src_dir, custom_ext_map=custom_map)
        result = execute_plan(proposals, db, session_id=None, dry_run=False)
        assert result.moved == 1
        assert (dst_dir / "Work").is_dir()

    def test_file_moved_to_custom_category_folder(self, src_dir, dst_dir, db):
        """File lands in the custom-category folder, not the built-in one."""
        rec = _rec(src_dir / "budget.xlsx", category="Finance")
        custom_map = {".xlsx": "MyFinance"}
        proposals = generate_plan([rec], dst_dir, src_dir, custom_ext_map=custom_map)
        result = execute_plan(proposals, db, session_id=None, dry_run=False)
        assert result.moved == 1
        assert (dst_dir / "MyFinance" / "budget.xlsx").exists()
        assert not (src_dir / "budget.xlsx").exists()

    def test_dry_run_does_not_move_file(self, src_dir, dst_dir, db):
        """Dry-run: moved counter incremented but file stays in place."""
        rec = _rec(src_dir / "script.py", category="Code")
        proposals = generate_plan([rec], dst_dir, src_dir)
        result = execute_plan(proposals, db, session_id=None, dry_run=True)
        assert result.moved == 1
        assert result.dry_run is True
        assert (src_dir / "script.py").exists()
        assert not (dst_dir / "Code" / "script.py").exists()
