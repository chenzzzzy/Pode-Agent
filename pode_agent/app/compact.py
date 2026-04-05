"""Token-aware context compression and tool-output truncation.

This module implements a three-layer compaction pipeline inspired by
Kode-Agent:

1. Tool output truncation for LLM-facing tool_result blocks
2. Token-aware auto-compact at 80% of the model context window
3. LLM-generated conversation summary plus lightweight file recovery

The runtime uses real provider usage when available, with the previous
character-count heuristics retained only as a fallback for providers that
do not report usage.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pode_agent.core.config.loader import get_global_config
from pode_agent.core.config.schema import GlobalConfig
from pode_agent.services.ai.base import TokenUsage, UnifiedRequestParams
from pode_agent.services.ai.factory import ModelAdapterFactory, query_llm
from pode_agent.services.context import clear_context_cache

logger = logging.getLogger(__name__)

# Auto-compact trigger thresholds
AUTO_COMPACT_THRESHOLD_RATIO = 0.8
AUTO_COMPACT_THRESHOLD_MESSAGES = 50
AUTO_COMPACT_THRESHOLD_CHARS = 400_000  # fallback when provider usage is unavailable
DEFAULT_KEEP_RECENT = 10

# Tool-result truncation
TOOL_OUTPUT_MAX_LINES = 120
TOOL_OUTPUT_MAX_CHARS = 12_000

# File recovery
MAX_FILES_TO_RECOVER = 5
MAX_TOKENS_PER_FILE = 10_000
MAX_TOTAL_FILE_TOKENS = 50_000
CHARS_PER_TOKEN_ESTIMATE = 4
RECENT_MESSAGES_TO_SCAN = 40

COMPRESSION_SYSTEM_PROMPT = (
    "You are a helpful AI assistant tasked with creating comprehensive "
    "conversation summaries that preserve the exact engineering context "
    "needed to continue the work without re-reading the full transcript."
)

COMPRESSION_PROMPT = """Please provide a comprehensive summary of our conversation structured as follows:

## Technical Context
Development environment, tools, frameworks, and configurations in use. Programming languages, libraries, and technical constraints. File structure, directory organization, and project architecture.

## Project Overview
Main project goals, features, and scope. Key components, modules, and their relationships. Data models, APIs, and integration patterns.

## Code Changes
Files created, modified, or analyzed during our conversation. Specific code implementations, functions, and algorithms added. Configuration changes and structural modifications.

## Debugging & Issues
Problems encountered and their root causes. Solutions implemented and their effectiveness. Error messages, logs, and diagnostic information.

## Current Status
What we just completed successfully. Current state of the codebase and any ongoing work. Test results, validation steps, and verification performed.

## Pending Tasks
Immediate next steps and priorities. Planned features, improvements, and refactoring. Known issues, technical debt, and areas needing attention.

## User Preferences
Coding style, formatting, and organizational preferences. Communication patterns and feedback style. Tool choices and workflow preferences.

## Key Decisions
Important technical decisions made and their rationale. Alternative approaches considered and why they were rejected. Trade-offs accepted and their implications.

Focus on concrete files, APIs, tests, failures, and remaining work. Avoid filler."""

_PATH_RE = re.compile(
    r"""
    (?:
        [A-Za-z]:\\[^\s"'`<>|]+
        |
        (?:\.{0,2}[\\/])?(?:[\w.-]+[\\/])+[\w.-]+
        |
        \b(?:README|AGENTS|CLAUDE)\.md\b
        |
        \b(?:pyproject|package|tsconfig|bunfig)\.toml\b
        |
        \bpackage\.json\b
    )
    """,
    re.VERBOSE,
)


@dataclass(frozen=True)
class TruncateResult:
    """Result for display-friendly tool output truncation."""

    text: str
    truncated: bool
    omitted_lines: int
    omitted_chars: int


@dataclass(frozen=True)
class AutoCompactThresholds:
    """Computed compact threshold metadata."""

    token_count: int
    context_length: int
    auto_compact_threshold: int
    percent_used: int
    is_above_auto_compact_threshold: bool


@dataclass(frozen=True)
class RecoveredFile:
    """A recovered project file injected after compaction."""

    path: str
    content: str
    tokens: int
    truncated: bool


def truncate_text_for_assistant(
    text: str,
    *,
    max_lines: int = TOOL_OUTPUT_MAX_LINES,
    max_chars: int = TOOL_OUTPUT_MAX_CHARS,
) -> TruncateResult:
    """Truncate verbose tool output before it enters the LLM context."""
    normalized = str(text or "")
    lines = normalized.splitlines()

    working_lines = lines
    omitted_lines = 0
    if max_lines > 0 and len(lines) > max_lines:
        working_lines = lines[:max_lines]
        omitted_lines = len(lines) - max_lines

    working_text = "\n".join(working_lines)
    omitted_chars = 0
    if max_chars > 0 and len(working_text) > max_chars:
        omitted_chars = len(working_text) - max_chars
        working_text = working_text[:max_chars]

    truncated = omitted_lines > 0 or omitted_chars > 0
    if not truncated:
        return TruncateResult(
            text=working_text,
            truncated=False,
            omitted_lines=0,
            omitted_chars=0,
        )

    suffix_parts: list[str] = []
    if omitted_lines > 0:
        suffix_parts.append(f"{omitted_lines} lines")
    if omitted_chars > 0:
        suffix_parts.append(f"{omitted_chars} chars")

    suffix = f"\n\n... [truncated {' · '.join(suffix_parts)}] ..."
    return TruncateResult(
        text=working_text + suffix,
        truncated=True,
        omitted_lines=omitted_lines,
        omitted_chars=omitted_chars,
    )


def truncate_tool_result_content(text: str) -> str:
    """Return the LLM-facing version of a tool result."""
    return truncate_text_for_assistant(text).text


def count_tokens_from_usage(messages: list[dict[str, Any]]) -> int:
    """Estimate current context tokens from usage plus trailing messages."""
    estimated_total = _estimate_message_tokens(messages)

    for index in range(len(messages) - 1, -1, -1):
        msg = messages[index]
        if _message_role(msg) != "assistant":
            continue
        if msg.get("synthetic") == "auto_compact_summary":
            continue
        usage = msg.get("usage")
        if not isinstance(usage, dict):
            continue
        usage_total = (
            int(usage.get("input_tokens", 0))
            + int(usage.get("output_tokens", 0))
            + int(usage.get("cache_read_tokens", 0))
            + int(usage.get("cache_write_tokens", 0))
        )
        trailing_estimate = _estimate_message_tokens(messages[index + 1 :])
        return max(estimated_total, usage_total + trailing_estimate)
    return estimated_total


def calculate_auto_compact_thresholds(
    token_count: int,
    context_length: int,
    *,
    ratio: float = AUTO_COMPACT_THRESHOLD_RATIO,
) -> AutoCompactThresholds:
    """Calculate the auto-compact budget for a model context window."""
    safe_context_length = context_length if context_length > 0 else 1
    threshold = int(safe_context_length * ratio)
    percent_used = round((token_count / safe_context_length) * 100) if safe_context_length else 0
    return AutoCompactThresholds(
        token_count=token_count,
        context_length=safe_context_length,
        auto_compact_threshold=threshold,
        percent_used=percent_used,
        is_above_auto_compact_threshold=token_count >= threshold,
    )


async def auto_compact_if_needed(
    messages: list[dict[str, Any]],
    options: Any,
    *,
    keep_recent: int = DEFAULT_KEEP_RECENT,
    config: GlobalConfig | None = None,
) -> list[dict[str, Any]]:
    """Compact long conversations when they approach the model context limit."""
    if len(messages) < 3:
        return messages

    cfg = config or get_global_config()
    token_count = count_tokens_from_usage(messages)
    context_length = _resolve_context_length(options.model, cfg)
    thresholds = calculate_auto_compact_thresholds(
        token_count,
        context_length,
        ratio=AUTO_COMPACT_THRESHOLD_RATIO,
    )
    heuristic_triggered = (
        len(messages) > AUTO_COMPACT_THRESHOLD_MESSAGES
        or _estimate_chars(messages) > AUTO_COMPACT_THRESHOLD_CHARS
    )

    if not thresholds.is_above_auto_compact_threshold and not heuristic_triggered:
        return messages

    if thresholds.is_above_auto_compact_threshold:
        logger.info(
            "Auto-compact triggered by usage: %d tokens / %d (%d%%)",
            thresholds.token_count,
            thresholds.context_length,
            thresholds.percent_used,
        )
    else:
        logger.info(
            "Auto-compact triggered by fallback heuristic: %d messages, ~%d chars",
            len(messages),
            _estimate_chars(messages),
        )

    try:
        return await compact_messages(messages, options=options, keep_recent=keep_recent, config=cfg)
    except Exception:
        logger.exception("LLM auto-compact failed; falling back to truncation")
        return truncate_messages(messages, keep_recent=keep_recent)


async def compact_messages(
    messages: list[dict[str, Any]],
    *,
    options: Any,
    keep_recent: int = DEFAULT_KEEP_RECENT,
    config: GlobalConfig | None = None,
) -> list[dict[str, Any]]:
    """Replace older history with an LLM-generated summary plus recovered files."""
    if len(messages) <= keep_recent:
        return messages

    system_prefix = _split_system_prefix(messages)
    remaining = messages[len(system_prefix):]
    if len(remaining) <= keep_recent:
        return messages

    to_summarize = remaining[:-keep_recent]
    if not to_summarize:
        return messages

    cfg = config or get_global_config()
    summary_text, summary_usage, model_used, model_notice = await generate_compaction_summary(
        messages=[*system_prefix, *to_summarize],
        model_name=options.model,
        config=cfg,
    )
    notice_parts = [
        "Context automatically compressed to preserve working memory.",
        f"Used '{model_used}' for the summary pass.",
    ]
    if model_notice:
        notice_parts.append(model_notice)

    notice_message = _build_user_message(" ".join(notice_parts), synthetic="auto_compact_notice")
    summary_message = _build_summary_message(summary_text, summary_usage)
    base_messages = [
        *system_prefix,
        notice_message,
        summary_message,
        *remaining[-keep_recent:],
    ]
    recovered_files = select_files_for_recovery(
        messages,
        options.cwd or None,
        max_total_tokens=_calculate_recovery_budget(base_messages, options.model, cfg),
    )
    compacted_messages = [
        *system_prefix,
        notice_message,
        summary_message,
        *[_build_recovery_message(file) for file in recovered_files],
        *remaining[-keep_recent:],
    ]

    clear_context_cache()
    return compacted_messages


def truncate_messages(
    messages: list[dict[str, Any]],
    *,
    keep_recent: int = DEFAULT_KEEP_RECENT,
) -> list[dict[str, Any]]:
    """Fallback strategy: keep the most recent messages plus a notice."""
    if len(messages) <= keep_recent:
        return messages

    system_prefix = _split_system_prefix(messages)
    remaining = messages[len(system_prefix):]
    if len(remaining) <= keep_recent:
        return messages

    truncated_count = len(remaining) - keep_recent
    notice = _build_user_message(
        (
            f"[System: {truncated_count} earlier messages were compacted to save "
            "context space. Only the recent conversation remains below.]"
        ),
        synthetic="auto_compact_notice",
    )
    return [*system_prefix, notice, *remaining[-keep_recent:]]


async def generate_compaction_summary(
    *,
    messages: list[dict[str, Any]],
    model_name: str,
    config: GlobalConfig,
) -> tuple[str, TokenUsage, str, str | None]:
    """Generate the compacted summary, preferring the configured compact model."""
    summary_messages = [
        *_normalize_messages(messages),
        {"role": "user", "content": COMPRESSION_PROMPT},
    ]

    token_count = count_tokens_from_usage(messages)
    compact_model = config.model_pointers.compact or model_name
    current_model = model_name
    compact_notice: str | None = None
    candidates: list[tuple[str, str | None]] = []

    compact_context = _resolve_context_length(compact_model, config)
    if compact_model != current_model and token_count > 0:
        thresholds = calculate_auto_compact_thresholds(
            token_count,
            compact_context,
            ratio=AUTO_COMPACT_THRESHOLD_RATIO,
        )
        if thresholds.is_above_auto_compact_threshold:
            compact_notice = (
                f"Configured compact model '{compact_model}' did not fit the current "
                f"context (~{thresholds.token_count} tokens), so the active model was used."
            )
        else:
            candidates.append((compact_model, None))
    else:
        candidates.append((compact_model, None))

    if current_model != compact_model or not candidates:
        candidates.append((current_model, compact_notice))

    last_error: Exception | None = None
    for candidate_model, notice in candidates:
        try:
            summary, usage = await _run_summary_query(
                messages=summary_messages,
                model_name=candidate_model,
                config=config,
            )
            return summary, usage, candidate_model, notice
        except Exception as exc:  # pragma: no cover - exercised by fallback path
            logger.warning("Summary query with '%s' failed: %s", candidate_model, exc)
            last_error = exc

    if last_error is not None:
        raise last_error
    raise RuntimeError("Failed to generate compaction summary")


async def _run_summary_query(
    *,
    messages: list[dict[str, Any]],
    model_name: str,
    config: GlobalConfig,
) -> tuple[str, TokenUsage]:
    """Query the summary model and collect the final text + usage."""
    max_tokens = min(_resolve_max_tokens(model_name, config), 4096)
    params = UnifiedRequestParams(
        messages=messages,
        system_prompt=COMPRESSION_SYSTEM_PROMPT,
        model=model_name,
        max_tokens=max_tokens,
        temperature=0.0,
        tools=None,
    )

    text_parts: list[str] = []
    usage = TokenUsage()
    async for response in query_llm(params, config=config):
        if response.type == "text_delta" and response.text:
            text_parts.append(response.text)
        elif response.type == "message_done" and response.usage is not None:
            usage = response.usage
        elif response.type == "error":
            raise RuntimeError(response.error_message or f"Summary query failed for {model_name}")

    summary = "".join(text_parts).strip()
    if not summary:
        raise RuntimeError("Summary query returned empty text")
    return summary, usage


def select_files_for_recovery(
    messages: list[dict[str, Any]],
    cwd: str | None,
    *,
    max_total_tokens: int = MAX_TOTAL_FILE_TOKENS,
) -> list[RecoveredFile]:
    """Recover a few recently referenced project files after compaction."""
    if not cwd or max_total_tokens <= 0:
        return []

    root = Path(cwd).resolve()
    candidates = _rank_file_candidates(messages, root)
    recovered: list[RecoveredFile] = []
    total_tokens = 0

    for path in candidates:
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        estimated_tokens = _estimate_text_tokens(content)
        available_tokens = min(MAX_TOKENS_PER_FILE, max_total_tokens - total_tokens)
        if available_tokens <= 0:
            break
        max_chars = available_tokens * CHARS_PER_TOKEN_ESTIMATE
        truncated = estimated_tokens > available_tokens
        final_content = content[:max_chars] if truncated else content
        final_tokens = min(estimated_tokens, available_tokens)

        if total_tokens + final_tokens > max_total_tokens:
            break

        total_tokens += final_tokens
        recovered.append(
            RecoveredFile(
                path=_display_path(path, root),
                content=_add_line_numbers(final_content),
                tokens=final_tokens,
                truncated=truncated,
            )
        )
        if len(recovered) >= MAX_FILES_TO_RECOVER:
            break

    return recovered


def _rank_file_candidates(messages: list[dict[str, Any]], root: Path) -> list[Path]:
    scores: dict[Path, int] = {}
    recent_messages = messages[-RECENT_MESSAGES_TO_SCAN:]

    for index, message in enumerate(reversed(recent_messages), start=1):
        recency_score = max(1, RECENT_MESSAGES_TO_SCAN - index + 1)
        seen_in_message: set[Path] = set()
        for candidate in _extract_file_candidates(message):
            path = _normalize_candidate_path(candidate, root)
            if path is None or path in seen_in_message:
                continue
            seen_in_message.add(path)
            scores[path] = scores.get(path, 0) + recency_score

    return [path for path, _score in sorted(scores.items(), key=lambda item: (-item[1], str(item[0])))]


def _extract_file_candidates(value: Any) -> set[str]:
    candidates: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"path", "file_path", "target_file"} and isinstance(item, str):
                candidates.add(item)
            candidates.update(_extract_file_candidates(item))
        return candidates
    if isinstance(value, list):
        for item in value:
            candidates.update(_extract_file_candidates(item))
        return candidates
    if not isinstance(value, str):
        return candidates

    for match in _PATH_RE.findall(value):
        cleaned = match.strip().strip("`'\"()[]{}<>,:;")
        if cleaned:
            candidates.add(cleaned)
    return candidates


def _normalize_candidate_path(candidate: str, root: Path) -> Path | None:
    raw = candidate.strip().replace("\r", "").replace("\n", "")
    if not raw:
        return None

    path = Path(raw)
    try:
        resolved = (root / path).resolve() if not path.is_absolute() else path.resolve()
    except OSError:
        return None

    try:
        resolved.relative_to(root)
    except ValueError:
        return None

    if not resolved.exists() or not resolved.is_file():
        return None
    return resolved


def _add_line_numbers(content: str) -> str:
    lines = content.splitlines()
    if not lines:
        return ""
    width = len(str(len(lines)))
    return "\n".join(f"{index:>{width}}→{line}" for index, line in enumerate(lines, start=1))


def _display_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _estimate_text_tokens(text: str) -> int:
    return max(1, (len(text) + (CHARS_PER_TOKEN_ESTIMATE - 1)) // CHARS_PER_TOKEN_ESTIMATE)


def _estimate_message_tokens(messages: list[dict[str, Any]]) -> int:
    if not messages:
        return 0
    return max(1, _estimate_chars(messages) // CHARS_PER_TOKEN_ESTIMATE)


def _calculate_recovery_budget(
    base_messages: list[dict[str, Any]],
    model_name: str,
    config: GlobalConfig,
) -> int:
    context_length = _resolve_context_length(model_name, config)
    threshold = calculate_auto_compact_thresholds(
        0,
        context_length,
        ratio=AUTO_COMPACT_THRESHOLD_RATIO,
    ).auto_compact_threshold
    remaining = max(0, threshold - _estimate_message_tokens(base_messages))
    return min(MAX_TOTAL_FILE_TOKENS, remaining)


def _resolve_context_length(model_name: str, config: GlobalConfig) -> int:
    for profile in config.model_profiles:
        if model_name in {profile.name, profile.model_name}:
            return profile.context_length
    return ModelAdapterFactory.get_capabilities(model_name).context_length


def _resolve_max_tokens(model_name: str, config: GlobalConfig) -> int:
    for profile in config.model_profiles:
        if model_name in {profile.name, profile.model_name}:
            return profile.max_tokens
    return ModelAdapterFactory.get_capabilities(model_name).max_tokens


def _normalize_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for msg in messages:
        role = _message_role(msg)
        content = _message_content(msg)
        if isinstance(content, list | str):
            normalized.append({"role": role, "content": content})
        else:
            normalized.append({"role": role, "content": str(content) if content else ""})
    return normalized


def _split_system_prefix(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    system_prefix: list[dict[str, Any]] = []
    for msg in messages:
        if _message_role(msg) == "system":
            system_prefix.append(msg)
            continue
        break
    return system_prefix


def _build_user_message(text: str, *, synthetic: str) -> dict[str, Any]:
    return {
        "type": "user",
        "uuid": str(uuid.uuid4()),
        "message": text,
        "synthetic": synthetic,
    }


def _build_summary_message(text: str, usage: TokenUsage) -> dict[str, Any]:
    return {
        "type": "assistant",
        "uuid": str(uuid.uuid4()),
        "message": [{"type": "text", "text": text}],
        "usage": {
            "input_tokens": 0,
            "output_tokens": usage.output_tokens,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
        },
        "synthetic": "auto_compact_summary",
    }


def _build_recovery_message(file: RecoveredFile) -> dict[str, Any]:
    note = f"Recovered file: {file.path} ({file.tokens} tokens"
    if file.truncated:
        note += ", truncated"
    note += ")"
    return _build_user_message(
        f"{note}\n\n```text\n{file.content}\n```",
        synthetic="auto_compact_recovery",
    )


def _message_role(message: dict[str, Any]) -> str:
    return str(message.get("role", message.get("type", "user")))


def _message_content(message: dict[str, Any]) -> Any:
    return message.get("content", message.get("message", ""))


def _estimate_chars(messages: list[dict[str, Any]]) -> int:
    """Fallback character estimate used when provider usage is unavailable."""
    total = 0
    for msg in messages:
        content = _message_content(msg)
        if isinstance(content, str):
            total += len(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    total += len(str(part.get("text", part.get("input", ""))))
                elif isinstance(part, str):
                    total += len(part)
    return total
