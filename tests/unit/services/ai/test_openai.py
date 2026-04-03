"""Tests for services/ai/openai.py — OpenAI provider adapter.

All tests mock the OpenAI SDK — no real API calls.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pode_agent.services.ai.base import (
    ToolDefinition,
    UnifiedRequestParams,
)
from pode_agent.services.ai.openai import (
    OpenAIProvider,
    _map_thinking_to_effort,
    _to_openai_messages,
    _to_openai_tools,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_params(**overrides: Any) -> UnifiedRequestParams:
    defaults: dict[str, Any] = {
        "messages": [{"role": "user", "content": "hello"}],
        "system_prompt": "You are helpful.",
        "model": "gpt-4o",
    }
    defaults.update(overrides)
    return UnifiedRequestParams(**defaults)


def _mock_text_chunk(text: str) -> MagicMock:
    """Create a mock ChatCompletionChunk with text content."""
    chunk = MagicMock()
    chunk.choices = [MagicMock()]
    chunk.choices[0].delta = MagicMock(content=text, tool_calls=None)
    chunk.choices[0].finish_reason = None
    chunk.usage = None
    return chunk


def _mock_tool_call_start_chunk(tool_id: str, func_name: str) -> MagicMock:
    """Create a chunk with a new tool call (has id)."""
    chunk = MagicMock()
    chunk.choices = [MagicMock()]
    tc = MagicMock()
    tc.id = tool_id
    func = MagicMock()
    func.name = func_name
    func.arguments = ""
    tc.function = func
    chunk.choices[0].delta = MagicMock(content=None, tool_calls=[tc])
    chunk.choices[0].finish_reason = None
    chunk.usage = None
    return chunk


def _mock_tool_call_delta_chunk(arguments: str) -> MagicMock:
    """Create a chunk with tool call arguments delta (no id)."""
    chunk = MagicMock()
    chunk.choices = [MagicMock()]
    tc = MagicMock()
    tc.id = None
    tc.function = MagicMock(arguments=arguments)
    chunk.choices[0].delta = MagicMock(content=None, tool_calls=[tc])
    chunk.choices[0].finish_reason = None
    chunk.usage = None
    return chunk


def _mock_done_chunk(finish_reason: str = "stop") -> MagicMock:
    """Create a chunk with finish_reason set."""
    chunk = MagicMock()
    chunk.choices = [MagicMock()]
    chunk.choices[0].delta = MagicMock(content=None, tool_calls=None)
    chunk.choices[0].finish_reason = finish_reason
    chunk.usage = MagicMock(prompt_tokens=100, completion_tokens=50)
    return chunk


class _FakeStream:
    """Async iterable that yields mock chunks."""

    def __init__(self, chunks: list[MagicMock]) -> None:
        self._chunks = chunks

    def __aiter__(self) -> AsyncGenerator[MagicMock, None]:
        return self._async_iter()

    async def _async_iter(self) -> AsyncGenerator[MagicMock, None]:
        for chunk in self._chunks:
            yield chunk


# ---------------------------------------------------------------------------
# _to_openai_tools
# ---------------------------------------------------------------------------


class TestToOpenAITools:
    def test_none_returns_empty_list(self) -> None:
        result = _to_openai_tools(None)
        assert result == []

    def test_empty_list_returns_empty_list(self) -> None:
        result = _to_openai_tools([])
        assert result == []

    def test_converts_tools(self) -> None:
        tools = [
            ToolDefinition(
                name="bash",
                description="Run commands",
                input_schema={"type": "object", "properties": {"command": {"type": "string"}}},
            )
        ]
        result = _to_openai_tools(tools)
        assert len(result) == 1
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "bash"
        assert result[0]["function"]["parameters"]["properties"]["command"]["type"] == "string"


# ---------------------------------------------------------------------------
# _to_openai_messages
# ---------------------------------------------------------------------------


class TestToOpenAIMessages:
    def test_string_content(self) -> None:
        result = _to_openai_messages([{"role": "user", "content": "hello"}])
        assert result == [{"role": "user", "content": "hello"}]

    def test_list_content(self) -> None:
        content = [{"type": "text", "text": "hi"}]
        result = _to_openai_messages([{"role": "assistant", "content": content}])
        assert result == [{"role": "assistant", "content": content}]

    def test_dict_content(self) -> None:
        content = {"type": "text", "text": "hi"}
        result = _to_openai_messages([{"role": "user", "content": content}])
        assert result == [{"role": "user", "content": [content]}]

    def test_assistant_tool_use_converts_to_tool_calls(self) -> None:
        """Anthropic-style tool_use blocks → OpenAI tool_calls."""
        messages = [{
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Let me run that."},
                {"type": "tool_use", "id": "tu_001", "name": "bash", "input": {"command": "ls"}},
            ],
        }]
        result = _to_openai_messages(messages)
        assert len(result) == 1
        msg = result[0]
        assert msg["role"] == "assistant"
        assert msg["content"] == "Let me run that."
        assert len(msg["tool_calls"]) == 1
        tc = msg["tool_calls"][0]
        assert tc["id"] == "tu_001"
        assert tc["type"] == "function"
        assert tc["function"]["name"] == "bash"
        assert tc["function"]["arguments"] == '{"command": "ls"}'

    def test_assistant_tool_use_only_no_text(self) -> None:
        """Assistant with only tool_use blocks, no text."""
        messages = [{
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "tu_002", "name": "file_read", "input": {"path": "a.py"}},
            ],
        }]
        result = _to_openai_messages(messages)
        assert len(result) == 1
        assert result[0]["content"] is None
        assert len(result[0]["tool_calls"]) == 1

    def test_user_tool_result_converts_to_tool_role(self) -> None:
        """Anthropic-style tool_result blocks → OpenAI role='tool' messages."""
        messages = [{
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "tu_001", "content": "file1.py\nfile2.py"},
            ],
        }]
        result = _to_openai_messages(messages)
        assert len(result) == 1
        assert result[0]["role"] == "tool"
        assert result[0]["tool_call_id"] == "tu_001"
        assert result[0]["content"] == "file1.py\nfile2.py"

    def test_user_tool_result_multiple_blocks(self) -> None:
        """Multiple tool_result blocks → separate tool messages."""
        messages = [{
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "tu_001", "content": "result_a"},
                {"type": "tool_result", "tool_use_id": "tu_002", "content": "result_b"},
            ],
        }]
        result = _to_openai_messages(messages)
        assert len(result) == 2
        assert result[0]["role"] == "tool"
        assert result[0]["tool_call_id"] == "tu_001"
        assert result[1]["role"] == "tool"
        assert result[1]["tool_call_id"] == "tu_002"

    def test_full_tool_roundtrip(self) -> None:
        """Complete conversation with tool use → tool result roundtrip."""
        messages = [
            {"role": "user", "content": "List files"},
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "I'll list the files."},
                    {"type": "tool_use", "id": "tu_001", "name": "bash", "input": {"command": "ls"}},
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "tu_001", "content": "file1.py"},
                ],
            },
        ]
        result = _to_openai_messages(messages)

        assert result[0] == {"role": "user", "content": "List files"}

        assert result[1]["role"] == "assistant"
        assert result[1]["content"] == "I'll list the files."
        assert len(result[1]["tool_calls"]) == 1

        assert result[2]["role"] == "tool"
        assert result[2]["tool_call_id"] == "tu_001"
        assert result[2]["content"] == "file1.py"


# ---------------------------------------------------------------------------
# OpenAIProvider init
# ---------------------------------------------------------------------------


class TestOpenAIProviderInit:
    def test_creates_client(self) -> None:
        provider = OpenAIProvider(api_key="test-key")
        assert provider._api_key == "test-key"

    @patch.dict(os.environ, {"OPENAI_API_KEY": "env-key"})
    def test_api_key_from_env(self) -> None:
        provider = OpenAIProvider()
        assert provider._api_key == "env-key"

    def test_custom_base_url(self) -> None:
        provider = OpenAIProvider(api_key="test", base_url="http://localhost:11434/v1")
        assert provider._base_url == "http://localhost:11434/v1"


# ---------------------------------------------------------------------------
# Streaming queries
# ---------------------------------------------------------------------------


class TestStreamTextResponse:
    async def test_text_streaming(self) -> None:
        provider = OpenAIProvider(api_key="test")

        mock_chunks = [
            _mock_text_chunk("Hello"),
            _mock_text_chunk(" world"),
            _mock_done_chunk(),
        ]

        provider._client = MagicMock()
        provider._client.chat.completions.create = AsyncMock(
            return_value=_FakeStream(mock_chunks)
        )

        responses = [r async for r in provider.query(_make_params())]

        text_deltas = [r for r in responses if r.type == "text_delta"]
        assert len(text_deltas) == 2
        assert text_deltas[0].text == "Hello"
        assert text_deltas[1].text == " world"

        done_events = [r for r in responses if r.type == "message_done"]
        assert len(done_events) == 1
        assert done_events[0].stop_reason == "stop"
        assert done_events[0].usage is not None
        assert done_events[0].usage.input_tokens == 100
        assert done_events[0].usage.output_tokens == 50


class TestStreamToolUse:
    async def test_tool_use_start_and_delta(self) -> None:
        provider = OpenAIProvider(api_key="test")

        mock_chunks = [
            _mock_tool_call_start_chunk("call_001", "bash"),
            _mock_tool_call_delta_chunk('{"command": "ls"}'),
            _mock_done_chunk(finish_reason="tool_calls"),
        ]

        provider._client = MagicMock()
        provider._client.chat.completions.create = AsyncMock(
            return_value=_FakeStream(mock_chunks)
        )

        responses = [r async for r in provider.query(_make_params())]

        start_events = [r for r in responses if r.type == "tool_use_start"]
        assert len(start_events) == 1
        assert start_events[0].tool_name == "bash"
        assert start_events[0].tool_use_id == "call_001"

        delta_events = [r for r in responses if r.type == "tool_use_delta"]
        assert len(delta_events) == 1
        assert delta_events[0].text == '{"command": "ls"}'


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    async def test_auth_error(self) -> None:
        import openai as _openai

        provider = OpenAIProvider(api_key="test")
        provider._client = MagicMock()
        provider._client.chat.completions.create = AsyncMock(
            side_effect=_openai.AuthenticationError(
                message="Invalid API key",
                response=MagicMock(status_code=401),
                body=None,
            )
        )

        responses = [r async for r in provider.query(_make_params())]
        assert len(responses) == 1
        assert responses[0].type == "error"
        assert responses[0].is_retriable is False
        assert "Authentication" in responses[0].error_message

    async def test_connection_error(self) -> None:
        import openai as _openai

        provider = OpenAIProvider(api_key="test")
        provider._client = MagicMock()
        provider._client.chat.completions.create = AsyncMock(
            side_effect=_openai.APIConnectionError(request=MagicMock())
        )

        responses = [r async for r in provider.query(_make_params())]
        assert len(responses) == 1
        assert responses[0].type == "error"
        assert responses[0].is_retriable is True

    async def test_rate_limit_exhausted(self) -> None:
        import openai as _openai

        provider = OpenAIProvider(api_key="test")
        provider._client = MagicMock()
        provider._client.chat.completions.create = AsyncMock(
            side_effect=_openai.RateLimitError(
                message="Rate limited",
                response=MagicMock(status_code=429),
                body=None,
            )
        )

        with patch("asyncio.sleep", new_callable=AsyncMock):
            responses = [r async for r in provider.query(_make_params())]

        assert len(responses) == 1
        assert responses[0].type == "error"
        assert responses[0].is_retriable is True
        assert "Rate limit" in responses[0].error_message


# ---------------------------------------------------------------------------
# Thinking tokens / reasoning_effort
# ---------------------------------------------------------------------------


class TestThinkingTokens:
    async def test_thinking_params_mapped_to_reasoning_effort(self) -> None:
        provider = OpenAIProvider(api_key="test")

        mock_chunks = [
            _mock_text_chunk("thinking..."),
            _mock_done_chunk(),
        ]

        provider._client = MagicMock()
        provider._client.chat.completions.create = AsyncMock(
            return_value=_FakeStream(mock_chunks)
        )

        params = _make_params(thinking_tokens=10000)
        _ = [r async for r in provider.query(params)]

        call_kwargs = provider._client.chat.completions.create.call_args
        assert "reasoning_effort" in call_kwargs.kwargs
        assert call_kwargs.kwargs["reasoning_effort"] == "high"


class TestMapThinkingToEffort:
    def test_high(self) -> None:
        assert _map_thinking_to_effort(10000) == "high"

    def test_medium(self) -> None:
        assert _map_thinking_to_effort(5000) == "medium"

    def test_low(self) -> None:
        assert _map_thinking_to_effort(1000) == "low"
