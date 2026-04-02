"""Unit tests for AskExpertModelTool."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from pode_agent.core.tools.base import ToolUseContext
from pode_agent.tools.ai.ask_expert import AskExpertInput, AskExpertModelTool


def _ctx() -> ToolUseContext:
    return ToolUseContext(abort_event=asyncio.Event())


def _find_result(outputs: list[Any]) -> Any:
    for o in reversed(outputs):
        if o.type == "result":
            return o
    raise AssertionError("No result output found")


class TestAskExpertModelToolProperties:
    def setup_method(self) -> None:
        self.tool = AskExpertModelTool()

    def test_name(self) -> None:
        assert self.tool.name == "ask_expert_model"

    @pytest.mark.asyncio
    async def test_is_enabled(self) -> None:
        assert await self.tool.is_enabled() is True

    def test_is_read_only(self) -> None:
        assert self.tool.is_read_only() is True

    def test_needs_permissions(self) -> None:
        assert self.tool.needs_permissions() is False

    def test_is_concurrency_safe(self) -> None:
        assert self.tool.is_concurrency_safe() is True


class TestAskExpertModelToolCall:
    def setup_method(self) -> None:
        self.tool = AskExpertModelTool()

    @pytest.mark.asyncio
    async def test_returns_placeholder_when_not_configured(self) -> None:
        inp = AskExpertInput(prompt="What is the best architecture for this module?")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert "error" in result.data
        assert result.data["error"] == "Expert model not yet configured"
        assert result.data["prompt"] == "What is the best architecture for this module?"
        assert "not yet configured" in result.result_for_assistant

    @pytest.mark.asyncio
    async def test_with_optional_fields(self) -> None:
        inp = AskExpertInput(
            prompt="Review this code",
            model="claude-opus-4",
            context="This is a performance-critical module",
        )
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        # Still returns placeholder in Phase 3
        assert "error" in result.data

    @pytest.mark.asyncio
    async def test_input_schema(self) -> None:
        schema = self.tool.input_schema()
        assert schema is AskExpertInput
