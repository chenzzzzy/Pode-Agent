"""SubAgent session factory — creates isolated SessionManager instances for SubAgents.

Reference: docs/subagent-system.md — Sub-session instantiation
"""

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
    return mapping.get(config.permission_mode, PermissionMode.ACCEPT_EDITS)


def _build_system_prompt(
    base_prompt: str,
    agent_config: AgentConfig,
) -> str:
    """Build the sub-agent system prompt by combining base + agent config.

    The agent config's system_prompt is appended to the base prompt,
    providing the agent's specialized role instructions.
    """
    parts: list[str] = []
    if base_prompt:
        parts.append(base_prompt)
    if agent_config.system_prompt:
        parts.append(agent_config.system_prompt)
    return "\n\n".join(parts)


def create_sub_session(
    parent_session: Any,
    agent_config: AgentConfig,
    tools: list[Any],
    initial_messages: list[dict[str, Any]],
) -> Any:
    """Create an isolated SessionManager for a SubAgent run.

    The sub-session inherits the parent's model and base system prompt,
    but has its own message history, abort event, permission context,
    and an augmented system prompt from the agent config.
    """
    from pode_agent.app.session import SessionManager

    perm_mode = _resolve_permission_mode(agent_config)

    # Resolve model from agent config
    model = getattr(parent_session, "model", "claude-sonnet-4-5-20251101")

    # Build combined system prompt
    base_prompt = getattr(parent_session, "_system_prompt", "")
    system_prompt = _build_system_prompt(base_prompt, agent_config)

    session = SessionManager(
        tools=tools,
        initial_messages=initial_messages,
        permission_context=PermissionContext(mode=perm_mode),
        model=model,
        system_prompt=system_prompt,
    )

    return session
