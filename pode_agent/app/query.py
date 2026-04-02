"""Agentic Loop engine — recursive query/query_core with tool execution.

This module implements the core agent loop:
1. ``query()`` — outer entry point, builds UserMessage, delegates to query_core
2. ``query_core()`` — recursive main loop: LLM call → tool use → recurse
3. ``ToolUseQueue`` — serial tool execution (Phase 2: no concurrency)
4. ``check_permissions_and_call_tool()`` — permission check + execute pipeline

Phase 2 simplifications:
- No pre/post hooks (deferred to Phase 5)
- No auto-compact (deferred to Phase 5)
- Serial-only ToolUseQueue (defer concurrency to Phase 5)
- No stop hooks (just save message and yield DONE)

Reference: docs/agent-loop.md — Full specification
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from pydantic import BaseModel, ConfigDict

from pode_agent.core.cost_tracker import add_to_total_cost, calculate_model_cost
from pode_agent.core.permissions.engine import PermissionEngine
from pode_agent.core.permissions.types import (
    PermissionContext,
    PermissionMode,
    PermissionResult,
)
from pode_agent.core.tools.base import Tool, ToolOptions, ToolUseContext
from pode_agent.core.tools.executor import collect_tool_result
from pode_agent.infra.logging import get_logger
from pode_agent.services.ai.base import (
    ToolDefinition,
    ToolUseBlock,
    UnifiedRequestParams,
)
from pode_agent.services.ai.factory import query_llm
from pode_agent.services.system.system_prompt import BASE_SYSTEM_PROMPT, build_system_prompt
from pode_agent.types.session_events import (
    PermissionRequestData,
    SessionEvent,
    SessionEventType,
)
from pode_agent.utils.messages.normalizer import (
    build_tool_result_message,
)

logger = get_logger(__name__)

MAX_TOOL_USE_ROUNDS = 50  # Safety limit for recursive tool use


# ---------------------------------------------------------------------------
# QueryOptions
# ---------------------------------------------------------------------------


class QueryOptions(BaseModel):
    """Runtime options for the Agentic Loop."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    cwd: str = ""
    model: str = "claude-sonnet-4-5-20251101"
    max_tokens: int = 8192
    temperature: float | None = None
    thinking_tokens: int | None = None
    permission_mode: PermissionMode = PermissionMode.DEFAULT
    verbose: bool = False
    safe_mode: bool = False
    stream: bool = True


# ---------------------------------------------------------------------------
# query() — outer entry point
# ---------------------------------------------------------------------------


async def query(
    prompt: str,
    system_prompt: str,
    tools: list[Tool],
    messages: list[dict[str, Any]],
    session: Any,  # SessionManager
    options: QueryOptions,
) -> AsyncGenerator[SessionEvent, None]:
    """Outer entry point: build UserMessage, save, delegate to query_core.

    Args:
        prompt: The user's text input.
        system_prompt: Base system prompt text.
        tools: Available tools for this session.
        messages: Existing conversation messages.
        session: SessionManager instance.
        options: Runtime options.

    Yields:
        SessionEvent instances.
    """
    # Build and save user message
    user_msg = {
        "type": "user",
        "uuid": str(uuid.uuid4()),
        "message": prompt,
    }
    session.save_message(user_msg)

    yield SessionEvent(
        type=SessionEventType.USER_MESSAGE,
        data={"message": user_msg},
        message_id=user_msg["uuid"],
    )

    # Delegate to recursive loop
    async for event in query_core(
        messages=session.get_messages(),
        system_prompt=system_prompt,
        tools=tools,
        session=session,
        options=options,
    ):
        yield event


# ---------------------------------------------------------------------------
# query_core() — recursive main loop
# ---------------------------------------------------------------------------


async def query_core(
    messages: list[dict[str, Any]],
    system_prompt: str,
    tools: list[Tool],
    session: Any,  # SessionManager
    options: QueryOptions,
    *,
    _round: int = 0,
) -> AsyncGenerator[SessionEvent, None]:
    """Recursive Agentic Loop: LLM call → tool use → recurse.

    Phase 2 simplifications: no hooks, no auto-compact, serial tool queue.

    Args:
        messages: Full conversation history.
        system_prompt: Base system prompt text.
        tools: Available tools.
        session: SessionManager instance.
        options: Runtime options.
        _round: Current recursion depth (safety counter).

    Yields:
        SessionEvent instances.
    """
    if _round >= MAX_TOOL_USE_ROUNDS:
        yield SessionEvent(type=SessionEventType.DONE, data={"reason": "max_rounds"})
        return

    if session.abort_event.is_set():
        yield SessionEvent(type=SessionEventType.DONE, data={"reason": "aborted"})
        return

    # 1. Build system prompt with CWD
    full_system_prompt = build_system_prompt(
        system_prompt or BASE_SYSTEM_PROMPT,
        options.cwd,
    )

    # 2. Build tool definitions
    tool_defs = _build_tool_definitions(tools)

    # 3. Build request params
    params = UnifiedRequestParams(
        messages=_messages_to_dicts(messages),
        system_prompt=full_system_prompt,
        model=options.model,
        max_tokens=options.max_tokens,
        tools=tool_defs,
        temperature=options.temperature,
        thinking_tokens=options.thinking_tokens,
    )

    # 4. Call LLM and stream responses
    assistant_text_parts: list[str] = []
    tool_use_blocks: list[ToolUseBlock] = []
    current_tool_id: str | None = None
    current_tool_name: str | None = None
    current_tool_json: str = ""
    token_input = 0
    token_output = 0

    start_time = time.monotonic()

    async for resp in query_llm(params):
        if resp.type == "text_delta" and resp.text:
            assistant_text_parts.append(resp.text)
            yield SessionEvent(
                type=SessionEventType.ASSISTANT_DELTA,
                data={"text": resp.text},
            )

        elif resp.type == "tool_use_start":
            current_tool_id = resp.tool_use_id
            current_tool_name = resp.tool_name
            current_tool_json = ""

        elif resp.type == "tool_use_delta":
            if resp.text:
                current_tool_json += resp.text

        elif resp.type == "message_done":
            # Finalize any pending tool use
            if current_tool_id and current_tool_name:
                try:
                    tool_input = json.loads(current_tool_json) if current_tool_json else {}
                except json.JSONDecodeError:
                    tool_input = {"raw": current_tool_json}
                tool_use_blocks.append(ToolUseBlock(
                    id=current_tool_id,
                    name=current_tool_name,
                    input=tool_input,
                ))
                current_tool_id = None
                current_tool_name = None

            # Capture usage
            if resp.usage:
                token_input = resp.usage.input_tokens
                token_output = resp.usage.output_tokens

        elif resp.type == "error":
            yield SessionEvent(
                type=SessionEventType.MODEL_ERROR,
                data={
                    "error": resp.error_message,
                    "is_retriable": resp.is_retriable,
                },
            )
            return

    # 5. Build assistant message
    assistant_content: list[dict[str, Any]] = []
    if assistant_text_parts:
        full_text = "".join(assistant_text_parts)
        assistant_content.append({"type": "text", "text": full_text})
    for tu in tool_use_blocks:
        assistant_content.append({
            "type": "tool_use",
            "id": tu.id,
            "name": tu.name,
            "input": tu.input,
        })

    duration_ms = int((time.monotonic() - start_time) * 1000)
    cost_usd = calculate_model_cost(options.model, token_input, token_output)

    assistant_msg = {
        "type": "assistant",
        "uuid": str(uuid.uuid4()),
        "message": assistant_content,
        "cost_usd": cost_usd,
        "duration_ms": duration_ms,
    }
    session.save_message(assistant_msg)

    # Cost tracking
    if cost_usd > 0:
        add_to_total_cost(cost_usd)
        yield SessionEvent(
            type=SessionEventType.COST_UPDATE,
            data={"cost_usd": cost_usd, "total_usd": 0.0},
        )

    # 6. No tool uses → save message, yield DONE
    if not tool_use_blocks:
        yield SessionEvent(
            type=SessionEventType.DONE,
            data={"stop_reason": "end_turn"},
            message_id=str(assistant_msg["uuid"]),
        )
        return

    # 7. Execute tools via ToolUseQueue
    tool_results: dict[str, str] = {}
    async for event in _run_tool_queue(
        tool_use_blocks, tools, session, options,
    ):
        yield event
        # Collect tool results
        if event.type == SessionEventType.TOOL_RESULT and event.data:
            tool_results[event.data.get("tool_use_id", "")] = event.data.get(
                "result", ""
            )

    # 8. Build tool result message
    result_msg = build_tool_result_message(tool_use_blocks, tool_results)
    session.save_message(result_msg)

    # 9. Recurse with updated messages
    async for event in query_core(
        messages=session.get_messages(),
        system_prompt=system_prompt,
        tools=tools,
        session=session,
        options=options,
        _round=_round + 1,
    ):
        yield event


# ---------------------------------------------------------------------------
# ToolUseQueue — Phase 2: serial only
# ---------------------------------------------------------------------------


async def _run_tool_queue(
    tool_uses: list[ToolUseBlock],
    tools: list[Tool],
    session: Any,  # SessionManager
    options: QueryOptions,
) -> AsyncGenerator[SessionEvent, None]:
    """Execute tool uses serially (Phase 2: no concurrency).

    Yields TOOL_USE_START, TOOL_PROGRESS, TOOL_RESULT events.
    """
    for tool_use in tool_uses:
        if session.abort_event.is_set():
            break

        async for event in _check_permissions_and_call_tool(
            tool_use, tools, session, options,
        ):
            yield event


# ---------------------------------------------------------------------------
# check_permissions_and_call_tool — single tool pipeline
# ---------------------------------------------------------------------------


async def _check_permissions_and_call_tool(
    tool_use: ToolUseBlock,
    tools: list[Tool],
    session: Any,  # SessionManager
    options: QueryOptions,
) -> AsyncGenerator[SessionEvent, None]:
    """Execute a single tool use with permission checking.

    Pipeline: find tool → validate input → permission check → execute → format result.

    Yields TOOL_USE_START, TOOL_PROGRESS, TOOL_RESULT, PERMISSION_REQUEST events.
    """
    yield SessionEvent(
        type=SessionEventType.TOOL_USE_START,
        data={"tool_name": tool_use.name, "tool_use_id": tool_use.id},
    )

    # 1. Find tool
    tool = _find_tool(tool_use.name, tools)
    if tool is None:
        yield SessionEvent(
            type=SessionEventType.TOOL_RESULT,
            data={
                "tool_use_id": tool_use.id,
                "tool_name": tool_use.name,
                "result": f"Unknown tool: {tool_use.name}",
                "is_error": True,
            },
        )
        return

    # 2. Permission check
    permission_result = _check_permissions(
        tool, tool_use.input, options, session,
    )
    if permission_result == PermissionResult.NEEDS_PROMPT:
        yield SessionEvent(
            type=SessionEventType.PERMISSION_REQUEST,
            data=PermissionRequestData(
                tool_name=tool_use.name,
                tool_input=tool_use.input,
                risk_level="medium",
                description=f"Tool '{tool_use.name}' requires permission",
            ).model_dump(),
        )
        # Phase 2: no interactive permission resolution — deny by default
        yield SessionEvent(
            type=SessionEventType.TOOL_RESULT,
            data={
                "tool_use_id": tool_use.id,
                "tool_name": tool_use.name,
                "result": "Permission denied (no interactive resolution in Phase 2)",
                "is_error": True,
            },
        )
        return
    elif permission_result == PermissionResult.DENIED:
        yield SessionEvent(
            type=SessionEventType.TOOL_RESULT,
            data={
                "tool_use_id": tool_use.id,
                "tool_name": tool_use.name,
                "result": "Permission denied",
                "is_error": True,
            },
        )
        return

    # 3. Execute tool
    try:
        tool_input_model = _build_tool_input(tool, tool_use.input)
        tool_context = _build_tool_context(session, options, tool_use.id)

        result = await collect_tool_result(
            tool, tool_input_model, tool_context,
            on_progress=lambda p: _on_tool_progress(
                p, tool_use.id, tool_use.name,
            ),
        )

        result_text = result.result_for_assistant or str(result.data or "")

        yield SessionEvent(
            type=SessionEventType.TOOL_RESULT,
            data={
                "tool_use_id": tool_use.id,
                "tool_name": tool_use.name,
                "result": result_text,
                "is_error": False,
            },
        )

    except Exception as e:
        logger.exception("Tool execution failed: %s", tool_use.name)
        yield SessionEvent(
            type=SessionEventType.TOOL_RESULT,
            data={
                "tool_use_id": tool_use.id,
                "tool_name": tool_use.name,
                "result": f"Tool error: {e}",
                "is_error": True,
            },
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_tool(name: str, tools: list[Tool]) -> Tool | None:
    """Find a tool by name in the tool list."""
    for t in tools:
        if t.name == name:
            return t
    return None


def _build_tool_definitions(tools: list[Tool]) -> list[ToolDefinition]:
    """Build ToolDefinition list from Tool instances."""
    defs: list[ToolDefinition] = []
    for t in tools:
        if t.is_enabled():
            defs.append(ToolDefinition(
                name=t.name,
                description=t.description or "",
                input_schema=t.input_schema(),
            ))
    return defs


def _messages_to_dicts(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert message list to plain dicts suitable for the LLM.

    Handles both raw dicts and Pydantic model instances.
    """
    result: list[dict[str, Any]] = []
    for msg in messages:
        if isinstance(msg, dict):
            role = msg.get("type", msg.get("role", "user"))
            content = msg.get("message", msg.get("content", ""))
            # Skip tool result messages (they have a different structure)
            if msg.get("tool_use_result") is not None:
                continue
            if role == "user":
                result.append({"role": "user", "content": str(content)})
            elif role == "assistant":
                result.append({"role": "assistant", "content": content})
        elif hasattr(msg, "model_dump"):
            data = msg.model_dump()
            role = data.get("type", "user")
            content = data.get("message", data.get("content", ""))
            if role == "user":
                result.append({"role": "user", "content": str(content)})
            elif role == "assistant":
                result.append({"role": "assistant", "content": content})
    return result


def _check_permissions(
    tool: Tool,
    tool_input: dict[str, Any],
    options: QueryOptions,
    session: Any,  # SessionManager
) -> PermissionResult:
    """Check if a tool has permission to execute."""
    engine = PermissionEngine()
    context = PermissionContext(
        mode=options.permission_mode,
        tool_permission_context=session.permission_context.tool_permission_context,
        allowed_tools=session.permission_context.allowed_tools,
        denied_tools=session.permission_context.denied_tools,
    )
    return engine.has_permissions(
        tool_name=tool.name,
        tool_input=tool_input,
        context=context,
        is_read_only=tool.is_read_only(),
    )


def _build_tool_input(
    tool: Tool,
    raw_input: dict[str, Any],
) -> BaseModel:
    """Parse and validate tool input using the tool's input schema."""
    # Phase 2: validate_input is synchronous
    tool.validate_input(raw_input)
    return _create_input_model(raw_input)


def _create_input_model(data: dict[str, Any]) -> BaseModel:
    """Create a simple Pydantic model wrapping tool input data."""

    class ToolInput(BaseModel):
        model_config = ConfigDict(extra="allow")

    return ToolInput(**data)


def _build_tool_context(
    session: Any,
    options: QueryOptions,
    tool_use_id: str,
) -> ToolUseContext:
    """Build ToolUseContext for a tool execution."""
    tool_opts = ToolOptions(
        tools=[],
        verbose=options.verbose,
        safe_mode=options.safe_mode,
        permission_mode=options.permission_mode,
        model=options.model,
    )
    return ToolUseContext(
        message_id=str(uuid.uuid4()),
        tool_use_id=tool_use_id,
        safe_mode=options.safe_mode,
        abort_event=session.abort_event,
        options=tool_opts,
    )


async def _on_tool_progress(
    progress: Any,
    tool_use_id: str,
    tool_name: str,
) -> None:
    """Handle tool progress updates. Phase 2: no-op."""
    pass
