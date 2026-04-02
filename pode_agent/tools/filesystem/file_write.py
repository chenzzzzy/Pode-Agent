"""FileWriteTool: create or overwrite files.

Reference: docs/api-specs.md — Tool System API, FileWriteTool
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from pode_agent.core.permissions.rules.file import is_path_in_working_directories
from pode_agent.core.tools.base import Tool, ToolOutput, ToolUseContext
from pode_agent.infra.fs import atomic_write, ensure_dir
from pode_agent.infra.logging import get_logger

logger = get_logger(__name__)


class FileWriteInput(BaseModel):
    """Input schema for FileWriteTool."""

    file_path: str = Field(description="Absolute path to the file to write")
    content: str = Field(description="Content to write to the file")


class FileWriteTool(Tool):
    """Create or overwrite a file with the given content."""

    name: str = "file_write"
    description: str = "Write content to a file, creating it if it does not exist"

    def input_schema(self) -> type[BaseModel]:
        return FileWriteInput

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
        assert isinstance(input, FileWriteInput)
        path = Path(input.file_path).resolve()

        # Security check
        if not is_path_in_working_directories(str(path)):
            yield ToolOutput(
                type="result",
                data={"error": f"Path outside working directory: {input.file_path}"},
                result_for_assistant=f"Error: Path outside working directory: {input.file_path}",
            )
            return

        is_update = path.exists()

        # Create parent directories if needed
        ensure_dir(path.parent)

        # Write atomically
        atomic_write(path, input.content)

        action = "Updated" if is_update else "Created"
        summary = f"{action} {path} ({len(input.content.splitlines())} lines)"

        yield ToolOutput(
            type="result",
            data={
                "file_path": str(path),
                "action": action.lower(),
                "lines": len(input.content.splitlines()),
            },
            result_for_assistant=summary,
        )

    def render_result_for_assistant(self, output: Any) -> str | list[Any]:
        if isinstance(output, dict) and "error" in output:
            return str(output["error"])
        return str(output)
