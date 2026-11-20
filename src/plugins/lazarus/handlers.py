"""Lazarus/FPC plugin tool handlers — pure functions independent of plugin instances.

Follows the Delphi plugin handlers.py pattern:
  1. Each handler accepts (arguments: dict) → returns Any (dict / CallToolResult)
  2. Exports LAZARUS_HANDLERS / LAZARUS_TOOL_DESCRIPTIONS / LAZARUS_TOOL_SCHEMAS
  3. Handlers lazily import CompilerService / LpiParser internally to avoid module-level dependencies
"""

from pathlib import Path
from typing import Any, List

from src.utils.logger import init_default_logger

logger = init_default_logger()


# ============================================================
# Tool handler functions
# ============================================================

async def _handle_lazarus_compile(arguments: dict) -> dict:
    """Compile a Lazarus/Free Pascal project (.lpi / .lpr)

    Arguments:
        project_path (str): .lpi or .lpr file path (required)
        target_platform (str, optional): win32 / win64, default win32
        build_configuration (str, optional): Default / Release / Debug
        timeout (int, optional): Timeout in seconds, default 600
        run_verify (bool, optional): After a successful build, launch the program for 3 seconds to verify it does not crash, default false
    """
    from src.services.compiler_service import CompilerService
    from src.services.config_manager import ConfigManager
    from src.models.compile_request import ProjectCompileRequest, CompileOptions, TargetPlatform

    project_path = arguments.get("project_path", "")
    if not project_path:
        return {"status": "failed", "error": "Missing required parameter: project_path"}

    platform_map = {
        "win32": TargetPlatform.WIN32,
        "win64": TargetPlatform.WIN64,
    }
    target = platform_map.get(
        arguments.get("target_platform", "win32").lower(),
        TargetPlatform.WIN32,
    )
    build_config = arguments.get("build_configuration")
    timeout = int(arguments.get("timeout", 600))
    run_verify = arguments.get("run_verify", False)

    compile_opts = CompileOptions(
        target_platform=target,
        build_configuration=build_config,
        timeout=timeout,
    )
    request = ProjectCompileRequest(
        project_path=project_path,
        options=compile_opts,
    )

    cm = ConfigManager()
    cs = CompilerService(cm)
    try:
        result = await cs.compile_with_lazbuild(request)
        result_dict = result.to_dict()

        # ── Run verification ──
        if run_verify and result.status.value == "success":
            verify_info = await _run_lazarus_verify(
                cs, request, project_path, target, build_config
            )
            result_dict["_verify"] = verify_info

        return result_dict
    except Exception as e:
        logger.error(f"lazarus_compile failed: {e}", exc_info=True)
        return {
            "status": "failed",
            "error": f"Compilation failed: {e}",
            "project_path": project_path,
        }


# ============================================================
# run_verify helper functions
# ============================================================

def _get_verify_tools_dir() -> Path:
    """Get the StackTrace tools directory"""
    return Path(__file__).resolve().parents[3] / "tools" / "stacktrace"


def _inject_lazarus_verify_units(lpi_path: str, lpr_path: str) -> dict:
    """Modify .lpi + .lpr to inject the StackTraceFPC verification unit and return backup paths.

    Injected content (.lpi):
       1. Add StackTraceFPC to the Uses section
       2. Add tools/stacktrace to the search path
       3. Enable debug information (-gl -gw)

    Injected content (.lpr):
       1. Append StackTraceFPC to the uses clause
       2. Insert a TStackTraceManagerFPC.Initialize call after the begin block

    Args:
        lpi_path: .lpi file path
        lpr_path: .lpr file path

    Returns:
        dict with backup paths
    """
    import shutil
    import re
    from pathlib import Path

    lpi = Path(lpi_path)
    lpr = Path(lpr_path)
    tools_dir = _get_verify_tools_dir()

    backs = {
        '.lpi': lpi.with_suffix('.lpi.verify_bak'),
        '.lpr': lpr.with_suffix('.lpr.verify_bak'),
    }

    # Backup
    shutil.copy2(str(lpi), str(backs['.lpi']))
    if lpr.exists():
        shutil.copy2(str(lpr), str(backs['.lpr']))

    # ── Modify .lpi ──
    content = lpi.read_text(encoding="utf-8-sig")

    # Add StackTraceFPC to Uses
    rel_stacktrace = tools_dir.name + '/Fpc.StackTrace.pas'
    if 'Fpc_StackTrace' not in content:
        # Find the <Units> node and add it
        units_pattern = r'(<Units>)'
        inject_unit = (
            f'    <Unit Filename="{rel_stacktrace}">\n'
            f'      <IsPartOfProject Value="False"/>\n'
            f'    </Unit>'
        )
        if re.search(units_pattern, content):
            content = re.sub(
                units_pattern,
                lambda m: m.group(1) + '\n' + inject_unit,
                content
            )
        else:
            # If there is no <Units>, add before <CompilerOptions>
            content = content.replace(
                '<CompilerOptions>',
                '<Units>\n' + inject_unit + '\n  </Units>\n  <CompilerOptions>'
            )

    # Add search path
    rel_path = tools_dir.name
    paths_pattern = r'(<OtherUnitFiles[^>]*Value=")(.*?)(")'
    if re.search(paths_pattern, content):
        content = re.sub(
            paths_pattern,
            lambda m: m.group(1) + m.group(2) + (';' if m.group(2).strip() else '') + rel_path + m.group(3),
            content
        )
    else:
        # Add OtherUnitFiles
        content = content.replace(
            '</CompilerOptions>',
            '    <OtherUnitFiles Value="' + rel_path + '"/>\n  </CompilerOptions>'
        )

    # Enable debug information (-gl -gw)
    if '-gl' not in content:
        content = content.replace(
            '</CompilerOptions>',
            '    <CustomOptions Value="-gl -gw"/>\n  </CompilerOptions>'
        )

    lpi.write_text(content, encoding="utf-8-sig")
    logger.info("Injected StackTraceFPC unit into .lpi: %s", lpi_path)

    # ── Modify .lpr ──
    if lpr.exists():
        original = lpr.read_text(encoding='utf-8-sig')
        if 'Fpc_StackTrace' not in original:
            # Append to uses
            uses_pos = original.lower().find('uses')
            if uses_pos >= 0:
                end_uses = original.find(';', uses_pos + 4)
                if end_uses > uses_pos:
                    uses_section = original[uses_pos:end_uses]
                    if 'Fpc_StackTrace' not in uses_section:
                        original = original[:end_uses] + ', Fpc_StackTrace' + original[end_uses:]

            # Add initialization after begin
            lines = original.split('\n')
            begin_idx = -1
            for i, line in enumerate(lines):
                if line.strip() == 'begin':
                    begin_idx = i
                    break

            if begin_idx >= 0:
                inject_lines = [
                    '{STACKTRACE_INJECT}',
                    '  TStackTraceManagerFPC.Initialize;',
                ]
                for j, line in enumerate(inject_lines):
                    lines.insert(begin_idx + 1 + j, line)

                lpr.write_text('\n'.join(lines), encoding='utf-8-sig')
                logger.info("Injected Fpc_StackTrace initialization into .lpr: %s", lpr_path)

    return backs


def _restore_lazarus_files(lpi_path: str, lpr_path: str, backs: dict):
    """Restore the backed-up .lpi and .lpr files"""
    import shutil
    from pathlib import Path

    lpi = Path(lpi_path)
    lpr = Path(lpr_path)

    if backs.get('.lpi') and backs['.lpi'].exists():
        shutil.copy2(str(backs['.lpi']), str(lpi))
        backs['.lpi'].unlink()
        logger.info("Restored .lpi: %s", lpi_path)

    if backs.get('.lpr') and backs['.lpr'].exists():
        shutil.copy2(str(backs['.lpr']), str(lpr))
        backs['.lpr'].unlink()
        logger.info("Restored .lpr: %s", lpr_path)


async def _run_lazarus_verify(
    cs: 'CompilerService',
    request: 'ProjectCompileRequest',
    project_path: str,
    target_platform: 'TargetPlatform',
    build_configuration: str
) -> dict:
    """Run runtime verification for a Lazarus project

    1. Inject the StackTraceFPC unit
    2. Recompile
    3. Run the exe for 3 seconds
    4. Check exception.log
    """
    import asyncio
    from pathlib import Path

    TIMEOUT_PROCESS_TERMINATE = 3.5  # seconds

    try:
        lpi_path = Path(project_path)
        lpr_path = lpi_path.with_suffix('.lpr')
        if not lpr_path.exists():
            # Try to get the main source file from .lpi
            from src.utils.lpi_parser import LpiParser
            parser = LpiParser(str(lpi_path))
            if parser.parse():
                main_src = parser.get_project_info().get('main_source', '')
                if main_src:
                    lpr_path = lpi_path.parent / main_src

        if not lpr_path.exists():
            return {"error": "Could not find the .lpr main source file"}

        # 1. Inject StackTraceFPC
        backs = _inject_lazarus_verify_units(str(lpi_path), str(lpr_path))

        try:
            # 2. Recompile
            verify_result = await cs.compile_with_lazbuild(request)

            if verify_result.status.value != "success":
                err_detail = verify_result.log or verify_result.error_message or "(no log)"
                logger.warning("Compilation failed after injecting StackTraceFPC: %s", err_detail[:500])
                return {"error": "injected compile failed", "log": err_detail[:1000]}

            # 3. Find the exe path
            # Lazarus output path is usually in the output directory
            exe_name = lpr_path.stem + '.exe'
            output_dir = lpi_path.parent / 'bin'
            if not output_dir.exists():
                output_dir = lpi_path.parent
            exe_path = output_dir / exe_name

            if not exe_path.exists():
                return {"error": f"Output file not found: {exe_path}"}

            # 4. Run verification
            exe_dir = exe_path.parent
            log_path = exe_dir / 'exception.log'
            if log_path.exists():
                try:
                    log_path.unlink()
                except Exception as e:
                    logger.debug("Failed to clean exception.log: %s", e)

            import subprocess
            proc = subprocess.Popen([str(exe_path)], cwd=str(exe_dir))
            try:
                proc.wait(timeout=TIMEOUT_PROCESS_TERMINATE)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

            # 5. Check exception.log
            if log_path.exists():
                try:
                    from src.utils.detect_encoding import detect_encoding
                    enc = detect_encoding(str(log_path))
                    log_content = log_path.read_text(encoding=enc, errors='replace')
                    logger.warning("Runtime exception: %s", log_content[:200])
                    return {"error": "runtime exception", "log": log_content}
                except Exception as read_err:
                    return {"error": "runtime exception", "read_error": str(read_err)}
            else:
                logger.info("Runtime verification passed")
                return {"passed": True}

        finally:
            # Restore original files
            _restore_lazarus_files(str(lpi_path), str(lpr_path), backs)

    except Exception as e:
        logger.warning("Runtime verification exception: %s", e, exc_info=True)
        return {"error": str(e)}


async def _handle_lazarus_project(arguments: dict) -> dict:
    """Get Lazarus project information

    Parse the .lpi file and return the project name, main source file, unit list, and compiler options.

    Arguments:
        project_path (str): .lpi or .lpr file path (required)
        action (str, optional): info / units / options, default info
    """
    from src.utils.lpi_parser import LpiParser

    project_path = arguments.get("project_path", "")
    if not project_path:
        return {"status": "failed", "error": "Missing required parameter: project_path"}

    # .lpr → find same-name .lpi
    from pathlib import Path
    p = Path(project_path)
    lpi_path = project_path
    if p.suffix.lower() == ".lpr":
        candidate = p.with_suffix(".lpi")
        if candidate.exists():
            lpi_path = str(candidate)
        else:
            return {
                "status": "failed",
                "error": f"No .lpi file found corresponding to {project_path}",
            }

    parser = LpiParser(lpi_path)
    if not parser.parse():
        return {
            "status": "failed",
            "error": f"Failed to parse .lpi file: {lpi_path}",
        }

    action = arguments.get("action", "info")

    if action == "units":
        return {
            "status": "success",
            "project_path": lpi_path,
            "units": parser.get_units(),
        }

    if action == "options":
        return {
            "status": "success",
            "project_path": lpi_path,
            "compiler_options": parser.get_compiler_options(),
        }

    # Default info
    info = parser.get_project_info()
    return {
        "status": "success",
        "project_path": lpi_path,
        "name": info.get("project_name", ""),
        "main_source": info.get("main_source", ""),
        "unit_count": info.get("unit_count", 0),
        "search_paths": parser.get_unit_search_paths(),
        "compiler_options": parser.get_compiler_options(),
    }


async def _handle_lazarus_kb(arguments: dict) -> dict:
    """Lazarus/FPC source knowledge base

    Index and search Lazarus LCL / FPC RTL source code. Uses an independent ZVec knowledge base
    stored in data/lazarus-knowledge-base/.

    Actions:
        build:   Scan the Lazarus installation directory and index source code
        search:  Search indexed source code (returns symbol definitions and usages)
        stats:   Knowledge base statistics
        read:    Read source file contents
    """
    from pathlib import Path

    action = arguments.get("action", "search")

    # Independent KB path
    server_root = Path(__file__).resolve().parents[3]
    kb_dir = str(server_root / "data" / "lazarus-knowledge-base")

    # ── Auto-detect Lazarus source directories ──
    def _detect_source_dirs() -> List[dict]:
        from .detect import find_lazarus_source_dirs
        return find_lazarus_source_dirs()

    # ── build ──
    if action == "build":
        from src.services.knowledge_base.scan_generic_documents import (
            GenericDocumentScanner,
        )

        sources = _detect_source_dirs()
        if not sources:
            return {
                "status": "failed",
                "error": "No Lazarus/FPC installation directory detected. Please confirm Lazarus is installed at C:\\lazarus",
            }

        Path(kb_dir).mkdir(parents=True, exist_ok=True)
        scanner = GenericDocumentScanner(kb_dir)

        results = []
        total_files = 0
        for src in sources:
            try:
                result = scanner.scan_directory(
                    directory=src["path"],
                    extensions=[".pas", ".inc", ".pp", ".lpr", ".lpi"],
                )
                total_files += result.get("total_files", 0)
                results.append({
                    "source": src["label"],
                    "path": src["path"],
                    "files": result.get("total_files", 0),
                    "processed": result.get("processed", 0),
                    "failed": result.get("failed", 0),
                })
            except Exception as e:
                logger.warning(f"Failed to scan {src['label']}: {e}")
                results.append({
                    "source": src["label"],
                    "path": src["path"],
                    "error": str(e),
                })

        stats = scanner.get_statistics()
        return {
            "status": "success",
            "action": "build",
            "sources": results,
            "total_files_scanned": total_files,
            "indexed_documents": stats.get("total_documents", 0),
            "kb_path": kb_dir,
        }

    # ── search ──
    if action == "search":
        query = arguments.get("query", "")
        if not query:
            return {"status": "failed", "error": "Missing required parameter: query"}

        top_k = min(int(arguments.get("top_k", 20)), 100)
        content_type = arguments.get("content_type")  # optional filter

        kb_path = Path(kb_dir)
        if not kb_path.is_dir() or not any(kb_path.iterdir()):
            return {
                "status": "failed",
                "error": "Lazarus knowledge base is empty. Please run lazarus_kb(action=build) first",
            }

        from src.services.knowledge_base.scan_generic_documents import (
            GenericDocumentScanner,
        )
        scanner = GenericDocumentScanner(kb_dir)
        results = scanner.search(query, content_type=content_type, top_k=top_k)

        if not results:
            return {
                "status": "success",
                "action": "search",
                "query": query,
                "count": 0,
                "results": [],
                "message": f"No documents matching '{query}' found",
            }

        output = []
        for doc in results:
            entry = {
                "id": doc.get("id"),
                "title": doc.get("title", "N/A"),
                "type": doc.get("content_type", "N/A"),
                "path": doc.get("path", doc.get("url", "")),
                "size": doc.get("size", 0),
            }
            content = doc.get("content", "")
            if content:
                entry["preview"] = content[:300]
            output.append(entry)

        return {
            "status": "success",
            "action": "search",
            "query": query,
            "count": len(output),
            "results": output,
        }

    # ── read ──
    if action == "read":
        file_path = arguments.get("file_path")
        if not file_path:
            return {"status": "failed", "error": "file_path parameter is required"}

        p = Path(file_path)
        if not p.exists():
            return {"status": "failed", "error": f"File does not exist: {file_path}"}
        try:
            # BOM auto-detection: prefer UTF-8 BOM, fallback UTF-8
            raw = p.read_bytes()
            if raw[:3] == b'\xef\xbb\xbf':
                text = raw[3:].decode('utf-8')
            elif raw[:2] in (b'\xff\xfe', b'\xfe\xff'):
                text = raw.decode('utf-16')
            else:
                text = raw.decode('utf-8')
            return {
                "status": "success",
                "action": "read",
                "file_path": file_path,
                "content": text,
                "size": len(text),
                "encoding": "utf-8",
            }
        except UnicodeDecodeError:
            # Fallback: system default encoding
            try:
                text = p.read_text(encoding="ansi")
                return {
                    "status": "success",
                    "action": "read",
                    "file_path": file_path,
                    "content": text,
                    "size": len(text),
                    "encoding": "ansi",
                }
            except Exception as e2:
                return {"status": "failed", "error": f"Unable to decode file (tried UTF-8/UTF-16/ANSI): {e2}"}
        except Exception as e:
            return {"status": "failed", "error": f"Failed to read file: {e}"}

    # ── stats ──
    if action == "stats":
        kb_path = Path(kb_dir)
        if not kb_path.is_dir():
            return {
                "status": "success",
                "action": "stats",
                "total_documents": 0,
                "sources_available": _detect_source_dirs(),
                "message": "Knowledge base has not been built yet. Please run lazarus_kb(action=build)",
            }

        from src.services.knowledge_base.scan_generic_documents import (
            GenericDocumentScanner,
        )
        scanner = GenericDocumentScanner(kb_dir)
        stats = scanner.get_statistics()

        return {
            "status": "success",
            "action": "stats",
            "kb_path": kb_dir,
            "total_documents": stats.get("total_documents", 0),
            "by_type": stats.get("by_type", {}),
            "by_language": stats.get("by_language", {}),
            "sources_available": _detect_source_dirs(),
        }

    return {"status": "failed", "error": f"Unknown action: {action}"}


async def _handle_lazarus_file(arguments: dict) -> dict:
    """Lazarus/FPC file read/write tool (read/write/backup only, reuses the shared file core)

    Actions:
        read:    Read file (BOM auto-detection)
        write:   Write file (edits=[...] batch modifications, automatically backed up to __history)
        backup:  Manually create a backup in __history

    Limits the action scope and disallows delphi_file-specific operations such as DFM/pasfmt/uses/grep.
    """
    from src.tools.file_tool import handle_file_tool

    allowed = {"read", "write", "backup"}
    action = arguments.get("action", "read")
    if action not in allowed:
        return {
            "status": "failed",
            "error": f"lazarus_file does not support action='{action}'. Supported: {', '.join(sorted(allowed))}",
        }

    return await handle_file_tool(arguments)


# ============================================================
# Exports: tool name → handler mapping
# ============================================================

LAZARUS_HANDLERS: dict[str, Any] = {
    "lazarus_compile": _handle_lazarus_compile,
    "lazarus_project": _handle_lazarus_project,
    "lazarus_kb": _handle_lazarus_kb,
    "lazarus_file": _handle_lazarus_file,
}

LAZARUS_TOOL_DESCRIPTIONS: dict[str, str] = {
    "lazarus_compile": "Lazarus/Free Pascal project compilation (lazbuild)",
    "lazarus_project": "Lazarus project information query — parse .lpi file and get project name/main source file/unit list/compiler options",
    "lazarus_kb": "Lazarus/FPC source knowledge base — index and search LCL/FPC RTL source code. build(build)/search(search)/stats(statistics)/read(read source)",
    "lazarus_file": "Lazarus/FPC file read/write — read(read)/write(edits batch modifications, automatic backup)/backup(manual backup)",
}

LAZARUS_TOOL_SCHEMAS: dict[str, dict] = {
    "lazarus_compile": {
        "type": "object",
        "properties": {
            "project_path": {
                "type": "string",
                "description": ".lpi or .lpr file absolute path",
            },
            "target_platform": {
                "type": "string",
                "enum": ["win32", "win64"],
                "default": "win32",
            },
            "build_configuration": {
                "type": "string",
                "description": "Default / Release / Debug",
            },
            "timeout": {
                "type": "integer",
                "default": 600,
            },
            "run_verify": {
                "type": "boolean",
                "default": False,
                "description": "After a successful build, launch the program for 3 seconds to verify it does not crash",
            },
        },
        "required": ["project_path"],
    },
    "lazarus_project": {
        "type": "object",
        "properties": {
            "project_path": {
                "type": "string",
                "description": ".lpi or .lpr file absolute path",
            },
            "action": {
                "type": "string",
                "enum": ["info", "units", "options"],
                "default": "info",
                "description": "info=project summary, units=unit list, options=compiler options",
            },
        },
        "required": ["project_path"],
    },
    "lazarus_kb": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["build", "search", "stats", "read"],
                "default": "search",
                "description": "build=build knowledge base, search=search, stats=statistics, read=read source code",
            },
            "query": {
                "type": "string",
                "description": "Search keyword (required when action=search)",
            },
            "top_k": {
                "type": "integer",
                "default": 20,
                "description": "Maximum number of returned results (default 20, max 100)",
            },
            "file_path": {
                "type": "string",
                "description": "Source file absolute path (required when action=read)",
            },
            "content_type": {
                "type": "string",
                "description": "Filter by file type (e.g. pas/inc/pp)",
            },
        },
    },
    "lazarus_file": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["read", "write", "backup"],
                "default": "read",
                "description": "read=read, write=write(edits), backup=backup",
            },
            "file_path": {
                "type": "string",
                "description": "File absolute path",
            },
            "edits": {
                "type": "array",
                "description": "Batch edit operations (required when write)",
                "items": {
                    "type": "object",
                    "properties": {
                        "start_line": {"type": "integer", "description": "Start line number (1-indexed inclusive)"},
                        "end_line": {"type": "integer", "description": "End line number (1-indexed inclusive)"},
                        "content": {"type": "string", "description": "New content"},
                    },
                    "required": ["start_line"],
                },
            },
            "encoding": {
                "type": "string",
                "description": "File encoding (auto-detect BOM if omitted)",
            },
        },
        "required": ["action"],
    },
}

