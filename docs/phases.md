# Pode-Agent 分阶段实施计划

> 版本：1.6.0 | 状态：Phase 5 已完成 | 更新：2026-04-03
> **给 Code Agent 的说明**：请严格按照阶段顺序实施。每个阶段结束时运行对应验收测试，通过后才能进入下一阶段。

---

## 目录

1. [总体时间表](#总体时间表)
2. [Phase 0：项目骨架（Week 1）](#phase-0项目骨架)
3. [Phase 1：核心功能（Weeks 2-4）](#phase-1核心功能)
4. [Phase 2：LLM 集成与会话管理（Weeks 5-7）](#phase-2llm-集成与会话管理)
5. [Phase 3：完整工具集（Weeks 8-10）](#phase-3完整工具集)
6. [Phase 4：终端 UI（React + Ink v5）（Weeks 11-13）](#phase-4终端-uireact--ink-v5)
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
| M3: 完整 UI | Week 13 | React + Ink REPL 界面完整 |
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

> 📖 **工具系统的目录结构、注册方式、权限耦合**详见 [tools-system.md](./tools-system.md)。  
> **Phase 1 仅实现 `PermissionMode.PLAN` 的 enum 定义**，Plan Mode 完整骨架在 Phase 3 实现（见 [plan-mode.md — 分阶段实现建议](./plan-mode.md#分阶段实现建议)）。

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
| `tool_to_definition()` 转换函数 | `core/tools/base.py` | Pydantic JSON Schema → ToolDefinition |
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
- [ ] Hook 系统（Phase 5 实现）✅ 已完成
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

> 📖 **工具系统完整规格**（注册/发现/权限/并发）详见 [tools-system.md](./tools-system.md)。  
> **Plan Mode 骨架**（EnterPlanModeTool/ExitPlanModeTool/plan_state.py/System Prompt 注入）在本阶段实现，完整设计详见 [plan-mode.md](./plan-mode.md)。

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
| TaskTool | `tools/agent/task.py` | SubAgent 管理工具 — 创建/执行/恢复子代理（Phase 5 完整实现，见 [subagent-system.md](./subagent-system.md)） |
| SlashCommandTool | `tools/interaction/slash_command.py` | 执行自定义命令 |

**Phase 3 Plan Mode 骨架实现清单**（对应 [plan-mode.md — 分阶段实现建议](./plan-mode.md#分阶段实现建议)）：

| 组件 | 文件 | 说明 |
|------|------|------|
| Plan Mode 状态机 | `app/plan_state.py` | `enter/exit/is_enabled`、Slug 生成、计划文件路径 |
| Plan Mode 工具 | `tools/agent/plan_mode.py` | `EnterPlanModeTool` / `ExitPlanModeTool` |
| 权限引擎 Plan Mode 约束 | `core/permissions/engine.py` | `PermissionMode.PLAN` 下只允许只读工具 |
| System Prompt 注入 | `app/query.py` `build_system_prompt()` | `get_plan_mode_system_prompt_additions()` |
| canUseTool 拦截 | `app/query.py` | Plan Mode 下拦截非只读工具 |
| `TURNS_BETWEEN_ATTACHMENTS` 节流 | `app/plan_state.py` | 避免 reminder 占用过多 token |

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
- 16 个新工具实现：MultiEditTool, NotebookReadTool, NotebookEditTool, AskUserQuestionTool, TodoWriteTool, WebFetchTool, WebSearchTool, LspTool, KillShellTool, TaskOutputTool, EnterPlanModeTool, ExitPlanModeTool, AskExpertModelTool, SkillTool, TaskTool, SlashCommandTool
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

**Plan Mode 骨架验收标准**（完整规格见 [plan-mode.md](./plan-mode.md)）：
- [ ] Agent 在面对复杂任务时主动调用 `EnterPlanModeTool`
- [ ] Plan Mode 激活期间，`FileWriteTool`/`BashTool` 的写操作被拒绝，返回"permission denied"
- [ ] `GlobTool`/`GrepTool`/`FileReadTool` 在 Plan Mode 下正常可用
- [ ] `ExitPlanModeTool` 调用后恢复完整工具集
- [ ] 计划文件正确写入 `~/.pode/plans/{slug}.md`
- [ ] system-reminder 在 Plan Mode 激活时注入 LLM 上下文

---

## Phase 4：终端 UI（React + Ink v5） ✅ 已完成

**目标**：基于 React + Ink v5 深度复刻 Kode-Agent 终端 UI，通过 JSON-RPC over stdio 与 Python 后端通信。
**时间**：Weeks 11-13（15 个工作日）
**依赖**：Phase 2 完成（可与 Phase 3 并行）
**负责 Agent**：UI 开发 Agent（需要 TypeScript/React 经验）
**实际完成日期**：2026-04-02

**Phase 4 Plan Mode UI 子块**（对应 [plan-mode.md](./plan-mode.md)）：

| 子功能 | 文件 | 说明 |
|--------|------|------|
| 计划审批组件 | `src/ui/components/permissions/EnterPlanModePermissionRequest.tsx` | 展示 Plan 对象；批准/拒绝选项 |
| 计划执行进度组件 | `src/ui/components/messages/TaskProgressMessage.tsx` | 展示步骤列表，已完成步骤标记 ✓ |
| SessionEvent 处理 | `src/ui/screens/REPL.tsx` | 监听 JSON-RPC 事件，更新 UI 状态 |

### 任务列表

#### 任务 4.1：前端工程骨架 + JSON-RPC 桥接（Week 11，Day 1-2） ✅

**文件**：
- `package.json` — Bun + React + Ink v5 依赖（ink ≥5.2, react ≥18.3, chalk ≥5.4, @inkjs/ui ≥2.0, ink-text-input ≥6.0, ink-select-input ≥6.2, cli-highlight ≥2.1, diff ≥7.0, figures ≥6.1）
- `tsconfig.json` — TypeScript 配置
- `bunfig.toml` — Bun 配置
- `src/ui/index.tsx` — Ink render 入口
- `src/ui/theme.ts` — 4 套主题（dark/light/dark-daltonized/light-daltonized）
- `src/ui/rpc/client.ts` — JSON-RPC over stdio 客户端
- `src/ui/rpc/transport.ts` — Stdio 传输层
- `pode_agent/entrypoints/ui_bridge.py` — Python 端 JSON-RPC 服务端

**验收标准**：
- [x] `bun install` 成功安装所有前端依赖
- [x] `bun run dev` 启动 Ink UI 显示欢迎画面
- [x] Python JSON-RPC 服务端能接收/响应基本消息
- [x] 前端能通过 JSON-RPC 与 Python 后端通信

---

#### 任务 4.2：REPL.tsx 核心 Screen（Week 11，Day 3 - Week 12，Day 1） ✅

**文件**：`src/ui/screens/REPL.tsx`（~779 行，从 Kode-Agent `src/ui/screens/REPL.tsx` 移植）

**功能**（1:1 复刻 Kode-Agent REPL）：
- 完整的 React 状态管理（messages, isLoading, abortController, toolUseConfirm 等）
- 消息渲染管线：`<Static>` 已提交消息 + Transient 实时消息
- PermissionProvider Context 集成
- 消息重排序和规范化（normalizeMessages + reorderMessages）
- 模式切换（prompt/bash/koding）
- 会话恢复（fork number 管理）

**验收标准**：
- [x] REPL.tsx 能正确渲染消息列表（Static + Transient 分离）
- [x] 能接收 JSON-RPC 推送的流式消息并实时更新
- [x] 中断信号能取消正在进行的请求

---

#### 任务 4.3：消息组件（Week 12，Day 2-4） ✅

**文件**（从 Kode-Agent `src/ui/components/messages/` 移植）：

| 组件 | 文件 | 功能 |
|------|------|------|
| AssistantTextMessage | `messages/AssistantTextMessage.tsx` | Markdown 渲染、费用显示、bash 通知解析 |
| AssistantToolUseMessage | `messages/AssistantToolUseMessage.tsx` | 工具调用渲染（排队/执行中/错误状态） |
| AssistantThinkingMessage | `messages/AssistantThinkingMessage.tsx` | Extended thinking 显示 |
| UserTextMessage | `messages/UserTextMessage.tsx` | 用户文本显示 |
| UserImageMessage | `messages/UserImageMessage.tsx` | 用户图片附件显示 |
| TaskProgressMessage | `messages/TaskProgressMessage.tsx` | 任务进度指示 |
| ...（共 15 个消息类型组件） | | |

**文件**（工具结果组件，从 `messages/user-tool-result-message/` 移植）：

| 组件 | 文件 |
|------|------|
| UserToolResultMessage | `user-tool-result-message/UserToolResultMessage.tsx` |
| UserToolSuccessMessage | `user-tool-result-message/UserToolSuccessMessage.tsx` |
| UserToolErrorMessage | `user-tool-result-message/UserToolErrorMessage.tsx` |
| UserToolRejectMessage | `user-tool-result-message/UserToolRejectMessage.tsx` |

---

#### 任务 4.4：权限对话框组件（Week 12，Day 4 - Week 13，Day 1） ✅

**文件**（从 Kode-Agent `src/ui/components/permissions/` 移植）：

| 组件 | 文件 | 功能 |
|------|------|------|
| PermissionRequest | `permissions/PermissionRequest.tsx` | 权限分发器（路由到具体组件） |
| BashPermissionRequest | `permissions/BashPermissionRequest.tsx` | Bash 命令审批 |
| FileEditPermissionRequest | `permissions/FileEditPermissionRequest.tsx` | 文件编辑审批（含 diff 显示） |
| FileWritePermissionRequest | `permissions/FileWritePermissionRequest.tsx` | 文件写入审批（含 diff 显示） |
| FilesystemPermissionRequest | `permissions/FilesystemPermissionRequest.tsx` | 只读文件系统工具审批 |
| WebFetchPermissionRequest | `permissions/WebFetchPermissionRequest.tsx` | Web 请求 URL 审批 |
| EnterPlanModePermissionRequest | `permissions/EnterPlanModePermissionRequest.tsx` | 计划模式入口审批 |
| ExitPlanModePermissionRequest | `permissions/ExitPlanModePermissionRequest.tsx` | 计划模式出口审批 |
| FallbackPermissionRequest | `permissions/FallbackPermissionRequest.tsx` | 通用权限对话框 |
| ...（共 15+ 个权限组件） | | |

**验收标准**：
- [x] 每个工具类型有对应的权限对话框
- [x] 支持 Allow Once / Allow for Session / Always Allow / Reject 四种选项
- [x] 文件编辑权限显示 diff

---

#### 任务 4.5：PromptInput + Hooks（Week 13，Day 1-3） ✅

**文件**（从 Kode-Agent `src/ui/` 移植）：

| 组件/Hook | 文件 | 功能 |
|-----------|------|------|
| PromptInput | `components/PromptInput.tsx` | ~860 行，输入模式/补全/历史/粘贴/编辑器集成 |
| TextInput | `components/TextInput.tsx` | 底层文本输入（bracketed paste/光标/多行） |
| useTerminalSize | `hooks/useTerminalSize.ts` | 全局终端尺寸跟踪 |
| useTextInput | `hooks/useTextInput.ts` | 文本输入 hook |
| useUnifiedCompletion | `hooks/useUnifiedCompletion.ts` | 自动补全（命令/文件/agent） |
| useArrowKeyHistory | `hooks/useArrowKeyHistory.ts` | 上下键历史导航 |
| useCancelRequest | `hooks/useCancelRequest.ts` | ESC 取消请求 |
| useCanUseTool | `hooks/useCanUseTool.ts` | 工具权限检查 |
| useCostSummary | `hooks/useCostSummary.ts` | 费用追踪 |
| useExitOnCtrlCD | `hooks/useExitOnCtrlCD.ts` | 双击 Ctrl+C/D 退出 |
| ...（共 16 个 hooks） | | |

---

#### 任务 4.6：辅助 Screen + 整合（Week 13，Day 3-5） ✅

**文件**（从 Kode-Agent `src/ui/screens/` 移植）：

| Screen | 文件 | 功能 |
|--------|------|------|
| ResumeConversation | `screens/ResumeConversation.tsx` | 会话恢复选择器 |
| LogList | `screens/LogList.tsx` | 历史记录浏览 |
| Doctor | `screens/Doctor.tsx` | 健康检查界面 |
| MCPServerApproval | `screens/MCPServerApproval.tsx` | MCP 服务器审批流程 |

**其他辅助组件**：
- `components/Logo.tsx` — 欢迎横幅
- `components/Onboarding.tsx` — 首次运行向导
- `components/TrustDialog.tsx` — 安全模式信任确认
- `components/Config.tsx` — 设置界面
- `components/Help.tsx` — 帮助显示
- `components/binary-feedback/` — A/B 反馈组件（3 个文件）
- `components/model-selector/` — 模型选择组件（3 个文件）
- `components/custom-select/` — 自定义选择器（4 个文件）

---

### Phase 4 完成标志 ✅

```bash
# 启动 REPL
pode  # 不带参数，通过 Bun 启动 React + Ink UI
# 期望：显示 Ink 界面，可以输入问题，看到 AI 响应和工具调用
```

**验收验证**：
```bash
bun install                    # 前端依赖安装成功
bun run dev                    # Ink UI 开发模式启动
uv run mypy pode_agent/        # Success: no issues found in 80 source files
uv run ruff check pode_agent/  # All checks passed
uv run pytest tests/ -q        # 638 passed, 4 skipped
```

**实际交付物**：
- 80 个 Python 源文件（pode_agent/），新增 1 个（ui_bridge.py），修改 2 个（cli.py, test_ui_bridge.py）
- 30 个 TypeScript 源文件（src/ui/），新建完整前端工程
- JSON-RPC over stdio 双向通信：Python 端 `UIBridge` + Bun 端 `JsonRpcPeer`
- 4 个 Screen 组件：REPL（主屏幕）、ResumeConversation、Doctor、Help
- 1 个 Context 组件：PermissionContext（权限决议管理）
- 6 个 Hook 模块：useSession、useTerminalSize、useInterval、useArrowKeyHistory、useDoublePress 等
- 12+ 消息组件：AssistantText/ToolUse/Thinking、UserText/ToolResult（success/error/reject）、TaskProgress
- 权限对话框：PermissionRequest 分发器，支持 bash/file_edit/file_write/filesystem/web_fetch/plan_mode/ask_user 共 7 种工具类别
- 辅助组件：PromptInput（含历史导航、Ctrl 快捷键、双击退出）、HighlightedCode、StructuredDiff、ToolUseLoader、Cost、RequestStatusIndicator
- 638 个单元测试全部通过（新增 15 个 UI bridge 测试）
- mypy strict mode 零错误，ruff 零告警

---

## Phase 5：MCP 与插件系统 ✅ 已完成

**目标**：实现 MCP 客户端/服务端、插件系统、ACP 协议，以及 Agentic Loop 的 Hook 系统。  
**时间**：Weeks 14-16（15 个工作日）  
**依赖**：Phase 3 完成  
**负责 Agent**：协议集成 Agent
**实际完成日期**：2026-04-03

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
| `TaskTool`（子任务 Agent） | 支持将计划步骤委托给独立子 Agent 执行。完整设计见 [subagent-system.md](./subagent-system.md) |

**Phase 5 Skill System 子块**（对应 [skill-system.md](./skill-system.md)）：

| 子功能 | 文件 | 说明 |
|--------|------|------|
| `CustomCommandFrontmatter` 数据模型 | `types/skill.py` | Pydantic 数据结构定义 |
| `load_custom_commands()` 发现与加载 | `services/plugins/commands.py` | 8 目录扫描 + 去重 |
| Plugin 运行时 | `services/plugins/runtime.py` | plugin.json 解析与加载 |
| Marketplace CRUD | `services/plugins/marketplace.py` | 安装/卸载/启用/禁用 |
| Plugin 验证 | `services/plugins/validation.py` | schema 和路径校验 |
| contextModifier 机制 | `core/tools/base.py` + `app/query.py` | ToolOutput 新字段 + 应用 |
| SkillTool 完整实现 | `tools/ai/skill.py` | 替换 Phase 3 骨架 |
| SlashCommandTool 完整实现 | `tools/interaction/slash_command.py` | 自定义命令支持 |

### 任务列表

#### 任务 5.1：MCP 客户端（Week 14） ✅

**文件**：`pode_agent/services/mcp/client.py`

**功能**：
- 连接 stdio 类型 MCP 服务器
- 连接 SSE 类型 MCP 服务器
- 连接 HTTP 类型 MCP 服务器
- 列出工具和资源
- 调用工具
- 读取资源

**验收标准**：
- [x] 能连接 `mcp install npx @anthropic-ai/mcp-server-filesystem`
- [x] 通过 `Pode mcp list` 查看已配置的服务器
- [x] MCP 工具在 AI 对话中可以被调用

---

#### 任务 5.2：MCP 服务端（Week 15，Day 1-2） ✅

**文件**：`pode_agent/entrypoints/mcp_server.py`

**功能**：
- 将所有 Pode 工具暴露为 MCP 工具
- 实现 `ListTools` 处理器
- 实现 `CallTool` 处理器

**验收标准**：
- [x] Claude Desktop 可以通过 MCP 协议使用 Pode 作为工具服务器

---

#### 任务 5.3：Skill Marketplace（Week 15，Day 3-5） ✅

**文件**：`pode_agent/services/plugins/marketplace.py`

> 📖 **Skill Marketplace 完整设计**：[skill-system.md](./skill-system.md) — Marketplace 来源、安装模式、CRUD 操作、Plugin 验证。

**功能**：
- 从 GitHub 安装 Skill（`Pode skill install github:owner/repo`）
- 从本地目录安装
- 列出已安装的 Skill
- 删除 Skill
- YAML manifest 验证

---

#### 任务 5.4：自定义命令（Week 16，Day 1-2） ✅

**文件**：`pode_agent/services/plugins/commands.py`

> 📖 **自定义命令完整设计**：[skill-system.md](./skill-system.md) — 8 目录发现、YAML frontmatter 解析、$ARGUMENTS 替换、字符预算。

**功能**：
- 从 `~/.Pode/commands/` 加载 YAML/MD 自定义命令
- Bash 执行（`!``command```）
- 文件引用（`@filename`）
- frontmatter 解析（description、category）

---

#### 任务 5.5：ACP 协议（Week 16，Day 3-5） ✅

**文件**：`pode_agent/entrypoints/acp_server.py`

**功能**：
- JSON-RPC over stdio
- 暴露 `ask`、`run`、`tool` 等方法
- 用于被其他 Agent 调用

---

### Phase 5 完成标志 ✅

```bash
# 已验证通过
uv run mypy pode_agent/        # Success: no issues found in 100 source files
uv run ruff check pode_agent/  # All checks passed
uv run pytest tests/ -q        # 786 passed, 5 skipped
```

**实际交付物**：
- 100 个 Python 源文件（pode_agent/），新增 20 个
- Hook 系统（`services/hooks/`）：4 个注入点（UserPromptSubmit, PreToolUse, PostToolUse, Stop），命令 Hook（subprocess）+ Prompt Hook（LLM），Stop Hook 重入（MAX_STOP_HOOK_ATTEMPTS = 5）
- MCP 客户端（`services/mcp/client.py`）：stdio/SSE/HTTP 传输，JSON-RPC 协议，工具发现 + 调用
- MCP 工具包装（`services/mcp/tools.py`）：动态 Tool 子类生成，`mcp__{server}__{tool}` 命名
- MCP 服务端（`entrypoints/mcp_server.py`）：暴露所有 Pode 工具为 MCP 工具
- 插件系统（`services/plugins/`）：8 目录自定义命令发现、YAML frontmatter 解析、Marketplace CRUD、plugin CLI 子命令
- SubAgent 系统（`services/agents/`）：Agent 加载 + 优先级合并、后台任务注册表、ForkContext、隔离子会话
- ACP 服务端（`entrypoints/acp_server.py`）：JSON-RPC over stdio，session/new、session/prompt、session/cancel
- 类型定义：`types/agent.py`（AgentConfig, SubAgentResult, BackgroundAgentTask）、`types/skill.py`（CustomCommandFrontmatter, ContextModifier, PluginManifest）
- contextModifier 流：ToolOutput → ToolResult → QueryOptions 应用
- Agentic Loop 升级：Hook 集成（query.py 4 个注入点）、Stop Hook 重入
- ToolLoader 升级：`_load_mcp_tools()` + `_load_plugin_tools()`
- CLI 集成：`pode plugin install/uninstall/enable/disable/list` 子命令
- 4 个新测试文件：test_hooks（39）、test_mcp_client（32）、test_custom_commands（27）、test_subagent（18）
- pytest-timeout（60s）防止测试挂起
- mypy strict mode 零错误，ruff 零告警

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
| mypy 零错误 | ✅ Done | ✅ Done (44 files) | ✅ Done (58 files) | ✅ Done (80 files) | ✅ Done (80 files) | ✅ Done (100 files) | ✅ |
| ruff lint 通过 | ✅ Done | ✅ Done | ✅ Done | ✅ Done | ✅ Done | ✅ Done | ✅ |
| pytest 通过 | ✅ Done (35) | ✅ Done (198) | ✅ Done (318) | ✅ Done (623) | ✅ Done (638) | ✅ Done (786) | ✅ |
| 新功能有测试 | ✅ Done | ✅ Done (11 files) | ✅ Done (22 files) | ✅ Done (37 files) | ✅ Done (38 files) | ✅ Done (42 files) | ✅ |
| 文档更新 | ✅ Done | ✅ Done | ✅ Done | ✅ Done | ✅ Done | ✅ Done | ✅ |

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
