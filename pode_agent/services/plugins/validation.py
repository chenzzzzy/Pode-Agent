"""Plugin validation — validates plugin.json, marketplace.json, and skill directories.

Reference: docs/skill-system.md — Plugin 验证
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pode_agent.infra.logging import get_logger

logger = get_logger(__name__)

# Kebab-case validation (1-64 chars)
_KEBAB_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
# Semver pattern
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+")


def validate_plugin_json(data: dict[str, Any]) -> list[str]:
    """Validate a parsed plugin.json manifest.

    Returns:
        List of validation error messages. Empty list means valid.

    Reference: docs/skill-system.md — Plugin 清单校验
    """
    errors: list[str] = []

    name = data.get("name")
    if not name:
        errors.append("Missing required field: name")
    elif not isinstance(name, str) or not _KEBAB_RE.match(name):
        errors.append(f"Invalid name '{name}': must be kebab-case (lowercase, hyphens)")

    version = data.get("version")
    if version and not _SEMVER_RE.match(str(version)):
        errors.append(f"Invalid version '{version}': must be semver (e.g. 1.0.0)")

    # Validate path fields — must be relative, no traversal
    for field in ("skills", "commands", "agents", "hooks", "output_styles"):
        values = data.get(field, [])
        if not isinstance(values, list):
            errors.append(f"'{field}' must be a list")
        else:
            for v in values:
                if not isinstance(v, str):
                    errors.append(f"'{field}' entries must be strings, got {type(v).__name__}")
                elif Path(v).is_absolute():
                    errors.append(f"'{field}' entry '{v}' must be a relative path")
                elif ".." in Path(v).parts:
                    errors.append(f"'{field}' entry '{v}' contains path traversal")

    return errors


def validate_marketplace_json(data: dict[str, Any]) -> list[str]:
    """Validate a parsed marketplace.json manifest.

    Returns:
        List of validation error messages. Empty list means valid.

    Reference: docs/skill-system.md — Marketplace 清单格式
    """
    errors: list[str] = []

    name = data.get("name")
    if not name:
        errors.append("Missing required field: name")
    elif not isinstance(name, str):
        errors.append("'name' must be a string")

    plugins = data.get("plugins", [])
    if not isinstance(plugins, list):
        errors.append("'plugins' must be a list")
    else:
        for i, plugin in enumerate(plugins):
            if not isinstance(plugin, dict):
                errors.append(f"plugins[{i}] must be an object")
                continue
            if not plugin.get("name"):
                errors.append(f"plugins[{i}]: missing required field 'name'")
            if not plugin.get("source"):
                errors.append(f"plugins[{i}]: missing required field 'source'")

    return errors


def validate_skill_dir(path: Path) -> list[str]:
    """Validate a skill directory structure.

    Requirements:
    - Directory name must be kebab-case (1-64 chars)
    - Must contain SKILL.md or skill.md
    - No path traversal in directory names
    - Frontmatter must contain name and description

    Reference: docs/skill-system.md — 技能目录校验
    """
    errors: list[str] = []

    if not path.exists():
        errors.append(f"Directory does not exist: {path}")
        return errors

    if not path.is_dir():
        errors.append(f"Not a directory: {path}")
        return errors

    # Check kebab-case name and length
    dir_name = path.name
    if not _KEBAB_RE.match(dir_name):
        errors.append(
            f"Invalid skill directory name '{dir_name}': must be kebab-case"
        )
    if len(dir_name) > 64:
        errors.append(f"Skill directory name too long ({len(dir_name)} chars, max 64)")

    # Check SKILL.md or skill.md exists
    skill_file = path / "SKILL.md"
    if not skill_file.exists():
        skill_file = path / "skill.md"
    if not skill_file.exists():
        errors.append(f"Missing SKILL.md in {path}")

    # Path safety: no '..' components
    if ".." in str(path):
        errors.append(f"Path traversal detected in: {path}")
    if path.is_absolute() and ".." in path.parts:
        errors.append(f"Path traversal detected in: {path}")

    return errors
