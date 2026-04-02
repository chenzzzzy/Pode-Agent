# Pode-Agent 核心引擎：Agentic Loop

> 版本：1.0.0 | 状态：草稿 | 更新：2026-03-31  
> 本文档是 **Agentic Loop 引擎的权威设计文档**。  
> 所有其他文档（data-flows.md、modules.md、api-specs.md）在提及核心循环时均引用本文档。

---

## 目录

1. [概述：什么是 Agentic Loop](#概述)
2. [递归式主循环：`query()` 与 `query_core()`](#递归式主循环)
3. [ToolUseQueue：并发工具调度器](#toolUseQueue并发工具调度器)
4. [Hook 系统：四个注入点](#hook-系统四个注入点)
5. [Auto-compact：自动上下文压缩](#auto-compact自动上下文压缩)
6. [System Prompt 动态组装](#system-prompt-动态组装)
7. [Stop Hook 重入机制](#stop-hook-重入机制)
8. [`check_permissions_and_call_tool` 完整管线](#check_permissions_and_call_tool-完整管线)
9. [与其他模块的关系映射](#与其他模块的关系映射)
10. [实现阶段划分](#实现阶段划分)

---

## 概述

Pode-Agent 的"智能"来自一个**递归式 Agentic Loop**——这是让一个普通 LLM 调用变成真正 Agent 的核心机制。

```
用户输入
   │
   ▼
query(messages, system_prompt, tools)
   │
   ▼
┌──────────────────────────────────────────────┐
│  query_core(messages, system_prompt, tools)  │
│                                              │
│  1. auto_compact(messages)                   │
│  2. build_system_prompt()                    │
│  3. llm_query(messages, system_prompt)       │
│         │                                    │
│    ┌────┴────────────────────┐               │
│    │ 有 tool_use？           │               │
│    ▼                         ▼               │
│   否                         是              │
│   │                          │               │
│  run_stop_hooks()      ToolUseQueue          │
│    │                    │                    │
│  block?              执行所有工具             │
│   / \                    │                   │
│  是  否            收集 tool_results         │
│  │    │                  │                   │
│ 重入  结束      yield* query_core(           │
│(≤5次)           messages + assistant_msg     │
│                 + tool_results, ...)          │
└──────────────────────────────────────────────┘
```

**关键设计**：循环不是 `while True`，而是**递归 AsyncGenerator**（Python 的 `yield from query_core(...)`）。  
这让每次工具执行后的消息历史自然增长，并且 Stop Hook 重入也通过递归优雅实现。

---

## 递归式主循环

### 函数签名

```python
# app/query.py

async def query(
    prompt: str,
    system_prompt: str,
    tools: list[Tool],
    messages: list[Message],
    session: SessionManager,
    options: QueryOptions,
) -> AsyncGenerator[SessionEvent, None]:
    """
    外层入口：处理会话持久化（日志写入），然后委托给 query_core()。
    对应 Kode-Agent src/app/query.ts: query()，L477-520。
    """
    # 处理 @mention，构建初始 UserMessage
    user_msg = await process_mentions(prompt, options.cwd)
    session.save_message(user_msg)
    yield SessionEvent(type=USER_MESSAGE, data=user_msg)

    # 委托给核心循环
    async for event in query_core(
        messages=[*messages, user_msg],
        system_prompt=system_prompt,
        tools=tools,
        session=session,
        options=options,
        hook_state=HookState(),
        stop_hook_attempts=0,
    ):
        yield event


async def query_core(
    messages: list[Message],
    system_prompt: str,
    tools: list[Tool],
    session: SessionManager,
    options: QueryOptions,
    hook_state: HookState,
    stop_hook_attempts: int = 0,
) -> AsyncGenerator[SessionEvent, None]:
    """
    核心递归循环。每次递归代表一轮 LLM 调用 + 工具执行。
    对应 Kode-Agent src/app/query.ts: queryCore()，L522-826。
    """
    # ── Step 1：前置处理 ──────────────────────────────────────────
    # 1a. 自动压缩（若消息过多）
    messages = await auto_compact_if_needed(messages, options)

    # 1b. 用户输入提交 Hook（仅第一轮）
    if stop_hook_attempts == 0:
        hook_result = await run_user_prompt_submit_hooks(messages, hook_state)
        messages = hook_result.messages  # Hook 可修改消息

    # 1c. 构建动态 System Prompt（详见"System Prompt 动态组装"节）
    final_system_prompt = await build_system_prompt(
        base=system_prompt,
        context=await get_project_context(options.cwd),
        tools=tools,
        messages=messages,
        hook_state=hook_state,
        options=options,
    )

    # ── Step 2：调用 LLM ──────────────────────────────────────────
    assistant_message, tool_uses = None, []
    async for event in query_llm(
        messages=messages,
        system_prompt=final_system_prompt,
        tools=tools,
        options=options,
    ):
        yield event  # 透传流式文本事件给 UI
        if event.type == ASSISTANT_MESSAGE_DONE:
            assistant_message = event.message
            tool_uses = extract_tool_uses(assistant_message)

    # ── Step 3：无工具调用 → Stop Hook → 终止或重入 ──────────────
    if not tool_uses:
        async for event in _handle_no_tool_use(
            messages=messages,
            assistant_message=assistant_message,
            system_prompt=system_prompt,
            tools=tools,
            session=session,
            options=options,
            hook_state=hook_state,
            stop_hook_attempts=stop_hook_attempts,
        ):
            yield event
        return  # 终止递归

    # ── Step 4：有工具调用 → 并发调度执行 ────────────────────────
    tool_results: list[ToolResult] = []
    async for event in ToolUseQueue(tool_uses, tools, session, options).run():
        yield event
        if event.type == TOOL_RESULT:
            tool_results.append(event.data)

    # ── Step 5：将工具结果追加到消息历史 ─────────────────────────
    tool_result_message = build_tool_result_message(tool_uses, tool_results)
    session.save_message(assistant_message)
    session.save_message(tool_result_message)
    yield SessionEvent(type=COST_UPDATE, data=session.get_total_cost())

    # ── Step 6：递归调用自身（核心！）────────────────────────────
    async for event in query_core(
        messages=[*messages, assistant_message, tool_result_message],
        system_prompt=system_prompt,
        tools=tools,
        session=session,
        options=options,
        hook_state=hook_state,
        stop_hook_attempts=0,  # 正常递归重置计数
    ):
        yield event
```

### 为什么使用递归而非 `while True`

| 维度 | `while True` | 递归 AsyncGenerator |
|------|-------------|---------------------|
| **消息历史** | 需要手动维护可变列表 | 每次递归自然传入不可变快照 |
| **Stop Hook 重入** | 需要额外标志位 | 通过 `stop_hook_attempts` 参数天然表达 |
| **调用链追踪** | 扁平，难以区分轮次 | 调用栈清晰，每轮 LLM 调用对应一个栈帧 |
| **Python 语义** | `break`/`continue` 逻辑碎片化 | `yield from` 让 AsyncGenerator 委托自然组合 |
| **测试** | 需要维护外部状态 | 每次调用参数完备，纯函数式更易测试 |

Python 中 `yield* queryCore(...)` 的等价写法：
```python
async for event in query_core(...):
    yield event
```

---

## ToolUseQueue：并发工具调度器

当 LLM 在一次回复中请求多个工具调用时，`ToolUseQueue` 负责调度这些调用——并发安全的工具并行执行，非并发安全的工具串行执行。

对应 Kode-Agent `src/app/query.ts: ToolUseQueue`（L184-435）。

### 并发安全的概念

```python
class Tool(ABC):
    @property
    def is_concurrency_safe(self) -> bool:
        """
        工具是否可以与其他工具并发执行。
        
        True（并发安全）：只读操作，或操作不同资源。
          示例：FileReadTool、GrepTool、WebFetchTool、LsTool
        
        False（非并发安全）：写操作，或有副作用，或修改共享状态。
          示例：BashTool、FileWriteTool、FileEditTool、NotebookEditTool
        
        默认：False（保守策略，子类可覆盖）
        """
        return False
```

### 队列调度逻辑

```
tool_uses = [A(safe), B(safe), C(unsafe), D(safe), E(unsafe)]

处理顺序（barrier 机制）：

批次 1：A、B 并发执行（均为 safe）
          ↓ 等待 A、B 全部完成
批次 2：C 单独执行（unsafe，形成 barrier）
          ↓ 等待 C 完成
批次 3：D 执行（safe，但 E 紧随其后是 unsafe）
          ↓ 实际上：D 和 E 作为分组处理
批次 4：E 单独执行（unsafe）
```

### Python 实现方案

```python
class ToolUseQueue:
    """
    工具并发调度器。
    对应 Kode-Agent ToolUseQueue 类。
    """

    def __init__(
        self,
        tool_uses: list[ToolUseBlock],
        tools: list[Tool],
        session: SessionManager,
        options: QueryOptions,
    ):
        self.tool_uses = tool_uses
        self.tools = tools
        self.session = session
        self.options = options
        self._abort_event = asyncio.Event()

    async def run(self) -> AsyncGenerator[SessionEvent, None]:
        """
        按并发安全性分批执行工具调用。
        
        算法：
        1. 将 tool_uses 按连续的 safe/unsafe 分组
        2. safe 组内并发执行（asyncio.gather）
        3. unsafe 工具单独执行（形成 barrier）
        4. 任何工具失败时，abort 同批次其他工具
        """
        groups = self._group_by_concurrency(self.tool_uses)

        for group in groups:
            if len(group) == 1 or not self._is_safe(group[0]):
                # 串行执行（单个 unsafe 工具或单独工具）
                for tool_use in group:
                    async for event in self._run_single(tool_use):
                        yield event
            else:
                # 并发执行（多个 safe 工具）
                async for event in self._run_concurrent(group):
                    yield event

    def _group_by_concurrency(
        self, tool_uses: list[ToolUseBlock]
    ) -> list[list[ToolUseBlock]]:
        """将连续的 safe 工具分为一组，unsafe 工具各自单独一组"""
        groups: list[list[ToolUseBlock]] = []
        current_safe_group: list[ToolUseBlock] = []

        for tool_use in tool_uses:
            tool = self._find_tool(tool_use.name)
            if tool and tool.is_concurrency_safe:
                current_safe_group.append(tool_use)
            else:
                if current_safe_group:
                    groups.append(current_safe_group)
                    current_safe_group = []
                groups.append([tool_use])  # unsafe 工具独立成组

        if current_safe_group:
            groups.append(current_safe_group)

        return groups

    async def _run_concurrent(
        self, tool_uses: list[ToolUseBlock]
    ) -> AsyncGenerator[SessionEvent, None]:
        """并发执行多个工具，通过 asyncio.Queue 汇总事件流"""
        event_queue: asyncio.Queue[SessionEvent | None] = asyncio.Queue()

        async def run_and_enqueue(tool_use: ToolUseBlock) -> None:
            try:
                async for event in self._run_single(tool_use):
                    await event_queue.put(event)
            except Exception as e:
                await event_queue.put(SessionEvent(type=TOOL_ERROR, data=str(e)))
                self._abort_event.set()  # 通知其他并发工具终止
            finally:
                await event_queue.put(None)  # sentinel

        tasks = [asyncio.create_task(run_and_enqueue(tu)) for tu in tool_uses]
        completed = 0

        while completed < len(tasks):
            event = await event_queue.get()
            if event is None:
                completed += 1
            else:
                yield event

        # 确保所有任务完成
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _run_single(
        self, tool_use: ToolUseBlock
    ) -> AsyncGenerator[SessionEvent, None]:
        """执行单个工具调用，包含完整的权限和 hook 管线"""
        yield SessionEvent(type=TOOL_USE_START, data=tool_use)

        async for event in check_permissions_and_call_tool(
            tool_use=tool_use,
            tools=self.tools,
            session=self.session,
            options=self.options,
            abort_event=self._abort_event,
        ):
            yield event
```

### 错误时的 sibling tool abort

当并发组中的某个工具失败时：
1. 设置 `abort_event`
2. 其他工具在下一个 `abort_event` 检查点（通常在 I/O 等待处）收到信号后终止
3. 向已取消的工具 yield `ToolResult(error="Aborted due to sibling tool failure")`

---

## Hook 系统：四个注入点

Hook 系统允许插件在 Agentic Loop 的关键节点注入行为（修改输入、阻断执行、追加系统提示等）。

对应 Kode-Agent `src/app/query.ts` 中多处 `run*Hooks()` 调用。

### 注入点总览

```
query_core 执行流程          Hook 注入点
─────────────────────────    ─────────────────────────────────────────────
用户输入进入              →  [1] run_user_prompt_submit_hooks
                               输入：messages
                               输出：modified messages | block
                               触发：每次新对话轮次开始（stop_hook_attempts == 0）

LLM 调用前                →  system_prompt 动态组装（Hook 可追加 prompt 片段）

LLM 返回 tool_use         →  [2] run_pre_tool_use_hooks（每个工具调用前）
                               输入：tool_name, tool_input
                               输出：modified input | block（阻止执行）

tool.call() 完成          →  [3] run_post_tool_use_hooks（每个工具调用后）
                               输入：tool_name, tool_input, tool_result
                               输出：modified result | block（阻止结果回传）

LLM 返回无 tool_use       →  [4] run_stop_hooks
                               输入：assistant_message, messages
                               输出：continue（重入循环）| stop（正常终止）
```

### Hook 接口定义

```python
# services/hooks/base.py

class HookResult(BaseModel):
    """所有 Hook 的统一返回类型"""
    action: Literal["continue", "block", "modify"]
    modified_data: Any = None      # action="modify" 时返回修改后的数据
    additional_system_prompt: str | None = None  # 追加到 system prompt

class HookState(BaseModel):
    """在 query_core 递归调用中传递，保存 Hook 的跨轮次状态"""
    additional_system_prompts: list[str] = []    # 各 Hook 追加的 prompt 片段
    user_prompt_hooks_ran: bool = False

# Hook 1：用户输入提交
async def run_user_prompt_submit_hooks(
    messages: list[Message],
    hook_state: HookState,
) -> HookResult:
    """
    当用户输入进入 query_core 时触发（每次新对话，非递归重入）。
    可以：修改消息内容、添加上下文、阻断整次对话。
    """

# Hook 2：工具调用前
async def run_pre_tool_use_hooks(
    tool_name: str,
    tool_input: dict,
    hook_state: HookState,
) -> HookResult:
    """
    在 check_permissions_and_call_tool 执行权限检查之前触发。
    可以：修改工具输入参数、完全阻止工具调用。
    action="block" 时，工具调用被跳过，向 LLM 返回错误消息。
    """

# Hook 3：工具调用后
async def run_post_tool_use_hooks(
    tool_name: str,
    tool_input: dict,
    tool_result: ToolResult,
    hook_state: HookState,
) -> HookResult:
    """
    tool.call() 完成后、结果回传给 LLM 之前触发。
    可以：修改工具结果、追加额外信息、阻止结果回传（向 LLM 发送替代消息）。
    """

# Hook 4：LLM 停止时
async def run_stop_hooks(
    assistant_message: AssistantMessage,
    messages: list[Message],
    hook_state: HookState,
) -> HookResult:
    """
    LLM 返回无 tool_use 的消息时触发（即 Agent 准备结束本轮对话）。
    可以：强制继续对话（action="block" 触发重入）、最多重入 MAX_STOP_HOOK_ATTEMPTS 次。
    重入时 additional_system_prompt 会被注入下一轮的 system prompt。
    """
```

### Hook 决策流程

```
pre_tool_use_hook 返回：
  action="continue"  → 执行工具（正常流程）
  action="modify"    → 用 modified_data 替换 tool_input，然后执行
  action="block"     → 跳过工具执行，向 LLM 发送 ToolResult(error="Hook blocked")

post_tool_use_hook 返回：
  action="continue"  → 将原始 tool_result 追加到消息
  action="modify"    → 将 modified_data 作为 tool_result 追加到消息
  action="block"     → 跳过结果回传（视情况而定）

stop_hook 返回：
  action="continue"  → 正常终止循环，yield SessionEvent(DONE)
  action="block"     → 触发重入（见"Stop Hook 重入机制"节）
```

---

## Auto-compact：自动上下文压缩

随着对话轮次增加，消息历史会不断增长，可能超过 LLM 的 context window 限制。  
`auto_compact_if_needed()` 在每轮 `query_core` 开始时检查并按需压缩。

对应 Kode-Agent `src/app/query.ts: checkAutoCompact()`。

### 触发条件

```python
AUTO_COMPACT_THRESHOLD_MESSAGES = 50  # 消息数阈值
AUTO_COMPACT_THRESHOLD_TOKENS = 180_000  # token 数阈值（估算）

async def auto_compact_if_needed(
    messages: list[Message],
    options: QueryOptions,
) -> list[Message]:
    """
    检查是否需要压缩，按需执行压缩，返回（可能已压缩的）消息列表。
    """
    if not options.auto_compact:
        return messages  # 配置禁用时跳过

    if (
        len(messages) < AUTO_COMPACT_THRESHOLD_MESSAGES
        and estimate_tokens(messages) < AUTO_COMPACT_THRESHOLD_TOKENS
    ):
        return messages  # 未达到阈值

    return await compact_messages(messages, options)
```

### 压缩策略

```
压缩前：[UserMsg1, AssistantMsg1, ToolResult1, ..., UserMsgN, AssistantMsgN]
              ↓
       调用 LLM 生成摘要
              ↓
压缩后：[SystemMsg("以下是之前对话的摘要：..."), UserMsgN, AssistantMsgN]
```

具体策略：
1. 保留最近 N 条消息（保证上下文连续性，通常 N=10）
2. 对之前的消息调用 LLM 生成摘要
3. 将摘要作为一条 `SystemMessage` 插入历史开头
4. yield `SessionEvent(type=COMPACT_DONE)` 通知 UI

```python
async def compact_messages(
    messages: list[Message],
    options: QueryOptions,
) -> list[Message]:
    KEEP_RECENT = 10
    to_compress = messages[:-KEEP_RECENT]
    to_keep = messages[-KEEP_RECENT:]

    summary = await generate_summary(to_compress, options)
    summary_msg = SystemMessage(content=f"[上下文已压缩]\n{summary}")

    return [summary_msg, *to_keep]
```

### 在循环中的位置

```python
async def query_core(...):
    # ← 每轮循环最开始执行压缩检查
    messages = await auto_compact_if_needed(messages, options)
    # → 后续所有步骤使用可能已压缩的 messages
```

---

## System Prompt 动态组装

每轮 `query_core` 在调用 LLM 之前，动态构建完整的 system prompt。

对应 Kode-Agent `src/app/query.ts` 中的 `getSystemPromptWithHooks()` 等相关逻辑。

### 组装顺序

```python
async def build_system_prompt(
    base: str,
    context: ProjectContext,
    tools: list[Tool],
    messages: list[Message],
    hook_state: HookState,
    options: QueryOptions,
) -> str:
    """
    动态构建完整 system prompt。
    组装顺序（各部分之间用换行分隔）：
    """
    parts: list[str] = []

    # 1. 基础 Prompt（核心人格、能力描述、安全规则）
    parts.append(base)

    # 2. 项目上下文（git 状态、目录结构、README 片段等）
    if context:
        parts.append(format_project_context(context))

    # 3. Plan Mode 追加（仅在 Plan Mode 激活时）
    if options.plan_mode:
        parts.append(PLAN_MODE_SYSTEM_PROMPT)

    # 4. Hook 追加（由之前的 stop_hook 或 user_prompt_hook 注入）
    for additional in hook_state.additional_system_prompts:
        parts.append(additional)

    # 5. Output Style 追加（JSON 模式、verbose 等）
    if options.output_style:
        parts.append(get_output_style_prompt(options.output_style))

    final_prompt = "\n\n".join(parts)

    # 6. Reminders 注入（注入到最后一条 UserMessage，而非 system prompt）
    #    由 inject_reminders() 在消息列表层面处理，不影响 system prompt 字符串
    return final_prompt
```

### Reminders 注入机制

Reminders 不追加到 system prompt 字符串，而是**注入到消息历史中的最后一条 UserMessage**：

```python
def inject_reminders(
    messages: list[Message],
    tools: list[Tool],
    options: QueryOptions,
) -> list[Message]:
    """
    在最后一条 UserMessage 末尾追加 reminders（工具使用规范、格式要求等）。
    这模拟了 Kode-Agent 中 'reminder' 注入最后一条用户消息的行为。
    """
    if not messages:
        return messages

    reminders = build_reminders(tools, options)
    if not reminders:
        return messages

    # 找到最后一条 UserMessage 并追加
    last_user_idx = next(
        (i for i in range(len(messages) - 1, -1, -1)
         if messages[i].role == "user"),
        None,
    )
    if last_user_idx is None:
        return messages

    messages = list(messages)
    messages[last_user_idx] = append_reminder_to_message(
        messages[last_user_idx], reminders
    )
    return messages
```

---

## Stop Hook 重入机制

当 LLM 返回**不含工具调用**的消息时，Agent 不一定直接终止——它会先执行 `run_stop_hooks()`，Stop Hook 可以强制 Agent 继续对话。

### 最大重入次数

```python
MAX_STOP_HOOK_ATTEMPTS = 5
```

### 完整流程

```python
async def _handle_no_tool_use(
    messages: list[Message],
    assistant_message: AssistantMessage,
    system_prompt: str,
    tools: list[Tool],
    session: SessionManager,
    options: QueryOptions,
    hook_state: HookState,
    stop_hook_attempts: int,
) -> AsyncGenerator[SessionEvent, None]:
    """处理 LLM 返回无 tool_use 的情况"""

    # 保存 AssistantMessage 到日志
    session.save_message(assistant_message)

    # 执行 Stop Hooks
    hook_result = await run_stop_hooks(assistant_message, messages, hook_state)

    if hook_result.action == "continue":
        # 正常终止
        yield SessionEvent(type=DONE)
        return

    # Hook 返回 block → 需要重入
    if stop_hook_attempts >= MAX_STOP_HOOK_ATTEMPTS:
        # 超过最大重入次数，强制终止（防止无限循环）
        yield SessionEvent(type=DONE)
        return

    # 将 Hook 追加的 prompt 片段注入 hook_state，下一轮循环使用
    if hook_result.additional_system_prompt:
        hook_state.additional_system_prompts.append(
            hook_result.additional_system_prompt
        )

    # 构建重入的消息（将 assistant_message 加入历史）
    new_messages = [*messages, assistant_message]

    # 添加 Hook 要求的继续消息（若有）
    if hook_result.modified_data:
        continuation_msg = UserMessage(content=hook_result.modified_data)
        new_messages.append(continuation_msg)
        session.save_message(continuation_msg)

    # 递归重入，stop_hook_attempts + 1
    async for event in query_core(
        messages=new_messages,
        system_prompt=system_prompt,
        tools=tools,
        session=session,
        options=options,
        hook_state=hook_state,
        stop_hook_attempts=stop_hook_attempts + 1,
    ):
        yield event
```

### 重入场景示例

```
第 1 轮：LLM 返回最终答案（无 tool_use）
  → run_stop_hooks() → action="block"（Hook 认为答案不完整）
  → stop_hook_attempts=1，重入 query_core

第 2 轮：LLM 补充内容（无 tool_use）
  → run_stop_hooks() → action="continue"
  → 正常终止，yield DONE
```

---

## `check_permissions_and_call_tool` 完整管线

这是单个工具调用的完整处理管线，包含从输入预处理到结果格式化的所有步骤。

对应 Kode-Agent `src/app/query.ts: checkPermissionsAndCallTool()`（L979-1248）。

### 管线流程图

```
ToolUseBlock (来自 LLM)
        │
        ▼
[1] 查找工具定义
  find_tool(tool_use.name, tools)
  ✗ → ToolResult(error="Unknown tool: {name}")
        │
        ▼
[2] Pre-hook 检查
  run_pre_tool_use_hooks(tool_name, tool_input)
  action="block" → ToolResult(error="Blocked by hook")
  action="modify" → 更新 tool_input
        │
        ▼
[3] Input 预处理
  raw_input = tool_use.tool_input (dict)
        │
        ▼
[4] Schema 验证（Pydantic）
  InputModel = tool.input_schema()
  InputModel.model_validate(raw_input)
  ValidationError → ToolResult(error=str(e))
        │
        ▼
[5] 额外验证（工具自定义）
  tool.validate_input(parsed_input)
  ✗ → ToolResult(error=validation.message)
        │
        ▼
[6] 权限检查
  permission_engine.has_permissions(tool_name, tool_input, ctx)
  ├─ ALLOWED    → 继续 ↓
  ├─ NEEDS_PROMPT → yield PERMISSION_REQUEST → 等待用户 → 继续/拒绝
  └─ DENIED     → ToolResult(error="Permission denied")
        │
        ▼
[7] tool.call() 执行
  context = ToolUseContext(abort_event=..., ...)
  async for output in tool.call(parsed_input, context):
      if output.type == "progress":
          yield SessionEvent(TOOL_PROGRESS, output)
      elif output.type == "result":
          final_result = output
        │
        ▼
[8] Post-hook 处理
  run_post_tool_use_hooks(tool_name, tool_input, final_result)
  action="modify" → 更新 final_result
        │
        ▼
[9] 格式化 tool_result
  ToolResult(
      tool_use_id=tool_use.id,
      content=tool.render_result_for_assistant(final_result),
      is_error=final_result.is_error,
  )
```

### Python 实现

```python
async def check_permissions_and_call_tool(
    tool_use: ToolUseBlock,
    tools: list[Tool],
    session: SessionManager,
    options: QueryOptions,
    abort_event: asyncio.Event,
) -> AsyncGenerator[SessionEvent, None]:

    # [1] 查找工具
    tool = find_tool(tool_use.name, tools)
    if not tool:
        yield SessionEvent(
            type=TOOL_RESULT,
            data=ToolResult(
                tool_use_id=tool_use.id,
                content=f"Unknown tool: {tool_use.name}",
                is_error=True,
            ),
        )
        return

    # [2] Pre-hook
    pre_hook_result = await run_pre_tool_use_hooks(
        tool_use.name, tool_use.input, session.hook_state
    )
    if pre_hook_result.action == "block":
        yield SessionEvent(
            type=TOOL_RESULT,
            data=ToolResult(
                tool_use_id=tool_use.id,
                content=f"Tool call blocked: {pre_hook_result.modified_data}",
                is_error=True,
            ),
        )
        return
    tool_input = pre_hook_result.modified_data or tool_use.input

    # [3+4] Pydantic 验证
    InputModel = tool.input_schema()
    try:
        parsed_input = InputModel.model_validate(tool_input)
    except ValidationError as e:
        yield SessionEvent(
            type=TOOL_RESULT,
            data=ToolResult(tool_use_id=tool_use.id, content=str(e), is_error=True),
        )
        return

    # [5] 额外验证
    validation = await tool.validate_input(parsed_input)
    if not validation.is_valid:
        yield SessionEvent(
            type=TOOL_RESULT,
            data=ToolResult(
                tool_use_id=tool_use.id, content=validation.error, is_error=True
            ),
        )
        return

    # [6] 权限检查
    perm_result = await session.permission_engine.has_permissions(
        tool.name, tool_input, session.permission_context
    )

    if perm_result == PermissionResult.NEEDS_PROMPT:
        yield SessionEvent(
            type=PERMISSION_REQUEST,
            data=PermissionRequestData(
                tool_name=tool.name,
                tool_input=tool_input,
                risk_level=tool.risk_level,
            ),
        )
        decision = await session.wait_for_permission_decision()
        if decision == PermissionDecision.DENY:
            yield SessionEvent(
                type=TOOL_RESULT,
                data=ToolResult(
                    tool_use_id=tool_use.id,
                    content="Permission denied by user",
                    is_error=True,
                ),
            )
            return

    elif perm_result == PermissionResult.DENIED:
        yield SessionEvent(
            type=TOOL_RESULT,
            data=ToolResult(
                tool_use_id=tool_use.id,
                content="Permission denied",
                is_error=True,
            ),
        )
        return

    # [7] 执行工具
    context = ToolUseContext(
        message_id=session.current_message_id,
        tool_use_id=tool_use.id,
        abort_event=abort_event,
        safe_mode=options.safe_mode,
        options=ToolOptions.from_query_options(options),
    )

    final_result: ToolOutput | None = None
    async for output in tool.call(parsed_input, context):
        if output.type == "progress":
            yield SessionEvent(type=TOOL_PROGRESS, data=output)
        elif output.type == "result":
            final_result = output

    if final_result is None:
        final_result = ToolOutput(type="result", data=None)

    # [8] Post-hook
    post_hook_result = await run_post_tool_use_hooks(
        tool.name, tool_input, final_result, session.hook_state
    )
    if post_hook_result.action == "modify":
        final_result = post_hook_result.modified_data

    # [9] 格式化并 yield 结果
    yield SessionEvent(
        type=TOOL_RESULT,
        data=ToolResult(
            tool_use_id=tool_use.id,
            content=tool.render_result_for_assistant(final_result),
            is_error=getattr(final_result, "is_error", False),
        ),
    )
```

---

## 与其他模块的关系映射

本文档描述的所有组件均属于 **Application 层**（`pode_agent/app/`），以下是详细的模块映射：

> 📖 **SubAgent 系统详解**：[subagent-system.md](./subagent-system.md) — TaskTool 完整设计、Agent 配置加载、上下文隔离（ForkContext）、前台/后台执行、工具权限隔离、Transcript 存储。SubAgent 复用本文档描述的 `query()` / `query_core()` 递归主循环，通过独立的子 SessionManager 实例实现上下文隔离。

| 本文档的组件 | Python 模块 | 文件路径 |
|------------|------------|---------|
| `query()` 外层入口 | `app.query` | `pode_agent/app/query.py` |
| `query_core()` 递归主循环 | `app.query` | `pode_agent/app/query.py` |
| `ToolUseQueue` 并发调度器 | `app.query` | `pode_agent/app/query.py` |
| `check_permissions_and_call_tool()` | `app.query` | `pode_agent/app/query.py` |
| `_handle_no_tool_use()` + Stop Hook 逻辑 | `app.query` | `pode_agent/app/query.py` |
| `SessionManager` 会话状态 | `app.session` | `pode_agent/app/session.py` |
| `build_system_prompt()` | `services.system` | `pode_agent/services/system/system_prompt.py` |
| `inject_reminders()` | `services.system` | `pode_agent/services/system/reminders.py` |
| `auto_compact_if_needed()` | `app.compact` | `pode_agent/app/compact.py` |
| `run_user_prompt_submit_hooks()` | `services.hooks` | `pode_agent/services/hooks/runner.py` |
| `run_pre_tool_use_hooks()` | `services.hooks` | `pode_agent/services/hooks/runner.py` |
| `run_post_tool_use_hooks()` | `services.hooks` | `pode_agent/services/hooks/runner.py` |
| `run_stop_hooks()` | `services.hooks` | `pode_agent/services/hooks/runner.py` |
| `PermissionEngine` | `core.permissions` | `pode_agent/core/permissions/engine.py` |
| `process_mentions()` | `services.context` | `pode_agent/services/context/mentions.py` |

### 调用关系图

```
entrypoints/cli.py
       │
       ▼
app/session.py (SessionManager.process_input)
       │
       ▼
app/query.py (query)
       │
       ▼
app/query.py (query_core)  ←──────────────────┐
       │                                        │
       ├─► services/system/system_prompt.py     │
       │                                        │
       ├─► services/ai/factory.py (query_llm)  │
       │                                        │
       ├─► app/compact.py (auto_compact)        │
       │                                        │
       ├─► services/hooks/runner.py (hooks)     │
       │                                        │
       └─► app/query.py (ToolUseQueue)          │
                  │                             │
                  └─► check_permissions_and_call_tool
                              │                 │
                              ├─► core/permissions
                              │                 │
                              ├─► tools/*/      │
                              │                 │
                              └─────── 递归 ────┘
```

### 与现有文档的边界

| 文档 | 内容边界 |
|------|---------|
| **本文档（agent-loop.md）** | Agentic Loop 引擎的运行时行为、详细伪代码、并发/Hook/压缩机制 |
| **modules.md** | 模块接口定义（函数签名、属性列表）—— 不含实现细节 |
| **data-flows.md** | 端到端时序图、用户视角的数据流 —— 核心循环细节引用本文档 |
| **api-specs.md** | 模块间 API 契约（类型签名）—— `process_input` 流程引用本文档 |
| **architecture.md** | 层次架构、依赖方向 —— Application 层细节引用本文档 |

---

## 实现阶段划分

各阶段与 Agentic Loop 组件的对应关系（详见 [`phases.md`](./phases.md)）：

| 组件 | 实现阶段 | 说明 |
|------|---------|------|
| `query()` / `query_core()` 基础骨架 | **Phase 2** | 无 Hook、无 Auto-compact 的最小可用版本 |
| `ToolUseQueue`（串行版） | **Phase 2** | 先串行执行，验证基本流程 |
| `check_permissions_and_call_tool()` | **Phase 2** | 含权限检查，不含 Hook |
| `ToolUseQueue`（并发版） | **Phase 3** | 添加 `is_concurrency_safe` 并发执行 |
| Hook 系统（4 个注入点） | **Phase 5** | 随插件系统一起实现 |
| Auto-compact | **Phase 6** | 长对话优化，后期实现 |
| Stop Hook 重入 | **Phase 5** | 依赖 Hook 系统 |
| System Prompt 动态组装（完整版） | **Phase 3** | Plan Mode、Reminders 等 |
