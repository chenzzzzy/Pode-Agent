"""TaskOutputTool: read the output of a background SubAgent task.

Supports both non-blocking reads and blocking waits with configurable
timeout. Reads from the background task registry.

Reference: docs/subagent-system.md — TaskOutputTool
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from pydantic import BaseModel, Field

from pode_agent.core.tools.base import Tool, ToolOutput, ToolUseContext
from pode_agent.infra.logging import get_logger
from pode_agent.services.agents.background_tasks import (
    get_background_agent_task,
    wait_for_background_agent_task,
)
from pode_agent.types.agent import BackgroundAgentStatus

logger = get_logger(__name__)


class TaskOutputInput(BaseModel):
    """Input schema for TaskOutputTool."""

    task_id: str = Field(description="ID of the background agent task")
    block: bool = Field(
        default=False,
        description="If true, wait for the task to complete before returning",
    )
    wait_ms: int = Field(
        default=30000,
        description="Maximum time to wait in milliseconds when block=true",
    )


class TaskOutputTool(Tool):
    """Read the output of a background SubAgent task."""

    name: str = "TaskOutput"
    description: str = (
        "Read the output of a background agent task by its task ID. "
        "Optionally block until the task completes."
    )

    def input_schema(self) -> type[BaseModel]:
        return TaskOutputInput

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
        assert isinstance(input, TaskOutputInput)

        task_id = input.task_id.strip()
        if not task_id:
            yield ToolOutput(
                type="result",
                data={"error": "Task ID cannot be empty"},
                result_for_assistant="Error: Task ID cannot be empty",
            )
            return

        # Blocking wait if requested
        if input.block:
            try:
                await wait_for_background_agent_task(task_id, timeout_ms=input.wait_ms)
            except KeyError:
                yield ToolOutput(
                    type="result",
                    data={"error": f"Background task not found: {task_id}"},
                    result_for_assistant=f"Error: Background task not found: {task_id}",
                )
                return

        # Read current state
        task = get_background_agent_task(task_id)
        if task is None:
            yield ToolOutput(
                type="result",
                data={"error": f"Background task not found: {task_id}"},
                result_for_assistant=f"Error: Background task not found: {task_id}",
            )
            return

        # Build result based on status
        data: dict[str, Any] = {
            "agent_id": task.agent_id,
            "description": task.description,
            "status": str(task.status),
        }

        if task.status == BackgroundAgentStatus.COMPLETED:
            data["result_text"] = task.result_text
            data["total_tool_use_count"] = task.total_tool_use_count
            data["total_duration_ms"] = task.total_duration_ms
            result_for_assistant = (
                f"[Agent {task.agent_id} completed] {task.result_text} "
                f"({task.total_tool_use_count} tool uses, "
                f"{task.total_duration_ms / 1000:.1f}s)"
            )
        elif task.status == BackgroundAgentStatus.FAILED:
            data["error"] = task.error
            result_for_assistant = (
                f"[Agent {task.agent_id} failed] {task.error}"
            )
        elif task.status == BackgroundAgentStatus.KILLED:
            data["error"] = "Task was killed"
            result_for_assistant = (
                f"[Agent {task.agent_id} killed]"
            )
        else:
            # Still running
            data["message"] = "Task is still running"
            result_for_assistant = (
                f"[Agent {task.agent_id} still running] "
                f"Use TaskOutput with block=true to wait for completion."
            )

        yield ToolOutput(
            type="result",
            data=data,
            result_for_assistant=result_for_assistant,
        )

    def render_result_for_assistant(self, output: Any) -> str | list[Any]:
        if isinstance(output, dict) and "error" in output:
            return str(output["error"])
        return str(output)
