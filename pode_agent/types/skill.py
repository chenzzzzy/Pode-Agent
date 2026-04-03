"""Skill and plugin types — custom commands, context modifiers, marketplace.

Reference: docs/skill-system.md
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Custom command frontmatter
# ---------------------------------------------------------------------------


class CustomCommandFrontmatter(BaseModel):
    """YAML frontmatter parsed from a custom command / skill markdown file.

    Field aliases use kebab-case (the YAML convention) while Python
    attributes are snake_case.
    """

    model_config = {"populate_by_name": True}

    name: str
    description: str
    allowed_tools: list[str] | None = Field(None, alias="allowed-tools")
    argument_hint: str | None = Field(None, alias="argument-hint")
    when_to_use: str | None = None
    model: str | None = None
    max_thinking_tokens: int | None = Field(None, alias="max-thinking-tokens")
    disable_model_invocation: bool = Field(False, alias="disable-model-invocation")

    @field_validator("description")
    @classmethod
    def _validate_description_length(cls, v: str) -> str:
        if len(v) > 1024:
            raise ValueError("description must be ≤ 1024 characters")
        return v


# ---------------------------------------------------------------------------
# Custom command with scope / source information
# ---------------------------------------------------------------------------


class CommandSource(StrEnum):
    """Origin of a custom command."""

    LOCAL_SETTINGS = "local_settings"
    USER_SETTINGS = "user_settings"
    PLUGIN_DIR = "plugin_dir"


class CommandScope(StrEnum):
    """Visibility scope of a custom command."""

    PROJECT = "project"
    USER = "user"


class CustomCommandWithScope(BaseModel):
    """A fully resolved custom command (or skill) ready for use."""

    type: str = "custom_command"  # "custom_command" or "skill"
    name: str
    description: str
    file_path: Path
    frontmatter: CustomCommandFrontmatter | None = None
    content: str = ""  # raw markdown body (after frontmatter)
    source: CommandSource = CommandSource.LOCAL_SETTINGS
    scope: CommandScope = CommandScope.PROJECT
    is_skill: bool = False
    is_hidden: bool = False
    is_enabled: bool = True
    plugin_name: str | None = None
    skill_dir: Path | None = None

    def user_facing_name(self) -> str:
        """Return the display name used for matching."""
        if self.skill_dir is not None:
            return f"{self.skill_dir.name}:{self.name}"
        return self.name

    def get_prompt_for_command(self, args: str | None = None) -> str:
        """Build the prompt to inject, with $ARGUMENTS substitution."""
        prompt = self.content
        if args:
            if "$ARGUMENTS" in prompt:
                prompt = prompt.replace("$ARGUMENTS", args)
            else:
                prompt = f"{prompt}\n\nThe user provided the following arguments: {args}"
        return prompt


# ---------------------------------------------------------------------------
# Context modifier — propagated from tool results to next query iteration
# ---------------------------------------------------------------------------


class ContextModifier(BaseModel):
    """Modifications applied to QueryOptions for the next recursive call.

    Produced by SkillTool and SlashCommandTool to restrict available tools,
    switch models, or adjust thinking budgets.
    """

    allowed_tools: list[str] | None = None
    model: str | None = None
    max_thinking_tokens: int | None = None

    def apply_to_options(self, options: Any) -> Any:
        """Return a *new* options object with modifications applied.

        Uses immutable update semantics (returns a copy).
        """
        updates: dict[str, Any] = {}
        if self.allowed_tools is not None:
            updates["command_allowed_tools"] = self.allowed_tools
        if self.model is not None:
            updates["model"] = self.model
        if self.max_thinking_tokens is not None:
            updates["max_thinking_tokens"] = self.max_thinking_tokens
        if not updates:
            return options
        return options.model_copy(update=updates)


# ---------------------------------------------------------------------------
# Plugin manifest & installation types
# ---------------------------------------------------------------------------


class PluginManifest(BaseModel):
    """Validated ``plugin.json`` manifest."""

    name: str
    version: str = "0.0.1"
    description: str | None = None
    author: str | None = None
    homepage: str | None = None
    repository: str | None = None
    license: str | None = None
    keywords: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)
    agents: list[str] = Field(default_factory=list)
    hooks: list[str] = Field(default_factory=list)
    mcp_servers: dict[str, Any] = Field(default_factory=dict)


class MarketplaceSource(BaseModel):
    """Describes how to reach a marketplace."""

    type: Literal["github", "git", "url", "npm", "file", "directory"]
    url: str
    ref: str | None = None
    path: Path | None = None


class MarketplacePluginEntry(BaseModel):
    """A single plugin listed in a marketplace manifest."""

    name: str
    description: str | None = None
    source: str  # URL or path
    skills: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)


class MarketplaceManifest(BaseModel):
    """Top-level ``marketplace.json`` manifest."""

    name: str
    description: str | None = None
    plugins: list[MarketplacePluginEntry] = Field(default_factory=list)


class InstalledPlugin(BaseModel):
    """Tracks a locally installed plugin."""

    id: str
    name: str
    source: str
    install_path: Path
    enabled: bool = True
    install_mode: Literal["skill-pack", "plugin-pack"] = "plugin-pack"
    installed_at: datetime = Field(default_factory=datetime.now)
