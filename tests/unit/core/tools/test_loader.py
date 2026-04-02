"""Unit tests for ToolLoader and get_all_tools."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from pode_agent.core.permissions.types import PermissionMode
from pode_agent.core.tools.loader import ToolLoader, get_enabled_tools
from pode_agent.core.tools.registry import ToolRegistry
from pode_agent.tools import get_all_tools


class TestGetAllTools:
    """Tests for the get_all_tools() function."""

    def test_returns_list(self) -> None:
        tools = get_all_tools()
        assert isinstance(tools, list)
        assert len(tools) > 0

    def test_all_have_names(self) -> None:
        for tool in get_all_tools():
            assert isinstance(tool.name, str)
            assert len(tool.name) > 0

    def test_unique_names(self) -> None:
        names = [t.name for t in get_all_tools()]
        assert len(names) == len(set(names)), f"Duplicate names: {names}"

    def test_phase3_tool_count(self) -> None:
        """Phase 3 delivers 7 core + 15+ new tools (25+ total)."""
        tools = get_all_tools()
        assert len(tools) >= 7

    def test_expected_tools_present(self) -> None:
        names = {t.name for t in get_all_tools()}
        assert "bash" in names
        assert "file_read" in names
        assert "file_write" in names
        assert "file_edit" in names
        assert "glob" in names
        assert "grep" in names
        assert "ls" in names


class TestToolLoader:
    """Tests for ToolLoader class."""

    def test_load_builtin_tools(self) -> None:
        registry = ToolRegistry()
        loader = ToolLoader(registry)
        loader._load_builtin_tools()
        assert len(registry) >= 7
        assert "bash" in registry
        assert "file_read" in registry

    async def test_load_all(self) -> None:
        registry = ToolRegistry()
        loader = ToolLoader(registry)
        await loader.load_all()
        assert len(registry) >= 7

    async def test_load_all_idempotent(self) -> None:
        registry = ToolRegistry()
        loader = ToolLoader(registry)
        await loader.load_all()
        count = len(registry)
        await loader.load_all()
        assert len(registry) == count  # no duplicates


class TestGetEnabledTools:
    """Tests for the get_enabled_tools() filtering function."""

    def _make_tool(self, name: str, *, enabled: bool = True, read_only: bool = True) -> MagicMock:
        tool = MagicMock()
        tool.name = name
        tool.is_enabled = AsyncMock(return_value=enabled)
        tool.is_read_only = MagicMock(return_value=read_only)
        return tool

    async def test_returns_enabled_tools(self) -> None:
        registry = ToolRegistry()
        registry.register(self._make_tool("a", enabled=True))
        registry.register(self._make_tool("b", enabled=False))
        result = await get_enabled_tools(registry)
        assert [t.name for t in result] == ["a"]

    async def test_safe_mode_filters_non_readonly(self) -> None:
        registry = ToolRegistry()
        registry.register(self._make_tool("read", read_only=True))
        registry.register(self._make_tool("write", read_only=False))
        result = await get_enabled_tools(registry, safe_mode=True)
        assert [t.name for t in result] == ["read"]

    async def test_plan_mode_filters_by_allowed_set(self) -> None:
        registry = ToolRegistry()
        # bash is in PLAN_MODE_ALLOWED_TOOLS
        registry.register(self._make_tool("bash", read_only=False))
        # file_edit is NOT in PLAN_MODE_ALLOWED_TOOLS and not read_only
        registry.register(self._make_tool("file_edit", read_only=False))
        # file_read is read_only (implicitly allowed)
        registry.register(self._make_tool("file_read", read_only=True))
        result = await get_enabled_tools(registry, permission_mode=PermissionMode.PLAN)
        names = {t.name for t in result}
        assert "bash" in names
        assert "file_read" in names
        assert "file_edit" not in names

    async def test_command_allowed_tools(self) -> None:
        registry = ToolRegistry()
        registry.register(self._make_tool("a"))
        registry.register(self._make_tool("b"))
        result = await get_enabled_tools(registry, command_allowed_tools=["a"])
        assert [t.name for t in result] == ["a"]

    async def test_all_filters_combined(self) -> None:
        registry = ToolRegistry()
        registry.register(self._make_tool("safe", read_only=True, enabled=True))
        registry.register(self._make_tool("unsafe", read_only=False, enabled=True))
        result = await get_enabled_tools(
            registry,
            safe_mode=True,
            command_allowed_tools=["safe", "unsafe"],
        )
        assert [t.name for t in result] == ["safe"]
