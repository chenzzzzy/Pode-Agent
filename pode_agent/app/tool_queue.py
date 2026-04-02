"""Concurrent ToolUseQueue: executes tool uses with concurrency awareness.

Groups consecutive concurrency-safe tools for parallel execution via
``asyncio.gather``, while unsafe tools form barriers that must complete
before the next group starts.

On any tool error within a concurrent group, sibling tools are cancelled
via the shared abort event.

Reference: docs/agent-loop.md — ToolUseQueue
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

from pode_agent.core.tools.base import Tool
from pode_agent.infra.logging import get_logger
from pode_agent.services.ai.base import ToolUseBlock
from pode_agent.types.session_events import SessionEvent, SessionEventType

logger = get_logger(__name__)


class ToolUseQueue:
    """Execute tool uses with concurrency-aware scheduling.

    Replaces the Phase 2 serial ``_run_tool_queue()`` with a grouping
    strategy:
    - Consecutive ``is_concurrency_safe()`` tools → parallel group
    - Each unsafe tool → solo group (barrier)

    Args:
        tool_uses: Tool use blocks from the LLM response.
        tools: Available tool instances.
        execute_single: Async generator function that executes a single tool.
        abort_event: Shared abort event for sibling cancellation.
    """

    def __init__(
        self,
        tool_uses: list[ToolUseBlock],
        tools: Any,  # list[Tool] — Any for test mock compatibility
        execute_single: Any,  # Callable returning AsyncGenerator[SessionEvent, None]
        abort_event: asyncio.Event,
    ) -> None:
        self._tool_uses = tool_uses
        self._tools = tools
        self._execute_single = execute_single
        self._abort_event = abort_event

    async def run(self) -> AsyncGenerator[SessionEvent, None]:
        """Execute all tool uses with concurrency grouping.

        Yields TOOL_USE_START, TOOL_PROGRESS, TOOL_RESULT events
        in a deterministic order within each group.
        """
        groups = self._group_by_concurrency()

        for group in groups:
            if self._abort_event.is_set():
                break

            if len(group) == 1:
                # Single tool (unsafe or lone safe tool) — run serially
                async for event in self._execute_single(group[0]):
                    yield event
            else:
                # Multiple safe tools — run concurrently
                async for event in self._run_concurrent(group):
                    yield event

    def _group_by_concurrency(self) -> list[list[ToolUseBlock]]:
        """Group tool uses into concurrent-safe batches.

        Consecutive safe tools are grouped together; each unsafe tool
        forms its own group (acts as a barrier).
        """
        groups: list[list[ToolUseBlock]] = []
        current_group: list[ToolUseBlock] = []

        for tu in self._tool_uses:
            tool = self._find_tool(tu.name)
            is_safe = tool.is_concurrency_safe() if tool else False

            if is_safe:
                current_group.append(tu)
            else:
                # Flush current safe group, then add unsafe tool as solo
                if current_group:
                    groups.append(current_group)
                    current_group = []
                groups.append([tu])

        if current_group:
            groups.append(current_group)

        return groups

    async def _run_concurrent(
        self,
        group: list[ToolUseBlock],
    ) -> AsyncGenerator[SessionEvent, None]:
        """Execute multiple safe tools concurrently, yielding events in order.

        Uses per-tool queues to collect events, then yields them in
        tool-use order for deterministic output.
        """
        queues: list[asyncio.Queue[SessionEvent | None]] = [
            asyncio.Queue() for _ in group
        ]

        async def _worker(idx: int, tu: ToolUseBlock) -> None:
            """Run a single tool and push events into its queue."""
            try:
                async for event in self._execute_single(tu):
                    await queues[idx].put(event)
            except Exception as exc:
                logger.error("Concurrent tool error: %s — %s", tu.name, exc)
                await queues[idx].put(SessionEvent(
                    type=SessionEventType.TOOL_RESULT,
                    data={
                        "tool_use_id": tu.id,
                        "tool_name": tu.name,
                        "result": f"Tool error: {exc}",
                        "is_error": True,
                    },
                ))
            finally:
                # Sentinel: signals this worker is done
                await queues[idx].put(None)

        tasks = [
            asyncio.create_task(_worker(i, tu))
            for i, tu in enumerate(group)
        ]

        try:
            # Yield events in tool-use order
            for idx, _tu in enumerate(group):
                while True:
                    if self._abort_event.is_set():
                        for t in tasks:
                            t.cancel()
                        return

                    event = await queues[idx].get()
                    if event is None:
                        break
                    yield event
        finally:
            for t in tasks:
                if not t.done():
                    t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    def _find_tool(self, name: str) -> Tool | None:
        """Find a tool by name."""
        for t in self._tools:
            if t.name == name:
                return t  # type: ignore[no-any-return]
        return None
