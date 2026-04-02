"""LspTool: query a Language Server Protocol server for code intelligence.

Phase 3 skeleton: checks if a language server is available and returns
an error message if not. Full LSP communication will be implemented in
a later phase.

Reference: docs/api-specs.md -- Tool System API, LspTool
"""

from __future__ import annotations

import shutil
from collections.abc import AsyncGenerator
from typing import Any, Literal

from pydantic import BaseModel, Field

from pode_agent.core.tools.base import Tool, ToolOutput, ToolUseContext
from pode_agent.infra.logging import get_logger

logger = get_logger(__name__)

# Known language server binaries
SUPPORTED_LSP_SERVERS: dict[str, str] = {
    "python": "pyright-langserver",
    "typescript": "typescript-language-server",
}


class LspInput(BaseModel):
    """Input schema for LspTool."""

    action: Literal["definition", "references", "hover"] = Field(
        description="LSP action to perform",
    )
    file_path: str = Field(description="Absolute path to the source file")
    line: int = Field(description="Line number (0-based)")
    character: int = Field(description="Character offset in the line (0-based)")


class LspTool(Tool):
    """Query a Language Server Protocol server for code intelligence."""

    name: str = "lsp"
    description: str = (
        "Query a Language Server Protocol server for code intelligence. "
        "Supports actions: definition, references, hover."
    )

    def input_schema(self) -> type[BaseModel]:
        return LspInput

    async def is_enabled(self) -> bool:
        return True

    def is_read_only(self, input: Any = None) -> bool:
        return True

    def needs_permissions(self, input: Any = None) -> bool:
        return False

    def is_concurrency_safe(self, input: Any = None) -> bool:
        return True

    async def call(
        self,
        input: BaseModel,
        context: ToolUseContext,
    ) -> AsyncGenerator[ToolOutput, None]:
        assert isinstance(input, LspInput)

        # Check for available language servers
        available_servers = [
            (lang, binary)
            for lang, binary in SUPPORTED_LSP_SERVERS.items()
            if shutil.which(binary)
        ]

        if not available_servers:
            server_list = ", ".join(SUPPORTED_LSP_SERVERS.values())
            yield ToolOutput(
                type="result",
                data={
                    "error": (
                        f"No language server found. Install one of: {server_list}"
                    ),
                },
                result_for_assistant=(
                    f"Error: No language server found. Install one of: {server_list}"
                ),
            )
            return

        # Phase 3 skeleton: report available servers but LSP is not yet connected
        available_names = ", ".join(f"{lang} ({binary})" for lang, binary in available_servers)
        yield ToolOutput(
            type="result",
            data={
                "status": "skeleton",
                "message": (
                    f"LSP tool is a skeleton. Available servers: {available_names}. "
                    "Full LSP integration will be implemented in a future phase."
                ),
                "action": input.action,
                "file_path": input.file_path,
                "line": input.line,
                "character": input.character,
            },
            result_for_assistant=(
                f"LSP tool is not yet fully implemented. "
                f"Available servers detected: {available_names}. "
                f"Action '{input.action}' at {input.file_path}:{input.line}:{input.character} "
                "will be supported in a future phase."
            ),
        )

    def render_result_for_assistant(self, output: Any) -> str | list[Any]:
        if isinstance(output, dict) and "error" in output:
            return str(output["error"])
        if isinstance(output, dict) and "message" in output:
            return str(output["message"])
        return str(output)
