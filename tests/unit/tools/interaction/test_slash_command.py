"""Unit tests for SlashCommandTool."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from pode_agent.core.tools.base import ToolOptions, ToolUseContext
from pode_agent.tools.interaction.slash_command import (
    SlashCommandInput,
    SlashCommandTool,
)


def _ctx(*, model: str | None = None) -> ToolUseContext:
    options = ToolOptions(model=model)
    return ToolUseContext(abort_event=asyncio.Event(), options=options)


def _find_result(outputs: list[Any]) -> Any:
    for o in reversed(outputs):
        if o.type == "result":
            return o
    raise AssertionError("No result output found")


class TestSlashCommandToolProperties:
    def setup_method(self) -> None:
        self.tool = SlashCommandTool()

    def test_name(self) -> None:
        assert self.tool.name == "slash_command"

    @pytest.mark.asyncio
    async def test_is_enabled(self) -> None:
        assert await self.tool.is_enabled() is True

    def test_is_read_only(self) -> None:
        assert self.tool.is_read_only() is True

    def test_needs_permissions(self) -> None:
        assert self.tool.needs_permissions() is False

    def test_is_concurrency_safe(self) -> None:
        assert self.tool.is_concurrency_safe() is True


class TestSlashCommandToolCall:
    def setup_method(self) -> None:
        self.tool = SlashCommandTool()

    @pytest.mark.asyncio
    async def test_help_command(self) -> None:
        inp = SlashCommandInput(command="/help")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert result.data["command"] == "help"
        assert "/help" in result.result_for_assistant
        assert "/clear" in result.result_for_assistant
        assert "/model" in result.result_for_assistant

    @pytest.mark.asyncio
    async def test_help_without_slash(self) -> None:
        inp = SlashCommandInput(command="help")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert result.data["command"] == "help"

    @pytest.mark.asyncio
    async def test_clear_command(self) -> None:
        inp = SlashCommandInput(command="/clear")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert result.data["command"] == "clear"
        assert "cleared" in result.result_for_assistant.lower()

    @pytest.mark.asyncio
    async def test_model_command(self) -> None:
        inp = SlashCommandInput(command="/model")
        outputs = [o async for o in self.tool.call(inp, _ctx(model="claude-sonnet-4-5"))]
        result = _find_result(outputs)

        assert result.data["command"] == "model"
        assert result.data["model"] == "claude-sonnet-4-5"
        assert "claude-sonnet-4-5" in result.result_for_assistant

    @pytest.mark.asyncio
    async def test_model_command_no_model_configured(self) -> None:
        inp = SlashCommandInput(command="/model")
        outputs = [o async for o in self.tool.call(inp, _ctx(model=None))]
        result = _find_result(outputs)

        assert result.data["model"] == "unknown"
        assert "unknown" in result.result_for_assistant

    @pytest.mark.asyncio
    async def test_unknown_command(self) -> None:
        inp = SlashCommandInput(command="/unknown_cmd")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert "error" in result.data
        assert "unknown" in result.result_for_assistant.lower()

    @pytest.mark.asyncio
    async def test_command_with_extra_whitespace(self) -> None:
        inp = SlashCommandInput(command="  //help  ")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert result.data["command"] == "help"

    @pytest.mark.asyncio
    async def test_input_schema(self) -> None:
        schema = self.tool.input_schema()
        assert schema is SlashCommandInput
