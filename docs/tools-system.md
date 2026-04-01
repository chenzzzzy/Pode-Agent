# Pode-Agent 工具系统（Tools System）

> 版本：1.0.0 | 状态：草稿 | 更新：2026-04-01  
> 本文档是 **工具系统的权威设计文档**，涵盖工具的组织、注册、发现、注入与执行全链路。  
> 并发执行调度（ToolUseQueue）的完整行为规格见 [agent-loop.md](./agent-loop.md)；  
> Plan Mode 对工具集的约束见 [plan-mode.md](./plan-mode.md)。

---

## 目录

1. [概述](#概述)
2. [工具的存储与组织](#工具的存储与组织)
3. [工具元数据规范（Tool ABC）](#工具元数据规范)
4. [工具的注册与发现（Discovery）](#工具的注册与发现)
5. [工具注入到 Agentic Loop](#工具注入到-agentic-loop)
6. [工具 Schema 与 LLM API 的连接](#工具-schema-与-llm-api-的连接)
7. [工具执行事件流](#工具执行事件流)
8. [权限系统与工具系统的耦合点](#权限系统与工具系统的耦合点)
9. [并发执行语义](#并发执行语义)
10. [内置工具与 MCP/插件工具的边界](#内置工具与-mcp插件工具的边界)
11. [Kode-Agent → Pode-Agent 映射表](#kode-agent--pode-agent-映射表)
12. [实现阶段划分](#实现阶段划分)

---

## 概述

Pode-Agent 的工具系统将 LLM 的"函数调用（Function Calling）"能力与具体的操作实现解耦。  
整体设计遵循以下原则：

- **静态注册，动态过滤**：所有内置工具在启动时一次性注册，运行时根据环境和配置动态过滤出可用工具。
- **统一 ABC 契约**：所有工具（内置 / MCP / 插件）实现同一个 `Tool` 抽象基类，对上层（Agentic Loop）无区别。
- **权限解耦**：工具只声明"是否需要权限（`needs_permissions`）"，实际权限决策由 `PermissionEngine` 负责。
- **AsyncGenerator 流式输出**：工具通过 `AsyncGenerator[ToolOutput, None]` 向上层推送进度和结果，与 UI 解耦。

---

## 工具的存储与组织

### 目录结构

Kode-Agent 将工具按功能类别分目录存储（`src/tools/{category}/{ToolName}/`）。  
Pode-Agent 采用相同的扁平分类，映射为 Python 包目录：

```
pode_agent/
└── tools/
    ├── __init__.py
    ├── agent/
    │   ├── __init__.py
    │   ├── plan_mode.py          # EnterPlanModeTool / ExitPlanModeTool
    │   ├── task.py               # TaskTool（子 Agent 调度）
    │   └── ls.py                 # LsTool
    ├── filesystem/
    │   ├── __init__.py
    │   ├── file_read.py          # FileReadTool
    │   ├── file_write.py         # FileWriteTool
    │   ├── file_edit.py          # FileEditTool
    │   ├── multi_edit.py         # MultiEditTool
    │   ├── glob_tool.py          # GlobTool
    │   ├── notebook_read.py      # NotebookReadTool
    │   └── notebook_edit.py      # NotebookEditTool
    ├── search/
    │   ├── __init__.py
    │   ├── grep.py               # GrepTool
    │   └── lsp.py                # LspTool
    ├── system/
    │   ├── __init__.py
    │   ├── bash.py               # BashTool
    │   ├── kill_shell.py         # KillShellTool
    │   └── task_output.py        # TaskOutputTool
    ├── network/
    │   ├── __init__.py
    │   ├── web_fetch.py          # WebFetchTool
    │   └── web_search.py         # WebSearchTool
    ├── interaction/
    │   ├── __init__.py
    │   ├── ask_user.py           # AskUserQuestionTool
    │   ├── todo_write.py         # TodoWriteTool
    │   └── slash_command.py      # SlashCommandTool
    ├── ai/
    │   ├── __init__.py
    │   ├── ask_expert.py         # AskExpertModelTool
    │   └── skill.py              # SkillTool
    └── mcp/
        ├── __init__.py
        ├── mcp_tool.py           # MCPTool（动态代理）
        ├── list_resources.py     # ListMcpResourcesTool
        └── read_resource.py      # ReadMcpResourceTool
```

每个工具文件导出一个与文件同名的类，继承自 `pode_agent.core.tools.base.Tool`。

### 工具注册入口

类似于 Kode-Agent 的 `src/tools/index.ts`，Pode-Agent 在 `pode_agent/tools/__init__.py` 中集中声明所有内置工具：

```python
# pode_agent/tools/__init__.py

from .agent.plan_mode import EnterPlanModeTool, ExitPlanModeTool
from .agent.task import TaskTool
from .agent.ls import LsTool
from .filesystem.file_read import FileReadTool
from .filesystem.file_write import FileWriteTool
from .filesystem.file_edit import FileEditTool
from .filesystem.multi_edit import MultiEditTool
from .filesystem.glob_tool import GlobTool
from .filesystem.notebook_read import NotebookReadTool
from .filesystem.notebook_edit import NotebookEditTool
from .search.grep import GrepTool
from .search.lsp import LspTool
from .system.bash import BashTool
from .system.kill_shell import KillShellTool
from .system.task_output import TaskOutputTool
from .network.web_fetch import WebFetchTool
from .network.web_search import WebSearchTool
from .interaction.ask_user import AskUserQuestionTool
from .interaction.todo_write import TodoWriteTool
from .interaction.slash_command import SlashCommandTool
from .ai.ask_expert import AskExpertModelTool
from .ai.skill import SkillTool
from .mcp.mcp_tool import MCPTool
from .mcp.list_resources import ListMcpResourcesTool
from .mcp.read_resource import ReadMcpResourceTool

#: 所有内置工具实例（有序列表）
ALL_BUILTIN_TOOLS: list["Tool"] = [
    TaskTool(),
    AskExpertModelTool(),
    BashTool(),
    TaskOutputTool(),
    KillShellTool(),
    LsTool(),
    GlobTool(),
    GrepTool(),
    LspTool(),
    FileReadTool(),
    FileWriteTool(),
    FileEditTool(),
    MultiEditTool(),
    NotebookReadTool(),
    NotebookEditTool(),
    TodoWriteTool(),
    WebSearchTool(),
    WebFetchTool(),
    AskUserQuestionTool(),
    EnterPlanModeTool(),
    ExitPlanModeTool(),
    SlashCommandTool(),
    SkillTool(),
    ListMcpResourcesTool(),
    ReadMcpResourceTool(),
    MCPTool(),
]
```

---

## 工具元数据规范

每个工具必须实现 `Tool` ABC（定义在 `pode_agent/core/tools/base.py`）。  
核心方法对应 Kode-Agent 的 Tool 接口：

```python
class Tool(ABC):
    """所有工具的抽象基类"""

    name: str
    """工具标识符，唯一，英文驼峰（如 'BashTool'）"""

    @abstractmethod
    def input_schema(self) -> type[BaseModel]:
        """
        返回 Pydantic 输入模型类。
        框架自动调用 model_json_schema() 生成 LLM function calling schema。
        等价于 Kode-Agent 的 Zod inputSchema。
        """

    @abstractmethod
    async def description(self) -> str:
        """给 LLM 的工具描述，异步允许动态生成"""

    @abstractmethod
    async def is_enabled(self) -> bool:
        """
        是否在当前环境启用。
        如 LspTool 在无 LSP 可用时返回 False。
        getTools() 会过滤掉 False 的工具。
        """

    @abstractmethod
    def is_read_only(self, input: Any = None) -> bool:
        """
        是否为只读操作（不修改文件系统 / 执行危险命令）。
        Plan Mode 下只允许调用 is_read_only() == True 的工具。
        等价于 Kode-Agent 的 isReadOnly()。
        """

    def is_concurrency_safe(self, input: Any = None) -> bool:
        """
        是否可与其他工具并发执行。
        等价于 Kode-Agent 的 isConcurrencySafe()。
        默认 False（串行执行）。
        """
        return False

    @abstractmethod
    def needs_permissions(self, input: Any = None) -> bool:
        """
        是否需要用户权限确认。
        True：由 PermissionEngine 判断是否需要弹权限对话框。
        False：直接执行（如 GlobTool、FileReadTool 通常不需要）。
        """

    @abstractmethod
    def call(
        self, input: BaseModel, context: ToolUseContext
    ) -> AsyncGenerator["ToolOutput", None]:
        """
        工具执行入口，返回 AsyncGenerator。
        yield {"type": "progress", ...} 用于流式进度。
        yield {"type": "result", "data": ..., "result_for_assistant": ...} 表示结束。
        """

    def render_result_for_assistant(self, output: Any) -> str | list:
        """将工具结果格式化为 LLM 可读格式（注入 tool_result 消息）"""

    def user_facing_name(self) -> str:
        """UI 显示的工具名称，可为空字符串（则不显示工具调用头）"""
        return self.name

    async def prompt(self) -> str | None:
        """
        工具自带的 System Prompt 追加内容（可选）。
        EnterPlanModeTool 用此机制注入计划模式约束。
        等价于 Kode-Agent 的 tool.prompt()。
        """
        return None

    def requires_user_interaction(self) -> bool:
        """
        是否需要用户主动确认（不仅是权限，而是真正的交互）。
        EnterPlanModeTool / ExitPlanModeTool 返回 True。
        """
        return False
```

### tool name alias（名称别名）

Kode-Agent 中存在 tool name alias 机制（在 `runToolUse` 中解析别名后再查找工具）。  
Pode-Agent 在 `ToolRegistry` 中实现：

```python
# pode_agent/core/tools/registry.py

class ToolRegistry:
    _tools: dict[str, Tool] = {}
    _aliases: dict[str, str] = {}  # alias → canonical name

    def register(self, tool: Tool, aliases: list[str] | None = None) -> None:
        self._tools[tool.name] = tool
        for alias in (aliases or []):
            self._aliases[alias] = tool.name

    def get(self, name: str) -> Tool | None:
        canonical = self._aliases.get(name, name)
        return self._tools.get(canonical)
```

---

## 工具的注册与发现

### get_all_tools() / get_tools() / get_read_only_tools()

类比 Kode-Agent 的 `getAllTools()` / `getTools()` / `getReadOnlyTools()`，  
Pode-Agent 提供以下函数：

```python
# pode_agent/tools/loader.py

from functools import lru_cache
from pode_agent.tools import ALL_BUILTIN_TOOLS
from pode_agent.services.mcp.client import get_mcp_tools

def get_all_tools() -> list[Tool]:
    """返回所有内置工具实例（不含 MCP 工具，不过滤）"""
    return list(ALL_BUILTIN_TOOLS)

async def get_tools(include_optional: bool = False) -> list[Tool]:
    """
    返回当前环境可用的全部工具（内置 + MCP）。
    - 内置工具：过滤 is_enabled() == False 的工具
    - MCP 工具：从已连接的 MCP 服务器动态加载
    等价于 Kode-Agent 的 getTools()。
    """
    builtin = get_all_tools()
    mcp_tools = await get_mcp_tools()
    all_tools = builtin + mcp_tools
    enabled = await asyncio.gather(*[t.is_enabled() for t in all_tools])
    return [t for t, ok in zip(all_tools, enabled) if ok]

async def get_read_only_tools() -> list[Tool]:
    """
    返回只读工具列表（Plan Mode 使用）。
    等价于 Kode-Agent 的 getReadOnlyTools()。
    """
    tools = get_all_tools()
    read_only = [t for t in tools if t.is_read_only()]
    enabled = await asyncio.gather(*[t.is_enabled() for t in read_only])
    return [t for t, ok in zip(read_only, enabled) if ok]
```

### 配置过滤

除了 `is_enabled()` 过滤，还需应用来自 `ProjectConfig` 的工具配置：

```python
def filter_tools_by_config(
    tools: list[Tool],
    config: ProjectConfig,
    command_allowed_tools: list[str] | None = None,
) -> list[Tool]:
    """
    根据配置过滤工具列表：
    - command_allowed_tools：CLI 命令指定的工具白名单
    - config.denied_tools：项目配置的工具黑名单
    - config.allowed_tools：项目配置的工具白名单（若设置则只允许此列表）
    """
    result = []
    for tool in tools:
        name = tool.name
        # 1. 命令行白名单优先
        if command_allowed_tools is not None:
            if name not in command_allowed_tools:
                continue
        # 2. 项目级黑名单
        if name in config.denied_tools:
            continue
        # 3. 项目级白名单（若有）
        if config.allowed_tools and name not in config.allowed_tools:
            continue
        result.append(tool)
    return result
```

---

## 工具注入到 Agentic Loop

### 工具列表的传递路径

```
CLI/UI
  │
  ▼
SessionManager.__init__()
  │  调用 get_tools() + filter_tools_by_config()
  │  得到 self.tools: list[Tool]
  ▼
query(messages, system_prompt, tools=self.tools, ...)
  │
  ▼
query_core(messages, system_prompt, tools, ...)
  │  将 tools 转换为 LLM provider 格式
  │  注入 system prompt（tool.prompt() 追加）
  ▼
LLM API 调用（携带 tools 参数）
```

对应 Kode-Agent 的 `toolUseContext.options.tools`，Pode-Agent 将工具列表作为显式参数传递给 `query()` / `query_core()`，而非通过全局上下文。

### UI 工具选择

- **完整工具集**（交互模式 REPL）：`await get_tools()`
- **只读工具集**（Plan Mode）：`await get_read_only_tools()`，见 [plan-mode.md](./plan-mode.md)
- **CLI 指定工具集**：通过 `--allowed-tools` 参数，传入 `filter_tools_by_config()`

---

## 工具 Schema 与 LLM API 的连接

### Pydantic → JSON Schema → LLM 工具格式

每个工具的 `input_schema()` 返回一个 Pydantic `BaseModel` 子类，框架自动将其转换为 LLM 所需的格式：

```python
# pode_agent/services/ai/schema_converter.py

def tool_to_anthropic_format(tool: Tool) -> dict:
    """将 Tool 转换为 Anthropic API 的 tools 格式"""
    schema = tool.input_schema().model_json_schema()
    return {
        "name": tool.name,
        "description": await tool.description(),
        "input_schema": schema,
    }

def tool_to_openai_format(tool: Tool) -> dict:
    """将 Tool 转换为 OpenAI API 的 tools 格式"""
    schema = tool.input_schema().model_json_schema()
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": await tool.description(),
            "parameters": schema,
        },
    }
```

### tool_use → tool_result 的消息格式

LLM 响应中的 `tool_use` block 经过工具执行后，以 `tool_result` 形式追加到消息历史：

```
┌─────────────────────────────────────────────────┐
│ AssistantMessage（含 tool_use block）            │
│  {                                               │
│    "type": "tool_use",                           │
│    "id": "toolu_01X...",                         │
│    "name": "BashTool",                           │
│    "input": {"command": "ls -la"}                │
│  }                                               │
└─────────────────────────────────────────────────┘
              │ ToolUseQueue 执行工具
              ▼
┌─────────────────────────────────────────────────┐
│ UserMessage（含 tool_result block）              │
│  {                                               │
│    "type": "tool_result",                        │
│    "tool_use_id": "toolu_01X...",                │
│    "content": "total 48\ndrwxr-xr-x ...\n..."   │
│  }                                               │
└─────────────────────────────────────────────────┘
              │ 追加到消息历史后递归调用 query_core()
              ▼
         （下一轮 LLM 调用）
```

`content` 字段来自 `tool.render_result_for_assistant(output)`。  
对于工具执行失败，`content` 包含错误描述，`is_error: true`。

---

## 工具执行事件流

工具 `call()` 返回的 `AsyncGenerator[ToolOutput, None]` 产生两种事件：

```python
class ToolOutput(BaseModel):
    type: Literal["progress", "result"]

    # type == "progress"：流式进度
    content: Any = None           # 进度内容（文本 / 数字 / 结构体）
    normalized_messages: list | None = None

    # type == "result"：最终结果
    data: Any = None              # 结构化结果数据
    result_for_assistant: str | list | None = None  # 注入 tool_result 的文本
    new_messages: list | None = None  # TaskTool 等工具产生的子消息
```

事件流经由 ToolUseQueue → `query_core()` → `SessionManager` → UI 的事件队列传递。  
完整的调度行为见 [agent-loop.md — ToolUseQueue：并发工具调度器](./agent-loop.md#toolUseQueue并发工具调度器)。

### progress 事件的 UI 消费

```
工具.call() yield ToolOutput(type="progress", content="Running...")
    │
    ▼
ToolUseQueue 转发为 SessionEvent(type=TOOL_PROGRESS, ...)
    │
    ▼
UI 更新工具调用行（spinner / 进度条）

工具.call() yield ToolOutput(type="result", data=..., result_for_assistant=...)
    │
    ▼
ToolUseQueue 转发为 SessionEvent(type=TOOL_RESULT, ...)
    │
    ▼
UI 渲染工具结果（折叠显示）
```

---

## 权限系统与工具系统的耦合点

### 权限检查流程

```
ToolUseQueue 决定执行某工具
    │
    ▼
check_permissions_and_call_tool(tool, input, context)
    │
    ├─ 1. run_pre_tool_use_hooks()（Phase 5）
    │
    ├─ 2. Pydantic 输入验证（tool.input_schema().model_validate(raw_input)）
    │
    ├─ 3. tool.needs_permissions(input) == False？
    │       → 直接执行（GlobTool、FileReadTool 等通常为 False）
    │
    └─ 4. tool.needs_permissions(input) == True？
            → PermissionEngine.has_permissions(tool.name, input, context)
                │
                ├─ PermissionMode.BYPASS_PERMISSIONS → 直接允许
                ├─ PermissionMode.PLAN → 只读工具允许，写操作拒绝
                ├─ PermissionMode.ACCEPT_EDITS → 文件编辑自动允许
                ├─ PermissionMode.DONT_ASK → 从不询问（拒绝危险操作）
                ├─ 已持久化允许 → 直接允许
                ├─ 已持久化拒绝 → 直接拒绝
                └─ 未知 → NEEDS_PROMPT → 发送 SESSION_PERMISSION_REQUEST 事件
                                            等待用户决策（UI 弹权限对话框）
```

权限模式（`PermissionMode`）由以下来源决定（优先级从高到低）：

1. `ToolUseContext.options.tool_permission_context.mode`（子 Agent 传入）
2. `ToolUseContext.options.permission_mode`（CLI 选项 `--permission-mode`）
3. `permissionModeByConversationKey`（运行时动态设置，如 EnterPlanModeTool 触发）
4. 默认值：`PermissionMode.DEFAULT`

> 📖 Permission Mode 与 Plan Mode 的关系详见 [plan-mode.md — 与权限系统的耦合](./plan-mode.md#与-agent-loop-的耦合点)。

### needsPermissions 的设计约定

| 工具类别 | `needs_permissions` 默认值 | 说明 |
|---------|--------------------------|------|
| 只读文件工具（FileReadTool、GlobTool、GrepTool） | `False` | 读操作通常不需要确认 |
| 写文件工具（FileWriteTool、FileEditTool） | `True` | 修改文件需要确认 |
| Shell 执行（BashTool） | 动态（取决于命令） | `needs_permissions(input)` 根据命令内容判断 |
| 网络工具（WebFetchTool、WebSearchTool） | `True` | 外部请求需确认 |
| 交互工具（AskUserQuestionTool、EnterPlanModeTool） | `True` | 需用户主动参与 |
| MCP 工具 | `True` | 外部服务调用需确认 |

### 批量权限与单次权限

`PermissionDecision` 有三种：

```python
class PermissionDecision(str, Enum):
    ALLOW_ONCE = "allow_once"    # 本次允许（不持久化）
    ALLOW_ALL = "allow_all"      # 本会话允许（持久化到 ProjectConfig.allowed_tools）
    DENY = "deny"                # 拒绝（工具执行失败，返回错误给 LLM）
```

---

## 并发执行语义

> 📖 **完整的 ToolUseQueue 设计规格（含 barrier 逻辑、sibling abort）见** [agent-loop.md — ToolUseQueue：并发工具调度器](./agent-loop.md#toolUseQueue并发工具调度器)。

本节仅概述与工具系统相关的关键点：

### `is_concurrency_safe()` 的定义

当 LLM 在一次回复中请求多个工具时，ToolUseQueue 决定其执行方式：

- **`is_concurrency_safe() == True`**：工具可与其他并发安全工具同时执行（`asyncio.gather`）。  
  典型例子：`GlobTool`、`GrepTool`、`FileReadTool`（只读，无副作用）。

- **`is_concurrency_safe() == False`**（默认）：工具形成 **barrier**，必须等待当前所有并发工具完成后才能开始，且之后的工具也必须等它完成。  
  典型例子：`BashTool`（有副作用）、`FileEditTool`（写操作）。

### 工具实现约定

```python
class GlobTool(Tool):
    name = "GlobTool"

    def is_concurrency_safe(self, input=None) -> bool:
        return True  # 只读，可并发

class BashTool(Tool):
    name = "BashTool"

    def is_concurrency_safe(self, input=None) -> bool:
        return False  # 有副作用，形成 barrier（默认行为，可省略）
```

---

## 内置工具与 MCP/插件工具的边界

### 三类工具

| 类型 | 来源 | 注册方式 | 是否有权限检查 |
|------|------|---------|--------------|
| **内置工具** | `pode_agent/tools/` | 静态，启动时注册 | 由 `tool.needs_permissions()` 决定 |
| **MCP 工具** | 外部 MCP 服务器 | 动态，连接时加载 | 统一要求权限确认（`needs_permissions=True`） |
| **插件工具（Skill）** | `~/.pode/skills/` | 动态，启动时扫描 | YAML manifest 中声明 |

### MCPTool 的工作方式

MCP 工具通过 `MCPTool` 代理类包装：

```python
class MCPTool(Tool):
    """动态代理外部 MCP 服务器上的工具"""
    name: str           # 来自 MCP 工具元数据
    mcp_server: str     # MCP 服务器标识
    mcp_tool_name: str  # 原始工具名

    def is_read_only(self) -> bool:
        return False  # MCP 工具默认为非只读（保守策略）

    def needs_permissions(self, input=None) -> bool:
        return True   # MCP 工具始终需要权限确认

    async def call(self, input, context):
        # 通过 MCPClient 调用远端工具
        async for output in mcp_client.call_tool(self.mcp_tool_name, input):
            yield output
```

### 后续阶段边界

| 功能 | 实现阶段 |
|------|---------|
| 内置工具完整集（25+） | Phase 3 |
| MCP 客户端 + MCPTool 动态加载 | Phase 5 |
| Skill 插件工具（SkillTool） | Phase 5 |
| 工具 entry_points 自动发现（`pyproject.toml`） | Phase 6 |

---

## Kode-Agent → Pode-Agent 映射表

| Kode-Agent（TypeScript） | Pode-Agent（Python） | 说明 |
|--------------------------|----------------------|------|
| `src/tools/index.ts` `getAllTools()` | `pode_agent/tools/__init__.py` `ALL_BUILTIN_TOOLS` | 内置工具静态列表 |
| `src/tools/index.ts` `getTools()` | `pode_agent/tools/loader.py` `get_tools()` | 动态过滤可用工具 |
| `src/tools/index.ts` `getReadOnlyTools()` | `pode_agent/tools/loader.py` `get_read_only_tools()` | 只读工具（Plan Mode） |
| `Tool` interface（`@tool`） | `pode_agent/core/tools/base.py` `Tool` ABC | 工具抽象接口 |
| `tool.inputSchema`（Zod） | `tool.input_schema()`（Pydantic BaseModel） | 输入 Schema |
| `tool.isConcurrencySafe()` | `tool.is_concurrency_safe()` | 并发安全标记 |
| `tool.isReadOnly()` | `tool.is_read_only()` | 只读标记 |
| `tool.needsPermissions()` | `tool.needs_permissions()` | 权限标记 |
| `tool.renderResultForAssistant()` | `tool.render_result_for_assistant()` | LLM 结果格式化 |
| `tool.prompt()` | `tool.prompt()` | System Prompt 追加 |
| `tool.requiresUserInteraction()` | `tool.requires_user_interaction()` | 需要用户交互 |
| `src/utils/tooling/` | `pode_agent/core/tools/registry.py` + `loader.py` | 工具注册/加载辅助 |
| `src/tools/agent/TaskTool/` | `pode_agent/tools/agent/task.py` | 子 Agent 工具 |
| `src/tools/agent/PlanModeTool/` | `pode_agent/tools/agent/plan_mode.py` | Plan Mode 工具 |
| `src/tools/mcp/MCPTool/` | `pode_agent/tools/mcp/mcp_tool.py` | MCP 代理工具 |
| `@utils/permissions/permissionModeState.ts` | `pode_agent/core/permissions/engine.py` | 权限模式状态 |
| `@utils/plan/planMode.ts` | `pode_agent/app/plan_state.py` | Plan Mode 状态管理 |

---

## 实现阶段划分

| 组件 | 实现阶段 | 对应任务 |
|------|---------|---------|
| Tool ABC + ToolRegistry + ToolOutput | Phase 0（已完成） | 任务 0.1 |
| BashTool + 权限系统（needs_permissions） | Phase 1 | 任务 1.1-1.2 |
| 文件系统工具（FileRead/Write/Edit/Glob） | Phase 1 | 任务 1.3 |
| GrepTool + LsTool | Phase 1 | 任务 1.4-1.5 |
| 工具注入 Agentic Loop（get_tools + query） | Phase 2 | 任务 2.5 |
| ToolUseQueue 串行版 | Phase 2 | 任务 2.5 |
| ToolUseQueue 并发版（is_concurrency_safe） | Phase 3 | Phase 3 升级 |
| Plan Mode 工具（Enter/Exit PlanMode） | Phase 3 | 低优先级工具 |
| 完整内置工具集（25+） | Phase 3 | 任务 3.x |
| get_tools() 配置过滤（denied/allowed_tools） | Phase 3 | Phase 3 |
| MCP 工具动态加载 | Phase 5 | 任务 5.1 |
| Skill 插件工具 | Phase 5 | 任务 5.3 |
| entry_points 工具自动发现 | Phase 6 | 任务 6.x |
