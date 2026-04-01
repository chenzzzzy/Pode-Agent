# Pode-Agent Plan Mode（规划模式）

> 版本：1.0.0 | 状态：草稿 | 更新：2026-04-01  
> 本文档是 **Plan Mode 规划机制的权威设计文档**，描述如何在多步任务中先规划后执行。  
> 工具系统（工具注册/发现/权限）见 [tools-system.md](./tools-system.md)；  
> Agentic Loop 的 System Prompt 注入点见 [agent-loop.md](./agent-loop.md)。

---

## 目录

1. [目标与原则](#目标与原则)
2. [Plan 的数据结构与存储](#plan-的数据结构与存储)
3. [进入/退出 Plan Mode 的工具](#进入退出-plan-mode-的工具)
4. [Plan Mode 的五阶段工作流](#plan-mode-的五阶段工作流)
5. [与 Agent Loop 的耦合点](#与-agent-loop-的耦合点)
6. [System Prompt 动态注入](#system-prompt-动态注入)
7. [权限系统与 Plan Mode](#权限系统与-plan-mode)
8. [多步任务的落地方式](#多步任务的落地方式)
9. [与 TaskTool/子 Agent 的关系](#与-taskTool子-agent-的关系)
10. [Kode-Agent → Pode-Agent 映射表](#kode-agent--pode-agent-映射表)
11. [分阶段实现建议](#分阶段实现建议)

---

## 目标与原则

**Plan Mode** 实现"先探索/设计/列计划，再执行"的约束工作流。  
其核心价值：

- **防止意外修改**：在用户批准计划前，Agent 不得写文件、执行 Shell 命令等破坏性操作。
- **提高对齐度**：复杂多步任务在执行前先与用户达成一致，避免"做完了才发现方向错误"。
- **可审计**：计划以 Markdown 文件形式存储在磁盘，用户可手动查看和修改。

### 何时使用 Plan Mode

Agent 应主动进入 Plan Mode 的场景（对应 Kode-Agent EnterPlanMode 工具的 prompt 文档）：

| 场景 | 示例 |
|------|------|
| 新功能实现 | "添加用户认证" — 需要架构决策 |
| 多种可行方案 | "优化数据库查询" — 有多种策略 |
| 影响现有代码结构 | "重构认证流程" — 影响多个文件 |
| 架构决策 | "添加实时更新" — WebSocket vs SSE vs Polling |
| 多文件变更 | 预计修改超过 2-3 个文件 |
| 需求不明确 | "让应用更快" — 需要先探索才能理解范围 |

**不需要** Plan Mode 的场景：单行修复、明显的 bug 修正、用户已给出非常具体的指令。

### 基本约束

Plan Mode 激活期间：

1. Agent **只能使用只读工具**（`tool.is_read_only() == True`）。
2. 唯一的例外：**计划文件**（`~/.pode/plans/{slug}.md`）允许写入/编辑。
3. 上述约束**优先于其他任何 system prompt 中的指令**（通过 `<system-reminder>` 标签强制注入）。

---

## Plan 的数据结构与存储

### Plan Slug（计划标识符）

每个 Plan Mode 会话生成一个唯一的"slug"，格式为三词组合：

```
{形容词}-{动词}-{名词}
例如：swift-building-river
     careful-fixing-mountain
```

Slug 由随机选词生成（对应 Kode-Agent 的 `planSlugWords.ts`），保证在 plans 目录中唯一。  
Pode-Agent 实现：

```python
# pode_agent/app/plan_state.py

import random
from .plan_slug_words import ADJECTIVES, VERBS, NOUNS

def generate_plan_slug() -> str:
    """生成 {adjective}-{verb}-{noun} 格式的唯一 slug"""
    return f"{random.choice(ADJECTIVES)}-{random.choice(VERBS)}-{random.choice(NOUNS)}"
```

### Plan 存储位置

```
~/.pode/
└── plans/
    ├── {slug}.md                    ← 主 Agent 的计划文件
    └── {slug}-agent-{agent_id}.md   ← 子 Agent（TaskTool）的计划文件
```

计划文件是**纯 Markdown 格式**，由 Agent 自由书写。  
框架不规定内容格式，但建议包含：

```markdown
# 实现计划：{任务简述}

## 背景
- 当前状况描述
- 探索发现的关键信息

## 实现步骤
1. 步骤一：描述 + 涉及文件
2. 步骤二：描述 + 涉及文件
...

## 关键文件
- `path/to/file.py`：说明作用

## 风险与注意事项
- 风险一：...

## 验收标准
- [ ] 条件一
- [ ] 条件二
```

### Conversation Key（会话键）

Plan Mode 状态以"conversation key"为单位管理，格式为：

```
{message_log_name}:{fork_number}
例如：2026-04-01_session_fork_0:0
```

这允许同一进程中的不同会话（fork）拥有独立的 Plan Mode 状态。

### 状态机

```
初始状态
    │
    │ EnterPlanModeTool 调用（用户批准）
    ▼
[PLAN_MODE_ACTIVE]
    │  只读工具可用
    │  写文件权限拒绝
    │  system-reminder 周期性注入
    │
    │ ExitPlanModeTool 调用（用户批准计划）
    ▼
[PLAN_APPROVED]
    │  恢复完整工具集
    │  system-reminder 注入"已退出计划模式"提示
    ▼
[EXECUTING]（Agent 开始实现计划）
```

---

## 进入/退出 Plan Mode 的工具

### EnterPlanModeTool

**文件**：`pode_agent/tools/agent/plan_mode.py`

```python
class EnterPlanModeTool(Tool):
    name = "EnterPlanMode"

    def is_read_only(self) -> bool:
        return True  # 进入 Plan Mode 本身是只读操作

    def is_concurrency_safe(self) -> bool:
        return True

    def needs_permissions(self, input=None) -> bool:
        return True  # 需要用户明确批准才能进入计划模式

    def requires_user_interaction(self) -> bool:
        return True  # 必须等用户操作，不能自动通过

    async def call(self, input, context):
        # 禁止在子 Agent 中使用
        if context.agent_id:
            raise ValueError("EnterPlanMode 不能在子 Agent 中使用")

        # 1. 将权限模式设置为 'plan'
        set_permission_mode(context, PermissionMode.PLAN)

        # 2. 激活 Plan Mode 状态（设置 conversation key 对应的标记）
        enter_plan_mode(context)

        yield ToolOutput(
            type="result",
            data={"message": "Entered plan mode."},
            result_for_assistant=self._render_result_for_assistant(),
        )

    def _render_result_for_assistant(self) -> str:
        return """Entered plan mode. You should now focus on exploring the codebase and designing an implementation approach.

In plan mode, you should:
1. Thoroughly explore the codebase to understand existing patterns
2. Identify similar features and architectural approaches
3. Consider multiple approaches and their trade-offs
4. Use AskUserQuestion if you need to clarify the approach
5. Design a concrete implementation strategy
6. When ready, use ExitPlanMode to present your plan for approval

Remember: DO NOT write or edit any files yet. This is a read-only exploration and planning phase."""
```

### ExitPlanModeTool

**文件**：`pode_agent/tools/agent/plan_mode.py`

```python
class ExitPlanModeTool(Tool):
    name = "ExitPlanMode"

    def is_read_only(self) -> bool:
        return False  # 退出 Plan Mode 会恢复写权限

    def needs_permissions(self, input=None) -> bool:
        return True  # 需要用户批准（用户审阅计划并批准）

    def requires_user_interaction(self) -> bool:
        return True

    async def call(self, input, context):
        plan_file_path = get_plan_file_path(context)

        # 1. 读取计划文件（必须存在）
        content, exists = read_plan_file(context)
        if not exists:
            raise ValueError(
                f"No plan file found at {plan_file_path}. "
                "Please write your plan to this file before calling ExitPlanMode."
            )

        # 2. 退出 Plan Mode（恢复权限模式为 default）
        exit_plan_mode(context)

        yield ToolOutput(
            type="result",
            data={
                "plan": content,
                "file_path": plan_file_path,
                "is_agent": bool(context.agent_id),
            },
            result_for_assistant=self._render_result_for_assistant(content, plan_file_path),
        )

    def _render_result_for_assistant(self, plan: str, file_path: str) -> str:
        return f"""User has approved your plan. You can now start coding.

Your plan has been saved to: {file_path}
You can refer back to it if needed during implementation.

## Approved Plan:
{plan}"""
```

### 工具对 UI 的影响

| 事件 | UI 行为 |
|------|---------|
| `EnterPlanModeTool` 执行成功 | 显示"已进入计划模式"提示，工具栏变色（计划模式主题色） |
| `EnterPlanModeTool` 被拒绝 | 显示"用户拒绝进入计划模式" |
| `ExitPlanModeTool` 执行成功 | 显示计划内容（折叠框），标记"用户已批准计划" |
| `ExitPlanModeTool` 被拒绝 | 显示计划内容，标记"用户已拒绝计划" |

---

## Plan Mode 的五阶段工作流

对应 Kode-Agent `planMode.ts` 的 `buildPlanModeMainReminder()` 所描述的工作流：

```
Phase 1: 初步理解（Initial Understanding）
    │  目标：理解用户请求和相关代码
    │  工具：Explore 子 Agent（并行 1-3 个）
    │  禁止：任何写操作
    ▼
Phase 2: 设计（Design）
    │  目标：设计实现方案
    │  工具：Plan 子 Agent（1-N 个）
    │  输出：多个方案对比
    ▼
Phase 3: 评审（Review）
    │  目标：与用户意图对齐
    │  工具：AskUserQuestionTool（有疑问时）
    │  输出：确定最终方案
    ▼
Phase 4: 撰写计划（Final Plan）
    │  目标：将最终方案写入计划文件
    │  文件：~/.pode/plans/{slug}.md
    │  内容：步骤、关键文件、风险、验收标准
    ▼
Phase 5: 退出并等待批准（ExitPlanMode）
    │  工具：ExitPlanModeTool
    │  效果：用户审阅 → 批准或拒绝
    ▼
（批准后）开始执行计划（工具集恢复完整）
```

### 主 Agent vs 子 Agent 的行为差异

| 角色 | 工作流 | 计划文件 |
|------|--------|---------|
| **主 Agent** | 5 阶段完整工作流，最终调用 ExitPlanMode | `~/.pode/plans/{slug}.md` |
| **子 Agent（agentId 非空）** | 只做探索/分析，不调用 Enter/ExitPlanMode | `~/.pode/plans/{slug}-agent-{id}.md` |

子 Agent 的 system-reminder 是简化版（`buildPlanModeSubAgentReminder()`），  
主要职责是回答主 Agent 的探索/设计问题，而非驱动整个计划流程。

---

## 与 Agent Loop 的耦合点

> 📖 **`query_core()` 的完整调用流程见** [agent-loop.md — 递归式主循环](./agent-loop.md#递归式主循环)。

### System Prompt 注入点

在 `query_core()` 的每轮 LLM 调用前，`build_system_prompt()` 会调用 `get_plan_mode_system_prompt_additions()`：

```python
# pode_agent/app/query.py (伪代码)

async def build_system_prompt(messages, context) -> str:
    base = get_base_system_prompt()

    # Hook 追加（Phase 5 实现）
    hook_additions = await run_user_prompt_submit_hooks(...)

    # Plan Mode 追加（Phase 3 实现）
    plan_additions = get_plan_mode_system_prompt_additions(messages, context)

    # Tool prompt 追加
    tool_additions = [
        await tool.prompt()
        for tool in context.options.tools or []
        if await tool.prompt()
    ]

    return base + "\n".join(hook_additions + plan_additions + tool_additions)
```

### system-reminder 的注入频率

为避免 system-reminder 占用过多 token，Kode-Agent（以及 Pode-Agent）仅在以下条件下注入：

- 首次进入 Plan Mode 时：**无条件注入**
- 后续轮次：距上次注入**超过 5 个 Assistant 轮次**才再次注入（`TURNS_BETWEEN_ATTACHMENTS = 5`）

```python
# pode_agent/app/plan_state.py

TURNS_BETWEEN_ATTACHMENTS = 5

def should_inject_plan_reminder(state: PlanModeAttachmentState, assistant_turns: int) -> bool:
    if not state.has_injected:
        return True  # 首次必须注入
    return assistant_turns - state.last_injected_assistant_turn >= TURNS_BETWEEN_ATTACHMENTS
```

### PermissionMode 的切换

```
EnterPlanModeTool.call()
    → set_permission_mode(context, PermissionMode.PLAN)
    
ExitPlanModeTool.call()
    → set_permission_mode(context, PermissionMode.DEFAULT)
    （或恢复到用户指定的默认模式）
```

`PermissionMode.PLAN` 在 `PermissionEngine.has_permissions()` 中的行为：

```python
def has_permissions(self, tool_name, input, context) -> PermissionResult:
    mode = get_permission_mode(context)

    if mode == PermissionMode.PLAN:
        tool = registry.get(tool_name)
        if tool and tool.is_read_only(input):
            return PermissionResult.ALLOWED  # 只读工具直接允许
        # 额外允许写计划文件
        if is_plan_file_path(input.get("file_path", ""), context):
            return PermissionResult.ALLOWED
        return PermissionResult.DENIED  # 写操作全部拒绝

    # ... 其他模式逻辑
```

### canUseTool 函数

`canUseTool` 是 `query_core()` 的参数，用于在工具执行前做最终拦截：

```python
# 由 SessionManager 构造并传入 query()

def can_use_tool(tool_name: str, input: dict, context: ToolUseContext) -> bool:
    """
    Plan Mode 下：只允许只读工具和计划文件写入
    Safe Mode 下：只允许只读工具
    """
    permission_mode = get_permission_mode(context)
    if permission_mode == PermissionMode.PLAN:
        tool = registry.get(tool_name)
        return (tool is not None and tool.is_read_only(input)) or \
               is_plan_file_path_for_active_conversation(input.get("path", ""))
    return True
```

---

## System Prompt 动态注入

### Plan Mode 激活时注入的 system-reminder 内容

对应 Kode-Agent 的 `buildPlanModeMainReminder()`，注入内容结构如下：

```
<system-reminder>
Plan mode is active. The user indicated that they do not want you to execute yet
-- you MUST NOT make any edits (with the exception of the plan file mentioned
below), run any non-readonly tools, or otherwise make any changes to the system.
This supercedes any other instructions you have received.

## Plan File Info:
[No plan file exists yet / A plan file already exists at {path}]
You should build your plan incrementally by writing to or editing this file.
NOTE that this is the only file you are allowed to edit.

## Plan Workflow
### Phase 1: Initial Understanding
...
### Phase 2: Design
...
### Phase 3: Review
...
### Phase 4: Final Plan
...
### Phase 5: Call ExitPlanMode
...
</system-reminder>
```

### Plan Mode 退出时注入的 system-reminder

```
<system-reminder>
## Exited Plan Mode

You have exited plan mode. You can now make edits, run tools, and take actions.
The plan file is located at {file_path} if you need to reference it.
</system-reminder>
```

### 重新进入 Plan Mode（Re-entry）

当用户在批准计划后再次触发 Plan Mode 时，额外注入"re-entry reminder"：

```
<system-reminder>
## Re-entering Plan Mode

You are returning to plan mode after having previously exited it.
A plan file exists at {file_path} from your previous planning session.

**Before proceeding with any new planning, you should:**
1. Read the existing plan file to understand what was previously planned
2. Evaluate the user's current request against that plan
3. Decide how to proceed: Different task（覆盖）vs Same task（修改）
4. Always edit the plan file before calling ExitPlanMode
...
</system-reminder>
```

---

## 权限系统与 Plan Mode

> 📖 **权限系统完整规格见** [tools-system.md — 权限系统与工具系统的耦合点](./tools-system.md#权限系统与工具系统的耦合点)。

### 权限模式对比

| PermissionMode | 写文件 | 执行 Shell | Plan 文件 | 说明 |
|---------------|-------|-----------|----------|------|
| `DEFAULT` | 需确认 | 需确认 | 需确认 | 正常模式 |
| `PLAN` | **拒绝** | **拒绝** | **允许** | 计划模式 |
| `ACCEPT_EDITS` | 自动允许 | 需确认 | 自动允许 | 文件编辑免确认 |
| `BYPASS_PERMISSIONS` | 自动允许 | 自动允许 | 自动允许 | 跳过所有检查 |
| `DONT_ASK` | 拒绝危险 | 拒绝危险 | 拒绝危险 | 保守模式 |

### Plan Mode 下的工具可用性

```python
# Plan Mode 下可用的工具（is_read_only == True）
PLAN_MODE_AVAILABLE_TOOLS = [
    "GlobTool",
    "GrepTool",
    "FileReadTool",
    "LsTool",
    "LspTool",
    "WebSearchTool",    # 只读（搜索）
    "WebFetchTool",     # 只读（抓取）
    "AskUserQuestionTool",  # 交互，但不写文件
    "TaskTool",         # 子 Agent（Explore 类型）
    # EnterPlanModeTool / ExitPlanModeTool 由框架特殊处理
]

# Plan Mode 下禁止的工具（is_read_only == False）
PLAN_MODE_BLOCKED_TOOLS = [
    "BashTool",         # 可能执行写操作
    "FileWriteTool",
    "FileEditTool",
    "MultiEditTool",
    "NotebookEditTool",
    "TodoWriteTool",
    # MCP 工具默认全部禁止
]
```

---

## 多步任务的落地方式

### 计划文件建议格式

为了让 Agent 在实现阶段能有效参考计划，推荐计划文件包含以下结构：

```markdown
# 计划：{简洁任务描述}

## 目标
{1-2句话描述最终目标}

## 背景信息
- 相关代码位置：`path/to/relevant/file.py`（L42-L89）
- 现有模式：{描述当前如何实现类似功能}
- 约束：{已知限制}

## 实现步骤
1. **{步骤标题}**（预计影响文件：`a.py`, `b.py`）
   - 具体操作描述
   - 注意事项

2. **{步骤标题}**
   - ...

## 验收标准
- [ ] {可测试的条件 1}
- [ ] {可测试的条件 2}

## 风险与回滚
- 风险：{描述}
  回滚方案：{描述}
```

### 用户批准后的执行方式

`ExitPlanModeTool` 调用成功（用户批准）后，`renderResultForAssistant` 中注入：

1. **计划文件路径**：Agent 在实现时可随时读取参考。
2. **完整计划内容**：直接嵌入 `tool_result` 消息，Agent 无需再读文件。
3. **执行提示**：`"You can now start coding. Start with updating your todo list if applicable"`。

Agent 通常会先用 `TodoWriteTool` 将计划步骤转化为 TODO 列表，然后按步骤逐一实现。

---

## 与 TaskTool/子 Agent 的关系

### TaskTool 在 Plan Mode 中的角色

`TaskTool` 可以在 Plan Mode 内启动子 Agent 进行并行探索/设计：

| 子 Agent 类型 | 在 Plan Mode 中的用途 |
|-------------|---------------------|
| `explore` | Phase 1：并行探索代码库的不同区域（最多 `KODE_PLAN_V2_EXPLORE_AGENT_COUNT` 个，默认 3） |
| `plan` | Phase 2：并行设计多个方案视角（最多 `KODE_PLAN_V2_AGENT_COUNT` 个，默认 1） |

子 Agent 在 Plan Mode 下自动继承 `PLAN` 权限模式，但收到简化版 system-reminder。

### 子 Agent 与计划文件

- 子 Agent 有自己独立的计划文件（`{slug}-agent-{id}.md`）。
- 主 Agent 读取子 Agent 的探索/设计结果后，整合到主计划文件（`{slug}.md`）。
- 只有主 Agent 可以调用 `ExitPlanModeTool`。

### Swarm 模式（高级用法）

当用户在批准计划时选择 "Launch Swarm" 时，`ExitPlanModeTool` 的 `renderResultForAssistant` 中注入指令，引导主 Agent 用 `TaskTool` 创建多个并行 worker，分批实现计划步骤。

**Pode-Agent 实现阶段**：Swarm 模式在 Phase 6 实现（依赖完整的 TaskTool + 子 Agent 通信）。

---

## Kode-Agent → Pode-Agent 映射表

| Kode-Agent（TypeScript） | Pode-Agent（Python） | 说明 |
|--------------------------|----------------------|------|
| `src/utils/plan/planMode.ts` | `pode_agent/app/plan_state.py` | Plan Mode 核心状态机 |
| `src/utils/plan/planSlugWords.ts` | `pode_agent/app/plan_slug_words.py` | 随机 slug 词库 |
| `enterPlanMode()` | `enter_plan_mode(context)` | 激活 Plan Mode |
| `exitPlanMode()` | `exit_plan_mode(context)` | 停用 Plan Mode |
| `isPlanModeEnabled()` | `is_plan_mode_enabled(context)` | 查询 Plan Mode 状态 |
| `getPlanFilePath()` | `get_plan_file_path(context)` | 计划文件路径 |
| `readPlanFile()` | `read_plan_file(context)` | 读取计划文件 |
| `getPlanModeSystemPromptAdditions()` | `get_plan_mode_system_prompt_additions(messages, context)` | System Prompt 追加 |
| `buildPlanModeMainReminder()` | `build_plan_mode_main_reminder(...)` | 主 Agent reminder |
| `buildPlanModeSubAgentReminder()` | `build_plan_mode_sub_agent_reminder(...)` | 子 Agent reminder |
| `buildPlanModeReentryReminder()` | `build_plan_mode_reentry_reminder(...)` | 重入 reminder |
| `buildPlanModeExitReminder()` | `build_plan_mode_exit_reminder(...)` | 退出 reminder |
| `src/utils/permissions/permissionModeState.ts` `setPermissionMode()` | `pode_agent/core/permissions/engine.py` `set_permission_mode()` | 切换权限模式 |
| `TURNS_BETWEEN_ATTACHMENTS = 5` | `TURNS_BETWEEN_ATTACHMENTS = 5` | Reminder 注入间隔 |
| `MAX_SLUG_ATTEMPTS = 10` | `MAX_SLUG_ATTEMPTS = 10` | Slug 生成最大重试 |
| `src/tools/agent/PlanModeTool/EnterPlanModeTool.tsx` | `pode_agent/tools/agent/plan_mode.py` `EnterPlanModeTool` | 进入计划模式工具 |
| `src/tools/agent/PlanModeTool/ExitPlanModeTool.tsx` | `pode_agent/tools/agent/plan_mode.py` `ExitPlanModeTool` | 退出计划模式工具 |
| `KODE_PLAN_V2_EXPLORE_AGENT_COUNT` | `PODE_PLAN_EXPLORE_AGENT_COUNT` | 最大探索子 Agent 数 |
| `KODE_PLAN_V2_AGENT_COUNT` | `PODE_PLAN_DESIGN_AGENT_COUNT` | 最大设计子 Agent 数 |

---

## 分阶段实现建议

| 功能组件 | 实现阶段 | 说明 |
|---------|---------|------|
| `PermissionMode.PLAN` 权限模式骨架 | **Phase 1** | 权限系统任务 1.1，仅定义 enum，不完整实现 |
| `plan_state.py`：`enter/exit/is_enabled` + Slug 生成 | **Phase 3** | 配合 Plan Mode 工具一起实现 |
| `EnterPlanModeTool` / `ExitPlanModeTool` | **Phase 3** | 低优先级工具，任务 3.x |
| `PermissionEngine` Plan Mode 约束（只读工具允许，写操作拒绝） | **Phase 3** | 配合工具实现 |
| System Prompt 注入（`get_plan_mode_system_prompt_additions`） | **Phase 3** | 配合 System Prompt 动态组装 |
| `canUseTool` Plan Mode 拦截 | **Phase 3** | 配合 query_core 升级 |
| `TURNS_BETWEEN_ATTACHMENTS` 节流逻辑 | **Phase 3** | 避免 reminder 占用过多 token |
| 计划文件 Re-entry 逻辑（`buildPlanModeReentryReminder`） | **Phase 3** | 与主流程一起实现 |
| TaskTool Explore/Plan 子 Agent 类型 | **Phase 5** | 依赖完整 TaskTool + MCP |
| Swarm 模式（并行 worker） | **Phase 6** | 依赖完整子 Agent 通信机制 |
