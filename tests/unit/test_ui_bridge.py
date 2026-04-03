"""Tests for UI bridge JSON-RPC server and event mapping.

Reference: docs/testing-strategy.md — tests/unit/entrypoints/test_ui_bridge.py
"""

from __future__ import annotations

import asyncio
import json
from io import StringIO
from typing import Any
from unittest.mock import MagicMock

import pytest

from pode_agent.entrypoints.ui_bridge import (
    JsonRpcError,
    JsonRpcServer,
    UIBridge,
    _make_error,
    _make_response,
    event_to_notification,
)
from pode_agent.types.session_events import SessionEvent, SessionEventType


# --- JSON-RPC helpers ---


class TestMakeResponse:
    def test_basic_response(self) -> None:
        result = _make_response(1, {"status": "ok"})
        parsed = json.loads(result)
        assert parsed["jsonrpc"] == "2.0"
        assert parsed["id"] == 1
        assert parsed["result"] == {"status": "ok"}

    def test_null_id(self) -> None:
        result = _make_response(None, "hello")
        parsed = json.loads(result)
        assert parsed["id"] is None
        assert parsed["result"] == "hello"


class TestMakeError:
    def test_basic_error(self) -> None:
        result = _make_error(1, -32600, "Invalid Request")
        parsed = json.loads(result)
        assert parsed["jsonrpc"] == "2.0"
        assert parsed["id"] == 1
        assert parsed["error"]["code"] == -32600
        assert parsed["error"]["message"] == "Invalid Request"

    def test_error_with_data(self) -> None:
        result = _make_error(2, -32602, "Bad params", {"field": "prompt"})
        parsed = json.loads(result)
        assert parsed["error"]["data"] == {"field": "prompt"}


# --- JSON-RPC Server ---


class TestJsonRpcServer:
    def test_register_and_handle_request(self) -> None:
        lines: list[str] = []
        server = JsonRpcServer(lambda line: lines.append(line))

        async def echo_handler(params: Any) -> Any:
            return params

        server.register_method("echo", echo_handler)

        request = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "echo", "params": {"msg": "hi"}})
        response = asyncio.run(server.handle_line(request))
        assert response is not None
        parsed = json.loads(response)
        assert parsed["result"] == {"msg": "hi"}

    def test_method_not_found(self) -> None:
        lines: list[str] = []
        server = JsonRpcServer(lambda line: lines.append(line))

        request = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "nonexistent"})
        response = asyncio.run(server.handle_line(request))
        assert response is not None
        parsed = json.loads(response)
        assert parsed["error"]["code"] == -32601

    def test_invalid_json(self) -> None:
        lines: list[str] = []
        server = JsonRpcServer(lambda line: lines.append(line))

        response = asyncio.run(server.handle_line("not json"))
        assert response is not None
        parsed = json.loads(response)
        assert parsed["error"]["code"] == -32700

    def test_notification_no_response(self) -> None:
        lines: list[str] = []
        server = JsonRpcServer(lambda line: lines.append(line))

        called = False

        async def handler(params: Any) -> None:
            nonlocal called
            called = True

        server.register_method("test_notify", handler)

        request = json.dumps({"jsonrpc": "2.0", "method": "test_notify", "params": {"x": 1}})
        response = asyncio.run(server.handle_line(request))
        assert response is None
        assert called

    def test_send_notification(self) -> None:
        lines: list[str] = []
        server = JsonRpcServer(lambda line: lines.append(line))
        server.send_notification("session/done", {})
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["method"] == "session/done"
        assert "id" not in parsed


# --- Event to notification mapping ---


class TestEventToNotification:
    def test_assistant_delta(self) -> None:
        event = SessionEvent(
            type=SessionEventType.ASSISTANT_DELTA,
            data={"text": "Hello world"},
        )
        method, params = event_to_notification(event)
        assert method == "session/assistant_delta"
        assert params["text"] == "Hello world"

    def test_tool_use_start(self) -> None:
        event = SessionEvent(
            type=SessionEventType.TOOL_USE_START,
            data={
                "tool_name": "Bash",
                "tool_use_id": "tool_123",
                "tool_input": {"command": "ls"},
            },
        )
        method, params = event_to_notification(event)
        assert method == "session/tool_use_start"
        assert params["tool_name"] == "Bash"
        assert params["tool_use_id"] == "tool_123"
        assert params["tool_input"] == {"command": "ls"}

    def test_permission_request(self) -> None:
        event = SessionEvent(
            type=SessionEventType.PERMISSION_REQUEST,
            data={
                "tool_name": "FileEdit",
                "tool_input": {"file_path": "/tmp/test.py"},
                "tool_use_id": "tool_456",
                "risk_level": "high",
            },
        )
        method, params = event_to_notification(event)
        assert method == "session/permission_request"
        assert params["tool_name"] == "FileEdit"
        assert params["risk_level"] == "high"

    def test_done(self) -> None:
        event = SessionEvent(type=SessionEventType.DONE)
        method, params = event_to_notification(event)
        assert method == "session/done"
        assert params == {}

    def test_plan_created(self) -> None:
        event = SessionEvent(
            type=SessionEventType.PLAN_CREATED,
            data={
                "plan_id": "plan_1",
                "objective": "Refactor auth",
                "steps_count": 5,
            },
        )
        method, params = event_to_notification(event)
        assert method == "plan/created"
        assert params["plan_id"] == "plan_1"
        assert params["steps_count"] == 5

    def test_unknown_event(self) -> None:
        event = SessionEvent(type=SessionEventType.DONE)
        event.type = SessionEventType.COST_UPDATE  # known but let's check it works
        event.data = {"cost_usd": 0.01, "total_usd": 0.05}
        method, params = event_to_notification(event)
        assert method == "session/cost_update"
        assert params["cost_usd"] == 0.01
        assert params["total_usd"] == 0.05


# --- _ensure_session ToolLoader integration (Fix 1) ---


class TestEnsureSessionToolLoading:
    def test_ensure_session_loads_all_tools(self) -> None:
        """_ensure_session() should create ToolLoader and call load_all."""
        from unittest.mock import AsyncMock, patch

        mock_loader = MagicMock()
        mock_loader.load_all = AsyncMock()
        mock_registry = MagicMock()
        mock_registry.tools = []

        with (
            patch(
                "pode_agent.core.tools.registry.ToolRegistry",
                return_value=mock_registry,
            ),
            patch(
                "pode_agent.core.tools.loader.ToolLoader",
                return_value=mock_loader,
            ),
            patch(
                "pode_agent.core.config.loader.get_global_config",
                return_value=MagicMock(default_model_name="test-model"),
            ),
            patch(
                "pode_agent.services.ai.factory.validate_provider_config",
                return_value=[],  # Skip validation in tool-loading test
            ),
        ):
            bridge = UIBridge.__new__(UIBridge)
            bridge._session = None
            bridge._read_stream = None
            bridge._write_stream = None
            bridge._server = None

            session = asyncio.run(bridge._ensure_session())

            mock_loader.load_all.assert_called_once()
            assert session is not None
