"""
Configuration management tool

Provides compiler configuration management
"""

from typing import Optional, Dict, Any
from mcp.types import CallToolResult, TextContent
from ..models.compiler_config import CompilerConfig
from ..services.config_manager import ConfigManager
from ..utils.validator import Validator
from ..utils.logger import get_logger
import os
from pathlib import Path

logger = get_logger(__name__)

# Global config manager instance
_config_manager: Optional[ConfigManager] = None


def set_config_manager(manager: ConfigManager):
    """Set the config manager instance"""
    global _config_manager
    _config_manager = manager


async def set_compiler_config(
    name: str,
    path: str,
    is_default: bool = False,
    version: Optional[str] = None
) -> Dict[str, Any]:
    """
    Configure a Delphi compiler

    Args:
        name: the compiler version name
        path: the compiler executable path
        is_default: whether to make it the default compiler
        version: the compiler version number

    Returns:
        The configuration result dict
    """
    logger.info(f"Received a configure-compiler request: {name}")

    if _config_manager is None:
        logger.error("The config manager is not initialized")
        return {
            "success": False,
            "message": "The config manager is not initialized",
            "compiler_name": name
        }

    try:
        # Validate the compiler path
        validator = Validator()
        is_valid, error_msg = validator.validate_compiler_path(path)
        if not is_valid:
            logger.error(f"Compiler path validation failed: {error_msg}")
            return {
                "success": False,
                "message": error_msg,
                "compiler_name": name
            }

        # Create the compiler config
        compiler = CompilerConfig(
            name=name,
            path=path,
            is_default=is_default,
            version=version
        )

        # Add the config
        _config_manager.add_compiler(compiler)

        logger.info(f"Compiler configured successfully: {name}")
        return {
            "success": True,
            "message": f"Compiler configured successfully: {name}",
            "compiler_name": name
        }

    except Exception as e:
        error_msg = f"Exception during configuration: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            "success": False,
            "message": error_msg,
            "compiler_name": name
        }


async def get_compiler_list() -> Dict[str, Any]:
    """
    Get the list of all compiler configurations

    Returns:
        A dict holding the list of compiler configurations
    """
    logger.info("Received a get-compiler-list request")

    if _config_manager is None:
        logger.error("The config manager is not initialized")
        return {
            "success": False,
            "message": "The config manager is not initialized",
            "compilers": []
        }

    try:
        compilers = _config_manager.get_all_compilers()
        default_compiler = _config_manager.get_compiler()

        return {
            "success": True,
            "message": f"{len(compilers)} compiler configuration(s)",
            "compilers": [c.to_dict() for c in compilers],
            "default_compiler": default_compiler.name if default_compiler else None
        }

    except Exception as e:
        error_msg = f"Exception while listing compilers: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            "success": False,
            "message": error_msg,
            "compilers": []
        }


async def search_compilers(search_path: Optional[str] = None) -> CallToolResult:
    """
    Search for Delphi compilers
    
    - without the search_path argument: auto-detect the compilers on this system
    - with the search_path argument: search for compilers under the given path
    Only valid compilers are returned

    Args:
        search_path: the search path; defaults to the common install locations

    Returns:
        CallToolResult with search results
    
    Note:
        Prefer the check_environment tool to validate a compiler and get full details
    """
    logger.info(f"Received a search-compilers request: {search_path or 'auto-detect'}")

    if _config_manager is None:
        logger.error("The config manager is not initialized")
        return CallToolResult(
            content=[{"type": "text", "text": "The config manager is not initialized; start the service first"}],
            isError=True
        )

    try:
        validator = Validator()
        found_compilers = []

        if search_path is None:
            # Auto-detect mode: check the compilers already configured on this system
            _config_manager._auto_detect_compilers()
            compilers = _config_manager.get_all_compilers()
            default_compiler = _config_manager.get_compiler()

            for c in compilers:
                is_valid, _ = validator.validate_compiler_path(c.path)
                if is_valid:
                    found_compilers.append({
                        "name": c.name,
                        "path": c.path,
                        "version": c.version,
                        "is_default": c.name == (default_compiler.name if default_compiler else None)
                    })
            
            logger.info(f"Auto-detection finished: {len(found_compilers)} valid compiler(s)")
            
            # Format output
            output = f"Detected {len(found_compilers)} valid Delphi compiler(s):\n\n"
            for c in found_compilers:
                default_mark = " (default)" if c.get("is_default") else ""
                output += f"- {c['name']}{default_mark}\n"
                output += f"  Path: {c['path']}\n"
                output += f"  Version: {c.get('version', 'unknown')}\n\n"
            
            return CallToolResult(content=[{"type": "text", "text": output}])
        else:
            # Search mode: search under the given path
            common_paths = [search_path]
            
            for base_path in common_paths:
                if not os.path.exists(base_path):
                    continue
                    
                for version_dir in os.listdir(base_path):
                    version_path = os.path.join(base_path, version_dir)
                    if not os.path.isdir(version_path):
                        continue
                        
                    bin_path = os.path.join(version_path, "bin")
                    if not os.path.exists(bin_path):
                        continue
                    
                    for dcc in ["dcc32.exe", "dcc64.exe"]:
                        dcc_path = os.path.join(bin_path, dcc)
                        if os.path.exists(dcc_path):
                            is_valid, _ = validator.validate_compiler_path(dcc_path)
                            if is_valid:
                                found_compilers.append({
                                    "name": f"Delphi {version_dir}",
                                    "path": dcc_path,
                                    "version": version_dir
                                })
            
            logger.info(f"Search finished: {len(found_compilers)} valid compiler(s)")
            
            output = f"Found {len(found_compilers)} valid Delphi compiler(s):\n\n"
            for c in found_compilers:
                output += f"- {c['name']}\n"
                output += f"  Path: {c['path']}\n"
                output += f"  Version: {c.get('version', 'unknown')}\n\n"
            
            return CallToolResult(content=[{"type": "text", "text": output}])

    except Exception as e:
        error_msg = f"Exception during the search: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return CallToolResult(
            content=[{"type": "text", "text": error_msg}],
            isError=True
        )


# Legacy interface compatibility
async def detect_compilers() -> CallToolResult:
    """Auto-detect the Delphi compilers available on this system (legacy interface)"""
    return await search_compilers()


async def search_delphi_compilers(search_path: Optional[str] = None) -> CallToolResult:
    """Search for Delphi compilers under the given path (legacy interface)"""
    return await search_compilers(search_path)


async def remove_compiler_config(name: str) -> Dict[str, Any]:
    """
    Remove a compiler configuration

    Args:
        name: the compiler name

    Returns:
        The removal result dict
    """
    logger.info(f"Received a remove-compiler-config request: {name}")

    if _config_manager is None:
        logger.error("The config manager is not initialized")
        return {
            "success": False,
            "message": "The config manager is not initialized",
            "compiler_name": name
        }

    try:
        result = _config_manager.remove_compiler(name)

        if result:
            logger.info(f"Compiler config removed successfully: {name}")
            return {
                "success": True,
                "message": f"Compiler config removed successfully: {name}",
                "compiler_name": name
            }
        else:
            logger.warning(f"Compiler config not found: {name}")
            return {
                "success": False,
                "message": f"Compiler config not found: {name}",
                "compiler_name": name
            }

    except Exception as e:
        error_msg = f"Exception during removal: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            "success": False,
            "message": error_msg,
            "compiler_name": name
        }

