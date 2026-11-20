"""
Delphi compiler plugin

Phase 1: delegate to existing compiler_service / dproj_parser and other modules, with zero rewrites.
Phase 2: tool ownership declaration (get_owned_tool_names).
Phase 3: handlers extracted to handlers.py, get_tools() returns complete ToolDefinitions.
"""

from pathlib import Path
from typing import List, Dict, Any, Optional

from ..base import CompilerPlugin, PluginInfo, ToolDefinition


class DelphiPlugin(CompilerPlugin):
    """Delphi compiler plugin

    Tool registration: declare Delphi-specific tool names → route to existing handlers in server.py.
    Compilation: delegate to compiler_service (MSBuild / DCC).
    Parsing: delegate to dproj_parser.
    """

    @property
    def info(self) -> PluginInfo:
        return PluginInfo(
            name="delphi",
            display_name="Delphi",
            version="1.0.0",
            description="Embarcadero Delphi compiler support (MSBuild/DCC)",
            supported_extensions=[".dproj", ".dpr", ".dpk"],
        )

    # ── detect ──

    async def detect(self) -> List[Dict[str, Any]]:
        """Detect installed Delphi compilers"""
        from ...services.config_manager import ConfigManager
        cm = ConfigManager()
        return cm._detect_delphi_from_registry()

    # ── compile ──

    async def compile(self, project_path: str, options: Dict[str, Any]) -> Dict[str, Any]:
        """Compile a Delphi project (delegated to compiler_service)"""
        from ...services.compiler_service import CompilerService
        from ...services.config_manager import ConfigManager

        cm = ConfigManager()
        cs = CompilerService(cm)

        result = await cs.compile_project(
            project_path=project_path,
            target_platform=options.get("target_platform", "win32"),
            build_configuration=options.get("build_configuration", "Debug"),
            extra_args=options.get("extra_args"),
            output_path=options.get("output_path"),
            compiler_version=options.get("compiler_version"),
            conditional_defines=options.get("conditional_defines"),
            unit_search_paths=options.get("unit_search_paths"),
            resource_search_paths=options.get("resource_search_paths"),
            optimize=options.get("optimize"),
            debug=options.get("debug"),
            warning_level=options.get("warning_level", 2),
            disabled_warnings=options.get("disabled_warnings", set()),
            output_type=options.get("output_type", "gui"),
        )
        return result.to_dict()

    # ── parse_project ──

    def parse_project(self, project_path: str) -> Optional[Dict[str, Any]]:
        """Parse a Delphi project file (.dproj)"""
        if not project_path.endswith(('.dproj', '.dpr', '.dpk')):
            return None

        from ...utils.dproj_parser import DprojParser
        parser = DprojParser(project_path)
        if not parser.parse():
            return None

        info = parser.get_project_info()
        return {
            "name": info.get("name", ""),
            "platform": "delphi",
            "file_path": project_path,
            "info": info,
        }

    # ── Coding rules ──
    # Phase 1: get_coding_rules is still implemented in a server.py closure;
    # the interface definition is kept here for Phase 2 migration.

    def get_coding_rules(self, section: str = None) -> str:
        """Get Delphi coding rules

        Phase 2 TODO: migrate the get_coding_rules implementation here.
        """
        return ""  # Phase 2: implement complete logic

    # ── Tool ownership declaration (Phase 2) + handler extraction (Phase 3) ──

    def get_owned_tool_names(self) -> List[str]:
        """List of MCP tool names owned by the Delphi plugin"""
        return [
            "delphi_project",
            "delphi_file",
            "delphi_kb",
            "manage_component",
            "get_coding_rules",
            "package",
            "check_environment",
            "delphi_rtti",
            "automate_delphi",
        ]

    def get_tools(self) -> List[ToolDefinition]:
        """Return MCP tools registered by the Delphi plugin (Phase 3: complete ToolDefinitions)"""
        from .handlers import DELPHI_HANDLERS
        return [
            ToolDefinition(
                name=name,
                description=self._TOOL_DESCRIPTIONS.get(name, f"Delphi tool: {name}"),
                input_schema=self._TOOL_SCHEMAS.get(name, {"type": "object", "properties": {}}),
                handler=handler,
            )
            for name, handler in DELPHI_HANDLERS.items()
            if name != "file_tool"  # file_tool is a compatibility alias for delphi_file and is not registered separately
        ]

    # Tool descriptions and schema metadata
    _TOOL_DESCRIPTIONS = {
        "delphi_project": "Delphi project full lifecycle management: compile/configure/audit/deploy",
        "delphi_file": "Unified entry point for Delphi files: read/write/search/grep/replace/insert/delete/backup",
        "delphi_kb": "Knowledge base search/management",
        "manage_component": "DFM component add/delete/modify/generate",
        "get_coding_rules": "Coding rules retrieval tool — get Delphi or Lazarus/FPC conventions before writing/compile/review/automation",
        "package": "Component package compile/install/list",
        "check_environment": "Environment check/RAD Studio compiler detect/check/install/dcc32/dcc64",
        "delphi_rtti": "RTTI discovery/invocation",
        "automate_delphi": "Delphi automated testing",
    }

    _TOOL_SCHEMAS: Dict[str, Dict[str, Any]] = {}  # schema provided by server.py list_tools

