# Pode-Agent E2E 测试执行 Prompt

> 本文档供外部 Agent 使用，用于执行 Pode-Agent 的端到端自动化测试。
> 项目路径: `D:\duyan\ai_agent\Pode-Agent`
>
> 请站在使用者角度 端到端 测试当前的项目，如有必要按照你的需求修改测试脚本。
>
> 相关的 端到端测试 Prompt 文档：D:\duyan\ai_agent\Pode-Agent\docs\e2e-test-prompts.md
>
> 目标：顺利跑通所有测试 e2e-test-prompts.md 中所有的用例，如有各种异常在代码中修复它，直到他们不在出现。

## 1. 环境要求

| 项目 | 值 |
|------|-----|
| Python | 3.12+ |
| 包管理 | `uv` (已安装在 PATH) |
| Bun | 1.3.11 |
| LLM API | DashScope (qwen3.5-plus, OpenAI-compatible) |
| .env 配置 | 项目根目录 `.env` 已配置 `DASHSCOPE_API_KEY`, `DASHSCOPE_BASE_URL`, `DASHSCOPE_MODEL` |

## 2. 执行命令

```bash
cd D:\duyan\ai_agent\Pode-Agent
uv run python tests/e2e/e2e_runner.py
```

所有测试通过 `subprocess.run()` 执行 `uv run pode -p "prompt"` 命令。
每个测试会自动记录结果到 `tests/e2e/e2e_results.json`。

**预估运行时间**: 60-90 分钟（含 LLM API 调用延迟）。

## 3. 测试结构

测试文件: `tests/e2e/e2e_runner.py`

每个测试函数返回 `TestResult` 对象:
- `id`: 测试编号 (如 D1, F3)
- `name`: 测试描述
- `status`: PASS / FAIL / TIMEOUT / ERROR / SKIP
- `output`: stdout + stderr 输出
- `duration`: 耗时(秒)
- `error`: 错误信息

## 4. 测试组概览

| 组 | 名称 | 测试数 | 可执行 | SKIP | 类型 |
|----|------|--------|--------|------|------|
| A | CLI 基础能力 | 8 | 8 | 0 | CLI subprocess |
| B | 配置与模型路由 | 8 | 8 | 0 | CLI subprocess |
| C | REPL 终端交互 | 3 | 2 | 0 | async subprocess |
| D | 项目感知 | 8 | 8 | 0 | LLM print mode |
| E | 文件搜索 | 8 | 8 | 0 | LLM print mode |
| F | Bash/编辑/写入 | 10 | 10 | 0 | LLM print mode + 文件操作 |
| G | 代码修改 | 8 | 8 | 0 | LLM print mode + 文件操作 |
| H | Web/Notebook | 6 | 3 | 3 | LLM print mode |
| I | AskUser/TodoWrite | 6 | 4 | 2 | LLM print mode |
| J | Plan Mode | 8 | 4 | 4 | LLM print mode |
| K | Skill/Slash | 10 | 3 | 7 | LLM print mode |
| L | Plugin/Marketplace | 12 | 3 | 9 | CLI subprocess |
| M | Hook 系统 | 8 | 0 | 8 | 无 fixture |
| N | MCP 客户端 | 8 | 0 | 8 | 无 MCP server |
| O | SubAgent | 8 | 4 | 4 | LLM print mode |
| P | 会话持久化 | 6 | 3 | 3 | LLM print mode |
| Q | Print Mode | 5 | 5 | 0 | LLM print mode |
| R | 错误处理 | 12 | 12 | 0 | CLI + LLM print mode |
| S | 综合链路 | 5 | 5 | 0 | LLM print mode |
| T | 自动化断言 | 10 | 10 | 0 | CLI + LLM print mode |
| **总计** | | **141** | **104** | **37** | |

## 5. 判定标准

### PASS 条件
- CLI 测试: `exit_code == 0` 且输出包含预期关键词
- LLM print mode 测试: `exit_code == 0`（LLM 成功响应即可，不检查内容准确性）
- SKIP: 无需 fixture 或多轮会话上下文的测试

### FAIL 条件
- `exit_code != 0`（LLM API 错误或工具执行失败）
- 输出明显异常（空输出、只有错误信息等）

### TIMEOUT 条件
- 超过设定的 timeout 时间（默认 300s for LLM 测试, 10-60s for CLI 测试）

### 预期的已知行为
- **C3 (REPL I/O)**: 在无 PTY 环境下必定 TIMEOUT，这是预期行为
- **I1 (ask_user in print mode)**: ask_user 工具在非交互模式下返回错误，LLM 通常会适配并完成任务
- **F10 (safe mode write)**: 使用 `--safe` 标志，写操作被阻止，exit_code 可能是 0 或 1，两种都可接受

## 6. 测试后清理

测试完成后会自动清理以下临时文件:
- `E2E_WRITE_TEST.txt`, `E2E_MULTI_EDIT.txt`
- `E2E_TEMP_G1.py` ~ `E2E_TEMP_G7.md`
- `E2E_PLAN_TEST.txt`, `E2E_DRAFT.md`
- `tmp-e2e-output/` 目录

如果测试中断，请手动删除这些文件。

## 7. 结果文件

| 文件 | 路径 |
|------|------|
| 测试脚本 | `tests/e2e/e2e_runner.py` |
| JSON 结果 | `tests/e2e/e2e_results.json` |
| 结果文档 | `docs/e2e-test-result.md` |

## 8. 执行后操作

1. 读取 `tests/e2e/e2e_results.json` 获取详细结果
2. 统计各组的 PASS/FAIL/TIMEOUT/SKIP 数量
3. 更新 `docs/e2e-test-result.md` 包含完整结果表
4. 如有 FAIL 项，检查 error 字段定位原因
5. 清理任何残留临时文件

## 9. 如果测试失败

**请定位代码中的错误并修复直到所有测试用例正常通过**

当测试进程卡死时，需要kill掉进程，并定位原因修复。

常见失败原因及处理:

| 症状 | 原因 | 处理 |
|------|------|------|
| LLM 测试全部 TIMEOUT | API Key 过期或网络问题 | 检查 `.env` 中的 `DASHSCOPE_API_KEY` |
| 工具调用测试 FAIL | 工具参数验证 bug | 查看错误输出中的 traceback |
| 文件操作测试 FAIL | 权限问题或文件已存在 | 先清理临时文件再重试 |
| 单元测试失败 | 代码改动引入回归 | 运行 `uv run pytest tests/ -q` 定位 |

## 10. 快速验证命令

```bash
# 验证环境
uv run pode --version          # 应输出 pode-agent 0.1.0
uv run pode config list        # 应正常输出配置

# 快速冒烟测试（不消耗 LLM API）
uv run pode --version
uv run pode --help
uv run pode config list
uv run pode config get theme
uv run pode plugin list
uv run pode plugin marketplace list
uv run pode plugin marketplace add file:./nonexistent.json  # 应失败 exit 1

# 单个 LLM 测试验证
uv run pode -p "只回复：ok"     # 应输出 ok, exit 0
```
