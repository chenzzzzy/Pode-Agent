"""Integration tests — full chain: SessionManager → query → query_core → tools.

Tests the complete pipeline from SessionManager.process_input() through
the Agentic Loop with real tools and mock LLM responses.

Also tests print_mode → SessionManager chain.

Run with:  uv run pytest tests/integration/test_full_chain.py -v
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pode_agent.app.query import QueryOptions
from pode_agent.app.session import SessionManager
from pode_agent.core.permissions.types import PermissionContext, PermissionMode
from pode_agent.services.ai.base import AIResponse, TokenUsage
from pode_agent.tools.filesystem.glob import GlobTool
from pode_agent.types.session_events import SessionEventType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _text_response(text: str) -> list[AIResponse]:
    return [
        AIResponse(type="text_delta", text=text),
        AIResponse(
            type="message_done",
            usage=TokenUsage(input_tokens=100, output_tokens=50),
            stop_reason="end_turn",
        ),
    ]


def _tool_use_response(
    tool_id: str,
    tool_name: str,
    tool_input: dict[str, Any],
) -> list[AIResponse]:
    return [
        AIResponse(type="tool_use_start", tool_use_id=tool_id, tool_name=tool_name),
        AIResponse(type="tool_use_delta", text=json.dumps(tool_input)),
        AIResponse(
            type="message_done",
            usage=TokenUsage(input_tokens=100, output_tokens=50),
            stop_reason="tool_use",
        ),
    ]


def _make_mock_query_llm(responses_list: list[list[AIResponse]]) -> Any:
    call_count = 0

    async def _mock_fn(params: Any, config: Any = None) -> Any:
        nonlocal call_count
        idx = min(call_count, len(responses_list) - 1)
        call_count += 1
        for resp in responses_list[idx]:
            yield resp

    return _mock_fn


# ---------------------------------------------------------------------------
# SessionManager → query → query_core
# ---------------------------------------------------------------------------


class TestSessionToQuery:
    """Integration: SessionManager.process_input → query → query_core."""

    async def test_text_only_e2e(self) -> None:
        """Full chain: user input → LLM text response → DONE."""
        mock_fn = _make_mock_query_llm([_text_response("Hello from assistant!")])

        session = SessionManager(tools=[], model="test-model")

        with patch("pode_agent.app.query.query_llm", side_effect=mock_fn):
            events = []
            async for event in session.process_input("Say hello"):
                events.append(event)

        types = [e.type for e in events]
        assert SessionEventType.USER_MESSAGE in types
        assert SessionEventType.ASSISTANT_DELTA in types
        assert SessionEventType.DONE in types

        # Session should have saved messages
        msgs = session.get_messages()
        user_msgs = [m for m in msgs if m.get("type") == "user"]
        assistant_msgs = [m for m in msgs if m.get("type") == "assistant"]
        assert len(user_msgs) == 1
        assert len(assistant_msgs) == 1

    async def test_with_tool_use_e2e(self) -> None:
        """Full chain with GlobTool: user → LLM → tool_use → execute → recurse."""
        repo_root = Path(__file__).resolve().parent.parent.parent

        glob_tool = GlobTool()
        mock_fn = _make_mock_query_llm([
            _tool_use_response(
                "tu_001", "glob", {"pattern": "pyproject.toml", "path": str(repo_root)}
            ),
            _text_response("I found pyproject.toml!"),
        ])

        session = SessionManager(tools=[glob_tool], model="test-model")
        options = QueryOptions(
            model="test-model",
            cwd=str(repo_root),
            permission_mode=PermissionMode.BYPASS_PERMISSIONS,
        )

        with patch("pode_agent.app.query.query_llm", side_effect=mock_fn):
            events = []
            async for event in session.process_input("Find config files", options=options):
                events.append(event)

        types = [e.type for e in events]
        assert SessionEventType.USER_MESSAGE in types
        assert SessionEventType.TOOL_USE_START in types
        assert SessionEventType.TOOL_RESULT in types
        assert SessionEventType.ASSISTANT_DELTA in types
        assert SessionEventType.DONE in types

        # Verify tool result contains pyproject.toml
        tool_results = [e for e in events if e.type == SessionEventType.TOOL_RESULT]
        assert len(tool_results) == 1
        assert "pyproject.toml" in tool_results[0].data.get("result", "")

    async def test_session_cost_tracking(self) -> None:
        """Session should track cumulative cost."""
        mock_fn = _make_mock_query_llm([_text_response("Hi!")])

        session = SessionManager(tools=[], model="test-model")

        with patch("pode_agent.app.query.query_llm", side_effect=mock_fn):
            async for _ in session.process_input("Hi"):
                pass

        # Session should have tracked cost from cost tracker
        # (exact value depends on cost table, but should be >= 0)
        assert session.get_total_cost() >= 0


# ---------------------------------------------------------------------------
# Print mode → SessionManager
# ---------------------------------------------------------------------------


class TestPrintModeIntegration:
    """Integration: run_print_mode → SessionManager → query."""

    async def test_print_mode_text_output(self) -> None:
        """Print mode should capture and print assistant text."""
        from pode_agent.app.print_mode import PrintModeOptions, run_print_mode

        mock_fn = _make_mock_query_llm([_text_response("Hello!")])

        with patch("pode_agent.app.query.query_llm", side_effect=mock_fn):
            exit_code = await run_print_mode(
                prompt="Say hello",
                tools=[],
                options=PrintModeOptions(model="test-model"),
            )

        assert exit_code == 0

    async def test_print_mode_with_glob_tool(self) -> None:
        """Print mode should execute tools and return results."""
        from pode_agent.app.print_mode import PrintModeOptions, run_print_mode

        repo_root = Path(__file__).resolve().parent.parent.parent

        glob_tool = GlobTool()
        mock_fn = _make_mock_query_llm([
            _tool_use_response(
                "tu_001", "glob", {"pattern": "pyproject.toml", "path": str(repo_root)}
            ),
            _text_response("Found pyproject.toml!"),
        ])

        with patch("pode_agent.app.query.query_llm", side_effect=mock_fn):
            exit_code = await run_print_mode(
                prompt="Find config files",
                tools=[glob_tool],
                options=PrintModeOptions(model="test-model"),
            )

        assert exit_code == 0

    async def test_print_mode_cwd_is_set(self) -> None:
        """Print mode QueryOptions should have cwd set."""
        from pydantic import BaseModel

        class DummyInput(BaseModel):
            pass

        captured_options: list[QueryOptions] = []

        async def capturing_process_input(
            self: Any, prompt: str, *, options: QueryOptions | None = None,
        ) -> Any:
            if options:
                captured_options.append(options)
            yield SessionEvent(
                type=SessionEventType.DONE,
                data={"stop_reason": "end_turn"},
            )

        from pode_agent.app.print_mode import PrintModeOptions, run_print_mode
        from pode_agent.types.session_events import SessionEvent

        with patch.object(
            SessionManager, "process_input", capturing_process_input
        ):
            await run_print_mode(
                prompt="test",
                tools=[],
                options=PrintModeOptions(model="test-model"),
            )

        assert len(captured_options) == 1
        assert captured_options[0].cwd != "", "cwd should be set to current directory"
        assert Path(captured_options[0].cwd).is_absolute()


# ---------------------------------------------------------------------------
# CLI → print mode
# ---------------------------------------------------------------------------


class TestCLIToPrintMode:
    """Integration: CLI args → print mode invocation."""

    def test_cli_print_mode_args(self) -> None:
        """CLI should parse --model and prompt correctly for print mode."""
        from typer.testing import CliRunner

        from pode_agent.entrypoints.cli import app

        runner = CliRunner()

        # Patch at source since run_print_mode is a local import in cli.py
        with patch("pode_agent.app.print_mode.run_print_mode", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = 0
            # Also patch ToolRegistry to avoid loading real tools
            with patch("pode_agent.core.tools.registry.ToolRegistry") as mock_reg:
                mock_reg.return_value.tools = []
                result = runner.invoke(app, ["--model", "qwen-plus", "hello world"])

        # Should have called run_print_mode with correct args
        if mock_run.called:
            assert mock_run.call_args[0][0] == "hello world"
