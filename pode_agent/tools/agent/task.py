"""TaskTool: launch SubAgent instances for delegated task execution.

Supports both foreground (synchronous) and background (asynchronous)
sub-agent execution with full context isolation, tool filtering, and
transcript persistence.

Reference: docs/subagent-system.md — TaskTool
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any, Literal

from pydantic import BaseModel, Field

from pode_agent.core.tools.base import Tool, ToolOutput, ToolUseContext
from pode_agent.infra.logging import get_logger
from pode_agent.services.agents.background_tasks import (
    update_background_agent_task,
    upsert_background_agent_task,
)
from pode_agent.services.agents.fork_context import build_fork_context
from pode_agent.services.agents.loader import get_agent_by_type, load_agents
from pode_agent.services.agents.transcripts import (
    get_agent_transcript,
    save_agent_transcript,
)
from pode_agent.types.agent import AgentModel

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SUBAGENT_DISALLOWED_TOOL_NAMES: frozenset[str] = frozenset([
    "Task",               # Prevent nested sub-agents
    "TaskOutput",         # Sub-agents don't read background tasks
    "KillShell",          # Sub-agents must not terminate the process
    "EnterPlanMode",      # Sub-agents don't enter plan mode
    "ExitPlanMode",       # Sub-agents don't exit plan mode
    "AskUserQuestion",    # Sub-agents don't directly ask the user
])


# ---------------------------------------------------------------------------
# Input schema
# ---------------------------------------------------------------------------


class TaskInput(BaseModel):
    """SubAgent input schema."""

    description: str = Field(
        description="A short (3-5 word) description of the task",
    )
    prompt: str = Field(
        description="The task for the agent to perform",
    )
    subagent_type: str = Field(
        default="general-purpose",
        description="The type of specialized agent to use for this task",
    )
    model: Literal["sonnet", "opus", "haiku"] | None = Field(
        default=None,
        description="Optional model to use for this agent",
    )
    resume: str | None = Field(
        default=None,
        description="Optional agent ID to resume from",
    )
    run_in_background: bool = Field(
        default=False,
        description="Set to true to run this agent in the background",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MODEL_MAP: dict[str, str] = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-5-20251101",
    "opus": "claude-opus-4-5-20250129",
}


def _model_enum_to_pointer(model_name: str) -> str:
    """Map a short model name to a full model identifier."""
    return _MODEL_MAP.get(model_name, model_name)


def resolve_subagent_model(
    *,
    input_model: str | None,
    agent_config: Any,  # AgentConfig
    parent_model: str,
    default_subagent_model: str = "claude-sonnet-4-5-20251101",
) -> str:
    """Determine the model for a sub-agent.

    Priority (highest to lowest):
    1. PODE_SUBAGENT_MODEL environment variable
    2. input_model parameter (TaskInput.model)
    3. agent_config.model (when not 'inherit')
    4. parent_model
    5. default_subagent_model
    """
    # 1. Environment variable
    env_model = os.environ.get("PODE_SUBAGENT_MODEL", "").strip()
    if env_model:
        return env_model

    # 2. Input parameter
    if input_model:
        return _model_enum_to_pointer(input_model)

    # 3. Agent config
    config_model = agent_config.model
    if config_model != AgentModel.INHERIT:
        return _model_enum_to_pointer(config_model.value)

    # 4. Parent model
    if parent_model:
        return parent_model

    # 5. Default
    return default_subagent_model


async def get_task_tools(
    safe_mode: bool = False,
    agent_config: Any | None = None,  # AgentConfig | None
) -> list[Tool]:
    """Get the filtered tool set for a sub-agent.

    Three-layer filtering:
    1. Remove always-disallowed tools
    2. Whitelist filter (agent_config.tools)
    3. Blacklist filter (agent_config.disallowed_tools)
    """
    from pode_agent.tools import get_all_tools

    all_tools = get_all_tools()
    if safe_mode:
        all_tools = [t for t in all_tools if t.is_read_only()]

    # Layer 1: Remove always-disallowed
    tools = [t for t in all_tools if t.name not in SUBAGENT_DISALLOWED_TOOL_NAMES]

    if agent_config is None:
        return tools

    # Layer 2: Whitelist
    tool_filter = agent_config.tools
    if tool_filter != "*":
        allowed = frozenset(tool_filter)
        tools = [t for t in tools if t.name in allowed]

    # Layer 3: Blacklist
    if agent_config.disallowed_tools:
        disallowed = frozenset(agent_config.disallowed_tools)
        tools = [t for t in tools if t.name not in disallowed]

    return tools


def _extract_assistant_text(messages: list[dict[str, Any]]) -> str:
    """Extract the text content from the last assistant message."""
    for msg in reversed(messages):
        role = msg.get("role", "")
        if role == "assistant":
            content = msg.get("content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts: list[str] = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        parts.append(block.get("text", ""))
                return "\n".join(parts)
    return ""


# ---------------------------------------------------------------------------
# TaskTool
# ---------------------------------------------------------------------------


class TaskTool(Tool):
    """Launch SubAgent instances for delegated task execution.

    Supports foreground (synchronous) and background (asynchronous) modes.
    """

    name: str = "Task"
    description: str = (
        "Launch a new agent to handle complex, multi-step tasks autonomously. "
        "The agent has its own conversation history and can use tools. "
        "Use for research, code review, testing, or any multi-step work."
    )

    def input_schema(self) -> type[BaseModel]:
        return TaskInput

    async def is_enabled(self) -> bool:
        return True

    def is_read_only(self, input: Any = None) -> bool:
        return False

    def needs_permissions(self, input: Any = None) -> bool:
        return True

    def is_concurrency_safe(self, input: Any = None) -> bool:
        return False

    async def call(
        self,
        input: BaseModel,
        context: ToolUseContext,
    ) -> AsyncGenerator[ToolOutput, None]:
        assert isinstance(input, TaskInput)
        async for output in self._execute(input, context):
            yield output

    # ------------------------------------------------------------------
    # Internal execution
    # ------------------------------------------------------------------

    async def _execute(
        self,
        input: TaskInput,
        context: ToolUseContext,
    ) -> AsyncGenerator[ToolOutput, None]:
        """Common setup, then dispatch to foreground or background."""
        # 1. Load agent config
        agents = await load_agents()
        agent_config = get_agent_by_type(agents, input.subagent_type)
        if agent_config is None:
            yield ToolOutput(
                type="result",
                data={"error": f"Unknown agent type: {input.subagent_type}"},
                result_for_assistant=f"Error: Unknown agent type: {input.subagent_type}",
            )
            return

        # 2. Resolve model
        parent_model = context.options.model or ""
        model = resolve_subagent_model(
            input_model=input.model,
            agent_config=agent_config,
            parent_model=parent_model,
        )

        # 3. Filter tools
        tools = await get_task_tools(
            safe_mode=context.options.safe_mode,
            agent_config=agent_config,
        )

        # 4. Generate or resume agent_id
        agent_id = input.resume or f"agent_{uuid.uuid4().hex[:8]}"

        # 5. Build initial messages
        messages: list[dict[str, Any]] = []

        # Resume from transcript if requested
        if input.resume:
            transcript = get_agent_transcript(input.resume)
            if transcript:
                messages = list(transcript)

        # Fork context (if enabled and not resuming)
        if agent_config.fork_context and not input.resume:
            fork_ctx, prompt_msgs = build_fork_context(
                enabled=True,
                prompt=input.prompt,
                tool_use_id=context.tool_use_id,
                message_log_name=context.options.message_log_name,
                fork_number=context.options.fork_number,
            )
            messages.extend(fork_ctx)
            messages.extend(prompt_msgs)
        elif not input.resume:
            messages.append({"role": "user", "content": input.prompt})

        # 6. Build system prompt
        system_prompt = agent_config.system_prompt or ""

        # 7. Dispatch
        if input.run_in_background:
            async for output in self._run_background(
                agent_id=agent_id,
                description=input.description,
                prompt=input.prompt,
                model=model,
                system_prompt=system_prompt,
                tools=tools,
                messages=messages,
                subagent_type=input.subagent_type,
                agent_config=agent_config,
                parent_session=context.session,
            ):
                yield output
        else:
            async for output in self._run_foreground(
                agent_id=agent_id,
                description=input.description,
                prompt=input.prompt,
                model=model,
                system_prompt=system_prompt,
                tools=tools,
                messages=messages,
                context=context,
                agent_config=agent_config,
            ):
                yield output

    # ------------------------------------------------------------------
    # Foreground execution
    # ------------------------------------------------------------------

    async def _run_foreground(
        self,
        *,
        agent_id: str,
        description: str,
        prompt: str,
        model: str,
        system_prompt: str,
        tools: list[Tool],
        messages: list[dict[str, Any]],
        context: ToolUseContext,
        agent_config: Any,
    ) -> AsyncGenerator[ToolOutput, None]:
        """Run sub-agent synchronously, yielding progress then result."""
        from pode_agent.app.query import query_core
        from pode_agent.app.sub_session import create_sub_session

        start_time = time.monotonic()

        # Yield initial progress
        yield ToolOutput(
            type="progress",
            content=f"[Agent {agent_id} starting: {description}]",
        )

        # Create sub-session using factory (proper permission mapping + system prompt)
        parent_session = context.session
        if parent_session is not None:
            session = create_sub_session(
                parent_session=parent_session,
                agent_config=agent_config,
                tools=tools,
                initial_messages=messages,
            )
        else:
            # Fallback when no parent session (e.g. isolated test)
            from pode_agent.app.session import SessionManager
            from pode_agent.core.permissions.types import PermissionContext, PermissionMode

            session = SessionManager(
                tools=tools,
                initial_messages=messages,
                permission_context=PermissionContext(mode=PermissionMode.ACCEPT_EDITS),
                model=model,
                system_prompt=system_prompt,
            )

        tool_use_count = 0
        last_progress_time = 0.0

        # Run agentic loop
        from pode_agent.app.query import QueryOptions

        options = QueryOptions(
            model=model,
            cwd=str(os.getcwd()),
            permission_mode=PermissionMode(context.options.permission_mode)
            if context.options.permission_mode
            else PermissionMode.BYPASS_PERMISSIONS,
            safe_mode=context.options.safe_mode,
        )

        try:
            async for event in query_core(
                messages=session.get_messages(),
                system_prompt=system_prompt,
                tools=tools,
                session=session,
                options=options,
            ):
                # Track tool usage
                event_type = getattr(event, "type", None)

                if event_type is not None and str(event_type) == "tool_use":
                    tool_use_count += 1

                # Throttled progress yielding (200ms)
                now = time.monotonic()
                if now - last_progress_time >= 0.2:
                    yield ToolOutput(
                        type="progress",
                        content=f"[Agent {agent_id} working...] ({tool_use_count} tool uses)",
                    )
                    last_progress_time = now

        except Exception as exc:
            logger.exception("SubAgent %s failed", agent_id)
            yield ToolOutput(
                type="result",
                data={
                    "status": "completed",
                    "agent_id": agent_id,
                    "description": description,
                    "prompt": prompt,
                    "error": str(exc),
                },
                result_for_assistant=f"[Agent {agent_id} failed: {exc}]",
            )
            return

        duration_ms = int((time.monotonic() - start_time) * 1000)

        # Extract result text
        sub_messages = session.get_messages()
        result_text = _extract_assistant_text(sub_messages)

        # Save transcript
        save_agent_transcript(agent_id, sub_messages)

        yield ToolOutput(
            type="result",
            data={
                "status": "completed",
                "agent_id": agent_id,
                "description": description,
                "prompt": prompt,
                "content": [{"type": "text", "text": result_text}],
                "total_tool_use_count": tool_use_count,
                "total_duration_ms": duration_ms,
            },
            result_for_assistant=(
                f"[Agent {agent_id} completed] {result_text} "
                f"({tool_use_count} tool uses, {duration_ms / 1000:.1f}s)"
            ),
        )

    # ------------------------------------------------------------------
    # Background execution
    # ------------------------------------------------------------------

    async def _run_background(
        self,
        *,
        agent_id: str,
        description: str,
        prompt: str,
        model: str,
        system_prompt: str,
        tools: list[Tool],
        messages: list[dict[str, Any]],
        subagent_type: str,
        agent_config: Any,
        parent_session: Any,
    ) -> AsyncGenerator[ToolOutput, None]:
        """Launch sub-agent as a background task, return immediately."""
        # Register background task
        upsert_background_agent_task(
            agent_id=agent_id,
            description=description,
            prompt=prompt,
            subagent_type=subagent_type,
        )

        # Launch coroutine
        asyncio.create_task(
            self._background_worker(
                agent_id=agent_id,
                model=model,
                system_prompt=system_prompt,
                tools=tools,
                messages=messages,
                agent_config=agent_config,
                parent_session=parent_session,
            )
        )

        # Return immediately
        yield ToolOutput(
            type="result",
            data={
                "status": "async_launched",
                "agent_id": agent_id,
                "description": description,
                "prompt": prompt,
            },
            result_for_assistant=(
                f"[Agent {agent_id} launched in background] "
                f"Use TaskOutput to check results."
            ),
        )

    async def _background_worker(
        self,
        *,
        agent_id: str,
        model: str,
        system_prompt: str,
        tools: list[Tool],
        messages: list[dict[str, Any]],
        agent_config: Any,
        parent_session: Any,
    ) -> None:
        """Run sub-agent in background, updating task registry."""
        from pode_agent.app.query import QueryOptions, query_core
        from pode_agent.app.sub_session import create_sub_session
        from pode_agent.core.permissions.types import PermissionMode
        from pode_agent.types.agent import BackgroundAgentStatus

        start_time = time.monotonic()

        if parent_session is not None:
            session = create_sub_session(
                parent_session=parent_session,
                agent_config=agent_config,
                tools=tools,
                initial_messages=messages,
            )
        else:
            from pode_agent.app.session import SessionManager
            from pode_agent.core.permissions.types import PermissionContext, PermissionMode

            session = SessionManager(
                tools=tools,
                initial_messages=messages,
                permission_context=PermissionContext(mode=PermissionMode.ACCEPT_EDITS),
                model=model,
                system_prompt=system_prompt,
            )

        options = QueryOptions(
            model=model,
            cwd=str(os.getcwd()),
            permission_mode=getattr(
                getattr(parent_session, "permission_context", None),
                "mode",
                PermissionMode.ACCEPT_EDITS,
            ) if parent_session else PermissionMode.ACCEPT_EDITS,
        )

        tool_use_count = 0

        try:
            async for event in query_core(
                messages=session.get_messages(),
                system_prompt=system_prompt,
                tools=tools,
                session=session,
                options=options,
            ):
                event_type = getattr(event, "type", None)
                if event_type is not None and str(event_type) == "tool_use":
                    tool_use_count += 1

                # Update messages in the background task record
                sub_messages = session.get_messages()
                update_background_agent_task(
                    agent_id,
                    total_tool_use_count=tool_use_count,
                )

            duration_ms = int((time.monotonic() - start_time) * 1000)
            sub_messages = session.get_messages()
            result_text = _extract_assistant_text(sub_messages)

            # Save transcript
            save_agent_transcript(agent_id, sub_messages)

            update_background_agent_task(
                agent_id,
                status=BackgroundAgentStatus.COMPLETED,
                result_text=result_text,
                total_tool_use_count=tool_use_count,
                total_duration_ms=duration_ms,
            )

        except Exception as exc:
            logger.exception("Background SubAgent %s failed", agent_id)
            update_background_agent_task(
                agent_id,
                status=BackgroundAgentStatus.FAILED,
                error=str(exc),
            )

    def render_result_for_assistant(self, output: Any) -> str | list[Any]:
        if isinstance(output, dict) and "error" in output:
            return str(output["error"])
        return str(output)
