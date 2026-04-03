"""SubAgent session factory — creates isolated SessionManager instances for SubAgents."""

from __future__ import annotations

from typing import Any

from pode_agent.core.permissions.types import PermissionContext, PermissionMode
from pode_agent.types.agent import AgentConfig, AgentPermissionMode


def _resolve_permission_mode(config: AgentConfig) -> PermissionMode:
    """Map agent permission mode to session PermissionMode."""
    mapping: dict[AgentPermissionMode, PermissionMode] = {
        AgentPermissionMode.DEFAULT: PermissionMode.DEFAULT,
        AgentPermissionMode.DONT_ASK: PermissionMode.ACCEPT_EDITS,
        AgentPermissionMode.BYPASS_PERMISSIONS: PermissionMode.BYPASS_PERMISSIONS,
    }
    return mapping.get(config.permission_mode, PermissionMode.DEFAULT)


def create_sub_session(
    parent_session: Any,
    agent_config: AgentConfig,
    tools: list[Any],
    initial_messages: list[dict[str, Any]],
) -> Any:
    """Create an isolated SessionManager for a SubAgent run.

    The sub-session inherits the parent's configuration but has its own
    message history, abort event, and permission context.
    """
    from pode_agent.app.session import SessionManager

    perm_mode = _resolve_permission_mode(agent_config)

    session = SessionManager(
        tools=tools,
        initial_messages=initial_messages,
        permission_context=PermissionContext(mode=perm_mode),
        model=parent_session._model if hasattr(parent_session, "_model") else "claude-sonnet-4-5-20251101",
        system_prompt=parent_session._system_prompt if hasattr(parent_session, "_system_prompt") else "",
    )

    return session
