"""
Compiler plugin base class

Defines the interfaces that all compiler plugins must implement.

Core capability layers:
  - Must implement: compile, detect, parse_project
  - Optional overrides: file_handling, kb_search, project_management
    Core capabilities not overridden by a plugin are provided by default by the MCP Server's core services.

Tool ownership:
  - Each plugin declares the MCP tool names it owns via owned_tools
  - Tools not owned by a plugin are provided by core services
  - handler references are injected into the registry by server.py in Phase 2
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Any, Callable


@dataclass
class PluginInfo:
    """Plugin metadata"""
    name: str
    display_name: str
    version: str = "1.0.0"
    description: str = ""
    supported_extensions: List[str] = field(default_factory=list)


@dataclass
class ToolDefinition:
    """MCP tool declaration (registered by the plugin to the core)"""
    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Optional[Callable] = None  # async def handler(arguments: dict) -> Any


class CompilerPlugin(ABC):
    """Compiler plugin base class — implement one per language/compiler.

    Phase 1: registration skeleton, handlers managed by server.py.
    Phase 2: plugins declare tool ownership, handlers injected by registry.
    Phase 3+: handlers extracted into plugin modules.
    """

    # ── Must implement ──

    @property
    @abstractmethod
    def info(self) -> PluginInfo:
        """Plugin metadata"""
        ...

    def is_available(self) -> bool:
        """Check whether the development tools corresponding to this plugin are installed in the current environment.

        When False is returned, registry.register() will skip tool registration for this plugin
        to avoid exposing unavailable tools to MCP clients.
        Subclasses can override this method to implement custom detection logic.
        """
        return True

    @abstractmethod
    async def detect(self) -> List[Dict[str, Any]]:
        """Detect instances of this compiler installed on the local machine"""
        ...

    @abstractmethod
    async def compile(self, project_path: str, options: Dict[str, Any]) -> Dict[str, Any]:
        """Execute compilation"""
        ...

    @abstractmethod
    def parse_project(self, project_path: str) -> Optional[Dict[str, Any]]:
        """Parse project files and extract source file lists, dependencies, configuration, etc."""
        ...

    # ── Tool ownership declaration ──

    def get_owned_tool_names(self) -> List[str]:
        """Return the list of MCP tool names owned by this plugin.

        Phase 2: only declare names; handlers are injected into the registry by server.py.
        Phase 3: after handlers are migrated to plugin modules, return complete ToolDefinitions.
        """
        return []

    # ── Optional override: coding rules ──

    def get_coding_rules(self, section: str = None) -> str:
        """Return language coding rules (optional override)"""
        return ""

    # ── Tool registration ──

    def get_tools(self) -> List[ToolDefinition]:
        """Return the list of MCP tools registered by the plugin.

        Phase 2: return an empty list; handlers are managed by the registry.
        Phase 3: return a complete list of ToolDefinitions.
        """
        return []

