# Pode-Agent 分阶段实施计划

> 版本：1.1.0 | 状态：Phase 0 已完成 | 更新：2026-03-31
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
mkdir Pode-agent && cd Pode-agent
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

## Phase 1：核心功能

**目标**：权限系统、核心工具（Bash + 文件 IO + Grep）可用，能执行非 LLM 操作。  
**时间**：Weeks 2-4（15 个工作日）  
**依赖**：Phase 0 完成  
**负责 Agent**：核心功能 Agent

### 任务列表

#### 任务 1.1：权限系统（Week 2，Day 1-3）

**文件**：
- `pode_agent/core/permissions/engine.py`
- `pode_agent/core/permissions/rules/bash.py`
- `pode_agent/core/permissions/rules/file.py`
- `pode_agent/core/permissions/rules/plan_mode.py`
- `pode_agent/core/permissions/store.py`
- `pode_agent/core/permissions/__init__.py`

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
- [ ] `is_safe_bash_command("ls -la")` → True
- [ ] `is_safe_bash_command("rm -rf /")` → False
- [ ] `PermissionEngine.has_permissions("bash", {"command": "ls"})` → ALLOWED（无需提示）
- [ ] `PermissionEngine.has_permissions("bash", {"command": "rm -rf ."})` → NEEDS_PROMPT
- [ ] 权限决定可以持久化到 ProjectConfig 并重新加载

---

#### 任务 1.2：BashTool（Week 2，Day 4-5）

**文件**：`pode_agent/tools/system/bash.py`

**功能**：
- 执行 Shell 命令（使用 `asyncio.create_subprocess_shell`）
- 超时控制（默认 120 秒）
- 捕获 stdout、stderr、exit_code
- 支持中止（通过 `abort_event`）
- 后台任务支持（`background=True` 时异步运行）

**验收标准**：
- [ ] `BashTool().call(BashInput(command="echo hello"))` → stdout="hello"
- [ ] 超时时返回错误，不挂起
- [ ] 中止信号触发时停止执行
- [ ] `is_read_only()` → False
- [ ] `needs_permissions({"command": "ls"})` → False（安全命令）
- [ ] `needs_permissions({"command": "npm install"})` → True

---

#### 任务 1.3：文件系统工具（Week 3）

按优先级实现：

1. **FileReadTool**（Day 1）
   - 读取文件内容
   - 支持行号范围（`offset`, `limit`）
   - 处理大文件截断
   - 记录读取时间戳到 `context.read_file_timestamps`

2. **FileWriteTool**（Day 2）
   - 写入/创建新文件
   - 不允许覆盖已存在文件（使用 FileEditTool）
   - 创建必要的父目录

3. **FileEditTool**（Day 3-4）
   - 精确的字符串替换（old_str → new_str）
   - 验证 old_str 在文件中唯一出现
   - 保存文件前校验
   - 提供 diff 输出

4. **GlobTool**（Day 5）
   - 使用 Python `glob.glob()` / `pathlib.Path.glob()`
   - 支持 `**` 递归匹配
   - 限制返回数量（默认 100 个）

**验收标准**：
- [ ] 每个工具有完整的单元测试
- [ ] FileEditTool 在 old_str 不唯一时抛出有用的错误
- [ ] 文件路径安全检查（不允许访问 cwd 之外的文件）

---

#### 任务 1.4：GrepTool（Week 4，Day 1-2）

**文件**：`pode_agent/tools/search/grep.py`

**实现**：
- 优先使用 `ripgrep`（通过 `subprocess`）
- 降级为 Python `re` 模块（当 `rg` 不可用时）
- 支持 `-i`（忽略大小写）、`-n`（显示行号）、`-l`（只显示文件名）
- 支持文件类型过滤（`--type py`）

---

#### 任务 1.5：LsTool（Week 4，Day 3）

**文件**：`pode_agent/tools/agent/ls.py`

**实现**：
- 列出目录内容
- 显示文件类型（目录/文件/链接）
- 基本的 `.gitignore` 过滤

---

#### 任务 1.6：会话基础（Week 4，Day 4-5）

**文件**：
- `pode_agent/app/session.py`（骨架）
- `pode_agent/utils/protocol/session_log.py`（JSONL 读写）

**实现**：
- JSONL 日志写入（save_message）
- JSONL 日志读取（load_messages_from_log）
- 日志文件命名（`~/.Pode/logs/YYYY-MM-DD_session_fork_N.jsonl`）

---

### Phase 1 完成标志

```bash
# 非 LLM 工具可以独立测试
Pode bash "ls -la"
Pode bash "cat README.md"
Pode file read README.md
Pode file edit src/main.py --old "foo" --new "bar"
Pode grep "TODO" --type py
```

---

## Phase 2：LLM 集成与会话管理

**目标**：实现完整的 LLM 对话循环（非交互打印模式），支持 Anthropic 和 OpenAI。  
**时间**：Weeks 5-7（15 个工作日）  
**依赖**：Phase 1 完成  
**负责 Agent**：LLM 集成 Agent

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
- [ ] 基本文本查询成功
- [ ] 工具调用返回正确的 tool_use block
- [ ] 速率限制时自动退避重试
- [ ] Mock 测试通过（不调用真实 API）

---

#### 任务 2.2：OpenAI 适配器（Week 6，Day 1-3）

**文件**：`pode_agent/services/ai/openai.py`

**功能**：
- Chat Completions API 流式
- Function calling / tool_choice
- `reasoning_effort` 参数（GPT-5）
- 代理支持
- 自定义 `base_url`（支持 Azure OpenAI）

---

#### 任务 2.3：ModelAdapterFactory（Week 6，Day 4-5）

**文件**：`pode_agent/services/ai/factory.py`

**功能**：
- 根据模型名路由到正确的 Provider
- 管理模型能力（max tokens、支持 thinking 等）
- 支持自定义 provider 注册

---

#### 任务 2.4：消息规范化（Week 6，Day 5 - Week 7，Day 1）

**文件**：`pode_agent/utils/messages/normalizer.py`

**功能**：
- Anthropic 消息格式 ↔ 通用 Message 格式转换
- OpenAI 消息格式 ↔ 通用 Message 格式转换
- 工具结果消息格式化

---

#### 任务 2.5：完整会话管理器（Week 7）

**文件**：`pode_agent/app/session.py`（完整实现）

**功能**：
- 完整的 `process_input()` 实现（参考 data-flows.md）
- 工具调用循环（LLM → 工具 → LLM → ...）
- 成本追踪
- 会话恢复（从 JSONL 加载历史）
- 中止处理

---

#### 任务 2.6：非交互打印模式（Week 7，Day 4-5）

**文件**：`pode_agent/app/print_mode.py`

**功能**：
- 单次查询 + 打印结果（类似 `kode -p "..."` 或 `echo "..." | kode`）
- JSON 输出模式（`--output-format json`）
- 退出码（0=成功，1=错误，2=权限拒绝）

**验收标准**：
- [ ] `Pode "What is 2+2?"` 打印回答然后退出
- [ ] 工具调用在打印模式下正确执行
- [ ] `Pode -p "list files" --output-format json` 输出有效 JSON

---

### Phase 2 完成标志

```bash
# MVP 可用
export ANTHROPIC_API_KEY=sk-ant-...
Pode "What files are in this directory?"
# 期望：调用 GlobTool，返回文件列表

Pode "Edit main.py to add a docstring to main()"
# 期望：调用 FileReadTool、FileEditTool，完成编辑

Pode "Run the tests and tell me if they pass"
# 期望：调用 BashTool("npm test")，分析结果
```

---

## Phase 3：完整工具集

**目标**：实现所有 25+ 个工具。  
**时间**：Weeks 8-10（15 个工作日）  
**依赖**：Phase 2 完成  
**负责 Agent**：工具实现 Agent（可以多个 Agent 并行）

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
| EnterPlanModeTool | `tools/agent/plan_mode.py` | 进入计划模式 |
| ExitPlanModeTool | `tools/agent/plan_mode.py` | 退出计划模式 |
| TaskTool | `tools/agent/task.py` | 子任务管理 |
| SlashCommandTool | `tools/interaction/slash_command.py` | 执行自定义命令 |

#### Web 搜索提供商（Week 10）

实现 WebSearchTool 的多个后端：
- Bing Web Search API
- SerpAPI
- Exa
- 降级：直接访问 DuckDuckGo（无 API key）

---

### Phase 3 完成标志

```bash
Pode tools list
# 期望：显示所有 25+ 工具

Pode "Search the web for 'Python asyncio best practices' and summarize"
# 期望：调用 WebSearchTool，返回摘要

Pode "Read my notebook.ipynb and explain what it does"
# 期望：调用 NotebookReadTool，返回解释
```

---

## Phase 4：终端 UI

**目标**：实现基于 Textual 的完整 REPL 界面。  
**时间**：Weeks 11-13（15 个工作日）  
**依赖**：Phase 2 完成（可与 Phase 3 并行）  
**负责 Agent**：UI 开发 Agent

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

**目标**：实现 MCP 客户端/服务端、插件系统和 ACP 协议。  
**时间**：Weeks 14-16（15 个工作日）  
**依赖**：Phase 3 完成  
**负责 Agent**：协议集成 Agent

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

#### 任务 6.3：上下文管理优化（Week 18）

**功能**：
- 消息自动压缩（当 token 超阈值时）
- 智能截断策略（保留最近的对话）
- 长会话处理

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
| mypy 零错误 | ✅ Done | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| ruff lint 通过 | ✅ Done | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| pytest 通过 | ✅ Done (35) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 新功能有测试 | ✅ Done | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 文档更新 | ✅ Done | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

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
3. 确认前序阶段的验收标准都已通过

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
