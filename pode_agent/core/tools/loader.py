"""Tool loader: discovers and registers all available tools.

Phase 3: loads built-in tools only.
Phase 5: adds MCP tools and plugin tools.

Reference: docs/tools-system.md — ToolLoader
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pode_agent.core.config.schema import GlobalConfig
    from pode_agent.core.tools.base import Tool
    from pode_agent.core.tools.registry import ToolRegistry

from pode_agent.core.permissions.types import PermissionMode

logger = logging.getLogger(__name__)


class ToolLoader:
    """Discovers and registers tools into a ``ToolRegistry``.

    Usage::

        registry = ToolRegistry()
        loader = ToolLoader(registry)
        await loader.load_all()
    """

    def __init__(self, registry: ToolRegistry, config: GlobalConfig | None = None) -> None:
        self._registry = registry
        self._config = config

    async def load_all(self) -> None:
        """Load all tool sources in order: builtin → (plugin) → (MCP)."""
        self._load_builtin_tools()
        # Phase 5: self._load_plugin_tools()
        # Phase 5: self._load_mcp_tools()

    def _load_builtin_tools(self) -> None:
        """Import and register all built-in tools from ``tools.get_all_tools()``."""
        from pode_agent.tools import get_all_tools

        tools = get_all_tools()
        for tool in tools:
            self._registry.register(tool)
        logger.debug("Loaded %d built-in tools", len(tools))


async def get_enabled_tools(
    registry: ToolRegistry,
    *,
    safe_mode: bool = False,
    permission_mode: PermissionMode = PermissionMode.DEFAULT,
    command_allowed_tools: list[str] | None = None,
) -> list[Tool]:
    """Filter registry tools by availability and mode constraints.

    Applies in order:
    1. ``tool.is_enabled()`` — environment check (e.g. ripgrep installed)
    2. ``safe_mode`` — removes non-read-only tools
    3. ``permission_mode == PLAN`` — keeps only plan-allowed tools
    4. ``command_allowed_tools`` — restricts to a specific tool list
    """
    from pode_agent.core.permissions.rules.plan_mode import PLAN_MODE_ALLOWED_TOOLS

    result: list[Tool] = []
    for tool in registry.tools:
        # 1. Environment check
        if not await tool.is_enabled():
            continue
        # 2. Safe mode: only read-only tools
        if safe_mode and not tool.is_read_only():
            continue
        # 3. Plan mode: only plan-allowed tools + read-only tools
        if (
            permission_mode == PermissionMode.PLAN
            and tool.name not in PLAN_MODE_ALLOWED_TOOLS
            and not tool.is_read_only()
        ):
            continue
        # 4. Command-allowed restriction
        if command_allowed_tools is not None and tool.name not in command_allowed_tools:
            continue
        result.append(tool)
    return result
