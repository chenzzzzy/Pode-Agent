"""GlobTool: find files matching a glob pattern.

Reference: docs/api-specs.md — Tool System API, GlobTool
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from pode_agent.core.permissions.rules.file import is_path_in_working_directories
from pode_agent.core.tools.base import Tool, ToolOutput, ToolUseContext
from pode_agent.infra.logging import get_logger

logger = get_logger(__name__)

DEFAULT_GLOB_LIMIT = 100


class GlobInput(BaseModel):
    """Input schema for GlobTool."""

    pattern: str = Field(description='Glob pattern to match (e.g. "**/*.py")')
    path: str | None = Field(default=None, description="Directory to search in (defaults to cwd)")
    limit: int = Field(default=DEFAULT_GLOB_LIMIT, description="Maximum number of results")


class GlobTool(Tool):
    """Find files matching a glob pattern."""

    name: str = "glob"
    description: str = "Find files matching a glob pattern"

    def input_schema(self) -> type[BaseModel]:
        return GlobInput

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
        assert isinstance(input, GlobInput)
        search_dir = Path(input.path).resolve() if input.path else Path.cwd()

        # Security check
        if not is_path_in_working_directories(str(search_dir)):
            yield ToolOutput(
                type="result",
                data={"error": f"Path outside working directory: {input.path}"},
                result_for_assistant=f"Error: Path outside working directory: {input.path}",
            )
            return

        if not search_dir.exists():
            yield ToolOutput(
                type="result",
                data={"error": f"Directory not found: {input.path}"},
                result_for_assistant=f"Error: Directory not found: {input.path}",
            )
            return

        matches = sorted(search_dir.glob(input.pattern))
        # Filter to files only (not directories)
        file_matches = [m for m in matches if m.is_file()]

        truncated = False
        if len(file_matches) > input.limit:
            file_matches = file_matches[: input.limit]
            truncated = True

        # Convert to relative paths
        try:
            rel_paths = [str(m.relative_to(search_dir)) for m in file_matches]
        except ValueError:
            rel_paths = [str(m) for m in file_matches]

        result_text = "\n".join(rel_paths)
        if truncated:
            result_text += f"\n... (truncated at {input.limit} results)"

        yield ToolOutput(
            type="result",
            data={
                "files": rel_paths,
                "total": len(file_matches),
                "truncated": truncated,
            },
            result_for_assistant=result_text or "(no files found)",
        )

    def render_result_for_assistant(self, output: Any) -> str | list[Any]:
        if isinstance(output, dict) and "error" in output:
            return str(output["error"])
        return str(output)
