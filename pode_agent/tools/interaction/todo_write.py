"""TodoWriteTool: create and manage a structured todo list.

Lets the agent maintain a task list so it can track progress on
multi-step operations.  Each todo item has an id, content, status, and
an optional activeForm describing the current action.

Reference: docs/api-specs.md -- Tool System API, TodoWriteTool
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any, Literal

from pydantic import BaseModel, Field

from pode_agent.core.tools.base import Tool, ToolOutput, ToolUseContext
from pode_agent.infra.logging import get_logger

logger = get_logger(__name__)

# Status indicators for the formatted output
_STATUS_ICONS: dict[str, str] = {
    "pending": "\u25cb",       # ○
    "in_progress": "\u25d0",   # ◐
    "completed": "\u25cf",     # ●
}


class TodoItem(BaseModel):
    """A single todo item."""

    id: str = Field(description="Unique identifier for the todo item")
    content: str = Field(description="Description of the task")
    status: Literal["pending", "in_progress", "completed"] = Field(
        description="Current status of the task",
    )
    activeForm: str | None = Field(
        default=None,
        description="Present-tense description of what is being done (for in_progress items)",
    )


class TodoWriteInput(BaseModel):
    """Input schema for TodoWriteTool."""

    todos: list[TodoItem] = Field(
        description="The complete list of todo items to set (replaces any existing list)",
    )


class TodoWriteTool(Tool):
    """Create and manage a structured todo list for tracking progress."""

    name: str = "todo_write"
    description: str = (
        "Create and manage a structured todo list to track progress on multi-step tasks. "
        "Each call replaces the entire list. Use this to plan and visualize work."
    )

    def input_schema(self) -> type[BaseModel]:
        return TodoWriteInput

    async def is_enabled(self) -> bool:
        return True

    def is_read_only(self, input: Any = None) -> bool:
        return False

    def needs_permissions(self, input: Any = None) -> bool:
        return False

    def is_concurrency_safe(self, input: Any = None) -> bool:
        return False

    async def call(
        self,
        input: BaseModel,
        context: ToolUseContext,
    ) -> AsyncGenerator[ToolOutput, None]:
        assert isinstance(input, TodoWriteInput)

        lines: list[str] = []
        for item in input.todos:
            icon = _STATUS_ICONS.get(item.status, "\u25cb")
            line = f"{icon} [{item.id}] {item.content}"
            if item.activeForm and item.status == "in_progress":
                line += f" -- {item.activeForm}"
            lines.append(line)

        result_text = "\n".join(lines) if lines else "(empty todo list)"

        yield ToolOutput(
            type="result",
            data={
                "todos": [item.model_dump() for item in input.todos],
                "total": len(input.todos),
            },
            result_for_assistant=result_text,
        )

    def render_result_for_assistant(self, output: Any) -> str | list[Any]:
        if isinstance(output, dict) and "error" in output:
            return str(output["error"])
        return str(output)
