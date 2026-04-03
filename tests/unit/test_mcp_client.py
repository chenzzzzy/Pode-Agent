"""Tests for services/mcp/ — MCP client and tool wrapping.

All tests mock subprocess/HTTP — no real MCP server connections.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pode_agent.core.config.schema import McpServerConfig
from pode_agent.services.mcp.client import (
    McpClient,
    McpToolCallResult,
    McpToolDefinition,
    WrappedMcpClient,
    connect_all_mcp_servers,
    connect_mcp_server,
)
from pode_agent.services.mcp.tools import (
    _build_input_schema,
    _mcp_tool_name,
    wrap_mcp_tool_as_pode_tool,
)


# ---------------------------------------------------------------------------
# McpToolDefinition
# ---------------------------------------------------------------------------


class TestMcpToolDefinition:
    def test_basic(self) -> None:
        d = McpToolDefinition(name="search", description="Search things")
        assert d.name == "search"
        assert d.input_schema == {}

    def test_with_schema(self) -> None:
        d = McpToolDefinition(
            name="search",
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        )
        assert "query" in d.input_schema["properties"]


class TestMcpToolCallResult:
    def test_success(self) -> None:
        r = McpToolCallResult(content="found 3 items")
        assert not r.is_error

    def test_error(self) -> None:
        r = McpToolCallResult(content="failed", is_error=True)
        assert r.is_error


# ---------------------------------------------------------------------------
# McpClient
# ---------------------------------------------------------------------------


class TestMcpClient:
    def test_initial_state(self) -> None:
        client = McpClient("test-server")
        assert client.name == "test-server"
        assert not client.is_connected

    async def test_connect_stdio_no_command(self) -> None:
        client = McpClient("test")
        config = McpServerConfig(type="stdio")
        with pytest.raises(ValueError, match="stdio requires"):
            await client.connect_stdio(config)

    async def test_connect_stdio_success(self) -> None:
        client = McpClient("test")
        config = McpServerConfig(type="stdio", command="echo", args=[])

        with patch("pode_agent.services.mcp.client.asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.stdin = AsyncMock()
            mock_proc.stdout = AsyncMock()
            mock_proc.stdout.readline = AsyncMock(
                return_value=json.dumps({"status": "ok"}).encode() + b"\n",
            )
            mock_exec.return_value = mock_proc

            await client.connect_stdio(config)
            assert client.is_connected

    async def test_connect_stdio_failure(self) -> None:
        client = McpClient("test")
        config = McpServerConfig(type="stdio", command="nonexistent")

        with patch(
            "pode_agent.services.mcp.client.asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("not found"),
        ):
            with pytest.raises(FileNotFoundError):
                await client.connect_stdio(config)
            assert not client.is_connected

    async def test_connect_sse_no_url(self) -> None:
        client = McpClient("test")
        config = McpServerConfig(type="sse")
        with pytest.raises(ValueError, match="SSE requires"):
            await client.connect_sse(config)

    async def test_connect_http_no_url(self) -> None:
        client = McpClient("test")
        config = McpServerConfig(type="http")
        with pytest.raises(ValueError, match="HTTP requires"):
            await client.connect_http(config)

    async def test_connect_sse_placeholder(self) -> None:
        client = McpClient("test")
        config = McpServerConfig(type="sse", url="http://localhost:3000")
        await client.connect_sse(config)
        assert client.is_connected

    async def test_connect_http_placeholder(self) -> None:
        client = McpClient("test")
        config = McpServerConfig(type="http", url="http://localhost:3000")
        await client.connect_http(config)
        assert client.is_connected

    async def test_list_tools_not_connected(self) -> None:
        client = McpClient("test")
        tools = await client.list_tools()
        assert tools == []

    async def test_call_tool_not_connected(self) -> None:
        client = McpClient("test")
        result = await client.call_tool("search", {"q": "hello"})
        assert result.is_error
        assert "Not connected" in result.content

    async def test_list_resources_not_connected(self) -> None:
        client = McpClient("test")
        resources = await client.list_resources()
        assert resources == []

    async def test_read_resource_not_connected(self) -> None:
        client = McpClient("test")
        result = await client.read_resource("file:///test.txt")
        assert result == {}

    async def test_close_no_process(self) -> None:
        client = McpClient("test")
        await client.close()  # Should not raise


# ---------------------------------------------------------------------------
# WrappedMcpClient
# ---------------------------------------------------------------------------


class TestWrappedMcpClient:
    def test_connected(self) -> None:
        client = McpClient("test")
        client._connected = True
        wrapped = WrappedMcpClient(name="test", client=client)
        assert wrapped.is_connected

    def test_failed(self) -> None:
        wrapped = WrappedMcpClient(name="test", error="Connection refused")
        assert not wrapped.is_connected
        assert wrapped.error == "Connection refused"

    def test_none_client(self) -> None:
        wrapped = WrappedMcpClient(name="test")
        assert not wrapped.is_connected


# ---------------------------------------------------------------------------
# connect_mcp_server
# ---------------------------------------------------------------------------


class TestConnectMcpServer:
    async def test_unsupported_transport(self) -> None:
        config = McpServerConfig(type="ws", url="http://localhost:3000")
        wrapped = await connect_mcp_server("test", config)
        # ws maps to connect_http, which is a placeholder
        assert wrapped.is_connected  # placeholder HTTP connects

    async def test_stdio_connect(self) -> None:
        config = McpServerConfig(type="stdio", command="echo")
        with patch("pode_agent.services.mcp.client.asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.stdin = AsyncMock()
            mock_proc.stdout = AsyncMock()
            mock_proc.stdout.readline = AsyncMock(
                return_value=json.dumps({"status": "ok"}).encode() + b"\n",
            )
            mock_exec.return_value = mock_proc

            wrapped = await connect_mcp_server("test", config)
            assert wrapped.is_connected

    async def test_connection_failure(self) -> None:
        config = McpServerConfig(type="stdio", command="nonexistent")
        with patch(
            "pode_agent.services.mcp.client.asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError,
        ):
            wrapped = await connect_mcp_server("test", config)
            assert not wrapped.is_connected
            assert wrapped.error is not None


class TestConnectAllMcpServers:
    async def test_empty(self) -> None:
        results = await connect_all_mcp_servers({})
        assert results == []

    async def test_multiple(self) -> None:
        servers = {
            "s1": McpServerConfig(type="http", url="http://localhost:3001"),
            "s2": McpServerConfig(type="http", url="http://localhost:3002"),
        }
        results = await connect_all_mcp_servers(servers)
        assert len(results) == 2


# ---------------------------------------------------------------------------
# Tool wrapping
# ---------------------------------------------------------------------------


class TestMcpToolName:
    def test_naming(self) -> None:
        assert _mcp_tool_name("my-server", "search") == "mcp__my-server__search"


class TestBuildInputSchema:
    def test_empty_schema(self) -> None:
        defn = McpToolDefinition(name="test")
        schema_cls = _build_input_schema(defn)
        instance = schema_cls()
        assert instance.model_dump() == {}

    def test_with_properties(self) -> None:
        defn = McpToolDefinition(
            name="test",
            input_schema={
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["query"],
            },
        )
        schema_cls = _build_input_schema(defn)
        instance = schema_cls(query="hello")
        data = instance.model_dump()
        assert data["query"] == "hello"
        assert data["limit"] == 10


class TestWrapMcpTool:
    async def test_wrapped_tool_name(self) -> None:
        client = McpClient("test-server")
        defn = McpToolDefinition(name="search", description="Search things")
        tool = wrap_mcp_tool_as_pode_tool(client, "test-server", defn)
        assert tool.name == "mcp__test-server__search"
        assert "Search things" in tool.description

    async def test_wrapped_tool_call(self) -> None:
        client = McpClient("test-server")
        defn = McpToolDefinition(name="search", description="Search")
        tool = wrap_mcp_tool_as_pode_tool(client, "test-server", defn)

        # Mock call_tool
        client.call_tool = AsyncMock(  # type: ignore[method-assign]
            return_value=McpToolCallResult(content="found 3 items"),
        )

        schema_cls = tool.input_schema()
        input_model = schema_cls()
        context = MagicMock()

        results = []
        async for output in tool.call(input_model, context):
            results.append(output)

        assert len(results) == 1
        assert results[0].type == "result"
        assert results[0].result_for_assistant == "found 3 items"

    async def test_wrapped_tool_permissions(self) -> None:
        client = McpClient("test-server")
        defn = McpToolDefinition(name="danger")
        tool = wrap_mcp_tool_as_pode_tool(client, "test-server", defn)

        # Conservative: not read-only, needs permissions
        assert not tool.is_read_only()
        assert tool.needs_permissions()

    async def test_wrapped_tool_enabled(self) -> None:
        client = McpClient("test-server")
        defn = McpToolDefinition(name="test")
        tool = wrap_mcp_tool_as_pode_tool(client, "test-server", defn)
        assert await tool.is_enabled()
