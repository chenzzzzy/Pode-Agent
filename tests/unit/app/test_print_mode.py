"""Tests for app/print_mode.py — Print mode execution."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from pode_agent.app.print_mode import PrintModeOptions, run_print_mode
from pode_agent.core.permissions.types import PermissionMode
from pode_agent.types.session_events import SessionEvent, SessionEventType


class TestPrintModeSuccess:
    @patch("pode_agent.app.print_mode.SessionManager")
    async def test_text_output_returns_0(self, mock_sm_cls: MagicMock) -> None:
        events = [
            SessionEvent(type=SessionEventType.ASSISTANT_DELTA, data={"text": "Hello"}),
            SessionEvent(type=SessionEventType.ASSISTANT_DELTA, data={"text": " world"}),
            SessionEvent(type=SessionEventType.DONE, data={}),
        ]

        async def mock_input(prompt: str, **kwargs: Any) -> Any:
            for ev in events:
                yield ev

        mock_sm_cls.return_value.process_input = mock_input
        mock_sm_cls.return_value.get_total_cost.return_value = 0.0

        opts = PrintModeOptions()
        exit_code = await run_print_mode("hi", [], opts)
        assert exit_code == 0

    @patch("pode_agent.app.print_mode.SessionManager")
    async def test_json_output(self, mock_sm_cls: MagicMock, capsys: Any) -> None:
        events = [
            SessionEvent(type=SessionEventType.ASSISTANT_DELTA, data={"text": "test"}),
            SessionEvent(type=SessionEventType.DONE, data={}),
        ]

        async def mock_input(prompt: str, **kwargs: Any) -> Any:
            for ev in events:
                yield ev

        mock_sm_cls.return_value.process_input = mock_input
        mock_sm_cls.return_value.get_total_cost.return_value = 0.01

        opts = PrintModeOptions(output_format="json")
        exit_code = await run_print_mode("hi", [], opts)
        assert exit_code == 0

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["text"] == "test"
        assert "cost_usd" in data


class TestPrintModeErrors:
    @patch("pode_agent.app.print_mode.SessionManager")
    async def test_model_error_returns_1(self, mock_sm_cls: MagicMock) -> None:
        events = [
            SessionEvent(
                type=SessionEventType.MODEL_ERROR,
                data={"error": "API failed"},
            ),
        ]

        async def mock_input(prompt: str, **kwargs: Any) -> Any:
            for ev in events:
                yield ev

        mock_sm_cls.return_value.process_input = mock_input
        mock_sm_cls.return_value.get_total_cost.return_value = 0.0

        opts = PrintModeOptions()
        exit_code = await run_print_mode("hi", [], opts)
        assert exit_code == 1

    @patch("pode_agent.app.print_mode.SessionManager")
    async def test_permission_denied_returns_2(self, mock_sm_cls: MagicMock) -> None:
        events = [
            SessionEvent(
                type=SessionEventType.PERMISSION_REQUEST,
                data={"tool_name": "bash"},
            ),
        ]

        async def mock_input(prompt: str, **kwargs: Any) -> Any:
            for ev in events:
                yield ev

        mock_sm_cls.return_value.process_input = mock_input
        mock_sm_cls.return_value.get_total_cost.return_value = 0.0

        opts = PrintModeOptions()
        exit_code = await run_print_mode("hi", [], opts)
        assert exit_code == 2
