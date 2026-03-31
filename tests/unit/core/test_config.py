"""Unit tests for the config system.

Reference: docs/testing-strategy.md — Phase 0 test requirements
           docs/api-specs.md — Config API contract
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pode_agent.core.config import (
    ConfigError,
    GlobalConfig,
    ProjectConfig,
    get_config_for_cli,
    get_global_config,
    list_config_for_cli,
    save_current_project_config,
    save_global_config,
    set_config_for_cli,
)
from pode_agent.core.config.loader import get_current_project_config


@pytest.fixture(autouse=True)
def _clear_config_cache():
    """Clear the global config cache between tests."""
    import pode_agent.core.config.loader as loader

    loader._global_config_cache = None
    yield
    loader._global_config_cache = None


class TestGetGlobalConfig:
    def test_returns_defaults_when_file_not_exist(self, tmp_pode_dir: Path) -> None:
        config = get_global_config()
        assert config.theme == "dark"
        assert config.verbose is False
        assert config.num_startups == 0

    def test_reads_existing_config(self, tmp_pode_dir: Path) -> None:
        config_file = tmp_pode_dir / "config.json"
        config_file.write_text(json.dumps({"theme": "light", "verbose": True}))

        config = get_global_config()

        assert config.theme == "light"
        assert config.verbose is True

    def test_returns_defaults_on_corrupted_file(
        self, tmp_pode_dir: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        (tmp_pode_dir / "config.json").write_text("not valid json")

        config = get_global_config()

        assert config.theme == "dark"


class TestSaveGlobalConfig:
    def test_writes_and_reads_back(self, tmp_pode_dir: Path) -> None:
        original = get_global_config()
        modified = original.model_copy(update={"theme": "light"})
        save_global_config(modified)

        reloaded = get_global_config(refresh=True)
        assert reloaded.theme == "light"

    def test_creates_parent_dirs(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        nested = tmp_path / "nested" / "pode"
        monkeypatch.setenv("PODE_CONFIG_DIR", str(nested))

        save_global_config(GlobalConfig())

        assert (nested / "config.json").exists()

    def test_atomic_write_no_partial_on_error(self, tmp_pode_dir: Path) -> None:
        config_file = tmp_pode_dir / "config.json"
        config_file.write_text(json.dumps({"theme": "dark"}))

        save_global_config(GlobalConfig(theme="light"))

        # File should contain valid JSON
        content = config_file.read_text()
        data = json.loads(content)
        assert data["theme"] == "light"


class TestProjectConfig:
    def test_reads_from_cwd(self, tmp_cwd: Path) -> None:
        (tmp_cwd / ".pode.json").write_text(
            json.dumps({"allowed_tools": ["bash"]})
        )

        config = get_current_project_config()
        assert "bash" in config.allowed_tools

    def test_returns_defaults_when_no_file(self, tmp_cwd: Path) -> None:
        config = get_current_project_config()
        assert config.allowed_tools == []

    def test_save_and_reload(self, tmp_cwd: Path) -> None:
        config = ProjectConfig(denied_tools=["rm_rf"])
        save_current_project_config(config)

        reloaded = get_current_project_config()
        assert "rm_rf" in reloaded.denied_tools


class TestConfigCli:
    def test_get_existing_key(self, tmp_pode_dir: Path) -> None:
        save_global_config(GlobalConfig(theme="light"))
        result = get_config_for_cli("theme")
        assert result == "light"

    def test_get_nested_key(self, tmp_pode_dir: Path) -> None:
        result = get_config_for_cli("model_pointers.main")
        assert result == "claude-sonnet-4-5-20251101"

    def test_get_missing_key_returns_none(self, tmp_pode_dir: Path) -> None:
        result = get_config_for_cli("nonexistent_key")
        assert result is None

    def test_set_and_get(self, tmp_pode_dir: Path) -> None:
        set_config_for_cli("theme", "light")
        result = get_config_for_cli("theme")
        assert result == "light"

    def test_set_unknown_key_raises(self, tmp_pode_dir: Path) -> None:
        with pytest.raises(ConfigError):
            set_config_for_cli("totally_unknown_key", "value")

    def test_list_returns_flat_dict(self, tmp_pode_dir: Path) -> None:
        items = list_config_for_cli()
        assert "theme" in items
        assert "verbose" in items
        assert items["theme"] == "dark"

    def test_set_bool_from_string(self, tmp_pode_dir: Path) -> None:
        set_config_for_cli("verbose", "true")
        assert get_config_for_cli("verbose") is True
