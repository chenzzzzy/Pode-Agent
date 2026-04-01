"""Unit tests for JSONL session log utilities.

Reference: docs/api-specs.md — Session Log API
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pode_agent.utils.protocol.session_log import (
    get_session_log_path,
    load_messages_from_log,
    save_message,
)


class TestSessionLogPath:
    def test_generates_path_with_date(self, tmp_path: Any) -> None:
        path = get_session_log_path(base_dir=tmp_path)
        assert path.parent == tmp_path
        assert "session_fork_0" in path.name
        assert path.suffix == ".jsonl"

    def test_fork_number_in_filename(self, tmp_path: Any) -> None:
        path = get_session_log_path(fork_number=3, base_dir=tmp_path)
        assert "fork_3" in path.name

    def test_creates_log_directory(self, tmp_path: Any) -> None:
        subdir = tmp_path / "logs"
        get_session_log_path(base_dir=subdir)
        assert subdir.exists()


class TestSessionLogWrite:
    def test_writes_jsonl_line(self, tmp_path: Any) -> None:
        log = tmp_path / "test.jsonl"
        save_message(log, {"type": "user", "message": "hello"})

        content = log.read_text()
        lines = [l for l in content.strip().split("\n") if l]
        assert len(lines) == 1
        assert '"type": "user"' in lines[0]

    def test_appends_multiple_lines(self, tmp_path: Any) -> None:
        log = tmp_path / "test.jsonl"
        save_message(log, {"type": "user", "message": "first"})
        save_message(log, {"type": "assistant", "message": "second"})

        content = log.read_text()
        lines = [l for l in content.strip().split("\n") if l]
        assert len(lines) == 2


class TestSessionLogRead:
    def test_reads_single_message(self, tmp_path: Any) -> None:
        log = tmp_path / "test.jsonl"
        save_message(log, {"type": "user", "msg": "hi"})

        messages = load_messages_from_log(log)
        assert len(messages) == 1
        assert messages[0]["msg"] == "hi"

    def test_reads_multiple_messages(self, tmp_path: Any) -> None:
        log = tmp_path / "test.jsonl"
        save_message(log, {"n": 1})
        save_message(log, {"n": 2})
        save_message(log, {"n": 3})

        messages = load_messages_from_log(log)
        assert len(messages) == 3

    def test_handles_empty_file(self, tmp_path: Any) -> None:
        log = tmp_path / "empty.jsonl"
        log.write_text("")

        messages = load_messages_from_log(log)
        assert messages == []

    def test_handles_corrupted_line(self, tmp_path: Any) -> None:
        log = tmp_path / "corrupt.jsonl"
        log.write_text('{"ok": true}\n{bad json}\n{"also_ok": true}\n')

        messages = load_messages_from_log(log)
        assert len(messages) == 2

    def test_handles_missing_file(self, tmp_path: Any) -> None:
        messages = load_messages_from_log(tmp_path / "nope.jsonl")
        assert messages == []
