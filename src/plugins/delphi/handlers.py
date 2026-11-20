"""Delphi plugin tool handlers — extracted from the server.py run_server() closure."""
import asyncio
import sys
import winreg
from pathlib import Path
from typing import Any

from mcp.types import CallToolResult, TextContent

from src.constants import (
    REG_KEY_EMBARCADERO_BDS,
    TIMEOUT_AUTOMATION_GUI,
)
from src.services.automation_service import (
    execute_automation as _execute_automation,
    detect_exe_subsystem as _detect_exe_subsystem,
    submit_run_tests as _submit_run_tests,
    IMAGE_SUBSYSTEM_WINDOWS_GUI,
    IMAGE_SUBSYSTEM_WINDOWS_CUI,
)
from src.utils.logger import init_default_logger

logger = init_default_logger()

# ── Tool module imports (each handler is self-contained) ──
from src.tools.project import handle_project as _handle_project
from src.tools import file_tool
from src.tools import pasfmt
from src.tools.config import search_compilers
from src.tools.environment import check_environment
from src.tools.install_package import handle_package
from src.tools.coding_rules import get_coding_rules as _get_coding_rules
from src.tools import knowledge_base as kb_tools
from src.tools import document_kb_tools as doc_tools
from src.tools import async_tasks as async_tools
from src.tools.read_source_file import read_source_file
from src.tools.knowledge_base import _resolve_project_path, _auto_detect_delphi_help_dir
from src.tools.manage_component import manage_component as _manage_component
from src.utils.delphi_env import get_delphi_version as _get_dv
from src.tools.delphi_rtti import handle_delphi_rtti as _handle_delphi_rtti


# ============================================================
# Helper functions — used only by Delphi handlers
# ============================================================

def _coerce_bool(val, default: bool = False) -> bool:
    """Safely convert any input to bool."""
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ('1', 'true', 'yes', 'on')
    if isinstance(val, (int, float)):
        return val != 0
    return default


def _auto_paths() -> list[str]:
    """Return the list of directories to register in the Delphi search path."""
    root = Path(__file__).resolve().parents[3]
    return [
        str(root / "tools" / "auto"),
        str(root / "tools" / "stacktrace"),
    ]


def _register_path_for_platform(key, reg_path: str, path: str, platform: str, results: list[dict]):
    """Register a single path in the Delphi search path for the given platform."""
    try:
        search_path, _ = winreg.QueryValueEx(key, "Search Path")
        paths = search_path.split(";")

        if path in paths:
            results.append({
                "platform": platform, "status": "already_present",
                "path": path,
            })
        else:
            clean_path = search_path.rstrip(";")
            new_path = clean_path + ";" + path if clean_path else path
            winreg.SetValueEx(key, "Search Path", 0, winreg.REG_SZ, new_path)
            results.append({
                "platform": platform, "status": "added",
                "path": path,
            })
    except Exception as e:
        results.append({
            "platform": platform, "status": "error",
            "path": path,
            "message": f"Failed to write search path: {e}",
        })


def _register_daofy_auto(version: str, platforms: list[str] | None = None) -> list[dict]:
    """Write the DaofyAutomation + StackTrace paths into the global Delphi search path (registry)."""
    if platforms is None:
        platforms = ["Win32", "Win64"]

    reg_paths = _auto_paths()
    results: list[dict] = []

    for platform in platforms:
        reg_path = f"{REG_KEY_EMBARCADERO_BDS}\\{version}\\Library\\{platform}"
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                reg_path,
                0,
                winreg.KEY_READ | winreg.KEY_WRITE,
            )
        except FileNotFoundError:
            for p in reg_paths:
                results.append({
                    "platform": platform, "status": "skipped",
                    "path": p,
                    "message": f"Registry path does not exist: HKCU\\{reg_path}",
                })
            continue
        except PermissionError:
            for p in reg_paths:
                results.append({
                    "platform": platform, "status": "error",
                    "path": p,
                    "message": "Insufficient permissions to write to the registry",
                })
            continue
        except Exception as e:
            for p in reg_paths:
                results.append({
                    "platform": platform, "status": "error",
                    "path": p,
                    "message": f"Failed to open registry: {e}",
                })
            continue

        try:
            for p in reg_paths:
                _register_path_for_platform(key, reg_path, p, platform, results)
        finally:
            try:
                winreg.CloseKey(key)
            except Exception:
                pass

    return results


# ============================================================
# Tool handler functions
# ============================================================

async def _handle_project_tool(arguments: dict) -> Any:
    return await _handle_project(**arguments)


async def _handle_delphi_kb(arguments: dict) -> Any:
    default_action = "web" if arguments.get("url") else "search"
    action = arguments.get("action", default_action)
    kb_type = arguments.get("kb_type", "all")
    if action == "search":
        return await doc_tools.search_documents(arguments) if kb_type == "document" else await kb_tools.search_knowledge(arguments)
    elif action == "stats":
        return await doc_tools.get_document_statistics(arguments) if kb_type == "document" else await kb_tools.get_unified_knowledge_stats(arguments)
    elif action == "build":
        async_mode = _coerce_bool(arguments.get("async_mode"), True)
        if not async_mode:
            return await kb_tools.build_unified_knowledge_base(arguments)
        version = arguments.get("version")
        rebuild = _coerce_bool(arguments.get("rebuild"), False)
        kb_type_map = {"all": "build_knowledge_base", "delphi": "build_knowledge_base",
                       "thirdparty": "build_thirdparty_knowledge_base", "project": "init_project_knowledge_base",
                       "document": "build_document_knowledge_base"}
        task_type = kb_type_map.get(kb_type, "build_knowledge_base")
        incremental = arguments.get("incremental", False)
        if task_type == "build_document_knowledge_base":
            directory = arguments.get("directory")
            start_url = arguments.get("start_url")
            urls = arguments.get("urls", [])
            # Only auto-detect the help directory when neither start_url nor urls is specified (pure directory scan)
            if not directory and not start_url and not urls:
                detected = _auto_detect_delphi_help_dir()
                if detected:
                    directory = detected
                    logger.info(f"Auto-detected Delphi help directory: {directory}")
                else:
                    logger.warning("No directory provided and no Delphi help directory detected")

            # Document KB rebuild confirmation: force_rebuild clears all existing documents
            if rebuild:
                try:
                    _scanner = doc_tools._get_scanner()
                    _stats = _scanner.get_statistics()
                    _total = _stats.get('total_documents', 0)
                    if _total > 0:
                        _confirm = _coerce_bool(arguments.get("confirm"), False)
                        if not _confirm:
                            _msg = [f"⚠️ **Confirm rebuilding the document knowledge base**\n\nThe current knowledge base contains **{_total}** documents:\n"]
                            _by_type = _stats.get('by_type', {})
                            if _by_type:
                                _msg.append("By type:\n")
                                for _t, _c in sorted(_by_type.items(), key=lambda x: x[1], reverse=True):
                                    _msg.append(f"  - {_t}: {_c}\n")
                            _by_ext = _stats.get('by_extension', {})
                            if _by_ext:
                                _msg.append("By extension:\n")
                                for _e, _c in sorted(_by_ext.items(), key=lambda x: x[1], reverse=True):
                                    _msg.append(f"  - {_e}: {_c}\n")
                            _msg.append(
                                "\n`rebuild=True` will **clear all the documents above** and rebuild from scratch; the original content cannot be recovered.\n\n"
                                "To keep the old content, either:\n"
                                "  1. Include the old document sources (e.g. multiple URLs or directories) in this build's parameters, or\n"
                                "  2. Remove `rebuild=True` and use incremental addition instead\n\n"
                                "**To confirm and continue, add the parameter `confirm=True`**"
                            )
                            return CallToolResult(content=[TextContent(type="text", text="".join(_msg))])
                except Exception as _e:
                    logger.warning(f"Failed to check document knowledge base status, skipping confirmation: {_e}")

            task_params = {"urls": arguments.get("urls", []), "directory": directory,
                           "extensions": arguments.get("extensions", [".chm"]),
                           "start_url": arguments.get("start_url"), "max_pages": arguments.get("max_pages", 100),
                           "max_depth": arguments.get("max_depth", 3), "domain_filter": arguments.get("domain_filter"),
                           "url_pattern": arguments.get("url_pattern"), "exclude": arguments.get("exclude"),
                           "rebuild": rebuild}
        elif task_type == "init_project_knowledge_base":
            resolved_path = _resolve_project_path(arguments.get("project_path"))
            task_params = {"project_path": resolved_path, "version": version,
                           "rebuild": rebuild, "build_thirdparty": arguments.get("build_thirdparty", True),
                           "build_project": arguments.get("build_project", True)}
        else:
            task_params = {"version": version, "rebuild": rebuild, "incremental": incremental}
        return await async_tools.start_async_task({"task_type": task_type, "task_params": task_params,
                                                      "show_progress": arguments.get("show_progress", True),
                                                      "_on_complete": arguments.get("_on_complete")})
    elif action == "build_embedding":
        pp = _resolve_project_path(arguments.get("project_path"))
        if not pp:
            return {"error": "Project path not detected"}
        return await async_tools.start_async_task({"task_type": "build_embedding", "task_params": {"project_path": pp},
                                                     "show_progress": True,
                                                     "_on_complete": arguments.get("_on_complete")})
    elif action == "scan":
        return await doc_tools.scan_documents(arguments) if kb_type == "document" else {"error": "action=scan only supports kb_type=document"}
    elif action == "web":
        return await doc_tools.add_web_document(arguments) if kb_type == "document" else {"error": "action=web only supports kb_type=document"}
    elif action == "read":
        if arguments.get("url") or arguments.get("doc_id"):
            return await doc_tools.read_document(arguments)
        elif arguments.get("file_path"):
            return await read_source_file(arguments)
        return {"error": "action=read requires url/doc_id or file_path parameter"}
    return {"error": f"Unknown action: {action}"}


async def _handle_file_tool(arguments: dict) -> Any:
    return await file_tool.handle_file_tool(arguments)


async def _handle_manage_component(arguments: dict) -> Any:
    # manage_component is an async function, call it directly
    return await _manage_component(
        action=arguments.get("action", "create"),
        target_dfm=arguments.get("target_dfm"),
        target_pas=arguments.get("target_pas"),
        component_name=arguments.get("component_name"),
        parent_name=arguments.get("parent_name"),
        new_component_class=arguments.get("new_component_class"),
        new_component_name=arguments.get("new_component_name"),
        properties=arguments.get("properties"),
        dfm_text=arguments.get("dfm_text"),
        code=arguments.get("code", ""),
        uses=arguments.get("uses"),
        type_decl=arguments.get("type_decl", ""),
        init_code=arguments.get("init_code", ""),
        compile_timeout=arguments.get("compile_timeout", 60),
        exec_timeout=arguments.get("exec_timeout", 15),
    )


async def _handle_check_environment(arguments: dict) -> Any:
    action = arguments.get("action", "check")
    if action == "detect":
        return await search_compilers(search_path=arguments.get("search_path"))
    elif action == "check":
        return await check_environment()
    elif action == "install":
        return await pasfmt.download_and_install_pasfmt(install_dir=arguments.get("install_dir"))
    elif action == "format_install":
        return await pasfmt.download_and_install_pasfmt_rad(delphi_version=arguments.get("delphi_version", "11"), install_dir=arguments.get("install_dir"))
    return {"error": f"Unknown action: {action}"}


async def _handle_package(arguments: dict) -> Any:
    return await handle_package(**arguments)


async def _handle_get_coding_rules(arguments: dict) -> Any:
    return await _get_coding_rules(
        project_path=arguments.get("project_path"),
        section=arguments.get("section"),
        examples=arguments.get("examples"),
        language=arguments.get("language"),
    )
async def _handle_automate_delphi(arguments: dict) -> dict:
    """Handle automate_delphi tool calls (auto-detect or route by action)."""
    requested_action = arguments.get("action", "auto")
    action = requested_action

    # ── prepare: register DaofyAutomation into the Delphi global search path ──
    if action == "prepare":
        try:
            version = _get_dv()
        except ImportError:
            version = None

        if not version:
            return {
                "action": "prepare", "status": "error",
                "message": "No installed Delphi compiler detected",
            }

        results = _register_daofy_auto(version)
        added = sum(1 for r in results if r["status"] == "added")
        already = sum(1 for r in results if r["status"] == "already_present")
        errors = sum(1 for r in results if r["status"] == "error")
        skipped = sum(1 for r in results if r["status"] == "skipped")

        return {
            "action": "prepare",
            "delphi_version": version,
            "daofy_auto_paths": _auto_paths(),
            "results": results,
            "status": "success" if errors == 0 else "partial",
            "message": (
                f"Delphi {version}: added {added} platform(s), "
                f"{already} already present"
                + (f", {skipped} skipped" if skipped else "")
                + (f", {errors} failed" if errors else "")
            ),
        }

    app_path = arguments.get("app_path", "")
    keep_alive = _coerce_bool(arguments.get("keep_alive", False))
    stop_on_failure = _coerce_bool(arguments.get("stop_on_failure", True))
    env = arguments.get("env", None)
    subsystem = None

    if not app_path:
        return {"status": "error", "message": "Missing required parameter: app_path"}

    # auto detection: read the Subsystem from the PE header
    if action == "auto":
        subsystem = _detect_exe_subsystem(app_path)
        if subsystem == IMAGE_SUBSYSTEM_WINDOWS_CUI:
            action = "console"
        elif subsystem == IMAGE_SUBSYSTEM_WINDOWS_GUI:
            action = "gui"
        else:
            # default to gui when detection fails (keeps compatibility)
            action = "gui"

    if action == "gui":
        script = arguments.get("script", "")
        snapshots_dir = arguments.get("snapshots_dir", "")
        wait_timeout = arguments.get("wait_timeout", 10)

        if not script:
            return {"status": "error", "message": "gui mode missing required parameter: script"}

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(_execute_automation,
                                  action="gui",
                                  app_path=app_path,
                                  script=script,
                                  snapshots_dir=snapshots_dir,
                                  wait_for_pipe=wait_timeout,
                                  keep_alive=keep_alive,
                                  stop_on_failure=stop_on_failure,
                                  env=env),
                timeout=TIMEOUT_AUTOMATION_GUI,
            )
            result.setdefault("requested_action", requested_action)
            result.setdefault("resolved_action", action)
            result.setdefault("detected_subsystem", subsystem)
            return result
        except asyncio.TimeoutError:
            return {
                "status": "failed",
                "message": "automate_delphi(gui) execution timed out (300s)",
            }
        except Exception as e:
            return {"status": "failed", "message": f"automate_delphi(gui) failed: {e}"}

    elif action == "console":
        input_text = arguments.get("input", "")
        expect = arguments.get("expect", "")
        timeout = arguments.get("timeout", 30)
        args = arguments.get("args", None)

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(_execute_automation,
                                  action="console",
                                  app_path=app_path,
                                  input_text=input_text,
                                  expect=expect,
                                  timeout=timeout,
                                  keep_alive=keep_alive,
                                  args=args,
                                  env=env),
                timeout=max(timeout + 10, 120),
            )
            result.setdefault("requested_action", requested_action)
            result.setdefault("resolved_action", action)
            result.setdefault("detected_subsystem", subsystem)
            return result
        except asyncio.TimeoutError:
            return {
                "status": "failed",
                "message": "automate_delphi(console) execution timed out",
                "action": "console",
            }
        except Exception as e:
            return {"status": "failed", "message": f"automate_delphi(console) failed: {e}"}

    elif action == "test":
        tests = arguments.get("tests", [])
        visibility = arguments.get("visibility", "public,published")
        test_keep_alive = _coerce_bool(arguments.get("keep_alive", True))
        wait_timeout = arguments.get("wait_timeout", 10)
        test_timeout = arguments.get("test_timeout", 30)

        if not tests:
            return {"status": "error", "message": "test mode missing required parameter: tests"}

        # submit for background async execution to avoid MCP channel timeouts
        try:
            task_id = _submit_run_tests(
                app_path=app_path,
                tests=tests,
                visibility=visibility,
                keep_alive=test_keep_alive,
                wait_for_pipe=wait_timeout,
                test_timeout=test_timeout,
                env=env,
            )
            return {
                "status": "submitted",
                "task_id": task_id,
                "message": "Test task submitted for background execution",
                "requested_action": requested_action,
                "resolved_action": action,
            }
        except Exception as e:
            return {"status": "failed", "message": f"automate_delphi(test) submit failed: {e}"}

    elif action == "list_tests":
        visibility = arguments.get("visibility", "public,published")
        wait_timeout = arguments.get("wait_timeout", 10)

        try:
            from ..services.automation_service import list_tests as _list_tests
            result = await asyncio.wait_for(
                asyncio.to_thread(
                    _list_tests,
                    app_path=app_path,
                    visibility=visibility,
                    wait_for_pipe=wait_timeout,
                    env=env,
                ),
                timeout=30,
            )
            result.setdefault("requested_action", requested_action)
            result.setdefault("resolved_action", action)
            return result
        except asyncio.TimeoutError:
            return {
                "status": "error",
                "message": "automate_delphi(list_tests) execution timed out (30s)",
            }
        except Exception as e:
            return {"status": "error", "message": f"automate_delphi(list_tests) failed: {e}"}

    else:
        return {"status": "error", "message": f"Unknown action: {action}"}


# ============================================================
# Export: tool name → handler mapping
# ============================================================
DELPHI_HANDLERS = {
    "delphi_project": _handle_project_tool,
    "delphi_kb": _handle_delphi_kb,
    "delphi_file": _handle_file_tool,
    "file_tool": _handle_file_tool,  # legacy alias
    "manage_component": _handle_manage_component,
    "check_environment": _handle_check_environment,
    "package": _handle_package,
    "get_coding_rules": _handle_get_coding_rules,
    "automate_delphi": _handle_automate_delphi,
    "delphi_rtti": _handle_delphi_rtti,
}

# ── Tool descriptions + inputSchema — list_tools() collects them from the registry, no longer hardcoded in server.py ──

DELPHI_TOOL_DESCRIPTIONS: dict[str, str] = {
    "delphi_project": "Delphi project compilation, configuration, auditing and deployment. Parameters vary by action; before calling, first run tool_help(tool_name='delphi_project', action='<action>').",
    "delphi_kb": "Delphi knowledge base search and management. Parameters vary by action; before calling, first run tool_help(tool_name='delphi_kb', action='<action>').",
    "delphi_file": "Unified entry point for Delphi files: read/write/search/grep/replace/insert/delete/backup. Even for merely reading .pas/.dfm/.dproj/.dpk/.dpr/.inc/.fmx you must use delphi_file; using the built-in Read/Edit/Write/grep/apply_patch is forbidden; parameters vary by action, before calling first run tool_help(tool_name='delphi_file', action='<action>').",
    "manage_component": "Adding, removing, modifying and generating DFM components. Parameters vary by action; before calling, first run tool_help(tool_name='manage_component', action='<action>').",
    "check_environment": "Environment check, RAD Studio/Delphi compiler detect/check/install; locates dcc32/dcc64, PATH/BPL. Parameters vary by action; before calling, first run tool_help(tool_name='check_environment', action='<action>').",
    "package": "Component package compilation, installation and listing. Parameters vary by action; before calling, first run tool_help(tool_name='package', action='<action>').",
    "get_coding_rules": "Coding rules retrieval tool — fetch Delphi or Lazarus/FPC coding standards before writing/compile/review/automation, supports retrieving in sections by language/chapter",
    "automate_delphi": "Delphi automated testing. Parameters vary by action; before calling, first run tool_help(tool_name='automate_delphi', action='<action>').",
    "delphi_rtti": "RTTI discovery and invocation. Parameters vary by action; before calling, first run tool_help(tool_name='delphi_rtti', action='<action>').",
}

DELPHI_TOOL_SCHEMAS: dict[str, dict] = {
    "delphi_project": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["compile", "compile_file", "dry_run", "info", "create",
                         "set", "add_config", "remove_config", "add_source",
                         "remove_source", "audit", "ast", "runtime", "layout",
                         "devices", "deploy"],
            },
            "project_path": {"type": "string", "description": "Absolute path to the project file (.dproj/.dpr/.dpk/.groupproj), e.g. C:\\project\\App.dproj"},
            "extra_args": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Extra compile arguments (e.g. [\"/p:DCC_DebugInfoInTds=true\"]); for parameters of other actions, call tool_help first",
            },
        },
        "required": ["action"]
    },
    "delphi_kb": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["search", "stats", "build", "scan", "web", "read", "build_embedding"]},
        }
    },
    "delphi_file": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["read", "write", "replace", "insert", "delete", "format", "backup", "encode", "uses", "fix_garbled", "grep"],
                "default": "read",
            },
            "file_path": {
                "oneOf": [
                    {"type": "string"},
                    {"type": "array", "items": {"type": "string"}},
                ],
                "description": "Absolute file path; grep also supports an absolute directory path or an array of paths",
            },
            "edits": {
                "type": "array",
                "description": "Batch edit operations (write/replace/insert/delete)",
                "items": {
                    "type": "object",
                    "properties": {
                        "start_line": {"type": "integer", "description": "Start line number (1-indexed inclusive)"},
                        "end_line": {"type": "integer", "description": "End line number (1-indexed inclusive)"},
                        "content": {"type": "string", "description": "New content"},
                        "old_content": {"type": "string", "description": "Original content (when non-empty, used as a pre-write check to prevent overwriting unexpected changes)"},
                        "position": {
                            "type": "string",
                            "enum": ["before", "after"],
                            "description": "Insert position relative to the start_line anchor for insert",
                        },
                    },
                    "required": ["start_line"],
                },
            },
            "force": {
                "type": "boolean",
                "description": "Skip consecutive duplicate line detection",
                "default": False,
            },
            "dry_run": {
                "type": "boolean",
                "description": "Preview changes without actually writing",
                "default": False,
            },
            "encoding": {"type": "string", "description": "File encoding (BOM auto-detected)"},
            "backup": {"type": "boolean", "description": "Create a backup before writing"},
            "auto_format": {"type": "boolean", "description": "Auto-format after writing"},
            "allow_dirty": {"type": "boolean", "description": "Allow writing to files already marked as dirty"},
            "project_path": {"type": "string", "description": "Absolute project path, used to restrict the file scope or resolve relative paths"},
            "start_line": {"type": "integer", "minimum": 1, "description": "read start line number (1-indexed inclusive)"},
            "end_line": {"type": "integer", "minimum": 1, "description": "read end line number (1-indexed inclusive)"},
            "limit": {"type": "integer", "minimum": 1, "description": "read maximum number of lines returned"},
            "show_line_numbers": {"type": "boolean", "description": "read output with 1-indexed line numbers"},
            "search_type": {"type": "string", "enum": ["path", "class", "function", "record"]},
            "search_in": {"type": "string", "enum": ["all", "delphi", "project", "thirdparty"]},
            "type_name": {"type": "string", "description": "Class or interface name"},
            "function_name": {"type": "string", "description": "Function or procedure name"},
            "class_name": {"type": "string", "description": "Class name"},
            "record_name": {"type": "string", "description": "Record type name"},
            "mode": {"type": "string", "enum": ["file", "code", "check"], "description": "format mode"},
            "code": {"type": "string", "description": "Code text when format mode=code"},
            "config_path": {"type": "string", "description": "Absolute path to the pasfmt config file"},
            "uses_style": {"type": "string", "enum": ["compact", "pasfmt_default"]},
            "to_encoding": {"type": "string", "description": "encode target encoding"},
            "from_encoding": {"type": "string", "description": "encode source encoding"},
            "uses_action": {"type": "string", "enum": ["add", "remove"]},
            "unit_name": {"type": "string", "description": "uses unit name"},
            "uses_section": {"type": "string", "enum": ["interface", "implementation"]},
            "backup_action": {"type": "string", "enum": ["create", "list", "restore"]},
            "version": {"type": "integer", "minimum": 1, "description": "Backup version number"},
            "include": {"type": "string", "description": "grep directory include glob; separate multiple patterns with commas or semicolons"},
            "exclude": {"type": "string", "description": "grep directory exclude glob; separate multiple patterns with commas or semicolons"},
            "pattern": {"type": "string", "description": "grep single regex pattern"},
            "patterns": {"type": "array", "items": {"type": "string"}, "description": "grep multiple OR regex patterns"},
            "filter_pattern": {"type": "string", "description": "grep secondary AND filter pattern"},
            "exclude_pattern": {"type": "string", "description": "grep NOT exclusion pattern"},
            "replace": {"type": "string", "description": "grep replacement text"},
            "context": {"type": "integer", "minimum": 0, "description": "grep context line count"},
            "count": {"type": "integer", "minimum": 1, "description": "grep max results returned per file"},
            "target_encoding": {"type": "string", "description": "fix_garbled target encoding"},
        },
        "required": ["action"]
    },
    "manage_component": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["create", "add", "remove", "modify"], "default": "create"},
        },
        "required": ["action"]
    },
    "check_environment": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["check", "detect", "install", "format_install"], "default": "check"},
        }
    },
    "package": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["install", "list"], "default": "install"},
        },
        "required": ["action"]
    },
    "get_coding_rules": {
        "type": "object",
        "properties": {
            "section": {"type": "string"},
            "language": {
                "type": "string",
                "enum": ["delphi", "lazarus"],
                "default": "delphi",
                "description": "Programming language: delphi (default) or lazarus",
            },
            "examples": {"type": "string", "description": "Example name, e.g. naming/formatting/error-handling/dirty-flag/debug-log-template. Loads the example file under coding-rules/{language}/examples/ by name"},
        }
    },
    "automate_delphi": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["auto", "gui", "console", "prepare", "test"],
                "default": "auto",
            },
        },
        "required": [],
    },
    "delphi_rtti": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["guide", "discover", "call"],
            },
        },
        "required": ["action"],
    },
}