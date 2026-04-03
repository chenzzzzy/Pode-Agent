"""MCP Server mode — expose all Pode tools as MCP tools.

Runs as an MCP server (stdio transport), allowing external tools
and IDEs to discover and call Pode-Agent tools via the MCP protocol.

Usage::

    pode-mcp

Reference: docs/mcp-system.md — MCP Server Mode
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from pode_agent.core.tools.base import Tool as PodeTool
from pode_agent.infra.logging import get_logger

logger = get_logger(__name__)


async def run_mcp_server() -> None:
    """Start the MCP server on stdio.

    Implements the MCP protocol:
    - ``initialize`` → return server capabilities
    - ``tools/list`` → return all registered tools
    - ``tools/call`` → execute a tool and return result
    """
    from pode_agent.core.tools.base import ToolOptions, ToolUseContext
    from pode_agent.core.tools.executor import collect_tool_result
    from pode_agent.core.tools.loader import ToolLoader
    from pode_agent.core.tools.registry import ToolRegistry

    # Load all tools
    registry = ToolRegistry()
    loader = ToolLoader(registry)
    await loader.load_all()

    logger.info("MCP server started with %d tools", len(registry.tools))

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
            request = json.loads(line.decode())
            request_id = request.get("id")
            method = request.get("method", "")
            params = request.get("params", {})

            response: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id}

            if method == "initialize":
                response["result"] = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "pode-agent", "version": "0.1.0"},
                }

            elif method == "tools/list":
                tools_list = []
                for t in registry.tools:
                    if await t.is_enabled():
                        tools_list.append({
                            "name": t.name,
                            "description": t.description or "",
                            "inputSchema": t.input_schema().model_json_schema(),
                        })
                response["result"] = {"tools": tools_list}

            elif method == "tools/call":
                tool_name = params.get("name", "")
                arguments = params.get("arguments", {})

                tool: PodeTool | None = registry.get_tool_by_name(tool_name)
                if tool is None:
                    response["result"] = {
                        "content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}],
                        "isError": True,
                    }
                else:
                    try:
                        input_model = tool.input_schema()(**arguments)
                        context = ToolUseContext(
                            options=ToolOptions(),
                        )
                        result = await collect_tool_result(tool, input_model, context)
                        text = result.result_for_assistant or str(result.data or "")
                        response["result"] = {
                            "content": [{"type": "text", "text": text}],
                            "isError": result.error is not None,
                        }
                    except Exception as e:
                        response["result"] = {
                            "content": [{"type": "text", "text": f"Tool error: {e}"}],
                            "isError": True,
                        }

            else:
                response["error"] = {"code": -32601, "message": f"Method not found: {method}"}

            writer.write((json.dumps(response) + "\n").encode())
            await writer.drain()

        except json.JSONDecodeError:
            logger.warning("Invalid JSON received")
        except Exception:
            logger.exception("MCP server error")


def main() -> None:
    """Entry point for ``pode-mcp`` console script."""
    asyncio.run(run_mcp_server())
