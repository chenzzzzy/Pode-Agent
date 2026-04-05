"""Mention processor — resolves @file and @agent mentions in user input.

Modeled after Kode-Agent ``src/services/context/mentionProcessor.ts``.

Supports:
- ``@file_path`` or ``@"file path with spaces"`` — file mentions
- ``@agent-<type>`` — agent mentions
- ``@run-agent-<type>`` — run agent mentions

Resolved mentions are converted into system prompt constraints so
the LLM is aware of mentioned files and agents.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class MentionContext:
    """A single resolved mention."""

    type: str  # "file" | "agent"
    mention: str  # raw mention text (without @)
    resolved: str  # resolved path or agent type
    exists: bool  # whether the file/agent exists


@dataclass
class ProcessedMentions:
    """Result of processing mentions in user input."""

    files: list[MentionContext] = field(default_factory=list)
    agents: list[MentionContext] = field(default_factory=list)

    @property
    def has_file_mentions(self) -> bool:
        return len(self.files) > 0

    @property
    def has_agent_mentions(self) -> bool:
        return len(self.agents) > 0

    @property
    def has_any(self) -> bool:
        return self.has_file_mentions or self.has_agent_mentions

    def to_system_reminder(self) -> str | None:
        """Convert resolved mentions into a system prompt section."""
        if not self.has_any:
            return None

        parts: list[str] = []

        if self.files:
            file_lines: list[str] = []
            for m in self.files:
                if m.exists:
                    file_lines.append(
                        f"- {m.resolved} (mentioned by user — "
                        "read this file before responding)"
                    )
                else:
                    file_lines.append(
                        f"- {m.resolved} (mentioned by user — file NOT found)"
                    )
            parts.append(
                "The user mentioned these files:\n" + "\n".join(file_lines)
            )

        if self.agents:
            agent_lines: list[str] = []
            for m in self.agents:
                agent_lines.append(
                    f"- @{m.mention} → agent type: {m.resolved}"
                )
            parts.append(
                "The user mentioned these agents:\n" + "\n".join(agent_lines)
            )

        return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Patterns (matching Kode-Agent)
# ---------------------------------------------------------------------------

# @run-agent-<name> or @agent-<name>
_RE_RUN_AGENT = re.compile(r"@(run-agent-[\w\-]+)")
_RE_AGENT = re.compile(r"@(agent-[\w\-]+)")
_RE_ASK_MODEL = re.compile(r"@(ask-[\w\-]+)")

# @"file path" or @'file path' or @bare/path
_RE_FILE = re.compile(
    r'@(?:"([^"\n]+)"|\'([^\'\n]+)\'|([a-zA-Z0-9/._~:\\\-]+))'
)


# ---------------------------------------------------------------------------
# Processor
# ---------------------------------------------------------------------------


class MentionProcessor:
    """Stateful mention processor with agent cache."""

    def __init__(self) -> None:
        self._agent_cache: set[str] = set()
        self._last_agent_check: float = 0
        self._cache_ttl: float = 60.0  # seconds

    def process_mentions(
        self, user_input: str, cwd: str | None = None
    ) -> ProcessedMentions:
        """Process all @-mentions in user input.

        Args:
            user_input: Raw user prompt text.
            cwd: Working directory for resolving relative file paths.

        Returns:
            ``ProcessedMentions`` with resolved files and agents.
        """
        result = ProcessedMentions()
        work_dir = cwd or os.getcwd()

        # --- Agent mentions ---
        agent_mention_strs: set[str] = set()
        for pattern in (_RE_RUN_AGENT, _RE_AGENT, _RE_ASK_MODEL):
            for m in pattern.finditer(user_input):
                mention = m.group(1)
                if mention in agent_mention_strs:
                    continue
                agent_mention_strs.add(mention)

                agent_type = mention
                for prefix in ("run-agent-", "agent-"):
                    if agent_type.startswith(prefix):
                        agent_type = agent_type[len(prefix):]
                        break

                result.agents.append(
                    MentionContext(
                        type="agent",
                        mention=mention,
                        resolved=agent_type,
                        exists=True,  # assume available
                    )
                )

        # --- File mentions ---
        for m in _RE_FILE.finditer(user_input):
            raw_mention = m.group(0)[1:]  # strip leading @
            file_text = (m.group(1) or m.group(2) or m.group(3) or "").strip()

            # Skip if this was an agent mention
            if any(
                file_text.startswith(p)
                for p in ("run-agent-", "agent-", "ask-")
            ):
                continue

            if not file_text:
                continue

            # Normalize and resolve path
            normalized = file_text.replace("\\ ", " ")
            resolved_path = os.path.normpath(
                os.path.join(work_dir, normalized)
            )
            exists = os.path.exists(resolved_path)

            result.files.append(
                MentionContext(
                    type="file",
                    mention=raw_mention,
                    resolved=resolved_path,
                    exists=exists,
                )
            )

        if result.has_any:
            logger.info(
                "Processed mentions: %d files, %d agents",
                len(result.files),
                len(result.agents),
            )

        return result

    def clear_cache(self) -> None:
        """Clear the agent cache."""
        self._agent_cache.clear()
        self._last_agent_check = 0


# Module-level singleton
mention_processor = MentionProcessor()


def process_mentions(
    user_input: str, cwd: str | None = None
) -> ProcessedMentions:
    """Process mentions in user input (module-level convenience)."""
    return mention_processor.process_mentions(user_input, cwd)


def clear_mention_cache() -> None:
    """Clear mention processor caches."""
    mention_processor.clear_cache()
