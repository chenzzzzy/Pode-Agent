"""Tests for entrypoints/cli.py — CLI print mode and config commands."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from pode_agent import __version__
from pode_agent.entrypoints.cli import app, config_app

runner = CliRunner()


# ---------------------------------------------------------------------------
# --version
# ---------------------------------------------------------------------------


class TestVersion:
    def test_version_flag(self) -> None:
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert __version__ in result.output

    def test_version_short_flag(self) -> None:
        result = runner.invoke(app, ["-v"])
        assert result.exit_code == 0
        assert __version__ in result.output


# ---------------------------------------------------------------------------
# No prompt — REPL placeholder
# ---------------------------------------------------------------------------


class TestNoPrompt:
    @patch("pode_agent.entrypoints.cli.asyncio")
    def test_no_args_launches_repl(self, mock_asyncio: MagicMock) -> None:
        """Without args, CLI attempts to launch REPL."""
        mock_asyncio.run.return_value = 0
        result = runner.invoke(app, [])
        assert result.exit_code == 0
        mock_asyncio.run.assert_called_once()

    def test_no_args_bun_not_found(self) -> None:
        """Without Bun installed, shows error and exits 1."""
        with patch("pode_agent.entrypoints.cli.asyncio") as mock_asyncio:
            # Make asyncio.run call _launch_repl which checks for Bun
            async def _fake_launch(*args: Any, **kwargs: Any) -> int:
                return 1
            mock_asyncio.run.side_effect = lambda coro: 1
            result = runner.invoke(app, [])
            assert result.exit_code == 1


# ---------------------------------------------------------------------------
# Print mode — prompt argument triggers run_print_mode
# ---------------------------------------------------------------------------


class TestPrintMode:
    @patch("pode_agent.entrypoints.cli.asyncio")
    @patch("pode_agent.core.tools.registry.ToolRegistry")
    def test_prompt_triggers_print_mode(
        self, mock_registry: MagicMock, mock_asyncio: MagicMock
    ) -> None:
        mock_asyncio.run.return_value = 0
        mock_registry.return_value.tools = []

        result = runner.invoke(app, ["hello world"])
        assert result.exit_code == 0
        mock_asyncio.run.assert_called_once()

    @patch("pode_agent.entrypoints.cli.asyncio")
    @patch("pode_agent.core.tools.registry.ToolRegistry")
    def test_prompt_with_model_option(
        self, mock_registry: MagicMock, mock_asyncio: MagicMock
    ) -> None:
        mock_asyncio.run.return_value = 0
        mock_registry.return_value.tools = []

        # Options must come before positional argument in Typer
        result = runner.invoke(app, ["--model", "gpt-4o", "test prompt"])
        assert result.exit_code == 0
        assert mock_asyncio.run.called

    @patch("pode_agent.entrypoints.cli.asyncio")
    @patch("pode_agent.core.tools.registry.ToolRegistry")
    def test_prompt_with_json_output(
        self, mock_registry: MagicMock, mock_asyncio: MagicMock
    ) -> None:
        mock_asyncio.run.return_value = 0
        mock_registry.return_value.tools = []

        result = runner.invoke(app, ["--output-format", "json", "test"])
        assert result.exit_code == 0
        assert mock_asyncio.run.called

    @patch("pode_agent.entrypoints.cli.asyncio")
    @patch("pode_agent.core.tools.registry.ToolRegistry")
    def test_prompt_with_verbose_flag(
        self, mock_registry: MagicMock, mock_asyncio: MagicMock
    ) -> None:
        mock_asyncio.run.return_value = 0
        mock_registry.return_value.tools = []

        result = runner.invoke(app, ["--verbose", "test"])
        assert result.exit_code == 0
        assert mock_asyncio.run.called

    @patch("pode_agent.entrypoints.cli.asyncio")
    @patch("pode_agent.core.tools.registry.ToolRegistry")
    def test_prompt_with_safe_flag(
        self, mock_registry: MagicMock, mock_asyncio: MagicMock
    ) -> None:
        mock_asyncio.run.return_value = 0
        mock_registry.return_value.tools = []

        result = runner.invoke(app, ["--safe", "test"])
        assert result.exit_code == 0
        assert mock_asyncio.run.called

    @patch("pode_agent.entrypoints.cli.asyncio")
    @patch("pode_agent.core.tools.registry.ToolRegistry")
    def test_error_exit_code_propagated(
        self, mock_registry: MagicMock, mock_asyncio: MagicMock
    ) -> None:
        mock_asyncio.run.return_value = 1
        mock_registry.return_value.tools = []

        result = runner.invoke(app, ["test"])
        assert result.exit_code == 1

    @patch("pode_agent.entrypoints.cli.asyncio")
    @patch("pode_agent.core.tools.registry.ToolRegistry")
    def test_permission_denied_exit_code(
        self, mock_registry: MagicMock, mock_asyncio: MagicMock
    ) -> None:
        mock_asyncio.run.return_value = 2
        mock_registry.return_value.tools = []

        result = runner.invoke(app, ["test"])
        assert result.exit_code == 2


# ---------------------------------------------------------------------------
# Config subcommand — get/set/list
# Test config_app directly to avoid positional prompt arg intercepting "config"
# ---------------------------------------------------------------------------


class TestConfigGet:
    @patch("pode_agent.entrypoints.cli.get_config_for_cli")
    def test_config_get_existing_key(self, mock_get: MagicMock) -> None:
        mock_get.return_value = "dark"
        result = runner.invoke(config_app, ["get", "theme"])
        assert result.exit_code == 0
        assert "dark" in result.output

    @patch("pode_agent.entrypoints.cli.get_config_for_cli")
    def test_config_get_missing_key(self, mock_get: MagicMock) -> None:
        mock_get.return_value = None
        result = runner.invoke(config_app, ["get", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()


class TestConfigSet:
    @patch("pode_agent.entrypoints.cli.set_config_for_cli")
    def test_config_set_success(self, mock_set: MagicMock) -> None:
        result = runner.invoke(config_app, ["set", "theme", "light"])
        assert result.exit_code == 0
        assert "theme" in result.output
        mock_set.assert_called_once_with("theme", "light", global_=True)


class TestConfigList:
    @patch("pode_agent.entrypoints.cli.list_config_for_cli")
    def test_config_list(self, mock_list: MagicMock) -> None:
        mock_list.return_value = {"theme": "dark", "model": "claude-sonnet-4-5"}
        result = runner.invoke(config_app, ["list"])
        assert result.exit_code == 0
        assert "theme" in result.output
        assert "model" in result.output


# ---------------------------------------------------------------------------
# ToolLoader integration (Fix 1)
# ---------------------------------------------------------------------------


class TestToolLoaderIntegration:
    @patch("pode_agent.core.config.loader.get_global_config")
    @patch("pode_agent.core.tools.loader.ToolLoader")
    @patch("pode_agent.core.tools.registry.ToolRegistry")
    def test_tool_loader_called_on_print_mode(
        self,
        mock_registry_cls: MagicMock,
        mock_loader_cls: MagicMock,
        mock_get_config: MagicMock,
    ) -> None:
        """ToolLoader.load_all() should be called in print mode."""
        import asyncio as real_asyncio
        from unittest.mock import AsyncMock

        mock_registry = MagicMock()
        mock_registry.tools = []
        mock_registry_cls.return_value = mock_registry
        mock_loader = MagicMock()
        mock_loader.load_all = AsyncMock()
        mock_loader_cls.return_value = mock_loader
        mock_get_config.return_value = MagicMock(default_model_name="test-model")

        with patch("pode_agent.app.print_mode.run_print_mode", new_callable=AsyncMock, return_value=0):
            with patch("pode_agent.entrypoints.cli.asyncio") as mock_aio:
                mock_aio.run = real_asyncio.run
                result = runner.invoke(app, ["test prompt"])

        assert result.exit_code == 0
        mock_loader.load_all.assert_called_once()
