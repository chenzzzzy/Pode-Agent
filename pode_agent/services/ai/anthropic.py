"""Anthropic Claude provider adapter.

Implements the AIProvider interface for Anthropic's Messages API,
supporting streaming, tool use, extended thinking, and Bedrock.

Reference: docs/api-specs.md — AI Provider API
           docs/modules.md — services/ai/anthropic
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator
from typing import Any

import anthropic
from anthropic import NOT_GIVEN, AsyncAnthropic, AsyncAnthropicBedrock

from pode_agent.infra.logging import get_logger
from pode_agent.services.ai.base import (
    AIProvider,
    AIResponse,
    TokenUsage,
    ToolDefinition,
    UnifiedRequestParams,
)

logger = get_logger(__name__)

MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 1.0


def _to_anthropic_tools(
    tools: list[ToolDefinition] | None,
) -> list[dict[str, Any]] | anthropic.NotGiven:
    """Convert ToolDefinition list to Anthropic ToolParam format."""
    if not tools:
        return NOT_GIVEN
    return [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.input_schema,
        }
        for t in tools
    ]


def _to_anthropic_messages(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert internal message format to Anthropic MessageParam format.

    Internal messages are dicts with ``role`` and ``content`` keys.
    ``content`` can be a string or a list of content blocks.
    Tool result messages use role ``user`` with ``tool_result`` content blocks.
    """
    result: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content")
        if isinstance(content, str | list):
            result.append({"role": role, "content": content})
        elif isinstance(content, dict):
            result.append({"role": role, "content": [content]})
        else:
            result.append({"role": role, "content": str(content)})
    return result


class AnthropicProvider(AIProvider):
    """Anthropic Claude API provider with streaming support."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        proxy: str | None = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._base_url = base_url
        self._proxy = proxy
        self._client = self._create_client()

    def _create_client(self) -> AsyncAnthropic | AsyncAnthropicBedrock:
        """Create the appropriate Anthropic client.

        Detects Bedrock environment variables and creates the
        corresponding client type.
        """
        if os.environ.get("ANTHROPIC_BEDROCK_BASE_URL"):
            return AsyncAnthropicBedrock(
                aws_access_key=os.environ.get("AWS_ACCESS_KEY_ID", ""),
                aws_secret_key=os.environ.get("AWS_SECRET_ACCESS_KEY", ""),
                aws_region=os.environ.get("AWS_REGION", "us-east-1"),
            )
        kwargs: dict[str, Any] = {}
        if self._api_key:
            kwargs["api_key"] = self._api_key
        if self._base_url:
            kwargs["base_url"] = self._base_url
        if self._proxy:
            kwargs["http_client"] = None  # proxy handled via httpx
        return AsyncAnthropic(**kwargs)

    async def query(
        self, params: UnifiedRequestParams
    ) -> AsyncGenerator[AIResponse, None]:
        """Stream responses from the Anthropic Messages API."""
        messages = _to_anthropic_messages(params.messages)
        tools = _to_anthropic_tools(params.tools)

        extra_kwargs: dict[str, Any] = {}
        if params.thinking_tokens and params.thinking_tokens > 0:
            extra_kwargs["thinking"] = {
                "type": "enabled",
                "budget_tokens": params.thinking_tokens,
            }

        retries = 0
        while True:
            try:
                # mypy: SDK types are overly strict for our dict-based approach.
                # The Anthropic SDK expects specific TypedDict types but we pass
                # plain dicts — functionally correct but type-incompatible.
                stream_ctx = self._client.messages.stream(
                    model=params.model,
                    max_tokens=params.max_tokens,
                    system=params.system_prompt,
                    messages=messages,
                    tools=tools,
                    temperature=(
                        params.temperature if params.temperature is not None else NOT_GIVEN
                    ),
                    stop_sequences=(
                        params.stop_sequences
                        if params.stop_sequences is not None
                        else NOT_GIVEN
                    ),
                    **extra_kwargs,
                )
                async with stream_ctx as stream:
                    async for event in stream:
                        async for resp in self._process_stream_event(event):
                            yield resp
                return  # Success — exit retry loop

            except anthropic.RateLimitError as e:
                retries += 1
                if retries > MAX_RETRIES:
                    yield AIResponse(
                        type="error",
                        error_message=f"Rate limit exceeded after {MAX_RETRIES} retries: {e}",
                        is_retriable=True,
                    )
                    return
                backoff = INITIAL_BACKOFF_SECONDS * (2 ** (retries - 1))
                logger.warning("Rate limited, retrying in %.1fs (attempt %d)", backoff, retries)
                await asyncio.sleep(backoff)

            except anthropic.AuthenticationError as e:
                yield AIResponse(
                    type="error",
                    error_message=f"Authentication error: {e}",
                    is_retriable=False,
                )
                return

            except anthropic.APIConnectionError as e:
                yield AIResponse(
                    type="error",
                    error_message=f"Connection error: {e}",
                    is_retriable=True,
                )
                return

            except Exception as e:
                yield AIResponse(
                    type="error",
                    error_message=f"Unexpected error: {e}",
                    is_retriable=False,
                )
                return

    async def _process_stream_event(
        self, event: Any,
    ) -> AsyncGenerator[AIResponse, None]:
        """Process a single Anthropic SSE stream event into AIResponse(s)."""
        event_type = getattr(event, "type", "")

        if event_type == "content_block_delta":
            delta = event.delta
            delta_type = getattr(delta, "type", "")

            if delta_type == "text_delta":
                yield AIResponse(type="text_delta", text=delta.text)

            elif delta_type == "thinking_delta":
                # Extended thinking — pass through as text_delta for now
                yield AIResponse(type="text_delta", text=delta.thinking)

            elif delta_type == "input_json_delta":
                # Tool use JSON delta — yield for buffering by caller
                yield AIResponse(
                    type="tool_use_delta",
                    tool_use_id=getattr(event, "index", None),
                    text=delta.partial_json,
                )

        elif event_type == "content_block_start":
            cb = event.content_block
            if getattr(cb, "type", "") == "tool_use":
                yield AIResponse(
                    type="tool_use_start",
                    tool_use_id=cb.id,
                    tool_name=cb.name,
                )

        elif event_type == "content_block_stop":
            # We don't yield tool_use_end here — the caller
            # (query_core) reconstructs from buffered deltas
            pass

        elif event_type == "message_delta":
            usage = getattr(event, "usage", None)
            delta = getattr(event, "delta", None)
            stop_reason = getattr(delta, "stop_reason", None) if delta else None
            token_usage = None
            if usage:
                token_usage = TokenUsage(
                    output_tokens=getattr(usage, "output_tokens", 0),
                )
            yield AIResponse(
                type="message_done",
                usage=token_usage,
                stop_reason=stop_reason,
            )
