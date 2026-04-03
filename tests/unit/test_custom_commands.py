"""Tests for services/plugins/ — Plugin system, commands, validation, marketplace."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from pode_agent.services.plugins.commands import (
    _scan_directory,
    load_custom_commands,
    parse_frontmatter,
    reload_custom_commands,
)
from pode_agent.services.plugins.marketplace import (
    _load_installed,
    _save_installed,
    disable_plugin,
    enable_plugin,
    install_plugin,
    list_installed_plugins,
    uninstall_plugin,
)
from pode_agent.services.plugins.validation import (
    validate_plugin_json,
    validate_skill_dir,
)
from pode_agent.types.skill import CustomCommandFrontmatter


# ---------------------------------------------------------------------------
# parse_frontmatter
# ---------------------------------------------------------------------------


class TestParseFrontmatter:
    def test_valid_frontmatter(self) -> None:
        content = "---\nname: my-cmd\ndescription: My command\n---\nBody text here"
        fm, body = parse_frontmatter(content)
        assert fm is not None
        assert fm.name == "my-cmd"
        assert fm.description == "My command"
        assert "Body text here" in body

    def test_no_frontmatter(self) -> None:
        content = "Just plain text"
        fm, body = parse_frontmatter(content)
        assert fm is None
        assert body == "Just plain text"

    def test_invalid_yaml(self) -> None:
        content = "---\n: invalid: yaml:\n---\nBody"
        fm, body = parse_frontmatter(content)
        assert fm is None

    def test_non_dict_yaml(self) -> None:
        content = "---\n- list\n- item\n---\nBody"
        fm, body = parse_frontmatter(content)
        assert fm is None

    def test_with_aliases(self) -> None:
        content = (
            "---\nname: test\n"
            "description: Test\n"
            "allowed-tools: [bash, glob]\n"
            "argument-hint: '<file>'\n"
            "---\nBody"
        )
        fm, body = parse_frontmatter(content)
        assert fm is not None
        assert fm.allowed_tools == ["bash", "glob"]
        assert fm.argument_hint == "<file>"


# ---------------------------------------------------------------------------
# _scan_directory
# ---------------------------------------------------------------------------


class TestScanDirectory:
    def test_nonexistent_dir(self, tmp_path: Path) -> None:
        from pode_agent.types.skill import CommandScope, CommandSource

        cmds = _scan_directory(
            tmp_path / "nonexistent", CommandSource.LOCAL_SETTINGS, CommandScope.PROJECT,
        )
        assert cmds == []

    def test_scans_md_files(self, tmp_path: Path) -> None:
        from pode_agent.types.skill import CommandScope, CommandSource

        (tmp_path / "test-cmd.md").write_text(
            "---\nname: test-cmd\ndescription: A test command\n---\nDo something",
            encoding="utf-8",
        )
        cmds = _scan_directory(tmp_path, CommandSource.LOCAL_SETTINGS, CommandScope.PROJECT)
        assert len(cmds) == 1
        assert cmds[0].name == "test-cmd"
        assert cmds[0].description == "A test command"

    def test_ignores_non_md(self, tmp_path: Path) -> None:
        from pode_agent.types.skill import CommandScope, CommandSource

        (tmp_path / "data.json").write_text("{}", encoding="utf-8")
        cmds = _scan_directory(tmp_path, CommandSource.LOCAL_SETTINGS, CommandScope.PROJECT)
        assert cmds == []


# ---------------------------------------------------------------------------
# load_custom_commands
# ---------------------------------------------------------------------------


class TestLoadCustomCommands:
    def setup_method(self) -> None:
        """Clear cache before each test."""
        reload_custom_commands()

    async def test_empty_with_no_dirs(self) -> None:
        reload_custom_commands()
        cmds = await load_custom_commands()
        assert isinstance(cmds, list)

    async def test_loads_from_project(self, tmp_path: Path) -> None:
        reload_custom_commands()
        cmds_dir = tmp_path / ".pode" / "commands"
        cmds_dir.mkdir(parents=True)
        (cmds_dir / "hello.md").write_text(
            "---\nname: hello\ndescription: Say hello\n---\nHello $ARGUMENTS",
            encoding="utf-8",
        )
        cmds = await load_custom_commands(project_dir=tmp_path)
        names = [c.name for c in cmds]
        assert "hello" in names

    async def test_deduplication(self, tmp_path: Path) -> None:
        reload_custom_commands()
        # Project-level command
        cmds_dir = tmp_path / ".pode" / "commands"
        cmds_dir.mkdir(parents=True)
        (cmds_dir / "greet.md").write_text(
            "---\nname: greet\ndescription: Project version\n---\nProject",
            encoding="utf-8",
        )

        # User-level command (same name, different path — but we can't easily
        # create this without mocking home, so just verify project one loads)
        cmds = await load_custom_commands(project_dir=tmp_path)
        greet_cmds = [c for c in cmds if c.name == "greet"]
        assert len(greet_cmds) == 1


# ---------------------------------------------------------------------------
# validate_plugin_json
# ---------------------------------------------------------------------------


class TestValidatePluginJson:
    def test_valid(self) -> None:
        errors = validate_plugin_json({
            "name": "my-plugin",
            "version": "1.0.0",
        })
        assert errors == []

    def test_missing_name(self) -> None:
        errors = validate_plugin_json({})
        assert any("name" in e for e in errors)

    def test_invalid_name(self) -> None:
        errors = validate_plugin_json({"name": "My Plugin!"})
        assert any("kebab-case" in e for e in errors)

    def test_invalid_version(self) -> None:
        errors = validate_plugin_json({"name": "test", "version": "abc"})
        assert any("version" in e for e in errors)

    def test_invalid_skills_type(self) -> None:
        errors = validate_plugin_json({"name": "test", "skills": "not-a-list"})
        assert any("skills" in e for e in errors)

    def test_invalid_commands_type(self) -> None:
        errors = validate_plugin_json({"name": "test", "commands": "not-a-list"})
        assert any("commands" in e for e in errors)


# ---------------------------------------------------------------------------
# validate_skill_dir
# ---------------------------------------------------------------------------


class TestValidateSkillDir:
    def test_valid_skill(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# My Skill", encoding="utf-8")
        errors = validate_skill_dir(skill_dir)
        assert errors == []

    def test_nonexistent(self, tmp_path: Path) -> None:
        errors = validate_skill_dir(tmp_path / "nope")
        assert len(errors) > 0

    def test_not_directory(self, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("hi", encoding="utf-8")
        errors = validate_skill_dir(f)
        assert any("Not a directory" in e for e in errors)

    def test_bad_name(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "BadName"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("# Bad", encoding="utf-8")
        errors = validate_skill_dir(skill_dir)
        assert any("kebab-case" in e for e in errors)

    def test_missing_skill_md(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        errors = validate_skill_dir(skill_dir)
        assert any("SKILL.md" in e for e in errors)


# ---------------------------------------------------------------------------
# Marketplace operations
# ---------------------------------------------------------------------------


class TestMarketplace:
    def test_install_and_list(self, tmp_path: Path) -> None:
        # Create a plugin source
        plugin_src = tmp_path / "source" / "test-plugin"
        plugin_src.mkdir(parents=True)
        (plugin_src / "plugin.json").write_text(
            json.dumps({"name": "test-plugin", "version": "1.0.0"}), encoding="utf-8",
        )
        (plugin_src / "commands").mkdir()
        (plugin_src / "commands" / "hello.md").write_text(
            "---\nname: hello\ndescription: Hi\n---\nHello!", encoding="utf-8",
        )

        with patch("pode_agent.services.plugins.marketplace._plugins_dir", return_value=tmp_path / "plugins"):
            installed = install_plugin(str(plugin_src))
            assert installed.name == "test-plugin"
            assert installed.enabled

            plugins = list_installed_plugins()
            names = [p.name for p in plugins]
            assert "test-plugin" in names

    def test_disable_enable(self, tmp_path: Path) -> None:
        plugin_src = tmp_path / "source" / "my-plugin"
        plugin_src.mkdir(parents=True)
        (plugin_src / "plugin.json").write_text(
            json.dumps({"name": "my-plugin", "version": "1.0.0"}), encoding="utf-8",
        )

        with patch("pode_agent.services.plugins.marketplace._plugins_dir", return_value=tmp_path / "plugins"):
            install_plugin(str(plugin_src))
            disable_plugin("my-plugin")

            plugins = list_installed_plugins()
            my_plugin = next(p for p in plugins if p.name == "my-plugin")
            assert not my_plugin.enabled

            enable_plugin("my-plugin")
            plugins = list_installed_plugins()
            my_plugin = next(p for p in plugins if p.name == "my-plugin")
            assert my_plugin.enabled

    def test_uninstall(self, tmp_path: Path) -> None:
        plugin_src = tmp_path / "source" / "to-remove"
        plugin_src.mkdir(parents=True)
        (plugin_src / "plugin.json").write_text(
            json.dumps({"name": "to-remove", "version": "1.0.0"}), encoding="utf-8",
        )

        with patch("pode_agent.services.plugins.marketplace._plugins_dir", return_value=tmp_path / "plugins"):
            install_plugin(str(plugin_src))
            uninstall_plugin("to-remove")
            plugins = list_installed_plugins()
            assert not any(p.name == "to-remove" for p in plugins)

    def test_install_nonexistent_source(self) -> None:
        with pytest.raises(FileNotFoundError):
            install_plugin("/nonexistent/path")

    def test_uninstall_not_found(self, tmp_path: Path) -> None:
        with patch("pode_agent.services.plugins.marketplace._plugins_dir", return_value=tmp_path):
            with pytest.raises(KeyError):
                uninstall_plugin("nonexistent")
