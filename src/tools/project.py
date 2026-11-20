"""
project unified tool — merges compile_project + dproj_tool + run_audit + deploy

Routes to each sub-function via action, reusing existing implementations.
"""

import json
import logging
import re
from typing import Any, List, Optional

from ..utils.logger import get_logger

logger = get_logger(__name__)

# ── Import existing tool functions ──
# compile_project related
from .compile_project import compile_project as _compile_project, set_compiler_service as _set_compile_svc
from .compile_file import compile_file as _compile_file
from .get_args import get_compiler_args as _get_compiler_args

# dproj_tool
from .dproj_tool import dproj_tool as _dproj_tool

# audit
from .audit import run_audit as _run_audit

# deploy
from .deploy import deploy_project as _deploy_project

# Compiler service (global instance set by server.py, but needs to be re-exported here to server.py)
_compiler_service_set = False


def set_compiler_service(svc):
    """Set the compiler service (called by server.py during initialization)"""
    global _compiler_service_set
    _set_compile_svc(svc)
    _compiler_service_set = True


# ── action routing ──

_ACTIONS = {
    # compile_project series
    "compile": "compile",
    "dry_run": "dry_run",
    "compile_file": "compile_file",
    # dproj_tool series
    "info": "dproj",
    "create": "dproj",
    "set": "dproj",
    "add_config": "dproj",
    "remove_config": "dproj",
    "add_source": "dproj",
    "remove_source": "dproj",
    # run_audit series
    "audit": "audit",
    "ast": "audit",
    "runtime": "audit",
    "layout": "audit",
    # deploy series
    "devices": "deploy",
    "deploy": "deploy",
}

_DISABLED_WARNINGS = {"W1000"}  # warnings disabled by default

# ── MSBuild property extraction (sync /p:Platform and /p:Config from extra_args) ──

_MS_BUILD_PROPERTY_RE = re.compile(r'^/p:(\w+)=(.+)$', re.IGNORECASE)


def _extract_msbuild_property(extra_args: Optional[List[str]], prop_name: str) -> Optional[str]:
    """Extract the value of the last /p:{prop_name}=... from extra_args (MSBuild last-wins semantics).

    Args:
        extra_args: list of additional compile arguments
        prop_name: MSBuild property name (e.g. "Platform", "Config")

    Returns:
        the property value string, or None if not found
    """
    if not extra_args:
        return None
    result = None
    for arg in extra_args:
        m = _MS_BUILD_PROPERTY_RE.match(arg)
        if m and m.group(1).lower() == prop_name.lower():
            result = m.group(2)
    return result


def _warn_extra_args_conflict(
    extra_args: Optional[List[str]],
    prop_name: str,
    explicit_value: str,
) -> Optional[str]:
    """Detect whether /p:{prop_name} in extra_args conflicts with the explicitly passed value.

    On conflict, the extra_args value wins (MSBuild last-wins), and a warning is logged.

    Returns:
        the value from extra_args on conflict; None if there is no conflict
    """
    extra_value = _extract_msbuild_property(extra_args, prop_name)
    if extra_value is None:
        return None
    if extra_value.lower() != explicit_value.lower():
        logger.warning(
            "extra_args /p:%s=%s conflicts with explicit parameter %s=%s; the extra_args value wins",
            prop_name, extra_value, prop_name, explicit_value,
        )
        return extra_value
    return None


async def handle_project(**kwargs) -> Any:
    """Unified project tool entry point; routes to sub-functions by action.

    As a prior step, call tool_help(tool_name="delphi_project") to view detailed parameters for each action.
    """
    action = kwargs.get("action", "")

    try:
        # ── compile series ──
        if action in ("compile",):
            return await _handle_compile(kwargs)

        elif action == "dry_run":
            return await _handle_dry_run(kwargs)

        elif action == "compile_file":
            return await _handle_compile_file(kwargs)

        # ── dproj_tool series ──
        elif action in ("info", "create", "set", "add_config", "remove_config",
                         "add_source", "remove_source"):
            return await _handle_dproj(action, kwargs)

        # ── run_audit series ──
        elif action in ("audit", "ast", "runtime", "layout"):
            return await _handle_audit(kwargs)

        # ── deploy series ──
        elif action in ("devices", "deploy"):
            return await _handle_deploy(action, kwargs)

        else:
            return {"status": "failed", "message": f"Unknown action: {action}. "
                    f"Run tool_help(tool_name='delphi_project') to view all available actions and their parameters."}
    except Exception as e:
        logger.exception("project execution failed")
        return {"status": "failed", "message": str(e)}


# ── sub-handlers ──


async def _handle_compile(kwargs: dict) -> Any:
    """Handle the compile action and record to the experience tracker when done."""
    project_path = kwargs.get("project_path", "")
    if not project_path:
        return {"status": "failed", "message": "Missing required parameter: project_path"}

    if project_path.lower().endswith('.pas'):
        result = await _compile_file(
            file_path=project_path,
            unit_search_paths=kwargs.get('unit_search_paths'),
            conditional_defines=kwargs.get('conditional_defines'),
            compiler_version=kwargs.get('compiler_version'),
            extra_args=kwargs.get('extra_args'),
        )
        _record_compile_to_tracker(project_path, result, "compile_file")
        return result

    # ── Sync platform/config from extra_args (fixes /p:Platform and /p:Config being ignored) ──
    # Priority: explicit parameter > extra_args /p: > .dproj parsing > "win32"/"Debug" fallback
    extra_args = kwargs.get("extra_args")
    target_platform = kwargs.get("target_platform")
    build_configuration = kwargs.get("build_configuration")

    # When the user did not pass target_platform, extract /p:Platform from extra_args
    if not target_platform:
        extra_platform = _extract_msbuild_property(extra_args, "Platform")
        if extra_platform:
            target_platform = extra_platform.lower()
            logger.info("Extracted target platform from extra_args: %s", target_platform)

    # When the user did not pass build_configuration, extract /p:Config from extra_args
    if not build_configuration:
        extra_config = _extract_msbuild_property(extra_args, "Config")
        if extra_config:
            build_configuration = extra_config
            logger.info("Extracted build configuration from extra_args: %s", build_configuration)

    # ── Conflict detection: when an explicit parameter differs from the same-named property in extra_args, extra_args wins ──
    if target_platform and extra_args:
        conflict = _warn_extra_args_conflict(extra_args, "Platform", target_platform)
        if conflict:
            target_platform = conflict.lower()

    if build_configuration and extra_args:
        conflict = _warn_extra_args_conflict(extra_args, "Config", build_configuration)
        if conflict:
            build_configuration = conflict

    result = await _compile_project(
        project_path=project_path,
        target_platform=target_platform,  # when None, compile_project parses it from the .dproj
        build_configuration=build_configuration or "Debug",
        extra_args=extra_args,
        output_path=kwargs.get("output_path"),
        compiler_version=kwargs.get("compiler_version"),
        conditional_defines=kwargs.get("conditional_defines"),
        unit_search_paths=kwargs.get("unit_search_paths"),
        resource_search_paths=kwargs.get("resource_search_paths"),
        optimize=kwargs.get("optimize"),
        debug=kwargs.get("debug"),
        warning_level=kwargs.get("warning_level", 2),
        disabled_warnings=kwargs.get("disabled_warnings", _DISABLED_WARNINGS),
        output_type=kwargs.get("output_type", "gui"),
        runtime_library=kwargs.get("runtime_library", "static"),
        timeout=kwargs.get("timeout", 600),
        auto_install=kwargs.get("auto_install", True),
        run_verify=kwargs.get("run_verify", False),
    )
    _record_compile_to_tracker(project_path, result, "compile")
    return result


def _record_compile_to_tracker(project_path: str, result: Any, action: str) -> None:
    """Record the compile result to the experience tracker."""
    try:
        from ..services.experience_tracker import get_tracker

        # Determine whether it succeeded
        success = True
        result_text = ""
        if hasattr(result, 'isError'):
            success = not result.isError
            if result.content and len(result.content) > 0:
                ct = result.content[0]
                if hasattr(ct, 'text'):
                    result_text = ct.text
        elif isinstance(result, dict):
            success = result.get('status') != 'failed'
            result_text = result.get('message', result.get('error', ''))

        tracker = get_tracker()
        tracker.record(
            name="delphi_project",
            arguments={"action": action, "project_path": project_path},
            success=success,
            result_text=result_text,
        )
    except Exception as e:
        logger.debug("Failed to record compile result to tracker (does not affect compilation): %s", e)


async def _handle_dry_run(kwargs: dict) -> Any:
    """Handle the dry_run action"""
    accepted_keys = {
        "project_path", "target_platform", "output_path", "compiler_version",
        "conditional_defines", "unit_search_paths", "resource_search_paths",
        "optimize", "debug", "warning_level",
        "disabled_warnings", "output_type", "runtime_library", "build_configuration",
        "extra_args",
    }
    filtered = {k: v for k, v in kwargs.items() if k in accepted_keys}
    return await _get_compiler_args(**filtered)


async def _handle_compile_file(kwargs: dict) -> Any:
    """Handle the compile_file action"""
    return await _compile_file(
        file_path=kwargs.get("file_path", kwargs.get("project_path", "")),
        unit_search_paths=kwargs.get('unit_search_paths'),
        conditional_defines=kwargs.get('conditional_defines'),
        compiler_version=kwargs.get('compiler_version'),
        extra_args=kwargs.get('extra_args'),
    )


async def _handle_dproj(action: str, kwargs: dict) -> Any:
    """Handle dproj_tool series actions"""
    return await _dproj_tool(
        action=action,
        project_path=kwargs.get("project_path", ""),
        main_source=kwargs.get("main_source"),
        project_guid=kwargs.get("project_guid"),
        project_version=kwargs.get("project_version"),
        framework_type=kwargs.get("framework_type", "VCL"),
        app_type=kwargs.get("app_type"),
        unit_search_paths=kwargs.get("unit_search_paths"),
        namespace=kwargs.get("namespace"),
        configs=kwargs.get("configs"),
        sources=kwargs.get("sources"),
        platforms=kwargs.get("platforms"),
        target_platform=kwargs.get("target_platform"),
        form_units=kwargs.get("form_units"),
        property_name=kwargs.get("property_name"),
        value=kwargs.get("value"),
        config=kwargs.get("config"),
        platform=kwargs.get("platform"),
        config_name=kwargs.get("config_name"),
        base_config=kwargs.get("base_config"),
        defines=kwargs.get("defines"),
        optimize=kwargs.get("optimize"),
        debug_info=kwargs.get("debug_info"),
        source_file=kwargs.get("source_file"),
        main_source_flag=kwargs.get("main_source_flag", False),
    )


async def _handle_audit(kwargs: dict) -> Any:
    """Handle run_audit series actions"""
    return await _run_audit(kwargs)


async def _handle_deploy(action: str, kwargs: dict) -> Any:
    """Handle deploy series actions"""
    # Remove action from kwargs to avoid duplication
    deploy_kwargs = {k: v for k, v in kwargs.items() if k != "action"}
    return await _deploy_project(action=action, **deploy_kwargs)
