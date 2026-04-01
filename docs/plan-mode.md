# Pode-Agent 计划模式（Plan Mode）

> 版本：1.0.0 | 状态：草稿 | 更新：2026-04-01  
> 本文档是 **Plan Mode（计划模式）的权威设计文档**，涵盖目标原则、数据结构、存储方案、Enter/Exit 机制、多步执行流程、与 Agent Loop 的耦合，以及分阶段实现建议。  
> 核心循环调度细节（query_core 递归、ToolUseQueue、Hook 系统）请参阅 [agent-loop.md](./agent-loop.md)。  
> 工具层权限硬拒绝机制请参阅 [tools-system.md](./tools-system.md#权限系统与工具的耦合点)。

---

## 目录

1. [Plan Mode 目标与原则](#plan-mode-目标与原则)
2. [Plan 数据结构与生命周期](#plan-数据结构与生命周期)
3. [存储方案 A：写入 Session JSONL](#存储方案-a写入-session-jsonl)
4. [进入与退出 Plan Mode 的工具](#进入与退出-plan-mode-的工具)
5. [多步任务如何落地执行](#多步任务如何落地执行)
6. [与 Agent Loop 的耦合点](#与-agent-loop-的耦合点)
7. [与 SubAgent / TaskTool 的关系](#与-subagent--tasktool-的关系)
8. [分阶段实现建议](#分阶段实现建议)
9. [映射表：Kode-Agent → Pode-Agent](#映射表kode-agent--pode-agent)

---

## Plan Mode 目标与原则

### 核心目标

**先规划，后执行**——在进行任何写操作（文件修改、代码执行等）之前，先通过只读探索生成一份人类可审查的计划，用户确认后再开始执行。

这解决了 AI Agent 的常见问题：**在没有充分理解情况下就开始修改文件**，导致难以回滚的意外操作。

### 设计原则

1. **只读探索阶段**：进入 Plan Mode 后，Agent 只能使用只读工具（文件读取、搜索、grep 等）收集信息，不得写入任何文件或执行有副作用的命令

2. **两种限制层次并存**：
   - **软约束**：System prompt additions 引导 LLM 只进行探索性操作
   - **硬拒绝（策略 B）**：`PermissionMode.PLAN` 使 `PermissionEngine` 在工具层直接拒绝所有非只读工具（`is_read_only() == False`），不询问用户

3. **计划透明可审**：计划输出给用户审查，包含目标、步骤、风险、验收标准等结构化内容

4. **边界清晰**：计划阶段（只读）和执行阶段（可写）有明确的切换点（`ExitPlanMode` 工具触发）

5. **可恢复性**：计划内容持久化到 Session JSONL，重启后可继续按计划推进

---

## Plan 数据结构与生命周期

### Plan 标识

```python
# pode_agent/app/plan.py（或 pode_agent/types/plan.py）

import uuid
from pydantic import BaseModel, Field
from datetime import datetime, timezone

class PlanStep(BaseModel):
    """计划中的单个执行步骤"""
    index: int                          # 步骤序号（1-based）
    title: str                          # 步骤标题（人类可读）
    description: str                    # 详细描述
    tools: list[str] = []               # 预计使用的工具（提示性）
    status: "StepStatus" = "pending"    # pending | running | done | skipped | failed
    result_summary: str | None = None   # 执行后填入结果摘要

class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    SKIPPED = "skipped"
    FAILED = "failed"

class Plan(BaseModel):
    """计划对象（完整结构）"""
    plan_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    slug: str | None = None             # 可读标识（如 "refactor-auth-module"）
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # ── 计划内容 ───────────────────────────────────────────
    objective: str                      # 总目标（一句话）
    research_notes: str | None = None   # 探索阶段收集的信息
    steps: list[PlanStep] = []          # 执行步骤列表
    acceptance_criteria: list[str] = [] # 验收标准
    risks: list[str] = []               # 潜在风险
    rollback_plan: str | None = None    # 回滚方案
    test_matrix: str | None = None      # 测试矩阵

    # ── 状态 ───────────────────────────────────────────────
    status: "PlanStatus" = "draft"      # draft | approved | executing | done | cancelled

class PlanStatus(str, Enum):
    DRAFT = "draft"                     # 生成中/未确认
    APPROVED = "approved"               # 用户已确认，等待执行
    EXECUTING = "executing"             # 执行中
    DONE = "done"                       # 完成
    CANCELLED = "cancelled"             # 取消
```

### Plan 生命周期

```
用户输入复杂任务
    │
    ▼
【计划阶段】EnterPlanModeTool 被调用
    │  PermissionMode = PLAN
    │  System prompt additions 注入
    │
    ▼
Agent 只读探索（文件读取/搜索/grep...）
    │
    ▼
ExitPlanModeTool 被调用，输出 Plan 对象
    │  写入 JSONL（plan_created 事件）
    │  PermissionMode 重置为 DEFAULT
    │
    ▼
用户审查计划（UI 显示结构化 Plan）
    │
    ├── 拒绝 → plan status = cancelled，回到普通对话
    └── 批准 → plan status = approved
              │
              ▼
        【执行阶段】按步骤推进
              │  每步完成后写入 JSONL（plan_step_done 事件）
              │
              ▼
        所有步骤完成 → plan status = done
```

---

## 存储方案 A：写入 Session JSONL

**决策**：计划数据全部以事件形式写入 Session JSONL，不单独创建计划文件。

### JSONL 事件格式

Session JSONL 文件（`~/.pode/logs/<session_id>.jsonl`）中，每行是一个 JSON 对象：

```jsonl
{"type": "user_message", "id": "msg_001", "content": "帮我重构 auth 模块", "ts": "2026-04-01T10:00:00Z"}
{"type": "assistant_message", "id": "msg_002", "content": "我来先分析代码结构...", "ts": "2026-04-01T10:00:02Z"}
{"type": "tool_use", "tool_use_id": "tu_001", "tool_name": "enter_plan_mode", "input": {}, "ts": "2026-04-01T10:00:05Z"}
{"type": "tool_result", "tool_use_id": "tu_001", "content": "已进入计划模式", "ts": "2026-04-01T10:00:05Z"}
{"type": "plan_created", "plan_id": "plan_abc123", "slug": "refactor-auth-module", "data": {...Plan 完整 JSON...}, "ts": "2026-04-01T10:01:00Z"}
{"type": "plan_approved", "plan_id": "plan_abc123", "ts": "2026-04-01T10:01:30Z"}
{"type": "plan_step_start", "plan_id": "plan_abc123", "step_index": 1, "ts": "2026-04-01T10:01:31Z"}
{"type": "plan_step_done", "plan_id": "plan_abc123", "step_index": 1, "result_summary": "已完成...", "ts": "2026-04-01T10:02:00Z"}
{"type": "plan_done", "plan_id": "plan_abc123", "ts": "2026-04-01T10:05:00Z"}
```

### 对应的 Pydantic 事件模型

```python
# pode_agent/types/session_events.py（或 pode_agent/types/conversation.py 扩展）

class PlanCreatedEvent(BaseModel):
    type: Literal["plan_created"] = "plan_created"
    plan_id: str
    slug: str | None = None
    data: Plan                          # 完整 Plan 对象序列化

class PlanApprovedEvent(BaseModel):
    type: Literal["plan_approved"] = "plan_approved"
    plan_id: str

class PlanStepStartEvent(BaseModel):
    type: Literal["plan_step_start"] = "plan_step_start"
    plan_id: str
    step_index: int

class PlanStepDoneEvent(BaseModel):
    type: Literal["plan_step_done"] = "plan_step_done"
    plan_id: str
    step_index: int
    result_summary: str | None = None

class PlanDoneEvent(BaseModel):
    type: Literal["plan_done"] = "plan_done"
    plan_id: str

class PlanCancelledEvent(BaseModel):
    type: Literal["plan_cancelled"] = "plan_cancelled"
    plan_id: str
    reason: str | None = None
```

### 会话恢复（Replay）

JSONL 格式天然支持重放：

```python
# pode_agent/app/session.py

async def load_plan_from_log(session_log_path: str) -> Plan | None:
    """
    从 JSONL 日志中恢复最近的活跃计划。
    
    扫描 plan_created / plan_approved / plan_step_done / plan_done 事件，
    重建 Plan 对象的当前状态（已完成哪些步骤）。
    
    Returns:
        最近的未完成 Plan，或 None（若无活跃计划）
    """
```

---

## 进入与退出 Plan Mode 的工具

### EnterPlanModeTool

```python
# pode_agent/tools/agent/plan_mode.py

class EnterPlanModeInput(BaseModel):
    objective: str = Field(
        description="The high-level objective of the plan (one sentence)"
    )

class EnterPlanModeTool(Tool):
    name = "enter_plan_mode"
    description = (
        "Enter plan mode to explore the codebase and create a structured plan "
        "before making any changes. In plan mode, only read-only tools are available."
    )

    def is_read_only(self, input=None) -> bool:
        return True  # 进入计划模式本身是只读操作

    def needs_permissions(self, input=None) -> bool:
        return False  # 无需权限确认

    async def call(self, input: EnterPlanModeInput, context: ToolUseContext):
        yield ToolOutput(type="progress", content="进入计划模式...")

        # 1. 切换 permission mode（写入 context.options.permission_mode）
        context.options.permission_mode = PermissionMode.PLAN

        # 2. 返回结果（触发 system prompt additions 更新）
        yield ToolOutput(
            type="result",
            data={"mode": "plan", "objective": input.objective},
            result_for_assistant=(
                f"已进入计划模式。目标：{input.objective}\n"
                "现在只有只读工具可用。请探索代码库，然后调用 exit_plan_mode 输出完整计划。"
            ),
        )
```

**EnterPlanModeTool 的副作用**：
1. `context.options.permission_mode` 设为 `PermissionMode.PLAN`
2. 触发 System Prompt 重新构建（下一轮 `query_core()` 递归时注入 plan mode additions）
3. UI 可以监听 `permission_mode_changed` 事件，显示"计划模式"标识

### ExitPlanModeTool

```python
class ExitPlanModeInput(BaseModel):
    plan: Plan = Field(
        description=(
            "The complete plan object including objective, steps, "
            "acceptance criteria, risks, and rollback plan."
        )
    )

class ExitPlanModeTool(Tool):
    name = "exit_plan_mode"
    description = (
        "Exit plan mode and present the structured plan to the user for approval. "
        "The plan will be saved and the user must approve it before execution begins."
    )

    def is_read_only(self, input=None) -> bool:
        return True  # 退出本身也是只读（写 JSONL 由 session 层负责）

    def needs_permissions(self, input=None) -> bool:
        return False

    async def call(self, input: ExitPlanModeInput, context: ToolUseContext):
        yield ToolOutput(type="progress", content="生成计划...")

        # 1. 重置 permission mode
        context.options.permission_mode = PermissionMode.DEFAULT

        # 2. 返回计划（SessionManager 监听 result.data["plan"] 并写入 JSONL）
        yield ToolOutput(
            type="result",
            data={"event": "plan_created", "plan": input.plan.model_dump()},
            result_for_assistant=_format_plan_for_llm(input.plan),
        )
```

**ExitPlanModeTool 的副作用**：
1. `context.options.permission_mode` 重置为 `PermissionMode.DEFAULT`
2. `SessionManager` 检测 `result.data["event"] == "plan_created"`，写入 `plan_created` JSONL 事件
3. UI 显示结构化计划，等待用户批准/拒绝

---

## 多步任务如何落地执行

### 阶段边界

```
╔═══════════════════════════════════╗
║          计划阶段（PLAN Mode）     ║
║  PermissionMode = PLAN            ║
║  只读工具可用                      ║
║  Agent：读文件 / grep / 分析       ║
╚═══════════════════════════════════╝
            │
            │ ExitPlanModeTool 调用
            │ 用户审批
            │
╔═══════════════════════════════════╗
║         执行阶段（DEFAULT Mode）   ║
║  PermissionMode = DEFAULT         ║
║  全部工具可用（受正常权限控制）     ║
║  Agent：按步骤写文件 / 执行命令    ║
╚═══════════════════════════════════╝
```

### 用户批准后的执行流程

```python
# 伪代码：SessionManager 处理计划审批

async def on_plan_approved(self, plan_id: str):
    """用户点击"批准"后触发"""
    
    # 1. 写 plan_approved JSONL 事件
    self.write_log(PlanApprovedEvent(plan_id=plan_id))
    
    # 2. 将计划注入到下一轮对话的上下文
    plan = self.get_plan(plan_id)
    plan_context = _build_plan_execution_context(plan)
    
    # 3. 发送给 Agent 一条"继续按计划执行"的系统消息
    continuation_prompt = (
        f"用户已批准计划（plan_id={plan_id}）。"
        f"请按以下步骤顺序执行，每完成一步告知进度：\n"
        f"{_format_steps(plan.steps)}"
    )
    
    # 4. 触发新一轮 Agentic Loop（执行模式）
    async for event in query(
        prompt=continuation_prompt,
        messages=self.messages,
        tools=await get_enabled_tools(...),  # 完整工具集（执行模式）
        session=self,
        options=QueryOptions(permission_mode=PermissionMode.DEFAULT),
    ):
        yield event
```

### Agent 执行过程中的步骤追踪

执行阶段，Agent 每完成一个步骤后，`SessionManager` 写入 `plan_step_done` 事件：

```
Agent 执行工具（FileEditTool / BashTool）
    │
    ▼
Agent 输出文本："步骤 1 完成：已修改 auth.py"
    │
    ▼
SessionManager 检测到 plan 关联消息
    │
    ▼
写入 plan_step_done JSONL 事件
    │
    ▼
UI 更新进度（步骤 1 标记为 ✓）
```

### 执行中断与恢复

若 Agent 执行中途中断（网络错误、用户中止等），通过 JSONL 恢复：

1. 重启时，`load_plan_from_log()` 找到 `status=executing` 的计划
2. 读取已完成的 `plan_step_done` 事件，确认当前步骤进度
3. 继续从上次中断的步骤开始执行

---

## 与 Agent Loop 的耦合点

### System Prompt Additions 注入

在 `query_core()` 的 `build_system_prompt()` 阶段，会检查当前 `permission_mode`：

```python
# pode_agent/services/system/system_prompt.py

async def build_system_prompt(context, tools, options) -> str:
    base = SYSTEM_PROMPT_BASE
    
    # ★ Plan Mode 附加提示（当 permission_mode == PLAN 时注入）
    if options.permission_mode == PermissionMode.PLAN:
        base += PLAN_MODE_SYSTEM_PROMPT_ADDITION
    
    # 其他动态部分...
    return base

PLAN_MODE_SYSTEM_PROMPT_ADDITION = """
<plan_mode>
你正处于**计划模式**。在此模式下：
1. 只允许使用只读工具（文件读取、搜索、grep 等）
2. 不得修改任何文件或执行有副作用的命令
3. 你的目标是充分探索代码库，然后调用 exit_plan_mode 工具，输出一份完整的执行计划
4. 计划必须包含：目标、步骤（含工具建议）、验收标准、风险、回滚方案
</plan_mode>
"""
```

> 📖 System Prompt 的完整构建逻辑详见 [agent-loop.md § System Prompt 动态组装](./agent-loop.md#system-prompt-动态组装)。

### PermissionMode 对 `can_use_tool` 的影响

```
query_core() 递归调用
    │
    ├─ build_system_prompt() ← 检查 permission_mode == PLAN，注入提示
    │
    └─ ToolUseQueue.run(tool_use_block)
            │
            └─ check_permissions_and_call_tool()
                    │
                    └─ PermissionEngine.has_permissions()
                            │
                            ├─ permission_mode == PLAN 且 tool.is_read_only() == False
                            │   → PermissionResult.DENIED（硬拒绝，不询问用户）
                            │
                            └─ 其他情况 → 正常权限流程
```

> 📖 权限检查的完整顺序详见 [tools-system.md § Plan Mode 硬拒绝](./tools-system.md#plan-mode-硬拒绝permission-mode-b-策略)。

### permission_mode 的传播路径

```
EnterPlanModeTool.call()
    └─ context.options.permission_mode = PermissionMode.PLAN
            │
            ▼
query_core() 递归（携带更新后的 options）
    │
    ├─ build_system_prompt(options) ← 检测到 PLAN，注入提示
    │
    └─ check_permissions_and_call_tool(context)
            └─ context.options.permission_mode == PLAN → 硬拒绝写工具
```

`query_core()` 的每次递归都会透传同一个 `context.options` 对象，所以 `EnterPlanModeTool` 修改后立即在后续所有轮次生效，无需额外传参。

---

## 与 SubAgent / TaskTool 的关系

### 当前范围（Phase 3）

Phase 3 实现的 Plan Mode 是**单 Agent 模式**：
- 计划由主 Agent 生成
- 执行也由主 Agent 按步骤推进
- 不涉及子 Agent 并行执行

### TaskTool（Phase 5+）

`TaskTool` 是 Kode-Agent 中支持"子任务 Agent"的工具，允许将计划的某个步骤委托给独立的子 Agent 执行：

```
主 Agent（计划模式）
    │
    ├── 步骤 1：探索代码库（FileReadTool）
    ├── 步骤 2：TaskTool(subtask="重构 auth.py")
    │       └── 子 Agent（独立 Agent Loop）
    │               ├── FileEditTool
    │               └── BashTool（运行测试）
    └── 步骤 3：验证结果（BashTool）
```

**注意**：`TaskTool` 在 Phase 5 实现，与 MCP 和插件系统同期。Plan Mode 的核心（Phase 3）不依赖 `TaskTool`。

---

## 分阶段实现建议

| 子功能 | 实现阶段 | 说明 |
|--------|---------|------|
| `PermissionMode.PLAN` 枚举值 | Phase 1（✅ 权限系统框架） | 权限引擎框架中已定义 |
| Plan Mode 硬拒绝规则（`permission_mode == PLAN → DENIED`） | Phase 1（✅ 权限系统框架） | `PermissionEngine` 的规则步骤 5 |
| `Plan` / `PlanStep` Pydantic 数据模型 | Phase 3 | 与 EnterPlanModeTool 一同实现 |
| Plan JSONL 事件类型（`plan_created` 等） | Phase 3 | 扩展 `SessionEvent` |
| `EnterPlanModeTool` | Phase 3 | 切换 permission_mode + 返回提示 |
| `ExitPlanModeTool` | Phase 3 | 输出 Plan 对象 + 重置 permission_mode |
| Plan Mode System Prompt Additions | Phase 3 | `build_system_prompt()` 中注入 |
| `load_plan_from_log()` 会话恢复 | Phase 3 | JSONL replay |
| UI 计划显示（结构化渲染） | Phase 4 | Textual Widget 展示 PlanStep 列表 |
| UI 审批/拒绝交互 | Phase 4 | 审批按钮 + 拒绝原因输入 |
| 执行进度追踪（`plan_step_done` 事件） | Phase 4 | 配合 UI 进度显示 |
| `TaskTool`（子 Agent 执行） | Phase 5 | 依赖 MCP 架构 |
| 计划模板（预设结构化提示） | Phase 6 | 优化 Agent 计划质量 |

---

## 映射表：Kode-Agent → Pode-Agent

| Kode-Agent（TypeScript）概念 | Pode-Agent（Python）计划模块/文件 |
|-----------------------------|----------------------------------|
| `EnterPlanMode` 工具（`src/tools/...`） | `pode_agent/tools/agent/plan_mode.EnterPlanModeTool` |
| `ExitPlanMode` 工具 | `pode_agent/tools/agent/plan_mode.ExitPlanModeTool` |
| `permissionMode: 'plan'` | `PermissionMode.PLAN`（`pode_agent/core/permissions/engine.py`） |
| Plan mode system prompt additions | `PLAN_MODE_SYSTEM_PROMPT_ADDITION`（`pode_agent/services/system/system_prompt.py`） |
| `isConcurrencySafe` / `isReadOnly` 对工具的影响 | `Tool.is_read_only()` + `PermissionEngine` 硬拒绝 |
| 计划存储（session log） | Session JSONL 事件（`plan_created` / `plan_step_done` 等） |
| `taskTool`（子任务 Agent） | `pode_agent/tools/agent/task.TaskTool`（Phase 5） |
| `permissionMode` 传播路径 | `ToolUseContext.options.permission_mode`（透传到每次递归） |
| 计划审批 UI | `pode_agent/ui/widgets/plan_approval.py`（Phase 4） |
