"""Tests for auto-compact framework."""

from __future__ import annotations

from pode_agent.app.compact import (
    auto_compact_if_needed,
    compact_messages,
    _estimate_chars,
)


def _msg(role: str, content: str) -> dict:
    return {"role": role, "content": content}


class TestEstimateChars:
    def test_string_content(self) -> None:
        msgs = [_msg("user", "hello"), _msg("assistant", "world")]
        assert _estimate_chars(msgs) == len("hello") + len("world")

    def test_list_content(self) -> None:
        msgs = [{"role": "assistant", "content": [
            {"type": "text", "text": "hello"},
        ]}]
        assert _estimate_chars(msgs) == len("hello")

    def test_empty(self) -> None:
        assert _estimate_chars([]) == 0


class TestCompactMessages:
    def test_short_list_unchanged(self) -> None:
        msgs = [_msg("user", "hi"), _msg("assistant", "hello")]
        result = compact_messages(msgs)
        assert result is msgs  # same object, not copied

    def test_truncation_keeps_recent(self) -> None:
        msgs = [_msg("user", f"msg{i}") for i in range(20)]
        result = compact_messages(msgs, keep_recent=5)
        # Should have: notice + last 5
        assert len(result) == 6  # 1 notice + 5 recent
        assert result[-1]["content"] == "msg19"
        assert result[-5]["content"] == "msg15"

    def test_system_prefix_preserved(self) -> None:
        msgs = [
            {"role": "system", "content": "system prompt"},
            *[_msg("user", f"msg{i}") for i in range(15)],
        ]
        result = compact_messages(msgs, keep_recent=5)
        assert result[0]["role"] == "system"
        assert "system prompt" in result[0]["content"]

    def test_compaction_notice_inserted(self) -> None:
        msgs = [_msg("user", f"msg{i}") for i in range(20)]
        result = compact_messages(msgs, keep_recent=5)
        notice = result[0]
        assert "compacted" in notice["content"].lower()
        assert "15" in notice["content"]  # 15 messages were truncated

    def test_does_not_mutate_input(self) -> None:
        msgs = [_msg("user", f"msg{i}") for i in range(20)]
        original_len = len(msgs)
        compact_messages(msgs, keep_recent=5)
        assert len(msgs) == original_len


class TestAutoCompactIfNeeded:
    def test_no_compaction_under_threshold(self) -> None:
        msgs = [_msg("user", "short")]
        result = auto_compact_if_needed(msgs)
        assert result is msgs

    def test_compaction_triggered_by_count(self) -> None:
        msgs = [_msg("user", f"msg{i}") for i in range(60)]
        result = auto_compact_if_needed(msgs, max_messages=50, keep_recent=10)
        assert len(result) < len(msgs)
        assert result[-1]["content"] == "msg59"

    def test_compaction_triggered_by_chars(self) -> None:
        long_content = "x" * 100_000
        msgs = [
            _msg("user", long_content),
            _msg("user", long_content),
            _msg("user", long_content),
            _msg("user", long_content),
            _msg("user", "recent"),
        ]
        result = auto_compact_if_needed(msgs, max_messages=100, max_chars=200_000, keep_recent=2)
        assert len(result) < len(msgs)
        assert result[-1]["content"] == "recent"

    def test_custom_thresholds(self) -> None:
        msgs = [_msg("user", f"msg{i}") for i in range(5)]
        result = auto_compact_if_needed(msgs, max_messages=3, keep_recent=2)
        assert len(result) < len(msgs)
