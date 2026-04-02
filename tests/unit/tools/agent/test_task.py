"""Unit tests for TaskTool."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from pode_agent.core.tools.base import ToolUseContext
from pode_agent.tools.agent.task import TaskInput, TaskTool


def _ctx() -> ToolUseContext:
    return ToolUseContext(abort_event=asyncio.Event())


def _find_result(outputs: list[Any]) -> Any:
    for o in reversed(outputs):
        if o.type == "result":
            return o
    raise AssertionError("No result output found")


class TestTaskToolProperties:
    def setup_method(self) -> None:
        self.tool = TaskTool()

    def test_name(self) -> None:
        assert self.tool.name == "task"

    @pytest.mark.asyncio
    async def test_is_enabled(self) -> None:
        assert await self.tool.is_enabled() is True

    def test_is_read_only(self) -> None:
        assert self.tool.is_read_only() is False

    def test_needs_permissions(self) -> None:
        assert self.tool.needs_permissions() is True

    def test_is_concurrency_safe(self) -> None:
        assert self.tool.is_concurrency_safe() is False


class TestTaskToolCreate:
    def setup_method(self) -> None:
        self.tool = TaskTool()

    @pytest.mark.asyncio
    async def test_creates_task(self) -> None:
        inp = TaskInput(action="create", description="Write unit tests")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert result.data["event"] == "task_created"
        assert result.data["description"] == "Write unit tests"
        assert result.data["status"] == "pending"
        assert result.data["task_id"]
        assert "Write unit tests" in result.result_for_assistant

    @pytest.mark.asyncio
    async def test_create_without_description_uses_default(self) -> None:
        inp = TaskInput(action="create")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert result.data["event"] == "task_created"
        assert result.data["description"] == "Untitled task"


class TestTaskToolList:
    def setup_method(self) -> None:
        self.tool = TaskTool()

    @pytest.mark.asyncio
    async def test_lists_empty_tasks(self) -> None:
        inp = TaskInput(action="list")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert result.data["total"] == 0
        assert result.data["tasks"] == []
        assert result.result_for_assistant == "(no tasks)"

    @pytest.mark.asyncio
    async def test_lists_created_tasks(self) -> None:
        # Create a task first
        create_inp = TaskInput(action="create", description="First task")
        [o async for o in self.tool.call(create_inp, _ctx())]

        # List tasks
        list_inp = TaskInput(action="list")
        outputs = [o async for o in self.tool.call(list_inp, _ctx())]
        result = _find_result(outputs)

        assert result.data["total"] == 1
        assert result.data["tasks"][0]["description"] == "First task"
        assert result.data["tasks"][0]["status"] == "pending"
        assert "First task" in result.result_for_assistant


class TestTaskToolCancel:
    def setup_method(self) -> None:
        self.tool = TaskTool()

    @pytest.mark.asyncio
    async def test_cancels_existing_task(self) -> None:
        # Create a task
        create_inp = TaskInput(action="create", description="Task to cancel")
        create_result = _find_result(
            [o async for o in self.tool.call(create_inp, _ctx())]
        )
        task_id = create_result.data["task_id"]

        # Cancel it
        cancel_inp = TaskInput(action="cancel", task_id=task_id)
        outputs = [o async for o in self.tool.call(cancel_inp, _ctx())]
        result = _find_result(outputs)

        assert result.data["event"] == "task_cancelled"
        assert result.data["task_id"] == task_id
        assert result.data["status"] == "cancelled"
        assert "cancelled" in result.result_for_assistant

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_task(self) -> None:
        inp = TaskInput(action="cancel", task_id="nonexistent")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert "error" in result.data
        assert "not found" in result.result_for_assistant.lower()

    @pytest.mark.asyncio
    async def test_cancel_without_task_id(self) -> None:
        inp = TaskInput(action="cancel")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert "error" in result.data
        assert "task_id is required" in result.result_for_assistant

    @pytest.mark.asyncio
    async def test_input_schema(self) -> None:
        schema = self.tool.input_schema()
        assert schema is TaskInput
