"""Custom command loader — discovers and parses skill/command markdown files.

Scans 8 standard directories for custom commands and skills (markdown with
YAML frontmatter), deduplicates by ``user_facing_name()``, and returns
a prioritized list.

Priority: project commands → project skills → user commands → user skills → plugin dirs.

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
                skill_dir=skill_dir,
            ))
        except Exception:
            logger.exception("Failed to parse command file: %s", md_file)

    return commands


async def load_custom_commands(
    project_dir: Path | None = None,
    plugin_dirs: list[Path] | None = None,
) -> list[CustomCommandWithScope]:
    """Load all custom commands and skills from standard directories.

    Scans in priority order and deduplicates by ``user_facing_name()``.
    """
    commands: list[CustomCommandWithScope] = []
    seen_names: set[str] = set()

    user_home = Path.home()
    project_pode = project_dir / ".pode" if project_dir else None
    user_pode = user_home / ".pode"

    # Priority 1: Project commands
    if project_pode:
        cmds_dir = project_pode / "commands"
        for cmd in _scan_directory(cmds_dir, CommandSource.LOCAL_SETTINGS, CommandScope.PROJECT):
            name = cmd.user_facing_name()
            if name not in seen_names:
                seen_names.add(name)
                commands.append(cmd)

    # Priority 2: Project skills
    if project_pode:
        skills_dir = project_pode / "skills"
        if skills_dir.exists():
            for skill_subdir in sorted(skills_dir.iterdir()):
                if not skill_subdir.is_dir():
                    continue
                skill_file = skill_subdir / "SKILL.md"
                if skill_file.exists():
                    cmds = _scan_directory(
                        skill_subdir, CommandSource.LOCAL_SETTINGS,
                        CommandScope.PROJECT, is_skill=True, skill_dir=skill_subdir,
                    )
                    # Override to only include SKILL.md
                    for cmd in cmds:
                        if cmd.file_path == skill_file:
                            name = cmd.user_facing_name()
                            if name not in seen_names:
                                seen_names.add(name)
                                commands.append(cmd)

    # Priority 3: User commands
    user_cmds_dir = user_pode / "commands"
    for cmd in _scan_directory(user_cmds_dir, CommandSource.USER_SETTINGS, CommandScope.USER):
        name = cmd.user_facing_name()
        if name not in seen_names:
            seen_names.add(name)
            commands.append(cmd)

    # Priority 4: User skills
    user_skills_dir = user_pode / "skills"
    if user_skills_dir.exists():
        for skill_subdir in sorted(user_skills_dir.iterdir()):
            if not skill_subdir.is_dir():
                continue
            skill_file = skill_subdir / "SKILL.md"
            if skill_file.exists():
                cmds = _scan_directory(
                    skill_subdir, CommandSource.USER_SETTINGS,
                    CommandScope.USER, is_skill=True, skill_dir=skill_subdir,
                )
                for cmd in cmds:
                    if cmd.file_path == skill_file:
                        name = cmd.user_facing_name()
                        if name not in seen_names:
                            seen_names.add(name)
                            commands.append(cmd)

    # Priority 5: Plugin dirs
    if plugin_dirs:
        for plugin_dir in plugin_dirs:
            cmds_dir = plugin_dir / "commands"
            for cmd in _scan_directory(cmds_dir, CommandSource.PLUGIN_DIR, CommandScope.PROJECT):
                name = cmd.user_facing_name()
                if name not in seen_names:
                    seen_names.add(name)
                    commands.append(cmd)

            skills_base = plugin_dir / "skills"
            if skills_base.exists():
                for skill_subdir in sorted(skills_base.iterdir()):
                    if not skill_subdir.is_dir():
                        continue
                    skill_file = skill_subdir / "SKILL.md"
                    if skill_file.exists():
                        cmds = _scan_directory(
                            skill_subdir, CommandSource.PLUGIN_DIR,
                            CommandScope.PROJECT, is_skill=True, skill_dir=skill_subdir,
                        )
                        for cmd in cmds:
                            if cmd.file_path == skill_file:
                                name = cmd.user_facing_name()
                                if name not in seen_names:
                                    seen_names.add(name)
                                    commands.append(cmd)

    logger.debug("Loaded %d custom commands/skills", len(commands))
    return commands
