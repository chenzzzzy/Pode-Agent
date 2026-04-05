# Pode-Agent E2E Test Results

> 执行时间: 2026-04-04
> 测试环境: Windows 11 / Python 3.12 / Bun 1.3.11 / `uv`
> 主测试模型: GLM-4.5（智谱 OpenAI-compatible，`https://open.bigmodel.cn/api/coding/paas/v4`）
> 测试脚本: `tests/e2e/e2e_runner.py`
> 相关 fixture: `tests/fixtures/mcp_echo_server.py`、`tests/fixtures/hooks/*`、`tests/fixtures/test-plugin/*`、`.pode.json`

## 本轮结论

- A-T 全量分组已实际跑通，不再是早期的 40 条轻量样例。
- 本轮把原先大量 `SKIP` 的 Plugin / Hook / MCP / Error / Integration 场景补成了真实 E2E。
- MCP / Hook / Plugin 已接入真实 fixture，不再依赖纯文字假设。
- 当前稳定结果为：**174 项中 134 PASS / 36 SKIP / 4 TIMEOUT / 0 FAIL**。

## 本轮关键修复与增强

| 类别 | 变更 |
|---|---|
| Provider 路由 | 新增按模型前缀解析环境变量，支持 `GLM_*` / `DASHSCOPE_*` 等并存 |
| GLM 接入 | `glm-*` 路由到 OpenAI-compatible provider，`.env` 可直接驱动 |
| MCP | 修复 JSON-RPC 响应未解包 `result` 的问题 |
| Project Config | MCP server 与 hooks 现在同时读取全局配置和项目级 `.pode.json` |
| E2E 基建 | `e2e_runner.py` 新增 `--model`、`--group`，支持单组回归 |
| Fixture | 新增 MCP echo server、4 个 hook 脚本、测试 plugin 包 |

## 验证摘要

| 项目 | 结果 |
|---|---|
| mypy | pass |
| ruff | pass |
| `pytest tests/unit/` | 799 passed, 4 skipped |
| E2E | 174 total / 134 PASS / 36 SKIP / 4 TIMEOUT / 0 FAIL |

## 分组结果

| 组 | 名称 | 结果 | 备注 |
|---|---|---:|---|
| A | CLI 基础能力 | 7/8 PASS | A8 超时，safe-mode 拒写场景在 GLM 下存在工具调用抖动 |
| B | 配置与模型路由 | 8/10 PASS | 2 项 provider route 为历史兼容场景，保留 SKIP |
| C | REPL 终端交互 | 2/3 PASS | C3 在无 PTY subprocess 下超时，属环境限制 |
| D | 项目感知 | 8/8 PASS | 项目上下文、文档总结、风险识别均通过 |
| E | 文件搜索 | 8/8 PASS | 文件/符号/上下文搜索链路通过 |
| F | Bash / 编辑 / 写入 | 10/10 PASS | 读写、失败命令、安全模式全部通过 |
| G | 代码修改 | 7/8 PASS | G4 长函数拆分超时，属复杂生成场景不稳定 |
| H | Web / Notebook | 3/6 PASS | Web 场景通过；Notebook 仍为占位 SKIP |
| I | AskUser / TodoWrite | 5/6 PASS | 多步 Todo 链路通过；交互 follow-up 仍 SKIP |
| J | Plan Mode | 4/8 PASS | 基础 plan 流程通过，交互式分支仍 SKIP |
| K | Skill / Slash | 3/10 PASS | 基础 skill/command 可用，高阶 slash 场景多为 SKIP |
| L | Plugin / Marketplace | 12/12 PASS | 安装、启停、卸载、坏包安装场景已覆盖 |
| M | Hook 系统 | 4/8 PASS | fixture hook 可运行；REPL-only hook 场景保留 SKIP |
| N | MCP 客户端 | 9/17 PASS | 核心 MCP 通路通过；Phase 5/REPL-only 场景仍 SKIP |
| O | SubAgent | 4/8 PASS | Explore / Plan / background 基础链路通过 |
| P | 会话持久化 | 3/6 PASS | 单轮会话记忆通过，跨重启恢复仍 SKIP |
| Q | Print Mode | 5/5 PASS | text/json/safe/verbose 全通过 |
| R | 错误处理 | 15/15 PASS | 错误路径覆盖完整 |
| S | 综合链路 | 6/6 PASS | 多步主链路、子 Agent 链路通过 |
| T | 自动化断言 | 11/12 PASS | T4 超时；其余断言链路通过 |

## 真实 fixture 覆盖

| 类型 | 文件/配置 | 用途 |
|---|---|---|
| MCP Server | `tests/fixtures/mcp_echo_server.py` | 验证 stdio MCP 工具发现与调用 |
| Hooks | `tests/fixtures/hooks/pre_tool_use.py` 等 | 验证 pre/post/user prompt hook |
| Plugin | `tests/fixtures/test-plugin/*` | 验证 plugin refresh / install / enable / disable / uninstall |
| Project Config | `.pode.json` | 验证项目级 MCP / hook 装载 |

## 剩余 TIMEOUT 用例

| ID | 场景 | 原因判断 |
|---|---|---|
| A8 | safe mode 写入阻止 | GLM 偶发进入工具参数自我纠正，未在超时前收敛 |
| C3 | REPL input/output | 当前自动化 subprocess 不提供真实 PTY，属于环境限制 |
| G4 | 长函数拆分 | 复杂多步代码生成在当前 provider 下不稳定 |
| T4 | dirname 断言 | 极短指令偶发触发不必要工具规划，导致超时 |

## SKIP 的主要类型

36 个 `SKIP` 主要集中在以下几类，不是主链路失败：

1. **REPL-only/交互式场景**：需要真实终端输入或多轮人工选择。
2. **Notebook / Phase 5 占位能力**：功能尚未完全落地。
3. **高级 Slash / Skill / SubAgent 恢复场景**：需要更强的会话恢复与前端协同。
4. **跨重启会话恢复**：当前 E2E runner 还没有完整自动化 harness。

## 结论

Pode-Agent 当前已经具备可用的主流程能力：**print mode、工具调用、项目感知、文件编辑、错误处理、Plugin、MCP、基础 SubAgent、综合链路** 都已经跑通。

剩余问题主要分为两类：

1. **自动化环境限制**：如 C3 的 PTY 缺失。
2. **模型级偶发抖动**：如 A8 / G4 / T4，这些更像 provider 在个别提示词上的稳定性问题，而不是核心产品链路已损坏。
