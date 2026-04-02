"""Tests for services/ai/anthropic.py — Anthropic provider adapter.

All tests mock the Anthropic SDK — no real API calls.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pode_agent.services.ai.anthropic import (
    AnthropicProvider,
    _to_anthropic_messages,
    _to_anthropic_tools,
)
from pode_agent.services.ai.base import (
    ToolDefinition,
    UnifiedRequestParams,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_params(**overrides: Any) -> UnifiedRequestParams:
    defaults: dict[str, Any] = {
        "messages": [{"role": "user", "content": "hello"}],
        "system_prompt": "You are helpful.",
        "model": "claude-sonnet-4-5-20251101",
    }
    defaults.update(overrides)
    return UnifiedRequestParams(**defaults)


def _mock_text_event(text: str) -> MagicMock:
    """Create a mock content_block_delta with text."""
    event = MagicMock()
    event.type = "content_block_delta"
    event.delta = MagicMock(type="text_delta", text=text)
    return event


def _mock_tool_use_start(tool_id: str, name: str) -> MagicMock:
    event = MagicMock()
    event.type = "content_block_start"
    cb = MagicMock()
    cb.type = "tool_use"
    cb.id = tool_id
    cb.name = name
    event.content_block = cb
    return event


def _mock_tool_use_delta(partial_json: str) -> MagicMock:
    event = MagicMock()
    event.type = "content_block_delta"
    event.delta = MagicMock(type="input_json_delta", partial_json=partial_json)
    event.index = "tu_001"
    return event


def _mock_message_done(stop_reason: str = "end_turn") -> MagicMock:
    event = MagicMock()
    event.type = "message_delta"
    event.usage = MagicMock(output_tokens=50)
    event.delta = MagicMock(stop_reason=stop_reason)
    return event


@asynccontextmanager
async def _mock_stream_ctx(events: list[MagicMock]) -> AsyncGenerator[MagicMock, None]:
    """Context manager that yields an async-iterable of mock events."""

    class _FakeStream:
        def __init__(self, evts: list[MagicMock]) -> None:
            self._events = evts

        def __aiter__(self) -> AsyncGenerator[MagicMock, None]:
            return self._async_iter()

        async def _async_iter(self) -> AsyncGenerator[MagicMock, None]:
            for event in self._events:
                yield event

    yield _FakeStream(events)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# _to_anthropic_tools
# ---------------------------------------------------------------------------


class TestToAnthropicTools:
    def test_none_returns_not_given(self) -> None:
        from anthropic import NOT_GIVEN
        result = _to_anthropic_tools(None)
        assert result is NOT_GIVEN

    def test_empty_list_returns_not_given(self) -> None:
        from anthropic import NOT_GIVEN
        result = _to_anthropic_tools([])
        assert result is NOT_GIVEN

    def test_converts_tools(self) -> None:
        tools = [
            ToolDefinition(
                name="bash",
                description="Run commands",
                input_schema={"type": "object", "properties": {"command": {"type": "string"}}},
            )
        ]
        result = _to_anthropic_tools(tools)
        assert len(result) == 1
        assert result[0]["name"] == "bash"
        assert result[0]["input_schema"]["properties"]["command"]["type"] == "string"


# ---------------------------------------------------------------------------
# _to_anthropic_messages
# ---------------------------------------------------------------------------


class TestToAnthropicMessages:
    def test_string_content(self) -> None:
        result = _to_anthropic_messages([{"role": "user", "content": "hello"}])
        assert result == [{"role": "user", "content": "hello"}]

    def test_list_content(self) -> None:
        content = [{"type": "text", "text": "hi"}]
        result = _to_anthropic_messages([{"role": "assistant", "content": content}])
        assert result == [{"role": "assistant", "content": content}]

    def test_dict_content(self) -> None:
        content = {"type": "text", "text": "hi"}
        result = _to_anthropic_messages([{"role": "user", "content": content}])
        assert result == [{"role": "user", "content": [content]}]


# ---------------------------------------------------------------------------
# AnthropicProvider init
# ---------------------------------------------------------------------------


class TestAnthropicProviderInit:
    def test_creates_client(self) -> None:
        provider = AnthropicProvider(api_key="test-key")
        assert provider._api_key == "test-key"

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "env-key"})
    def test_api_key_from_env(self) -> None:
        provider = AnthropicProvider()
        assert provider._api_key == "env-key"


# ---------------------------------------------------------------------------
# Streaming queries
# ---------------------------------------------------------------------------


class TestStreamTextResponse:
    async def test_text_streaming(self) -> None:
        provider = AnthropicProvider(api_key="test")

        mock_events = [
            _mock_text_event("Hello"),
            _mock_text_event(" world"),
            _mock_message_done(),
        ]

        provider._client = MagicMock()
        provider._client.messages.stream = MagicMock(return_value=_mock_stream_ctx(mock_events))

        responses = [r async for r in provider.query(_make_params())]

        text_deltas = [r for r in responses if r.type == "text_delta"]
        assert len(text_deltas) == 2
        assert text_deltas[0].text == "Hello"
        assert text_deltas[1].text == " world"

        done_events = [r for r in responses if r.type == "message_done"]
        assert len(done_events) == 1
        assert done_events[0].stop_reason == "end_turn"


class TestStreamToolUse:
    async def test_tool_use_start_and_delta(self) -> None:
        provider = AnthropicProvider(api_key="test")

        mock_events = [
            _mock_tool_use_start("tu_001", "bash"),
            _mock_tool_use_delta('{"command": "ls"}'),
            _mock_message_done(stop_reason="tool_use"),
        ]

        provider._client = MagicMock()
        provider._client.messages.stream = MagicMock(return_value=_mock_stream_ctx(mock_events))

        responses = [r async for r in provider.query(_make_params())]

        start_events = [r for r in responses if r.type == "tool_use_start"]
        assert len(start_events) == 1
        assert start_events[0].tool_name == "bash"
        assert start_events[0].tool_use_id == "tu_001"

        delta_events = [r for r in responses if r.type == "tool_use_delta"]
        assert len(delta_events) == 1


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    async def test_auth_error(self) -> None:
        import anthropic as _anthropic

        provider = AnthropicProvider(api_key="test")
        provider._client = MagicMock()
        provider._client.messages.stream.side_effect = _anthropic.AuthenticationError(
            message="Invalid API key",
            response=MagicMock(status_code=401),
            body=None,
        )

        responses = [r async for r in provider.query(_make_params())]
        assert len(responses) == 1
        assert responses[0].type == "error"
        assert responses[0].is_retriable is False
        assert "Authentication" in responses[0].error_message

    async def test_connection_error(self) -> None:
        import anthropic as _anthropic

        provider = AnthropicProvider(api_key="test")
        provider._client = MagicMock()
        provider._client.messages.stream.side_effect = _anthropic.APIConnectionError(
            request=MagicMock(),
        )

        responses = [r async for r in provider.query(_make_params())]
        assert len(responses) == 1
        assert responses[0].type == "error"
        assert responses[0].is_retriable is True

    async def test_rate_limit_exhausted(self) -> None:
        import anthropic as _anthropic

        provider = AnthropicProvider(api_key="test")
        provider._client = MagicMock()
        provider._client.messages.stream.side_effect = _anthropic.RateLimitError(
            message="Rate limited",
            response=MagicMock(status_code=429),
            body=None,
        )

        # Mock sleep to avoid real waits
        with patch("asyncio.sleep", new_callable=AsyncMock):
            responses = [r async for r in provider.query(_make_params())]

        assert len(responses) == 1
        assert responses[0].type == "error"
        assert responses[0].is_retriable is True
        assert "Rate limit" in responses[0].error_message


# ---------------------------------------------------------------------------
# Thinking tokens
# ---------------------------------------------------------------------------


class TestThinkingTokens:
    async def test_thinking_params_passed(self) -> None:
        provider = AnthropicProvider(api_key="test")

        mock_events = [
            _mock_text_event("thinking..."),
            _mock_message_done(),
        ]

        mock_stream = AsyncMock()
        mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
        mock_stream.__aexit__ = AsyncMock(return_value=None)
        mock_stream.__aiter__ = MagicMock(return_value=iter(mock_events))

        provider._client = MagicMock()
        provider._client.messages.stream.return_value = mock_stream

        params = _make_params(thinking_tokens=10000)
        _ = [r async for r in provider.query(params)]

        # Verify thinking kwarg was passed
        call_kwargs = provider._client.messages.stream.call_args
        assert "thinking" in call_kwargs.kwargs
        assert call_kwargs.kwargs["thinking"]["budget_tokens"] == 10000
