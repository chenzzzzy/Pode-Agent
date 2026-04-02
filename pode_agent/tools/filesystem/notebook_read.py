"""NotebookReadTool: read and display cells from a Jupyter notebook (.ipynb) file.

Reference: docs/api-specs.md — Tool System API, NotebookReadTool
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from pode_agent.core.permissions.rules.file import is_path_in_working_directories
from pode_agent.core.tools.base import Tool, ToolOutput, ToolUseContext
from pode_agent.infra.logging import get_logger

logger = get_logger(__name__)

MAX_OUTPUT_LENGTH = 500


class NotebookReadInput(BaseModel):
    """Input schema for NotebookReadTool."""

    file_path: str = Field(description="Absolute path to the .ipynb file to read")
    cell_index: int | None = Field(
        default=None,
        description="Index of a specific cell to read (0-based). If omitted, all cells are returned.",
    )
    limit: int | None = Field(
        default=None,
        description="Maximum number of cells to return. If omitted, all cells are returned.",
    )


class NotebookReadTool(Tool):
    """Read and display cells from a Jupyter notebook (.ipynb) file."""

    name: str = "notebook_read"
    description: str = (
        "Read and display cells from a Jupyter notebook (.ipynb) file, "
        "including cell types (code/markdown), source content, and outputs."
    )

    def input_schema(self) -> type[BaseModel]:
        return NotebookReadInput

    async def is_enabled(self) -> bool:
        return True

    def is_read_only(self, input: Any = None) -> bool:
        return True

    def needs_permissions(self, input: Any = None) -> bool:
        return False

    def is_concurrency_safe(self, input: Any = None) -> bool:
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
        assert isinstance(input, NotebookReadInput)
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

        if path.is_dir():
            yield ToolOutput(
                type="result",
                data={"error": f"Path is a directory, not a file: {input.file_path}"},
                result_for_assistant=f"Error: Path is a directory: {input.file_path}",
            )
            return

        # Read and parse the notebook JSON
        try:
            raw = path.read_text(encoding="utf-8")
            notebook = json.loads(raw)
        except json.JSONDecodeError as exc:
            yield ToolOutput(
                type="result",
                data={"error": f"Invalid notebook JSON: {exc}"},
                result_for_assistant=f"Error: Invalid notebook JSON in {input.file_path}: {exc}",
            )
            return

        # Extract cells
        cells = notebook.get("cells")
        if not isinstance(cells, list):
            yield ToolOutput(
                type="result",
                data={"error": "Malformed notebook: 'cells' key missing or not a list"},
                result_for_assistant=f"Error: Malformed notebook (no cells array) in {input.file_path}",
            )
            return

        total_cells = len(cells)

        # Apply cell_index filter
        if input.cell_index is not None:
            if input.cell_index < 0 or input.cell_index >= total_cells:
                yield ToolOutput(
                    type="result",
                    data={
                        "error": (
                            f"Cell index {input.cell_index} out of range "
                            f"(notebook has {total_cells} cells, 0-{total_cells - 1})"
                        )
                    },
                    result_for_assistant=(
                        f"Error: Cell index {input.cell_index} out of range "
                        f"(notebook has {total_cells} cells)"
                    ),
                )
                return
            selected = [(input.cell_index, cells[input.cell_index])]
        else:
            selected = list(enumerate(cells))

        # Apply limit
        if input.limit is not None and input.limit >= 0:
            selected = selected[: input.limit]

        # Format each cell
        formatted_cells: list[dict[str, Any]] = []
        for idx, cell in selected:
            cell_type = cell.get("cell_type", "unknown")
            source = cell.get("source", "")
            if isinstance(source, list):
                source = "".join(source)

            # Extract and truncate outputs
            outputs = cell.get("outputs", [])
            formatted_outputs = _format_outputs(outputs)

            formatted_cells.append({
                "cell_number": idx,
                "cell_type": cell_type,
                "source": source,
                "outputs": formatted_outputs,
            })

        result_text = _render_cells(formatted_cells)

        yield ToolOutput(
            type="result",
            data={
                "file_path": str(path),
                "total_cells": total_cells,
                "cells": formatted_cells,
            },
            result_for_assistant=result_text,
        )


def _format_outputs(outputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract and truncate cell outputs."""
    formatted: list[dict[str, Any]] = []
    for output in outputs:
        output_type = output.get("output_type", "unknown")
        entry: dict[str, Any] = {"output_type": output_type}

        if output_type == "stream":
            text = output.get("text", "")
            if isinstance(text, list):
                text = "".join(text)
            entry["text"] = _truncate(text)
        elif output_type in ("execute_result", "display_data"):
            data = output.get("data", {})
            if "text/plain" in data:
                text = data["text/plain"]
                if isinstance(text, list):
                    text = "".join(text)
                entry["text"] = _truncate(text)
        elif output_type == "error":
            traceback = output.get("traceback", [])
            entry["ename"] = output.get("ename", "")
            entry["evalue"] = output.get("evalue", "")
            entry["traceback"] = [_truncate(line) for line in traceback]

        formatted.append(entry)
    return formatted


def _truncate(text: str) -> str:
    """Truncate text to MAX_OUTPUT_LENGTH characters."""
    if len(text) > MAX_OUTPUT_LENGTH:
        return text[:MAX_OUTPUT_LENGTH] + "... (truncated)"
    return text


def _render_cells(cells: list[dict[str, Any]]) -> str:
    """Render cells into a human-readable string for the assistant."""
    parts: list[str] = []
    for cell in cells:
        idx = cell["cell_number"]
        cell_type = cell["cell_type"]
        source = cell["source"]
        outputs = cell["outputs"]

        header = f"Cell {idx} ({cell_type}):"
        parts.append(header)
        parts.append(source)
        if outputs:
            parts.append("Outputs:")
            for out in outputs:
                output_type = out.get("output_type", "unknown")
                if "text" in out:
                    parts.append(f"  [{output_type}] {out['text']}")
                elif "ename" in out:
                    parts.append(f"  [{output_type}] {out['ename']}: {out['evalue']}")
                else:
                    parts.append(f"  [{output_type}]")
        parts.append("")  # blank line between cells
    return "\n".join(parts)
