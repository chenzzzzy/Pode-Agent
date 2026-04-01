"""LsTool: list directory contents.

Reference: docs/api-specs.md — Tool System API, LsTool
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

MAX_FILES = 1000

# Common directories to skip
SKIP_DIRS = frozenset([
    "__pycache__", ".git", ".svn", ".hg", ".bzr",
    "node_modules", ".venv", "venv", ".tox", ".mypy_cache",
    ".pytest_cache", ".ruff_cache",
])


class LsInput(BaseModel):
    """Input schema for LsTool."""

    path: str | None = Field(default=None, description="Directory path to list (defaults to cwd)")


class LsTool(Tool):
    """List directory contents with file type indicators."""

    name: str = "ls"
    description: str = "List directory contents"

    def input_schema(self) -> type[BaseModel]:
        return LsInput

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
        assert isinstance(input, LsInput)
        target = Path(input.path).resolve() if input.path else Path.cwd()

        if not is_path_in_working_directories(str(target)):
            yield ToolOutput(
                type="result",
                data={"error": f"Path outside working directory: {input.path}"},
                result_for_assistant=f"Error: Path outside working directory: {input.path}",
            )
            return

        if not target.exists():
            yield ToolOutput(
                type="result",
                data={"error": f"Directory not found: {target}"},
                result_for_assistant=f"Error: Directory not found: {target}",
            )
            return

        if not target.is_dir():
            yield ToolOutput(
                type="result",
                data={"error": f"Not a directory: {target}"},
                result_for_assistant=f"Error: Not a directory: {target}",
            )
            return

        entries: list[dict[str, str]] = []
        count = 0

        try:
            items = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            yield ToolOutput(
                type="result",
                data={"error": f"Permission denied: {target}"},
                result_for_assistant=f"Error: Permission denied: {target}",
            )
            return

        for item in items:
            name = item.name
            # Skip hidden files and common skip dirs
            if name.startswith(".") or name in SKIP_DIRS:
                continue

            if item.is_dir():
                entry_type = "dir"
            elif item.is_symlink():
                entry_type = "link"
            else:
                entry_type = "file"

            entries.append({"name": name, "type": entry_type})
            count += 1
            if count >= MAX_FILES:
                break

        # Format output
        lines: list[str] = []
        for entry in entries:
            indicator = "/" if entry["type"] == "dir" else ("@" if entry["type"] == "link" else "")
            lines.append(f"  {entry['name']}{indicator}")

        result_text = "\n".join(lines) if lines else "(empty directory)"
        if count >= MAX_FILES:
            result_text += f"\n... (truncated at {MAX_FILES} entries)"

        yield ToolOutput(
            type="result",
            data={"entries": entries, "total": count},
            result_for_assistant=result_text,
        )

    def render_result_for_assistant(self, output: Any) -> str | list[Any]:
        if isinstance(output, dict) and "error" in output:
            return str(output["error"])
        return str(output)
