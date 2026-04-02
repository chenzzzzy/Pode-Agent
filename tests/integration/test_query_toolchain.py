"""Integration tests — query_core + real tools + mock query_llm.

Tests the Agentic Loop with real tool implementations (GlobTool, etc.)
but mock LLM responses. Validates cross-layer integration between
query.py → tools → executor → normalizer without real API calls.

Run with:  uv run pytest tests/integration/test_query_toolchain.py -v
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from pode_agent.app.query import QueryOptions, query_core, _build_tool_definitions
from pode_agent.core.permissions.types import PermissionContext, PermissionMode
from pode_agent.services.ai.base import AIResponse, TokenUsage, ToolUseBlock
from pode_agent.tools.filesystem.glob import GlobTool
from pode_agent.types.session_events import SessionEventType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(
    tools: list[Any] | None = None,
    messages: list[dict[str, Any]] | None = None,
) -> Any:
    """Create a mock SessionManager."""
    session = AsyncMock()
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
        "permission_mode": PermissionMode.BYPASS_PERMISSIONS,
    }
    defaults.update(overrides)
    return QueryOptions(**defaults)


def _text_response(text: str) -> list[AIResponse]:
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
) -> list[AIResponse]:
    return [
        AIResponse(type="tool_use_start", tool_use_id=tool_id, tool_name=tool_name),
        AIResponse(type="tool_use_delta", text=json.dumps(tool_input)),
        AIResponse(
            type="message_done",
            usage=TokenUsage(input_tokens=100, output_tokens=50),
            stop_reason="tool_use",
        ),
    ]


def _multi_tool_use_response(
    tools: list[tuple[str, str, dict[str, Any]]],
) -> list[AIResponse]:
    """Build response with multiple tool_use blocks."""
    events: list[AIResponse] = []
    for tool_id, tool_name, tool_input in tools:
        events.append(
            AIResponse(type="tool_use_start", tool_use_id=tool_id, tool_name=tool_name)
        )
        events.append(
            AIResponse(type="tool_use_delta", text=json.dumps(tool_input))
        )
    events.append(
        AIResponse(
            type="message_done",
            usage=TokenUsage(input_tokens=100, output_tokens=50),
            stop_reason="tool_use",
        ),
    )
    return events


def _make_mock_query_llm(responses_list: list[list[AIResponse]]) -> Any:
    """Create a mock query_llm that returns the next response set per call."""
    call_count = 0

    async def _mock_fn(params: Any, config: Any = None) -> Any:
        nonlocal call_count
        idx = min(call_count, len(responses_list) - 1)
        call_count += 1
        for resp in responses_list[idx]:
            yield resp

    return _mock_fn


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGlobToolExecution:
    """Integration: query_core → GlobTool (real) → result."""

    async def test_glob_tool_with_real_files(self) -> None:
        """GlobTool should find real files in the project repo."""
        # Use the project root (which is the cwd) so security check passes
        repo_root = Path(__file__).resolve().parent.parent.parent

        glob_tool = GlobTool()
        mock_fn = _make_mock_query_llm([
            _tool_use_response(
                "tu_001", "glob",
                {"pattern": "pyproject.toml", "path": str(repo_root)},
            ),
            _text_response("Found pyproject.toml."),
        ])

        session = _make_session(tools=[glob_tool])
        options = _make_options()

        with patch("pode_agent.app.query.query_llm", side_effect=mock_fn):
            events = []
            async for event in query_core(
                messages=[],
                system_prompt="",
                tools=[glob_tool],
                session=session,
                options=options,
            ):
                events.append(event)

        types = [e.type for e in events]
        assert SessionEventType.TOOL_USE_START in types
        assert SessionEventType.TOOL_RESULT in types

        # Verify tool result contains pyproject.toml
        tool_results = [e for e in events if e.type == SessionEventType.TOOL_RESULT]
        assert len(tool_results) >= 1
        result_text = tool_results[0].data.get("result", "")
        assert "pyproject.toml" in result_text


class TestToolUseRecursion:
    """Integration: query_core recursive loop (tool_use → text)."""

    async def test_recurse_two_rounds(self) -> None:
        """query_core should recurse: LLM returns tool_use, then text."""
        from pydantic import BaseModel

        class EchoInput(BaseModel):
            msg: str = ""

        from unittest.mock import MagicMock
        mock_tool = MagicMock()
        mock_tool.name = "echo"
        mock_tool.description = "Echo input"
        mock_tool.input_schema.return_value = EchoInput
        mock_tool.is_enabled = AsyncMock(return_value=True)
        mock_tool.is_read_only.return_value = True
        mock_tool.needs_permissions.return_value = False
        mock_tool.validate_input = AsyncMock()

        async def mock_call(input: Any, context: Any) -> Any:
            from pode_agent.core.tools.base import ToolOutput
            yield ToolOutput(type="result", result_for_assistant=input.msg)

        mock_tool.call = mock_call

        mock_fn = _make_mock_query_llm([
            _tool_use_response("tu_001", "echo", {"msg": "hello"}),
            _text_response("Done!"),
        ])

        session = _make_session(tools=[mock_tool])
        options = _make_options()

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
        # Should have tool execution + second round text
        assert SessionEventType.TOOL_USE_START in types
        assert SessionEventType.TOOL_RESULT in types
        assert SessionEventType.ASSISTANT_DELTA in types
        assert SessionEventType.DONE in types

        # Should have 2 rounds of LLM calls → 2 assistant messages saved
        saved = session.get_messages()
        assistant_msgs = [m for m in saved if m.get("type") == "assistant"]
        assert len(assistant_msgs) == 2


class TestMultiToolReconstruction:
    """Integration: multiple tool_uses in a single LLM response."""

    async def test_two_tools_captured_correctly(self) -> None:
        """When LLM returns 2 tool_uses, both should be captured and executed."""
        from pydantic import BaseModel

        class SimpleInput(BaseModel):
            value: str = ""

        from unittest.mock import MagicMock
        tool_a = MagicMock()
        tool_a.name = "tool_a"
        tool_a.description = "Tool A"
        tool_a.input_schema.return_value = SimpleInput
        tool_a.is_enabled = AsyncMock(return_value=True)
        tool_a.is_read_only.return_value = True
        tool_a.needs_permissions.return_value = False
        tool_a.validate_input = AsyncMock()

        async def call_a(input: Any, context: Any) -> Any:
            from pode_agent.core.tools.base import ToolOutput
            yield ToolOutput(type="result", result_for_assistant=f"A:{input.value}")

        tool_a.call = call_a

        tool_b = MagicMock()
        tool_b.name = "tool_b"
        tool_b.description = "Tool B"
        tool_b.input_schema.return_value = SimpleInput
        tool_b.is_enabled = AsyncMock(return_value=True)
        tool_b.is_read_only.return_value = True
        tool_b.needs_permissions.return_value = False
        tool_b.validate_input = AsyncMock()

        async def call_b(input: Any, context: Any) -> Any:
            from pode_agent.core.tools.base import ToolOutput
            yield ToolOutput(type="result", result_for_assistant=f"B:{input.value}")

        tool_b.call = call_b

        mock_fn = _make_mock_query_llm([
            _multi_tool_use_response([
                ("tu_001", "tool_a", {"value": "first"}),
                ("tu_002", "tool_b", {"value": "second"}),
            ]),
            _text_response("Both done."),
        ])

        session = _make_session(tools=[tool_a, tool_b])
        options = _make_options()

        with patch("pode_agent.app.query.query_llm", side_effect=mock_fn):
            events = []
            async for event in query_core(
                messages=[],
                system_prompt="",
                tools=[tool_a, tool_b],
                session=session,
                options=options,
            ):
                events.append(event)

        # Both tools should have TOOL_USE_START and TOOL_RESULT
        tool_starts = [e for e in events if e.type == SessionEventType.TOOL_USE_START]
        tool_results = [e for e in events if e.type == SessionEventType.TOOL_RESULT]
        assert len(tool_starts) == 2
        assert len(tool_results) == 2

        names = [r.data.get("tool_name") for r in tool_results]
        assert "tool_a" in names
        assert "tool_b" in names


class TestBuildToolDefinitionsIntegration:
    """Integration: _build_tool_definitions with real tools."""

    async def test_real_glob_tool_builds_definition(self) -> None:
        """GlobTool should produce a valid ToolDefinition."""
        glob_tool = GlobTool()
        defs = await _build_tool_definitions([glob_tool])
        assert len(defs) == 1
        assert defs[0].name == "glob"
        assert "pattern" in defs[0].input_schema.get("properties", {})


class TestPermissionBypass:
    """Integration: permission modes affect tool execution."""

    async def test_bypass_mode_executes(self) -> None:
        """BYPASS_PERMISSIONS should allow tool execution without prompts."""
        from pydantic import BaseModel
        from unittest.mock import MagicMock

        class DummyInput(BaseModel):
            pass

        mock_tool = MagicMock()
        mock_tool.name = "danger"
        mock_tool.description = "Dangerous tool"
        mock_tool.input_schema.return_value = DummyInput
        mock_tool.is_enabled = AsyncMock(return_value=True)
        mock_tool.is_read_only.return_value = False
        mock_tool.needs_permissions.return_value = True
        mock_tool.validate_input = AsyncMock()

        from pode_agent.core.tools.base import ToolOutput

        async def mock_call(input: Any, context: Any) -> Any:
            yield ToolOutput(type="result", result_for_assistant="executed")

        mock_tool.call = mock_call

        mock_fn = _make_mock_query_llm([
            _tool_use_response("tu_001", "danger", {}),
            _text_response("OK"),
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

        # Tool should execute (not denied)
        tool_results = [
            e for e in events
            if e.type == SessionEventType.TOOL_RESULT and not e.data.get("is_error")
        ]
        assert len(tool_results) >= 1


class TestToolResultMessageFormat:
    """Integration: tool result messages pass through _messages_to_dicts correctly."""

    async def test_tool_result_preserved_in_recursion(self) -> None:
        """After tool execution, the tool_result message should be readable by the LLM."""
        from pydantic import BaseModel
        from unittest.mock import MagicMock

        class SimpleInput(BaseModel):
            x: int = 0

        mock_tool = MagicMock()
        mock_tool.name = "calc"
        mock_tool.description = "Calculate"
        mock_tool.input_schema.return_value = SimpleInput
        mock_tool.is_enabled = AsyncMock(return_value=True)
        mock_tool.is_read_only.return_value = True
        mock_tool.needs_permissions.return_value = False
        mock_tool.validate_input = AsyncMock()

        from pode_agent.core.tools.base import ToolOutput

        async def mock_call(input: Any, context: Any) -> Any:
            yield ToolOutput(type="result", result_for_assistant="42")

        mock_tool.call = mock_call

        # Capture the params sent to query_llm on the second call
        captured_params: list[Any] = []

        call_count = 0

        async def capturing_query_llm(params: Any, config: Any = None) -> Any:
            nonlocal call_count
            captured_params.append(params)
            if call_count == 0:
                call_count += 1
                for resp in _tool_use_response("tu_001", "calc", {"x": 1}):
                    yield resp
            else:
                for resp in _text_response("The answer is 42"):
                    yield resp

        session = _make_session(tools=[mock_tool])
        options = _make_options()

        with patch("pode_agent.app.query.query_llm", side_effect=capturing_query_llm):
            events = []
            async for event in query_core(
                messages=[],
                system_prompt="",
                tools=[mock_tool],
                session=session,
                options=options,
            ):
                events.append(event)

        # Second call should include tool_result messages
        assert len(captured_params) == 2
        second_messages = captured_params[1].messages
        # Should have: user (tool_result), assistant (from round 1)
        # The tool_result message should have list content, not str()
        tool_result_msgs = [
            m for m in second_messages
            if isinstance(m.get("content"), list)
            and any(
                isinstance(b, dict) and b.get("type") == "tool_result"
                for b in m["content"]
            )
        ]
        assert len(tool_result_msgs) >= 1, (
            f"Expected tool_result message in second call, got: {second_messages}"
        )
