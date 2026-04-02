"""Tests for app/session.py — Phase 2 SessionManager features.

Tests process_input(), cost tracking, permission resolution, and log restoration.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from pode_agent.app.session import SessionManager
from pode_agent.core.permissions.types import PermissionContext, PermissionDecision
from pode_agent.types.session_events import SessionEvent, SessionEventType


class TestSessionManagerCost:
    def test_initial_cost_zero(self) -> None:
        sm = SessionManager()
        assert sm.get_total_cost() == 0.0

    def test_add_cost(self) -> None:
        sm = SessionManager()
        sm.add_cost(0.005)
        assert sm.get_total_cost() == pytest.approx(0.005)

    def test_accumulates(self) -> None:
        sm = SessionManager()
        sm.add_cost(0.003)
        sm.add_cost(0.002)
        assert sm.get_total_cost() == pytest.approx(0.005)


class TestSessionManagerModel:
    def test_default_model(self) -> None:
        sm = SessionManager()
        assert sm.model == "claude-sonnet-4-5-20251101"

    def test_set_model(self) -> None:
        sm = SessionManager()
        sm.model = "gpt-4o"
        assert sm.model == "gpt-4o"


class TestSessionManagerProcessInput:
    async def test_delegates_to_query(self) -> None:
        """process_input should call query() and yield its events."""
        mock_event = SessionEvent(
            type=SessionEventType.USER_MESSAGE,
            data={"message": "test"},
        )

        async def mock_query(*args: Any, **kwargs: Any) -> Any:
            yield mock_event

        with patch("pode_agent.app.session.query", side_effect=mock_query):
            sm = SessionManager()
            events = [e async for e in sm.process_input("hello")]
            assert len(events) >= 1
            assert events[0].type == SessionEventType.USER_MESSAGE

    async def test_tracks_cost_from_events(self) -> None:
        """process_input should accumulate cost from COST_UPDATE events."""
        events_sequence = [
            SessionEvent(type=SessionEventType.COST_UPDATE, data={"cost_usd": 0.01}),
            SessionEvent(type=SessionEventType.DONE, data={}),
        ]

        async def mock_query(*args: Any, **kwargs: Any) -> Any:
            for ev in events_sequence:
                yield ev

        with patch("pode_agent.app.session.query", side_effect=mock_query):
            sm = SessionManager()
            _ = [e async for e in sm.process_input("hello")]
            assert sm.get_total_cost() == pytest.approx(0.01)


class TestSessionManagerLoadFromLog:
    def test_load_from_nonexistent_file(self) -> None:
        sm = SessionManager.load_from_log("/nonexistent/path.jsonl")
        assert len(sm.get_messages()) == 0

    def test_load_from_existing_file(self, tmp_path: Any) -> None:
        import json

        log_file = tmp_path / "test.jsonl"
        msg = {"type": "user", "message": "hello from log"}
        log_file.write_text(json.dumps(msg) + "\n")

        sm = SessionManager.load_from_log(str(log_file))
        assert len(sm.get_messages()) == 1


class TestSessionManagerPermission:
    def test_resolve_permission(self) -> None:
        sm = SessionManager()
        sm.resolve_permission(PermissionDecision.ALLOW_ONCE)
        assert sm._last_permission_decision == PermissionDecision.ALLOW_ONCE


import pytest  # noqa: E402
