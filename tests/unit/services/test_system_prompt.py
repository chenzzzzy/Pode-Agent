"""Tests for system prompt dynamic assembly."""

from __future__ import annotations

from unittest.mock import MagicMock

from pode_agent.core.permissions.types import PermissionMode
from pode_agent.services.system.system_prompt import (
    BASE_SYSTEM_PROMPT,
    build_system_prompt,
)


def _make_tool(name: str, desc: str = "A tool") -> MagicMock:
    tool = MagicMock()
    tool.name = name
    tool.description = desc
    return tool


class TestBuildSystemPromptBasic:
    """Tests for basic prompt assembly (Phase 2 compat)."""

    def test_base_only(self) -> None:
        result = build_system_prompt("Hello", "")
        assert result == "Hello"

    def test_base_with_cwd(self) -> None:
        result = build_system_prompt("Hello", "/home/user")
        assert "Hello" in result
        assert "/home/user" in result

    def test_base_system_prompt_content(self) -> None:
        assert "Pode" in BASE_SYSTEM_PROMPT
        assert "coding assistant" in BASE_SYSTEM_PROMPT


class TestBuildSystemPromptPlanMode:
    """Tests for plan mode prompt injection."""

    def test_plan_mode_adds_instructions(self) -> None:
        result = build_system_prompt(
            "base", "/cwd", permission_mode=PermissionMode.PLAN,
        )
        assert "plan_mode" in result
        assert "read-only tools" in result

    def test_default_mode_no_plan_instructions(self) -> None:
        result = build_system_prompt(
            "base", "/cwd", permission_mode=PermissionMode.DEFAULT,
        )
        assert "plan_mode" not in result

    def test_bypass_mode_no_plan_instructions(self) -> None:
        result = build_system_prompt(
            "base", "/cwd", permission_mode=PermissionMode.BYPASS_PERMISSIONS,
        )
        assert "plan_mode" not in result


class TestBuildSystemPromptTools:
    """Tests for tool reminders injection."""

    def test_tools_listed(self) -> None:
        tools = [
            _make_tool("bash", "Execute shell commands"),
            _make_tool("file_read", "Read file contents"),
        ]
        result = build_system_prompt("base", "/cwd", tools=tools)
        assert "available_tools" in result
        assert "bash" in result
        assert "file_read" in result

    def test_no_tools_no_section(self) -> None:
        result = build_system_prompt("base", "/cwd", tools=None)
        assert "available_tools" not in result

    def test_empty_tools_no_section(self) -> None:
        result = build_system_prompt("base", "/cwd", tools=[])
        assert "available_tools" not in result


class TestBuildSystemPromptPlan:
    """Tests for active plan context injection."""

    def test_active_plan_shown(self) -> None:
        from pode_agent.types.plan import Plan, PlanStep, PlanStatus

        plan = Plan(
            objective="Refactor auth",
            steps=[
                PlanStep(index=1, title="Read code"),
                PlanStep(index=2, title="Modify", status="done"),
            ],
            status=PlanStatus.EXECUTING,
        )
        result = build_system_prompt("base", "/cwd", plan=plan)
        assert "active_plan" in result
        assert "Refactor auth" in result
        assert "Read code" in result

    def test_no_plan_no_section(self) -> None:
        result = build_system_prompt("base", "/cwd", plan=None)
        assert "active_plan" not in result


class TestBuildSystemPromptTodos:
    """Tests for todo list context injection."""

    def test_todos_shown(self) -> None:
        todos = [
            {"content": "Fix bug", "status": "in_progress"},
            {"content": "Write tests", "status": "pending"},
        ]
        result = build_system_prompt("base", "/cwd", todos=todos)
        assert "todos" in result
        assert "Fix bug" in result
        assert "Write tests" in result

    def test_no_todos_no_section(self) -> None:
        result = build_system_prompt("base", "/cwd", todos=None)
        assert "todos" not in result

    def test_empty_todos_no_section(self) -> None:
        result = build_system_prompt("base", "/cwd", todos=[])
        assert "todos" not in result


class TestBuildSystemPromptCombined:
    """Tests for all sections combined."""

    def test_all_sections(self) -> None:
        from pode_agent.types.plan import Plan, PlanStep

        plan = Plan(objective="Test", steps=[PlanStep(index=1, title="Step 1")])
        tools = [_make_tool("bash")]
        todos = [{"content": "Task", "status": "pending"}]

        result = build_system_prompt(
            "base",
            "/cwd",
            permission_mode=PermissionMode.PLAN,
            tools=tools,
            plan=plan,
            todos=todos,
        )
        assert "base" in result
        assert "/cwd" in result
        assert "plan_mode" in result
        assert "bash" in result
        assert "Test" in result
        assert "Task" in result
