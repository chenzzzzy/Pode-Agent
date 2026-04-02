"""Integration tests — real API calls to third-party OpenAI-compatible providers.

These tests require real API keys and are SKIPPED by default.
Run with:  uv run pytest tests/integration/ -m requires_api_key -v

Environment variables (set in .env or export manually):
    DASHSCOPE_API_KEY   — Alibaba Cloud DashScope API key
    DASHSCOPE_BASE_URL  — API base URL (default: https://dashscope.aliyuncs.com/compatible-mode/v1)
    DASHSCOPE_MODEL     — Model name (default: qwen-plus)
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import pytest

from pode_agent.services.ai.base import AIResponse, UnifiedRequestParams
from pode_agent.services.ai.factory import ModelAdapterFactory
from pode_agent.services.ai.openai import OpenAIProvider

# Skip entire module if no API key is configured
pytestmark = pytest.mark.requires_api_key

DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
DASHSCOPE_BASE_URL = os.environ.get(
    "DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
)
DASHSCOPE_MODEL = os.environ.get("DASHSCOPE_MODEL", "qwen-plus")

skip_no_key = pytest.mark.skipif(
    not DASHSCOPE_API_KEY,
    reason="DASHSCOPE_API_KEY not set — skipping live API test",
)


def _make_params(
    prompt: str = "Say hello in one word.",
    model: str = DASHSCOPE_MODEL,
) -> UnifiedRequestParams:
    return UnifiedRequestParams(
        messages=[{"role": "user", "content": prompt}],
        system_prompt="You are a helpful assistant. Be concise.",
        model=model,
    )


# ---------------------------------------------------------------------------
# Direct OpenAIProvider with custom base_url
# ---------------------------------------------------------------------------


@skip_no_key
class TestDashScopeDirect:
    """Test OpenAIProvider directly against Alibaba Cloud DashScope."""

    @pytest.fixture
    def provider(self) -> OpenAIProvider:
        return OpenAIProvider(
            api_key=DASHSCOPE_API_KEY,
            base_url=DASHSCOPE_BASE_URL,
        )

    async def test_simple_text_response(self, provider: OpenAIProvider) -> None:
        """Basic text query should yield text_delta events and a message_done."""
        params = _make_params("Say hello in one word.")
        events: list[AIResponse] = []
        async for resp in provider.query(params):
            events.append(resp)

        types = [e.type for e in events]
        assert "text_delta" in types, f"Expected text_delta in {types}"
        assert "message_done" in types, f"Expected message_done in {types}"

        text = "".join(e.text for e in events if e.type == "text_delta" and e.text)
        assert len(text) > 0, "Expected non-empty text response"

    async def test_streaming_yields_incremental_deltas(
        self, provider: OpenAIProvider,
    ) -> None:
        """Streaming should produce multiple text_delta events (not one big chunk)."""
        params = _make_params("Count from 1 to 5, one number per line.")
        events: list[AIResponse] = []
        async for resp in provider.query(params):
            events.append(resp)

        deltas = [e for e in events if e.type == "text_delta"]
        assert len(deltas) >= 2, f"Expected multiple deltas, got {len(deltas)}"

    async def test_message_done_has_stop_reason(
        self, provider: OpenAIProvider,
    ) -> None:
        """message_done event should have stop_reason='stop'."""
        params = _make_params()
        events: list[AIResponse] = []
        async for resp in provider.query(params):
            events.append(resp)

        done_events = [e for e in events if e.type == "message_done"]
        assert len(done_events) >= 1
        assert done_events[0].stop_reason == "stop"

    async def test_error_on_invalid_model(self, provider: OpenAIProvider) -> None:
        """Invalid model name should yield an error response."""
        params = _make_params(model="nonexistent-model-xyz")
        events: list[AIResponse] = []
        async for resp in provider.query(params):
            events.append(resp)

        types = [e.type for e in events]
        assert "error" in types, f"Expected error in response, got {types}"

    async def test_chinese_prompt(self, provider: OpenAIProvider) -> None:
        """Chinese language prompt should work correctly."""
        params = _make_params("用一句话介绍Python编程语言。")
        events: list[AIResponse] = []
        async for resp in provider.query(params):
            events.append(resp)

        text = "".join(e.text for e in events if e.type == "text_delta" and e.text)
        assert len(text) > 0, "Expected non-empty Chinese text response"


# ---------------------------------------------------------------------------
# Via ModelAdapterFactory (end-to-end routing)
# ---------------------------------------------------------------------------


@skip_no_key
class TestDashScopeViaFactory:
    """Test third-party provider via ModelAdapterFactory routing."""

    async def test_factory_routes_qwen_to_openai_compat(self) -> None:
        """qwen-* model should be routed to OPENAI_COMPAT provider type."""
        from pode_agent.core.config.schema import ProviderType

        provider_type = ModelAdapterFactory._resolve_provider_type("qwen-plus")
        assert provider_type == ProviderType.OPENAI_COMPAT

    async def test_factory_creates_provider_with_env(self) -> None:
        """Factory should pick up DASHSCOPE_* env vars for qwen models."""
        provider = ModelAdapterFactory.get_provider("qwen-plus")
        assert isinstance(provider, OpenAIProvider)

    async def test_full_query_through_factory(self) -> None:
        """End-to-end: factory → provider → streaming response."""
        provider = ModelAdapterFactory.get_provider("qwen-plus")
        params = _make_params("Reply with exactly: pong")
        events: list[AIResponse] = []
        async for resp in provider.query(params):
            events.append(resp)

        text = "".join(e.text for e in events if e.type == "text_delta" and e.text)
        assert len(text) > 0, "Expected non-empty response from factory-routed provider"


# ---------------------------------------------------------------------------
# DeepSeek provider (if key available)
# ---------------------------------------------------------------------------


DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get(
    "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
)

skip_no_deepseek = pytest.mark.skipif(
    not DEEPSEEK_API_KEY,
    reason="DEEPSEEK_API_KEY not set",
)


@skip_no_deepseek
class TestDeepSeekDirect:
    """Test against DeepSeek API (if key available)."""

    async def test_simple_response(self) -> None:
        provider = OpenAIProvider(
            api_key=DEEPSEEK_API_KEY,
            base_url=DEEPSEEK_BASE_URL,
        )
        params = _make_params("Say hello in one word.", model="deepseek-chat")
        events: list[AIResponse] = []
        async for resp in provider.query(params):
            events.append(resp)

        text = "".join(e.text for e in events if e.type == "text_delta" and e.text)
        assert len(text) > 0


# ---------------------------------------------------------------------------
# End-to-end: query_llm → real DashScope API
# ---------------------------------------------------------------------------


@skip_no_key
class TestLiveQueryLLM:
    """End-to-end: query_llm convenience wrapper → DashScope streaming."""

    async def test_query_llm_text_stream(self) -> None:
        """query_llm should route qwen model to DashScope and stream text."""
        from pode_agent.services.ai.factory import query_llm as factory_query_llm

        params = _make_params("Reply with exactly: pong")
        events: list[AIResponse] = []
        async for resp in factory_query_llm(params):
            events.append(resp)

        types = [e.type for e in events]
        assert "text_delta" in types, f"Expected text_delta in {types}"
        assert "message_done" in types, f"Expected message_done in {types}"

        text = "".join(e.text for e in events if e.type == "text_delta" and e.text)
        assert len(text) > 0, "Expected non-empty text from query_llm"
