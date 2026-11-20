"""
Asynchronous task management MCP tools

Copyright (C) Jilin ZuoYou Software Development Co., Ltd.
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
Update & Mod By Crystalxp (Night Killer QQ:281309196)

Provides asynchronous task start, query, and management functions
"""

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

from mcp.types import CallToolResult

from ..constants import DIR_DELPHI_KB, REG_KEY_EMBARCADERO_BDS
from ..services.knowledge_base.async_task_manager import get_task_manager, TaskStatus
from ..utils.logger import get_logger

logger = get_logger(__name__)

# Large result threshold: write to temp file when exceeding this size (bytes)
_RESULT_FILE_THRESHOLD = 10 * 1024  # 10 KB
# Temporary result file directory (write to project .tmp subdirectory to avoid system Temp permission issues)
_RESULT_FILE_DIR = Path(__file__).resolve().parent.parent.parent / ".tmp" / "async_results"
# Auto-cleanup: delete temp files older than this time (seconds)
_RESULT_FILE_TTL = 3600  # 1 hour


def _ensure_result_dir() -> Path:
    """Ensure temporary result directory exists"""
    _RESULT_FILE_DIR.mkdir(parents=True, exist_ok=True)
    return _RESULT_FILE_DIR


def _cleanup_old_result_files() -> int:
    """Delete expired temporary result files, return deleted count"""
    now = time.time()
    count = 0
    try:
        for f in _RESULT_FILE_DIR.glob("task_*.json"):
            if now - f.stat().st_mtime > _RESULT_FILE_TTL:
                f.unlink(missing_ok=True)
                count += 1
    except OSError:
        pass
    return count


def _format_result_text(task_info: Any) -> str:
    """Format task result as text"""
    result_text = "Task executed successfully!\n\n"
    if isinstance(task_info.result, dict):
        for key, value in task_info.result.items():
            result_text += f"{key}: {value}\n"
    else:
        result_text += f"Result: {task_info.result}\n"
    return result_text


def _write_result_to_file(task_id: str, result_text: str) -> str:
    """Write large result to temporary file, return file path"""
    _ensure_result_dir()
    file_path = _RESULT_FILE_DIR / f"{task_id}.json"
    try:
        file_path.write_text(result_text, encoding="utf-8")
        return str(file_path)
    except OSError as e:
        logger.error(f"Failed to write result file: {e}")
        return ""


async def start_async_task(arguments: Any) -> CallToolResult:
    """
    Start asynchronous task

    Args:
        arguments: contains the following parameters:
             - task_type: task type (required)
                - "build_knowledge_base": build Delphi knowledge base
                - "build_thirdparty_knowledge_base": build third-party library knowledge base
                - "init_project_knowledge_base": initialize project knowledge base
                - "build_document_knowledge_base": build document knowledge base
                - "build_example_knowledge_base": build example knowledge base
            - params: task parameters (optional, depends on task type)
                - build_document_knowledge_base:
                    - urls: web page URL list
                    - directory: scan directory path
                    - extensions: file extension list
            - show_progress: whether to show progress (optional, default true)

    Returns:
        Task start result, containing task ID
    """
    task_type = arguments.get("task_type")
    params = arguments.get("task_params", {})
    show_progress = arguments.get("show_progress", True)

    if not task_type:
        return CallToolResult(
            content=[{"type": "text", "text": "Please provide task type"}],
            isError=True
        )

    task_manager = get_task_manager()

    # Create task function based on task type
    if task_type == "build_knowledge_base":
        from ..services.knowledge_base.zvec_adapter import ZVecKnowledgeBaseAdapter
        from src.utils.delphi_env import get_delphi_version
        import winreg
        from pathlib import Path

        def _get_delphi_source_dirs(version=None):
            # Share the same version filtering strategy with RTL/third-party library paths:
            # when version is passed, index only official source for that Delphi version; otherwise take all.
            try:
                from ...utils.delphi_env import resolve_delphi_source_dirs
                return resolve_delphi_source_dirs(version)
            except Exception:
                import winreg
                from pathlib import Path

                dirs = []
                try:
                    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY_EMBARCADERO_BDS)
                    i = 0
                    while True:
                        try:
                            vkey = winreg.EnumKey(key, i)
                            vpath = winreg.OpenKey(key, vkey)
                            try:
                                root = winreg.QueryValueEx(vpath, "RootDir")[0]
                                src = Path(root) / "source"
                                if src.exists():
                                    dirs.append(str(src))
                            except OSError:
                                pass
                            finally:
                                winreg.CloseKey(vpath)
                            i += 1
                        except WindowsError:
                            break
                    winreg.CloseKey(key)
                except Exception:
                    pass
                return dirs

        def build_kb_task(**kwargs):
            rebuild = kwargs.get("rebuild", False)
            progress_callback = kwargs.get("_progress_callback")
            # version passthrough: filter system library source directories by version (default None → all versions)
            version = kwargs.get("version")
            source_dirs = _get_delphi_source_dirs(version)
            kb_dir = str(Path(__file__).parent.parent.parent / "data" / "delphi-knowledge-base")
            service = ZVecKnowledgeBaseAdapter(kb_dir, source_dirs=source_dirs)
            service.progress_callback = progress_callback
            return service.build_knowledge_base(rebuild=rebuild)

        # Determine displayed version number
        display_version = params.get("version")
        if not display_version:
            display_version = get_delphi_version()
        if not display_version:
            display_version = "latest"
        task_name = f"Build Delphi knowledge base (version: {display_version})"

    elif task_type == "build_thirdparty_knowledge_base":
        from ..services.knowledge_base.thirdparty_knowledge_base import ThirdPartyKnowledgeBase

        def build_thirdparty_task(**kwargs):
            version = kwargs.get("version")
            rebuild = kwargs.get("rebuild", False)
            progress_callback = kwargs.get("_progress_callback")

            service = ThirdPartyKnowledgeBase(progress_callback=progress_callback)
            return service.build_thirdparty_knowledge_base(version=version, rebuild=rebuild)

        task_name = "Build third-party library knowledge base"

    elif task_type == "init_project_knowledge_base":
        from ..services.knowledge_base.project_knowledge_base import ProjectKnowledgeBase
        import shutil
        import time as _time_mod

        def init_project_task(**kwargs):
            project_path = kwargs.get("project_path")
            rebuild = kwargs.get("rebuild", False)
            progress_callback = kwargs.get("_progress_callback")

            project_kb = ProjectKnowledgeBase(project_path, progress_callback)

            # ── Hot swap: when rebuilding, build to a temporary directory, old KB remains queryable ──
            old_kb_dir = project_kb.kb_dir
            has_old_kb = old_kb_dir.exists() and any(old_kb_dir.iterdir())
            use_temp_build = rebuild and has_old_kb
            temp_dir = None

            if use_temp_build:
                # Create temporary directory name with a timestamp to avoid conflicts
                temp_suffix = f"-tmp-{int(_time_mod.time())}"
                temp_dir = old_kb_dir.parent / f"{DIR_DELPHI_KB}{temp_suffix}"
                # Temporarily point kb_dir to temp, build to the temporary directory
                project_kb.kb_dir = temp_dir
                logger.info(
                    "Rebuilding project KB to temporary directory: %s (old KB is at %s, still queryable)",
                    temp_dir, old_kb_dir,
                )

            results = {}
            try:
                _t0 = _time_mod.monotonic()
                success = project_kb.build_project_knowledge_base(
                    rebuild=rebuild)
                _elapsed = _time_mod.monotonic() - _t0
                logger.info(
                    "Project KB build %s: %s (%.1f seconds, %s)",
                    "complete" if success else "failed",
                    project_path,
                    _elapsed,
                    "full" if rebuild else "incremental",
                )
                results["project"] = success

                # Build succeeded + used temporary directory → perform hot swap
                if use_temp_build and success:
                    project_kb.close()
                    # Delete old KB
                    shutil.rmtree(old_kb_dir, ignore_errors=True)
                    # Temp directory → official directory
                    shutil.move(str(temp_dir), str(old_kb_dir))
                    # Clear cache, next search uses new instance
                    from ..tools.knowledge_base import _clear_pkb_cache
                    _clear_pkb_cache(project_path)
                    logger.info("Project KB hot swap complete: %s → %s", temp_dir, old_kb_dir)
                elif use_temp_build and not success:
                    # Build failed: delete temp directory, old KB remains unchanged
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    project_kb.kb_dir = old_kb_dir  # Restore pointer
                    logger.warning("Project KB rebuild failed, old KB retained: %s", old_kb_dir)

            except Exception:
                # Clean up temp directory on exception too
                if use_temp_build and temp_dir and temp_dir.exists():
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    project_kb.kb_dir = old_kb_dir
                raise

            stats = project_kb.get_statistics()
            results["statistics"] = stats

            return results

        task_name = f"Initialize project knowledge base ({params.get('project_path', 'unknown project')})"

    elif task_type == "build_embedding":
        from ..services.knowledge_base.project_knowledge_base import ProjectKnowledgeBase

        def build_embedding_task(**kwargs):
            project_path = kwargs.get("project_path")
            progress_callback = kwargs.get("_progress_callback")
            pkb = ProjectKnowledgeBase(project_path, progress_callback)
            pkb.load_knowledge_bases()
            counts = pkb.build_vectors(progress_callback=progress_callback)
            pkb.close()
            return counts

        task_name = f"Build embedding vectors ({params.get('project_path', '')})"

    elif task_type == "build_example_knowledge_base":
        from ..services.knowledge_base.example_knowledge_base import (
            ExampleKnowledgeBase,
        )

        def build_example_task(**kwargs):
            rebuild = kwargs.get("rebuild", False)
            progress_callback = kwargs.get("_progress_callback")
            ekb = ExampleKnowledgeBase(progress_callback=progress_callback)
            return ekb.build_example_knowledge_base(rebuild=rebuild)

        task_name = "Build example knowledge base"

    elif task_type == "build_document_knowledge_base":
        from ..services.knowledge_base.scan_generic_documents import GenericDocumentScanner
        from pathlib import Path as FilePath
        
        def build_doc_task(**kwargs):
            urls = kwargs.get("urls", [])
            directory = kwargs.get("directory")
            extensions = kwargs.get("extensions")
            start_url = kwargs.get("start_url")
            max_pages = kwargs.get("max_pages", 100)
            max_depth = kwargs.get("max_depth", 3)
            domain_filter = kwargs.get("domain_filter")
            url_pattern = kwargs.get("url_pattern")
            exclude = kwargs.get("exclude")
            rebuild = kwargs.get("rebuild", False)
            progress_callback = kwargs.get("_progress_callback")
            
            server_root = FilePath(__file__).parent.parent.parent
            kb_dir = str(server_root / "data" / "document-knowledge-base")
            FilePath(kb_dir).mkdir(parents=True, exist_ok=True)
            
            scanner = GenericDocumentScanner(kb_dir, progress_callback=progress_callback)
            
            results = {"success": 0, "failed": 0, "total": 0, "total_size": 0}
            
            # Crawl website (automatic nested collection)
            if start_url:
                crawl_result = scanner.crawl_website(
                    start_url=start_url,
                    max_pages=max_pages,
                    max_depth=max_depth,
                    domain_filter=domain_filter,
                    url_pattern=url_pattern
                )
                results.update(crawl_result)
            
            # Add specified URL list
            if urls:
                for url in urls:
                    result = scanner.add_web_document(url)
                    if result and not (isinstance(result, dict) and 'error' in result):
                        results["success"] += 1
                    else:
                        results["failed"] += 1
                    results["total"] += 1
            
            # Scan directory
            if directory:
                scan_result = scanner.scan_directory(directory, extensions=extensions, exclude=exclude,
                                                     rebuild=rebuild)
                results["scan"] = scan_result
                # The scanner writes directly to ZVec; no extra export step is needed
                if scan_result and not scan_result.get("error"):
                    results["zvec_built"] = True

            return results
        
        if params.get("start_url"):
            task_name = f"Crawl website (up to {params.get('max_pages', 100)} pages)"
        elif params.get("directory"):
            task_name = f"Build document knowledge base (scan directory: {params.get('directory')})"
        else:
            urls_count = len(params.get("urls", []))
            task_name = f"Build document knowledge base ({urls_count} URLs)"

    else:
        return CallToolResult(
            content=[{"type": "text", "text": f"Unknown task type: {task_type}"}],
            isError=True
        )

    # Get MCP push callback (injected by server.py)
    on_complete = arguments.pop('_on_complete', None)

    try:
        # Create progress callback
        def progress_callback(progress, message):
            if show_progress:
                logger.info(f"Task progress: {progress:.1f}% - {message}")

        # Compute dedup key to prevent duplicate submissions of same build type
        dedup_key = params.pop("dedup_key", None)
        if dedup_key is None:
            if task_type == "init_project_knowledge_base":
                dedup_key = f"project_rebuild:{params.get('project_path', '')}"
            elif task_type == "build_thirdparty_knowledge_base":
                dedup_key = "thirdparty_rebuild"
            elif task_type == "build_knowledge_base":
                dedup_key = "delphi_rebuild"
            elif task_type == "build_document_knowledge_base":
                dedup_key = f"document_rebuild:{params.get('directory', '')}"
            elif task_type == "build_embedding":
                dedup_key = f"embedding:{params.get('project_path', '')}"
            elif task_type == "build_example_knowledge_base":
                dedup_key = "example_rebuild"

        # Submit asynchronous task
        task_func = (
            build_kb_task if task_type == "build_knowledge_base" else
            build_thirdparty_task if task_type == "build_thirdparty_knowledge_base" else
            init_project_task if task_type == "init_project_knowledge_base" else
            build_embedding_task if task_type == "build_embedding" else
            build_example_task if task_type == "build_example_knowledge_base" else
            build_doc_task
        )
        
        task_id = task_manager.submit_task(
            name=task_name,
            func=task_func,
            progress_callback=progress_callback if show_progress else None,
            dedup_key=dedup_key,
            on_complete=on_complete,
            **params
        )

        result_text = f"✓ Asynchronous task started\n\n"
        result_text += f"Task ID: {task_id}\n"
        result_text += f"Task name: {task_name}\n"
        result_text += f"Status: submitted for background execution\n\n"
        result_text += f"Use the following commands to query task status:\n"
        result_text += f"  - get_task_status: query task status\n"
        result_text += f"  - get_task_result: get task result\n"
        result_text += f"  - list_tasks: list all tasks"

        return CallToolResult(content=[{"type": "text", "text": result_text}])

    except Exception as e:
        logger.error(f"Failed to start asynchronous task: {e}", exc_info=True)
        return CallToolResult(
            content=[{"type": "text", "text": f"Failed to start asynchronous task: {str(e)}"}],
            isError=True
        )


async def get_task_status(arguments: Any) -> CallToolResult:
    """
    Get task status (supports long polling)

    ⚠️ Note: For slow tasks (such as automated tests, knowledge base builds), do not use long_poll_seconds.
    Long polling blocks the MCP request channel; if the task does not complete for a long time, it may cause client timeout.
    Use action="result" polling instead: return current status immediately with zero waiting.

    Args:
        arguments: contains the following parameters:
            - task_id: task ID (required)
            - long_poll_seconds: long polling wait seconds (optional, default 0 returns immediately. MCP request channel has a timeout limit; ≤30 seconds recommended; use short polling after timeout)

    Returns:
        Task status information
    """
    task_id = arguments.get("task_id")
    if not task_id:
        return CallToolResult(
            content=[{"type": "text", "text": "Please provide task ID"}],
            isError=True
        )

    task_manager = get_task_manager()
    
    # Long polling: wait for progress change before returning
    long_poll = arguments.get("long_poll_seconds", 0)
    if long_poll > 0:
        task_info = task_manager.wait_for_progress_change(task_id, long_poll)
    else:
        task_info = task_manager.get_task_info(task_id)

    if not task_info:
        return CallToolResult(
            content=[{"type": "text", "text": f"Task not found: {task_id}"}],
            isError=True
        )

    result_text = f"Task status: {task_id}\n\n"
    result_text += f"Task name: {task_info.name}\n"
    result_text += f"Status: {task_info.status.value}\n"
    result_text += f"Progress: {task_info.progress:.1f}%\n"
    result_text += f"Message: {task_info.message}\n"
    result_text += f"Created at: {task_info.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"

    if task_info.started_at:
        result_text += f"Started at: {task_info.started_at.strftime('%Y-%m-%d %H:%M:%S')}\n"

    if task_info.completed_at:
        result_text += f"Completed at: {task_info.completed_at.strftime('%Y-%m-%d %H:%M:%S')}\n"

    if task_info.error:
        result_text += f"Error: {task_info.error}\n"

    return CallToolResult(content=[{"type": "text", "text": result_text}])


async def get_task_result(arguments: Any) -> CallToolResult:
    """
    Get task result (return immediately, zero waiting)

    ✅ Recommended for polling slow task status: return current result immediately without blocking the MCP channel.
    When the task is not complete, returns "Task not yet complete" + current progress; when complete, returns full result.

    Args:
        arguments: contains the following parameters:
            - task_id: task ID (required)

    Returns:
        Task result (CallToolResult)
    """
    task_id = arguments.get("task_id")
    if not task_id:
        return CallToolResult(
            content=[{"type": "text", "text": "Please provide task ID"}],
            isError=True
        )

    task_manager = get_task_manager()
    task_info = task_manager.get_task_info(task_id)

    if not task_info:
        return CallToolResult(
            content=[{"type": "text", "text": f"Task not found: {task_id}"}],
            isError=True
        )

    if task_info.status != TaskStatus.COMPLETED:
        result_text = f"Task not yet complete\n\n"
        result_text += f"Task ID: {task_id}\n"
        result_text += f"Current status: {task_info.status.value}\n"
        result_text += f"Progress: {task_info.progress:.1f}%\n"
        result_text += f"Message: {task_info.message}\n"

        return CallToolResult(content=[{"type": "text", "text": result_text}])

    if task_info.error:
        return CallToolResult(
            content=[{"type": "text", "text": f"Task execution failed: {task_info.error}"}],
            isError=True
        )

    # Format result
    result_text = _format_result_text(task_info)

    # Write large result to temp file, return summary + file path
    if len(result_text.encode("utf-8")) > _RESULT_FILE_THRESHOLD:
        file_path = _write_result_to_file(task_id, result_text)
        if file_path:
            # Also clean up expired files
            _cleanup_old_result_files()
            summary = (
                f"Task executed successfully!\n\n"
                f"Result is large ({len(result_text):,} characters) and has been written to a temporary file:\n"
                f"{file_path}\n\n"
                f"Use the Read tool to read the file for the full result, then delete the file after reading."
            )
            return CallToolResult(content=[{"type": "text", "text": summary}])

    return CallToolResult(content=[{"type": "text", "text": result_text}])


async def cancel_task(arguments: Any) -> CallToolResult:
    """
    Cancel task

    Args:
        arguments: contains the following parameters:
            - task_id: task ID (required)

    Returns:
        Operation result
    """
    task_id = arguments.get("task_id")
    if not task_id:
        return CallToolResult(
            content=[{"type": "text", "text": "Please provide task ID"}],
            isError=True
        )

    task_manager = get_task_manager()
    success = task_manager.cancel_task(task_id)

    if success:
        return CallToolResult(content=[{"type": "text", "text": f"Task {task_id} has been cancelled"}])
    else:
        return CallToolResult(
            content=[{"type": "text", "text": f"Cannot cancel task {task_id} (task does not exist or is already complete)"}],
            isError=True
        )


async def list_tasks(arguments: Any) -> CallToolResult:
    """
    List all tasks

    Args:
        arguments: empty parameters

    Returns:
        List of all tasks
    """
    task_manager = get_task_manager()
    tasks = task_manager.get_all_tasks()

    if not tasks:
        return CallToolResult(content=[{"type": "text", "text": "There are currently no tasks"}])

    result_text = f"Task list ({len(tasks)} total):\n\n"

    for task_id, task_info in tasks.items():
        result_text += f"Task ID: {task_id}\n"
        result_text += f"  Name: {task_info.name}\n"
        result_text += f"  Status: {task_info.status.value}\n"
        result_text += f"  Progress: {task_info.progress:.1f}%\n"
        result_text += f"  Message: {task_info.message}\n"
        result_text += f"  Created at: {task_info.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
        result_text += "\n"

    return CallToolResult(content=[{"type": "text", "text": result_text}])

