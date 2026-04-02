"""Unit tests for WebFetchTool.

Reference: docs/api-specs.md -- Tool System API, WebFetchTool
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from pode_agent.core.tools.base import ToolOutput, ToolUseContext
from pode_agent.tools.network.web_fetch import WebFetchInput, WebFetchTool


def _ctx() -> ToolUseContext:
    return ToolUseContext(abort_event=asyncio.Event())


def _find_result(outputs: list[ToolOutput]) -> ToolOutput:
    for o in reversed(outputs):
        if o.type == "result":
            return o
    raise AssertionError("No result output found")


# ---------------------------------------------------------------------------
# WebFetchInput schema
# ---------------------------------------------------------------------------


class TestWebFetchInput:
    def test_defaults(self) -> None:
        inp = WebFetchInput(url="https://example.com")
        assert inp.method == "GET"
        assert inp.headers is None
        assert inp.body is None
        assert inp.timeout == 20

    def test_schema_has_required_url(self) -> None:
        schema = WebFetchInput.model_json_schema()
        assert "url" in schema["properties"]
        assert "url" in schema["required"]


# ---------------------------------------------------------------------------
# WebFetchTool properties
# ---------------------------------------------------------------------------


class TestWebFetchToolProperties:
    def setup_method(self) -> None:
        self.tool = WebFetchTool()

    def test_name(self) -> None:
        assert self.tool.name == "web_fetch"

    def test_input_schema_returns_web_fetch_input(self) -> None:
        assert self.tool.input_schema() is WebFetchInput

    @pytest.mark.asyncio
    async def test_is_enabled(self) -> None:
        assert await self.tool.is_enabled() is True

    def test_is_read_only_get(self) -> None:
        inp = WebFetchInput(url="https://example.com", method="GET")
        assert self.tool.is_read_only(inp) is True

    def test_is_read_only_post(self) -> None:
        inp = WebFetchInput(url="https://example.com", method="POST")
        assert self.tool.is_read_only(inp) is False

    def test_is_read_only_default(self) -> None:
        assert self.tool.is_read_only() is True

    def test_needs_permissions_get(self) -> None:
        inp = WebFetchInput(url="https://example.com", method="GET")
        assert self.tool.needs_permissions(inp) is False

    def test_needs_permissions_post(self) -> None:
        inp = WebFetchInput(url="https://example.com", method="POST")
        assert self.tool.needs_permissions(inp) is True

    def test_needs_permissions_default(self) -> None:
        assert self.tool.needs_permissions() is False

    def test_is_concurrency_safe(self) -> None:
        assert self.tool.is_concurrency_safe() is True


# ---------------------------------------------------------------------------
# WebFetchTool.call()
# ---------------------------------------------------------------------------


class TestWebFetchToolCall:
    def setup_method(self) -> None:
        self.tool = WebFetchTool()

    @pytest.mark.asyncio
    async def test_successful_get(self) -> None:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = "<html>Hello World</html>"
        mock_response.headers = {"content-type": "text/html"}

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("pode_agent.tools.network.web_fetch.httpx.AsyncClient", return_value=mock_client):
            inp = WebFetchInput(url="https://example.com")
            outputs = [o async for o in self.tool.call(inp, _ctx())]
            result = _find_result(outputs)

            assert result.data["status_code"] == 200
            assert "Hello World" in result.data["body"]
            assert result.data["truncated"] is False

    @pytest.mark.asyncio
    async def test_successful_post(self) -> None:
        mock_response = AsyncMock()
        mock_response.status_code = 201
        mock_response.text = '{"created": true}'
        mock_response.headers = {"content-type": "application/json"}

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("pode_agent.tools.network.web_fetch.httpx.AsyncClient", return_value=mock_client):
            inp = WebFetchInput(
                url="https://example.com/api",
                method="POST",
                body='{"key": "value"}',
            )
            outputs = [o async for o in self.tool.call(inp, _ctx())]
            result = _find_result(outputs)

            assert result.data["status_code"] == 201
            assert result.data["method"] == "POST"

    @pytest.mark.asyncio
    async def test_unsupported_scheme_rejected(self) -> None:
        inp = WebFetchInput(url="ftp://example.com/file")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)
        assert "error" in result.data
        assert "Unsupported URL scheme" in result.data["error"]

    @pytest.mark.asyncio
    async def test_unsupported_method_rejected(self) -> None:
        inp = WebFetchInput(url="https://example.com", method="DELETE")
        outputs = [o async for o in self.tool.call(inp, _ctx())]
        result = _find_result(outputs)
        assert "error" in result.data
        assert "Unsupported HTTP method" in result.data["error"]

    @pytest.mark.asyncio
    async def test_timeout_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("pode_agent.tools.network.web_fetch.httpx.AsyncClient", return_value=mock_client):
            inp = WebFetchInput(url="https://example.com", timeout=5)
            outputs = [o async for o in self.tool.call(inp, _ctx())]
            result = _find_result(outputs)
            assert "error" in result.data
            assert "timed out" in result.data["error"]

    @pytest.mark.asyncio
    async def test_connection_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.request = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("pode_agent.tools.network.web_fetch.httpx.AsyncClient", return_value=mock_client):
            inp = WebFetchInput(url="https://example.com")
            outputs = [o async for o in self.tool.call(inp, _ctx())]
            result = _find_result(outputs)
            assert "error" in result.data
            assert "Connection error" in result.data["error"]

    @pytest.mark.asyncio
    async def test_truncates_large_response(self) -> None:
        large_body = "x" * 60_000
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = large_body
        mock_response.headers = {"content-type": "text/plain"}

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("pode_agent.tools.network.web_fetch.httpx.AsyncClient", return_value=mock_client):
            inp = WebFetchInput(url="https://example.com")
            outputs = [o async for o in self.tool.call(inp, _ctx())]
            result = _find_result(outputs)

            assert result.data["truncated"] is True
            assert len(result.data["body"]) < 60_000
            assert "truncated" in result.data["body"]

    @pytest.mark.asyncio
    async def test_custom_headers_passed(self) -> None:
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = "ok"
        mock_response.headers = {}

        mock_client = AsyncMock()
        mock_client.request = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("pode_agent.tools.network.web_fetch.httpx.AsyncClient", return_value=mock_client):
            inp = WebFetchInput(
                url="https://example.com",
                headers={"Authorization": "Bearer token123"},
            )
            outputs = [o async for o in self.tool.call(inp, _ctx())]
            result = _find_result(outputs)
            assert result.data["status_code"] == 200

            # Verify headers were passed
            call_kwargs = mock_client.request.call_args
            assert call_kwargs.kwargs.get("headers") == {"Authorization": "Bearer token123"}

    def test_render_result_for_assistant_error(self) -> None:
        result = self.tool.render_result_for_assistant({"error": "something broke"})
        assert "something broke" in result

    def test_render_result_for_assistant_normal(self) -> None:
        result = self.tool.render_result_for_assistant({"status_code": 200})
        assert "200" in result
