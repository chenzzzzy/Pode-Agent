"""Session event types for communication between query loop and UI.

These types flow through the ``SessionManager.process_input()``
async generator, allowing the UI layer to render progress, handle
permission prompts, and track costs.

Reference: docs/api-specs.md — Session Event API
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel


class SessionEventType(StrEnum):
    """Types of events emitted during an agent session."""

    USER_MESSAGE = "user_message"
    ASSISTANT_DELTA = "assistant_delta"
    TOOL_USE_START = "tool_use_start"
    TOOL_PROGRESS = "tool_progress"
    TOOL_RESULT = "tool_result"
    PERMISSION_REQUEST = "permission_request"
    COST_UPDATE = "cost_update"
    MODEL_ERROR = "model_error"
    DONE = "done"


class SessionEvent(BaseModel):
    """A single event emitted by the Agentic Loop.

    Events are yielded by ``query()`` / ``query_core()`` and consumed
    by the UI layer (REPL or print mode).
    """

    type: SessionEventType
    data: Any = None
    message_id: str | None = None


class PermissionRequestData(BaseModel):
    """Data payload for a ``PERMISSION_REQUEST`` event."""

    tool_name: str
    tool_input: dict[str, Any]
    risk_level: Literal["low", "medium", "high"] = "medium"
    description: str | None = None
