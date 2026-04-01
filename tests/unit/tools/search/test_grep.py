"""Unit tests for GrepTool.

Reference: docs/api-specs.md — Tool System API, GrepTool
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from pode_agent.core.tools.base import ToolUseContext
from pode_agent.tools.search.grep import GrepInput, GrepTool


def _ctx() -> ToolUseContext:
    return ToolUseContext(abort_event=asyncio.Event())


def _find_result(outputs: list[Any]) -> Any:
    for o in reversed(outputs):
        if o.type == "result":
            return o
    raise AssertionError("No result output found")


class TestGrepToolProperties:
    def setup_method(self) -> None:
        self.tool = GrepTool()

    def test_name(self) -> None:
        assert self.tool.name == "grep"

    @pytest.mark.asyncio
    async def test_is_enabled(self) -> None:
        assert await self.tool.is_enabled() is True

    def test_is_read_only(self) -> None:
        assert self.tool.is_read_only() is True

    def test_needs_permissions(self) -> None:
        assert self.tool.needs_permissions() is False


class TestGrepToolCall:
    def setup_method(self) -> None:
        self.tool = GrepTool()

    @pytest.mark.asyncio
    async def test_finds_matching_lines(self, tmp_cwd: Any) -> None:
        (tmp_cwd / "test.py").write_text("hello world\nfoo bar\nhello again\n")

        inp = GrepInput(pattern="hello")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)
        assert result.data["total"] > 0
        assert "hello" in result.data["content"]

    @pytest.mark.asyncio
    async def test_case_insensitive(self, tmp_cwd: Any) -> None:
        (tmp_cwd / "test.py").write_text("HELLO\n")

        inp = GrepInput(pattern="hello", ignore_case=True)
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)
        assert result.data["total"] > 0

    @pytest.mark.asyncio
    async def test_files_only(self, tmp_cwd: Any) -> None:
        (tmp_cwd / "a.py").write_text("match here\n")
        (tmp_cwd / "b.py").write_text("no match\n")

        inp = GrepInput(pattern="match", files_only=True)
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)
        assert result.data["total"] > 0

    @pytest.mark.asyncio
    async def test_no_matches(self, tmp_cwd: Any) -> None:
        (tmp_cwd / "test.py").write_text("nothing here\n")

        inp = GrepInput(pattern="xyz_missing")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)
        assert result.data["total"] == 0

    @pytest.mark.asyncio
    async def test_path_outside_cwd_rejected(self, tmp_cwd: Any) -> None:
        inp = GrepInput(pattern="test", path="/etc")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)
        assert "error" in result.data

    @pytest.mark.asyncio
    async def test_file_type_filter(self, tmp_cwd: Any) -> None:
        (tmp_cwd / "a.py").write_text("match\n")
        (tmp_cwd / "b.js").write_text("match\n")

        inp = GrepInput(pattern="match", file_type="py")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)
        content = result.data.get("content", "")
        assert "a.py" in content
