"""
Single-file compile tool

Provides single-file compilation for Delphi
"""

import json
import os
from typing import Optional, List, Dict, Any
from mcp.types import CallToolResult
from pathlib import Path
from ..models.compile_request import FileCompileRequest
from ..services.compiler_service import CompilerService
from ..services.project_settings import load_project_settings
from ..utils.delphi_versions import normalize_version_key
from ..utils.logger import get_logger
from ..utils.dproj_parser import DprojParser
from ..utils.delphi_env import get_delphi_library_paths, expand_delphi_path_macros
from ..services.delphi_edit_guard import external_edit_block_message

logger = get_logger(__name__)

# Global compiler service instance
_compiler_service: Optional[CompilerService] = None


def set_compiler_service(service: CompilerService):
    """Set the compiler service instance."""
    global _compiler_service
    _compiler_service = service


def _find_dproj_in_directory(file_dir: Path) -> Optional[str]:
    """
    Find a .dproj file in the given directory

    Args:
        file_dir: Directory containing the file

    Returns:
        Path to the .dproj file, or None when none is found
    """
    dproj_files = list(file_dir.glob("*.dproj"))
    if dproj_files:
        return str(dproj_files[0])
    return None


def _get_search_paths_from_dproj(dproj_path: str, platform: str = "Win32") -> List[str]:
    """
    Get the search paths from a .dproj file

    Args:
        dproj_path: Path to the .dproj file
        platform: Target platform

    Returns:
        List of search paths
    """
    try:
        parser = DprojParser(dproj_path)
        if not parser.parse():
            return []

        paths = []

        unit_paths = parser.get_unit_search_paths(platform=platform)
        paths.extend(unit_paths)

        return list(set(paths))
    except Exception as e:
        logger.warning(f"Failed to parse the .dproj file: {e}")
        return []


def _get_delphi_default_library_paths(
    platform: str = "Win32",
    compiler_version: Optional[str] = None,
    project_version: Optional[str] = None,
    override_version: Optional[str] = None,
) -> List[str]:
    """
    Get the default Delphi library search paths

    Args:
        platform: Target platform
        compiler_version: Compiler version name (optional)
        project_version: .dproj ProjectVersion (optional; used as a fallback when compiler_version is not given)
        override_version: Delphi version named by the project settings (optional; takes priority over ProjectVersion inference)

    Returns:
        List of library search paths
    """
    try:
        # Resolve the Delphi version for the compiler (same as the compile service: compiler_version first)
        registry_version = None
        if compiler_version:
            from ..services.config_manager import get_config_manager
            cfg_mgr = get_config_manager()
            if cfg_mgr:
                compiler_cfg = cfg_mgr.get_compiler(compiler_version)
                if compiler_cfg:
                    registry_version = compiler_cfg.registry_version
        if not registry_version and compiler_version:
            # compiler_version may also be a version number/product name ("11.0"/"XE4")
            registry_version = normalize_version_key(compiler_version)
        if not registry_version and override_version:
            registry_version = normalize_version_key(override_version)
        # Fallback: when unspecified/undeterminable, infer from the .dproj ProjectVersion
        if not registry_version and project_version:
            from ..utils.delphi_versions import project_version_to_registry_version
            registry_version = project_version_to_registry_version(project_version)
            if registry_version:
                logger.debug(
                    ".dproj ProjectVersion=%s -> registry_version=%s",
                    project_version, registry_version,
                )
        delphi_lib_paths = get_delphi_library_paths(version=registry_version, platform=platform)
        expanded_paths = []
        for p in delphi_lib_paths:
            expanded = expand_delphi_path_macros(p, version=registry_version, platform=platform)
            if expanded:
                expanded_paths.append(expanded)
        return expanded_paths
    except Exception as e:
        logger.warning(f"Failed to get the default Delphi library paths: {e}")
        return []


async def compile_file(
    file_path: str,
    unit_search_paths: Optional[List[str]] = None,
    conditional_defines: Optional[List[str]] = None,
    warning_level: int = 2,
    disabled_warnings: Optional[List[str]] = None,
    compiler_version: Optional[str] = None,
    extra_args: Optional[List[str]] = None,
) -> CallToolResult:
    """
    Compile a single Delphi unit file (syntax check only)

    Args:
        file_path: Unit file path (.pas)
        unit_search_paths: Unit search paths (optional; when empty, taken from the .dproj or the Delphi defaults)
        conditional_defines: Conditional compilation symbols (optional)
        warning_level: Warning level (0-4)
        disabled_warnings: List of disabled warnings
        compiler_version: Compiler version name (optional; the newest installed version is used when omitted)
        extra_args: Extra compiler arguments

    Returns:
        The compile result
    """
    logger.info(f"Received single-file compile request: {file_path}")

    if _compiler_service is None:
        logger.error("Compiler service is not initialized")
        return CallToolResult(
            content=[{"type": "text", "text": "Compiler service is not initialized"}],
            isError=True
        )

    try:
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            return CallToolResult(
                content=[{"type": "text", "text": f"File not found: {file_path}"}],
                isError=True
            )

        block_message = external_edit_block_message(file_path_obj)
        if block_message:
            return CallToolResult(
                content=[{"type": "text", "text": block_message}],
                isError=True,
            )

        file_dir = file_path_obj.parent

        search_paths = unit_search_paths or []

        dproj_path = _find_dproj_in_directory(file_dir)
        if dproj_path:
            logger.info(f"Found .dproj file: {dproj_path}")
            project_paths = _get_search_paths_from_dproj(dproj_path)
            search_paths.extend(project_paths)
            logger.info(f"Search paths from .dproj: {len(project_paths)}")
        else:
            logger.info("No .dproj file found; using the default Delphi library paths")
            settings = load_project_settings(file_path)
            default_paths = _get_delphi_default_library_paths(
                compiler_version=(
                    compiler_version
                    or (settings.compiler_version if settings else None)
                ),
                override_version=(
                    settings.delphi_version if settings else None
                ),
            )
            search_paths.extend(default_paths)
            logger.info(f"Search paths from the Delphi defaults: {len(default_paths)}")

        request = FileCompileRequest(
            file_path=file_path,
            unit_search_paths=search_paths,
            conditional_defines=conditional_defines or [],
            warning_level=warning_level,
            disabled_warnings=disabled_warnings or [],
            compiler_version=compiler_version,
            extra_args=extra_args or [],
        )

        result = await _compiler_service.compile_file(request)

        return CallToolResult(
            content=[{"type": "text", "text": json.dumps(result.to_dict(), ensure_ascii=False, default=str)}],
            isError=result.status.value != "success"
        )

    except Exception as e:
        error_msg = f"Exception during compilation: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return CallToolResult(
            content=[{"type": "text", "text": error_msg}],
            isError=True
        )
