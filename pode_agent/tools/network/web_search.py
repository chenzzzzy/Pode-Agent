"""WebSearchTool: search the web for information using DuckDuckGo.

Uses DuckDuckGo HTML search endpoint to find results without requiring
an API key. Parses the HTML response to extract titles, URLs, and snippets.

Reference: docs/api-specs.md -- Tool System API, WebSearchTool
"""

from __future__ import annotations

import re
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from pydantic import BaseModel, Field

from pode_agent.core.tools.base import Tool, ToolOutput, ToolUseContext
from pode_agent.infra.logging import get_logger

logger = get_logger(__name__)

DDG_HTML_URL = "https://html.duckduckgo.com/html/"


class WebSearchInput(BaseModel):
    """Input schema for WebSearchTool."""

    query: str = Field(description="The search query string")
    limit: int = Field(default=10, description="Maximum number of results to return")


class WebSearchTool(Tool):
    """Search the web for information using DuckDuckGo."""

    name: str = "web_search"
    description: str = (
        "Search the web for information using DuckDuckGo. "
        "Returns a list of results with title, URL, and snippet for each."
    )

    def input_schema(self) -> type[BaseModel]:
        return WebSearchInput

    async def is_enabled(self) -> bool:
        return True

    def is_read_only(self, input: Any = None) -> bool:
        return True

    def needs_permissions(self, input: Any = None) -> bool:
        return False

    def is_concurrency_safe(self, input: Any = None) -> bool:
        return True

    async def call(
        self,
        input: BaseModel,
        context: ToolUseContext,
    ) -> AsyncGenerator[ToolOutput, None]:
        assert isinstance(input, WebSearchInput)

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(
                    DDG_HTML_URL,
                    data={"q": input.query, "b": ""},
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/120.0.0.0 Safari/537.36"
                        ),
                    },
                )
        except httpx.HTTPError as exc:
            yield ToolOutput(
                type="result",
                data={"error": f"Search request failed: {exc}"},
                result_for_assistant=f"Error: Search request failed: {exc}",
            )
            return

        if response.status_code != 200:
            yield ToolOutput(
                type="result",
                data={"error": f"Search returned status {response.status_code}"},
                result_for_assistant=f"Error: Search returned status {response.status_code}",
            )
            return

        results = _parse_ddg_html(response.text, limit=input.limit)

        if not results:
            yield ToolOutput(
                type="result",
                data={"results": [], "total": 0, "query": input.query},
                result_for_assistant=f"No results found for: {input.query}",
            )
            return

        # Format for assistant
        lines: list[str] = []
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r['title']}\n   {r['url']}\n   {r['snippet']}")
        result_text = "\n\n".join(lines)

        yield ToolOutput(
            type="result",
            data={
                "results": results,
                "total": len(results),
                "query": input.query,
            },
            result_for_assistant=result_text,
        )

    def render_result_for_assistant(self, output: Any) -> str | list[Any]:
        if isinstance(output, dict) and "error" in output:
            return str(output["error"])
        return str(output)


def _parse_ddg_html(html: str, limit: int = 10) -> list[dict[str, str]]:
    """Parse DuckDuckGo HTML search results into structured data."""
    results: list[dict[str, str]] = []

    # Match result blocks in DDG HTML
    # Each result is in a <div class="result..."> block
    result_pattern = re.compile(
        r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a.*?'
        r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
        re.DOTALL,
    )

    for match in result_pattern.finditer(html):
        if len(results) >= limit:
            break

        url = match.group(1)
        title = _strip_tags(match.group(2)).strip()
        snippet = _strip_tags(match.group(3)).strip()

        # DDG uses redirect URLs; extract the actual URL from the ud= parameter
        url = _extract_real_url(url)

        if title and url:
            results.append({
                "title": title,
                "url": url,
                "snippet": snippet,
            })

    return results


def _strip_tags(text: str) -> str:
    """Remove HTML tags from text."""
    return re.sub(r"<[^>]+>", "", text)


def _extract_real_url(url: str) -> str:
    """Extract the real URL from a DuckDuckGo redirect URL."""
    # DDG URLs look like: //duckduckgo.com/l/?uddg=<encoded_url>&...
    match = re.search(r"uddg=([^&]+)", url)
    if match:
        from urllib.parse import unquote
        return unquote(match.group(1))
    # If not a redirect, return as-is (strip leading //)
    if url.startswith("//"):
        return "https:" + url
    return url
