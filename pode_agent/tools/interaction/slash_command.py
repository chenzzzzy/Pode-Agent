"""SlashCommandTool: execute a slash command.

Handles both built-in commands (/help, /clear, /model) and custom
user/project commands discovered via ``load_custom_commands()``.

Reference: docs/skill-system.md — SlashCommandTool 设计
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from pydantic import BaseModel, Field

from pode_agent.core.tools.base import Tool, ToolOutput, ToolUseContext
from pode_agent.infra.logging import get_logger
from pode_agent.services.plugins.commands import load_custom_commands

logger = get_logger(__name__)

# Built-in commands
_HELP_TEXT = (
    "Available commands:\n"
    "  /help   - Show this help message\n"
    "  /clear  - Clear the session conversation\n"
    "  /model  - Show the current model\n"
    "\nCustom commands may also be available."
)

# Built-in command names (not dispatched through custom commands)
_BUILTIN_COMMANDS = frozenset({"help", "clear", "model"})


class SlashCommandInput(BaseModel):
    """Input schema for SlashCommandTool.

    Reference: docs/skill-system.md — SlashCommandInput
    """

    command: str = Field(
        description="The slash command to execute (without the leading /)",
    )
    args: str | None = Field(
        default=None,
        description="Arguments for the command",
    )


class SlashCommandTool(Tool):
    """Execute a slash command.

    Handles built-in commands (/help, /clear, /model) and custom
    commands discovered from .pode/commands/, ~/.pode/commands/,
    and plugin directories.

    Reference: docs/skill-system.md — SlashCommandTool 完整实现
    """

    name: str = "slash_command"
    description: str = (
        "Execute a slash command. "
        "Built-in commands include /help, /clear, and /model. "
        "Custom commands may also be available."
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

        # 1. Check built-in commands first
        if cmd in _BUILTIN_COMMANDS:
            async for output in self._handle_builtin(cmd, context):
                yield output
            return

        # 2. Look up in custom commands (filter is_skill=False)
        commands = await load_custom_commands()
        custom_cmd = next(
            (c for c in commands if c.name == cmd and not c.is_skill),
            None,
        )

        if custom_cmd is None:
            yield ToolOutput(
                type="result",
                data={"error": f"Unknown command: /{cmd}"},
                result_for_assistant=(
                    f"Unknown command: /{cmd}\n"
                    "Type /help to see available commands."
                ),
                is_error=True,
            )
            return

        # 3. Execute custom command
        prompt_text = custom_cmd.get_prompt_for_command(input.args)

        # 4. Build context modifier from frontmatter
        context_modifier = self._build_context_modifier(custom_cmd)

        # 5. Return result with new_messages and context_modifier
        result_text = f"Launching command: /{custom_cmd.name}"
        yield ToolOutput(
            type="result",
            data={"success": True, "command_name": custom_cmd.name},
            result_for_assistant=result_text,
            new_messages=[
                {"role": "user", "content": prompt_text},
            ],
            context_modifier=context_modifier,
        )

    async def _handle_builtin(
        self, cmd: str, context: ToolUseContext,
    ) -> AsyncGenerator[ToolOutput, None]:
        """Handle built-in slash commands."""
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

    def _build_context_modifier(self, cmd: Any) -> Any:
        """Extract ContextModifier from command's frontmatter."""
        from pode_agent.types.skill import ContextModifier

        fm = cmd.frontmatter
        if fm is None:
            return None
        if not any([fm.allowed_tools, fm.model, fm.max_thinking_tokens]):
            return None
        return ContextModifier(
            allowed_tools=fm.allowed_tools,
            model=fm.model,
            max_thinking_tokens=fm.max_thinking_tokens,
        )

    def render_result_for_assistant(self, output: Any) -> str | list[Any]:
        if isinstance(output, dict) and "error" in output:
            return str(output["error"])
        return str(output)
