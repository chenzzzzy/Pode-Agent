"""Context gathering functions with memoization.

Each getter is cached via a simple ``_cache`` dict keyed by function name.
``clear_context_cache()`` resets all caches in one call.

Reference: Kode-Agent ``src/context/index.ts``
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Memoization helpers
# ---------------------------------------------------------------------------

_cache: dict[str, Any] = {}


def _get_cached(key: str) -> Any | None:
    return _cache.get(key)


def _set_cached(key: str, value: Any) -> None:
    _cache[key] = value


def clear_context_cache() -> None:
    """Clear all memoized context caches.

    Call after compaction, session reset, or cwd change.
    """
    _cache.clear()
    logger.debug("Context cache cleared")


# ---------------------------------------------------------------------------
# CWD helpers
# ---------------------------------------------------------------------------


def _get_cwd() -> str:
    return os.getcwd()


# ---------------------------------------------------------------------------
# Git status
# ---------------------------------------------------------------------------


async def get_git_status(cwd: str | None = None) -> str | None:
    """Gather a snapshot of git status, branch, and recent commits.

    Returns ``None`` if not in a git repo or on error.
    """
    cache_key = "git_status"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    work_dir = cwd or _get_cwd()

    # Quick check: is this a git repo?
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "rev-parse", "--is-inside-work-tree",
            cwd=work_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        if proc.returncode != 0 or b"true" not in out:
            _set_cached(cache_key, None)
            return None
    except Exception:
        _set_cached(cache_key, None)
        return None

    async def _run_git(*args: str) -> str:
        try:
            p = await asyncio.create_subprocess_exec(
                "git", *args,
                cwd=work_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, _ = await asyncio.wait_for(p.communicate(), timeout=10)
            return out.decode(errors="replace").strip()
        except Exception:
            return ""

    branch, main_branch, status, log_lines, author_log = await asyncio.gather(
        _run_git("branch", "--show-current"),
        _run_git("rev-parse", "--abbrev-ref", "origin/HEAD"),
        _run_git("status", "--short"),
        _run_git("log", "--oneline", "-n", "5"),
        _run_git("log", "--oneline", "-n", "5", "--author",
                 await _run_git("config", "user.email") or "unknown"),
    )

    main_branch = main_branch.replace("origin/", "").strip()

    # Truncate large status output
    status_lines = status.split("\n")
    if len(status_lines) > 200:
        status = "\n".join(status_lines[:200]) + (
            "\n... (truncated; run 'git status' for full output)"
        )

    result = (
        "This is the git status at the start of the conversation. "
        "Note that this status is a snapshot in time, and will not update "
        "during the conversation.\n"
        f"Current branch: {branch}\n\n"
        f"Main branch (you will usually use this for PRs): {main_branch}\n\n"
        f"Status:\n{status or '(clean)'}\n\n"
        f"Recent commits:\n{log_lines}\n\n"
        f"Your recent commits:\n{author_log or '(no recent commits)'}"
    )
    _set_cached(cache_key, result)
    return result


# ---------------------------------------------------------------------------
# Directory structure
# ---------------------------------------------------------------------------


async def get_directory_structure(cwd: str | None = None) -> str | None:
    """Return a shallow directory listing (1 level) of the project root."""
    cache_key = "directory_structure"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    work_dir = Path(cwd or _get_cwd())
    try:
        entries = sorted(work_dir.iterdir())
        lines: list[str] = []
        for entry in entries:
            if entry.name.startswith("."):
                continue
            kind = "d" if entry.is_dir() else "f"
            lines.append(f"{kind} {entry.name}")
        listing = "\n".join(lines)
    except Exception as exc:
        logger.debug("Failed to list directory: %s", exc)
        _set_cached(cache_key, None)
        return None

    result = (
        "Below is a snapshot of this project's file structure at the start "
        "of the conversation. This snapshot will NOT update during the conversation.\n\n"
        + listing
    )
    _set_cached(cache_key, result)
    return result


# ---------------------------------------------------------------------------
# README
# ---------------------------------------------------------------------------


async def get_readme(cwd: str | None = None) -> str | None:
    """Read the project's README.md (if present)."""
    cache_key = "readme"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    work_dir = Path(cwd or _get_cwd())
    readme_path = work_dir / "README.md"
    if not readme_path.exists():
        _set_cached(cache_key, None)
        return None

    try:
        content = readme_path.read_text(encoding="utf-8", errors="replace")
        _set_cached(cache_key, content)
        return content
    except Exception as exc:
        logger.debug("Failed to read README.md: %s", exc)
        _set_cached(cache_key, None)
        return None


# ---------------------------------------------------------------------------
# Project docs / instruction files (AGENTS.md, CLAUDE.md, .pode-instructions)
# ---------------------------------------------------------------------------

_INSTRUCTION_FILENAMES = [
    "AGENTS.md",
    "CLAUDE.md",
    ".pode-instructions",
    ".pode-instructions.md",
]


async def get_project_docs(cwd: str | None = None) -> str | None:
    """Read project instruction files (AGENTS.md, CLAUDE.md, etc.)."""
    cache_key = "project_docs"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    work_dir = Path(cwd or _get_cwd())
    docs: list[str] = []
    for filename in _INSTRUCTION_FILENAMES:
        fpath = work_dir / filename
        if fpath.exists():
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
                docs.append(f"# {filename}\n\n{content}")
            except Exception:
                pass

    result = "\n\n---\n\n".join(docs) if docs else None
    _set_cached(cache_key, result)
    return result


async def get_instruction_files_note(cwd: str | None = None) -> str | None:
    """Return a note listing discovered instruction files."""
    cache_key = "instruction_files_note"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    work_dir = Path(cwd or _get_cwd())
    found: list[str] = []
    for filename in _INSTRUCTION_FILENAMES:
        if (work_dir / filename).exists():
            found.append(str(work_dir / filename))

    if not found:
        _set_cached(cache_key, None)
        return None

    note = (
        "NOTE: Additional project instruction files were found. "
        "When working in these directories, make sure to read and "
        "follow the instructions in the corresponding files:\n"
        + "\n".join(f"- {p}" for p in found)
    )
    _set_cached(cache_key, note)
    return note


# ---------------------------------------------------------------------------
# Aggregated context
# ---------------------------------------------------------------------------


async def get_context(cwd: str | None = None) -> dict[str, str]:
    """Gather all project context into a single dict.

    Keys are context names that map to XML ``<context name="...">`` tags
    in the system prompt.

    Also merges any ``context`` entries from the project config.
    """
    cache_key = "full_context"
    cached = _get_cached(cache_key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    work_dir = cwd or _get_cwd()

    # Load project config context (user-defined key-value pairs)
    project_context: dict[str, str] = {}
    try:
        from pode_agent.core.config.loader import get_current_project_config
        proj = get_current_project_config()
        project_context = dict(proj.context)
    except Exception:
        pass

    git_status, dir_struct, readme, project_docs, instruction_note = (
        await asyncio.gather(
            get_git_status(work_dir),
            get_directory_structure(work_dir),
            get_readme(work_dir),
            get_project_docs(work_dir),
            get_instruction_files_note(work_dir),
        )
    )

    result: dict[str, str] = {**project_context}
    if git_status:
        result["gitStatus"] = git_status
    if dir_struct:
        result["directoryStructure"] = dir_struct
    if readme:
        result["readme"] = readme
    if project_docs:
        result["projectDocs"] = project_docs
    if instruction_note:
        result["instructionFilesNote"] = instruction_note

    _set_cached(cache_key, result)
    return result
