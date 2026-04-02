"""Configuration data models (Pydantic v2).

Defines all config schemas: global config (~/.pode/config.json),
project config (.pode.json), and related types.

Reference: docs/api-specs.md — Config API
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DEFAULT_MODEL_NAME = "claude-sonnet-4-5-20251101"


class ProviderType(StrEnum):
    """Supported LLM provider types."""

    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OPENAI_COMPAT = "openai-compat"
    MISTRAL = "mistral"
    DEEPSEEK = "deepseek"
    OLLAMA = "ollama"
    AZURE = "azure"
    GEMINI = "gemini"
    GROQ = "groq"
    BEDROCK = "bedrock"
    VERTEX = "vertex"


class ModelProfile(BaseModel):
    """A user-defined model configuration."""

    name: str
    provider: ProviderType
    model_name: str
    base_url: str | None = None
    api_key: str = ""
    max_tokens: int = 8192
    context_length: int = 200_000
    reasoning_effort: Literal["low", "medium", "high", "minimal"] | None = None
    is_active: bool = True


class ModelPointers(BaseModel):
    """Named model references for different use cases."""

    main: str = "claude-sonnet-4-5-20251101"
    task: str = "claude-haiku-4-5"
    compact: str = "claude-haiku-4-5"
    quick: str = "claude-haiku-4-5"


class McpServerConfig(BaseModel):
    """Configuration for a single MCP server connection."""

    type: Literal["stdio", "sse", "http", "ws", "sse-ide", "ws-ide"]
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)


class CustomApiKeyResponses(BaseModel):
    """Records of user-approved/rejected API keys (stored as hashes)."""

    approved: list[str] = Field(default_factory=list)
    rejected: list[str] = Field(default_factory=list)


class AccountInfo(BaseModel):
    """OAuth account information."""

    email: str
    name: str | None = None
    org: str | None = None
    access_token: str
    refresh_token: str | None = None
    expires_at: datetime | None = None


class GlobalConfig(BaseModel):
    """Global configuration stored at ~/.pode/config.json.

    ``extra='allow'`` provides forward compatibility — unknown keys
    from newer versions won't cause parse failures.
    """

    model_config = ConfigDict(extra="allow")

    num_startups: int = 0
    theme: Literal["dark", "light"] = "dark"
    verbose: bool = False
    has_completed_onboarding: bool = False
    last_onboarding_version: str | None = None
    last_release_notes_seen: str | None = None
    default_model_name: str = DEFAULT_MODEL_NAME
    max_tokens: int | None = None
    auto_compact_threshold: int = 50
    primary_provider: ProviderType | None = None
    model_profiles: list[ModelProfile] = Field(default_factory=list)
    model_pointers: ModelPointers = Field(default_factory=ModelPointers)
    mcp_servers: dict[str, McpServerConfig] = Field(default_factory=dict)
    proxy: str | None = None
    stream: bool = True
    oauth_account: AccountInfo | None = None
    custom_api_key_responses: CustomApiKeyResponses | None = None
    preferred_notif_channel: Literal["terminal", "system"] = "terminal"
    auto_updater_status: (
        Literal["disabled", "enabled", "no_permissions", "not_configured"] | None
    ) = None


class ProjectConfig(BaseModel):
    """Per-project configuration stored at .pode.json.

    ``extra='allow'`` for forward compatibility.
    """

    model_config = ConfigDict(extra="allow")

    allowed_tools: list[str] = Field(default_factory=list)
    denied_tools: list[str] = Field(default_factory=list)
    asked_tools: list[str] = Field(default_factory=list)
    context: dict[str, str] = Field(default_factory=dict)
    history: list[str] = Field(default_factory=list)
    dont_crawl_directory: bool = False
    enable_architect_tool: bool = False
    mcp_servers: dict[str, McpServerConfig] = Field(default_factory=dict)
    last_cost: float | None = None
    last_duration: int | None = None
