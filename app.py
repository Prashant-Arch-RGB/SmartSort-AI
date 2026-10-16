"""
app.py — SmartSort AI Flask application entry point.

Run with:
    python app.py
    or
    flask run

Pages:
  /             → Dashboard
  /scan         → Scan a Folder
  /preview      → Preview & Organize
  /history      → History & Undo
  /settings     → Settings
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

# Ensure project root on path
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from src.database import init_db
from src.config import load_settings, save_setting, DEFAULT_CATEGORIES

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    filename=str(ROOT / "smartsort.log"),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Flask app setup
# ---------------------------------------------------------------------------
app = Flask(__name__, template_folder="templates", static_folder="static")
# Use a fixed secret key so sessions survive server restarts.
# Generate once and store in a local file; create if missing.
_key_file = ROOT / ".secret_key"
if _key_file.exists():
    app.secret_key = _key_file.read_bytes()
else:
    _key = os.urandom(32)
    _key_file.write_bytes(_key)
    app.secret_key = _key
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"

# ---------------------------------------------------------------------------
# Database (module-level singleton)
# ---------------------------------------------------------------------------
_conn = None


def get_db():
    global _conn
    if _conn is None:
        _conn = init_db()
    return _conn


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1_048_576:
        return f"{n / 1024:.1f} KB"
    if n < 1_073_741_824:
        return f"{n / 1_048_576:.1f} MB"
    return f"{n / 1_073_741_824:.2f} GB"


def get_session_records() -> List[Dict]:
    """Return scanned file records stored in the server session."""
    return session.get("scan_records", [])


def set_session_records(records) -> None:
    """Serialize FileRecord objects into session-storable dicts."""
    session["scan_records"] = [
        {
            "filepath": str(r.filepath),
            "filename": r.filename,
            "extension": r.extension,
            "size_bytes": r.size_bytes,
            "sha256": r.sha256,
            "category": r.category,
            "confidence": r.confidence,
            "reason": r.reason,
            "status": r.status,
            "suggested_dest": r.suggested_dest,
            "extracted_text": r.extracted_text[:500] if r.extracted_text else "",
        }
        for r in records
    ]


def records_from_session() -> List[Any]:
    """Re-hydrate FileRecord objects from session dicts."""
    from src.scanner import FileRecord

    records = []
    for d in get_session_records():
        rec = FileRecord(
            filepath=Path(d["filepath"]),
            filename=d["filename"],
            extension=d["extension"],
            size_bytes=d["size_bytes"],
        )
        rec.sha256 = d.get("sha256", "")
        rec.category = d.get("category", "")
        rec.confidence = d.get("confidence", 0.0)
        rec.reason = d.get("reason", "")
        rec.status = d.get("status", "pending")
        rec.suggested_dest = d.get("suggested_dest", "")
        rec.extracted_text = d.get("extracted_text", "")
        records.append(rec)
    return records


# ---------------------------------------------------------------------------
# Context processor — inject common data into all templates
# ---------------------------------------------------------------------------

@app.context_processor
def inject_globals():
    from src.database import get_custom_categories
    conn = get_db()
    settings = load_settings(conn)
    custom_names = [c["name"] for c in get_custom_categories(conn)]
    all_categories = DEFAULT_CATEGORIES + [c for c in custom_names if c not in DEFAULT_CATEGORIES]
    return {
        "settings": settings,
        "categories": all_categories,
        "scan_done": session.get("scan_done", False),
        "scan_count": len(get_session_records()),
        "selected_folder": session.get("selected_folder", ""),
    }


# ===========================================================================
# PAGE ROUTES
# ===========================================================================

@app.route("/")
def dashboard():
    conn = get_db()
    from src.history import get_history_dataframe
    from src.classifier import model_status

    hist_df = get_history_dataframe(conn)
    records = records_from_session()

    # Stats
    n_total = len(records)
    n_organized = sum(1 for r in records if r.category and r.category != "Other")
    n_review = sum(1 for r in records if r.confidence < 0.55 and r.category)
    n_duplicates = 0  # computed via duplicate module if needed

    # Build recent operations list from DB
    recent_ops = []
    if not hist_df.empty:
        for _, row in hist_df.head(6).iterrows():
            recent_ops.append({
                "date": row.get("Date", ""),
                "folder": Path(row.get("Folder", "—")).name if row.get("Folder", "—") != "—" else "—",
                "folder_full": row.get("Folder", "—"),
                "files_processed": row.get("Moved", 0),
                "status": row.get("Status", ""),
                "batch_id": row.get("Batch ID", 0),
            })

    # All-time stats from DB
    total_scanned_alltime = int(hist_df["Total"].sum()) if not hist_df.empty and "Total" in hist_df.columns else 0
    total_organized_alltime = int(hist_df["Moved"].sum()) if not hist_df.empty and "Moved" in hist_df.columns else 0

    # Quick settings for sidebar widget
    settings = load_settings(conn)

    # Greeting
    from datetime import datetime
    hour = datetime.now().hour
    if hour < 12:
        greeting = "Good Morning! 👋"
    elif hour < 17:
        greeting = "Good Afternoon! 👋"
    else:
        greeting = "Good Evening! 👋"

    return render_template(
        "dashboard.html",
        page="dashboard",
        greeting=greeting,
        n_total=n_total,
        n_organized=n_organized,
        n_review=n_review,
        n_duplicates=n_duplicates,
        total_scanned_alltime=total_scanned_alltime,
        total_organized_alltime=total_organized_alltime,
        recent_ops=recent_ops,
        model_status=model_status(),
        settings=settings,
    )


@app.route("/scan")
def scan_page():
    conn = get_db()
    settings = load_settings(conn)
    return render_template(
        "scan.html",
        page="scan",
        settings=settings,
    )


@app.route("/preview")
def preview_page():
    conn = get_db()
    settings = load_settings(conn)
    records = records_from_session()
    overrides = session.get("category_overrides", {})

    if not records:
        return render_template(
            "preview.html",
            page="preview",
            records=[],
            settings=settings,
            overrides={},
            categories=DEFAULT_CATEGORIES,
        )

    # Build display rows
    rows = []
    for r in records:
        cat = overrides.get(str(r.filepath), r.category) or "Other"
        rows.append({
            "filepath": str(r.filepath),
            "filename": r.filename,
            "extension": r.extension,
            "size": fmt_size(r.size_bytes),
            "size_bytes": r.size_bytes,
            "category": cat,
            "original_category": r.category,
            "confidence": round(r.confidence * 100, 1),
            "reason": r.reason,
        })

    all_categories = sorted(set(r.category for r in records if r.category))
    all_extensions = sorted(set(r.extension for r in records if r.extension))

    return render_template(
        "preview.html",
        page="preview",
        records=rows,
        all_categories=all_categories,
        all_extensions=all_extensions,
        settings=settings,
        overrides=overrides,
        categories=DEFAULT_CATEGORIES,
        dest_folder=session.get("dest_folder", settings.get("default_dest_dir", "")),
    )


@app.route("/history")
def history_page():
    conn = get_db()
    from src.history import get_history_dataframe, get_undoable_dataframe

    hist_df = get_history_dataframe(conn)
    undo_df = get_undoable_dataframe(conn)

    # Collect batch IDs that are fully undone (all moved ops have undone=1)
    fully_undone_batches = set()
    rows_check = conn.execute(
        """SELECT batch_id
           FROM file_operations
           WHERE status = 'moved'
           GROUP BY batch_id
           HAVING COUNT(*) = SUM(undone)"""
    ).fetchall()
    for r in rows_check:
        fully_undone_batches.add(r["batch_id"])

    history_rows = []
    if not hist_df.empty:
        for _, row in hist_df.iterrows():
            batch_id = row.get("Batch ID", 0)
            if batch_id in fully_undone_batches:
                continue
            folder_name = Path(row.get("Folder", "—")).name if row.get("Folder", "—") != "—" else "—"
            status = row.get("Status", "")
            history_rows.append({
                "batch_id": batch_id,
                "date": row.get("Date", ""),
                "folder": folder_name,
                "folder_full": row.get("Folder", "—"),
                "files_affected": row.get("Moved", 0),
                "total": row.get("Total", 0),
                "status": status,
                "dry_run": row.get("Dry Run", "No") == "Yes",
            })

    undo_rows = []
    if not undo_df.empty:
        for _, row in undo_df.iterrows():
            undo_rows.append({
                "op_id": row.get("Op ID", 0),
                "filename": row.get("Filename", ""),
                "moved_from": row.get("Moved From", ""),
                "moved_to": row.get("Moved To", ""),
                "executed": row.get("Executed", ""),
            })

    return render_template(
        "history.html",
        page="history",
        history_rows=history_rows,
        undo_rows=undo_rows,
        total_items=len(history_rows),
    )


@app.route("/settings")
def settings_page():
    conn = get_db()
    settings = load_settings(conn)

    # Parse max_file_size_mb — could be "unlimited" or a number
    max_size_raw = settings.get("max_file_size_mb", "50")
    if max_size_raw == "unlimited":
        max_size_val = None  # represents unlimited
        max_size_display = "Unlimited"
    else:
        try:
            max_size_val = float(max_size_raw)
            max_size_display = str(int(max_size_val)) + " MB"
        except ValueError:
            max_size_val = 50.0
            max_size_display = "50 MB"

    return render_template(
        "settings.html",
        page="settings",
        settings=settings,
        max_size_val=max_size_val,
        max_size_display=max_size_display,
    )


# ===========================================================================
# API ROUTES
# ===========================================================================

@app.route("/api/scan", methods=["POST"])
def api_scan():
    """Start a folder scan + classify. Returns JSON with results."""
    from src.security import validate_scan_root
    from src.scanner import Scanner
    from src.classifier import classify_batch
    from src.database import create_scan_session, finish_scan_session, insert_scanned_file

    data = request.get_json() or {}
    folder_str = data.get("folder", "").strip()
    recursive = data.get("recursive", True)
    excl_ext_str = data.get("excluded_extensions", "")
    excl_paths_str = data.get("excluded_subfolders", "")
    max_size_raw = data.get("max_size", 500)

    # Handle unlimited
    if max_size_raw is None or max_size_raw == "unlimited":
        max_size_mb = float("inf")
    else:
        try:
            max_size_mb = float(max_size_raw)
        except (TypeError, ValueError):
            max_size_mb = 500.0

    if not folder_str:
        return jsonify({"error": "No folder path provided."}), 400

    root_path, err = validate_scan_root(folder_str)
    if err:
        return jsonify({"error": err}), 400

    excl_exts = [e.strip() for e in excl_ext_str.split(",") if e.strip()]
    excl_paths = [p.strip() for p in excl_paths_str.split(",") if p.strip()]

    conn = get_db()
    settings = load_settings(conn)

    conf_threshold = float(settings.get("confidence_threshold", "0.55"))
    ocr_enabled = settings.get("ocr_enabled", "false") == "true"

    try:
        scanner = Scanner(
            root=root_path,
            recursive=recursive,
            excluded_paths=excl_paths,
            excluded_extensions=excl_exts,
            max_file_size_mb=max_size_mb if max_size_mb != float("inf") else 999999,
        )
        records = scanner.scan()
    except Exception as exc:
        logger.error("Scan failed: %s", exc)
        return jsonify({"error": f"Scan failed: {exc}"}), 500

    if not records:
        return jsonify({"error": "No files found in the selected folder."}), 404

    # Classify
    try:
        classify_batch(
            records,
            confidence_threshold=conf_threshold,
            max_file_size_mb=max_size_mb if max_size_mb != float("inf") else 999999,
            ocr_enabled=ocr_enabled,
        )
    except Exception as exc:
        logger.error("Classification failed: %s", exc)

    # Persist to DB
    session_id = create_scan_session(conn, str(root_path))
    for rec in records:
        insert_scanned_file(conn, {
            "session_id": session_id,
            "filepath": str(rec.filepath),
            "filename": rec.filename,
            "extension": rec.extension,
            "size_bytes": rec.size_bytes,
            "sha256": rec.sha256,
            "category": rec.category,
            "confidence": rec.confidence,
            "reason": rec.reason,
            "status": "pending",
            "suggested_dest": rec.suggested_dest,
        })
    finish_scan_session(conn, session_id, len(records))

    # Store in session
    set_session_records(records)
    session["scan_done"] = True
    session["scan_session_id"] = session_id
    session["selected_folder"] = str(root_path)
    session["category_overrides"] = {}

    # Build summary
    cat_counts = {}
    for r in records:
        cat_counts[r.category or "Unknown"] = cat_counts.get(r.category or "Unknown", 0) + 1

    return jsonify({
        "success": True,
        "total": len(records),
        "session_id": session_id,
        "folder": str(root_path),
        "category_counts": cat_counts,
        "needs_review": sum(1 for r in records if r.confidence < conf_threshold and r.category),
    })


@app.route("/api/organize", methods=["POST"])
def api_organize():
    """Generate and optionally execute an organization plan."""
    from src.organizer import generate_plan, execute_plan
    from src.security import validate_destination

    data = request.get_json() or {}
    dest_str = data.get("dest_folder", "").strip()
    dry_run = data.get("dry_run", False)
    selected_filepaths = data.get("selected", None)  # None = all
    execute = data.get("execute", False)

    records = records_from_session()
    if not records:
        return jsonify({"error": "No scan results. Please scan a folder first."}), 400

    if not dest_str:
        return jsonify({"error": "No destination folder provided."}), 400

    source_root_str = session.get("selected_folder", "")
    if not source_root_str:
        return jsonify({"error": "Source folder not set. Please rescan."}), 400

    source_root = Path(source_root_str)
    _, err = validate_destination(dest_str, source_root)
    if err:
        return jsonify({"error": err}), 400

    dest_root = Path(dest_str)
    overrides = session.get("category_overrides", {})

    # Filter to selected files
    if selected_filepaths is not None:
        selected_set = set(selected_filepaths)
        records = [r for r in records if str(r.filepath) in selected_set]

    conn = get_db()
    session_id = session.get("scan_session_id")

    # Load custom extension rules so they take effect for this organize run
    from src.database import get_custom_ext_map
    custom_ext_map = get_custom_ext_map(conn)

    try:
        proposals = generate_plan(records, dest_root, source_root,
                                  overrides, custom_ext_map)
    except Exception as exc:
        return jsonify({"error": f"Plan generation failed: {exc}"}), 500

    plan_data = [
        {
            "filename": p.record.filename,
            "category": p.record.category,
            "src": str(p.src_path),
            "dst": str(p.dst_path),
            "conflict": p.conflict,
            "conflict_reason": p.conflict_reason,
        }
        for p in proposals
    ]

    if not execute:
        return jsonify({"success": True, "plan": plan_data, "total": len(plan_data)})

    # Execute
    try:
        result = execute_plan(proposals, conn, session_id, dry_run=dry_run)
    except Exception as exc:
        return jsonify({"error": f"Execute failed: {exc}"}), 500

    session["dest_folder"] = dest_str

    return jsonify({
        "success": True,
        "batch_id": result.batch_id,
        "total": result.total,
        "moved": result.moved,
        "skipped": result.skipped,
        "failed": result.failed,
        "dry_run": dry_run,
        "details": result.details,
        "plan": plan_data,
    })


@app.route("/api/correction", methods=["POST"])
def api_correction():
    """Save a category correction for a file."""
    from src.database import save_feedback

    data = request.get_json() or {}
    filepath = data.get("filepath", "")
    correct_category = data.get("category", "")

    if not filepath or not correct_category:
        return jsonify({"error": "filepath and category are required."}), 400

    if correct_category not in DEFAULT_CATEGORIES:
        return jsonify({"error": f"Unknown category: {correct_category}"}), 400

    # Update session override
    overrides = session.get("category_overrides", {})
    overrides[filepath] = correct_category
    session["category_overrides"] = overrides

    # Save to DB for retraining
    records = records_from_session()
    matched = [r for r in records if str(r.filepath) == filepath]
    extracted_text = matched[0].extracted_text if matched else ""

    conn = get_db()
    filename = Path(filepath).name
    save_feedback(conn, filepath, filename, correct_category, extracted_text)

    return jsonify({"success": True, "filepath": filepath, "category": correct_category})


@app.route("/api/undo", methods=["POST"])
def api_undo():
    """Undo a file operation."""
    from src.organizer import undo_operation

    data = request.get_json() or {}
    op_id = data.get("op_id")
    alt_dest = data.get("alternative_dest", "")

    if not op_id:
        return jsonify({"error": "op_id is required."}), 400

    conn = get_db()
    success, msg = undo_operation(conn, int(op_id), alt_dest.strip() or None)

    if success:
        return jsonify({"success": True, "message": msg})
    else:
        return jsonify({"error": msg}), 400


@app.route("/api/settings", methods=["POST"])
def api_save_settings():
    """Save application settings."""
    data = request.get_json() or {}
    conn = get_db()

    allowed_keys = {
        "default_dest_dir", "recursive_scan", "excluded_extensions",
        "excluded_paths", "confidence_threshold", "ocr_enabled",
        "dry_run", "theme", "max_file_size_mb",
    }

    for key, value in data.items():
        if key in allowed_keys:
            # Special handling for max_file_size_mb — allow "unlimited"
            if key == "max_file_size_mb":
                if value is None or str(value).lower() == "unlimited":
                    save_setting(conn, key, "unlimited")
                else:
                    try:
                        save_setting(conn, key, str(float(value)))
                    except (TypeError, ValueError):
                        save_setting(conn, key, "unlimited")
            else:
                save_setting(conn, key, str(value))

    # Update session dest folder
    if "default_dest_dir" in data:
        session["dest_folder"] = data["default_dest_dir"]

    return jsonify({"success": True})


@app.route("/api/retrain", methods=["POST"])
def api_retrain():
    """Retrain the ML model using feedback."""
    from src.trainer import retrain_from_feedback
    from src.classifier import reload_model

    conn = get_db()
    try:
        result = retrain_from_feedback(conn)
        if result.get("skipped"):
            return jsonify({"success": False, "message": result.get("reason", "No usable feedback.")}), 200
        reload_model()
        return jsonify({
            "success": True,
            "accuracy": result["accuracy"],
            "message": f"Model retrained. Accuracy: {result['accuracy']:.1%}",
        })
    except Exception as exc:
        logger.error("Retrain failed: %s", exc)
        return jsonify({"error": f"Retraining failed: {exc}"}), 500


@app.route("/api/clear_history", methods=["POST"])
def api_clear_history():
    """Clear operation history from the database."""
    conn = get_db()
    try:
        conn.execute("DELETE FROM file_operations")
        conn.execute("DELETE FROM operation_batches")
        # Reset autoincrement counters so IDs restart from 1
        conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('file_operations', 'operation_batches')")
        conn.commit()
        return jsonify({"success": True, "message": "History cleared."})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/history/<int:batch_id>", methods=["GET"])
def api_batch_detail(batch_id: int):
    """Get details for a specific operation batch."""
    from src.history import get_batch_ops_dataframe

    conn = get_db()
    df = get_batch_ops_dataframe(conn, batch_id)
    if df.empty:
        return jsonify({"ops": []})

    ops = []
    for _, row in df.iterrows():
        ops.append({
            "op_id": row.get("Op ID"),
            "filename": row.get("Filename", ""),
            "category": row.get("Category", ""),
            "from": row.get("From", ""),
            "to": row.get("To", ""),
            "status": row.get("Status", ""),
            "executed": row.get("Executed", ""),
            "undone": bool(row.get("Undone", False)),
        })
    return jsonify({"ops": ops})


@app.route("/api/search", methods=["GET"])
def api_search():
    """Search files, folders, or categories."""
    query = request.args.get("q", "").strip().lower()
    if not query:
        return jsonify({"results": []})

    records = records_from_session()
    results = []
    for r in records:
        if (query in r.filename.lower() or
                query in (r.category or "").lower() or
                query in r.extension.lower()):
            results.append({
                "filename": r.filename,
                "category": r.category,
                "extension": r.extension,
                "size": fmt_size(r.size_bytes),
                "filepath": str(r.filepath),
            })
        if len(results) >= 20:
            break

    return jsonify({"results": results})


@app.route("/api/status", methods=["GET"])
def api_status():
    """Return system status information."""
    from src.classifier import model_status
    from src.extractors import tesseract_status

    conn = get_db()
    settings = load_settings(conn)

    return jsonify({
        "model_status": model_status(),
        "tesseract_status": tesseract_status(),
        "ocr_enabled": settings.get("ocr_enabled", "false") == "true",
        "scan_done": session.get("scan_done", False),
        "scan_count": len(get_session_records()),
    })


@app.route("/api/browse_folder", methods=["POST"])
def api_browse_folder():
    """
    Open a native OS folder-picker dialog and return the selected path.
    Uses tkinter (stdlib) — runs on the server side.
    Falls back gracefully if a display is not available.
    """
    try:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()          # hide the empty root window
        root.wm_attributes("-topmost", True)  # bring dialog to front
        folder = filedialog.askdirectory(title="Select Folder")
        root.destroy()

        if folder:
            return jsonify({"path": folder})
        return jsonify({"path": ""})
    except Exception as exc:
        logger.warning("Folder dialog failed: %s", exc)
        return jsonify({"error": str(exc)}), 500


# ===========================================================================
# Custom-category API
# ===========================================================================

@app.route("/api/categories", methods=["GET"])
def api_list_categories():
    """Return all custom categories with their mapped extensions."""
    from src.database import get_custom_categories
    conn = get_db()
    cats = get_custom_categories(conn)
    return jsonify({"categories": cats})


@app.route("/api/categories", methods=["POST"])
def api_add_category():
    """Create a custom category.  Body: {name, color?}"""
    import sqlite3 as _sqlite3
    from src.database import add_custom_category
    from src.config import sanitize_category_name

    data = request.get_json() or {}
    raw  = data.get("name", "").strip()
    color = data.get("color", "#6366f1").strip()

    name = sanitize_category_name(raw)
    if not name:
        return jsonify({"error": "Category name is required."}), 400
    if name in DEFAULT_CATEGORIES:
        return jsonify({"error": f"'{name}' is already a built-in category."}), 409

    conn = get_db()
    try:
        new_id = add_custom_category(conn, name, color)
    except _sqlite3.IntegrityError:
        return jsonify({"error": f"Category '{name}' already exists."}), 409

    return jsonify({"success": True, "id": new_id, "name": name, "color": color})


@app.route("/api/categories/<string:name>", methods=["PUT"])
def api_update_category(name: str):
    """Update a custom category's name, color, and/or extensions.

    Body: {new_name?, color?, extensions?: [".ext", ...]}
    """
    import sqlite3 as _sqlite3
    from src.database import (rename_custom_category, delete_custom_category,
                               add_custom_category, set_extensions_for_category,
                               get_custom_categories)
    from src.config import sanitize_category_name

    data = request.get_json() or {}
    conn = get_db()

    # Rename if requested
    new_name = data.get("new_name", "").strip()
    final_name = name
    if new_name:
        new_name = sanitize_category_name(new_name)
        if new_name != name:
            if new_name in DEFAULT_CATEGORIES:
                return jsonify({"error": f"'{new_name}' is a built-in category."}), 409
            ok = rename_custom_category(conn, name, new_name)
            if not ok:
                return jsonify({"error": f"Category '{name}' not found."}), 404
            final_name = new_name

    # Update color if provided
    if "color" in data:
        conn.execute(
            "UPDATE custom_categories SET color=? WHERE name=?",
            (data["color"], final_name),
        )
        conn.commit()

    # Replace extension list if provided
    if "extensions" in data:
        set_extensions_for_category(conn, final_name, data["extensions"])

    cats = get_custom_categories(conn)
    updated = next((c for c in cats if c["name"] == final_name), None)
    return jsonify({"success": True, "category": updated})


@app.route("/api/categories/<string:name>", methods=["DELETE"])
def api_delete_category(name: str):
    """Delete a custom category and all its extension mappings."""
    from src.database import delete_custom_category

    if name in DEFAULT_CATEGORIES:
        return jsonify({"error": "Cannot delete a built-in category."}), 403

    conn = get_db()
    ok = delete_custom_category(conn, name)
    if not ok:
        return jsonify({"error": f"Category '{name}' not found."}), 404
    return jsonify({"success": True, "deleted": name})


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    logger.info("Starting SmartSort AI Flask app")
    app.run(debug=True, host="127.0.0.1", port=5000)
