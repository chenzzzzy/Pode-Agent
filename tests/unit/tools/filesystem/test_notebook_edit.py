"""Unit tests for NotebookEditTool.

Reference: docs/api-specs.md — Tool System API
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from pode_agent.core.tools.base import ToolOutput, ToolUseContext
from pode_agent.tools.filesystem.notebook_edit import (
    NotebookEditInput,
    NotebookEditTool,
)


def _ctx() -> ToolUseContext:
    return ToolUseContext(abort_event=asyncio.Event())


def _find_result(outputs: list[ToolOutput]) -> ToolOutput:
    for o in reversed(outputs):
        if o.type == "result":
            return o
    raise AssertionError("No result output found")


def _sample_notebook() -> dict[str, Any]:
    """Return a minimal valid notebook dict."""
    return {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {},
        "cells": [
            {
                "cell_type": "code",
                "id": "abc123",
                "metadata": {},
                "source": "print('hello')",
                "outputs": [
                    {
                        "output_type": "stream",
                        "name": "stdout",
                        "text": ["hello\n"],
                    }
                ],
                "execution_count": 1,
            },
            {
                "cell_type": "markdown",
                "id": "def456",
                "metadata": {},
                "source": "# Title",
            },
        ],
    }


def _write_notebook(path: Path, nb: dict[str, Any] | None = None) -> Path:
    """Write a sample notebook to disk and return the path."""
    if nb is None:
        nb = _sample_notebook()
    path.write_text(json.dumps(nb, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# NotebookEditTool — Properties
# ---------------------------------------------------------------------------


class TestNotebookEditToolProperties:
    def setup_method(self) -> None:
        self.tool = NotebookEditTool()

    def test_name(self) -> None:
        assert self.tool.name == "notebook_edit"

    def test_input_schema(self) -> None:
        assert self.tool.input_schema() is NotebookEditInput

    def test_is_read_only(self) -> None:
        assert self.tool.is_read_only() is False

    def test_needs_permissions(self) -> None:
        assert self.tool.needs_permissions() is True

    def test_is_concurrency_safe(self) -> None:
        assert self.tool.is_concurrency_safe() is False

    @pytest.mark.asyncio
    async def test_is_enabled(self) -> None:
        assert await self.tool.is_enabled() is True


# ---------------------------------------------------------------------------
# NotebookEditTool — Call
# ---------------------------------------------------------------------------


class TestNotebookEditToolCall:
    def setup_method(self) -> None:
        self.tool = NotebookEditTool()

    @pytest.mark.asyncio
    async def test_add_code_cell(self, tmp_cwd: Any) -> None:
        nb_path = _write_notebook(tmp_cwd / "test.ipynb")

        inp = NotebookEditInput(
            file_path=str(nb_path),
            operation="add",
            cell_type="code",
            source="x = 42",
        )
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert result.data["operation"] == "add"
        assert result.data["total_cells"] == 3

        nb = json.loads(nb_path.read_text(encoding="utf-8"))
        assert nb["cells"][2]["cell_type"] == "code"
        assert nb["cells"][2]["source"] == "x = 42"

    @pytest.mark.asyncio
    async def test_add_markdown_cell(self, tmp_cwd: Any) -> None:
        nb_path = _write_notebook(tmp_cwd / "test.ipynb")

        inp = NotebookEditInput(
            file_path=str(nb_path),
            operation="add",
            cell_type="markdown",
            source="## Section",
        )
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert result.data["total_cells"] == 3

        nb = json.loads(nb_path.read_text(encoding="utf-8"))
        assert nb["cells"][2]["cell_type"] == "markdown"
        assert nb["cells"][2]["source"] == "## Section"

    @pytest.mark.asyncio
    async def test_add_cell_at_index(self, tmp_cwd: Any) -> None:
        nb_path = _write_notebook(tmp_cwd / "test.ipynb")

        inp = NotebookEditInput(
            file_path=str(nb_path),
            operation="add",
            cell_type="code",
            source="import os",
            cell_index=0,
        )
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        _find_result(outputs)

        nb = json.loads(nb_path.read_text(encoding="utf-8"))
        assert nb["cells"][0]["source"] == "import os"
        assert nb["cells"][1]["source"] == "print('hello')"

    @pytest.mark.asyncio
    async def test_edit_cell_source(self, tmp_cwd: Any) -> None:
        nb_path = _write_notebook(tmp_cwd / "test.ipynb")

        inp = NotebookEditInput(
            file_path=str(nb_path),
            operation="edit",
            cell_index=0,
            source="print('updated')",
        )
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert result.data["operation"] == "edit"

        nb = json.loads(nb_path.read_text(encoding="utf-8"))
        assert nb["cells"][0]["source"] == "print('updated')"

    @pytest.mark.asyncio
    async def test_delete_cell(self, tmp_cwd: Any) -> None:
        nb_path = _write_notebook(tmp_cwd / "test.ipynb")

        inp = NotebookEditInput(
            file_path=str(nb_path),
            operation="delete",
            cell_index=0,
        )
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert result.data["total_cells"] == 1

        nb = json.loads(nb_path.read_text(encoding="utf-8"))
        assert len(nb["cells"]) == 1
        assert nb["cells"][0]["source"] == "# Title"

    @pytest.mark.asyncio
    async def test_clear_cell_output(self, tmp_cwd: Any) -> None:
        nb_path = _write_notebook(tmp_cwd / "test.ipynb")

        inp = NotebookEditInput(
            file_path=str(nb_path),
            operation="clear_output",
            cell_index=0,
        )
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert result.data["operation"] == "clear_output"

        nb = json.loads(nb_path.read_text(encoding="utf-8"))
        assert nb["cells"][0]["outputs"] == []
        assert nb["cells"][0]["execution_count"] is None

    @pytest.mark.asyncio
    async def test_clear_output_on_markdown_cell_is_noop(self, tmp_cwd: Any) -> None:
        """clear_output on a markdown cell should succeed but not crash."""
        nb_path = _write_notebook(tmp_cwd / "test.ipynb")

        inp = NotebookEditInput(
            file_path=str(nb_path),
            operation="clear_output",
            cell_index=1,
        )
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert result.data["operation"] == "clear_output"

        nb = json.loads(nb_path.read_text(encoding="utf-8"))
        # Markdown cell should remain unchanged (no outputs key modified)
        assert nb["cells"][1]["source"] == "# Title"

    @pytest.mark.asyncio
    async def test_invalid_operation_rejected(self, tmp_cwd: Any) -> None:
        """Pydantic should reject an invalid operation value."""
        with pytest.raises(ValidationError):
            NotebookEditInput(
                file_path=str(tmp_cwd / "test.ipynb"),
                operation="invalid",
            )

    @pytest.mark.asyncio
    async def test_edit_without_cell_index_fails(self, tmp_cwd: Any) -> None:
        """edit operation requires cell_index."""
        nb_path = _write_notebook(tmp_cwd / "test.ipynb")

        inp = NotebookEditInput(
            file_path=str(nb_path),
            operation="edit",
            source="new source",
        )
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert "error" in result.data
        assert "cell_index is required" in result.data["error"]

    @pytest.mark.asyncio
    async def test_edit_without_source_fails(self, tmp_cwd: Any) -> None:
        """edit operation requires source."""
        nb_path = _write_notebook(tmp_cwd / "test.ipynb")

        inp = NotebookEditInput(
            file_path=str(nb_path),
            operation="edit",
            cell_index=0,
        )
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert "error" in result.data
        assert "source is required" in result.data["error"]

    @pytest.mark.asyncio
    async def test_add_without_source_fails(self, tmp_cwd: Any) -> None:
        """add operation requires source."""
        nb_path = _write_notebook(tmp_cwd / "test.ipynb")

        inp = NotebookEditInput(
            file_path=str(nb_path),
            operation="add",
            cell_type="code",
        )
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert "error" in result.data
        assert "source is required" in result.data["error"]

    @pytest.mark.asyncio
    async def test_add_without_cell_type_fails(self, tmp_cwd: Any) -> None:
        """add operation requires cell_type."""
        nb_path = _write_notebook(tmp_cwd / "test.ipynb")

        inp = NotebookEditInput(
            file_path=str(nb_path),
            operation="add",
            source="x = 1",
        )
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert "error" in result.data
        assert "cell_type is required" in result.data["error"]

    @pytest.mark.asyncio
    async def test_delete_without_cell_index_fails(self, tmp_cwd: Any) -> None:
        """delete operation requires cell_index."""
        nb_path = _write_notebook(tmp_cwd / "test.ipynb")

        inp = NotebookEditInput(
            file_path=str(nb_path),
            operation="delete",
        )
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert "error" in result.data
        assert "cell_index is required" in result.data["error"]

    @pytest.mark.asyncio
    async def test_path_outside_cwd_rejected(self, tmp_cwd: Any) -> None:
        inp = NotebookEditInput(
            file_path="/etc/notebooks/evil.ipynb",
            operation="add",
            cell_type="code",
            source="x = 1",
        )
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert "error" in result.data
        assert "outside" in result.data["error"]

    @pytest.mark.asyncio
    async def test_path_traversal_rejected(self, tmp_cwd: Any) -> None:
        inp = NotebookEditInput(
            file_path=str(tmp_cwd / "test.ipynb" / ".." / ".." / "etc" / "passwd"),
            operation="delete",
            cell_index=0,
        )
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert "error" in result.data

    @pytest.mark.asyncio
    async def test_nonexistent_file_rejected(self, tmp_cwd: Any) -> None:
        inp = NotebookEditInput(
            file_path=str(tmp_cwd / "missing.ipynb"),
            operation="add",
            cell_type="code",
            source="x = 1",
        )
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert "error" in result.data
        assert "not found" in result.data["error"]

    @pytest.mark.asyncio
    async def test_non_ipynb_file_rejected(self, tmp_cwd: Any) -> None:
        f = tmp_cwd / "test.txt"
        f.write_text("not a notebook")

        inp = NotebookEditInput(
            file_path=str(f),
            operation="add",
            cell_type="code",
            source="x = 1",
        )
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert "error" in result.data
        assert "not a notebook" in result.data["error"].lower()

    @pytest.mark.asyncio
    async def test_invalid_json_rejected(self, tmp_cwd: Any) -> None:
        f = tmp_cwd / "bad.ipynb"
        f.write_text("{invalid json!!!")

        inp = NotebookEditInput(
            file_path=str(f),
            operation="add",
            cell_type="code",
            source="x = 1",
        )
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert "error" in result.data
        assert "Invalid JSON" in result.data["error"]

    @pytest.mark.asyncio
    async def test_missing_cells_array_rejected(self, tmp_cwd: Any) -> None:
        f = tmp_cwd / "nocells.ipynb"
        f.write_text(json.dumps({"nbformat": 4, "metadata": {}}))

        inp = NotebookEditInput(
            file_path=str(f),
            operation="add",
            cell_type="code",
            source="x = 1",
        )
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert "error" in result.data
        assert "cells" in result.data["error"]

    @pytest.mark.asyncio
    async def test_render_result_for_assistant_error(self) -> None:
        rendered = self.tool.render_result_for_assistant({"error": "something broke"})
        assert "something broke" in rendered

    @pytest.mark.asyncio
    async def test_render_result_for_assistant_success(self) -> None:
        rendered = self.tool.render_result_for_assistant({"operation": "add", "total_cells": 3})
        assert "add" in str(rendered)
