"""GrepTool: search file contents with regex patterns.

Prefers ripgrep (rg) when available, falls back to Python re module.

Reference: docs/api-specs.md — Tool System API, GrepTool
"""

from __future__ import annotations

import re
import shutil
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from pode_agent.core.permissions.rules.file import is_path_in_working_directories
from pode_agent.core.tools.base import Tool, ToolOutput, ToolUseContext
from pode_agent.infra.logging import get_logger

logger = get_logger(__name__)

MAX_RESULT_CHARS = 20_000
DEFAULT_GREP_LIMIT = 100

# Map file type names to extensions for Python fallback
FILE_TYPE_EXTENSIONS: dict[str, list[str]] = {
    "py": [".py"],
    "js": [".js", ".mjs", ".cjs"],
    "ts": [".ts", ".tsx"],
    "rs": [".rs"],
    "go": [".go"],
    "java": [".java"],
    "rb": [".rb"],
    "cpp": [".cpp", ".cxx", ".cc", ".hpp"],
    "c": [".c", ".h"],
    "cs": [".cs"],
    "swift": [".swift"],
    "kt": [".kt", ".kts"],
    "md": [".md", ".markdown"],
    "json": [".json"],
    "yaml": [".yaml", ".yml"],
    "toml": [".toml"],
}


class GrepInput(BaseModel):
    """Input schema for GrepTool."""

    pattern: str = Field(description="Regular expression pattern to search for")
    path: str | None = Field(default=None, description="File or directory to search in")
    ignore_case: bool = Field(default=False, description="Case-insensitive search")
    show_line_numbers: bool = Field(default=True, description="Show line numbers in output")
    files_only: bool = Field(
        default=False,
        description="Only show file paths, not matching content",
    )
    file_type: str | None = Field(
        default=None,
        description="Filter by file type (e.g. 'py', 'js')",
    )
    limit: int = Field(default=DEFAULT_GREP_LIMIT, description="Maximum number of results")


class GrepTool(Tool):
    """Search file contents for a regex pattern."""

    name: str = "grep"
    description: str = "Search file contents with regex pattern matching"

    def input_schema(self) -> type[BaseModel]:
        return GrepInput

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
        assert isinstance(input, GrepInput)
        search_path = Path(input.path).resolve() if input.path else Path.cwd()

        if not is_path_in_working_directories(str(search_path)):
            yield ToolOutput(
                type="result",
                data={"error": f"Path outside working directory: {input.path}"},
                result_for_assistant=f"Error: Path outside working directory: {input.path}",
            )
            return

        if not search_path.exists():
            yield ToolOutput(
                type="result",
                data={"error": f"Path not found: {input.path}"},
                result_for_assistant=f"Error: Path not found: {input.path}",
            )
            return

        # Try ripgrep first
        if shutil.which("rg"):
            result_text, file_count = await self._grep_ripgrep(input, search_path)
        else:
            result_text, file_count = self._grep_python(input, search_path)

        if not result_text:
            yield ToolOutput(
                type="result",
                data={"files": [], "total": 0, "content": ""},
                result_for_assistant="(no matches found)",
            )
            return

        yield ToolOutput(
            type="result",
            data={
                "files": [],  # populated in result_text
                "total": file_count,
                "content": result_text,
            },
            result_for_assistant=result_text,
        )

    async def _grep_ripgrep(
        self, input: GrepInput, search_path: Path,
    ) -> tuple[str, int]:
        """Use ripgrep for search."""
        from pode_agent.infra.shell import execute_command

        args = ["rg"]
        if input.ignore_case:
            args.append("-i")
        if input.files_only:
            args.append("-l")
        else:
            args.append("-n")  # line numbers

        if input.file_type:
            args.extend(["--type", input.file_type])

        args.extend([
            "--max-count", str(input.limit),
            input.pattern,
            str(search_path),
        ])

        result = await execute_command(args)
        if result.exit_code == 2:
            # rg error (bad regex, etc.)
            return f"ripgrep error: {result.stderr}", 0

        content = result.stdout
        if len(content) > MAX_RESULT_CHARS:
            content = content[:MAX_RESULT_CHARS] + "\n... (truncated)"

        file_count = len(set(
            line.split(":")[0]
            for line in content.splitlines()
            if ":" in line
        ))

        return content, file_count

    def _grep_python(
        self, input: GrepInput, search_path: Path,
    ) -> tuple[str, int]:
        """Pure-Python fallback when ripgrep is unavailable."""
        flags = re.IGNORECASE if input.ignore_case else 0
        try:
            regex = re.compile(input.pattern, flags)
        except re.error as e:
            return f"Invalid regex: {e}", 0

        # Determine extensions filter
        extensions: set[str] | None = None
        if input.file_type and input.file_type in FILE_TYPE_EXTENSIONS:
            extensions = set(FILE_TYPE_EXTENSIONS[input.file_type])

        # Collect files
        if search_path.is_file():
            files = [search_path]
        else:
            files = [
                f
                for f in search_path.rglob("*")
                if f.is_file()
                and not any(p.startswith(".") for p in f.relative_to(search_path).parts)
                and (extensions is None or f.suffix in extensions)
            ]

        lines: list[str] = []
        matched_files: set[str] = set()
        count = 0

        for fpath in files:
            try:
                text = fpath.read_text(encoding="utf-8", errors="replace")
            except (OSError, PermissionError):
                continue

            for i, line in enumerate(text.splitlines(), 1):
                if regex.search(line):
                    count += 1
                    matched_files.add(str(fpath))

                    if input.files_only:
                        if str(fpath) not in matched_files or len(matched_files) == 1:
                            lines.append(str(fpath))
                    elif input.show_line_numbers:
                        rel = str(fpath.relative_to(search_path))
                        lines.append(f"{rel}:{i}:{line}")
                    else:
                        rel = str(fpath.relative_to(search_path))
                        lines.append(f"{rel}:{line}")

                    if count >= input.limit:
                        break
            if count >= input.limit:
                break

        content = (
            "\n".join(sorted(matched_files))
            if input.files_only
            else "\n".join(lines)
        )

        if len(content) > MAX_RESULT_CHARS:
            content = content[:MAX_RESULT_CHARS] + "\n... (truncated)"

        return content, len(matched_files)

    def render_result_for_assistant(self, output: Any) -> str | list[Any]:
        if isinstance(output, dict) and "error" in output:
            return str(output["error"])
        return str(output)
