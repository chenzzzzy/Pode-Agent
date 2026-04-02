"""MultiEditTool: atomic multi-file string replacement.

Applies multiple edit operations across one or more files. All edits are
validated before any file is modified, ensuring atomic semantics — if any
edit is invalid, no files are changed.

Reference: docs/api-specs.md — Tool System API, MultiEditTool
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


class EditOperation(BaseModel):
    """A single string-replacement operation within a file."""

    file_path: str = Field(description="Absolute path to the file to modify")
    old_str: str = Field(description="Text to find and replace")
    new_str: str = Field(description="Text to replace it with")


class MultiEditInput(BaseModel):
    """Input schema for MultiEditTool."""

    edits: list[EditOperation] = Field(
        description="List of edit operations to apply atomically",
    )


class MultiEditTool(Tool):
    """Apply multiple file edits atomically across one or more files.

    All edits are validated first — if any single edit is invalid (bad path,
    missing old_str, ambiguous match), no files are modified.
    """

    name: str = "multi_edit"
    description: str = (
        "Apply multiple file edits atomically across one or more files. "
        "All edits are validated first — if any edit is invalid, no files are changed."
    )

    def input_schema(self) -> type[BaseModel]:
        return MultiEditInput

    async def is_enabled(self) -> bool:
        return True

    def is_read_only(self, input: Any = None) -> bool:
        return False

    def needs_permissions(self, input: Any = None) -> bool:
        return True

    def is_concurrency_safe(self, input: Any = None) -> bool:
        return False

    def render_result_for_assistant(self, output: Any) -> str | list[Any]:
        if isinstance(output, dict) and "error" in output:
            return str(output["error"])
        return str(output)

    async def call(
        self,
        input: BaseModel,
        context: ToolUseContext,
    ) -> AsyncGenerator[ToolOutput, None]:
        assert isinstance(input, MultiEditInput)

        if not input.edits:
            yield ToolOutput(
                type="result",
                data={"error": "No edits provided"},
                result_for_assistant="Error: No edits provided",
            )
            return

        # ------------------------------------------------------------------
        # Phase 1: Validate ALL edits before touching any file.
        # ------------------------------------------------------------------
        # Collect per-file content and validate each edit operation.
        file_contents: dict[str, str] = {}
        file_edits: dict[str, list[EditOperation]] = {}

        for edit in input.edits:
            path = Path(edit.file_path).resolve()

            # Security check
            if not is_path_in_working_directories(str(path)):
                yield ToolOutput(
                    type="result",
                    data={
                        "error": f"Path outside working directory: {edit.file_path}",
                    },
                    result_for_assistant=(
                        f"Error: Path outside working directory: {edit.file_path}"
                    ),
                )
                return

            key = str(path)
            if key not in file_contents:
                if not path.exists():
                    yield ToolOutput(
                        type="result",
                        data={
                            "error": f"File not found: {edit.file_path}",
                        },
                        result_for_assistant=(
                            f"Error: File not found: {edit.file_path}"
                        ),
                    )
                    return
                file_contents[key] = path.read_text(encoding="utf-8")
                file_edits[key] = []

            file_edits[key].append(edit)

        # Check each edit against current file content (pre-application).
        for edit in input.edits:
            fkey = str(Path(edit.file_path).resolve())
            content = file_contents[fkey]
            count = content.count(edit.old_str)
            if count == 0:
                yield ToolOutput(
                    type="result",
                    data={
                        "error": (
                            f"old_str not found in {edit.file_path}. "
                            "No files were modified."
                        ),
                    },
                    result_for_assistant=(
                        f"Error: old_str not found in {edit.file_path}. "
                        "No files were modified."
                    ),
                )
                return
            if count > 1:
                yield ToolOutput(
                    type="result",
                    data={
                        "error": (
                            f"old_str appears {count} times in {edit.file_path}. "
                            "The replacement must be unique — provide more "
                            "surrounding context to make the match unambiguous. "
                            "No files were modified."
                        ),
                    },
                    result_for_assistant=(
                        f"Error: old_str appears {count} times in "
                        f"{edit.file_path} — provide more context for a unique "
                        "match. No files were modified."
                    ),
                )
                return

        # ------------------------------------------------------------------
        # Phase 2: Apply all edits (validation passed).
        # ------------------------------------------------------------------
        # Work on a mutable copy of file contents so that multiple edits to
        # the same file are applied sequentially.
        modified: dict[str, str] = dict(file_contents)
        diffs: list[str] = []
        total_replacements = 0

        for edit in input.edits:
            key = str(Path(edit.file_path).resolve())
            original = modified[key]
            updated = original.replace(edit.old_str, edit.new_str, 1)
            modified[key] = updated
            total_replacements += 1

            # Generate diff
            diff_lines = list(
                difflib.unified_diff(
                    original.splitlines(keepends=True),
                    updated.splitlines(keepends=True),
                    fromfile=edit.file_path,
                    tofile=edit.file_path,
                )
            )
            diffs.append("".join(diff_lines))

        # Write all modified files.
        for key, content in modified.items():
            atomic_write(Path(key), content)

        # Build summary.
        files_changed = len(modified)
        summary = (
            f"Applied {total_replacements} edit(s) across "
            f"{files_changed} file(s) atomically."
        )

        yield ToolOutput(
            type="result",
            data={
                "edits_applied": total_replacements,
                "files_changed": list(modified.keys()),
                "diffs": diffs,
            },
            result_for_assistant=f"{summary}\n" + "\n".join(diffs),
        )
