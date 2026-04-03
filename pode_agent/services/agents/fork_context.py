"""Fork context builder — creates initial messages for SubAgent sessions.

When an agent has ``fork_context=True``, the parent session's messages up
to and including the tool_use block are loaded from disk (JSONL) and passed
to the child agent as read-only context.

Reference: docs/subagent-system.md — ForkContext
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pode_agent.utils.protocol.session_log import load_messages_from_log

FORK_CONTEXT_TOOL_RESULT_TEXT = (
    "### FORKING CONVERSATION CONTEXT ###\n"
    "The messages above are from a parent conversation context. "
    "They are provided for background only. "
    "Focus on completing the task described below."
)


def _slice_before_tool_use(
    messages: list[dict[str, Any]],
    tool_use_id: str,
) -> list[dict[str, Any]]:
    """Return messages up to (but not including) the assistant turn containing *tool_use_id*.

    Only copies history *before* the TaskTool invocation — the actual
    tool_use / tool_result exchange is replaced with synthetic boundary
    markers built by the caller.
    """
    result: list[dict[str, Any]] = []
    for msg in messages:
        # Check if this is an assistant message containing our tool_use
        if msg.get("role") == "assistant" or msg.get("type") == "assistant":
            content = msg.get("content") or msg.get("message", [])
            if isinstance(content, list):
                for block in content:
                    if (
                        isinstance(block, dict)
                        and block.get("type") == "tool_use"
                        and block.get("id") == tool_use_id
                    ):
                        # Stop *before* this assistant turn
                        return result
        result.append(msg)
    return result


def _build_tool_use_assistant_message(tool_use_id: str) -> dict[str, Any]:
    """Build a synthetic assistant message with a Task tool_use block.

    This mimics the original TaskTool invocation so the child agent
    receives a well-formed conversation prefix.
    """
    return {
        "role": "assistant",
        "content": [
            {
                "type": "tool_use",
                "id": tool_use_id,
                "name": "Task",
                "input": {},
            },
        ],
    }


def _build_fork_context_user_message(tool_use_id: str) -> dict[str, Any]:
    """Build a synthetic user message that acts as context boundary marker."""
    return {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": FORK_CONTEXT_TOOL_RESULT_TEXT,
            },
        ],
    }


def build_fork_context(
    *,
    enabled: bool,
    prompt: str,
    tool_use_id: str | None = None,
    message_log_name: str | None = None,
    fork_number: int = 0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build forked message context for a SubAgent.

    Reads parent messages from disk (JSONL) for read-only isolation.

    Args:
        enabled: Whether fork_context is enabled on the agent config.
        prompt: The task prompt for the sub-agent.
        tool_use_id: The tool_use ID that triggered the fork.
        message_log_name: Path to the parent session's JSONL log file.
        fork_number: Fork number for log disambiguation.

    Returns:
        ``(fork_context_messages, prompt_messages)`` tuple.
        - *fork_context_messages*: parent history (read-only context).
        - *prompt_messages*: synthetic boundary markers + actual task prompt.
    """
    user_prompt_message: dict[str, Any] = {"role": "user", "content": prompt}

    if not enabled or not tool_use_id or not message_log_name:
        # Disabled — only pass the prompt
        return [], [user_prompt_message]

    # Load parent messages from disk (read-only isolation)
    log_path = Path(message_log_name)
    parent_messages = load_messages_from_log(log_path)

    # Copy only messages before the TaskTool invocation
    fork_context_messages = _slice_before_tool_use(parent_messages, tool_use_id)

    # Build prompt messages: synthetic assistant (tool_use) → boundary → task
    prompt_messages: list[dict[str, Any]] = [
        _build_tool_use_assistant_message(tool_use_id),
        _build_fork_context_user_message(tool_use_id),
        user_prompt_message,
    ]

    return fork_context_messages, prompt_messages
