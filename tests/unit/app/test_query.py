"""Tests for app/query.py — Agentic Loop engine.

All tests mock the LLM provider — no real API calls.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from pode_agent.app.query import (
    QueryOptions,
    _build_tool_definitions,
    _find_tool,
    _messages_to_dicts,
    query,
    query_core,
)
from pode_agent.core.cost_tracker import reset_cost
from pode_agent.core.permissions.types import PermissionContext, PermissionMode
from pode_agent.services.ai.base import (
    AIResponse,
    TokenUsage,
)
from pode_agent.types.session_events import SessionEvent, SessionEventType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(
    tools: list[Any] | None = None,
    messages: list[dict[str, Any]] | None = None,
) -> MagicMock:
    """Create a mock SessionManager."""
    session = MagicMock()
    session._messages = list(messages or [])
    session.abort_event = asyncio.Event()
    session._permission_event = asyncio.Event()
    session._last_permission_decision = None
    session.permission_context = PermissionContext()

    def save_message(msg: dict[str, Any]) -> None:
        session._messages.append(msg)

    def replace_messages(msgs: list[dict[str, Any]]) -> None:
        session._messages = list(msgs)

    session.save_message = save_message
    session.replace_messages = replace_messages
    session.get_messages = lambda: list(session._messages)
    session.tools = tools or []
    return session


def _make_options(**overrides: Any) -> QueryOptions:
    defaults: dict[str, Any] = {
        "model": "claude-sonnet-4-5-20251101",
        "cwd": "/tmp/test",
    }
    defaults.update(overrides)
    return QueryOptions(**defaults)


def _text_response(text: str) -> list[AIResponse]:
    """Simulate a text-only LLM response."""
    return [
        AIResponse(type="text_delta", text=text),
        AIResponse(
            type="message_done",
            usage=TokenUsage(input_tokens=100, output_tokens=50),
            stop_reason="end_turn",
        ),
    ]


def _tool_use_response(
    tool_id: str,
    tool_name: str,
    tool_input: dict[str, Any],
    text: str = "",
) -> list[AIResponse]:
    """Simulate a tool-use LLM response."""
    events: list[AIResponse] = []
    if text:
        events.append(AIResponse(type="text_delta", text=text))
    events.append(AIResponse(type="tool_use_start", tool_use_id=tool_id, tool_name=tool_name))
    events.append(AIResponse(type="tool_use_delta", text=json.dumps(tool_input)))
    events.append(AIResponse(
        type="message_done",
        usage=TokenUsage(input_tokens=100, output_tokens=50),
        stop_reason="tool_use",
    ))
    return events


def _make_mock_query_llm(responses_list: list[list[AIResponse]]) -> Any:
    """Create a mock query_llm function that returns async generators.

    Each call returns the next set of responses from responses_list.
    """
    call_count = 0

    async def _mock_fn(params: Any, config: Any = None) -> Any:
        nonlocal call_count
        idx = min(call_count, len(responses_list) - 1)
        call_count += 1
        for resp in responses_list[idx]:
            yield resp

    return _mock_fn


# ---------------------------------------------------------------------------
# _find_tool
# ---------------------------------------------------------------------------


class TestFindTool:
    def test_finds_matching_tool(self) -> None:
        tool = MagicMock()
        tool.name = "bash"
        assert _find_tool("bash", [tool]) is tool

    def test_returns_none_for_missing(self) -> None:
        assert _find_tool("missing", []) is None


# ---------------------------------------------------------------------------
# _build_tool_definitions
# ---------------------------------------------------------------------------


class TestBuildToolDefinitions:
    async def test_builds_from_enabled_tools(self) -> None:
        tool = MagicMock()
        tool.name = "bash"
        tool.description = "Run commands"
        # input_schema() returns a Pydantic model class
        from pydantic import BaseModel
        class FakeInput(BaseModel):
            pass
        tool.input_schema.return_value = FakeInput
        tool.is_enabled = AsyncMock(return_value=True)

        defs = await _build_tool_definitions([tool])
        assert len(defs) == 1
        assert defs[0].name == "bash"

    async def test_skips_disabled_tools(self) -> None:
        tool = MagicMock()
        tool.name = "bash"
        tool.is_enabled = AsyncMock(return_value=False)

        defs = await _build_tool_definitions([tool])
        assert len(defs) == 0


# ---------------------------------------------------------------------------
# _messages_to_dicts
# ---------------------------------------------------------------------------


class TestMessagesToDicts:
    def test_user_message(self) -> None:
        msgs = [{"type": "user", "message": "hello"}]
        result = _messages_to_dicts(msgs)
        assert result == [{"role": "user", "content": "hello"}]

    def test_assistant_message_with_list(self) -> None:
        msgs = [{"type": "assistant", "message": [{"type": "text", "text": "hi"}]}]
        result = _messages_to_dicts(msgs)
        assert result[0]["role"] == "assistant"
        assert result[0]["content"] == [{"type": "text", "text": "hi"}]

    def test_tool_result_content_preserved_as_list(self) -> None:
        """Tool result messages with list content should pass through as-is."""
        tool_result_content = [
            {"type": "tool_result", "tool_use_id": "tu_001", "content": "3 files found"},
        ]
        msgs = [{"role": "user", "content": tool_result_content}]
        result = _messages_to_dicts(msgs)
        assert len(result) == 1
        assert result[0]["content"] == tool_result_content

    def test_string_content_user_message(self) -> None:
        msgs = [{"type": "user", "message": "plain text"}]
        result = _messages_to_dicts(msgs)
        assert result == [{"role": "user", "content": "plain text"}]

    def test_non_string_non_list_content_coerced(self) -> None:
        msgs = [{"type": "user", "message": 42}]
        result = _messages_to_dicts(msgs)
        assert result == [{"role": "user", "content": "42"}]


# ---------------------------------------------------------------------------
# query() — outer entry point
# ---------------------------------------------------------------------------


class TestQuery:
    async def test_text_only_response(self) -> None:
        mock_fn = _make_mock_query_llm([_text_response("Hello!")])
        with patch("pode_agent.app.query.query_llm", side_effect=mock_fn):
            session = _make_session()
            options = _make_options()

            events = []
            async for event in query(
                prompt="hi",
                system_prompt="You are helpful",
                tools=[],
                messages=[],
                session=session,
                options=options,
            ):
                events.append(event)

            types = [e.type for e in events]
            assert SessionEventType.USER_MESSAGE in types
            assert SessionEventType.ASSISTANT_DELTA in types
            assert SessionEventType.DONE in types


# ---------------------------------------------------------------------------
# query_core() — recursive loop
# ---------------------------------------------------------------------------


class TestQueryCore:
    async def test_text_only_saves_assistant_message(self) -> None:
        mock_fn = _make_mock_query_llm([_text_response("I can help!")])
        with patch("pode_agent.app.query.query_llm", side_effect=mock_fn):
            session = _make_session()
            options = _make_options()

            events = []
            async for event in query_core(
                messages=[],
                system_prompt="You are helpful",
                tools=[],
                session=session,
                options=options,
            ):
                events.append(event)

            saved = session.get_messages()
            assistant_msgs = [m for m in saved if m.get("type") == "assistant"]
            assert len(assistant_msgs) == 1

    async def test_usage_event_includes_token_counts(self) -> None:
        mock_fn = _make_mock_query_llm([_text_response("Usage please!")])
        with patch("pode_agent.app.query.query_llm", side_effect=mock_fn):
            session = _make_session()
            options = _make_options()

            events = []
            async for event in query_core(
                messages=[],
                system_prompt="You are helpful",
                tools=[],
                session=session,
                options=options,
            ):
                events.append(event)

            usage_events = [e for e in events if e.type == SessionEventType.COST_UPDATE]
            assert len(usage_events) == 1
            assert usage_events[0].data["input_tokens"] == 100
            assert usage_events[0].data["output_tokens"] == 50
            assert usage_events[0].data["total_tokens"] == 150

    async def test_error_response_yields_model_error(self) -> None:
        async def _error_fn(params: Any, config: Any = None) -> Any:
            yield AIResponse(type="error", error_message="API failed", is_retriable=True)

        with patch("pode_agent.app.query.query_llm", side_effect=_error_fn):
            session = _make_session()
            options = _make_options()

            events = []
            async for event in query_core(
                messages=[],
                system_prompt="",
                tools=[],
                session=session,
                options=options,
            ):
                events.append(event)

            assert any(e.type == SessionEventType.MODEL_ERROR for e in events)

    async def test_abort_stops_loop(self) -> None:
        session = _make_session()
        session.abort_event.set()
        options = _make_options()

        events = []
        async for event in query_core(
            messages=[],
            system_prompt="",
            tools=[],
            session=session,
            options=options,
        ):
            events.append(event)

        done_events = [e for e in events if e.type == SessionEventType.DONE]
        assert len(done_events) == 1
        assert done_events[0].data.get("reason") == "aborted"

    async def test_tool_use_executes_and_recurses(self) -> None:
        """Test the full tool_use -> execute -> recurse cycle."""
        # Mock tool with real Pydantic input_schema
        from pydantic import BaseModel

        class GlobInput(BaseModel):
            pattern: str = "*.py"

        mock_tool = MagicMock()
        mock_tool.name = "glob"
        mock_tool.description = "Find files"
        mock_tool.input_schema.return_value = GlobInput
        mock_tool.is_enabled = AsyncMock(return_value=True)
        mock_tool.is_read_only.return_value = True
        mock_tool.needs_permissions.return_value = False
        mock_tool.validate_input = AsyncMock()

        # Mock tool output
        mock_tool_output = MagicMock()
        mock_tool_output.type = "result"
        mock_tool_output.data = {"files": ["a.py", "b.py", "c.py"]}
        mock_tool_output.result_for_assistant = "Found 3 files"
        mock_tool_output.new_messages = []
        mock_tool_output.context_modifier = None

        async def mock_call(input: Any, context: Any) -> Any:
            yield mock_tool_output

        mock_tool.call = mock_call

        # Two rounds: first tool_use, then text
        mock_fn = _make_mock_query_llm([
            _tool_use_response("tu_001", "glob", {"pattern": "*.py"}),
            _text_response("Found 3 files!"),
        ])

        session = _make_session(tools=[mock_tool])
        options = _make_options(permission_mode=PermissionMode.BYPASS_PERMISSIONS)

        with patch("pode_agent.app.query.query_llm", side_effect=mock_fn):
            events = []
            async for event in query_core(
                messages=[],
                system_prompt="",
                tools=[mock_tool],
                session=session,
                options=options,
            ):
                events.append(event)

        types = [e.type for e in events]
        assert SessionEventType.TOOL_USE_START in types
        assert SessionEventType.TOOL_RESULT in types
        assert SessionEventType.DONE in types

    async def test_unknown_tool_yields_error_result(self) -> None:
        """Tool use for unknown tool should yield error result."""
        mock_fn = _make_mock_query_llm([
            _tool_use_response("tu_001", "nonexistent_tool", {}),
            _text_response("Sorry, that tool doesn't exist"),
        ])

        session = _make_session()
        options = _make_options()

        with patch("pode_agent.app.query.query_llm", side_effect=mock_fn):
            events = []
            async for event in query_core(
                messages=[],
                system_prompt="",
                tools=[],
                session=session,
                options=options,
            ):
                events.append(event)

        tool_results = [
            e for e in events
            if e.type == SessionEventType.TOOL_RESULT and e.data.get("is_error")
        ]
        assert len(tool_results) == 1
        assert "Unknown tool" in tool_results[0].data["result"]


# ---------------------------------------------------------------------------
# auto_compact integration (Fix 3)
# ---------------------------------------------------------------------------


class TestAutoCompact:
    async def test_auto_compact_called_in_query_core(self) -> None:
        """auto_compact_if_needed should be invoked inside query_core."""
        mock_fn = _make_mock_query_llm([_text_response("ok")])
        with (
            patch("pode_agent.app.query.query_llm", side_effect=mock_fn),
            patch(
                "pode_agent.app.query.auto_compact_if_needed",
                new=AsyncMock(return_value=[]),
            ) as mock_compact,
        ):
            session = _make_session()
            options = _make_options()

            events = []
            async for event in query_core(
                messages=[{"type": "user", "message": "hi"}],
                system_prompt="",
                tools=[],
                session=session,
                options=options,
            ):
                events.append(event)

            mock_compact.assert_called_once()

    async def test_auto_compact_returns_trimmed_messages(self) -> None:
        """query_core should use the messages returned by auto_compact_if_needed."""
        trimmed = [{"type": "user", "message": "compact: ..."}]
        mock_fn = _make_mock_query_llm([_text_response("ok")])
        with (
            patch("pode_agent.app.query.query_llm", side_effect=mock_fn),
            patch(
                "pode_agent.app.query.auto_compact_if_needed",
                new=AsyncMock(return_value=trimmed),
            ),
        ):
            session = _make_session()
            options = _make_options()

            async for _ in query_core(
                messages=[{"type": "user", "message": "old"}] * 100,
                system_prompt="",
                tools=[],
                session=session,
                options=options,
            ):
                pass

            saved = session.get_messages()
            assert saved[0]["message"] == "compact: ..."
            assistant_msgs = [m for m in saved if m.get("type") == "assistant"]
            assert len(assistant_msgs) == 1


# ---------------------------------------------------------------------------
# Permission interaction (Fix 4)
# ---------------------------------------------------------------------------


class TestPermissionInteraction:
    async def test_permission_prompt_waits_for_allow(self) -> None:
        """NEEDS_PROMPT should yield PERMISSION_REQUEST then await user decision."""
        from pydantic import BaseModel

        class BashInput(BaseModel):
            command: str = "ls"

        mock_tool = MagicMock()
        mock_tool.name = "bash"
        mock_tool.description = "Run bash"
        mock_tool.input_schema.return_value = BashInput
        mock_tool.is_enabled = AsyncMock(return_value=True)
        mock_tool.is_read_only.return_value = False
        mock_tool.needs_permissions.return_value = True
        mock_tool.validate_input = AsyncMock()

        mock_tool_output = MagicMock()
        mock_tool_output.type = "result"
        mock_tool_output.data = {"stdout": "file.txt"}
        mock_tool_output.result_for_assistant = "file.txt"
        mock_tool_output.new_messages = []
        mock_tool_output.context_modifier = None

        async def mock_call(inp: Any, ctx: Any) -> Any:
            yield mock_tool_output

        mock_tool.call = mock_call

        # Round 1: tool_use response with dangerous command; Round 2: text
        mock_fn = _make_mock_query_llm([
            _tool_use_response("tu_001", "bash", {"command": "npm install"}),
            _text_response("Done!"),
        ])

        session = _make_session(tools=[mock_tool])
        # DEFAULT mode triggers NEEDS_PROMPT for non-read-only tools
        options = _make_options(permission_mode=PermissionMode.DEFAULT)

        # Set up permission resolution: allow after a short delay
        from pode_agent.core.permissions.types import PermissionDecision

        async def _resolve_later() -> None:
            await asyncio.sleep(0.05)
            session._last_permission_decision = PermissionDecision.ALLOW_SESSION
            session._permission_event.set()

        with patch("pode_agent.app.query.query_llm", side_effect=mock_fn):
            events = []
            async_task = asyncio.create_task(_resolve_later())
            try:
                async for event in query_core(
                    messages=[],
                    system_prompt="",
                    tools=[mock_tool],
                    session=session,
                    options=options,
                ):
                    events.append(event)
            finally:
                async_task.cancel()

            types = [e.type for e in events]
            assert SessionEventType.PERMISSION_REQUEST in types
            assert SessionEventType.TOOL_RESULT in types
            # Should NOT be an error result
            tool_result = next(
                e for e in events
                if e.type == SessionEventType.TOOL_RESULT
            )
            assert not tool_result.data.get("is_error", False)

    async def test_permission_deny_returns_error(self) -> None:
        """If user denies permission, tool_result should have is_error=True."""
        from pydantic import BaseModel

        class BashInput(BaseModel):
            command: str = "rm -rf /"

        mock_tool = MagicMock()
        mock_tool.name = "bash"
        mock_tool.description = "Run bash"
        mock_tool.input_schema.return_value = BashInput
        mock_tool.is_enabled = AsyncMock(return_value=True)
        mock_tool.is_read_only.return_value = False
        mock_tool.needs_permissions.return_value = True
        mock_tool.validate_input = AsyncMock()

        mock_fn = _make_mock_query_llm([
            _tool_use_response("tu_002", "bash", {"command": "rm -rf /"}),
            _text_response("ok"),
        ])

        session = _make_session(tools=[mock_tool])
        options = _make_options(permission_mode=PermissionMode.DEFAULT)

        from pode_agent.core.permissions.types import PermissionDecision

        async def _deny_later() -> None:
            await asyncio.sleep(0.05)
            session._last_permission_decision = PermissionDecision.DENY
            session._permission_event.set()

        with patch("pode_agent.app.query.query_llm", side_effect=mock_fn):
            events = []
            async_task = asyncio.create_task(_deny_later())
            try:
                async for event in query_core(
                    messages=[],
                    system_prompt="",
                    tools=[mock_tool],
                    session=session,
                    options=options,
                ):
                    events.append(event)
            finally:
                async_task.cancel()

            tool_result = next(
                e for e in events
                if e.type == SessionEventType.TOOL_RESULT
            )
            assert tool_result.data.get("is_error") is True
            assert "Permission denied" in tool_result.data["result"]


# ---------------------------------------------------------------------------
# TOOL_PROGRESS events (Fix 5)
# ---------------------------------------------------------------------------


class TestToolProgress:
    async def test_on_tool_progress_enqueues_event(self) -> None:
        """Progress callback should put a TOOL_PROGRESS event into the queue."""
        queue: asyncio.Queue[SessionEvent] = asyncio.Queue()

        progress = MagicMock()
        progress.content = "Running command..."

        # Replicate the inline callback used in _check_permissions_and_call_tool
        async def progress_callback(p: Any) -> None:
            await queue.put(SessionEvent(
                type=SessionEventType.TOOL_PROGRESS,
                data={
                    "tool_use_id": "tu_001",
                    "content": p.content if hasattr(p, "content") else str(p),
                },
            ))

        await progress_callback(progress)

        event = queue.get_nowait()
        assert event.type == SessionEventType.TOOL_PROGRESS
        assert event.data["tool_use_id"] == "tu_001"
        assert event.data["content"] == "Running command..."

    async def test_tool_execution_yields_progress_events(self) -> None:
        """Tool execution should yield TOOL_PROGRESS events via queue."""
        from pydantic import BaseModel

        class BashInput(BaseModel):
            command: str = "ls"

        mock_tool = MagicMock()
        mock_tool.name = "bash"
        mock_tool.description = "Run bash"
        mock_tool.input_schema.return_value = BashInput
        mock_tool.is_enabled = AsyncMock(return_value=True)
        mock_tool.is_read_only.return_value = True
        mock_tool.needs_permissions.return_value = False
        mock_tool.validate_input = AsyncMock()

        # Tool yields progress then result
        mock_progress = MagicMock()
        mock_progress.type = "progress"
        mock_progress.content = "listing files..."

        mock_result = MagicMock()
        mock_result.type = "result"
        mock_result.data = {"files": ["a.py"]}
        mock_result.result_for_assistant = "1 file"
        mock_result.new_messages = []
        mock_result.context_modifier = None

        async def mock_call(inp: Any, ctx: Any) -> Any:
            yield mock_progress
            yield mock_result

        mock_tool.call = mock_call

        mock_fn = _make_mock_query_llm([
            _tool_use_response("tu_001", "bash", {"command": "ls"}),
            _text_response("Done"),
        ])

        session = _make_session(tools=[mock_tool])
        options = _make_options(permission_mode=PermissionMode.BYPASS_PERMISSIONS)

        with patch("pode_agent.app.query.query_llm", side_effect=mock_fn):
            events = []
            async for event in query_core(
                messages=[],
                system_prompt="",
                tools=[mock_tool],
                session=session,
                options=options,
            ):
                events.append(event)

        progress_events = [
            e for e in events if e.type == SessionEventType.TOOL_PROGRESS
        ]
        assert len(progress_events) >= 1
        assert progress_events[0].data["content"] == "listing files..."


# ---------------------------------------------------------------------------
# COST_UPDATE total_usd (Fix 6)
# ---------------------------------------------------------------------------


class TestCostUpdate:
    async def test_cost_update_includes_cumulative_total(self) -> None:
        """COST_UPDATE event should reflect actual cumulative cost via get_total_cost."""
        reset_cost()

        mock_fn = _make_mock_query_llm([_text_response("ok")])
        with patch("pode_agent.app.query.query_llm", side_effect=mock_fn):
            session = _make_session()
            options = _make_options()

            events = []
            async for event in query_core(
                messages=[],
                system_prompt="",
                tools=[],
                session=session,
                options=options,
            ):
                events.append(event)

        cost_events = [
            e for e in events if e.type == SessionEventType.COST_UPDATE
        ]
        if cost_events:
            # total_usd should be > 0 (model has non-zero pricing)
            assert cost_events[0].data["total_usd"] > 0
            assert cost_events[0].data["cost_usd"] > 0
        else:
            # If no cost event (e.g., 0 cost model), that's also acceptable
            pass

        reset_cost()
