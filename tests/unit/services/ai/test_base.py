"""Tests for services/ai/base.py — foundation types."""

from __future__ import annotations

import pytest

from pode_agent.core.config.schema import ProviderType
from pode_agent.services.ai.base import (
    AIResponse,
    ModelCapabilities,
    TokenUsage,
    ToolDefinition,
    ToolUseBlock,
    UnifiedRequestParams,
)


# ---------------------------------------------------------------------------
# TokenUsage
# ---------------------------------------------------------------------------


class TestTokenUsage:
    def test_defaults(self) -> None:
        usage = TokenUsage()
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0
        assert usage.cache_read_tokens == 0
        assert usage.cache_write_tokens == 0

    def test_with_values(self) -> None:
        usage = TokenUsage(input_tokens=100, output_tokens=50, cache_read_tokens=30)
        assert usage.input_tokens == 100
        assert usage.output_tokens == 50
        assert usage.cache_read_tokens == 30


# ---------------------------------------------------------------------------
# ToolDefinition
# ---------------------------------------------------------------------------


class TestToolDefinition:
    def test_construction(self) -> None:
        td = ToolDefinition(
            name="bash",
            description="Execute shell commands",
            input_schema={"type": "object", "properties": {"command": {"type": "string"}}},
        )
        assert td.name == "bash"
        assert td.description == "Execute shell commands"
        assert "command" in td.input_schema["properties"]


# ---------------------------------------------------------------------------
# ToolUseBlock
# ---------------------------------------------------------------------------


class TestToolUseBlock:
    def test_construction(self) -> None:
        block = ToolUseBlock(id="tu_001", name="bash", input={"command": "ls"})
        assert block.id == "tu_001"
        assert block.name == "bash"
        assert block.input["command"] == "ls"


# ---------------------------------------------------------------------------
# AIResponse
# ---------------------------------------------------------------------------


class TestAIResponse:
    def test_text_delta(self) -> None:
        resp = AIResponse(type="text_delta", text="Hello")
        assert resp.type == "text_delta"
        assert resp.text == "Hello"
        assert resp.tool_use_id is None

    def test_tool_use_end(self) -> None:
        resp = AIResponse(
            type="tool_use_end",
            tool_use_id="tu_001",
            tool_name="bash",
            tool_input={"command": "ls"},
        )
        assert resp.type == "tool_use_end"
        assert resp.tool_name == "bash"

    def test_message_done(self) -> None:
        resp = AIResponse(
            type="message_done",
            usage=TokenUsage(input_tokens=100, output_tokens=50),
            stop_reason="end_turn",
        )
        assert resp.type == "message_done"
        assert resp.usage is not None
        assert resp.usage.input_tokens == 100

    def test_error(self) -> None:
        resp = AIResponse(
            type="error",
            error_message="Rate limit exceeded",
            is_retriable=True,
        )
        assert resp.type == "error"
        assert resp.is_retriable is True

    def test_defaults(self) -> None:
        resp = AIResponse(type="text_delta")
        assert resp.text is None
        assert resp.cost_usd is None
        assert resp.is_retriable is False


# ---------------------------------------------------------------------------
# UnifiedRequestParams
# ---------------------------------------------------------------------------


class TestUnifiedRequestParams:
    def test_construction(self) -> None:
        params = UnifiedRequestParams(
            messages=[{"role": "user", "content": "hello"}],
            system_prompt="You are helpful.",
            model="claude-sonnet-4-5-20251101",
        )
        assert params.model == "claude-sonnet-4-5-20251101"
        assert len(params.messages) == 1
        assert params.tools is None
        assert params.temperature is None
        assert params.stream is True
        assert params.max_tokens == 8192

    def test_with_tools(self) -> None:
        td = ToolDefinition(name="bash", description="run commands", input_schema={})
        params = UnifiedRequestParams(
            messages=[],
            system_prompt="",
            model="gpt-4o",
            tools=[td],
        )
        assert params.tools is not None
        assert len(params.tools) == 1


# ---------------------------------------------------------------------------
# ModelCapabilities
# ---------------------------------------------------------------------------


class TestModelCapabilities:
    def test_defaults(self) -> None:
        caps = ModelCapabilities(provider=ProviderType.ANTHROPIC)
        assert caps.max_tokens == 8192
        assert caps.context_length == 200_000
        assert caps.supports_thinking is False
        assert caps.supports_tool_use is True

    def test_custom_values(self) -> None:
        caps = ModelCapabilities(
            max_tokens=16384,
            supports_thinking=True,
            supports_vision=True,
            provider=ProviderType.OPENAI,
        )
        assert caps.max_tokens == 16384
        assert caps.supports_thinking is True
        assert caps.provider == ProviderType.OPENAI
