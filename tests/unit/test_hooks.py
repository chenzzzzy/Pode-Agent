"""Tests for services/hooks/ — Hook system base types and runner.

All tests use mocks — no real subprocess or LLM calls.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pode_agent.services.hooks.base import (
    HookConfig,
    HookEvent,
    HookResult,
    HookState,
    PostToolUsePayload,
    PreToolUsePayload,
    StopPayload,
    UserPromptSubmitPayload,
)
from pode_agent.services.hooks.runner import (
    _aggregate_results,
    _matching_hooks,
    load_hook_configs,
    run_post_tool_use_hooks,
    run_pre_tool_use_hooks,
    run_stop_hooks,
    run_user_prompt_submit_hooks,
)


# ---------------------------------------------------------------------------
# HookConfig / HookEvent / HookResult
# ---------------------------------------------------------------------------


class TestHookConfig:
    def test_parse_from_dict(self) -> None:
        cfg = HookConfig(
            event=HookEvent.PRE_TOOL_USE,
            matcher="bash",
            type="command",
            command=["node", "check.js"],
        )
        assert cfg.event == HookEvent.PRE_TOOL_USE
        assert cfg.matcher == "bash"
        assert cfg.type == "command"
        assert cfg.timeout_ms == 30000

    def test_defaults(self) -> None:
        cfg = HookConfig(event=HookEvent.STOP)
        assert cfg.matcher == "all"
        assert cfg.type == "command"
        assert cfg.command is None
        assert cfg.prompt_text is None


class TestHookResult:
    def test_default_continue(self) -> None:
        result = HookResult()
        assert result.action == "continue"
        assert result.message is None
        assert result.modified_data is None

    def test_block_result(self) -> None:
        result = HookResult(action="block", message="Not allowed")
        assert result.action == "block"
        assert result.message == "Not allowed"


class TestHookState:
    def test_default_state(self) -> None:
        state = HookState()
        assert state.additional_system_prompts == []
        assert state.user_prompt_hooks_ran is False


class TestPayloads:
    def test_user_prompt_submit_payload(self) -> None:
        p = UserPromptSubmitPayload(prompt="hello", messages=[{"role": "user"}])
        data = p.model_dump()
        assert data["prompt"] == "hello"

    def test_pre_tool_use_payload(self) -> None:
        p = PreToolUsePayload(tool_name="bash", tool_input={"cmd": "ls"}, tool_use_id="tu1")
        assert p.tool_name == "bash"

    def test_post_tool_use_payload(self) -> None:
        p = PostToolUsePayload(
            tool_name="bash", tool_input={"cmd": "ls"}, tool_result="ok",
            tool_use_id="tu1", is_error=False,
        )
        assert p.is_error is False

    def test_stop_payload(self) -> None:
        p = StopPayload(messages=[], stop_reason="end_turn")
        assert p.stop_reason == "end_turn"


# ---------------------------------------------------------------------------
# load_hook_configs
# ---------------------------------------------------------------------------


class TestLoadHookConfigs:
    def test_empty_settings(self) -> None:
        assert load_hook_configs() == []

    def test_loads_from_project(self) -> None:
        settings = {
            "hooks": [
                {"event": "PreToolUse", "matcher": "bash", "type": "command", "command": ["echo"]},
            ]
        }
        configs = load_hook_configs(project_settings=settings)
        assert len(configs) == 1
        assert configs[0].event == HookEvent.PRE_TOOL_USE

    def test_merges_project_and_user(self) -> None:
        proj = {"hooks": [{"event": "PreToolUse"}]}
        user = {"hooks": [{"event": "Stop"}]}
        configs = load_hook_configs(project_settings=proj, user_settings=user)
        assert len(configs) == 2

    def test_skips_invalid_config(self) -> None:
        settings = {"hooks": [{"event": "INVALID_EVENT"}]}
        configs = load_hook_configs(project_settings=settings)
        assert len(configs) == 0


# ---------------------------------------------------------------------------
# _matching_hooks
# ---------------------------------------------------------------------------


class TestMatchingHooks:
    def test_match_all(self) -> None:
        configs = [HookConfig(event=HookEvent.PRE_TOOL_USE, matcher="all")]
        matched = _matching_hooks(configs, HookEvent.PRE_TOOL_USE, "bash")
        assert len(matched) == 1

    def test_match_glob(self) -> None:
        configs = [HookConfig(event=HookEvent.PRE_TOOL_USE, matcher="bash*")]
        matched = _matching_hooks(configs, HookEvent.PRE_TOOL_USE, "bash_run")
        assert len(matched) == 1

    def test_no_match(self) -> None:
        configs = [HookConfig(event=HookEvent.PRE_TOOL_USE, matcher="glob")]
        matched = _matching_hooks(configs, HookEvent.PRE_TOOL_USE, "bash")
        assert len(matched) == 0

    def test_different_event(self) -> None:
        configs = [HookConfig(event=HookEvent.STOP)]
        matched = _matching_hooks(configs, HookEvent.PRE_TOOL_USE, "bash")
        assert len(matched) == 0

    def test_no_tool_name_with_specific_matcher(self) -> None:
        configs = [HookConfig(event=HookEvent.PRE_TOOL_USE, matcher="bash")]
        matched = _matching_hooks(configs, HookEvent.PRE_TOOL_USE, None)
        assert len(matched) == 0


# ---------------------------------------------------------------------------
# _aggregate_results
# ---------------------------------------------------------------------------


class TestAggregateResults:
    def test_empty_list_returns_continue(self) -> None:
        result = _aggregate_results([])
        assert result.action == "continue"

    def test_single_continue(self) -> None:
        result = _aggregate_results([HookResult(action="continue")])
        assert result.action == "continue"

    def test_block_overrides_modify(self) -> None:
        results = [
            HookResult(action="modify", modified_data={"x": 1}),
            HookResult(action="block", message="Nope"),
        ]
        result = _aggregate_results(results)
        assert result.action == "block"
        assert result.message == "Nope"

    def test_modify_takes_effect(self) -> None:
        results = [
            HookResult(action="continue"),
            HookResult(action="modify", modified_data={"x": 1}),
        ]
        result = _aggregate_results(results)
        assert result.action == "modify"
        assert result.modified_data == {"x": 1}

    def test_prompts_concatenated(self) -> None:
        results = [
            HookResult(additional_system_prompt="extra1"),
            HookResult(additional_system_prompt="extra2"),
        ]
        result = _aggregate_results(results)
        assert "extra1" in (result.additional_system_prompt or "")
        assert "extra2" in (result.additional_system_prompt or "")


# ---------------------------------------------------------------------------
# Command hook execution (via _execute_command_hook)
# ---------------------------------------------------------------------------


class TestCommandHookExecution:
    async def test_command_hook_returns_continue_on_success(self) -> None:
        from pode_agent.services.hooks.runner import _execute_command_hook

        config = HookConfig(
            event=HookEvent.PRE_TOOL_USE,
            type="command",
            command=["echo", json.dumps({"action": "continue"})],
        )
        # echo will write the JSON to stdout — but the command is actually
        # the hook executable, not our payload. Mock subprocess instead.
        with patch("pode_agent.services.hooks.runner.asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.communicate = AsyncMock(return_value=(
                json.dumps({"action": "block", "message": "denied"}).encode(),
                b"",
            ))
            mock_proc.returncode = 0
            mock_exec.return_value = mock_proc

            result = await _execute_command_hook(config, {"tool_name": "bash"})
            assert result.action == "block"
            assert result.message == "denied"

    async def test_command_hook_continues_on_failure(self) -> None:
        from pode_agent.services.hooks.runner import _execute_command_hook

        config = HookConfig(
            event=HookEvent.PRE_TOOL_USE,
            type="command",
            command=["fail-script"],
        )
        with patch("pode_agent.services.hooks.runner.asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.communicate = AsyncMock(return_value=(b"", b"error"))
            mock_proc.returncode = 1
            mock_exec.return_value = mock_proc

            result = await _execute_command_hook(config, {})
            assert result.action == "continue"

    async def test_command_hook_timeout_continues(self) -> None:
        from pode_agent.services.hooks.runner import _execute_command_hook

        config = HookConfig(
            event=HookEvent.PRE_TOOL_USE,
            type="command",
            command=["slow-script"],
            timeout_ms=100,
        )
        with patch("pode_agent.services.hooks.runner.asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.communicate = AsyncMock(side_effect=TimeoutError)
            mock_proc.kill = MagicMock()
            mock_exec.return_value = mock_proc

            result = await _execute_command_hook(config, {})
            assert result.action == "continue"
            mock_proc.kill.assert_called_once()

    async def test_no_command_returns_continue(self) -> None:
        from pode_agent.services.hooks.runner import _execute_command_hook

        config = HookConfig(event=HookEvent.PRE_TOOL_USE, command=None)
        result = await _execute_command_hook(config, {})
        assert result.action == "continue"


# ---------------------------------------------------------------------------
# Public API runners
# ---------------------------------------------------------------------------


class TestRunUserPromptSubmitHooks:
    async def test_skips_if_already_ran(self) -> None:
        state = HookState(user_prompt_hooks_ran=True)
        result = await run_user_prompt_submit_hooks("hi", [], state)
        assert result.action == "continue"

    async def test_skips_if_no_configs(self) -> None:
        state = HookState()
        result = await run_user_prompt_submit_hooks("hi", [], state)
        assert result.action == "continue"

    async def test_runs_and_marks_state(self) -> None:
        config = HookConfig(event=HookEvent.USER_PROMPT_SUBMIT, matcher="all")
        state = HookState()

        with patch(
            "pode_agent.services.hooks.runner._execute_command_hook",
            return_value=HookResult(action="continue"),
        ) as mock_exec:
            result = await run_user_prompt_submit_hooks(
                "hi", [], state, configs=[config],
            )
            assert result.action == "continue"
            assert state.user_prompt_hooks_ran is True
            mock_exec.assert_called_once()

    async def test_appends_additional_system_prompt(self) -> None:
        config = HookConfig(event=HookEvent.USER_PROMPT_SUBMIT, matcher="all")
        state = HookState()

        with patch(
            "pode_agent.services.hooks.runner._execute_command_hook",
            return_value=HookResult(
                action="continue", additional_system_prompt="Be concise"
            ),
        ):
            await run_user_prompt_submit_hooks("hi", [], state, configs=[config])
            assert "Be concise" in state.additional_system_prompts


class TestRunPreToolUseHooks:
    async def test_no_configs_returns_continue(self) -> None:
        result = await run_pre_tool_use_hooks("bash", {}, "tu1", HookState())
        assert result.action == "continue"

    async def test_matching_hook_executes(self) -> None:
        config = HookConfig(event=HookEvent.PRE_TOOL_USE, matcher="bash")
        state = HookState()

        with patch(
            "pode_agent.services.hooks.runner._execute_command_hook",
            return_value=HookResult(action="block", message="Not allowed"),
        ) as mock_exec:
            result = await run_pre_tool_use_hooks(
                "bash", {"cmd": "ls"}, "tu1", state, configs=[config],
            )
            assert result.action == "block"
            assert result.message == "Not allowed"
            mock_exec.assert_called_once()

    async def test_non_matching_hook_skipped(self) -> None:
        config = HookConfig(event=HookEvent.PRE_TOOL_USE, matcher="glob")
        state = HookState()

        with patch(
            "pode_agent.services.hooks.runner._execute_command_hook",
        ) as mock_exec:
            result = await run_pre_tool_use_hooks(
                "bash", {}, "tu1", state, configs=[config],
            )
            assert result.action == "continue"
            mock_exec.assert_not_called()


class TestRunPostToolUseHooks:
    async def test_no_configs_returns_continue(self) -> None:
        result = await run_post_tool_use_hooks(
            "bash", {}, "ok", "tu1", False, HookState(),
        )
        assert result.action == "continue"

    async def test_matching_hook_executes(self) -> None:
        config = HookConfig(event=HookEvent.POST_TOOL_USE, matcher="bash")
        state = HookState()

        with patch(
            "pode_agent.services.hooks.runner._execute_command_hook",
            return_value=HookResult(action="continue"),
        ) as mock_exec:
            result = await run_post_tool_use_hooks(
                "bash", {"cmd": "ls"}, "ok", "tu1", False, state, configs=[config],
            )
            assert result.action == "continue"
            mock_exec.assert_called_once()


class TestRunStopHooks:
    async def test_no_configs_returns_continue(self) -> None:
        result = await run_stop_hooks([], "end_turn", HookState())
        assert result.action == "continue"

    async def test_stop_hook_can_block(self) -> None:
        config = HookConfig(event=HookEvent.STOP, matcher="all")
        state = HookState()

        with patch(
            "pode_agent.services.hooks.runner._execute_command_hook",
            return_value=HookResult(
                action="block", additional_system_prompt="Keep going"
            ),
        ):
            result = await run_stop_hooks(
                [], "end_turn", state, configs=[config],
            )
            assert result.action == "block"
            assert "Keep going" in state.additional_system_prompts


# ---------------------------------------------------------------------------
# query.py integration: stop hook reentry
# ---------------------------------------------------------------------------


class TestQueryStopHookReentry:
    async def test_stop_hook_forces_continuation(self) -> None:
        """When stop hook blocks, query_core should recurse instead of yielding DONE."""
        from pydantic import BaseModel

        from pode_agent.app.query import QueryOptions, query_core
        from pode_agent.core.permissions.types import PermissionMode
        from pode_agent.services.ai.base import AIResponse, TokenUsage
        from pode_agent.services.hooks.base import HookResult, HookState
        from pode_agent.types.session_events import SessionEvent, SessionEventType

        # Round 1: text response (triggers stop hooks)
        # Round 2: text response (stop hooks allow → DONE)
        call_count = 0

        async def mock_llm(params: Any, config: Any = None) -> Any:
            nonlocal call_count
            call_count += 1
            yield AIResponse(type="text_delta", text=f"Round {call_count}")
            yield AIResponse(
                type="message_done",
                usage=TokenUsage(input_tokens=10, output_tokens=5),
                stop_reason="end_turn",
            )

        hook_state = HookState()

        with (
            patch("pode_agent.app.query.query_llm", side_effect=mock_llm),
            patch(
                "pode_agent.app.query.run_stop_hooks",
                side_effect=[
                    # First stop: block (force continue)
                    HookResult(action="block", additional_system_prompt="Keep going"),
                    # Second stop: allow
                    HookResult(action="continue"),
                ],
            ),
        ):
            session = MagicMock()
            session._messages = []
            session.abort_event = asyncio.Event()
            session._permission_event = asyncio.Event()
            session._last_permission_decision = None
            session.permission_context = MagicMock()
            session.save_message = lambda msg: session._messages.append(msg)
            session.get_messages = lambda: list(session._messages)
            session.tools = []

            options = QueryOptions(model="claude-sonnet-4-5-20251101", cwd="/tmp")

            events: list[SessionEvent] = []
            async for event in query_core(
                messages=[],
                system_prompt="",
                tools=[],
                session=session,
                options=options,
                _hook_state=hook_state,
            ):
                events.append(event)

        # Should have 2 rounds of assistant deltas + 1 DONE
        types = [e.type for e in events]
        assert types.count(SessionEventType.ASSISTANT_DELTA) >= 2
        assert SessionEventType.DONE in types
        assert call_count == 2
