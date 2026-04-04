"""Marketplace operations — marketplace CRUD, plugin install/uninstall/enable/disable.

Manages the lifecycle of plugins sourced from GitHub, Git, URLs, or
local directories. Supports two install modes:
- ``skill-pack``: copies individual skills/commands into the user's .pode directory
- ``plugin-pack``: copies the entire plugin into the plugins directory

Storage paths (per spec):
- ``~/.pode/plugins/known_marketplaces.json`` — known marketplace sources
- ``~/.pode/installed-skill-plugins.json`` — installed plugin registry

Reference: docs/skill-system.md — Marketplace
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pode_agent.infra.logging import get_logger
from pode_agent.services.plugins.validation import validate_marketplace_json
from pode_agent.types.skill import (
    InstalledPlugin,
    MarketplaceManifest,
    MarketplaceSource,
    PluginManifest,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Storage paths
# ---------------------------------------------------------------------------

# Source prefix patterns for parsing marketplace source strings
_SOURCE_RE = re.compile(
    r"^(?P<type>github|git|url|npm|file|dir):(?P<value>.+)$",
)


def _plugins_dir() -> Path:
    """Get the user's plugins directory (~/.pode/plugins/)."""
    d = Path.home() / ".pode" / "plugins"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _installed_json_path() -> Path:
    """Path to the installed plugins registry (per spec)."""
    return Path.home() / ".pode" / "installed-skill-plugins.json"


def _known_marketplaces_path() -> Path:
    """Path to the known marketplaces registry (per spec)."""
    return _plugins_dir() / "known_marketplaces.json"


# ---------------------------------------------------------------------------
# Internal persistence helpers
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> dict[str, Any]:
    """Load a JSON file, returning empty dict on failure."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        logger.exception("Failed to load %s", path)
        return {}


def _save_json(path: Path, data: dict[str, Any]) -> None:
    """Save data as pretty-printed JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def _load_installed() -> dict[str, dict[str, Any]]:
    """Load the installed plugins registry from disk."""
    return _load_json(_installed_json_path())


def _save_installed(registry: dict[str, dict[str, Any]]) -> None:
    """Save the installed plugins registry to disk."""
    _save_json(_installed_json_path(), registry)


def _load_known_marketplaces() -> dict[str, dict[str, Any]]:
    """Load the known marketplaces registry from disk."""
    return _load_json(_known_marketplaces_path())


def _save_known_marketplaces(registry: dict[str, dict[str, Any]]) -> None:
    """Save the known marketplaces registry to disk."""
    _save_json(_known_marketplaces_path(), registry)


# ---------------------------------------------------------------------------
# Source string parsing
# ---------------------------------------------------------------------------


def parse_source_string(source: str) -> MarketplaceSource:
    """Parse a source string like ``github:owner/repo`` into a MarketplaceSource.

    Supported formats:
    - ``github:owner/repo`` → type=github, url=owner/repo
    - ``git:https://...`` → type=git, url=...
    - ``url:https://...`` → type=url, url=...
    - ``npm:package-name`` → type=npm, url=package-name
    - ``file:/path/to/file`` → type=file, path=...
    - ``dir:/path/to/dir`` → type=directory, path=...

    Reference: docs/skill-system.md — Marketplace 来源类型
    """
    m = _SOURCE_RE.match(source.strip())
    if not m:
        # Default: treat as a local path (directory)
        return MarketplaceSource(type="directory", path=source)

    src_type = m.group("type")
    value = m.group("value").strip()

    if src_type in ("github", "git", "url", "npm"):
        return MarketplaceSource(
            type=src_type,  # type: ignore[arg-type]
            url=value,
        )
    elif src_type == "file":
        return MarketplaceSource(type="file", path=value)
    elif src_type == "dir":
        return MarketplaceSource(type="directory", path=value)

    return MarketplaceSource(type="directory", path=source)


# ---------------------------------------------------------------------------
# Marketplace CRUD
# ---------------------------------------------------------------------------


def add_marketplace(
    source: str,
    *,
    name: str | None = None,
    ref: str = "main",
) -> dict[str, Any]:
    """Add a marketplace source to the known marketplaces registry.

    Args:
        source: Source string (e.g. ``github:owner/repo``).
        name: Optional display name. Defaults to derived name from source.
        ref: Git ref to use (default ``main``).

    Returns:
        The marketplace entry that was saved.

    Reference: docs/skill-system.md — CLI 命令: pode plugin marketplace add
    """
    parsed = parse_source_string(source)
    parsed.ref = ref

    # Validate file/dir sources exist
    if parsed.type in ("file", "dir", "directory"):
        source_path = Path(parsed.path) if parsed.path else Path(source.split(":", 1)[1])
        if not source_path.exists():
            raise FileNotFoundError(f"Source path does not exist: {source_path}")

    marketplace_name = name or _derive_marketplace_name(parsed)

    registry = _load_known_marketplaces()
    registry[marketplace_name] = {
        "source": parsed.model_dump(mode="json"),
        "added_at": datetime.now(tz=UTC).isoformat(),
        "cache": None,
    }
    _save_known_marketplaces(registry)

    logger.info("Added marketplace '%s' from %s", marketplace_name, source)
    return registry[marketplace_name]


def remove_marketplace(name: str) -> None:
    """Remove a marketplace from the known marketplaces registry.

    Raises:
        KeyError: If the marketplace name is not found.
    """
    registry = _load_known_marketplaces()
    if name not in registry:
        raise KeyError(f"Marketplace not found: {name}")
    del registry[name]
    _save_known_marketplaces(registry)
    logger.info("Removed marketplace '%s'", name)


def list_marketplaces() -> list[dict[str, Any]]:
    """List all known marketplaces with their metadata.

    Returns:
        List of marketplace entries, each containing name, source, and added_at.
    """
    registry = _load_known_marketplaces()
    results: list[dict[str, Any]] = []
    for name, data in registry.items():
        results.append({
            "name": name,
            **data,
        })
    return results


def update_marketplace(name: str) -> dict[str, Any]:
    """Refresh the cached plugin list for a marketplace.

    For local sources, re-reads the marketplace.json file.
    For remote sources, fetches the latest data (placeholder for future).

    Raises:
        KeyError: If the marketplace name is not found.

    Reference: docs/skill-system.md — CLI 命令: pode plugin marketplace update
    """
    registry = _load_known_marketplaces()
    if name not in registry:
        raise KeyError(f"Marketplace not found: {name}")

    entry = registry[name]
    source_data = entry.get("source", {})
    source_type = source_data.get("type", "")

    if source_type in ("file", "directory"):
        # Local: read marketplace.json directly
        path_str = source_data.get("path", source_data.get("url", ""))
        path = Path(path_str)
        if not path.is_dir():
            path = path.parent
        manifest_path = path / "marketplace.json"
        if manifest_path.exists():
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
                errors = validate_marketplace_json(data)
                if errors:
                    logger.warning(
                        "Marketplace %s has validation errors: %s", name, errors,
                    )
                else:
                    manifest = MarketplaceManifest(**data)
                    entry["cache"] = {
                        "plugins": [
                            p.model_dump(mode="json") for p in manifest.plugins
                        ],
                        "updated_at": datetime.now(tz=UTC).isoformat(),
                    }
            except Exception:
                logger.exception("Failed to read marketplace.json for %s", name)
    else:
        # Remote: placeholder — would need git clone / http fetch
        logger.info(
            "Remote marketplace update for '%s' (type=%s) not yet implemented",
            name,
            source_type,
        )

    registry[name] = entry
    _save_known_marketplaces(registry)
    return entry


# ---------------------------------------------------------------------------
# Plugin lifecycle
# ---------------------------------------------------------------------------


def list_installed_plugins() -> list[InstalledPlugin]:
    """List all installed plugins."""
    registry = _load_installed()
    result: list[InstalledPlugin] = []
    for plugin_id, data in registry.items():
        try:
            result.append(InstalledPlugin(
                id=plugin_id,
                name=data["name"],
                source=data["source"],
                install_path=Path(data["install_path"]),
                enabled=data.get("enabled", True),
                install_mode=data.get("install_mode", "plugin-pack"),
                installed_at=str(data.get("installed_at", "")),
            ))
        except Exception:
            logger.warning("Invalid installed plugin entry: %s", plugin_id)
    return result


def install_plugin(
    source: str,
    *,
    scope: str = "user",
    install_mode: str = "plugin-pack",
    plugin_name: str | None = None,
) -> InstalledPlugin:
    """Install a plugin from a source path, URL, or marketplace reference.

    Supports local directories (``file:`` or ``dir:`` or bare path) and
    marketplace entries (``marketplace:marketplace-name/plugin-name``).
    Remote sources (``github:``, ``git:``, ``url:``, ``npm:``) are
    placeholders for future implementation.

    Reference: docs/skill-system.md — CLI 命令: pode plugin install
    """
    # Check for marketplace reference: marketplace:name/plugin-name
    if source.startswith("marketplace:"):
        return _install_from_marketplace(
            source, scope=scope, install_mode=install_mode,
        )

    parsed = parse_source_string(source)

    # Dispatch by source type
    if parsed.type in ("file", "directory"):
        source_path = Path(parsed.path or parsed.url or source)
        if not source_path.exists():
            raise FileNotFoundError(f"Source path does not exist: {source_path}")
        return _install_from_local(
            source_path,
            scope=scope,
            install_mode=install_mode,
            plugin_name=plugin_name,
        )

    # Remote sources: placeholder
    raise NotImplementedError(
        f"Installing from '{parsed.type}' source is not yet implemented. "
        f"Use a local path (file:/path or dir:/path) for now."
    )


def _install_from_local(
    source_path: Path,
    *,
    scope: str = "user",
    install_mode: str = "plugin-pack",
    plugin_name: str | None = None,
) -> InstalledPlugin:
    """Install a plugin from a local directory."""
    # Parse manifest
    manifest: PluginManifest | None = None
    manifest_path = source_path / ".pode-plugin" / "plugin.json"
    if not manifest_path.exists():
        manifest_path = source_path / "plugin.json"
    if manifest_path.exists():
        try:
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest = PluginManifest(**manifest_data)
            name = manifest.name
        except Exception:
            name = plugin_name or source_path.name
    else:
        name = plugin_name or source_path.name

    # Install directory
    plugins_base = _plugins_dir()
    install_path = plugins_base / name
    plugin_id = name

    if install_mode == "plugin-pack":
        # Copy entire directory
        if install_path.exists():
            shutil.rmtree(install_path)
        shutil.copytree(source_path, install_path)
    elif install_mode == "skill-pack":
        # Copy individual skills/commands into user dirs
        install_path.mkdir(parents=True, exist_ok=True)
        if manifest:
            _copy_skill_pack(manifest, source_path)
    else:
        install_path.mkdir(parents=True, exist_ok=True)

    # Record in registry
    registry = _load_installed()
    now_iso = datetime.now(tz=UTC).isoformat()
    installed = InstalledPlugin(
        id=plugin_id,
        name=name,
        source=str(source_path),
        install_path=install_path,
        enabled=True,
        install_mode=install_mode,  # type: ignore[arg-type]
        installed_at=now_iso,
    )
    registry[plugin_id] = installed.model_dump(mode="json")
    _save_installed(registry)

    logger.info("Installed plugin '%s' from %s", name, source_path)
    return installed


def _install_from_marketplace(
    source: str,
    *,
    scope: str = "user",
    install_mode: str = "plugin-pack",
) -> InstalledPlugin:
    """Install a plugin referenced as marketplace:name/plugin-name."""
    ref = source[len("marketplace:"):]
    parts = ref.split("/", 1)
    if len(parts) != 2:
        raise ValueError(
            f"Invalid marketplace reference: {source}. "
            "Expected format: marketplace:marketplace-name/plugin-name"
        )
    marketplace_name, plugin_name = parts

    # Look up marketplace
    registry = _load_known_marketplaces()
    if marketplace_name not in registry:
        raise KeyError(f"Marketplace not found: {marketplace_name}")

    entry = registry[marketplace_name]
    cache = entry.get("cache", {})
    plugins = cache.get("plugins", [])

    # Find the plugin in the marketplace cache
    plugin_entry = next(
        (p for p in plugins if p.get("name") == plugin_name),
        None,
    )
    if plugin_entry is None:
        raise KeyError(
            f"Plugin '{plugin_name}' not found in marketplace '{marketplace_name}'"
        )

    # Resolve the plugin source path
    source_data = entry.get("source", {})
    source_type = source_data.get("type", "")

    if source_type in ("file", "directory"):
        base_path = Path(source_data.get("path", source_data.get("url", "")))
        plugin_source = base_path / plugin_entry.get("source", plugin_name)
        return _install_from_local(
            plugin_source,
            scope=scope,
            install_mode=install_mode,
            plugin_name=plugin_name,
        )

    raise NotImplementedError(
        f"Installing marketplace plugins from '{source_type}' is not yet implemented."
    )


def _copy_skill_pack(
    manifest: PluginManifest,
    source_path: Path,
) -> None:
    """Copy individual skills/commands for skill-pack mode.

    Copies skill directories to ~/.pode/skills/ and command files
    to ~/.pode/commands/.
    """
    user_skills = Path.home() / ".pode" / "skills"
    user_commands = Path.home() / ".pode" / "commands"
    user_skills.mkdir(parents=True, exist_ok=True)
    user_commands.mkdir(parents=True, exist_ok=True)

    for skill_rel in manifest.skills:
        src = source_path / skill_rel
        if src.is_dir():
            dst = user_skills / src.name
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)

    for cmd_rel in manifest.commands:
        src = source_path / cmd_rel
        if src.is_file():
            shutil.copy2(src, user_commands / src.name)


def uninstall_plugin(plugin_id: str) -> None:
    """Uninstall a plugin by ID.

    Removes the plugin directory and deletes its entry from the registry.

    Reference: docs/skill-system.md — CLI 命令: pode plugin uninstall
    """
    registry = _load_installed()
    if plugin_id not in registry:
        raise KeyError(f"Plugin not found: {plugin_id}")

    data = registry[plugin_id]
    install_path = Path(data["install_path"])

    # Remove files
    if install_path.exists():
        shutil.rmtree(install_path, ignore_errors=True)

    # Remove from registry
    del registry[plugin_id]
    _save_installed(registry)

    logger.info("Uninstalled plugin '%s'", plugin_id)


def enable_plugin(plugin_id: str) -> None:
    """Enable a previously disabled plugin.

    Reference: docs/skill-system.md — CLI 命令: pode plugin enable
    """
    registry = _load_installed()
    if plugin_id not in registry:
        raise KeyError(f"Plugin not found: {plugin_id}")
    registry[plugin_id]["enabled"] = True
    _save_installed(registry)
    logger.info("Enabled plugin '%s'", plugin_id)


def disable_plugin(plugin_id: str) -> None:
    """Disable a plugin without removing it.

    Reference: docs/skill-system.md — CLI 命令: pode plugin disable
    """
    registry = _load_installed()
    if plugin_id not in registry:
        raise KeyError(f"Plugin not found: {plugin_id}")
    registry[plugin_id]["enabled"] = False
    _save_installed(registry)
    logger.info("Disabled plugin '%s'", plugin_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _derive_marketplace_name(source: MarketplaceSource) -> str:
    """Derive a default marketplace name from a source descriptor."""
    if source.url:
        # github:owner/repo → owner-repo
        name = source.url.replace("/", "-")
        # git/https URLs → last path segment
        if "/" in source.url:
            name = source.url.rsplit("/", 1)[-1]
            # Strip .git suffix
            if name.endswith(".git"):
                name = name[:-4]
        return name or "unnamed-marketplace"
    if source.path:
        return Path(source.path).name or "unnamed-marketplace"
    return "unnamed-marketplace"
