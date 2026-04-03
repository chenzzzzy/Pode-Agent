"""Unit tests for TaskTool — SubAgent execution engine.

Reference: docs/subagent-system.md — TaskTool
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pode_agent.core.tools.base import ToolOutput, ToolUseContext
from pode_agent.tools.agent.task import (
    SUBAGENT_DISALLOWED_TOOL_NAMES,
    TaskInput,
    TaskTool,
    get_task_tools,
    resolve_subagent_model,
)
from pode_agent.types.agent import AgentConfig, AgentModel


def _ctx(**overrides: Any) -> ToolUseContext:
    defaults: dict[str, Any] = {
        "abort_event": asyncio.Event(),
        "tool_use_id": "tu_001",
    }
    defaults.update(overrides)
    return ToolUseContext(**defaults)


def _find_result(outputs: list[ToolOutput]) -> ToolOutput:
    for o in reversed(outputs):
        if o.type == "result":
            return o
    raise AssertionError("No result output found")


# ---------------------------------------------------------------------------
# TaskTool properties
# ---------------------------------------------------------------------------


class TestTaskToolProperties:
    def setup_method(self) -> None:
        self.tool = TaskTool()

    def test_name(self) -> None:
        assert self.tool.name == "Task"

    @pytest.mark.asyncio
    async def test_is_enabled(self) -> None:
        assert await self.tool.is_enabled() is True

    def test_is_read_only(self) -> None:
        assert self.tool.is_read_only() is False

    def test_needs_permissions(self) -> None:
        assert self.tool.needs_permissions() is True

    def test_is_concurrency_safe(self) -> None:
        assert self.tool.is_concurrency_safe() is False


# ---------------------------------------------------------------------------
# TaskInput schema
# ---------------------------------------------------------------------------


class TestTaskInput:
    def test_schema_fields(self) -> None:
        schema = TaskInput.model_json_schema()
        props = schema["properties"]
        assert "description" in props
        assert "prompt" in props
        assert "subagent_type" in props
        assert "model" in props
        assert "resume" in props
        assert "run_in_background" in props

    def test_defaults(self) -> None:
        inp = TaskInput(description="Test", prompt="Do something")
        assert inp.subagent_type == "general-purpose"
        assert inp.model is None
        assert inp.resume is None
        assert inp.run_in_background is False


# ---------------------------------------------------------------------------
# resolve_subagent_model
# ---------------------------------------------------------------------------


class TestResolveSubagentModel:
    def test_env_overrides_all(self) -> None:
        config = AgentConfig(
            agent_type="test", when_to_use="test", model=AgentModel.HAIKU,
        )
        with patch.dict("os.environ", {"PODE_SUBAGENT_MODEL": "custom-model"}):
            result = resolve_subagent_model(
                input_model="sonnet",
                agent_config=config,
                parent_model="parent-model",
            )
        assert result == "custom-model"

    def test_input_model_takes_priority(self) -> None:
        config = AgentConfig(
            agent_type="test", when_to_use="test", model=AgentModel.HAIKU,
        )
        with patch.dict("os.environ", {}, clear=True):
            result = resolve_subagent_model(
                input_model="opus",
                agent_config=config,
                parent_model="parent-model",
            )
        assert "opus" in result

    def test_agent_config_model_used(self) -> None:
        config = AgentConfig(
            agent_type="test", when_to_use="test", model=AgentModel.HAIKU,
        )
        with patch.dict("os.environ", {}, clear=True):
            result = resolve_subagent_model(
                input_model=None,
                agent_config=config,
                parent_model="parent-model",
            )
        assert "haiku" in result

    def test_parent_model_inherited(self) -> None:
        config = AgentConfig(
            agent_type="test", when_to_use="test", model=AgentModel.INHERIT,
        )
        with patch.dict("os.environ", {}, clear=True):
            result = resolve_subagent_model(
                input_model=None,
                agent_config=config,
                parent_model="my-parent-model",
            )
        assert result == "my-parent-model"

    def test_default_used(self) -> None:
        config = AgentConfig(
            agent_type="test", when_to_use="test", model=AgentModel.INHERIT,
        )
        with patch.dict("os.environ", {}, clear=True):
            result = resolve_subagent_model(
                input_model=None,
                agent_config=config,
                parent_model="",
                default_subagent_model="fallback-model",
            )
        assert result == "fallback-model"


# ---------------------------------------------------------------------------
# SUBAGENT_DISALLOWED_TOOL_NAMES
# ---------------------------------------------------------------------------


class TestDisallowedTools:
    def test_task_is_disallowed(self) -> None:
        assert "Task" in SUBAGENT_DISALLOWED_TOOL_NAMES

    def test_task_output_is_disallowed(self) -> None:
        assert "TaskOutput" in SUBAGENT_DISALLOWED_TOOL_NAMES

    def test_kill_shell_is_disallowed(self) -> None:
        assert "KillShell" in SUBAGENT_DISALLOWED_TOOL_NAMES


# ---------------------------------------------------------------------------
# get_task_tools
# ---------------------------------------------------------------------------


class TestGetTaskTools:
    @pytest.mark.asyncio
    async def test_removes_disallowed_tools(self) -> None:
        tools = await get_task_tools()
        tool_names = {t.name for t in tools}
        for disallowed in SUBAGENT_DISALLOWED_TOOL_NAMES:
            assert disallowed not in tool_names

    @pytest.mark.asyncio
    async def test_whitelist_filter(self) -> None:
        config = AgentConfig(
            agent_type="test",
            when_to_use="test",
            tools=["bash", "file_read"],
        )
        tools = await get_task_tools(agent_config=config)
        tool_names = {t.name for t in tools}
        assert tool_names == {"bash", "file_read"}

    @pytest.mark.asyncio
    async def test_blacklist_filter(self) -> None:
        config = AgentConfig(
            agent_type="test",
            when_to_use="test",
            tools="*",
            disallowed_tools=["bash"],
        )
        tools = await get_task_tools(agent_config=config)
        tool_names = {t.name for t in tools}
        assert "bash" not in tool_names


# ---------------------------------------------------------------------------
# TaskTool.call() — foreground (mocked)
# ---------------------------------------------------------------------------


class TestTaskToolForeground:
    def setup_method(self) -> None:
        self.tool = TaskTool()

    @pytest.mark.asyncio
    async def test_unknown_agent_type_returns_error(self) -> None:
        inp = TaskInput(
            description="Test",
            prompt="Do something",
            subagent_type="nonexistent-agent",
        )
        mock_agents: dict[str, Any] = {}
        with patch("pode_agent.tools.agent.task.load_agents", return_value=mock_agents):
            outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)
        assert "error" in result.data
        assert "nonexistent-agent" in result.data["error"]


# ---------------------------------------------------------------------------
# TaskTool.call() — background (mocked)
# ---------------------------------------------------------------------------


class TestTaskToolBackground:
    def setup_method(self) -> None:
        self.tool = TaskTool()

    @pytest.mark.asyncio
    async def test_background_launches_and_returns(self) -> None:
        from pode_agent.services.agents.background_tasks import clear_registry

        clear_registry()

        config = AgentConfig(
            agent_type="general-purpose",
            when_to_use="test",
            system_prompt="You are a test agent.",
        )
        mock_agents = {"general-purpose": config}

        inp = TaskInput(
            description="Test bg",
            prompt="Do something in background",
            subagent_type="general-purpose",
            run_in_background=True,
        )

        with (
            patch("pode_agent.tools.agent.task.load_agents", return_value=mock_agents),
            patch("pode_agent.tools.agent.task.get_task_tools", return_value=[]),
            patch("pode_agent.tools.agent.task.asyncio.create_task"),
        ):
            outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)

        assert result.data["status"] == "async_launched"
        assert "agent_id" in result.data
        assert "background" in result.result_for_assistant.lower()

        clear_registry()
