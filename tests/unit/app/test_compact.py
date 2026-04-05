"""Tests for token-aware auto-compact and tool-output truncation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from pode_agent.app.compact import (
    AUTO_COMPACT_THRESHOLD_RATIO,
    DEFAULT_KEEP_RECENT,
    auto_compact_if_needed,
    calculate_auto_compact_thresholds,
    count_tokens_from_usage,
    select_files_for_recovery,
    truncate_messages,
    truncate_text_for_assistant,
)
from pode_agent.app.query import QueryOptions
from pode_agent.core.config.schema import GlobalConfig
from pode_agent.services.ai.base import AIResponse, TokenUsage


def _msg(role: str, content: str) -> dict:
    return {"role": role, "content": content}


def _assistant_with_usage(total_input: int, total_output: int, *, synthetic: str | None = None) -> dict:
    msg = {
        "type": "assistant",
        "message": [{"type": "text", "text": "assistant"}],
        "usage": {
            "input_tokens": total_input,
            "output_tokens": total_output,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
        },
    }
    if synthetic:
        msg["synthetic"] = synthetic
    return msg


class TestTruncateTextForAssistant:
    def test_short_text_unchanged(self) -> None:
        result = truncate_text_for_assistant("hello\nworld")
        assert result.text == "hello\nworld"
        assert result.truncated is False

    def test_truncates_by_lines_and_chars(self) -> None:
        text = "\n".join(f"line {i}" for i in range(200))
        result = truncate_text_for_assistant(text, max_lines=3, max_chars=12)
        assert result.truncated is True
        assert "[truncated" in result.text
        assert result.omitted_lines > 0


class TestTokenCounting:
    def test_uses_latest_real_assistant_usage(self) -> None:
        messages = [
            _assistant_with_usage(10, 5, synthetic="auto_compact_summary"),
            _assistant_with_usage(100, 40),
        ]
        assert count_tokens_from_usage(messages) == 140

    def test_adds_estimate_for_messages_after_usage(self) -> None:
        messages = [
            _assistant_with_usage(100, 40),
            _msg("user", "x" * 400),
        ]
        assert count_tokens_from_usage(messages) >= 240

    def test_estimates_tokens_without_usage(self) -> None:
        assert count_tokens_from_usage([_msg("user", "hello")]) > 0

    def test_calculates_thresholds(self) -> None:
        thresholds = calculate_auto_compact_thresholds(160_000, 200_000)
        assert thresholds.auto_compact_threshold == int(200_000 * AUTO_COMPACT_THRESHOLD_RATIO)
        assert thresholds.is_above_auto_compact_threshold is True


class TestFileRecovery:
    def test_recovers_recently_referenced_files(self, tmp_path: Path) -> None:
        foo = tmp_path / "src" / "foo.py"
        foo.parent.mkdir()
        foo.write_text("print('foo')\n", encoding="utf-8")

        bar = tmp_path / "README.md"
        bar.write_text("# hello\n", encoding="utf-8")

        messages = [
            {
                "type": "assistant",
                "message": [
                    {
                        "type": "tool_use",
                        "name": "file_read",
                        "input": {"file_path": "src/foo.py"},
                    }
                ],
            },
            _msg("user", "Please also keep README.md in mind."),
        ]

        recovered = select_files_for_recovery(messages, str(tmp_path))
        paths = {item.path for item in recovered}
        assert "src\\foo.py" in paths or "src/foo.py" in paths
        assert "README.md" in paths


class TestFallbackTruncation:
    def test_truncate_messages_keeps_recent(self) -> None:
        messages = [_msg("user", f"msg{i}") for i in range(20)]
        result = truncate_messages(messages, keep_recent=5)
        assert len(result) == 6
        assert result[-1]["content"] == "msg19"


@pytest.mark.asyncio
class TestAutoCompact:
    async def test_no_compaction_below_token_threshold(self, tmp_path: Path) -> None:
        messages = [
            _msg("user", "hello"),
            _assistant_with_usage(10_000, 500),
            _msg("user", "follow-up"),
        ]
        options = QueryOptions(model="claude-sonnet-4-5", cwd=str(tmp_path))

        with patch("pode_agent.app.compact.get_global_config", return_value=GlobalConfig()):
            result = await auto_compact_if_needed(messages, options)

        assert result is messages

    async def test_compacts_with_summary_and_recovered_files(self, tmp_path: Path) -> None:
        source = tmp_path / "src" / "worker.py"
        source.parent.mkdir()
        source.write_text("def run() -> None:\n    pass\n", encoding="utf-8")

        messages = [
            _msg("user", "Investigate src/worker.py"),
            {
                "type": "assistant",
                "message": [
                    {
                        "type": "tool_use",
                        "name": "file_read",
                        "input": {"file_path": "src/worker.py"},
                    }
                ],
            },
            _msg("user", "old context"),
            _assistant_with_usage(170_000, 5_000),
            _msg("user", "recent request"),
            _msg("assistant", "recent reply"),
        ]
        options = QueryOptions(model="claude-sonnet-4-5", cwd=str(tmp_path))

        async def fake_query_llm(*_args, **_kwargs):
            yield AIResponse(type="text_delta", text="## Current Status\n- done")
            yield AIResponse(
                type="message_done",
                usage=TokenUsage(input_tokens=1_000, output_tokens=200),
            )

        with (
            patch("pode_agent.app.compact.get_global_config", return_value=GlobalConfig()),
            patch("pode_agent.app.compact.query_llm", new=fake_query_llm),
        ):
            result = await auto_compact_if_needed(messages, options, keep_recent=2)

        assert result is not messages
        assert any(msg.get("synthetic") == "auto_compact_notice" for msg in result)
        assert any(msg.get("synthetic") == "auto_compact_summary" for msg in result)
        assert any(msg.get("synthetic") == "auto_compact_recovery" for msg in result)
        assert result[-2:] == messages[-2:]

    async def test_large_fresh_user_message_can_trigger_compaction(self, tmp_path: Path) -> None:
        messages = [
            _msg("user", "initial"),
            _assistant_with_usage(150_000, 5_000),
            _msg("user", "x" * 60_000),
        ]
        options = QueryOptions(model="claude-sonnet-4-5", cwd=str(tmp_path))

        async def fake_query_llm(*_args, **_kwargs):
            yield AIResponse(type="text_delta", text="summary")
            yield AIResponse(type="message_done", usage=TokenUsage(output_tokens=100))

        with (
            patch("pode_agent.app.compact.get_global_config", return_value=GlobalConfig()),
            patch("pode_agent.app.compact.query_llm", new=fake_query_llm),
        ):
            result = await auto_compact_if_needed(messages, options, keep_recent=1)

        assert any(msg.get("synthetic") == "auto_compact_summary" for msg in result)

    async def test_summary_failure_falls_back_to_truncation(self, tmp_path: Path) -> None:
        messages = [
            _msg("user", f"old {i}") for i in range(DEFAULT_KEEP_RECENT + 5)
        ]
        messages.insert(1, _assistant_with_usage(170_000, 5_000))
        options = QueryOptions(model="claude-sonnet-4-5", cwd=str(tmp_path))

        async def failing_query_llm(*_args, **_kwargs):
            raise RuntimeError("boom")
            yield  # pragma: no cover

        with (
            patch("pode_agent.app.compact.get_global_config", return_value=GlobalConfig()),
            patch("pode_agent.app.compact.query_llm", new=failing_query_llm),
        ):
            result = await auto_compact_if_needed(messages, options)

        assert any(msg.get("synthetic") == "auto_compact_notice" for msg in result)
        assert len(result) == DEFAULT_KEEP_RECENT + 1
