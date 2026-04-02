"""Unit tests for KillShellTool.

Reference: docs/api-specs.md -- Tool System API, KillShellTool
"""

from __future__ import annotations

import asyncio
import signal
import sys
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pode_agent.core.tools.base import ToolOutput, ToolUseContext
from pode_agent.tools.system.kill_shell import KillShellInput, KillShellTool


def _ctx() -> ToolUseContext:
    return ToolUseContext(abort_event=asyncio.Event())


def _find_result(outputs: list[ToolOutput]) -> ToolOutput:
    for o in reversed(outputs):
        if o.type == "result":
            return o
    raise AssertionError("No result output found")


# ---------------------------------------------------------------------------
# KillShellInput schema
# ---------------------------------------------------------------------------


class TestKillShellInput:
    def test_defaults(self) -> None:
        inp = KillShellInput(pid=1234)
        assert inp.signal == "SIGTERM"

    def test_schema_has_required_pid(self) -> None:
        schema = KillShellInput.model_json_schema()
        assert "pid" in schema["properties"]
        assert "pid" in schema["required"]


# ---------------------------------------------------------------------------
# KillShellTool properties
# ---------------------------------------------------------------------------


class TestKillShellToolProperties:
    def setup_method(self) -> None:
        self.tool = KillShellTool()

    def test_name(self) -> None:
        assert self.tool.name == "kill_shell"

    def test_input_schema(self) -> None:
        assert self.tool.input_schema() is KillShellInput

    @pytest.mark.asyncio
    async def test_is_enabled(self) -> None:
        assert await self.tool.is_enabled() is True

    def test_is_read_only(self) -> None:
        assert self.tool.is_read_only() is False

    def test_needs_permissions(self) -> None:
        assert self.tool.needs_permissions() is True

    def test_is_concurrency_safe(self) -> None:
        assert self.tool.is_concurrency_safe() is False


# ---------------------------------------------------------------------------
# KillShellTool.call()
# ---------------------------------------------------------------------------


class TestKillShellToolCall:
    def setup_method(self) -> None:
        self.tool = KillShellTool()

    @pytest.mark.asyncio
    async def test_invalid_pid_rejected(self) -> None:
        inp = KillShellInput(pid=-1)
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)
        assert "error" in result.data
        assert "Invalid PID" in result.data["error"]

    @pytest.mark.asyncio
    async def test_invalid_pid_zero(self) -> None:
        inp = KillShellInput(pid=0)
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)
        assert "error" in result.data

    @pytest.mark.asyncio
    async def test_unsupported_signal_rejected(self) -> None:
        inp = KillShellInput(pid=1234, signal="SIGUSR99")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)
        assert "error" in result.data
        assert "Unsupported signal" in result.data["error"]

    @pytest.mark.asyncio
    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
    async def test_unix_kill_success(self) -> None:
        with patch("pode_agent.tools.system.kill_shell.os.kill") as mock_kill:
            inp = KillShellInput(pid=1234, signal="SIGTERM")
            outputs = [o async for o in self.tool.call(inp, _ctx())]
            result = _find_result(outputs)

            mock_kill.assert_called_once_with(1234, signal.SIGTERM)
            assert result.data["pid"] == 1234
            assert "SIGTERM" in result.data["signal"]

    @pytest.mark.asyncio
    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
    async def test_unix_kill_process_not_found(self) -> None:
        with patch("pode_agent.tools.system.kill_shell.os.kill", side_effect=ProcessLookupError):
            inp = KillShellInput(pid=99999)
            outputs = [o async for o in self.tool.call(inp, _ctx())]
            result = _find_result(outputs)

            assert "error" in result.data
            assert "not found" in result.data["error"]

    @pytest.mark.asyncio
    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
    async def test_unix_kill_permission_denied(self) -> None:
        with patch("pode_agent.tools.system.kill_shell.os.kill", side_effect=PermissionError):
            inp = KillShellInput(pid=1)
            outputs = [o async for o in self.tool.call(inp, _ctx())]
            result = _find_result(outputs)

            assert "error" in result.data
            assert "Permission denied" in result.data["error"]

    def test_render_result_for_assistant_error(self) -> None:
        result = self.tool.render_result_for_assistant({"error": "process not found"})
        assert "process not found" in result

    def test_render_result_for_assistant_normal(self) -> None:
        result = self.tool.render_result_for_assistant({"pid": 1234, "signal": "SIGTERM"})
        assert "1234" in result
