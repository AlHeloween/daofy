"""Core tool handlers — extracted from the server.py run_server() closure.

Tools that do not belong to any compiler plugin: async_task, code_hosting, tool_help,
experience, daofy_update, generate_copyright, ocr
"""
import asyncio
import sys
from typing import Any

from src.constants import TIMEOUT_EXPERIENCE_TOOL, TIMEOUT_GENERATE_COPYRIGHT
from src.services.copyright_service import generate_copyright as _generate_copyright
from src.services.knowledge_base.async_task_manager import get_task_manager
from src.tools import async_tasks as async_tools
from src.tools.code_hosting import code_hosting
from src.tools.experience import experience as _experience
from src.tools.tool_help import get_tool_help
from src.utils import updater
from src.tool_docs import TOOL_NAMES
from src.utils.logger import init_default_logger
from src.tools.structured_content import handle_structured_content as _sc_handler

logger = init_default_logger()


def _coerce_bool(val, default: bool = False) -> bool:
    """Safely convert any input to bool."""
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ('1', 'true', 'yes', 'on')
    if isinstance(val, (int, float)):
        return val != 0
    return default


async def _handle_async_task(arguments: dict) -> Any:
    action = arguments.get("action", "list")
    handlers = {"start": async_tools.start_async_task, "status": async_tools.get_task_status,
                 "result": async_tools.get_task_result, "list": async_tools.list_tasks,
                 "cancel": async_tools.cancel_task}
    handler = handlers.get(action)
    if handler:
        return await handler(arguments)
    return {"error": f"Unknown action: {action}"}


async def _handle_code_hosting(arguments: dict) -> Any:
    try:
        if "action" not in arguments:
            return {"status": "failed", "message": "missing required parameter: action"}
        # Use asyncio.to_thread to avoid blocking the event loop with synchronous HTTP
        return await asyncio.to_thread(code_hosting, **arguments)
    except Exception as e:
        logger.error(f"code_hosting execution failed: {e}", exc_info=True)
        return {"status": "failed", "message": f"code_hosting failed: {e}"}


async def _handle_tool_help(arguments: dict) -> Any:
    return get_tool_help(
        tool_name=arguments.get("tool_name", ""),
        action=arguments.get("action", ""),
    )


async def _handle_experience(arguments: dict) -> dict:
    """Handle experience tool calls with asyncio timeout protection (30s)."""
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(_experience, **arguments),
            timeout=TIMEOUT_EXPERIENCE_TOOL,
        )
        return result
    except asyncio.TimeoutError:
        return {
            "status": "failed",
            "message": "experience operation timed out (30s); embedding model loading/download may be taking too long."
                " Suggestion: first call delphi_kb(action=build_embedding) to preload the model,"
                " then use experience semantic search.",
        }
    except Exception as e:
        return {"status": "failed", "message": f"experience failed: {e}"}


async def _handle_daofy_update(arguments: dict) -> dict:
    """Handle daofy_update tool calls (similar to code_hosting pattern: background async + scheduled retries)."""
    action = arguments.get("action", "check")
    task_manager = get_task_manager()

    # ── version: return synchronously, no network needed ──
    if action == "version":
        install_type = "git" if updater.is_git_installation() else "pip"
        return {
            "version": updater.get_current_version(),
            "install_type": install_type,
            "python": sys.version,
        }

    # ── check: first try quickly (synchronously); if it fails, submit a background retry task ──
    if action == "check":
        # 1. Check cache first
        cached = updater.get_cached_update_result()
        if cached is not None:
            install_type = "git" if updater.is_git_installation() else "pip"
            cached["install_type"] = install_type
            status_msg = (
                f"New version v{cached['latest']} found! (current v{cached['current']})"
                if cached.get("update_available")
                else f"Already up to date: v{cached['current']}"
            )
            return {**cached, "message": status_msg, "cache_hit": True}

        # 2. Quick synchronous attempt
        quick = await asyncio.get_running_loop().run_in_executor(
            None, updater.check_for_update
        )
        if quick is not None:
            install_type = "git" if updater.is_git_installation() else "pip"
            quick["install_type"] = install_type
            if quick["update_available"]:
                if install_type == "git":
                    quick["message"] = (
                        f"New version v{quick['latest']} found!"
                        f" Current version v{quick['current']}."
                        f" Suggestion: run daofy_update(action='update') to perform a git pull update."
                    )
                else:
                    quick["message"] = (
                        f"New version v{quick['latest']} found!"
                        f" Current version v{quick['current']}."
                        f" Please run: pip install --upgrade daofy-for-delphi"
                    )
            else:
                quick["message"] = f"Already up to date: v{quick['current']}"
            return quick

        # 3. Quick attempt failed; submit a background automatic retry task (similar to code_hosting git_push_retry)
        logger.info("Version check quick attempt failed; submitting background automatic retry task...")
        on_complete = arguments.get('_on_complete')
        task_id = task_manager.submit_task(
            name="version_check_retry",
            func=updater.check_for_update_retry,
            on_complete=on_complete,
            dedup_key="version_check_retry",
        )
        return {
            "task_id": task_id,
            "status": "async",
            "message": (
                "Quick check failed (network unreachable); a background automatic retry task has been submitted.\n"
                f"  Task ID: {task_id}\n"
                f"  Retry interval: {updater.RETRY_INTERVAL}s | Max {updater.MAX_RETRIES} times\n"
                "  Use async_task(action=status, task_id=...) to check progress."
            ),
        }

    # ── check_retry: force-submit a background automatic retry task (returns task_id) ──
    if action == "check_retry":
        on_complete = arguments.get('_on_complete')
        task_id = task_manager.submit_task(
            name="version_check_retry",
            func=updater.check_for_update_retry,
            on_complete=on_complete,
            dedup_key="version_check_retry",
        )
        return {
            "task_id": task_id,
            "status": "async",
            "message": (
                "Background version check task submitted.\n"
                f"  Task ID: {task_id}\n"
                f"  Retry interval: {updater.RETRY_INTERVAL}s | Max {updater.MAX_RETRIES} times\n"
                "  Use async_task(action=status, task_id=...) to check progress."
            ),
        }

    # ── update / update_retry: background git pull update ──
    if action in ("update", "update_retry"):
        if not updater.is_git_installation():
            return {
                "success": False,
                "message": (
                    "Currently in pip installation mode; git pull updates are not supported.\n"
                    "Please run manually: pip install --upgrade daofy-for-delphi"
                ),
            }

        on_complete = arguments.get('_on_complete')
        retry_interval = int(arguments.get("retry_interval", 60))
        max_retries = int(arguments.get("max_retries", 10))

        if action == "update_retry":
            # Custom retry parameters
            orig_interval = updater.UPDATE_RETRY_INTERVAL
            orig_max = updater.UPDATE_MAX_RETRIES
            updater.UPDATE_RETRY_INTERVAL = retry_interval
            updater.UPDATE_MAX_RETRIES = max_retries
            try:
                task_id = task_manager.submit_task(
                    name="git_update_retry",
                    func=updater._do_retry_update,
                    on_complete=on_complete,
                    dedup_key="git_update_retry",
                )
            finally:
                updater.UPDATE_RETRY_INTERVAL = orig_interval
                updater.UPDATE_MAX_RETRIES = orig_max
            eta_min = (retry_interval * max_retries) // 60
            return {
                "task_id": task_id,
                "status": "async",
                "message": (
                    "Background automatic retry git pull update task submitted.\n"
                    f"  Task ID: {task_id}\n"
                    f"  Retry interval: {retry_interval}s | Max {max_retries} times | Estimated max ~{eta_min}min\n"
                    "  Use async_task(action=status, task_id=...) to check progress."
                ),
            }

        # update (single attempt)
        task_id = task_manager.submit_task(
            name="git_update",
            func=updater.git_pull_update_sync,
            on_complete=on_complete,
        )
        return {
            "task_id": task_id,
            "status": "async",
            "message": (
                "Background git pull update task submitted.\n"
                f"  Task ID: {task_id}\n"
                "  Use async_task(action=status, task_id=...) to check progress."
            ),
        }

    return {"error": f"Unknown action: {action}"}


async def _handle_generate_copyright(arguments: dict) -> dict:
    """Handle generate_copyright tool calls."""
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(_generate_copyright, **arguments),
            timeout=TIMEOUT_GENERATE_COPYRIGHT,
        )
        return result
    except asyncio.TimeoutError:
        return {"status": "failed", "message": "generate_copyright execution timed out (300s)"}
    except Exception as e:
        return {"status": "failed", "message": f"generate_copyright failed: {e}"}


async def _handle_ocr(arguments: dict) -> dict:
    """Handle ocr tool calls (lazy import; return a friendly error when OCR dependencies are unavailable)."""
    try:
        from src.tools.ocr import handle_ocr as _ocr_handler
    except ImportError as e:
        return {
            "status": "failed",
            "error": (
                f"Missing OCR dependencies: {e}."
                "Please install the optional dependency: pip install daofy-for-delphi[ocr]"
            ),
        }
    return await asyncio.to_thread(_ocr_handler, arguments)


async def _handle_structured_content(arguments: dict) -> dict:
    """Unified read/write/search/modify for structured documents (DFM/LFM/FMX/XML/JSON/MessagePack/ProtoBuf)."""
    try:
        return await _sc_handler(arguments)
    except Exception as e:
        return {"status": "failed", "error": str(e)}


CORE_HANDLERS = {
    "async_task": _handle_async_task,
    "code_hosting": _handle_code_hosting,
    "tool_help": _handle_tool_help,
    "experience": _handle_experience,
    "daofy_update": _handle_daofy_update,
    "generate_copyright": _handle_generate_copyright,
    "ocr": _handle_ocr,
    "structured_content": _handle_structured_content,
}

# ── Tool descriptions + inputSchema — list_tools() collects from the registry, no longer hardcoded in server.py ──

CORE_TOOL_DESCRIPTIONS: dict[str, str] = {
    "async_task": "Async task management",
    "code_hosting": "Git operations and code hosting platform APIs. Parameters vary by action; before calling, run tool_help(tool_name='code_hosting', action='<action>').",
    "tool_help": "Get on-demand help documentation, parameter descriptions, and examples by tool name and optional action",
    "experience": "Experience memory management. Parameters vary by action; before calling, run tool_help(tool_name='experience', action='<action>').",
    "daofy_update": "Version update checking and git pull. Parameters vary by action; before calling, run tool_help(tool_name='daofy_update', action='<action>').",
    "generate_copyright": "Generate software copyright documents. Parameters vary by action; before calling, run tool_help(tool_name='generate_copyright', action='<action>').",
    "ocr": "Image analysis. Parameters vary by action; before calling, run tool_help(tool_name='ocr', action='<action>').",
    "structured_content": "Unified read/write/search/modify for structured documents — DFM/LFM/FMX/XML/JSON/MessagePack/ProtoBuf. Read/write by JSONPath and generate JSON Schema. Parameters vary by action; before calling, run tool_help(tool_name='structured_content', action='<action>').",
}

CORE_TOOL_SCHEMAS: dict[str, dict] = {
    "async_task": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["start", "status", "result", "list", "cancel"], "default": "list"},
            "task_id": {"type": "string", "description": "Task ID"},
            "long_poll_seconds": {
                "type": "integer",
                "description": "Long-polling wait seconds (optional; default 0 returns immediately. The MCP request channel has a timeout limit; ≤30 seconds is recommended)",
                "default": 0,
            },
        }
    },
    "code_hosting": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": [
                "create_token", "init_labels", "create_issue", "get_issue", "edit_issue",
                "set_labels", "close_issue", "add_comment", "list_issues",
                "create_pull", "get_pull", "list_pulls", "edit_pull", "merge_pull",
                "close_pull", "reopen_pull",
                "create_release", "get_release", "list_releases", "edit_release", "delete_release",
                "git_clone", "git_add", "git_commit", "git_push", "git_push_retry",
                "git_status", "git_diff", "git_show", "git_log",
                "git_fetch", "git_pull", "git_branch", "git_switch", "git_merge",
                "git_restore", "git_unstage", "git_stash", "git_tag",
            ]},
        },
        "required": ["action"]
    },
    "tool_help": {
        "type": "object",
        "properties": {
            "tool_name": {
                "type": "string",
                "enum": TOOL_NAMES,
            },
            "action": {
                "type": "string",
                "description": "Optional; return only the parameter descriptions and examples for the specified tool action",
            },
        },
        "required": ["tool_name"],
    },
    "experience": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["save", "search", "get", "list", "update", "merge", "prune", "delete", "rebuild_embedding"],
            },
        },
        "required": ["action"],
    },
    "daofy_update": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["check", "check_retry", "update", "update_retry", "version"],
                "default": "check",
            },
        },
        "required": ["action"],
    },
    "generate_copyright": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["generate", "validate", "update_config", "status", "list", "generate_content", "audit"],
                "default": "generate",
            },
        },
        "required": ["action"],
    },
    "ocr": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["recognize", "detect", "status", "diff", "color", "match"],
                "default": "recognize",
            },
        },
        "required": [],
    },
    "structured_content": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["read", "get_schema", "set", "search"],
                "description": "Operation type: read(read as JSON/Schema) / get_schema(generate JSON Schema) / set(modify by path) / search(search by JSONPath)",
                "default": "read",
            },
            "file_path": {
                "type": "string",
                "description": "File absolute path (required for read/set/search)",
            },
            "path": {
                "type": "string",
                "description": "JSONPath path, e.g. $.Form.Left or $..Button1, default $",
                "default": "$",
            },
            "value": {
                "type": "string",
                "description": "New value to set for set action",
            },
            "format": {
                "type": "string",
                "enum": ["dfm", "lfm", "fmx", "xml", "json", "msgpack", "protobuf"],
                "description": "Force format (default detected from extension)",
            },
            "output": {
                "type": "string",
                "enum": ["json", "schema", "both"],
                "description": "Output format for read action: json(default)/schema/both",
                "default": "json",
            },
            "proto_file": {
                "type": "string",
                "description": "When in ProtoBuf mode, pass the .proto file absolute path",
            },
            "message_name": {
                "type": "string",
                "description": "When in ProtoBuf mode, pass the message name",
            },
        },
        "required": ["action"],
    },
}