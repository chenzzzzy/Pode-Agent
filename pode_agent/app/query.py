"""Agentic Loop engine — recursive query/query_core with tool execution.

This module implements the core agent loop:
1. ``query()`` — outer entry point, builds UserMessage, delegates to query_core
2. ``query_core()`` — recursive main loop: auto-compact → system prompt → LLM → tools → recurse
3. ``ToolUseQueue`` — concurrency-aware tool execution (from tool_queue.py)
4. ``check_permissions_and_call_tool()`` — permission check + execute pipeline

Phase 3 additions:
- Concurrent ToolUseQueue (safe tools parallel, unsafe tools serial)
- Dynamic system prompt assembly (plan mode, tool reminders)
- Auto-compact framework (threshold-based truncation)
- Plan mode result detection (enter_plan_mode / exit_plan_mode)

Phase 5 additions:
- Hook system integration (4 injection points)
- Stop hook reentry with MAX_STOP_HOOK_ATTEMPTS guard
- contextModifier propagation from tool results

Reference: docs/agent-loop.md — Full specification
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from pydantic import BaseModel, ConfigDict

# Phase 3: auto-compact and concurrent tool queue
from pode_agent.app.compact import auto_compact_if_needed
from pode_agent.app.tool_queue import ToolUseQueue
from pode_agent.core.config.schema import DEFAULT_MODEL_NAME
from pode_agent.core.cost_tracker import add_to_total_cost, calculate_model_cost, get_total_cost
from pode_agent.core.permissions.engine import PermissionEngine
from pode_agent.core.permissions.types import (
    PermissionContext,
    PermissionDecision,
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
from pode_agent.services.hooks.base import HookState
from pode_agent.services.hooks.runner import (
    MAX_STOP_HOOK_ATTEMPTS,
    run_post_tool_use_hooks,
    run_pre_tool_use_hooks,
    run_stop_hooks,
    run_user_prompt_submit_hooks,
)
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
    model: str = DEFAULT_MODEL_NAME
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
    _hook_state: HookState | None = None,
    _stop_hook_attempts: int = 0,
) -> AsyncGenerator[SessionEvent, None]:
    """Recursive Agentic Loop: LLM call → tool use → recurse.

    Phase 5: hooks, contextModifier, stop hook reentry.

    Args:
        messages: Full conversation history.
        system_prompt: Base system prompt text.
        tools: Available tools.
        session: SessionManager instance.
        options: Runtime options.
        _round: Current recursion depth (safety counter).
        _hook_state: Hook state carried across injection points.
        _stop_hook_attempts: Stop hook reentry counter.

    Yields:
        SessionEvent instances.
    """
    if _round >= MAX_TOOL_USE_ROUNDS:
        yield SessionEvent(type=SessionEventType.DONE, data={"reason": "max_rounds"})
        return

    if session.abort_event.is_set():
        yield SessionEvent(type=SessionEventType.DONE, data={"reason": "aborted"})
        return

    # Step 1a: auto-compact if needed
    messages = auto_compact_if_needed(messages)

    # Step 1b: Hook state (Phase 5)
    hook_state = _hook_state or HookState()

    # Step 1c: UserPromptSubmit hooks (only on first entry)
    await run_user_prompt_submit_hooks(
        "", messages, hook_state,
    )

    # 1. Build system prompt with dynamic assembly (Phase 3)
    full_system_prompt = build_system_prompt(
        system_prompt or BASE_SYSTEM_PROMPT,
        options.cwd,
        permission_mode=options.permission_mode,
        tools=tools,
    )
    # Phase 5: append hook-injected system prompts
    if hook_state.additional_system_prompts:
        full_system_prompt += "\n\n" + "\n\n".join(hook_state.additional_system_prompts)

    # 2. Build tool definitions
    tool_defs = await _build_tool_definitions(tools)

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
    # Track pending tool uses by ID to support multiple concurrent tool_uses
    pending_tools: dict[str, tuple[str, str]] = {}  # tool_use_id → (name, json_str)
    current_tool_id: str | None = None  # fallback for deltas without tool_use_id
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
            if resp.tool_use_id and resp.tool_name:
                pending_tools[resp.tool_use_id] = (resp.tool_name, "")
                current_tool_id = resp.tool_use_id

        elif resp.type == "tool_use_delta":
            tu_id = resp.tool_use_id or current_tool_id
            if resp.text and tu_id and tu_id in pending_tools:
                name, json_str = pending_tools[tu_id]
                pending_tools[tu_id] = (name, json_str + resp.text)

        elif resp.type == "message_done":
            # Finalize all pending tool uses
            for tu_id, (tu_name, tu_json) in pending_tools.items():
                try:
                    tool_input = json.loads(tu_json) if tu_json else {}
                except json.JSONDecodeError:
                    tool_input = {"raw": tu_json}
                tool_use_blocks.append(ToolUseBlock(
                    id=tu_id,
                    name=tu_name,
                    input=tool_input,
                ))
            pending_tools.clear()

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
            data={"cost_usd": cost_usd, "total_usd": get_total_cost()},
        )

    # 6. No tool uses → check stop hooks, then DONE (Phase 5: stop hook reentry)
    if not tool_use_blocks:
        stop_reason = "end_turn"
        if _stop_hook_attempts < MAX_STOP_HOOK_ATTEMPTS:
            stop_result = await run_stop_hooks(
                session.get_messages(), stop_reason, hook_state,
            )
            if stop_result.action == "block" or stop_result.additional_system_prompt:
                # Stop hook wants the loop to continue
                async for event in query_core(
                    messages=session.get_messages(),
                    system_prompt=system_prompt,
                    tools=tools,
                    session=session,
                    options=options,
                    _round=_round + 1,
                    _hook_state=hook_state,
                    _stop_hook_attempts=_stop_hook_attempts + 1,
                ):
                    yield event
                return
        yield SessionEvent(
            type=SessionEventType.DONE,
            data={"stop_reason": stop_reason},
            message_id=str(assistant_msg["uuid"]),
        )
        return

    # 7. Execute tools via concurrent ToolUseQueue (Phase 3)
    tool_results: dict[str, str] = {}
    collected_modifiers: list[Any] = []
    queue = ToolUseQueue(
        tool_uses=tool_use_blocks,
        tools=tools,
        execute_single=lambda tu: _check_permissions_and_call_tool(
            tu, tools, session, options, hook_state=hook_state,
        ),
        abort_event=session.abort_event,
    )
    async for event in queue.run():
        yield event
        # Collect tool results and context modifiers
        if event.type == SessionEventType.TOOL_RESULT and event.data:
            tool_results[event.data.get("tool_use_id", "")] = event.data.get(
                "result", ""
            )
            if event.data.get("context_modifier"):
                collected_modifiers.append(event.data["context_modifier"])

    # 8. Build tool result message
    result_msg = build_tool_result_message(tool_use_blocks, tool_results)
    session.save_message(result_msg)

    # 8b. Apply context modifiers from tool results (Phase 5: contextModifier)
    updated_options = options
    for modifier_data in collected_modifiers:
        from pode_agent.types.skill import ContextModifier
        modifier = ContextModifier.model_validate(modifier_data)
        updated_options = modifier.apply_to_options(updated_options)

    # 9. Recurse with updated messages (Phase 5: propagate hook_state + context_modifier)
    async for event in query_core(
        messages=session.get_messages(),
        system_prompt=system_prompt,
        tools=tools,
        session=session,
        options=updated_options,
        _round=_round + 1,
        _hook_state=hook_state,
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
    hook_state: HookState | None = None,
) -> AsyncGenerator[SessionEvent, None]:
    """Execute a single tool use with permission checking and hook integration.

    Pipeline: find tool → pre hooks → validate → permission → execute → post hooks.

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

    # 2. PreToolUse hooks (Phase 5)
    if hook_state is not None:
        pre_result = await run_pre_tool_use_hooks(
            tool_use.name, tool_use.input, tool_use.id, hook_state,
        )
        if pre_result.action == "block":
            yield SessionEvent(
                type=SessionEventType.TOOL_RESULT,
                data={
                    "tool_use_id": tool_use.id,
                    "tool_name": tool_use.name,
                    "result": pre_result.message or "Blocked by hook",
                    "is_error": True,
                },
            )
            return
        if pre_result.action == "modify" and pre_result.modified_data and isinstance(
            pre_result.modified_data, dict
        ):
            tool_use = ToolUseBlock(
                id=tool_use.id,
                name=pre_result.modified_data.get("tool_name", tool_use.name),
                input=pre_result.modified_data.get("tool_input", tool_use.input),
            )

    # 3. Permission check
    permission_result = _check_permissions(
        tool, tool_use.input, options, session,
    )
    if permission_result == PermissionResult.NEEDS_PROMPT:
        yield SessionEvent(
            type=SessionEventType.PERMISSION_REQUEST,
            data=PermissionRequestData(
                tool_name=tool_use.name,
                tool_input=tool_use.input,
                tool_use_id=tool_use.id,
                risk_level="medium",
                description=f"Tool '{tool_use.name}' requires permission",
            ).model_dump(),
        )
        # Wait for user's permission decision
        decision = await _wait_for_permission_decision(session, tool_use.name)
        if decision == PermissionDecision.DENY:
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
        _apply_permission_decision(session, tool_use.name, decision)
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
        tool_input_model = await _build_tool_input(tool, tool_use.input)
        tool_context = _build_tool_context(session, options, tool_use.id)

        # Queue for progress events from callback
        progress_queue: asyncio.Queue[SessionEvent] = asyncio.Queue()

        result = await collect_tool_result(
            tool, tool_input_model, tool_context,
            on_progress=lambda p: _on_tool_progress(
                p, tool_use.id, tool_use.name, progress_queue,
            ),
        )

        # Yield any progress events that accumulated during execution
        while not progress_queue.empty():
            yield await progress_queue.get()

        result_text = result.result_for_assistant or str(result.data or "")

        yield SessionEvent(
            type=SessionEventType.TOOL_RESULT,
            data={
                "tool_use_id": tool_use.id,
                "tool_name": tool_use.name,
                "result": result_text,
                "is_error": False,
                "context_modifier": result.context_modifier,
                "new_messages": result.new_messages,
            },
        )

        # 4. PostToolUse hooks (Phase 5)
        if hook_state is not None:
            await run_post_tool_use_hooks(
                tool_use.name, tool_use.input, result_text,
                tool_use.id, is_error=False, hook_state=hook_state,
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

        # 4b. PostToolUse hooks for error case (Phase 5)
        if hook_state is not None:
            await run_post_tool_use_hooks(
                tool_use.name, tool_use.input, f"Tool error: {e}",
                tool_use.id, is_error=True, hook_state=hook_state,
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


async def _build_tool_definitions(tools: list[Tool]) -> list[ToolDefinition]:
    """Build ToolDefinition list from Tool instances."""
    defs: list[ToolDefinition] = []
    for t in tools:
        if await t.is_enabled():
            defs.append(ToolDefinition(
                name=t.name,
                description=t.description or "",
                input_schema=t.input_schema().model_json_schema(),
            ))
    return defs


def _messages_to_dicts(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert message list to plain dicts suitable for the LLM.

    Handles both raw dicts and Pydantic model instances.
    Preserves structured content (lists) for tool_result blocks.
    """
    result: list[dict[str, Any]] = []
    for msg in messages:
        if isinstance(msg, dict):
            role = msg.get("type", msg.get("role", "user"))
            content = msg.get("message", msg.get("content", ""))
            if isinstance(content, list):
                # Structured content (tool_result blocks, assistant content) — pass through
                result.append({"role": role, "content": content})
            elif isinstance(content, str):
                result.append({"role": role, "content": content})
            else:
                result.append({"role": role, "content": str(content) if content else ""})
        elif hasattr(msg, "model_dump"):
            data = msg.model_dump()
            role = data.get("type", "user")
            content = data.get("message", data.get("content", ""))
            if isinstance(content, list | str):
                result.append({"role": role, "content": content})
            else:
                result.append({"role": role, "content": str(content) if content else ""})
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


async def _build_tool_input(
    tool: Tool,
    raw_input: dict[str, Any],
) -> BaseModel:
    """Parse and validate tool input using the tool's input schema."""
    input_cls = tool.input_schema()
    input_model = input_cls(**raw_input)
    await tool.validate_input(input_model)
    return input_model


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
    queue: asyncio.Queue[SessionEvent],
) -> None:
    """Enqueue TOOL_PROGRESS event from tool callback."""
    await queue.put(SessionEvent(
        type=SessionEventType.TOOL_PROGRESS,
        data={
            "tool_use_id": tool_use_id,
            "content": progress.content if hasattr(progress, "content") else str(progress),
        },
    ))


async def _wait_for_permission_decision(
    session: Any,
    tool_name: str,
) -> PermissionDecision:
    """Await user permission response. Falls back to DENY on abort."""
    session._permission_event.clear()
    done, pending = await asyncio.wait(
        [
            asyncio.create_task(session._permission_event.wait()),
            asyncio.create_task(session.abort_event.wait()),
        ],
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()
    if session.abort_event.is_set():
        return PermissionDecision.DENY
    return session._last_permission_decision or PermissionDecision.DENY


def _apply_permission_decision(
    session: Any,
    tool_name: str,
    decision: PermissionDecision,
) -> None:
    """Update session permission context with user's decision."""
    tpc = session.permission_context.tool_permission_context
    if decision in (PermissionDecision.ALLOW_SESSION, PermissionDecision.ALLOW_ALWAYS):
        tpc.approved_tools = tpc.approved_tools | {tool_name}
