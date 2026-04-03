"""OpenAI provider adapter.

Implements the AIProvider interface for OpenAI's Chat Completions API,
supporting streaming, function calling (tool use), and reasoning models.

Reference: docs/api-specs.md — AI Provider API
           docs/modules.md — services/ai/openai
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncGenerator
from typing import Any

import openai
from openai import AsyncOpenAI

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


def _to_openai_tools(
    tools: list[ToolDefinition] | None,
) -> list[dict[str, Any]]:
    """Convert ToolDefinition list to OpenAI function calling format."""
    if not tools:
        return []
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.input_schema,
            },
        }
        for t in tools
    ]


def _to_openai_messages(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert internal message format to OpenAI ChatCompletion format.

    Internal messages are dicts with ``role`` and ``content`` keys.
    Handles conversion from Anthropic-style content blocks:

    - Assistant messages with ``tool_use`` blocks → ``tool_calls`` array
    - User messages with ``tool_result`` blocks → ``role="tool"`` messages

    Plain text / list content without tool blocks is passed through unchanged.
    """
    result: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content")

        # --- Assistant with tool_use content blocks → tool_calls ---
        if role == "assistant" and isinstance(content, list):
            has_tool_uses = any(
                isinstance(b, dict) and b.get("type") == "tool_use"
                for b in content
            )
            if has_tool_uses:
                text_parts: list[str] = []
                tool_calls: list[dict[str, Any]] = []
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_use":
                        tool_input = block.get("input", {})
                        if isinstance(tool_input, dict):
                            tool_input = json.dumps(tool_input)
                        elif not isinstance(tool_input, str):
                            tool_input = str(tool_input)
                        tool_calls.append({
                            "id": block.get("id", ""),
                            "type": "function",
                            "function": {
                                "name": block.get("name", ""),
                                "arguments": tool_input,
                            },
                        })
                openai_msg: dict[str, Any] = {"role": "assistant"}
                openai_msg["content"] = "\n".join(text_parts) if text_parts else None
                if tool_calls:
                    openai_msg["tool_calls"] = tool_calls
                result.append(openai_msg)
                continue

        # --- User with tool_result content blocks → role="tool" messages ---
        if role == "user" and isinstance(content, list):
            has_tool_results = any(
                isinstance(b, dict) and b.get("type") == "tool_result"
                for b in content
            )
            if has_tool_results:
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        result.append({
                            "role": "tool",
                            "tool_call_id": block.get("tool_use_id", ""),
                            "content": block.get("content", ""),
                        })
                    elif isinstance(block, dict) and block.get("type") == "text":
                        result.append({"role": "user", "content": block.get("text", "")})
                continue

        # --- Default: plain string/list/dict content ---
        if isinstance(content, str | list):
            result.append({"role": role, "content": content})
        elif isinstance(content, dict):
            result.append({"role": role, "content": [content]})
        else:
            result.append({"role": role, "content": str(content) if content else ""})

    return result


class OpenAIProvider(AIProvider):
    """OpenAI Chat Completions API provider with streaming support."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        proxy: str | None = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self._base_url = base_url
        self._proxy = proxy
        self._client = self._create_client()

    def _create_client(self) -> AsyncOpenAI:
        """Create the AsyncOpenAI client.

        Supports custom ``base_url`` for OpenAI-compatible providers
        (Ollama, DeepSeek, Azure, etc.).
        """
        kwargs: dict[str, Any] = {}
        if self._api_key:
            kwargs["api_key"] = self._api_key
        if self._base_url:
            kwargs["base_url"] = self._base_url
        if self._proxy:
            kwargs["http_client"] = None  # proxy handled via httpx
        return AsyncOpenAI(**kwargs)

    async def query(
        self, params: UnifiedRequestParams
    ) -> AsyncGenerator[AIResponse, None]:
        """Stream responses from the OpenAI Chat Completions API."""
        messages = _to_openai_messages(params.messages)
        tools = _to_openai_tools(params.tools)

        kwargs: dict[str, Any] = {
            "model": params.model,
            "max_tokens": params.max_tokens,
            "messages": messages,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools
        if params.temperature is not None:
            kwargs["temperature"] = params.temperature
        if params.stop_sequences:
            kwargs["stop"] = params.stop_sequences
        if params.thinking_tokens and params.thinking_tokens > 0:
            kwargs["reasoning_effort"] = _map_thinking_to_effort(params.thinking_tokens)

        retries = 0
        while True:
            try:
                response = await self._client.chat.completions.create(**kwargs)
                async for chunk in response:
                    async for resp in self._process_chunk(chunk):
                        yield resp
                return  # Success — exit retry loop

            except openai.RateLimitError as e:
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

            except openai.AuthenticationError as e:
                yield AIResponse(
                    type="error",
                    error_message=f"Authentication error: {e}",
                    is_retriable=False,
                )
                return

            except openai.APIConnectionError as e:
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

    async def _process_chunk(
        self, chunk: Any,
    ) -> AsyncGenerator[AIResponse, None]:
        """Process a single ChatCompletionChunk into AIResponse(s)."""
        if not chunk.choices:
            return

        choice = chunk.choices[0]
        delta = choice.delta

        # Text content
        content = getattr(delta, "content", None)
        if content:
            yield AIResponse(type="text_delta", text=content)

        # Tool calls
        tool_calls = getattr(delta, "tool_calls", None)
        if tool_calls:
            for tc in tool_calls:
                tc_id = getattr(tc, "id", None)
                func = getattr(tc, "function", None)

                if tc_id:
                    # New tool call — yield start event
                    func_name = getattr(func, "name", "") if func else ""
                    yield AIResponse(
                        type="tool_use_start",
                        tool_use_id=tc_id,
                        tool_name=func_name or "",
                    )
                elif func:
                    # Continuing tool call — yield delta
                    args_delta = getattr(func, "arguments", "")
                    if args_delta:
                        yield AIResponse(
                            type="tool_use_delta",
                            text=args_delta,
                        )

        # Finish reason
        finish_reason = getattr(choice, "finish_reason", None)
        if finish_reason:
            usage = None
            if hasattr(chunk, "usage") and chunk.usage:
                usage = TokenUsage(
                    input_tokens=getattr(chunk.usage, "prompt_tokens", 0),
                    output_tokens=getattr(chunk.usage, "completion_tokens", 0),
                )
            yield AIResponse(
                type="message_done",
                usage=usage,
                stop_reason=finish_reason,
            )


def _map_thinking_to_effort(thinking_tokens: int) -> str:
    """Map thinking token budget to OpenAI reasoning_effort level."""
    if thinking_tokens >= 10000:
        return "high"
    elif thinking_tokens >= 5000:
        return "medium"
    return "low"
