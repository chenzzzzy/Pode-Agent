"""Unit tests for Tool ABC and core tool types."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

from pode_agent.core.tools.base import (
    Tool,
    ToolOutput,
    ToolUseContext,
)
from pode_agent.core.tools.executor import collect_tool_result
from pode_agent.core.tools.registry import ToolRegistry

# --- Concrete test tool ---


class EchoInput(BaseModel):
    message: str


class EchoTool(Tool):
    name = "echo"
    description = "Echo input back as output"

    def input_schema(self) -> type[BaseModel]:
        return EchoInput

    async def is_enabled(self) -> bool:
        return True

    def is_read_only(self, input: Any = None) -> bool:
        return True

    def needs_permissions(self, input: Any = None) -> bool:
        return False

    def render_result_for_assistant(self, output: Any) -> str | list:
        return str(output)

    async def call(self, input: BaseModel, context: ToolUseContext):
        echo_input = input  # type: ignore
        yield ToolOutput(type="progress", content=f"Echoing: {echo_input.message}")
        yield ToolOutput(type="result", data=echo_input.message)


class _EmptyInput(BaseModel):
    pass


class FailingTool(Tool):
    """A tool that doesn't yield a result (for testing executor error)."""

    name = "failing"

    def input_schema(self) -> type[BaseModel]:
        return _EmptyInput

    async def is_enabled(self) -> bool:
        return True

    def is_read_only(self, input: Any = None) -> bool:
        return True

    def needs_permissions(self, input: Any = None) -> bool:
        return False

    def render_result_for_assistant(self, output: Any) -> str | list:
        return ""

    async def call(self, input: BaseModel, context: ToolUseContext):
        # Intentionally does not yield a result
        return
        yield  # makes this an async generator


class TestToolABC:
    def test_get_json_schema(self) -> None:
        tool = EchoTool()
        schema = tool.get_json_schema()

        assert schema["name"] == "echo"
        assert "input_schema" in schema
        assert "message" in schema["input_schema"]["properties"]

    @pytest.mark.asyncio
    async def test_default_validate_input(self) -> None:
        tool = EchoTool()
        result = await tool.validate_input(EchoInput(message="test"))
        assert result.result is True

    def test_render_tool_use_message(self) -> None:
        tool = EchoTool()
        msg = tool.render_tool_use_message({"message": "hello"})
        assert "echo" in msg


class TestToolExecutor:
    @pytest.mark.asyncio
    async def test_collect_tool_result(self) -> None:
        tool = EchoTool()
        context = ToolUseContext(message_id="test")
        result = await collect_tool_result(
            tool, EchoInput(message="hello"), context
        )
        assert result.data == "hello"

    @pytest.mark.asyncio
    async def test_collect_tool_result_raises_on_no_result(self) -> None:
        tool = FailingTool()
        context = ToolUseContext(message_id="test")
        with pytest.raises(RuntimeError, match="did not yield a result"):
            await collect_tool_result(tool, _EmptyInput(), context)

    @pytest.mark.asyncio
    async def test_progress_callback(self) -> None:
        progress_items: list[ToolOutput] = []

        async def on_progress(output: ToolOutput) -> None:
            progress_items.append(output)

        tool = EchoTool()
        context = ToolUseContext(message_id="test")
        await collect_tool_result(
            tool, EchoInput(message="hi"), context, on_progress=on_progress
        )

        assert len(progress_items) == 1
        assert progress_items[0].type == "progress"
        assert "hi" in str(progress_items[0].content)


class TestToolRegistry:
    def test_register_and_lookup(self) -> None:
        registry = ToolRegistry()
        tool = EchoTool()
        registry.register(tool)

        assert registry.get_tool_by_name("echo") is tool
        assert len(registry) == 1

    def test_lookup_missing_returns_none(self) -> None:
        registry = ToolRegistry()
        assert registry.get_tool_by_name("nonexistent") is None

    def test_contains(self) -> None:
        registry = ToolRegistry([EchoTool()])
        assert "echo" in registry
        assert "missing" not in registry

    def test_tools_property(self) -> None:
        tool = EchoTool()
        registry = ToolRegistry([tool])
        assert registry.tools == [tool]
