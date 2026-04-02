# Pode-Agent Skill System（技能系统）

> 版本：1.0.0 | 状态：草稿 | 更新：2026-04-02
> 本文档是 **Skill System 的权威设计文档**，涵盖技能/命令发现、YAML Frontmatter 规范、SkillTool/SlashCommandTool 实现、contextModifier 机制、Plugin 架构、Marketplace 分发，以及分阶段实现计划。
> 工具层调度（ToolUseQueue、并发语义）请参阅 [agent-loop.md](./agent-loop.md)。
> 工具注册/发现/权限过滤请参阅 [tools-system.md](./tools-system.md)。
> SubAgent 系统中 Agent 配置文件的加载请参阅 [subagent-system.md](./subagent-system.md)。

---

## 目录

1. [概念与动机](#概念与动机)
2. [核心架构概览](#核心架构概览)
3. [数据模型](#数据模型)
4. [SkillTool 设计](#skilltool-设计)
5. [SlashCommandTool 设计](#slashcommandtool-设计)
6. [自定义命令发现流程](#自定义命令发现流程)
7. [YAML Frontmatter 规范](#yaml-frontmatter-规范)
8. [字符预算机制](#字符预算机制)
9. [$ARGUMENTS 替换](#arguments-替换)
10. [contextModifier 机制](#contextmodifier-机制)
11. [Plugin 架构](#plugin-架构)
12. [Marketplace 系统](#marketplace-系统)
13. [Plugin 验证](#plugin-验证)
14. [存储路径映射](#存储路径映射)
15. [与 Agent Loop 的集成](#与-agent-loop-的集成)
16. [与 Tool System 的集成](#与-tool-system-的集成)
17. [分阶段实现计划](#分阶段实现计划)
18. [映射表：Kode-Agent → Pode-Agent](#映射表kode-agent--pode-agent)

---

## 概念与动机

### Skill 定义

Skill（技能）是 Pode-Agent 中一种**以 Markdown 文件定义的可扩展能力单元**。它本质上是一个预定义的 Prompt 模板，包含专业领域知识和指令，让 LLM 能以"即插即用"的方式获得特定领域的处理能力。

Skill **不是可执行代码**——它是提示工程（Prompt Engineering）的结构化封装。

### Skill vs Tool vs Command

| 维度 | Tool（工具） | Skill（技能） | Command（命令） |
|------|-------------|--------------|----------------|
| **本质** | 程序化功能（读写文件、执行 Bash） | 领域知识 + 指令模板 | 用户触发的自定义指令 |
| **定义方式** | Python 代码，继承 `Tool` ABC | `SKILL.md` + YAML frontmatter | `*.md` + YAML frontmatter |
| **调用方式** | LLM 通过 tool_use 直接执行 | LLM 通过 `SkillTool` 加载 Prompt | 用户通过 `/command-name` 调用 |
| **放置目录** | `pode_agent/tools/` | `.pode/skills/` 或 `~/.pode/skills/` | `.pode/commands/` 或 `~/.pode/commands/` |
| **isHidden** | — | `True`（LLM 自动使用） | `False`（用户可见） |
| **isSkill** | — | `True` | `False` |

**核心差异**：Command 侧重于用户主动调用（`/commit`），Skill 侧重于 LLM 在需要时自动调用。

### 解决的问题

| 问题 | Skill System 如何解决 |
|------|---------------------|
| 需要改代码才能扩展 LLM 能力 | 只需创建 Markdown 文件，零代码扩展 |
| LLM 缺乏领域专业知识 | 通过 Skill 注入最佳实践、审查清单、工作流程 |
| 不同任务需要不同工具集 | `allowed-tools` 限制 Skill 执行时的可用工具 |
| 需要不同模型处理不同任务 | `model` 字段指定使用的模型 |
| Skill 无法分发和共享 | Plugin + Marketplace 机制支持安装/分发 |

---

## 核心架构概览

### 组件关系图

```
┌─────────────────────────────────────────────────────────────┐
│                      定义层                                   │
│  SKILL.md (YAML frontmatter + Markdown)                     │
│  plugin.json (Plugin 清单)                                   │
│  marketplace.json (Marketplace 清单)                         │
└───────────────────────┬─────────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────────┐
│                      发现层                                   │
│  services/plugins/commands.py  — 文件系统扫描 + 去重          │
│  services/plugins/runtime.py   — Plugin 加载 + Session 管理  │
│  services/plugins/marketplace.py — Marketplace CRUD          │
└───────────────────────┬─────────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────────┐
│                      注册层                                   │
│  load_custom_commands() — 统一命令/技能注册表                  │
│  SkillTool.prompt()     — 生成 LLM 可用的技能列表             │
│  SlashCommandTool       — 用户可见的命令列表                   │
└───────────────────────┬─────────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────────┐
│                      调用层                                   │
│  SkillTool.call()        — 加载 Prompt + contextModifier     │
│  SlashCommandTool.call() — 加载 Command + contextModifier    │
│  $ARGUMENTS 替换         — 用户参数注入                       │
└─────────────────────────────────────────────────────────────┘
```

### Skill 生命周期

```
1. 定义 → 创建 SKILL.md 文件（或安装 Plugin）
2. 发现 → load_custom_commands() 扫描文件系统
3. 注册 → 加入统一注册表（去重）
4. 展示 → SkillTool.prompt() 列出可用 Skill
5. 调用 → LLM 选择并调用 SkillTool.call()
6. 执行 → Prompt 注入对话，LLM 按指令执行
```

### Skill 来源汇总

| 来源 | 路径模式（Pode-Agent） | 作用域 |
|------|----------------------|--------|
| 项目级 Skill | `{project}/.pode/skills/{name}/SKILL.md` | project |
| 用户级 Skill | `~/.pode/skills/{name}/SKILL.md` | user |
| 项目级 Command | `{project}/.pode/commands/{name}.md` | project |
| 用户级 Command | `~/.pode/commands/{name}.md` | user |
| Plugin Skill | `{plugin-root}/skills/{name}/SKILL.md` | plugin |
| Plugin Command | `{plugin-root}/commands/{name}.md` | plugin |
| Marketplace 安装 | 通过 `pode plugin install` 安装到上述目录 | user/project |

---

## 数据模型

> 所有模型使用 Pydantic v2 定义，位于 `pode_agent/types/skill.py`（Phase 5 新建）。

### CustomCommandFrontmatter

```python
from pydantic import BaseModel, Field
from typing import Literal

class CustomCommandFrontmatter(BaseModel):
    """SKILL.md / Command .md 文件的 YAML frontmatter 数据模型"""
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

    model_config = {"populate_by_name": True}
```

### CustomCommandWithScope

```python
from pathlib import Path

class CommandSource(str, Enum):
    """命令来源"""
    LOCAL_SETTINGS = "LOCAL_SETTINGS"    # 项目级 .pode/commands/
    USER_SETTINGS = "USER_SETTINGS"      # 用户级 ~/.pode/commands/
    PLUGIN_DIR = "PLUGIN_DIR"            # Plugin 提供

class CommandScope(str, Enum):
    """命令作用域"""
    PROJECT = "project"
    USER = "user"

class CustomCommandWithScope(BaseModel):
    """完整的命令/技能记录"""
    type: Literal["prompt"] = "prompt"
    name: str                              # 命令/Skill 名称
    description: str = ""                  # 描述
    file_path: Path                        # Markdown 文件路径
    frontmatter: CustomCommandFrontmatter  # 解析后的 frontmatter
    content: str                           # Markdown 正文（去掉 frontmatter 后的内容）
    source: CommandSource                  # 来源
    scope: CommandScope                    # 作用域
    is_skill: bool = False                 # True = Skill（LLM 自动调用）
    is_hidden: bool = False                # True = 对用户隐藏
    is_enabled: bool = True                # 是否启用
    plugin_name: str | None = None         # 来源 Plugin 名称（仅 Plugin 命令）
    skill_dir: Path | None = None          # Skill 目录路径（仅 Skill 类型）

    def user_facing_name(self) -> str:
        """用户可见名称，用于去重键"""
        if self.plugin_name:
            return f"{self.plugin_name}:{self.name}"
        return self.name

    def get_prompt_for_command(self, args: str | None = None) -> str:
        """生成 Skill/Command 的完整 Prompt 文本"""
        # 拼接基础目录路径 + 正文内容
        parts = []
        if self.skill_dir:
            parts.append(f"Base directory for this skill: {self.skill_dir}")
            parts.append("")
        parts.append(self.content)

        prompt = "\n".join(parts)

        # $ARGUMENTS 替换
        trimmed_args = (args or "").strip()
        if trimmed_args:
            if "$ARGUMENTS" in prompt:
                prompt = prompt.replace("$ARGUMENTS", trimmed_args)
            else:
                prompt = f"{prompt}\n\nARGUMENTS:\n{trimmed_args}"

        return prompt
```

### ContextModifier

```python
class ContextModifier(BaseModel):
    """工具结果携带的上下文修改指令。

    当 SkillTool/SlashCommandTool 返回 contextModifier 时，
    后续 query_core() 递归调用会使用修改后的上下文参数。
    """
    allowed_tools: list[str] | None = Field(
        default=None,
        description="限制后续可用的工具列表。非空时覆盖 options.command_allowed_tools",
    )
    model: str | None = Field(
        default=None,
        description="切换 LLM 模型。值: quick/task/main 或模型全名",
    )
    max_thinking_tokens: int | None = Field(
        default=None,
        description="设置思考 token 预算",
    )

    def apply_to_options(self, options: "QueryOptions") -> "QueryOptions":
        """将修改应用到 QueryOptions，返回新的 options 对象（不可变模式）"""
        updates = {}
        if self.allowed_tools is not None:
            existing = options.command_allowed_tools or []
            updates["command_allowed_tools"] = list(
                set(existing + self.allowed_tools)
            )
        if self.model is not None:
            # 模型名映射：haiku→quick, sonnet→task, opus→main
            model_map = {"haiku": "quick", "sonnet": "task", "opus": "main"}
            updates["model"] = model_map.get(self.model, self.model)
        if self.max_thinking_tokens is not None:
            updates["max_thinking_tokens"] = self.max_thinking_tokens

        if not updates:
            return options
        return options.model_copy(update=updates)
```

### PluginManifest

```python
class PluginManifest(BaseModel):
    """对应 .pode-plugin/plugin.json 的插件清单"""
    name: str
    version: str = "1.0.0"
    description: str = ""
    skills: list[str] = Field(default_factory=list, description="技能目录路径列表")
    commands: list[str] = Field(default_factory=list, description="命令目录路径列表")
    agents: list[str] = Field(default_factory=list, description="Agent 配置路径列表")
    hooks: list[str] = Field(default_factory=list, description="Hook 配置路径列表")
    output_styles: list[str] = Field(default_factory=list, description="输出样式路径列表")
    mcp_servers: dict[str, dict] = Field(
        default_factory=dict, description="MCP 服务器配置"
    )
```

### MarketplaceManifest / MarketplaceSource

```python
class MarketplacePluginEntry(BaseModel):
    """Marketplace 中单个 Plugin 的条目"""
    name: str
    description: str = ""
    source: str                           # 相对路径或 URL
    skills: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)

class MarketplaceManifest(BaseModel):
    """对应 marketplace.json"""
    name: str
    description: str = ""
    plugins: list[MarketplacePluginEntry] = Field(default_factory=list)

class MarketplaceSource(BaseModel):
    """Marketplace 来源配置"""
    type: Literal["github", "git", "url", "npm", "file", "directory"]
    url: str | None = None
    ref: str = "main"
    path: str | None = None
```

### InstalledPlugin

```python
class InstalledPlugin(BaseModel):
    """已安装插件的注册记录"""
    id: str                               # 插件唯一标识
    name: str
    source: str                           # 来源 marketplace 或 URL
    install_path: Path                    # 安装目录
    enabled: bool = True
    install_mode: Literal["skill-pack", "plugin-pack"] = "plugin-pack"
    installed_at: str                     # ISO 8601 时间戳
```

---

## SkillTool 设计

### 输入 Schema

```python
class SkillInput(BaseModel):
    skill: str = Field(
        description="要调用的技能名称"
    )
    args: str | None = Field(
        default=None,
        description="传递给技能的参数",
    )
```

### 完整实现规格

```python
class SkillTool(Tool):
    """让 LLM 调用已注册的技能（Skill）"""
    name = "skill"
    description = "Execute a registered skill"

    def input_schema(self) -> type[BaseModel]:
        return SkillInput

    async def is_enabled(self) -> bool:
        return True

    def is_read_only(self, input: Any = None) -> bool:
        return False

    def needs_permissions(self, input: Any = None) -> bool:
        return True

    def is_concurrency_safe(self, input: Any = None) -> bool:
        return True

    async def call(
        self,
        input: SkillInput,
        context: ToolUseContext,
    ) -> AsyncGenerator[ToolOutput, None]:
        """
        调用流程：
        1. load_custom_commands() 获取所有技能/命令列表
        2. 按 skill name 查找匹配的 CustomCommandWithScope
        3. 调用 cmd.get_prompt_for_command(args) 获取 Prompt 文本
        4. 构建 ToolOutput（含 contextModifier 和 newMessages）
        """
        commands = await load_custom_commands()

        # 按 name 查找
        cmd = next(
            (c for c in commands if c.name == input.skill and c.is_skill),
            None,
        )
        if cmd is None:
            yield ToolOutput(
                type="result",
                data={"error": f"Skill not found: {input.skill}"},
                result_for_assistant=f"Skill not found: {input.skill}",
            )
            return

        # 生成 Prompt
        prompt_text = cmd.get_prompt_for_command(input.args)

        # 提取 contextModifier（从 frontmatter）
        context_modifier = self._build_context_modifier(cmd)

        # 构建结果
        result_text = f"Launching skill: {cmd.name}"

        yield ToolOutput(
            type="result",
            data={"success": True, "command_name": cmd.name},
            result_for_assistant=result_text,
            new_messages=[
                {"role": "user", "content": prompt_text},
            ],
            context_modifier=context_modifier,
        )

    def _build_context_modifier(
        self, cmd: CustomCommandWithScope
    ) -> ContextModifier | None:
        """从命令的 frontmatter 提取 ContextModifier"""
        fm = cmd.frontmatter
        if not any([fm.allowed_tools, fm.model, fm.max_thinking_tokens]):
            return None
        return ContextModifier(
            allowed_tools=fm.allowed_tools,
            model=fm.model,
            max_thinking_tokens=fm.max_thinking_tokens,
        )

    async def prompt(self) -> str:
        """
        生成 LLM 可用的技能列表描述。
        受字符预算限制（SLASH_COMMAND_TOOL_CHAR_BUDGET，默认 15000 字符）。
        """
        commands = await load_custom_commands()
        skills = [c for c in commands if c.is_skill and not c.frontmatter.disable_model_invocation]

        budget = int(os.environ.get("SLASH_COMMAND_TOOL_CHAR_BUDGET", "15000"))
        parts = []
        used = 0

        for skill in skills:
            block = self._format_skill_block(skill)
            used += len(block) + 1
            if used > budget:
                break
            parts.append(block)

        if not parts:
            return "No skills are currently installed."

        return "\n".join(parts)

    def _format_skill_block(self, cmd: CustomCommandWithScope) -> str:
        """格式化单个 Skill 的描述块"""
        fm = cmd.frontmatter
        lines = [f"- {cmd.name}: {fm.description}"]
        if fm.when_to_use:
            lines.append(f"  When to use: {fm.when_to_use}")
        if fm.argument_hint:
            lines.append(f"  Arguments: {fm.argument_hint}")
        return "\n".join(lines)
```

---

## SlashCommandTool 设计

### 输入 Schema

```python
class SlashCommandInput(BaseModel):
    command: str = Field(
        description="The slash command to execute (without the leading /)"
    )
    args: str | None = Field(
        default=None,
        description="Arguments for the command",
    )
```

### 与 SkillTool 的差异

| 维度 | SkillTool | SlashCommandTool |
|------|-----------|-----------------|
| 触发方式 | LLM 自动调用 | 用户输入 `/command` |
| 过滤条件 | `is_skill=True` | `is_skill=False`（排除纯 Skill） |
| 可见性 | `is_hidden=True`（对用户隐藏） | `is_hidden=False`（用户可见） |
| 描述展示 | 通过 `prompt()` 列出给 LLM | 通过 REPL UI 展示给用户 |
| 内置命令 | 无 | `/help`, `/clear`, `/model` 等 |

### 实现要点

SlashCommandTool 在 Phase 3 已有骨架实现（仅支持内置命令）。Phase 5 需要扩展：

1. **命令发现**：调用 `load_custom_commands()` 获取自定义命令
2. **命令过滤**：只展示 `is_skill=False` 的命令
3. **命令执行**：匹配命令名后调用 `cmd.get_prompt_for_command(args)`
4. **contextModifier**：与 SkillTool 相同的处理逻辑
5. **内置命令保留**：`/help`, `/clear`, `/model` 等不走自定义命令流程

---

## 自定义命令发现流程

### 扫描目录

`load_custom_commands()` 按优先级扫描以下目录（Pode-Agent 路径）：

| 序号 | 路径 | 类型 | 来源 |
|------|------|------|------|
| 1 | `{project}/.pode/commands/` | 命令 | localSettings |
| 2 | `~/.pode/commands/` | 命令 | userSettings |
| 3 | `{project}/.pode/skills/` | 技能 | localSettings |
| 4 | `~/.pode/skills/` | 技能 | userSettings |
| 5 | `{project}/.pode/agents/*/commands/` | Agent 命令 | localSettings |
| 6 | `~/.pode/agents/*/commands/` | Agent 命令 | userSettings |
| 7 | `{plugin}/commands/` | Plugin 命令 | pluginDir |
| 8 | `{plugin}/skills/` | Plugin 技能 | pluginDir |

### 发现流程

```python
async def load_custom_commands() -> list[CustomCommandWithScope]:
    """
    发现并加载所有自定义命令和技能。

    步骤：
    1. 扫描 8 个标准目录
    2. 解析每个 .md 文件的 YAML frontmatter
    3. 对技能目录（skills/）查找 SKILL.md，设置 is_skill=True, is_hidden=True
    4. 按 user_facing_name() 去重（后者优先）
    5. 返回去重后的列表

    结果缓存：使用 functools.lru_cache，可通过 reload_custom_commands() 失效
    """
```

### 去重规则

```
加载顺序（低 → 高优先级）：
  project commands → user commands → project skills → user skills
  → plugin commands → plugin skills

去重规则：
  同一个 user_facing_name()，后加载的覆盖先加载的
  （即 user skills 可覆盖 project commands，plugin skills 可覆盖 user skills）
```

### 缓存与刷新

```python
_custom_commands_cache: list[CustomCommandWithScope] | None = None

async def load_custom_commands() -> list[CustomCommandWithScope]:
    global _custom_commands_cache
    if _custom_commands_cache is not None:
        return _custom_commands_cache
    # ... 扫描和加载逻辑
    _custom_commands_cache = result
    return result

def reload_custom_commands() -> None:
    """手动失效缓存，下次调用时重新扫描"""
    global _custom_commands_cache
    _custom_commands_cache = None
```

---

## YAML Frontmatter 规范

### 完整字段表

| 字段 | YAML 键名 | 类型 | 必需 | 说明 |
|------|----------|------|------|------|
| name | `name` | string | 是 | 命令/Skill 名称，必须与目录名一致 |
| description | `description` | string | 是 | 简短描述，不超过 1024 字符 |
| allowed_tools | `allowed-tools` | string[] | 否 | 限制 LLM 可使用的工具列表 |
| argument_hint | `argument-hint` | string | 否 | 参数提示，显示给用户 |
| when_to_use | `when_to_use` | string | 否 | 告诉 LLM 何时使用此 Skill |
| model | `model` | string | 否 | 指定使用的模型（见映射表） |
| max_thinking_tokens | `max-thinking-tokens` | number | 否 | 扩展思考的 token 上限 |
| disable_model_invocation | `disable-model-invocation` | boolean | 否 | 是否禁止 LLM 自动调用 |

### model 值映射

| Frontmatter 值 | 内部映射 | 说明 |
|----------------|---------|------|
| `haiku` | `quick` | 快速模型 |
| `sonnet` | `task` | 任务模型 |
| `opus` | `main` | 主力模型 |
| `quick` | `quick` | 直接引用 |
| `task` | `task` | 直接引用 |
| `main` | `main` | 直接引用 |
| 其他 | 原样传递 | 自定义模型名 |

### 示例 SKILL.md

```markdown
---
name: code-reviewer
description: 按照安全性和质量标准进行代码审查
when_to_use: 编写或修改代码后，需要代码审查时使用
allowed-tools:
  - Glob
  - Grep
  - FileReadTool
  - Bash
argument-hint: "<file-or-directory>"
model: sonnet
max-thinking-tokens: 10000
---

# 代码审查专家

请对以下代码变更进行审查。

## 审查清单

### 安全性
- 无硬编码密钥
- 所有用户输入已验证
- SQL 注入防护
- XSS 防护

### 代码质量
- 函数小于 50 行
- 文件小于 800 行
- 嵌套不超过 4 层

### 审查目标

$ARGUMENTS
```

### 示例 Command .md

```markdown
---
name: deploy
description: 部署到生产环境
argument-hint: "<environment>"
---

# 部署流程

执行以下步骤部署到 $ARGUMENTS 环境：

1. 运行测试确保所有测试通过
2. 检查 git 状态确保无未提交更改
3. 执行部署命令
```

---

## 字符预算机制

SkillTool 在生成可用 Skill 列表时使用字符预算限制，避免消耗过多上下文窗口：

```python
# 环境变量控制，默认 15000 字符
budget = int(os.environ.get("SLASH_COMMAND_TOOL_CHAR_BUDGET", "15000"))

# 在 prompt() 中截断
used = 0
for skill in skills:
    block = format_skill_block(skill)
    used += len(block) + 1
    if used > budget:
        break
    limited.append(block)
```

超出预算的 Skill 不会被列出（但仍然可以通过名称调用）。

---

## $ARGUMENTS 替换

用户通过 `args` 参数传入的文本会被注入到 Skill/Command 的 Prompt 中：

**替换规则**：

1. 如果 Prompt 模板中包含 `$ARGUMENTS` 占位符 → 直接替换
2. 如果没有占位符但用户提供了 args → 追加到末尾：`{prompt}\n\nARGUMENTS:\n{args}`
3. 如果用户未提供 args → 不追加

```python
def get_prompt_for_command(self, args: str | None = None) -> str:
    prompt = self.content
    trimmed = (args or "").strip()
    if trimmed:
        if "$ARGUMENTS" in prompt:
            prompt = prompt.replace("$ARGUMENTS", trimmed)
        else:
            prompt = f"{prompt}\n\nARGUMENTS:\n{trimmed}"
    return prompt
```

---

## contextModifier 机制

### 概念

`contextModifier` 是 SkillTool/SlashCommandTool 工具结果中携带的**上下文修改指令**。当 Skill 被调用后，它可以修改后续对话的上下文参数，包括：

1. **限制可用工具**（`allowed_tools`）— 只允许 Skill 指定的工具
2. **切换模型**（`model`）— 使用不同的 LLM 模型
3. **设置思考 token 上限**（`max_thinking_tokens`）— 控制推理深度

### 数据流

```
SkillTool.call()
    │
    ├─ 从 frontmatter 提取 allowed_tools, model, max_thinking_tokens
    ├─ 构建 ContextModifier 对象
    │
    └─ yield ToolOutput(
         type="result",
         data=...,
         result_for_assistant=...,
         new_messages=[...],            # Prompt 注入对话历史
         context_modifier=modifier,     # 上下文修改指令
       )
                │
                ▼
        ToolUseQueue 收集结果
                │
                ▼
        query_core() 应用 context_modifier
        ┌─ options.command_allowed_tools = modifier.allowed_tools
        ├─ options.model = modifier.model
        └─ options.max_thinking_tokens = modifier.max_thinking_tokens
                │
                ▼
        下一次 query_core() 递归使用修改后的 options
```

### 需要修改的现有文件

为支持 contextModifier，需要修改以下文件：

| 文件 | 修改内容 |
|------|---------|
| `core/tools/base.py` | `ToolOutput` 新增 `context_modifier` 字段 |
| `core/tools/executor.py` | `collect_tool_result()` 捕获并返回 `context_modifier` |
| `app/query.py` | `ToolUseQueue._run()` 应用 `context_modifier` 到 `options` |

---

## Plugin 架构

### Plugin 清单

Plugin 通过 `.pode-plugin/plugin.json` 清单文件定义：

```json
{
  "name": "devops-tools",
  "version": "1.0.0",
  "description": "DevOps 工具集：提交、审查、部署",
  "skills": ["./skills/commit", "./skills/review-pr"],
  "commands": ["./commands"],
  "agents": [],
  "hooks": [],
  "outputStyles": [],
  "mcpServers": {}
}
```

### Plugin 目录结构

```
my-plugin/
├── .pode-plugin/
│   └── plugin.json         # 插件清单
├── skills/
│   ├── commit/
│   │   └── SKILL.md
│   └── review-pr/
│       └── SKILL.md
├── commands/
│   └── deploy.md
├── agents/                  # Agent 配置（可选）
├── hooks/                   # Hook 配置（可选）
│   └── hooks.json
├── output-styles/           # 输出样式（可选）
└── .mcp.json                # MCP 服务器配置（可选）
```

### Plugin 加载流程

```python
# services/plugins/runtime.py

async def configure_session_plugins(
    config: GlobalConfig,
    plugin_dirs: list[str] | None = None,
) -> list[SessionPlugin]:
    """
    1. 解析插件目录路径（支持 glob 模式）
    2. 逐个加载插件（解析 plugin.json）
    3. 保存到 Session 状态
    4. 刷新命令缓存（reload_custom_commands()）
    """
```

### 安装模式

| 模式 | 说明 |
|------|------|
| `skill-pack` | 单独技能目录安装到 `~/.pode/skills/` |
| `plugin-pack` | 整个目录安装到 `~/.pode/plugins/installed/` |

---

## Marketplace 系统

### Marketplace 清单格式

```json
{
  "name": "team-marketplace",
  "description": "团队共享的技能市场",
  "plugins": [
    {
      "name": "devops-tools",
      "description": "DevOps 工具集",
      "source": "./",
      "skills": ["./skills/commit"],
      "commands": ["./commands/deploy.md"]
    }
  ]
}
```

### Marketplace 来源类型

| 类型 | 格式 | 示例 |
|------|------|------|
| GitHub | `github:owner/repo` | `github:my-org/pode-skills` |
| Git | `git:https://...` | `git:https://github.com/org/repo.git` |
| HTTP URL | `url:https://...` | `url:https://example.com/marketplace.json` |
| NPM | `npm:package-name` | `npm:pode-skills-collection` |
| 本地文件 | `file:/path/to/marketplace.json` | `file:./local-marketplace.json` |
| 本地目录 | `dir:/path/to/dir` | `dir:./my-skills` |

### 存储文件

| 文件 | 用途 |
|------|------|
| `~/.pode/plugins/known_marketplaces.json` | 已知 Marketplace 列表 |
| `~/.pode/installed-skill-plugins.json` | 已安装插件注册表 |

### CLI 命令

```bash
# Marketplace 管理
pode plugin marketplace add <source>       # 添加 Marketplace 来源
pode plugin marketplace remove <name>      # 移除 Marketplace
pode plugin marketplace list               # 列出所有 Marketplace
pode plugin marketplace update <name>      # 更新 Marketplace 缓存

# Plugin 管理
pode plugin install <plugin> [--scope user|project]   # 安装 Plugin
pode plugin uninstall <plugin-id>                     # 卸载 Plugin
pode plugin enable <plugin-id>                        # 启用 Plugin
pode plugin disable <plugin-id>                       # 禁用 Plugin
pode plugin list [--scope user|project]               # 列出已安装 Plugin

# Skill/Command 缓存刷新
pode plugin refresh                                    # 刷新缓存
```

### Marketplace 生命周期

```
添加 Marketplace → 缓存到 known_marketplaces.json
    ↓
浏览可用 Plugin → 从 Marketplace 读取 plugin 列表
    ↓
安装 Plugin → 复制文件到 ~/.pode/skills/ 或 ~/.pode/plugins/installed/
    ↓
启用 Plugin → 注册到 installed-skill-plugins.json + 刷新缓存
    ↓
使用 Skill → LLM 自动发现并调用
    ↓
禁用/卸载 → 移动到 .disabled/ 或删除
```

---

## Plugin 验证

### 验证函数

| 函数 | 文件 | 说明 |
|------|------|------|
| `validate_plugin_json()` | `services/plugins/validation.py` | 校验 `plugin.json` schema |
| `validate_marketplace_json()` | `services/plugins/validation.py` | 校验 `marketplace.json` schema |
| `validate_skill_dir()` | `services/plugins/validation.py` | 校验技能目录结构 |

### 验证规则

**Plugin 清单校验**：
- `name` 必须是非空字符串
- `version` 必须符合 semver 格式
- 路径字段（skills/commands/agents/hooks）必须是合法相对路径
- 不能包含绝对路径或路径遍历（`..`）

**技能目录校验**：
- 目录名必须是 kebab-case（`^[a-z0-9]+(?:-[a-z0-9]+)*$`）
- 目录名长度 1-64 字符
- 必须包含 `SKILL.md` 或 `skill.md` 文件
- Frontmatter 必须包含 `name` 和 `description`

---

## 存储路径映射

### Kode-Agent → Pode-Agent

| Kode-Agent (TypeScript) | Pode-Agent (Python) | 用途 |
|---|---|---|
| `~/.kode/commands/` | `~/.pode/commands/` | 用户自定义命令 |
| `~/.kode/skills/` | `~/.pode/skills/` | 用户自定义技能 |
| `~/.kode/plugins/` | `~/.pode/plugins/` | 已安装插件 |
| `.kode/commands/` | `.pode/commands/` | 项目级命令 |
| `.kode/skills/` | `.pode/skills/` | 项目级技能 |
| `.kode-plugin/` | `.pode-plugin/` | Plugin 清单目录 |
| `~/.kode/plugins/known_marketplaces.json` | `~/.pode/plugins/known_marketplaces.json` | Marketplace 注册表 |
| `~/.kode/installed-skill-plugins.json` | `~/.pode/installed-skill-plugins.json` | 已安装插件记录 |

### 文件格式兼容性

YAML frontmatter 字段名使用 kebab-case（与 Kode-Agent 一致），Pydantic 模型使用 `alias` 映射到 snake_case Python 属性名。

---

## 与 Agent Loop 的集成

### SkillTool/SlashCommandTool 在 Agent Loop 中的位置

```
query_core()
    │
    ├─ query_llm() → LLM 返回 tool_use blocks
    │
    └─ ToolUseQueue.run()
         │
         ├─ SkillTool.call()
         │    ├─ 返回 ToolOutput（含 new_messages + context_modifier）
         │    └─ new_messages 注入对话历史
         │
         ├─ SlashCommandTool.call()
         │    ├─ 返回 ToolOutput（含 new_messages + context_modifier）
         │    └─ new_messages 注入对话历史
         │
         └─ 其他工具（BashTool, FileEditTool 等）
              └─ 返回 ToolOutput（不含 context_modifier）
```

### contextModifier 应用流程

1. `ToolUseQueue._run()` 收集所有工具结果
2. 检查每个 `ToolResult.context_modifier`
3. 如果非 None，调用 `modifier.apply_to_options(options)`
4. 将修改后的 `options` 传递到下一次 `query_core()` 递归

### newMessages 注入

SkillTool/SlashCommandTool 的 `new_messages` 会被追加到 `messages` 列表中，作为新的对话历史传递给下一次 LLM 调用。

### 需要修改的核心文件

| 文件 | 修改 | 说明 |
|------|------|------|
| `pode_agent/core/tools/base.py` | ToolOutput 新增 `context_modifier` 字段 | 类型 `ContextModifier \| None = None` |
| `pode_agent/core/tools/executor.py` | `collect_tool_result()` 捕获 `context_modifier` | 传递到 `ToolResult` |
| `pode_agent/app/query.py` | `ToolUseQueue._run()` 应用 `context_modifier` | 更新 `options` |

---

## 与 Tool System 的集成

### 工具注册

SkillTool 和 SlashCommandTool 在 `pode_agent/tools/__init__.py` 中注册：

```python
# Phase 3 已注册（骨架），Phase 5 替换为完整实现
from pode_agent.tools.ai.skill import SkillTool
from pode_agent.tools.interaction.slash_command import SlashCommandTool
```

### 工具发现

- `SkillTool`：通过 `ToolLoader` 标准注册，`is_enabled()` 始终返回 True
- `SlashCommandTool`：同上

### 工具过滤

`get_enabled_tools()` 不需要为 SkillTool/SlashCommandTool 添加特殊过滤。它们与普通工具一样受 `safe_mode` 和 `permission_mode` 控制。

---

## 分阶段实现计划

### Phase 5 子任务

| 子任务 | 文件 | 说明 |
|--------|------|------|
| 5.S.1: 数据模型 | `pode_agent/types/skill.py` | ContextModifier, CustomCommandFrontmatter, CustomCommandWithScope, PluginManifest, MarketplaceManifest, InstalledPlugin |
| 5.S.2: 自定义命令服务 | `pode_agent/services/plugins/commands.py` | 发现、加载、frontmatter 解析、去重 |
| 5.S.3: Plugin 运行时 | `pode_agent/services/plugins/runtime.py` | 加载 plugin.json、Session 管理 |
| 5.S.4: Plugin 验证 | `pode_agent/services/plugins/validation.py` | schema 和路径校验 |
| 5.S.5: Marketplace | `pode_agent/services/plugins/marketplace.py` | CRUD、安装/卸载、来源解析 |
| 5.S.6: contextModifier 基础设施 | `core/tools/base.py` + `core/tools/executor.py` + `app/query.py` | ToolOutput 新字段 + collect_tool_result 传播 + apply 逻辑 |
| 5.S.7: SkillTool 完整实现 | `pode_agent/tools/ai/skill.py` | 替换 Phase 3 骨架 |
| 5.S.8: SlashCommandTool 完整实现 | `pode_agent/tools/interaction/slash_command.py` | 自定义命令支持 |
| 5.S.9: CLI 集成 | `pode_agent/entrypoints/cli.py` | `pode plugin` 子命令 |

### 实现顺序

```
5.S.1 (数据模型)
    ↓
5.S.2 (命令服务) ← 依赖 5.S.1
    ↓
5.S.3 (Plugin 运行时) ← 依赖 5.S.1
5.S.4 (Plugin 验证) ← 依赖 5.S.1
5.S.5 (Marketplace) ← 依赖 5.S.3, 5.S.4
    ↓
5.S.6 (contextModifier) ← 依赖 5.S.1，独立于 5.S.2-5.S.5
    ↓
5.S.7 (SkillTool) ← 依赖 5.S.2, 5.S.6
5.S.8 (SlashCommandTool) ← 依赖 5.S.2, 5.S.6
5.S.9 (CLI 集成) ← 依赖 5.S.5
```

---

## 映射表：Kode-Agent → Pode-Agent

| Kode-Agent (TypeScript) | Pode-Agent (Python) |
|---|---|
| `src/tools/ai/SkillTool/SkillTool.tsx` | `pode_agent/tools/ai/skill.py` |
| `src/tools/ai/SkillTool/prompt.ts` | `pode_agent/tools/ai/skill.py`（常量） |
| `src/tools/interaction/SlashCommandTool/SlashCommandTool.tsx` | `pode_agent/tools/interaction/slash_command.py` |
| `src/services/plugins/customCommands.ts` | `pode_agent/services/plugins/commands.py` |
| `src/services/plugins/pluginRuntime.ts` | `pode_agent/services/plugins/runtime.py` |
| `src/services/plugins/skillMarketplace.ts` | `pode_agent/services/plugins/marketplace.py` |
| `src/services/plugins/pluginValidation.ts` | `pode_agent/services/plugins/validation.py` |
| `src/utils/session/sessionPlugins.ts` | `pode_agent/services/plugins/session.py` |
| `src/commands/plugin.ts` | `pode_agent/entrypoints/cli.py`（`pode plugin` 子命令） |
| `src/commands/refreshCommands.ts` | `pode_agent/services/plugins/commands.py:reload_custom_commands()` |
| `src/commands/index.ts` → `getCommands()` | `pode_agent/services/plugins/commands.py:load_custom_commands()` |
| `loadCustomCommands()` | `load_custom_commands()` |
| `loadSkillDirectoryCommandsFromBaseDir()` | `_load_skill_dir_commands()` |
| `loadCommandMarkdownFilesFromBaseDir()` | `_load_command_files()` |
| `loadPluginSkillDirectoryCommandsFromBaseDir()` | `_load_plugin_skill_commands()` |
| `parseFrontmatter()` | `parse_frontmatter()` |
| `applySkillFilePreference()` | `_apply_skill_file_preference()` |
| `userFacingName()` | `CustomCommandWithScope.user_facing_name()` |
| `getPromptForCommand()` | `CustomCommandWithScope.get_prompt_for_command()` |
| `contextModifier` (TS 函数) | `ContextModifier.apply_to_options()` (Pydantic 方法) |
| `normalizeCommandModelName()` | `_normalize_model_name()` |
| `.kode-plugin/plugin.json` | `.pode-plugin/plugin.json` |
| `.kode/commands/`, `.kode/skills/` | `.pode/commands/`, `.pode/skills/` |
| `known_marketplaces.json` | `~/.pode/plugins/known_marketplaces.json` |
| `installed-skill-plugins.json` | `~/.pode/installed-skill-plugins.json` |
| `SLASH_COMMAND_TOOL_CHAR_BUDGET` 环境变量 | `SLASH_COMMAND_TOOL_CHAR_BUDGET` 环境变量（同） |
