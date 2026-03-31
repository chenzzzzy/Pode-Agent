# Pode-Agent 关键数据流

> 版本：1.0.0 | 状态：草稿 | 更新：2026-03-31  
> 本文档描述系统中最关键的数据流转路径，使用时序图和伪代码说明。

---

## 目录

1. [主对话流程（用户输入 → LLM → 工具 → 响应）](#主对话流程)
2. [工具调用流程（BashTool 示例）](#工具调用流程)
3. [权限申请与用户确认流程](#权限申请与用户确认流程)
4. [LLM 流式响应处理](#llm-流式响应处理)
5. [会话日志读写流程](#会话日志读写流程)
6. [MCP 工具调用流程](#mcp-工具调用流程)
7. [上下文构建流程](#上下文构建流程)
8. [多工具并发执行](#多工具并发执行)

---

## 主对话流程

**场景**：用户在 REPL 中输入 "帮我运行测试"，AI 调用 BashTool 执行 `npm test`。

### 时序图

```
User         UI (Textual)     SessionManager   AIProvider     BashTool    FileSystem
 │                │                 │               │             │            │
 │──(input)──────▶│                 │               │             │            │
 │                │──process_input─▶│               │             │            │
 │                │                 │──mentions()   │             │            │
 │                │                 │──build_sys_prompt()         │            │
 │                │                 │──query_llm()─▶│             │            │
 │                │◀──(stream delta)─────────────────│             │            │
 │                │                 │◀──(tool_use)──│             │            │
 │                │                 │               │             │            │
 │                │◀──(permission_request)          │             │            │
 │──(approve)────▶│                 │               │             │            │
 │                │──(approved)────▶│               │             │            │
 │                │                 │──call()───────────────────▶│            │
 │                │◀──(progress)────────────────────────────────  │            │
 │                │◀──(result)──────────────────────────────────  │            │
 │                │                 │──query_llm(tool_result)──▶│             │
 │                │◀──(stream delta)──────────────────│           │            │
 │                │◀──(done)─────────────────────────│            │            │
 │                │                 │──save_log()               │            │
 │◀──(display)────│                 │               │             │            │
```

### 伪代码（SessionManager.process_input）

```python
async def process_input(self, prompt: str) -> AsyncGenerator[SessionEvent, None]:
    # Step 1: 处理 @mention
    processed_prompt, file_contents = await process_mentions(prompt, cwd)
    
    # Step 2: 添加 UserMessage 到历史
    user_msg = UserMessage(message=format_user_message(processed_prompt, file_contents))
    self.messages.append(user_msg)
    self.save_message(user_msg)
    yield SessionEvent(type="user_message", data=user_msg)
    
    # Step 3: 主循环（LLM → 工具 → LLM → ...）
    while True:
        # 构建系统提示
        system_prompt = await build_system_prompt(
            context=await get_project_context(cwd),
            tools=self.tools,
        )
        
        # LLM 查询
        assistant_content = []
        tool_uses = []
        cost_usd = 0.0
        
        params = UnifiedRequestParams(
            messages=normalize_messages(self.messages),
            system_prompt=system_prompt,
            model=get_current_model(),
            max_tokens=get_max_tokens(),
            tools=[t.get_json_schema() for t in self.tools],
        )
        
        async for ai_response in query_llm(params):
            if ai_response.type == "text_delta":
                yield SessionEvent(type="assistant_delta", data=ai_response.text)
                assistant_content.append({"type": "text", "text": ai_response.text})
            
            elif ai_response.type == "tool_use_end":
                tool_uses.append(ai_response)
            
            elif ai_response.type == "message_done":
                cost_usd = ai_response.cost_usd or 0.0
                add_to_total_cost(cost_usd)
        
        # 保存 AssistantMessage
        assistant_msg = AssistantMessage(
            message={"role": "assistant", "content": assistant_content},
            cost_usd=cost_usd,
        )
        self.messages.append(assistant_msg)
        self.save_message(assistant_msg)
        
        # 如果没有工具调用，结束循环
        if not tool_uses:
            yield SessionEvent(type="done")
            break
        
        # Step 4: 执行所有工具（可并发）
        tool_results = []
        for tool_use in tool_uses:
            result = await self._execute_tool_use(tool_use)
            tool_results.append(result)
        
        # Step 5: 将工具结果添加到消息历史
        tool_result_msg = UserMessage(
            message=format_tool_results_message(tool_uses, tool_results)
        )
        self.messages.append(tool_result_msg)
        self.save_message(tool_result_msg)
        
        yield SessionEvent(type="cost_update", data=get_total_cost())
```

---

## 工具调用流程

**场景**：AI 调用 BashTool 执行 `npm test`。

### 时序图

```
SessionManager       PermissionEngine     UI (Textual)      BashTool        Shell
      │                    │                  │                  │              │
      │──has_permissions()─▶│                  │                  │              │
      │◀──NEEDS_PROMPT──────│                  │                  │              │
      │──permission_request─▶─────────────────▶│                  │              │
      │                    │                  │                  │              │
      │◀──────────────────────────(approved)──│                  │              │
      │──persist_permission()──▶              │                  │              │
      │                    │                  │                  │              │
      │──call(input, ctx)───────────────────────────────────────▶│              │
      │◀──progress: "Running npm test"─────────────────────────  │              │
      │──update_ui()──────────────────────────▶│                 │              │
      │                    │                  │                  │──subprocess─▶│
      │                    │                  │                  │◀──stdout──── │
      │◀──result: {stdout, exit_code}─────────────────────────── │              │
      │──format_for_llm()  │                  │                  │              │
```

### 伪代码（_execute_tool_use）

```python
async def _execute_tool_use(
    self,
    tool_use: ToolUseBlock,
) -> ToolResult:
    # Step 1: 查找工具
    tool = find_tool_by_name(self.tools, tool_use.tool_name)
    if not tool:
        return ToolResult(error=f"Unknown tool: {tool_use.tool_name}")
    
    # Step 2: 验证输入
    input_model = tool.input_schema()
    try:
        parsed_input = input_model.model_validate(tool_use.tool_input)
    except ValidationError as e:
        return ToolResult(error=str(e))
    
    # Step 3: 额外验证
    validation = await tool.validate_input(parsed_input)
    if not validation.result:
        return ToolResult(error=validation.message)
    
    # Step 4: 权限检查
    if tool.needs_permissions(parsed_input):
        perm_result = await self.permission_engine.has_permissions(
            tool.name, tool_use.tool_input, self.permission_context
        )
        
        if perm_result == PermissionResult.NEEDS_PROMPT:
            # 向 UI 发送权限请求
            self._pending_permission = asyncio.Event()
            yield SessionEvent(
                type="permission_request",
                data=PermissionRequest(tool_name=tool.name, input=tool_use.tool_input)
            )
            # 等待用户决定
            await self._pending_permission.wait()
            
            if self._user_rejected:
                return ToolResult(error="Permission denied by user")
        
        elif perm_result == PermissionResult.DENIED:
            return ToolResult(error="Permission denied")
    
    # Step 5: 执行工具
    context = ToolUseContext(
        message_id=self.current_message_id,
        tool_use_id=tool_use.id,
        abort_event=self._abort_event,
        options=self._build_tool_options(),
    )
    
    async def on_progress(output: ToolOutput):
        yield SessionEvent(type="tool_progress", data=output)
    
    result = await collect_tool_result(tool, parsed_input, context, on_progress)
    
    yield SessionEvent(type="tool_result", data=result)
    return result
```

---

## 权限申请与用户确认流程

### 状态机

```
Tool.needs_permissions() == True
          │
          ▼
    PermissionEngine.has_permissions()
          │
    ┌─────┴──────────────────┐
    ▼                        ▼
ALLOWED                NEEDS_PROMPT
(直接执行)               │
                        ▼
                  yield permission_request 事件
                        │
                  UI 显示权限对话框
                        │
               ┌────────┴────────┐
               ▼                 ▼
          User APPROVE      User REJECT
               │                 │
    ┌──────────┼─────────┐       ▼
    ▼          ▼         ▼   ToolResult(error)
ONCE       SESSION    ALWAYS
 │           │          │
 │           │          ├─ persist to ProjectConfig
 │           │          └─ add to approved_tools set
 ▼           ▼          ▼
       继续执行工具
```

### UI 权限对话框的信息

对于不同工具，需要显示不同的权限信息：

| 工具 | 显示信息 |
|------|---------|
| BashTool | 命令文本、预估影响（只读/写入） |
| FileEditTool | 文件路径、diff 预览 |
| FileWriteTool | 文件路径、内容预览 |
| WebFetchTool | URL、请求方法 |
| MCPTool | 服务器名、工具名、参数 |

---

## LLM 流式响应处理

### Anthropic SSE 流到 AIResponse 的映射

```
Anthropic SSE Event → AIResponse mapping:

content_block_start (type=text)      → (buffering)
content_block_delta (text_delta)     → AIResponse(type="text_delta", text=delta)
content_block_stop                   → (flush)

content_block_start (type=tool_use)  → AIResponse(type="tool_use_start", tool_name=..., tool_use_id=...)
content_block_delta (input_json)     → (buffering JSON)
content_block_stop                   → AIResponse(type="tool_use_end", tool_input=parsed_json)

message_delta (usage)                → AIResponse(type="message_done", usage=..., cost_usd=...)
```

### 流处理伪代码

```python
async def query_anthropic(
    self,
    params: UnifiedRequestParams,
) -> AsyncGenerator[AIResponse, None]:
    
    tool_input_buffers: dict[str, str] = {}  # tool_use_id -> JSON string
    
    async with self.client.messages.stream(
        model=params.model,
        messages=to_anthropic_messages(params.messages),
        system=params.system_prompt,
        max_tokens=params.max_tokens,
        tools=to_anthropic_tools(params.tools or []),
    ) as stream:
        async for event in stream:
            if event.type == "content_block_start":
                if event.content_block.type == "tool_use":
                    yield AIResponse(
                        type="tool_use_start",
                        tool_use_id=event.content_block.id,
                        tool_name=event.content_block.name,
                    )
                    tool_input_buffers[event.content_block.id] = ""
            
            elif event.type == "content_block_delta":
                if event.delta.type == "text_delta":
                    yield AIResponse(type="text_delta", text=event.delta.text)
                elif event.delta.type == "input_json_delta":
                    tool_use_id = event.index  # 简化
                    tool_input_buffers[tool_use_id] = (
                        tool_input_buffers.get(tool_use_id, "") + event.delta.partial_json
                    )
            
            elif event.type == "content_block_stop":
                # 检查是否是工具调用结束
                for tool_use_id, json_str in list(tool_input_buffers.items()):
                    if json_str:  # 有内容表示刚完成
                        yield AIResponse(
                            type="tool_use_end",
                            tool_use_id=tool_use_id,
                            tool_input=json.loads(json_str),
                        )
                        del tool_input_buffers[tool_use_id]
            
            elif event.type == "message_delta":
                if event.usage:
                    cost = calculate_cost(
                        model=params.model,
                        input_tokens=event.usage.input_tokens or 0,
                        output_tokens=event.usage.output_tokens or 0,
                    )
                    yield AIResponse(
                        type="message_done",
                        usage=TokenUsage(
                            input_tokens=event.usage.input_tokens,
                            output_tokens=event.usage.output_tokens,
                        ),
                        cost_usd=cost,
                        stop_reason=event.delta.stop_reason,
                    )
```

---

## 会话日志读写流程

### JSONL 格式（与 Kode-Agent 兼容）

每行一个 JSON 对象：

```jsonl
{"type":"user","uuid":"abc123","message":{"role":"user","content":"帮我运行测试"},"timestamp":"2026-03-31T10:00:00Z"}
{"type":"assistant","uuid":"def456","message":{"role":"assistant","content":[{"type":"text","text":"我来帮你运行测试..."}]},"cost_usd":0.002,"duration_ms":1200,"timestamp":"2026-03-31T10:00:01Z"}
{"type":"user","uuid":"ghi789","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"xyz","content":"Tests passed: 42"}]},"timestamp":"2026-03-31T10:00:03Z"}
{"type":"assistant","uuid":"jkl012","message":{"role":"assistant","content":[{"type":"text","text":"所有 42 个测试通过！"}]},"cost_usd":0.001,"duration_ms":800,"timestamp":"2026-03-31T10:00:04Z"}
```

### 写入流程

```python
def save_message(self, message: Message) -> None:
    """原子追加一行到 JSONL 日志"""
    log_entry = {
        "type": message.type,
        "uuid": message.uuid,
        "message": message.message,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
    
    if isinstance(message, AssistantMessage):
        log_entry["cost_usd"] = message.cost_usd
        log_entry["duration_ms"] = message.duration_ms
    
    line = json.dumps(log_entry, ensure_ascii=False) + "\n"
    
    with open(self.log_file, "a", encoding="utf-8") as f:
        f.write(line)
```

### 读取（恢复会话）

```python
def load_messages_from_log(log_path: Path) -> list[Message]:
    """从 JSONL 文件恢复会话历史"""
    messages = []
    
    with open(log_path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                msg_type = entry.get("type")
                
                if msg_type == "user":
                    messages.append(UserMessage(**entry))
                elif msg_type == "assistant":
                    messages.append(AssistantMessage(**entry))
                # 跳过 progress 类型（临时状态，不需要恢复）
                
            except (json.JSONDecodeError, ValidationError) as e:
                logger.warning(f"Skipping invalid log entry at line {line_no}: {e}")
    
    return messages
```

### 日志文件命名规则

```python
def generate_log_name() -> str:
    """生成唯一的日志文件名"""
    date_str = datetime.now().strftime("%Y-%m-%d")
    fork_number = get_next_fork_number(date_str)
    return f"{date_str}_session_fork_{fork_number}"

# 存储路径
LOG_DIR = Path.home() / ".pode" / "logs"
# 示例：~/.pode/logs/2026-03-31_session_fork_0.jsonl
```

---

## MCP 工具调用流程

**场景**：AI 调用一个外部 MCP 服务器的工具。

### 时序图

```
SessionManager    MCPTool    WrappedMcpClient    External MCP Server
      │             │               │                     │
      │──call()────▶│               │                     │
      │             │──call_tool()─▶│                     │
      │             │               │──MCP Request (JSON-RPC)──▶│
      │             │               │                     │──process──│
      │             │               │◀──MCP Response──────────────────│
      │             │◀──result──────│                     │
      │◀──ToolOutput│               │                     │
```

### MCPTool 实现要点

```python
class MCPTool(Tool):
    name = "mcp__tool_name"  # 动态生成：mcp__{server}__{tool}
    
    async def call(self, input: BaseModel, context: ToolUseContext):
        mcp_client = self._get_mcp_client(context)
        
        yield ToolOutput(type="progress", content=f"Calling MCP tool {self.mcp_tool_name}...")
        
        result = await mcp_client.call_tool(
            name=self.mcp_tool_name,
            arguments=input.model_dump(),
        )
        
        yield ToolOutput(
            type="result",
            data=result.content,
            result_for_assistant=format_mcp_result(result),
        )
```

---

## 上下文构建流程

### 上下文收集顺序

```python
async def get_project_context(cwd: str) -> dict[str, str]:
    """
    按优先级收集项目上下文。
    超过 PODE_PROJECT_DOC_MAX_BYTES（默认 32 KiB）时截断。
    """
    context = {}
    total_bytes = 0
    max_bytes = int(os.environ.get("PODE_PROJECT_DOC_MAX_BYTES", 32 * 1024))
    
    collectors = [
        ("git_status", collect_git_status),          # git status + log
        ("directory_tree", collect_directory_tree),   # ls -la recursive
        ("instruction_files", collect_instruction_files),  # AGENTS.md, CLAUDE.md
        ("readme", collect_readme),                   # README.md
        ("custom_context", collect_custom_context),   # ProjectConfig.context
    ]
    
    for key, collector in collectors:
        if total_bytes >= max_bytes:
            break
        try:
            content = await collector(cwd)
            if content:
                context[key] = content
                total_bytes += len(content.encode())
        except Exception as e:
            logger.debug(f"Context collector {key} failed: {e}")
    
    return context
```

### System Prompt 构建

```python
async def build_system_prompt(
    context: dict[str, str],
    tools: list[Tool],
    options: SystemPromptOptions,
) -> str:
    parts = []
    
    # 1. 基础角色描述
    parts.append(BASE_SYSTEM_PROMPT)
    
    # 2. 项目上下文
    for key, content in context.items():
        parts.append(f"\n<{key}>\n{content}\n</{key}>")
    
    # 3. 工具能力描述（Anthropic 的工具描述会自动注入，这里是补充）
    if options.include_tool_descriptions:
        tool_descriptions = []
        for tool in tools:
            desc = await tool.get_description()
            tool_descriptions.append(f"- {tool.name}: {desc}")
        parts.append("\n<available_tools>\n" + "\n".join(tool_descriptions) + "\n</available_tools>")
    
    # 4. 日期/时间
    parts.append(f"\nCurrent date/time: {datetime.utcnow().isoformat()}Z")
    
    return "\n".join(parts)
```

---

## 多工具并发执行

Kode-Agent 支持 AI 在一次响应中返回多个工具调用，并且部分工具可以并发执行。

### 并发策略

```python
async def execute_tool_uses(
    self,
    tool_uses: list[ToolUseBlock],
) -> list[ToolResult]:
    """
    并发执行多个工具调用。
    
    规则：
    1. 标记为 isConcurrencySafe=True 的工具可以并发
    2. 其余工具串行执行
    3. 权限检查不并发（避免重复询问）
    """
    results = []
    
    # 分组：并发安全 vs 串行
    concurrent_tools = [tu for tu in tool_uses 
                        if self._tool_is_concurrency_safe(tu)]
    serial_tools = [tu for tu in tool_uses 
                    if not self._tool_is_concurrency_safe(tu)]
    
    # 并发执行安全工具
    if concurrent_tools:
        concurrent_results = await asyncio.gather(
            *[self._execute_tool_use(tu) for tu in concurrent_tools],
            return_exceptions=True
        )
        results.extend(concurrent_results)
    
    # 串行执行其余工具
    for tu in serial_tools:
        result = await self._execute_tool_use(tu)
        results.append(result)
    
    # 按原始顺序返回
    return reorder_results(results, tool_uses)
```

### 工具并发安全性标记

| 工具 | `is_concurrency_safe` | 原因 |
|------|----------------------|------|
| FileReadTool | ✅ True | 只读，无副作用 |
| GrepTool | ✅ True | 只读，无副作用 |
| GlobTool | ✅ True | 只读，无副作用 |
| WebFetchTool | ✅ True | 无本地副作用 |
| BashTool | ❌ False | 有状态，可能竞争 |
| FileEditTool | ❌ False | 写操作，不可并发 |
| FileWriteTool | ❌ False | 写操作，不可并发 |
| AskUserQuestionTool | ❌ False | 交互，不可并发 |
