"""
Command-line argument retrieval tool

Provides command-line argument generation functionality
"""

import json
from typing import Optional, List, Dict, Any
from mcp.types import CallToolResult, TextContent
from ..models.compile_request import ProjectCompileRequest, CompileOptions, TargetPlatform, OutputType, RuntimeLibrary
from ..services.compiler_service import CompilerService
from ..utils.logger import get_logger
from ..utils.dproj_parser import resolve_target_platform_from_dproj

logger = get_logger(__name__)

# Global compiler service instance
_compiler_service: Optional[CompilerService] = None


def set_compiler_service(service: CompilerService):
    """Set compiler service instance"""
    global _compiler_service
    _compiler_service = service


async def get_compiler_args(
    project_path: str,
    target_platform: Optional[str] = None,
    output_path: Optional[str] = None,
    compiler_version: Optional[str] = None,
    conditional_defines: Optional[List[str]] = None,
    unit_search_paths: Optional[List[str]] = None,
    resource_search_paths: Optional[List[str]] = None,
    optimize: bool = True,
    debug: bool = False,
    warning_level: int = 2,
    disabled_warnings: Optional[List[str]] = None,
    output_type: str = "gui",
    runtime_library: str = "static",
    build_configuration: Optional[str] = None,
    extra_args: Optional[List[str]] = None
) -> CallToolResult:
    """
    Get compiler command-line arguments (without executing compilation)

    Args:
        project_path: project file path (.dproj or .dpr)
        target_platform: target platform (win32/win64/osx64/osxarm64/iosdevice64/android/linux64, etc.)
        output_path: output path
        compiler_version: compiler version name
        conditional_defines: conditional compilation symbol list
        unit_search_paths: unit search path list
        resource_search_paths: resource search path list
        optimize: whether to enable optimization
        debug: whether to generate debug information
        warning_level: warning level (0-4)
        disabled_warnings: disabled warning list
        output_type: output type (console/gui/dll)
        runtime_library: runtime library linking method (static/dynamic)
        build_configuration: build configuration name
        extra_args: additional compiler argument list

    Returns:
        Command-line arguments
    """
    logger.info(f"Received get command-line arguments request: {project_path}")

    if _compiler_service is None:
        logger.error("Compiler service not initialized")
        return CallToolResult(
            content=[{"type": "text", "text": "Compiler service not initialized, please start the service first"}],
            isError=True
        )

    try:
        # Only read from .dproj when the user has not specified a target platform
        # (explicitly passed win32/win64 etc. must not be overridden by Active Platform in .dproj)
        if not target_platform:
            target_platform = resolve_target_platform_from_dproj(project_path)
            logger.info(f"Read target platform from .dproj: {target_platform}")
        else:
            target_platform = target_platform.lower()
        
        # Build compilation options
        options = CompileOptions(
            target_platform=TargetPlatform(target_platform),
            output_path=output_path,
            compiler_version=compiler_version,
            conditional_defines=conditional_defines or [],
            unit_search_paths=unit_search_paths or [],
            resource_search_paths=resource_search_paths or [],
            optimize=optimize,
            debug=debug,
            warning_level=warning_level,
            disabled_warnings=disabled_warnings or [],
            output_type=OutputType(output_type),
            runtime_library=RuntimeLibrary(runtime_library),
            build_configuration=build_configuration,
            extra_args=extra_args or [],
        )

        # Build compilation request
        request = ProjectCompileRequest(
            project_path=project_path,
            options=options
        )

        # Generate arguments
        result = _compiler_service.get_args(request)

        # Return result
        return CallToolResult(
            content=[{"type": "text", "text": json.dumps(result.to_dict(), ensure_ascii=False, default=str)}],
            isError=False
        )

    except Exception as e:
        error_msg = f"Exception occurred while generating arguments: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return CallToolResult(
            content=[{"type": "text", "text": error_msg}],
            isError=True
        )

