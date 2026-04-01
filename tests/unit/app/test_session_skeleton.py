"""Unit tests for SessionManager skeleton.

Reference: docs/api-specs.md — Session API
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from pode_agent.app.session import SessionManager
from pode_agent.tools.system.bash import BashTool


class TestSessionManagerInit:
    def test_creates_with_defaults(self) -> None:
        sm = SessionManager()
        assert sm.get_messages() == []
        assert sm.tools == []

    def test_creates_with_initial_messages(self) -> None:
        msgs = [{"type": "user", "message": "hello"}]
        sm = SessionManager(initial_messages=msgs)
        assert len(sm.get_messages()) == 1

    def test_has_tools_list(self) -> None:
        tools = [BashTool()]
        sm = SessionManager(tools=tools)
        assert len(sm.tools) == 1
        assert sm.tools[0].name == "bash"


class TestSessionManagerSaveMessage:
    def test_save_message_writes_to_log(self, tmp_path: Any) -> None:
        sm = SessionManager()
        # Override log path to tmp
        sm._log_path = tmp_path / "test.jsonl"

        sm.save_message({"type": "user", "message": "test"})

        assert len(sm.get_messages()) == 1
        assert sm._log_path.exists()

    def test_get_messages_returns_copy(self) -> None:
        sm = SessionManager()
        msgs = sm.get_messages()
        msgs.append({"foo": "bar"})
        assert len(sm.get_messages()) == 0  # original unchanged


class TestSessionManagerAbort:
    def test_abort_sets_event(self) -> None:
        sm = SessionManager()
        assert not sm.abort_event.is_set()
        sm.abort()
        assert sm.abort_event.is_set()
