"""File path safety rules.

Checks whether a file path is within the allowed working directories,
preventing path-traversal attacks (e.g. ``../../etc/passwd``).

Reference: docs/api-specs.md — Permissions API, File path safety
"""

from __future__ import annotations

import os
from pathlib import Path


def is_path_in_working_directories(
    path: str,
    working_directories: list[str] | None = None,
) -> bool:
    """Return True if *path* resolves to a location inside a working directory.

    Args:
        path: The file path to check (may be relative or absolute).
        working_directories: List of allowed root directories.
            Defaults to ``[os.getcwd()]`` if not provided.

    The check uses :meth:`pathlib.Path.resolve` so symlinks and ``..``
    components are resolved before comparison.
    """
    if working_directories is None:
        working_directories = [os.getcwd()]

    target = Path(path).resolve()
    for wd in working_directories:
        wd_resolved = Path(wd).resolve()
        try:
            target.relative_to(wd_resolved)
            return True
        except ValueError:
            continue
    return False
