"""Unit tests for SkillTool — full implementation.

Reference: docs/skill-system.md — SkillTool 设计
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from pode_agent.core.tools.base import ToolUseContext
from pode_agent.tools.ai.skill import SkillInput, SkillTool
from pode_agent.types.skill import (
    CommandScope,
    CommandSource,
    CustomCommandFrontmatter,
    CustomCommandWithScope,
)


def _ctx() -> ToolUseContext:
    return ToolUseContext(abort_event=asyncio.Event())


def _find_result(outputs: list[Any]) -> Any:
    for o in reversed(outputs):
        if o.type == "result":
            return o
    raise AssertionError("No result output found")


def _make_skill_cmd(
    name: str = "test-skill",
    description: str = "Test skill",
    content: str = "Hello $ARGUMENTS, welcome!",
    allowed_tools: list[str] | None = None,
    model: str | None = None,
    max_thinking_tokens: int | None = None,
) -> CustomCommandWithScope:
    """Helper to create a skill CustomCommandWithScope for testing."""
    fm = CustomCommandFrontmatter(
        name=name,
        description=description,
        allowed_tools=allowed_tools,
        model=model,
        max_thinking_tokens=max_thinking_tokens,
    )
    return CustomCommandWithScope(
        name=name,
        description=description,
        file_path=Path(f"/fake/{name}.md"),
        frontmatter=fm,
        content=content,
        source=CommandSource.LOCAL_SETTINGS,
        scope=CommandScope.PROJECT,
        is_skill=True,
        is_hidden=True,
    )


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
        """Skills are concurrency-safe per spec."""
        assert self.tool.is_concurrency_safe() is True

    def test_input_schema(self) -> None:
        schema = self.tool.input_schema()
        assert schema is SkillInput
        # Verify field names match spec
        fields = schema.model_fields
        assert "skill" in fields
        assert "args" in fields


class TestSkillToolCall:
    def setup_method(self) -> None:
        self.tool = SkillTool()

    @pytest.mark.asyncio
    async def test_returns_error_when_skill_not_found(self) -> None:
        """When no skill matches, return error."""
        with patch(
            "pode_agent.tools.ai.skill.load_custom_commands",
            new_callable=AsyncMock,
            return_value=[],
        ):
            inp = SkillInput(skill="nonexistent")
            outputs = [o async for o in self.tool.call(inp, _ctx())]
            result = _find_result(outputs)

            assert result.data.get("error") is not None

    @pytest.mark.asyncio
    async def test_skill_invocation_with_args(self) -> None:
        """When skill is found, returns prompt with $ARGUMENTS replaced."""
        cmd = _make_skill_cmd(content="Hello $ARGUMENTS, welcome!")

        with patch(
            "pode_agent.tools.ai.skill.load_custom_commands",
            new_callable=AsyncMock,
            return_value=[cmd],
        ):
            inp = SkillInput(skill="test-skill", args="world")
            outputs = [o async for o in self.tool.call(inp, _ctx())]
            result = _find_result(outputs)

            assert result.data.get("success") is True
            assert result.data["command_name"] == "test-skill"
            # Verify new_messages contains the prompt with $ARGUMENTS replaced
            assert result.new_messages is not None
            assert len(result.new_messages) > 0
            assert "Hello world, welcome!" in result.new_messages[0]["content"]

    @pytest.mark.asyncio
    async def test_skill_with_context_modifier(self) -> None:
        """When frontmatter has allowed_tools, context_modifier is set."""
        cmd = _make_skill_cmd(
            allowed_tools=["bash", "read", "glob", "grep"],
            model="sonnet",
            max_thinking_tokens=5000,
        )

        with patch(
            "pode_agent.tools.ai.skill.load_custom_commands",
            new_callable=AsyncMock,
            return_value=[cmd],
        ):
            inp = SkillInput(skill="test-skill")
            outputs = [o async for o in self.tool.call(inp, _ctx())]
            result = _find_result(outputs)

            assert result.context_modifier is not None
            assert result.context_modifier.allowed_tools == [
                "bash", "read", "glob", "grep",
            ]
            assert result.context_modifier.max_thinking_tokens == 5000

    @pytest.mark.asyncio
    async def test_skill_without_context_modifier(self) -> None:
        """When frontmatter has no modifier fields, context_modifier is None."""
        cmd = _make_skill_cmd()

        with patch(
            "pode_agent.tools.ai.skill.load_custom_commands",
            new_callable=AsyncMock,
            return_value=[cmd],
        ):
            inp = SkillInput(skill="test-skill")
            outputs = [o async for o in self.tool.call(inp, _ctx())]
            result = _find_result(outputs)

            assert result.context_modifier is None

    @pytest.mark.asyncio
    async def test_skill_args_appended_when_no_placeholder(self) -> None:
        """When content has no $ARGUMENTS, args are appended."""
        cmd = _make_skill_cmd(content="Just do the thing.")

        with patch(
            "pode_agent.tools.ai.skill.load_custom_commands",
            new_callable=AsyncMock,
            return_value=[cmd],
        ):
            inp = SkillInput(skill="test-skill", args="extra info")
            outputs = [o async for o in self.tool.call(inp, _ctx())]
            result = _find_result(outputs)

            assert result.new_messages is not None
            content = result.new_messages[0]["content"]
            assert "Just do the thing." in content
            assert "extra info" in content
