# Pode-Agent — Python AI Coding Agent

> **Python 1:1 rewrite of [Kode-Agent](https://github.com/chenzzzzy/Kode-Agent)**  
> A powerful, extensible, terminal-native AI coding assistant.

---

## 目录（Table of Contents）

1. [项目愿景 (Project Vision)](#项目愿景)
2. [产品目标 (Product Goals)](#产品目标)
3. [核心特性 (Core Features)](#核心特性)
4. [与原版对比 (Comparison with Kode-Agent)](#与原版对比)
5. [文档导航 (Documentation Index)](#文档导航)
6. [快速开始 (Quick Start)](#快速开始)
7. [路线图 (Roadmap)](#路线图)

---

## 项目愿景

**Pode-Agent** 是 Kode-Agent 的 Python 重写版本，目标是：

- **开发者友好**：使用纯 Python 生态，降低贡献门槛（不需要 Bun/Node 环境）
- **生产就绪**：完整保留原版所有功能，行为 1:1 对齐
- **可扩展性**：利用 Python 丰富的 AI/ML 生态（LangChain、LlamaIndex、HuggingFace 等）更易集成
- **跨平台**：通过 `pip install pode-agent` 在任意平台安装

**核心价值主张**：让每个 Python 开发者都能用自己熟悉的工具，在终端中拥有一个智能 AI 编程助手。

---

## 产品目标

### 短期目标（Phase 1-2，0-3 个月）
- [ ] 实现完整 CLI 基础框架（typer + rich）
- [ ] 实现多 LLM Provider 支持（Anthropic、OpenAI）
- [ ] 实现核心 Tool 系统（Bash、文件读写、Grep）
- [ ] 实现基础会话管理（JSONL 日志）
- [ ] 实现权限系统基础

### 中期目标（Phase 3-4，3-6 个月）
- [ ] 实现完整终端 UI（Textual 框架）
- [ ] 实现 MCP 客户端/服务端协议
- [ ] 实现插件系统（Skill Marketplace）
- [ ] 实现所有 24+ 个 Tool
- [ ] 实现上下文管理（项目感知）

### 长期目标（Phase 5，6 个月以上）
- [ ] 100% 功能对齐 Kode-Agent
- [ ] Python 生态独有功能（Jupyter 集成增强、Python REPL）
- [ ] 发布到 PyPI，提供完整文档

---

## 核心特性

| 特性 | 描述 |
|------|------|
| **多 Provider 支持** | Anthropic Claude、OpenAI GPT-5、Mistral、DeepSeek、Ollama 等 15+ 个 |
| **智能工具系统** | 24+ 个内置工具（Bash、文件系统、Web 搜索、Jupyter 等） |
| **权限管理** | 细粒度工具执行权限，每个操作可审批/拒绝 |
| **会话持久化** | JSONL 格式会话日志，支持断点续传 |
| **MCP 协议** | 作为 MCP 客户端连接外部服务，也可作为 MCP 服务端暴露工具 |
| **插件系统** | 从 GitHub/npm/URL 安装技能包（Skill Marketplace） |
| **上下文感知** | 自动读取 README、git 状态、项目结构 |
| **终端 UI** | 基于 Textual 的丰富终端界面，支持语法高亮 |
| **计划模式** | 先规划后执行，减少意外操作 |

---

## 与原版对比

| 维度 | Kode-Agent (TypeScript) | Pode-Agent (Python) |
|------|------------------------|---------------------|
| **运行时** | Bun / Node.js ≥20 | Python ≥3.11 |
| **安装方式** | `npm install -g @shareai-lab/kode` | `pip install pode-agent` |
| **CLI 框架** | Commander.js | Typer |
| **终端 UI** | React + Ink | Textual |
| **Schema 验证** | Zod | Pydantic v2 |
| **HTTP 客户端** | undici / fetch | httpx (async) |
| **测试框架** | Bun test | pytest + pytest-asyncio |
| **异步模型** | Async/Await + Generator | asyncio + AsyncGenerator |
| **LLM SDK** | anthropic-sdk-js / openai-node | anthropic / openai Python SDK |
| **MCP SDK** | @modelcontextprotocol/sdk | mcp (Python SDK) |
| **打包** | esbuild bundle + binary | PyInstaller / zipapp |

---

## 文档导航

| 文档                           | 描述 | 受众 |
|------------------------------|------|------|
| [架构设计](./docs/architecture.md) | 系统架构、层次划分、模块依赖图 | 架构师、Tech Lead |
| [核心引擎](./docs/agent-loop.md)   | **Agentic Loop 权威文档**：递归主循环、ToolUseQueue、Hook 系统、Auto-compact | 开发者 |
| [工具系统](./docs/tools-system.md) | **工具系统权威文档**：存储组织、注册发现、LLM 连接、权限耦合、并发语义 | 开发者 |
| [计划模式](./docs/plan-mode.md)    | **Plan Mode 权威文档**：先规划后执行、JSONL 存储、Enter/Exit、多步执行 | 开发者 |
| [技术栈](./docs/tech-stack.md)  | Python 技术选型及理由 | 所有开发者 |
| [模块规范](./docs/modules.md)    | 每个模块的职责、接口、内部结构 | 开发者 |
| [数据流](./docs/data-flows.md)       | 关键路径时序图（用户输入→工具执行→响应） | 开发者 |
| [实施计划](./docs/phases.md)          | 分阶段开发计划，含优先级和依赖 | PM、Tech Lead |
| [API 规范](./docs/api-specs.md)     | 模块间内部 API 契约 | 开发者 |
| [测试策略](./docs/testing-strategy.md) | 单元/集成/E2E 测试方案 | QA、开发者 |

---

## 快速开始（目标效果）

```bash
# 安装
pip install pode-agent

# 配置 API Key
pode config set api_key sk-...

# 运行
pode "Help me refactor this function"

# 交互模式
pode

# 非交互模式（print mode）
pode -p "What does this codebase do?"

# 安全模式
pode --safe "Run tests and show me the results"
```

---

## 路线图

```
Phase 1 (Weeks 1-4):  基础骨架
  ├─ CLI 框架 + 配置系统
  ├─ 基础 LLM 集成（Anthropic）
  ├─ 核心工具（Bash + File IO + Grep）
  └─ JSONL 会话日志

Phase 2 (Weeks 5-8):  核心功能
  ├─ 多 Provider 支持（OpenAI + 自定义）
  ├─ 权限系统
  ├─ 上下文管理（项目感知）
  └─ 所有文件系统工具

Phase 3 (Weeks 9-12): 终端 UI
  ├─ Textual REPL 界面
  ├─ 消息渲染（Markdown + 语法高亮）
  ├─ 权限对话框
  └─ 进度指示器

Phase 4 (Weeks 13-16): 高级功能
  ├─ MCP 客户端/服务端
  ├─ 插件系统 + Skill Marketplace
  ├─ Web 工具（搜索 + 抓取）
  └─ ACP 协议

Phase 5 (Weeks 17-20): 完善与发布
  ├─ 100% 功能对齐验证
  ├─ 性能优化
  ├─ 完整文档
  └─ PyPI 发布
```

---

> 📌 **给 Code Agent 的说明**：请按照 [实施计划](./phases.md) 中规定的阶段顺序实现。每个阶段完成后，运行对应的测试套件验证功能正确性，然后再进入下一阶段。详细的接口规范请参考 [模块规范](./modules.md) 和 [API 规范](./api-specs.md)。**核心 Agentic Loop 引擎**的运行时行为和设计规格请参阅 [核心引擎文档](./docs/agent-loop.md)（实现 `app/query.py` 的权威参考）。**工具系统**（注册/发现/启用/权限/并发）的设计规格请参阅 [工具系统文档](./docs/tools-system.md)。**计划模式**（先规划后执行、JSONL 存储、步骤追踪）的设计规格请参阅 [计划模式文档](./docs/plan-mode.md)。
