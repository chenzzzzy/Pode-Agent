"""TaskTool: manage sub-tasks within the agent session.

Provides basic in-memory task management with create, list, and cancel
actions.  Tasks are stored per-tool-instance in an internal dict.

Reference: docs/api-specs.md -- Tool System API, TaskTool
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any, Literal

from pydantic import BaseModel, Field

from pode_agent.core.tools.base import Tool, ToolOutput, ToolUseContext
from pode_agent.infra.logging import get_logger

logger = get_logger(__name__)


class TaskInput(BaseModel):
    """Input schema for TaskTool."""

    action: Literal["create", "list", "cancel"] = Field(
        description="Action to perform: create a new task, list all tasks, or cancel a task",
    )
    description: str | None = Field(
        default=None,
        description="Description of the task (required for create action)",
    )
    task_id: str | None = Field(
        default=None,
        description="ID of the task to cancel (required for cancel action)",
    )


class _TaskEntry(BaseModel):
    """Internal representation of a task."""

    task_id: str
    description: str
    status: str = "pending"


class TaskTool(Tool):
    """Manage sub-tasks within the agent session.

    Phase 3 skeleton: in-memory dict for tasks, basic create/list/cancel.
    """

    name: str = "task"
    description: str = (
        "Manage sub-tasks within the agent session. "
        "Create new tasks, list existing ones, or cancel pending tasks."
    )

    # In-memory task store keyed by task_id
    _tasks: dict[str, _TaskEntry]

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._tasks = {}

    def input_schema(self) -> type[BaseModel]:
        return TaskInput

    async def is_enabled(self) -> bool:
        return True

    def is_read_only(self, input: Any = None) -> bool:
        return False

    def needs_permissions(self, input: Any = None) -> bool:
        return True

    def is_concurrency_safe(self, input: Any = None) -> bool:
        return False

    async def call(
        self,
        input: BaseModel,
        context: ToolUseContext,
    ) -> AsyncGenerator[ToolOutput, None]:
        assert isinstance(input, TaskInput)

        if input.action == "create":
            async for output in self._handle_create(input):
                yield output
        elif input.action == "list":
            async for output in self._handle_list():
                yield output
        elif input.action == "cancel":
            async for output in self._handle_cancel(input):
                yield output

    async def _handle_create(self, input: TaskInput) -> AsyncGenerator[ToolOutput, None]:
        """Create a new task."""
        description = input.description or "Untitled task"

        # Generate a simple task ID
        import uuid

        task_id = str(uuid.uuid4())[:8]
        entry = _TaskEntry(task_id=task_id, description=description, status="pending")
        self._tasks[task_id] = entry

        yield ToolOutput(
            type="result",
            data={
                "event": "task_created",
                "task_id": task_id,
                "description": description,
                "status": "pending",
            },
            result_for_assistant=(
                f"Task created: [{task_id}] {description}"
            ),
        )

    async def _handle_list(self) -> AsyncGenerator[ToolOutput, None]:
        """List all tasks."""
        tasks_list = [
            {
                "task_id": entry.task_id,
                "description": entry.description,
                "status": entry.status,
            }
            for entry in self._tasks.values()
        ]

        if not tasks_list:
            result_text = "(no tasks)"
        else:
            lines: list[str] = []
            for t in tasks_list:
                status_icon = "+" if t["status"] == "pending" else "-"
                lines.append(f"  [{status_icon}] {t['task_id']}: {t['description']}")
            result_text = "\n".join(lines)

        yield ToolOutput(
            type="result",
            data={
                "tasks": tasks_list,
                "total": len(tasks_list),
            },
            result_for_assistant=result_text,
        )

    async def _handle_cancel(self, input: TaskInput) -> AsyncGenerator[ToolOutput, None]:
        """Cancel an existing task."""
        task_id = input.task_id
        if not task_id:
            yield ToolOutput(
                type="result",
                data={"error": "task_id is required for cancel action"},
                result_for_assistant="Error: task_id is required for cancel action",
            )
            return

        entry = self._tasks.get(task_id)
        if not entry:
            yield ToolOutput(
                type="result",
                data={"error": f"Task not found: {task_id}"},
                result_for_assistant=f"Error: Task not found: {task_id}",
            )
            return

        entry.status = "cancelled"
        yield ToolOutput(
            type="result",
            data={
                "event": "task_cancelled",
                "task_id": task_id,
                "status": "cancelled",
            },
            result_for_assistant=f"Task cancelled: [{task_id}] {entry.description}",
        )

    def render_result_for_assistant(self, output: Any) -> str | list[Any]:
        if isinstance(output, dict) and "error" in output:
            return str(output["error"])
        return str(output)
