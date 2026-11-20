"""
Daofy main program

Copyright (C) Jilin Province ZuoYou Software Development Co., Ltd.
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
Update & Mod By Crystalxp (Night Killer QQ:281309196)

Provides MCP protocol services, registers all tools and starts the server
"""

import asyncio
import sys
import os
import time
import winreg
import logging as _logging
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Optional

import anyio

os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['PYTHONUTF8'] = '1'

# Guard: the stdout of child processes (multiprocessing spawn) is already piped,
# so TextIOWrapper may fail. Skipping on failure does not affect child process communication.
if __name__ != '__mp_main__':
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=False)
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace', line_buffering=False)
    except Exception:
        import logging as _logging
        _logger = _logging.getLogger(__name__)
        _logger.warning("Failed to set stdout/stderr encoding, some output may be garbled", exc_info=True)

# Add the project root directory to the Python path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


def _ensure_deps() -> None:
    """Check core dependencies before startup and auto pip install when missing (main process only, failure does not block).

    Uses importlib.util.find_spec to probe without triggering an actual import, avoiding side effects.
    """
    import subprocess
    import importlib.util

    # (module probe name, pip install spec)
    CORE: list[tuple[str, str]] = [
        ("zvec",      "zvec>=0.5.0"),
        ("chardet",   "chardet>=7.0"),
        ("mcp",       "mcp>=0.9.0"),
        ("pydantic",  "pydantic>=2.0.0"),
        ("bs4",       "beautifulsoup4>=4.12.0"),
        ("html2text", "html2text>=2024.2.25"),
        ("lxml",      "lxml>=4.9.0"),
        ("docx",      "python-docx>=0.8.11"),
        ("requests",  "requests>=2.31.0"),
    ]

    missing = [spec for mod, spec in CORE if importlib.util.find_spec(mod) is None]
    if not missing:
        return

    try:
        _logging.getLogger("daofy").info(
            "Missing dependencies, auto-installing: %s ...", ", ".join(missing)
        )
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--quiet", *missing],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=120,
        )
        _logging.getLogger("daofy").info("Dependency installation complete")
    except Exception as exc:
        _logging.getLogger("daofy").warning(
            "Failed to auto-install dependencies (%s), please run manually:  pip install -r requirements.txt", exc
        )


# Skip installation when a multiprocessing spawn child re-executes this file
if __name__ != "__mp_main__":
    _ensure_deps()

from src.constants import (
    REG_KEY_EMBARCADERO_BDS,
    TIMEOUT_AUTOMATION_GUI,
    TIMEOUT_EXPERIENCE_TOOL,
    TIMEOUT_GENERATE_COPYRIGHT,
)
from src.client_tool_policy import ensure_tool_visible, filter_tools
from src.utils.path_guard import validate_tool_paths


def _get_mcp_client_name(server_obj: Any) -> str | None:
    """Return ``initialize.clientInfo.name`` for the active MCP request."""
    try:
        session = get_server_session(server_obj)
        if session is None:
            return None
        def read_member(value: Any, name: str, default: Any = None) -> Any:
            if isinstance(value, dict):
                return value.get(name, default)
            return getattr(value, name, default)

        params = read_member(session, "client_params")
        if params is None:
            params = read_member(session, "_client_params")
        if params is None:
            return None
        client_info = read_member(params, "clientInfo")
        if client_info is None:
            client_info = read_member(params, "client_info")
        return read_member(client_info, "name")
    except Exception:
        return None

def _filter_surrogates(text: str) -> str:
    """Filter out invalid UTF-8 surrogate characters from a string.

    Surrogate characters (U+D800 to U+DFFF) are invalid in UTF-8 encoding
    and will cause Pydantic JSON serialization to fail. This function replaces
    them with the Unicode replacement character.

    Note: this function does not affect normal Unicode characters (such as
    Chinese, Japanese, Korean, emoji, etc.), because the Unicode ranges of
    those characters (U+0000-U+D7FF, U+E000-U+10FFFF) do not overlap at all
    with the range of surrogate characters (U+D800-U+DFFF).

    Common causes of surrogate characters appearing:
    1. A UTF-16 encoded string was mistakenly treated as UTF-8
    2. Some legacy Delphi components used a non-standard encoding
    3. Encoding detection error when reading a file

    Args:
        text: input string

    Returns:
        The filtered string, with all surrogate characters replaced
    """
    import re
    # Check whether surrogate characters are present
    surrogate_pattern = re.compile(r'[\ud800-\udfff]')
    if surrogate_pattern.search(text):
        # Log a warning to help debug encoding issues
        count = len(surrogate_pattern.findall(text))
        logger.warning(
            "Detected %d invalid UTF-8 surrogate characters, replaced with the replacement character. "
            "This may indicate that the source file encoding is incorrect.",
            count
        )
        return surrogate_pattern.sub('\ufffd', text)
    return text


MCP_SERVER_INSTRUCTIONS = (
    "DaofyCoding does not depend on this Server and uses the host-native automation_run and structured_content; this Server hides the duplicate tools. Daofy: Delphi files must be handled with delphi_file, and get_coding_rules comes before coding; before calling a complex tool, use tool_help(tool_name, action) to fetch the parameters of the current action"
)

MCP_SERVER_DESCRIPTION = (
    "Daofy for Delphi MCP Server: Delphi project compilation, knowledge base search, "
    "safe file read/write, automation testing and audit tools."
)

# ============================================================
# multiprocessing child process protection
# Under Windows spawn mode, the child process re-imports the __main__ module (i.e. this file),
# causing all service modules to be re-imported (885 modules) and startup to be extremely slow.
# When a child process is detected, skip all service imports and keep only the necessary modules.
# ============================================================
_is_multiprocessing_child = __name__ == '__mp_main__'

if _is_multiprocessing_child:
    # Child processes do not need any MCP services, so skip directly.
    # ProcessPoolExecutor workers only need to be able to pickle/unpickle functions.
    pass
else:

    from src.mcp_compat import (
        CompatibleServer,
        ReadResourceContents,
        stdio_server,
        CallToolResult,
        TextContent,
        Prompt,
        PromptArgument,
        PromptMessage,
        GetPromptResult,
        make_tool,
        make_resource,
        make_text_resource_contents,
        make_read_resource_result,
        call_tool_result_is_error,
        run_mcp_server,
        get_server_session,
    )

    from src.services.config_manager import ConfigManager
    from src.services.compiler_service import CompilerService
    from src.services.knowledge_base.zvec_adapter import ZVecKnowledgeBaseAdapter
    from src.services.knowledge_base.thirdparty_knowledge_base import ThirdPartyKnowledgeBase
    from src.services.agent_skill_installer import install_daofy_agent_skills
    from src.tools.project import handle_project as _handle_project
    # The project module manages the compiler service centrally; keep the alias for initialization
    from src.tools.compile_project import set_compiler_service as sp1
    from src.tools.compile_file import set_compiler_service as sp2
    from src.tools.get_args import set_compiler_service as sp3
    from src.tools.config import set_config_manager, search_compilers
    from src.tools.environment import check_environment, set_config_manager as scm, set_thirdparty_kb_service as stks
    from src.tools.knowledge_base import (
        set_delphi_kb_service,
        set_thirdparty_kb_service,
        _resolve_project_path,
    )
    from src.tools.read_source_file import set_knowledge_base_services, read_source_file
    from src.tools import knowledge_base as kb_tools
    from src.tools import thirdparty_knowledge_base as thirdparty_kb_tools
    from src.tools import async_tasks as async_tools
    from src.tools import pasfmt
    from src.tools.install_package import handle_package, set_compiler_service as sip
    from src.tools import document_kb_tools as doc_tools
    from src.tools.code_hosting import code_hosting
    from src.tools import file_tool
    from src.tools import dfm_utils as dfm_utils_mod
    from src.tools import manage_component as manage_component_mod
    from src.tools import create_component_dfm as create_component_dfm_mod
    from src.tools.coding_rules import get_coding_rules as _get_coding_rules
    from src.tools.tool_help import get_tool_help
    from src.tools.experience import experience as _experience
    from src.mcp_resources import (
        available_public_resources,
        build_public_resource_index,
        get_public_resource_text,
    )
    from src.tool_docs import TOOL_NAMES
    from src.utils.logger import init_default_logger, log_api_call
    from src.__version__ import __version__, __copyright__
    from src.utils import updater
    from src.services.knowledge_base.async_task_manager import get_task_manager
    from src.services.automation_service import (
    execute_automation as _execute_automation,
    detect_exe_subsystem as _detect_exe_subsystem,
    IMAGE_SUBSYSTEM_WINDOWS_GUI,
    IMAGE_SUBSYSTEM_WINDOWS_CUI,
)
    from src.tools.delphi_rtti import handle_delphi_rtti as _handle_delphi_rtti
    from src.services.copyright_service import generate_copyright as _generate_copyright
    # ocr uses a lazy import — it is imported only when the tool is called (to avoid a startup crash when onnxruntime is not installed)

    # Background version check result cache (filled by the startup async task)
    _update_check_result: Optional[dict] = None
    _update_check_done: bool = False

    # File change watcher (started by the startup async task)
    _project_file_watcher: Optional[object] = None

    # Server start time (used by the /health resource)
    _server_start_time: float = 0.0
    # Timestamp of the most recent KB build
    _last_kb_build_time: Optional[float] = None

    # Initialize logging
    logger = init_default_logger()

    # ============================================================
    # Plugin system (Phase 2: tool ownership + handler dispatch)
    # ============================================================
    from src.plugins.registry import PluginRegistry
    from src.plugins.delphi import DelphiPlugin
    from src.plugins.lazarus import LazarusPlugin

    _plugin_registry = PluginRegistry()
    _plugin_registry.register(DelphiPlugin())
    _plugin_registry.register(LazarusPlugin())

    logger.info(f"Registered plugins: {[p.info.name for p in _plugin_registry.get_all_plugins()]}")
    logger.info(f"Plugin extension mapping: {_plugin_registry.get_all_extensions()}")
    logger.info(f"Available plugin tools: {list(_plugin_registry.collect_tools())}")

    # Plugin tool ownership:
    #   delphi plugin owns: delphi_project, delphi_file, delphi_kb, manage_component,
    #                     get_coding_rules, package, check_environment, delphi_rtti, automate_delphi
    #   lazarus plugin owns: lazarus_compile, lazarus_project, lazarus_kb, lazarus_file
    #                    (registered only when lazbuild.exe is available, otherwise skipped)
    #   core owns: async_task, code_hosting, tool_help, experience, daofy_update,
    #            generate_copyright, ocr
    # All handlers have been extracted into the plugin modules (Phase 3 / Phase 5).


    async def _fetch_workspace_roots(session) -> None:
        """Asynchronously fetch the AI Agent workspace roots and cache them in file_tool.

        After session initialization completes, call session.list_roots() to get the
        workspace roots, convert the first valid file:// URI to a local path and cache it.
        If the client does not support roots or the call times out, skip silently.
        """
        try:
            # Wait for initialization to complete (roots/list can only be issued after the InitializedNotification arrives)
            await anyio.sleep(1.0)
            result = await session.list_roots()
            if not result or not result.roots:
                logger.info("Client did not provide a workspace root (roots is empty)")
                return

            for root in result.roots:
                uri = root.uri
                if uri.scheme == "file":
                    local_path = uri.path.rstrip("/\\")
                    if local_path and os.path.isdir(local_path):
                        from src.tools.file_tool import set_workspace_root
                        set_workspace_root(local_path)
                        from src.tools.read_source_file import set_workspace_root as set_read_source_workspace_root
                        set_read_source_workspace_root(local_path)
                        return
                    logger.info("Workspace root URI is not a valid directory: %s", uri)
                else:
                    logger.debug("Skipping non-file:// workspace root: %s", uri)

            logger.info("No valid file:// workspace root found")
        except anyio.EndOfStream:
            logger.debug("session already closed, skipping root retrieval")
        except Exception:
            logger.debug("Failed to fetch workspace roots (the client may not support roots) - skipping silently", exc_info=True)


    async def _install_client_rules(session) -> None:
        """Install the Daofy client rules into the rules directory of the connected MCP client.

        The client identity is only available after initialize, so this runs in a
        background task and does not block the handshake. Failure does not affect Server operation.
        """
        try:
            from src.services.client_rules_installer import install_client_rules

            client_params = getattr(session, "_client_params", None)
            outcome = install_client_rules(client_params)
            if outcome.get("message"):
                logger.info("[client-rules] %s", outcome["message"])
        except Exception:
            logger.info("Failed to install Daofy client rules (does not affect normal operation)", exc_info=True)


    async def _run_mcp_server(server, read_stream, write_stream) -> None:
        """Run the MCP server (version-adaptive, delegates to mcp_compat)."""
        logger.info("mcp_lifecycle event=server_run_started")
        await run_mcp_server(
            server,
            read_stream,
            write_stream,
            fetch_workspace_roots=_fetch_workspace_roots,
            install_client_rules=_install_client_rules,
        )
        logger.info("mcp_lifecycle event=run_mcp_server_returned")


def _auto_detect_delphi_help_dir() -> Optional[str]:
    """Automatically detect the help document directory of the most recently installed Delphi"""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY_EMBARCADERO_BDS)
        versions = []
        i = 0
        while True:
            try:
                versions.append(winreg.EnumKey(key, i))
                i += 1
            except OSError:
                break
        winreg.CloseKey(key)

        versions.sort(key=lambda x: float(x) if x.replace('.', '').isdigit() else 0, reverse=True)
        for ver in versions:
            try:
                vk = winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"{REG_KEY_EMBARCADERO_BDS}\\{ver}")
                root_dir = winreg.QueryValueEx(vk, "RootDir")[0]
                winreg.CloseKey(vk)
                help_dir = Path(root_dir) / "Help" / "Doc"
                if help_dir.exists():
                    logger.info(f"Auto-detected Delphi help directory (version {ver}): {help_dir}")
                    return str(help_dir)
            except Exception:
                logger.debug("Failed to read registry version key", exc_info=True)
                continue
    except Exception:
        logger.debug("Failed to open registry BDS key", exc_info=True)

    # Registry failed; try the default paths (version numbers match the registry: 37.0=Delphi13, 23.0=Delphi12, 22.0=Delphi11...)
    # Only 17.0 (XE) and later versions use this directory structure
    program_files_x86 = os.environ.get("ProgramFiles(x86)")
    if not program_files_x86:
        return None
    for ver in ["37.0", "23.0", "22.0", "21.0", "20.0", "19.0", "18.0", "17.0"]:
        path = Path(program_files_x86) / "Embarcadero" / "Studio" / ver / "Help" / "Doc"
        if path.exists():
            logger.info(f"Using default help directory: {path}")
            return str(path)
    return None
def _get_smart_hint(name: str, result: Any, arguments: dict) -> Optional[str]:
    """
    Smart hint: generate next-step suggestions based on tool name and result.

    Args:
        name: Tool name
        result: Tool return result (dict or CallToolResult)
        arguments: Call arguments

    Returns:
        Suggestion text, or None if no suggestion
    """
    if name == "delphi_kb":
        action = arguments.get("action", "search")
        if action == "search":
            if isinstance(result, dict):
                results = result.get('results') or result.get('data') or []
                if isinstance(results, list) and len(results) > 0:
                    return ("hint: use "
                            'delphi_file(action="read", file_path="...") to read full source')
        elif action == "stats":
            return ("hint: if KB data is stale, "
                    "use delphi_kb(action='build', kb_type='project') to rebuild")

    elif name == "get_coding_rules":
        # Only hint when section=None (default mode)
        section = arguments.get("section")
        if section is None or section == "":
            return ("hint: use section param for specific chapters:\n"
                    '   get_coding_rules(section="writing")  - before writing\n'
                    '   get_coding_rules(section="review")   - after compile, before review\n'
                    '   get_coding_rules(section="safety")   - security-sensitive ops')

    elif name == "check_environment":
        action = arguments.get("action", "check")
        if action == "detect" or action == "check":
            if isinstance(result, dict):
                compilers = result.get('compilers') or result.get('data')
                if compilers and len(compilers) > 0:
                    return ("hint: environment ready, "
                            "use delphi_project(action='compile') to verify")
                else:
                    return ("hint: no compiler detected, "
                            "check Delphi installation, "
                            "or use check_environment(action='detect', search_path=...)")

    elif name == "delphi_project":
        action = arguments.get("action", "")
        if action == "compile":
            # Determine whether compilation succeeded
            is_success = False
            if isinstance(result, CallToolResult):
                is_success = not call_tool_result_is_error(result)
            elif isinstance(result, dict):
                is_success = (
                    result.get('status') != 'failed'
                    and result.get('success') is not False
                )
            if is_success:
                return (
                    "Compilation passed ✅ — subsequent workflow steps (execute in order):\n"
                    "  1️⃣  Code review: get_coding_rules(section=\"review\")\n"
                    "  2️⃣  Cleanup: remove unused variables/imports/dead code\n"
                    "  3️⃣  automate_delphi tests: tool_help(tool_name=\"automate_delphi\")\n"
                    "  4️⃣  Experience capture: experience(action=\"suggest\") → save"
                )

    elif name == "package":
        action = arguments.get("action", "")
        if action == "install":
            if isinstance(result, CallToolResult):
                is_error = call_tool_result_is_error(result)
            elif isinstance(result, dict):
                is_error = (
                    result.get('status') == 'failed'
                    or result.get('success') is False
                    or (result.get('error') is not None and result.get('error') != '')
                )
            else:
                is_error = False
            if not is_error:
                return ("hint: install done, "
                        "use package(action='list') to verify IDE registration")

    # P4: Version update hint (notify AI when check is done and a new version exists)
    if _update_check_done and _update_check_result and _update_check_result.get("update_available"):
        return (
            f"📦 New Daofy version found: v{_update_check_result['current']} → "
            f"v{_update_check_result['latest']}!\n"
            f"Use `daofy_update(action=\"check\")` for details, "
            f"or `daofy_update(action=\"update\")` to update via git pull.\n"
            f"Release notes: {_update_check_result['release_url']}"
        )

    return None


# ============================================================
# Delphi file read/write footnote — remind AI to use the delphi_file tool
# ============================================================
# The following tools append a footnote to their results, preventing AI from
# bypassing delphi_file to directly read/write .pas/.dfm files
def _redact_env_argument(value: Any) -> Any:
    """Return a log-safe summary for env/environment argument values."""
    if not isinstance(value, dict):
        return "<redacted-env>"
    return {
        "count": len(value),
        "names": sorted(str(key) for key in value),
    }


def _redact_sensitive_arguments(value: Any) -> Any:
    """Recursively redact sensitive values from tool-call arguments."""
    if isinstance(value, dict):
        redacted: dict = {}
        for key, item in value.items():
            if str(key) in {"env", "environment"}:
                redacted[key] = _redact_env_argument(item)
            else:
                redacted[key] = _redact_sensitive_arguments(item)
        return redacted
    if isinstance(value, list):
        return [_redact_sensitive_arguments(item) for item in value]
    return value


_DELPHI_FILE_FOOTNOTE_TOOLS: set = {
    "delphi_file",
    "delphi_kb",
    "delphi_project",
    "manage_component",
    "check_environment",
    "get_coding_rules",
    "code_hosting",
}


_DELPHI_FILE_FOOTNOTE_TEXT = (
    "\n\n---\n"
    "⚠️ Delphi files must be read/written/searched/regex-matched+replaced using `delphi_file`, "
    "do not use built-in Read/Edit/Write/grep."
)

# action → set of operations that need the footnote
_DELPHI_FILE_FOOTNOTE_ACTIONS: dict[str, set[str]] = {
    "delphi_kb":          {"search", "read", "stats"},
    "delphi_project":     {"info", "ast", "audit", "compile", "compile_file", "devices", "deploy"},
    "check_environment":  {"detect"},
    "code_hosting":       {"git_clone", "git_pull", "git_merge", "git_switch"},
}


def _get_delphi_file_footnote(name: str, arguments: dict) -> Optional[str]:
    """Return a footnote for tools that may involve Delphi file operations, reminding to use delphi_file."""
    if name not in _DELPHI_FILE_FOOTNOTE_TOOLS:
        return None
    # manage_component, get_coding_rules, delphi_file have no action restriction
    if name in ("manage_component", "get_coding_rules", "delphi_file"):
        return _DELPHI_FILE_FOOTNOTE_TEXT
    action = arguments.get("action", "")
    if name in _DELPHI_FILE_FOOTNOTE_ACTIONS and action in _DELPHI_FILE_FOOTNOTE_ACTIONS[name]:
        return _DELPHI_FILE_FOOTNOTE_TEXT
    return None


def _build_mcp_resource_list(root: Path = project_root) -> list:
    """Build MCP Resource objects exposed by Daofy."""
    resources = [
        make_resource(
            uri="delphi://resources",
            name="resources",
            title="Daofy public resource index",
            description="Index of stable Daofy MCP resource URIs for AI agents.",
            mime_type="text/markdown",
        )
    ]
    for spec in available_public_resources(root):
        resources.append(make_resource(
            uri=spec.uri,
            name=spec.name,
            title=spec.title,
            description=spec.description,
            mime_type=spec.mime_type,
        ))
    resources.append(make_resource(
        uri="delphi://health",
        name="health",
        title="Daofy server status",
        description="Health check info such as server running status, version, and file watcher status",
        mime_type="application/json"
    ))
    return resources


def _compute_uptime_seconds(start_time: float) -> float:
    """Return non-negative uptime for monotonic and legacy epoch start times."""
    if start_time <= 0:
        return 0.0

    monotonic_now = time.monotonic()
    uptime = monotonic_now - start_time
    if uptime < 0:
        uptime = time.time() - start_time
    return max(0.0, uptime)


def _read_mcp_resource(uri: str, root: Path = project_root):
    """Read one MCP Resource exposed by Daofy."""
    from pydantic import AnyUrl  # lazy import to avoid extra loading at startup

    uri = str(uri)

    if uri == "delphi://resources":
        return make_read_resource_result(
            contents=[make_text_resource_contents(
                uri=AnyUrl(uri),
                mime_type="text/markdown",
                text=build_public_resource_index(root),
            )]
        )

    if uri.startswith("delphi://automation/") or uri == "delphi://coding-rules":
        try:
            mime_type, content = get_public_resource_text(uri, root)
            return make_read_resource_result(
                contents=[make_text_resource_contents(
                    uri=AnyUrl(uri),
                    mime_type=mime_type,
                    text=content
                )]
            )
        except FileNotFoundError as e:
            return make_read_resource_result(
                contents=[make_text_resource_contents(
                    uri=AnyUrl(uri),
                    mime_type="text/plain",
                    text=str(e),
                )]
            )
        except KeyError:
            pass

    if uri == "delphi://health":
        import json as _json
        uptime = _compute_uptime_seconds(_server_start_time)
        watcher_running = (
            _project_file_watcher is not None
        ) if '_project_file_watcher' in globals() else False
        health = {
            "version": __version__,
            "uptime_seconds": round(uptime, 1),
            "uptime": f"{int(uptime // 3600)}h{int((uptime % 3600) // 60)}m{int(uptime % 60)}s",
            "file_watcher_active": watcher_running,
        }
        try:
            from src.services.delphi_edit_guard import snapshot_status
            health["edit_guard"] = snapshot_status()
        except Exception as e:
            health["edit_guard"] = {
                "enabled": False,
                "error": str(e),
            }
        return make_read_resource_result(
            contents=[make_text_resource_contents(
                uri=AnyUrl(uri),
                mime_type="application/json",
                text=_json.dumps(health, ensure_ascii=False, indent=2)
            )]
        )

    raise ValueError(f"Unknown resource: {uri}")


def _read_mcp_resource_contents(uri: str, root: Path = project_root) -> list:
    """Read one resource in the shape expected by mcp.server.Server."""
    result = _read_mcp_resource(uri, root)
    return [
        ReadResourceContents(
            content=content.text,
            mime_type=getattr(content, "mime_type", None)
            or getattr(content, "mimeType", None),
        )
        for content in result.contents
    ]
async def run_server():
    """Run MCP Server"""
    global _server_start_time
    _server_start_time = time.monotonic()
    logger.info(f"Starting Daofy v{__version__}")
    logger.info(f"{__copyright__}")

    # Version banner output to stderr (keep MCP stdout pure for JSON-RPC).
    # Logs (including runtime logs) are written to file only by default; console only shows version info;
    # for full console logging, set console_logging=true in config/logging_config.json.
    print(f"Daofy v{__version__}", file=sys.stderr, flush=True)
    print(f"{__copyright__}", file=sys.stderr, flush=True)

    # Best-effort sync of Daofy Agent Skill. Failure does not affect MCP Server startup.
    try:
        install_daofy_agent_skills()
    except Exception:
        logger.warning("Failed to sync Daofy Agent Skill (does not affect normal operation)", exc_info=True)

    # Initialize config manager
    config_manager = ConfigManager()
    logger.info("Config manager initialized")

    # Initialize compilation service
    compiler_service = CompilerService(config_manager)
    logger.info("Compilation service initialized")

    # Initialize knowledge base service (ZVec engine)
    # Shares the same version filtering strategy as RTL/third-party library paths (resolve_delphi_source_dirs);
    # startup defaults to official sources of all installed versions; builds can filter by version via the version parameter.
    from src.utils.delphi_env import resolve_delphi_source_dirs
    delphi_source_dirs = resolve_delphi_source_dirs()

    kb_dir = str(Path(__file__).parent.parent / "data" / "delphi-knowledge-base")
    kb_service = ZVecKnowledgeBaseAdapter(kb_dir, source_dirs=delphi_source_dirs)
    logger.info(f"ZVec knowledge base initialized (source dirs: {delphi_source_dirs})")

    # Initialize third-party library knowledge base service
    thirdparty_kb_service = ThirdPartyKnowledgeBase()
    thirdparty_kb_tools.set_thirdparty_knowledge_base_service(thirdparty_kb_service)
    logger.info("Third-party library knowledge base service initialized")

    # Set service instances for tools
    sp1(compiler_service)
    sp2(compiler_service)
    sp3(compiler_service)
    sip(compiler_service)
    scm(config_manager)
    set_config_manager(config_manager)
    stks(thirdparty_kb_service)
    set_knowledge_base_services(kb_service, thirdparty_kb_service)
    set_delphi_kb_service(kb_service)
    # Project KB service is created dynamically via project_path parameter, not initialized at startup
    # set_project_kb_service(kb_service)  # kb_service is Delphi RTL KB, not suitable as project KB
    set_thirdparty_kb_service(thirdparty_kb_service)

    # Set DFM tool compiler path
    newest = config_manager.get_newest_compiler()
    if newest and newest.path:
        if os.path.isfile(newest.path):
            dfm_utils_mod.set_compiler_path(newest.path)
            create_component_dfm_mod.set_compiler_path(newest.path)
            logger.info(f"DFM tool compiler path set: {newest.path}")
        else:
            logger.warning("Compiler file does not exist: %s, DFM conversion will be unavailable. Please re-detect the compiler.", newest.path)
    else:
        logger.warning("No available compiler found, DFM conversion will be unavailable")

    # Set KB service references for event signature parser
    from src.tools.dfm_parser import set_kb_services as _set_dfm_kb
    _set_dfm_kb(delphi_kb=kb_service, thirdparty_kb=thirdparty_kb_service)

    logger.info("Tool service instances set")

    # Create MCP Server instance
    server = CompatibleServer(
        "daofy-for-delphi",
        version=__version__,
        instructions=MCP_SERVER_INSTRUCTIONS,
    )
    logger.info("MCP Server instance created")

    # ============================================================
    # MCP tool registration
    # All tools must be registered in both list_tools() and call_tool()
    # ============================================================
    @server.list_tools()
    async def list_tools():
        """List all available tools (schemas are registered by plugin handler modules, collected uniformly by registry)"""
        client_name = _get_mcp_client_name(server)
        return [
            make_tool(
                name=td.name,
                description=td.description,
                input_schema=td.input_schema,
            )
            for td in filter_tools(_plugin_registry.collect_tools(), client_name)
        ]

    # Register core + Delphi + Lazarus handler modules (handler + description + schema registered at once)
    from src.plugins.core.handlers import CORE_HANDLERS, CORE_TOOL_DESCRIPTIONS, CORE_TOOL_SCHEMAS
    from src.plugins.delphi.handlers import DELPHI_HANDLERS, DELPHI_TOOL_DESCRIPTIONS, DELPHI_TOOL_SCHEMAS
    from src.plugins.lazarus.handlers import LAZARUS_HANDLERS, LAZARUS_TOOL_DESCRIPTIONS, LAZARUS_TOOL_SCHEMAS

    _plugin_registry.register_handlers(
        CORE_HANDLERS, CORE_TOOL_DESCRIPTIONS, CORE_TOOL_SCHEMAS,
    )
    _plugin_registry.register_handlers(
        DELPHI_HANDLERS, DELPHI_TOOL_DESCRIPTIONS, DELPHI_TOOL_SCHEMAS,
        owner="delphi", aliases={"file_tool"},
    )
    _plugin_registry.register_handlers(
        LAZARUS_HANDLERS, LAZARUS_TOOL_DESCRIPTIONS, LAZARUS_TOOL_SCHEMAS,
        owner="lazarus",
    )

    @server.call_tool()
    async def call_tool(name: str, arguments: dict):
        """Invoke tool (dispatched by _plugin_registry)"""
        import time as _time
        from datetime import datetime as _datetime
        import asyncio as _asyncio

        _call_start = _time.monotonic()
        _call_start_dt = _datetime.now()

        logger.info(f"Invoking tool: {name}")
        result = None

        try:
            ensure_tool_visible(name, _get_mcp_client_name(server))
            path_error = validate_tool_paths(name, arguments)
            if path_error:
                raise ValueError(path_error)
            handler = _plugin_registry.get_handler(name)
            if handler:
                # ── MCP push notification injection ──
                # For tools supporting async tasks like code_hosting, inject _on_complete callback
                # Automatically push TaskStatusNotification to MCP client on task completion, no polling needed
                try:
                    from mcp.types import (
                        TaskStatusNotification, TaskStatusNotificationParams,
                    )
                    _session = get_server_session(server)
                    _loop = _asyncio.get_running_loop()

                    def _make_on_complete(session, loop):
                        def _on_complete(task_info):
                            """Background task completion callback — pushes TaskStatusNotification"""
                            # Map local TaskStatus → MCP Literal status values
                            status_map = {
                                'COMPLETED': 'completed',
                                'FAILED': 'failed',
                                'CANCELLED': 'cancelled',
                            }
                            ts = task_info.status.name  # e.g. 'COMPLETED'
                            mcp_status = status_map.get(ts, 'completed')
                            # Ensure datetime type
                            created = task_info.created_at
                            updated = task_info.completed_at or _datetime.now()

                            notif = TaskStatusNotification(
                                params=TaskStatusNotificationParams(
                                    taskId=task_info.task_id,
                                    status=mcp_status,
                                    statusMessage=task_info.message[:500] if task_info.message else None,
                                    createdAt=created,
                                    lastUpdatedAt=updated,
                                    ttl=3600000,  # 1 hour retention
                                )
                            )
                            # Schedule from background thread to asyncio event loop
                            asyncio.run_coroutine_threadsafe(
                                session.send_notification(notif),
                                loop
                            )
                        return _on_complete

                    arguments['_on_complete'] = _make_on_complete(_session, _loop)
                except (LookupError, AttributeError, ImportError) as _ctx_err:
                    logger.debug(f"Unable to inject MCP push callback: {_ctx_err}")
                    # Silently skip in non-MCP environments (e.g. tests) or without request_context

                result = await handler(arguments)
            else:
                raise ValueError(f"Unknown tool: {name}")

            # Calculate call duration
            _call_end = _time.monotonic()
            _call_end_dt = _datetime.now()
            _duration = _call_end - _call_start

            # P2: Smart hint
            hint = _get_smart_hint(name, result, arguments)
            if hint:
                if isinstance(result, CallToolResult):
                    if result.content and hasattr(result.content[0], 'text'):
                        result.content[0].text = result.content[0].text + "\n\n" + hint
                elif isinstance(result, dict):
                    msg = result.get('message', '')
                    if isinstance(msg, str):
                        result['message'] = msg + "\n\n" + hint

            # P2b: Delphi file read/write footnote
            footnote = _get_delphi_file_footnote(name, arguments)
            if footnote:
                if isinstance(result, CallToolResult):
                    if result.content and hasattr(result.content[0], 'text'):
                        # Avoid duplicate addition (will be embedded again during later serialize)
                        result.content[0].text = result.content[0].text + footnote
                elif isinstance(result, dict):
                    msg = result.get('message', '')
                    if isinstance(msg, str):
                        result['message'] = msg + footnote

            # P3: API call log (exclude injected _on_complete callback to prevent json.dumps serialization errors on functions)
            _log_args = _redact_sensitive_arguments(
                {k: v for k, v in arguments.items() if k != '_on_complete'}
            )
            log_api_call(logger, name, _log_args, result)

            import json as _json
            _show_timing = config_manager.get_show_timing()
            # Uniformly extract data: dict→use directly, CallToolResult→extract TextContent text
            if isinstance(result, dict):
                data = result
                is_error = (result.get('status') == 'failed'
                            or result.get('success') is False
                            or (result.get('error') is not None and result.get('error') != ''))
            elif isinstance(result, CallToolResult):
                extracted = None
                if result.content and len(result.content) > 0:
                    ct = result.content[0]
                    if hasattr(ct, 'text'):
                        extracted = ct.text
                if extracted is not None:
                    try:
                        parsed = _json.loads(extracted)
                        if isinstance(parsed, dict):
                            data = {k: v for k, v in parsed.items() if v is not None}
                        else:
                            data = extracted
                    except (_json.JSONDecodeError, TypeError):
                        data = extracted
                else:
                    data = str(result)
                is_error = call_tool_result_is_error(result)
            elif isinstance(result, (str, bytes)):
                data = result
                is_error = False
            else:
                data = str(result)
                is_error = False

            response = {'success': not is_error, 'data': data}
            if isinstance(result, CallToolResult):
                response['isError'] = is_error
            if _show_timing and isinstance(data, dict):
                response['timing'] = {
                    'duration': round(_duration * 1000, 1),
                    'startTime': _call_start_dt.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3],
                    'endTime': _call_end_dt.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3],
                }
            if isinstance(response, (dict, list)):
                try:
                    text = _json.dumps(response, ensure_ascii=False, indent=2, default=str)
                except (TypeError, ValueError):
                    text = str(response)
            else:
                text = str(response)
            # Filter invalid UTF-8 surrogate pair characters to prevent Pydantic JSON serialization failure
            text = _filter_surrogates(text)
            if hasattr(CallToolResult, "is_error"):
                result = CallToolResult(
                    content=[TextContent(type="text", text=text)], is_error=is_error
                )
            else:
                result = CallToolResult(
                    content=[TextContent(type="text", text=text)], isError=is_error
                )
            return result

        except Exception as e:
            _call_end = _time.monotonic()
            _call_end_dt = _datetime.now()
            _duration = _call_end - _call_start
            error_result = {
                "error": str(e),
                "timing": {
                    'duration': round(_duration * 1000, 1),
                    'startTime': _call_start_dt.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3],
                    'endTime': _call_end_dt.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3],
                }
            }
            log_api_call(logger, name, _redact_sensitive_arguments(arguments), {"error": str(e)})
            logger.error(f"Tool call failed: {str(e)}", exc_info=True)
            import json as _json
            return CallToolResult(
                content=[TextContent(type="text", text=_json.dumps(error_result, ensure_ascii=False, indent=2))],
                isError=True
            )

    # Register MCP resources

    @server.list_resources()
    async def list_resources():
        """List available resources"""
        return _build_mcp_resource_list(project_root)

    @server.read_resource()
    async def read_resource(uri: str):
        """Read resource content"""
        return _read_mcp_resource_contents(uri, project_root)

    # ============================================================
    # MCP prompt registration
    # Prompt templates for automation test workflow
    # ============================================================

    @server.list_prompts()
    async def list_prompts():
        """List all available prompt templates"""
        return [
            Prompt(
                name="automate-expert-primer",
                description="🎭 Inject test expert role: set identity, thinking framework, three-tier progressive thinking model",
                arguments=[
                    PromptArgument(
                        name="app_name",
                        description="Name of the Delphi application under test",
                        required=False,
                    ),
                    PromptArgument(
                        name="project_path",
                        description="Project path (for subsequent code analysis)",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="automate-code-analysis",
                description="🔍 Code-aware analysis: read target unit's DFM/PAS, generate control mapping table, event analysis, test paths",
                arguments=[
                    PromptArgument(
                        name="form_name",
                        description="Target Form/Frame class name (e.g., TNewCustomerForm)",
                        required=True,
                    ),
                    PromptArgument(
                        name="project_path",
                        description="Project path (passed to delphi_kb to search code)",
                        required=True,
                    ),
                    PromptArgument(
                        name="app_path",
                        description="Delphi application exe path (optional, for subsequent automation)",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="automate-test-plan",
                description="Start automation test planning: role setup + code analysis + structured step sequence",
                arguments=[
                    PromptArgument(
                        name="goal",
                        description="Test goal description (e.g., 'New Customer - Success Path')",
                        required=True,
                    ),
                    PromptArgument(
                        name="app_path",
                        description="Delphi application exe path",
                        required=False,
                    ),
                    PromptArgument(
                        name="project_path",
                        description="Project path (for code analysis)",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="automate-step-execute",
                description="Single-step automation execution protocol: pre-perception → execute → wait → verify",
                arguments=[
                    PromptArgument(
                        name="phase",
                        description="Step phase: perceive / execute / verify",
                        required=True,
                    ),
                    PromptArgument(
                        name="tool",
                        description="Tool/command name (e.g., goto+click, capture, waitfor, rcall)",
                        required=True,
                    ),
                    PromptArgument(
                        name="target",
                        description="Operation target (control name/coordinates/file path)",
                        required=True,
                    ),
                    PromptArgument(
                        name="expected",
                        description="Expected result description",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="automate-failure-recover",
                description="Automation test failure recovery: diagnose → decide → recover → learn",
                arguments=[
                    PromptArgument(
                        name="signal",
                        description="Failure signal: timeout / click_error / unexpected_dialog / rtti_exception / ocr_mismatch",
                        required=True,
                    ),
                    PromptArgument(
                        name="expected",
                        description="Expected result",
                        required=False,
                    ),
                    PromptArgument(
                        name="actual",
                        description="Actual result",
                        required=False,
                    ),
                ],
            ),
            Prompt(
                name="automate-save-experience",
                description="Save experience to knowledge base after test completion: structured recording of success/failure patterns",
                arguments=[],
            ),
            Prompt(
                name="automate-session-end",
                description="End test session: save experience, export script, switch role back to development mode",
                arguments=[
                    PromptArgument(
                        name="save_experience",
                        description="Whether to save test experience (true/false, default true)",
                        required=False,
                    ),
                    PromptArgument(
                        name="export_script",
                        description="Whether to export test script to tests/scripts/ (true/false, default true)",
                        required=False,
                    ),
                ],
            ),
        ]

    @server.get_prompt()
    async def get_prompt(name: str, arguments: dict[str, str] | None) -> GetPromptResult:
        """Get content of specified prompt template"""
        args = arguments or {}

        if name == "automate-expert-primer":
            app_name = args.get("app_name", "Delphi application under test")
            project_path = args.get("project_path", "")
            proj_line = f"\nProject path: `{project_path}`" if project_path else ""
            return GetPromptResult(
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text=(
                                f"## Role Setup: Delphi UI Automation Test Expert\n\n"
                                f"You are a **Delphi UI Automation Test Expert**."
                                f"Application under test: **{app_name}**{proj_line}\n\n"
                                f"### Your Core Methodology\n\n"
                                f"**Perceive → Plan → Execute → Feedback (loop)**\n\n"
                                f"### Three-Tier Progressive Thinking Model\n\n"
                                f"**Tier 1: Understand the system under test (code perception)**\n"
                                f"Before operating any control, first read the source code to understand it:\n"
                                f"- Read `.dfm` → understand control layout, type, name, event bindings\n"
                                f"- Read `.pas` → understand event handlers, validation logic, data flow\n"
                                f"- Use `delphi_kb` to query API → understand framework behavior\n"
                                f"- Output: control mapping table + event handler analysis + code branch path table\n\n"
                                f"**Tier 2: Generate test strategy (planning)**\n"
                                f"Based on source code understanding, determine:\n"
                                f"- Which paths to cover — every event handler + every code branch\n"
                                f"- Which tools to use — RTTI(`rcall`) > control-level(`goto+click`) > coordinate-level(`move+click`)\n"
                                f"- Expected results — assertions derived from code logic (e.g., `ModalResult := mrOk` → window should close)\n"
                                f"- Boundary conditions — extracted from validation code (`if edtName.Text=''` → test empty value)\n\n"
                                f"**Tier 3: Execute-Verify Loop (execution)**\n"
                                f"Strictly follow perceive→execute→verify loop for each step:\n"
                                f"- Perceive first (`capture`/`dumpstate`/`msgscan`), never assume UI state\n"
                                f"- One verify per step, stop on failure\n"
                                f"- Handle dialogs first — `msgscan` immediately after operation\n"
                                f"- On failure: diagnose→decide→recover→learn\n\n"
                                f"---\n"
                                f"Before starting, please first read MCP Resource `delphi://automation/workflow`,"
                                f"then execute `get_coding_rules(section=\"automation\")` "
                                f"to load complete methodology and prompt templates."
                            ),
                        ),
                    ),
                ]
            )

        if name == "automate-code-analysis":
            form_name = args.get("form_name", "")
            project_path = args.get("project_path", "")
            app_path = args.get("app_path", "")
            app_hint = f"\nApplication path: `{app_path}`" if app_path else ""
            return GetPromptResult(
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text=(
                                f"## Code Perception Analysis\n\n"
                                f"Target class: **{form_name}**\n"
                                f"Project path: `{project_path}`{app_hint}\n\n"
                                f"Please analyze the source code according to the following process and output test paths:\n\n"
                                f"### Step 1: Locate target code\n"
                                f"```\n"
                                f"delphi_kb(query=\"{form_name}\", search_type=\"class\", "
                                f"kb_type=\"project\", project_path=\"{project_path}\")\n"
                                f"delphi_file(action=\"read\", search_type=\"class\", "
                                f"type_name=\"{form_name}\", search_in=\"project\", "
                                f"project_path=\"{project_path}\")\n"
                                f"```\n\n"
                                f"### Step 2: Analyze DFM control structure\n"
                                f"Read the `.dfm` file and list:\n"
                                f"- Names, types, and event bindings of all controls\n"
                                f"- Key initial states (Visible, Enabled, ReadOnly, MaxLength, etc.)\n"
                                f"- Output: control mapping table\n\n"
                                f"### Step 3: Analyze PAS event handlers\n"
                                f"For each bound event handler, analyze:\n"
                                f"- Code paths: `if`/`case`/`try` branches\n"
                                f"- Validation logic: code checking empty values, ranges, formats\n"
                                f"- Business operations: data creation, DB writes, window closing, etc.\n"
                                f"- Output: event handler analysis table\n\n"
                                f"### Step 4: Derive test paths\n"
                                f"Following the mapping rules from code to test paths, output:\n\n"
                                f"| # | Path | Operation | Code-derived assertion |\n"
                                f"|---|------|------|--------------|\n"
                                f"| 1 | Success path | ... | ... |\n"
                                f"| 2 | Empty value path | ... | ... |\n"
                                f"| 3 | Boundary value | ... | ... |\n"
                                f"| 4 | Exception path | ... | ... |\n"
                                f"| ... | ... | ... | ... |\n\n"
                                f"### Step 5 (optional): Integrate into test planning\n"
                                f"Use `prompts/get automate-test-plan` to embed analysis results into complete test planning.\n\n"
                                f"For the complete script generation process, see MCP Resource "
                                f"`delphi://automation/script-generation-workflow`,"
                                f"methodology see `get_coding_rules(section=\"automation\")` §H"
                            ),
                        ),
                    ),
                ]
            )

        if name == "automate-test-plan":
            goal = args.get("goal", "no test goal specified")
            app_path = args.get("app_path", "")
            project_path = args.get("project_path", "")
            app_line = f"\nApplication path: `{app_path}`" if app_path else ""
            proj_line = f"\nProject path: `{project_path}`" if project_path else ""
            code_analysis_step = (
                f"\n\n### Stage 0 (preliminary): Code perception analysis\n"
                f"Before perceiving the UI, first read the source code to understand the functionality under test:\n"
                f"- Use `automate-code-analysis` prompt to analyze target unit's DFM + PAS\n"
                f"- Obtain control mapping table + event handler analysis + code-derived assertions\n"
                f"- These analysis results will directly guide subsequent planning steps"
            ) if project_path else ""

            return GetPromptResult(
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text=(
                                f"## Automation Test Planning\n\n"
                                f"**Goal**: {goal}{app_line}{proj_line}\n\n"
                                f"Role: You are a **Delphi UI Automation Test Expert**."
                                f"Work according to the three-tier progressive model: code perception → strategy planning → execution verification.\n"
                                f"For complete role definition, see `get_coding_rules(section=\"automation\")` §F0\n"
                                f"For code perception methodology, see §H\n{code_analysis_step}"
                                f"\n\n### Stage 1: Load methodology\n"
                                f"Read `delphi://automation/script-generation-workflow`, and execute "
                                f"`get_coding_rules(section=\"automation\")` to obtain the complete"
                                f"perceive·plan·execute·feedback architecture, prompt templates (F), and experience optimization loop (G)\n\n"
                                f"### Stage 2: Retrieve experience\n"
                                f"```\n"
                                f"experience(action=\"search\", query=\"{goal}\", top_k=3)\n"
                                f"```\n\n"
                                f"### Stage 3: Perceive current state\n"
                                f"Use `capture` / `dumpstate` / `listwnd` / `msgscan` "
                                f"to understand current UI state\n\n"
                                f"### Stage 4: Plan step sequence\n"
                                f"Output a structured step table, with assertions derived from code logic:\n\n"
                                f"| # | Stage | Tool | Target | Expected result | Timeout | Failure handling |\n"
                                f"|---|------|------|------|---------|------|---------|\n"
                                f"| 0 | code | delphi_kb/delphi_file | Read source analysis | Control mapping table | — | — |\n"
                                f"| 1 | perceive | capture/dumpstate | Initial state | Main window opened | 5s | Report |\n"
                                f"| 2 | execute | goto+click | Operation target | Code-derived assertion | 10s | capture→analyze |\n"
                                f"| 3 | verify | waitfor+rget | Verification result | Consistent with code logic | 5s | Downgrade RTTI |\n"
                                f"| ... | ... | ... | ... | ... | ... | ... |\n\n"
                                f"### Stage 5: Execute after confirmation\n"
                                f"Strictly follow the `perceive→execute→verify` loop for each step, stop on failure and do not continue subsequent steps\n\n"
                                f"For detailed templates, see MCP Resource `delphi://automation/script-schema` "
                                f"and `get_coding_rules(section=\"automation\")` §F1"
                            ),
                        ),
                    ),
                ]
            )

        if name == "automate-step-execute":
            phase = args.get("phase", "")
            tool = args.get("tool", "")
            target = args.get("target", "")
            expected = args.get("expected", "Unspecified")
            return GetPromptResult(
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text=(
                                f"## Single-Step Automation Execution\n\n"
                                f"**Phase**: {phase}\n"
                                f"**Tool**: {tool}\n"
                                f"**Target**: {target}\n"
                                f"**Expected**: {expected}\n\n"
                                f"### Execution Protocol\n\n"
                                f"1. **Pre-perception** — `msgscan` to check for dialogs; if necessary, use `capture`/`dumpstate` to confirm current state\n"
                                f"2. **Execute** — call `{tool}` to operate on `{target}`\n"
                                f"   - Synchronous command → check return code\n"
                                f"   - Asynchronous command → record that operation has been initiated\n"
                                f"3. **Wait** — for asynchronous commands use `wait(500~2000)` or `waitfor(control, 10000)`\n"
                                f"4. **Verify** — `msgscan` to confirm no dialog; `capture`/`rget`/`ocr` to confirm result\n"
                                f"   - Consistent → mark complete\n"
                                f"   - Inconsistent → switch to failure recovery flow\n\n"
                                f"For detailed protocol, see MCP Resource `delphi://automation/script-schema` "
                                f"and `get_coding_rules(section=\"automation\")` §F2"
                            ),
                        ),
                    ),
                ]
            )

        if name == "automate-failure-recover":
            signal = args.get("signal", "Unspecified")
            expected = args.get("expected", "Not recorded")
            actual = args.get("actual", "Not recorded")
            return GetPromptResult(
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text=(
                                f"## Automation Test Failure Recovery\n\n"
                                f"**Failure signal**: {signal}\n"
                                f"**Expected**: {expected}\n"
                                f"**Actual**: {actual}\n\n"
                                f"### Diagnosis\n"
                                f"1. `capture` screenshot for records\n"
                                f"2. `dumpstate` to get current control tree\n"
                                f"3. `msgscan` to detect dialogs\n"
                                f"4. Analyze cause of difference: control state/dialog/timing/path changes\n\n"
                                f"### Recovery Strategy\n\n"
                                f"| Condition | Recovery Action |\n"
                                f"|------|---------|\n"
                                f"| Dialog interference | msgclick(OK/Cancel) → retry original operation |\n"
                                f"| Control not visible | dumpstate to find alternative path → correct goto |\n"
                                f"| Timeout without error | increase waitfor time → retry |\n"
                                f"| RTTI available | degrade to rcall/rset to bypass GUI |\n"
                                f"| Deterministic failure | report and save experience |\n\n"
                                f"### Learning Record\n"
                                f"Save experience after recovery:\n"
                                f"`experience(action=\"save\", problem=\"{signal} in {expected}\", "
                                f"solution=\"...recovery method...\", tags=[\"automation\", \"failure_recovery\"])`\n\n"
                                f"For complete recovery template, see MCP Resource `delphi://automation/repair-loop` "
                                f"and `get_coding_rules(section=\"automation\")` §F3"
                            ),
                        ),
                    ),
                ]
            )

        if name == "automate-save-experience":
            return GetPromptResult(
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text=(
                                f"## Save Automation Test Experience\n\n"
                                f"Test execution complete. Please save experience according to the following template:\n\n"
                                f"### Execution Overview\n"
                                f"- **Total steps**: \n"
                                f"- **Success**: \n"
                                f"- **Failure+Recovery**: \n"
                                f"- **Unrecoverable failures**: \n"
                                f"- **Total duration**: \n\n"
                                f"### Success Patterns\n"
                                f"- Stable tool combinations: \n"
                                f"- RTTI usage: \n"
                                f"- Key timing adjustments: \n\n"
                                f"### Failure Patterns\n"
                                f"- Failure description → Cause → Recovery method → Whether it can be automated\n\n"
                                f"### Save\n"
                                f"```\n"
                                f"experience(action=\"save\",\n"
                                f"    problem=\"<scenario keyword>\",\n"
                                f"    solution=\"<core approach>\",\n"
                                f"    tools_used=[\"<tool list>\"],\n"
                                f"    tags=[\"automation\", \"<app_name>\"])\n"
                                f"```\n\n"
                                f"For complete template, see `get_coding_rules(section=\"automation\")` §F4"
                            ),
                        ),
                    ),
                ]
            )

        if name == "automate-session-end":
            save_exp = args.get("save_experience", "true")
            export_script = args.get("export_script", "true")
            return GetPromptResult(
                messages=[
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text=(
                                f"## End Automation Test Session\n\n"
                                f"Test execution complete. Please wrap up according to the following steps:\n\n"
                                f"### 1. Save this test's experience\n"
                                f"(save_experience={save_exp})\n"
                                f"```\n"
                                f"experience(action=\"save\",\n"
                                f"    problem=\"<scenario keyword>\",\n"
                                f"    solution=\"<core approach>\",\n"
                                f"    tools_used=[\"<tool list>\"],\n"
                                f"    tags=[\"automation\", \"<app_name>\"])\n"
                                f"```\n\n"
                                f"### 2. Export reusable script\n"
                                f"(export_script={export_script})\n"
                                f"Save this execution's script to `tests/scripts/`:\n"
                                f"```\n"
                                f"delphi_file(action=\"write\",\n"
                                f"    file_path=\"tests/scripts/<test_name>.json\",\n"
                                f"    content=<script_json>)\n"
                                f"```\n"
                                f"For detailed format, see MCP Resource `delphi://automation/script-schema` "
                                f"and `get_coding_rules(section=\"automation\")` §I2\n\n"
                                f"### 3. Role switch\n"
                                f"Automation test session has ended.\n"
                                f"Role switches from **Delphi UI Automation Test Expert** back to **Delphi Development Expert**.\n"
                                f"Thinking framework switches to coding mode:\n"
                                f"```\n"
                                f"get_coding_rules(section=\"coding\")\n"
                                f"```\n"
                                f"Before starting coding work, it is recommended to first execute `get_coding_rules(section=\"workflow\")` "
                                f"to obtain the complete development workflow."
                            ),
                        ),
                    ),
                ]
            )

        raise ValueError(f"Unknown prompt: {name}")

    # ============================================================
    # Background version check — asynchronously detect at startup whether GitHub has a new version (with auto-retry)
    # ============================================================

    async def _background_version_check():
        """Check Daofy version updates in the background, using AsyncTaskManager to submit auto-retry tasks.

        Similar to the code_hosting git_push_retry pattern:
        - Auto-retry when network is unreachable (5-minute interval, max 12 times ≈ 1 hour)
        - Non-blocking to MCP service during retries
        - Update global variable via on_complete callback on success
        """
        global _update_check_result, _update_check_done
        try:
            logger.info("Checking Daofy version update in background (async auto-retry)...")

            # First try quickly once (without waiting for retry)
            loop = asyncio.get_running_loop()
            quick_result = await loop.run_in_executor(
                None, updater.check_for_update
            )
            if quick_result is not None:
                _update_check_result = quick_result
                if quick_result.get("update_available"):
                    logger.warning(
                        "New version found! Current: %s, latest: %s → %s",
                        quick_result["current"], quick_result["latest"],
                        quick_result["release_url"],
                    )
                else:
                    logger.info("Already the latest version: %s", quick_result["current"])
                _update_check_done = True
                return

            # Quick attempt failed, submit background auto-retry task
            logger.info("Version check quick attempt failed, submitting background auto-retry task...")

            def _on_update_complete(task_info):
                """Background retry task completion callback — update global cache."""
                global _update_check_result, _update_check_done
                result = task_info.result
                if isinstance(result, dict) and 'error' not in result:
                    _update_check_result = result
                    if result.get("update_available"):
                        logger.warning(
                            "Background retry found new version! Current: %s, latest: %s",
                            result["current"], result["latest"],
                        )
                    else:
                        logger.info(
                            "Background retry confirmed already the latest version: %s", result["current"]
                        )
                elif isinstance(result, dict) and result.get('error'):
                    logger.warning(
                        "All background version check retries failed: %s", result['error']
                    )
                _update_check_done = True

            from src.services.knowledge_base.async_task_manager import get_task_manager
            task_id = get_task_manager().submit_task(
                name="version_check_retry",
                func=updater.check_for_update_retry,
                on_complete=_on_update_complete,
            )
            logger.info(
                "Background version check retry task submitted: task_id=%s | "
                "interval=%ds | max %d times | up to about %dmin",
                task_id,
                updater.RETRY_INTERVAL,
                updater.MAX_RETRIES,
                updater.ETA_MINUTES,
            )

        except ImportError as e:
            logger.warning(
                "Unable to submit async retry task (AsyncTaskManager unavailable): %s", e
            )
            _update_check_done = True
        except Exception as e:
            logger.debug("Version check failed (does not affect normal operation): %s", e)
            _update_check_done = True

    # Start background version check (non-blocking to startup)
    asyncio.create_task(_background_version_check())

    # ============================================================
    # Auto-build project knowledge base — detect project directory at startup and build in background
    # ============================================================

    async def _auto_build_project_kb():
        """Automatically detect project directory and build project knowledge base in background (non-blocking to startup)"""
        try:
            logger.info("Automatically detecting project directory...")
            loop = asyncio.get_running_loop()

            # Execute CWD scan in executor (may involve file system I/O)
            project_path = await loop.run_in_executor(
                None, _resolve_project_path, None
            )

            if not project_path:
                logger.info(
                    "No project file detected (.dproj/.dpr/.dpk), skipping auto-build of project knowledge base"
                )
                return

            logger.info(
                "Detected project: %s, automatically building project knowledge base in background...",
                project_path,
            )

            # Submit background build using existing async task mechanism
            # rebuild=False → incremental update (only index changed files)
            # On first run KB does not exist, build_project_knowledge_base will automatically perform full build
            # Step 1's hot-swap mechanism guarantees: rebuilding existing KB does not block searches
            task_params = {
                "project_path": project_path,
                "rebuild": False,
                "build_thirdparty": True,
                "build_project": True,
            }
            result = await async_tools.start_async_task({
                "task_type": "init_project_knowledge_base",
                "task_params": task_params,
                "show_progress": False,
            })

            # start_async_task returns CallToolResult; isError=False means the task has been successfully submitted to the background
            if call_tool_result_is_error(result):
                logger.warning(
                    "Automatic project knowledge base build submission failed: %s", project_path
                )
            else:
                logger.info(
                    "Automatic project knowledge base build task submitted to the background: %s", project_path
                )

            # ── Step 3: start file change watcher (if watchdog is available) ──
            await _start_project_file_watcher(project_path)

        except Exception as e:
            logger.debug(
                "Automatic project knowledge base build failed (does not affect normal operation): %s", e
            )

    async def _start_project_file_watcher(project_path: str) -> None:
        """Start the project file change watcher, automatically triggering incremental KB updates.

        Start in an executor without blocking the event loop. Silently degrade when watchdog is unavailable.
        """
        global _project_file_watcher
        try:
            from src.services.knowledge_base.file_watcher import (
                ProjectFileWatcher,
            )

            project_dir = str(Path(project_path).parent)
            loop = asyncio.get_running_loop()

            def _start_watcher() -> Optional[object]:
                w = ProjectFileWatcher(project_path, project_dir)
                w.start()
                return w

            watcher = await loop.run_in_executor(None, _start_watcher)
            if watcher:
                _project_file_watcher = watcher
                logger.info(
                    "File change watcher started (watchdog available): %s", project_dir
                )
            else:
                logger.info(
                    "File change watcher not started (watchdog unavailable): %s", project_dir
                )

        except Exception as e:
            logger.debug(
                "Failed to start file change watcher (does not affect normal operation): %s", e
            )

    # Start background automatic project knowledge base build (non-blocking at startup)
    asyncio.create_task(_auto_build_project_kb())

    # Start server
    logger.info("MCP Server startup complete, ready to receive requests...")
    async with stdio_server() as (read_stream, write_stream):
        logger.info("mcp_lifecycle event=stdio_transport_opened")
        await _run_mcp_server(
            server,
            read_stream,
            write_stream,
        )
    logger.info("mcp_lifecycle event=stdio_transport_closed")
    logger.info("mcp_lifecycle event=run_server_returned")


def _cleanup_resources(shutdown_reason: str = "unknown") -> None:
    """Clean up resources: close background tasks, DB connections, temporary files, etc."""
    cleanup_started = time.monotonic()
    cleanup_failures = 0
    logger.info("mcp_cleanup event=started reason=%s", shutdown_reason)

    def run_cleanup_step(step_name: str, action: Any) -> None:
        nonlocal cleanup_failures
        logger.info("mcp_cleanup event=step_started step=%s", step_name)
        try:
            action()
        except Exception:
            cleanup_failures += 1
            logger.warning(
                "mcp_cleanup event=step_failed step=%s", step_name,
                exc_info=True,
            )
        else:
            logger.info("mcp_cleanup event=step_completed step=%s", step_name)

    try:
        from src.tools.knowledge_base import _cleanup_pkb_cache  # Lazy import to avoid circular import
    except Exception:
        cleanup_failures += 1
        logger.warning(
            "mcp_cleanup event=step_failed step=pkb_cache_import",
            exc_info=True,
        )
    else:
        run_cleanup_step("pkb_cache", _cleanup_pkb_cache)
    try:
        from src.tools.dfm_utils import _cleanup_dfm_temp_dirs
    except Exception:
        cleanup_failures += 1
        logger.warning(
            "mcp_cleanup event=step_failed step=dfm_temp_dirs_import",
            exc_info=True,
        )
    else:
        run_cleanup_step("dfm_temp_dirs", _cleanup_dfm_temp_dirs)
    try:
        from src.services.experience_service import cleanup as _cleanup_exp
    except Exception:
        cleanup_failures += 1
        logger.warning(
            "mcp_cleanup event=step_failed step=experience_service_import",
            exc_info=True,
        )
    else:
        run_cleanup_step("experience_service", _cleanup_exp)
    # Note: the knowledge_base module has no public getter function to obtain service instances,
    # global variables _delphi_kb_service and _thirdparty_kb_service are automatically cleaned up on process exit.
    # No longer attempt to import nonexistent get_knowledge_base_service / get_thirdparty_knowledge_base_service here.
    try:
        from src.tools.project_knowledge_base import _cleanup_project_kb_cache
    except Exception:
        cleanup_failures += 1
        logger.warning(
            "mcp_cleanup event=step_failed step=project_kb_cache_import",
            exc_info=True,
        )
    else:
        run_cleanup_step("project_kb_cache", _cleanup_project_kb_cache)
    global _project_file_watcher
    if _project_file_watcher is not None:
        watcher = _project_file_watcher
        _project_file_watcher = None
        run_cleanup_step("project_file_watcher", watcher.stop)
    else:
        logger.info(
            "mcp_cleanup event=step_skipped step=project_file_watcher reason=not_started"
        )
    elapsed_ms = round((time.monotonic() - cleanup_started) * 1000)
    logger.info(
        "mcp_cleanup event=finished reason=%s failures=%d elapsed_ms=%d",
        shutdown_reason,
        cleanup_failures,
        elapsed_ms,
    )


def _build_arg_parser() -> "argparse.ArgumentParser":
    """Build the CLI argument parser (does not depend on any service; --help/--version exit immediately)"""
    import argparse
    parser = argparse.ArgumentParser(
        prog="daofy",
        description="Daofy for Delphi — MCP Server (Delphi compilation + knowledge base)",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Show version information and exit",
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        help="Custom compilers.json path (default: config/compilers.json)",
    )
    return parser


def main():
    """Main function"""
    # ── Early exit: --help/--version does not trigger any service initialization ──
    # Avoid --help erroring in environments without Delphi installed / with invalid default paths
    parser = _build_arg_parser()
    args = parser.parse_args()
    if args.version:
        print(f"Daofy v{__version__}")
        print(f"Python {sys.version.split()[0]}")
        print(f"{__copyright__}")
        return

    # ── dsh subcommand interface has been removed (DSH install/uninstall has been merged into install_mcp.py, see --agent DSH) ──
    exit_code = 0
    shutdown_reason = "server_run_returned"
    try:
        asyncio.run(run_server())
        logger.info("mcp_lifecycle event=asyncio_run_returned")
    except KeyboardInterrupt:
        shutdown_reason = "keyboard_interrupt"
        logger.info("mcp_lifecycle event=keyboard_interrupt")
    except Exception as e:
        shutdown_reason = "exception"
        exit_code = 1
        logger.error(
            "mcp_lifecycle event=server_exception error_type=%s message=%s",
            type(e).__name__,
            str(e),
            exc_info=True,
        )
    finally:
        _cleanup_resources(shutdown_reason)
        _logging.shutdown()
    if exit_code:
        sys.exit(exit_code)


if __name__ == "__main__":
    main()