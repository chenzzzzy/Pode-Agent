"""Global test fixtures.

Reference: docs/testing-strategy.md — Test tools and fixtures
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Set and return a temporary working directory."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def tmp_pode_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a temporary pode config directory and set PODE_CONFIG_DIR."""
    pode_dir = tmp_path / ".pode"
    pode_dir.mkdir()
    monkeypatch.setenv("PODE_CONFIG_DIR", str(pode_dir))
    return pode_dir


@pytest.fixture
def sample_project(tmp_cwd: Path) -> Path:
    """Create a sample project with some files in tmp_cwd."""
    (tmp_cwd / "main.py").write_text("def main():\n    pass\n")
    (tmp_cwd / "README.md").write_text("# Test Project\nA test project.\n")
    (tmp_cwd / "requirements.txt").write_text("pytest\n")
    return tmp_cwd
