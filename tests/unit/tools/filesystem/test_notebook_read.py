"""Unit tests for NotebookReadTool.

Reference: docs/api-specs.md — Tool System API
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from pode_agent.core.tools.base import ToolOutput, ToolUseContext
from pode_agent.tools.filesystem.notebook_read import (
    NotebookReadInput,
    NotebookReadTool,
)


def _ctx() -> ToolUseContext:
    return ToolUseContext(abort_event=asyncio.Event())


def _find_result(outputs: list[ToolOutput]) -> ToolOutput:
    for o in reversed(outputs):
        if o.type == "result":
            return o
    raise AssertionError("No result output found")


def _make_notebook(cells: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a minimal valid notebook dict."""
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {},
        "cells": cells,
    }


def _code_cell(source: str, outputs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Build a code cell."""
    return {
        "cell_type": "code",
        "source": source,
        "metadata": {},
        "execution_count": 1,
        "outputs": outputs or [],
    }


def _markdown_cell(source: str) -> dict[str, Any]:
    """Build a markdown cell."""
    return {
        "cell_type": "markdown",
        "source": source,
        "metadata": {},
    }


def _stream_output(text: str) -> dict[str, Any]:
    return {"output_type": "stream", "name": "stdout", "text": text}


def _error_output(ename: str, evalue: str) -> dict[str, Any]:
    return {
        "output_type": "error",
        "ename": ename,
        "evalue": evalue,
        "traceback": [f"{ename}: {evalue}"],
    }


# ---------------------------------------------------------------------------
# NotebookReadTool — properties
# ---------------------------------------------------------------------------


class TestNotebookReadToolProperties:
    def setup_method(self) -> None:
        self.tool = NotebookReadTool()

    def test_name(self) -> None:
        assert self.tool.name == "notebook_read"

    @pytest.mark.asyncio
    async def test_is_enabled(self) -> None:
        assert await self.tool.is_enabled() is True

    def test_is_read_only(self) -> None:
        assert self.tool.is_read_only() is True

    def test_needs_permissions(self) -> None:
        assert self.tool.needs_permissions() is False

    def test_is_concurrency_safe(self) -> None:
        assert self.tool.is_concurrency_safe() is True

    def test_input_schema(self) -> None:
        assert self.tool.input_schema() is NotebookReadInput

    def test_render_result_for_assistant_error(self) -> None:
        result = self.tool.render_result_for_assistant({"error": "bad"})
        assert result == "bad"

    def test_render_result_for_assistant_normal(self) -> None:
        result = self.tool.render_result_for_assistant({"cells": []})
        assert "cells" in result


# ---------------------------------------------------------------------------
# NotebookReadTool — call
# ---------------------------------------------------------------------------


class TestNotebookReadToolCall:
    def setup_method(self) -> None:
        self.tool = NotebookReadTool()

    @pytest.mark.asyncio
    async def test_reads_full_notebook(self, tmp_cwd: Any) -> None:
        nb = _make_notebook([
            _markdown_cell("# Title"),
            _code_cell("print('hello')", [_stream_output("hello\n")]),
        ])
        nb_path = tmp_cwd / "test.ipynb"
        nb_path.write_text(json.dumps(nb), encoding="utf-8")

        inp = NotebookReadInput(file_path=str(nb_path))
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert result.data["total_cells"] == 2
        assert len(result.data["cells"]) == 2
        assert result.data["cells"][0]["cell_type"] == "markdown"
        assert result.data["cells"][0]["source"] == "# Title"
        assert result.data["cells"][1]["cell_type"] == "code"
        assert result.data["cells"][1]["source"] == "print('hello')"
        assert len(result.data["cells"][1]["outputs"]) == 1

    @pytest.mark.asyncio
    async def test_reads_specific_cell_by_index(self, tmp_cwd: Any) -> None:
        nb = _make_notebook([
            _markdown_cell("# First"),
            _markdown_cell("# Second"),
            _markdown_cell("# Third"),
        ])
        nb_path = tmp_cwd / "test.ipynb"
        nb_path.write_text(json.dumps(nb), encoding="utf-8")

        inp = NotebookReadInput(file_path=str(nb_path), cell_index=1)
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert result.data["total_cells"] == 3
        assert len(result.data["cells"]) == 1
        assert result.data["cells"][0]["cell_number"] == 1
        assert result.data["cells"][0]["source"] == "# Second"

    @pytest.mark.asyncio
    async def test_reads_with_limit(self, tmp_cwd: Any) -> None:
        cells = [_markdown_cell(f"# Cell {i}") for i in range(5)]
        nb = _make_notebook(cells)
        nb_path = tmp_cwd / "test.ipynb"
        nb_path.write_text(json.dumps(nb), encoding="utf-8")

        inp = NotebookReadInput(file_path=str(nb_path), limit=3)
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert result.data["total_cells"] == 5
        assert len(result.data["cells"]) == 3
        assert result.data["cells"][0]["cell_number"] == 0
        assert result.data["cells"][2]["cell_number"] == 2

    @pytest.mark.asyncio
    async def test_handles_nonexistent_file(self, tmp_cwd: Any) -> None:
        inp = NotebookReadInput(file_path=str(tmp_cwd / "nope.ipynb"))
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert "error" in result.data
        assert "not found" in result.data["error"]

    @pytest.mark.asyncio
    async def test_handles_invalid_json(self, tmp_cwd: Any) -> None:
        nb_path = tmp_cwd / "bad.ipynb"
        nb_path.write_text("this is not json{{{", encoding="utf-8")

        inp = NotebookReadInput(file_path=str(nb_path))
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert "error" in result.data
        assert "Invalid notebook JSON" in result.data["error"]

    @pytest.mark.asyncio
    async def test_handles_file_outside_working_directory(self, tmp_cwd: Any) -> None:
        inp = NotebookReadInput(file_path="/etc/some_notebook.ipynb")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert "error" in result.data
        assert "outside" in result.data["error"]

    @pytest.mark.asyncio
    async def test_handles_malformed_notebook_no_cells(self, tmp_cwd: Any) -> None:
        nb_path = tmp_cwd / "nocells.ipynb"
        nb_path.write_text(json.dumps({"nbformat": 4}), encoding="utf-8")

        inp = NotebookReadInput(file_path=str(nb_path))
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert "error" in result.data
        assert "Malformed" in result.data["error"]

    @pytest.mark.asyncio
    async def test_handles_cell_index_out_of_range(self, tmp_cwd: Any) -> None:
        nb = _make_notebook([_markdown_cell("# Only")])
        nb_path = tmp_cwd / "test.ipynb"
        nb_path.write_text(json.dumps(nb), encoding="utf-8")

        inp = NotebookReadInput(file_path=str(nb_path), cell_index=5)
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert "error" in result.data
        assert "out of range" in result.data["error"]

    @pytest.mark.asyncio
    async def test_handles_directory_path(self, tmp_cwd: Any) -> None:
        sub = tmp_cwd / "subdir"
        sub.mkdir()

        inp = NotebookReadInput(file_path=str(sub))
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert "error" in result.data
        assert "directory" in result.data["error"]

    @pytest.mark.asyncio
    async def test_source_as_list_joined(self, tmp_cwd: Any) -> None:
        """Cell source can be a list of strings in .ipynb format."""
        nb = _make_notebook([
            {
                "cell_type": "code",
                "source": ["line1\n", "line2\n"],
                "metadata": {},
                "execution_count": 1,
                "outputs": [],
            }
        ])
        nb_path = tmp_cwd / "list_source.ipynb"
        nb_path.write_text(json.dumps(nb), encoding="utf-8")

        inp = NotebookReadInput(file_path=str(nb_path))
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert result.data["cells"][0]["source"] == "line1\nline2\n"

    @pytest.mark.asyncio
    async def test_error_output_extracted(self, tmp_cwd: Any) -> None:
        nb = _make_notebook([
            _code_cell("raise ValueError('oops')", [_error_output("ValueError", "oops")]),
        ])
        nb_path = tmp_cwd / "error.ipynb"
        nb_path.write_text(json.dumps(nb), encoding="utf-8")

        inp = NotebookReadInput(file_path=str(nb_path))
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        cell_outputs = result.data["cells"][0]["outputs"]
        assert len(cell_outputs) == 1
        assert cell_outputs[0]["ename"] == "ValueError"
        assert cell_outputs[0]["evalue"] == "oops"

    @pytest.mark.asyncio
    async def test_truncates_long_output(self, tmp_cwd: Any) -> None:
        long_text = "x" * 1000
        nb = _make_notebook([
            _code_cell("print(long)", [_stream_output(long_text)]),
        ])
        nb_path = tmp_cwd / "long.ipynb"
        nb_path.write_text(json.dumps(nb), encoding="utf-8")

        inp = NotebookReadInput(file_path=str(nb_path))
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        output_text = result.data["cells"][0]["outputs"][0]["text"]
        assert "truncated" in output_text
        assert len(output_text) < len(long_text)

    @pytest.mark.asyncio
    async def test_result_for_assistant_format(self, tmp_cwd: Any) -> None:
        nb = _make_notebook([
            _markdown_cell("# Title"),
            _code_cell("print('hi')", [_stream_output("hi\n")]),
        ])
        nb_path = tmp_cwd / "test.ipynb"
        nb_path.write_text(json.dumps(nb), encoding="utf-8")

        inp = NotebookReadInput(file_path=str(nb_path))
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        text = result.result_for_assistant
        assert "Cell 0 (markdown):" in text
        assert "# Title" in text
        assert "Cell 1 (code):" in text
        assert "print('hi')" in text
        assert "Outputs:" in text
