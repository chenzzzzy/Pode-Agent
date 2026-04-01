"""Unit tests for filesystem tools (FileRead, FileWrite, FileEdit, Glob).

Reference: docs/api-specs.md — Tool System API
           docs/testing-strategy.md — Phase 1 test requirements
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from pode_agent.core.tools.base import ToolOutput, ToolUseContext
from pode_agent.tools.filesystem.file_edit import FileEditInput, FileEditTool
from pode_agent.tools.filesystem.file_read import FileReadInput, FileReadTool
from pode_agent.tools.filesystem.file_write import FileWriteInput, FileWriteTool
from pode_agent.tools.filesystem.glob import GlobInput, GlobTool


def _ctx() -> ToolUseContext:
    return ToolUseContext(abort_event=asyncio.Event())


def _find_result(outputs: list[ToolOutput]) -> ToolOutput:
    for o in reversed(outputs):
        if o.type == "result":
            return o
    raise AssertionError("No result output found")


# ---------------------------------------------------------------------------
# FileReadTool
# ---------------------------------------------------------------------------


class TestFileReadToolProperties:
    def setup_method(self) -> None:
        self.tool = FileReadTool()

    def test_name(self) -> None:
        assert self.tool.name == "file_read"

    @pytest.mark.asyncio
    async def test_is_enabled(self) -> None:
        assert await self.tool.is_enabled() is True

    def test_is_read_only(self) -> None:
        assert self.tool.is_read_only() is True

    def test_needs_permissions(self) -> None:
        assert self.tool.needs_permissions() is False


class TestFileReadToolCall:
    def setup_method(self) -> None:
        self.tool = FileReadTool()

    @pytest.mark.asyncio
    async def test_reads_file_content(self, sample_project: Any) -> None:
        inp = FileReadInput(file_path=str(sample_project / "README.md"))
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)
        assert "content" in result.data
        assert "Test Project" in result.data["content"]

    @pytest.mark.asyncio
    async def test_with_offset_and_limit(self, sample_project: Any) -> None:
        # Create a file with multiple lines
        f = sample_project / "multi.txt"
        f.write_text("line0\nline1\nline2\nline3\nline4\n")

        inp = FileReadInput(file_path=str(f), offset=1, limit=2)
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)
        assert result.data["start_line"] == 1
        assert result.data["lines_read"] == 2
        assert "line1" in result.data["content"]
        assert "line3" not in result.data["content"]

    @pytest.mark.asyncio
    async def test_nonexistent_file(self, tmp_cwd: Any) -> None:
        inp = FileReadInput(file_path=str(tmp_cwd / "nope.txt"))
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)
        assert "error" in result.data
        assert "not found" in result.data["error"]

    @pytest.mark.asyncio
    async def test_records_read_timestamp(self, sample_project: Any) -> None:
        ctx = _ctx()
        inp = FileReadInput(file_path=str(sample_project / "main.py"))
        [o async for o in self.tool.call(inp, ctx)]
        # Timestamp should have been recorded
        assert len(ctx.read_file_timestamps) > 0

    @pytest.mark.asyncio
    async def test_path_outside_cwd_rejected(self, tmp_cwd: Any) -> None:
        inp = FileReadInput(file_path="/etc/passwd")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)
        assert "error" in result.data
        assert "outside" in result.data["error"]

    @pytest.mark.asyncio
    async def test_directory_path_rejected(self, tmp_cwd: Any) -> None:
        (tmp_cwd / "subdir").mkdir()
        inp = FileReadInput(file_path=str(tmp_cwd / "subdir"))
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)
        assert "error" in result.data
        assert "directory" in result.data["error"]


# ---------------------------------------------------------------------------
# FileWriteTool
# ---------------------------------------------------------------------------


class TestFileWriteToolProperties:
    def setup_method(self) -> None:
        self.tool = FileWriteTool()

    def test_name(self) -> None:
        assert self.tool.name == "file_write"

    def test_is_read_only(self) -> None:
        assert self.tool.is_read_only() is False

    def test_needs_permissions(self) -> None:
        assert self.tool.needs_permissions() is True


class TestFileWriteToolCall:
    def setup_method(self) -> None:
        self.tool = FileWriteTool()

    @pytest.mark.asyncio
    async def test_creates_new_file(self, tmp_cwd: Any) -> None:
        inp = FileWriteInput(
            file_path=str(tmp_cwd / "new.txt"),
            content="hello world",
        )
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)
        assert result.data["action"] == "created"
        assert (tmp_cwd / "new.txt").read_text() == "hello world"

    @pytest.mark.asyncio
    async def test_creates_parent_directories(self, tmp_cwd: Any) -> None:
        inp = FileWriteInput(
            file_path=str(tmp_cwd / "sub" / "dir" / "file.txt"),
            content="nested",
        )
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)
        assert result.data["action"] == "created"
        assert (tmp_cwd / "sub" / "dir" / "file.txt").read_text() == "nested"

    @pytest.mark.asyncio
    async def test_overwrites_existing_file(self, tmp_cwd: Any) -> None:
        f = tmp_cwd / "existing.txt"
        f.write_text("old content")

        inp = FileWriteInput(file_path=str(f), content="new content")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)
        assert result.data["action"] == "updated"
        assert f.read_text() == "new content"

    @pytest.mark.asyncio
    async def test_path_outside_cwd_rejected(self, tmp_cwd: Any) -> None:
        inp = FileWriteInput(file_path="/tmp/evil.txt", content="nope")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)
        assert "error" in result.data

    @pytest.mark.asyncio
    async def test_empty_content_creates_empty_file(self, tmp_cwd: Any) -> None:
        inp = FileWriteInput(file_path=str(tmp_cwd / "empty.txt"), content="")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)
        assert result.data["action"] == "created"
        assert (tmp_cwd / "empty.txt").read_text() == ""


# ---------------------------------------------------------------------------
# FileEditTool
# ---------------------------------------------------------------------------


class TestFileEditToolProperties:
    def setup_method(self) -> None:
        self.tool = FileEditTool()

    def test_name(self) -> None:
        assert self.tool.name == "file_edit"

    def test_is_read_only(self) -> None:
        assert self.tool.is_read_only() is False

    def test_needs_permissions(self) -> None:
        assert self.tool.needs_permissions() is True


class TestFileEditToolCall:
    def setup_method(self) -> None:
        self.tool = FileEditTool()

    @pytest.mark.asyncio
    async def test_simple_replacement(self, tmp_cwd: Any) -> None:
        f = tmp_cwd / "test.py"
        f.write_text("def foo():\n    pass\n")

        inp = FileEditInput(
            file_path=str(f),
            old_str="pass",
            new_str="return 42",
        )
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)
        assert result.data["replacements"] == 1
        assert f.read_text() == "def foo():\n    return 42\n"

    @pytest.mark.asyncio
    async def test_multiline_replacement(self, tmp_cwd: Any) -> None:
        f = tmp_cwd / "test.py"
        f.write_text("old start\nmiddle\nold end\n")

        inp = FileEditInput(
            file_path=str(f),
            old_str="old start\nmiddle\nold end",
            new_str="new start\nnew end",
        )
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)
        assert result.data["replacements"] == 1
        content = f.read_text()
        assert "new start" in content
        assert "old start" not in content

    @pytest.mark.asyncio
    async def test_old_str_not_found(self, tmp_cwd: Any) -> None:
        f = tmp_cwd / "test.py"
        f.write_text("hello\n")

        inp = FileEditInput(file_path=str(f), old_str="xyz", new_str="abc")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)
        assert "error" in result.data
        assert "not found" in result.data["error"]

    @pytest.mark.asyncio
    async def test_old_str_not_unique(self, tmp_cwd: Any) -> None:
        f = tmp_cwd / "test.py"
        f.write_text("dup\ndup\ndup\n")

        inp = FileEditInput(file_path=str(f), old_str="dup", new_str="unique")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)
        assert "error" in result.data
        assert "3 times" in result.data["error"]

    @pytest.mark.asyncio
    async def test_deletion_with_empty_new_str(self, tmp_cwd: Any) -> None:
        f = tmp_cwd / "test.py"
        f.write_text("keep\ndelete me\nkeep\n")

        inp = FileEditInput(file_path=str(f), old_str="delete me\n", new_str="")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)
        assert result.data["replacements"] == 1
        assert f.read_text() == "keep\nkeep\n"

    @pytest.mark.asyncio
    async def test_path_outside_cwd_rejected(self, tmp_cwd: Any) -> None:
        inp = FileEditInput(file_path="/etc/hosts", old_str="a", new_str="b")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)
        assert "error" in result.data

    @pytest.mark.asyncio
    async def test_nonexistent_file(self, tmp_cwd: Any) -> None:
        inp = FileEditInput(
            file_path=str(tmp_cwd / "nope.txt"),
            old_str="a",
            new_str="b",
        )
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)
        assert "error" in result.data
        assert "not found" in result.data["error"]

    @pytest.mark.asyncio
    async def test_result_includes_diff(self, tmp_cwd: Any) -> None:
        f = tmp_cwd / "test.py"
        f.write_text("old text\n")

        inp = FileEditInput(file_path=str(f), old_str="old text", new_str="new text")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)
        assert "diff" in result.data
        assert "-old text" in result.data["diff"]
        assert "+new text" in result.data["diff"]

    @pytest.mark.asyncio
    async def test_identical_strings_rejected(self, tmp_cwd: Any) -> None:
        f = tmp_cwd / "test.py"
        f.write_text("same\n")

        inp = FileEditInput(file_path=str(f), old_str="same", new_str="same")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)
        assert "error" in result.data
        assert "identical" in result.data["error"]


# ---------------------------------------------------------------------------
# GlobTool
# ---------------------------------------------------------------------------


class TestGlobToolProperties:
    def setup_method(self) -> None:
        self.tool = GlobTool()

    def test_name(self) -> None:
        assert self.tool.name == "glob"

    def test_is_read_only(self) -> None:
        assert self.tool.is_read_only() is True

    def test_needs_permissions(self) -> None:
        assert self.tool.needs_permissions() is False


class TestGlobToolCall:
    def setup_method(self) -> None:
        self.tool = GlobTool()

    @pytest.mark.asyncio
    async def test_finds_matching_files(self, sample_project: Any) -> None:
        inp = GlobInput(pattern="**/*.py", path=str(sample_project))
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)
        assert len(result.data["files"]) >= 1
        assert any("main.py" in f for f in result.data["files"])

    @pytest.mark.asyncio
    async def test_recursive_glob(self, tmp_cwd: Any) -> None:
        (tmp_cwd / "sub").mkdir()
        (tmp_cwd / "sub" / "nested.py").write_text("pass")
        (tmp_cwd / "top.py").write_text("pass")

        inp = GlobInput(pattern="**/*.py")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)
        paths = result.data["files"]
        assert any("nested.py" in p for p in paths)
        assert any("top.py" in p for p in paths)

    @pytest.mark.asyncio
    async def test_no_matches(self, tmp_cwd: Any) -> None:
        inp = GlobInput(pattern="*.nonexistent")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)
        assert result.data["total"] == 0

    @pytest.mark.asyncio
    async def test_limits_results(self, tmp_cwd: Any) -> None:
        for i in range(5):
            (tmp_cwd / f"file{i}.txt").write_text("x")

        inp = GlobInput(pattern="*.txt", limit=3)
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)
        assert result.data["total"] == 3
        assert result.data["truncated"] is True

    @pytest.mark.asyncio
    async def test_path_outside_cwd_rejected(self, tmp_cwd: Any) -> None:
        inp = GlobInput(pattern="*", path="/etc")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)
        assert "error" in result.data
