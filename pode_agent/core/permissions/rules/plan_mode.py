"""Plan mode permission rules.

When plan mode is active, only read-only tools and a small set of
management tools are allowed. Write tools (file_edit, file_write, etc.)
are blocked.

Reference: docs/api-specs.md — Permissions API, Plan mode
"""

from __future__ import annotations

# Tools permitted in plan mode.  All read-only tools are implicitly
# allowed by the engine (via ``tool.is_read_only()``); this set covers
# the write-capable tools that are nonetheless safe in plan mode.
PLAN_MODE_ALLOWED_TOOLS: frozenset[str] = frozenset([
    "file_read",
    "glob",
    "grep",
    "ls",
    "bash",
    "todo_write",
    "exit_plan_mode",
    "kill_shell",
])
