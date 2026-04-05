"""SessionManager: conversation state, JSONL persistence, and event orchestration.

Coordinates the Agentic Loop by running ``query()`` / ``query_core()``
and yielding ``SessionEvent`` instances to the UI layer.

Reference: docs/api-specs.md — Session API
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from pode_agent.app.query import QueryOptions, query
from pode_agent.core.config.schema import DEFAULT_MODEL_NAME
from pode_agent.core.permissions.types import (
    PermissionContext,
    PermissionDecision,
)
from pode_agent.core.tools.base import Tool
from pode_agent.infra.logging import get_logger
from pode_agent.types.session_events import SessionEvent, SessionEventType
from pode_agent.utils.protocol.session_log import (
    get_session_log_path,
    load_messages_from_log,
    rewrite_messages,
    save_message,
)

logger = get_logger(__name__)

BASE_SYSTEM_PROMPT = "You are Pode, an AI-powered terminal coding assistant."


class SessionManager:
    """Manages a single conversation session.

    Responsibilities:
    - Hold messages in memory
    - Persist messages to JSONL
    - Track tools and permission context
    - Support abort via asyncio.Event
    - Orchestrate the Agentic Loop via process_input()
    - Track cumulative cost
    """

    def __init__(
        self,
        tools: list[Tool] | None = None,
        *,
        initial_messages: list[dict[str, Any]] | None = None,
        message_log_name: str | None = None,
        fork_number: int = 0,
        permission_context: PermissionContext | None = None,
        model: str = DEFAULT_MODEL_NAME,
        system_prompt: str = BASE_SYSTEM_PROMPT,
    ) -> None:
        self._messages: list[dict[str, Any]] = list(initial_messages or [])
        self._tools: list[Tool] = tools or []
        self._abort_event = asyncio.Event()
        self._permission_context = permission_context or PermissionContext()
        self._cost_usd: float = 0.0
        self._input_tokens: int = 0
        self._output_tokens: int = 0
        self._model = model
        self._system_prompt = system_prompt

        # Permission resolution
        self._permission_event = asyncio.Event()
        self._last_permission_decision: PermissionDecision | None = None

        # JSONL log
        self._log_path = (
            Path(message_log_name)
            if message_log_name is not None
            else get_session_log_path(fork_number=fork_number)
        )

        # If a log name was given, try to load existing messages
        if message_log_name and self._log_path.exists():
            loaded = load_messages_from_log(self._log_path)
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

    @property
    def model(self) -> str:
        return self._model

    @model.setter
    def model(self, value: str) -> None:
        self._model = value

    def get_messages(self) -> list[dict[str, Any]]:
        """Return a copy of the message list."""
        return list(self._messages)

    def save_message(self, message: dict[str, Any]) -> None:
        """Append a message to the in-memory list and persist to JSONL."""
        self._messages.append(message)
        save_message(self._log_path, message)

    def replace_messages(self, messages: list[dict[str, Any]]) -> None:
        """Replace the in-memory history and rewrite the session log."""
        self._messages = list(messages)
        rewrite_messages(self._log_path, self._messages)

    def abort(self) -> None:
        """Signal that the current operation should be aborted."""
        self._abort_event.set()

    def get_total_cost(self) -> float:
        """Return the session-level cumulative cost in USD."""
        return self._cost_usd

    def add_cost(self, cost_usd: float) -> None:
        """Add a cost amount to the session total."""
        self._cost_usd += cost_usd

    def add_usage(self, input_tokens: int, output_tokens: int) -> None:
        """Add token usage to the session totals."""
        self._input_tokens += input_tokens
        self._output_tokens += output_tokens

    def get_usage_totals(self) -> dict[str, int]:
        """Return cumulative token usage totals for this session."""
        return {
            "cumulative_input_tokens": self._input_tokens,
            "cumulative_output_tokens": self._output_tokens,
            "cumulative_total_tokens": self._input_tokens + self._output_tokens,
        }

    def resolve_permission(self, decision: PermissionDecision) -> None:
        """Resolve a pending permission request.

        Called by the UI layer when the user makes a permission decision.
        """
        self._last_permission_decision = decision
        self._permission_event.set()

    async def process_input(
        self,
        prompt: str,
        *,
        options: QueryOptions | None = None,
    ) -> AsyncGenerator[SessionEvent, None]:
        """Process a user input through the Agentic Loop.

        Builds QueryOptions, runs ``query()``, yields events,
        and handles side effects (cost tracking).

        Args:
            prompt: The user's text input.
            options: Optional override for QueryOptions.

        Yields:
            SessionEvent instances.
        """
        if options is None:
            options = QueryOptions(
                model=self._model,
                cwd=str(Path.cwd()),
            )

        async for event in query(
            prompt=prompt,
            system_prompt=self._system_prompt,
            tools=self._tools,
            messages=self._messages,
            session=self,
            options=options,
        ):
            # Handle side effects
            if event.type == SessionEventType.COST_UPDATE and event.data:
                cost = float(event.data.get("cost_usd", 0.0))
                input_tokens = int(event.data.get("input_tokens", 0))
                output_tokens = int(event.data.get("output_tokens", 0))
                duration_ms = int(event.data.get("duration_ms", 0))
                self.add_cost(cost)
                self.add_usage(input_tokens, output_tokens)
                usage_totals = self.get_usage_totals()
                # Update event with actual total
                event = SessionEvent(
                    type=event.type,
                    data={
                        **event.data,
                        "total_usd": self.get_total_cost(),
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "total_tokens": int(event.data.get("total_tokens", input_tokens + output_tokens)),
                        "duration_ms": duration_ms,
                        **usage_totals,
                    },
                    message_id=event.message_id,
                )

            yield event

    @classmethod
    def load_from_log(
        cls,
        log_name: str,
        tools: list[Tool] | None = None,
        **kwargs: Any,
    ) -> SessionManager:
        """Create a SessionManager restored from a JSONL log.

        Args:
            log_name: Path to the JSONL log file.
            tools: Tools to make available.
            **kwargs: Additional constructor arguments.

        Returns:
            A SessionManager with messages loaded from the log.
        """
        return cls(
            tools=tools,
            message_log_name=log_name,
            **kwargs,
        )
