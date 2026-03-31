"""Async HTTP client factory.

Creates a pre-configured ``httpx.AsyncClient`` with proxy support,
timeout defaults, and a custom User-Agent header.

Reference: docs/tech-stack.md — httpx configuration
"""

from __future__ import annotations

import httpx

from pode_agent import __version__


def create_http_client(
    proxy: str | None = None,
    timeout: float = 30.0,
    connect_timeout: float = 10.0,
    follow_redirects: bool = True,
) -> httpx.AsyncClient:
    """Create a pre-configured async HTTP client.

    Args:
        proxy: Optional proxy URL (e.g. ``http://127.0.0.1:7890``).
        timeout: Total request timeout in seconds.
        connect_timeout: Connection timeout in seconds.
        follow_redirects: Whether to follow HTTP redirects.

    Returns:
        Configured ``httpx.AsyncClient``. Caller is responsible for
        using it as an async context manager or calling ``aclose()``.
    """
    transport = None
    if proxy:
        transport = httpx.AsyncHTTPTransport(proxy=proxy)

    return httpx.AsyncClient(
        transport=transport,
        timeout=httpx.Timeout(timeout, connect=connect_timeout),
        headers={"User-Agent": f"pode-agent/{__version__}"},
        follow_redirects=follow_redirects,
    )
