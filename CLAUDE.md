# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Pode-Agent is a Python (>=3.11) 1:1 rewrite of [Kode-Agent](https://github.com/chenzzzzy/Kode-Agent) (TypeScript). It is an AI-powered terminal coding assistant supporting 15+ LLM providers, 25+ tools, MCP protocol, and a React + Ink v5 terminal UI (deep 1:1 replication of Kode-Agent's UI layer).

**Current status**: Planning phase — only design docs exist in `docs/`. No source code yet.

## Architecture

Strict 6-layer architecture with one-way dependencies (lower layers never import higher layers):

```
infra ← core ← services ← tools ← app ← entrypoints
                                            ↕ (JSON-RPC over stdio)
                                         src/ui/ (Bun + React + Ink v5)
```

| Layer | Package | Responsibility |
|-------|---------|----------------|
| Infrastructure | `pode_agent/infra/` | Logging, HTTP (httpx), shell exec, filesystem utils, terminal detection |
| Core | `pode_agent/core/` | Config (Pydantic), permissions engine, Tool ABC, tool registry, cost tracker |
| Services | `pode_agent/services/` | AI providers (Anthropic/OpenAI adapters + factory), MCP client, context/auth/plugins |
| Tools | `pode_agent/tools/` | 25+ tool implementations inheriting `core.tools.base.Tool` ABC, organized by category |
| Application | `pode_agent/app/` | REPL engine, session manager (JSONL persistence), orchestrator, print mode |
| UI | `src/ui/` (TypeScript) | React + Ink v5 terminal UI (5 screens, 60+ components, 16 hooks), communicates with Python backend via JSON-RPC over stdio |
| Entrypoints | `pode_agent/entrypoints/` | Thin CLI (Typer), MCP server, ACP server |

Key abstractions:
- **Tool ABC** (`core/tools/base.py`): All tools implement `call()` returning `AsyncGenerator[ToolOutput, None]`, plus `input_schema()`, `is_enabled()`, `is_read_only()`, `needs_permissions()`
- **AIProvider ABC** (`services/ai/base.py`): Providers implement `query()` returning `AsyncGenerator[AIResponse, None]`, with `UnifiedRequestParams` as input
- **PermissionEngine** (`core/permissions/engine.py`): Layered rule evaluation — bypass > denied > approved > plan_mode > tool-specific > default
- **ModelAdapterFactory** (`services/ai/factory.py`): Routes model names to the correct AIProvider

## Design Decisions

- **Pydantic v2** for all data models and JSON Schema generation (replaces Zod)
- **React + Ink v5** for terminal UI (1:1 deep replication of Kode-Agent UI) — TypeScript/Bun frontend communicates with Python backend via JSON-RPC over stdio
- **AsyncGenerator** pattern throughout — tool execution, LLM streaming, event publishing
- **Asyncio-first** — all I/O is async (httpx, `asyncio.create_subprocess_exec`, asyncio.Queue for UI↔session decoupling)
- **Official SDKs** (anthropic, openai) over abstraction layers like litellm/langchain
- **Entry points** (`project.entry-points."pode_agent.tools"`) for auto-discovery of custom tools
- Config stored at `~/.pode/config.json`, format compatible with Kode-Agent

## Development Commands

**All commands must use `uv run` to ensure the `.venv` environment, never the system Python.**

```bash
# Setup (uv required)
uv venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"

# Type check
uv run mypy pode_agent/

# Lint and format
uv run ruff check pode_agent/
uv run ruff format pode_agent/

# Tests
uv run pytest tests/unit/                     # Unit tests only
uv run pytest tests/integration/              # Integration tests
uv run pytest tests/ --cov=pode_agent --cov-report=html  # Full coverage
uv run pytest tests/unit/test_bash_tool.py -v # Single test file
uv run pytest -m "not requires_api_key"       # Skip tests needing real API keys
uv run pytest -m "e2e"                        # E2E tests only

# UI development (React + Ink v5 frontend)
cd src/ui && bun install && bun run dev   # Start Ink UI in dev mode
bun run build                             # Build optimized frontend
bun test                                  # Run frontend component tests
```

## Tooling Configuration

- **Build system**: hatchling (`pyproject.toml`)
- **Type checking**: mypy strict mode, Python 3.11 target
- **Linting/formatting**: ruff, line-length 100, double quotes, rules: E, F, UP, B, SIM, I
- **Testing**: pytest + pytest-asyncio (auto mode), pytest-mock, pytest-cov, respx (HTTP mocking), syrupy (snapshots)
- **Console entry points**: `pode`, `pode-mcp`, `pode-acp`

## Implementation Phases

Detailed in `docs/phases.md`. Phases must be completed in order:

| Phase | Focus | Key Deliverable |
|-------|-------|-----------------|
| 0 | Project skeleton | Runnable CLI shell, config system, Tool ABC |
| 1 | Core features | Permissions, BashTool, file tools, GrepTool |
| 2 | LLM integration | Anthropic/OpenAI adapters, session manager, print mode |
| 3 | Full tool set | All 25+ tools |
| 4 | Terminal UI | React + Ink v5 REPL interface (deep replication of Kode-Agent UI) |
| 5 | MCP & plugins | MCP client/server, skill marketplace, custom commands |
| 6 | Polish | Extra providers, context optimization, PyPI release |

Each phase requires: mypy zero errors, ruff pass, pytest pass, new tests for new features.

## Design Documents

All in `docs/`:
- `architecture.md` — Layer details, component specs, async model, error handling
- `tech-stack.md` — Dependency choices, pyproject.toml reference, dev toolchain
- `modules.md` — Module specifications and public API
- `data-flows.md` — Data flow diagrams and sequence diagrams
- `api-specs.md` — Internal API contracts (Python type signatures)
- `testing-strategy.md` — Test tiers, naming conventions, fixtures, CI config
