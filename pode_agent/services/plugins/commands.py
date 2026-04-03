"""Custom command loader — discovers and parses skill/command markdown files.

Scans 8 standard directories for custom commands and skills (markdown with
YAML frontmatter), deduplicates by ``user_facing_name()``, and returns
a prioritized list.

Priority (low → high): project commands → user commands → project skills
→ user skills → agent commands → plugin commands → plugin skills.

Reference: docs/skill-system.md — Custom Commands
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from pode_agent.infra.logging import get_logger
from pode_agent.types.skill import (
    CommandScope,
    CommandSource,
    CustomCommandFrontmatter,
    CustomCommandWithScope,
)

logger = get_logger(__name__)

# Regex to extract YAML frontmatter from markdown
_FRONTMATTER_RE = re.compile(
    r"\A---\s*\n(.*?)\n---\s*\n(.*)", re.DOTALL,
)

# Module-level cache for custom commands
_custom_commands_cache: list[CustomCommandWithScope] | None = None


def parse_frontmatter(content: str) -> tuple[CustomCommandFrontmatter | None, str]:
    """Parse YAML frontmatter from a command/skill markdown file.

    Returns:
        (frontmatter, body) tuple. frontmatter is None if no valid
        frontmatter block is found.
    """
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return None, content

    yaml_text = match.group(1)
    body = match.group(2)

    try:
        data = yaml.safe_load(yaml_text)
        if not isinstance(data, dict):
            return None, content
        return CustomCommandFrontmatter(**data), body
    except Exception:
        logger.warning("Invalid frontmatter YAML")
        return None, content


def _scan_directory(
    directory: Path,
    source: CommandSource,
    scope: CommandScope,
    is_skill: bool = False,
    skill_dir: Path | None = None,
) -> list[CustomCommandWithScope]:
    """Scan a directory for .md files and parse them as custom commands."""
    commands: list[CustomCommandWithScope] = []
    if not directory.exists():
        return commands

    for md_file in sorted(directory.glob("*.md")):
        try:
            content = md_file.read_text(encoding="utf-8")
            frontmatter, body = parse_frontmatter(content)
            name = md_file.stem

            # Use frontmatter name if available, else filename
            cmd_name = frontmatter.name if frontmatter else name

            commands.append(CustomCommandWithScope(
                name=cmd_name,
                description=frontmatter.description if frontmatter else "",
                file_path=md_file,
                frontmatter=frontmatter,
                content=body,
                source=source,
                scope=scope,
                is_skill=is_skill,
                is_hidden=is_skill,  # Skills are hidden from user-facing lists
                skill_dir=skill_dir,
            ))
        except Exception:
            logger.exception("Failed to parse command file: %s", md_file)

    return commands


def _scan_skill_directories(
    base_dir: Path,
    source: CommandSource,
    scope: CommandScope,
) -> list[CustomCommandWithScope]:
    """Scan skill directories under a base dir (e.g. .pode/skills/*/SKILL.md)."""
    commands: list[CustomCommandWithScope] = []
    if not base_dir.exists():
        return commands

    for skill_subdir in sorted(base_dir.iterdir()):
        if not skill_subdir.is_dir():
            continue

        # Look for SKILL.md or skill.md
        skill_file = skill_subdir / "SKILL.md"
        if not skill_file.exists():
            skill_file = skill_subdir / "skill.md"
        if not skill_file.exists():
            continue

        try:
            content = skill_file.read_text(encoding="utf-8")
            frontmatter, body = parse_frontmatter(content)
            name = frontmatter.name if frontmatter else skill_subdir.name

            commands.append(CustomCommandWithScope(
                name=name,
                description=frontmatter.description if frontmatter else "",
                file_path=skill_file,
                frontmatter=frontmatter,
                content=body,
                source=source,
                scope=scope,
                is_skill=True,
                is_hidden=True,
                skill_dir=skill_subdir,
            ))
        except Exception:
            logger.exception("Failed to parse skill file: %s", skill_file)

    return commands


def _scan_agent_command_dirs(
    agents_base: Path,
    source: CommandSource,
    scope: CommandScope,
) -> list[CustomCommandWithScope]:
    """Scan agent command directories ({agents_base}/*/commands/)."""
    commands: list[CustomCommandWithScope] = []
    if not agents_base.exists():
        return commands

    for agent_dir in sorted(agents_base.iterdir()):
        if not agent_dir.is_dir():
            continue
        cmds_dir = agent_dir / "commands"
        if cmds_dir.is_dir():
            commands.extend(_scan_directory(cmds_dir, source, scope))

    return commands


def _dedup_commands(commands: list[CustomCommandWithScope]) -> list[CustomCommandWithScope]:
    """Deduplicate by user_facing_name() — last-wins (later entries override earlier)."""
    by_name: dict[str, CustomCommandWithScope] = {}
    for cmd in commands:
        by_name[cmd.user_facing_name()] = cmd
    return list(by_name.values())


async def load_custom_commands(
    project_dir: Path | None = None,
    plugin_dirs: list[Path] | None = None,
) -> list[CustomCommandWithScope]:
    """Load all custom commands and skills from standard directories.

    Scans 8 standard directories in priority order and deduplicates by
    ``user_facing_name()`` (last-wins).

    Uses a module-level cache; call ``reload_custom_commands()`` to invalidate.

    Reference: docs/skill-system.md — 自定义命令发现流程
    """
    global _custom_commands_cache
    if _custom_commands_cache is not None:
        return _custom_commands_cache

    all_commands: list[CustomCommandWithScope] = []

    user_home = Path.home()
    project_pode = project_dir / ".pode" if project_dir else None
    user_pode = user_home / ".pode"

    # Priority 1: Project commands ({project}/.pode/commands/)
    if project_pode:
        cmds_dir = project_pode / "commands"
        all_commands.extend(
            _scan_directory(cmds_dir, CommandSource.LOCAL_SETTINGS, CommandScope.PROJECT)
        )

    # Priority 2: User commands (~/.pode/commands/)
    user_cmds_dir = user_pode / "commands"
    all_commands.extend(
        _scan_directory(user_cmds_dir, CommandSource.USER_SETTINGS, CommandScope.USER)
    )

    # Priority 3: Project skills ({project}/.pode/skills/)
    if project_pode:
        skills_dir = project_pode / "skills"
        all_commands.extend(
            _scan_skill_directories(skills_dir, CommandSource.LOCAL_SETTINGS, CommandScope.PROJECT)
        )

    # Priority 4: User skills (~/.pode/skills/)
    user_skills_dir = user_pode / "skills"
    all_commands.extend(
        _scan_skill_directories(user_skills_dir, CommandSource.USER_SETTINGS, CommandScope.USER)
    )

    # Priority 5: Project agent commands ({project}/.pode/agents/*/commands/)
    if project_pode:
        agents_dir = project_pode / "agents"
        all_commands.extend(
            _scan_agent_command_dirs(agents_dir, CommandSource.LOCAL_SETTINGS, CommandScope.PROJECT)
        )

    # Priority 6: User agent commands (~/.pode/agents/*/commands/)
    user_agents_dir = user_pode / "agents"
    all_commands.extend(
        _scan_agent_command_dirs(user_agents_dir, CommandSource.USER_SETTINGS, CommandScope.USER)
    )

    # Priority 7-8: Plugin dirs (commands/ and skills/)
    if plugin_dirs:
        for plugin_dir in plugin_dirs:
            cmds_dir = plugin_dir / "commands"
            all_commands.extend(
                _scan_directory(cmds_dir, CommandSource.PLUGIN_DIR, CommandScope.PROJECT)
            )
            skills_base = plugin_dir / "skills"
            all_commands.extend(
                _scan_skill_directories(skills_base, CommandSource.PLUGIN_DIR, CommandScope.PROJECT)
            )

    # Deduplicate — last-wins
    result = _dedup_commands(all_commands)

    _custom_commands_cache = result
    logger.debug("Loaded %d custom commands/skills", len(result))
    return result


def reload_custom_commands() -> None:
    """Invalidate the cache so next call rescans the filesystem.

    Reference: docs/skill-system.md — 缓存与刷新
    """
    global _custom_commands_cache
    _custom_commands_cache = None
