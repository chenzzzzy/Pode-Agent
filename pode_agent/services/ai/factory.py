"""Model adapter factory — routes model names to AI providers.

Routes model names (e.g. ``claude-sonnet-4-5-20251101``, ``gpt-4o``) to
the appropriate ``AIProvider`` implementation based on prefix matching.

Reference: docs/api-specs.md — AI Provider API
           docs/modules.md — services/ai/factory
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from typing import Any

from pode_agent.core.config.schema import GlobalConfig, ProviderType
from pode_agent.services.ai.base import (
    AIProvider,
    AIResponse,
    ModelCapabilities,
    UnifiedRequestParams,
)

# ---------------------------------------------------------------------------
# Built-in model capability table
# ---------------------------------------------------------------------------

_MODEL_CAPABILITIES: dict[str, dict[str, Any]] = {
    # Anthropic Claude
    "claude-sonnet-4-5": {
        "max_tokens": 8192,
        "context_length": 200_000,
        "supports_thinking": True,
        "supports_tool_use": True,
        "supports_streaming": True,
        "supports_vision": True,
        "provider": ProviderType.ANTHROPIC,
    },
    "claude-haiku-4-5": {
        "max_tokens": 8192,
        "context_length": 200_000,
        "supports_thinking": False,
        "supports_tool_use": True,
        "supports_streaming": True,
        "supports_vision": True,
        "provider": ProviderType.ANTHROPIC,
    },
    "claude-opus-4": {
        "max_tokens": 32768,
        "context_length": 200_000,
        "supports_thinking": True,
        "supports_tool_use": True,
        "supports_streaming": True,
        "supports_vision": True,
        "provider": ProviderType.ANTHROPIC,
    },
    # OpenAI
    "gpt-4o": {
        "max_tokens": 16384,
        "context_length": 128_000,
        "supports_thinking": False,
        "supports_tool_use": True,
        "supports_streaming": True,
        "supports_vision": True,
        "provider": ProviderType.OPENAI,
    },
    "gpt-4o-mini": {
        "max_tokens": 16384,
        "context_length": 128_000,
        "supports_thinking": False,
        "supports_tool_use": True,
        "supports_streaming": True,
        "supports_vision": True,
        "provider": ProviderType.OPENAI,
    },
    "o1": {
        "max_tokens": 32768,
        "context_length": 200_000,
        "supports_thinking": True,
        "supports_tool_use": True,
        "supports_streaming": True,
        "supports_vision": False,
        "provider": ProviderType.OPENAI,
    },
    "o1-mini": {
        "max_tokens": 65536,
        "context_length": 128_000,
        "supports_thinking": True,
        "supports_tool_use": True,
        "supports_streaming": True,
        "supports_vision": False,
        "provider": ProviderType.OPENAI,
    },
}

# Provider class registry — maps provider type to module.class path
_PROVIDER_CLASSES: dict[ProviderType, tuple[str, str]] = {
    ProviderType.ANTHROPIC: (
        "pode_agent.services.ai.anthropic",
        "AnthropicProvider",
    ),
    ProviderType.OPENAI: (
        "pode_agent.services.ai.openai",
        "OpenAIProvider",
    ),
    ProviderType.OPENAI_COMPAT: (
        "pode_agent.services.ai.openai",
        "OpenAIProvider",
    ),
}

# Model prefix → provider type routing
_PREFIX_ROUTING: list[tuple[str, ProviderType]] = [
    # Anthropic Claude
    ("claude-", ProviderType.ANTHROPIC),
    # OpenAI
    ("gpt-", ProviderType.OPENAI),
    ("o1-", ProviderType.OPENAI),
    ("o3-", ProviderType.OPENAI),
    ("chatgpt-", ProviderType.OPENAI),
    # Alibaba Cloud DashScope (qwen)
    ("qwen-", ProviderType.OPENAI_COMPAT),
    ("qwen3", ProviderType.OPENAI_COMPAT),
    ("qwq-", ProviderType.OPENAI_COMPAT),
    # DeepSeek
    ("deepseek-", ProviderType.OPENAI_COMPAT),
    # Zhipu GLM
    ("glm-", ProviderType.OPENAI_COMPAT),
    # Moonshot
    ("moonshot-", ProviderType.OPENAI_COMPAT),
    # Ollama local
    ("llama", ProviderType.OPENAI_COMPAT),
    ("mistral", ProviderType.OPENAI_COMPAT),
    ("codestral", ProviderType.OPENAI_COMPAT),
    # Groq
    ("mixtral-", ProviderType.OPENAI_COMPAT),
    ("llama-", ProviderType.OPENAI_COMPAT),
]


class ModelAdapterFactory:
    """Routes model names to the appropriate AIProvider."""

    @staticmethod
    def get_provider(
        model_name: str,
        config: GlobalConfig | None = None,
    ) -> AIProvider:
        """Get an AIProvider for the given model name.

        Uses prefix routing to determine the provider type, then
        instantiates the appropriate provider class.

        Args:
            model_name: The model identifier (e.g. ``claude-sonnet-4-5-20251101``).
            config: Optional global config for API keys and settings.

        Returns:
            An initialized AIProvider instance.

        Raises:
            ValueError: If no provider is found for the model name.
        """
        provider_type = ModelAdapterFactory._resolve_provider_type(model_name)

        # Check for custom model profile in config
        if config:
            for profile in config.model_profiles:
                if profile.model_name == model_name or profile.name == model_name:
                    return ModelAdapterFactory._create_from_profile(profile)

        module_path, class_name = _PROVIDER_CLASSES.get(
            provider_type, (("", ""))
        )
        if not module_path:
            raise ValueError(f"No provider registered for type: {provider_type}")

        provider_class = _load_provider_class(module_path, class_name)
        kwargs = _build_provider_kwargs(provider_type, config)
        return provider_class(**kwargs)

    @staticmethod
    def get_capabilities(model_name: str) -> ModelCapabilities:
        """Get capability flags for a specific model.

        Uses built-in table with prefix matching. Returns sensible
        defaults for unknown models.
        """
        caps = _MODEL_CAPABILITIES.get(model_name)
        if caps is None:
            # Try prefix match
            for prefix, cap_data in _MODEL_CAPABILITIES.items():
                if model_name.startswith(prefix):
                    caps = cap_data
                    break

        if caps:
            return ModelCapabilities(**caps)

        # Default capabilities
        return ModelCapabilities()

    @staticmethod
    def register_provider(prefix: str, provider_type: ProviderType) -> None:
        """Register a custom model prefix → provider mapping.

        Args:
            prefix: Model name prefix (e.g. ``"my-model-"``).
            provider_type: The provider type to route to.
        """
        _PREFIX_ROUTING.insert(0, (prefix, provider_type))

    @staticmethod
    def _resolve_provider_type(model_name: str) -> ProviderType:
        """Determine provider type from model name prefix."""
        for prefix, provider_type in _PREFIX_ROUTING:
            if model_name.startswith(prefix):
                return provider_type
        raise ValueError(f"Unknown model prefix: {model_name}")

    @staticmethod
    def _create_from_profile(
        profile: Any,  # ModelProfile
    ) -> AIProvider:
        """Create a provider from a ModelProfile config entry."""
        provider_type = profile.provider
        module_path, class_name = _PROVIDER_CLASSES.get(
            provider_type, (("", ""))
        )
        if not module_path:
            raise ValueError(f"No provider for type: {provider_type}")

        provider_class = _load_provider_class(module_path, class_name)
        provider: AIProvider = provider_class(
            api_key=profile.api_key or None,
            base_url=profile.base_url,
        )
        return provider


def _load_provider_class(module_path: str, class_name: str) -> type[AIProvider]:
    """Lazy-load a provider class by module path."""
    import importlib

    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    if not isinstance(cls, type) or not issubclass(cls, AIProvider):
        raise ValueError(f"{module_path}.{class_name} is not an AIProvider subclass")
    return cls


def _build_provider_kwargs(
    provider_type: ProviderType,
    config: GlobalConfig | None,
) -> dict[str, Any]:
    """Build kwargs dict for provider constructor from config."""
    kwargs: dict[str, Any] = {}

    # For OPENAI_COMPAT providers, auto-detect base_url and api_key from env
    if provider_type == ProviderType.OPENAI_COMPAT:
        base_url = os.environ.get("OPENAI_BASE_URL", "") or os.environ.get(
            "DASHSCOPE_BASE_URL", ""
        )
        api_key = os.environ.get("OPENAI_API_KEY", "") or os.environ.get(
            "DASHSCOPE_API_KEY", ""
        )
        if base_url:
            kwargs["base_url"] = base_url
        if api_key:
            kwargs["api_key"] = api_key

    # Config overrides and extensions
    if config:
        # Proxy applies to all providers
        if config.proxy:
            kwargs["proxy"] = config.proxy

        # For openai-compat, check model profiles for base_url
        if provider_type == ProviderType.OPENAI_COMPAT and config.model_profiles:
            for profile in config.model_profiles:
                if profile.base_url:
                    kwargs["base_url"] = profile.base_url
                    if profile.api_key:
                        kwargs["api_key"] = profile.api_key
                    break

    return kwargs


async def query_llm(
    params: UnifiedRequestParams,
    config: GlobalConfig | None = None,
) -> AsyncGenerator[AIResponse, None]:
    """Convenience wrapper: route model name to provider and stream response.

    Args:
        params: Unified request parameters (includes ``model`` field).
        config: Optional global config for API keys.

    Yields:
        AIResponse events from the provider.
    """
    provider = ModelAdapterFactory.get_provider(params.model, config)
    async for response in provider.query(params):
        yield response


# ---------------------------------------------------------------------------
# Provider configuration validation
# ---------------------------------------------------------------------------

# Map provider type → (sdk_module, env_var_name, pip_package, display_name)
_PROVIDER_SDK_INFO: dict[ProviderType, tuple[str, str, str, str]] = {
    ProviderType.ANTHROPIC: (
        "anthropic",
        "ANTHROPIC_API_KEY",
        "anthropic",
        "Anthropic",
    ),
    ProviderType.OPENAI: (
        "openai",
        "OPENAI_API_KEY",
        "openai",
        "OpenAI",
    ),
    ProviderType.OPENAI_COMPAT: (
        "openai",
        "OPENAI_API_KEY",
        "openai",
        "OpenAI-compatible",
    ),
}


def validate_provider_config(
    model_name: str,
    config: GlobalConfig | None = None,
) -> list[str]:
    """Validate that the configured LLM provider is ready to use.

    Checks:
    1. Model name can be resolved to a provider type
    2. Required SDK is importable
    3. API key is available (env var or config profile)

    Returns:
        List of validation error messages (empty if valid).
    """
    errors: list[str] = []

    # 1. Resolve provider type
    try:
        provider_type = ModelAdapterFactory._resolve_provider_type(model_name)
    except ValueError:
        errors.append(
            f"Unknown model: '{model_name}'. "
            f"Supported prefixes: claude-, gpt-, o1-, o3-, qwen-, deepseek-, glm-, moonshot-"
        )
        return errors

    sdk_info = _PROVIDER_SDK_INFO.get(provider_type)
    if sdk_info is None:
        # Provider type exists but no SDK validation info (e.g. ollama local)
        return errors

    sdk_module, env_var, pip_package, display_name = sdk_info

    # 2. Check SDK importability
    import importlib

    try:
        importlib.import_module(sdk_module)
    except ImportError:
        errors.append(
            f"{display_name} SDK not installed. Install it with: "
            f"uv pip install {pip_package}"
        )
        return errors  # No point checking API key if SDK is missing

    # 3. Check API key availability
    api_key_found = False

    # Check environment variable
    if os.environ.get(env_var):
        api_key_found = True

    # Check DASHSCOPE_API_KEY for openai-compat (Alibaba Cloud)
    if (
        not api_key_found
        and provider_type == ProviderType.OPENAI_COMPAT
        and os.environ.get("DASHSCOPE_API_KEY")
    ):
        api_key_found = True

    # Check config model profiles
    if not api_key_found and config:
        for profile in config.model_profiles:
            if (
                profile.model_name == model_name
                or profile.name == model_name
                or profile.provider == provider_type
            ) and profile.api_key:
                api_key_found = True
                break

    if not api_key_found:
        if provider_type == ProviderType.OPENAI_COMPAT:
            errors.append(
                f"API key not configured for {display_name} provider (model: {model_name}). "
                f"Set one of: OPENAI_API_KEY, DASHSCOPE_API_KEY, or add an api_key "
                f"to a model_profile in ~/.pode/config.json"
            )
        else:
            errors.append(
                f"API key not configured for {display_name}. "
                f"Set the {env_var} environment variable, or add an api_key "
                f"to a model_profile in ~/.pode/config.json"
            )

    return errors
