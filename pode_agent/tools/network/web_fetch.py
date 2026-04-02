"""WebFetchTool: fetch content from a URL using HTTP GET or POST.

Uses httpx async client for HTTP requests with configurable method,
headers, body, and timeout. Output is truncated at ~50KB to avoid
overwhelming the context window.

Reference: docs/api-specs.md -- Tool System API, WebFetchTool
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field

from pode_agent.core.tools.base import Tool, ToolOutput, ToolUseContext
from pode_agent.infra.logging import get_logger

logger = get_logger(__name__)

MAX_RESPONSE_SIZE = 50_000  # ~50KB


class WebFetchInput(BaseModel):
    """Input schema for WebFetchTool."""

    url: str = Field(description="The URL to fetch")
    method: str = Field(default="GET", description="HTTP method (GET or POST)")
    headers: dict[str, str] | None = Field(
        default=None,
        description="Optional HTTP headers",
    )
    body: str | None = Field(
        default=None,
        description="Request body (for POST requests)",
    )
    timeout: int = Field(default=20, description="Request timeout in seconds")


class WebFetchTool(Tool):
    """Fetch content from a URL using HTTP GET or POST."""

    name: str = "web_fetch"
    description: str = (
        "Fetch content from a URL using HTTP GET or POST. "
        "Returns the response body (truncated at ~50KB) and status code."
    )

    def input_schema(self) -> type[BaseModel]:
        return WebFetchInput

    async def is_enabled(self) -> bool:
        return True

    def is_read_only(self, input: Any = None) -> bool:
        if input is not None:
            method = getattr(input, "method", "GET").upper()
            return method == "GET"
        return True

    def needs_permissions(self, input: Any = None) -> bool:
        if input is not None:
            method = getattr(input, "method", "GET").upper()
            return method != "GET"
        return False

    def is_concurrency_safe(self, input: Any = None) -> bool:
        return True

    async def call(
        self,
        input: BaseModel,
        context: ToolUseContext,
    ) -> AsyncGenerator[ToolOutput, None]:
        assert isinstance(input, WebFetchInput)

        # Validate URL scheme
        parsed = urlparse(input.url)
        if parsed.scheme not in ("http", "https"):
            yield ToolOutput(
                type="result",
                data={"error": f"Unsupported URL scheme: {parsed.scheme}. Only http and https are allowed."},
                result_for_assistant=f"Error: Unsupported URL scheme: {parsed.scheme}. Only http and https are allowed.",
            )
            return

        method = input.method.upper()
        if method not in ("GET", "POST"):
            yield ToolOutput(
                type="result",
                data={"error": f"Unsupported HTTP method: {method}. Only GET and POST are supported."},
                result_for_assistant=f"Error: Unsupported HTTP method: {method}. Only GET and POST are supported.",
            )
            return

        try:
            async with httpx.AsyncClient(timeout=input.timeout) as client:
                request_kwargs: dict[str, Any] = {}
                if input.headers:
                    request_kwargs["headers"] = input.headers
                if input.body and method == "POST":
                    request_kwargs["content"] = input.body

                response = await client.request(
                    method=method,
                    url=input.url,
                    **request_kwargs,
                )

        except httpx.TimeoutException:
            yield ToolOutput(
                type="result",
                data={"error": f"Request timed out after {input.timeout}s"},
                result_for_assistant=f"Error: Request timed out after {input.timeout}s",
            )
            return
        except httpx.ConnectError as exc:
            yield ToolOutput(
                type="result",
                data={"error": f"Connection error: {exc}"},
                result_for_assistant=f"Error: Connection error: {exc}",
            )
            return
        except httpx.HTTPError as exc:
            yield ToolOutput(
                type="result",
                data={"error": f"HTTP error: {exc}"},
                result_for_assistant=f"Error: HTTP error: {exc}",
            )
            return

        # Read and truncate body
        body = response.text
        truncated = len(body) > MAX_RESPONSE_SIZE
        if truncated:
            body = body[:MAX_RESPONSE_SIZE] + "\n... (truncated)"

        yield ToolOutput(
            type="result",
            data={
                "url": input.url,
                "method": method,
                "status_code": response.status_code,
                "body": body,
                "truncated": truncated,
                "content_type": response.headers.get("content-type", ""),
            },
            result_for_assistant=body,
        )

    def render_result_for_assistant(self, output: Any) -> str | list[Any]:
        if isinstance(output, dict) and "error" in output:
            return str(output["error"])
        return str(output)
