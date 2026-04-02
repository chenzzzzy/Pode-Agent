"""Tests for app/query.py — Agentic Loop engine.

All tests mock the LLM provider — no real API calls.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pode_agent.app.query import (
    QueryOptions,
    _build_tool_definitions,
    _find_tool,
    _messages_to_dicts,
    query,
    query_core,
)
from pode_agent.core.permissions.types import PermissionContext, PermissionMode
from pode_agent.services.ai.base import (
    AIResponse,
    TokenUsage,
    ToolUseBlock,
)
from pode_agent.types.session_events import SessionEventType


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
    session.permission_context = PermissionContext()

    def save_message(msg: dict[str, Any]) -> None:
        session._messages.append(msg)

    session.save_message = save_message
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
    def test_builds_from_enabled_tools(self) -> None:
        tool = MagicMock()
        tool.name = "bash"
        tool.description = "Run commands"
        tool.input_schema.return_value = {"type": "object"}
        tool.is_enabled.return_value = True

        defs = _build_tool_definitions([tool])
        assert len(defs) == 1
        assert defs[0].name == "bash"

    def test_skips_disabled_tools(self) -> None:
        tool = MagicMock()
        tool.name = "bash"
        tool.is_enabled.return_value = False

        defs = _build_tool_definitions([tool])
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

    def test_skips_tool_result_messages(self) -> None:
        msgs = [{"type": "user", "message": "result", "tool_use_result": "data"}]
        result = _messages_to_dicts(msgs)
        assert len(result) == 0


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
        # Mock tool
        mock_tool = MagicMock()
        mock_tool.name = "glob"
        mock_tool.description = "Find files"
        mock_tool.input_schema.return_value = {"type": "object", "properties": {}}
        mock_tool.is_enabled.return_value = True
        mock_tool.is_read_only.return_value = True
        mock_tool.needs_permissions.return_value = False
        mock_tool.validate_input = MagicMock()

        # Mock tool output
        mock_tool_output = MagicMock()
        mock_tool_output.type = "result"
        mock_tool_output.data = {"files": ["a.py", "b.py", "c.py"]}
        mock_tool_output.result_for_assistant = "Found 3 files"
        mock_tool_output.new_messages = []

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
