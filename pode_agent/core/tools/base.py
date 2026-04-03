"""Tool abstract base class and core types.

Defines the contract every tool must implement. Tools are the primary
extension mechanism in Pode-Agent — each tool exposes a single capability
(e.g. file editing, shell execution, web search) to the AI assistant.

Reference: docs/api-specs.md — Tool System API
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from pode_agent.types.skill import ContextModifier


class ToolOutput(BaseModel):
    """A single output item yielded by a tool during execution.

    Tools yield progress updates (type='progress') while working, and a
    final result (type='result') when done.
    """

    type: Literal["result", "progress"]

    # Progress-type fields
    content: Any = None
    normalized_messages: list[Any] | None = None
    tools: list[Any] | None = None

    # Result-type fields
    data: Any = None
    result_for_assistant: str | list[Any] | None = None
    new_messages: list[Any] | None = None
    context_modifier: ContextModifier | None = None
    is_error: bool = False


class ToolOptions(BaseModel):
    """Runtime options passed to tools via ToolUseContext."""

    commands: list[Any] | None = None
    tools: list[Any] | None = None
    verbose: bool = False
    slow_and_capable_model: str | None = None
    safe_mode: bool = False
    permission_mode: str | None = None
    tool_permission_context: Any | None = None
    last_user_prompt: str | None = None
    fork_number: int = 0
    message_log_name: str | None = None
    max_thinking_tokens: int | None = None
    model: str | None = None
    command_allowed_tools: list[str] | None = None
    mcp_clients: list[Any] | None = None


class ToolUseContext(BaseModel):
    """Runtime context provided to a tool during execution."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    message_id: str | None = None
    tool_use_id: str | None = None
    agent_id: str | None = None
    safe_mode: bool = False
    abort_event: asyncio.Event | None = None
    read_file_timestamps: dict[str, float] = Field(default_factory=dict)
    options: ToolOptions = ToolOptions()


class ValidationResult(BaseModel):
    """Result of tool input validation."""

    result: bool
    message: str | None = None


class ToolResult(BaseModel):
    """Final result collected from a tool's AsyncGenerator."""

    data: Any = None
    result_for_assistant: str | list[Any] | None = None
    new_messages: list[Any] = []
    error: str | None = None
    context_modifier: ContextModifier | None = None


class Tool(ABC):
    """Abstract base class for all tools.

    Every tool must:
    - Declare a unique ``name`` (snake_case)
    - Define a Pydantic ``BaseModel`` as its input schema
    - Implement ``call()`` yielding ``ToolOutput`` items via AsyncGenerator
    - Declare read-only / permission requirements

    Reference: docs/api-specs.md — Tool interface contract
    """

    name: str
    description: str | None = None
    cached_description: str | None = None

    @abstractmethod
    def input_schema(self) -> type[BaseModel]:
        """Return the Pydantic model class for tool input validation."""
        ...

    @abstractmethod
    async def is_enabled(self) -> bool:
        """Whether this tool is available in the current environment."""
        ...

    @abstractmethod
    def is_read_only(self, input: Any = None) -> bool:
        """Whether the operation is read-only (used by plan mode)."""
        ...

    def is_concurrency_safe(self, input: Any = None) -> bool:
        """Whether this tool can safely run concurrently with others."""
        return False

    @abstractmethod
    def needs_permissions(self, input: Any = None) -> bool:
        """Whether the operation requires explicit user approval."""
        ...

    async def validate_input(
        self,
        input: BaseModel,
        context: ToolUseContext | None = None,
    ) -> ValidationResult:
        """Optional extra validation. Default: always pass."""
        return ValidationResult(result=True)

    @abstractmethod
    def render_result_for_assistant(self, output: Any) -> str | list[Any]:
        """Format tool output for the LLM to consume."""
        ...

    def render_tool_use_message(
        self,
        input: Any,
        options: dict[str, Any] | None = None,
    ) -> str:
        """Human-readable description for UI display."""
        return f"Running {self.name}..."

    @abstractmethod
    async def call(
        self,
        input: BaseModel,
        context: ToolUseContext,
    ) -> AsyncGenerator[ToolOutput, None]:
        """Execute the tool.

        Must yield at least one ``ToolOutput(type='result', ...)``.
        May yield ``ToolOutput(type='progress', ...)`` items before that
        to report incremental progress.
        """
        yield  # type: ignore[misc]  # pragma: no cover

    def get_json_schema(self) -> dict[str, Any]:
        """Generate JSON Schema for LLM tool calling."""
        return {
            "name": self.name,
            "description": self.description or "",
            "input_schema": self.input_schema().model_json_schema(),
        }
