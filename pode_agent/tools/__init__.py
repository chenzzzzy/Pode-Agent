"""Tools package — central registry for all built-in tools.

``get_all_tools()`` is the single source of truth for the built-in
tool inventory.  As new tools are added during development, they are
registered here.

Reference: docs/tools-system.md — Tool Storage
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pode_agent.core.tools.base import Tool


def get_all_tools() -> list[Tool]:
    """Return instances of all built-in tools.

    Phase 2 delivers 7 core tools.  Phase 3 adds 18 more to reach 25+.
    Tools are imported lazily inside this function to avoid circular
    imports and keep startup fast.
    """
    import importlib

    # Agent
    from pode_agent.tools.agent.ls import LsTool

    # Filesystem
    from pode_agent.tools.filesystem.file_edit import FileEditTool
    from pode_agent.tools.filesystem.file_read import FileReadTool
    from pode_agent.tools.filesystem.file_write import FileWriteTool
    from pode_agent.tools.filesystem.glob import GlobTool

    # Search
    from pode_agent.tools.search.grep import GrepTool

    # System
    from pode_agent.tools.system.bash import BashTool

    all_tools: list[Tool] = [
        # System
        BashTool(),
        # Filesystem
        FileReadTool(),
        FileWriteTool(),
        FileEditTool(),
        GlobTool(),
        # Search
        GrepTool(),
        # Agent
        LsTool(),
    ]

    # Phase 3 additions — conditionally imported as they are implemented
    _phase3_specs = [
        # Filesystem
        ("pode_agent.tools.filesystem.multi_edit", "MultiEditTool"),
        ("pode_agent.tools.filesystem.notebook_read", "NotebookReadTool"),
        ("pode_agent.tools.filesystem.notebook_edit", "NotebookEditTool"),
        # Network
        ("pode_agent.tools.network.web_fetch", "WebFetchTool"),
        ("pode_agent.tools.network.web_search", "WebSearchTool"),
        # Search
        ("pode_agent.tools.search.lsp", "LspTool"),
        # System
        ("pode_agent.tools.system.kill_shell", "KillShellTool"),
        ("pode_agent.tools.system.task_output", "TaskOutputTool"),
        # Interaction
        ("pode_agent.tools.interaction.ask_user", "AskUserQuestionTool"),
        ("pode_agent.tools.interaction.todo_write", "TodoWriteTool"),
        ("pode_agent.tools.interaction.slash_command", "SlashCommandTool"),
        # AI
        ("pode_agent.tools.ai.ask_expert", "AskExpertModelTool"),
        ("pode_agent.tools.ai.skill", "SkillTool"),
        # Agent
        ("pode_agent.tools.agent.plan_mode", "EnterPlanModeTool"),
        ("pode_agent.tools.agent.plan_mode", "ExitPlanModeTool"),
        ("pode_agent.tools.agent.task", "TaskTool"),
    ]

    for module_path, class_name in _phase3_specs:
        try:
            mod = importlib.import_module(module_path)
            tool_cls = getattr(mod, class_name)
            all_tools.append(tool_cls())
        except (ImportError, AttributeError):
            pass

    return all_tools
