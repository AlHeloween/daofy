"""
Lazarus/FPC compiler plugin

Phase 1: Delegate to the existing compiler_service.compile_with_lazbuild / lpi_parser,
         do not duplicate any business logic.
Phase 2: Tool ownership declaration (get_owned_tool_names).
Phase 5: Handler extraction to handlers.py, get_tools() returns the complete ToolDefinition.
"""

from pathlib import Path
from typing import List, Dict, Any, Optional

from ..base import CompilerPlugin, PluginInfo, ToolDefinition
from ...utils.logger import get_logger

logger = get_logger(__name__)


class LazarusPlugin(CompilerPlugin):
    """Lazarus/Free Pascal compiler plugin"""

    @property
    def info(self) -> PluginInfo:
        return PluginInfo(
            name="lazarus",
            display_name="Lazarus/Free Pascal",
            version="1.0.0",
            description="Lazarus IDE / Free Pascal compiler support (lazbuild)",
            supported_extensions=[".lpi", ".lpr", ".lpk"],
        )

    # ── Availability detection ──

    def is_available(self) -> bool:
        """Check whether lazbuild.exe is available (PATH/common directories/Start Menu/registry)"""
        from .detect import is_lazarus_available as _check
        return _check()

    # ── detect ──

    async def detect(self) -> List[Dict[str, Any]]:
        """Detect installed Lazarus/FPC compilers"""
        from .detect import find_lazbuild
        from ...services.config_manager import ConfigManager

        lazbuild_paths = find_lazbuild()
        if not lazbuild_paths:
            return []

        cm = ConfigManager()
        compilers = []
        for lb_path in lazbuild_paths:
            version = cm._get_lazarus_version(str(lb_path))
            compilers.append({
                "name": f"Lazarus FPC {version}" if version else "Lazarus FPC",
                "path": str(lb_path),
                "version": version or "",
                "compiler_type": "lazarus",
            })
        return compilers

    # ── compile ──

    async def compile(self, project_path: str, options: Dict[str, Any]) -> Dict[str, Any]:
        """Compile a Lazarus project (delegates to compiler_service.compile_with_lazbuild)"""
        from ...services.compiler_service import CompilerService
        from ...services.config_manager import ConfigManager
        from ...models.compile_request import ProjectCompileRequest, CompileOptions, TargetPlatform

        platform_map = {
            "win32": TargetPlatform.WIN32,
            "win64": TargetPlatform.WIN64,
        }
        target = platform_map.get(options.get("target_platform", "win32"), TargetPlatform.WIN32)

        build_config = options.get("build_configuration")
        timeout = options.get("timeout", 600)

        compile_opts = CompileOptions(
            target_platform=target,
            build_configuration=build_config,
            timeout=timeout,
        )
        request = ProjectCompileRequest(
            project_path=project_path,
            options=compile_opts,
        )

        cm = ConfigManager()
        cs = CompilerService(cm)
        result = await cs.compile_with_lazbuild(request)
        return result.to_dict()

    # ── parse_project ──

    def parse_project(self, project_path: str) -> Optional[Dict[str, Any]]:
        """Parse a Lazarus project file (.lpi)"""
        if not project_path.endswith(('.lpi', '.lpr', '.lpk')):
            return None

        from ...utils.lpi_parser import LpiParser

        p = Path(project_path)
        if p.suffix.lower() == '.lpr':
            lpi_path = p.with_suffix('.lpi')
            if not lpi_path.exists():
                return None
            project_path = str(lpi_path)

        parser = LpiParser(project_path)
        if not parser.parse():
            return None

        info = parser.get_project_info()
        return {
            "name": info.get("name", ""),
            "platform": "lazarus",
            "file_path": project_path,
            "info": info,
        }

    # ── Tool ownership declaration (Phase 2) + handler extraction (Phase 5) ──

    def get_owned_tool_names(self) -> List[str]:
        """List of MCP tool names owned by the Lazarus plugin"""
        return [
            "lazarus_compile",
            "lazarus_project",
            "lazarus_kb",
            "lazarus_file",
        ]

    def get_tools(self) -> List[ToolDefinition]:
        """Return the MCP tools registered by the Lazarus plugin (Phase 5: complete ToolDefinition)"""
        from .handlers import LAZARUS_HANDLERS
        return [
            ToolDefinition(
                name=name,
                description=self._TOOL_DESCRIPTIONS.get(name, f"Lazarus tool: {name}"),
                input_schema=self._TOOL_SCHEMAS.get(name, {"type": "object", "properties": {}}),
                handler=handler,
            )
            for name, handler in LAZARUS_HANDLERS.items()
        ]

    # Tool descriptions and schema metadata
    _TOOL_DESCRIPTIONS = {
        "lazarus_compile": "Lazarus/Free Pascal project compilation (lazbuild)",
        "lazarus_project": "Lazarus project information query — parse .lpi files",
        "lazarus_kb": "Lazarus/FPC source knowledge base — index and search LCL/FPC RTL source code",
        "lazarus_file": "Lazarus/FPC file read/write — read/write(edits, automatic backup)/backup",
    }

    _TOOL_SCHEMAS: Dict[str, Dict[str, Any]] = {}