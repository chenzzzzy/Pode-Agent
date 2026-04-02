"""Unit tests for EnterPlanModeTool and ExitPlanModeTool."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from pode_agent.core.tools.base import ToolUseContext
from pode_agent.tools.agent.plan_mode import (
    EnterPlanModeInput,
    EnterPlanModeTool,
    ExitPlanModeInput,
    ExitPlanModeTool,
)


def _ctx() -> ToolUseContext:
    return ToolUseContext(abort_event=asyncio.Event())


def _find_result(outputs: list[Any]) -> Any:
    for o in reversed(outputs):
        if o.type == "result":
            return o
    raise AssertionError("No result output found")


# ---------------------------------------------------------------------------
# EnterPlanModeTool
# ---------------------------------------------------------------------------


class TestEnterPlanModeToolProperties:
    def setup_method(self) -> None:
        self.tool = EnterPlanModeTool()

    def test_name(self) -> None:
        assert self.tool.name == "enter_plan_mode"

    @pytest.mark.asyncio
    async def test_is_enabled(self) -> None:
        assert await self.tool.is_enabled() is True

    def test_is_read_only(self) -> None:
        assert self.tool.is_read_only() is True

    def test_needs_permissions(self) -> None:
        assert self.tool.needs_permissions() is False

    def test_is_concurrency_safe(self) -> None:
        assert self.tool.is_concurrency_safe() is True


class TestEnterPlanModeToolCall:
    def setup_method(self) -> None:
        self.tool = EnterPlanModeTool()

    @pytest.mark.asyncio
    async def test_switches_to_plan_mode(self) -> None:
        inp = EnterPlanModeInput(objective="Refactor the auth module")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert result.data["mode"] == "plan"
        assert result.data["objective"] == "Refactor the auth module"
        assert "plan mode" in result.result_for_assistant.lower()
        assert "Refactor the auth module" in result.result_for_assistant

    @pytest.mark.asyncio
    async def test_input_schema(self) -> None:
        schema = self.tool.input_schema()
        assert schema is EnterPlanModeInput


# ---------------------------------------------------------------------------
# ExitPlanModeTool
# ---------------------------------------------------------------------------


class TestExitPlanModeToolProperties:
    def setup_method(self) -> None:
        self.tool = ExitPlanModeTool()

    def test_name(self) -> None:
        assert self.tool.name == "exit_plan_mode"

    @pytest.mark.asyncio
    async def test_is_enabled(self) -> None:
        assert await self.tool.is_enabled() is True

    def test_is_read_only(self) -> None:
        assert self.tool.is_read_only() is True

    def test_needs_permissions(self) -> None:
        assert self.tool.needs_permissions() is False

    def test_is_concurrency_safe(self) -> None:
        assert self.tool.is_concurrency_safe() is True


class TestExitPlanModeToolCall:
    def setup_method(self) -> None:
        self.tool = ExitPlanModeTool()

    @pytest.mark.asyncio
    async def test_submits_plan_with_steps(self) -> None:
        inp = ExitPlanModeInput(
            objective="Add caching layer",
            steps=[
                {"title": "Research caching options", "description": "Compare Redis vs Memcached"},
                {"title": "Implement cache module", "description": "Create cache abstraction layer"},
                {"title": "Add tests", "description": "Unit and integration tests"},
            ],
            acceptance_criteria=["All tests pass", "Cache hit rate > 80%"],
            risks=["Cache invalidation complexity", "Memory overhead"],
        )
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert result.data["event"] == "plan_created"
        plan = result.data["plan"]
        assert plan["objective"] == "Add caching layer"
        assert len(plan["steps"]) == 3
        assert plan["steps"][0]["title"] == "Research caching options"
        assert plan["acceptance_criteria"] == ["All tests pass", "Cache hit rate > 80%"]
        assert plan["risks"] == ["Cache invalidation complexity", "Memory overhead"]

        # Check formatted output
        text = result.result_for_assistant
        assert "Add caching layer" in text
        assert "Research caching options" in text
        assert "All tests pass" in text
        assert "Cache invalidation complexity" in text

    @pytest.mark.asyncio
    async def test_submits_minimal_plan(self) -> None:
        inp = ExitPlanModeInput(
            objective="Fix bug #42",
            steps=[{"title": "Reproduce the bug"}],
        )
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert result.data["event"] == "plan_created"
        assert result.data["plan"]["objective"] == "Fix bug #42"
        assert result.data["plan"]["acceptance_criteria"] == []
        assert result.data["plan"]["risks"] == []

    @pytest.mark.asyncio
    async def test_plan_with_empty_steps(self) -> None:
        inp = ExitPlanModeInput(
            objective="Explore codebase",
            steps=[],
        )
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert result.data["plan"]["steps"] == []
        assert "no steps defined" in result.result_for_assistant

    @pytest.mark.asyncio
    async def test_input_schema(self) -> None:
        schema = self.tool.input_schema()
        assert schema is ExitPlanModeInput
