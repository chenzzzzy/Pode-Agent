"""FileEditTool: precise string replacement in files.

Reference: docs/api-specs.md — Tool System API, FileEditTool
"""

from __future__ import annotations

import difflib
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from pode_agent.core.permissions.rules.file import is_path_in_working_directories
from pode_agent.core.tools.base import Tool, ToolOutput, ToolUseContext
from pode_agent.infra.fs import atomic_write
from pode_agent.infra.logging import get_logger

logger = get_logger(__name__)


class FileEditInput(BaseModel):
    """Input schema for FileEditTool."""

    file_path: str = Field(description="Absolute path to the file to modify")
    old_str: str = Field(description="Text to find and replace")
    new_str: str = Field(description="Text to replace it with")


class FileEditTool(Tool):
    """Perform a precise string replacement in a file."""

    name: str = "file_edit"
    description: str = "Replace exact text in a file (old_str -> new_str)"

    def input_schema(self) -> type[BaseModel]:
        return FileEditInput

    async def is_enabled(self) -> bool:
        return True

    def is_read_only(self, input: Any = None) -> bool:
        return False

    def needs_permissions(self, input: Any = None) -> bool:
        return True

    async def call(
        self,
        input: BaseModel,
        context: ToolUseContext,
    ) -> AsyncGenerator[ToolOutput, None]:
        assert isinstance(input, FileEditInput)
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

        if input.old_str == input.new_str:
            yield ToolOutput(
                type="result",
                data={"error": "old_str and new_str are identical — no change needed"},
                result_for_assistant="Error: old_str and new_str are identical",
            )
            return

        content = path.read_text(encoding="utf-8")

        # Check for uniqueness
        count = content.count(input.old_str)
        if count == 0:
            yield ToolOutput(
                type="result",
                data={"error": f"old_str not found in {input.file_path}"},
                result_for_assistant=f"Error: old_str not found in {input.file_path}",
            )
            return

        if count > 1:
            yield ToolOutput(
                type="result",
                data={
                    "error": (
                        f"old_str appears {count} times in {input.file_path}. "
                        "The replacement must be unique — provide more surrounding "
                        "context to make the match unambiguous."
                    ),
                },
                result_for_assistant=(
                    f"Error: old_str appears {count} times — provide more context "
                    "for a unique match"
                ),
            )
            return

        # Perform the replacement
        new_content = content.replace(input.old_str, input.new_str, 1)
        atomic_write(path, new_content)

        # Generate diff
        diff_lines = list(difflib.unified_diff(
            content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=str(path),
            tofile=str(path),
        ))
        diff_text = "".join(diff_lines)

        summary = f"Edited {path}: replaced 1 occurrence"

        yield ToolOutput(
            type="result",
            data={
                "file_path": str(path),
                "diff": diff_text,
                "replacements": 1,
            },
            result_for_assistant=f"{summary}\n{diff_text}",
        )

    def render_result_for_assistant(self, output: Any) -> str | list[Any]:
        if isinstance(output, dict) and "error" in output:
            return str(output["error"])
        return str(output)
