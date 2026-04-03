"""Background agent task registry — tracks running background SubAgent tasks."""

from __future__ import annotations

import asyncio
import contextlib

from pode_agent.infra.logging import get_logger
from pode_agent.types.agent import BackgroundAgentStatus, BackgroundAgentTask

logger = get_logger(__name__)

# In-memory registry
_registry: dict[str, BackgroundAgentTask] = {}
_runtime_registry: dict[str, _BackgroundAgentRuntime] = {}


class _BackgroundAgentRuntime:
    """Runtime state for a background agent task."""

    def __init__(self, task: BackgroundAgentTask) -> None:
        self.task = task
        self.abort_event = asyncio.Event()
        self.done_event = asyncio.Event()


def upsert_background_agent_task(
    agent_id: str,
    description: str,
    prompt: str,
    subagent_type: str = "general-purpose",
) -> BackgroundAgentTask:
    """Create or update a background agent task entry."""
    task = BackgroundAgentTask(
        agent_id=agent_id,
        description=description,
        prompt=prompt,
        subagent_type=subagent_type,
    )
    _registry[agent_id] = task
    _runtime_registry[agent_id] = _BackgroundAgentRuntime(task)
    return task


async def wait_for_background_agent_task(
    agent_id: str,
    timeout_ms: int = 5000,
) -> BackgroundAgentTask:
    """Wait for a background agent task to complete.

    Returns the completed task. Raises TimeoutError if not done within timeout.
    """
    runtime = _runtime_registry.get(agent_id)
    if not runtime:
        raise KeyError(f"Background task not found: {agent_id}")

    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(
            runtime.done_event.wait(),
            timeout=timeout_ms / 1000,
        )

    return runtime.task


def get_background_agent_task(agent_id: str) -> BackgroundAgentTask | None:
    """Get the current state of a background agent task."""
    return _registry.get(agent_id)


def update_background_agent_task(
    agent_id: str,
    *,
    status: BackgroundAgentStatus | None = None,
    result_text: str | None = None,
    error: str | None = None,
    total_tool_use_count: int | None = None,
    total_duration_ms: int | None = None,
    total_tokens: int | None = None,
) -> BackgroundAgentTask | None:
    """Update a background agent task's state."""
    task = _registry.get(agent_id)
    if not task:
        return None

    if status is not None:
        task.status = status
    if result_text is not None:
        task.result_text = result_text
    if error is not None:
        task.error = error
    if total_tool_use_count is not None:
        task.total_tool_use_count = total_tool_use_count
    if total_duration_ms is not None:
        task.total_duration_ms = total_duration_ms
    if total_tokens is not None:
        task.total_tokens = total_tokens

    # Signal completion if terminal state
    if status in (BackgroundAgentStatus.COMPLETED, BackgroundAgentStatus.FAILED, BackgroundAgentStatus.KILLED):
        runtime = _runtime_registry.get(agent_id)
        if runtime:
            runtime.done_event.set()

    return task


def get_abort_event(agent_id: str) -> asyncio.Event | None:
    """Get the abort event for a background task."""
    runtime = _runtime_registry.get(agent_id)
    return runtime.abort_event if runtime else None


def clear_registry() -> None:
    """Clear all entries (for testing)."""
    _registry.clear()
    _runtime_registry.clear()
