"""SessionManager skeleton: conversation state and JSONL persistence.

Full process_input() and event publishing are deferred to Phase 2.

Reference: docs/api-specs.md — Session API
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from pode_agent.core.permissions.types import PermissionContext
from pode_agent.core.tools.base import Tool
from pode_agent.infra.logging import get_logger
from pode_agent.utils.protocol.session_log import (
    get_session_log_path,
    load_messages_from_log,
    save_message,
)

logger = get_logger(__name__)


class SessionManager:
    """Manages a single conversation session.

    Responsibilities (Phase 1 skeleton):
    - Hold messages in memory
    - Persist messages to JSONL
    - Track tools and permission context
    - Support abort via asyncio.Event

    process_input() is deferred to Phase 2 (LLM integration).
    """

    def __init__(
        self,
        tools: list[Tool] | None = None,
        *,
        initial_messages: list[dict[str, Any]] | None = None,
        message_log_name: str | None = None,
        fork_number: int = 0,
        permission_context: PermissionContext | None = None,
    ) -> None:
        self._messages: list[dict[str, Any]] = list(initial_messages or [])
        self._tools: list[Tool] = tools or []
        self._abort_event = asyncio.Event()
        self._permission_context = permission_context or PermissionContext()

        # JSONL log
        self._log_path = get_session_log_path(fork_number=fork_number)

        # If a log name was given, try to load existing messages
        if message_log_name:
            log_file = Path(message_log_name)
            if log_file.exists():
                loaded = load_messages_from_log(log_file)
                if loaded:
                    self._messages = loaded

    @property
    def tools(self) -> list[Tool]:
        return list(self._tools)

    @property
    def permission_context(self) -> PermissionContext:
        return self._permission_context

    @property
    def abort_event(self) -> asyncio.Event:
        return self._abort_event

    @property
    def log_path(self) -> Path:
        return self._log_path

    def get_messages(self) -> list[dict[str, Any]]:
        """Return a copy of the message list."""
        return list(self._messages)

    def save_message(self, message: dict[str, Any]) -> None:
        """Append a message to the in-memory list and persist to JSONL."""
        self._messages.append(message)
        save_message(self._log_path, message)

    def abort(self) -> None:
        """Signal that the current operation should be aborted."""
        self._abort_event.set()
