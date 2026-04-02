"""Permission persistence: save approved/denied tools to project config.

Reference: docs/api-specs.md — Permissions API, Permission store
"""

from __future__ import annotations

from pode_agent.core.config.loader import (
    get_current_project_config,
    save_current_project_config,
)
from pode_agent.core.permissions.types import (
    PermissionDecision,
    ToolPermissionContext,
)


def apply_context_update(
    context: ToolPermissionContext,
    tool_name: str,
    decision: PermissionDecision,
) -> ToolPermissionContext:
    """Return a new :class:`ToolPermissionContext` reflecting *decision*.

    Immutable — the original context is not modified.
    """
    approved = set(context.approved_tools)
    rejected = set(context.rejected_tools)

    if decision == PermissionDecision.ALLOW_ONCE:
        # ALLOW_ONCE is not persisted — only in-session memory.
        approved.add(tool_name)
    elif decision == PermissionDecision.ALLOW_SESSION:
        approved.add(tool_name)
    elif decision == PermissionDecision.ALLOW_ALWAYS:
        approved.add(tool_name)
        _persist_to_project(tool_name, allow=True)
    elif decision == PermissionDecision.DENY:
        rejected.add(tool_name)

    return ToolPermissionContext(
        approved_tools=approved,
        rejected_tools=rejected,
    )


def _persist_to_project(tool_name: str, *, allow: bool) -> None:
    """Write an allow/deny rule to ``.pode.json``."""
    config = get_current_project_config()
    if allow:
        if tool_name not in config.allowed_tools:
            config.allowed_tools = [*config.allowed_tools, tool_name]
    else:
        if tool_name not in config.denied_tools:
            config.denied_tools = [*config.denied_tools, tool_name]
    save_current_project_config(config)
