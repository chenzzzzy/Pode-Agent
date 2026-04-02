"""NotebookEditTool: edit Jupyter notebook (.ipynb) files.

Supports add, edit, delete, and clear_output operations on notebook cells.

Reference: docs/api-specs.md — Tool System API, NotebookEditTool
"""

from __future__ import annotations

import copy
import json
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from pode_agent.core.permissions.rules.file import is_path_in_working_directories
from pode_agent.core.tools.base import Tool, ToolOutput, ToolUseContext
from pode_agent.infra.fs import atomic_write
from pode_agent.infra.logging import get_logger

logger = get_logger(__name__)

# Minimal nbformat structure constants
_NBFORMAT_MAJOR = 4
_NBFORMAT_MINOR = 5


def _make_cell(cell_type: str, source: str) -> dict[str, Any]:
    """Create a new notebook cell dict."""
    return {
        "cell_type": cell_type,
        "metadata": {},
        "source": source,
        "id": _generate_cell_id(),
        **({"outputs": [], "execution_count": None} if cell_type == "code" else {}),
    }


def _generate_cell_id() -> str:
    """Generate a simple unique cell ID."""
    import uuid

    return uuid.uuid4().hex[:8]


class NotebookEditInput(BaseModel):
    """Input schema for NotebookEditTool."""

    file_path: str = Field(description="Absolute path to the .ipynb file to edit")
    operation: Literal["add", "edit", "delete", "clear_output"] = Field(
        description="Operation to perform: add, edit, delete, or clear_output"
    )
    cell_index: int | None = Field(
        default=None,
        description=(
            "Index of the cell to operate on (0-based). "
            "Required for edit, delete, and clear_output operations."
        ),
    )
    source: str | None = Field(
        default=None,
        description="New source content for the cell. Required for add and edit operations.",
    )
    cell_type: Literal["code", "markdown"] | None = Field(
        default=None,
        description="Type of cell to add. Required for add operation.",
    )


class NotebookEditTool(Tool):
    """Edit a Jupyter notebook (.ipynb) file by manipulating cells."""

    name: str = "notebook_edit"
    description: str = (
        "Edit a Jupyter notebook (.ipynb) file by adding, editing, "
        "deleting cells or clearing cell outputs"
    )

    def input_schema(self) -> type[BaseModel]:
        return NotebookEditInput

    async def is_enabled(self) -> bool:
        return True

    def is_read_only(self, input: Any = None) -> bool:
        return False

    def is_concurrency_safe(self, input: Any = None) -> bool:
        return False

    def needs_permissions(self, input: Any = None) -> bool:
        return True

    def render_result_for_assistant(self, output: Any) -> str | list[Any]:
        if isinstance(output, dict) and "error" in output:
            return str(output["error"])
        return str(output)

    async def call(
        self,
        input: BaseModel,
        context: ToolUseContext,
    ) -> AsyncGenerator[ToolOutput, None]:
        assert isinstance(input, NotebookEditInput)
        path = Path(input.file_path).resolve()

        # Security check
        if not is_path_in_working_directories(str(path)):
            yield ToolOutput(
                type="result",
                data={"error": f"Path outside working directory: {input.file_path}"},
                result_for_assistant=f"Error: Path outside working directory: {input.file_path}",
            )
            return

        if not path.exists():
            yield ToolOutput(
                type="result",
                data={"error": f"File not found: {input.file_path}"},
                result_for_assistant=f"Error: File not found: {input.file_path}",
            )
            return

        if path.suffix != ".ipynb":
            yield ToolOutput(
                type="result",
                data={"error": f"Not a notebook file: {input.file_path}"},
                result_for_assistant=f"Error: Not a notebook file: {input.file_path}",
            )
            return

        # Read and parse notebook
        try:
            nb = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            yield ToolOutput(
                type="result",
                data={"error": f"Invalid JSON in notebook: {exc}"},
                result_for_assistant=f"Error: Invalid JSON in notebook: {exc}",
            )
            return

        # Validate minimal nbformat structure
        if "cells" not in nb or not isinstance(nb["cells"], list):
            yield ToolOutput(
                type="result",
                data={"error": "Invalid notebook: missing 'cells' array"},
                result_for_assistant="Error: Invalid notebook: missing 'cells' array",
            )
            return

        cells = nb["cells"]

        # Validate operation-specific required fields
        error = self._validate_operation(input)
        if error:
            yield ToolOutput(
                type="result",
                data={"error": error},
                result_for_assistant=f"Error: {error}",
            )
            return

        # Deep copy to avoid mutating the original
        nb = copy.deepcopy(nb)
        cells = nb["cells"]

        # Apply the operation
        if input.operation == "add":
            new_cell = _make_cell(input.cell_type or "code", input.source or "")
            if input.cell_index is not None:
                cells.insert(input.cell_index, new_cell)
            else:
                cells.append(new_cell)
            summary = (
                f"Added {input.cell_type or 'code'} cell at "
                f"index {input.cell_index if input.cell_index is not None else len(cells) - 1}"
            )

        elif input.operation == "edit":
            assert input.cell_index is not None
            cells[input.cell_index]["source"] = input.source or ""
            summary = f"Edited cell at index {input.cell_index}"

        elif input.operation == "delete":
            assert input.cell_index is not None
            del cells[input.cell_index]
            summary = f"Deleted cell at index {input.cell_index}"

        elif input.operation == "clear_output":
            assert input.cell_index is not None
            cell = cells[input.cell_index]
            if cell.get("cell_type") == "code":
                cell["outputs"] = []
                cell["execution_count"] = None
            summary = f"Cleared output of cell at index {input.cell_index}"

        else:
            yield ToolOutput(
                type="result",
                data={"error": f"Unknown operation: {input.operation}"},
                result_for_assistant=f"Error: Unknown operation: {input.operation}",
            )
            return

        # Write back
        atomic_write(path, json.dumps(nb, indent=1, ensure_ascii=False) + "\n")

        yield ToolOutput(
            type="result",
            data={
                "file_path": str(path),
                "operation": input.operation,
                "total_cells": len(cells),
            },
            result_for_assistant=f"{summary} in {path} ({len(cells)} cells total)",
        )

    @staticmethod
    def _validate_operation(input: NotebookEditInput) -> str | None:
        """Validate that required fields are present for the given operation.

        Returns an error message string if validation fails, None on success.
        """
        op = input.operation

        if op in ("edit", "delete", "clear_output") and input.cell_index is None:
            return f"cell_index is required for {op} operation"

        if op == "add" and input.source is None:
            return "source is required for add operation"

        if op == "add" and input.cell_type is None:
            return "cell_type is required for add operation"

        if op == "edit" and input.source is None:
            return "source is required for edit operation"

        return None
