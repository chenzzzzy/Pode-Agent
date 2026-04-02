"""Unit tests for TaskOutputTool.

Reference: docs/api-specs.md -- Tool System API, TaskOutputTool
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from pode_agent.core.tools.base import ToolOutput, ToolUseContext
from pode_agent.tools.system.task_output import TaskOutputInput, TaskOutputTool


def _ctx() -> ToolUseContext:
    return ToolUseContext(abort_event=asyncio.Event())


def _find_result(outputs: list[ToolOutput]) -> ToolOutput:
    for o in reversed(outputs):
        if o.type == "result":
            return o
    raise AssertionError("No result output found")


# ---------------------------------------------------------------------------
# TaskOutputInput schema
# ---------------------------------------------------------------------------


class TestTaskOutputInput:
    def test_schema_has_required_task_id(self) -> None:
        schema = TaskOutputInput.model_json_schema()
        assert "task_id" in schema["properties"]
        assert "task_id" in schema["required"]


# ---------------------------------------------------------------------------
# TaskOutputTool properties
# ---------------------------------------------------------------------------


class TestTaskOutputToolProperties:
    def setup_method(self) -> None:
        self.tool = TaskOutputTool()

    def test_name(self) -> None:
        assert self.tool.name == "task_output"

    def test_input_schema(self) -> None:
        assert self.tool.input_schema() is TaskOutputInput

    @pytest.mark.asyncio
    async def test_is_enabled(self) -> None:
        assert await self.tool.is_enabled() is True

    def test_is_read_only(self) -> None:
        assert self.tool.is_read_only() is True

    def test_needs_permissions(self) -> None:
        assert self.tool.needs_permissions() is False

    def test_is_concurrency_safe(self) -> None:
        assert self.tool.is_concurrency_safe() is True


# ---------------------------------------------------------------------------
# TaskOutputTool.call()
# ---------------------------------------------------------------------------


class TestTaskOutputToolCall:
    def setup_method(self) -> None:
        self.tool = TaskOutputTool()

    @pytest.mark.asyncio
    async def test_skeleton_response(self) -> None:
        inp = TaskOutputInput(task_id="task-123")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert result.data["status"] == "skeleton"
        assert result.data["task_id"] == "task-123"
        assert "No background tasks tracked yet" in result.data["message"]

    @pytest.mark.asyncio
    async def test_empty_task_id_rejected(self) -> None:
        inp = TaskOutputInput(task_id="   ")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert "error" in result.data
        assert "cannot be empty" in result.data["error"]

    @pytest.mark.asyncio
    async def test_result_text_contains_task_id(self) -> None:
        inp = TaskOutputInput(task_id="my-task-456")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert "my-task-456" in result.result_for_assistant

    def test_render_result_for_assistant_error(self) -> None:
        result = self.tool.render_result_for_assistant({"error": "task not found"})
        assert "task not found" in result

    def test_render_result_for_assistant_message(self) -> None:
        result = self.tool.render_result_for_assistant({"message": "skeleton mode"})
        assert "skeleton mode" in result
