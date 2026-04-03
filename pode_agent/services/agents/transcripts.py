"""In-memory transcript storage for SubAgent conversations.

Stores the full message history of completed sub-agent runs,
enabling the ``resume`` feature in TaskTool.

Reference: docs/subagent-system.md — Transcript Storage
"""

from __future__ import annotations

from typing import Any

# Process-level in-memory store
_transcripts: dict[str, list[dict[str, Any]]] = {}


def save_agent_transcript(agent_id: str, messages: list[dict[str, Any]]) -> None:
    """Save a sub-agent's full conversation history (deep copy)."""
    _transcripts[agent_id] = [dict(m) if isinstance(m, dict) else m for m in messages]


def get_agent_transcript(agent_id: str) -> list[dict[str, Any]] | None:
    """Retrieve a transcript for ``resume`` (returns None if not found)."""
    transcript = _transcripts.get(agent_id)
    if transcript is None:
        return None
    return list(transcript)


def clear_transcripts() -> None:
    """Clear all stored transcripts (for testing)."""
    _transcripts.clear()
