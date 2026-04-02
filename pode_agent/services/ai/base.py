"""AI provider abstract base class and shared types.

Defines the contract for all LLM provider adapters and the shared
data types used between the Agentic Loop (app/query.py) and providers.

Reference: docs/api-specs.md — AI Service API
           docs/modules.md — services/ai module
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any, Literal

from pydantic import BaseModel

from pode_agent.core.config.schema import ProviderType

# ---------------------------------------------------------------------------
# Token usage
# ---------------------------------------------------------------------------

class TokenUsage(BaseModel):
    """Token consumption metrics from an LLM API call."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


# ---------------------------------------------------------------------------
# Tool definition (provider-agnostic)
# ---------------------------------------------------------------------------

class ToolDefinition(BaseModel):
    """A tool definition passed to the LLM in a unified format.

    Each provider adapter converts this to its native schema
    (e.g. ``anthropic.types.ToolParam``).
    """

    name: str
    description: str
    input_schema: dict[str, Any]


# ---------------------------------------------------------------------------
# Tool use block (from LLM response)
# ---------------------------------------------------------------------------

class ToolUseBlock(BaseModel):
    """A tool use request returned by the LLM."""

    id: str
    name: str
    input: dict[str, Any]


# ---------------------------------------------------------------------------
# AI response (streaming event)
# ---------------------------------------------------------------------------

class AIResponse(BaseModel):
    """A single streaming event from an AI provider.

    Providers yield these during a streaming query. The Agentic Loop
    consumes them to build assistant messages and detect tool use.
    """

    type: Literal[
        "text_delta",
        "tool_use_start",
        "tool_use_delta",
        "tool_use_end",
        "message_done",
        "error",
    ]
    text: str | None = None
    tool_use_id: str | None = None
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    usage: TokenUsage | None = None
    cost_usd: float | None = None
    stop_reason: str | None = None
    error_message: str | None = None
    is_retriable: bool = False


# ---------------------------------------------------------------------------
# Unified request params
# ---------------------------------------------------------------------------

class UnifiedRequestParams(BaseModel):
    """Provider-agnostic parameters for an LLM query."""

    messages: list[dict[str, Any]]
    system_prompt: str
    model: str
    max_tokens: int = 8192
    tools: list[ToolDefinition] | None = None
    temperature: float | None = None
    thinking_tokens: int | None = None
    stream: bool = True
    stop_sequences: list[str] | None = None
    metadata: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Model capabilities
# ---------------------------------------------------------------------------

class ModelCapabilities(BaseModel):
    """Capability flags for a specific model."""

    max_tokens: int = 8192
    context_length: int = 200_000
    supports_thinking: bool = False
    supports_tool_use: bool = True
    supports_streaming: bool = True
    supports_vision: bool = False
    provider: ProviderType = ProviderType.ANTHROPIC


# ---------------------------------------------------------------------------
# AI Provider ABC
# ---------------------------------------------------------------------------

class AIProvider(ABC):
    """Abstract base class for LLM provider adapters.

    Each provider implements ``query()`` which returns an async generator
    of ``AIResponse`` events (streaming).
    """

    @abstractmethod
    async def query(
        self, params: UnifiedRequestParams
    ) -> AsyncGenerator[AIResponse, None]:
        """Stream responses from the LLM.

        Yields ``AIResponse`` events of various types (text_delta,
        tool_use_*, message_done, error).
        """
        ...  # pragma: no cover
