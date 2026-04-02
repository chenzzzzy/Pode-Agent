# Pode-Agent 模块规范

> 版本：1.0.0 | 状态：草稿 | 更新：2026-03-31  
> 本文档为每个模块定义职责边界、公共接口和内部结构。

---

## 目录

1. [Core 层模块](#core-层模块)
   - [config](#config-模块)
   - [permissions](#permissions-模块)
   - [tools/base](#toolsbase-模块)
   - [cost_tracker](#cost_tracker-模块)
2. [Services 层模块](#services-层模块)
   - [services/ai](#servicesai-模块)
   - [services/mcp](#servicesmcp-模块)
   - [services/context](#servicescontext-模块)
   - [services/auth](#servicesauth-模块)
   - [services/plugins](#servicesplugins-模块)
   - [services/system](#servicessystem-模块)
3. [Tools 层模块](#tools-层模块)
4. [App 层模块](#app-层模块)
5. [UI 层模块](#ui-层模块)
6. [Entrypoints 层模块](#entrypoints-层模块)
7. [Types（数据模型）](#types数据模型)

---

## Core 层模块

### `config` 模块

**职责**：管理全局配置（`~/.pode/config.json`）和项目配置（`.pode.json`、`.mcprc`）的读取、写入、验证和迁移。

**文件结构**：
```
pode_agent/core/config/
├── __init__.py        # 公共 API 导出
├── schema.py          # Pydantic 数据模型
├── loader.py          # 读写 JSON 文件
├── defaults.py        # 默认值常量
└── migrations.py      # 版本迁移逻辑
```

**公共 API**：

```python
# pode_agent/core/config/__init__.py

def get_global_config() -> GlobalConfig:
    """读取 ~/.pode/config.json，不存在则返回默认值"""

def save_global_config(config: GlobalConfig) -> None:
    """原子写入 ~/.pode/config.json"""

def get_current_project_config() -> ProjectConfig:
    """读取当前工作目录的项目配置，向上查找到 git 根目录"""

def save_current_project_config(config: ProjectConfig) -> None:
    """写入当前项目配置"""

def get_project_mcp_server_definitions() -> dict[str, McpServerConfig]:
    """合并读取 .mcp.json 和 .mcprc 中的 MCP 服务器配置"""

def get_config_for_cli(key: str, global_: bool = True) -> Any:
    """CLI 命令用：获取单个配置值"""

def set_config_for_cli(key: str, value: Any, global_: bool = True) -> None:
    """CLI 命令用：设置单个配置值"""

def list_config_for_cli(global_: bool = True) -> dict[str, Any]:
    """CLI 命令用：列出所有配置"""
```

**数据模型（`schema.py`）**：

```python
from pydantic import BaseModel, Field
from typing import Literal

class ModelProfile(BaseModel):
    name: str
    provider: ProviderType
    model_name: str
    base_url: str | None = None
    api_key: str = ""
    max_tokens: int = 8192
    context_length: int = 200000
    reasoning_effort: Literal["low", "medium", "high", "minimal"] | None = None
    is_active: bool = True

class ModelPointers(BaseModel):
    main: str = "claude-3-5-sonnet-20241022"
    task: str = "claude-3-5-haiku-20241022"
    compact: str = "claude-3-5-haiku-20241022"
    quick: str = "claude-3-5-haiku-20241022"

class GlobalConfig(BaseModel):
    model_config = {"extra": "allow"}  # 向前兼容
    
    num_startups: int = 0
    theme: Literal["dark", "light"] = "dark"
    verbose: bool = False
    has_completed_onboarding: bool = False
    default_model_name: str = "claude-3-5-sonnet-20241022"
    max_tokens: int | None = None
    auto_compact_threshold: int = 50
    primary_provider: ProviderType | None = None
    model_profiles: list[ModelProfile] = Field(default_factory=list)
    model_pointers: ModelPointers = Field(default_factory=ModelPointers)
    mcp_servers: dict[str, McpServerConfig] = Field(default_factory=dict)
    proxy: str | None = None
    stream: bool = True
    oauth_account: AccountInfo | None = None
    custom_api_key_responses: CustomApiKeyResponses | None = None

class ProjectConfig(BaseModel):
    model_config = {"extra": "allow"}
    
    allowed_tools: list[str] = Field(default_factory=list)
    denied_tools: list[str] = Field(default_factory=list)
    asked_tools: list[str] = Field(default_factory=list)
    context: dict[str, str] = Field(default_factory=dict)
    history: list[str] = Field(default_factory=list)
    dont_crawl_directory: bool = False
    enable_architect_tool: bool = False
    mcp_servers: dict[str, McpServerConfig] = Field(default_factory=dict)
    last_cost: float | None = None
    last_duration: int | None = None

class McpServerConfig(BaseModel):
    type: Literal["stdio", "sse", "http", "ws", "sse-ide", "ws-ide"]
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    url: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
```

**内部实现要点**：
- 配置文件路径：`~/.pode/config.json`（参考 `PODE_CONFIG_DIR` 环境变量）
- 原子写入：先写临时文件，再 `os.replace()`
- 版本迁移：读取 `__version__` 字段，逐版本应用 migration functions
- 错误处理：文件损坏时回退到默认值，打印警告

---

### `permissions` 模块

**职责**：判断工具是否有权限执行，管理权限存储，定义各工具的安全规则。

> 📖 **权限系统与工具的耦合点**（plan mode 硬拒绝、safe_mode 过滤、Hook 对输入的影响）详见 [tools-system.md § 权限系统与工具的耦合点](./tools-system.md#权限系统与工具的耦合点)。  
> 📖 **Plan Mode 中 PermissionMode 的传播路径**详见 [plan-mode.md § 与 Agent Loop 的耦合点](./plan-mode.md#与-agent-loop-的耦合点)。

**文件结构**：
```
pode_agent/core/permissions/
├── __init__.py        # 公共 API：has_permissions, persist_permission
├── engine.py          # 权限检查主逻辑
├── rules/
│   ├── bash.py        # Bash 命令安全规则（allowlist/denylist）
│   ├── file.py        # 文件路径安全规则
│   ├── plan_mode.py   # 计划模式允许工具列表
│   └── mcp.py         # MCP 工具权限规则
└── store.py           # 权限持久化（写入 ProjectConfig）
```

**公共 API**：

```python
class PermissionEngine:
    async def has_permissions(
        self,
        tool_name: str,
        input: dict,
        context: PermissionContext,
    ) -> PermissionResult:
        """
        检查工具是否有权限执行。
        
        Returns:
            PermissionResult.ALLOWED       - 直接允许，无需提示
            PermissionResult.NEEDS_PROMPT  - 需要用户确认
            PermissionResult.DENIED        - 拒绝执行
        """

    async def persist_permission_update(
        self,
        tool_name: str,
        input: dict,
        decision: PermissionDecision,  # ALLOW_ONCE | ALLOW_ALL | DENY
        context: PermissionContext,
    ) -> None:
        """保存用户的权限决定到磁盘"""

    def apply_permission_context_update(
        self,
        tool_name: str,
        decision: PermissionDecision,
        permission_context: ToolPermissionContext,
    ) -> ToolPermissionContext:
        """将权限决定应用到当前会话的权限上下文"""
```

**权限模式（PermissionMode）**：

```python
class PermissionMode(str, Enum):
    DEFAULT = "default"                  # 正常询问
    ACCEPT_EDITS = "acceptEdits"         # 自动接受文件编辑
    PLAN = "plan"                        # 计划模式（只读工具）
    BYPASS_PERMISSIONS = "bypassPermissions"  # 跳过所有权限检查
    DONT_ASK = "dontAsk"                 # 从不询问，拒绝危险操作
    DELEGATE = "delegate"                # 委托给其他工具
```

**Bash 规则（`rules/bash.py`）**：

```python
SAFE_BASH_COMMANDS = frozenset([
    "cat", "ls", "pwd", "echo", "date", "find",
    "grep", "head", "tail", "wc", "sort", "uniq",
    "which", "type", "env", "printenv",
    "git status", "git log", "git diff",
    # ... 更多只读命令
])

DANGEROUS_BASH_PATTERNS = [
    r"rm\s+(-[rRf]*\s+)*[^-]",    # rm
    r">\s*[^>]",                    # 输出重定向（覆盖）
    r"sudo\s+",                     # sudo
    r"curl.*\|.*sh",                # curl piped to sh
    r"eval\s+",                     # eval
    # ...
]

def is_safe_bash_command(command: str) -> bool:
    """判断 Bash 命令是否安全（不需要权限）"""
```

---

### `tools/base` 模块

**职责**：定义工具系统的抽象基类、数据类型和工具注册表。

> 📖 **工具系统完整设计**（存储组织、ToolRegistry/ToolLoader、get_enabled_tools、与 LLM 的连接、权限耦合、并发语义、MCP/插件边界）详见 [tools-system.md](./tools-system.md)。  
> 本节仅展示 `core/tools/` 下的接口定义；工具具体实现在 `pode_agent/tools/` 中。

**文件结构**：
```
pode_agent/core/tools/
├── __init__.py
├── base.py        # Tool ABC, ToolOutput, ToolUseContext
├── registry.py    # ToolRegistry: 注册/查找工具
└── executor.py    # collect_tool_result: 消费 AsyncGenerator
```

**核心类型（`base.py`）**：

```python
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Any, Literal, TYPE_CHECKING
from pydantic import BaseModel
import asyncio

class ToolOutput(BaseModel):
    """工具调用产生的单个输出项"""
    type: Literal["result", "progress"]
    # 进度类型字段
    content: Any = None
    normalized_messages: list | None = None
    tools: list | None = None
    # 结果类型字段
    data: Any = None
    result_for_assistant: str | list | None = None
    new_messages: list | None = None
    is_error: bool = False
    context_modifier: Any = None  # ContextModifier | None（见 skill-system.md）

class ToolOptions(BaseModel):
    commands: list | None = None
    tools: list | None = None
    verbose: bool = False
    slow_and_capable_model: str | None = None
    safe_mode: bool = False
    permission_mode: "PermissionMode | None" = None
    tool_permission_context: "ToolPermissionContext | None" = None
    last_user_prompt: str | None = None
    fork_number: int = 0
    message_log_name: str | None = None
    max_thinking_tokens: int | None = None
    model: str | None = None
    command_allowed_tools: list[str] | None = None
    mcp_clients: list | None = None

class ToolUseContext(BaseModel):
    """工具调用时的运行上下文"""
    message_id: str | None
    tool_use_id: str | None = None
    agent_id: str | None = None
    safe_mode: bool = False
    abort_event: asyncio.Event = None  # 中止信号
    read_file_timestamps: dict[str, float] = {}
    options: ToolOptions = ToolOptions()

    class Config:
        arbitrary_types_allowed = True  # 允许 asyncio.Event

class ValidationResult(BaseModel):
    result: bool
    message: str | None = None

class Tool(ABC):
    """所有工具的抽象基类"""
    
    name: str                          # 工具标识符（唯一）
    description: str | None = None     # 工具描述（给 LLM 看）
    cached_description: str | None = None

    @abstractmethod
    def input_schema(self) -> type[BaseModel]:
        """返回 Pydantic 输入模型类（自动生成 JSON Schema）"""
        ...

    @abstractmethod
    async def is_enabled(self) -> bool:
        """是否在当前环境启用"""
        ...

    @abstractmethod
    def is_read_only(self, input: Any = None) -> bool:
        """是否为只读操作（计划模式用）"""
        ...

    def is_concurrency_safe(self, input: Any = None) -> bool:
        """是否可并发执行（默认 False）"""
        return False

    @abstractmethod
    def needs_permissions(self, input: Any = None) -> bool:
        """是否需要用户权限确认"""
        ...

    async def validate_input(
        self, input: BaseModel, context: ToolUseContext | None = None
    ) -> ValidationResult:
        """可选的额外输入验证（默认通过）"""
        return ValidationResult(result=True)

    @abstractmethod
    def render_result_for_assistant(self, output: Any) -> str | list:
        """将工具结果格式化为 LLM 可读格式"""
        ...

    def render_tool_use_message(
        self, input: Any, options: dict | None = None
    ) -> str:
        """返回工具调用的人类可读描述（用于 UI 显示）"""
        return f"[{self.name}] {input}"

    @abstractmethod
    async def call(
        self,
        input: BaseModel,
        context: ToolUseContext,
    ) -> AsyncGenerator[ToolOutput, None]:
        """
        主执行方法。
        通过 AsyncGenerator 流式返回进度（type='progress'）和最终结果（type='result'）。
        
        实现示例:
            async def call(self, input, context):
                yield ToolOutput(type='progress', content='Starting...')
                result = await do_work(input)
                yield ToolOutput(type='result', data=result)
        """
        yield  # type: ignore  # pragma: no cover

    def get_json_schema(self) -> dict:
        """生成 JSON Schema（用于 LLM tool calling）"""
        return self.input_schema().model_json_schema()
```

**工具执行器（`executor.py`）**：

```python
async def collect_tool_result(
    tool: Tool,
    input: BaseModel,
    context: ToolUseContext,
    on_progress: Callable[[ToolOutput], None] | None = None,
) -> ToolResult:
    """
    消费工具的 AsyncGenerator，收集最终结果。
    
    Args:
        tool: 要执行的工具
        input: 验证后的输入
        context: 执行上下文
        on_progress: 进度回调（UI 更新用）
    
    Returns:
        ToolResult with data, result_for_assistant, new_messages
    """
    async for output in tool.call(input, context):
        if output.type == 'progress':
            if on_progress:
                on_progress(output)
        elif output.type == 'result':
            return ToolResult(
                data=output.data,
                result_for_assistant=output.result_for_assistant,
                new_messages=output.new_messages or [],
            )
    
    raise ToolError(f"Tool {tool.name} did not yield a result")
```

---

### `cost_tracker` 模块

**职责**：追踪单次会话的 LLM 费用。

```python
# pode_agent/core/cost_tracker.py

_total_cost_usd: float = 0.0

def add_to_total_cost(cost_usd: float) -> None:
    global _total_cost_usd
    _total_cost_usd += cost_usd

def get_total_cost() -> float:
    return _total_cost_usd

def reset_cost() -> None:
    global _total_cost_usd
    _total_cost_usd = 0.0
```

---

## Services 层模块

### `services/ai` 模块

**职责**：LLM 的所有集成逻辑，包括 Provider 适配器、模型管理、响应状态追踪。

**文件结构**：
```
pode_agent/services/ai/
├── __init__.py
├── base.py             # AIProvider ABC, UnifiedRequestParams, AIResponse
├── anthropic.py        # Anthropic Claude 适配器
├── openai.py           # OpenAI/GPT 适配器
├── factory.py          # ModelAdapterFactory：根据模型名选 Provider
├── response_state.py   # 响应状态管理（prevResponseId, conversationId）
└── custom_providers.py # 自定义 Provider（Mistral、Ollama 等）
```

**公共 API**：

```python
class AIProvider(ABC):
    @abstractmethod
    async def query(
        self, params: UnifiedRequestParams
    ) -> AsyncGenerator["AIResponse", None]:
        """流式查询，yield AIResponse 对象"""
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
    metadata: dict | None = None
    
class AIResponse(BaseModel):
    type: Literal["text_delta", "tool_use_start", "tool_use_delta",
                  "tool_use_end", "message_done", "error"]
    # text_delta
    text: str | None = None
    # tool_use_start / end
    tool_use_id: str | None = None
    tool_name: str | None = None
    tool_input: dict | None = None
    # message_done
    usage: TokenUsage | None = None
    cost_usd: float | None = None
    stop_reason: str | None = None

class ModelAdapterFactory:
    @staticmethod
    def get_provider(model_name: str) -> AIProvider:
        """根据模型名返回对应的 Provider 实例"""

    @staticmethod
    def get_capabilities(model_name: str) -> ModelCapabilities:
        """返回模型的能力（最大 token、是否支持 thinking 等）"""

async def query_llm(params: UnifiedRequestParams) -> AsyncGenerator[AIResponse, None]:
    """顶层函数：自动选择 Provider 并查询"""
    provider = ModelAdapterFactory.get_provider(params.model)
    async for response in provider.query(params):
        yield response
```

**Anthropic 适配器要点**：
- 使用官方 `anthropic.AsyncAnthropic` 客户端
- 支持 Bedrock（`anthropic.AsyncAnthropicBedrock`）和 Vertex AI（`anthropic.AsyncAnthropicVertex`）
- 处理 `extended_thinking` 参数（o1 style）
- 将 Anthropic 的 SSE 流映射到 `AIResponse` 对象

**OpenAI 适配器要点**：
- 使用官方 `openai.AsyncOpenAI` 客户端
- 支持代理（`httpx_client` 参数）
- 处理 `reasoning_effort` 参数（GPT-5 系列）
- 将 OpenAI Chat Completions 流映射到 `AIResponse` 对象

---

### `services/mcp` 模块

**职责**：MCP 客户端逻辑，包括连接管理、工具发现和资源读取。

**文件结构**：
```
pode_agent/services/mcp/
├── __init__.py
├── client.py           # MCP 客户端，连接各类型服务器
├── discovery.py        # 发现并读取 MCP 服务器配置
├── tools.py            # 将 MCP 工具/资源包装为 Pode Tool
└── types.py            # WrappedMcpClient, McpToolDefinition
```

**公共 API**：

```python
class WrappedMcpClient:
    name: str
    client: ClientSession
    tools: list[McpToolDefinition]
    resources: list[McpResourceDefinition]

async def connect_to_server(
    name: str,
    config: McpServerConfig,
) -> WrappedMcpClient:
    """连接到 MCP 服务器并返回封装的客户端"""

async def connect_all_servers(
    server_configs: dict[str, McpServerConfig],
) -> list[WrappedMcpClient]:
    """并发连接所有配置的 MCP 服务器"""

def wrap_mcp_tool_as_pode_tool(
    client: WrappedMcpClient,
    mcp_tool: McpToolDefinition,
) -> Tool:
    """将 MCP 工具定义包装为 Pode Tool"""
```

---

### `services/context` 模块

**职责**：生成项目感知的上下文（system prompt 的一部分），处理 @mention。

**公共 API**：

```python
async def get_project_context(cwd: str) -> dict[str, str]:
    """
    收集项目上下文：
    - git 状态
    - 目录结构（如未禁用）
    - README.md
    - AGENTS.md / CLAUDE.md 等指令文件
    - 自定义 context（来自 ProjectConfig.context）
    
    返回 key-value 字典（key 作为标题，value 作为内容）
    """

async def process_mentions(
    user_input: str,
    cwd: str,
) -> tuple[str, list[FileContent]]:
    """
    解析 @mention 语法。
    返回：(处理后的 prompt, 提取的文件内容列表)
    """
```

---

### `services/auth` 模块

**职责**：OAuth 认证流程管理。

```python
async def start_oauth_flow() -> AccountInfo:
    """启动 OAuth 认证，打开浏览器，等待回调，返回账户信息"""

async def refresh_token(account: AccountInfo) -> AccountInfo:
    """刷新 OAuth 令牌"""

def logout() -> None:
    """清除存储的凭据"""

def get_current_account() -> AccountInfo | None:
    """获取当前登录的账户"""
```

---

### `services/plugins` 模块

**职责**：自定义命令/技能发现与加载、Skill Marketplace 管理、Plugin 运行时、插件验证。

> 📖 **完整设计规格**：[skill-system.md](./skill-system.md) — 技能发现、YAML frontmatter、contextModifier、Marketplace、Plugin 架构。

**文件结构**：
```
pode_agent/services/plugins/
├── __init__.py
├── commands.py         # 自定义命令/技能发现与加载（8 目录扫描 + 去重）
├── marketplace.py      # Skill Marketplace（安装/卸载/启用/禁用）
├── runtime.py          # Plugin 运行时（plugin.json 解析 + Session 管理）
├── validation.py       # Plugin/Marketplace/技能目录 schema 校验
└── session.py          # 会话插件状态管理
```

**公共 API**：

```python
# commands.py
async def load_custom_commands() -> list[CustomCommandWithScope]:
    """扫描所有标准目录，返回去重后的命令/技能列表"""
def reload_custom_commands() -> None:
    """手动失效缓存，下次调用时重新扫描"""
def parse_frontmatter(content: str) -> tuple[dict, str]:
    """解析 Markdown 文件的 YAML frontmatter，返回 (frontmatter_dict, body)"""

# marketplace.py
async def install_skill_plugin(source: MarketplaceSource) -> str:
    """安装 Skill Plugin，返回插件 ID"""
async def uninstall_skill_plugin(plugin_id: str) -> None:
    """卸载已安装的插件"""
async def list_installed_plugins() -> list[InstalledPlugin]:
    """列出已安装的插件"""

# runtime.py
async def configure_session_plugins(config: GlobalConfig) -> list[SessionPlugin]:
    """加载所有 Plugin 配置到 Session"""
async def load_plugin_from_dir(plugin_dir: Path) -> PluginManifest:
    """从目录加载 Plugin 清单"""

# validation.py
def validate_plugin_json(data: dict) -> list[str]:
    """校验 plugin.json schema，返回错误列表"""
def validate_marketplace_json(data: dict) -> list[str]:
    """校验 marketplace.json schema，返回错误列表"""
def validate_skill_dir(skill_dir: Path) -> list[str]:
    """校验技能目录结构，返回错误列表"""
```

**自定义命令 YAML 格式**（兼容 Kode-Agent）：

```yaml
---
description: 运行测试并显示结果
category: development
---
运行以下命令并分析结果：

!`npm test`

项目结构：
@package.json
```

**Marketplace 安装来源**：
- `{"source": "github", "repo": "owner/repo", "ref": "main", "path": "skills/"}`
- `{"source": "git", "url": "https://github.com/...", "ref": "main"}`
- `{"source": "url", "url": "https://example.com/skills.zip"}`
- `{"source": "pip", "package": "pode-skills-python"}`
- `{"source": "directory", "path": "/local/path"}`

---

### `services/system` 模块

**职责**：文件修改追踪、系统提示构建、提醒事件。

```python
# file_freshness.py
class FileFreshnessTracker:
    def mark_read(self, path: str) -> None: ...
    def is_stale(self, path: str) -> bool: ...
    def get_stale_files(self) -> list[str]: ...

# system_prompt.py
async def build_system_prompt(
    context: dict[str, str],
    tools: list[Tool],
    options: SystemPromptOptions,
) -> str:
    """构建完整的 system prompt（包含工具描述、项目上下文等）"""
```

### `services/agents` 模块

**职责**：SubAgent（子代理）系统的配置加载、上下文隔离、后台任务管理和 Transcript 存储。

> 📖 **完整设计规格**详见 [subagent-system.md](./subagent-system.md)。

**文件结构**（Phase 5 新建）：
```
pode_agent/services/agents/
├── __init__.py
├── loader.py              # AgentConfig 多源发现 + 优先级合并
├── storage.py             # Markdown + YAML frontmatter 解析、文件管理
├── transcripts.py         # Transcript 内存存储（dict）
├── background_tasks.py    # 后台 Agent 任务管理（注册/更新/等待/快照）
└── fork_context.py        # ForkContext 构建（从 JSONL 读取父消息）
```

---

## Tools 层模块

> 📖 **工具系统完整设计**（目录结构、ToolRegistry/ToolLoader、`get_enabled_tools()`、与 LLM 的连接、权限耦合、并发语义、MCP/插件边界、映射表）详见 [tools-system.md](./tools-system.md)。

每个 Tool 文件遵循统一结构：

```python
# 示例：pode_agent/tools/system/bash.py

from pydantic import BaseModel, Field
from pode_agent.core.tools.base import Tool, ToolOutput, ToolUseContext
from pode_agent.core.permissions.rules.bash import is_safe_bash_command

class BashInput(BaseModel):
    command: str = Field(description="The bash command to execute")
    timeout: int | None = Field(
        default=120000,
        description="Timeout in milliseconds"
    )
    description: str | None = Field(
        default=None,
        description="What this command does (for user display)"
    )

class BashTool(Tool):
    name = "bash"
    description = "Execute bash commands..."

    def input_schema(self) -> type[BaseModel]:
        return BashInput

    async def is_enabled(self) -> bool:
        return True

    def is_read_only(self, input: BashInput | None = None) -> bool:
        return False

    def needs_permissions(self, input: BashInput | None = None) -> bool:
        if input is None:
            return True
        return not is_safe_bash_command(input.command)

    def render_result_for_assistant(self, output: dict) -> str:
        stdout = output.get("stdout", "")
        stderr = output.get("stderr", "")
        exit_code = output.get("exit_code", 0)
        result = f"Exit code: {exit_code}\n"
        if stdout:
            result += f"Stdout:\n{stdout}\n"
        if stderr:
            result += f"Stderr:\n{stderr}\n"
        return result

    async def call(
        self,
        input: BashInput,
        context: ToolUseContext,
    ):
        yield ToolOutput(type="progress", content=f"Running: {input.command}")
        
        proc = await asyncio.create_subprocess_shell(
            input.command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=(input.timeout or 120000) / 1000,
            )
        except asyncio.TimeoutError:
            proc.kill()
            yield ToolOutput(
                type="result",
                data={"error": "Command timed out", "exit_code": -1}
            )
            return
        
        yield ToolOutput(
            type="result",
            data={
                "stdout": stdout.decode(),
                "stderr": stderr.decode(),
                "exit_code": proc.returncode,
            }
        )
```

**工具注册（`tools/__init__.py`）**：

```python
def get_all_tools() -> list[Tool]:
    """返回所有启用的工具列表"""
    tools = [
        # System
        BashTool(),
        KillShellTool(),
        TaskOutputTool(),
        # Filesystem
        FileReadTool(),
        FileWriteTool(),
        FileEditTool(),
        GlobTool(),
        MultiEditTool(),
        NotebookReadTool(),
        NotebookEditTool(),
        # Search
        GrepTool(),
        LspTool(),
        # Network
        WebFetchTool(),
        WebSearchTool(),
        # Interaction
        AskUserQuestionTool(),
        SlashCommandTool(),
        TodoWriteTool(),
        # AI
        AskExpertModelTool(),
        SkillTool(),
        # Agent
        EnterPlanModeTool(),
        ExitPlanModeTool(),
        TaskTool(),
        LsTool(),
    ]
    
    # 过滤未启用的工具（异步检查）
    return tools  # 调用方需 await tool.is_enabled()
```

---

## App 层模块

### `app/session.py`

**职责**：单次对话的完整生命周期管理，包括消息历史、工具调用编排、日志持久化。

> 📖 **`process_input()` 内部调用的核心 Agentic Loop（递归主循环、`ToolUseQueue`、Hook 系统、Auto-compact）详见** [agent-loop.md](./agent-loop.md)。  
> 📖 **计划模式的 JSONL 事件写入（`plan_created`/`plan_approved` 等）详见** [plan-mode.md § 存储方案 A](./plan-mode.md#存储方案-a写入-session-jsonl)。  
> `session.py` 负责会话状态和 JSONL 持久化；循环引擎本身位于 `app/query.py`。

```python
class SessionManager:
    """管理一次完整的对话会话"""

    def __init__(
        self,
        tools: list[Tool],
        commands: list[Command],
        message_log_name: str,
        initial_messages: list[Message] | None = None,
        permission_mode: PermissionMode = PermissionMode.DEFAULT,
        verbose: bool = False,
    ):
        self.messages: list[Message] = initial_messages or []
        self.tools = tools
        self.commands = commands
        self.log_file = self._open_log(message_log_name)
        self.permission_context = ToolPermissionContext()
        self.cost_summary = CostSummary()
        self._abort_event = asyncio.Event()
        self.permission_engine: PermissionEngine = PermissionEngine()
        self.hook_state: HookState = HookState()
        self.current_message_id: str | None = None

    async def process_input(
        self,
        prompt: str,
    ) -> AsyncGenerator[SessionEvent, None]:
        """
        处理用户输入的完整流程：
        1. 处理 @mention
        2. 委托给 app/query.py: query() → query_core()（递归 Agentic Loop）
        3. 保存消息到 JSONL 日志
        
        通过 AsyncGenerator yield 各种 SessionEvent 给 UI。
        核心循环的设计规格见 docs/agent-loop.md。
        """

    def abort(self) -> None:
        """中断当前进行中的操作"""
        self._abort_event.set()

    def save_message(self, message: Message) -> None:
        """追加消息到 JSONL 日志"""

class SessionEvent(BaseModel):
    """Session 向 UI 发送的事件"""
    type: Literal[
        "user_message",
        "assistant_delta",        # 流式文本
        "tool_use_start",
        "tool_progress",
        "tool_result",
        "permission_request",
        "cost_update",
        "error",
        "done",
    ]
    data: Any = None
```

---

### `app/query.py`

**职责**：Agentic Loop 核心引擎 —— `query()`、`query_core()`、`ToolUseQueue`、`check_permissions_and_call_tool()`。

> 📖 **本模块的完整设计规格（递归主循环、并发调度、Hook 注入、Auto-compact、Stop Hook 重入）详见** [agent-loop.md](./agent-loop.md)。

```python
# 核心入口（由 SessionManager.process_input 调用）
async def query(
    prompt: str,
    messages: list[Message],
    tools: list[Tool],
    session: "SessionManager",
    options: QueryOptions,
    system_prompt: str,
) -> AsyncGenerator[SessionEvent, None]:
    """Agentic Loop 外层入口，负责初始消息构建，内部委托 query_core()"""

# 递归主循环
async def query_core(
    messages: list[Message],
    system_prompt: str,
    tools: list[Tool],
    session: "SessionManager",
    options: QueryOptions,
    hook_state: HookState,
    stop_hook_attempts: int = 0,
) -> AsyncGenerator[SessionEvent, None]:
    """
    递归式 Agentic Loop：
      auto_compact → build_system_prompt → query_llm
      → (无 tool_use) run_stop_hooks → 终止或重入
      → (有 tool_use) ToolUseQueue → 递归 query_core
    """

# 并发工具调度器
class ToolUseQueue:
    """按 is_concurrency_safe 分批调度工具调用"""
    async def run(self) -> AsyncGenerator[SessionEvent, None]: ...

# 单工具完整管线
async def check_permissions_and_call_tool(
    tool_use: ToolUseBlock,
    tools: list[Tool],
    session: "SessionManager",
    options: QueryOptions,
    abort_event: asyncio.Event,
) -> AsyncGenerator[SessionEvent, None]:
    """Pre-hook → Pydantic 验证 → 权限检查 → tool.call() → Post-hook"""
```

---

### `app/compact.py`

**职责**：自动上下文压缩（Auto-compact），在消息历史超过阈值时调用 LLM 生成摘要。

> 📖 **触发条件、压缩策略和在循环中的位置详见** [agent-loop.md — Auto-compact](./agent-loop.md#auto-compact自动上下文压缩)。

```python
AUTO_COMPACT_THRESHOLD_MESSAGES = 50
AUTO_COMPACT_THRESHOLD_TOKENS = 180_000

async def auto_compact_if_needed(
    messages: list[Message],
    options: QueryOptions,
) -> list[Message]:
    """检查并按需压缩消息历史，返回（可能已压缩的）消息列表"""
```

---

### `app/print_mode.py`

**职责**：非交互（print）模式的运行逻辑（与 REPL 共享 SessionManager，但输出到 stdout）。

```python
async def run_print_mode(
    prompt: str,
    tools: list[Tool],
    commands: list[Command],
    options: PrintModeOptions,
) -> int:
    """
    非交互模式：执行单次查询并打印结果。
    返回退出码（0=成功，1=错误）。
    """
```

---

## UI 层模块

> UI 层使用 **React + Ink (TypeScript)** 实现，通过 JSON-RPC over stdio 与 Python 后端通信。

### `src/ui/index.tsx`（Ink 入口）

```typescript
// src/ui/index.tsx — Ink render 入口
import { render } from "ink";
import REPL from "./screens/REPL";

// 通过 JSON-RPC over stdio 与 Python 后端通信
const rpcClient = new JsonRpcClient(process.stdin, process.stdout);

render(<REPL rpcClient={rpcClient} />, { exitOnCtrlC: false });
```

### `src/ui/screens/REPL.tsx`（主 REPL 界面）

React 函数式组件（约 779 行），包含完整的状态管理：消息列表、加载状态、中止请求、工具确认、二选一反馈、费用阈值对话框。

渲染组件树：Logo + Static messages、transient messages、PromptInput、PermissionRequest、BinaryFeedback、CostThresholdDialog、MessageSelector。

通过 `PermissionProvider` Context 管理权限状态。

```typescript
// src/ui/screens/REPL.tsx — 核心结构示意
const REPL: React.FC<{ rpcClient: JsonRpcClient }> = ({ rpcClient }) => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  return (
    <PermissionProvider rpcClient={rpcClient}>
      <Logo />
      <Static items={messages}>{renderMessage}</Static>
      {isLoading && <Spinner />}
      <PromptInput onSubmit={handleSubmit} />
      <PermissionRequest />
      <BinaryFeedback />
      <CostThresholdDialog />
      <MessageSelector />
    </PermissionProvider>
  );
};
```

### `src/ui/hooks/`（React Hooks）

16 个自定义 Hook，按职责组织：

| Hook | 职责 |
|------|------|
| `useTerminalSize` | 监听终端尺寸变化 |
| `useTextInput` | 管理输入框状态与提交 |
| `useUnifiedCompletion` | 统一的 Tab 补全逻辑 |
| `useArrowKeyHistory` | 上下箭头历史记录导航 |
| `useCancelRequest` | 取消正在进行的请求 |
| `useCanUseTool` | 检查工具是否可用 |
| `useCostSummary` | 计算并展示费用摘要 |
| `useDoublePress` | 双击按键检测 |
| `useExitOnCtrlCD` | Ctrl+C/D 退出确认 |
| `useInterval` | 定时轮询 Hook |
| `useMessageState` | 消息列表状态管理 |
| `useToolConfirmation` | 工具确认对话框状态 |
| `useBinaryFeedback` | 二选一反馈状态 |
| `useCostThreshold` | 费用阈值对话框状态 |
| `useModelSelector` | 模型选择器状态 |
| `useSession` | 会话数据与 RPC 通信 |

### `src/ui/components/`（UI 组件）

60+ React 组件，按类别组织：

| 目录 | 组件示例 | 职责 |
|------|---------|------|
| `messages/` | `UserMessage`, `AssistantMessage`, `ToolResultMessage`, `SystemMessage` | 各类型消息渲染 |
| `permissions/` | `PermissionRequest`, `PermissionBanner`, `PermissionProvider` | 权限请求与审批 UI |
| `binary-feedback/` | `BinaryFeedback`, `FeedbackOption` | 二选一反馈交互 |
| `model-selector/` | `ModelSelector`, `ModelOption` | LLM 模型切换选择器 |
| `custom-select/` | `CustomSelect`, `SelectOption` | 自定义选择器组件 |
| 根目录 | `PromptInput`, `StatusBar`, `Logo`, `Spinner`, `MessageSelector`, `CostThresholdDialog` | 通用 UI 组件 |

### `src/ui/rpc/client.ts`（JSON-RPC 客户端）

通过 stdio 与 Python 后端通信的 JSON-RPC 客户端，支持双向消息流。

```typescript
// src/ui/rpc/client.ts — 核心接口示意
class JsonRpcClient {
  constructor(stdin: NodeJS.ReadStream, stdout: NodeJS.WriteStream);

  // 发送请求并等待响应
  request(method: string, params?: unknown): Promise<unknown>;

  // 发送通知（不等待响应）
  notify(method: string, params?: unknown): void;

  // 订阅后端推送的事件（流式消息、工具确认请求等）
  onNotification(handler: (notification: JsonRpcNotification) => void): void;
}
```

---

## Entrypoints 层模块

### `entrypoints/cli.py`

```python
import typer

app = typer.Typer(
    name="pode",
    help="Pode-Agent: AI Coding Assistant",
    no_args_is_help=False,  # 无参数时启动 REPL
)

@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    prompt: str | None = typer.Argument(None),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    safe_mode: bool = typer.Option(False, "--safe"),
    model: str | None = typer.Option(None, "--model", "-m"),
    print_mode: bool = typer.Option(False, "-p", "--print"),
    no_stream: bool = typer.Option(False, "--no-stream"),
    debug: bool = typer.Option(False, "--debug"),
):
    """
    Main entrypoint:
    - 无参数 → 启动 REPL
    - 有 prompt → 执行单次查询（print 模式）
    """
    if ctx.invoked_subcommand is not None:
        return
    
    asyncio.run(run_cli(prompt, options=CLIOptions(...)))
```

---

## Types（数据模型）

### `types/conversation.py`（消息类型）

```python
from pydantic import BaseModel, Field
from typing import Literal
import uuid as _uuid

class UserMessage(BaseModel):
    type: Literal["user"] = "user"
    uuid: str = Field(default_factory=lambda: str(_uuid.uuid4()))
    message: MessageParam
    tool_use_result: Any | None = None

class AssistantMessage(BaseModel):
    type: Literal["assistant"] = "assistant"
    uuid: str = Field(default_factory=lambda: str(_uuid.uuid4()))
    message: APIAssistantMessage
    cost_usd: float = 0.0
    duration_ms: int = 0
    is_api_error_message: bool = False

class ProgressMessage(BaseModel):
    type: Literal["progress"] = "progress"
    uuid: str = Field(default_factory=lambda: str(_uuid.uuid4()))
    content: AssistantMessage
    normalized_messages: list
    sibling_tool_use_ids: set[str]
    tools: list[Tool]
    tool_use_id: str

Message = UserMessage | AssistantMessage | ProgressMessage
```

### `types/tool_permission_context.py`

```python
class ToolPermissionContext(BaseModel):
    approved_tools: set[str] = Field(default_factory=set)
    rejected_tools: set[str] = Field(default_factory=set)
    approval_rules: dict[str, PermissionRule] = Field(default_factory=dict)
```
