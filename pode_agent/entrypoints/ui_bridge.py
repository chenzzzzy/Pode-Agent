"""JSON-RPC 2.0 bridge between the Ink UI (Bun) and SessionManager (Python).

This module implements the Python side of the UI bridge:
- Reads JSON-RPC requests from stdin (sent by Bun process)
- Dispatches to SessionManager methods
- Forwards SessionEvent instances as JSON-RPC notifications to stdout

Architecture::

    Bun (Ink UI)  ─── stdin/stdout (JSON-RPC) ───  Python (ui_bridge.py)
                  ◄──────────────────────────────►
                  request/response + notifications

Reference: docs/phases.md — Task 4.1, docs/api-specs.md — JSON-RPC protocol
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import sys
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

from pode_agent.app.session import SessionManager
from pode_agent.core.permissions.types import PermissionDecision
from pode_agent.infra.logging import get_logger
from pode_agent.types.session_events import SessionEvent, SessionEventType

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# JSON-RPC 2.0 helpers
# ---------------------------------------------------------------------------

_JSONRPC_VERSION = "2.0"


class JsonRpcError(Exception):
    """JSON-RPC error with code and message."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.data = data


def _make_response(msg_id: str | int | None, result: Any = None) -> str:
    return json.dumps(
        {"jsonrpc": _JSONRPC_VERSION, "id": msg_id, "result": result}
    )


def _make_error(
    msg_id: str | int | None,
    code: int,
    message: str,
    data: Any = None,
) -> str:
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return json.dumps({"jsonrpc": _JSONRPC_VERSION, "id": msg_id, "error": err})


# ---------------------------------------------------------------------------
# Event → JSON-RPC notification mapping
# ---------------------------------------------------------------------------

# Maps SessionEventType to (json-rpc-method, param-transform)
_EVENT_MAP: dict[
    SessionEventType,
    tuple[str, Callable[[SessionEvent], dict[str, Any]]],
] = {
    SessionEventType.USER_MESSAGE: (
        "session/user_message",
        lambda e: {
            "text": (
                e.data.get("message", {}).get("message", "")
                if isinstance(e.data.get("message"), dict)
                else e.data.get("text", "")
            )
            if e.data
            else "",
            "message_id": e.message_id or "",
        },
    ),
    SessionEventType.ASSISTANT_DELTA: (
        "session/assistant_delta",
        lambda e: {"text": e.data.get("text", "") if e.data else ""},
    ),
    SessionEventType.TOOL_USE_START: (
        "session/tool_use_start",
        lambda e: {
            "tool_name": e.data.get("tool_name", "") if e.data else "",
            "tool_use_id": e.data.get("tool_use_id", "") if e.data else "",
            "tool_input": e.data.get("tool_input", {}) if e.data else {},
        },
    ),
    SessionEventType.TOOL_PROGRESS: (
        "session/tool_progress",
        lambda e: {
            "tool_use_id": e.data.get("tool_use_id", "") if e.data else "",
            "content": e.data.get("content", "") if e.data else "",
        },
    ),
    SessionEventType.TOOL_RESULT: (
        "session/tool_result",
        lambda e: {
            "tool_use_id": e.data.get("tool_use_id", "") if e.data else "",
            "data": e.data.get("result") if e.data else None,
            "is_error": e.data.get("is_error", False) if e.data else False,
        },
    ),
    SessionEventType.PERMISSION_REQUEST: (
        "session/permission_request",
        lambda e: {
            "tool_name": e.data.get("tool_name", "") if e.data else "",
            "tool_input": e.data.get("tool_input", {}) if e.data else {},
            "tool_use_id": e.data.get("tool_use_id", "") if e.data else "",
            "risk_level": e.data.get("risk_level", "medium") if e.data else "medium",
            "description": e.data.get("description") if e.data else None,
        },
    ),
    SessionEventType.COST_UPDATE: (
        "session/cost_update",
        lambda e: {
            "cost_usd": e.data.get("cost_usd", 0.0) if e.data else 0.0,
            "total_usd": e.data.get("total_usd", 0.0) if e.data else 0.0,
            "input_tokens": e.data.get("input_tokens", 0) if e.data else 0,
            "output_tokens": e.data.get("output_tokens", 0) if e.data else 0,
            "total_tokens": e.data.get("total_tokens", 0) if e.data else 0,
            "cumulative_input_tokens": e.data.get("cumulative_input_tokens", 0) if e.data else 0,
            "cumulative_output_tokens": e.data.get("cumulative_output_tokens", 0) if e.data else 0,
            "cumulative_total_tokens": e.data.get("cumulative_total_tokens", 0) if e.data else 0,
            "duration_ms": e.data.get("duration_ms", 0) if e.data else 0,
        },
    ),
    SessionEventType.MODEL_ERROR: (
        "session/model_error",
        lambda e: {
            "error": e.data.get("error", "Unknown error") if e.data else "Unknown error",
            "is_retryable": e.data.get("is_retryable", False) if e.data else False,
        },
    ),
    SessionEventType.DONE: (
        "session/done",
        lambda _e: {},
    ),
    SessionEventType.PLAN_CREATED: (
        "plan/created",
        lambda e: {
            "plan_id": e.data.get("plan_id", "") if e.data else "",
            "objective": e.data.get("objective", "") if e.data else "",
            "steps_count": e.data.get("steps_count", 0) if e.data else 0,
        },
    ),
    SessionEventType.PLAN_APPROVED: (
        "plan/approved",
        lambda e: {"plan_id": e.data.get("plan_id", "") if e.data else ""},
    ),
    SessionEventType.PLAN_STEP_START: (
        "plan/step_start",
        lambda e: {
            "plan_id": e.data.get("plan_id", "") if e.data else "",
            "step_index": e.data.get("step_index", 0) if e.data else 0,
            "step_title": e.data.get("step_title", "") if e.data else "",
        },
    ),
    SessionEventType.PLAN_STEP_DONE: (
        "plan/step_done",
        lambda e: {
            "plan_id": e.data.get("plan_id", "") if e.data else "",
            "step_index": e.data.get("step_index", 0) if e.data else 0,
            "result_summary": e.data.get("result_summary") if e.data else None,
        },
    ),
    SessionEventType.PLAN_DONE: (
        "plan/done",
        lambda e: {"plan_id": e.data.get("plan_id", "") if e.data else ""},
    ),
    SessionEventType.PLAN_CANCELLED: (
        "plan/cancelled",
        lambda e: {
            "plan_id": e.data.get("plan_id", "") if e.data else "",
            "reason": e.data.get("reason") if e.data else None,
        },
    ),
    SessionEventType.SUB_AGENT_STARTED: (
        "sub_agent/started",
        lambda e: {
            "agent_id": e.data.get("agent_id", "") if e.data else "",
            "subagent_type": e.data.get("subagent_type", "") if e.data else "",
            "description": e.data.get("description", "") if e.data else "",
        },
    ),
    SessionEventType.SUB_AGENT_PROGRESS: (
        "sub_agent/progress",
        lambda e: {
            "agent_id": e.data.get("agent_id", "") if e.data else "",
            "tool_use_count": e.data.get("tool_use_count", 0) if e.data else 0,
            "duration_ms": e.data.get("duration_ms", 0) if e.data else 0,
        },
    ),
    SessionEventType.SUB_AGENT_COMPLETED: (
        "sub_agent/completed",
        lambda e: {
            "agent_id": e.data.get("agent_id", "") if e.data else "",
            "subagent_type": e.data.get("subagent_type", "") if e.data else "",
            "description": e.data.get("description", "") if e.data else "",
            "result_text": e.data.get("result_text", "") if e.data else "",
            "tool_use_count": e.data.get("tool_use_count", 0) if e.data else 0,
            "duration_ms": e.data.get("duration_ms", 0) if e.data else 0,
        },
    ),
    SessionEventType.SUB_AGENT_FAILED: (
        "sub_agent/failed",
        lambda e: {
            "agent_id": e.data.get("agent_id", "") if e.data else "",
            "subagent_type": e.data.get("subagent_type", "") if e.data else "",
            "description": e.data.get("description", "") if e.data else "",
            "error": e.data.get("error", "") if e.data else "",
        },
    ),
}


def event_to_notification(event: SessionEvent) -> tuple[str, dict[str, Any]]:
    """Convert a SessionEvent to a (method, params) JSON-RPC notification pair."""
    entry = _EVENT_MAP.get(event.type)
    if entry is None:
        return ("session/unknown", {"type": event.type.value, "data": event.data})
    method, transform = entry
    return (method, transform(event))


# ---------------------------------------------------------------------------
# JsonRpcServer — minimal JSON-RPC 2.0 server
# ---------------------------------------------------------------------------

Handler = Callable[..., Coroutine[Any, Any, Any]]


class JsonRpcServer:
    """Minimal JSON-RPC 2.0 server that reads from stdin, writes to stdout."""

    def __init__(self, write: Callable[[str], None]) -> None:
        self._handlers: dict[str, Handler] = {}
        self._write = write

    def register_method(self, method: str, handler: Handler) -> None:
        self._handlers[method] = handler

    async def handle_line(self, line: str) -> str | None:
        """Parse a JSON-RPC line, dispatch, return response line (or None for notifications)."""
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            return _make_error(None, -32700, "Parse error")

        if not isinstance(payload, dict):
            return _make_error(None, -32600, "Invalid Request")

        if payload.get("jsonrpc") != _JSONRPC_VERSION:
            return _make_error(payload.get("id"), -32600, "Invalid Request")

        has_method = isinstance(payload.get("method"), str)
        has_id = "id" in payload and payload["id"] is not None

        # Incoming response (for our outgoing requests) — ignore
        if not has_method and has_id and ("result" in payload or "error" in payload):
            return None

        if not has_method:
            return _make_error(payload.get("id"), -32600, "Invalid Request")

        method = str(payload["method"])
        params = payload.get("params")
        msg_id = payload.get("id")

        handler = self._handlers.get(method)
        if handler is None:
            if msg_id is None:
                return None  # notification for unknown method
            return _make_error(msg_id, -32601, f"Method not found: {method}")

        # Notification (no id) — fire and forget
        if msg_id is None:
            try:
                await handler(params)
            except Exception:
                logger.exception("Error handling notification %s", method)
            return None

        # Request (has id) — send response
        try:
            result = await handler(params)
            return _make_response(msg_id, result)
        except JsonRpcError as e:
            return _make_error(msg_id, e.code, str(e), e.data)
        except Exception as e:
            logger.exception("Error handling request %s", method)
            return _make_error(msg_id, -32603, str(e))

    def send_notification(self, method: str, params: dict[str, Any] | None = None) -> None:
        """Send a JSON-RPC notification to stdout."""
        msg: dict[str, Any] = {"jsonrpc": _JSONRPC_VERSION, "method": method}
        if params:
            msg["params"] = params
        self._write(json.dumps(msg))


# ---------------------------------------------------------------------------
# UIBridge — connects JsonRpcServer to SessionManager
# ---------------------------------------------------------------------------


class UIBridge:
    """Bridges JSON-RPC requests from Ink UI to SessionManager.

    Args:
        read_stream: Stream to read JSON-RPC from (Bun process stdout).
        write_stream: Stream to write JSON-RPC to (Bun process stdin).

    Usage::

        bridge = UIBridge(read_stream=proc.stdout, write_stream=proc.stdin)
        await bridge.run()
    """

    def __init__(
        self,
        read_stream: asyncio.StreamReader | None = None,
        write_stream: asyncio.StreamWriter | None = None,
    ) -> None:
        self._read_stream = read_stream
        self._write_stream = write_stream
        self._session: SessionManager | None = None
        self._server: JsonRpcServer | None = None

    def _write_line(self, line: str) -> None:
        """Write a JSON-RPC line to the connected stream."""
        if self._write_stream is not None:
            self._write_stream.write((line + "\n").encode("utf-8"))
            # Schedule flush but don't await — fire and forget for notifications
            # Responses are awaited in the calling context
        else:
            sys.stdout.write(line + "\n")
            sys.stdout.flush()

    async def _write_line_async(self, line: str) -> None:
        """Async write a JSON-RPC line to the connected stream."""
        if self._write_stream is not None:
            self._write_stream.write((line + "\n").encode("utf-8"))
            await self._write_stream.drain()
        else:
            sys.stdout.write(line + "\n")
            sys.stdout.flush()

    async def run(self) -> None:
        """Main loop: read from stream, dispatch JSON-RPC, forward events."""
        server = JsonRpcServer(self._write_line)
        self._server = server

        # Register method handlers
        server.register_method("session/submit", self._handle_submit)
        server.register_method("session/abort", self._handle_abort)
        server.register_method(
            "session/resolve_permission", self._handle_resolve_permission
        )
        server.register_method("session/get_messages", self._handle_get_messages)
        server.register_method("session/get_cost", self._handle_get_cost)
        server.register_method("config/get", self._handle_config_get)
        server.register_method("config/set", self._handle_config_set)
        server.register_method("session/list_logs", self._handle_list_logs)
        server.register_method("session/load_log", self._handle_load_log)

        # Set up reader
        if self._read_stream is not None:
            reader = self._read_stream
        else:
            # Fall back to Python's stdin
            reader = asyncio.StreamReader()
            protocol = asyncio.StreamReaderProtocol(reader)
            loop = asyncio.get_event_loop()
            await loop.connect_read_pipe(lambda: protocol, sys.stdin)

        logger.info("UI bridge started, waiting for JSON-RPC")

        # Track background tasks so they can be cleaned up
        pending_tasks: set[asyncio.Task[None]] = set()

        try:
            while True:
                line = await reader.readline()
                if not line:
                    break  # stream closed
                line_str = line.decode("utf-8").strip()
                if not line_str:
                    continue

                # Dispatch concurrently so long-running handlers (e.g. submit)
                # don't block the read loop. This prevents deadlocks when
                # _handle_submit waits for permission and the UI sends
                # resolve_permission on the same connection.
                task = asyncio.create_task(
                    self._dispatch_line(server, line_str)
                )
                pending_tasks.add(task)
                task.add_done_callback(pending_tasks.discard)
        except asyncio.CancelledError:
            pass
        finally:
            # Cancel any still-running dispatch tasks
            for t in pending_tasks:
                t.cancel()
            if pending_tasks:
                await asyncio.gather(*pending_tasks, return_exceptions=True)
            logger.info("UI bridge shutting down")

    async def _dispatch_line(
        self, server: JsonRpcServer, line_str: str
    ) -> None:
        """Dispatch a single JSON-RPC line and write back the response."""
        try:
            response = await server.handle_line(line_str)
            if response:
                await self._write_line_async(response)
        except Exception:
            logger.exception("Error dispatching JSON-RPC line")

    async def _ensure_session(self) -> SessionManager:
        """Lazy-initialize SessionManager on first use."""
        if self._session is None:
            import os
            from pathlib import Path

            from dotenv import load_dotenv

            from pode_agent.core.config.loader import get_global_config
            from pode_agent.core.tools.loader import ToolLoader
            from pode_agent.core.tools.registry import ToolRegistry
            from pode_agent.services.ai.factory import validate_provider_config

            # Ensure .env is loaded (belt-and-suspenders with cli.py)
            load_dotenv(Path.cwd() / ".env")

            config = get_global_config()
            model_name = config.default_model_name

            # Auto-detect model from env if the default model has no API key
            errors = validate_provider_config(model_name, config)
            if errors:
                # Try env-based model fallbacks: DASHSCOPE_MODEL, GLM_MODEL
                for env_key in ("DASHSCOPE_MODEL", "GLM_MODEL"):
                    env_model = os.environ.get(env_key, "").strip()
                    if env_model:
                        alt_errors = validate_provider_config(env_model, config)
                        if not alt_errors:
                            model_name = env_model
                            errors = []
                            logger.info(
                                "Default model unavailable, using %s=%s",
                                env_key, env_model,
                            )
                            break

            if errors:
                raise JsonRpcError(
                    -32001,
                    "LLM provider not configured: " + "; ".join(errors),
                    data={"setup_hints": errors, "model": model_name},
                )

            registry = ToolRegistry()
            loader = ToolLoader(registry, config=config)
            await loader.load_all()
            tools = registry.tools

            self._session = SessionManager(
                tools=tools,
                model=model_name,
            )
        return self._session

    async def _handle_submit(self, params: Any) -> dict[str, Any]:
        """Handle session/submit request."""
        if not isinstance(params, dict):
            raise JsonRpcError(-32602, "Invalid params")
        prompt = params.get("prompt", "")
        if not prompt:
            raise JsonRpcError(-32602, "Missing 'prompt'")

        session = await self._ensure_session()
        assert self._server is not None

        # Process input and forward events as notifications
        try:
            async for event in session.process_input(prompt):
                method, event_params = event_to_notification(event)
                self._server.send_notification(method, event_params)
                # Async flush for notifications
                if self._write_stream is not None:
                    with contextlib.suppress(Exception):
                        await self._write_stream.drain()
        except Exception as exc:
            logger.exception("_handle_submit crashed: %s", exc)
            # Send error + done so the UI is never stuck
            self._server.send_notification(
                "session/model_error",
                {"error": f"Internal error: {exc}", "is_retryable": False},
            )
            self._server.send_notification("session/done", {})
            if self._write_stream is not None:
                with contextlib.suppress(Exception):
                    await self._write_stream.drain()

        return {"message_id": "submitted"}

    async def _handle_abort(self, _params: Any) -> dict[str, Any]:
        """Handle session/abort request."""
        if self._session is not None:
            self._session.abort()
        return {}

    async def _handle_resolve_permission(self, params: Any) -> dict[str, Any]:
        """Handle session/resolve_permission request."""
        if not isinstance(params, dict):
            raise JsonRpcError(-32602, "Invalid params")
        decision_str = params.get("decision", "deny")
        try:
            decision = PermissionDecision(decision_str)
        except ValueError:
            decision = PermissionDecision.DENY

        if self._session is not None:
            self._session.resolve_permission(decision)
        return {}

    async def _handle_get_messages(self, _params: Any) -> dict[str, Any]:
        """Handle session/get_messages request."""
        if self._session is None:
            return {"messages": []}
        return {"messages": self._session.get_messages()}

    async def _handle_get_cost(self, _params: Any) -> dict[str, Any]:
        """Handle session/get_cost request."""
        if self._session is None:
            return {"total_usd": 0.0}
        return {"total_usd": self._session.get_total_cost()}

    async def _handle_config_get(self, params: Any) -> dict[str, Any]:
        """Handle config/get request."""
        from pode_agent.core.config import get_config_for_cli

        if not isinstance(params, dict):
            raise JsonRpcError(-32602, "Invalid params")
        key = params.get("key", "")
        value = get_config_for_cli(key, global_=True)
        return {"value": value}

    async def _handle_config_set(self, params: Any) -> dict[str, Any]:
        """Handle config/set request."""
        from pode_agent.core.config import set_config_for_cli

        if not isinstance(params, dict):
            raise JsonRpcError(-32602, "Invalid params")
        key = params.get("key", "")
        value = params.get("value", "")
        set_config_for_cli(key, value, global_=True)
        return {}

    async def _handle_list_logs(self, _params: Any) -> dict[str, Any]:
        """Handle session/list_logs request."""
        from pode_agent.utils.protocol.session_log import get_session_log_path

        log_dir = get_session_log_path().parent
        if not log_dir.exists():
            return {"logs": []}
        logs = sorted(str(p) for p in log_dir.glob("*.jsonl"))
        return {"logs": logs}

    async def _handle_load_log(self, params: Any) -> dict[str, Any]:
        """Handle session/load_log request."""
        from pode_agent.utils.protocol.session_log import load_messages_from_log

        if not isinstance(params, dict):
            raise JsonRpcError(-32602, "Invalid params")
        log_name = params.get("log_name", "")
        messages = load_messages_from_log(Path(log_name))
        return {"messages": messages}
