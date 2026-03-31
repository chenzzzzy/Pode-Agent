"""Configuration loader: read/write config files with atomic writes.

Reference: docs/api-specs.md — Config API (get/set/save/list functions)
"""

from __future__ import annotations

import json
import logging
import operator
from functools import reduce
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from pode_agent.core.config.defaults import get_config_path
from pode_agent.core.config.schema import GlobalConfig, ProjectConfig
from pode_agent.infra.fs import atomic_write

logger = logging.getLogger(__name__)

_global_config_cache: GlobalConfig | None = None


class ConfigError(Exception):
    """Configuration read/write error."""


def get_global_config(*, refresh: bool = False) -> GlobalConfig:
    """Read ~/.pode/config.json, returning defaults if missing or corrupt.

    Args:
        refresh: Force re-read from disk (bypass in-memory cache).
    """
    global _global_config_cache
    if _global_config_cache is not None and not refresh:
        return _global_config_cache

    config_path = get_config_path()
    if not config_path.exists():
        _global_config_cache = GlobalConfig()
        return _global_config_cache

    try:
        raw = config_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        _global_config_cache = GlobalConfig.model_validate(data)
        return _global_config_cache
    except (json.JSONDecodeError, ValidationError) as e:
        logger.warning("Config file corrupt (%s), using defaults: %s", config_path, e)
        _global_config_cache = GlobalConfig()
        return _global_config_cache


def save_global_config(config: GlobalConfig) -> None:
    """Atomically write global config to ~/.pode/config.json."""
    global _global_config_cache
    config_path = get_config_path()
    config_dir = config_path.parent
    config_dir.mkdir(parents=True, exist_ok=True)

    content = config.model_dump_json(indent=2)
    atomic_write(config_path, content)

    _global_config_cache = config


def get_current_project_config() -> ProjectConfig:
    """Read project config (.pode.json) from cwd, walking up to git root."""
    start = Path.cwd()
    config_path = _find_project_config(start)
    if config_path is None:
        return ProjectConfig()

    try:
        raw = config_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        return ProjectConfig.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as e:
        logger.warning("Project config corrupt (%s): %s", config_path, e)
        return ProjectConfig()


def save_current_project_config(config: ProjectConfig) -> None:
    """Write project config to {cwd}/.pode.json."""
    config_path = Path.cwd() / ".pode.json"
    content = config.model_dump_json(indent=2)
    atomic_write(config_path, content)


def get_config_for_cli(key: str, *, global_: bool = True) -> Any:
    """Get a single config value by dotted key (e.g. 'model_pointers.main').

    Args:
        key: Dotted path to the config field.
        global_: True=global config, False=project config.

    Returns:
        Config value, or None if not found.
    """
    config = get_global_config() if global_ else get_current_project_config()
    return _get_nested(config.model_dump(), key)


def set_config_for_cli(key: str, value: Any, *, global_: bool = True) -> None:
    """Set a single config value by dotted key.

    Args:
        key: Dotted path to the config field.
        value: Value to set (will be coerced to the field's type).
        global_: True=global config, False=project config.

    Raises:
        ConfigError: Key not found or type mismatch.
    """
    if global_:
        gconfig = get_global_config()
        _set_nested(gconfig, key, value)
        save_global_config(gconfig)
    else:
        pconfig = get_current_project_config()
        _set_nested(pconfig, key, value)
        save_current_project_config(pconfig)


def list_config_for_cli(*, global_: bool = True) -> dict[str, Any]:
    """List all config values as a flat key→value dict."""
    config = get_global_config() if global_ else get_current_project_config()
    return _flatten(config.model_dump())


# --- Internal helpers ---


def _find_project_config(start: Path) -> Path | None:
    """Walk from start up to git root looking for .pode.json."""
    current = start.resolve()
    # Walk up to 20 levels or until git root
    for _ in range(20):
        candidate = current / ".pode.json"
        if candidate.exists():
            return candidate
        git_dir = current / ".git"
        if git_dir.exists():
            # Reached git root, stop
            return None
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def _get_nested(data: dict[str, Any], key: str) -> Any:
    """Get a value from a nested dict by dotted key."""
    keys = key.split(".")
    try:
        return reduce(operator.getitem, keys, data)
    except (KeyError, TypeError):
        return None


def _set_nested(model: GlobalConfig | ProjectConfig, key: str, value: Any) -> None:
    """Set a value on a Pydantic model by dotted key path."""
    keys = key.split(".")
    obj: Any = model
    for k in keys[:-1]:
        try:
            obj = getattr(obj, k)
        except AttributeError:
            raise ConfigError(f"Unknown config key: {key}") from None

    final_key = keys[-1]
    if not hasattr(obj, final_key):
        raise ConfigError(f"Unknown config key: {key}")

    # Get field info for type coercion
    field_info = obj.model_fields.get(final_key)
    if field_info is not None and field_info.annotation is not None:
        # Simple type coercion for common types
        annotation = field_info.annotation
        if annotation is bool and isinstance(value, str):
            value = value.lower() in ("true", "1", "yes")
        elif annotation is int and isinstance(value, str):
            value = int(value)

    setattr(obj, final_key, value)


def _flatten(
    data: dict[str, Any],
    parent_key: str = "",
    sep: str = ".",
) -> dict[str, Any]:
    """Flatten a nested dict into dotted key→value pairs."""
    items: dict[str, Any] = {}
    for k, v in data.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.update(_flatten(v, new_key, sep))
        else:
            items[new_key] = v
    return items
