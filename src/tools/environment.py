"""
Environment check tool

Provides compiler environment checking
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
from mcp.types import CallToolResult
from ..services.config_manager import ConfigManager
from ..services.delphi_edit_guard import snapshot_status
from ..utils.validator import Validator
from ..utils.logger import get_logger

logger = get_logger(__name__)

# Global config manager instance
_config_manager: Optional[ConfigManager] = None

# Global third-party library service instance
_thirdparty_kb_service = None


def set_config_manager(manager: ConfigManager):
    """Set the config manager instance"""
    global _config_manager
    _config_manager = manager


def set_thirdparty_kb_service(service):
    """Set the third-party library knowledge base service instance"""
    global _thirdparty_kb_service
    _thirdparty_kb_service = service


async def check_environment(arguments: dict = None) -> CallToolResult:
    """
    Check the compiler environment status

    Args:
        arguments: optional argument dict

    Returns:
        CallToolResult
    """
    logger.info("Received an environment-check request")

    if _config_manager is None:
        logger.error("The config manager is not initialized")
        return CallToolResult(
            content=[{"type": "text", "text": "The config manager is not initialized; start the service first"}],
            isError=True
        )

    try:
        compilers = _config_manager.get_all_compilers()
        default_compiler = _config_manager.get_compiler()

        # Check whether each compiler is usable
        validator = Validator()
        compiler_infos = []

        for compiler in compilers:
            is_valid, _ = validator.validate_compiler_path(compiler.path)
            compiler_infos.append({
                "name": compiler.name,
                "path": compiler.path,
                "version": compiler.version,
                "is_available": is_valid,
                "is_default": compiler.is_default
            })

        # Decide the overall status
        available_count = sum(1 for info in compiler_infos if info["is_available"])
        status = "available" if available_count > 0 else "unavailable"

        logger.info(f"Environment check finished: {available_count}/{len(compilers)} compiler(s) available")

        # Fetch the third-party library paths (filtered by the default compiler's registry_version, matching the RTL library path policy)
        thirdparty_paths = []
        try:
            if _thirdparty_kb_service:
                effective_compiler = _config_manager.get_effective_compiler(platform="win32")
                version = (
                    getattr(effective_compiler, "registry_version", None)
                    if effective_compiler
                    else getattr(default_compiler, "registry_version", None)
                )
                thirdparty_paths = _thirdparty_kb_service.get_library_paths(version)
        except Exception as e:
            logger.warning(f"Failed to fetch the third-party library paths: {e}")

        # Format the output
        output = f"Delphi compiler environment status: {status}\n\n"
        output += f"Compiler count: {len(compilers)} ({available_count} available)\n"
        if default_compiler:
            output += f"Default compiler: {default_compiler.name} ({default_compiler.version})\n"

        output += (
            "MSBuild: the project config .daofy/project.json wins first, "
            "then the per-version mapping, and lastly auto-probing (vswhere → VS → Delphi → PATH)\n"
        )

        version_msbuild = getattr(
            _config_manager.config,
            "msbuild_by_delphi_version",
            None,
        )
        if version_msbuild:
            output += "MSBuild configured per Delphi version:\n"
            for version_key, msbuild_value in version_msbuild.items():
                resolved_value = (
                    _config_manager.get_msbuild_for_version(version_key)
                    or msbuild_value
                )
                exists_mark = "present" if Path(resolved_value).is_file() else "missing"
                output += f"  {version_key} → {resolved_value} [{exists_mark}]\n"

        output += (
            "Project-level override: in the project directory or a parent directory, "
            ".daofy/project.json / daofy.project.json\n"
        )

        output += f"\nThird-party library paths: {len(thirdparty_paths)}\n"
        for i, path in enumerate(thirdparty_paths[:10], 1):
            output += f"  {i}. {path}\n"
        if len(thirdparty_paths) > 10:
            output += f"  ... {len(thirdparty_paths) - 10} more\n"

        guard = snapshot_status()
        output += "\nDelphi edit guard:\n"
        output += f"  enabled: {guard['enabled']}\n"
        output += f"  mode: {guard['mode']}\n"
        output += f"  strict_blocks: {guard['strict_blocks']}\n"
        output += f"  recent_unauthorized_count: {guard['recent_unauthorized_count']}\n"
        for item in guard["recent_unauthorized_edits"][:5]:
            output += f"  - {item['path']} ({item['event_type']}, age_ms={item.get('age_ms', 0)})\n"
        if guard["recent_unauthorized_count"] > 5:
            output += f"  ... {guard['recent_unauthorized_count'] - 5} more\n"
        output += (
            "  note: strict mode blocks delphi_project compile after the watcher "
            "detects non-Daofy Delphi file writes.\n"
        )

        return CallToolResult(content=[{"type": "text", "text": output}])

    except Exception as e:
        error_msg = f"Exception during the environment check: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return CallToolResult(
            content=[{"type": "text", "text": error_msg}],
            isError=True
        )


async def get_compile_history(limit: int = 10) -> Dict[str, Any]:
    """
    Get the compile history

    Args:
        limit: the maximum number of entries

    Returns:
        The compile history dict
    """
    logger.info(f"Received a get-compile-history request, limit: {limit}")

    if _config_manager is None:
        logger.error("The config manager is not initialized")
        return {
            "success": False,
            "message": "The config manager is not initialized",
            "entries": []
        }

    try:
        entries = _config_manager.get_history(limit)

        return {
            "success": True,
            "message": f"{len(entries)} history record(s)",
            "entries": [e.to_dict() for e in entries]
        }

    except Exception as e:
        error_msg = f"Exception while fetching the compile history: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            "success": False,
            "message": error_msg,
            "entries": []
        }

