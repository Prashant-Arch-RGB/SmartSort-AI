"""
src/duplicates.py — Duplicate file detection utilities.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from src.scanner import FileRecord


def find_duplicates(records: List[FileRecord]) -> Dict[str, List[FileRecord]]:
    """
    Group FileRecord objects by their SHA-256 hash.

    Returns a dict of {sha256: [record, ...]} for hashes that appear
    more than once.  Records without a hash are excluded.
    """
    groups: Dict[str, List[FileRecord]] = defaultdict(list)
    for rec in records:
        if rec.sha256:
            groups[rec.sha256].append(rec)

    return {sha: recs for sha, recs in groups.items() if len(recs) > 1}


def duplicate_count(records: List[FileRecord]) -> int:
    """Return the number of *extra* duplicate files (originals not counted)."""
    total = 0
    for recs in find_duplicates(records).values():
        total += len(recs) - 1
    return total
