"""Tests for services/ai/factory.py — Model adapter factory."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from pode_agent.core.config.schema import GlobalConfig, ModelProfile, ProviderType
from pode_agent.services.ai.base import AIProvider, ModelCapabilities
from pode_agent.services.ai.factory import (
    ModelAdapterFactory,
    _MODEL_CAPABILITIES,
    _PREFIX_ROUTING,
)


# ---------------------------------------------------------------------------
# Provider type routing
# ---------------------------------------------------------------------------


class TestResolveProviderType:
    def test_claude_prefix(self) -> None:
        assert ModelAdapterFactory._resolve_provider_type("claude-sonnet-4-5-20251101") == ProviderType.ANTHROPIC

    def test_gpt_prefix(self) -> None:
        assert ModelAdapterFactory._resolve_provider_type("gpt-4o") == ProviderType.OPENAI

    def test_o1_prefix(self) -> None:
        assert ModelAdapterFactory._resolve_provider_type("o1-mini") == ProviderType.OPENAI

    def test_o3_prefix(self) -> None:
        assert ModelAdapterFactory._resolve_provider_type("o3-mini") == ProviderType.OPENAI

    def test_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown model prefix"):
            ModelAdapterFactory._resolve_provider_type("unknown-model")


class TestGetProvider:
    @patch("pode_agent.services.ai.factory._load_provider_class")
    def test_returns_anthropic_provider(self, mock_load: MagicMock) -> None:
        mock_cls = MagicMock(spec=AIProvider)
        mock_load.return_value = mock_cls
        provider = ModelAdapterFactory.get_provider("claude-sonnet-4-5-20251101")
        mock_cls.assert_called_once()

    @patch("pode_agent.services.ai.factory._load_provider_class")
    def test_returns_openai_provider(self, mock_load: MagicMock) -> None:
        mock_cls = MagicMock(spec=AIProvider)
        mock_load.return_value = mock_cls
        provider = ModelAdapterFactory.get_provider("gpt-4o")
        mock_cls.assert_called_once()

    def test_unknown_model_raises(self) -> None:
        with pytest.raises(ValueError):
            ModelAdapterFactory.get_provider("xyz-123")


# ---------------------------------------------------------------------------
# Model capabilities
# ---------------------------------------------------------------------------


class TestGetCapabilities:
    def test_exact_match(self) -> None:
        caps = ModelAdapterFactory.get_capabilities("claude-sonnet-4-5")
        assert caps.provider == ProviderType.ANTHROPIC
        assert caps.supports_thinking is True
        assert caps.context_length == 200_000

    def test_prefix_match(self) -> None:
        caps = ModelAdapterFactory.get_capabilities("claude-sonnet-4-5-20251101")
        assert caps.provider == ProviderType.ANTHROPIC

    def test_unknown_returns_defaults(self) -> None:
        caps = ModelAdapterFactory.get_capabilities("unknown-model")
        assert caps.provider == ProviderType.ANTHROPIC  # default
        assert caps.max_tokens == 8192

    def test_openai_model(self) -> None:
        caps = ModelAdapterFactory.get_capabilities("gpt-4o")
        assert caps.provider == ProviderType.OPENAI
        assert caps.supports_vision is True


# ---------------------------------------------------------------------------
# Custom provider registration
# ---------------------------------------------------------------------------


class TestRegisterProvider:
    def test_register_custom_prefix(self) -> None:
        original_len = len(_PREFIX_ROUTING)
        ModelAdapterFactory.register_provider("my-model-", ProviderType.OPENAI)
        assert len(_PREFIX_ROUTING) == original_len + 1
        # Verify it routes correctly
        assert ModelAdapterFactory._resolve_provider_type("my-model-v1") == ProviderType.OPENAI
        # Cleanup
        _PREFIX_ROUTING.pop(0)


# ---------------------------------------------------------------------------
# query_llm convenience wrapper
# ---------------------------------------------------------------------------


class TestQueryLlm:
    async def test_delegates_to_provider(self) -> None:
        from pode_agent.services.ai.base import AIResponse, UnifiedRequestParams
        from pode_agent.services.ai.factory import query_llm

        mock_provider = MagicMock(spec=AIProvider)
        mock_response = AIResponse(type="text_delta", text="hi")

        async def mock_query(params: Any) -> Any:
            yield mock_response

        mock_provider.query = mock_query

        with patch.object(
            ModelAdapterFactory, "get_provider", return_value=mock_provider
        ):
            params = UnifiedRequestParams(
                messages=[{"role": "user", "content": "hi"}],
                system_prompt="test",
                model="gpt-4o",
            )
            results = [r async for r in query_llm(params)]
            assert len(results) == 1
            assert results[0].text == "hi"
