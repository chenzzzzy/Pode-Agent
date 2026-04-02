# Pode-Agent 内部 API 规范

> 版本：1.0.0 | 状态：草稿 | 更新：2026-03-31  
> 本文档定义模块之间的接口契约（Python 类型注解形式）。所有 Code Agent 必须遵守这些接口，不得随意修改。

---

## 目录

1. [Core API](#core-api)
   - [Config API](#config-api)
   - [Permissions API](#permissions-api)
   - [Tool System API](#tool-system-api)
   - [Cost Tracker API](#cost-tracker-api)
2. [Services API](#services-api)
   - [AI Service API](#ai-service-api)
   - [MCP Service API](#mcp-service-api)
   - [Context Service API](#context-service-api)
   - [Plugin Service API](#plugin-service-api)
   - [System Service API](#system-service-api)
3. [Application API](#application-api)
   - [Session API](#session-api)
4. [事件系统（SessionEvent）](#事件系统)
5. [工具接口契约](#工具接口契约)

---

## Core API

### Config API

**模块**：`pode_agent.core.config`

```python
# === 数据类型 ===

class ProviderType(str, Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    OPENAI_COMPAT = "openai-compat"
    MISTRAL = "mistral"
    DEEPSEEK = "deepseek"
    OLLAMA = "ollama"
    AZURE = "azure"
    GEMINI = "gemini"
    GROQ = "groq"
    BEDROCK = "bedrock"
    VERTEX = "vertex"

class ModelProfile(BaseModel):
    name: str                    # 显示名称（用户自定义）
    provider: ProviderType
    model_name: str              # API model 标识符
    base_url: str | None = None  # 自定义 API 地址
    api_key: str = ""            # API 密钥（存储时脱敏）
    max_tokens: int = 8192
    context_length: int = 200_000
    reasoning_effort: Literal["low", "medium", "high", "minimal"] | None = None
    is_active: bool = True

class ModelPointers(BaseModel):
    main: str = "claude-sonnet-4-5-20251101"    # 主要模型（复杂任务）
    task: str = "claude-haiku-4-5"              # 任务模型（工具调用）
    compact: str = "claude-haiku-4-5"           # 压缩模型（摘要）
    quick: str = "claude-haiku-4-5"             # 快速模型（简单查询）

class McpServerConfig(BaseModel):
    type: Literal["stdio", "sse", "http", "ws", "sse-ide", "ws-ide"]
    command: str | None = None          # stdio 用
    args: list[str] = []                # stdio 用
    env: dict[str, str] = {}            # 额外环境变量
    url: str | None = None              # sse/http/ws 用
    headers: dict[str, str] = {}        # http/sse 认证头

class CustomApiKeyResponses(BaseModel):
    approved: list[str] = []   # 已批准的 API key（hash）
    rejected: list[str] = []   # 已拒绝的 API key（hash）

class AccountInfo(BaseModel):
    email: str
    name: str | None = None
    org: str | None = None
    access_token: str
    refresh_token: str | None = None
    expires_at: datetime | None = None

class GlobalConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    
    num_startups: int = 0
    theme: Literal["dark", "light"] = "dark"
    verbose: bool = False
    has_completed_onboarding: bool = False
    last_onboarding_version: str | None = None
    last_release_notes_seen: str | None = None
    default_model_name: str = "claude-3-5-sonnet-20241022"
    max_tokens: int | None = None
    auto_compact_threshold: int = 50       # 消息数超过此值时自动压缩
    primary_provider: ProviderType | None = None
    model_profiles: list[ModelProfile] = []
    model_pointers: ModelPointers = ModelPointers()
    mcp_servers: dict[str, McpServerConfig] = {}
    proxy: str | None = None
    stream: bool = True
    oauth_account: AccountInfo | None = None
    custom_api_key_responses: CustomApiKeyResponses | None = None
    preferred_notif_channel: Literal["terminal", "system"] = "terminal"
    auto_updater_status: Literal[
        "disabled", "enabled", "no_permissions", "not_configured"
    ] | None = None

class ProjectConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    
    allowed_tools: list[str] = []       # 已授权工具
    denied_tools: list[str] = []        # 已拒绝工具
    asked_tools: list[str] = []         # 询问过的工具（去重）
    context: dict[str, str] = {}        # 自定义上下文键值对
    history: list[str] = []             # 历史会话日志文件名
    dont_crawl_directory: bool = False
    enable_architect_tool: bool = False
    mcp_servers: dict[str, McpServerConfig] = {}
    last_cost: float | None = None      # 上次会话费用（USD）
    last_duration: int | None = None    # 上次会话时长（ms）

# === 公共函数 ===

def get_global_config() -> GlobalConfig:
    """
    读取全局配置文件。
    
    路径：${PODE_CONFIG_DIR:-~/.pode}/config.json
    不存在时返回 GlobalConfig()（默认值）。
    文件损坏时记录警告并返回默认值。
    
    Returns:
        GlobalConfig 实例
    """

def save_global_config(config: GlobalConfig) -> None:
    """
    原子写入全局配置文件。
    
    先写入临时文件，再 os.replace()，保证原子性。
    创建必要的父目录（exist_ok=True）。
    
    Args:
        config: 要保存的配置
    
    Raises:
        ConfigError: 写入失败时
    """

def get_current_project_config() -> ProjectConfig:
    """
    读取当前工作目录的项目配置。
    
    查找路径（从 cwd 向上到 git 根目录）：
    1. cwd/.pode.json
    2. parent/.pode.json
    3. ...直到 git 根目录
    
    Returns:
        ProjectConfig 实例（不存在时返回默认值）
    """

def save_current_project_config(config: ProjectConfig) -> None:
    """
    保存当前项目配置到 {cwd}/.pode.json
    """

def get_project_mcp_server_definitions() -> dict[str, McpServerConfig]:
    """
    读取项目级别的 MCP 服务器配置。
    
    读取顺序（后者覆盖前者）：
    1. .mcprc（JSON 格式）
    2. .mcp.json
    
    Returns:
        合并后的 server name → config 字典
    """

def get_config_for_cli(key: str, global_: bool = True) -> Any:
    """
    获取单个配置值（CLI 命令用）。
    
    Args:
        key: 配置键（支持点号分隔，如 "model_pointers.main"）
        global_: True=全局配置，False=项目配置
    
    Returns:
        配置值，不存在时返回 None
    """

def set_config_for_cli(key: str, value: Any, global_: bool = True) -> None:
    """
    设置单个配置值（CLI 命令用）。
    
    Args:
        key: 配置键
        value: 配置值（会根据目标字段类型转换）
        global_: True=全局配置，False=项目配置
    
    Raises:
        ConfigError: 键不存在或类型不匹配时
    """

def list_config_for_cli(global_: bool = True) -> dict[str, Any]:
    """
    列出所有配置项（CLI 命令用）。
    
    Returns:
        扁平化的 key → value 字典
    """
```

---

### Permissions API

**模块**：`pode_agent.core.permissions`

```python
# === 数据类型 ===

class PermissionMode(str, Enum):
    DEFAULT = "default"
    ACCEPT_EDITS = "acceptEdits"
    PLAN = "plan"
    BYPASS_PERMISSIONS = "bypassPermissions"
    DONT_ASK = "dontAsk"
    DELEGATE = "delegate"

class PermissionResult(str, Enum):
    ALLOWED = "allowed"
    NEEDS_PROMPT = "needs_prompt"
    DENIED = "denied"

class PermissionDecision(str, Enum):
    ALLOW_ONCE = "allow_once"
    ALLOW_SESSION = "allow_session"
    ALLOW_ALWAYS = "allow_always"
    DENY = "deny"

class PermissionRule(BaseModel):
    pattern: str                 # 匹配模式（glob 或正则）
    decision: PermissionDecision

class ToolPermissionContext(BaseModel):
    approved_tools: set[str] = set()      # 本会话已批准的工具
    rejected_tools: set[str] = set()      # 本会话已拒绝的工具
    approval_rules: dict[str, PermissionRule] = {}  # 模式规则

class PermissionContext(BaseModel):
    mode: PermissionMode = PermissionMode.DEFAULT
    tool_permission_context: ToolPermissionContext = ToolPermissionContext()
    project_config: ProjectConfig | None = None  # 用于检查已持久化权限

# === 主要类 ===

class PermissionEngine:
    async def has_permissions(
        self,
        tool_name: str,
        input: dict[str, Any],
        context: PermissionContext,
    ) -> PermissionResult:
        """
        检查工具是否有权限执行。
        
        检查顺序：
        1. bypassPermissions 模式 → ALLOWED
        2. 工具在 rejected_tools 中 → DENIED
        3. 工具在 approved_tools 中 → ALLOWED
        4. 工具在 ProjectConfig.denied_tools 中 → DENIED
        5. 工具在 ProjectConfig.allowed_tools 中 → ALLOWED
        6. plan 模式 + 非只读工具 → DENIED
        7. 工具特定规则（bash.py, file.py 等）
        8. 默认：NEEDS_PROMPT
        """

    async def persist_permission_update(
        self,
        tool_name: str,
        input: dict[str, Any],
        decision: PermissionDecision,
        context: PermissionContext,
    ) -> None:
        """
        保存用户的权限决定到磁盘。
        
        ALLOW_ALWAYS → 写入 ProjectConfig.allowed_tools
        DENY → 写入 ProjectConfig.denied_tools
        ALLOW_ONCE / ALLOW_SESSION → 不写磁盘，只更新内存
        """

    def apply_context_update(
        self,
        tool_name: str,
        decision: PermissionDecision,
        context: ToolPermissionContext,
    ) -> ToolPermissionContext:
        """
        将权限决定应用到内存中的权限上下文（不影响磁盘）。
        返回更新后的新 ToolPermissionContext 实例。
        """

# === 便捷函数 ===

def is_safe_bash_command(command: str) -> bool:
    """判断 Bash 命令是否安全（只读、无副作用）"""

def is_path_in_working_directories(path: str, cwd: str) -> bool:
    """判断文件路径是否在工作目录内（防路径穿越）"""

PLAN_MODE_ALLOWED_TOOLS: frozenset[str] = frozenset([
    "bash",          # 只允许安全命令
    "file_read",
    "grep",
    "glob",
    "ls",
    "web_fetch",
    "web_search",
    "list_mcp_resources",
    "read_mcp_resource",
    # EnterPlanMode / ExitPlanMode 自己管理
])
```

---

### Tool System API

**模块**：`pode_agent.core.tools`

> 📖 **工具系统完整设计**（ToolRegistry/ToolLoader/`get_enabled_tools()`、工具注入 Agent Loop、Pydantic JSON Schema → Provider tools schema、权限耦合、并发语义）详见 [tools-system.md](./tools-system.md)。  
> 本节展示核心数据类型和接口契约；工具的目录组织和各域工具清单见该文档。

```python
# === 数据类型（可参考 modules.md 中的完整定义）===

class ToolOutput(BaseModel):
    type: Literal["result", "progress"]
    data: Any = None
    content: Any = None
    result_for_assistant: str | list | None = None
    new_messages: list[Any] | None = None
    normalized_messages: list[Any] | None = None
    tools: list[Any] | None = None

class ToolResult(BaseModel):
    """collect_tool_result 的返回值"""
    data: Any
    result_for_assistant: str | list | None = None
    new_messages: list[Any] = []
    error: str | None = None

class ValidationResult(BaseModel):
    result: bool
    message: str | None = None

# === Tool ABC（所有工具必须实现）===

class Tool(ABC):
    name: str
    description: str | Callable[..., Awaitable[str]] | None = None
    cached_description: str | None = None

    @abstractmethod
    def input_schema(self) -> type[BaseModel]: ...

    @abstractmethod
    async def is_enabled(self) -> bool: ...

    @abstractmethod
    def is_read_only(self, input: Any = None) -> bool: ...

    def is_concurrency_safe(self, input: Any = None) -> bool:
        return False

    @abstractmethod
    def needs_permissions(self, input: Any = None) -> bool: ...

    async def validate_input(
        self,
        input: BaseModel,
        context: ToolUseContext | None = None,
    ) -> ValidationResult:
        return ValidationResult(result=True)

    @abstractmethod
    def render_result_for_assistant(self, output: Any) -> str | list: ...

    def render_tool_use_message(
        self,
        input: Any,
        options: dict | None = None,
    ) -> str:
        return f"Running {self.name}..."

    @abstractmethod
    async def call(
        self,
        input: BaseModel,
        context: "ToolUseContext",
    ) -> AsyncGenerator[ToolOutput, None]: ...

    def get_json_schema(self) -> dict[str, Any]:
        """生成 JSON Schema（直接调用 Pydantic model_json_schema()）"""
        return self.input_schema().model_json_schema()

# === Registry ===

class ToolRegistry:
    """
    单例注册表，保存所有已知工具（内置 + 插件 + MCP 包装）。
    程序启动时由 ToolLoader 填充，运行期间只读。
    """

    def register(self, tool: Tool, aliases: list[str] | None = None) -> None:
        """注册工具。name 重复时抛出 ToolRegistryError。"""

    def get(self, name: str) -> Tool | None:
        """按名称或别名查找工具。"""

    def all(self) -> list[Tool]:
        """返回所有已注册工具（不含别名重复项）。"""

    def names(self) -> list[str]:
        """返回所有工具名（含别名）。"""

# === Executor ===

async def collect_tool_result(
    tool: Tool,
    input: BaseModel,
    context: "ToolUseContext",
    on_progress: Callable[[ToolOutput], Awaitable[None]] | None = None,
) -> ToolResult:
    """
    消费工具的 AsyncGenerator，收集最终 result。
    
    逐个消费 ToolOutput：
    - type='progress' → 调用 on_progress 回调（如有）
    - type='result' → 返回 ToolResult
    
    如果 generator 结束但没有 result，抛出 ToolError。
    """
```

---

### Cost Tracker API

**模块**：`pode_agent.core.cost_tracker`

```python
def add_to_total_cost(cost_usd: float) -> None:
    """累加到当前会话总费用"""

def get_total_cost() -> float:
    """获取当前会话总费用（USD）"""

def reset_cost() -> None:
    """重置费用（新会话开始时调用）"""

def calculate_model_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float:
    """
    根据模型和 token 数计算费用（USD）。
    
    价格数据内置（定期更新），未知模型返回 0.0。
    """
```

---

## Services API

### AI Service API

**模块**：`pode_agent.services.ai`

```python
# === 核心数据类型 ===

class TokenUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

class ToolDefinition(BaseModel):
    """传递给 LLM 的工具定义（JSON Schema 格式）"""
    name: str
    description: str
    input_schema: dict[str, Any]

class ToolUseBlock(BaseModel):
    """LLM 返回的工具调用块"""
    id: str
    name: str
    input: dict[str, Any]

class AIResponse(BaseModel):
    type: Literal[
        "text_delta",       # 文本增量
        "tool_use_start",   # 工具调用开始（name 已知，input 待收集）
        "tool_use_delta",   # 工具调用 input 的增量 JSON
        "tool_use_end",     # 工具调用结束（input 完整）
        "message_done",     # 消息完成
        "error",            # 错误
    ]
    # type = text_delta
    text: str | None = None
    # type = tool_use_start/end
    tool_use_id: str | None = None
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None  # 仅 tool_use_end 有
    # type = message_done
    usage: TokenUsage | None = None
    cost_usd: float | None = None
    stop_reason: str | None = None
    # type = error
    error_message: str | None = None
    is_retriable: bool = False

class UnifiedRequestParams(BaseModel):
    messages: list[dict[str, Any]]  # 统一消息格式（见下文）
    system_prompt: str
    model: str
    max_tokens: int
    tools: list[ToolDefinition] | None = None
    temperature: float | None = None
    thinking_tokens: int | None = None    # Extended thinking（o1 style）
    stream: bool = True
    stop_sequences: list[str] | None = None
    metadata: dict[str, Any] | None = None

# 统一消息格式（模块内部使用）
# {"role": "user", "content": str | list[ContentBlock]}
# {"role": "assistant", "content": str | list[ContentBlock]}
# ContentBlock: {"type": "text", "text": str}
#             | {"type": "tool_use", "id": ..., "name": ..., "input": ...}
#             | {"type": "tool_result", "tool_use_id": ..., "content": ...}

# === Provider 抽象 ===

class AIProvider(ABC):
    @abstractmethod
    async def query(
        self,
        params: UnifiedRequestParams,
    ) -> AsyncGenerator[AIResponse, None]:
        """
        流式查询 LLM。
        
        必须按顺序 yield：
        1. 若干 text_delta
        2. 若干 tool_use_start + tool_use_delta... + tool_use_end
        3. 最终 message_done（含 usage 和 cost_usd）
        
        异常处理：
        - 速率限制：yield error(is_retriable=True)，内部重试最多 3 次
        - 认证错误：yield error(is_retriable=False)
        """

# === Model Management ===

class ModelCapabilities(BaseModel):
    max_tokens: int
    context_length: int
    supports_thinking: bool = False
    supports_tool_use: bool = True
    supports_streaming: bool = True
    supports_vision: bool = False
    provider: ProviderType

class ModelAdapterFactory:
    @staticmethod
    def get_provider(model_name: str) -> AIProvider:
        """
        根据 model_name 返回 AIProvider 实例。
        
        查找顺序：
        1. 模型名前缀匹配（claude- → Anthropic, gpt- → OpenAI 等）
        2. GlobalConfig.model_profiles 中的自定义 profile
        3. 默认：Anthropic
        """

    @staticmethod
    def get_capabilities(model_name: str) -> ModelCapabilities:
        """返回模型能力（内置数据，支持自定义 profile 覆盖）"""

    @staticmethod
    def register_provider(prefix: str, provider_class: type[AIProvider]) -> None:
        """注册自定义 Provider（插件用）"""

# === 顶层函数 ===

async def query_llm(
    params: UnifiedRequestParams,
) -> AsyncGenerator[AIResponse, None]:
    """
    顶层 LLM 查询函数。自动选择 Provider。
    Session 层应调用此函数而非直接调用 Provider。
    """

def normalize_messages_for_provider(
    messages: list[Message],
    provider: ProviderType,
) -> list[dict[str, Any]]:
    """将内部 Message 列表转换为特定 Provider 的消息格式"""
```

---

### MCP Service API

**模块**：`pode_agent.services.mcp`

```python
class McpToolDefinition(BaseModel):
    name: str
    description: str | None = None
    input_schema: dict[str, Any]

class McpResourceDefinition(BaseModel):
    uri: str
    name: str | None = None
    description: str | None = None
    mime_type: str | None = None

class WrappedMcpClient(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    name: str                              # server name（来自配置）
    config: McpServerConfig                # 原始配置
    session: Any                           # mcp.ClientSession
    tools: list[McpToolDefinition] = []
    resources: list[McpResourceDefinition] = []

async def connect_to_server(
    name: str,
    config: McpServerConfig,
) -> WrappedMcpClient:
    """
    连接到 MCP 服务器。
    
    根据 config.type 选择 transport：
    - stdio → stdio_client
    - sse → sse_client
    - http → streamable_http_client
    - ws → websocket_client
    
    连接后自动发现工具和资源。
    
    Raises:
        McpConnectionError: 连接失败
        McpTimeoutError: 连接超时（默认 30s）
    """

async def connect_all_servers(
    configs: dict[str, McpServerConfig],
    on_error: Callable[[str, Exception], None] | None = None,
) -> list[WrappedMcpClient]:
    """
    并发连接所有 MCP 服务器。
    
    连接失败的服务器会调用 on_error 并跳过（不影响其他服务器）。
    """

def wrap_mcp_tools_as_pode_tools(
    client: WrappedMcpClient,
) -> list[Tool]:
    """
    将 MCP 工具包装为 Pode Tool。
    
    工具名格式：mcp__{server_name}__{tool_name}
    """

async def discover_mcp_servers() -> dict[str, McpServerConfig]:
    """
    自动发现 MCP 服务器配置。
    
    查找路径：
    1. ~/.pode/config.json 中的 mcp_servers
    2. cwd/.mcp.json
    3. cwd/.mcprc
    （后者优先级更高）
    """
```

---

### Context Service API

**模块**：`pode_agent.services.context`

```python
class ContextItem(BaseModel):
    key: str          # 标题（如 "git_status"）
    content: str      # 内容
    source: str       # 来源路径或描述

async def get_project_context(
    cwd: str | None = None,
    max_bytes: int | None = None,
) -> dict[str, str]:
    """
    收集项目上下文。
    
    Args:
        cwd: 工作目录（默认 os.getcwd()）
        max_bytes: 最大字节数（默认 ${PODE_PROJECT_DOC_MAX_BYTES:-32768}）
    
    Returns:
        有序的 key → content 字典（按重要性排序）
    
    收集顺序（超出 max_bytes 时截断）：
    1. git_status（git status + recent commits）
    2. instruction_files（AGENTS.md, CLAUDE.md, PODE.md）
    3. readme（README.md, README.rst）
    4. directory_tree（ls -la，只看顶层）
    5. custom_context（ProjectConfig.context）
    """

async def process_mentions(
    user_input: str,
    cwd: str | None = None,
) -> tuple[str, list[FileContent]]:
    """
    处理用户输入中的 @mention。
    
    语法：@path/to/file 或 @filename
    
    Returns:
        (处理后的 prompt（@mention 替换为占位符）, 文件内容列表)
    """

class FileContent(BaseModel):
    path: str
    content: str
    mention: str     # 原始 @mention 字符串
```

---

### Plugin Service API

**模块**：`pode_agent.services.plugins`

```python
# === 自定义命令 ===

class CustomCommand(BaseModel):
    name: str                   # 文件名（无扩展名）
    description: str | None
    category: str | None
    template: str               # 原始模板内容
    file_path: Path

async def load_custom_commands(
    search_dirs: list[Path] | None = None,
) -> list[CustomCommand]:
    """
    加载自定义命令。
    
    搜索路径（按优先级）：
    1. cwd/.pode/commands/
    2. ~/.pode/commands/
    
    文件格式：.md 或 .yaml，支持 YAML frontmatter。
    """

async def render_custom_command(
    command: CustomCommand,
    args: dict[str, str] | None = None,
) -> str:
    """
    渲染自定义命令模板。
    
    处理：
    - !`cmd` → 执行 bash，替换为输出
    - @file → 替换为文件内容
    - {{key}} → 替换为 args[key]
    """

# === Skill Marketplace ===

class SkillManifest(BaseModel):
    name: str
    description: str
    version: str = "1.0.0"
    author: str | None = None
    commands: list[SkillCommand] = []
    tools: list[str] = []          # 需要的工具名
    requires: list[str] = []       # 依赖其他 skill 名

class SkillSource(BaseModel):
    source: Literal["github", "git", "url", "pip", "directory"]
    # github:
    repo: str | None = None        # "owner/repo"
    ref: str | None = None         # branch/tag
    path: str | None = None        # skills 子目录
    # url:
    url: str | None = None
    # pip:
    package: str | None = None
    # directory:
    directory: str | None = None

async def install_skill(
    source: SkillSource,
    name: str | None = None,
) -> SkillManifest:
    """
    安装 Skill。
    
    下载→解压→验证 manifest→安装到 ~/.pode/skills/{name}/
    
    Raises:
        SkillInstallError: 安装失败
        SkillValidationError: manifest 验证失败
    """

async def list_installed_skills() -> list[SkillManifest]:
    """列出所有已安装的 Skill"""

async def uninstall_skill(name: str) -> None:
    """卸载指定 Skill"""
```

---

### System Service API

**模块**：`pode_agent.services.system`

```python
# === 文件新鲜度 ===

class FileFreshnessTracker:
    def mark_read(self, path: str, timestamp: float | None = None) -> None:
        """记录文件读取时间"""

    def is_stale(self, path: str, read_timestamp: float) -> bool:
        """
        判断文件自上次读取后是否被修改。
        
        通过 os.stat().st_mtime 对比 read_timestamp。
        """

    def get_stale_files(
        self,
        read_timestamps: dict[str, float],
    ) -> list[str]:
        """返回所有已修改的文件路径列表"""

# === System Prompt ===

class SystemPromptOptions(BaseModel):
    include_tool_descriptions: bool = False
    safe_mode: bool = False
    current_date: str | None = None    # 覆盖当前日期（测试用）

async def build_system_prompt(
    context: dict[str, str],
    tools: list[Tool],
    options: SystemPromptOptions | None = None,
) -> str:
    """
    构建完整的 system prompt。
    
    结构：
    1. 基础角色描述（SYSTEM_PROMPT 常量）
    2. 当前日期时间
    3. 项目上下文（<context_key>...</context_key> 格式）
    4. 工具能力描述（若 options.include_tool_descriptions=True）
    5. 工具提示词（每个 tool.prompt() 的输出）
    """
```

---

## Application API

### Session API

**模块**：`pode_agent.app.session`

> 📖 **`SessionManager.process_input()` 所调用的核心 Agentic Loop 设计规格详见** [agent-loop.md](./agent-loop.md)。  
> 📖 **Plan Mode 的 JSONL 事件类型（`plan_created`/`plan_approved`/`plan_step_done` 等）和 Session 恢复详见** [plan-mode.md § 存储方案 A](./plan-mode.md#存储方案-a写入-session-jsonl)。  
> 本节仅描述 Session API 的类型契约；循环引擎的递归结构、`ToolUseQueue`、Hook 系统请参阅 agent-loop.md。

```python
# === 事件类型（Session → UI）===

class SessionEventType(str, Enum):
    USER_MESSAGE = "user_message"
    ASSISTANT_DELTA = "assistant_delta"
    TOOL_USE_START = "tool_use_start"
    TOOL_PROGRESS = "tool_progress"
    TOOL_RESULT = "tool_result"
    PERMISSION_REQUEST = "permission_request"
    COST_UPDATE = "cost_update"
    MODEL_ERROR = "model_error"
    DONE = "done"
    # Plan Mode 事件（Phase 3+，详见 plan-mode.md）
    PLAN_CREATED = "plan_created"         # ExitPlanModeTool 返回计划
    PLAN_APPROVED = "plan_approved"       # 用户批准计划
    PLAN_STEP_START = "plan_step_start"   # 步骤开始执行
    PLAN_STEP_DONE = "plan_step_done"     # 步骤完成
    PLAN_DONE = "plan_done"               # 所有步骤完成
    PLAN_CANCELLED = "plan_cancelled"     # 计划取消

class SessionEvent(BaseModel):
    type: SessionEventType
    data: Any = None
    message_id: str | None = None

class PermissionRequestData(BaseModel):
    """PERMISSION_REQUEST 事件的 data 字段"""
    tool_name: str
    tool_input: dict[str, Any]
    risk_level: Literal["low", "medium", "high"] = "medium"
    description: str | None = None

# === 主类 ===

class SessionManager:
    """
    管理一次对话会话的完整生命周期。
    
    职责：
    - 维护消息历史
    - 协调 LLM 查询和工具执行
    - 管理权限上下文
    - 持久化到 JSONL 日志
    - 提供中止机制
    """

    def __init__(
        self,
        tools: list[Tool],
        commands: list["CustomCommand"],
        message_log_name: str,
        mcp_clients: list["WrappedMcpClient"] | None = None,
        initial_messages: list[Message] | None = None,
        permission_mode: PermissionMode = PermissionMode.DEFAULT,
        model: str | None = None,
        verbose: bool = False,
        safe_mode: bool = False,
    ) -> None: ...

    async def process_input(
        self,
        prompt: str,
    ) -> AsyncGenerator[SessionEvent, None]:
        """
        处理用户输入。
        
        这是 Session 的核心方法，UI 层通过 async for 消费 SessionEvent。
        
        高层流程：
        1. 处理 @mention，构建 UserMessage
        2. yield SessionEvent(USER_MESSAGE)
        3. 委托 app/query.py: query() → query_core()（递归 Agentic Loop）
           - 自动上下文压缩（auto_compact）
           - 动态构建 system prompt（含 Hook 注入）
           - LLM 调用 → ToolUseQueue 并发工具调度 → 递归
           - Stop Hook 重入（最多 MAX_STOP_HOOK_ATTEMPTS 次）
        4. yield SessionEvent(DONE)
        
        ⚠️  核心循环不是简单的 while True，而是递归 AsyncGenerator。
        完整设计规格（伪代码、Hook 注入点、并发策略）见 docs/agent-loop.md。
        """

    def resolve_permission(
        self,
        tool_name: str,
        decision: PermissionDecision,
    ) -> None:
        """
        用户响应权限请求后调用此方法。
        
        UI 层收到 PERMISSION_REQUEST 事件后，
        等待用户操作，然后调用此方法继续执行。
        """

    def abort(self) -> None:
        """
        中断当前进行中的操作。
        
        设置 abort_event，当前工具/LLM 查询将在下一个检查点停止。
        """

    def get_messages(self) -> list[Message]:
        """返回当前会话的消息历史（只读）"""

    def save_message(self, message: Message) -> None:
        """手动追加消息到日志（通常由 process_input 内部调用）"""

    @classmethod
    def load_from_log(
        cls,
        log_name: str,
        tools: list[Tool],
        **kwargs: Any,
    ) -> "SessionManager":
        """
        从 JSONL 日志文件恢复会话。
        
        Args:
            log_name: 日志文件名（不含路径和扩展名）
        """
```

---

## 事件系统

### PERMISSION_REQUEST 事件处理流程

```
Session.process_input() 内部：

1. await permission_engine.has_permissions() → NEEDS_PROMPT
2. 创建 asyncio.Event: permission_resolved_event
3. yield SessionEvent(type=PERMISSION_REQUEST, data=PermissionRequestData(...))
4. await permission_resolved_event.wait()  ← 阻塞，等待 UI 调用 resolve_permission()
5. 检查 _last_permission_decision
6. 如果 DENY: return ToolResult(error="Permission denied")
7. 如果 ALLOW_*: continue 执行工具

UI 层：
async for event in session.process_input(prompt):
    if event.type == SessionEventType.PERMISSION_REQUEST:
        # 显示权限对话框
        decision = await show_permission_dialog(event.data)
        # 通知 Session
        session.resolve_permission(event.data.tool_name, decision)
```

---

## 工具接口契约

每个工具实现必须遵守以下契约：

### 命名规范

```python
# 工具名：snake_case，全局唯一
name = "file_edit"          # ✅
name = "FileEdit"           # ❌
name = "file-edit"          # ❌

# MCP 工具名格式
name = "mcp__filesystem__read_file"   # ✅ mcp__{server}__{tool}
```

### 输入模式契约

```python
# ✅ 正确：使用 Pydantic BaseModel
class FileEditInput(BaseModel):
    file_path: str = Field(description="Path to the file to edit")
    old_str: str = Field(description="String to find and replace")
    new_str: str = Field(description="Replacement string")

# ❌ 错误：使用 dict 或 TypedDict
```

### AsyncGenerator 契约

```python
# ✅ 正确：至少 yield 一个 type='result'
async def call(self, input, context):
    yield ToolOutput(type="progress", content="Working...")
    # ... 执行操作 ...
    yield ToolOutput(type="result", data=result)

# ❌ 错误：直接 return，不 yield result
# ❌ 错误：yield 多个 type='result'（只 yield 最后一个）
```

### 幂等性

- `FileReadTool`, `GrepTool`, `GlobTool`, `LsTool`：**幂等**，可安全重复调用
- `FileEditTool`, `FileWriteTool`, `BashTool`：**非幂等**，需要权限确认

### 路径安全

文件系统工具必须调用：

```python
from pode_agent.core.permissions.rules.file import is_path_in_working_directories

# ✅ 在 call() 开始时验证路径
if not is_path_in_working_directories(input.file_path, get_cwd()):
    yield ToolOutput(type="result", data=None, result_for_assistant=(
        f"Error: Path '{input.file_path}' is outside the working directory"
    ))
    return
```
