"""Bash command safety rules.

Defines the safe-command allowlist and dangerous-pattern denylist used
by the permission engine to classify bash commands without prompting.

Reference: docs/api-specs.md — Permissions API, Bash safety rules
"""

from __future__ import annotations

import re

# Commands whose first token (or first two tokens for git subcommands)
# is considered safe to run without user approval.
SAFE_BASH_COMMANDS: frozenset[str] = frozenset([
    "cat",
    "ls",
    "pwd",
    "echo",
    "date",
    "find",
    "grep",
    "rg",
    "head",
    "tail",
    "wc",
    "sort",
    "uniq",
    "which",
    "type",
    "env",
    "printenv",
    "whoami",
    "git status",
    "git log",
    "git diff",
    "git show",
    "git branch",
    "git remote",
    "git tag",
    "git stash",
    "du",
    "df",
    "file",
    "stat",
    "id",
    "uname",
    "seq",
    "tee",
    "test",
    "true",
    "false",
    "noecho",
])

# Regex patterns that mark a command as dangerous regardless of the
# first token being in the safe list (e.g. ``echo foo > file``).
DANGEROUS_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"rm\s+.*-[rRf]"),
    re.compile(r">\s*[^>]"),  # overwrite redirect (not >>)
    re.compile(r"sudo\s+"),
    re.compile(r"curl.*\|\s*(sh|bash)"),
    re.compile(r"\|\s*(sh|bash)\b"),
    re.compile(r"eval\s+"),
    re.compile(r"chmod\s"),
    re.compile(r"chown\s"),
    re.compile(r"mkfs"),
    re.compile(r"\bdd\s+"),
    re.compile(r">/dev/"),
    re.compile(r"shutdown"),
    re.compile(r"reboot"),
]


def is_safe_bash_command(command: str) -> bool:
    """Return True if *command* is considered safe to run without approval.

    Algorithm:
    1. Strip leading whitespace.
    2. Extract the first token (or first two tokens for ``git`` subcommands).
    3. Check against :data:`SAFE_BASH_COMMANDS`.
    4. Even if safe, reject if any :data:`DANGEROUS_PATTERNS` matches.
    """
    stripped = command.strip()
    if not stripped:
        return True

    parts = stripped.split(None, 2)
    if not parts:
        return True

    # Build the lookup key: "git status", "git log", etc.
    first = parts[0]
    key = f"git {parts[1]}" if first == "git" and len(parts) >= 2 else first

    if key not in SAFE_BASH_COMMANDS:
        return False

    # Even safe commands can be dangerous with redirects or pipes.
    return all(not pattern.search(stripped) for pattern in DANGEROUS_PATTERNS)
