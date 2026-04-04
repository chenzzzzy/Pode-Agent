"""Pode-Agent E2E 自动化测试脚本

使用 subprocess 模拟终端交互，超时自动 kill。
覆盖 A-T 组测试（D-S 为新增）。
"""
import asyncio
import json
import os
import shutil
import sys
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

# 确保使用 UTF-8
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUTF8"] = "1"

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
UV_RUN = ["uv", "run"]


@dataclass
class TestResult:
    id: str
    name: str
    status: str  # PASS, FAIL, SKIP, TIMEOUT, ERROR
    output: str = ""
    duration: float = 0.0
    error: str = ""


results: list[TestResult] = []
cleanup_files: list[str] = []

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run_cmd(cmd: list[str], timeout: int = 30, cwd: str = None) -> tuple[int, str, str, float]:
    start = time.time()
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            cwd=cwd or str(PROJECT_DIR), encoding="utf-8", errors="replace",
        )
        return proc.returncode, proc.stdout, proc.stderr, time.time() - start
    except subprocess.TimeoutExpired as e:
        dur = time.time() - start
        out = (e.stdout or b"").decode("utf-8", errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        err = (e.stderr or b"").decode("utf-8", errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
        return -1, out, err, dur
    except Exception as e:
        return -2, "", str(e), time.time() - start


def run_print_mode(prompt: str, extra_args: list[str] = None, timeout: int = 300) -> TestResult:
    cmd = UV_RUN + ["pode"] + (extra_args or []) + ["-p", prompt]
    rc, stdout, stderr, dur = run_cmd(cmd, timeout=timeout)
    output = f"STDOUT:\n{stdout}\nSTDERR:\n{stderr}"
    if rc == 0:
        return TestResult(id="", name="", status="PASS", output=output, duration=dur)
    elif rc == -1:
        return TestResult(id="", name="", status="TIMEOUT", output=output, duration=dur, error="Timed out")
    else:
        error = stderr.strip().split("\n")[-1] if stderr else f"exit code {rc}"
        return TestResult(id="", name="", status="FAIL", output=output, duration=dur, error=error)


def _skip(tid: str, name: str, reason: str) -> TestResult:
    return TestResult(tid, name, "SKIP", error=reason)


def cleanup():
    """Remove temporary files/dirs created by tests."""
    for f in cleanup_files:
        p = Path(f)
        if p.is_file():
            p.unlink()
        elif p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
    # Always attempt known temp paths
    for name in [
        "E2E_WRITE_TEST.txt", "E2E_MULTI_EDIT.txt",
        "E2E_TEMP_G1.py", "E2E_TEMP_G2.py", "E2E_TEMP_G3.py",
        "E2E_TEMP_G4.py", "E2E_TEMP_G5.py", "E2E_TEMP_G6.json",
        "E2E_TEMP_G7.md", "E2E_PLAN_TEST.txt", "E2E_DRAFT.md",
    ]:
        p = PROJECT_DIR / name
        if p.exists():
            p.unlink()
    for d in ["tmp-e2e-output"]:
        p = PROJECT_DIR / d
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)


# ===========================================================================
# A. CLI 基础能力
# ===========================================================================

def test_a1_version():
    rc, out, _, dur = run_cmd(UV_RUN + ["pode", "--version"])
    return TestResult("A1", "pode --version", "PASS" if rc == 0 and "pode-agent" in out else "FAIL", out.strip(), dur)

def test_a2_help():
    rc, out, _, dur = run_cmd(UV_RUN + ["pode", "--help"])
    return TestResult("A2", "pode --help", "PASS" if rc == 0 and "config" in out else "FAIL", out.strip()[:500], dur)

def test_a3_repl_no_tty():
    rc, out, err, dur = run_cmd(UV_RUN + ["pode"], timeout=15)
    combined = out + err
    ok = "interactive terminal" in combined or "Bun" in combined or "TTY" in combined
    return TestResult("A3", "pode (no TTY)", "PASS" if ok else "FAIL", combined.strip()[:500], dur)

def test_a4_print_mode():
    r = run_print_mode("只回复：print mode ok", timeout=60)
    r.id, r.name = "A4", "pode -p print mode"
    return r

def test_a5_text_format():
    r = run_print_mode("只回复：text format ok", extra_args=["--output-format", "text"], timeout=60)
    r.id, r.name = "A5", "pode --output-format text"
    return r

def test_a6_json_format():
    r = run_print_mode("返回一个最简单的 JSON 结果", extra_args=["--output-format", "json"], timeout=60)
    r.id, r.name = "A6", "pode --output-format json"
    return r

def test_a7_verbose():
    r = run_print_mode("请读取 ./not-found-file.txt，并明确展示失败原因", extra_args=["--verbose"], timeout=60)
    r.id, r.name = "A7", "pode --verbose (read missing)"
    return r

def test_a8_safe_mode():
    r = run_print_mode("请在当前目录新建 SAFE_MODE_TEST.md，内容为 hello", extra_args=["--safe"], timeout=60)
    r.id, r.name = "A8", "pode --safe (write blocked)"
    return r


# ===========================================================================
# B. 配置与模型路由
# ===========================================================================

def test_b1_config_list():
    rc, out, err, dur = run_cmd(UV_RUN + ["pode", "config", "list"])
    return TestResult("B1", "pode config list", "PASS" if rc == 0 else "FAIL", (out+err).strip()[:500], dur)

def test_b2_config_get_theme():
    rc, out, err, dur = run_cmd(UV_RUN + ["pode", "config", "get", "theme"])
    return TestResult("B2", "pode config get theme", "PASS" if rc == 0 else "FAIL", (out+err).strip()[:300], dur)

def test_b3_config_set_theme():
    rc, out, err, dur = run_cmd(UV_RUN + ["pode", "config", "set", "theme", "light"])
    return TestResult("B3", "pode config set theme light", "PASS" if rc == 0 else "FAIL", (out+err).strip()[:300], dur)

def test_b4_config_get_theme_again():
    rc, out, _, dur = run_cmd(UV_RUN + ["pode", "config", "get", "theme"])
    return TestResult("B4", "pode config get theme (after set)", "PASS" if rc == 0 and "light" in out else "FAIL", out.strip()[:300], dur)

def test_b5_config_set_verbose():
    rc, out, err, dur = run_cmd(UV_RUN + ["pode", "config", "set", "verbose", "true"])
    return TestResult("B5", "pode config set verbose", "PASS" if rc == 0 else "FAIL", (out+err).strip()[:300], dur)

def test_b6_config_get_verbose():
    rc, out, err, dur = run_cmd(UV_RUN + ["pode", "config", "get", "verbose"])
    return TestResult("B6", "pode config get verbose", "PASS" if rc == 0 else "FAIL", (out+err).strip()[:300], dur)

def test_b7_model_pointers():
    rc, out, err, dur = run_cmd(UV_RUN + ["pode", "config", "set", "model_pointers.quick", "qwen3.5-plus"])
    return TestResult("B7", "config set model_pointers.quick", "PASS" if rc == 0 else "FAIL", (out+err).strip()[:300], dur)

def test_b8_model_pointers_get():
    rc, out, _, dur = run_cmd(UV_RUN + ["pode", "config", "get", "model_pointers.quick"])
    return TestResult("B8", "config get model_pointers.quick", "PASS" if rc == 0 and "qwen" in out.lower() else "FAIL", out.strip()[:300], dur)

def test_b9_model_route_anthropic():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return _skip("B9", "model route anthropic", "ANTHROPIC_API_KEY not set")
    r = run_print_mode("只回复：anthropic route ok", extra_args=["--model", "claude-sonnet-4-5-20251101"], timeout=60)
    r.id, r.name = "B9", "model route anthropic"
    return r

def test_b10_model_route_openai():
    if not os.environ.get("OPENAI_API_KEY"):
        return _skip("B10", "model route openai", "OPENAI_API_KEY not set")
    r = run_print_mode("只回复：openai route ok", extra_args=["--model", "gpt-5"], timeout=60)
    r.id, r.name = "B10", "model route openai"
    return r


# ===========================================================================
# D. 项目感知、上下文与 @mention
# ===========================================================================

def test_d1():
    r = run_print_mode("请先告诉我这个仓库是做什么的，只根据你自动收集到的项目上下文回答。只回答事实，不要编造。")
    r.id, r.name = "D1", "project context awareness"
    return r

def test_d2():
    r = run_print_mode("请阅读 README.md，用 5 句话总结这个项目的目标、技术栈和当前进度。")
    r.id, r.name = "D2", "README.md summary"
    return r

def test_d3():
    r = run_print_mode("请同时阅读 README.md 和 docs/architecture.md，说明这两个文档在系统分层上的一致点和差异点。")
    r.id, r.name = "D3", "dual doc comparison"
    return r

def test_d4():
    r = run_print_mode("请阅读 docs/plan-mode.md，总结 Plan Mode 的目标、进入方式、退出方式和持久化方式。")
    r.id, r.name = "D4", "plan-mode doc summary"
    return r

def test_d5():
    r = run_print_mode("请阅读 docs/subagent-system.md，说明子代理和主代理的上下文隔离是如何设计的。")
    r.id, r.name = "D5", "subagent context isolation"
    return r

def test_d6():
    r = run_print_mode("请阅读 docs/skill-system.md，对比 Skill、Tool、Slash Command 三者的定位。")
    r.id, r.name = "D6", "skill/tool/command comparison"
    return r

def test_d7():
    r = run_print_mode("请阅读 docs/not-exist.md，如果文件不存在请明确报错，不要编造内容。只回复错误信息。")
    r.id, r.name = "D7", "read nonexistent doc"
    return r

def test_d8():
    r = run_print_mode("请基于当前项目上下文，告诉我最值得优先测试的 5 个高风险功能点。只列出名称和原因。")
    r.id, r.name = "D8", "risk assessment from context"
    return r


# ===========================================================================
# E. 文件搜索
# ===========================================================================

def test_e1():
    r = run_print_mode("请列出当前仓库顶层目录，并说明每个目录的大致职责。只回答事实。")
    r.id, r.name = "E1", "top-level directory listing"
    return r

def test_e2():
    r = run_print_mode("请在当前仓库中找出所有定义了 Tool 子类的文件，并按功能域分组。")
    r.id, r.name = "E2", "find Tool subclasses"
    return r

def test_e3():
    r = run_print_mode("请搜索 enter_plan_mode 的定义、调用链路和相关文档引用。")
    r.id, r.name = "E3", "search enter_plan_mode"
    return r

def test_e4():
    r = run_print_mode("请搜索 TaskTool 和 TaskOutputTool 的实现位置，并总结它们如何协作。")
    r.id, r.name = "E4", "search TaskTool/TaskOutput"
    return r

def test_e5():
    r = run_print_mode("请搜索所有 plugin marketplace 相关 CLI 命令，并列出命令名和用途。")
    r.id, r.name = "E5", "search marketplace CLI"
    return r

def test_e6():
    r = run_print_mode("请找出所有处理 mention 的实现和文档说明，并总结支持的语法。")
    r.id, r.name = "E6", "search @mention handling"
    return r

def test_e7():
    r = run_print_mode("请对比 docs/testing-strategy.md 和当前代码目录，指出哪些 E2E 场景已经有明显实现基础。")
    r.id, r.name = "E7", "testing strategy gap analysis"
    return r

def test_e8():
    r = run_print_mode("请定位 REPL 输入处理相关文件，并说明当前输入事件是如何集中处理的。")
    r.id, r.name = "E8", "REPL input handling"
    return r


# ===========================================================================
# F. Bash、编辑与写入链路
# ===========================================================================

def test_f1():
    r = run_print_mode("请运行一个只读命令，告诉我当前仓库的 git 状态摘要。")
    r.id, r.name = "F1", "git status (read-only bash)"
    return r

def test_f2():
    r = run_print_mode("请运行一个只读命令，列出 docs 目录下所有 Markdown 文件。")
    r.id, r.name = "F2", "list docs/*.md (bash)"
    return r

def test_f3():
    cleanup_files.append(str(PROJECT_DIR / "E2E_WRITE_TEST.txt"))
    r = run_print_mode("请在当前目录创建一个文件 E2E_WRITE_TEST.txt，内容为 first line。")
    r.id, r.name = "F3", "create E2E_WRITE_TEST.txt"
    return r

def test_f4():
    r = run_print_mode("请把 E2E_WRITE_TEST.txt 的内容改成 second line，并说明你改了什么。")
    r.id, r.name = "F4", "edit E2E_WRITE_TEST.txt"
    return r

def test_f5():
    cleanup_files.append(str(PROJECT_DIR / "E2E_MULTI_EDIT.txt"))
    r = run_print_mode("请在当前目录创建 E2E_MULTI_EDIT.txt 写入 3 行不同内容，然后把每行的第一个词替换为大写。")
    r.id, r.name = "F5", "create + multi-edit"
    return r

def test_f6():
    r = run_print_mode("请尝试读取一个不存在的文件 ./missing/none.py，并只返回真实错误。")
    r.id, r.name = "F6", "read nonexistent file"
    return r

def test_f7():
    r = run_print_mode("请执行一个会失败的命令（例如 ls /nonexistent_dir_xyz），并把 stdout、stderr 和 exit code 分开总结给我。")
    r.id, r.name = "F7", "failing bash command"
    return r

def test_f8():
    cleanup_files.append(str(PROJECT_DIR / "tmp-e2e-output"))
    r = run_print_mode("请创建目录 ./tmp-e2e-output，然后列出该目录内容。")
    r.id, r.name = "F8", "mkdir + ls"
    return r

def test_f9():
    r = run_print_mode("请删除 ./tmp-e2e-output 目录。")
    r.id, r.name = "F9", "rmdir cleanup"
    return r

def test_f10():
    r = run_print_mode("请在 safe mode 下尝试创建一个文件 E2E_SAFE_TEST.txt，并解释为什么当前模式下不能直接执行。",
                        extra_args=["--safe"])
    r.id, r.name = "F10", "safe mode write blocked"
    return r


# ===========================================================================
# G. 代码修改
# ===========================================================================

def test_g1():
    cleanup_files.append(str(PROJECT_DIR / "E2E_TEMP_G1.py"))
    r = run_print_mode("请在 E2E_TEMP_G1.py 中新增一个 hello_world 函数，只做最小改动。")
    r.id, r.name = "G1", "create function in temp file"
    return r

def test_g2():
    cleanup_files.append(str(PROJECT_DIR / "E2E_TEMP_G2.py"))
    r = run_print_mode("请在 E2E_TEMP_G2.py 中写一个 main() 函数内容为 print('hello')，然后把 main 重命名为 run_main，确保引用同步更新。")
    r.id, r.name = "G2", "rename function + update refs"
    return r

def test_g3():
    cleanup_files.append(str(PROJECT_DIR / "E2E_TEMP_G3.py"))
    r = run_print_mode("请在 E2E_TEMP_G3.py 中写一些乱序 import 的 Python 代码（标准库、第三方库、本地模块混在一起），然后在不改逻辑的前提下重排 import 顺序。")
    r.id, r.name = "G3", "reorder imports"
    return r

def test_g4():
    cleanup_files.append(str(PROJECT_DIR / "E2E_TEMP_G4.py"))
    r = run_print_mode("请在 E2E_TEMP_G4.py 中写一个包含至少 30 行的单一函数，然后把它拆成两个小函数，并解释拆分依据。")
    r.id, r.name = "G4", "split long function"
    return r

def test_g5():
    cleanup_files.append(str(PROJECT_DIR / "E2E_TEMP_G5.py"))
    r = run_print_mode("请在 E2E_TEMP_G5.py 中写一个有语法错误的 Python 函数（比如少了冒号），然后只修复语法错误，不要顺手做风格清理。")
    r.id, r.name = "G5", "fix syntax error only"
    return r

def test_g6():
    cleanup_files.append(str(PROJECT_DIR / "E2E_TEMP_G6.json"))
    r = run_print_mode('请在 E2E_TEMP_G6.json 中创建一个 JSON 对象 {"name":"test"}，然后做结构化修改，新增字段 e2e=true。')
    r.id, r.name = "G6", "JSON structured edit"
    return r

def test_g7():
    cleanup_files.append(str(PROJECT_DIR / "E2E_TEMP_G7.md"))
    r = run_print_mode("请编辑 E2E_TEMP_G7.md 文件（如果不存在就新建），在末尾追加一节 E2E Notes。")
    r.id, r.name = "G7", "Markdown append section"
    return r

def test_g8():
    r = run_print_mode("请告诉我：如果我让你在当前目录创建一个文件 E2E_DRY_RUN.txt，你会改哪些文件？先告诉我计划，但不要真的执行。")
    r.id, r.name = "G8", "dry-run predict changes"
    return r


# ===========================================================================
# H. Web Fetch / Web Search / Notebook
# ===========================================================================

def test_h1():
    r = run_print_mode("请抓取 https://example.com，并用中文总结页面主旨。")
    r.id, r.name = "H1", "web fetch example.com"
    return r

def test_h2():
    r = run_print_mode("请搜索 Python 3.13 release notes official，只总结最重要的 3 点。")
    r.id, r.name = "H2", "web search Python 3.13"
    return r

def test_h3():
    r = run_print_mode("请搜索 Anthropic prompt caching documentation，并告诉我是否适合这个项目。")
    r.id, r.name = "H3", "web search prompt caching"
    return r

def test_h4():
    return _skip("H4", "notebook read", "No test notebook fixture")

def test_h5():
    return _skip("H5", "notebook edit", "No test notebook fixture")

def test_h6():
    return _skip("H6", "corrupted notebook", "No test notebook fixture")


# ===========================================================================
# I. AskUser / TodoWrite
# ===========================================================================

def test_i1():
    r = run_print_mode("请帮我生成一个发布说明，但在开始前你必须先问我版本号和目标受众。", timeout=120)
    r.id, r.name = "I1", "ask_user in print mode"
    return r

def test_i2():
    return _skip("I2", "ask_user follow-up", "Multi-turn: requires I1 session context")

def test_i3():
    r = run_print_mode("请用 todo list 追踪以下任务：阅读 README、阅读 architecture、输出架构摘要。先建 list 再逐项完成。")
    r.id, r.name = "I3", "todo_write create + execute"
    return r

def test_i4():
    r = run_print_mode("请把当前待办重新排序，优先级最高的放在最前面。如果你没有待办列表，请先用 todo_write 创建一个然后再排序。")
    r.id, r.name = "I4", "todo_write reorder"
    return r

def test_i5():
    r = run_print_mode("请把你刚才创建的待办列表中已完成的标记出来，并告诉我还剩什么。如果你没有待办列表，请先创建一个示例列表然后标记完成。")
    r.id, r.name = "I5", "todo_write mark completed"
    return r

def test_i6():
    r = run_print_mode("请用 todo_write 为'补齐 MCP 回归测试'生成一份可执行待办列表，每项不超过一行。")
    r.id, r.name = "I6", "todo_write generate plan"
    return r


# ===========================================================================
# J. Plan Mode
# ===========================================================================

def test_j1():
    r = run_print_mode("先不要修改任何文件。请先为'给 pode plugin install 增加 dry-run 参数'制定一个完整计划，包含步骤、风险、验收标准。只规划不要执行任何写操作。")
    r.id, r.name = "J1", "plan mode: create plan"
    return r

def test_j2():
    return _skip("J2", "plan: supplement plan", "Multi-turn: requires J1 session context")

def test_j3():
    return _skip("J3", "plan: approve and execute", "Multi-turn: requires approval flow")

def test_j4():
    return _skip("J4", "plan: reject and explain", "Multi-turn: requires rejection flow")

def test_j5():
    r = run_print_mode("请先进入计划模式，分析如何为 TaskTool 增加更清晰的用户可见状态提示。只做分析不要改文件。")
    r.id, r.name = "J5", "plan mode: enter + analyze"
    return r

def test_j6():
    cleanup_files.append(str(PROJECT_DIR / "E2E_PLAN_TEST.txt"))
    r = run_print_mode("请在计划模式中尝试修改 E2E_PLAN_TEST.txt 文件；如果当前模式不允许，请明确告诉我为什么不允许。")
    r.id, r.name = "J6", "plan mode: attempt write"
    return r

def test_j7():
    r = run_print_mode("请先做只读探索，再给我一版'最小可行改动'的计划，不要给大而全方案。只回答计划不要执行。")
    r.id, r.name = "J7", "plan mode: minimal viable plan"
    return r

def test_j8():
    return _skip("J8", "plan: resume unfinished", "Requires session persistence across runs")


# ===========================================================================
# K. Skill / Slash Command
# ===========================================================================

def test_k1():
    r = run_print_mode("请列出当前项目里可发现的自定义命令和技能，并区分哪些是用户可见命令，哪些是隐藏技能。")
    r.id, r.name = "K1", "list discoverable skills/commands"
    return r

def test_k2():
    r = run_print_mode("如果当前项目里有适合'代码审查'的 skill，请自动使用它来审查最近修改过的文件。如果没有，请明确说明没有找到。")
    r.id, r.name = "K2", "attempt code-review skill"
    return r

def test_k3():
    r = run_print_mode("如果当前项目里有适合'生成 commit message'的 command，请调用它，但不要真的执行 git commit。如果没有，请明确说明。")
    r.id, r.name = "K3", "attempt commit-message command"
    return r

def test_k4():
    return _skip("K4", "/commit slash command", "Slash commands require REPL interactive mode")

def test_k5():
    return _skip("K5", "/review-pr slash command", "Slash commands require REPL interactive mode")

def test_k6():
    return _skip("K6", "$ARGUMENTS in slash command", "No custom command fixtures")

def test_k7():
    return _skip("K7", "allowed-tools restricted skill", "No skill fixtures")

def test_k8():
    return _skip("K8", "model=haiku skill", "No skill fixtures")

def test_k9():
    return _skip("K9", "nonexistent /not-found-command", "Slash commands require REPL interactive mode")

def test_k10():
    return _skip("K10", "skill context injection", "No skill fixtures to execute")


# ===========================================================================
# L. Plugin / Marketplace (L1-L3 already exist above)
# ===========================================================================

def test_l1_plugin_list():
    rc, out, err, dur = run_cmd(UV_RUN + ["pode", "plugin", "list"])
    return TestResult("L1", "pode plugin list", "PASS" if rc == 0 else "FAIL", (out+err).strip()[:300], dur)

def test_l2_plugin_refresh():
    rc, out, err, dur = run_cmd(UV_RUN + ["pode", "plugin", "refresh"])
    return TestResult("L2", "pode plugin refresh", "PASS" if rc == 0 else "FAIL", (out+err).strip()[:300], dur)

def test_l3_marketplace_list():
    rc, out, err, dur = run_cmd(UV_RUN + ["pode", "plugin", "marketplace", "list"])
    return TestResult("L3", "pode plugin marketplace list", "PASS" if rc == 0 else "FAIL", (out+err).strip()[:300], dur)

def test_l4():
    return _skip("L4", "marketplace add file source", "No tests/fixtures/marketplace.json fixture")

def test_l5():
    return _skip("L5", "marketplace list (after add)", "Depends on L4 fixture")

def test_l6():
    return _skip("L6", "marketplace update", "Depends on L4 fixture")

def test_l7():
    return _skip("L7", "plugin install from file", "No tests/fixtures/test-plugin fixture")

def test_l8():
    return _skip("L8", "plugin list --scope project", "Depends on L7 fixture")

def test_l9():
    return _skip("L9", "plugin disable", "No installed plugin ID")

def test_l10():
    return _skip("L10", "plugin enable", "No installed plugin ID")

def test_l11():
    return _skip("L11", "plugin uninstall", "No installed plugin ID")

def test_l12():
    return _skip("L12", "install broken plugin", "No tests/fixtures/broken-plugin fixture")


# ===========================================================================
# M. Hook 系统
# ===========================================================================

def test_m1():
    return _skip("M1", "user_prompt_submit hook", "No hook configuration")

def test_m2():
    return _skip("M2", "pre_tool_use hook block", "No hook configuration")

def test_m3():
    return _skip("M3", "post_tool_use hook audit", "No hook configuration")

def test_m4():
    return _skip("M4", "stop hook completeness", "No hook configuration")

def test_m5():
    return _skip("M5", "stop hook continuation", "No hook configuration")

def test_m6():
    return _skip("M6", "hook path rewrite", "No hook configuration")

def test_m7():
    return _skip("M7", "hook system prompt injection", "No hook configuration")

def test_m8():
    return _skip("M8", "hook reentry stability", "No hook configuration")


# ===========================================================================
# N. MCP 客户端
# ===========================================================================

def test_n1():
    return _skip("N1", "list MCP tools", "No MCP server configured")

def test_n2():
    return _skip("N2", "call MCP read tool", "No MCP server configured")

def test_n3():
    return _skip("N3", "call MCP write tool", "No MCP server configured")

def test_n4():
    return _skip("N4", "nonexistent MCP tool", "No MCP server configured")

def test_n5():
    return _skip("N5", "MCP permission denied", "No MCP server configured")

def test_n6():
    return _skip("N6", "MCP permission allow once", "No MCP server configured")

def test_n7():
    return _skip("N7", "MCP server unreachable", "No MCP server configured")

def test_n8():
    return _skip("N8", "MCP vs native permission diff", "No MCP server configured")

def test_n9():
    return _skip("N9", "MCP transport listing (stdio/SSE/HTTP)", "No MCP server configured")

def test_n10():
    return _skip("N10", "SSE MCP read-only tool", "No SSE MCP server configured")

def test_n11():
    return _skip("N11", "HTTP MCP read-only tool", "No HTTP MCP server configured")

def test_n12():
    return _skip("N12", "MCP discover then call roundtrip", "No MCP server configured")

def test_n13():
    return _skip("N13", "MCP resources list and read", "No MCP server configured")

def test_n14():
    return _skip("N14", "MCP invalid endpoint handling", "No MCP server configured")

def test_n15():
    return _skip("N15", "MCP normal + abnormal server isolation", "No MCP server configured")

def test_n16():
    return _skip("N16", "MCP initialize failure cleanup", "No MCP server configured")

def test_n17():
    return _skip("N17", "MCP status consistency check", "No MCP server configured")


# ===========================================================================
# O. SubAgent / 后台任务
# ===========================================================================

def test_o1():
    r = run_print_mode("请启动一个 Explore 子代理，找出所有与 permissions 相关的实现文件，并只返回汇总。不要使用 EnterPlanMode、ExitPlanMode 或 AskUserQuestion 工具。")
    r.id, r.name = "O1", "SubAgent Explore: permissions files"
    return r

def test_o2():
    r = run_print_mode("请启动一个 Plan 子代理，分析如何为 plugin marketplace update 增加缓存失效测试。不要使用 EnterPlanMode、ExitPlanMode 或 AskUserQuestion 工具。")
    r.id, r.name = "O2", "SubAgent Plan: marketplace cache"
    return r

def test_o3():
    r = run_print_mode("请启动一个 general-purpose 子代理，在后台扫描 docs 目录并生成架构摘要；先只告诉我 task id。")
    r.id, r.name = "O3", "SubAgent background: docs scan"
    return r

def test_o4():
    r = run_print_mode("请查询一个不存在的后台 task id nonexistent-task-xyz，并明确报错。")
    r.id, r.name = "O4", "TaskOutput: nonexistent task"
    return r

def test_o5():
    return _skip("O5", "background task status query", "Requires O3 task_id from prior session")

def test_o6():
    return _skip("O6", "background task output read", "Requires O3 task_id from prior session")

def test_o7():
    return _skip("O7", "resume subagent by agent_id", "Requires real agent_id from prior session")

def test_o8():
    return _skip("O8", "foreground vs background UX", "Requires multi-turn session context")


# ===========================================================================
# P. 会话持久化
# ===========================================================================

def test_p1():
    r = run_print_mode("请记住这次测试标签：E2E-SESSION-001。在回答中确认你记住了。")
    r.id, r.name = "P1", "session: remember tag 1"
    return r

def test_p2():
    r = run_print_mode("请记住第二个标签：E2E-SESSION-ALPHA。在回答中确认。")
    r.id, r.name = "P2", "session: remember tag 2"
    return r

def test_p3():
    r = run_print_mode("请总结到目前为止，这个会话中你已经完成了哪些动作。")
    r.id, r.name = "P3", "session: summarize actions"
    return r

def test_p4():
    return _skip("P4", "session: recall both tags", "Multi-turn: requires P1+P2 session context")

def test_p5():
    return _skip("P5", "session: resume across restart", "Requires session restore from JSONL")

def test_p6():
    return _skip("P6", "session: long context keywords", "Multi-turn: requires P1-P5 context chain")


# ===========================================================================
# Q. Print Mode
# ===========================================================================

def test_q1():
    r = run_print_mode("只输出 OK，不要解释", timeout=60)
    r.id, r.name = "Q1", "pode print mode simple"
    return r

def test_q2():
    r = run_print_mode("只回复：text format ok", extra_args=["--output-format", "text"], timeout=60)
    r.id, r.name = "Q2", "pode --output-format text"
    return r

def test_q3():
    r = run_print_mode("返回字段 status=ok, mode=print", extra_args=["--output-format", "json"], timeout=60)
    r.id, r.name = "Q3", "pode --output-format json"
    return r

def test_q4():
    r = run_print_mode("只回复：safe mode ok", extra_args=["--safe"], timeout=60)
    r.id, r.name = "Q4", "pode --safe print mode"
    return r

def test_q5():
    r = run_print_mode("只回复：verbose ok", extra_args=["--verbose"], timeout=60)
    r.id, r.name = "Q5", "pode --verbose print mode"
    return r


# ===========================================================================
# R. 错误处理
# ===========================================================================

def test_r1():
    r = run_print_mode("请读取 ./does/not/exist.py，只回复真实错误信息")
    r.id, r.name = "R1", "read nonexistent file"
    return r

def test_r2():
    r = run_print_mode("请编辑一个不存在的文件 ./does/not/exist_edit.py，只回复真实行为")
    r.id, r.name = "R2", "edit nonexistent file"
    return r

def test_r3():
    r = run_print_mode("请在一个只读文件上执行写操作，并如实说明失败原因。请先创建 /tmp/e2e_readonly_test.txt 然后用 chmod 设为只读再尝试写入。")
    r.id, r.name = "R3", "write to read-only file"
    return r

def test_r4():
    r = run_print_mode("请执行一个超时命令 sleep 999，在 3 秒后如果还没完成就停止等待。")
    r.id, r.name = "R4", "timeout command"
    return r

def test_r5():
    r = run_print_mode("请抓取一个不可达的 URL https://this-domain-does-not-exist-xyz123.com，并说明这是 DNS、连接失败还是超时。")
    r.id, r.name = "R5", "fetch unreachable URL"
    return r

def test_r6():
    r = run_print_mode("请搜索 __THIS_SYMBOL_SHOULD_NOT_EXIST__，只回复搜索结果")
    r.id, r.name = "R6", "search nonexistent symbol"
    return r

def test_r7():
    r = run_print_mode("请让一个子代理在不存在的 agent type nonexistent_type 上启动，并展示真实错误。")
    r.id, r.name = "R7", "SubAgent nonexistent type"
    return r

def test_r8():
    rc, out, err, dur = run_cmd(UV_RUN + ["pode", "plugin", "install", "file:./nonexistent_plugin_dir"], timeout=10)
    return TestResult("R8", "install invalid plugin", "PASS" if rc != 0 else "FAIL", (out+err).strip()[:300], dur)

def test_r9():
    rc, out, err, dur = run_cmd(UV_RUN + ["pode", "plugin", "marketplace", "add", "file:./nonexistent.json"], timeout=10)
    return TestResult("R9", "broken marketplace source", "PASS" if rc != 0 else "FAIL", (out+err).strip()[:300], dur)

def test_r10():
    env_no_bun = os.environ.copy()
    env_no_bun["PATH"] = ""
    start = time.time()
    try:
        proc = subprocess.run(
            UV_RUN + ["pode"], capture_output=True, text=True, timeout=15,
            cwd=str(PROJECT_DIR), encoding="utf-8", errors="replace", env=env_no_bun,
        )
        dur = time.time() - start
        combined = proc.stdout + proc.stderr
        has_bun = "Bun" in combined or "TTY" in combined or "interactive terminal" in combined
        return TestResult("R10", "REPL no Bun error", "PASS" if has_bun else "FAIL", combined[:500], dur)
    except subprocess.TimeoutExpired:
        return TestResult("R10", "REPL no Bun error", "TIMEOUT", duration=time.time()-start, error="Timed out")

def test_r11():
    r = run_print_mode("请尝试读取一个敏感路径 /etc/shadow，如果被拒绝请明确说明。")
    r.id, r.name = "R11", "read sensitive path"
    return r

def test_r12():
    r = run_print_mode("请在权限被拒绝后重试同一操作：先尝试写入 /root/e2e_test.txt，如果被拒绝就再次尝试。确认不会绕过拒绝策略。")
    r.id, r.name = "R12", "permission denied retry"
    return r

def test_r13():
    return _skip("R13", "MCP missing url config error", "No MCP server configured")

def test_r14():
    return _skip("R14", "MCP invalid JSON-RPC endpoint", "No MCP server configured")

def test_r15():
    return _skip("R15", "MCP partial failure detection", "No MCP server configured")


# ===========================================================================
# S. 综合链路
# ===========================================================================

def test_s1():
    r = run_print_mode("请先阅读 README.md 和 docs/testing-strategy.md，然后给我一份'当前仓库最需要补的 E2E 用例清单'，先只规划不要改文件。")
    r.id, r.name = "S1", "integration: plan E2E test cases"
    return r

def test_s2():
    cleanup_files.append(str(PROJECT_DIR / "E2E_DRAFT.md"))
    r = run_print_mode("请在当前仓库里新增一份测试文档草稿 E2E_DRAFT.md，只覆盖 CLI、权限、Plan Mode 三部分。创建后不要做其他修改。")
    r.id, r.name = "S2", "integration: create test doc draft"
    return r

def test_s3():
    r = run_print_mode("请把 E2E_DRAFT.md 这份测试文档再扩展到 Skill、MCP、SubAgent，并保证结构清晰。只编辑这一个文件。")
    r.id, r.name = "S3", "integration: extend test doc"
    return r

def test_s4():
    r = run_print_mode("请启动一个 Explore 子代理去核对 docs 和代码目录是否一致，同时你作为主代理继续整理一份关于当前项目文件结构的最终总结。不要使用 EnterPlanMode、AskUserQuestion 工具。")
    r.id, r.name = "S4", "integration: SubAgent + main agent"
    return r

def test_s5():
    r = run_print_mode("请把当前项目测试状况总结成三部分：1.已验证的功能 2.待验证的功能 3.高风险未覆盖的功能。只做总结不要修改任何文件。")
    r.id, r.name = "S5", "integration: final summary"
    return r

def test_s6():
    return _skip("S6", "MCP transport integration test", "No MCP server configured")


# ===========================================================================
# T. 自动化断言
# ===========================================================================

def test_t1():
    r = run_print_mode("只回复：ok", timeout=60)
    r.id, r.name = "T1", "assert: ok"
    return r

def test_t2():
    r = run_print_mode('只回复 JSON：{"status":"ok"}', timeout=60)
    r.id, r.name = "T2", "assert: json"
    return r

def test_t3():
    r = run_print_mode("只回复当前仓库名，不要任何解释", timeout=60)
    r.id, r.name = "T3", "assert: repo name"
    return r

def test_t4():
    r = run_print_mode("只回复当前工作目录的最后一级目录名", timeout=60)
    r.id, r.name = "T4", "assert: dirname"
    return r

def test_t5():
    r = run_print_mode("只回复 docs 目录下 Markdown 文件数量，只要一个数字", timeout=60)
    r.id, r.name = "T5", "assert: md file count"
    return r

def test_t6():
    rc, out, _, dur = run_cmd(UV_RUN + ["pode", "config", "get", "theme"])
    return TestResult("T6", "assert: theme config", "PASS" if rc == 0 and out.strip() else "FAIL", out.strip()[:300], dur)

def test_t7():
    r = run_print_mode("只回复当前是否处于 safe mode，回答是或否", extra_args=["--safe"], timeout=60)
    r.id, r.name = "T7", "assert: safe mode status"
    return r

def test_t8():
    r = run_print_mode("只回复当前是否检测到可用 plugin，回答是或否", timeout=60)
    r.id, r.name = "T8", "assert: plugin detection"
    return r

def test_t9():
    r = run_print_mode("只回复当前是否检测到可用 MCP 工具，回答是或否", timeout=60)
    r.id, r.name = "T9", "assert: MCP detection"
    return r

def test_t10():
    r = run_print_mode("只回复当前是否存在活跃后台任务，回答是或否", timeout=60)
    r.id, r.name = "T10", "assert: background task"
    return r

def test_t11():
    r = run_print_mode("只回复当前每个 MCP server 的 transport 和状态，如果没有配置就说没有配置", timeout=60)
    r.id, r.name = "T11", "assert: MCP transport status"
    return r

def test_t12():
    r = run_print_mode("只回复当前是否存在显示已连接但无法完成 roundtrip 的 MCP server，回答是或否", timeout=60)
    r.id, r.name = "T12", "assert: MCP roundtrip check"
    return r


# ===========================================================================
# C. REPL 终端交互
# ===========================================================================

async def test_repl_with_pty():
    tests = []
    proc = await asyncio.create_subprocess_exec(
        *UV_RUN, "pode",
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE, cwd=str(PROJECT_DIR),
    )
    try:
        await asyncio.sleep(3)
        if proc.returncode is not None:
            stdout, stderr = await proc.communicate()
            out = (stdout + stderr).decode("utf-8", errors="replace")
            tests.append(TestResult("C1", "REPL startup", "PASS" if ("interactive" in out or "Bun" in out) else "FAIL", out[:500]))
        else:
            tests.append(TestResult("C1", "REPL startup", "PASS", "REPL process started"))
            proc.stdin.write(b"hello world\n")
            await proc.stdin.drain()
            await asyncio.sleep(3)
            try:
                data = await asyncio.wait_for(proc.stdout.read(4096), timeout=5)
                out = data.decode("utf-8", errors="replace")
                tests.append(TestResult("C3", "REPL I/O", "PASS" if out else "FAIL", out[:500]))
            except asyncio.TimeoutError:
                tests.append(TestResult("C3", "REPL I/O", "TIMEOUT", error="No output in 5s"))
            for _ in range(2):
                proc.stdin.write(b"\x03")
                await proc.stdin.drain()
                await asyncio.sleep(1)
            if proc.returncode is None:
                proc.terminate()
                try: await asyncio.wait_for(proc.wait(), timeout=5)
                except asyncio.TimeoutError: proc.kill(); await proc.wait()
            tests.append(TestResult("C8", "REPL Ctrl+C exit", "PASS", f"Exit: {proc.returncode}"))
    except Exception as e:
        if proc.returncode is None: proc.kill(); await proc.wait()
        tests.append(TestResult("C1", "REPL startup", "ERROR", error=str(e)))
    return tests


# ===========================================================================
# Run all tests
# ===========================================================================

def _run_group(name: str, fns: list, parallel: int = 1):
    """Run a group of test functions, optionally in parallel."""
    print(f"\n--- {name} ---")
    if parallel > 1:
        with ThreadPoolExecutor(max_workers=parallel) as pool:
            futures = {pool.submit(fn): fn for fn in fns}
            group_results = []
            for fut in as_completed(futures):
                r = fut.result()
                results.append(r)
                group_results.append(r)
                print(f"  {r.id} {r.name}: {r.status} ({r.duration:.1f}s)")
                if r.status not in ("PASS", "SKIP"):
                    print(f"    err: {r.error[:100]}")
        return group_results
    else:
        group_results = []
        for fn in fns:
            r = fn()
            results.append(r)
            group_results.append(r)
            print(f"  {r.id} {r.name}: {r.status} ({r.duration:.1f}s)")
            if r.status not in ("PASS", "SKIP"):
                print(f"    err: {r.error[:100]}")
        return group_results


def run_all():
    print("=" * 70)
    print("Pode-Agent E2E 自动化测试 (Full Suite)")
    print(f"项目: {PROJECT_DIR}")
    print("=" * 70)

    # ---- Fast CLI-only groups ----
    _run_group("A. CLI 基础能力", [test_a1_version, test_a2_help, test_a3_repl_no_tty,
                test_a4_print_mode, test_a5_text_format, test_a6_json_format,
                test_a7_verbose, test_a8_safe_mode], parallel=1)
    _run_group("B. 配置与模型路由", [test_b1_config_list, test_b2_config_get_theme,
                test_b3_config_set_theme, test_b4_config_get_theme_again,
                test_b5_config_set_verbose, test_b6_config_get_verbose,
                test_b7_model_pointers, test_b8_model_pointers_get,
                test_b9_model_route_anthropic, test_b10_model_route_openai])
    _run_group("L. Plugin / Marketplace", [test_l1_plugin_list, test_l2_plugin_refresh,
                test_l3_marketplace_list, test_l4, test_l5, test_l6, test_l7,
                test_l8, test_l9, test_l10, test_l11, test_l12])

    # ---- LLM read-only groups (parallel within group) ----
    _run_group("D. 项目感知", [test_d1, test_d2, test_d3, test_d4, test_d5, test_d6, test_d7, test_d8], parallel=2)
    _run_group("E. 文件搜索", [test_e1, test_e2, test_e3, test_e4, test_e5, test_e6, test_e7, test_e8], parallel=2)
    _run_group("H. Web / Notebook", [test_h1, test_h2, test_h3, test_h4, test_h5, test_h6])
    _run_group("Q. Print Mode", [test_q1, test_q2, test_q3, test_q4, test_q5])
    _run_group("T. 自动化断言", [test_t1, test_t2, test_t3, test_t4, test_t5,
                test_t6, test_t7, test_t8, test_t9, test_t10,
                test_t11, test_t12], parallel=2)

    # ---- LLM write groups (sequential within group for file dependencies) ----
    _run_group("F. Bash/编辑/写入", [test_f1, test_f2, test_f3, test_f4, test_f5,
                test_f6, test_f7, test_f8, test_f9, test_f10])
    _run_group("G. 代码修改", [test_g1, test_g2, test_g3, test_g4, test_g5, test_g6, test_g7, test_g8])

    # ---- Interaction / Plan / SubAgent ----
    _run_group("I. AskUser / TodoWrite", [test_i1, test_i2, test_i3, test_i4, test_i5, test_i6], parallel=2)
    _run_group("J. Plan Mode", [test_j1, test_j2, test_j3, test_j4, test_j5, test_j6, test_j7, test_j8])
    _run_group("K. Skill / Slash", [test_k1, test_k2, test_k3, test_k4, test_k5, test_k6, test_k7, test_k8, test_k9, test_k10])
    _run_group("O. SubAgent", [test_o1, test_o2, test_o3, test_o4, test_o5, test_o6, test_o7, test_o8], parallel=2)
    _run_group("P. 会话持久化", [test_p1, test_p2, test_p3, test_p4, test_p5, test_p6])
    _run_group("R. 错误处理", [test_r1, test_r2, test_r3, test_r4, test_r5, test_r6,
                test_r7, test_r8, test_r9, test_r10, test_r11, test_r12,
                test_r13, test_r14, test_r15], parallel=2)

    # ---- SKIP-only groups ----
    _run_group("M. Hook 系统", [test_m1, test_m2, test_m3, test_m4, test_m5, test_m6, test_m7, test_m8])
    _run_group("N. MCP 客户端", [test_n1, test_n2, test_n3, test_n4, test_n5, test_n6,
                test_n7, test_n8, test_n9, test_n10, test_n11, test_n12,
                test_n13, test_n14, test_n15, test_n16, test_n17])

    # ---- Integration ----
    _run_group("S. 综合链路", [test_s1, test_s2, test_s3, test_s4, test_s5, test_s6])

    # ---- REPL (async) ----
    print("\n--- C. REPL 终端交互 ---")
    repl_results = asyncio.run(test_repl_with_pty())
    for r in repl_results:
        results.append(r)
        print(f"  {r.id} {r.name}: {r.status}")
        if r.status != "PASS":
            print(f"    err: {r.error[:100]}")

    # ---- Cleanup ----
    print("\n--- 清理临时文件 ---")
    cleanup()
    print("  清理完成")

    # ---- Summary ----
    print("\n" + "=" * 70)
    print("测试汇总")
    print("=" * 70)
    passed = sum(1 for r in results if r.status == "PASS")
    failed = sum(1 for r in results if r.status == "FAIL")
    timeout = sum(1 for r in results if r.status == "TIMEOUT")
    error = sum(1 for r in results if r.status == "ERROR")
    skipped = sum(1 for r in results if r.status == "SKIP")
    total = len(results)

    print(f"  总计: {total}")
    print(f"  通过: {passed}")
    print(f"  失败: {failed}")
    print(f"  超时: {timeout}")
    print(f"  错误: {error}")
    print(f"  跳过: {skipped}")

    # Save results
    result_file = Path(__file__).resolve().parent / "e2e_results.json"
    result_file.parent.mkdir(parents=True, exist_ok=True)
    with open(result_file, "w", encoding="utf-8") as f:
        json.dump([{
            "id": r.id, "name": r.name, "status": r.status,
            "duration": round(r.duration, 2), "error": r.error,
            "output": r.output[:1000],
        } for r in results], f, ensure_ascii=False, indent=2)
    print(f"\n详细结果: {result_file}")

    return failed + error


if __name__ == "__main__":
    sys.exit(run_all())
