"""Plugin validation — validates plugin.json manifests and skill directories."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pode_agent.infra.logging import get_logger

logger = get_logger(__name__)

# Kebab-case validation
_KEBAB_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")


def validate_plugin_json(data: dict[str, Any]) -> list[str]:
    """Validate a parsed plugin.json manifest.

    Returns:
        List of validation error messages. Empty list means valid.
    """
    errors: list[str] = []

    name = data.get("name")
    if not name:
        errors.append("Missing required field: name")
    elif not _KEBAB_RE.match(name):
        errors.append(f"Invalid name '{name}': must be kebab-case (lowercase, hyphens)")

    version = data.get("version")
    if version and not re.match(r"^\d+\.\d+\.\d+", str(version)):
        errors.append(f"Invalid version '{version}': must be semver (e.g. 1.0.0)")

    # Validate skills list
    skills = data.get("skills", [])
    if not isinstance(skills, list):
        errors.append("'skills' must be a list")

    # Validate commands list
    commands = data.get("commands", [])
    if not isinstance(commands, list):
        errors.append("'commands' must be a list")

    return errors


def validate_skill_dir(path: Path) -> list[str]:
    """Validate a skill directory structure.

    Requirements:
    - Directory name must be kebab-case
    - Must contain a SKILL.md file
    - No path traversal in directory names
    """
    errors: list[str] = []

    if not path.exists():
        errors.append(f"Directory does not exist: {path}")
        return errors

    if not path.is_dir():
        errors.append(f"Not a directory: {path}")
        return errors

    # Check kebab-case name
    dir_name = path.name
    if not _KEBAB_RE.match(dir_name):
        errors.append(f"Invalid skill directory name '{dir_name}': must be kebab-case")

    # Check SKILL.md exists
    skill_file = path / "SKILL.md"
    if not skill_file.exists():
        errors.append(f"Missing SKILL.md in {path}")

    # Path safety: no '..' components
    if ".." in str(path):
        errors.append(f"Path traversal detected in: {path}")

    return errors
