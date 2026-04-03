"""Permission engine: decides whether a tool call is allowed.

Implements the layered permission check order documented in
docs/api-specs.md:

    bypass > rejected > approved > project denied >
    project allowed > plan mode > tool-specific > default NEEDS_PROMPT

Reference: docs/api-specs.md — Permissions API, Permission engine
"""

from __future__ import annotations

from typing import Any

from pode_agent.core.permissions.rules.bash import is_safe_bash_command
from pode_agent.core.permissions.rules.plan_mode import PLAN_MODE_ALLOWED_TOOLS
from pode_agent.core.permissions.types import (
    PermissionContext,
    PermissionResult,
)


class PermissionEngine:
    """Evaluates tool-call permission requests.

    Stateless — all context is passed via :class:`PermissionContext`.
    """

    def has_permissions(
        self,
        tool_name: str,
        tool_input: Any = None,
        *,
        context: PermissionContext | None = None,
        is_read_only: bool = False,
    ) -> PermissionResult:
        """Check whether a tool call is allowed.

        Args:
            tool_name: The ``tool.name`` identifier.
            tool_input: The validated tool input (for tool-specific checks).
            context: Permission context with mode, approved/rejected sets,
                and project-level rules.
            is_read_only: Whether the tool reports itself as read-only.

        Returns:
            :attr:`PermissionResult.ALLOWED`,
            :attr:`PermissionResult.NEEDS_PROMPT`, or
            :attr:`PermissionResult.DENIED`.
        """
        if context is None:
            context = PermissionContext()

        # 1. Bypass mode — allow everything.
        if context.mode.value == "bypass_permissions":
            return PermissionResult.ALLOWED

        tpc = context.tool_permission_context

        # 2. Session-level rejected tools.
        if tool_name in tpc.rejected_tools:
            return PermissionResult.DENIED

        # 3. Session-level approved tools.
        if tool_name in tpc.approved_tools:
            return PermissionResult.ALLOWED

        # 4. Project-level denied tools.
        if tool_name in context.denied_tools:
            return PermissionResult.DENIED

        # 5. Project-level allowed tools.
        if tool_name in context.allowed_tools:
            return PermissionResult.ALLOWED

        # 6. Plan mode — allow listed tools and read-only tools; deny the rest.
        if context.mode.value == "plan":
            if tool_name in PLAN_MODE_ALLOWED_TOOLS or is_read_only:
                return PermissionResult.ALLOWED
            return PermissionResult.DENIED

        # 7. Accept-edits mode — allow all tools (including writes).
        if context.mode.value == "accept_edits":
            return PermissionResult.ALLOWED

        # 8. Tool-specific rules.
        tool_result = self._check_tool_specific(tool_name, tool_input)
        if tool_result is not None:
            return tool_result

        # 9. Default.
        return PermissionResult.NEEDS_PROMPT

    def _check_tool_specific(
        self,
        tool_name: str,
        tool_input: Any,
    ) -> PermissionResult | None:
        """Apply tool-specific safety rules. Returns None to fall through."""
        if tool_name == "bash":
            if tool_input is not None:
                # tool_input may be a dict (from JSON) or a Pydantic model
                if isinstance(tool_input, dict):
                    command = tool_input.get("command")
                else:
                    command = getattr(tool_input, "command", None)
                if command is not None and is_safe_bash_command(command):
                    return PermissionResult.ALLOWED
            return PermissionResult.NEEDS_PROMPT

        return None
