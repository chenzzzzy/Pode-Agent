# Pode-Agent 测试策略

> 版本：1.0.0 | 状态：草稿 | 更新：2026-03-31

---

## 目录

1. [测试层次](#测试层次)
2. [单元测试规范](#单元测试规范)
3. [集成测试规范](#集成测试规范)
4. [E2E 测试规范](#e2e-测试规范)
5. [测试工具和夹具](#测试工具和夹具)
6. [各 Phase 测试要求](#各-phase-测试要求)
7. [CI/CD 集成](#cicd-集成)

---

## 测试层次

```
                    ┌──────────────────────┐
                    │     E2E Tests         │  少量，测试关键用户路径
                    │  (tests/e2e/)         │  真实 CLI 命令
                    └──────────┬───────────┘
                               │
               ┌───────────────┴────────────────┐
               │      Integration Tests          │  中等数量，测试模块协作
               │  (tests/integration/)           │  Mock 外部 API
               └───────────────┬────────────────┘
                               │
    ┌──────────────────────────┴─────────────────────────┐
    │                  Unit Tests                         │  大量，快速
    │              (tests/unit/)                          │  完全 Mock
    └─────────────────────────────────────────────────────┘
```

**目标覆盖率**：

| 层次 | 文件 | 覆盖率目标 |
|------|------|----------|
| 单元测试 | `tests/unit/` | ≥ 80% |
| 集成测试 | `tests/integration/` | 关键路径 100% |
| E2E 测试 | `tests/e2e/` | 10 个核心场景 |

---

## 单元测试规范

### 文件组织

```
tests/unit/
├── core/
│   ├── test_config.py
│   ├── test_permissions.py
│   ├── test_cost_tracker.py
│   └── tools/
│       ├── test_tool_base.py
│       └── test_executor.py
├── tools/
│   ├── system/
│   │   ├── test_bash.py
│   │   ├── test_kill_shell.py
│   │   └── test_task_output.py
│   ├── filesystem/
│   │   ├── test_file_read.py
│   │   ├── test_file_write.py
│   │   ├── test_file_edit.py
│   │   └── test_glob.py
│   ├── search/
│   │   └── test_grep.py
│   └── network/
│       ├── test_web_fetch.py
│       └── test_web_search.py
├── services/
│   ├── ai/
│   │   ├── test_anthropic.py
│   │   ├── test_openai.py
│   │   └── test_factory.py
│   ├── context/
│   │   └── test_mentions.py
│   └── plugins/
│       └── test_commands.py
└── app/
    └── test_session.py
```

### 测试命名规范

```python
# 格式：test_{method}_{scenario}_{expected_result}

def test_is_safe_bash_command_ls_returns_true():
    assert is_safe_bash_command("ls -la") is True

def test_is_safe_bash_command_rm_returns_false():
    assert is_safe_bash_command("rm -rf .") is False

def test_file_edit_old_str_not_found_raises_error():
    ...

async def test_bash_tool_call_captures_stdout():
    ...
```

### 单元测试示例

#### Config 测试

```python
# tests/unit/core/test_config.py
import pytest
from pathlib import Path
from pode_agent.core.config import (
    get_global_config, save_global_config, GlobalConfig
)

class TestGetGlobalConfig:
    def test_returns_defaults_when_file_not_exist(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PODE_CONFIG_DIR", str(tmp_path))
        
        config = get_global_config()
        
        assert config.theme == "dark"
        assert config.verbose is False
        assert config.num_startups == 0

    def test_reads_existing_config(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PODE_CONFIG_DIR", str(tmp_path))
        config_file = tmp_path / "config.json"
        config_file.write_text('{"theme": "light", "verbose": true}')
        
        config = get_global_config()
        
        assert config.theme == "light"
        assert config.verbose is True

    def test_returns_defaults_on_corrupted_file(self, tmp_path, monkeypatch, caplog):
        monkeypatch.setenv("PODE_CONFIG_DIR", str(tmp_path))
        (tmp_path / "config.json").write_text("not valid json")
        
        config = get_global_config()
        
        assert config.theme == "dark"  # 默认值
        assert "corrupted" in caplog.text.lower() or "invalid" in caplog.text.lower()

class TestSaveGlobalConfig:
    def test_writes_and_reads_back(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PODE_CONFIG_DIR", str(tmp_path))
        
        original = get_global_config()
        modified = original.model_copy(update={"theme": "light"})
        save_global_config(modified)
        
        reloaded = get_global_config()
        assert reloaded.theme == "light"

    def test_creates_parent_dirs(self, tmp_path, monkeypatch):
        config_dir = tmp_path / "nested" / "pode"
        monkeypatch.setenv("PODE_CONFIG_DIR", str(config_dir))
        
        save_global_config(GlobalConfig())
        
        assert (config_dir / "config.json").exists()
```

#### BashTool 测试

```python
# tests/unit/tools/system/test_bash.py
import pytest
import asyncio
from pode_agent.tools.system.bash import BashTool, BashInput
from pode_agent.core.tools.base import ToolUseContext, ToolOutput

@pytest.fixture
def bash_tool():
    return BashTool()

@pytest.fixture
def context():
    return ToolUseContext(
        message_id="test-msg",
        abort_event=asyncio.Event(),
    )

class TestBashToolPermissions:
    def test_safe_command_needs_no_permission(self, bash_tool):
        assert bash_tool.needs_permissions(BashInput(command="ls -la")) is False

    def test_dangerous_command_needs_permission(self, bash_tool):
        assert bash_tool.needs_permissions(BashInput(command="npm install")) is True
    
    def test_rm_command_needs_permission(self, bash_tool):
        assert bash_tool.needs_permissions(BashInput(command="rm -rf /tmp/test")) is True

class TestBashToolCall:
    @pytest.mark.asyncio
    async def test_captures_stdout(self, bash_tool, context):
        outputs = []
        async for output in bash_tool.call(BashInput(command="echo hello"), context):
            outputs.append(output)
        
        result = next(o for o in outputs if o.type == "result")
        assert result.data["stdout"].strip() == "hello"
        assert result.data["exit_code"] == 0

    @pytest.mark.asyncio
    async def test_captures_stderr(self, bash_tool, context):
        outputs = []
        async for output in bash_tool.call(
            BashInput(command="echo error >&2"),
            context
        ):
            outputs.append(output)
        
        result = next(o for o in outputs if o.type == "result")
        assert "error" in result.data["stderr"]

    @pytest.mark.asyncio
    async def test_handles_timeout(self, bash_tool, context):
        outputs = []
        async for output in bash_tool.call(
            BashInput(command="sleep 100", timeout=100),  # 100ms timeout
            context
        ):
            outputs.append(output)
        
        result = next(o for o in outputs if o.type == "result")
        assert "timed out" in (result.data.get("error") or "").lower()

    @pytest.mark.asyncio
    async def test_abort_stops_execution(self, bash_tool):
        abort_event = asyncio.Event()
        context = ToolUseContext(
            message_id="test",
            abort_event=abort_event,
        )
        
        # 中止事件在执行中触发
        asyncio.get_event_loop().call_later(0.1, abort_event.set)
        
        outputs = []
        async for output in bash_tool.call(
            BashInput(command="sleep 10"),
            context
        ):
            outputs.append(output)
        
        # 应该在 sleep 10 完成之前结束
        assert any(o.type == "result" for o in outputs)
```

#### Permissions 测试

```python
# tests/unit/core/test_permissions.py
import pytest
from pode_agent.core.permissions.engine import PermissionEngine
from pode_agent.core.permissions import PermissionResult, PermissionContext, PermissionMode
from pode_agent.core.config.schema import ProjectConfig

@pytest.fixture
def engine():
    return PermissionEngine()

class TestHasPermissions:
    @pytest.mark.asyncio
    async def test_bypass_mode_always_allowed(self, engine):
        ctx = PermissionContext(mode=PermissionMode.BYPASS_PERMISSIONS)
        result = await engine.has_permissions("bash", {"command": "rm -rf /"}, ctx)
        assert result == PermissionResult.ALLOWED

    @pytest.mark.asyncio
    async def test_safe_bash_allowed_by_default(self, engine):
        ctx = PermissionContext()
        result = await engine.has_permissions("bash", {"command": "ls"}, ctx)
        assert result == PermissionResult.ALLOWED

    @pytest.mark.asyncio
    async def test_dangerous_bash_needs_prompt(self, engine):
        ctx = PermissionContext()
        result = await engine.has_permissions("bash", {"command": "npm install"}, ctx)
        assert result == PermissionResult.NEEDS_PROMPT

    @pytest.mark.asyncio
    async def test_plan_mode_blocks_write_tools(self, engine):
        ctx = PermissionContext(mode=PermissionMode.PLAN)
        result = await engine.has_permissions("file_edit", {"file_path": "test.py"}, ctx)
        assert result == PermissionResult.DENIED

    @pytest.mark.asyncio
    async def test_project_config_denied_tools(self, engine):
        config = ProjectConfig(denied_tools=["bash"])
        ctx = PermissionContext(project_config=config)
        result = await engine.has_permissions("bash", {"command": "ls"}, ctx)
        assert result == PermissionResult.DENIED
```

---

## 集成测试规范

### 文件组织

```
tests/integration/
├── test_session.py          # 完整会话流程（Mock LLM）
├── test_bash_tool.py        # BashTool + 真实 Shell 执行
├── test_file_tools.py       # 文件工具 + 真实文件系统
├── test_llm_providers.py    # LLM Provider Mock 测试
└── test_mcp_client.py       # MCP 客户端（Mock 服务器）
```

### 集成测试示例

#### Session 集成测试

```python
# tests/integration/test_session.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pode_agent.app.session import SessionManager, SessionEventType
from pode_agent.tools import get_all_tools

@pytest.fixture
def tools():
    return get_all_tools()

@pytest.fixture
def session(tmp_path, tools):
    return SessionManager(
        tools=tools,
        commands=[],
        message_log_name="test_session",
        # 使用 tmp_path 作为日志目录
    )

class TestSessionProcessInput:
    @pytest.mark.asyncio
    async def test_text_only_response(self, session):
        """测试纯文本响应（无工具调用）"""
        mock_response = create_mock_llm_response(text="Hello, World!")
        
        with patch("pode_agent.services.ai.query_llm", return_value=mock_response):
            events = []
            async for event in session.process_input("Say hello"):
                events.append(event)
        
        event_types = [e.type for e in events]
        assert SessionEventType.USER_MESSAGE in event_types
        assert SessionEventType.ASSISTANT_DELTA in event_types
        assert SessionEventType.DONE in event_types
        
        # 验证 delta 内容
        deltas = [e for e in events if e.type == SessionEventType.ASSISTANT_DELTA]
        full_text = "".join(e.data for e in deltas)
        assert "Hello, World!" in full_text

    @pytest.mark.asyncio
    async def test_tool_call_flow(self, session):
        """测试单次工具调用流程"""
        # Mock LLM 先返回工具调用，再返回最终文本
        mock_responses = [
            create_mock_tool_use_response("bash", {"command": "echo test"}),
            create_mock_text_response("The command output 'test'"),
        ]
        
        call_count = 0
        async def mock_query_llm(params):
            nonlocal call_count
            response = mock_responses[call_count]
            call_count += 1
            for item in response:
                yield item
        
        with patch("pode_agent.services.ai.query_llm", side_effect=mock_query_llm):
            events = []
            async for event in session.process_input("Run echo test"):
                events.append(event)
        
        event_types = [e.type for e in events]
        assert SessionEventType.TOOL_USE_START in event_types
        assert SessionEventType.TOOL_RESULT in event_types
        assert SessionEventType.DONE in event_types
```

### LLM Provider Mock

```python
# tests/helpers/llm_mocks.py
from collections.abc import AsyncGenerator
from pode_agent.services.ai.base import AIResponse

async def mock_text_response(text: str) -> AsyncGenerator[AIResponse, None]:
    """生成文本响应的 mock"""
    yield AIResponse(type="text_delta", text=text)
    yield AIResponse(
        type="message_done",
        usage={"input_tokens": 10, "output_tokens": 5},
        cost_usd=0.001,
        stop_reason="end_turn",
    )

async def mock_tool_use_response(
    tool_name: str,
    tool_input: dict,
    tool_use_id: str = "tool_123",
) -> AsyncGenerator[AIResponse, None]:
    """生成工具调用响应的 mock"""
    yield AIResponse(
        type="tool_use_start",
        tool_use_id=tool_use_id,
        tool_name=tool_name,
    )
    yield AIResponse(
        type="tool_use_end",
        tool_use_id=tool_use_id,
        tool_name=tool_name,
        tool_input=tool_input,
    )
    yield AIResponse(
        type="message_done",
        usage={"input_tokens": 20, "output_tokens": 10},
        cost_usd=0.002,
        stop_reason="tool_use",
    )
```

---

## E2E 测试规范

### 关键场景

```python
# tests/e2e/test_cli.py
import subprocess
import pytest

@pytest.mark.e2e
class TestCliBasicUsage:
    def test_version_command(self):
        result = subprocess.run(
            ["pode", "--version"],
            capture_output=True, text=True
        )
        assert result.returncode == 0
        assert "pode-agent" in result.stdout
    
    def test_help_command(self):
        result = subprocess.run(
            ["pode", "--help"],
            capture_output=True, text=True
        )
        assert result.returncode == 0
        assert "Usage" in result.stdout
    
    def test_config_get_set(self, tmp_pode_dir):
        # set
        result = subprocess.run(
            ["pode", "config", "set", "theme", "light"],
            capture_output=True, text=True,
            env={"PODE_CONFIG_DIR": str(tmp_pode_dir)},
        )
        assert result.returncode == 0
        
        # get
        result = subprocess.run(
            ["pode", "config", "get", "theme"],
            capture_output=True, text=True,
            env={"PODE_CONFIG_DIR": str(tmp_pode_dir)},
        )
        assert result.returncode == 0
        assert "light" in result.stdout

@pytest.mark.e2e
@pytest.mark.requires_api_key
class TestCliWithLLM:
    """需要真实 API key 才能运行（标记为 requires_api_key）"""
    
    def test_simple_query(self):
        result = subprocess.run(
            ["pode", "-p", "Say 'test passed' and nothing else"],
            capture_output=True, text=True,
            timeout=30,
        )
        assert result.returncode == 0
        assert "test passed" in result.stdout.lower()
```

---

## 测试工具和夹具

### `tests/conftest.py`（全局夹具）

```python
import pytest
import asyncio
from pathlib import Path

@pytest.fixture(scope="session")
def event_loop():
    """全局 asyncio 事件循环"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def tmp_cwd(tmp_path, monkeypatch):
    """临时工作目录"""
    monkeypatch.chdir(tmp_path)
    return tmp_path

@pytest.fixture
def tmp_pode_dir(tmp_path, monkeypatch):
    """临时 Pode 配置目录"""
    pode_dir = tmp_path / ".pode"
    pode_dir.mkdir()
    monkeypatch.setenv("PODE_CONFIG_DIR", str(pode_dir))
    return pode_dir

@pytest.fixture
def sample_project(tmp_cwd):
    """包含一些示例文件的测试项目"""
    (tmp_cwd / "main.py").write_text("def main():\n    pass\n")
    (tmp_cwd / "README.md").write_text("# Test Project\nA test project.\n")
    (tmp_cwd / "requirements.txt").write_text("pytest\n")
    return tmp_cwd

@pytest.fixture
def mock_anthropic_client():
    """Mock Anthropic 客户端"""
    with patch("anthropic.AsyncAnthropic") as mock:
        yield mock
```

### VCR 录制/回放（HTTP 交互测试）

```python
# tests/helpers/vcr_helper.py
# 用于录制和回放 HTTP 请求（类似 Kode-Agent 的 VCR 工具）

import respx  # httpx mock 库
import httpx

@pytest.fixture
def respx_mock():
    """Mock HTTP 请求"""
    with respx.mock() as mock:
        yield mock

# 使用示例
def test_web_fetch_tool(respx_mock):
    respx_mock.get("https://example.com").mock(
        return_value=httpx.Response(200, text="<html>Hello</html>")
    )
    ...
```

---

## 各 Phase 测试要求

### Phase 0 测试要求

- [ ] `tests/unit/core/test_config.py`：config 读写、默认值、错误处理
- [ ] `tests/unit/infra/test_logging.py`：日志基础配置

### Phase 1 测试要求

- [ ] `tests/unit/core/test_permissions.py`：权限检查所有场景
- [ ] `tests/unit/tools/system/test_bash.py`：BashTool 所有功能
- [ ] `tests/unit/tools/filesystem/test_file_read.py`
- [ ] `tests/unit/tools/filesystem/test_file_write.py`
- [ ] `tests/unit/tools/filesystem/test_file_edit.py`：重点测试 old_str 唯一性
- [ ] `tests/unit/tools/search/test_grep.py`

### Phase 2 测试要求

- [ ] `tests/unit/services/ai/test_anthropic.py`：流式响应处理，mock 所有 API 调用
- [ ] `tests/unit/services/ai/test_openai.py`
- [ ] `tests/unit/services/ai/test_factory.py`：模型路由逻辑
- [ ] `tests/integration/test_session.py`：完整会话流程（Mock LLM）
- [ ] `tests/unit/app/test_session.py`：权限交互、中止处理

### Phase 3 测试要求

- [ ] 每个新工具至少 5 个单元测试
- [ ] `tests/integration/test_tool_registry.py`：所有工具正确注册和可用

### Phase 4 测试要求

- [ ] `src/ui/components/__tests__/test_permission_dialog.tsx`：权限对话框渲染（Ink `render()` + `lastFrame()`）
- [ ] `src/ui/components/__tests__/test_message.tsx`：消息组件渲染测试
- [ ] `src/ui/__tests__/test_repl.tsx`：REPL Screen 集成测试
- [ ] `src/ui/rpc/__tests__/test_client.ts`：JSON-RPC 客户端测试
- [ ] `tests/unit/entrypoints/test_ui_bridge.py`：Python 端 JSON-RPC 服务端测试
- [ ] React 组件快照测试（`src/ui/__snapshots__/`）

### Phase 5 测试要求

- [ ] `tests/integration/test_mcp_client.py`：连接 Mock MCP 服务器
- [ ] `tests/unit/services/plugins/test_commands.py`：YAML 命令解析
- [ ] `tests/unit/services/plugins/test_marketplace.py`：manifest 验证

### Phase 6 测试要求

- [ ] `tests/e2e/test_cli.py`：10 个关键用户场景
- [ ] `tests/parity/test_parity.py`：与 Kode-Agent 的功能对比测试

---

## CI/CD 集成

### GitHub Actions 配置

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest]
        python-version: ["3.11", "3.12"]
    
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: "pip"
      
      - name: Install dependencies
        run: pip install -e ".[dev]"
      
      - name: Type check
        run: mypy pode_agent/
      
      - name: Lint
        run: ruff check pode_agent/
      
      - name: Format check
        run: ruff format --check pode_agent/
      
      - name: Unit tests
        run: pytest tests/unit/ -v --cov=pode_agent --cov-report=xml
      
      - name: Integration tests
        run: pytest tests/integration/ -v -m "not requires_api_key"
      
      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          files: coverage.xml

  e2e:
    runs-on: ubuntu-latest
    needs: test
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - name: E2E tests (no API key)
        run: pytest tests/e2e/ -v -m "not requires_api_key"
```

### 测试标记系统

```python
# pytest.ini_options 中配置
markers = [
    "e2e: End-to-end tests that run the full CLI",
    "requires_api_key: Tests that need real API keys",
    "slow: Tests that take more than 10 seconds",
    "integration: Integration tests",
]

# 运行特定标记
# pytest -m "not requires_api_key and not slow"
# pytest -m "e2e"
# pytest -m "integration and not requires_api_key"
```
