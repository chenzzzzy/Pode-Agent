"""FileReadTool: read file contents with optional line range.

Reference: docs/api-specs.md — Tool System API, FileReadTool
"""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from pode_agent.core.permissions.rules.file import is_path_in_working_directories
from pode_agent.core.tools.base import Tool, ToolOutput, ToolUseContext
from pode_agent.infra.logging import get_logger

logger = get_logger(__name__)

MAX_LINE_LENGTH = 2000
DEFAULT_READ_LIMIT = 2000


class FileReadInput(BaseModel):
    """Input schema for FileReadTool."""

    file_path: str = Field(description="Absolute path to the file to read")
    offset: int = Field(default=0, description="Line number to start reading from (0-based)")
    limit: int | None = Field(
        default=None,
        description="Number of lines to read (None = all remaining)",
    )


class FileReadTool(Tool):
    """Read a file and return its contents with line numbers."""

    name: str = "file_read"
    description: str = "Read file contents with optional line range"

    def input_schema(self) -> type[BaseModel]:
        return FileReadInput

    async def is_enabled(self) -> bool:
        return True

    def is_read_only(self, input: Any = None) -> bool:
        return True

    def needs_permissions(self, input: Any = None) -> bool:
        return False

    async def call(
        self,
        input: BaseModel,
        context: ToolUseContext,
    ) -> AsyncGenerator[ToolOutput, None]:
        assert isinstance(input, FileReadInput)
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

        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            yield ToolOutput(
                type="result",
                data={"error": f"Binary file cannot be read as text: {input.file_path}"},
                result_for_assistant=f"Error: Binary file: {input.file_path}",
            )
            return

        # Split into lines and apply offset/limit
        lines = content.splitlines(keepends=True)
        total_lines = len(lines)
        offset = max(0, input.offset)
        end = len(lines) if input.limit is None else offset + input.limit
        selected = lines[offset:end]

        # Truncate long lines
        truncated: list[str] = []
        for line in selected:
            if len(line) > MAX_LINE_LENGTH:
                truncated.append(line[:MAX_LINE_LENGTH] + "... (truncated)\n")
            else:
                truncated.append(line)

        # Format with line numbers
        numbered = _add_line_numbers(truncated, start=offset)
        result_text = "".join(numbered)

        # Record read timestamp
        context.read_file_timestamps[str(path)] = time.time()

        yield ToolOutput(
            type="result",
            data={
                "file_path": str(path),
                "content": result_text,
                "start_line": offset,
                "total_lines": total_lines,
                "lines_read": len(truncated),
            },
            result_for_assistant=result_text,
        )

    def render_result_for_assistant(self, output: Any) -> str | list[Any]:
        if isinstance(output, dict) and "error" in output:
            return str(output["error"])
        return str(output)


def _add_line_numbers(lines: list[str], start: int = 0) -> list[str]:
    """Prepend line numbers to each line (1-based display)."""
    width = len(str(start + len(lines)))
    return [
        f"{i + start + 1:>{width}}→{line}" if line.endswith("\n") else f"{i + start + 1:>{width}}→{line}\n"
        for i, line in enumerate(lines)
    ]
