"""Unit tests for LsTool.

Reference: docs/api-specs.md — Tool System API, LsTool
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from pode_agent.core.tools.base import ToolUseContext
from pode_agent.tools.agent.ls import LsInput, LsTool


def _ctx() -> ToolUseContext:
    return ToolUseContext(abort_event=asyncio.Event())


def _find_result(outputs: list[Any]) -> Any:
    for o in reversed(outputs):
        if o.type == "result":
            return o
    raise AssertionError("No result output found")


class TestLsToolProperties:
    def setup_method(self) -> None:
        self.tool = LsTool()

    def test_name(self) -> None:
        assert self.tool.name == "ls"

    @pytest.mark.asyncio
    async def test_is_enabled(self) -> None:
        assert await self.tool.is_enabled() is True

    def test_is_read_only(self) -> None:
        assert self.tool.is_read_only() is True

    def test_needs_permissions(self) -> None:
        assert self.tool.needs_permissions() is False


class TestLsToolCall:
    def setup_method(self) -> None:
        self.tool = LsTool()

    @pytest.mark.asyncio
    async def test_lists_directory_contents(self, sample_project: Any) -> None:
        inp = LsInput(path=str(sample_project))
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)
        names = [e["name"] for e in result.data["entries"]]
        assert "main.py" in names
        assert "README.md" in names

    @pytest.mark.asyncio
    async def test_shows_file_types(self, tmp_cwd: Any) -> None:
        (tmp_cwd / "file.txt").write_text("x")
        (tmp_cwd / "subdir").mkdir()

        inp = LsInput()
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)
        types = {e["name"]: e["type"] for e in result.data["entries"]}
        assert types["subdir"] == "dir"
        assert types["file.txt"] == "file"

    @pytest.mark.asyncio
    async def test_handles_nonexistent_directory(self, tmp_cwd: Any) -> None:
        inp = LsInput(path=str(tmp_cwd / "nope"))
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)
        assert "error" in result.data

    @pytest.mark.asyncio
    async def test_path_outside_cwd_rejected(self, tmp_cwd: Any) -> None:
        inp = LsInput(path="/etc")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)
        assert "error" in result.data

    @pytest.mark.asyncio
    async def test_empty_directory(self, tmp_cwd: Any) -> None:
        inp = LsInput()
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)
        assert result.data["total"] == 0

    @pytest.mark.asyncio
    async def test_skips_hidden_and_cache_dirs(self, tmp_cwd: Any) -> None:
        (tmp_cwd / ".hidden").mkdir()
        (tmp_cwd / "__pycache__").mkdir()
        (tmp_cwd / "visible.txt").write_text("x")

        inp = LsInput()
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)
        names = [e["name"] for e in result.data["entries"]]
        assert "visible.txt" in names
        assert ".hidden" not in names
        assert "__pycache__" not in names
