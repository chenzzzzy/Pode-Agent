"""Default configuration values."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_CONFIG_DIR = "~/.pode"
DEFAULT_CONFIG_FILE = "config.json"
DEFAULT_MODEL_NAME = "claude-sonnet-4-5-20251101"
DEFAULT_THEME = "dark"


def get_config_dir() -> Path:
    """Return the resolved config directory path.

    Checks ``PODE_CONFIG_DIR`` env var on every call so that
    tests can override via ``monkeypatch.setenv``.
    """
    raw = os.environ.get("PODE_CONFIG_DIR", DEFAULT_CONFIG_DIR)
    return Path(raw).expanduser().resolve()


def get_config_path() -> Path:
    """Return the resolved global config file path."""
    return get_config_dir() / DEFAULT_CONFIG_FILE
