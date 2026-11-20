"""
Read Source File MCP Tool

Copyright (C) Jilin Province Zuoyou Software Development Co., Ltd.
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
Update & Mod By Crystalxp (黑夜杀手 QQ:281309196)

Provides the ability to read Delphi source file content
The tool first verifies whether the file exists in the knowledge base, then reads the file content directly from disk
Supports locating files from the global knowledge base (official source, third-party libraries) and the project knowledge base
"""

import os
import re
from typing import Any, Optional
from pathlib import Path
import sqlite3
import logging
import locale
from mcp.types import CallToolResult
from ..constants import DIR_DELPHI_KB
from ..utils.file_backup import detect_encoding
from .project_knowledge_base import get_project_kb

logger = logging.getLogger(__name__)


# ── Workspace root cache (synced with file_tool._workspace_root) ──
_workspace_root: Optional[str] = None


def set_workspace_root(root: Optional[str]) -> None:
    """Set the AI Agent workspace root directory (called by server.py during initialization)."""
    global _workspace_root
    _workspace_root = root
    if root:
        logger.info("read_source_file: Workspace root directory set: %s", root)


def get_workspace_root() -> Optional[str]:
    """Get the cached workspace root directory, returns None if not set."""
    return _workspace_root


def _resolve_relative_path(file_path: str, project_path: Optional[str] = None) -> str:
    """Resolve a relative path, preferring resolution based on project_path or _workspace_root.

    When file_path is a relative path, resolution is attempted in the following priority order:
      1. Resolve based on project_path (explicitly provided project root directory)
      2. Resolve based on _workspace_root (AI Agent workspace root directory)
      3. Resolve based on the current working directory (preserving the original behavior)

    When file_path is already an absolute path or the resolved file does not exist, the original path is returned.

    Args:
        file_path: File path (may be relative or absolute)
        project_path: Project root directory (optional)

    Returns:
        The resolved path (preferring a path where the file exists)
    """
    # Absolute paths are returned directly
    if os.path.isabs(file_path):
        return file_path

    # Relative path, attempt resolution by priority
    candidates = []
    if project_path:
        candidates.append(os.path.join(project_path, file_path))
    if _workspace_root:
        candidates.append(os.path.join(_workspace_root, file_path))

    for candidate in candidates:
        if os.path.isfile(candidate):
            logger.debug("Relative path resolved: %s -> %s", file_path, candidate)
            return candidate

    # Not found, return the original path (the caller decides the subsequent behavior)
    return file_path

# Knowledge base service instances
delphi_kb_service = None
thirdparty_kb_service = None


def set_knowledge_base_services(delphi_service, thirdparty_service):
    """Set the knowledge base service instances"""
    global delphi_kb_service, thirdparty_kb_service
    delphi_kb_service = delphi_service
    thirdparty_kb_service = thirdparty_service


def _get_kb_db_path(kb_service) -> Path:
    """Get the actual database file path of the knowledge base (reads config.json)"""
    kb_dir = kb_service.kb_dir
    config_path = kb_dir / "config.json"
    db_name = "knowledge.sqlite"  # Default value
    if config_path.exists():
        try:
            import json
            with open(config_path, encoding='utf-8') as f:
                config = json.load(f)
            db_name = config.get('database', {}).get('file', db_name)
        except Exception as e:
            logger.debug("Failed to read knowledge base config: %s", str(e))
    return kb_dir / db_name


def _search_project_kb_db(project_path: str, file_path: str) -> Optional[Path]:
    """Search for a file in the project knowledge base SQLite"""
    try:
        kb_dir = Path(project_path).parent / DIR_DELPHI_KB
        db_file = kb_dir / "knowledge.sqlite"
        if not db_file.exists():
            return None
        from src.services.knowledge_base.schema import use_connection
        with use_connection(str(db_file), use_wal=False) as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()
            normalized = file_path.replace('\\', '/')
            backslashed = file_path.replace('/', '\\')
            name_part = Path(file_path).name
            c.execute("""
                SELECT full_path FROM files
                WHERE full_path = ? OR full_path = ? OR full_path = ?
                   OR full_path LIKE ? OR full_path LIKE ?
                   OR relative_path = ? OR relative_path = ? OR relative_path = ?
                   OR relative_path LIKE ? OR relative_path LIKE ?
                   OR relative_path LIKE ?
                LIMIT 1
            """, (
                file_path, normalized, backslashed,
                f'%/{normalized}', f'%\\{backslashed}',
                file_path, normalized, backslashed,
                f'%/{normalized}', f'%\\{backslashed}',
                f'%/{name_part}'
            ))
            row = c.fetchone()
            if row and row['full_path'] and Path(row['full_path']).exists():
                return Path(row['full_path'])
    except Exception as e:
        logger.debug("Project KB search failed: %s", str(e))
    return None


def _find_file_in_knowledge_base(file_path: str, project_path: Optional[str] = None) -> Optional[Path]:
    """
    Search for a file in the knowledge base
    
    Args:
        file_path: File path (may be a relative path or a full path)
        project_path: Project root directory (optional, used to resolve relative paths)
        
    Returns:
        The full path of the file, or None if not found
    """
    # 0. Resolve relative path: based on project_path or _workspace_root
    resolved_path = _resolve_relative_path(file_path, project_path)

    # 1. First check whether it is a full path and the file exists
    full_path = Path(resolved_path)
    if full_path.exists() and full_path.is_file():
        return full_path
    
    # Prepare multiple path formats for matching (the DB may store forward slashes / or backslashes \)
    normalized = file_path.replace('\\', '/')            # Forward-slash version
    backslashed = file_path.replace('/', '\\')            # Backslash version
    name_part = Path(file_path).name                      # File name only, e.g. "System.Classes.pas"
    
    # 2. Search in all knowledge bases (Delphi official + third-party libraries)
    for kb_service in [delphi_kb_service, thirdparty_kb_service]:
        if not kb_service:
            continue
        # Auto-load the knowledge base (kb_instance is None on the first call)
        if kb_service.kb_instance is None:
            try:
                kb_service.load_knowledge_base()
            except Exception as e:
                logger.debug("Failed to load knowledge base: %s", str(e))
        if not kb_service.kb_instance:
            continue
        try:
            db_path = _get_kb_db_path(kb_service)
            if not db_path.exists():
                continue
            
            from src.services.knowledge_base.schema import use_connection
            with use_connection(str(db_path), use_wal=False) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                
                # Detect the path column name of the files table
                cursor.execute(f"PRAGMA table_info(files)")
                col_names = {r['name'] for r in cursor.fetchall()}
                path_col = 'relative_path' if 'relative_path' in col_names else 'path'
                
                # Multi-strategy matching:
                #   1) Exact match (original path, forward-slash, backslash formats)
                #   2) LIKE fuzzy matching (path suffix matching, handling both separators)
                #   3) Match by file name suffix
                cursor.execute(f"""
                    SELECT full_path FROM files 
                    WHERE {path_col} = ? OR {path_col} = ? OR {path_col} = ?
                       OR {path_col} LIKE ? OR {path_col} LIKE ?
                       OR {path_col} LIKE ? OR {path_col} LIKE ?
                       OR full_path LIKE ? OR full_path LIKE ?
                       OR {path_col} LIKE ?
                    LIMIT 1
                """, (
                    file_path, normalized, backslashed,
                    f'%/{normalized}', f'%\\{normalized}',
                    f'%/{backslashed}', f'%\\{backslashed}',
                    f'%/{normalized}', f'%\\{backslashed}',
                    f'%/{name_part}'
                ))
                
                row = cursor.fetchone()
            
            if row and row['full_path'] and Path(row['full_path']).exists():
                return Path(row['full_path'])
        except Exception as e:
            logger.debug("Global KB search failed: %s", str(e))
    
    # 3. Search in the project knowledge base
    if project_path:
        try:
            result = _search_project_kb_db(project_path, file_path)
            if result:
                return result
        except Exception as e:
            logger.debug("Project KB search failed: %s", str(e))
    
    return None


async def read_source_file(arguments: Any) -> CallToolResult:
    """
    Read Delphi source file content
    
    The tool first verifies whether the file exists in the knowledge base and obtains the full path of the file,
    then reads the file content directly from disk. Supports reading the full file or a specified range of content.
    
    Args:
        arguments: Contains the following parameters:
            - file_path: File path (relative path or full path) (required)
            - start_line: Start line number (optional, starts from 1, default 1)
            - end_line: End line number (optional, defaults to end of file)
            - max_lines: Maximum number of lines to return (optional, default 500, max 1000)
            - search_in: Search scope (optional)
                - "all": All knowledge bases (default)
                - "delphi": Delphi official source only
                - "thirdparty": Third-party libraries only
    
    Returns:
        File content
    """
    file_path = arguments.get("file_path")
    if not file_path:
        return CallToolResult(
            content=[{"type": "text", "text": "Please provide a file path"}],
            isError=True
        )
    
    # Parse arguments
    start_line = arguments.get("start_line", 1)
    end_line = arguments.get("end_line")
    max_lines = min(arguments.get("max_lines", 500), 1000)  # Limit to a maximum of 1000 lines
    search_in = arguments.get("search_in", "all")
    project_path = arguments.get("project_path")
    
    try:
        # Find the file
        full_path = _find_file_in_knowledge_base(file_path, project_path)
        
        if not full_path:
            return CallToolResult(
                content=[{"type": "text", "text": f"File not found: {file_path}\n\n"
                        f"Tip: The file may not be in the knowledge base. You can:\n"
                        f"1. Use search_class or search_function to find related files\n"
                        f"2. Use semantic_search to semantically search related code\n"
                        f"3. Make sure the corresponding knowledge base has been built"}],
                isError=True
            )
        
        # Encoding detection + fallback chain reading (consistent with delphi_file._read_content)
        detected = detect_encoding(str(full_path))
        encodings_to_try = [detected]
        if detected not in ('utf-8', 'utf-8-sig'):
            encodings_to_try.append('utf-8')
        try:
            ansi = locale.getpreferredencoding()
            if ansi.lower() not in (e.lower() for e in encodings_to_try):
                encodings_to_try.append(ansi)
        except Exception as e:
            logger.debug("Failed to get ANSI encoding (does not affect the main flow): %s", e)

        encoding_used = 'utf-8'
        all_lines = None
        for enc in encodings_to_try:
            try:
                with open(full_path, 'r', encoding=enc) as f:
                    all_lines = f.readlines()
                encoding_used = enc
                break
            except UnicodeDecodeError:
                continue

        if all_lines is None:
            # All encoding attempts failed; fall back to utf-8 and ignore erroneous characters
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                all_lines = f.readlines()
        
        total_lines = len(all_lines)
        
        # Handle the line number range
        if start_line < 1:
            start_line = 1
        
        if end_line is None or end_line > total_lines:
            end_line = total_lines
        
        if end_line < start_line:
            end_line = start_line
        
        # Limit the maximum number of lines
        if end_line - start_line + 1 > max_lines:
            end_line = start_line + max_lines - 1
        
        # Extract the lines in the specified range
        selected_lines = all_lines[start_line - 1:end_line]
        
        # Build the output
        output = f"File: {full_path.name}\n"
        output += f"Full path: {full_path}\n"
        output += f"Encoding: {encoding_used}\n"
        output += f"Total lines: {total_lines}\n"
        output += f"Showing range: line {start_line} to line {end_line}"
        
        if end_line < total_lines:
            output += f" ({end_line - start_line + 1} lines in total)"
        output += "\n"
        output += "=" * 60 + "\n\n"
        
        # Add line numbers and output
        for i, line in enumerate(selected_lines, start=start_line):
            # Ensure line numbers are aligned
            line_num = str(i).rjust(len(str(total_lines)))
            output += f"{line_num} | {line}"
        
        # If there is remaining content, prompt the user
        if end_line < total_lines:
            remaining = total_lines - end_line
            output += f"\n... ({remaining} lines not shown) ...\n"
            output += f"Tip: Use start_line={end_line + 1} to continue reading the following content\n"
        
        return CallToolResult(content=[{"type": "text", "text": output}])
        
    except Exception as e:
        return CallToolResult(
            content=[{"type": "text", "text": f"Error reading file: {str(e)}"}],
            isError=True
        )


def _extract_result_file_path(result: dict) -> Optional[str]:
    """Extract the file path from a KB search result"""
    file_info = result.get('file')
    if isinstance(file_info, dict):
        path = file_info.get('full_path') or file_info.get('path')
        if path:
            return path
    return result.get('full_path') or result.get('relative_path')



def _read_file_for_function(file_path: str, function_name: str, max_lines: int) -> CallToolResult:
    """Synchronously read the file and use a regex to find the function definition"""
    for enc in ('utf-8', 'gbk', 'utf-8-sig'):
        try:
            with open(file_path, 'r', encoding=enc, errors='replace') as f:
                content = f.read()
            break
        except (FileNotFoundError, UnicodeDecodeError, UnicodeError):
            continue
    else:
        return CallToolResult(
            content=[{"type": "text", "text": f"Unable to read file with utf-8/gbk encoding: {file_path}"}],
            isError=True
        )

    lines = content.splitlines()
    total_lines = len(lines)

    pattern = re.compile(
        r'(?:procedure|function|constructor|destructor)\s+' + re.escape(function_name) + r'\b',
        re.IGNORECASE
    )

    found = [i for i, line in enumerate(lines, 1) if pattern.search(line)]

    if not found:
        return CallToolResult(
            content=[{"type": "text", "text": f"Function/procedure '{function_name}' not found in file '{os.path.basename(file_path)}'"}],
            isError=True
        )

    line = found[0]
    read_start = max(1, line - 5)
    read_end = min(total_lines, read_start + max_lines - 1)
    selected = lines[read_start - 1:read_end]

    output = f"File: {file_path} (lines {read_start}-{read_end}, {total_lines} lines in total)\n"
    output += "=" * 60 + "\n\n"
    for i, ln in enumerate(selected, start=read_start):
        line_num = str(i).rjust(len(str(total_lines)))
        output += f"{line_num} | {ln}\n"

    if read_end < total_lines:
        output += f"\n... ({total_lines - read_end} lines not shown) ...\n"

    return CallToolResult(content=[{"type": "text", "text": output}])


async def _search_function_in_file(
    file_path: str,
    function_name: str,
    max_lines: int = 100,
) -> CallToolResult:
    """Fallback strategy: read the file directly, use a regex to find the function definition line number, and return context"""
    import asyncio
    return await asyncio.to_thread(_read_file_for_function, file_path, function_name, max_lines)


async def search_and_read_file(arguments: Any) -> CallToolResult:
    """
    Search for and read a file
    
    Searches by type name (class, record, interface) or function name, then reads the content of the found file.
    
    Args:
        arguments: Contains the following parameters:
            - file_path: Specify a file path (optional; when specified, filters KB results by path, and falls back to directly grepping the file when there is no match)
            - type_name: Type name (class, record, interface, optional)
            - record_name: Record type name (optional, choose one of type_name)
            - function_name: Function name (optional)
            - search_in: Search scope (optional)
                - "all": All knowledge bases (default)
                - "delphi": Delphi official source only
                - "project": Project source only (requires project_path)
                - "thirdparty": Third-party libraries only
            - start_line: Start line number (optional, default 1)
            - max_lines: Maximum number of lines to return (optional, default 100)
    
    Returns:
        File content
    """
    type_name = arguments.get("type_name")
    record_name = arguments.get("record_name")
    function_name = arguments.get("function_name")
    search_in = arguments.get("search_in", "all")
    start_line = arguments.get("start_line", 1)
    max_lines = arguments.get("max_lines", 100)
    project_path = arguments.get("project_path")
    file_path = arguments.get("file_path")
    
    # Compatible with the old parameter name class_name
    if not type_name and arguments.get("class_name"):
        type_name = arguments.get("class_name")
    
    if not type_name and not record_name and not function_name:
        return CallToolResult(
            content=[{"type": "text", "text": "Please provide a type name (type_name/record_name) or a function name"}],
            isError=True
        )

    if search_in == "project" and not project_path:
        return CallToolResult(
            content=[{"type": "text", "text": "search_in='project' requires the project_path parameter"}],
            isError=True
        )
    
    try:
        results = []
        
        # Determine the search name
        search_name = type_name or record_name
        is_record_search = record_name is not None

        # Search in the project knowledge base (requires project_path). When search_in=all, project
        # results are only included if the project path is explicitly provided, to avoid accidentally
        # scanning the current directory without context.
        if search_in in ["all", "project"] and project_path:
            try:
                project_kb = get_project_kb(project_path)
                project_kb.load_knowledge_bases()
                if search_name:
                    if project_kb.project_kb is None:
                        project_results = []
                    else:
                        project_results = project_kb.project_kb.search_by_name(search_name)
                    if is_record_search:
                        project_results = [
                            r for r in project_results
                            if r.get('kind_code', '') == 'TR'
                            or r.get('kind') == 'record'
                        ]
                    elif type_name:
                        project_results = [
                            r for r in project_results
                            if r.get('kind_code', '') in ('TC', 'TR', 'TI', 'TE', 'TS', 'TY')
                        ]
                    results.extend(project_results)
                if function_name:
                    if project_kb.project_kb is not None:
                        func_results = project_kb.project_kb.search_by_name(function_name)
                        func_results = [
                            r for r in func_results
                            if r.get('kind_code', '') in ('FF', 'FP')
                        ]
                        results.extend(func_results)
            except Exception as e:
                logger.debug("Project KB search failed: %s", str(e))
        
        # Search in the Delphi official source
        if search_in in ["all", "delphi"] and delphi_kb_service:
            # Ensure the knowledge base is loaded
            if not delphi_kb_service.kb_instance:
                delphi_kb_service.load_knowledge_base()
            
            if delphi_kb_service.kb_instance:
                if search_name:
                    # DelphiKnowledgeBaseService only has search_by_name; use it to search and then filter by kind_code
                    all_results = delphi_kb_service.search_by_name(search_name)
                    if is_record_search:
                        all_results = [r for r in all_results if r.get('kind_code', '') == 'TR']
                    elif type_name:
                        # Search for type definitions such as classes/interfaces/enums
                        all_results = [r for r in all_results if r.get('kind_code', '') in ('TC', 'TR', 'TI', 'TE', 'TS', 'TY')]
                    results.extend(all_results)
                if function_name:
                    func_results = delphi_kb_service.search_by_name(function_name)
                    func_results = [r for r in func_results if r.get('kind_code', '') in ('FF', 'FP')]
                    results.extend(func_results)
        
        # Search in third-party libraries (ThirdPartyKnowledgeBase has search_by_class_name / search_by_function_name)
        if search_in in ["all", "thirdparty"] and thirdparty_kb_service:
            # Ensure the knowledge base is loaded
            if not thirdparty_kb_service.kb_instance:
                thirdparty_kb_service.load_knowledge_base()
            
            if thirdparty_kb_service.kb_instance:
                if search_name:
                    all_results = thirdparty_kb_service.search_by_class_name(search_name)
                    if is_record_search:
                        all_results = [r for r in all_results if r.get('kind_code', '') == 'TR']
                    results.extend(all_results)
                if function_name:
                    results.extend(thirdparty_kb_service.search_by_function_name(function_name))
        
        # If file_path is specified, filter KB results by path to ensure records matching the specified file are returned
        if file_path and results:
            target = os.path.abspath(file_path).lower()
            filtered = [
                r for r in results
                if _extract_result_file_path(r)
                and os.path.abspath(_extract_result_file_path(r)).lower() == target
            ]
            if filtered:
                results = filtered
            elif function_name and os.path.exists(file_path):
                # A file was specified but there is no match in the KB → fall back to directly grepping the file
                return await _search_function_in_file(file_path, function_name, max_lines)

        if not results:
            search_term = search_name or function_name
            return CallToolResult(
                content=[{"type": "text", "text": f"'{search_term}' not found"}],
                isError=True
            )
        
        # Get the first result
        result = results[0]
        
        # Extract the file path from the result: check multiple nested formats
        # search_by_name return format: result['file']['path'] / result['file']['full_path']
        # search_by_class_name return format: result['full_path'] / result['relative_path']
        file_path = None
        file_info = result.get('file')
        if isinstance(file_info, dict):
            file_path = file_info.get('full_path') or file_info.get('path')
        if not file_path:
            file_path = result.get('full_path') or result.get('relative_path')
        
        # If still not found, fall back to querying by file_id
        if not file_path:
            file_id = result.get('file_id')
            kb = delphi_kb_service or thirdparty_kb_service
            if file_id and kb:
                try:
                    db_path = _get_kb_db_path(kb)
                    if db_path.exists():
                        from src.services.knowledge_base.schema import use_connection
                        with use_connection(str(db_path), use_wal=False) as conn:
                            conn.row_factory = sqlite3.Row
                            cur = conn.cursor()
                            cur.execute("SELECT full_path, relative_path, path FROM files WHERE id = ?", (file_id,))
                            row = cur.fetchone()
                            if row:
                                file_path = row['full_path'] or row['relative_path'] or row['path']
                except Exception as e:
                    logger.debug("Failed to search for file path: %s", str(e))
        
        if not file_path:
            return CallToolResult(
                content=[{"type": "text", "text": f"Search result is missing file path information: {result}"}],
                isError=True
            )
        
        line = result.get('line', 1)
        start_line = max(1, line - 5)
        
        # Call read_source_file to read the file
        read_args = {
            "file_path": file_path,
            "start_line": start_line,
            "max_lines": max_lines,
            "project_path": project_path,
        }
        
        return await read_source_file(read_args)
        
    except Exception as e:
        return CallToolResult(
            content=[{"type": "text", "text": f"Error searching and reading file: {str(e)}"}],
            isError=True
        )