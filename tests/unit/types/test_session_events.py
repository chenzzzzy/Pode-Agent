"""Tests for types/session_events.py — session event types."""

from __future__ import annotations

from pode_agent.types.session_events import (
    PermissionRequestData,
    SessionEvent,
    SessionEventType,
)


class TestSessionEventType:
    def test_enum_values(self) -> None:
        assert SessionEventType.USER_MESSAGE == "user_message"
        assert SessionEventType.ASSISTANT_DELTA == "assistant_delta"
        assert SessionEventType.TOOL_USE_START == "tool_use_start"
        assert SessionEventType.TOOL_PROGRESS == "tool_progress"
        assert SessionEventType.TOOL_RESULT == "tool_result"
        assert SessionEventType.PERMISSION_REQUEST == "permission_request"
        assert SessionEventType.COST_UPDATE == "cost_update"
        assert SessionEventType.MODEL_ERROR == "model_error"
        assert SessionEventType.DONE == "done"

    def test_all_values(self) -> None:
        expected = {
            "user_message", "assistant_delta", "tool_use_start",
            "tool_progress", "tool_result", "permission_request",
            "cost_update", "model_error", "done",
        }
        actual = {e.value for e in SessionEventType}
        assert actual == expected


class TestSessionEvent:
    def test_construction(self) -> None:
        event = SessionEvent(type=SessionEventType.USER_MESSAGE, data="hello")
        assert event.type == SessionEventType.USER_MESSAGE
        assert event.data == "hello"
        assert event.message_id is None

    def test_with_message_id(self) -> None:
        event = SessionEvent(
            type=SessionEventType.ASSISTANT_DELTA,
            data="text chunk",
            message_id="msg_001",
        )
        assert event.message_id == "msg_001"

    def test_defaults(self) -> None:
        event = SessionEvent(type=SessionEventType.DONE)
        assert event.data is None
        assert event.message_id is None


class TestPermissionRequestData:
    def test_construction(self) -> None:
        data = PermissionRequestData(
            tool_name="bash",
            tool_input={"command": "rm -rf /"},
        )
        assert data.tool_name == "bash"
        assert data.risk_level == "medium"
        assert data.description is None

    def test_custom_risk_level(self) -> None:
        data = PermissionRequestData(
            tool_name="file_write",
            tool_input={"file_path": "/etc/passwd"},
            risk_level="high",
            description="Writing to system file",
        )
        assert data.risk_level == "high"
        assert data.description == "Writing to system file"
