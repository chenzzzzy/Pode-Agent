"""Tool registry: store and look up tools by name."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pode_agent.core.tools.base import Tool


class ToolRegistry:
    """Central registry for all available tools.

    Supports lookup by name and iteration over all registered tools.
    """

    def __init__(self, tools: list[Tool] | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        if tools:
            for tool in tools:
                self.register(tool)

    def register(self, tool: Tool) -> None:
        """Register a tool. Overwrites if name already exists."""
        self._tools[tool.name] = tool

    def get_tool_by_name(self, name: str) -> Tool | None:
        """Look up a tool by its unique name."""
        return self._tools.get(name)

    @property
    def tools(self) -> list[Tool]:
        """All registered tools."""
        return list(self._tools.values())

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
