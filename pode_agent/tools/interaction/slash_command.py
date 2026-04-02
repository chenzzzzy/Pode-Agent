"""SlashCommandTool: execute a slash command.

Handles built-in commands such as /help, /clear, and /model.
Phase 3 skeleton supports only built-in commands.

Reference: docs/api-specs.md -- Tool System API, SlashCommandTool
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from pydantic import BaseModel, Field

from pode_agent.core.tools.base import Tool, ToolOutput, ToolUseContext
from pode_agent.infra.logging import get_logger

logger = get_logger(__name__)

# Built-in command handlers
_HELP_TEXT = (
    "Available commands:\n"
    "  /help   - Show this help message\n"
    "  /clear  - Clear the session conversation\n"
    "  /model  - Show the current model\n"
)


class SlashCommandInput(BaseModel):
    """Input schema for SlashCommandTool."""

    command: str = Field(description="The slash command to execute (e.g. /help, /clear)")
    args: str | None = Field(
        default=None,
        description="Optional arguments for the command",
    )


class SlashCommandTool(Tool):
    """Execute a slash command.

    Phase 3 skeleton: handle built-in commands only.
    """

    name: str = "slash_command"
    description: str = (
        "Execute a slash command. "
        "Built-in commands include /help, /clear, and /model."
    )

    def input_schema(self) -> type[BaseModel]:
        return SlashCommandInput

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
        assert isinstance(input, SlashCommandInput)

        # Normalize command: strip leading slashes and whitespace
        cmd = input.command.strip().lstrip("/").lower()

        if cmd == "help":
            yield ToolOutput(
                type="result",
                data={"command": "help"},
                result_for_assistant=_HELP_TEXT,
            )
        elif cmd == "clear":
            yield ToolOutput(
                type="result",
                data={"command": "clear", "message": "Session cleared"},
                result_for_assistant="Session cleared.",
            )
        elif cmd == "model":
            model_name = context.options.model or "unknown"
            yield ToolOutput(
                type="result",
                data={"command": "model", "model": model_name},
                result_for_assistant=f"Current model: {model_name}",
            )
        else:
            yield ToolOutput(
                type="result",
                data={"error": f"Unknown command: /{cmd}"},
                result_for_assistant=(
                    f"Unknown command: /{cmd}\n"
                    "Type /help to see available commands."
                ),
            )

    def render_result_for_assistant(self, output: Any) -> str | list[Any]:
        if isinstance(output, dict) and "error" in output:
            return str(output["error"])
        return str(output)
