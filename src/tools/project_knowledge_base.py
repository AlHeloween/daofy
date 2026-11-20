"""
Project knowledge base MCP tools

Copyright (C) Jilin Province Zuoyou Software Development Co., Ltd.
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
Update & Mod By Crystalxp (Dark Night Killer QQ:281309196)

Provides MCP tools for querying and managing the project knowledge base
"""

from typing import Any, Dict, Optional, Callable
from mcp.types import CallToolResult
from pathlib import Path

from ..services.knowledge_base.project_knowledge_base import ProjectKnowledgeBase
from ..utils.logger import get_logger
from ..utils.progress_tracker import ProgressInfo

logger = get_logger(__name__)

# Project knowledge base instance cache (LRU eviction to prevent unbounded memory growth)
_project_kb_cache: Dict[str, ProjectKnowledgeBase] = {}
_project_kb_cache_order: list[str] = []  # Access order; most recently accessed at the end
_MAX_PROJECT_KB_CACHE = 5  # Cache at most 5 project knowledge bases


def _evict_oldest_project_kb() -> None:
    """Evict the least recently accessed project knowledge base instance"""
    while len(_project_kb_cache) >= _MAX_PROJECT_KB_CACHE and _project_kb_cache_order:
        oldest_key = _project_kb_cache_order.pop(0)
        if oldest_key in _project_kb_cache:
            try:
                _project_kb_cache[oldest_key].close()
            except Exception as e:
                logger.debug("Failed to close evicted project knowledge base: %s", e)
            del _project_kb_cache[oldest_key]
            logger.debug("Evicted project knowledge base cache: %s", oldest_key)


def _touch_project_kb_cache(project_path: str) -> None:
    """Update cache access order"""
    if project_path in _project_kb_cache_order:
        _project_kb_cache_order.remove(project_path)
    _project_kb_cache_order.append(project_path)


def _cleanup_project_kb_cache() -> None:
    """Clean up all project knowledge base caches (called when the service shuts down)"""
    for path, pkb in list(_project_kb_cache.items()):
        try:
            pkb.close()
        except Exception:
            pass
    _project_kb_cache.clear()
    _project_kb_cache_order.clear()


def get_project_kb(project_path: str, progress_callback: Optional[Callable[[ProgressInfo], None]] = None) -> ProjectKnowledgeBase:
    """
    Get or create a project knowledge base instance

    Args:
        project_path: Project file path
        progress_callback: Progress callback function

    Returns:
        Project knowledge base instance
    """
    project_path = str(Path(project_path).resolve())

    if project_path not in _project_kb_cache:
        _evict_oldest_project_kb()
        _project_kb_cache[project_path] = ProjectKnowledgeBase(project_path, progress_callback)
        _project_kb_cache[project_path].load_knowledge_bases()

    _touch_project_kb_cache(project_path)
    return _project_kb_cache[project_path]


async def init_project_knowledge_base(arguments: Any) -> CallToolResult:
    """
    Initialize the project knowledge base

    Args:
        arguments: Contains the following parameters:
            - project_path: Project file path (.dproj or .dpr) (required)
            - build_thirdparty: Whether to build the third-party library knowledge base (optional, default true)
            - build_project: Whether to build the project source knowledge base (optional, default true)
            - rebuild: Whether to force rebuild (optional, default false)
            - show_progress: Whether to show progress (optional, default true)

    Returns:
        Initialization result
    """
    project_path = arguments.get("project_path")
    if not project_path:
        return CallToolResult(
            content=[{"type": "text", "text": "Please provide a project file path"}],
            isError=True
        )

    # Check whether the project file exists
    if not Path(project_path).exists():
        return CallToolResult(
            content=[{"type": "text", "text": f"Project file does not exist: {project_path}"}],
            isError=True
        )

    build_thirdparty = arguments.get("build_thirdparty", True)
    build_project = arguments.get("build_project", True)
    rebuild = arguments.get("rebuild", False)
    show_progress = arguments.get("show_progress", True)

    # Create progress callback
    progress_messages = []
    def progress_callback(progress: ProgressInfo):
        if show_progress:
            msg = f"Progress: {progress.current}/{progress.total} ({progress.percentage:.1f}%) | "
            msg += f"Speed: {progress.speed:.1f} items/sec | "
            msg += f"Elapsed: {progress.elapsed_time:.1f} sec | "
            msg += f"Remaining: {progress.estimated_remaining:.1f} sec | "
            msg += f"{progress.message}"
            progress_messages.append(msg)
            logger.info(msg)

    try:
        project_kb = get_project_kb(project_path, progress_callback if show_progress else None)

        output = f"Project knowledge base initialization: {project_kb.project_name}\n\n"

        # Build the project knowledge base (including third-party libraries)
        if not (build_project or build_thirdparty):
            output += "Please specify build_thirdparty or build_project parameter\n"
        else:
            logger.info("Building project knowledge base...")
            if project_kb.build_project_knowledge_base(rebuild=rebuild):
                output += "✓ Project knowledge base built successfully\n"
            else:
                output += "✗ Failed to build project knowledge base\n"

        # Get statistics
        stats = project_kb.get_statistics()
        output += "\nKnowledge base statistics:\n"

        if stats["project"]:
            output += f"  Project source: {stats['project']['files']} files, "
            output += f"{stats['project']['classes']} classes\n"

        if stats["thirdparty"]:
            output += f"  Third-party libraries: {stats['thirdparty']['files']} files, "
            output += f"{stats['thirdparty']['classes']} classes\n"

        output += f"\nKnowledge base location: {project_kb.kb_dir}"

        # Add progress information
        if show_progress and progress_messages:
            output += f"\n\nBuild progress (last 10 entries):\n"
            for msg in progress_messages[-10:]:
                output += f"  {msg}\n"

        return CallToolResult(content=[{"type": "text", "text": output}])

    except Exception as e:
        logger.error(f"Failed to initialize project knowledge base: {e}", exc_info=True)
        return CallToolResult(
            content=[{"type": "text", "text": f"Failed to initialize project knowledge base: {str(e)}"}],
            isError=True
        )


async def search_project_class(arguments: Any) -> CallToolResult:
    """
    Search for a class in the project

    Args:
        arguments: Contains the following parameters:
            - project_path: Project file path (required)
            - class_name: Class name (required)
            - search_in: Search scope "project", "thirdparty", "all" (optional, default "all")

    Returns:
        Search results
    """
    project_path = arguments.get("project_path")
    class_name = arguments.get("class_name")

    if not project_path:
        return CallToolResult(
            content=[{"type": "text", "text": "Please provide a project file path"}],
            isError=True
        )

    if not class_name:
        return CallToolResult(
            content=[{"type": "text", "text": "Please provide a class name"}],
            isError=True
        )

    search_in = arguments.get("search_in", "all")

    try:
        project_kb = get_project_kb(project_path)
        results = project_kb.search_class(class_name, search_in=search_in)

        if not results:
            return CallToolResult(
                content=[{"type": "text", "text": f"Class '{class_name}' not found"}]
            )

        # Format results
        output = f"Found {len(results)} classes '{class_name}':\n\n"
        for i, result in enumerate(results, 1):
            source = result.get('_source', 'unknown')
            output += f"{i}. [{source}] {result['file']['path']}\n"
            output += f"   Class name: {result['class']['name']}\n"
            output += f"   Base class: {result['class']['base_class']}\n"
            output += f"   Line: {result['class']['line']}\n"
            output += f"   Full path: {result['file']['full_path']}\n\n"

        return CallToolResult(content=[{"type": "text", "text": output}])

    except Exception as e:
        logger.error(f"Failed to search for class: {e}", exc_info=True)
        return CallToolResult(
            content=[{"type": "text", "text": f"Error searching for class: {str(e)}"}],
            isError=True
        )


async def search_project_function(arguments: Any) -> CallToolResult:
    """
    Search for a function in the project

    Args:
        arguments: Contains the following parameters:
            - project_path: Project file path (required)
            - function_name: Function name (required)
            - search_in: Search scope "project", "thirdparty", "all" (optional, default "all")

    Returns:
        Search results
    """
    project_path = arguments.get("project_path")
    function_name = arguments.get("function_name")

    if not project_path:
        return CallToolResult(
            content=[{"type": "text", "text": "Please provide a project file path"}],
            isError=True
        )

    if not function_name:
        return CallToolResult(
            content=[{"type": "text", "text": "Please provide a function name"}],
            isError=True
        )

    search_in = arguments.get("search_in", "all")

    try:
        project_kb = get_project_kb(project_path)
        results = project_kb.search_function(function_name, search_in=search_in)

        if not results:
            return CallToolResult(
                content=[{"type": "text", "text": f"Function '{function_name}' not found"}]
            )

        # Format results
        output = f"Found {len(results)} functions '{function_name}':\n\n"
        for i, result in enumerate(results, 1):
            source = result.get('_source', 'unknown')
            output += f"{i}. [{source}] {result['file']['path']}\n"
            output += f"   Function name: {result['function']['name']}\n"
            output += f"   Type: {result['function']['type']}\n"
            output += f"   Line: {result['function']['line']}\n"
            output += f"   Full path: {result['file']['full_path']}\n\n"

        return CallToolResult(content=[{"type": "text", "text": output}])

    except Exception as e:
        logger.error(f"Failed to search for function: {e}", exc_info=True)
        return CallToolResult(
            content=[{"type": "text", "text": f"Error searching for function: {str(e)}"}],
            isError=True
        )


async def semantic_search_project(arguments: Any) -> CallToolResult:
    """
    Perform semantic search in the project

    Args:
        arguments: Contains the following parameters:
            - project_path: Project file path (required)
            - query: Search query (required)
            - top_k: Number of results to return (optional, default 200, max 500)
            - search_in: Search scope "project", "thirdparty", "all" (optional, default "all")

    Returns:
        Search results
    """
    project_path = arguments.get("project_path")
    query = arguments.get("query")

    if not project_path:
        return CallToolResult(
            content=[{"type": "text", "text": "Please provide a project file path"}],
            isError=True
        )

    if not query:
        return CallToolResult(
            content=[{"type": "text", "text": "Please provide a search query"}],
            isError=True
        )

    top_k = min(arguments.get("top_k", 200), 500)
    search_in = arguments.get("search_in", "all")

    try:
        project_kb = get_project_kb(project_path)
        results = project_kb.semantic_search(query, top_k=top_k, search_in=search_in)

        if not results["classes"] and not results["functions"]:
            return CallToolResult(
                content=[{"type": "text", "text": f"No content related to '{query}' found"}]
            )

        # Format results
        output = f"Semantic search results for '{query}':\n\n"

        if results["classes"]:
            output += f"Related classes (Top {len(results['classes'])}):\n"
            for item in results["classes"][:5]:
                result = item["data"]
                output += f"  - [{item['source']}] {result['class']['name']} (similarity: {item['score']:.3f})\n"
                output += f"    Location: {result['file']['path']}\n"
                output += f"    Base class: {result['class']['base_class']}\n"
                output += f"    Line: {result['class']['line']}\n\n"

        if results["functions"]:
            output += f"Related functions (Top {len(results['functions'])}):\n"
            for item in results["functions"][:5]:
                result = item["data"]
                output += f"  - [{item['source']}] {result['function']['name']} (similarity: {item['score']:.3f})\n"
                output += f"    Location: {result['file']['path']}\n"
                output += f"    Type: {result['function']['type']}\n"
                output += f"    Line: {result['function']['line']}\n\n"

        return CallToolResult(content=[{"type": "text", "text": output}])

    except Exception as e:
        logger.error(f"Semantic search failed: {e}", exc_info=True)
        return CallToolResult(
            content=[{"type": "text", "text": f"Error during semantic search: {str(e)}"}],
            isError=True
        )


async def get_project_kb_stats(arguments: Any) -> CallToolResult:
    """
    Get project knowledge base statistics

    Args:
        arguments: Contains the following parameters:
            - project_path: Project file path (required)

    Returns:
        Statistics
    """
    project_path = arguments.get("project_path")

    if not project_path:
        return CallToolResult(
            content=[{"type": "text", "text": "Please provide a project file path"}],
            isError=True
        )

    try:
        project_kb = get_project_kb(project_path)
        stats = project_kb.get_statistics()

        output = f"Project knowledge base statistics: {project_kb.project_name}\n\n"

        if stats["project"]:
            output += "Project source:\n"
            output += f"  - Files: {stats['project']['files']}\n"
            output += f"  - Classes: {stats['project']['classes']}\n"
            output += f"  - Database size: {stats['project']['database_size_mb']:.2f} MB\n\n"
        else:
            output += "Project source: not built\n\n"

        if stats["thirdparty"]:
            output += "Third-party libraries:\n"
            output += f"  - Files: {stats['thirdparty']['files']}\n"
            output += f"  - Classes: {stats['thirdparty']['classes']}\n"
            output += f"  - Database size: {stats['thirdparty']['database_size_mb']:.2f} MB\n\n"
        else:
            output += "Third-party libraries: not built\n\n"

        # Display third-party library paths
        if project_kb.metadata.get("thirdparty_paths"):
            output += "Third-party library paths:\n"
            for path in project_kb.metadata["thirdparty_paths"]:
                output += f"  - {path}\n"

        output += f"\nKnowledge base location: {project_kb.kb_dir}"

        return CallToolResult(content=[{"type": "text", "text": output}])

    except Exception as e:
        logger.error(f"Failed to get statistics: {e}", exc_info=True)
        return CallToolResult(
            content=[{"type": "text", "text": f"Error getting statistics: {str(e)}"}],
            isError=True
        )


async def get_thirdparty_paths(arguments: Any) -> CallToolResult:
    """
    Get the project's third-party library paths

    Args:
        arguments: Contains the following parameters:
            - project_path: Project file path (required)

    Returns:
        List of third-party library paths
    """
    project_path = arguments.get("project_path")

    if not project_path:
        return CallToolResult(
            content=[{"type": "text", "text": "Please provide a project file path"}],
            isError=True
        )

    try:
        project_kb = get_project_kb(project_path)
        paths = project_kb.get_thirdparty_paths_from_dproj()

        if not paths:
            return CallToolResult(
                content=[{"type": "text", "text": "No third-party library paths found"}]
            )

        output = f"Project third-party library paths ({len(paths)}):\n\n"
        for i, path in enumerate(paths, 1):
            output += f"{i}. {path}\n"

        return CallToolResult(content=[{"type": "text", "text": output}])

    except Exception as e:
        logger.error(f"Failed to get third-party library paths: {e}", exc_info=True)
        return CallToolResult(
            content=[{"type": "text", "text": f"Error getting third-party library paths: {str(e)}"}],
            isError=True
        )