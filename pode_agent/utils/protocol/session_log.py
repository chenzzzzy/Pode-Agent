"""JSONL session log: append and read conversation messages.

Each log file is stored as newline-delimited JSON (JSONL), one message
per line, under ``~/.pode/logs/``.

Reference: docs/api-specs.md — Session Log API
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pode_agent.core.config.defaults import get_config_dir
from pode_agent.infra.logging import get_logger

logger = get_logger(__name__)


def get_session_log_path(
    fork_number: int = 0,
    *,
    base_dir: Path | None = None,
) -> Path:
    """Return the log file path for the current session.

    Format: ``~/.pode/logs/YYYY-MM-DD_session_fork_N.jsonl``
    """
    if base_dir is None:
        base_dir = get_config_dir() / "logs"
    base_dir.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now().strftime("%Y-%m-%d")
    filename = f"{date_str}_session_fork_{fork_number}.jsonl"
    return base_dir / filename


def save_message(log_path: Path, message: dict[str, Any]) -> None:
    """Append a single message to the JSONL log file.

    Each call writes one JSON object followed by a newline.
    """
    line = json.dumps(message, default=str, ensure_ascii=False)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_messages_from_log(log_path: Path) -> list[dict[str, Any]]:
    """Read all messages from a JSONL log file.

    Corrupted lines are logged as warnings and skipped.
    Returns an empty list if the file does not exist.
    """
    if not log_path.exists():
        return []

    messages: list[dict[str, Any]] = []
    with open(log_path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                messages.append(json.loads(line))
            except json.JSONDecodeError:
                logger.warning("Skipping corrupted line %d in %s", line_num, log_path)

    return messages
