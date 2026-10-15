"""
security.py — Path validation and safe-path enforcement.

All path operations must pass through these checks before touching the filesystem.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Tuple


# ---------------------------------------------------------------------------
# Safe-path validation
# ---------------------------------------------------------------------------

def resolve_safe(path_str: str) -> Tuple[Optional[Path], str]:
    """
    Resolve a user-supplied path string to a real, absolute Path.

    Returns (Path, "") on success or (None, error_message) on failure.
    - Symlinks are NOT followed (uses Path.resolve() only on existing paths).
    - Paths containing null bytes or other control characters are rejected.
    """
    if not path_str or not path_str.strip():
        return None, "Path is empty."

    # Reject null bytes and control chars
    if any(ord(c) < 32 for c in path_str):
        return None, "Path contains invalid control characters."

    try:
        p = Path(path_str.strip())
        # Make absolute without resolving symlinks
        if not p.is_absolute():
            return None, f"Path must be absolute. Got: {path_str!r}"
        return p, ""
    except Exception as exc:
        return None, f"Cannot parse path: {exc}"


def validate_scan_root(path_str: str) -> Tuple[Optional[Path], str]:
    """
    Validate a directory that the user wants to scan.

    Returns (Path, "") or (None, error).
    """
    p, err = resolve_safe(path_str)
    if err:
        return None, err

    assert p is not None
    if not p.exists():
        return None, f"Directory does not exist: {p}"
    if not p.is_dir():
        return None, f"Path is not a directory: {p}"
    if p.is_symlink():
        return None, f"Path is a symlink — please select the real directory: {p}"
    try:
        # Check we can list the directory
        next(p.iterdir())
    except StopIteration:
        pass  # Empty directory is fine
    except PermissionError:
        return None, f"Permission denied reading directory: {p}"
    return p, ""


def validate_destination(dest_str: str, source_root: Path) -> Tuple[Optional[Path], str]:
    """
    Validate a destination directory for file moves.

    - Must be absolute.
    - Must not be exactly the source root.
    - Must not be a symlink.
    """
    p, err = resolve_safe(dest_str)
    if err:
        return None, err

    assert p is not None

    # Prevent destination being exactly the source root (would organize in place)
    try:
        if p == source_root:
            return None, (
                f"Destination cannot be the same as the source directory {source_root}."
            )
    except Exception:
        pass

    if p.is_symlink():
        return None, f"Destination is a symlink: {p}"

    return p, ""


def is_safe_file(file_path: Path) -> bool:
    """
    Return True if a file is safe to process (not a symlink, not a special device).
    """
    if file_path.is_symlink():
        return False
    if not file_path.is_file():
        return False
    return True


def contains_path_traversal(path_str: str) -> bool:
    """Detect obvious path-traversal attempts like '..' segments."""
    p = Path(path_str)
    for part in p.parts:
        if part in ("..", "."):
            return True
    return False
