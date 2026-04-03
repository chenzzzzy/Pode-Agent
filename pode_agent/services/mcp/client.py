"""MCP client — connects to MCP servers via stdio/SSE/HTTP.

Manages the lifecycle of connections to one or more MCP servers,
discovers their tools and resources, and provides a unified interface
for calling them.

Reference: docs/mcp-system.md — MCP Client Architecture
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any

from pydantic import BaseModel

from pode_agent.core.config.schema import McpServerConfig
from pode_agent.infra.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# MCP tool / resource definitions (returned by MCP servers)
# ---------------------------------------------------------------------------


class McpToolParameter(BaseModel):
    """A single parameter in an MCP tool's input schema."""

    name: str
    type: str = "string"
    description: str | None = None
    required: bool = False


class McpToolDefinition(BaseModel):
    """Tool definition as reported by an MCP server."""

    name: str
    description: str | None = None
    input_schema: dict[str, Any] = {}


class McpToolCallResult(BaseModel):
    """Result from calling an MCP tool."""

    content: str | list[dict[str, Any]] = ""
    is_error: bool = False


# ---------------------------------------------------------------------------
# Connected client (actual MCP connection)
# ---------------------------------------------------------------------------


class McpClient:
    """Manages a connection to a single MCP server.

    Supports three transport modes:
    - **stdio**: spawns a child process and communicates over stdin/stdout
    - **sse**: connects via Server-Sent Events (HTTP streaming)
    - **http**: standard HTTP request/response

    Usage::

        client = McpClient(name="my-server")
        await client.connect_stdio(config)
        tools = await client.list_tools()
        result = await client.call_tool("search", {"query": "hello"})
        await client.close()
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self._process: asyncio.subprocess.Process | None = None
        self._connected = False
        self._tools_cache: list[McpToolDefinition] = []
        self._request_id = 0

    @property
    def is_connected(self) -> bool:
        return self._connected

    # --- Transport: stdio ---

    async def connect_stdio(self, config: McpServerConfig) -> None:
        """Connect to an MCP server by spawning a child process."""
        if not config.command:
            raise ValueError(f"MCP server '{self.name}': stdio requires 'command'")

        try:
            self._process = await asyncio.create_subprocess_exec(
                config.command,
                *config.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**_default_env(), **config.env},
            )
            self._connected = True
            logger.info("MCP server '%s' connected via stdio: %s", self.name, config.command)

            # Initialize the server
            await self._send_initialize()

        except Exception:
            logger.exception("Failed to connect MCP server '%s' via stdio", self.name)
            self._connected = False
            raise

    # --- Transport: SSE / HTTP ---

    async def connect_sse(self, config: McpServerConfig) -> None:
        """Connect to an MCP server via SSE (placeholder for Phase 5)."""
        if not config.url:
            raise ValueError(f"MCP server '{self.name}': SSE requires 'url'")
        # SSE transport will use httpx for streaming
        self._connected = True
        logger.info("MCP server '%s' connected via SSE to %s", self.name, config.url)
        await self._send_initialize()

    async def connect_http(self, config: McpServerConfig) -> None:
        """Connect to an MCP server via HTTP (placeholder for Phase 5)."""
        if not config.url:
            raise ValueError(f"MCP server '{self.name}': HTTP requires 'url'")
        self._connected = True
        logger.info("MCP server '%s' connected via HTTP to %s", self.name, config.url)
        await self._send_initialize()

    # --- Protocol methods ---

    async def list_tools(self) -> list[McpToolDefinition]:
        """Discover tools exposed by the MCP server."""
        if not self._connected:
            return []

        try:
            response = await self._send_request("tools/list", {})
            tools_raw = response.get("tools", [])
            self._tools_cache = [McpToolDefinition(**t) for t in tools_raw]
            return self._tools_cache
        except Exception:
            logger.exception("Failed to list tools from MCP server '%s'", self.name)
            return []

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> McpToolCallResult:
        """Call a tool on the MCP server."""
        if not self._connected:
            return McpToolCallResult(content="Not connected", is_error=True)

        try:
            response = await self._send_request("tools/call", {
                "name": name,
                "arguments": arguments,
            })
            content = response.get("content", "")
            is_error = response.get("isError", False)
            return McpToolCallResult(content=content, is_error=is_error)
        except Exception as e:
            logger.exception("Failed to call tool '%s' on MCP server '%s'", name, self.name)
            return McpToolCallResult(content=str(e), is_error=True)

    async def list_resources(self) -> list[dict[str, Any]]:
        """Discover resources exposed by the MCP server."""
        if not self._connected:
            return []
        try:
            response = await self._send_request("resources/list", {})
            return response.get("resources", [])  # type: ignore[no-any-return]
        except Exception:
            logger.exception("Failed to list resources from MCP server '%s'", self.name)
            return []

    async def read_resource(self, uri: str) -> dict[str, Any]:
        """Read a resource from the MCP server."""
        if not self._connected:
            return {}
        try:
            return await self._send_request("resources/read", {"uri": uri})
        except Exception:
            logger.exception("Failed to read resource '%s' from MCP server '%s'", uri, self.name)
            return {}

    async def close(self) -> None:
        """Close the connection to the MCP server."""
        if self._process is not None:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except Exception:
                with contextlib.suppress(Exception):
                    self._process.kill()
            self._process = None
        self._connected = False
        logger.info("MCP server '%s' disconnected", self.name)

    # --- Internal JSON-RPC ---

    async def _send_initialize(self) -> None:
        """Send the MCP initialize request."""
        await self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "pode-agent", "version": "0.1.0"},
        })

    async def _send_request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send a JSON-RPC request and return the response."""
        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }

        if self._process is not None:
            return await self._stdio_request(request)
        # SSE/HTTP: placeholder
        return {}

    async def _stdio_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Send a JSON-RPC request via stdio and read the response."""
        if not self._process or not self._process.stdin or not self._process.stdout:
            return {}

        data = json.dumps(request) + "\n"
        self._process.stdin.write(data.encode())
        await self._process.stdin.drain()

        # Read response line
        response_line = await self._process.stdout.readline()
        if not response_line:
            return {}

        return json.loads(response_line.decode())  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Wrapped client — discriminated union: Connected | Failed
# ---------------------------------------------------------------------------


class WrappedMcpClient:
    """Wraps an MCP client connection result — either connected or failed.

    Used by the tool loader to handle connection failures gracefully.
    """

    def __init__(
        self,
        name: str,
        client: McpClient | None = None,
        error: str | None = None,
    ) -> None:
        self.name = name
        self.client = client
        self.error = error

    @property
    def is_connected(self) -> bool:
        return self.client is not None and self.client.is_connected


# ---------------------------------------------------------------------------
# Connection factory
# ---------------------------------------------------------------------------


async def connect_mcp_server(
    name: str, config: McpServerConfig,
) -> WrappedMcpClient:
    """Connect to a single MCP server based on its config type.

    Returns a ``WrappedMcpClient`` that captures either the connected client
    or the error message.
    """
    client = McpClient(name=name)

    try:
        if config.type == "stdio":
            await client.connect_stdio(config)
        elif config.type == "sse" or config.type == "sse-ide":
            await client.connect_sse(config)
        elif config.type in ("http", "ws", "ws-ide"):
            await client.connect_http(config)
        else:
            return WrappedMcpClient(name=name, error=f"Unsupported transport: {config.type}")

        return WrappedMcpClient(name=name, client=client)

    except Exception as e:
        logger.warning("MCP server '%s' connection failed: %s", name, e)
        return WrappedMcpClient(name=name, error=str(e))


async def connect_all_mcp_servers(
    servers: dict[str, McpServerConfig],
) -> list[WrappedMcpClient]:
    """Connect to all configured MCP servers in parallel."""
    tasks = [connect_mcp_server(name, config) for name, config in servers.items()]
    if not tasks:
        return []
    return list(await asyncio.gather(*tasks))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _default_env() -> dict[str, str]:
    """Get a clean environment dict for subprocess spawning."""
    import os
    return dict(os.environ)
