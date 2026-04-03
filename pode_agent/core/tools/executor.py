"""Tool executor: consume a tool's AsyncGenerator and collect the final result."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from pode_agent.core.tools.base import ToolOutput, ToolResult, ToolUseContext

if TYPE_CHECKING:
    from pydantic import BaseModel

    from pode_agent.core.tools.base import Tool


async def collect_tool_result(
    tool: Tool,
    input: BaseModel,
    context: ToolUseContext,
    on_progress: Callable[[ToolOutput], Awaitable[None]] | None = None,
) -> ToolResult:
    """Consume a tool's AsyncGenerator and return the final ToolResult.

    Iterates through the tool's ``call()`` generator:
    - ``type='progress'`` → calls ``on_progress`` callback (if provided)
    - ``type='result'`` → returns immediately as ToolResult

    Raises:
        RuntimeError: If the generator ends without yielding a result.
    """
    async for output in tool.call(input, context):
        if output.type == "progress":
            if on_progress is not None:
                await on_progress(output)
        elif output.type == "result":
            return ToolResult(
                data=output.data,
                result_for_assistant=output.result_for_assistant,
                new_messages=output.new_messages or [],
                context_modifier=output.context_modifier,
            )

    raise RuntimeError(f"Tool {tool.name} did not yield a result")
