"""
Third-party library knowledge base MCP tools

Copyright (C) Jilin Province Zuoyou Software Development Co., Ltd.
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
Update & Mod By Crystalxp (Dark Night Killer QQ:281309196)

Provides MCP tools for building and querying the third-party library knowledge base
"""

from typing import Any
from mcp.types import CallToolResult

# Third-party library knowledge base service instance
thirdparty_kb_service = None


def set_thirdparty_knowledge_base_service(service):
    """Set the third-party library knowledge base service instance"""
    global thirdparty_kb_service
    thirdparty_kb_service = service


async def build_thirdparty_knowledge_base(arguments: Any) -> CallToolResult:
    """
    Build the third-party library knowledge base

    Args:
        arguments: Contains the following parameters:
            - version: Delphi version (optional)
            - rebuild: Whether to force rebuild (optional, default false)

    Returns:
        Build result
    """
    global thirdparty_kb_service

    if thirdparty_kb_service is None:
        return CallToolResult(
            content=[{"type": "text", "text": "Third-party library knowledge base service is not initialized"}],
            isError=True
        )

    version = arguments.get("version")
    rebuild = arguments.get("rebuild", False)

    try:
        # Get the path list (do not build, only display)
        paths = thirdparty_kb_service.get_library_paths(version)

        if not paths:
            return CallToolResult(
                content=[{"type": "text", "text": "No third-party library paths found. Please check the Delphi installation and Library configuration"}],
                isError=True
            )

        # Build the knowledge base
        success = thirdparty_kb_service.build_thirdparty_knowledge_base(
            version=version,
            rebuild=rebuild
        )

        if success:
            stats = thirdparty_kb_service.get_statistics()
            return CallToolResult(
                content=[{
                    "type": "text",
                    "text": f"Third-party library knowledge base built successfully!\n\n"
                            f"Scanned paths: {len(paths)}\n"
                            f"Statistics:\n"
                            f"- Classes: {stats.get('classes', 0)}\n"
                            f"- Files: {stats.get('files', 0)}\n"
                            f"- Database size: {stats.get('database_size_mb', 0):.2f} MB\n\n"
                            f"Scanned third-party library paths:\n" +
                            "\n".join([f"  - {p}" for p in paths[:10]]) +
                            (f"\n  ... {len(paths)} paths in total" if len(paths) > 10 else "")
                }]
            )
        else:
            return CallToolResult(
                content=[{"type": "text", "text": "Failed to build the third-party library knowledge base"}],
                isError=True
            )

    except Exception as e:
        return CallToolResult(
            content=[{"type": "text", "text": f"Error building the third-party library knowledge base: {str(e)}"}],
            isError=True
        )


async def search_thirdparty_class(arguments: Any) -> CallToolResult:
    """
    Search for a class in the third-party library

    Args:
        arguments: Contains the following parameters:
            - class_name: Class name (required)

    Returns:
        Search results
    """
    global thirdparty_kb_service

    if thirdparty_kb_service is None:
        return CallToolResult(
            content=[{"type": "text", "text": "Third-party library knowledge base service is not initialized"}],
            isError=True
        )

    class_name = arguments.get("class_name")
    if not class_name:
        return CallToolResult(
            content=[{"type": "text", "text": "Please provide a class name"}],
            isError=True
        )

    try:
        results = thirdparty_kb_service.search_by_class_name(class_name)

        if not results:
            return CallToolResult(
                content=[{"type": "text", "text": f"Class '{class_name}' not found in the third-party library"}]
            )

        # Format results
        output = f"Found {len(results)} classes '{class_name}' in the third-party library:\n\n"
        for i, result in enumerate(results, 1):
            output += f"{i}. File: {result['file']['path']}\n"
            output += f"   Class name: {result['class']['name']}\n"
            output += f"   Base class: {result['class']['base_class']}\n"
            output += f"   Line: {result['class']['line']}\n"
            output += f"   Full path: {result['file']['full_path']}\n\n"

        return CallToolResult(content=[{"type": "text", "text": output}])

    except Exception as e:
        return CallToolResult(
            content=[{"type": "text", "text": f"Error searching for class: {str(e)}"}],
            isError=True
        )


async def search_thirdparty_function(arguments: Any) -> CallToolResult:
    """
    Search for a function in the third-party library

    Args:
        arguments: Contains the following parameters:
            - function_name: Function name (required)

    Returns:
        Search results
    """
    global thirdparty_kb_service

    if thirdparty_kb_service is None:
        return CallToolResult(
            content=[{"type": "text", "text": "Third-party library knowledge base service is not initialized"}],
            isError=True
        )

    function_name = arguments.get("function_name")
    if not function_name:
        return CallToolResult(
            content=[{"type": "text", "text": "Please provide a function name"}],
            isError=True
        )

    try:
        results = thirdparty_kb_service.search_by_function_name(function_name)

        if not results:
            return CallToolResult(
                content=[{"type": "text", "text": f"Function '{function_name}' not found in the third-party library"}]
            )

        # Format results
        output = f"Found {len(results)} functions '{function_name}' in the third-party library:\n\n"
        for i, result in enumerate(results, 1):
            output += f"{i}. File: {result['file']['path']}\n"
            output += f"   Function name: {result['function']['name']}\n"
            output += f"   Type: {result['function']['type']}\n"
            output += f"   Line: {result['function']['line']}\n"
            output += f"   Full path: {result['file']['full_path']}\n\n"

        return CallToolResult(content=[{"type": "text", "text": output}])

    except Exception as e:
        return CallToolResult(
            content=[{"type": "text", "text": f"Error searching for function: {str(e)}"}],
            isError=True
        )


async def semantic_search_thirdparty(arguments: Any) -> CallToolResult:
    """
    Perform semantic search in the third-party library

    Args:
        arguments: Contains the following parameters:
            - query: Search query (required)
            - top_k: Number of results to return (optional, default 200, max 500)

    Returns:
        Search results
    """
    global thirdparty_kb_service

    if thirdparty_kb_service is None:
        return CallToolResult(
            content=[{"type": "text", "text": "Third-party library knowledge base service is not initialized"}],
            isError=True
        )

    query = arguments.get("query")
    if not query:
        return CallToolResult(
            content=[{"type": "text", "text": "Please provide a search query"}],
            isError=True
        )

    top_k = min(arguments.get("top_k", 200), 500)

    try:
        # Search classes and functions
        class_results = thirdparty_kb_service.semantic_search_classes(query, top_k=top_k)
        function_results = thirdparty_kb_service.semantic_search_functions(query, top_k=top_k)

        if not class_results and not function_results:
            return CallToolResult(
                content=[{"type": "text", "text": f"No content related to '{query}' found in the third-party library"}]
            )

        # Format results
        output = f"Semantic search results for '{query}' in the third-party library:\n\n"

        if class_results:
            output += f"Related classes (Top {len(class_results)}):\n"
            for class_name, score in class_results[:5]:
                # Get detailed information
                exact_results = thirdparty_kb_service.search_by_class_name(class_name)
                if exact_results:
                    result = exact_results[0]
                    output += f"  - {result['class']['name']} (similarity: {score:.3f})\n"
                    output += f"    Location: {result['file']['path']}\n"
                    output += f"    Base class: {result['class']['base_class']}\n"
                    output += f"    Line: {result['class']['line']}\n\n"

        if function_results:
            output += f"Related functions (Top {len(function_results)}):\n"
            for func_name, score in function_results[:5]:
                # Get detailed information
                exact_results = thirdparty_kb_service.search_by_function_name(func_name)
                if exact_results:
                    result = exact_results[0]
                    output += f"  - {result['function']['name']} (similarity: {score:.3f})\n"
                    output += f"    Location: {result['file']['path']}\n"
                    output += f"    Type: {result['function']['type']}\n"
                    output += f"    Line: {result['function']['line']}\n\n"

        return CallToolResult(content=[{"type": "text", "text": output}])

    except Exception as e:
        return CallToolResult(
            content=[{"type": "text", "text": f"Error during semantic search: {str(e)}"}],
            isError=True
        )


async def get_thirdparty_kb_stats(arguments: Any) -> CallToolResult:
    """
    Get third-party library knowledge base statistics

    Args:
        arguments: No parameters

    Returns:
        Statistics
    """
    global thirdparty_kb_service

    if thirdparty_kb_service is None:
        return CallToolResult(
            content=[{"type": "text", "text": "Third-party library knowledge base service is not initialized"}],
            isError=True
        )

    try:
        stats = thirdparty_kb_service.get_statistics()

        if not stats:
            return CallToolResult(
                content=[{"type": "text", "text": "Third-party library knowledge base has not been built. Please use the build_thirdparty_knowledge_base tool to build it first"}]
            )

        # Format results
        output = "Third-party library knowledge base statistics:\n\n"
        output += f"- Classes: {stats.get('classes', 0)}\n"
        output += f"- Files: {stats.get('files', 0)}\n"
        output += f"- Database size: {stats.get('database_size_mb', 0):.2f} MB\n"
        output += f"- Number of third-party library paths: {stats.get('thirdparty_paths_count', 0)}\n"
        output += f"- Delphi version: {stats.get('delphi_version', 'Unknown')}\n"

        return CallToolResult(content=[{"type": "text", "text": output}])

    except Exception as e:
        return CallToolResult(
            content=[{"type": "text", "text": f"Error getting statistics: {str(e)}"}],
            isError=True
        )


async def get_thirdparty_paths(arguments: Any) -> CallToolResult:
    """
    Get the list of third-party library paths

    Args:
        arguments: Contains the following parameters:
            - version: Delphi version (optional)

    Returns:
        List of third-party library paths
    """
    global thirdparty_kb_service

    if thirdparty_kb_service is None:
        return CallToolResult(
            content=[{"type": "text", "text": "Third-party library knowledge base service is not initialized"}],
            isError=True
        )

    version = arguments.get("version")

    try:
        paths = thirdparty_kb_service.get_library_paths(version)

        if not paths:
            return CallToolResult(
                content=[{"type": "text", "text": "No third-party library paths found"}]
            )

        # Format results
        output = f"Found {len(paths)} third-party library paths:\n\n"
        for i, path in enumerate(paths, 1):
            output += f"{i}. {path}\n"

        return CallToolResult(content=[{"type": "text", "text": output}])

    except Exception as e:
        return CallToolResult(
            content=[{"type": "text", "text": f"Error getting path list: {str(e)}"}],
            isError=True
        )


async def search_record(arguments: Any) -> CallToolResult:
    """
    Search for a record type in the third-party library

    Args:
        arguments: Contains the following parameters:
            - record_name: Record type name (required)

    Returns:
        Search results
    """
    global thirdparty_kb_service

    if thirdparty_kb_service is None:
        return CallToolResult(
            content=[{"type": "text", "text": "Third-party library knowledge base service is not initialized"}],
            isError=True
        )

    record_name = arguments.get("record_name")
    if not record_name:
        return CallToolResult(
            content=[{"type": "text", "text": "Please provide a record type name"}],
            isError=True
        )

    try:
        # Use search_by_class_name to search, then filter results with type_kind='record'
        results = thirdparty_kb_service.search_by_class_name(record_name)

        # Filter out record types
        record_results = [r for r in results if r.get('class', {}).get('type_kind') == 'record']

        if not record_results:
            # If there is no exact match, try searching all types and show suggestions
            all_results = thirdparty_kb_service.search_by_class_name(record_name)
            if all_results:
                output = f"Record type '{record_name}' not found, but the following types were found:\n\n"
                for result in all_results[:5]:
                    type_kind = result.get('class', {}).get('type_kind', 'class')
                    output += f"  - {result['class']['name']} ({type_kind})\n"
                    output += f"    Location: {result['file']['path']}\n"
                    output += f"    Line: {result['class']['line']}\n\n"
                return CallToolResult(content=[{"type": "text", "text": output}])
            else:
                return CallToolResult(
                    content=[{"type": "text", "text": f"'{record_name}' not found in the third-party library"}]
                )

        # Format results
        output = f"Found {len(record_results)} record types '{record_name}' in the third-party library:\n\n"

        for i, result in enumerate(record_results, 1):
            output += f"{i}. Type: {result['class']['name']}\n"
            output += f"   Base class/parent record: {result['class']['base_class'] or 'None'}\n"
            output += f"   File: {result['file']['path']}\n"
            output += f"   Full path: {result['file']['full_path']}\n"
            output += f"   Line: {result['class']['line']}\n\n"

        return CallToolResult(content=[{"type": "text", "text": output}])

    except Exception as e:
        return CallToolResult(
            content=[{"type": "text", "text": f"Error during search: {str(e)}"}],
            isError=True
        )


async def search_by_filename(arguments: Any) -> CallToolResult:
    """
    Search for files by filename

    Args:
        arguments: Contains the following parameters:
            - filename: Filename or wildcard pattern (required)
            - search_in: Search scope (optional)
                - "all": All knowledge bases (default)
                - "delphi": Delphi official source only
                - "thirdparty": Third-party libraries only

    Returns:
        Search results
    """
    global thirdparty_kb_service

    if thirdparty_kb_service is None:
        return CallToolResult(
            content=[{"type": "text", "text": "Third-party library knowledge base service is not initialized"}],
            isError=True
        )

    filename = arguments.get("filename")
    if not filename:
        return CallToolResult(
            content=[{"type": "text", "text": "Please provide a filename"}],
            isError=True
        )

    search_in = arguments.get("search_in", "all")

    try:
        from src.services.knowledge_base.schema import use_connection
        from pathlib import Path

        results = []

        # Search in third-party libraries
        if search_in in ["all", "thirdparty"]:
            with use_connection(str(thirdparty_kb_service.kb_dir / 'knowledge.sqlite'), use_wal=False) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                # Use LIKE for wildcard matching
                pattern = filename.replace('*', '%').replace('?', '_')
                cursor.execute("""
                    SELECT path, full_path, extension, size, line_count FROM files
                    WHERE path LIKE ? OR full_path LIKE ?
                    ORDER BY path
                """, (f'%{pattern}%', f'%{pattern}%'))

                for row in cursor.fetchall():
                    results.append({
                        'source': 'Third-party library',
                        'path': row['path'],
                        'full_path': row['full_path'],
                        'extension': row['extension'],
                        'size': row['size'],
                        'line_count': row['line_count']
                    })

        if not results:
            return CallToolResult(
                content=[{"type": "text", "text": f"No files matching '{filename}' found"}]
            )

        # Format results
        output = f"Found {len(results)} files matching '{filename}':\n\n"

        for i, result in enumerate(results[:20], 1):  # Display at most 20
            output += f"{i}. [{result['source']}] {result['path']}\n"
            output += f"   Full path: {result['full_path']}\n"
            output += f"   Size: {result['size']} bytes, lines: {result['line_count']}\n\n"

        if len(results) > 20:
            output += f"... {len(results) - 20} more results not shown\n"

        return CallToolResult(content=[{"type": "text", "text": output}])

    except Exception as e:
        return CallToolResult(
            content=[{"type": "text", "text": f"Error during search: {str(e)}"}],
            isError=True
        )

