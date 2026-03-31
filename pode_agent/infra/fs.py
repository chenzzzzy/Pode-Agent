"""File system utility functions.

Provides safe, atomic file operations for config persistence and
session logging.

Reference: docs/modules.md — Infrastructure Layer
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from pode_agent.infra.logging import get_logger

logger = get_logger(__name__)


def ensure_dir(path: Path) -> None:
    """Create directory and all parents. No-op if already exists."""
    path.mkdir(parents=True, exist_ok=True)


def atomic_write(path: Path, content: str, encoding: str = "utf-8") -> None:
    """Atomically write content to a file.

    Writes to a temporary file in the same directory first, then
    replaces the target file via ``os.replace()``.
    """
    ensure_dir(path.parent)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=".tmp_",
        suffix=path.suffix,
    )
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(content)
        os.replace(tmp_path, str(path))
    except BaseException:
        # Clean up temp file on failure
        import contextlib

        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


def read_file_safe(path: Path, encoding: str = "utf-8") -> str | None:
    """Read a file, returning None if it doesn't exist or can't be read."""
    try:
        return path.read_text(encoding=encoding)
    except (FileNotFoundError, PermissionError, UnicodeDecodeError) as e:
        logger.debug("read_file_safe failed", extra={"path": str(path), "error": str(e)})
        return None


def expand_home(path: str | Path) -> Path:
    """Expand ``~`` in a path and resolve to absolute."""
    return Path(os.path.expanduser(str(path))).resolve()
