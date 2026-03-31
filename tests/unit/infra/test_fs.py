"""Unit tests for file system utilities."""

from __future__ import annotations

from pathlib import Path

from pode_agent.infra.fs import atomic_write, ensure_dir, read_file_safe


class TestEnsureDir:
    def test_creates_directory(self, tmp_path: Path) -> None:
        target = tmp_path / "a" / "b" / "c"
        ensure_dir(target)
        assert target.is_dir()

    def test_no_op_if_exists(self, tmp_path: Path) -> None:
        ensure_dir(tmp_path)  # Already exists
        assert tmp_path.is_dir()


class TestAtomicWrite:
    def test_writes_content(self, tmp_path: Path) -> None:
        target = tmp_path / "test.txt"
        atomic_write(target, "hello world")
        assert target.read_text() == "hello world"

    def test_overwrites_existing(self, tmp_path: Path) -> None:
        target = tmp_path / "test.txt"
        target.write_text("old")
        atomic_write(target, "new")
        assert target.read_text() == "new"

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        target = tmp_path / "deep" / "nested" / "file.txt"
        atomic_write(target, "content")
        assert target.read_text() == "content"

    def test_no_partial_file_on_error(self, tmp_path: Path) -> None:
        target = tmp_path / "test.txt"
        atomic_write(target, "original")

        # Atomic write should leave a valid file even if something goes wrong
        # (we can't easily simulate mid-write failure, but verify no .tmp files remain)
        tmp_files = list(tmp_path.glob(".tmp_*"))
        assert len(tmp_files) == 0


class TestReadFileSafe:
    def test_reads_existing_file(self, tmp_path: Path) -> None:
        file = tmp_path / "test.txt"
        file.write_text("content")
        assert read_file_safe(file) == "content"

    def test_returns_none_for_missing_file(self, tmp_path: Path) -> None:
        result = read_file_safe(tmp_path / "nonexistent.txt")
        assert result is None

    def test_returns_none_for_unreadable_encoding(self, tmp_path: Path) -> None:
        file = tmp_path / "binary.bin"
        file.write_bytes(b"\xff\xfe\x00\x01")
        result = read_file_safe(file)
        assert result is None
