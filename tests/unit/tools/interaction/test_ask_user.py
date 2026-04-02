"""Unit tests for AskUserQuestionTool."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from pode_agent.core.tools.base import ToolUseContext
from pode_agent.tools.interaction.ask_user import AskUserInput, AskUserQuestionTool

_UNSET: object = object()


def _ctx(*, abort_event: asyncio.Event | None | object = _UNSET) -> ToolUseContext:
    actual = asyncio.Event() if abort_event is _UNSET else abort_event  # type: ignore[arg-type]
    return ToolUseContext(abort_event=actual)  # type: ignore[arg-type]


def _find_result(outputs: list[Any]) -> Any:
    for o in reversed(outputs):
        if o.type == "result":
            return o
    raise AssertionError("No result output found")


class TestAskUserToolProperties:
    def setup_method(self) -> None:
        self.tool = AskUserQuestionTool()

    def test_name(self) -> None:
        assert self.tool.name == "ask_user_question"

    @pytest.mark.asyncio
    async def test_is_enabled(self) -> None:
        assert await self.tool.is_enabled() is True

    def test_is_read_only(self) -> None:
        assert self.tool.is_read_only() is True

    def test_needs_permissions(self) -> None:
        assert self.tool.needs_permissions() is False

    def test_is_concurrency_safe(self) -> None:
        assert self.tool.is_concurrency_safe() is True


class TestAskUserToolCall:
    def setup_method(self) -> None:
        self.tool = AskUserQuestionTool()

    @pytest.mark.asyncio
    async def test_yields_question_in_interactive_mode(self) -> None:
        inp = AskUserInput(question="What framework should we use?")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert result.data["question"] == "What framework should we use?"
        assert result.data["options"] is None
        assert result.result_for_assistant == "What framework should we use?"

    @pytest.mark.asyncio
    async def test_yields_question_with_options(self) -> None:
        inp = AskUserInput(
            question="Which language?",
            options=["Python", "TypeScript", "Go"],
        )
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert "Python" in result.result_for_assistant
        assert "TypeScript" in result.result_for_assistant
        assert "Go" in result.result_for_assistant

    @pytest.mark.asyncio
    async def test_error_in_non_interactive_mode(self) -> None:
        inp = AskUserInput(question="What should I do?")
        outputs = [o async for o in self.tool.call(inp, _ctx(abort_event=None))]
        result = _find_result(outputs)

        assert "error" in result.data
        assert "non-interactive" in result.result_for_assistant.lower()

    @pytest.mark.asyncio
    async def test_input_schema(self) -> None:
        schema = self.tool.input_schema()
        assert schema is AskUserInput
