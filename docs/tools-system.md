# Pode-Agent 工具系统

> 版本：1.0.0 | 状态：草稿 | 更新：2026-04-01  
> 本文档是**工具系统的权威设计文档**，涵盖存储组织、注册发现、启用过滤、与 LLM 的连接、权限耦合、并发语义、MCP/插件边界，以及 Kode-Agent → Pode-Agent 映射表。  
> 工具在 Agent 循环中的运行时调度（ToolUseQueue、Hook 执行、tool_result 回灌）请参阅 [agent-loop.md](./agent-loop.md)。

---

## 目录

1. [工具的存储与组织（Storage/Layout）](#工具的存储与组织)
2. [Tool 基类接口](#tool-基类接口)
3. [工具注册与发现（Registry/Discovery）](#工具注册与发现)
4. [工具启用与过滤（Enablement）](#工具启用与过滤)
5. [工具如何注入 Agent Loop](#工具如何注入-agent-loop)
6. [工具与 LLM API 的连接](#工具与-llm-api-的连接)
7. [权限系统与工具的耦合点](#权限系统与工具的耦合点)
8. [并发语义](#并发语义)
9. [与 MCP/插件系统边界](#与-mcp插件系统边界)
10. [分阶段实现建议](#分阶段实现建议)
11. [映射表：Kode-Agent → Pode-Agent](#映射表kode-agent--pode-agent)

---

## 工具的存储与组织

### 目录结构

所有工具实现位于 `pode_agent/tools/`，按**功能域**分包，每个工具一个文件或子包：

```
pode_agent/
├── core/
│   └── tools/
│       ├── base.py        # Tool ABC + ToolOutput + ToolUseContext（抽象定义）
│       ├── registry.py    # ToolRegistry（内存态注册表）
│       └── executor.py    # collect_tool_result（消费 AsyncGenerator）
└── tools/                 # 具体工具实现（继承 core/tools/base.Tool）
    ├── __init__.py        # get_all_tools()：返回所有内置工具实例
    ├── system/
    │   ├── bash.py        # BashTool
    │   ├── kill_shell.py  # KillShellTool
    │   └── task_output.py # TaskOutputTool
    ├── filesystem/
    │   ├── file_read.py   # FileReadTool
    │   ├── file_write.py  # FileWriteTool
    │   ├── file_edit.py   # FileEditTool
    │   ├── glob_tool.py   # GlobTool
    │   ├── multi_edit.py  # MultiEditTool
    │   ├── notebook_read.py
    │   └── notebook_edit.py
    ├── search/
    │   ├── grep.py        # GrepTool
    │   └── lsp.py         # LspTool
    ├── network/
    │   ├── web_fetch.py   # WebFetchTool
    │   └── web_search.py  # WebSearchTool
    ├── interaction/
    │   ├── ask_user.py    # AskUserQuestionTool
    │   ├── slash_command.py
    │   └── todo_write.py  # TodoWriteTool
    ├── ai/
    │   ├── ask_expert.py  # AskExpertModelTool
    │   └── skill.py       # SkillTool
    └── agent/
        ├── plan_mode.py   # EnterPlanModeTool / ExitPlanModeTool
        ├── task.py        # TaskTool
        └── ls.py          # LsTool
```

**关键分层约定**：
- `core/tools/base.py`：只定义抽象，**不含任何具体工具逻辑**
- `tools/` 下的工具实现**只能依赖 core 层及以下**（不得依赖 services、app、ui）
- `tools/__init__.py` 中的 `get_all_tools()` 是内置工具的唯一注册入口

---

## Tool 基类接口

所有工具继承 `pode_agent.core.tools.base.Tool`（ABC）：

```python
# pode_agent/core/tools/base.py

from abc import ABC, abstractmethod
from typing import AsyncGenerator, Any, ClassVar
from pydantic import BaseModel

class Tool(ABC):
    # ── 元信息（类级别属性）────────────────────────────────────
    name: ClassVar[str]                           # 唯一标识符，供 LLM tool_use.name 匹配（子类必须赋值）
    description: ClassVar[str | None]             # LLM 可见的静态工具描述（固定文字）
    cached_description: str | None = None         # 动态描述的运行时缓存（实例属性）；
                                                  # 若工具描述需根据环境动态生成，在首次 `is_enabled()` 后
                                                  # 填入此字段，后续通过 get_description() 优先读取此缓存

    # ── 输入 Schema ──────────────────────────────────────────
    @abstractmethod
    def input_schema(self) -> type[BaseModel]:
        """
        返回 Pydantic 输入模型类。
        系统通过 model.model_json_schema() 自动生成 JSON Schema，
        传给 LLM 的 tools 列表。
        """

    # ── 启用检查 ──────────────────────────────────────────────
    @abstractmethod
    async def is_enabled(self) -> bool:
        """
        当前环境是否启用此工具。
        例：NotebookTool 在无 Jupyter 环境时返回 False。
        """

    # ── 权限相关 ──────────────────────────────────────────────
    @abstractmethod
    def is_read_only(self, input: Any = None) -> bool:
        """
        操作是否为只读（不修改文件/状态）。
        计划模式（PermissionMode.PLAN）下，非只读工具会被 PermissionEngine 硬拒绝。
        """

    @abstractmethod
    def needs_permissions(self, input: Any = None) -> bool:
        """
        在 default 模式下是否需要用户确认。
        safe_mode=True 时此值应返回 True（触发更严格检查）。
        """

    # ── 并发语义 ──────────────────────────────────────────────
    def is_concurrency_safe(self, input: Any = None) -> bool:
        """
        是否可与其他工具并发执行（默认 False）。
        ToolUseQueue 根据此值决定是否并行或串行执行。
        详见 agent-loop.md § ToolUseQueue。
        """
        return False

    # ── 输入验证 ──────────────────────────────────────────────
    async def validate_input(
        self, input: BaseModel, context: "ToolUseContext | None" = None
    ) -> "ValidationResult":
        """可选的额外输入验证（在 Pydantic 验证之后执行）"""
        return ValidationResult(result=True)

    # ── 执行 ──────────────────────────────────────────────────
    @abstractmethod
    async def call(
        self,
        input: BaseModel,
        context: "ToolUseContext",
    ) -> AsyncGenerator["ToolOutput", None]:
        """
        主执行方法。通过 AsyncGenerator 流式返回：
        - type='progress'：执行中的进度事件（UI 展示用）
        - type='result'  ：最终结果（含 result_for_assistant 字段）
        
        示例：
            async def call(self, input, context):
                yield ToolOutput(type='progress', content='Executing...')
                result = await do_work(input)
                yield ToolOutput(type='result', data=result,
                                 result_for_assistant=str(result))
        """
        yield  # pragma: no cover

    # ── 渲染 ──────────────────────────────────────────────────
    @abstractmethod
    def render_result_for_assistant(self, output: Any) -> str | list:
        """将工具结果序列化为 LLM 可读格式（字符串或内容块列表）"""

    def render_tool_use_message(
        self, input: Any, options: dict | None = None
    ) -> str:
        """工具调用的人类可读摘要（UI 显示用），可覆盖"""
        return f"[{self.name}] {input}"

    # ── Schema 工具方法 ──────────────────────────────────────
    def get_json_schema(self) -> dict:
        """生成 JSON Schema（直接调用 Pydantic model_json_schema()）"""
        return self.input_schema().model_json_schema()
```

### 工具 name alias（别名）

部分工具支持别名（例如 `computer_use` 对应 `bash`）：在 `ToolRegistry` 中维护 `name → tool` 映射时，额外注册别名键。`run_tool_use()` 在查找工具时先按 `name` 查，再按 `aliases` 查。

---

## 工具注册与发现

### ToolRegistry（内存态注册表）

```python
# pode_agent/core/tools/registry.py

class ToolRegistry:
    """
    单例注册表，保存所有已知工具（内置 + 插件 + MCP 包装）。
    
    生命周期：
    - 程序启动时由 ToolLoader 填充
    - 运行期间只读（不支持热插拔，下次启动时重建）
    """

    _tools: dict[str, Tool] = {}    # name → Tool 实例
    _aliases: dict[str, str] = {}   # alias → canonical name

    def register(self, tool: Tool, aliases: list[str] | None = None) -> None:
        """注册工具。name 重复时抛出 ToolRegistryError。"""

    def get(self, name: str) -> Tool | None:
        """按名称或别名查找工具。"""

    def all(self) -> list[Tool]:
        """返回所有已注册工具（不含别名重复项）。"""

    def names(self) -> list[str]:
        """返回所有工具名（含别名）。"""
```

### ToolLoader（加载态）

`ToolLoader` 负责在程序启动时将各类工具加载进 `ToolRegistry`：

```python
# pode_agent/core/tools/loader.py

class ToolLoader:
    """
    工具加载器。按优先级加载：
    1. 内置工具（tools/__init__.py: get_all_tools()）
    2. 插件工具（services/plugins 加载，Phase 5 实现）
    3. MCP 工具（services/mcp 加载，Phase 5 实现）
    """

    def __init__(
        self,
        registry: ToolRegistry,
        config: GlobalConfig,
        mcp_clients: list["WrappedMcpClient"] | None = None,
    ): ...

    async def load_all(self) -> None:
        """
        顺序加载所有工具来源，填充 registry。
        加载顺序决定冲突时的优先级（后加载的覆盖同名内置工具）。
        """

    def _load_builtin_tools(self) -> None:
        """加载 tools/__init__.py: get_all_tools()"""

    async def _load_plugin_tools(self) -> None:
        """加载已安装插件导出的工具（Phase 5）"""

    async def _load_mcp_tools(self) -> None:
        """将 MCP 工具包装为 Pode Tool 并注册（Phase 5）"""
```

### 内置工具列表（`tools/__init__.py`）

```python
# pode_agent/tools/__init__.py

from pode_agent.tools.system.bash import BashTool
from pode_agent.tools.filesystem.file_read import FileReadTool
# ... 其他工具导入

def get_all_tools() -> list[Tool]:
    """
    返回所有内置工具的实例。
    是工具系统的"静态清单"——所有内置工具必须在此注册。
    """
    return [
        BashTool(),
        FileReadTool(),
        FileWriteTool(),
        FileEditTool(),
        GlobTool(),
        MultiEditTool(),
        GrepTool(),
        LspTool(),
        WebFetchTool(),
        WebSearchTool(),
        AskUserQuestionTool(),
        TodoWriteTool(),
        LsTool(),
        NotebookReadTool(),
        NotebookEditTool(),
        KillShellTool(),
        TaskOutputTool(),
        AskExpertModelTool(),
        SkillTool(),
        EnterPlanModeTool(),
        ExitPlanModeTool(),
        TaskTool(),
        SlashCommandTool(),
    ]
```

---

## 工具启用与过滤

### get_enabled_tools()

每次启动 Agent Loop 之前，必须通过 `get_enabled_tools()` 过滤出**本次对话可用的工具列表**：

```python
# pode_agent/core/tools/registry.py（或 loader.py）

async def get_enabled_tools(
    registry: ToolRegistry,
    config: GlobalConfig,
    safe_mode: bool = False,
    permission_mode: PermissionMode = PermissionMode.DEFAULT,
    command_allowed_tools: list[str] | None = None,
) -> list[Tool]:
    """
    根据运行时条件过滤可用工具。
    
    过滤规则（按优先级）：
    1. tool.is_enabled() → False 则排除（环境不满足）
    2. safe_mode=True → 只保留 is_read_only() 为 True 的工具
    3. command_allowed_tools 非空 → 只保留白名单中的工具
    4. permission_mode=PLAN → 只保留 is_read_only() 为 True 的工具
       （写工具会在权限层被硬拒绝，但也可在此预过滤以减少 LLM 混淆）
    5. GlobalConfig.denied_tools → 排除已永久拒绝的工具
    
    Returns:
        过滤后的 Tool 实例列表（用于构建 LLM tools 参数）
    """
    enabled = []
    for tool in registry.all():
        if not await tool.is_enabled():
            continue
        if safe_mode and not tool.is_read_only():
            continue
        if command_allowed_tools and tool.name not in command_allowed_tools:
            continue
        enabled.append(tool)
    return enabled
```

**关键行为**：
- `safe_mode` 和 `permission_mode=PLAN` 都会收缩工具列表，但权限层仍会对漏网的写操作进行二次硬拒绝（见 [§ 权限系统与工具的耦合点](#权限系统与工具的耦合点)）
- MCP 工具和插件工具也通过此函数过滤，无特殊通道

---

## 工具如何注入 Agent Loop

### 注入点

```
app/query.py: query_core()
    │
    ├─ 构建 UnifiedRequestParams.tools = [tool_to_definition(t) for t in enabled_tools]
    │                                     ↑
    │            get_enabled_tools(registry, config, safe_mode, permission_mode)
    │
    └─ AIProvider.query(params) ──→ LLM
```

`query_core()` 在每次递归调用时都会重新传入 `tools` 列表（这允许 plan mode 切换后立即生效）。

### ToolDefinition 结构

```python
class ToolDefinition(BaseModel):
    """传给 LLM 的工具定义（provider 无关格式）"""
    name: str
    description: str
    input_schema: dict    # JSON Schema（来自 tool.get_json_schema()）
```

工具定义的构建：

```python
def tool_to_definition(tool: Tool) -> ToolDefinition:
    return ToolDefinition(
        name=tool.name,
        description=tool.description or "",
        input_schema=tool.get_json_schema(),
    )
```

> 📖 完整的注入流程（包括 LLM 返回 tool_use 后的调度逻辑）详见 [agent-loop.md § 递归式主循环](./agent-loop.md#递归式主循环)。

---

## 工具与 LLM API 的连接

### Pydantic JSON Schema → Provider Tools Schema

每个 Provider 有自己的工具 schema 格式。Pode-Agent 统一使用 `ToolDefinition`（provider 无关），在适配器层转换：

```
Tool.input_schema()  →  model_json_schema()  →  ToolDefinition
     │                                                │
     ▼                                                ▼
Pydantic BaseModel                        AnthropicProvider.query():
                                          将 ToolDefinition 转为
                                          anthropic.types.ToolParam

                                          OpenAIProvider.query():
                                          将 ToolDefinition 转为
                                          openai.types.chat.ChatCompletionToolParam
```

### tool_use → 执行 → tool_result 的完整链路

```
LLM 返回 AssistantMessage（含 tool_use block）
    │
    ├── tool_use.name    ──→ ToolRegistry.get(name)
    ├── tool_use.id      ──→ 贯穿整个执行过程（用于构造 tool_result）
    └── tool_use.input   ──→ Pydantic 验证（tool.input_schema().model_validate()）
                                │
                                ▼
                        check_permissions_and_call_tool()
                                │
                                ▼
                        tool.call(input, context)   ← AsyncGenerator
                                │
                         [progress events]          → UI 进度更新
                                │
                         [result event]
                                │
                                ▼
                        ToolResultMessage {
                            role: "tool",
                            tool_use_id: tool_use.id,   ← 与 tool_use.id 对应
                            content: result_for_assistant,
                        }
                                │
                                ▼
                        追加到 messages，递归调用 query_core()
```

> 📖 `check_permissions_and_call_tool()` 的完整管线（含 Hook 注入点）详见 [agent-loop.md § check_permissions_and_call_tool 完整管线](./agent-loop.md#check_permissions_and_call_tool-完整管线)。

### 事件流（ToolOutput）

工具执行过程中产生两类事件：

| 事件类型 | 字段 | 用途 |
|---------|------|------|
| `progress` | `content: str \| list` | 实时进度（UI 展示：spinner、命令输出） |
| `result` | `data: Any`, `result_for_assistant: str \| list` | 最终结果；`result_for_assistant` 写入 tool_result |

`ToolUseQueue` 将这些事件包装为 `SessionEvent` 向 UI 层 yield；详见 [agent-loop.md § ToolUseQueue](./agent-loop.md#toolUseQueue并发工具调度器)。

---

## 权限系统与工具的耦合点

### 两个耦合层

```
第 1 层（预过滤）：get_enabled_tools()
    safe_mode / permission_mode / command_allowed_tools
    → 过滤出本次对话可见的工具列表（减少 LLM 困惑）

第 2 层（运行时硬拒绝）：PermissionEngine.has_permissions()
    → 每次工具调用前强制检查，无论第 1 层如何
```

### `needs_permissions` vs `is_read_only`

| 方法 | 含义 | 作用时机 |
|------|------|---------|
| `needs_permissions(input)` | 该输入是否需要用户确认 | default 模式下，触发权限询问对话框 |
| `is_read_only(input)` | 是否为纯只读操作 | plan 模式/safe_mode 下，非只读工具被硬拒绝 |

### Plan Mode 硬拒绝（Permission Mode B 策略）

当 `PermissionMode = PLAN` 时，`PermissionEngine` 对非只读工具**直接返回 DENIED**，不询问用户：

```python
# pode_agent/core/permissions/engine.py

async def has_permissions(self, tool_name, input, context) -> PermissionResult:
    tool = registry.get(tool_name)
    
    # 1. bypassPermissions → 无条件允许
    if context.mode == PermissionMode.BYPASS_PERMISSIONS:
        return PermissionResult.ALLOWED
    
    # 2. 会话级拒绝
    if tool_name in context.tool_permission_context.rejected_tools:
        return PermissionResult.DENIED
    
    # 3. 会话级批准
    if tool_name in context.tool_permission_context.approved_tools:
        return PermissionResult.ALLOWED
    
    # 4. 项目级持久化决定
    if tool_name in project_config.denied_tools:
        return PermissionResult.DENIED
    if tool_name in project_config.allowed_tools:
        return PermissionResult.ALLOWED
    
    # 5. ★ Plan Mode 硬拒绝（非只读工具）★
    if context.mode == PermissionMode.PLAN and tool and not tool.is_read_only(input):
        return PermissionResult.DENIED
    
    # 6. 工具特定规则（bash.py / file.py）
    # 7. 默认：NEEDS_PROMPT
    ...
```

> 📖 计划模式下工具权限的完整行为见 [plan-mode.md § 与权限系统的耦合](./plan-mode.md#与-agent-loop-的耦合点)。

### Safe Mode

`safe_mode=True` 时（`--safe` 命令行参数）：
- `get_enabled_tools()` 预过滤非只读工具
- 即使通过了预过滤，`PermissionEngine` 仍会对所有需要权限的工具要求用户确认

### Hook 对工具输入的影响

Pre-Tool Hook 可以在工具执行前**修改或拦截**工具输入：

```python
# services/hooks/runner.py（Phase 5 实现）

hook_result = await run_pre_tool_use_hooks(tool_name, input, hook_state)
if hook_result.type == "block":
    # 返回 tool_result 错误，不执行工具
    return tool_result_error(hook_result.message)
if hook_result.type == "modify":
    input = hook_result.modified_input  # 替换工具输入
```

Hook 系统在 Phase 5 实现；详见 [agent-loop.md § Hook 系统](./agent-loop.md#hook-系统四个注入点)。

---

## 并发语义

### `is_concurrency_safe` 的定义

| 值 | 含义 | 示例工具 |
|----|------|---------|
| `True` | 工具可以与其他工具并发执行 | FileReadTool、GrepTool、WebFetchTool |
| `False`（默认）| 工具必须在所有并发安全工具完成后串行执行 | BashTool、FileWriteTool、FileEditTool |

### barrier 机制

当一批 tool_use 同时到达时，`ToolUseQueue` 按如下策略调度：

```
批次 [tool_A(safe=True), tool_B(safe=True), tool_C(safe=False)]

阶段 1（并发）：tool_A 和 tool_B 并发执行
            ↓ 等待两者都完成（barrier）
阶段 2（串行）：tool_C 单独执行
```

> 📖 `ToolUseQueue` 完整实现规格详见 [agent-loop.md § ToolUseQueue：并发工具调度器](./agent-loop.md#toolUseQueue并发工具调度器)。

---

## 与 MCP/插件系统边界

### 三类工具来源

| 来源 | 加载方式 | 实现阶段 |
|------|---------|---------|
| **内置工具** | `tools/__init__.py: get_all_tools()` | Phase 1-3 |
| **MCP 工具** | `services/mcp/tools.py: wrap_mcp_tool_as_pode_tool()` | Phase 5 |
| **插件工具** | `services/plugins/runtime.py`（via entry_points） | Phase 5 |

### MCP 工具包装

MCP 工具通过 `wrap_mcp_tool_as_pode_tool()` 适配为 `Tool` ABC，对 Agent Loop 透明：

```python
def wrap_mcp_tool_as_pode_tool(
    client: WrappedMcpClient,
    mcp_tool: McpToolDefinition,
) -> Tool:
    """
    生成一个动态 Tool 子类：
    - name = mcp_tool.name
    - input_schema() 返回从 mcp_tool.inputSchema 构建的 Pydantic 模型
    - call() 调用 client.session.call_tool()
    - is_read_only() 默认 False（MCP 工具权限需保守处理）
    - needs_permissions() 默认 True
    """
```

### 插件工具（Phase 5）

通过 Python entry_points 机制实现插件工具自动发现：

```toml
# 插件包的 pyproject.toml
[project.entry-points."pode_agent.tools"]
my_tool = "my_package.tools:MyTool"
```

`ToolLoader._load_plugin_tools()` 在启动时扫描所有已安装包的 `pode_agent.tools` entry_points，自动注册。

---

## 分阶段实现建议

| 子功能 | 实现阶段 | 说明 |
|--------|---------|------|
| Tool ABC（`core/tools/base.py`） | Phase 0（✅ 已完成） | 抽象基类，不含具体工具 |
| ToolRegistry 基础实现 | Phase 0（✅ 已完成） | 内存态 name → tool 映射 |
| `get_all_tools()` 骨架 | Phase 0（✅ 已完成） | 空列表或仅含 BashTool |
| BashTool、FileReadTool、FileWriteTool、FileEditTool、GlobTool | Phase 1 | 核心工具 |
| GrepTool、LsTool | Phase 1 | 核心工具 |
| ToolLoader 基础（仅内置） | Phase 1 | 只加载内置工具 |
| `get_enabled_tools()`（safe_mode 过滤） | Phase 1 | 与权限系统配合 |
| 工具与 LLM API 的连接（ToolDefinition、适配器转换） | Phase 2 | 需要 AI 适配器就位 |
| ToolUseQueue（串行版） | Phase 2 | Agent Loop 基础 |
| ToolUseQueue（并发版，`is_concurrency_safe`） | Phase 3 | 性能提升 |
| Plan Mode 工具预过滤（`permission_mode=PLAN`） | Phase 3 | 与 EnterPlanModeTool 配合 |
| EnterPlanModeTool / ExitPlanModeTool | Phase 3 | 详见 [plan-mode.md](./plan-mode.md) |
| 全部 25+ 内置工具 | Phase 3 | 完整工具集 |
| MCP 工具包装 | Phase 5 | 需要 MCP 客户端就位 |
| 插件工具 entry_points | Phase 5 | 需要插件系统就位 |
| Hook 系统（Pre/Post-Tool Hook） | Phase 5 | 详见 [agent-loop.md](./agent-loop.md) |

---

## 映射表：Kode-Agent → Pode-Agent

| Kode-Agent（TypeScript）概念/路径 | Pode-Agent（Python）计划模块/文件 |
|----------------------------------|----------------------------------|
| `src/tools/*.ts`（各工具文件） | `pode_agent/tools/<domain>/<tool>.py` |
| `Tool` 接口（`name/description/input_schema/call`） | `pode_agent/core/tools/base.Tool`（ABC） |
| `isConcurrencySafe` 属性 | `Tool.is_concurrency_safe()` 方法 |
| `isReadOnly` 属性 | `Tool.is_read_only()` 方法 |
| `needsPermissions` 方法 | `Tool.needs_permissions()` 方法 |
| `renderResultForAssistant()` | `Tool.render_result_for_assistant()` |
| Zod schema（`inputSchema`） | Pydantic BaseModel + `model_json_schema()` |
| `toolUseContext.options.tools` | `get_enabled_tools()` 的返回值 |
| 工具动态发现（entry-points） | `project.entry-points."pode_agent.tools"` |
| `ToolRegistry`（内存态） | `pode_agent/core/tools/registry.ToolRegistry` |
| 工具并发调度（`ToolUseQueue`） | `pode_agent/app/query.ToolUseQueue` |
| `checkPermissionsAndCallTool()` | `pode_agent/app/query.check_permissions_and_call_tool()` |
| MCP 工具包装（`MCPTool`） | `pode_agent/services/mcp/tools.wrap_mcp_tool_as_pode_tool()` |
| `EnterPlanMode` / `ExitPlanMode` 工具 | `pode_agent/tools/agent/plan_mode.py` |
| `src/tools/index.ts`（工具总清单） | `pode_agent/tools/__init__.py: get_all_tools()` |
