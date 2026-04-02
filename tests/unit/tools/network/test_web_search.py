"""Unit tests for WebSearchTool.

Reference: docs/api-specs.md -- Tool System API, WebSearchTool
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from pode_agent.core.tools.base import ToolOutput, ToolUseContext
from pode_agent.tools.network.web_search import WebSearchInput, WebSearchTool


def _ctx() -> ToolUseContext:
    return ToolUseContext(abort_event=asyncio.Event())


def _find_result(outputs: list[ToolOutput]) -> ToolOutput:
    for o in reversed(outputs):
        if o.type == "result":
            return o
    raise AssertionError("No result output found")


# Sample DDG HTML response
_DDG_HTML = """
<div class="result results_links results_links_deep web-result">
    <div class="links_main links_deep result__body">
        <h2 class="result__title">
            <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpage1&amp;rut=abc">
                Example Result 1
            </a>
        </h2>
        <a class="result__snippet" href="#">
            This is the first search result snippet.
        </a>
    </div>
</div>
<div class="result results_links results_links_deep web-result">
    <div class="links_main links_deep result__body">
        <h2 class="result__title">
            <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpage2&amp;rut=def">
                Example Result 2
            </a>
        </h2>
        <a class="result__snippet" href="#">
            This is the second search result snippet.
        </a>
    </div>
</div>
"""

_DDG_HTML_EMPTY = "<html><body>No results here.</body></html>"


# ---------------------------------------------------------------------------
# WebSearchInput schema
# ---------------------------------------------------------------------------


class TestWebSearchInput:
    def test_defaults(self) -> None:
        inp = WebSearchInput(query="test")
        assert inp.limit == 10

    def test_schema_has_required_query(self) -> None:
        schema = WebSearchInput.model_json_schema()
        assert "query" in schema["properties"]
        assert "query" in schema["required"]


# ---------------------------------------------------------------------------
# WebSearchTool properties
# ---------------------------------------------------------------------------


class TestWebSearchToolProperties:
    def setup_method(self) -> None:
        self.tool = WebSearchTool()

    def test_name(self) -> None:
        assert self.tool.name == "web_search"

    def test_input_schema(self) -> None:
        assert self.tool.input_schema() is WebSearchInput

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
# WebSearchTool.call()
# ---------------------------------------------------------------------------


class TestWebSearchToolCall:
    def setup_method(self) -> None:
        self.tool = WebSearchTool()

    @pytest.mark.asyncio
    async def test_returns_search_results(self) -> None:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = _DDG_HTML

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("pode_agent.tools.network.web_search.httpx.AsyncClient", return_value=mock_client):
            inp = WebSearchInput(query="test query")
            outputs = [o async for o in self.tool.call(inp, _ctx())]
            result = _find_result(outputs)

            assert result.data["total"] == 2
            assert result.data["query"] == "test query"
            assert len(result.data["results"]) == 2
            assert result.data["results"][0]["title"] == "Example Result 1"
            assert "example.com" in result.data["results"][0]["url"]

    @pytest.mark.asyncio
    async def test_no_results(self) -> None:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = _DDG_HTML_EMPTY

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("pode_agent.tools.network.web_search.httpx.AsyncClient", return_value=mock_client):
            inp = WebSearchInput(query="obscure query with no results")
            outputs = [o async for o in self.tool.call(inp, _ctx())]
            result = _find_result(outputs)

            assert result.data["total"] == 0
            assert result.data["results"] == []

    @pytest.mark.asyncio
    async def test_respects_limit(self) -> None:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = _DDG_HTML

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("pode_agent.tools.network.web_search.httpx.AsyncClient", return_value=mock_client):
            inp = WebSearchInput(query="test", limit=1)
            outputs = [o async for o in self.tool.call(inp, _ctx())]
            result = _find_result(outputs)

            assert result.data["total"] == 1

    @pytest.mark.asyncio
    async def test_http_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=httpx.HTTPError("network error"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("pode_agent.tools.network.web_search.httpx.AsyncClient", return_value=mock_client):
            inp = WebSearchInput(query="test")
            outputs = [o async for o in self.tool.call(inp, _ctx())]
            result = _find_result(outputs)

            assert "error" in result.data
            assert "failed" in result.data["error"]

    @pytest.mark.asyncio
    async def test_non_200_status(self) -> None:
        mock_response = AsyncMock()
        mock_response.status_code = 503
        mock_response.text = "Service Unavailable"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("pode_agent.tools.network.web_search.httpx.AsyncClient", return_value=mock_client):
            inp = WebSearchInput(query="test")
            outputs = [o async for o in self.tool.call(inp, _ctx())]
            result = _find_result(outputs)

            assert "error" in result.data
            assert "503" in result.data["error"]

    @pytest.mark.asyncio
    async def test_result_text_formatted(self) -> None:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = _DDG_HTML

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("pode_agent.tools.network.web_search.httpx.AsyncClient", return_value=mock_client):
            inp = WebSearchInput(query="test query")
            outputs = [o async for o in self.tool.call(inp, _ctx())]
            result = _find_result(outputs)

            # Should be numbered list
            assert "1." in result.result_for_assistant
            assert "2." in result.result_for_assistant

    def test_render_result_for_assistant_error(self) -> None:
        result = self.tool.render_result_for_assistant({"error": "search failed"})
        assert "search failed" in result
