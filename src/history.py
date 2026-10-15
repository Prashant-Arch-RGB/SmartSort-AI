"""
src/history.py — History query helpers that return pandas DataFrames.
"""

from __future__ import annotations

import pandas as pd


def get_history_dataframe(conn) -> pd.DataFrame:
    """
    Return a summary DataFrame of operation batches, one row per batch.

    Columns: Batch ID, Date, Folder, Total, Moved, Skipped, Failed,
             Dry Run, Status
    """
    rows = conn.execute(
        """SELECT id, executed_at, source_root, dest_root,
                  total, moved, skipped, failed, dry_run
           FROM operation_batches
           ORDER BY id DESC"""
    ).fetchall()

    if not rows:
        return pd.DataFrame()

    records = []
    for r in rows:
        dry_label = "Yes" if r["dry_run"] else "No"
        if r["failed"] > 0:
            status = "partial"
        elif r["moved"] == 0 and r["total"] > 0:
            status = "skipped"
        else:
            status = "success"

        records.append({
            "Batch ID": r["id"],
            "Date": r["executed_at"],
            "Folder": r["source_root"],
            "Dest": r["dest_root"],
            "Total": r["total"],
            "Moved": r["moved"],
            "Skipped": r["skipped"],
            "Failed": r["failed"],
            "Dry Run": dry_label,
            "Status": status,
        })

    return pd.DataFrame(records)


def get_undoable_dataframe(conn) -> pd.DataFrame:
    """
    Return a DataFrame of individual file operations that can be undone
    (status='moved', undone=0).

    Columns: Op ID, Filename, Moved From, Moved To, Executed
    """
    rows = conn.execute(
        """SELECT fo.id, fo.filename, fo.filepath_src, fo.filepath_dst,
                  fo.executed_at
           FROM file_operations fo
           WHERE fo.status='moved' AND fo.undone=0
           ORDER BY fo.id DESC
           LIMIT 500"""
    ).fetchall()

    if not rows:
        return pd.DataFrame()

    records = [
        {
            "Op ID": r["id"],
            "Filename": r["filename"],
            "Moved From": r["filepath_src"],
            "Moved To": r["filepath_dst"],
            "Executed": r["executed_at"],
        }
        for r in rows
    ]
    return pd.DataFrame(records)


def get_batch_ops_dataframe(conn, batch_id: int) -> pd.DataFrame:
    """
    Return all file operations for a specific batch.

    Columns: Op ID, Filename, Category, From, To, Status, Executed, Undone
    """
    rows = conn.execute(
        """SELECT id, filename, category, filepath_src, filepath_dst,
                  status, executed_at, undone
           FROM file_operations
           WHERE batch_id=?
           ORDER BY id""",
        (batch_id,),
    ).fetchall()

    if not rows:
        return pd.DataFrame()

    records = [
        {
            "Op ID": r["id"],
            "Filename": r["filename"],
            "Category": r["category"],
            "From": r["filepath_src"],
            "To": r["filepath_dst"],
            "Status": r["status"],
            "Executed": r["executed_at"],
            "Undone": bool(r["undone"]),
        }
        for r in rows
    ]
    return pd.DataFrame(records)
