"""Unit tests for SkillTool."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from pode_agent.core.tools.base import ToolUseContext
from pode_agent.tools.ai.skill import SkillInput, SkillTool


def _ctx() -> ToolUseContext:
    return ToolUseContext(abort_event=asyncio.Event())


def _find_result(outputs: list[Any]) -> Any:
    for o in reversed(outputs):
        if o.type == "result":
            return o
    raise AssertionError("No result output found")


class TestSkillToolProperties:
    def setup_method(self) -> None:
        self.tool = SkillTool()

    def test_name(self) -> None:
        assert self.tool.name == "skill"

    @pytest.mark.asyncio
    async def test_is_enabled(self) -> None:
        assert await self.tool.is_enabled() is True

    def test_is_read_only(self) -> None:
        assert self.tool.is_read_only() is False

    def test_needs_permissions(self) -> None:
        assert self.tool.needs_permissions() is True

    def test_is_concurrency_safe(self) -> None:
        assert self.tool.is_concurrency_safe() is False


class TestSkillToolCall:
    def setup_method(self) -> None:
        self.tool = SkillTool()

    @pytest.mark.asyncio
    async def test_returns_error_when_no_skills_installed(self) -> None:
        inp = SkillInput(skill_name="code_review")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert "error" in result.data
        assert result.data["skill_name"] == "code_review"
        assert "No skills are currently installed" in result.result_for_assistant

    @pytest.mark.asyncio
    async def test_with_args(self) -> None:
        inp = SkillInput(
            skill_name="deploy",
            args={"environment": "staging", "version": "1.2.3"},
        )
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert "error" in result.data
        assert result.data["skill_name"] == "deploy"

    @pytest.mark.asyncio
    async def test_input_schema(self) -> None:
        schema = self.tool.input_schema()
        assert schema is SkillInput
