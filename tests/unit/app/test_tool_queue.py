"""Tests for concurrent ToolUseQueue."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import MagicMock

import pytest

from pode_agent.app.tool_queue import ToolUseQueue
from pode_agent.services.ai.base import ToolUseBlock
from pode_agent.types.session_events import SessionEvent, SessionEventType


def _make_tool(name: str, *, concurrency_safe: bool = False) -> MagicMock:
    tool = MagicMock()
    tool.name = name
    tool.is_concurrency_safe = MagicMock(return_value=concurrency_safe)
    return tool


def _make_tool_use(name: str, tool_use_id: str | None = None) -> ToolUseBlock:
    return ToolUseBlock(
        id=tool_use_id or f"tu_{name}",
        name=name,
        input={"test": True},
    )


async def _single_tool_executor(
    tool_use: ToolUseBlock,
) -> AsyncGenerator[SessionEvent, None]:
    """Simple mock executor that yields start + result events."""
    yield SessionEvent(
        type=SessionEventType.TOOL_USE_START,
        data={"tool_name": tool_use.name, "tool_use_id": tool_use.id},
    )
    yield SessionEvent(
        type=SessionEventType.TOOL_RESULT,
        data={
            "tool_use_id": tool_use.id,
            "tool_name": tool_use.name,
            "result": f"Result of {tool_use.name}",
            "is_error": False,
        },
    )


class TestGroupByConcurrency:
    """Tests for _group_by_concurrency method."""

    def test_all_unsafe_separate_groups(self) -> None:
        tools = [_make_tool("a"), _make_tool("b")]
        queue = ToolUseQueue(
            tool_uses=[_make_tool_use("a"), _make_tool_use("b")],
            tools=tools,
            execute_single=_single_tool_executor,
            abort_event=asyncio.Event(),
        )
        groups = queue._group_by_concurrency()
        assert len(groups) == 2
        assert len(groups[0]) == 1
        assert len(groups[1]) == 1

    def test_all_safe_one_group(self) -> None:
        tools = [_make_tool("a", concurrency_safe=True), _make_tool("b", concurrency_safe=True)]
        queue = ToolUseQueue(
            tool_uses=[_make_tool_use("a"), _make_tool_use("b")],
            tools=tools,
            execute_single=_single_tool_executor,
            abort_event=asyncio.Event(),
        )
        groups = queue._group_by_concurrency()
        assert len(groups) == 1
        assert len(groups[0]) == 2

    def test_mixed_safe_unsafe(self) -> None:
        tools = [
            _make_tool("s1", concurrency_safe=True),
            _make_tool("s2", concurrency_safe=True),
            _make_tool("u1", concurrency_safe=False),
            _make_tool("s3", concurrency_safe=True),
            _make_tool("u2", concurrency_safe=False),
        ]
        queue = ToolUseQueue(
            tool_uses=[_make_tool_use(n) for n in ["s1", "s2", "u1", "s3", "u2"]],
            tools=tools,
            execute_single=_single_tool_executor,
            abort_event=asyncio.Event(),
        )
        groups = queue._group_by_concurrency()
        assert len(groups) == 4
        # [s1, s2], [u1], [s3], [u2]
        assert [tu.name for tu in groups[0]] == ["s1", "s2"]
        assert [tu.name for tu in groups[1]] == ["u1"]
        assert [tu.name for tu in groups[2]] == ["s3"]
        assert [tu.name for tu in groups[3]] == ["u2"]

    def test_unknown_tool_treated_unsafe(self) -> None:
        queue = ToolUseQueue(
            tool_uses=[_make_tool_use("unknown")],
            tools=[],
            execute_single=_single_tool_executor,
            abort_event=asyncio.Event(),
        )
        groups = queue._group_by_concurrency()
        assert len(groups) == 1
        assert len(groups[0]) == 1


class TestToolUseQueueRun:
    """Tests for the run() method."""

    async def test_serial_execution_unsafe_tools(self) -> None:
        tools = [_make_tool("a"), _make_tool("b")]
        queue = ToolUseQueue(
            tool_uses=[_make_tool_use("a"), _make_tool_use("b")],
            tools=tools,
            execute_single=_single_tool_executor,
            abort_event=asyncio.Event(),
        )
        events = [e async for e in queue.run()]
        # 2 tools × (START + RESULT) = 4 events
        assert len(events) == 4
        assert events[0].type == SessionEventType.TOOL_USE_START
        assert events[0].data["tool_name"] == "a"
        assert events[2].type == SessionEventType.TOOL_USE_START
        assert events[2].data["tool_name"] == "b"

    async def test_concurrent_execution_safe_tools(self) -> None:
        tools = [
            _make_tool("s1", concurrency_safe=True),
            _make_tool("s2", concurrency_safe=True),
        ]
        queue = ToolUseQueue(
            tool_uses=[_make_tool_use("s1"), _make_tool_use("s2")],
            tools=tools,
            execute_single=_single_tool_executor,
            abort_event=asyncio.Event(),
        )
        events = [e async for e in queue.run()]
        # Events yielded in tool-use order
        assert len(events) == 4
        assert events[0].data["tool_name"] == "s1"
        assert events[2].data["tool_name"] == "s2"

    async def test_abort_stops_execution(self) -> None:
        abort = asyncio.Event()
        tools = [_make_tool("a"), _make_tool("b")]
        queue = ToolUseQueue(
            tool_uses=[_make_tool_use("a"), _make_tool_use("b")],
            tools=tools,
            execute_single=_single_tool_executor,
            abort_event=abort,
        )
        abort.set()
        events = [e async for e in queue.run()]
        assert len(events) == 0

    async def test_empty_tool_uses(self) -> None:
        queue = ToolUseQueue(
            tool_uses=[],
            tools=[],
            execute_single=_single_tool_executor,
            abort_event=asyncio.Event(),
        )
        events = [e async for e in queue.run()]
        assert len(events) == 0

    async def test_single_tool(self) -> None:
        tools = [_make_tool("a")]
        queue = ToolUseQueue(
            tool_uses=[_make_tool_use("a")],
            tools=tools,
            execute_single=_single_tool_executor,
            abort_event=asyncio.Event(),
        )
        events = [e async for e in queue.run()]
        assert len(events) == 2
        assert events[0].type == SessionEventType.TOOL_USE_START
        assert events[1].type == SessionEventType.TOOL_RESULT
