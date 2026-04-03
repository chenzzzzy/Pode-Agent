"""Unit tests for BashTool.

Reference: docs/api-specs.md — Tool System API, BashTool
           docs/testing-strategy.md — Phase 1 test requirements
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from pode_agent.core.tools.base import ToolOutput, ToolUseContext
from pode_agent.tools.system.bash import BashInput, BashTool


def _context() -> ToolUseContext:
    return ToolUseContext(abort_event=asyncio.Event())


# ---------------------------------------------------------------------------
# BashInput schema
# ---------------------------------------------------------------------------


class TestBashInput:
    def test_default_timeout(self) -> None:
        inp = BashInput(command="echo hi")
        assert inp.timeout == 120_000

    def test_schema_has_required_command(self) -> None:
        schema = BashInput.model_json_schema()
        assert "command" in schema["properties"]
        assert "command" in schema["required"]


# ---------------------------------------------------------------------------
# BashTool properties
# ---------------------------------------------------------------------------


class TestBashToolProperties:
    def setup_method(self) -> None:
        self.tool = BashTool()

    def test_name_is_bash(self) -> None:
        assert self.tool.name == "bash"

    def test_input_schema_returns_bash_input(self) -> None:
        assert self.tool.input_schema() is BashInput

    @pytest.mark.asyncio
    async def test_is_enabled_returns_true(self) -> None:
        assert await self.tool.is_enabled() is True

    def test_is_read_only_returns_false(self) -> None:
        assert self.tool.is_read_only() is False

    def test_needs_permissions_safe_command(self) -> None:
        inp = BashInput(command="ls -la")
        assert self.tool.needs_permissions(inp) is False

    def test_needs_permissions_dangerous_command(self) -> None:
        inp = BashInput(command="rm -rf /")
        assert self.tool.needs_permissions(inp) is True

    def test_needs_permissions_no_input(self) -> None:
        assert self.tool.needs_permissions() is True

    def test_render_result_for_assistant_with_stdout(self) -> None:
        result = self.tool.render_result_for_assistant({
            "stdout": "hello",
            "stderr": "",
            "exit_code": 0,
            "timed_out": False,
        })
        assert "hello" in result

    def test_render_result_for_assistant_with_errors(self) -> None:
        result = self.tool.render_result_for_assistant({
            "stdout": "",
            "stderr": "error msg",
            "exit_code": 1,
            "timed_out": False,
        })
        assert "error msg" in result
        assert "Exit code: 1" in result

    def test_render_tool_use_message(self) -> None:
        inp = BashInput(command="ls", description="List files")
        msg = self.tool.render_tool_use_message(inp)
        assert "List files" in msg
        assert "ls" in msg


# ---------------------------------------------------------------------------
# BashTool.call()
# ---------------------------------------------------------------------------


class TestBashToolCall:
    def setup_method(self) -> None:
        self.tool = BashTool()

    @pytest.mark.asyncio
    async def test_captures_stdout(self) -> None:
        inp = BashInput(command="echo hello")
        outputs = [o async for o in self.tool.call(inp, _context())]
        result = _find_result(outputs)
        assert result.data["stdout"].strip() == "hello"
        assert result.data["exit_code"] == 0

    @pytest.mark.asyncio
    async def test_captures_stderr(self) -> None:
        inp = BashInput(command="echo error >&2")
        outputs = [o async for o in self.tool.call(inp, _context())]
        result = _find_result(outputs)
        assert "error" in result.data["stderr"]

    @pytest.mark.asyncio
    async def test_captures_exit_code_nonzero(self) -> None:
        inp = BashInput(command="exit 42")
        outputs = [o async for o in self.tool.call(inp, _context())]
        result = _find_result(outputs)
        assert result.data["exit_code"] == 42

    @pytest.mark.asyncio
    async def test_handles_timeout(self) -> None:
        # Use python for cross-platform sleep (Windows lacks 'sleep' command)
        inp = BashInput(
            command='python -c "import time; time.sleep(30)"',
            timeout=500,
        )
        outputs = [o async for o in self.tool.call(inp, _context())]
        result = _find_result(outputs)
        assert result.data["timed_out"] is True
        assert result.data["exit_code"] == -1

    @pytest.mark.asyncio
    async def test_yields_progress_first(self) -> None:
        inp = BashInput(command="echo hi")
        outputs = [o async for o in self.tool.call(inp, _context())]
        assert outputs[0].type == "progress"
        assert outputs[-1].type == "result"

    @pytest.mark.asyncio
    async def test_multiline_output(self) -> None:
        inp = BashInput(command="echo line1 && echo line2")
        outputs = [o async for o in self.tool.call(inp, _context())]
        result = _find_result(outputs)
        assert "line1" in result.data["stdout"]
        assert "line2" in result.data["stdout"]

    @pytest.mark.asyncio
    async def test_background_rejected(self) -> None:
        inp = BashInput(command="echo hi", run_in_background=True)
        validation = await self.tool.validate_input(inp)
        assert validation.result is False


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestBashToolValidation:
    def setup_method(self) -> None:
        self.tool = BashTool()

    @pytest.mark.asyncio
    async def test_empty_command_rejected(self) -> None:
        inp = BashInput(command="  ")
        validation = await self.tool.validate_input(inp)
        assert validation.result is False

    @pytest.mark.asyncio
    async def test_timeout_too_large(self) -> None:
        inp = BashInput(command="echo hi", timeout=700_000)
        validation = await self.tool.validate_input(inp)
        assert validation.result is False

    @pytest.mark.asyncio
    async def test_valid_input_passes(self) -> None:
        inp = BashInput(command="echo hi")
        validation = await self.tool.validate_input(inp)
        assert validation.result is True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_result(outputs: list[ToolOutput]) -> ToolOutput:
    """Return the last result-type ToolOutput."""
    for o in reversed(outputs):
        if o.type == "result":
            return o
    raise AssertionError("No result output found")
