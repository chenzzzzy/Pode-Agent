# Pode-Agent 用户体验改进清单

> 记录需要修复的 UX 问题，按优先级排序。

---

## P0 — 启动体验

### UX-01: REPL 启动无反馈，用户不知道发生了什么

**现象**：运行 `pode`（无参数）后，终端只显示一行 INFO 日志就卡住：
```
INFO     UI bridge started, waiting for JSON-RPC
```
用户完全不知道系统在做什么——是在等待 Bun 启动？在安装依赖？还是已经崩溃？

**根本原因**：
1. `_launch_repl()` 在 `cli.py:171` spawn Bun 子进程后，没有任何进度输出
2. `UIBridge.run()` 只打印了一条 INFO 级别日志就开始阻塞等待 readline()
3. Bun 进程的 stdout/stderr 没有被转发到终端（用户看不到 Bun 的编译/启动日志）
4. 如果 Bun 未安装或 UI 构建失败，用户只看到卡死，没有任何错误提示

**修复方案**：

#### 方案 A：启动进度条（推荐）

在 `_launch_repl()` 中增加启动阶段的用户反馈：

```
$ pode
⠋ Starting Pode-Agent...
  ✓ Checking Bun installation
  ✓ Loading UI dependencies
  ✓ Building UI (2.3s)
  ✓ Starting backend
  ● Connected — welcome!
```

具体改动：
1. `cli.py` — `_launch_repl()` 增加 Rich spinner/status 输出：
   - "Checking Bun installation..." → 检查 `shutil.which("bun")`
   - "Installing UI dependencies..." → `bun install`（如果需要）
   - "Building UI..." → `bun run build`（如果需要）
   - "Starting Pode-Agent..." → spawn Bun + 启动 UIBridge
2. `ui_bridge.py` — 将 Bun 子进程的 stderr 输出实时转发到终端（至少在 debug 模式下）
3. 添加超时检测：如果 30 秒内没有收到 UI 的第一个 JSON-RPC 消息，显示错误提示

#### 方案 B：降级模式

当 Bun 不可用时，自动降级到纯终端 REPL（类似 Python REPL），用 Rich 渲染输出，不依赖 Ink UI：

```
$ pode
⚠ Bun not found. Falling back to terminal mode.
Pode-Agent v0.1.0 (terminal mode)
Type your message and press Enter. Type /help for commands.
> _
```

#### 方案 C：启动画面 + 错误诊断

至少显示一个启动画面，让用户知道程序已经启动：

```
$ pode
╭──────────────────────────────────╮
│  Pode-Agent v0.1.0              │
│  Starting UI...                  │
╰──────────────────────────────────╯
```

并在检测到问题时给出明确指引：
```
✗ Bun not found. Install it: https://bun.sh
  Or use print mode: pode "your question"
```

**涉及文件**：
- `pode_agent/entrypoints/cli.py` — `_launch_repl()` 函数
- `pode_agent/entrypoints/ui_bridge.py` — `UIBridge.run()` 启动阶段
- 可能新增 `pode_agent/entrypoints/repl_fallback.py`（方案 B）

**关联**：
- docs/phases.md — Task 4.1 (UI Bridge)
- Kode-Agent 对应行为：启动时显示 loading spinner + 版本信息

---

## P1 — 可用性

### UX-02: 无 Bun 时缺少降级方案

**现象**：如果系统没有 Bun，`pode` 直接报错退出，不给任何替代方案。

**修复**：检测到 Bun 缺失时，自动降级到 print mode 或显示交互提示：
```
✗ Bun not found. Options:
  1. Install Bun: https://bun.sh (recommended)
  2. Use print mode: pode "your question"
```

**涉及文件**：`pode_agent/entrypoints/cli.py` — `_launch_repl()`

---

## P2 — 锦上添花

### UX-03: Print mode 缺少工具执行进度反馈

**现象**：`pode "写一个排序"` 执行时，如果工具调用耗时较长（如 BashTool），用户只看到空白等待。

**修复**：在 print mode 中实时输出工具调用进度（类似 Claude Code 的 spinner）。

**涉及文件**：`pode_agent/app/print_mode.py`
