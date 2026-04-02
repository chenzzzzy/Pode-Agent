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

    async def test_passes_config_to_get_provider(self) -> None:
        from pode_agent.services.ai.base import AIResponse, UnifiedRequestParams
        from pode_agent.services.ai.factory import query_llm

        mock_provider = MagicMock(spec=AIProvider)

        async def mock_query(params: Any) -> Any:
            yield AIResponse(type="text_delta", text="ok")

        mock_provider.query = mock_query
        mock_config = MagicMock(spec=GlobalConfig)

        with patch.object(
            ModelAdapterFactory, "get_provider", return_value=mock_provider
        ) as mock_get:
            params = UnifiedRequestParams(
                messages=[{"role": "user", "content": "hi"}],
                system_prompt="test",
                model="gpt-4o",
            )
            _ = [r async for r in query_llm(params, config=mock_config)]
            mock_get.assert_called_once_with("gpt-4o", mock_config)


# ---------------------------------------------------------------------------
# get_provider with config (profile matching)
# ---------------------------------------------------------------------------


class TestGetProviderWithConfig:
    @patch("pode_agent.services.ai.factory._load_provider_class")
    def test_matches_profile_by_model_name(self, mock_load: MagicMock) -> None:
        from pode_agent.core.config.schema import ModelProfile

        mock_cls = MagicMock(spec=AIProvider)
        mock_load.return_value = mock_cls

        profile = ModelProfile(
            name="my-claude",
            provider=ProviderType.ANTHROPIC,
            model_name="claude-sonnet-4-5-custom",
            api_key="sk-test-123",
            base_url="https://custom.api.com",
        )
        config = GlobalConfig(model_profiles=[profile])

        provider = ModelAdapterFactory.get_provider("claude-sonnet-4-5-custom", config=config)
        mock_load.assert_called_once()
        mock_cls.assert_called_once_with(api_key="sk-test-123", base_url="https://custom.api.com")

    @patch("pode_agent.services.ai.factory._load_provider_class")
    def test_matches_profile_by_name(self, mock_load: MagicMock) -> None:
        from pode_agent.core.config.schema import ModelProfile

        mock_cls = MagicMock(spec=AIProvider)
        mock_load.return_value = mock_cls

        profile = ModelProfile(
            name="claude-custom-alias",  # matches "claude-" prefix for routing
            provider=ProviderType.ANTHROPIC,
            model_name="claude-sonnet-custom",
            api_key="key-456",
        )
        config = GlobalConfig(model_profiles=[profile])

        # Match by profile.name field — passes _resolve_provider_type via "claude-" prefix
        provider = ModelAdapterFactory.get_provider("claude-custom-alias", config=config)
        mock_load.assert_called_once()

    @patch("pode_agent.services.ai.factory._load_provider_class")
    def test_no_profile_match_falls_through(self, mock_load: MagicMock) -> None:
        mock_cls = MagicMock(spec=AIProvider)
        mock_load.return_value = mock_cls

        config = GlobalConfig(model_profiles=[])
        provider = ModelAdapterFactory.get_provider("claude-sonnet-4-5", config=config)
        # Falls through to default path
        mock_load.assert_called_once()

    def test_unregistered_provider_type_raises(self) -> None:
        from pode_agent.core.config.schema import ModelProfile

        # Register a prefix for a provider type that has no class registered
        ModelAdapterFactory.register_provider("test-unregistered-", ProviderType.BEDROCK)
        try:
            with pytest.raises(ValueError, match="No provider registered for type"):
                ModelAdapterFactory.get_provider("test-unregistered-model")
        finally:
            # Cleanup
            _PREFIX_ROUTING.pop(0)


# ---------------------------------------------------------------------------
# _create_from_profile
# ---------------------------------------------------------------------------


class TestCreateFromProfile:
    @patch("pode_agent.services.ai.factory._load_provider_class")
    def test_creates_provider_from_profile(self, mock_load: MagicMock) -> None:
        from pode_agent.core.config.schema import ModelProfile

        mock_cls = MagicMock(spec=AIProvider)
        mock_load.return_value = mock_cls

        profile = ModelProfile(
            name="test",
            provider=ProviderType.ANTHROPIC,
            model_name="claude-test",
            api_key="sk-key",
            base_url="https://api.example.com",
        )
        provider = ModelAdapterFactory._create_from_profile(profile)
        mock_cls.assert_called_once_with(api_key="sk-key", base_url="https://api.example.com")

    def test_unregistered_provider_type_raises(self) -> None:
        from pode_agent.core.config.schema import ModelProfile

        profile = ModelProfile(
            name="test",
            provider=ProviderType.GEMINI,  # Not in _PROVIDER_CLASSES
            model_name="gemini-pro",
        )
        with pytest.raises(ValueError, match="No provider for type"):
            ModelAdapterFactory._create_from_profile(profile)


# ---------------------------------------------------------------------------
# _load_provider_class
# ---------------------------------------------------------------------------


class TestLoadProviderClass:
    def test_loads_anthropic_provider(self) -> None:
        from pode_agent.services.ai.factory import _load_provider_class

        cls = _load_provider_class(
            "pode_agent.services.ai.anthropic", "AnthropicProvider"
        )
        from pode_agent.services.ai.anthropic import AnthropicProvider
        assert cls is AnthropicProvider

    def test_loads_openai_provider(self) -> None:
        from pode_agent.services.ai.factory import _load_provider_class

        cls = _load_provider_class(
            "pode_agent.services.ai.openai", "OpenAIProvider"
        )
        from pode_agent.services.ai.openai import OpenAIProvider
        assert cls is OpenAIProvider

    def test_invalid_class_name_raises(self) -> None:
        from pode_agent.services.ai.factory import _load_provider_class

        with pytest.raises(AttributeError):
            _load_provider_class("pode_agent.services.ai.anthropic", "NonexistentClass")

    def test_non_provider_class_raises(self) -> None:
        from pode_agent.services.ai.factory import _load_provider_class

        with pytest.raises(ValueError, match="is not an AIProvider subclass"):
            _load_provider_class("pode_agent.services.ai.base", "TokenUsage")


# ---------------------------------------------------------------------------
# _build_provider_kwargs
# ---------------------------------------------------------------------------


class TestBuildProviderKwargs:
    def test_no_config_returns_empty(self) -> None:
        from pode_agent.services.ai.factory import _build_provider_kwargs

        kwargs = _build_provider_kwargs(ProviderType.ANTHROPIC, None)
        assert kwargs == {}

    def test_config_without_proxy_returns_empty(self) -> None:
        from pode_agent.services.ai.factory import _build_provider_kwargs

        config = GlobalConfig()
        kwargs = _build_provider_kwargs(ProviderType.ANTHROPIC, config)
        assert kwargs == {}

    def test_proxy_injected(self) -> None:
        from pode_agent.services.ai.factory import _build_provider_kwargs

        config = GlobalConfig(proxy="http://proxy:8080")
        kwargs = _build_provider_kwargs(ProviderType.ANTHROPIC, config)
        assert kwargs == {"proxy": "http://proxy:8080"}

    def test_openai_compat_with_profile_base_url(self) -> None:
        from pode_agent.core.config.schema import ModelProfile
        from pode_agent.services.ai.factory import _build_provider_kwargs

        profile = ModelProfile(
            name="custom-llm",
            provider=ProviderType.OPENAI_COMPAT,
            model_name="custom-model",
            base_url="https://llm.example.com/v1",
            api_key="sk-custom",
        )
        config = GlobalConfig(model_profiles=[profile])
        kwargs = _build_provider_kwargs(ProviderType.OPENAI_COMPAT, config)
        assert kwargs == {"base_url": "https://llm.example.com/v1", "api_key": "sk-custom"}

    def test_openai_compat_no_base_url_skipped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from pode_agent.core.config.schema import ModelProfile
        from pode_agent.services.ai.factory import _build_provider_kwargs

        # Clear env vars that may be set by integration test conftest
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        monkeypatch.delenv("DASHSCOPE_BASE_URL", raising=False)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)

        profile = ModelProfile(
            name="no-url",
            provider=ProviderType.OPENAI_COMPAT,
            model_name="test",
        )
        config = GlobalConfig(model_profiles=[profile])
        kwargs = _build_provider_kwargs(ProviderType.OPENAI_COMPAT, config)
        assert "base_url" not in kwargs
