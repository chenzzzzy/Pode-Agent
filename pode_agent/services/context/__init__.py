"""Project context gathering and caching.

Collects project-level context (git status, directory structure, README,
project docs, instruction files, code style) and injects it into the
system prompt so the LLM has awareness of the current project.

Modeled after Kode-Agent ``src/context/index.ts``.

All top-level getters are memoized (cached until explicitly cleared).
Call ``clear_context_cache()`` after compaction, session reset, or
directory change.
"""

from pode_agent.services.context.gatherer import (
    clear_context_cache,
    get_context,
    get_directory_structure,
    get_git_status,
    get_instruction_files_note,
    get_project_docs,
    get_readme,
)

__all__ = [
    "clear_context_cache",
    "get_context",
    "get_directory_structure",
    "get_git_status",
    "get_instruction_files_note",
    "get_project_docs",
    "get_readme",
]
