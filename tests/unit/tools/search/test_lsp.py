"""Unit tests for LspTool.

Reference: docs/api-specs.md -- Tool System API, LspTool
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

import pytest

from pode_agent.core.tools.base import ToolOutput, ToolUseContext
from pode_agent.tools.search.lsp import LspInput, LspTool


def _ctx() -> ToolUseContext:
    return ToolUseContext(abort_event=asyncio.Event())


def _find_result(outputs: list[ToolOutput]) -> ToolOutput:
    for o in reversed(outputs):
        if o.type == "result":
            return o
    raise AssertionError("No result output found")


# ---------------------------------------------------------------------------
# LspInput schema
# ---------------------------------------------------------------------------


class TestLspInput:
    def test_valid_actions(self) -> None:
        for action in ("definition", "references", "hover"):
            inp = LspInput(action=action, file_path="/test.py", line=0, character=0)
            assert inp.action == action

    def test_schema_has_required_fields(self) -> None:
        schema = LspInput.model_json_schema()
        required = schema.get("required", [])
        assert "action" in required
        assert "file_path" in required
        assert "line" in required
        assert "character" in required


# ---------------------------------------------------------------------------
# LspTool properties
# ---------------------------------------------------------------------------


class TestLspToolProperties:
    def setup_method(self) -> None:
        self.tool = LspTool()

    def test_name(self) -> None:
        assert self.tool.name == "lsp"

    def test_input_schema(self) -> None:
        assert self.tool.input_schema() is LspInput

    @pytest.mark.asyncio
    async def test_is_enabled(self) -> None:
        assert await self.tool.is_enabled() is True

    def test_is_read_only(self) -> None:
        assert self.tool.is_read_only() is True

    def test_needs_permissions(self) -> None:
        assert self.tool.needs_permissions() is False

    def test_is_concurrency_safe(self) -> None:
        assert self.tool.is_concurrency_safe() is True


# ---------------------------------------------------------------------------
# LspTool.call()
# ---------------------------------------------------------------------------


class TestLspToolCall:
    def setup_method(self) -> None:
        self.tool = LspTool()

    @pytest.mark.asyncio
    async def test_no_language_server_available(self) -> None:
        with patch("pode_agent.tools.search.lsp.shutil.which", return_value=None):
            inp = LspInput(action="definition", file_path="/test.py", line=5, character=10)
            outputs = [o async for o in self.tool.call(inp, _ctx())]
            result = _find_result(outputs)

            assert "error" in result.data
            assert "No language server found" in result.data["error"]

    @pytest.mark.asyncio
    async def test_language_server_available_skeleton(self) -> None:
        with patch("pode_agent.tools.search.lsp.shutil.which", return_value="/usr/bin/pyright-langserver"):
            inp = LspInput(action="hover", file_path="/test.py", line=1, character=0)
            outputs = [o async for o in self.tool.call(inp, _ctx())]
            result = _find_result(outputs)

            assert result.data["status"] == "skeleton"
            assert "hover" in result.data["action"]
            assert result.data["file_path"] == "/test.py"
            assert result.data["line"] == 1
            assert result.data["character"] == 0

    @pytest.mark.asyncio
    async def test_result_text_mentions_phase(self) -> None:
        with patch("pode_agent.tools.search.lsp.shutil.which", return_value=None):
            inp = LspInput(action="references", file_path="/app/main.py", line=10, character=5)
            outputs = [o async for o in self.tool.call(inp, _ctx())]
            result = _find_result(outputs)
            assert "error" in result.data

    def test_render_result_for_assistant_error(self) -> None:
        result = self.tool.render_result_for_assistant({"error": "something broke"})
        assert "something broke" in result

    def test_render_result_for_assistant_message(self) -> None:
        result = self.tool.render_result_for_assistant({"message": "skeleton mode"})
        assert "skeleton mode" in result
