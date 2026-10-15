"""
src/scanner.py — Directory scanner and FileRecord dataclass.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class FileRecord:
    """Represents a single file discovered during a scan."""
    filepath: Path
    filename: str
    extension: str
    size_bytes: int

    # Set by classifier
    sha256: str = ""
    category: str = ""
    confidence: float = 0.0
    reason: str = ""
    status: str = "pending"          # pending | organized | skipped | failed
    suggested_dest: str = ""
    extracted_text: str = ""


def _compute_sha256(path: Path, chunk: int = 65536) -> str:
    """Return hex SHA-256 of file contents; return '' on read error."""
    h = hashlib.sha256()
    try:
        with path.open("rb") as f:
            while True:
                data = f.read(chunk)
                if not data:
                    break
                h.update(data)
        return h.hexdigest()
    except OSError:
        return ""


class Scanner:
    """
    Recursively (or shallowly) scan a directory and return FileRecord objects.

    Parameters
    ----------
    root : Path
        Directory to scan.
    recursive : bool
        Whether to descend into subdirectories.
    excluded_paths : list[str]
        Subdirectory names / path fragments to skip.
    excluded_extensions : list[str]
        File extensions (with dot) to skip, e.g. [".tmp", ".log"].
    max_file_size_mb : float
        Files larger than this are still *listed* but text extraction will
        skip them (the extractor enforces the limit).  Pass float("inf") or
        a very large number for unlimited.
    compute_hash : bool
        Whether to compute SHA-256 hashes (used for duplicate detection).
    """

    def __init__(
        self,
        root: Path,
        recursive: bool = True,
        excluded_paths: Optional[List[str]] = None,
        excluded_extensions: Optional[List[str]] = None,
        max_file_size_mb: float = 500.0,
        compute_hash: bool = True,
    ) -> None:
        self.root = root
        self.recursive = recursive
        self.excluded_paths = [p.lower() for p in (excluded_paths or [])]
        self.excluded_extensions = {e.lower() for e in (excluded_extensions or [])}
        self.max_file_size_mb = max_file_size_mb
        self.compute_hash = compute_hash

    def _is_excluded_dir(self, path: Path) -> bool:
        """Return True if any part of the directory path matches exclusions."""
        for part in path.parts:
            if part.lower() in self.excluded_paths:
                return True
        return False

    def scan(self) -> List[FileRecord]:
        """Walk the root directory and return a list of FileRecord objects."""
        records: List[FileRecord] = []

        if self.recursive:
            iterator = self.root.rglob("*")
        else:
            iterator = self.root.glob("*")

        for path in iterator:
            if not path.is_file():
                continue
            if path.is_symlink():
                continue

            # Skip excluded directories
            if self._is_excluded_dir(path.parent):
                continue

            ext = path.suffix.lower()
            if ext in self.excluded_extensions:
                continue

            try:
                size = path.stat().st_size
            except OSError:
                continue

            sha = _compute_sha256(path) if self.compute_hash else ""

            records.append(
                FileRecord(
                    filepath=path,
                    filename=path.name,
                    extension=ext,
                    size_bytes=size,
                    sha256=sha,
                )
            )

        return records
