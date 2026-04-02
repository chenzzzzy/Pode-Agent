"""TaskOutputTool: read the output of a background task.

Phase 3 skeleton: returns a placeholder message indicating that
background task tracking is not yet implemented.

Reference: docs/api-specs.md -- Tool System API, TaskOutputTool
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from pydantic import BaseModel, Field

from pode_agent.core.tools.base import Tool, ToolOutput, ToolUseContext
from pode_agent.infra.logging import get_logger

logger = get_logger(__name__)


class TaskOutputInput(BaseModel):
    """Input schema for TaskOutputTool."""

    task_id: str = Field(description="ID of the background task to read output from")


class TaskOutputTool(Tool):
    """Read the output of a background task."""

    name: str = "task_output"
    description: str = (
        "Read the output of a background task by its task ID. "
        "Returns the current stdout/stderr and completion status."
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

        if not input.task_id.strip():
            yield ToolOutput(
                type="result",
                data={"error": "Task ID cannot be empty"},
                result_for_assistant="Error: Task ID cannot be empty",
            )
            return

        # Phase 3 skeleton: no background tasks tracked yet
        yield ToolOutput(
            type="result",
            data={
                "status": "skeleton",
                "task_id": input.task_id,
                "message": "No background tasks tracked yet. Background task management will be implemented in a future phase.",
            },
            result_for_assistant=(
                f"No background tasks tracked yet for task_id '{input.task_id}'. "
                "Background task management will be implemented in a future phase."
            ),
        )

    def render_result_for_assistant(self, output: Any) -> str | list[Any]:
        if isinstance(output, dict) and "error" in output:
            return str(output["error"])
        if isinstance(output, dict) and "message" in output:
            return str(output["message"])
        return str(output)
