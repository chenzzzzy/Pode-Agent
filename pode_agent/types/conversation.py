"""Conversation message types.

These types model the messages exchanged between user, assistant, and
tools within a session. They are persisted to JSONL logs and used
throughout the application layer.

Reference: docs/api-specs.md — Types section
           docs/data-flows.md — Session log format
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field


class UserMessage(BaseModel):
    """A message from the user (or tool result fed back as user message)."""

    type: Literal["user"] = "user"
    uuid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    message: Any  # MessageParam — flexible to support provider-specific formats
    tool_use_result: Any | None = None


class AssistantMessage(BaseModel):
    """A message from the AI assistant."""

    type: Literal["assistant"] = "assistant"
    uuid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    message: Any  # APIAssistantMessage — provider-specific content blocks
    cost_usd: float = 0.0
    duration_ms: int = 0
    is_api_error_message: bool = False


class ProgressMessage(BaseModel):
    """An intermediate progress message during tool execution."""

    type: Literal["progress"] = "progress"
    uuid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    content: AssistantMessage
    normalized_messages: list[Any] = []
    sibling_tool_use_ids: set[str] = Field(default_factory=set)
    tools: list[Any] = []
    tool_use_id: str


Message = UserMessage | AssistantMessage | ProgressMessage
