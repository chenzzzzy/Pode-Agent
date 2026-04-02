"""Auto-compact: automatic context compression for long conversations.

Phase 3: framework with truncation-based compaction.
Phase 6: LLM-based summarization strategy.

When the conversation exceeds a token threshold, older messages are
compacted to keep the context window within limits. The strategy is:
- Keep the system message (first message if role=system)
- Keep the last N messages for recency
- Truncate (Phase 3) or summarize (Phase 6) the middle messages

Reference: docs/agent-loop.md — Auto-compact
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Thresholds for triggering auto-compact
AUTO_COMPACT_THRESHOLD_MESSAGES = 50
AUTO_COMPACT_THRESHOLD_CHARS = 400_000  # rough proxy for ~100k tokens
DEFAULT_KEEP_RECENT = 10  # number of recent messages to preserve


def auto_compact_if_needed(
    messages: list[dict[str, Any]],
    *,
    max_messages: int = AUTO_COMPACT_THRESHOLD_MESSAGES,
    max_chars: int = AUTO_COMPACT_THRESHOLD_CHARS,
    keep_recent: int = DEFAULT_KEEP_RECENT,
) -> list[dict[str, Any]]:
    """Check if compaction is needed and apply if so.

    Returns a new list (immutable — input is never mutated).
    If compaction is not needed, returns the original list unchanged.
    """
    if len(messages) <= max_messages and _estimate_chars(messages) <= max_chars:
        return messages

    logger.info(
        "Auto-compact triggered: %d messages, ~%d chars",
        len(messages),
        _estimate_chars(messages),
    )
    return compact_messages(messages, keep_recent=keep_recent)


def compact_messages(
    messages: list[dict[str, Any]],
    *,
    keep_recent: int = DEFAULT_KEEP_RECENT,
) -> list[dict[str, Any]]:
    """Compact messages by truncating older ones.

    Phase 3: simple truncation (keep system + last N).
    Phase 6: will use LLM-based summarization.

    Args:
        messages: Full conversation history.
        keep_recent: Number of recent messages to preserve.

    Returns:
        New list with compacted messages.
    """
    if len(messages) <= keep_recent:
        return messages

    # Find system messages at the start
    system_prefix: list[dict[str, Any]] = []
    for msg in messages:
        role = msg.get("role", msg.get("type", ""))
        if role in ("system",):
            system_prefix.append(msg)
        else:
            break

    # Keep system prefix + last N messages
    remaining_count = len(messages) - len(system_prefix)
    if remaining_count <= keep_recent:
        return messages

    truncated_count = remaining_count - keep_recent
    recent = messages[-keep_recent:]

    logger.info(
        "Compacted %d/%d messages (kept %d system + %d recent)",
        truncated_count,
        remaining_count,
        len(system_prefix),
        keep_recent,
    )

    # Insert a compaction notice so the LLM knows context was trimmed
    notice: dict[str, Any] = {
        "role": "user",
        "content": (
            f"[System: {truncated_count} earlier messages were compacted "
            f"to save context space. The conversation continues below.]"
        ),
    }

    return [*system_prefix, notice, *recent]


def _estimate_chars(messages: list[dict[str, Any]]) -> int:
    """Rough character count estimate across all messages."""
    total = 0
    for msg in messages:
        content = msg.get("content", msg.get("message", ""))
        if isinstance(content, str):
            total += len(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    total += len(str(part.get("text", part.get("input", ""))))
                elif isinstance(part, str):
                    total += len(part)
    return total
