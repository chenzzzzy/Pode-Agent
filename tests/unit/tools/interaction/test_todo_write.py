"""Unit tests for TodoWriteTool."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from pode_agent.core.tools.base import ToolUseContext
from pode_agent.tools.interaction.todo_write import (
    TodoItem,
    TodoWriteInput,
    TodoWriteTool,
)


def _ctx() -> ToolUseContext:
    return ToolUseContext(abort_event=asyncio.Event())


def _find_result(outputs: list[Any]) -> Any:
    for o in reversed(outputs):
        if o.type == "result":
            return o
    raise AssertionError("No result output found")


class TestTodoWriteToolProperties:
    def setup_method(self) -> None:
        self.tool = TodoWriteTool()

    def test_name(self) -> None:
        assert self.tool.name == "todo_write"

    @pytest.mark.asyncio
    async def test_is_enabled(self) -> None:
        assert await self.tool.is_enabled() is True

    def test_is_read_only(self) -> None:
        assert self.tool.is_read_only() is False

    def test_needs_permissions(self) -> None:
        assert self.tool.needs_permissions() is False

    def test_is_concurrency_safe(self) -> None:
        assert self.tool.is_concurrency_safe() is False


class TestTodoWriteToolCall:
    def setup_method(self) -> None:
        self.tool = TodoWriteTool()

    @pytest.mark.asyncio
    async def test_formats_todo_list_with_status_icons(self) -> None:
        inp = TodoWriteInput(
            todos=[
                TodoItem(id="1", content="Plan feature", status="completed"),
                TodoItem(id="2", content="Write tests", status="in_progress"),
                TodoItem(id="3", content="Deploy", status="pending"),
            ],
        )
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        # Check status icons appear
        text = result.result_for_assistant
        assert "\u25cf" in text  # ● completed
        assert "\u25d0" in text  # ◐ in_progress
        assert "\u25cb" in text  # ○ pending

        # Check content is present
        assert "Plan feature" in text
        assert "Write tests" in text
        assert "Deploy" in text

        # Check data structure
        assert result.data["total"] == 3
        assert len(result.data["todos"]) == 3

    @pytest.mark.asyncio
    async def test_active_form_shown_for_in_progress(self) -> None:
        inp = TodoWriteInput(
            todos=[
                TodoItem(
                    id="1",
                    content="Refactor module",
                    status="in_progress",
                    activeForm="Refactoring auth module",
                ),
            ],
        )
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert "Refactoring auth module" in result.result_for_assistant

    @pytest.mark.asyncio
    async def test_active_form_not_shown_for_completed(self) -> None:
        inp = TodoWriteInput(
            todos=[
                TodoItem(
                    id="1",
                    content="Done task",
                    status="completed",
                    activeForm="Should not appear",
                ),
            ],
        )
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert "Should not appear" not in result.result_for_assistant

    @pytest.mark.asyncio
    async def test_empty_todo_list(self) -> None:
        inp = TodoWriteInput(todos=[])
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert result.data["total"] == 0
        assert result.data["todos"] == []
        assert result.result_for_assistant == "(empty todo list)"

    @pytest.mark.asyncio
    async def test_input_schema(self) -> None:
        schema = self.tool.input_schema()
        assert schema is TodoWriteInput

    @pytest.mark.asyncio
    async def test_todo_item_status_validation(self) -> None:
        """Only valid status literals are accepted."""
        with pytest.raises(Exception):
            TodoItem(id="1", content="Bad status", status="invalid")
