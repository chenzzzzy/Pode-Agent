"""Configuration public API.

Re-exports the primary config functions for convenient access::

    from pode_agent.core.config import get_global_config, save_global_config

Reference: docs/api-specs.md — Config API
"""

from pode_agent.core.config.loader import (
    ConfigError,
    get_config_for_cli,
    get_current_project_config,
    get_global_config,
    list_config_for_cli,
    save_current_project_config,
    save_global_config,
    set_config_for_cli,
)
from pode_agent.core.config.schema import (
    AccountInfo,
    CustomApiKeyResponses,
    GlobalConfig,
    McpServerConfig,
    ModelPointers,
    ModelProfile,
    ProjectConfig,
    ProviderType,
)

__all__ = [
    "ConfigError",
    "AccountInfo",
    "CustomApiKeyResponses",
    "GlobalConfig",
    "McpServerConfig",
    "ModelPointers",
    "ModelProfile",
    "ProjectConfig",
    "ProviderType",
    "get_config_for_cli",
    "get_current_project_config",
    "get_global_config",
    "list_config_for_cli",
    "save_current_project_config",
    "save_global_config",
    "set_config_for_cli",
]
