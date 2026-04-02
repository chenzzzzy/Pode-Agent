"""Message format normalizer — converts messages between internal and provider formats.

Internal messages are plain dicts with ``role`` and ``content`` keys.
Each provider adapter has its own expected format for messages.

Reference: docs/api-specs.md — Message Normalization
"""

from __future__ import annotations

import json
from typing import Any

from pode_agent.core.config.schema import ProviderType
from pode_agent.services.ai.base import ToolUseBlock


def normalize_messages_for_provider(
    messages: list[dict[str, Any]],
    provider: ProviderType,
) -> list[dict[str, Any]]:
    """Convert internal messages to the format expected by a specific provider.

    Args:
        messages: Internal message dicts with ``role`` and ``content``.
        provider: The target provider type.

    Returns:
        Messages in the provider's native format.
    """
    if provider == ProviderType.ANTHROPIC or provider == ProviderType.BEDROCK:
        return to_anthropic_messages(messages)
    elif provider in (
        ProviderType.OPENAI,
        ProviderType.OPENAI_COMPAT,
        ProviderType.AZURE,
    ):
        return to_openai_messages(messages)
    # Default: pass through as-is
    return list(messages)


def to_anthropic_messages(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert internal messages to Anthropic MessageParam format.

    Rules:
    - String content → pass through.
    - List content → pass through.
    - Dict content → wrap in a list.
    - Tool result messages → ``role="user"`` with ``tool_result`` content blocks.
    """
    result: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content")

        if isinstance(content, str | list):
            result.append({"role": role, "content": content})
        elif isinstance(content, dict):
            # Check if this is a tool result
            if content.get("type") == "tool_result":
                result.append({"role": "user", "content": [content]})
            else:
                result.append({"role": role, "content": [content]})
        else:
            result.append({"role": role, "content": str(content)})

    return result


def to_openai_messages(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert internal messages to OpenAI ChatCompletionMessageParam format.

    Rules:
    - String content → pass through.
    - List content → pass through (OpenAI supports multipart content).
    - Dict content → wrap in a list.
    - Tool result messages → ``role="tool"`` with ``tool_call_id``.
    """
    result: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content")
        tool_call_id = msg.get("tool_call_id")

        # Tool result messages
        if tool_call_id:
            result.append({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": content if isinstance(content, str) else json.dumps(content),
            })
            continue

        if isinstance(content, str | list):
            result.append({"role": role, "content": content})
        elif isinstance(content, dict):
            result.append({"role": role, "content": [content]})
        else:
            result.append({"role": role, "content": str(content)})

    return result


def build_tool_result_message(
    tool_uses: list[ToolUseBlock],
    tool_results: dict[str, str],
) -> dict[str, Any]:
    """Build a tool result message for the LLM.

    Creates a user message containing tool_result content blocks,
    one for each tool use.

    Args:
        tool_uses: The tool use requests from the assistant.
        tool_results: Mapping of tool_use_id → result text.

    Returns:
        A message dict with ``role="user"`` and tool result content blocks.
    """
    content_blocks: list[dict[str, Any]] = []
    for tu in tool_uses:
        result_text = tool_results.get(tu.id, "")
        # Anthropic-style tool_result block
        content_blocks.append({
            "type": "tool_result",
            "tool_use_id": tu.id,
            "content": result_text,
        })

    return {
        "role": "user",
        "content": content_blocks,
    }


def extract_tool_uses(
    assistant_message: dict[str, Any],
) -> list[ToolUseBlock]:
    """Extract tool use blocks from an assistant message.

    Looks for ``tool_use`` content blocks in the message content.

    Args:
        assistant_message: The assistant's response message dict.

    Returns:
        List of ToolUseBlock instances found in the message.
    """
    content = assistant_message.get("content")
    if not content:
        return []

    blocks: list[ToolUseBlock] = []

    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                tool_input = block.get("input", {})
                if isinstance(tool_input, str):
                    try:
                        tool_input = json.loads(tool_input)
                    except json.JSONDecodeError:
                        tool_input = {"raw": tool_input}
                blocks.append(ToolUseBlock(
                    id=block.get("id", ""),
                    name=block.get("name", ""),
                    input=tool_input if isinstance(tool_input, dict) else {},
                ))
    elif isinstance(content, dict) and content.get("type") == "tool_use":
        tool_input = content.get("input", {})
        if isinstance(tool_input, str):
            try:
                tool_input = json.loads(tool_input)
            except json.JSONDecodeError:
                tool_input = {"raw": tool_input}
        blocks.append(ToolUseBlock(
            id=content.get("id", ""),
            name=content.get("name", ""),
            input=tool_input if isinstance(tool_input, dict) else {},
        ))

    return blocks
