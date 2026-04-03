"""Skill and plugin types — custom commands, context modifiers, marketplace.

Reference: docs/skill-system.md
"""

from __future__ import annotations

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

    Reference: docs/skill-system.md — YAML Frontmatter 规范
    """

    model_config = {"populate_by_name": True}

    name: str = Field(description="命令/Skill 名称，必须与目录名一致")
    description: str = Field(
        max_length=1024,
        description="简短描述，不超过 1024 字符，供 LLM 理解用途",
    )
    allowed_tools: list[str] | None = Field(
        default=None,
        alias="allowed-tools",
        description="限制 Skill 执行时可用的工具列表",
    )
    argument_hint: str | None = Field(
        default=None,
        alias="argument-hint",
        description="参数提示，显示给用户",
    )
    when_to_use: str | None = Field(
        default=None,
        description="告诉 LLM 何时使用此 Skill/Command",
    )
    model: str | None = Field(
        default=None,
        description="指定使用的模型（haiku/sonnet/opus 或 quick/task/main）",
    )
    max_thinking_tokens: int | None = Field(
        default=None,
        alias="max-thinking-tokens",
        description="扩展思考的 token 上限",
    )
    disable_model_invocation: bool | None = Field(
        default=None,
        alias="disable-model-invocation",
        description="是否禁止 LLM 自动调用（用户必须显式触发）",
    )

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
    """Origin of a custom command.

    Values use UPPER_SNAKE_CASE (Python convention for enum members).
    """

    LOCAL_SETTINGS = "LOCAL_SETTINGS"
    USER_SETTINGS = "USER_SETTINGS"
    PLUGIN_DIR = "PLUGIN_DIR"


class CommandScope(StrEnum):
    """Visibility scope of a custom command."""

    PROJECT = "project"
    USER = "user"


class CustomCommandWithScope(BaseModel):
    """A fully resolved custom command (or skill) ready for use.

    Reference: docs/skill-system.md — CustomCommandWithScope
    """

    type: Literal["prompt"] = "prompt"
    name: str
    description: str = ""
    file_path: Path
    frontmatter: CustomCommandFrontmatter | None = None
    content: str = ""
    source: CommandSource = CommandSource.LOCAL_SETTINGS
    scope: CommandScope = CommandScope.PROJECT
    is_skill: bool = False
    is_hidden: bool = False
    is_enabled: bool = True
    plugin_name: str | None = None
    skill_dir: Path | None = None

    def user_facing_name(self) -> str:
        """Return the display name used for deduplication.

        Plugin commands are prefixed with ``plugin_name:``.
        """
        if self.plugin_name:
            return f"{self.plugin_name}:{self.name}"
        return self.name

    def get_prompt_for_command(self, args: str | None = None) -> str:
        """Build the prompt to inject, with $ARGUMENTS substitution.

        Reference: docs/skill-system.md — $ARGUMENTS 替换
        """
        # Build base prompt — prepend skill_dir context if available
        parts: list[str] = []
        if self.skill_dir:
            parts.append(f"Base directory for this skill: {self.skill_dir}")
            parts.append("")
        parts.append(self.content)
        prompt = "\n".join(parts)

        # $ARGUMENTS substitution
        trimmed_args = (args or "").strip()
        if trimmed_args:
            if "$ARGUMENTS" in prompt:
                prompt = prompt.replace("$ARGUMENTS", trimmed_args)
            else:
                prompt = f"{prompt}\n\nARGUMENTS:\n{trimmed_args}"

        return prompt


# ---------------------------------------------------------------------------
# Context modifier — propagated from tool results to next query iteration
# ---------------------------------------------------------------------------


class ContextModifier(BaseModel):
    """Modifications applied to QueryOptions for the next recursive call.

    Produced by SkillTool and SlashCommandTool to restrict available tools,
    switch models, or adjust thinking budgets.

    Reference: docs/skill-system.md — contextModifier 机制
    """

    allowed_tools: list[str] | None = Field(
        default=None,
        description="限制后续可用的工具列表。非空时与现有列表合并",
    )
    model: str | None = Field(
        default=None,
        description="切换 LLM 模型。值: quick/task/main 或模型全名",
    )
    max_thinking_tokens: int | None = Field(
        default=None,
        description="设置思考 token 预算",
    )

    # Model name alias mapping: haiku→quick, sonnet→task, opus→main
    _MODEL_MAP: dict[str, str] = {
        "haiku": "quick",
        "sonnet": "task",
        "opus": "main",
    }

    def apply_to_options(self, options: Any) -> Any:
        """Return a *new* options object with modifications applied.

        Uses immutable update semantics (returns a copy via model_copy).

        Reference: docs/skill-system.md — contextModifier 应用流程
        """
        updates: dict[str, Any] = {}
        if self.allowed_tools is not None:
            existing = getattr(options, "command_allowed_tools", None) or []
            updates["command_allowed_tools"] = list(
                set(existing + self.allowed_tools)
            )
        if self.model is not None:
            updates["model"] = self._MODEL_MAP.get(self.model, self.model)
        if self.max_thinking_tokens is not None:
            updates["max_thinking_tokens"] = self.max_thinking_tokens
        if not updates:
            return options
        return options.model_copy(update=updates)


# ---------------------------------------------------------------------------
# Plugin manifest & installation types
# ---------------------------------------------------------------------------


class PluginManifest(BaseModel):
    """Validated ``plugin.json`` manifest.

    Reference: docs/skill-system.md — Plugin 清单
    """

    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str | None = None
    homepage: str | None = None
    repository: str | None = None
    license: str | None = None
    keywords: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list, description="技能目录路径列表")
    commands: list[str] = Field(default_factory=list, description="命令目录路径列表")
    agents: list[str] = Field(default_factory=list, description="Agent 配置路径列表")
    hooks: list[str] = Field(default_factory=list, description="Hook 配置路径列表")
    output_styles: list[str] = Field(
        default_factory=list, description="输出样式路径列表",
    )
    mcp_servers: dict[str, dict[str, Any]] = Field(
        default_factory=dict, description="MCP 服务器配置",
    )


class MarketplaceSource(BaseModel):
    """Describes how to reach a marketplace.

    Reference: docs/skill-system.md — Marketplace 来源类型
    """

    type: Literal["github", "git", "url", "npm", "file", "directory"]
    url: str | None = None
    ref: str = "main"
    path: str | None = None


class MarketplacePluginEntry(BaseModel):
    """A single plugin listed in a marketplace manifest."""

    name: str
    description: str = ""
    source: str
    skills: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)


class MarketplaceManifest(BaseModel):
    """Top-level ``marketplace.json`` manifest."""

    name: str
    description: str = ""
    plugins: list[MarketplacePluginEntry] = Field(default_factory=list)


class InstalledPlugin(BaseModel):
    """Tracks a locally installed plugin.

    Reference: docs/skill-system.md — InstalledPlugin
    """

    id: str
    name: str
    source: str
    install_path: Path
    enabled: bool = True
    install_mode: Literal["skill-pack", "plugin-pack"] = "plugin-pack"
    installed_at: str = ""
