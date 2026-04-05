"""Tests for app/session.py — Phase 2 SessionManager features.

Tests process_input(), cost tracking, permission resolution, and log restoration.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from pode_agent.app.session import SessionManager
from pode_agent.core.permissions.types import PermissionDecision
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

    def test_usage_totals_start_at_zero(self) -> None:
        sm = SessionManager()
        assert sm.get_usage_totals() == {
            "cumulative_input_tokens": 0,
            "cumulative_output_tokens": 0,
            "cumulative_total_tokens": 0,
        }

    def test_add_usage_accumulates(self) -> None:
        sm = SessionManager()
        sm.add_usage(120, 45)
        sm.add_usage(30, 5)
        assert sm.get_usage_totals() == {
            "cumulative_input_tokens": 150,
            "cumulative_output_tokens": 50,
            "cumulative_total_tokens": 200,
        }


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
            SessionEvent(
                type=SessionEventType.COST_UPDATE,
                data={
                    "cost_usd": 0.01,
                    "input_tokens": 100,
                    "output_tokens": 20,
                    "total_tokens": 120,
                    "duration_ms": 1500,
                },
            ),
            SessionEvent(type=SessionEventType.DONE, data={}),
        ]

        async def mock_query(*args: Any, **kwargs: Any) -> Any:
            for ev in events_sequence:
                yield ev

        with patch("pode_agent.app.session.query", side_effect=mock_query):
            sm = SessionManager()
            yielded = [e async for e in sm.process_input("hello")]
            assert sm.get_total_cost() == pytest.approx(0.01)
            assert sm.get_usage_totals() == {
                "cumulative_input_tokens": 100,
                "cumulative_output_tokens": 20,
                "cumulative_total_tokens": 120,
            }
            usage_event = next(e for e in yielded if e.type == SessionEventType.COST_UPDATE)
            assert usage_event.data["total_usd"] == pytest.approx(0.01)
            assert usage_event.data["cumulative_total_tokens"] == 120
            assert usage_event.data["duration_ms"] == 1500

    async def test_cost_update_has_full_payload(self) -> None:
        """COST_UPDATE should contain all required fields for UI consumption."""
        events_sequence = [
            SessionEvent(
                type=SessionEventType.COST_UPDATE,
                data={
                    "cost_usd": 0.005,
                    "input_tokens": 200,
                    "output_tokens": 50,
                    "total_tokens": 250,
                    "duration_ms": 800,
                },
            ),
            SessionEvent(type=SessionEventType.DONE, data={}),
        ]

        async def mock_query(*args: Any, **kwargs: Any) -> Any:
            for ev in events_sequence:
                yield ev

        with patch("pode_agent.app.session.query", side_effect=mock_query):
            sm = SessionManager()
            yielded = [e async for e in sm.process_input("hello")]
            cost_events = [e for e in yielded if e.type == SessionEventType.COST_UPDATE]
            assert len(cost_events) == 1
            d = cost_events[0].data
            # All required fields must exist
            for key in [
                "cost_usd", "total_usd",
                "input_tokens", "output_tokens", "total_tokens",
                "cumulative_input_tokens", "cumulative_output_tokens", "cumulative_total_tokens",
                "duration_ms",
            ]:
                assert key in d, f"Missing key: {key}"
            assert d["input_tokens"] == 200
            assert d["output_tokens"] == 50
            assert d["total_tokens"] == 250
            assert d["cumulative_input_tokens"] == 200
            assert d["cumulative_output_tokens"] == 50
            assert d["cumulative_total_tokens"] == 250
            assert d["duration_ms"] == 800


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

    def test_load_from_log_reuses_same_log_file_for_writes(self, tmp_path: Any) -> None:
        import json

        log_file = tmp_path / "resume.jsonl"
        log_file.write_text(json.dumps({"type": "user", "message": "hello"}) + "\n")

        sm = SessionManager.load_from_log(str(log_file))
        sm.replace_messages([{"type": "assistant", "message": "summary"}])

        lines = [line for line in log_file.read_text().splitlines() if line]
        assert len(lines) == 1
        assert json.loads(lines[0])["message"] == "summary"


class TestSessionManagerPermission:
    def test_resolve_permission(self) -> None:
        sm = SessionManager()
        sm.resolve_permission(PermissionDecision.ALLOW_ONCE)
        assert sm._last_permission_decision == PermissionDecision.ALLOW_ONCE
