# Pode-Agent SubAgent（子代理）系统

> 版本：1.0.0 | 状态：草稿 | 更新：2026-04-02
> 本文档是 **SubAgent 系统的权威设计文档**，涵盖概念模型、数据结构、TaskTool 完整实现、Agent 配置加载、上下文隔离（ForkContext）、前台/后台执行、工具权限隔离、Transcript 存储，以及分阶段实现计划。
> 核心循环调度细节（query_core 递归、ToolUseQueue、Hook 系统）请参阅 [agent-loop.md](./agent-loop.md)。
> 工具层权限硬拒绝机制请参阅 [tools-system.md](./tools-system.md#权限系统与工具的耦合点)。
> 计划模式与 SubAgent 的关系请参阅 [plan-mode.md](./plan-mode.md#与-subagent--tasktool-的关系)。

---

## 目录

1. [概念与动机](#概念与动机)
2. [核心架构](#核心架构)
3. [数据模型](#数据模型)
4. [TaskTool 输入/输出](#tasktool-输入输出)
5. [执行流程](#执行流程)
6. [Agent 配置加载器](#agent-配置加载器)
7. [上下文隔离机制（ForkContext）](#上下文隔离机制forkcontext)
8. [工具权限隔离](#工具权限隔离)
9. [模型选择优先级](#模型选择优先级)
10. [后台任务管理](#后台任务管理)
11. [Transcript 存储](#transcript-存储)
12. [与 Agent Loop 的集成](#与-agent-loop-的集成)
13. [SessionEvent 扩展](#sessionevent-扩展)
14. [分阶段实现计划](#分阶段实现计划)
15. [映射表：Kode-Agent → Pode-Agent](#映射表kode-agent--pode-agent)

---

## 概念与动机

### SubAgent 定义

SubAgent 是在主 Agent（Main Agent）内部启动的**独立代理实例**。每个 SubAgent 拥有：

- 独立的消息历史（上下文隔离）
- 独立的工具集（可限制可用工具）
- 独立的系统提示词（专门化角色）
- 独立的 Agent ID（可恢复/继续）

### 解决的问题

| 问题 | SubAgent 如何解决 |
|------|-----------------|
| 主 Agent 上下文窗口有限 | 子 Agent 在独立上下文中工作，不污染主上下文 |
| 不同任务需要不同专长 | 子 Agent 可以加载专门的系统提示词和工具 |
| 并发执行多个独立任务 | 子 Agent 可以在后台运行（`run_in_background`） |
| 主 Agent 需要专注于决策 | 子 Agent 负责执行细节，只返回最终结果 |
| 跨模型成本优化 | 子 Agent 可以使用不同模型（如 haiku 用于快速探索） |

### 设计原则

1. **绝对隔离**：子 Agent 的消息历史与父 Agent 完全独立，互不污染
2. **安全过滤**：子 Agent 默认使用 `dontAsk` 权限模式，不直接提示用户
3. **可恢复性**：每个子 Agent 有唯一 `agent_id`，支持 `resume` 恢复之前的执行
4. **可配置性**：Agent 配置支持多源发现和优先级合并（内置 → 插件 → 用户 → 项目）
5. **前台/后台双模式**：前台模式父 Agent 等待结果，后台模式立即返回

---

## 核心架构

### 父子 Agent 关系

```
Main Agent（父）
    │
    ├── TaskTool.call() 创建 SubAgent
    │       ├── agent_id: 唯一标识
    │       ├── tools: 过滤后的工具集
    │       ├── system_prompt: 专用提示词
    │       ├── model: 可指定不同模型
    │       └── messages: 独立消息历史
    │
    ├── 前台模式：父 Agent 等待子 Agent 完成
    │       └── 子 Agent 结果直接返回给父 Agent
    │
    └── 后台模式：子 Agent 异步运行
            ├── 父 Agent 立即获得 `async_launched` 确认
            └── 通过 TaskOutputTool 获取结果
```

### 组件映射表

| Kode-Agent (TypeScript) | Pode-Agent (Python) | 说明 |
|---|---|---|
| `src/tools/agent/TaskTool/TaskTool.tsx` | `pode_agent/tools/agent/task.py` | TaskTool 主实现 |
| `src/tools/agent/TaskTool/prompt.ts` | `pode_agent/tools/agent/task.py`（内部函数） | 工具描述和禁用工具列表 |
| `src/utils/agent/loader.ts` | `pode_agent/services/agents/loader.py`（新建） | Agent 配置加载器 |
| `src/utils/agent/transcripts.ts` | `pode_agent/services/agents/transcripts.py`（新建） | Transcript 内存存储 |
| `src/utils/session/backgroundTasks.ts` | `pode_agent/services/agents/background_tasks.py`（新建） | 后台任务管理 |
| `src/tools/system/TaskOutputTool/TaskOutputTool.tsx` | `pode_agent/tools/system/task_output.py` | 读取后台任务结果 |
| `src/commands/agents/storage.ts` | `pode_agent/services/agents/storage.py`（新建） | Agent 文件存储管理 |
| `src/commands/agents/generation.ts` | `pode_agent/services/agents/generation.py`（新建） | Agent 动态生成（Phase 6） |

---

## 数据模型

### AgentConfig

```python
# pode_agent/types/agent.py（或 pode_agent/services/agents/models.py）

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


class AgentSource(str, Enum):
    """Agent 配置来源"""
    BUILTIN = "builtin"          # 内置 Agent
    PLUGIN = "plugin"            # 插件提供
    USER = "user"                # 用户自定义（~/.pode/agents/）
    PROJECT = "project"          # 项目级（.pode/agents/）
    FLAG = "flag"                # CLI 参数指定
    POLICY = "policy"            # 策略/管理指定


class AgentLocation(str, Enum):
    """Agent 位置分类"""
    LOCAL = "local"              # 本地定义
    REMOTE = "remote"            # 远程（GitHub URL）


class AgentModel(str, Enum):
    """Agent 使用的模型"""
    INHERIT = "inherit"          # 继承父 Agent 的模型
    HAIKU = "haiku"              # 快速轻量模型
    SONNET = "sonnet"            # 标准编码模型
    OPUS = "opus"                # 最强推理模型


class AgentPermissionMode(str, Enum):
    """Agent 权限模式"""
    DEFAULT = "default"                # 默认（需要用户确认）
    DONT_ASK = "dontAsk"               # 自动批准（子 Agent 默认）
    BYPASS_PERMISSIONS = "bypassPermissions"  # 绕过所有权限检查


class AgentConfig(BaseModel):
    """Agent 配置对象（完整结构）"""

    agent_type: str = Field(description="Agent 类型名，如 'general-purpose', 'Explore'")
    when_to_use: str = Field(description="何时使用此 Agent 的描述")
    tools: list[str] | Literal["*"] = Field(
        default="*",
        description="可用工具列表，'*' 表示全部",
    )
    disallowed_tools: list[str] = Field(
        default_factory=list,
        description="禁用工具列表（即使 tools='*' 也排除）",
    )
    skills: list[str] = Field(default_factory=list, description="关联的技能")
    system_prompt: str = Field(default="", description="Agent 角色的系统提示词")
    source: AgentSource = AgentSource.BUILTIN
    location: AgentLocation = AgentLocation.LOCAL
    base_dir: str | None = None
    filename: str | None = None
    color: str | None = None
    model: AgentModel = AgentModel.INHERIT
    permission_mode: AgentPermissionMode = AgentPermissionMode.DONT_ASK
    fork_context: bool = Field(
        default=False,
        description="是否继承父 Agent 的上下文",
    )
```

### BackgroundAgentTask

```python
# pode_agent/services/agents/background_tasks.py

from pydantic import BaseModel, Field


class BackgroundAgentStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    KILLED = "killed"


class BackgroundAgentTask(BaseModel):
    """后台 Agent 任务记录"""

    type: Literal["async_agent"] = "async_agent"
    agent_id: str
    description: str
    prompt: str
    status: BackgroundAgentStatus = BackgroundAgentStatus.RUNNING
    started_at: float = Field(default_factory=time.time)
    completed_at: float | None = None
    error: str | None = None
    result_text: str | None = None
    messages: list[dict[str, Any]] = Field(default_factory=list)
    retrieved: bool = False
```

### SubAgentResult

```python
# pode_agent/services/agents/models.py

class SubAgentResult(BaseModel):
    """SubAgent 执行完成后的返回结果"""

    status: Literal["completed", "async_launched"]
    agent_id: str
    description: str
    prompt: str
    content: list[dict[str, Any]] | None = None        # 前台模式：最终回答
    total_tool_use_count: int = 0
    total_duration_ms: int = 0
    total_tokens: int = 0
```

---

## TaskTool 输入/输出

### TaskInput（完整版，Phase 5 重写）

当前 Phase 3 骨架仅支持 `create/list/cancel` 动作。Phase 5 将重写为以下 Schema：

```python
# pode_agent/tools/agent/task.py（Phase 5 重写）

class TaskInput(BaseModel):
    """SubAgent 输入 Schema"""

    description: str = Field(
        description="A short (3-5 word) description of the task",
    )
    prompt: str = Field(
        description="The task for the agent to perform",
    )
    subagent_type: str = Field(
        description="The type of specialized agent to use for this task",
    )
    model: Literal["sonnet", "opus", "haiku"] | None = Field(
        default=None,
        description="Optional model to use for this agent",
    )
    resume: str | None = Field(
        default=None,
        description="Optional agent ID to resume from",
    )
    run_in_background: bool = Field(
        default=False,
        description="Set to true to run this agent in the background",
    )
```

### 输出格式

**前台模式完成时**：

```python
ToolOutput(
    type="result",
    data={
        "status": "completed",
        "agent_id": "agent_abc123",
        "description": "Search codebase for auth",
        "prompt": "Find all authentication-related files...",
        "content": [{"type": "text", "text": "Found 5 auth files..."}],
        "total_tool_use_count": 7,
        "total_duration_ms": 3200,
    },
    result_for_assistant=(
        "[Agent agent_abc123 completed] Found 5 auth files... "
        "(7 tool uses, 3.2s)"
    ),
)
```

**后台模式启动时**：

```python
ToolOutput(
    type="result",
    data={
        "status": "async_launched",
        "agent_id": "agent_xyz789",
        "description": "Run test suite",
        "prompt": "Execute pytest and report results...",
    },
    result_for_assistant=(
        "[Agent agent_xyz789 launched in background] "
        "Use TaskOutput to check results."
    ),
)
```

---

## 执行流程

### 前台模式（同步）

```
TaskTool.call(input, context)
    │
    ├── 1. 加载 Agent 配置（get_agent_by_type）
    │       └── 找不到 → 返回错误
    │
    ├── 2. 确定模型（model selection chain）
    │
    ├── 3. 过滤工具集（三层过滤）
    │
    ├── 4. 生成/恢复 agent_id
    │
    ├── 5. 构建上下文消息
    │       ├── fork_context_messages（如果启用）
    │       ├── transcript（如果是 resume）
    │       └── prompt_messages（新任务）
    │
    ├── 6. 构建系统提示词（base + agent_config.system_prompt）
    │
    ├── 7. yield progress（初始进度）
    │
    ├── 8. 运行 query_core() 递归循环（复用 Agentic Loop）
    │       ├── 实时 yield progress（节流 200ms）
    │       └── 追踪 tool_use_count
    │
    ├── 9. 提取最终助手消息作为结果
    │
    ├── 10. 保存 Transcript（save_agent_transcript）
    │
    └── 11. yield result（含 agent_id, content, stats）
```

### 后台模式（异步）

```
TaskTool.call(input, context)  [run_in_background=True]
    │
    ├── 1-6. 同前台模式
    │
    ├── 7. 创建 BackgroundAgentTask 记录
    │       └── 注册到 background_tasks Map
    │
    ├── 8. asyncio.create_task() 启动独立协程
    │       └── 运行 query_core()（独立 abort_event）
    │           ├── 每条消息更新 task.messages
    │           ├── 完成时设置 task.result_text
    │           └── 异常时设置 task.error
    │
    ├── 9. 立即返回 async_launched
    │
    └── 父 Agent 继续工作
            └── 通过 TaskOutputTool 获取结果
```

### 时序图

```
Main Agent        TaskTool         AgentConfig Loader    SubAgent (query_core)
    │                 │                    │                      │
    │─(tool_use)─────▶│                    │                      │
    │                 │──get_agent_by_type─▶│                      │
    │                 │◀──AgentConfig──────│                      │
    │                 │                    │                      │
    │                 │──filter_tools()    │                      │
    │                 │──build_messages()  │                      │
    │                 │──build_sys_prompt()│                      │
    │                 │                    │                      │
    │                 │──────────────── query_core() ────────────▶│
    │                 │                    │                      │
    │◀─(progress)──── │◀───── progress ───────────────────────── │
    │◀─(progress)──── │◀───── progress ───────────────────────── │
    │                 │                    │                      │
    │                 │◀───── result ─────────────────────────── │
    │                 │──save_transcript() │                      │
    │                 │                    │                      │
    │◀─(result)────── │                    │                      │
    │                 │                    │                      │
```

---

## Agent 配置加载器

### 多源发现

```python
# pode_agent/services/agents/loader.py

async def load_agents() -> list[AgentConfig]:
    """从所有来源加载 Agent 配置，按优先级合并。"""
    agents: list[AgentConfig] = []

    # 来源 1: 内置 Agent（硬编码）
    agents.extend(BUILTIN_AGENTS)

    # 来源 2: 插件提供（Phase 5 通过 entry_points）
    # agents.extend(load_plugin_agents())

    # 来源 3: 用户自定义（~/.pode/agents/*.md）
    agents.extend(load_agents_from_dir(Path.home() / ".pode" / "agents"))

    # 来源 4: 项目级（.pode/agents/*.md）
    agents.extend(load_agents_from_dir(Path.cwd() / ".pode" / "agents"))

    # 来源 5: CLI flag（Phase 5）
    # agents.extend(load_flag_agents())

    # 来源 6: 策略（Phase 5）
    # agents.extend(load_policy_agents())

    return merge_agents(agents)
```

### 优先级合并

```
policy > flag > project > user > plugin > built-in

同 agent_type 时，高优先级覆盖低优先级。
```

### 配置文件格式

用户可在 `~/.pode/agents/` 或 `.pode/agents/` 下创建 `.md` 文件定义自定义 Agent：

```markdown
---
name: my-custom-agent
description: 自定义代码审查代理
tools: FileReadTool, GrepTool, GlobTool
disallowedTools: FileEditTool, FileWriteTool, BashTool
model: haiku
color: blue
permissionMode: default
forkContext: true
---

你是一个代码审查专家。你的任务是审查代码变更并提供反馈。
只关注以下方面：
- 代码质量
- 安全漏洞
- 性能问题
```

### 内置 Agent

| Agent 类型 | 用途 | 模型 | 工具限制 | forkContext |
|-----------|------|------|---------|------------|
| `general-purpose` | 通用任务 | inherit | 全部 | False |
| `Explore` | 代码搜索/探索 | haiku | 只读 + Glob | False |
| `Plan` | 架构规划 | inherit | 只读 + Glob | False |
| `statusline-setup` | 状态栏配置 | inherit | FileReadTool, FileEditTool, BashTool | False |

内置 Agent 的配置定义：

```python
BUILTIN_AGENTS: list[AgentConfig] = [
    AgentConfig(
        agent_type="general-purpose",
        when_to_use="处理复杂多步任务",
        tools="*",
        system_prompt="你是一个通用代理，可以使用所有工具完成任务。",
        model=AgentModel.INHERIT,
        permission_mode=AgentPermissionMode.DONT_ASK,
        fork_context=False,
    ),
    AgentConfig(
        agent_type="Explore",
        when_to_use="快速探索代码库，搜索文件和代码",
        tools="*",
        disallowed_tools=["Task", "FileEditTool", "FileWriteTool"],
        system_prompt=(
            "你是一个代码搜索专家。使用 Glob、Grep 和 FileRead "
            "快速找到文件和代码。只做研究，不做修改。"
        ),
        model=AgentModel.HAIKU,
        permission_mode=AgentPermissionMode.DONT_ASK,
        fork_context=False,
    ),
    AgentConfig(
        agent_type="Plan",
        when_to_use="架构规划和设计分析",
        tools="*",
        disallowed_tools=["Task", "FileEditTool", "FileWriteTool"],
        system_prompt="你是一个架构规划专家。分析代码结构并制定实施计划。",
        model=AgentModel.INHERIT,
        permission_mode=AgentPermissionMode.DONT_ASK,
        fork_context=False,
    ),
]
```

---

## 上下文隔离机制（ForkContext）

### 原理

当 Agent 配置中 `fork_context = True` 时，SubAgent 会继承父 Agent 在 TaskTool 调用之前的消息历史。

### 构建过程

```python
# pode_agent/services/agents/fork_context.py

FORK_CONTEXT_TOOL_RESULT_TEXT = (
    "### FORKING CONVERSATION CONTEXT ###\n"
    "The messages above are from a parent conversation context. "
    "They are provided for background only. "
    "Focus on completing the task described below."
)


def build_fork_context(
    *,
    enabled: bool,
    prompt: str,
    tool_use_id: str | None,
    message_log_name: str | None,
    fork_number: int,
) -> tuple[list[dict], list[dict]]:
    """构建 ForkContext 消息。

    Returns:
        (fork_context_messages, prompt_messages) 元组
    """
    user_prompt_message = {"role": "user", "content": prompt}

    if not enabled or not tool_use_id or not message_log_name:
        # 未启用 → 只传递 prompt
        return [], [user_prompt_message]

    # 启用 → 从磁盘 JSONL 读取主线程历史
    from pode_agent.utils.protocol.session_log import load_messages_from_log

    main_log_path = get_session_log_path(
        log_name=message_log_name,
        fork_number=fork_number,
    )
    main_messages = load_messages_from_log(main_log_path)

    # 只复制到 TaskTool 调用之前的消息
    fork_context_messages = _slice_before_tool_use(main_messages, tool_use_id)

    # 注入 "进入子代理" 提示消息
    prompt_messages = [
        _build_tool_use_assistant_message(tool_use_id),
        _build_fork_context_user_message(tool_use_id),
        user_prompt_message,
    ]

    return fork_context_messages, prompt_messages
```

### 子 Agent 的消息数组结构

```
messages_for_query = [
    # ── fork_context_messages（父 Agent 历史）──
    {role: "user", content: "帮我重构 auth 模块"},
    {role: "assistant", content: [...]},
    {role: "user", content: [tool_result: ...]},
    ...

    # ── prompt_messages ──
    {role: "assistant", content: [tool_use: Task(...)]},     # TaskTool 调用
    {role: "user", content: "### FORKING CONTEXT ###"},       # 进入子代理提示
    {role: "user", content: "具体的任务指令"},                   # 实际任务
]
```

### 关键点

1. 从**磁盘 JSONL** 读取父消息（不是内存引用），确保只读隔离
2. 只复制到 TaskTool 调用之前的历史，不包含当前工具调用
3. 注入特殊提示，告诉子 Agent "上面的消息只是上下文"
4. 子 Agent 的后续消息不会影响父 Agent 的消息数组

---

## 工具权限隔离

### 三层过滤

```
第一层：Agent 配置白名单（tools）
  tools: ["FileReadTool", "GrepTool", "GlobTool"]  → 只能用这三个工具
  tools: "*"                                         → 可以用所有工具（受黑名单限制）

第二层：Agent 配置黑名单（disallowed_tools）
  disallowed_tools: ["Task", "FileEditTool"]  → 即使 tools="*" 也排除

第三层：权限模式（permission_mode）
  DONT_ASK（默认）     → 自动批准，不提示用户
  DEFAULT              → 每次需要用户确认
  BYPASS_PERMISSIONS   → 绕过所有权限检查
```

### 禁用工具常量

以下工具**始终**在子 Agent 中禁用（`SUBAGENT_DISALLOWED_TOOL_NAMES`）：

```python
# pode_agent/tools/agent/task.py

SUBAGENT_DISALLOWED_TOOL_NAMES: frozenset[str] = frozenset([
    "Task",               # 防止嵌套子 Agent
    "TaskOutput",         # 子 Agent 不需要读取后台任务
    "KillShell",          # 子 Agent 不应终止进程
    "EnterPlanMode",      # 子 Agent 不进入计划模式
    "ExitPlanMode",       # 子 Agent 不退出计划模式
    "AskUserQuestion",    # 子 Agent 不直接询问用户
])
```

### get_task_tools() 实现

```python
async def get_task_tools(
    safe_mode: bool = False,
    agent_config: AgentConfig | None = None,
) -> list[Tool]:
    """获取子 Agent 可用的工具集。"""
    from pode_agent.tools import get_all_tools

    # 获取基础工具集
    all_tools = get_all_tools()
    if safe_mode:
        all_tools = [t for t in all_tools if t.is_read_only()]

    # 第一层：移除始终禁用的工具
    tools = [t for t in all_tools if t.name not in SUBAGENT_DISALLOWED_TOOL_NAMES]

    if agent_config is None:
        return tools

    # 第二层：白名单过滤
    tool_filter = agent_config.tools
    if tool_filter != "*":
        allowed = frozenset(tool_filter)
        tools = [t for t in tools if t.name in allowed]

    # 第三层：黑名单过滤
    if agent_config.disallowed_tools:
        disallowed = frozenset(agent_config.disallowed_tools)
        tools = [t for t in tools if t.name not in disallowed]

    return tools
```

---

## 模型选择优先级

```python
def resolve_subagent_model(
    *,
    input_model: str | None,           # TaskInput.model
    agent_config: AgentConfig,
    parent_model: str,
    default_subagent_model: str = "claude-sonnet-4-5-20251101",
) -> str:
    """确定子 Agent 使用的模型。

    优先级（从高到低）：
    1. PODE_SUBAGENT_MODEL 环境变量
    2. input_model 参数（TaskInput.model）
    3. agent_config.model（非 inherit 时）
    4. 继承父 Agent 模型
    5. 默认值
    """
    import os

    # 1. 环境变量
    env_model = os.environ.get("PODE_SUBAGENT_MODEL", "").strip()
    if env_model:
        return env_model

    # 2. 输入参数
    if input_model:
        return _model_enum_to_pointer(input_model)

    # 3. Agent 配置
    config_model = agent_config.model
    if config_model != AgentModel.INHERIT:
        return _model_enum_to_pointer(config_model.value)

    # 4. 继承父 Agent
    if parent_model:
        return parent_model

    # 5. 默认
    return default_subagent_model
```

---

## 后台任务管理

### BackgroundAgentTask 生命周期

```
创建 task（status=running）
    │
    ├── asyncio.create_task() 启动
    │       │
    │       ├── 正常完成 → status=completed, result_text=...
    │       ├── 异常 → status=failed, error=...
    │       └── 被终止 → status=killed
    │
    └── TaskOutputTool 读取结果
            ├── block=True → waitForBackgroundAgentTask()
            └── block=False → getBackgroundAgentTaskSnapshot()
```

### 内存存储

```python
# pode_agent/services/agents/background_tasks.py

_background_tasks: dict[str, BackgroundAgentTaskRuntime] = {}


class BackgroundAgentTaskRuntime:
    """运行时后台任务（含 asyncio 控制对象）"""
    task: BackgroundAgentTask
    abort_event: asyncio.Event
    done_event: asyncio.Event


def upsert_background_agent_task(task: BackgroundAgentTaskRuntime) -> None:
    """注册/更新后台任务"""
    _background_tasks[task.task.agent_id] = task


def get_background_agent_task(agent_id: str) -> BackgroundAgentTaskRuntime | None:
    """获取后台任务"""
    return _background_tasks.get(agent_id)


def get_background_agent_task_snapshot(agent_id: str) -> BackgroundAgentTask | None:
    """获取后台任务快照（不含 asyncio 对象）"""
    runtime = _background_tasks.get(agent_id)
    if runtime is None:
        return None
    return runtime.task


async def wait_for_background_agent_task(
    agent_id: str,
    wait_up_to_ms: int = 30000,
    abort_event: asyncio.Event | None = None,
) -> BackgroundAgentTaskRuntime | None:
    """等待后台任务完成（带超时）"""
    runtime = _background_tasks.get(agent_id)
    if runtime is None:
        return None
    if runtime.task.status != BackgroundAgentStatus.RUNNING:
        return runtime

    try:
        await asyncio.wait_for(
            runtime.done_event.wait(),
            timeout=wait_up_to_ms / 1000,
        )
    except asyncio.TimeoutError:
        pass

    return _background_tasks.get(agent_id)


def mark_background_agent_task_retrieved(agent_id: str) -> None:
    """标记后台任务结果已被读取"""
    runtime = _background_tasks.get(agent_id)
    if runtime is not None:
        runtime.task.retrieved = True
```

### TaskOutputTool 集成

Phase 5 将重写现有的 `TaskOutputTool`（Phase 3 骨架），使其读取 `BackgroundAgentTask`：

```python
# pode_agent/tools/system/task_output.py（Phase 5 重写）

class TaskOutputInput(BaseModel):
    task_id: str = Field(description="ID of the background agent task")
    block: bool = Field(
        default=False,
        description="If true, wait for the task to complete before returning",
    )
    wait_ms: int = Field(
        default=30000,
        description="Maximum time to wait in milliseconds when block=true",
    )
```

---

## Transcript 存储

### 内存 Map

```python
# pode_agent/services/agents/transcripts.py

from collections.abc import MutableMapping

# 进程级别内存存储
_transcripts: dict[str, list[dict[str, Any]]] = {}


def save_agent_transcript(agent_id: str, messages: list[dict[str, Any]]) -> None:
    """保存子 Agent 的完整对话历史"""
    _transcripts[agent_id] = list(messages)  # 深拷贝


def get_agent_transcript(agent_id: str) -> list[dict[str, Any]] | None:
    """获取历史记录（用于 resume）"""
    return _transcripts.get(agent_id)
```

### 注意事项

- Transcript 存储在**内存**中（dict），进程退出后丢失
- 每次 SubAgent 执行完成后自动保存（前台和后台模式均如此）
- `resume` 参数使用 `get_agent_transcript()` 恢复历史消息
- 可选增强（Phase 6）：持久化到 JSONL 文件，跨进程恢复

---

## 与 Agent Loop 的集成

### 复用 query_core()

SubAgent 直接复用 `pode_agent/app/query.py` 中的 `query()` / `query_core()` 递归主循环：

```python
# TaskTool.call() 内部调用
async for event in query(
    prompt=effective_prompt,
    messages=messages_for_query,
    tools=filtered_tools,
    session=sub_session,       # 独立的子 SessionManager
    options=QueryOptions(
        model=model_to_use,
        permission_mode=resolved_permission_mode,
        safe_mode=safe_mode,
        max_tokens=max_tokens,
    ),
):
    # 前台模式：实时 yield progress
    yield _transform_event(event, agent_id)
```

### 子 SessionManager 实例化

```python
sub_session = SessionManager(
    tools=filtered_tools,
    initial_messages=messages_for_query,
    model=model_to_use,
    system_prompt=agent_system_prompt,
    permission_context=PermissionContext(
        mode=resolved_permission_mode,
    ),
)
```

### agent_id 传播

`ToolUseContext` 已有 `agent_id` 字段（Phase 0 定义）。子 Agent 的所有工具调用都会携带 `agent_id`：

```python
# pode_agent/core/tools/base.py — 已有定义
class ToolUseContext(BaseModel):
    ...
    agent_id: str | None = None  # 子 Agent 的唯一 ID
    ...
```

TaskTool 在创建子 Agent 时设置 `context.agent_id = agent_id`，后续所有工具调用自动携带。

---

## SessionEvent 扩展

### 新增事件类型

```python
# pode_agent/types/session_events.py — 扩展

class SessionEventType(str, Enum):
    # ... 现有事件 ...

    # SubAgent 事件
    SUB_AGENT_STARTED = "sub_agent_started"       # 子 Agent 启动
    SUB_AGENT_PROGRESS = "sub_agent_progress"     # 子 Agent 进度更新
    SUB_AGENT_COMPLETED = "sub_agent_completed"   # 子 Agent 完成
    SUB_AGENT_FAILED = "sub_agent_failed"         # 子 Agent 失败
```

### 事件结构

```python
@dataclass
class SubAgentEventData:
    agent_id: str
    subagent_type: str
    description: str
    model: str
    tool_use_count: int = 0
    duration_ms: int = 0
```

UI 层监听这些事件，在 REPL 界面中展示子 Agent 的执行状态。

---

## 分阶段实现计划

| 子功能 | 实现阶段 | 文件 | 说明 |
|--------|---------|------|------|
| `AgentConfig` 数据模型 | Phase 5 | `pode_agent/types/agent.py`（新建） | Pydantic v2 模型 |
| Agent 配置加载器 | Phase 5 | `pode_agent/services/agents/loader.py`（新建） | 多源发现 + 优先级合并 |
| Agent 文件存储 | Phase 5 | `pode_agent/services/agents/storage.py`（新建） | Markdown + YAML frontmatter 解析 |
| Transcript 内存存储 | Phase 5 | `pode_agent/services/agents/transcripts.py`（新建） | dict 存储 |
| 后台任务管理 | Phase 5 | `pode_agent/services/agents/background_tasks.py`（新建） | 注册/更新/等待/快照 |
| ForkContext 构建 | Phase 5 | `pode_agent/services/agents/fork_context.py`（新建） | 从 JSONL 读取父消息 |
| TaskTool 完整实现 | Phase 5 | `pode_agent/tools/agent/task.py`（重写） | 前台 + 后台 + resume |
| TaskOutputTool 更新 | Phase 5 | `pode_agent/tools/system/task_output.py`（重写） | 读取 BackgroundAgentTask |
| 子 Session 工厂 | Phase 5 | `pode_agent/app/sub_session.py`（新建） | 创建隔离的 SessionManager |
| SubAgent SessionEvent | Phase 5 | `pode_agent/types/session_events.py`（扩展） | 4 个新事件类型 |
| Agent 动态生成 | Phase 6 | `pode_agent/services/agents/generation.py`（新建） | LLM 生成 Agent 配置 |
| 文件监视器 | Phase 6 | `pode_agent/services/agents/watcher.py`（新建） | 监视 agents/ 目录变化 |
| Transcript 持久化 | Phase 6 | `pode_agent/services/agents/transcripts.py`（增强） | JSONL 文件存储 |

### Phase 5 实现顺序

```
1. types/agent.py                     — 数据模型（无依赖）
2. services/agents/transcripts.py     — Transcript 存储（无依赖）
3. services/agents/background_tasks.py — 后台任务管理（无依赖）
4. services/agents/storage.py         — 文件存储（依赖 types/agent.py）
5. services/agents/loader.py          — 配置加载器（依赖 storage.py）
6. services/agents/fork_context.py    — ForkContext（依赖 session_log.py）
7. app/sub_session.py                 — 子 Session 工厂（依赖 session.py）
8. tools/agent/task.py                — TaskTool 重写（依赖以上全部）
9. tools/system/task_output.py        — TaskOutputTool 重写（依赖 background_tasks.py）
10. types/session_events.py           — 事件扩展（依赖 types/agent.py）
```

---

## 映射表：Kode-Agent → Pode-Agent

| Kode-Agent（TypeScript） | Pode-Agent（Python） |
|---|---|
| `src/tools/agent/TaskTool/TaskTool.tsx` (839 行) | `pode_agent/tools/agent/task.py`（重写） |
| `src/tools/agent/TaskTool/prompt.ts` (97 行) | `pode_agent/tools/agent/task.py` 内 `get_task_tools()` + `get_prompt()` |
| `src/tools/agent/TaskTool/constants.ts` | `pode_agent/tools/agent/task.py` 内 `SUBAGENT_DISALLOWED_TOOL_NAMES` |
| `src/utils/agent/loader.ts` (892 行) | `pode_agent/services/agents/loader.py` |
| `src/utils/agent/storage.ts` | `pode_agent/services/agents/storage.py` |
| `src/utils/agent/transcripts.ts` (17 行) | `pode_agent/services/agents/transcripts.py` |
| `src/utils/session/backgroundTasks.ts` (85 行) | `pode_agent/services/agents/background_tasks.py` |
| `src/tools/system/TaskOutputTool/TaskOutputTool.tsx` (387 行) | `pode_agent/tools/system/task_output.py`（重写） |
| `src/commands/agents/storage.ts` | `pode_agent/services/agents/storage.py` |
| `src/commands/agents/generation.ts` | `pode_agent/services/agents/generation.py`（Phase 6） |
| `inputSchema = z.object({...})` | `class TaskInput(BaseModel)` |
| `interface AgentConfig` | `class AgentConfig(BaseModel)` |
| `BackgroundAgentTask` type | `class BackgroundAgentTask(BaseModel)` |
| `const transcripts = new Map()` | `_transcripts: dict[str, list[dict]]` |
| `const backgroundTasks = new Map()` | `_background_tasks: dict[str, BackgroundAgentTaskRuntime]` |
| `SUBAGENT_DISALLOWED_TOOL_NAMES = new Set()` | `SUBAGENT_DISALLOWED_TOOL_NAMES: frozenset[str]` |
| `buildForkContextForAgent()` | `build_fork_context()` |
| `getTaskTools()` | `get_task_tools()` |
| `getPrompt()` | `get_task_prompt()` |
| `generateAgentId()` | `uuid.uuid4()` 或 `f"agent_{uuid.uuid4().hex[:8]}"` |
| `upsertBackgroundAgentTask()` | `upsert_background_agent_task()` |
| `waitForBackgroundAgentTask()` | `wait_for_background_agent_task()` |
| `saveAgentTranscript()` / `getAgentTranscript()` | `save_agent_transcript()` / `get_agent_transcript()` |
| `process.env.KODE_SUBAGENT_MODEL` | `os.environ.get("PODE_SUBAGENT_MODEL")` |
| `AbortController` | `asyncio.Event` |
| `for await (const msg of queryFn(...))` | `async for event in query(...)` |
| `agentConfig.permissionMode = 'dontAsk'` | `AgentPermissionMode.DONT_ASK` |
| `agentConfig.forkContext = true` | `AgentConfig.fork_context = True` |
