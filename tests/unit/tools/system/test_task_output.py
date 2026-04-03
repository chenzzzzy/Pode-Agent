"""Unit tests for TaskOutputTool — background SubAgent result reader.

Reference: docs/subagent-system.md — TaskOutputTool
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from pode_agent.core.tools.base import ToolOutput, ToolUseContext
from pode_agent.services.agents.background_tasks import (
    clear_registry,
    upsert_background_agent_task,
)
from pode_agent.tools.system.task_output import TaskOutputInput, TaskOutputTool
from pode_agent.types.agent import BackgroundAgentStatus


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

    def test_schema_has_block_field(self) -> None:
        schema = TaskOutputInput.model_json_schema()
        assert "block" in schema["properties"]

    def test_schema_has_wait_ms_field(self) -> None:
        schema = TaskOutputInput.model_json_schema()
        assert "wait_ms" in schema["properties"]


# ---------------------------------------------------------------------------
# TaskOutputTool properties
# ---------------------------------------------------------------------------


class TestTaskOutputToolProperties:
    def setup_method(self) -> None:
        self.tool = TaskOutputTool()

    def test_name(self) -> None:
        assert self.tool.name == "TaskOutput"

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

    def teardown_method(self) -> None:
        clear_registry()

    @pytest.mark.asyncio
    async def test_not_found(self) -> None:
        inp = TaskOutputInput(task_id="nonexistent")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert "error" in result.data
        assert "not found" in result.data["error"].lower()

    @pytest.mark.asyncio
    async def test_empty_task_id(self) -> None:
        inp = TaskOutputInput(task_id="   ")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert "error" in result.data

    @pytest.mark.asyncio
    async def test_running_task_status(self) -> None:
        upsert_background_agent_task("agent-1", "Test task", "Do something")
        inp = TaskOutputInput(task_id="agent-1")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert result.data["status"] == "running"
        assert "still running" in result.data["message"]

    @pytest.mark.asyncio
    async def test_completed_task_result(self) -> None:
        from pode_agent.services.agents.background_tasks import (
            update_background_agent_task,
        )

        upsert_background_agent_task("agent-2", "Completed task", "Done")
        update_background_agent_task(
            "agent-2",
            status=BackgroundAgentStatus.COMPLETED,
            result_text="All done!",
            total_tool_use_count=3,
            total_duration_ms=1500,
        )

        inp = TaskOutputInput(task_id="agent-2")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert result.data["status"] == "completed"
        assert result.data["result_text"] == "All done!"
        assert "agent-2" in result.result_for_assistant

    @pytest.mark.asyncio
    async def test_failed_task_error(self) -> None:
        from pode_agent.services.agents.background_tasks import (
            update_background_agent_task,
        )

        upsert_background_agent_task("agent-3", "Failed task", "Will fail")
        update_background_agent_task(
            "agent-3",
            status=BackgroundAgentStatus.FAILED,
            error="Something went wrong",
        )

        inp = TaskOutputInput(task_id="agent-3")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert result.data["status"] == "failed"
        assert result.data["error"] == "Something went wrong"
        assert "failed" in result.result_for_assistant

    def test_render_result_for_assistant_error(self) -> None:
        result = self.tool.render_result_for_assistant({"error": "task not found"})
        assert "task not found" in result

    def test_render_result_for_assistant_generic(self) -> None:
        result = self.tool.render_result_for_assistant("some text")
        assert "some text" in result
