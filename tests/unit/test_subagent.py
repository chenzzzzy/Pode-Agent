"""Tests for services/agents/ — Agent loader, background tasks, fork context."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pode_agent.services.agents.background_tasks import (
    clear_registry,
    get_abort_event,
    get_background_agent_task,
    update_background_agent_task,
    upsert_background_agent_task,
    wait_for_background_agent_task,
)
from pode_agent.services.agents.fork_context import (
    FORK_CONTEXT_TOOL_RESULT_TEXT,
    build_fork_context,
)
from pode_agent.services.agents.loader import (
    BUILTIN_AGENTS,
    load_agents,
    merge_agents,
    parse_agent_markdown,
)
from pode_agent.types.agent import AgentConfig, AgentSource


# ---------------------------------------------------------------------------
# parse_agent_markdown
# ---------------------------------------------------------------------------


class TestParseAgentMarkdown:
    def test_valid(self, tmp_path: Path) -> None:
        content = (
            "---\nagent_type: code-review\n"
            "when_to_use: Review code\n"
            "tools: ['*']\n"
            "---\nYou are a code reviewer."
        )
        config = parse_agent_markdown(content, tmp_path / "agent.md")
        assert config is not None
        assert config.agent_type == "code-review"
        assert config.when_to_use == "Review code"
        assert config.system_prompt == "You are a code reviewer."

    def test_no_frontmatter(self, tmp_path: Path) -> None:
        config = parse_agent_markdown("Just text", tmp_path / "agent.md")
        assert config is None

    def test_invalid_yaml(self, tmp_path: Path) -> None:
        content = "---\n: bad yaml:\n---\nBody"
        config = parse_agent_markdown(content, tmp_path / "agent.md")
        assert config is None


# ---------------------------------------------------------------------------
# load_agents
# ---------------------------------------------------------------------------


class TestLoadAgents:
    async def test_builtin_agents_loaded(self) -> None:
        agents = await load_agents()
        assert "general-purpose" in agents
        assert "Explore" in agents
        assert "Plan" in agents

    async def test_project_agents_override(self, tmp_path: Path) -> None:
        agents_dir = tmp_path / ".pode" / "agents"
        agents_dir.mkdir(parents=True)
        (agents_dir / "Explore.md").write_text(
            "---\nagent_type: Explore\nwhen_to_use: Custom explore\n---\nCustom prompt",
            encoding="utf-8",
        )

        agents = await load_agents(project_dir=tmp_path)
        assert agents["Explore"].when_to_use == "Custom explore"
        assert agents["Explore"].source == AgentSource.PROJECT

    async def test_no_project_dir(self) -> None:
        agents = await load_agents()
        assert len(agents) >= 3  # At least builtins


class TestMergeAgents:
    def test_override(self) -> None:
        base = {
            "a": AgentConfig(agent_type="a", when_to_use="agent a"),
            "b": AgentConfig(agent_type="b", when_to_use="agent b"),
        }
        override = {
            "b": AgentConfig(agent_type="b", when_to_use="overridden"),
            "c": AgentConfig(agent_type="c", when_to_use="agent c"),
        }
        merged = merge_agents(base, override)
        assert merged["b"].when_to_use == "overridden"
        assert "c" in merged


# ---------------------------------------------------------------------------
# Background task registry
# ---------------------------------------------------------------------------


class TestBackgroundTasks:
    def setup_method(self) -> None:
        clear_registry()

    def test_upsert_and_get(self) -> None:
        task = upsert_background_agent_task("agent-1", "Test task", "Do something")
        assert task.agent_id == "agent-1"
        assert task.description == "Test task"

        retrieved = get_background_agent_task("agent-1")
        assert retrieved is not None
        assert retrieved.agent_id == "agent-1"

    def test_get_nonexistent(self) -> None:
        assert get_background_agent_task("nope") is None

    def test_update_status(self) -> None:
        upsert_background_agent_task("agent-2", "Test", "Prompt")
        updated = update_background_agent_task(
            "agent-2", status="completed", result_text="Done!",
        )
        assert updated is not None
        assert updated.status == "completed"
        assert updated.result_text == "Done!"

    def test_update_nonexistent(self) -> None:
        result = update_background_agent_task("nope", status="completed")
        assert result is None

    async def test_wait_completes(self) -> None:
        upsert_background_agent_task("agent-3", "Test", "Prompt")
        update_background_agent_task("agent-3", status="completed")

        task = await wait_for_background_agent_task("agent-3", timeout_ms=100)
        assert task.status == "completed"

    async def test_wait_not_found(self) -> None:
        with pytest.raises(KeyError):
            await wait_for_background_agent_task("nope")

    def test_abort_event(self) -> None:
        upsert_background_agent_task("agent-4", "Test", "Prompt")
        event = get_abort_event("agent-4")
        assert event is not None
        assert isinstance(event, asyncio.Event)

    def test_abort_event_nonexistent(self) -> None:
        assert get_abort_event("nope") is None


# ---------------------------------------------------------------------------
# Fork context
# ---------------------------------------------------------------------------


class TestForkContext:
    def test_disabled_returns_only_prompt(self) -> None:
        ctx, prompt = build_fork_context(
            enabled=False, prompt="Do something",
        )
        assert ctx == []
        assert len(prompt) == 1
        assert prompt[0]["role"] == "user"
        assert prompt[0]["content"] == "Do something"

    def test_enabled_no_log_returns_only_prompt(self) -> None:
        ctx, prompt = build_fork_context(
            enabled=True, prompt="Do something", tool_use_id="tu_001",
        )
        assert ctx == []
        assert len(prompt) == 1

    def test_enabled_reads_jsonl_and_slices(self, tmp_path: Path) -> None:
        # Write a fake JSONL log
        import json

        log_file = tmp_path / "session.jsonl"
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": [
                {"type": "text", "text": "Let me search"},
            ]},
            {"role": "assistant", "content": [
                {"type": "text", "text": "Now running task"},
                {"type": "tool_use", "id": "tu_001", "name": "Task", "input": {}},
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "tu_001"},
            ]},
        ]
        with open(log_file, "w", encoding="utf-8") as f:
            for msg in messages:
                f.write(json.dumps(msg) + "\n")

        ctx, prompt = build_fork_context(
            enabled=True,
            prompt="Sub task",
            tool_use_id="tu_001",
            message_log_name=str(log_file),
        )

        # ctx should have messages BEFORE the assistant turn with tu_001
        assert len(ctx) == 2
        assert ctx[0]["role"] == "user"
        assert ctx[1]["role"] == "assistant"

        # prompt should have: synthetic assistant + boundary user + actual prompt
        assert len(prompt) == 3
        assert prompt[0]["role"] == "assistant"  # synthetic tool_use
        assert prompt[1]["role"] == "user"  # boundary marker
        assert prompt[2]["role"] == "user"  # actual task
        assert prompt[2]["content"] == "Sub task"

    def test_no_matching_tool_use_returns_all(self, tmp_path: Path) -> None:
        import json

        log_file = tmp_path / "session.jsonl"
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": [{"type": "text", "text": "Hi"}]},
        ]
        with open(log_file, "w", encoding="utf-8") as f:
            for msg in messages:
                f.write(json.dumps(msg) + "\n")

        ctx, prompt = build_fork_context(
            enabled=True,
            prompt="Sub task",
            tool_use_id="tu_999",
            message_log_name=str(log_file),
        )
        # All messages returned since no match
        assert len(ctx) == 2
