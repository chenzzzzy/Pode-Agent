"""Structured logging configuration.

Uses Python stdlib ``logging`` with Rich handler for coloured terminal
output. Structlog integration is deferred to a later phase.

Usage::

    from pode_agent.infra.logging import get_logger

    logger = get_logger(__name__)
    logger.info("session_started", log_name="2026-03-31_session_fork_0")
"""

from __future__ import annotations

import logging

from rich.console import Console
from rich.logging import RichHandler

_console = Console(stderr=True)
_handler: RichHandler | None = None
_initialized = False

LOG_FORMAT = "%(message)s"
DEFAULT_LEVEL = logging.INFO


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name.

    On first call, configures the root logger with a Rich handler.
    """
    _ensure_initialized()
    return logging.getLogger(name)


def _ensure_initialized() -> None:
    global _initialized, _handler
    if _initialized:
        return

    _handler = RichHandler(
        console=_console,
        show_path=False,
        show_time=True,
        markup=True,
    )
    _handler.setFormatter(logging.Formatter(LOG_FORMAT))

    root = logging.getLogger("pode_agent")
    root.setLevel(DEFAULT_LEVEL)
    root.addHandler(_handler)
    _initialized = True


def set_level(level: int | str) -> None:
    """Change the logging level for all pode_agent loggers."""
    _ensure_initialized()
    logging.getLogger("pode_agent").setLevel(level)
