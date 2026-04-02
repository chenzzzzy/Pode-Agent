# Pode-Agent 分阶段实施计划

> 版本：1.4.0 | 状态：Phase 3 已完成 | 更新：2026-04-02
> **给 Code Agent 的说明**：请严格按照阶段顺序实施。每个阶段结束时运行对应验收测试，通过后才能进入下一阶段。

---

## 目录

1. [总体时间表](#总体时间表)
2. [Phase 0：项目骨架（Week 1）](#phase-0项目骨架)
3. [Phase 1：核心功能（Weeks 2-4）](#phase-1核心功能)
4. [Phase 2：LLM 集成与会话管理（Weeks 5-7）](#phase-2llm-集成与会话管理)
5. [Phase 3：完整工具集（Weeks 8-10）](#phase-3完整工具集)
6. [Phase 4：终端 UI（Weeks 11-13）](#phase-4终端-ui)
7. [Phase 5：MCP 与插件系统（Weeks 14-16）](#phase-5mcp-与插件系统)
8. [Phase 6：高级特性与完善（Weeks 17-20）](#phase-6高级特性与完善)
9. [验收标准矩阵](#验收标准矩阵)
10. [依赖关系图](#依赖关系图)

---

## 总体时间表

```
Week:  1    2    3    4    5    6    7    8    9   10   11   12   13   14   15   16   17   18   19   20
       ├────┤    ├─────────────┤    ├─────────┤    ├────┤    ├─────────┤    ├─────────┤    ├──────────┤
Phase: │ 0  │    │     1       │    │    2    │    │   3     │    │    4    │    │    5    │    │    6     │
       │Skel│    │   Core      │    │   LLM   │    │  Tools  │    │   UI   │    │   MCP   │    │  Polish  │
       └────┘    └─────────────┘    └─────────┘    └─────────┘    └─────────┘    └─────────┘    └──────────┘
```

**里程碑**：

| 里程碑 | 时间 | 可交付物 |
|--------|------|---------|
| M0: 项目骨架 | Week 1 | 可运行的空壳 CLI |
| M1: MVP | Week 7 | 可使用基础工具的非交互模式 |
| M2: 完整工具 | Week 10 | 所有 25+ 工具可用 |
| M3: 完整 UI | Week 13 | Textual REPL 界面完整 |
| M4: 完整协议 | Week 16 | MCP + 插件 + ACP 支持 |
| M5: 1.0 发布 | Week 20 | PyPI 发布，功能 100% 对齐 |

---

## Phase 0：项目骨架 ✅ 已完成

**目标**：建立可运行的项目结构，所有基础设施就位。
**时间**：Week 1（5 个工作日）
**负责 Agent**：架构/基础 Agent
**实际完成日期**：2026-03-31

### 任务列表

#### 任务 0.1：初始化项目（Day 1）

```bash
# 已完成命令
mkdir Pode-Agent && cd Pode-Agent
git init
```

**文件结构**：

```
Pode-agent/
├── pyproject.toml         ← 完整的项目配置
├── README.md
├── .gitignore
├── .github/
│   └── workflows/
│       └── ci.yml         ← GitHub Actions CI
├── pode_agent/
│   ├── __init__.py        ← 版本号定义
│   ├── entrypoints/
│   │   ├── __init__.py
│   │   └── cli.py         ← 空壳 CLI（只有 `Pode --version` 工作）
│   ├── core/
│   │   ├── __init__.py
│   │   └── tools/
│   │       ├── __init__.py
│   │       └── base.py    ← Tool ABC（完整定义）
│   ├── infra/
│   │   ├── __init__.py
│   │   └── logging.py     ← 基础日志配置
│   └── types/
│       ├── __init__.py
│       └── conversation.py ← 消息类型 Pydantic 模型
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── unit/
    │   └── __init__.py
    └── integration/
        └── __init__.py
```

**验收标准**：
- [x] `pip install -e ".[dev]"` 成功
- [x] `pode --version` 输出版本号（`pode-agent 0.1.0`）
- [x] `pode --help` 显示帮助信息（含 config 子命令）
- [x] `mypy pode_agent/` 无错误（19 source files, 0 errors）
- [x] `ruff check pode_agent/` 无错误（All checks passed）
- [x] `pytest tests/` 通过（35 tests passed）

---

#### 任务 0.2：基础设施（Day 2-3） ✅

**文件**：
- `pode_agent/infra/logging.py` — Rich handler 日志配置
- `pode_agent/infra/http_client.py` — httpx AsyncClient 工厂（代理支持）
- `pode_agent/infra/fs.py` — 原子写入、安全读取、目录创建
- `pode_agent/infra/shell.py` — Shell 命令执行（含安全的 `execute_command` 和 `execute_shell`）

**验收标准**：
- [x] 日志可以用 `logger.debug/info/warning/error()` 调用
- [x] HTTP 客户端支持代理配置
- [x] 文件系统工具函数有单元测试（9 tests in test_fs.py）
- [x] Shell 执行支持超时和中止

---

#### 任务 0.3：配置系统（Day 4-5） ✅

**文件**：
- `pode_agent/core/config/schema.py` — 所有 Pydantic 数据模型（GlobalConfig, ProjectConfig 等）
- `pode_agent/core/config/loader.py` — 读写 config.json（原子写入、缓存、dotted key 访问）
- `pode_agent/core/config/defaults.py` — 默认值（支持 PODE_CONFIG_DIR 环境变量覆盖）
- `pode_agent/core/config/__init__.py` — 公共 API 重导出

**验收标准**：
- [x] `get_global_config()` 在 `~/.pode/config.json` 不存在时返回默认值
- [x] `save_global_config()` 写入文件，`get_global_config()` 能读回来
- [x] 配置模型能通过 `model_json_schema()` 生成 JSON Schema
- [x] 单元测试覆盖读写、默认值、错误处理（16 tests in test_config.py）

---

### Phase 0 完成标志 ✅

```bash
# 这些命令已全部验证通过
pode --version          # pode-agent 0.1.0
pode --help             # 显示帮助（含 config 子命令）
pode config get theme   # dark
pode config set theme light   # Set theme = light
pode config list        # 列出所有配置（flat key=value）
mypy pode_agent/        # Success: no issues found in 19 source files
ruff check pode_agent/  # All checks passed
pytest tests/           # 35 passed
```

**实际交付物**：
- 17 个 Python 源文件（pode_agent/）
- 6 个测试文件（tests/）
- 35 个单元测试，全部通过
- 完整的 CLI 入口点（pode 命令）
- 配置系统（读写、dotted key 访问、原子写入、类型转换）
- Tool ABC + Registry + Executor
- 基础设施层（logging, httpx, fs, shell）
- 消息类型定义（UserMessage, AssistantMessage, ProgressMessage）
- mypy strict mode 零错误，ruff 零告警

---

## Phase 1：核心功能 ✅ 已完成

**目标**：权限系统、核心工具（Bash + 文件 IO + Grep）可用，能执行非 LLM 操作。
**时间**：Weeks 2-4（15 个工作日）
**依赖**：Phase 0 完成
**负责 Agent**：核心功能 Agent
**实际完成日期**：2026-04-01

**Phase 1 工具系统子块**（对应 [tools-system.md](./tools-system.md)）：

| 子功能 | 文件 | 状态 |
|--------|------|------|
| Tool ABC（基类） | `core/tools/base.py` | ✅ 已在 Phase 0 完成，Phase 1 验证 `is_read_only()`/`is_concurrency_safe()` |
| ToolRegistry（基础） | `core/tools/registry.py` | ✅ 已在 Phase 0 完成，Phase 1 无需改动 |
| `get_enabled_tools()`（基础版） | `core/tools/registry.py` | ✅ safe_mode 过滤已实现；permission_mode 过滤在 Phase 3 完善 |
| 权限系统（`PermissionMode.PLAN` 规则） | `core/permissions/engine.py` | ✅ 框架就位，Plan Mode 硬拒绝规则已实现（Phase 3 的 EnterPlanModeTool 依赖它） |

### 任务列表

#### 任务 1.1：权限系统（Week 2，Day 1-3） ✅

**文件**：
- `pode_agent/core/permissions/engine.py`
- `pode_agent/core/permissions/rules/bash.py`
- `pode_agent/core/permissions/rules/file.py`
- `pode_agent/core/permissions/rules/plan_mode.py`
- `pode_agent/core/permissions/store.py`
- `pode_agent/core/permissions/__init__.py`
- `pode_agent/core/permissions/types.py`

**关键实现**：

```python
# Bash 安全命令 allowlist（从 Kode-Agent 原版移植）
SAFE_BASH_COMMANDS = frozenset([
    "cat", "ls", "pwd", "echo", "date", "find",
    "grep", "rg", "head", "tail", "wc", "sort",
    "git status", "git log", "git diff", "git show",
    # ... 完整列表见 src/core/permissions/rules/bash.ts
])

# 危险模式 denylist
DANGEROUS_PATTERNS = [
    r"rm\s+.*-[rRf]",
    r">\s*[^>]",      # 覆盖重定向
    r"sudo",
    # ...
]
```

**验收标准**：
- [x] `is_safe_bash_command("ls -la")` → True
- [x] `is_safe_bash_command("rm -rf /")` → False
- [x] `PermissionEngine.has_permissions("bash", {"command": "ls"})` → ALLOWED（无需提示）
- [x] `PermissionEngine.has_permissions("bash", {"command": "rm -rf ."})` → NEEDS_PROMPT
- [x] 权限决定可以持久化到 ProjectConfig 并重新加载

---

#### 任务 1.2：BashTool（Week 2，Day 4-5） ✅

**文件**：`pode_agent/tools/system/bash.py`

**功能**：
- 执行 Shell 命令（使用 `asyncio.create_subprocess_shell`）
- 超时控制（默认 120 秒）
- 捕获 stdout、stderr、exit_code
- 支持中止（通过 `abort_event`）
- 后台任务支持（`background=True` 时异步运行，完整版在 Phase 3）

**验收标准**：
- [x] `BashTool().call(BashInput(command="echo hello"))` → stdout="hello"
- [x] 超时时返回错误，不挂起
- [x] 中止信号触发时停止执行
- [x] `is_read_only()` → False
- [x] `needs_permissions({"command": "ls"})` → False（安全命令）
- [x] `needs_permissions({"command": "npm install"})` → True

---

#### 任务 1.3：文件系统工具（Week 3） ✅

按优先级实现：

1. **FileReadTool** ✅
   - 读取文件内容
   - 支持行号范围（`offset`, `limit`）
   - 处理大文件截断
   - 记录读取时间戳到 `context.read_file_timestamps`

2. **FileWriteTool** ✅
   - 写入/创建新文件
   - 不允许覆盖已存在文件（使用 FileEditTool）
   - 创建必要的父目录

3. **FileEditTool** ✅
   - 精确的字符串替换（old_str → new_str）
   - 验证 old_str 在文件中唯一出现
   - 保存文件前校验
   - 提供 diff 输出

4. **GlobTool** ✅
   - 使用 Python `glob.glob()` / `pathlib.Path.glob()`
   - 支持 `**` 递归匹配
   - 限制返回数量（默认 100 个）

**验收标准**：
- [x] 每个工具有完整的单元测试
- [x] FileEditTool 在 old_str 不唯一时抛出有用的错误
- [x] 文件路径安全检查（不允许访问 cwd 之外的文件）

---

#### 任务 1.4：GrepTool（Week 4，Day 1-2） ✅

**文件**：`pode_agent/tools/search/grep.py`

**实现**：
- 优先使用 `ripgrep`（通过 `subprocess`）
- 降级为 Python `re` 模块（当 `rg` 不可用时）
- 支持 `-i`（忽略大小写）、`-n`（显示行号）、`-l`（只显示文件名）
- 支持文件类型过滤（`--type py`）

---

#### 任务 1.5：LsTool（Week 4，Day 3） ✅

**文件**：`pode_agent/tools/agent/ls.py`

**实现**：
- 列出目录内容
- 显示文件类型（目录/文件/链接）
- 基本的 `.gitignore` 过滤（跳过 `__pycache__`、`.git`、隐藏文件）

---

#### 任务 1.6：会话基础（Week 4，Day 4-5） ✅

**文件**：
- `pode_agent/app/session.py`（骨架）
- `pode_agent/utils/protocol/session_log.py`（JSONL 读写）

**实现**：
- JSONL 日志写入（save_message）
- JSONL 日志读取（load_messages_from_log）
- 日志文件命名（`~/.pode/logs/YYYY-MM-DD_session_fork_N.jsonl`）

---

### Phase 1 完成标志 ✅

```bash
# 非 LLM 工具可以独立测试
Pode bash "ls -la"
Pode bash "cat README.md"
Pode file read README.md
Pode file edit src/main.py --old "foo" --new "bar"
Pode grep "TODO" --type py
```

**验收验证**：
```bash
uv run mypy pode_agent/        # Success: no issues found in 44 source files
uv run ruff check pode_agent/  # All checks passed
uv run pytest tests/ -v        # 198 passed, 1 skipped
```

**实际交付物**：
- 44 个 Python 源文件（pode_agent/）
- 11 个测试文件（tests/）
- 198 个单元测试，全部通过（1 个 Windows symlink 测试跳过）
- 权限系统（PermissionMode 枚举、PermissionEngine 8 步检查、bash 安全规则、文件路径安全、Plan Mode 硬拒绝）
- 7 个工具实现：BashTool、FileReadTool、FileWriteTool、FileEditTool、GlobTool、GrepTool、LsTool
- SessionManager 骨架 + JSONL 日志读写
- mypy strict mode 零错误，ruff 零告警
- 修复了 `infra/shell.py` 中的超时处理 bug（abort_event + timeout 竞态条件）

---

## Phase 2：LLM 集成与会话管理 ✅ 已完成

**目标**：实现完整的 LLM 对话循环（非交互打印模式），支持 Anthropic 和 OpenAI。
**时间**：Weeks 5-7（15 个工作日）
**依赖**：Phase 1 完成
**负责 Agent**：LLM 集成 Agent
**实际完成日期**：2026-04-01

> 📖 **本阶段核心交付物 `app/query.py`（Agentic Loop）的设计规格详见** [agent-loop.md](./agent-loop.md)。  
> Phase 2 实现基础版本（无 Hook、无 Auto-compact）；各组件的完整版本在后续阶段完成（见下表）。

**Agentic Loop 组件分阶段实现一览**（完整设计见 [agent-loop.md](./agent-loop.md)）：

| 组件 | 实现阶段 |
|------|---------|
| `query()` / `query_core()` 基础骨架 | **Phase 2** |
| `ToolUseQueue`（串行版） | **Phase 2** |
| `check_permissions_and_call_tool()`（无 Hook） | **Phase 2** |
| `ToolUseQueue`（并发版，`is_concurrency_safe`） | **Phase 3** |
| System Prompt 动态组装（Plan Mode、Reminders） | **Phase 3** |
| `app/compact.py` 框架 | **Phase 3** |
| Hook 系统（4 个注入点） | **Phase 5** |
| Stop Hook 重入（`MAX_STOP_HOOK_ATTEMPTS`） | **Phase 5** |
| Auto-compact 完整实现（LLM 摘要） | **Phase 6** |

**Phase 2 工具系统子块**（对应 [tools-system.md](./tools-system.md)）：

| 子功能 | 文件 | 说明 |
|--------|------|------|
| `ToolDefinition` 数据类型 | `services/ai/base.py` | 传给 LLM 的工具定义结构 |
| `tool_to_definition()` 转换函数 | `core/tools/base.py` 或 `services/ai/` | Pydantic JSON Schema → ToolDefinition |
| Anthropic 适配器工具格式转换 | `services/ai/anthropic.py` | ToolDefinition → `anthropic.types.ToolParam` |
| OpenAI 适配器工具格式转换 | `services/ai/openai.py` | ToolDefinition → `openai.types.ChatCompletionToolParam` |

### 任务列表

#### 任务 2.1：Anthropic 适配器（Week 5）

**文件**：`pode_agent/services/ai/anthropic.py`

**功能**：
- 流式查询（`messages.stream()`）
- 工具调用（tool_use）支持
- Extended thinking（claude-3.5-sonnet-thinking）
- Bedrock 支持（通过 `ANTHROPIC_BEDROCK_*` 环境变量）
- 错误处理（速率限制、认证错误、网络错误）

**验收标准**：
- [x] 基本文本查询成功
- [x] 工具调用返回正确的 tool_use block
- [x] 速率限制时自动退避重试
- [x] Mock 测试通过（不调用真实 API）

---

#### 任务 2.2：OpenAI 适配器（Week 6，Day 1-3） ✅

**文件**：`pode_agent/services/ai/openai.py`

**功能**：
- Chat Completions API 流式
- Function calling / tool_choice
- `reasoning_effort` 参数（GPT-5）
- 代理支持
- 自定义 `base_url`（支持 Azure OpenAI）

---

#### 任务 2.3：ModelAdapterFactory（Week 6，Day 4-5） ✅

**文件**：`pode_agent/services/ai/factory.py`

**功能**：
- 根据模型名路由到正确的 Provider
- 管理模型能力（max tokens、支持 thinking 等）
- 支持自定义 provider 注册

---

#### 任务 2.4：消息规范化（Week 6，Day 5 - Week 7，Day 1） ✅

**文件**：`pode_agent/utils/messages/normalizer.py`

**功能**：
- Anthropic 消息格式 ↔ 通用 Message 格式转换
- OpenAI 消息格式 ↔ 通用 Message 格式转换
- 工具结果消息格式化

---

#### 任务 2.5：Agentic Loop 核心引擎（Week 7，Day 1-3） ✅

**文件**：`pode_agent/app/query.py`（新建）

**功能**（对应 [agent-loop.md](./agent-loop.md) Phase 2 范围）：
- `query()` 外层入口：处理 @mention，委托给 `query_core()`
- `query_core()` 递归主循环：auto_compact → build_system_prompt → query_llm → 工具执行 → 递归
- `ToolUseQueue`（串行版本）：单工具顺序执行，验证基本流程（并发版本在 Phase 3 实现）
- `check_permissions_and_call_tool()`：Pre-hook（占位）→ Pydantic 验证 → 权限检查 → `tool.call()` → Post-hook（占位）
- `_handle_no_tool_use()`：Stop Hook 占位（直接终止，Phase 5 实现真正的重入）

**注意**：本任务实现的是**不含 Hook、不含 Auto-compact** 的最小可用版本。  
Hook 系统在 Phase 5 实现，Auto-compact 在 Phase 6 实现。

> 📖 完整设计规格见 [docs/agent-loop.md](./agent-loop.md)

---

#### 任务 2.6：完整会话管理器（Week 7，Day 3-4） ✅

**文件**：`pode_agent/app/session.py`（完整实现）

**功能**：
- `process_input()` 实现：构建初始消息，调用 `app/query.py: query()`
- 成本追踪
- 会话恢复（从 JSONL 加载历史）
- 中止处理（`abort_event`）
- 权限决策等待机制（`wait_for_permission_decision()`）

> ⚠️ `process_input()` 本身不实现循环逻辑，仅委托给 `query()`。

---

#### 任务 2.7：非交互打印模式（Week 7，Day 5） ✅

**文件**：`pode_agent/app/print_mode.py`

**功能**：
- 单次查询 + 打印结果（类似 `kode -p "..."` 或 `echo "..." | kode`）
- JSON 输出模式（`--output-format json`）
- 退出码（0=成功，1=错误，2=权限拒绝）

**验收标准**：
- [x] `Pode "What is 2+2?"` 打印回答然后退出
- [x] 工具调用在打印模式下正确执行
- [x] `Pode -p "list files" --output-format json` 输出有效 JSON

---

### Phase 2 完成标志 ✅

**Agentic Loop 核心引擎交付物**（对应 [agent-loop.md](./agent-loop.md)）：
- [x] `app/query.py`: `query()` / `query_core()` 递归主循环
- [x] `app/query.py`: `ToolUseQueue`（串行版，Phase 3 升级为并发版）
- [x] `app/query.py`: `check_permissions_and_call_tool()`（含权限检查，不含 Hook）
- [ ] Hook 系统（Phase 5 实现）
- [ ] Auto-compact（Phase 6 实现）

```bash
# MVP 可用
export ANTHROPIC_API_KEY=sk-ant-...
pode "What files are in this directory?"
# 期望：调用 GlobTool，返回文件列表

pode "Edit main.py to add a docstring to main()"
# 期望：调用 FileReadTool、FileEditTool，完成编辑

pode "Run the tests and tell me if they pass"
# 期望：调用 BashTool("pytest tests/ -v")，分析结果
```

**验收验证**：
```bash
uv run mypy pode_agent/        # Success: no issues found in 58 source files
uv run ruff check pode_agent/  # All checks passed
uv run pytest tests/ -q        # 318 passed, 1 skipped
```

**实际交付物**：
- 58 个 Python 源文件（pode_agent/），新增 14 个
- 11 个新测试文件，共 318 个测试全部通过
- Anthropic 适配器：流式查询、tool_use、Extended thinking、Bedrock 支持、错误重试
- OpenAI 适配器：Chat Completions 流式、Function calling、reasoning_effort、代理支持
- ModelAdapterFactory：模型名前缀路由、能力查询、自定义 provider 注册
- 消息规范化：Anthropic/OpenAI 格式互转、工具结果构建
- Agentic Loop 核心引擎：`query()`/`query_core()` 递归主循环、串行 ToolUseQueue、权限检查管道
- SessionManager 完整实现：`process_input()`、成本追踪、权限决议、JSONL 恢复
- Print Mode：单次查询非交互执行，text/JSON 输出，退出码语义
- CLI 集成：`pode "prompt"` + --model/-m, --output-format/-f, --verbose, --safe
- mypy strict mode 零错误，ruff 零告警

---

## Phase 3：完整工具集 ✅ 已完成

**目标**：实现所有 25+ 个工具，并升级 Agentic Loop 引擎（并发 ToolUseQueue、完整 System Prompt 组装）；同时实现 Plan Mode 骨架。
**时间**：Weeks 8-10（15 个工作日）
**依赖**：Phase 2 完成
**负责 Agent**：工具实现 Agent（可以多个 Agent 并行）
**实际完成日期**：2026-04-02

**Phase 3 同时完成的 Agentic Loop 升级**（对应 [agent-loop.md](./agent-loop.md)）：
- `ToolUseQueue` 并发版本（`is_concurrency_safe` + `asyncio.gather` + sibling abort）
- System Prompt 动态组装完整版（Plan Mode、Reminders 注入）
- `app/compact.py`：Auto-compact 框架（触发逻辑，压缩策略在 Phase 6 完善）

**Phase 3 工具系统子块**（对应 [tools-system.md](./tools-system.md)）：

| 子功能 | 文件 | 说明 |
|--------|------|------|
| `ToolLoader`（内置工具加载） | `core/tools/loader.py` | 仅加载内置工具；MCP/插件在 Phase 5 |
| `get_enabled_tools()`（完整过滤逻辑） | `core/tools/registry.py` | safe_mode + permission_mode + command_allowed_tools |
| 工具 → ToolDefinition 转换 | `core/tools/base.py` | `tool_to_definition()` 供适配器使用 |
| ToolUseQueue 并发版 | `app/query.py` | `is_concurrency_safe` + barrier + sibling abort |

**Phase 3 Plan Mode 子块**（对应 [plan-mode.md](./plan-mode.md)）：

| 子功能 | 文件 | 说明 |
|--------|------|------|
| `Plan` / `PlanStep` Pydantic 模型 | `app/plan.py` 或 `types/plan.py` | 数据结构定义 |
| Plan JSONL 事件类型 | `types/session_events.py` | `plan_created`/`plan_approved` 等 |
| `EnterPlanModeTool` | `tools/agent/plan_mode.py` | 切换 `PermissionMode.PLAN` + 进度提示 |
| `ExitPlanModeTool` | `tools/agent/plan_mode.py` | 输出 Plan 对象 + 重置 permission_mode |
| Plan Mode System Prompt Additions | `services/system/system_prompt.py` | `build_system_prompt()` 中注入 PLAN 模式提示 |
| `load_plan_from_log()` | `app/session.py` | JSONL replay 恢复活跃计划 |

### 任务列表（按优先级）

#### 高优先级工具（Week 8）

| 工具 | 文件 | 核心功能 |
|------|------|---------|
| MultiEditTool | `tools/filesystem/multi_edit.py` | 原子性多文件编辑 |
| NotebookReadTool | `tools/filesystem/notebook_read.py` | 读取 `.ipynb` 文件 |
| NotebookEditTool | `tools/filesystem/notebook_edit.py` | 编辑 notebook 单元格 |
| AskUserQuestionTool | `tools/interaction/ask_user.py` | 提问用户（交互模式） |
| TodoWriteTool | `tools/interaction/todo_write.py` | 写入/更新 TODO 列表 |

#### 中优先级工具（Week 9）

| 工具 | 文件 | 核心功能 |
|------|------|---------|
| WebFetchTool | `tools/network/web_fetch.py` | HTTP GET/POST，返回内容 |
| WebSearchTool | `tools/network/web_search.py` | Bing/SerpAPI/Exa 搜索 |
| LspTool | `tools/search/lsp.py` | 调用 LSP 服务器查询 |
| KillShellTool | `tools/system/kill_shell.py` | 终止后台任务 |
| TaskOutputTool | `tools/system/task_output.py` | 读取后台任务输出 |

#### 低优先级工具（Week 10）

| 工具 | 文件 | 核心功能 |
|------|------|---------|
| AskExpertModelTool | `tools/ai/ask_expert.py` | 调用另一个 AI 模型 |
| SkillTool | `tools/ai/skill.py` | 执行已安装的 Skill |
| **EnterPlanModeTool** | `tools/agent/plan_mode.py` | **进入计划模式**（详见 plan-mode.md） |
| **ExitPlanModeTool** | `tools/agent/plan_mode.py` | **退出计划模式，输出 Plan 对象** |
| TaskTool | `tools/agent/task.py` | 子任务管理（完整版在 Phase 5） |
| SlashCommandTool | `tools/interaction/slash_command.py` | 执行自定义命令 |

#### Web 搜索提供商（Week 10）

实现 WebSearchTool 的多个后端：
- Bing Web Search API
- SerpAPI
- Exa
- 降级：直接访问 DuckDuckGo（无 API key）

---

### Phase 3 完成标志 ✅

```bash
# 已验证通过
uv run mypy pode_agent/        # Success: no issues found in 80 source files
uv run ruff check pode_agent/  # All checks passed
uv run pytest tests/ -q --ignore=tests/integration  # 623 passed, 4 skipped
```

**实际交付物**：
- 80 个 Python 源文件（pode_agent/），新增 22 个
- 15 个新工具实现：MultiEditTool, NotebookReadTool, NotebookEditTool, AskUserQuestionTool, TodoWriteTool, WebFetchTool, WebSearchTool, LspTool, KillShellTool, TaskOutputTool, EnterPlanModeTool, ExitPlanModeTool, AskExpertModelTool, SkillTool, TaskTool, SlashCommandTool
- Plan Mode 数据模型：Plan, PlanStep, PlanStatus, StepStatus
- Plan Mode 事件类型：PLAN_CREATED, PLAN_APPROVED, PLAN_STEP_START, PLAN_STEP_DONE, PLAN_DONE, PLAN_CANCELLED
- ToolLoader + get_enabled_tools() 过滤框架
- 并发 ToolUseQueue（is_concurrency_safe 分组 + asyncio.gather 并行执行）
- 动态 System Prompt 组装（plan mode 注入 + tool reminders + active plan + todos）
- Auto-compact 框架（阈值检查 + 消息截断策略）
- 623 个单元测试全部通过（新增 305 个）
- mypy strict mode 零错误，ruff 零告警

```bash
Pode tools list
# 期望：显示所有 25+ 工具

Pode "Search the web for 'Python asyncio best practices' and summarize"
# 期望：调用 WebSearchTool，返回摘要

Pode "Read my notebook.ipynb and explain what it does"
# 期望：调用 NotebookReadTool，返回解释

Pode "Help me refactor auth.py"
# 期望：LLM 自动调用 EnterPlanModeTool，探索代码后输出 Plan；
#       用户批准后进入执行阶段
```

---

## Phase 4：终端 UI

**目标**：实现基于 Textual 的完整 REPL 界面，以及 Plan Mode 的审批 UI 和进度追踪。  
**时间**：Weeks 11-13（15 个工作日）  
**依赖**：Phase 2 完成（可与 Phase 3 并行）  
**负责 Agent**：UI 开发 Agent

**Phase 4 Plan Mode UI 子块**（对应 [plan-mode.md](./plan-mode.md)）：

| 子功能 | 文件 | 说明 |
|--------|------|------|
| 计划审批 Widget | `ui/widgets/plan_approval.py` | 展示 Plan 对象；批准/拒绝按钮 |
| 计划执行进度 Widget | `ui/widgets/plan_progress.py` | 展示步骤列表，已完成步骤标记 ✓ |
| SessionEvent 处理（`plan_created`/`plan_step_done`） | `ui/screens/repl_screen.py` | 监听计划事件，更新 UI |

### 任务列表

#### 任务 4.1：基础 Textual 应用框架（Week 11，Day 1-2）

**文件**：
- `pode_agent/ui/app.py` — PodeApp（Textual App 子类）
- `pode_agent/ui/theme.py` — 主题（深色/浅色）
- `pode_agent/ui/styles.tcss` — Textual CSS 样式

---

#### 任务 4.2：消息显示 Widget（Week 11，Day 3-5）

**文件**：`pode_agent/ui/widgets/message_view.py`

**功能**：
- 滚动消息列表
- 用户消息（右对齐，不同颜色）
- AI 响应（Markdown 渲染 via `rich.Markdown`）
- 代码块语法高亮
- 工具调用显示（工具名、参数摘要）
- 工具结果折叠显示

---

#### 任务 4.3：输入框 Widget（Week 12，Day 1-2）

**文件**：`pode_agent/ui/widgets/prompt_input.py`

**功能**：
- 多行文本输入
- 历史记录（上下键）
- 粘贴支持
- Ctrl+C 取消当前请求
- Ctrl+D 退出
- Tab 补全（文件名、命令）

---

#### 任务 4.4：权限对话框（Week 12，Day 3-5）

**文件**：`pode_agent/ui/widgets/permission_dialog.py`

**功能**：
- 工具名和操作描述
- 每种工具的专属信息（BashTool: 显示命令；FileEdit: 显示 diff）
- 三个选项：[允许一次] [本会话允许] [始终允许] [拒绝]
- 键盘快捷键

---

#### 任务 4.5：状态栏和费用显示（Week 13，Day 1-2）

**文件**：
- `pode_agent/ui/widgets/status_bar.py`
- `pode_agent/ui/widgets/cost_summary.py`

**功能**：
- 当前模型名称
- 会话费用（累计 USD）
- 请求进行中指示器（spinner）
- 连接状态

---

#### 任务 4.6：REPL Screen 整合（Week 13，Day 3-5）

**文件**：`pode_agent/ui/screens/repl_screen.py`

**功能**：
- 整合所有 Widget
- 连接 SessionManager 事件到 UI 更新
- 键盘快捷键：
  - `Ctrl+C`: 取消当前请求
  - `Ctrl+K`: 清空历史（新建会话）
  - `Ctrl+R`: 恢复上次会话
  - `Ctrl+M`: 切换模型

---

### Phase 4 完成标志

```bash
Pode  # 不带参数，启动 REPL
# 期望：显示 Textual 界面，可以输入问题，看到 AI 响应和工具调用
```

**截图测试**：使用 `textual run --screenshot` 生成界面截图用于回归测试。

---

## Phase 5：MCP 与插件系统

**目标**：实现 MCP 客户端/服务端、插件系统、ACP 协议，以及 Agentic Loop 的 Hook 系统。  
**时间**：Weeks 14-16（15 个工作日）  
**依赖**：Phase 3 完成  
**负责 Agent**：协议集成 Agent

**Phase 5 同时完成的 Agentic Loop 升级**（对应 [agent-loop.md](./agent-loop.md)）：
- Hook 系统完整实现（4 个注入点：`run_user_prompt_submit_hooks`、`run_pre_tool_use_hooks`、`run_post_tool_use_hooks`、`run_stop_hooks`）
- Stop Hook 重入机制（`MAX_STOP_HOOK_ATTEMPTS = 5`）
- `services/hooks/runner.py` 模块

**Phase 5 工具系统子块**（对应 [tools-system.md](./tools-system.md)）：

| 子功能 | 文件 | 说明 |
|--------|------|------|
| `ToolLoader` MCP 工具加载 | `core/tools/loader.py` | `_load_mcp_tools()`：包装为 Pode Tool |
| `ToolLoader` 插件工具加载 | `core/tools/loader.py` | `_load_plugin_tools()`：扫描 entry_points |
| `wrap_mcp_tool_as_pode_tool()` | `services/mcp/tools.py` | MCP 工具 → Tool ABC 包装 |
| Hook 对工具输入的影响 | `services/hooks/runner.py` | Pre-Tool Hook 可 block/modify input |

**Phase 5 Plan Mode 子块**（对应 [plan-mode.md](./plan-mode.md)）：

| 子功能 | 说明 |
|--------|------|
| `TaskTool`（子任务 Agent） | 支持将计划步骤委托给独立子 Agent 执行 |

### 任务列表

#### 任务 5.1：MCP 客户端（Week 14）

**文件**：`pode_agent/services/mcp/client.py`

**功能**：
- 连接 stdio 类型 MCP 服务器
- 连接 SSE 类型 MCP 服务器
- 连接 HTTP 类型 MCP 服务器
- 列出工具和资源
- 调用工具
- 读取资源

**验收标准**：
- [ ] 能连接 `mcp install npx @anthropic-ai/mcp-server-filesystem`
- [ ] 通过 `Pode mcp list` 查看已配置的服务器
- [ ] MCP 工具在 AI 对话中可以被调用

---

#### 任务 5.2：MCP 服务端（Week 15，Day 1-2）

**文件**：`pode_agent/entrypoints/mcp_server.py`

**功能**：
- 将所有 Pode 工具暴露为 MCP 工具
- 实现 `ListTools` 处理器
- 实现 `CallTool` 处理器

**验收标准**：
- [ ] Claude Desktop 可以通过 MCP 协议使用 Pode 作为工具服务器

---

#### 任务 5.3：Skill Marketplace（Week 15，Day 3-5）

**文件**：`pode_agent/services/plugins/marketplace.py`

**功能**：
- 从 GitHub 安装 Skill（`Pode skill install github:owner/repo`）
- 从本地目录安装
- 列出已安装的 Skill
- 删除 Skill
- YAML manifest 验证

---

#### 任务 5.4：自定义命令（Week 16，Day 1-2）

**文件**：`pode_agent/services/plugins/commands.py`

**功能**：
- 从 `~/.Pode/commands/` 加载 YAML/MD 自定义命令
- Bash 执行（`!``command```）
- 文件引用（`@filename`）
- frontmatter 解析（description、category）

---

#### 任务 5.5：ACP 协议（Week 16，Day 3-5）

**文件**：`pode_agent/entrypoints/acp_server.py`

**功能**：
- JSON-RPC over stdio
- 暴露 `ask`、`run`、`tool` 等方法
- 用于被其他 Agent 调用

---

## Phase 6：高级特性与完善

**目标**：完成所有剩余功能，进行性能优化和发布准备。  
**时间**：Weeks 17-20（20 个工作日）  
**依赖**：Phase 5 完成

**Phase 6 同时完成的 Agentic Loop 升级**（对应 [agent-loop.md](./agent-loop.md)）：
- Auto-compact 完整实现（`app/compact.py` 的 LLM 摘要生成策略，Phase 3 仅建立框架）

### 任务列表

#### 任务 6.1：功能完整性验证（Week 17）

对照 Kode-Agent 原版进行功能 checklist 对比：

```bash
# 使用 parity test
KODE_REFERENCE_REPO=/path/to/kode-agent python tests/parity/compare.py
```

---

#### 任务 6.2：多 Provider 支持完善（Week 18）

额外 Provider 实现：

| Provider | 实现文件 |
|----------|---------|
| Mistral | `services/ai/providers/mistral.py` |
| DeepSeek | `services/ai/providers/deepseek.py` |
| Ollama（本地）| `services/ai/providers/ollama.py` |
| Azure OpenAI | `services/ai/providers/azure.py` |
| Gemini | `services/ai/providers/gemini.py` |
| Groq | `services/ai/providers/groq.py` |
| 通用 OpenAI 兼容 | `services/ai/providers/openai_compat.py` |

---

#### 任务 6.3：Auto-compact 完整实现（Week 18）

**文件**：`pode_agent/app/compact.py`（完善 Phase 3 建立的框架）

**功能**：
- LLM 摘要生成策略（调用 LLM 压缩旧消息）
- 消息自动压缩（当 token 超阈值时）
- 智能截断策略（保留最近的对话）
- 长会话处理

> 📖 设计规格见 [agent-loop.md — Auto-compact：自动上下文压缩](./agent-loop.md#auto-compact自动上下文压缩)

---

#### 任务 6.4：Doctor 命令（Week 19，Day 1-2）

**文件**：`pode_agent/ui/screens/doctor.py`

**功能**：
- 检查 API 密钥配置
- 验证 MCP 服务器连接
- 检查依赖工具（ripgrep、git 等）
- 显示版本信息

---

#### 任务 6.5：Auto-updater（Week 19，Day 3-5）

**功能**：
- 检查 PyPI 上的新版本
- 提示用户更新
- `Pode update` 命令

---

#### 任务 6.6：性能优化（Week 20）

**关键优化**：
- 启动时间优化（延迟导入）
- 上下文缓存（`functools.lru_cache`）
- 工具描述缓存
- MCP 连接池

---

#### 任务 6.7：文档完善（Week 20）

**文档**：
- `README.md` — 快速开始
- `docs/configuration.md` — 配置参考
- `docs/tools.md` — 工具参考
- `docs/providers.md` — Provider 配置
- `CONTRIBUTING.md` — 贡献指南
- API 文档（`mkdocs`）

---

#### 任务 6.8：PyPI 发布（Week 20，最后）

```bash
hatch build
hatch publish
# 或：
python -m build && twine upload dist/*
```

---

## 验收标准矩阵

### 每个 Phase 的通用验收标准

| 标准 | Phase 0 | Phase 1 | Phase 2 | Phase 3 | Phase 4 | Phase 5 | Phase 6 |
|------|---------|---------|---------|---------|---------|---------|---------|
| mypy 零错误 | ✅ Done | ✅ Done (44 files) | ✅ Done (58 files) | ✅ Done (80 files) | ✅ | ✅ | ✅ |
| ruff lint 通过 | ✅ Done | ✅ Done | ✅ Done | ✅ Done | ✅ | ✅ | ✅ |
| pytest 通过 | ✅ Done (35) | ✅ Done (198) | ✅ Done (318) | ✅ Done (623) | ✅ | ✅ | ✅ |
| 新功能有测试 | ✅ Done | ✅ Done (11 files) | ✅ Done (22 files) | ✅ Done (37 files) | ✅ | ✅ | ✅ |
| 文档更新 | ✅ Done | ✅ Done | ✅ Done | ✅ Done | ✅ | ✅ | ✅ |

### 最终发布验收标准

- [ ] 所有 25+ 工具通过功能测试
- [ ] Anthropic + OpenAI Provider 通过集成测试
- [ ] MCP 客户端连接 3 个真实 MCP 服务器
- [ ] REPL 界面在 macOS + Linux 上正常显示
- [ ] `pip install Pode-agent` 在 Python 3.11、3.12 上成功
- [ ] 与 Kode-Agent 原版 parity 测试通过率 > 95%
- [ ] 启动时间 < 1 秒

---

## 依赖关系图

```
Phase 0 (骨架)
    │
    ├── Phase 1 (核心工具) ──────────────────────────────┐
    │       │                                            │
    │       └── Phase 2 (LLM 集成) ──────────────────── │
    │               │                                    │
    │               ├── Phase 3 (完整工具集) ─────────── │
    │               │       │                           ▼
    │               │       └── Phase 5 (MCP + 插件) → Phase 6 (完善)
    │               │
    │               └── Phase 4 (终端 UI) ─────────────▶ Phase 6
    │
    └─ (Phase 3 和 Phase 4 可以并行进行)
```

**并行开发说明**：
- Phase 3（工具集）和 Phase 4（UI）可以由不同 Agent 并行实施
- Phase 5（MCP）需要 Phase 3 的工具系统就绪
- Phase 6（完善）需要等所有前序阶段完成

---

## 给 Code Agent 的工作指引

### 开始一个阶段前

1. 阅读 [modules.md](./modules.md) 中对应模块的规范
2. 阅读 [api-specs.md](./api-specs.md) 中相关的接口契约
3. 如果涉及 `app/` 层（Phase 2 及以后），**必须阅读 [agent-loop.md](./agent-loop.md)**
4. 确认前序阶段的验收标准都已通过

### 实施每个任务时

1. 先写测试（TDD 风格）
2. 实现代码使测试通过
3. 运行 `mypy` 和 `ruff` 检查
4. 更新相关文档

### 每个任务完成后

```bash
# 必须全部通过
mypy pode_agent/
ruff check pode_agent/
pytest tests/ -v --cov=pode_agent
```
