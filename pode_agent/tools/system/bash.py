"""BashTool: execute shell commands.

Wraps :func:`pode_agent.infra.shell.execute_shell` as a Tool ABC
implementation with permission integration.

Reference: docs/api-specs.md — Tool System API, BashTool
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from pydantic import BaseModel, Field

from pode_agent.core.permissions.rules.bash import is_safe_bash_command
from pode_agent.core.tools.base import Tool, ToolOutput, ToolUseContext
from pode_agent.infra.logging import get_logger
from pode_agent.infra.shell import execute_shell

logger = get_logger(__name__)


class BashInput(BaseModel):
    """Input schema for BashTool."""

    command: str = Field(description="The shell command to execute")
    timeout: int = Field(
        default=120_000,
        description="Timeout in milliseconds (max 600000)",
    )
    description: str | None = Field(
        default=None,
        description="Clear, concise description of what this command does",
    )
    run_in_background: bool = Field(
        default=False,
        description="Run the command in the background (non-blocking)",
    )


class BashTool(Tool):
    """Execute a shell command and return stdout, stderr, exit_code."""

    name: str = "bash"
    description: str = "Execute a shell command and return the output"

    def input_schema(self) -> type[BaseModel]:
        return BashInput

    async def is_enabled(self) -> bool:
        return True

    def is_read_only(self, input: Any = None) -> bool:
        return False

    def is_concurrency_safe(self, input: Any = None) -> bool:
        return False

    def needs_permissions(self, input: Any = None) -> bool:
        if input is None:
            return True
        command = getattr(input, "command", None)
        if command is None:
            return True
        return not is_safe_bash_command(command)

    async def validate_input(
        self,
        input: BaseModel,
        context: ToolUseContext | None = None,
    ) -> Any:
        from pode_agent.core.tools.base import ValidationResult

        assert isinstance(input, BashInput)
        if not input.command.strip():
            return ValidationResult(result=False, message="Command cannot be empty")
        if input.timeout > 600_000:
            return ValidationResult(
                result=False,
                message="Timeout cannot exceed 600000ms",
            )
        if input.run_in_background:
            return ValidationResult(
                result=False,
                message="Background execution not yet supported",
            )
        return ValidationResult(result=True)

    def render_result_for_assistant(self, output: Any) -> str | list[Any]:
        if isinstance(output, dict):
            parts: list[str] = []
            if output.get("stdout"):
                parts.append(f"<stdout>\n{output['stdout']}</stdout>")
            if output.get("stderr"):
                parts.append(f"<stderr>\n{output['stderr']}</stderr>")
            exit_code = output.get("exit_code", 0)
            if exit_code != 0:
                parts.append(f"Exit code: {exit_code}")
            return "\n".join(parts) if parts else "(no output)"
        return str(output)

    def render_tool_use_message(
        self,
        input: Any,
        options: dict[str, Any] | None = None,
    ) -> str:
        cmd = getattr(input, "command", "")
        desc = getattr(input, "description", None)
        if desc:
            return f"Running: {desc} ({cmd})"
        return f"Running: {cmd}"

    async def call(
        self,
        input: BaseModel,
        context: ToolUseContext,
    ) -> AsyncGenerator[ToolOutput, None]:
        bash_input: BashInput = input  # type: ignore[assignment]

        # Yield a progress update.
        yield ToolOutput(
            type="progress",
            content=f"Executing: {bash_input.command}",
        )

        timeout_sec = bash_input.timeout / 1000.0
        abort_event = context.abort_event

        result = await execute_shell(
            command=bash_input.command,
            timeout=timeout_sec,
            abort_event=abort_event,
        )

        data = {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.exit_code,
            "timed_out": result.timed_out,
        }

        yield ToolOutput(
            type="result",
            data=data,
            result_for_assistant=self.render_result_for_assistant(data),
        )
