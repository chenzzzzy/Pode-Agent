"""Fork context builder — creates initial messages for SubAgent sessions.

When an agent has ``fork_context=True``, the parent session's messages up
to and including the tool_use block are passed to the child agent as context.
"""

from __future__ import annotations

from typing import Any

FORK_CONTEXT_TOOL_RESULT_TEXT = "[Fork context from parent session]"


def build_fork_context(
    parent_messages: list[dict[str, Any]],
    tool_use_id: str,
) -> list[dict[str, Any]]:
    """Build forked message context for a SubAgent.

    Slices parent messages up to (and including) the assistant message that
    contains the tool_use block with the given ID. Replaces the tool_use with
    a synthetic tool_result containing a summary marker.

    Args:
        parent_messages: Full parent conversation history.
        tool_use_id: The tool_use ID that triggered the fork.

    Returns:
        Sliced and modified messages suitable for the child agent.
    """
    forked: list[dict[str, Any]] = []

    for msg in parent_messages:
        forked.append(msg)

        # Check if this is an assistant message containing our tool_use
        if msg.get("type") == "assistant":
            content = msg.get("message", [])
            if isinstance(content, list):
                for block in content:
                    if (
                        isinstance(block, dict)
                        and block.get("type") == "tool_use"
                        and block.get("id") == tool_use_id
                    ):
                        # We found the triggering message — stop here
                        return forked

    # If we didn't find the tool_use, return all messages
    return forked
