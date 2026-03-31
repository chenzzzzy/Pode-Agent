# Pode-Agent 技术栈选型

> 版本：1.0.0 | 状态：已决定 | 更新：2026-03-31

---

## 目录

1. [运行时要求](#运行时要求)
2. [核心依赖](#核心依赖)
3. [选型对比表](#选型对比表)
4. [各库详细说明](#各库详细说明)
5. [项目结构（pyproject.toml）](#项目结构)
6. [开发工具链](#开发工具链)

---

## 运行时要求

| 项目 | 要求 |
|------|------|
| **Python** | ≥ 3.11（用于 `tomllib`、`ExceptionGroup`、`TaskGroup`） |
| **操作系统** | Linux、macOS、Windows（WSL2 推荐） |
| **内存** | ≥ 512MB |
| **依赖工具** | `ripgrep`（可选，GrepTool 推荐） |

---

## 核心依赖

### 生产依赖

| 类别 | 库 | 版本 | TypeScript 对应 |
|------|-----|------|-----------------|
| **CLI 框架** | `typer` | ≥0.12 | Commander.js |
| **终端 UI** | `textual` | ≥0.60 | React + Ink |
| **数据验证** | `pydantic` | ≥2.6 | Zod |
| **HTTP 客户端** | `httpx` | ≥0.27 | undici / fetch |
| **LLM - Anthropic** | `anthropic` | ≥0.26 | @anthropic-ai/sdk |
| **LLM - OpenAI** | `openai` | ≥1.30 | openai |
| **MCP 协议** | `mcp` | ≥1.0 | @modelcontextprotocol/sdk |
| **富文本输出** | `rich` | ≥13.7 | chalk + ink |
| **YAML 解析** | `pyyaml` | ≥6.0 | js-yaml |
| **TOML 解析** | `tomllib`（stdlib） | 内置 | toml |
| **Git 集成** | `gitpython` | ≥3.1 | isomorphic-git |
| **错误追踪** | `sentry-sdk` | ≥2.0 | @sentry/node |
| **进程管理** | asyncio（stdlib） | 内置 | child_process |
| **JSON Schema** | `jsonschema` | ≥4.21 | zod-to-json-schema |
| **Markdown 渲染** | `rich`（内置） | 内置 | react-markdown |
| **WebSocket** | `websockets` | ≥12.0 | ws |

### 开发依赖

| 类别 | 库 | 版本 | TypeScript 对应 |
|------|-----|------|-----------------|
| **测试框架** | `pytest` | ≥8.0 | bun test |
| **异步测试** | `pytest-asyncio` | ≥0.23 | - |
| **Mock** | `pytest-mock` | ≥3.12 | - |
| **覆盖率** | `pytest-cov` | ≥5.0 | - |
| **类型检查** | `mypy` | ≥1.10 | tsc |
| **Linter** | `ruff` | ≥0.4 | ESLint |
| **格式化** | `ruff format` | ≥0.4 | Prettier |
| **HTTP Mock** | `respx` | ≥0.20 | msw |
| **测试快照** | `syrupy` | ≥4.0 | jest snapshots |

---

## 选型对比表

### CLI 框架：Typer vs Click vs argparse

| 特性 | Typer | Click | argparse |
|------|-------|-------|----------|
| 类型提示支持 | ✅ 原生 | 部分 | ❌ |
| 自动帮助生成 | ✅ | ✅ | ✅ |
| 子命令嵌套 | ✅ | ✅ | 手动 |
| 丰富输出（rich）| ✅ 内置 | 手动 | 手动 |
| 学习曲线 | 低 | 低 | 低 |
| **选择** | ✅ **选用** | - | - |

**选用 Typer 理由**：Pydantic-like 的类型注解即文档风格，与项目整体类型系统一致；内置 Rich 支持。

---

### 终端 UI：Textual vs Rich vs urwid vs curses

| 特性 | Textual | Rich | urwid | curses |
|------|---------|------|-------|--------|
| 交互式 Widget | ✅ | ❌ | ✅ | 手动 |
| CSS 样式 | ✅ | ❌ | ❌ | ❌ |
| 异步支持 | ✅ | ❌ | 有限 | ❌ |
| 鼠标支持 | ✅ | ❌ | ✅ | 有限 |
| 测试友好 | ✅（截图）| ✅ | 困难 | 困难 |
| 活跃维护 | ✅ | ✅ | 一般 | 稳定 |
| **选择** | ✅ **选用** | 辅助用 | - | - |

**选用 Textual 理由**：
- 最接近 React/Ink 的编程模型（组件化、响应式）
- 原生异步支持（与 asyncio 完美集成）
- 有完整的测试工具（`TextualPilot` 用于自动化测试）
- 活跃的社区和维护（Will McGugan 主导）

---

### LLM 客户端：官方 SDK vs litellm vs langchain

| 特性 | 官方 SDK | litellm | langchain |
|------|----------|---------|-----------|
| 最新 API 支持 | ✅ | 有延迟 | 有延迟 |
| 轻量级 | ✅ | ✅ | ❌（很重）|
| 流式支持 | ✅ | ✅ | 有限 |
| Tool Calling | ✅ | ✅ | 封装 |
| 控制粒度 | ✅ 完全 | 中等 | 低 |
| **选择** | ✅ **选用** | 作为备选 | ❌ |

**选用官方 SDK 理由**：
- 与 Kode-Agent 保持对应关系（一对一对照）
- 支持所有最新功能（extended thinking、tool_choice 等）
- 避免不必要的抽象层

---

### 数据验证：Pydantic v2 vs attrs vs dataclasses

| 特性 | Pydantic v2 | attrs | dataclasses |
|------|-------------|-------|-------------|
| JSON Schema 生成 | ✅ | 需插件 | ❌ |
| 运行时验证 | ✅ | ✅ | 手动 |
| 性能 | ✅（Rust）| ✅ | ✅ |
| 序列化 | ✅ | 手动 | 手动 |
| FastAPI 兼容 | ✅ | 部分 | 部分 |
| **选择** | ✅ **选用** | - | 仅简单 DTO |

---

## 各库详细说明

### Typer（CLI 框架）

```python
# 示例：pode 的 CLI 结构
import typer
from typing import Annotated

app = typer.Typer(help="Pode-Agent: AI Coding Assistant")

@app.command()
def ask(
    prompt: Annotated[str, typer.Argument(help="Your question")],
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    safe_mode: bool = typer.Option(False, "--safe"),
    model: str = typer.Option(None, "--model", "-m"),
):
    """Ask the AI assistant a question"""
    ...

config_app = typer.Typer()
app.add_typer(config_app, name="config")

@config_app.command("set")
def config_set(key: str, value: str): ...

@config_app.command("get")
def config_get(key: str): ...
```

### Textual（终端 UI）

```python
# 示例：REPL Screen
from textual.app import App, ComposeResult
from textual.widgets import Input, ListView, Label
from textual.containers import Container

class ReplScreen(App):
    CSS = """
    Screen { background: $surface; }
    #messages { height: 1fr; overflow-y: scroll; }
    #input-area { height: auto; dock: bottom; }
    """

    def compose(self) -> ComposeResult:
        yield Container(id="messages")
        yield Container(
            Input(placeholder="Type your message...", id="prompt"),
            id="input-area"
        )

    async def on_input_submitted(self, event: Input.Submitted):
        await self.process_input(event.value)
```

### Pydantic v2（数据模型）

```python
# 示例：Config Schema
from pydantic import BaseModel, Field
from typing import Literal

class GlobalConfig(BaseModel):
    model_config = {"extra": "allow"}  # 允许未知字段（向前兼容）

    num_startups: int = 0
    theme: Literal["dark", "light"] = "dark"
    verbose: bool = False
    default_model_name: str = "claude-3-5-sonnet-20241022"
    auto_compact_threshold: int = 50

    # 生成 JSON Schema（用于 MCP 工具定义）
    @classmethod
    def tool_schema(cls) -> dict:
        return cls.model_json_schema()
```

### httpx（HTTP 客户端）

```python
# 示例：带代理支持的 HTTP 客户端
import httpx

async def create_http_client(proxy: str | None = None) -> httpx.AsyncClient:
    transport = None
    if proxy:
        transport = httpx.AsyncHTTPTransport(proxy=proxy)
    
    return httpx.AsyncClient(
        transport=transport,
        timeout=httpx.Timeout(30.0, connect=10.0),
        headers={"User-Agent": f"pode-agent/{VERSION}"}
    )
```

### MCP Python SDK

```python
# 示例：MCP 客户端连接
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def connect_to_mcp_server(name: str, config: McpServerConfig):
    server_params = StdioServerParameters(
        command=config.command,
        args=config.args,
        env=config.env,
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            return tools
```

---

## 项目结构

### pyproject.toml（完整）

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "pode-agent"
version = "0.1.0"
description = "AI-powered terminal coding assistant (Python rewrite of Kode-Agent)"
readme = "README.md"
license = { text = "Apache-2.0" }
requires-python = ">=3.11"
authors = [
    { name = "Pode-Agent Contributors" }
]
keywords = ["ai", "agent", "cli", "coding-assistant", "llm"]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Environment :: Console",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: Apache Software License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Topic :: Software Development :: Code Generators",
]

dependencies = [
    # CLI
    "typer>=0.12.0",
    # Terminal UI
    "textual>=0.60.0",
    "rich>=13.7.0",
    # Data validation
    "pydantic>=2.6.0",
    "pydantic-settings>=2.2.0",
    # HTTP
    "httpx>=0.27.0",
    "httpx[http2]>=0.27.0",
    # LLM Providers
    "anthropic>=0.26.0",
    "openai>=1.30.0",
    # MCP Protocol
    "mcp>=1.0.0",
    # Git
    "gitpython>=3.1.40",
    # Config / YAML
    "pyyaml>=6.0.1",
    # WebSocket
    "websockets>=12.0",
    # Error Tracking
    "sentry-sdk>=2.0.0",
    # Utilities
    "python-dateutil>=2.9.0",
    "click>=8.1.7",  # Typer dependency
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-mock>=3.12.0",
    "pytest-cov>=5.0.0",
    "mypy>=1.10.0",
    "ruff>=0.4.0",
    "respx>=0.20.0",      # HTTP mocking
    "syrupy>=4.0.0",      # Snapshot testing
    "textual-dev>=0.60.0", # Textual testing tools
    "types-pyyaml",
    "types-python-dateutil",
]

[project.scripts]
pode = "pode_agent.entrypoints.cli:main"
pode-mcp = "pode_agent.entrypoints.mcp_server:main"
pode-acp = "pode_agent.entrypoints.acp_server:main"

[project.entry-points."pode_agent.tools"]
# 内置工具（自动注册）
bash = "pode_agent.tools.system.bash:BashTool"
file_read = "pode_agent.tools.filesystem.file_read:FileReadTool"
# ... 其余工具

[tool.hatch.build.targets.wheel]
packages = ["pode_agent"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
addopts = "-v --tb=short"

[tool.mypy]
python_version = "3.11"
strict = true
ignore_missing_imports = true

[tool.ruff]
target-version = "py311"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "UP", "B", "SIM", "I"]
ignore = ["E501"]

[tool.ruff.format]
quote-style = "double"
```

---

## 开发工具链

### 本地开发环境

```bash
# 推荐使用 uv 管理虚拟环境
pip install uv

# 创建虚拟环境并安装所有依赖
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# 或使用 pip
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
.venv\Scripts\activate      # Windows
pip install -e ".[dev]"
```

### 常用开发命令

```bash
# 开发模式运行
pode --verbose "hello"

# 类型检查
mypy pode_agent/

# Lint + Format
ruff check pode_agent/
ruff format pode_agent/

# 运行测试
pytest tests/unit/
pytest tests/integration/
pytest tests/ --cov=pode_agent --cov-report=html

# 单个测试
pytest tests/unit/test_bash_tool.py -v

# 查看 UI（Textual 开发模式）
textual run --dev pode_agent/ui/app.py
```

### 版本管理

```bash
# 使用 hatch 管理版本
pip install hatch
hatch version patch   # 0.1.0 → 0.1.1
hatch version minor   # 0.1.0 → 0.2.0
hatch version major   # 0.1.0 → 1.0.0

# 构建发行包
hatch build

# 发布到 PyPI
hatch publish
```

### CI/CD（GitHub Actions）

```yaml
# .github/workflows/ci.yml
name: CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        python-version: ["3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -e ".[dev]"
      - run: mypy pode_agent/
      - run: ruff check pode_agent/
      - run: pytest tests/ --cov=pode_agent
```

---

## 版本兼容性矩阵

| Pode-Agent | Python | Anthropic SDK | OpenAI SDK | MCP SDK |
|------------|--------|---------------|------------|---------|
| 0.1.x | 3.11+ | 0.26+ | 1.30+ | 1.0+ |
| 0.2.x | 3.11+ | 0.28+ | 1.35+ | 1.2+ |
| 1.0.x | 3.12+ | 0.30+ | 1.40+ | 1.5+ |
