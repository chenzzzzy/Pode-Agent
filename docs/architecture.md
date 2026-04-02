# Pode-Agent 系统架构设计

> 版本：1.0.0 | 状态：草稿 | 更新：2026-03-31

---

## 目录

1. [架构概览](#架构概览)
2. [层次模型](#层次模型)
3. [模块依赖图](#模块依赖图)
4. [核心组件详述](#核心组件详述)
5. [关键设计决策](#关键设计决策)
6. [异步模型](#异步模型)
7. [错误处理策略](#错误处理策略)
8. [扩展点](#扩展点)

---

## 架构概览

Pode-Agent 采用**分层架构**，遵循严格的依赖方向（低层不依赖高层）：

```
┌─────────────────────────────────────────────────────────────┐
│                    Entrypoints Layer                         │
│        CLI (typer) │ MCP Server │ ACP Server                │
├─────────────────────────────────────────────────────────────┤
│                    Application Layer                         │
│   REPL Engine │ Session Manager │ Orchestration             │
├─────────────────────────────────────────────────────────────┤
│                    Service Layer                             │
│  AI Service │ MCP Client │ Context │ Auth │ Plugins         │
├─────────────────────────────────────────────────────────────┤
│                    Core Layer                                │
│  Tool System │ Permissions │ Config │ Cost Tracker           │
├─────────────────────────────────────────────────────────────┤
│                  Infrastructure Layer                        │
│  Logging │ HTTP Client │ File System │ Shell Executor        │
└─────────────────────────────────────────────────────────────┘
```

**核心原则**：
1. **Core Layer 不依赖 UI**（可在无终端环境中运行）
2. **Service Layer 通过接口依赖 Core**（可替换实现）
3. **Application Layer 协调各 Service**（业务逻辑）
4. **Entrypoint Layer 仅负责启动和路由**（薄层）

---

## 层次模型

### Layer 1：Infrastructure（基础设施层）

最底层，提供无业务逻辑的技术能力：

```
pode_agent/
└── infra/
    ├── logging.py          # 结构化日志（structlog）
    ├── http_client.py      # 异步 HTTP 客户端（httpx）
    ├── shell.py            # Shell 命令执行（asyncio.subprocess）
    ├── fs.py               # 文件系统操作工具函数
    └── terminal.py         # 终端能力检测（颜色、尺寸等）
```

**约束**：
- 不导入任何 Service/Core 模块
- 不包含业务逻辑
- 100% 可单元测试（可 mock）

---

### Layer 2：Core（核心层）

业务核心，不依赖 UI：

```
pode_agent/
└── core/
    ├── config/             # 配置系统（全局 + 项目）
    │   ├── schema.py       # Pydantic 数据模型
    │   ├── loader.py       # 读取/写入 config.json
    │   ├── defaults.py     # 默认值
    │   └── migrations.py   # 配置版本迁移
    ├── permissions/        # 权限引擎
    │   ├── engine.py       # 权限检查逻辑
    │   ├── rules/          # 各工具权限规则
    │   │   ├── bash.py     # Bash 安全规则
    │   │   ├── file.py     # 文件操作规则
    │   │   └── plan_mode.py
    │   └── store.py        # 权限持久化
    ├── tools/              # 工具系统抽象
    │   ├── base.py         # Tool ABC + ToolOutput 类型
    │   ├── registry.py     # 工具注册表
    │   └── executor.py     # 工具执行器（collect result）
    └── cost_tracker.py     # LLM 成本追踪
```

**约束**：
- 不导入 `pode_agent.ui` 或 `pode_agent.entrypoints`
- 所有数据结构使用 Pydantic models

---

### Layer 3：Services（服务层）

领域服务，协调 Core 和外部系统：

```
pode_agent/
└── services/
    ├── ai/                 # LLM 集成
    │   ├── base.py         # Provider ABC
    │   ├── anthropic.py    # Anthropic Claude 适配器
    │   ├── openai.py       # OpenAI 适配器
    │   ├── factory.py      # Provider 工厂
    │   └── response_state.py
    ├── mcp/                # Model Context Protocol
    │   ├── client.py       # MCP 客户端
    │   ├── discovery.py    # MCP 服务发现
    │   └── tools.py        # MCP 工具包装
    ├── context/            # 项目上下文
    │   ├── project.py      # 项目上下文生成
    │   └── mentions.py     # @mention 处理
    ├── auth/               # 认证
    │   └── oauth.py        # OAuth 流程
    ├── plugins/            # 插件系统
    │   ├── commands.py     # 自定义命令
    │   ├── marketplace.py  # Skill Marketplace
    │   ├── runtime.py      # 插件运行时
    │   └── validation.py   # 插件验证
    ├── system/             # 系统服务
    │   ├── file_freshness.py
    │   ├── system_prompt.py
    │   └── reminders.py
    ├── agents/              # SubAgent 系统（Phase 5）
    │   ├── loader.py        # Agent 配置多源加载 + 优先级合并
    │   ├── storage.py       # Markdown + YAML frontmatter 解析
    │   ├── transcripts.py   # Transcript 内存存储
    │   ├── background_tasks.py  # 后台 Agent 任务管理
    │   └── fork_context.py  # ForkContext 上下文隔离
    └── telemetry/
        └── sentry.py
```

---

### Layer 4：Tools（工具实现层）

具体工具实现，继承 Core 的 Tool ABC：

```
pode_agent/
└── tools/
    ├── __init__.py         # 工具注册（get_all_tools()）
    ├── system/
    │   ├── bash.py         # BashTool
    │   ├── kill_shell.py   # KillShellTool
    │   └── task_output.py  # TaskOutputTool
    ├── filesystem/
    │   ├── file_read.py    # FileReadTool
    │   ├── file_write.py   # FileWriteTool
    │   ├── file_edit.py    # FileEditTool
    │   ├── glob_tool.py    # GlobTool
    │   ├── multi_edit.py   # MultiEditTool
    │   ├── notebook_read.py # NotebookReadTool
    │   └── notebook_edit.py # NotebookEditTool
    ├── search/
    │   ├── grep.py         # GrepTool（ripgrep/Python grep）
    │   └── lsp.py          # LspTool
    ├── network/
    │   ├── web_fetch.py    # WebFetchTool
    │   └── web_search.py   # WebSearchTool
    ├── mcp/
    │   ├── mcp_tool.py     # MCPTool
    │   ├── list_resources.py
    │   └── read_resource.py
    ├── interaction/
    │   ├── ask_user.py     # AskUserQuestionTool
    │   ├── slash_command.py # SlashCommandTool
    │   └── todo_write.py   # TodoWriteTool
    ├── ai/
    │   ├── ask_expert.py   # AskExpertModelTool
    │   └── skill.py        # SkillTool
    └── agent/
        ├── plan_mode.py    # EnterPlanModeTool / ExitPlanModeTool
        ├── task.py         # TaskTool
        └── ls.py           # LsTool
```

---

### Layer 5：Application（应用层）

业务编排，不处理 I/O 细节：

```
pode_agent/
└── app/
    ├── query.py            # Agentic Loop 核心引擎（query / query_core / ToolUseQueue）
    ├── repl.py             # REPL 主循环（业务逻辑，无 UI）
    ├── session.py          # 会话状态管理
    ├── compact.py          # 自动上下文压缩
    ├── orchestrator.py     # 工具调用编排
    └── print_mode.py       # 非交互模式逻辑
```

> 📖 **核心引擎详见**：[agent-loop.md](./agent-loop.md) — 详细描述了 `query_core()` 递归主循环、`ToolUseQueue` 并发工具调度器、Hook 系统、Auto-compact、Stop Hook 重入等运行时行为。  
> 📖 **工具系统详见**：[tools-system.md](./tools-system.md) — 工具的存储组织、注册/发现/启用过滤、与 LLM 的连接（ToolDefinition/tool_result）、权限耦合（Plan Mode 硬拒绝）、并发语义（is_concurrency_safe）。  
> 📖 **计划模式详见**：[plan-mode.md](./plan-mode.md) — Plan Mode 目标原则、Plan 数据结构、JSONL 存储方案、Enter/Exit 工具、多步执行流程、与 Agent Loop 的耦合点。

---

### Layer 6：UI（界面层）

基于 React + Ink v5 的终端 UI（TypeScript/Bun 运行时），通过 JSON-RPC over stdio 与 Python 后端通信。1:1 深度复刻 Kode-Agent 的 UI 层。

```
src/ui/
├── index.tsx                      # Ink render 入口
├── theme.ts                       # 4 套主题（dark/light/dark-daltonized/light-daltonized）
├── screens/
│   ├── REPL.tsx                   # 主 REPL 界面（~779 行，完整状态管理）
│   ├── ResumeConversation.tsx     # 会话恢复
│   ├── LogList.tsx                # 历史记录界面
│   ├── Doctor.tsx                 # 诊断界面
│   └── MCPServerApproval.tsx      # MCP 服务器审批
├── components/
│   ├── PromptInput.tsx            # 输入框（~860 行，补全/历史/粘贴/编辑器集成）
│   ├── TextInput.tsx              # 底层文本输入（bracketed paste/光标/多行）
│   ├── Message.tsx                # 消息分发器（路由到各消息类型组件）
│   ├── Spinner.tsx                # 加载动画
│   ├── Logo.tsx                   # 欢迎横幅
│   ├── Cost.tsx                   # 费用显示
│   ├── CostThresholdDialog.tsx    # 费用警告（>$5）
│   ├── RequestStatusIndicator.tsx # 请求状态指示
│   ├── ToolUseLoader.tsx          # 工具执行状态动画
│   ├── StructuredDiff.tsx         # Diff 渲染
│   ├── HighlightedCode.tsx        # 语法高亮代码
│   ├── MessageSelector.tsx        # 消息回溯选择
│   ├── Onboarding.tsx             # 首次运行向导
│   ├── TrustDialog.tsx            # 安全模式信任确认
│   ├── Help.tsx                   # 帮助显示
│   ├── Config.tsx                 # 设置界面
│   ├── messages/                  # 15 个消息类型组件
│   │   ├── AssistantTextMessage.tsx
│   │   ├── AssistantToolUseMessage.tsx
│   │   ├── AssistantThinkingMessage.tsx
│   │   ├── AssistantRedactedThinkingMessage.tsx
│   │   ├── AssistantBashOutputMessage.tsx
│   │   ├── TaskProgressMessage.tsx
│   │   ├── TaskToolMessage.tsx
│   │   ├── UserTextMessage.tsx
│   │   ├── UserImageMessage.tsx
│   │   ├── UserBashInputMessage.tsx
│   │   ├── UserCommandMessage.tsx
│   │   ├── UserKodingInputMessage.tsx
│   │   └── ...                    # 其他消息类型
│   ├── user-tool-result-message/  # 6 个工具结果组件
│   │   ├── UserToolResultMessage.tsx
│   │   ├── UserToolSuccessMessage.tsx
│   │   ├── UserToolErrorMessage.tsx
│   │   ├── UserToolRejectMessage.tsx
│   │   ├── UserToolCanceledMessage.tsx
│   │   └── utils.tsx
│   ├── permissions/               # 15+ 个权限对话框组件
│   │   ├── PermissionRequest.tsx  # 权限分发器
│   │   ├── BashPermissionRequest.tsx
│   │   ├── FileEditPermissionRequest.tsx
│   │   ├── FileWritePermissionRequest.tsx
│   │   ├── FilesystemPermissionRequest.tsx
│   │   ├── SlashCommandPermissionRequest.tsx
│   │   ├── SkillPermissionRequest.tsx
│   │   ├── WebFetchPermissionRequest.tsx
│   │   ├── EnterPlanModePermissionRequest.tsx
│   │   ├── ExitPlanModePermissionRequest.tsx
│   │   ├── AskUserQuestionPermissionRequest.tsx
│   │   ├── FallbackPermissionRequest.tsx
│   │   └── ...
│   ├── binary-feedback/           # A/B 反馈组件
│   │   ├── BinaryFeedback.tsx
│   │   ├── BinaryFeedbackOption.tsx
│   │   └── BinaryFeedbackView.tsx
│   ├── model-selector/            # 模型选择组件
│   │   ├── ModelSelector.tsx
│   │   ├── ModelSelectionScreen.tsx
│   │   └── ModelListManager.tsx
│   └── custom-select/             # 自定义选择器
│       ├── select.tsx
│       ├── select-option.tsx
│       └── use-select.ts
├── hooks/                         # 16 个 React Hooks
│   ├── useTerminalSize.ts         # 终端尺寸跟踪
│   ├── useTextInput.ts            # 文本输入 hook
│   ├── useUnifiedCompletion.ts    # 自动补全
│   ├── useArrowKeyHistory.ts      # 历史导航
│   ├── useCancelRequest.ts        # ESC 取消
│   ├── useCanUseTool.ts           # 工具权限检查
│   ├── useCostSummary.ts          # 费用追踪
│   ├── useDoublePress.ts          # 双击检测
│   ├── useExitOnCtrlCD.ts         # Ctrl+C/D 退出
│   ├── useInterval.ts             # setInterval hook
│   └── ...
└── rpc/
    └── client.ts                  # JSON-RPC 客户端（与 Python 后端通信）
```

**通信架构**：UI 进程（Bun）和后端进程（Python daemon）通过 stdio 双向 JSON-RPC 通信：

```
┌──────────────────────┐   stdin/stdout   ┌──────────────────────────┐
│   Bun Process        │ ◀══════════════▶ │   Python Process         │
│   (React + Ink v5)   │   JSON-RPC       │   (pode_agent/)          │
│                      │                  │                          │
│   UI 渲染 + 用户交互  │                  │   Agent Loop + Tools     │
│   状态管理（React）   │                  │   Session + Permissions  │
│   主题（Chalk 5）     │                  │   Config + Logging       │
└──────────────────────┘                  └──────────────────────────┘
```

---

### Layer 7：Entrypoints（入口层）

最薄的一层，负责启动和参数解析：

```
pode_agent/
└── entrypoints/
    ├── cli.py              # 主 CLI（typer），命令路由
    ├── mcp_server.py       # MCP 服务端模式
    ├── acp_server.py       # ACP 服务端模式
    └── setup.py            # 初始化序列（env、日志、context）
```

---

## 模块依赖图

```
entrypoints
    │
    ├──► app  ──────────────────────────────────────┐
    │       │                                       │
    │       ├──► services/ai ──► core/tools ──► infra
    │       ├──► services/mcp                       │
    │       ├──► services/context                   │
    │       ├──► services/plugins                   │
    │       ├──► core/permissions                   │
    │       ├──► core/config                        │
    │       └──► core/cost_tracker                  │
    │                                               │
    │       + JSON-RPC bridge (ui_bridge.py)        │
    │           │                                   │
    │           │ stdin/stdout JSON-RPC             │
    │           │                                   │
    │       src/ui/ (Bun Process) ◀─────────────────┘
    │         React + Ink v5
    │         5 Screens, 60+ Components, 16 Hooks
    │
tools ──(register to app via core/tools ABC)
```

**依赖方向规则**（严格执行）：

```
# Python 后端（单体进程）
infra ← core ← services ← tools ← app ← entrypoints

# TypeScript 前端（独立 Bun 进程）
src/ui/ ←→ (JSON-RPC over stdio) ←→ entrypoints/ui_bridge.py
```

任何违反此方向的导入都是架构错误。

---

## 核心组件详述

### 1. Tool 抽象基类（`core/tools/base.py`）

```python
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Any
from pydantic import BaseModel

class ToolOutput(BaseModel):
    type: Literal['result', 'progress']
    data: Any = None
    content: Any = None
    result_for_assistant: str | list | None = None
    new_messages: list | None = None
    normalized_messages: list | None = None
    tools: list | None = None

class ToolUseContext(BaseModel):
    message_id: str | None
    tool_use_id: str | None = None
    agent_id: str | None = None
    safe_mode: bool = False
    abort_controller: Any  # asyncio.Event 作为 abort signal
    read_file_timestamps: dict[str, float] = {}
    options: ToolOptions = ToolOptions()

class Tool(ABC):
    name: str
    description: str | Callable

    @abstractmethod
    def input_schema(self) -> type[BaseModel]:
        """返回 Pydantic 输入模型类"""
        ...

    @abstractmethod
    async def is_enabled(self) -> bool: ...

    @abstractmethod
    def is_read_only(self, input: Any = None) -> bool: ...

    @abstractmethod
    def needs_permissions(self, input: Any = None) -> bool: ...

    @abstractmethod
    async def call(
        self,
        input: BaseModel,
        context: ToolUseContext
    ) -> AsyncGenerator[ToolOutput, None]:
        """主执行方法，通过 AsyncGenerator 流式返回进度和结果"""
        yield  # pragma: no cover

    @abstractmethod
    def render_result_for_assistant(self, output: Any) -> str | list:
        """将工具结果格式化为 LLM 可读的格式"""
        ...
```

---

### 2. AI Provider 抽象（`services/ai/base.py`）

```python
class AIProvider(ABC):
    @abstractmethod
    async def query(
        self,
        params: UnifiedRequestParams,
    ) -> AsyncGenerator[AIResponse, None]:
        """流式查询 LLM，返回增量内容"""
        yield  # pragma: no cover

class UnifiedRequestParams(BaseModel):
    messages: list[Message]
    system_prompt: str
    model: str
    max_tokens: int
    tools: list[ToolDefinition] | None = None
    temperature: float | None = None
    thinking_tokens: int | None = None
    stream: bool = True

class AIResponse(BaseModel):
    type: Literal['delta', 'tool_use', 'done', 'error']
    content: str | None = None        # 文本增量
    tool_use: ToolUseBlock | None = None
    usage: TokenUsage | None = None
    cost_usd: float | None = None
```

---

### 3. Session Manager（`app/session.py`）

```python
class SessionManager:
    """管理单次对话的完整生命周期"""

    messages: list[Message]            # 对话历史
    in_progress_tool_use_ids: set[str] # 执行中的工具
    permission_context: ToolPermissionContext
    cost_summary: CostSummary
    log_file: Path                     # JSONL 日志路径

    async def process_user_input(self, prompt: str) -> AsyncGenerator:
        """主处理循环：输入 → LLM → 工具 → 响应"""
        ...

    async def execute_tool(
        self,
        tool_use: ToolUseBlock,
        context: ToolUseContext
    ) -> ToolResult:
        """执行单个工具调用"""
        ...

    def save_message(self, message: Message) -> None:
        """追加到 JSONL 日志"""
        ...
```

---

### 4. Permission Engine（`core/permissions/engine.py`）

```python
class PermissionEngine:
    async def has_permissions(
        self,
        tool_name: str,
        input: dict,
        context: PermissionContext,
    ) -> PermissionResult:
        """
        返回：
        - PermissionResult(allowed=True)       # 直接允许
        - PermissionResult(needs_prompt=True)  # 需要用户确认
        - PermissionResult(allowed=False)      # 拒绝
        """
        ...
```

---

## 关键设计决策

### 决策 1：使用 Pydantic v2 替代 Zod

**背景**：Zod 是 TypeScript 运行时 schema 验证库。Python 中最接近的是 Pydantic v2。

**选择 Pydantic v2 的理由**：
- 内置 JSON schema 生成（`model.model_json_schema()`）
- 严格类型验证，Mypy/Pyright 友好
- 性能优秀（Rust 实现的核心）
- 与 FastAPI 等框架天然兼容

**影响**：所有 Tool 的 `inputSchema` 改为 Pydantic Model 类。

---

### 决策 2：使用 React + Ink v5 深度复刻 Kode-Agent UI

**背景**：Kode-Agent 使用 React + Ink v5 构建终端 UI，包含 5 个 Screen、60+ 个组件、16 个 Hooks。

**选择 React + Ink 的理由**：
- 1:1 深度复刻 Kode-Agent 源码，降低维护偏差
- Ink v5 + React 18 是成熟的终端 UI 方案（Kode-Agent 已验证）
- 前后端解耦：UI（TypeScript/Bun）和后端（Python）独立开发
- 组件可直接从 Kode-Agent 移植，大幅减少 UI 开发工作量

**通信方式**：JSON-RPC over stdio/pipe，Python 后端作为 daemon 运行，TypeScript UI 作为独立 Bun 进程。

**替代方案考虑**：
- `Textual`（Python 原生但无法复刻 Kode-Agent 组件，需全部重写）
- `rich`（too simple, 无交互性）
- `urwid`（过时）

**影响**：UI 层使用 TypeScript/React（Ink v5），通过 JSON-RPC 与 Python 后端通信。后端（`pode_agent/`）需新增 `entrypoints/ui_bridge.py` 提供 JSON-RPC 服务端。

---

### 决策 3：AsyncGenerator 工具模式

**背景**：TypeScript 的 `async function*` 在 Python 中有完美对等：`async def` + `async for`。

**Python 实现**：

```python
# TypeScript:
async *call(input, context): AsyncGenerator<ToolOutput> {
  yield { type: 'progress', content: 'Running...' }
  yield { type: 'result', data: output }
}

# Python（等价）:
async def call(self, input, context) -> AsyncGenerator[ToolOutput, None]:
    yield ToolOutput(type='progress', content='Running...')
    yield ToolOutput(type='result', data=output)
```

**影响**：工具接口保持与原版高度一致。

---

### 决策 4：配置文件兼容性

**原版配置路径**：`~/.kode/config.json`  
**Pode-Agent 路径**：`~/.pode/config.json`

**格式完全兼容**，键名相同（保留 snake_case）。

提供迁移工具：`pode migrate-from-kode`。

---

### 决策 5：异步优先

所有 I/O 操作（文件、网络、Shell）默认异步：

```python
# 不允许
import requests
response = requests.get(url)   # ❌ 阻塞

# 标准做法
import httpx
async with httpx.AsyncClient() as client:
    response = await client.get(url)  # ✅
```

**Shell 执行使用** `asyncio.create_subprocess_exec`：

```python
proc = await asyncio.create_subprocess_exec(
    *shlex.split(command),
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
)
stdout, stderr = await proc.communicate()
```

---

## 异步模型

Pode-Agent 的异步模型基于 Python `asyncio`：

```
┌──────────────────────────────────────────────────┐
│              双进程架构                           │
│                                                   │
│  ┌──────────────────────────┐                    │
│  │  Bun Process             │                    │
│  │  (React + Ink v5)        │                    │
│  │                          │                    │
│  │  UI 渲染 + 用户交互       │                    │
│  │  React 状态管理           │                    │
│  │  Chalk 5 主题/颜色        │                    │
│  └───────────┬──────────────┘                    │
│              │ stdin/stdout JSON-RPC              │
│  ┌───────────▼──────────────┐                    │
│  │  Python Process          │                    │
│  │  (asyncio Event Loop)    │                    │
│  │                          │                    │
│  │  ┌──────────────────┐    │                    │
│  │  │ Session Task     │    │                    │
│  │  │ (REPL Engine)    │    │                    │
│  │  └──────────────────┘    │                    │
│  │                          │                    │
│  │  ┌──────────────────────┐│                    │
│  │  │ Tool Executor Tasks  ││                    │
│  │  │ (parallel)           ││                    │
│  │  │ [Bash][FileEdit]...  ││                    │
│  │  └──────────────────────┘│                    │
│  └──────────────────────────┘                    │
└──────────────────────────────────────────────────┘
```

**UI 与业务逻辑解耦**（通过 JSON-RPC over stdio）：

- Python 后端作为 daemon 运行，监听 stdin 接收 JSON-RPC 请求
- Bun UI 进程通过 stdout 发送用户事件，通过 stdin 接收会话事件
- 工具调用在独立 asyncio Task 中运行（支持中断）

**中断信号**：

```python
# 用 asyncio.Event 替代 AbortController
abort_event = asyncio.Event()

async def run_tool_with_cancel(tool, input, context):
    tool_task = asyncio.create_task(
        collect_tool_result(tool, input, context)
    )
    abort_task = asyncio.create_task(abort_event.wait())
    
    done, pending = await asyncio.wait(
        [tool_task, abort_task],
        return_when=asyncio.FIRST_COMPLETED
    )
    for task in pending:
        task.cancel()
```

---

## 错误处理策略

### 分层错误处理

```
Tool Error
    └─► ToolExecutionError（caught by Orchestrator）
            └─► 格式化为 tool_result（error message）
            └─► 继续对话（LLM 可 retry 或报告）

AI Provider Error
    └─► APIError（caught by Session）
            ├─► 可重试：自动退避重试（最多 3 次）
            └─► 不可重试：显示错误消息，允许用户重新输入

Permission Error
    └─► PermissionDenied（caught by REPL）
            └─► 通知 LLM 工具被拒绝

Critical Error
    └─► 捕获到 Exception Loop 顶层
            ├─► Sentry 上报
            ├─► 保存当前会话
            └─► 优雅退出
```

### 自定义异常层次

```python
class PodeAgentError(Exception): pass

class ToolError(PodeAgentError): pass
class PermissionDenied(PodeAgentError): pass
class ConfigError(PodeAgentError): pass

class AIError(PodeAgentError): pass
class APIRateLimitError(AIError): pass
class APIAuthError(AIError): pass
class APIConnectionError(AIError): pass
```

---

## 扩展点

### 1. 自定义工具（Custom Tool）

通过 Python 入口点（entry_points）注册：

```python
# pyproject.toml
[project.entry-points."pode_agent.tools"]
my_tool = "my_package.tools:MyTool"
```

或通过 YAML 自定义命令（兼容 Kode-Agent 格式）。

### 2. 自定义 Provider

实现 `AIProvider` ABC 并注册：

```python
class MyProvider(AIProvider):
    async def query(self, params) -> AsyncGenerator[AIResponse, None]:
        ...

# 注册
from pode_agent.services.ai.factory import register_provider
register_provider("my-provider", MyProvider)
```

### 3. 插件（Plugin/Skill）

通过 YAML manifest 定义，可从 GitHub/URL/本地安装：

```yaml
# skill.yaml
name: my-skill
description: My custom skill
commands:
  - name: do-something
    prompt: "Please do {{arg}} to {{file}}"
```

### 4. UI 主题

```typescript
// 自定义主题（Chalk 5 + TypeScript）
// 1:1 复刻 Kode-Agent 的 theme.ts
type Theme = {
  kode: string           // 主品牌色
  text: string           // 主文本
  secondaryText: string  // 次要文本
  permission: string     // 权限对话框强调色
  planMode: string       // 计划模式强调色
  success: string        // 成功消息
  error: string          // 错误消息
  warning: string        // 警告消息
  diff: {
    added: string        // Diff 新增行
    removed: string      // Diff 删除行
  }
}

// 4 套内置主题：dark / light / dark-daltonized / light-daltonized
```
