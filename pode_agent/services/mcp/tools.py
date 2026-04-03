"""MCP tool wrapper — converts MCP tool definitions into Pode-Agent Tool instances.

Each MCP tool becomes a dynamic ``Tool`` subclass that delegates execution
to the MCP client's ``call_tool()`` method.

Tool naming convention: ``mcp__{server_name}__{tool_name}``

Reference: docs/mcp-system.md — MCP Tool Wrapping
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from pydantic import BaseModel, create_model

from pode_agent.core.tools.base import Tool, ToolOutput, ToolUseContext
from pode_agent.infra.logging import get_logger
from pode_agent.services.mcp.client import McpClient, McpToolDefinition

logger = get_logger(__name__)


def _mcp_tool_name(server_name: str, tool_name: str) -> str:
    """Generate the Pode-Agent tool name for an MCP tool.

    Format: ``mcp__{server_name}__{tool_name}``
    """
    return f"mcp__{server_name}__{tool_name}"


def _build_input_schema(definition: McpToolDefinition) -> type[BaseModel]:
    """Dynamically create a Pydantic model from an MCP tool's input schema."""
    properties = definition.input_schema.get("properties", {})
    required_fields = set(definition.input_schema.get("required", []))

    fields: dict[str, Any] = {}
    for prop_name, prop_schema in properties.items():
        prop_type = prop_schema.get("type", "string")
        is_required = prop_name in required_fields

        # Map JSON Schema types to Python types
        type_map: dict[str, type] = {
            "string": str,
            "integer": int,
            "number": float,
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        python_type = type_map.get(prop_type, str)

        if is_required:
            fields[prop_name] = (python_type, ...)
        else:
            default = prop_schema.get("default")
            fields[prop_name] = (python_type, default)

    if not fields:
        # Create a model with a single catch-all field
        return create_model("McpToolInput")

    return create_model("McpToolInput", **fields)


def wrap_mcp_tool_as_pode_tool(
    client: McpClient,
    server_name: str,
    definition: McpToolDefinition,
) -> Tool:
    """Create a dynamic ``Tool`` subclass wrapping an MCP tool.

    The wrapped tool:
    - Uses the MCP naming convention: ``mcp__{server}__{tool}``
    - Delegates execution to ``client.call_tool()``
    - Is conservative: always requires permissions (not read-only)
    """
    tool_name = _mcp_tool_name(server_name, definition.name)
    input_cls = _build_input_schema(definition)
    tool_desc = definition.description or f"MCP tool: {definition.name}"

    class McpToolWrapper(Tool):
        name = tool_name
        description = tool_desc

        def input_schema(self) -> type[BaseModel]:
            return input_cls

        async def is_enabled(self) -> bool:
            return True

        def is_read_only(self, input: Any = None) -> bool:
            return False  # Conservative: assume side effects

        def needs_permissions(self, input: Any = None) -> bool:
            return True  # Conservative: require approval

        async def validate_input(
            self, input: BaseModel, context: ToolUseContext | None = None,
        ) -> Any:
            from pode_agent.core.tools.base import ValidationResult
            return ValidationResult(result=True)

        def render_result_for_assistant(self, output: Any) -> str | list[Any]:
            if isinstance(output, str):
                return output
            return str(output)

        async def call(
            self,
            input: BaseModel,
            context: ToolUseContext,
        ) -> AsyncGenerator[ToolOutput, None]:
            """Execute the MCP tool via the client."""
            args = input.model_dump() if hasattr(input, "model_dump") else dict(input)
            result = await client.call_tool(definition.name, args)

            text = result.content if isinstance(result.content, str) else str(result.content)

            yield ToolOutput(
                type="result",
                data={"content": text, "is_error": result.is_error},
                result_for_assistant=text,
            )

    return McpToolWrapper()
