"""Unit tests for MultiEditTool.

Reference: docs/api-specs.md — Tool System API, MultiEditTool
           docs/testing-strategy.md — Phase 1 test requirements
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from pode_agent.core.tools.base import ToolOutput, ToolUseContext
from pode_agent.tools.filesystem.multi_edit import (
    EditOperation,
    MultiEditInput,
    MultiEditTool,
)


def _ctx() -> ToolUseContext:
    return ToolUseContext(abort_event=asyncio.Event())


def _find_result(outputs: list[ToolOutput]) -> ToolOutput:
    for o in reversed(outputs):
        if o.type == "result":
            return o
    raise AssertionError("No result output found")


async def _call(tool: MultiEditTool, edits: list[EditOperation]) -> ToolOutput:
    inp = MultiEditInput(edits=edits)
    outputs = [o async for o in tool.call(inp, _ctx())]
    return _find_result(outputs)


# ---------------------------------------------------------------------------
# Tool properties
# ---------------------------------------------------------------------------


class TestMultiEditToolProperties:
    def setup_method(self) -> None:
        self.tool = MultiEditTool()

    def test_name(self) -> None:
        assert self.tool.name == "multi_edit"

    def test_schema(self) -> None:
        assert self.tool.input_schema() is MultiEditInput

    def test_is_read_only(self) -> None:
        assert self.tool.is_read_only() is False

    def test_permissions(self) -> None:
        assert self.tool.needs_permissions() is True

    def test_concurrency_safe(self) -> None:
        assert self.tool.is_concurrency_safe() is False


# ---------------------------------------------------------------------------
# Tool call
# ---------------------------------------------------------------------------


class TestMultiEditToolCall:
    def setup_method(self) -> None:
        self.tool = MultiEditTool()

    @pytest.mark.asyncio
    async def test_single_file_multiple_edits(self, tmp_cwd: Any) -> None:
        f = tmp_cwd / "test.py"
        f.write_text("def foo():\n    pass\n\ndef bar():\n    pass\n")

        result = await _call(self.tool, [
            EditOperation(
                file_path=str(f),
                old_str="def foo():\n    pass",
                new_str="def foo():\n    return 1",
            ),
            EditOperation(
                file_path=str(f),
                old_str="def bar():\n    pass",
                new_str="def bar():\n    return 2",
            ),
        ])

        assert result.data["edits_applied"] == 2
        assert len(result.data["files_changed"]) == 1
        content = f.read_text()
        assert "return 1" in content
        assert "return 2" in content
        assert "pass" not in content

    @pytest.mark.asyncio
    async def test_cross_file_edits(self, tmp_cwd: Any) -> None:
        a = tmp_cwd / "a.py"
        b = tmp_cwd / "b.py"
        a.write_text("old_a\n")
        b.write_text("old_b\n")

        result = await _call(self.tool, [
            EditOperation(
                file_path=str(a),
                old_str="old_a",
                new_str="new_a",
            ),
            EditOperation(
                file_path=str(b),
                old_str="old_b",
                new_str="new_b",
            ),
        ])

        assert result.data["edits_applied"] == 2
        assert len(result.data["files_changed"]) == 2
        assert a.read_text() == "new_a\n"
        assert b.read_text() == "new_b\n"

    @pytest.mark.asyncio
    async def test_validation_failure_no_modifications(self, tmp_cwd: Any) -> None:
        a = tmp_cwd / "a.py"
        b = tmp_cwd / "b.py"
        original_a = "keep_a\n"
        original_b = "keep_b\n"
        a.write_text(original_a)
        b.write_text(original_b)

        result = await _call(self.tool, [
            EditOperation(
                file_path=str(a),
                old_str="keep_a",
                new_str="changed_a",
            ),
            EditOperation(
                file_path=str(b),
                old_str="nonexistent",
                new_str="changed_b",
            ),
        ])

        assert "error" in result.data
        assert "not found" in result.data["error"]
        # Nothing should have been modified
        assert a.read_text() == original_a
        assert b.read_text() == original_b

    @pytest.mark.asyncio
    async def test_non_unique_old_str(self, tmp_cwd: Any) -> None:
        f = tmp_cwd / "dup.py"
        f.write_text("dup\ndup\ndup\n")

        result = await _call(self.tool, [
            EditOperation(
                file_path=str(f),
                old_str="dup",
                new_str="unique",
            ),
        ])

        assert "error" in result.data
        assert "3 times" in result.data["error"]

    @pytest.mark.asyncio
    async def test_path_traversal_rejected(self, tmp_cwd: Any) -> None:
        f = tmp_cwd / "safe.py"
        f.write_text("safe\n")

        result = await _call(self.tool, [
            EditOperation(
                file_path=str(f),
                old_str="safe",
                new_str="changed",
            ),
            EditOperation(
                file_path="/etc/hosts",
                old_str="a",
                new_str="b",
            ),
        ])

        assert "error" in result.data
        assert "outside" in result.data["error"]
        # First file should not have been modified
        assert f.read_text() == "safe\n"

    @pytest.mark.asyncio
    async def test_empty_edits_list(self, tmp_cwd: Any) -> None:
        result = await _call(self.tool, [])

        assert "error" in result.data
        assert "No edits" in result.data["error"]

    @pytest.mark.asyncio
    async def test_result_includes_diffs(self, tmp_cwd: Any) -> None:
        f = tmp_cwd / "test.py"
        f.write_text("old text\n")

        result = await _call(self.tool, [
            EditOperation(
                file_path=str(f),
                old_str="old text",
                new_str="new text",
            ),
        ])

        assert "diffs" in result.data
        assert len(result.data["diffs"]) == 1
        assert "-old text" in result.data["diffs"][0]
        assert "+new text" in result.data["diffs"][0]
