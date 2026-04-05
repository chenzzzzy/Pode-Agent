# Pode-Agent UI 交互打通修复提示词

## 背景

本提示词基于以下资料综合审计整理：

- `README.md`
- `docs/phases.md`
- `docs/modules.md`
- `docs/plan-mode.md`
- 当前 Python 后端、JSON-RPC 桥接层、`src/ui/` Ink 前端实现

当前仓库文档多处声明 UI 已达到 “Phase 4/5 已完成”“深度 1:1 复刻 Kode-Agent”“Plan Mode / Resume / Doctor / Help / SubAgent / 权限审批链路完整可用” 的状态，但结合现有代码实现来看，UI 仍停留在“可运行的最小 REPL 壳 + 部分状态占位”的阶段，距离文档宣称的完整交互闭环还有明显差距。

本文件不是产品说明，而是给后续修复 Agent 的执行提示词。目标是让后续 Agent 仅打开本文件，就能知道：

- 现在到底哪些 UI 主链路没有打通
- 这些问题为什么成立
- 修复顺序应该是什么
- 修完以后怎么验证

## 给修复 Agent 的工作要求

- 必须先修 `P0`，再修 `P1/P2`。不要先做视觉 polish。
- 优先修协议、事件、状态机和前后端契约，不要优先改文案和样式。
- 必须先对齐 Python `SessionEvent`、JSON-RPC 映射、Ink `useSession` 状态更新链路，再改帮助文案、提示语和辅助屏。
- 不要因为当前文档声称“已完成”就保留失效行为；以当前代码真实行为和用户链路闭环为准。
- 本文档本身不要求新增运行时 API，但在修复过程中必须明确对齐以下契约：
  - `SessionEvent -> JSON-RPC notification -> useSession state update`
  - Python 工具名 / 输入字段名 与 Ink 权限 UI 的映射关系
  - `session/list_logs` / `session/load_log` 的返回结构与 Resume UI 的期望结构
  - `plan/*` 与 `sub_agent/*` 事件是否真的会被发出、字段是否完整、UI 是否真的消费

## P0 — 必须先打通的主链路

### UI-01: 工具执行进度被缓存到结束后才显示，长任务没有实时反馈

**用户影响**

- 用户在运行长 Bash、长文件处理、网络工具时，看不到真实执行过程。
- 当前 REPL 更像“卡住思考”，而不是“正在执行工具”。
- 这会直接削弱用户对 Agent 行为的可理解性和信任感。

**根因**

- `pode_agent/app/query.py:573-585` 中，工具 progress 事件先进入 `progress_queue`，等 `collect_tool_result()` 返回后才统一 `yield`。
- 这意味着工具运行中的增量反馈不会实时送到 UI，而是被延迟到工具执行结束之后。
- 虽然 `pode_agent/core/tools/executor.py:16-41` 已支持 progress callback，但主循环没有把这条能力真正打通到前端。

**涉及文件**

- `pode_agent/app/query.py`
- `pode_agent/core/tools/executor.py`
- `src/ui/src/hooks/useSession.ts`
- `src/ui/src/components/Message.tsx`

**修复要求**

- 让 `TOOL_PROGRESS` 事件在工具执行期间实时向外 `yield`，而不是等工具结束后再统一输出。
- 保证长耗时工具至少能在 UI 中呈现“开始执行 -> 持续进度 -> 完成/失败”的连续反馈。
- 如果需要调整 `collect_tool_result()`、`query.py` 或 `ToolUseQueue`，优先保证用户侧实时感知正确。

**验收标准**

- 长时间运行的工具在 Ink UI 中能持续更新，而不是只在结束后一次性显示。
- `session/tool_progress` 到 `useSession` 的更新路径是真正流式的。
- 用户能明确区分“模型在思考”和“工具正在执行”。

### UI-02: `tool_use_start` 不携带真实 `tool_input`，导致工具卡片经常是空的

**用户影响**

- UI 经常只能渲染出 `bash()`、`file_read()`、`tool()` 这种空壳信息。
- 用户看不到 Agent 正在对哪个路径、哪个命令、哪个输入参数执行操作。
- 即使工具真的在运行，界面也很难解释它在做什么。

**根因**

- `pode_agent/app/query.py:482-485` 发送 `TOOL_USE_START` 时只包含 `tool_name` 和 `tool_use_id`，没有把真实 `tool_input` 带出来。
- `pode_agent/entrypoints/ui_bridge.py:94-100` 却把 `tool_input` 当作预期字段透传给前端，最终大多只能得到空对象。
- `src/ui/src/hooks/useSession.ts:90-109` 会把这个空 `tool_input` 存到 `AssistantToolUseMessage`。
- `src/ui/src/components/Message.tsx:111-123` 又依赖 `toolInput` 渲染参数摘要，最终形成空工具卡片。

**涉及文件**

- `pode_agent/app/query.py`
- `pode_agent/entrypoints/ui_bridge.py`
- `src/ui/src/hooks/useSession.ts`
- `src/ui/src/components/Message.tsx`

**修复要求**

- 在 `TOOL_USE_START` 事件中提供真实、可展示的 `tool_input`。
- 保证 JSON-RPC 桥接层和前端类型定义对这个字段的约定完全一致。
- 让工具卡片至少能稳定显示命令、文件路径、核心参数摘要。

**验收标准**

- Bash 工具卡片能显示真实命令。
- 文件系统工具卡片能显示真实路径和关键参数。
- 不再出现大面积的空参数工具卡片。

### UI-03: Plan Mode 只有事件占位，没有真正打通成完整状态机

**用户影响**

- 文档宣称支持 Plan Mode 计划生成、审批、步骤进度，但用户在实际 REPL 中无法获得可靠的计划闭环。
- UI 可能显示某些计划占位文本，但计划的创建、审批、执行状态并没有真正从后端贯通。

**根因**

- `src/ui/src/hooks/useSession.ts:229-320` 已经监听 `plan/created`、`plan/approved`、`plan/step_start`、`plan/step_done`、`plan/done`、`plan/cancelled`。
- 但全仓搜索可见，`PLAN_*` 事件目前主要只定义在 `pode_agent/types/session_events.py`，并映射在 `pode_agent/entrypoints/ui_bridge.py:145-181`。
- 现有 agent loop 中没有可靠地发出这整套 `PLAN_*` 事件，导致 UI 的 plan 状态消费端与后端生产端脱节。
- `pode_agent/tools/agent/plan_mode.py:71-89` 的 `EnterPlanModeTool` 只是返回普通结果，并未建立完整的 plan 生命周期。
- `pode_agent/app/query.py:723-743` 构造的是 `ToolUseContext` 的 `ToolOptions` 副本，Plan Mode 切换不会自然写回主会话的运行状态。

**涉及文件**

- `src/ui/src/hooks/useSession.ts`
- `pode_agent/entrypoints/ui_bridge.py`
- `pode_agent/types/session_events.py`
- `pode_agent/tools/agent/plan_mode.py`
- `pode_agent/app/query.py`
- `docs/plan-mode.md`

**修复要求**

- 先确认 Plan Mode 的真实状态源在哪里，再统一由后端发出完整 `PLAN_*` 事件。
- 明确 `enter_plan_mode -> plan draft -> approval -> step progress -> done/cancelled` 的完整状态机。
- 让主会话真正持有 Plan Mode 状态，而不是只在 tool result 文本中“看起来像进入了计划模式”。
- Ink UI 只消费真实后端状态，不自行猜测计划是否存在。

**验收标准**

- 可以在 REPL 中看到真实的计划创建、步骤开始、步骤完成、结束/取消事件。
- Plan 状态在后端和 UI 中保持一致，不靠字符串推断。
- Plan 相关 UI 不再只是文本占位，而是消费真实事件流。

### UI-04: SubAgent 生命周期事件只打通了桥接层，UI 没有消费

**用户影响**

- README 和文档宣称支持 SubAgent / TaskTool 前后台执行，但用户侧几乎看不到子代理生命周期。
- Task 工具即使运行了，界面也缺少“已启动 / 运行中 / 完成 / 失败”的可视反馈。

**根因**

- `pode_agent/entrypoints/ui_bridge.py:184-216` 已经把 `sub_agent/started`、`sub_agent/progress`、`sub_agent/completed`、`sub_agent/failed` 映射好了。
- `pode_agent/app/query.py:601-604` 与 `pode_agent/app/query.py:793-838` 也能在部分 Task 场景中产出 SubAgent 事件。
- 但 `src/ui/src/hooks/useSession.ts` 没有注册这些 `sub_agent/*` 通知处理器，导致 UI 完全不消费这条事件流。

**涉及文件**

- `pode_agent/app/query.py`
- `pode_agent/entrypoints/ui_bridge.py`
- `src/ui/src/hooks/useSession.ts`
- `src/ui/src/components/Message.tsx`

**修复要求**

- 在 `useSession` 中完整接入 `sub_agent/*` 事件。
- 明确这些事件在 UI 中应显示为哪类消息或状态卡片。
- 保证 TaskTool 相关用户路径至少可见：启动、进度、完成、失败。

**验收标准**

- 触发 Task / SubAgent 路径时，UI 能看到完整生命周期状态。
- 子代理结果不再只是埋在工具结果文本里。
- 后端发出的 `sub_agent/*` 事件在前端有稳定消费逻辑。

## P1 — 高优先级可用性问题

### UI-05: Resume / Doctor / Help 屏存在代码文件，但没有接入真实 REPL 流程

**用户影响**

- 仓库里看起来已经有 ResumeConversation、Doctor、Help，但用户在当前 REPL 中无法进入这些屏幕。
- 这会制造“功能已实现”的假象，实际上用户路径并不存在。

**根因**

- `src/ui/src/index.tsx:51-59` 入口始终直接渲染 `REPL`，没有任何 screen routing。
- `src/ui/src/screens/ResumeConversation.tsx`、`src/ui/src/screens/Doctor.tsx`、`src/ui/src/components/Help.tsx` 都没有接入真实导航。
- Resume 协议还存在结构错位：
  - 前端 `src/ui/src/screens/ResumeConversation.tsx:12-24` 期望结构化的 `LogEntry`
  - 前端类型 `src/ui/src/rpc/types.ts:81-82` 只声明 `session/list_logs -> string[]`
  - 后端 `pode_agent/entrypoints/ui_bridge.py:565-583` 也只返回日志路径字符串，没有日期、标题、消息数

**涉及文件**

- `src/ui/src/index.tsx`
- `src/ui/src/screens/ResumeConversation.tsx`
- `src/ui/src/screens/Doctor.tsx`
- `src/ui/src/components/Help.tsx`
- `src/ui/src/rpc/types.ts`
- `pode_agent/entrypoints/ui_bridge.py`

**修复要求**

- 建立真实的 screen/router 状态，让 REPL、Resume、Doctor、Help 能被实际进入和退出。
- 统一 Resume 所需的 RPC 数据结构，不要让 UI 期待结构化数据而后端只返回字符串列表。
- Doctor 和 Help 只有在能被用户实际打开时才算完成。

**验收标准**

- 用户可以从 REPL 中进入 Resume、Doctor、Help。
- Resume 可以列出历史会话并选择加载。
- Doctor 和 Help 不再是孤立文件，而是真实可触达的 UI 功能。

### UI-06: 权限对话框的工具名与字段名映射和真实后端不一致

**用户影响**

- 权限对话框经常落到 fallback，不能展示本应有的 Bash 命令预览、文件 diff、Plan 说明。
- 用户审批时看到的内容不准确，直接影响安全感和判断质量。

**根因**

- `src/ui/src/components/permissions/PermissionRequest.tsx:21-40` 使用的是 `Bash`、`FileEdit`、`EnterPlanMode` 等 PascalCase 名称映射。
- 实际 Python 工具名是 snake_case：
  - `pode_agent/tools/system/bash.py:42-45` -> `bash`
  - `pode_agent/tools/filesystem/file_edit.py:31-35` -> `file_edit`
  - `pode_agent/tools/agent/plan_mode.py:46-54` / `97-100` -> `enter_plan_mode` / `exit_plan_mode`
- 字段名也不一致：
  - 前端权限 UI 读 `old_string/new_string`
  - 后端 `file_edit` 实际是 `old_str/new_str`

**涉及文件**

- `src/ui/src/components/permissions/PermissionRequest.tsx`
- `pode_agent/tools/system/bash.py`
- `pode_agent/tools/filesystem/file_edit.py`
- `pode_agent/tools/agent/plan_mode.py`
- 其他所有需要专用权限预览的工具实现

**修复要求**

- 统一工具命名规范，前端权限映射必须基于真实后端工具名。
- 统一权限 UI 读取的输入字段名，必须和 Python 工具 schema 保持一致。
- 专用权限组件只有在真实 payload 能稳定命中时才算修复完成。

**验收标准**

- Bash 审批显示真实命令。
- FileEdit 审批显示真实 diff 输入字段。
- Plan Mode 审批不再因为工具名不匹配而退回 fallback。

### UI-07: 输入体验没有真正用上历史导航，退出语义也不完整

**用户影响**

- 用户按上/下键时实际不是历史导航，而只是光标跳到行首/行尾。
- 空输入时 `Ctrl+C` / `Esc` 的退出行为不稳定或根本无效。
- Help 文案在教用户使用当前并不存在的行为。

**根因**

- `src/ui/src/components/PromptInput.tsx:179-186` 中，上/下键只是移动光标，不是历史导航。
- `src/ui/src/hooks/useArrowKeyHistory.ts:18-67` 已有历史导航逻辑，但没有接入 `PromptInput` 或 `REPL`。
- `src/ui/src/screens/REPL.tsx:172-178` 没有向 `PromptInput` 传递 `onExit`。
- `src/ui/src/components/Help.tsx:16-36` 宣称支持 `Up/Down` 历史、`Ctrl+D` 双击退出、`/config`、`/cost` 等命令。
- 但后端内建 slash command 实际只有 `/help`、`/clear`、`/model`，见 `pode_agent/tools/interaction/slash_command.py:22-32`。

**涉及文件**

- `src/ui/src/components/PromptInput.tsx`
- `src/ui/src/screens/REPL.tsx`
- `src/ui/src/hooks/useArrowKeyHistory.ts`
- `src/ui/src/components/Help.tsx`
- `pode_agent/tools/interaction/slash_command.py`

**修复要求**

- 让输入框真正接入历史导航逻辑。
- 统一 `Ctrl+C`、`Ctrl+D`、`Esc` 在“请求进行中 / 输入非空 / 输入为空”三种状态下的行为。
- Help 文案必须只描述当前真实可用行为，不能继续超前宣传。

**验收标准**

- 上/下键能实际浏览输入历史。
- 退出行为在空输入和加载状态下都有明确且稳定的结果。
- Help 中列出的快捷键和 slash commands 与真实功能一致。

## P2 — 文档与质量门禁修正

### UI-08: 前端质量门禁当前不是绿色，类型检查和测试链路未收口

**用户影响**

- 即使只做 UI 文档和交互修复，也缺少一个可靠的前端质量门禁。
- 后续 agent 很容易在“代码看起来能跑”的情况下继续累积回归。

**根因**

- 当前 `bun run typecheck` 失败，主要暴露出：
  - `src/ui/src/hooks/useSession.ts` 使用 `findLastIndex`，但 `src/ui/tsconfig.json:3` 仍是 `ES2022`
  - `src/ui/src/components/permissions/PermissionRequest.tsx` 存在 `unknown -> ReactNode` 类型问题
  - `src/ui/src/rpc/client.ts` 存在泛型不匹配
- 当前 `bun test` 也无法正常跑通，`src/ui/bunfig.toml:1-2` 会直接导致 Bun 配置加载错误。

**涉及文件**

- `src/ui/tsconfig.json`
- `src/ui/bunfig.toml`
- `src/ui/src/hooks/useSession.ts`
- `src/ui/src/components/permissions/PermissionRequest.tsx`
- `src/ui/src/rpc/client.ts`

**修复要求**

- 让 `bun run typecheck` 恢复为绿色。
- 让 `bun test` 至少能正常启动并执行测试，而不是在配置阶段失败。
- 在交互主链路修复完成后，把这两个命令纳入必跑验证。

**验收标准**

- `bun run typecheck` 通过。
- `bun test` 通过。
- 前端门禁可以作为后续 UI 修复的回归保护。

### UI-09: README 和 phases 文档对 UI 完成度存在明显过度声明

**用户影响**

- 新接手的 agent 会被文档误导，以为大量 UI 功能已经完整实现。
- 这会导致修复方向错误，甚至为了维持文档叙事而保留失效实现。

**根因**

- `README.md:22-50` 明确写了 “Phase 0-5 已完成”“完整终端 UI”“SubAgent 已实现”。
- `docs/phases.md:668-845` 声称：
  - REPL 深度复刻
  - 15+ 消息组件
  - 15+ 权限组件
  - 16 个 hooks
  - Resume / Doctor / Help / MCPServerApproval
  - 完整 PromptInput
- 但当前 `src/ui/src/components/Message.tsx:5-6` 自己就注明仍是 “initial simplified version”。
- 当前 `src/ui/` 中大量组件、hooks、辅助 screen 仍未真正接入主链路。

**涉及文件**

- `README.md`
- `docs/phases.md`
- `src/ui/src/components/Message.tsx`
- `src/ui/` 全体实现

**修复要求**

- 先以代码修复为主，不要先改 README 自圆其说。
- 当且仅当真实行为与文档描述对齐之后，再更新 README / phases / modules 等宣称性文档。
- 如果短期内无法补齐，应下调文档表述，避免继续误导后续 agent。

**验收标准**

- 文档中的完成度描述与真实代码能力一致。
- 不再出现“文档已完成，但入口不可达 / 事件未接 / 仅有占位文件”的情况。

## 修复顺序建议

1. 先修 `UI-01` 与 `UI-02`
   - 打通工具开始、进度、结束的实时事件链
   - 让工具卡片先具备真实可见性
2. 再修 `UI-03` 与 `UI-04`
   - 统一 Plan Mode / SubAgent 的后端状态源和前端消费逻辑
3. 然后修 `UI-05`、`UI-06`、`UI-07`
   - 把 Resume / Doctor / Help 真正接进 REPL
   - 对齐权限 UI 和输入体验
4. 最后修 `UI-08`、`UI-09`
   - 收口 typecheck / test
   - 回头更新 README 和 phases 等文档

## 验收清单

### 自动化验收

- `bun run typecheck` 通过
- `bun test` 通过
- 与 UI 主链路相关的测试能覆盖：
  - 工具开始/进度/结束事件
  - 权限请求事件
  - Plan 事件
  - SubAgent 事件
  - Resume RPC 数据结构

### 交互闭环验收

- 长时间运行的工具在 Ink UI 中能实时显示 progress
- 工具卡片能显示真实 command/path/input 摘要
- Plan 创建、审批、步骤进度、完成/取消都能在 UI 中稳定渲染
- SubAgent 的 started/progress/completed/failed 都能在 UI 中渲染
- Resume 可以列出日志、选择会话并恢复消息
- 权限对话框能正确命中真实工具类型并显示专用预览
- 上下键历史、退出行为、Help 文案与真实行为一致

### 最小手动冒烟测试

1. 启动 REPL
   - 执行 `uv run pode`
   - 确认 Ink UI 正常进入主界面
2. 运行一个安全 Bash
   - 例如触发 `bash` 的只读命令
   - 确认工具卡片有真实命令，且有实时进度/结果
3. 触发一次权限请求
   - 例如触发写文件或危险 Bash
   - 确认权限 UI 显示真实参数而不是 fallback 空内容
4. 触发一次 Plan Mode 路径
   - 确认 `plan/*` 事件链真实出现并更新 UI
5. 触发一次 SubAgent / Task 路径
   - 若当前环境可用，确认 `sub_agent/*` 生命周期在 UI 中可见

