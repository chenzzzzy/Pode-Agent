"""Tool loader: discovers and registers all available tools.

Phase 3: loads built-in tools only.
Phase 5: adds MCP tools and plugin tools.

Reference: docs/tools-system.md — ToolLoader
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

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
        self._mcp_clients: list[Any] = []

    async def load_all(self) -> None:
        """Load all tool sources in order: builtin → MCP → plugin."""
        self._load_builtin_tools()
        await self._load_mcp_tools()
        self._load_plugin_tools()

    def _load_builtin_tools(self) -> None:
        """Import and register all built-in tools from ``tools.get_all_tools()``."""
        from pode_agent.tools import get_all_tools

        tools = get_all_tools()
        for tool in tools:
            self._registry.register(tool)
        logger.debug("Loaded %d built-in tools", len(tools))

    async def _load_mcp_tools(self) -> None:
        """Connect to configured MCP servers and register their tools.

        Merges MCP server definitions from both global config and project config.
        Project config overrides global config for same-named servers.
        """
        # Merge MCP servers from global config + project config
        from pode_agent.core.config.schema import McpServerConfig

        mcp_servers: dict[str, McpServerConfig] = {}
        if self._config:
            mcp_servers.update(getattr(self._config, "mcp_servers", {}))

        # Also check project-level .pode.json
        try:
            from pode_agent.core.config.loader import get_current_project_config

            project_config = get_current_project_config()
            project_mcp = getattr(project_config, "mcp_servers", {})
            if project_mcp:
                mcp_servers.update(project_mcp)  # project overrides global
        except Exception:
            logger.debug("No project config found for MCP servers")

        if not mcp_servers:
            return

        from pode_agent.services.mcp.client import connect_all_mcp_servers
        from pode_agent.services.mcp.tools import wrap_mcp_tool_as_pode_tool

        wrapped_clients = await connect_all_mcp_servers(mcp_servers)
        for wrapped in wrapped_clients:
            if not wrapped.is_connected or not wrapped.client:
                logger.warning(
                    "MCP server '%s' not connected: %s", wrapped.name, wrapped.error,
                )
                continue
            self._mcp_clients.append(wrapped.client)
            try:
                tools = await wrapped.client.list_tools()
                for tool_def in tools:
                    pode_tool = wrap_mcp_tool_as_pode_tool(
                        wrapped.client, wrapped.name, tool_def,
                    )
                    self._registry.register(pode_tool)
                logger.info(
                    "Loaded %d MCP tools from server '%s'", len(tools), wrapped.name,
                )
            except Exception:
                logger.exception("Failed to load MCP tools from '%s'", wrapped.name)

    def _load_plugin_tools(self) -> None:
        """Load tools from package entry_points."""
        try:
            import importlib.metadata

            eps = importlib.metadata.entry_points()
            # Python 3.12+: entry_points() returns a SelectableGroups
            tool_eps = (
                eps.select(group="pode_agent.tools")
                if hasattr(eps, "select")
                else eps.get("pode_agent.tools", [])  # type: ignore[arg-type]
            )
            for ep in tool_eps:
                try:
                    tool_cls = ep.load()
                    self._registry.register(tool_cls())
                    logger.debug("Loaded plugin tool: %s", ep.name)
                except Exception:
                    logger.exception("Failed to load plugin tool: %s", ep.name)
        except Exception:
            logger.debug("No plugin entry_points group found")

    async def close_all(self) -> None:
        """Close all MCP client connections (subprocess cleanup)."""
        import contextlib

        for client in self._mcp_clients:
            with contextlib.suppress(Exception):
                await client.close()
        self._mcp_clients.clear()


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
