"""ACP Server — Agent Communication Protocol over JSON-RPC stdio.

Provides an IDE-integration endpoint that wraps Pode-Agent's session
manager behind a clean JSON-RPC interface.

Usage::

    pode-acp

Reference: docs/acp-protocol.md — ACP Protocol Specification
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from pydantic import BaseModel

from pode_agent.infra.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Protocol types
# ---------------------------------------------------------------------------


class AcpRequest(BaseModel):
    """An incoming ACP JSON-RPC request."""

    jsonrpc: str = "2.0"
    id: int | str | None = None
    method: str
    params: dict[str, Any] = {}


class AcpResponse(BaseModel):
    """An outgoing ACP JSON-RPC response."""

    jsonrpc: str = "2.0"
    id: int | str | None = None
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Server implementation
# ---------------------------------------------------------------------------


class AcpServer:
    """ACP protocol server — manages sessions via JSON-RPC over stdio."""

    def __init__(self) -> None:
        self._sessions: dict[str, Any] = {}
        self._running = False

    async def handle_request(self, request: AcpRequest) -> AcpResponse:
        """Dispatch a JSON-RPC request to the appropriate handler."""
        method = request.method
        handlers: dict[str, Any] = {
            "initialize": self._handle_initialize,
            "session/new": self._handle_session_new,
            "session/prompt": self._handle_session_prompt,
            "session/cancel": self._handle_session_cancel,
            "session/request_permission": self._handle_permission,
        }

        handler = handlers.get(method)
        if handler is None:
            return AcpResponse(
                id=request.id,
                error={"code": -32601, "message": f"Method not found: {method}"},
            )

        try:
            result = await handler(request.params)
            return AcpResponse(id=request.id, result=result)
        except Exception as e:
            logger.exception("ACP handler error for %s", method)
            return AcpResponse(
                id=request.id,
                error={"code": -32603, "message": str(e)},
            )

    async def _handle_initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle ``initialize`` request."""
        return {
            "protocolVersion": "0.1.0",
            "capabilities": {
                "sessions": True,
                "streaming": True,
                "permissions": True,
            },
            "serverInfo": {"name": "pode-agent", "version": "0.1.0"},
        }

    async def _handle_session_new(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle ``session/new`` — create a new session."""
        import uuid

        session_id = str(uuid.uuid4())
        # Session will be lazily initialized on first prompt
        self._sessions[session_id] = {"id": session_id, "messages": []}

        return {
            "sessionId": session_id,
            "status": "ready",
        }

    async def _handle_session_prompt(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle ``session/prompt`` — process user input."""
        session_id = params.get("sessionId")
        prompt = params.get("prompt", "")

        if not session_id or session_id not in self._sessions:
            return {"error": "Session not found"}

        # For now, return a placeholder response
        # Full integration will delegate to SessionManager.process_input()
        return {
            "sessionId": session_id,
            "status": "processing",
            "message": f"Received: {prompt[:100]}",
        }

    async def _handle_session_cancel(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle ``session/cancel`` — abort current operation."""
        session_id = params.get("sessionId")
        if session_id and session_id in self._sessions:
            # Signal abort via session's event
            return {"sessionId": session_id, "status": "cancelled"}
        return {"error": "Session not found"}

    async def _handle_permission(self, params: dict[str, Any]) -> dict[str, Any]:
        """Handle ``session/request_permission`` — permission response."""
        session_id = params.get("sessionId")
        decision = params.get("decision", "deny")
        return {"sessionId": session_id, "decision": decision}


async def run_acp_server() -> None:
    """Start the ACP server on stdio."""
    server = AcpServer()
    logger.info("ACP server starting")

    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)

    writer_transport, writer_protocol = await asyncio.get_event_loop().connect_write_pipe(
        asyncio.streams.FlowControlMixin, sys.stdout,
    )
    writer = asyncio.StreamWriter(writer_transport, writer_protocol, reader, asyncio.get_event_loop())

    while True:
        line = await reader.readline()
        if not line:
            break

        try:
            request = AcpRequest(**json.loads(line.decode()))
            response = await server.handle_request(request)
            writer.write((response.model_dump_json(exclude_none=True) + "\n").encode())
            await writer.drain()
        except json.JSONDecodeError:
            logger.warning("Invalid JSON received")
        except Exception:
            logger.exception("ACP server error")


def main() -> None:
    """Entry point for ``pode-acp`` console script."""
    asyncio.run(run_acp_server())
