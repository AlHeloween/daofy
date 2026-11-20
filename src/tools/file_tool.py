"""
delphi_file — Delphi file-specific operation tool (MCP registration name delphi_file, formerly file_tool)

Integrates read/write/format/backup management, covering the complete lifecycle of Delphi file operations.
MCP clients register it as delphi_file; the old name file_tool remains compatible as an alias.

Action modes:
  read        Read file content (inherits read_source_file; supports searching by path/class name/function name)
  write       Compatible write entry (auto-backup to __history, supports transparent DFM conversion)
  replace     Replace by line range (existing files require old_content validation)
  insert      Insert at anchor (existing files require old_content validation, supports before/after)
  delete      Delete by line range (existing files require old_content validation)
  format      Format Delphi source code (inherits format_delphi, driven by pasfmt)
  backup      Backup management (create/restore/list/compare)
  encode      File encoding conversion (auto-detect source encoding, supports BOM handling, auto-backup)
  uses        Add/remove units in uses clause (namespace conflict detection + auto-sort)
  fix_garbled Fix Chinese garbled text (auto-detect U+FFFD, missing BOM, encoding misdetection, etc. and repair)
  count_lines Count code lines (supports excluding blank lines and comment lines)

Return values are uniformly dict, following project conventions:
  success: {"status": "success", "message": "...", ...}
  error:   {"status": "failed", "message": "..."}
"""

import codecs
import asyncio
import fnmatch
import glob
import locale
import os
import re
import shutil
import tempfile
import threading
import uuid
from typing import Any, Optional, Dict, List, Set
from mcp.types import CallToolResult
from ..constants import BUFFER_SIZE_1MB
from ..utils.logger import get_logger
from ..utils.file_backup import create_backup, list_backups, restore_backup, detect_encoding
from ..services.delphi_edit_guard import record_authorized_write
from . import pasfmt
from .read_source_file import read_source_file as _read_file, search_and_read_file as _search_read_file
from . import dfm_utils

logger = get_logger(__name__)

_DELPHI_EXTENSIONS = {'.pas', '.dpr', '.dpk', '.dfm', '.fmx', '.inc', '.dproj', '.groupproj'}

# A recursive grep must not be allowed to materialize an entire workspace in
# one request.  The limit is deliberately high enough for a source tree, but
# turns accidental patterns such as **/*.* into a fast, actionable error.
MAX_GREP_TARGETS = 5000

_SYSTEM_SENSITIVE_DIRS: List[str] = []

# ── AI Agent workspace root cache ──────────────────────────────
# Set by server.py after MCP initialization via session.list_roots();
# delphi_file actions fall back to this path when project_path is not provided.
_workspace_root: Optional[str] = None
_workspace_root_lock = threading.Lock()


def set_workspace_root(root: Optional[str]) -> None:
    """Set the AI Agent workspace root (called by server.py during initialization)."""
    global _workspace_root
    with _workspace_root_lock:
        _workspace_root = root
        if root:
            logger.info("Workspace root set: %s", root)
        else:
            logger.info("Workspace root cleared")


def get_workspace_root() -> Optional[str]:
    """Get the cached workspace root; return None if not set."""
    with _workspace_root_lock:
        return _workspace_root
if os.name == 'nt':
    _windir = os.environ.get('WINDIR', r'C:\Windows')
    _SYSTEM_SENSITIVE_DIRS = [
        os.path.join(_windir, 'System32', 'config'),
        os.path.join(_windir, 'System32', 'drivers', 'etc'),
    ]
else:
    _SYSTEM_SENSITIVE_DIRS = ['/etc/shadow', '/etc/ssh']


def _resolve_project_path(arguments: Dict[str, Any]) -> Optional[str]:
    """Return project_path, falling back to the AI Agent workspace root when not provided.

    Priority:
      1. project_path explicitly passed in arguments
      2. Workspace root cached by get_workspace_root()
    """
    explicit = arguments.get("project_path")
    if explicit:
        return explicit
    fallback = get_workspace_root()
    if fallback:
        logger.debug("project_path not provided, falling back to workspace root: %s", fallback)
    return fallback


def _resolve_relative_path(file_path: str, project_path: Optional[str] = None) -> str:
    """Resolve a relative path, preferably based on project_path or _workspace_root.

    When file_path is relative, try to resolve it in the following priority order:
      1. Resolve based on project_path (explicitly passed project root)
      2. Resolve based on _workspace_root (AI Agent workspace root)
      3. Resolve based on current working directory (preserve original behavior)

    When file_path is already absolute or the resolved file does not exist, return the original path.

    Args:
        file_path: File path (may be relative or absolute)
        project_path: Project root directory (optional)

    Returns:
        Resolved path (prefer the path where the file exists)
    """
    # Return absolute paths directly
    if os.path.isabs(file_path):
        return file_path

    # Relative path: try resolution in priority order
    candidates = []
    if project_path:
        candidates.append(os.path.join(project_path, file_path))
    workspace = get_workspace_root()
    if workspace:
        candidates.append(os.path.join(workspace, file_path))

    for candidate in candidates:
        if os.path.isfile(candidate):
            logger.debug("Relative path resolved: %s -> %s", file_path, candidate)
            return candidate

    # Not found: return original path (caller decides subsequent behavior)
    return file_path


def _coerce_positive_int(value: Any, default: int, name: str) -> tuple[Optional[int], Optional[str]]:
    """Return a 1-indexed positive integer value, or an error message."""
    if value is None:
        value = default
    if not isinstance(value, int):
        return None, f"{name} must be an integer"
    if value < 1:
        return None, f"{name} cannot be less than 1 (actual value: {value})"
    return value, None


def _validate_path(file_path: str, project_path: Optional[str] = None) -> Optional[str]:
    """Validate file path safety. Return None if safe, otherwise return an error message.

    Args:
        file_path: File path to validate
        project_path: Project path (optional; when provided, restricts file_path to within the project directory).
                       When not provided, falls back to get_workspace_root().
    """
    # Null byte injection check
    if '\0' in file_path:
        return "Path contains null byte"
    try:
        resolved = os.path.abspath(os.path.realpath(file_path))
    except (OSError, ValueError) as e:
        return "Path resolution failed: %s" % str(e)

    # Protect system-sensitive directories
    for sensitive_dir in _SYSTEM_SENSITIVE_DIRS:
        try:
            resolved_relative = os.path.relpath(resolved, sensitive_dir)
            if not resolved_relative.startswith('..'):
                return "Path is inside a system-sensitive directory: %s" % sensitive_dir
        except ValueError:
            pass

    # Project directory check: allow the project directory and its subdirectories, and also allow output directories configured by the project
    # (DCC_ExeOutput / DCC_DcuOutput), even if the output directory is outside the project directory
    effective_project = project_path or get_workspace_root()
    if effective_project:
        try:
            proj_resolved = os.path.abspath(os.path.realpath(effective_project))
            # project_path may be a .dproj file; use its directory as the project root
            proj_dir = proj_resolved if os.path.isdir(proj_resolved) else os.path.dirname(proj_resolved)

            # 1. Inside the project directory -> safe
            rel = os.path.relpath(resolved, proj_dir)
            if not rel.startswith('..'):
                return None

            # 2. Inside an output directory configured by the project -> safe
            #    Parse output paths such as DCC_ExeOutput / DCC_DcuOutput from the project .dproj
            allowed_dirs = _get_project_output_dirs(proj_resolved)
            for allowed in allowed_dirs:
                try:
                    allowed_resolved = os.path.abspath(os.path.realpath(allowed))
                    rel_allowed = os.path.relpath(resolved, allowed_resolved)
                    if not rel_allowed.startswith('..'):
                        return None  # Inside project output directory; safe
                except (OSError, ValueError):
                    continue

            return "Path is not inside the project directory: %s (project: %s)" % (file_path, effective_project)
        except (OSError, ValueError):
            # Do not block when project_path resolution fails; let caller handle it
            pass

    return None


def _get_project_output_dirs(project_path: str) -> List[str]:
    """
    Parse the output directories configured by the project file (.dproj/.dpr) (DCC_ExeOutput / DCC_DcuOutput).

    Output directories may be outside the project directory; _validate_path must allow these paths
    to support the scenario "read/write is also possible when the output directory is not in the project directory".

    Args:
        project_path: Project root directory or .dproj/.dpr file path

    Returns:
        List of absolute output directory paths (may be empty)
    """
    result: List[str] = []
    if not project_path:
        return result

    proj_path = project_path
    if os.path.isdir(project_path):
        # Project root directory: find .dproj file
        for ext in ('.dproj', '.dpr', '.dpk'):
            candidates = list(glob.glob(os.path.join(project_path, '*' + ext)))
            if candidates:
                proj_path = candidates[0]
                break
        else:
            return result

    dproj_file = proj_path
    # If .dpr/.dpk, prefer the same-named .dproj (which contains DCC_ExeOutput)
    base, ext = os.path.splitext(proj_path)
    if ext.lower() in ('.dpr', '.dpk'):
        dproj_candidate = base + '.dproj'
        if os.path.isfile(dproj_candidate):
            dproj_file = dproj_candidate

    if not os.path.isfile(dproj_file) or not dproj_file.lower().endswith('.dproj'):
        return result

    try:
        from ..utils.dproj_parser import DprojParser
        parser = DprojParser(dproj_file)
        if not parser.parse():
            return result
        # Iterate over ExeOutput / DcuOutput for all configuration combinations
        for output_tag in ('get_output_path', 'get_dcu_output_path'):
            for config in (None, 'Debug', 'Release', 'Dev'):
                for platform in (None, 'Win32', 'Win64'):
                    try:
                        out = getattr(parser, output_tag)(config, platform)
                        if out:
                            abs_out = os.path.abspath(os.path.realpath(out))
                            if abs_out not in result:
                                result.append(abs_out)
                    except Exception:
                        continue
    except Exception:
        logger.debug("Failed to parse project output directories: %s", proj_path, exc_info=True)

    return result


def _is_delphi_file(file_path: str) -> bool:
    """Determine whether this is a Delphi source file"""
    ext = os.path.splitext(file_path)[1].lower()
    return ext in _DELPHI_EXTENSIONS


def _is_dfm_file(file_path: str) -> bool:
    """Determine whether this is a DFM/FMX form file (Delphi VCL/FireMonkey form, may be binary or text format)"""
    ext = os.path.splitext(file_path)[1].lower()
    return ext in {'.dfm', '.fmx'}


def _wrap_error(msg: str) -> Dict[str, Any]:
    """Build error dict"""
    return {"status": "failed", "message": msg}


def _is_pascal_word_char(ch: str) -> bool:
    """Return True for identifier/number token characters."""
    return ch == "_" or ch.isalnum()


def _next_non_space(text: str, start: int) -> str:
    """Return the next non-whitespace character after start, or empty string."""
    for idx in range(start, len(text)):
        if not text[idx].isspace():
            return text[idx]
    return ""


def _append_word_boundary_if_needed(result: List[str], next_ch: str) -> None:
    """Preserve token boundaries while ignoring formatting whitespace."""
    if result and next_ch and _is_pascal_word_char(result[-1]) and _is_pascal_word_char(next_ch):
        result.append(" ")


def _normalize_code_for_compare(text: str) -> str:
    """Ignore whitespace outside Pascal string literals for old_content checks.

    Rules:
      - Code area: remove whitespace tokens, adding a single space only when needed to prevent token concatenation
      - Comment area: collapse consecutive whitespace to a single space, do not remove all
      - String area: preserve as-is
    """
    result: List[str] = []
    i = 0
    state = "code"
    # Within comment area, track whether previous char was whitespace (for collapsing)
    prev_was_space = False

    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""

        if state == "string":
            result.append(ch)
            if ch == "'":
                if nxt == "'":
                    result.append(nxt)
                    i += 1
                else:
                    state = "code"
        elif state in ("line_comment", "brace_comment", "paren_comment"):
            # ── Inside comment: collapse whitespace to single space ──
            if state == "line_comment" and ch in "\r\n":
                state = "code"
                prev_was_space = False
                # Line comments end at newline; keep that boundary meaningful.
                if not result or result[-1] != "\n":
                    result.append("\n")
            elif state == "brace_comment" and ch == "}":
                result.append(ch)
                state = "code"
                prev_was_space = False
            elif state == "paren_comment" and ch == "*" and nxt == ")":
                result.append(ch)
                result.append(nxt)
                i += 1
                state = "code"
                prev_was_space = False
            elif ch.isspace():
                if not prev_was_space:
                    result.append(" ")
                    prev_was_space = True
            else:
                result.append(ch)
                prev_was_space = False
        else:
            # ── Code area: original logic unchanged ──
            if ch == "'":
                state = "string"
                result.append(ch)
            elif ch == "/" and nxt == "/":
                result.append(ch)
                result.append(nxt)
                i += 1
                state = "line_comment"
                prev_was_space = False
            elif ch == "{":
                result.append(ch)
                state = "brace_comment"
                prev_was_space = False
            elif ch == "(" and nxt == "*":
                result.append(ch)
                result.append(nxt)
                i += 1
                state = "paren_comment"
                prev_was_space = False
            elif not ch.isspace():
                result.append(ch)
            else:
                _append_word_boundary_if_needed(result, _next_non_space(text, i + 1))
        i += 1
    return ''.join(result)


def _get_old_content(edit: Dict[str, Any]) -> Optional[str]:
    """Read the old_content guard from an edit.

    Automatically strip trailing \\r\\n to avoid validation failure when AI copies from read output with line-ending newlines.
    """
    value = edit.get("old_content")
    if isinstance(value, str):
        value = value.rstrip('\r\n')
    return value


def _all_edits_have_old_content(edits: Any) -> bool:
    """Return True when every edit can be guarded by old_content."""
    if not isinstance(edits, (list, tuple)) or not edits:
        return False
    return all(
        isinstance(edit, dict) and _edit_has_non_empty_old_content(edit)
        for edit in edits
    )


def _edit_has_non_empty_old_content(edit: Dict[str, Any]) -> bool:
    """Return True when an edit contains a usable old_content guard."""
    old_content = _get_old_content(edit)
    return old_content is not None and bool(_normalize_code_for_compare(old_content))


def _prepare_insert_content(content: str, has_crlf: bool) -> str:
    """Normalize inserted text and make it occupy complete lines."""
    if has_crlf:
        content = content.replace('\r\n', '\n').replace('\n', '\r\n')
        newline = '\r\n'
    else:
        content = content.replace('\r\n', '\n')
        newline = '\n'
    if content and not content.endswith(('\n', '\r\n')):
        content += newline
    return content


async def _read_structured_anchor_lines(file_path: str) -> tuple[List[str], Optional[str]]:
    """Read text lines for insert anchors, converting binary DFM/FMX first."""
    read_path = file_path
    tmp_cleanup = None
    try:
        if _is_dfm_file(file_path):
            try:
                fmt = dfm_utils._detect_dfm_format(file_path)
            except (FileNotFoundError, PermissionError) as e:
                raise RuntimeError(str(e)) from e
            if fmt == "binary":
                tmp_cleanup = tempfile.mkdtemp(prefix="filetool_anchor_")
                read_path = os.path.join(tmp_cleanup, os.path.basename(file_path) + ".txt")
                conv_result = await dfm_utils.convert_dfm(file_path, read_path, to_text=True)
                if not conv_result.get("success"):
                    raise RuntimeError(
                        f"Binary DFM conversion failed: {conv_result.get('message', 'unknown error')}"
                    )

        read_enc = detect_encoding(read_path)
        with open(read_path, 'r', encoding=read_enc, newline='',
                  buffering=BUFFER_SIZE_1MB) as f:
            return f.readlines(), tmp_cleanup
    except Exception as exc:
        if tmp_cleanup:
            shutil.rmtree(tmp_cleanup, ignore_errors=True)
        raise RuntimeError(str(exc)) from exc


def _format_line_snippet(lines: List[str], start_idx: int, end_idx: int, context: int = 2) -> List[str]:
    """Return compact 1-indexed snippet lines around a conflict range."""
    if not lines:
        return ["    <empty file>"]
    lo = max(0, start_idx - context)
    hi = min(len(lines), max(end_idx, start_idx + 1) + context)
    snippet = []
    for idx in range(lo, hi):
        text = lines[idx].rstrip("\r\n")
        if len(text) > 120:
            text = text[:117] + "..."
        snippet.append(f"    L{idx + 1}: {text}")
    return snippet


def _get_history_dir(file_path: str) -> str:
    """Return the __history directory used for backups and temporary writes."""
    return os.path.join(os.path.dirname(os.path.abspath(file_path)), "__history")


def _make_temp_write_path(file_path: str) -> str:
    """Create a unique temporary path on the same volume as the target file."""
    target_dir = os.path.dirname(os.path.abspath(file_path))
    basename = os.path.basename(file_path)
    return os.path.join(target_dir, f".__daofy_tmp_{basename}_{uuid.uuid4().hex}")


def _write_text_temp(temp_path: str, content: str, encoding: str) -> None:
    """Write text to a temp file and flush it before replacement."""
    with open(temp_path, 'w', encoding=encoding, newline='', buffering=BUFFER_SIZE_1MB) as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())


def _replace_with_temp(temp_path: str, file_path: str) -> None:
    """Atomically replace file_path with temp_path."""
    os.replace(temp_path, file_path)


async def _apply_auto_format_atomically(
    file_path: str,
    encoding: str,
    has_crlf: bool,
    backup: bool = False,
    config_path: Optional[str] = None,
    uses_style: Optional[str] = None,
) -> tuple[bool, str, bool, Optional[str]]:
    """Run pasfmt in stdout mode and atomically replace the formatted file."""
    fmt_result = await pasfmt.format_file(
        file_path=file_path,
        backup=False,
        in_place=False,
        config_path=config_path,
        uses_style=uses_style,
    )
    if fmt_result.get("status") == "failed":
        raise RuntimeError(fmt_result.get("message", "pasfmt formatting failed"))
    if not fmt_result.get("formatted") or not isinstance(fmt_result.get("content"), str):
        return False, encoding, False, None

    formatted_text = fmt_result["content"]
    if has_crlf:
        formatted_text = formatted_text.replace('\r\n', '\n').replace('\n', '\r\n')
    else:
        formatted_text = formatted_text.replace('\r\n', '\n')
    if formatted_text and not formatted_text.endswith(('\n', '\r\n')):
        formatted_text += '\r\n' if has_crlf else '\n'

    temp_write_path = _make_temp_write_path(file_path)
    encoding_fallback = False
    backup_path = None
    try:
        try:
            _write_text_temp(temp_write_path, formatted_text, encoding)
        except UnicodeEncodeError:
            logger.warning(f"Writing formatted result with encoding {encoding} failed, falling back to utf-8")
            _write_text_temp(temp_write_path, formatted_text, "utf-8")
            encoding = "utf-8"
            encoding_fallback = True
        if backup:
            backup_path = create_backup(file_path)
            if not backup_path:
                raise RuntimeError("Failed to create backup; formatting canceled")
        record_authorized_write(
            file_path,
            tool="delphi_file",
            operation="format",
        )
        _replace_with_temp(temp_write_path, file_path)
    finally:
        if os.path.exists(temp_write_path):
            try:
                os.remove(temp_write_path)
            except OSError:
                pass

    return True, encoding, encoding_fallback, backup_path


def _warn_if_old_content_too_short(old_content: str) -> Optional[str]:
    """Return a non-blocking warning for weak old_content guards."""
    normalized = _normalize_code_for_compare(old_content)
    line_count = len([line for line in old_content.splitlines() if line.strip()])
    common_tokens = {
        "begin",
        "end",
        "end;",
        "inherited",
        "inherited;",
        "try",
        "finally",
        "except",
    }
    if len(normalized) < 12 or (line_count <= 1 and normalized.lower() in common_tokens):
        return "old_content is very short; if line numbers shift to the same short snippet it may still match incorrectly; including more context lines is recommended"
    return None


def _normalize_encoding_name(enc: str) -> str:
    """
    Normalize encoding name: remove BOM suffix, -/_ variants, and lowercase.

    utf-8-sig is treated as utf-8 at normalization level (BOM is automatically stripped/added when opening),
    for encoding compatibility comparison.
    """
    if not enc:
        return ""
    e = enc.lower().replace("_", "-")
    if e == "utf-8-sig":
        e = "utf-8"
    return e


def _is_encoding_compatible(user_enc: str, detected_enc: str) -> bool:
    """
    Check whether the user-specified encoding is compatible with the file's actual encoding.

    Compatibility rules:
      - Exactly equal (after normalization)
      - utf-8 <-> utf-8-sig compatible with each other
      - utf-16 family (utf-16/utf-16-le/utf-16-be) only compatible within the same subfamily

    Args:
        user_enc: encoding parameter explicitly specified by user
        detected_enc: actual result detected by detect_encoding

    Returns:
        True means compatible and can continue; False means encoding mismatch and must reject
    """
    u = _normalize_encoding_name(user_enc)
    d = _normalize_encoding_name(detected_enc)

    if u == d:
        return True

    # Mutually compatible within utf-8 family (utf-8 / utf-8-sig)
    utf8_family = {"utf-8", "utf-8-sig"}
    if u in utf8_family and d in utf8_family:
        return True

    # Mutually compatible within utf-16 family (only when both sides are utf-16 series)
    utf16_family = {"utf-16", "utf-16-le", "utf-16-be"}
    if u in utf16_family and d in utf16_family:
        return True

    return False


async def _read_content(
    file_path: str,
    start_line: int = 1,
    limit: int = 500,
    search_in: str = "all",
    project_path: Optional[str] = None,
    end_line: Optional[int] = None,
    show_line_numbers: bool = False,
    encoding: str = "auto",
) -> Dict[str, Any]:
    """
    Internal implementation for reading file content.

    If the file exists locally, detect encoding and read directly (supports UTF-8/GBK/UTF-16, etc.).
    Otherwise delegate to read_source_file to go through the knowledge base search path.

    start_line/end_line are 1-indexed inclusive intervals:
      - start_line=1 means start from line 1 of the file
      - when end_line is not passed, it is equivalent to "read until start_line + limit - 1"

    show_line_numbers: when True, add a line-number prefix to each line (e.g. "     1: unit Unit1;"),
                       line numbers are 1-indexed absolute line numbers.
    """
    # Resolve relative path: based on project_path or _workspace_root
    file_path = _resolve_relative_path(file_path, project_path)

    # Direct file read (supports encoding detection + fallback chain)
    if os.path.isfile(file_path):
        effective_start = max(1, start_line)
        target_end = end_line if end_line is not None else (effective_start + limit - 1)

        # Build encoding fallback chain
        detected = detect_encoding(file_path)

        if encoding != "auto":
            # User explicitly specified encoding -> use as first choice, auto-detected result as fallback
            fallback_encodings = [encoding]
            if encoding.lower() != detected.lower():
                fallback_encodings.append(detected)
        else:
            fallback_encodings = [detected]

        # UTF-8 without BOM (add if different from detected encoding)
        if 'utf-8' not in (e.lower() for e in fallback_encodings) and 'utf-8-sig' not in (e.lower() for e in fallback_encodings):
            fallback_encodings.append('utf-8')

        # CP_ACP — system ANSI code page
        try:
            ansi = locale.getpreferredencoding()
            if ansi.lower() not in (e.lower() for e in fallback_encodings):
                fallback_encodings.append(ansi)
        except Exception:
            logger.debug("Failed to get system default encoding; skipping ANSI fallback")

        # CJK encoding fallback (try common CJK encodings regardless of system locale)
        cjk_fallbacks = ['gbk', 'gb18030', 'big5', 'shift_jis', 'euc-kr', 'euc-jp']
        for cjk_enc in cjk_fallbacks:
            if cjk_enc not in (e.lower() for e in fallback_encodings):
                fallback_encodings.append(cjk_enc)

        last_error = None
        for enc in fallback_encodings:
            try:
                if target_end < effective_start:
                    return {
                        "status": "success",
                        "message": (
                            f"# encoding: {enc}, 1-indexed empty, "
                            f"requested [{effective_start}, {target_end}]\n"
                        ),
                        "range": [effective_start, target_end],
                    }

                # Streaming read: read only the needed lines, avoiding loading entire large files into memory
                # For scenarios reading the first N lines or a specified line range, linear scanning saves more memory than readlines()
                # target_start/target_end are internal 1-indexed inclusive representations
                target_start = effective_start
                selected = []
                reached_eof = True  # Track whether EOF was reached
                line_no = 0  # For empty files the for loop body does not execute; initialize
                with open(file_path, 'r', encoding=enc, newline='',
                          buffering=BUFFER_SIZE_1MB) as f:
                    for line_no, line in enumerate(f, 1):
                        if line_no > target_end:
                            reached_eof = False
                            break
                        if line_no >= target_start:
                            selected.append(line)

                if reached_eof:
                    total_lines = line_no  # Loop ended normally; line_no is the actual total line count
                else:
                    total_lines = None  # Truncated by target_end; actual total line count unknown

                raw_selected_text = ''.join(selected)
                text = raw_selected_text

                # show_line_numbers: add 1-indexed absolute line-number prefix to each line
                if show_line_numbers and selected:
                    line_offset = target_start  # 1-indexed start
                    numbered_lines = []
                    for i, line in enumerate(selected):
                        lineno = line_offset + i  # 1-indexed absolute line number
                        numbered_lines.append(f"{lineno:>6}: {line}")
                    text = ''.join(numbered_lines)

                if not text.endswith('\n'):
                    text += '\n'

                lines_shown = len(selected)
                actual_end_line = target_start + lines_shown - 1  # 1-indexed inclusive end

                # Single-line meta: encoding + 1-indexed line number range
                # All line numbers are 1-indexed and can be used directly in write's start_line/edits.
                # When truncated, append only the (truncated) marker.
                if lines_shown == 0:
                    total_hint = f", total_lines: {total_lines}" if total_lines is not None else ""
                    meta = (
                        f"# encoding: {enc}, 1-indexed empty, "
                        f"requested [{target_start}, {target_end}]{total_hint}"
                    )
                else:
                    meta = f"# encoding: {enc}, 1-indexed [{target_start}, {actual_end_line}]"
                if not reached_eof:
                    meta += " (truncated)"
                meta += "\n"

                return {
                    "status": "success",
                    "message": meta + text,
                    "range": [target_start, actual_end_line] if lines_shown else [target_start, target_end],
                    "encoding": enc,
                }
            except UnicodeDecodeError:
                last_error = f"Encoding {enc} decode failed"
                continue
            except Exception as e:
                last_error = str(e)
                continue

        # All encoding attempts failed; return error (do not fall back to KB — file is local, KB would read empty)
        logger.warning(f"Failed to read file {file_path}; attempts with encodings {fallback_encodings} all failed: {last_error}")
        return _wrap_error(f"Unable to read file (encoding detection failed): {last_error}")

    # File not local (may be a knowledge-base path) — delegate to read_source_file
    args = {
        "file_path": file_path,
        "start_line": start_line,
        "max_lines": limit,  # read_source_file internally still uses max_lines
        "search_in": search_in,
        "project_path": project_path,
    }
    if end_line is not None:
        args["end_line"] = end_line
    result = await _read_file(args)
    if result.isError:
        return {"status": "failed", "message": result.content[0].text if result.content else "read failed"}
    return {"status": "success", "message": result.content[0].text if result.content else ""}


async def _search_and_read(
    search_type: str,
    file_path: Optional[str] = None,
    type_name: Optional[str] = None,
    record_name: Optional[str] = None,
    function_name: Optional[str] = None,
    search_in: str = "all",
    start_line: int = 1,
    limit: int = 100,
    project_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Search by class name/function name and read file"""
    args = {
        "file_path": file_path,
        "type_name": type_name,
        "record_name": record_name,
        "function_name": function_name,
        "search_in": search_in,
        "start_line": start_line,
        "max_lines": limit,  # read_source_file internally still uses max_lines
        "project_path": project_path,
    }
    result = await _search_read_file(args)
    if result.isError:
        return {"status": "failed", "message": result.content[0].text if result.content else "search failed"}
    return {"status": "success", "message": result.content[0].text if result.content else ""}


async def handle_read(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle read action.

    Supports two modes:
      1. Read by path: file_path parameter
      2. Read by search: search_type + type_name/function_name

    Transparent DFM handling: binary DFM is automatically converted to text before reading.
    """
    file_path = arguments.get("file_path")
    search_type = arguments.get("search_type", "path")
    start_line, start_err = _coerce_positive_int(arguments.get("start_line"), 1, "start_line")
    if start_err:
        return _wrap_error(start_err)
    end_line = arguments.get("end_line")
    if end_line is not None and not isinstance(end_line, int):
        return _wrap_error("end_line must be an integer")
    if end_line is not None:
        limit = min(end_line - start_line + 1, 1000)
    else:
        limit_value = arguments.get("limit", 500)
        if not isinstance(limit_value, int):
            return _wrap_error("limit must be an integer")
        limit = min(max(1, limit_value), 1000)
    search_in = arguments.get("search_in", "all")
    project_path = arguments.get("project_path")
    show_line_numbers = arguments.get("show_line_numbers", False)
    encoding = arguments.get("encoding", "auto")

    # --- Search mode ---
    if search_type != "path":
        return await _search_and_read(
            search_type=search_type,
            file_path=file_path,
            type_name=arguments.get("type_name") or arguments.get("class_name"),
            record_name=arguments.get("record_name"),
            function_name=arguments.get("function_name"),
            search_in=search_in,
            start_line=start_line,
            limit=limit,
            project_path=project_path,
        )

    # --- Path mode ---
    if not file_path:
        return _wrap_error("Please provide file_path parameter")

    path_err = _validate_path(file_path, project_path)
    if path_err:
        return _wrap_error("Path safety validation failed: %s" % path_err)

    # Acquire read permission (multi-reader single-writer: multiple reads can run concurrently, no reads during writes)
    # Must be acquired before DFM detection/conversion to prevent interference from concurrent writes
    read_lock_err = _acquire_read_lock(file_path)
    if read_lock_err:
        return _wrap_error(read_lock_err)

    tmp_cleanup = None
    lock_file_path = file_path  # Save original path for lock release (DFM conversion will overwrite file_path)
    try:
        if _is_dfm_file(file_path):
            try:
                fmt = dfm_utils._detect_dfm_format(file_path)
            except FileNotFoundError:
                return _wrap_error(f"DFM file does not exist: {file_path}")
            except PermissionError:
                return _wrap_error(f"No permission to read DFM file: {file_path}")
            if fmt == "binary":
                tmp_dir = tempfile.mkdtemp(prefix="filetool_")
                tmp_text = os.path.join(tmp_dir, os.path.basename(file_path) + ".txt")
                result = await dfm_utils.convert_dfm(file_path, tmp_text, to_text=True)
                if result.get("success"):
                    file_path = tmp_text
                    tmp_cleanup = tmp_dir
                else:
                    # Return a clear error on conversion failure; do not attempt to read the binary file
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                    return _wrap_error(
                        f"Binary DFM conversion failed: {result.get('message', 'unknown error')}. "
                        "Please check whether the Delphi compiler (dcc32) is available"
                    )

        result = await _read_content(
            file_path=file_path,
            start_line=start_line,
            limit=limit,
            search_in=search_in,
            project_path=project_path,
            end_line=end_line,
            show_line_numbers=show_line_numbers,
            encoding=encoding,
        )
        if result.get("status") == "success":
            _clear_dirty(lock_file_path)
            # DFM: restore #XXXX escape sequences to visible characters (inverse operation of escape_dfm_chinese during write)
            if _is_dfm_file(lock_file_path) and "message" in result:
                result["message"] = dfm_utils.unescape_dfm_chinese(result["message"])
        return result
    finally:
        _release_read_lock(lock_file_path)
        if tmp_cleanup:
            shutil.rmtree(tmp_cleanup, ignore_errors=True)



# ── File-level write lock: prevent parallel writes to the same file ──────────────────────────────
# Multiple agents writing the same file concurrently will cause content corruption.
# Use an in-process dict for simple mutual exclusion: reject the second concurrent write directly, letting the agent merge and retry.
# Multi-reader single-writer (RWLock) — one lock entry per file path
# Structure: { normalized_path: {"lock": threading.Lock(), "readers": int, "writer": bool} }
_file_rw_locks: Dict[str, Dict] = {}
_file_rw_dict_lock = threading.Lock()  # Protects the _file_rw_locks dictionary itself from concurrent access


def _get_rw_entry(file_path: str) -> Dict:
    """Get or create the RWLock entry for a path (thread-safe)"""
    normalized = os.path.abspath(file_path)
    with _file_rw_dict_lock:
        entry = _file_rw_locks.get(normalized)
        if entry is None:
            entry = {
                "lock": threading.Lock(),
                "readers": 0,
                "writer": False,
            }
            _file_rw_locks[normalized] = entry
        return entry


def _acquire_read_lock(file_path: str) -> Optional[str]:
    """
    Acquire read permission for a file.
    Multiple reads can run concurrently, but reading is not allowed while a write is in progress.
    
    Returns:
        None means success and reading is allowed
        str  means conflict, returns error message
    """
    normalized = os.path.abspath(file_path)
    entry = _get_rw_entry(file_path)
    with entry["lock"]:
        if entry["writer"]:
            return (
                f"File {os.path.basename(normalized)} is occupied by a write operation and cannot be read. "
                "Please wait for the write to finish and try again."
            )
        entry["readers"] += 1
    return None


def _release_read_lock(file_path: str) -> None:
    """Release the file's read permission"""
    entry = _get_rw_entry(file_path)
    with entry["lock"]:
        entry["readers"] = max(0, entry["readers"] - 1)


def _acquire_write_lock(file_path: str) -> Optional[str]:
    """
    Acquire write permission for a file.
    Writing does not allow other reads or writes to run concurrently.
    
    Returns:
        None means success and writing is allowed
        str  means conflict, returns error message
    """
    normalized = os.path.abspath(file_path)
    entry = _get_rw_entry(file_path)
    with entry["lock"]:
        if entry["writer"] or entry["readers"] > 0:
            rc = entry["readers"]
            wc = "yes" if entry["writer"] else "no"
            return (
                f"File {os.path.basename(normalized)} is occupied by another operation "
                f"(readers: {rc}, writer: {wc}). "
                "All modifications to the same file must be merged into a single write(edits=[...]) call. "
                "Please re-read the file, plan all edits, then write once."
            )
        entry["writer"] = True
    return None


def _release_write_lock(file_path: str) -> None:
    """Release the file's write permission"""
    entry = _get_rw_entry(file_path)
    with entry["lock"]:
        entry["writer"] = False


# ── Dirty-write marker: prevent AI from writing the same file again without re-reading/previewing ──────────────────
# After a file is modified (write/format/uses), line numbers change; AI must re-read or validate with old_content before writing again.
_dirty_files: Set[str] = set()
_dirty_lock = threading.Lock()


def _mark_dirty(file_path: str) -> None:
    """Mark file as modified; preview or re-read is required before the next write."""
    normalized = os.path.abspath(file_path)
    with _dirty_lock:
        _dirty_files.add(normalized)


def _clear_dirty(file_path: str) -> None:
    """Clear dirty marker (cleared after a successful read)."""
    normalized = os.path.abspath(file_path)
    with _dirty_lock:
        _dirty_files.discard(normalized)


def _reject_removed_preview_argument(arguments: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Reject the removed delphi_file preview parameter before it can imply a write."""
    if "preview" in arguments:
        return _wrap_error("The preview parameter has been removed; use dry_run=true to preview, or dry_run=false to perform actual modification")
    return None


def _check_dirty(file_path: str, dry_run: bool = False) -> None:
    """
    Check whether the file is dirty (not re-read/previewed since last modification).
    If dirty and not dry_run mode, raise exception to block write.
    """
    if dry_run:
        return
    normalized = os.path.abspath(file_path)
    with _dirty_lock:
        if normalized in _dirty_files:
            raise RuntimeError(
                f"Line numbers in file {os.path.basename(normalized)} may have changed since the last write. "
                "Please call read first to get the latest line numbers, or provide old_content original-text validation for each edit, "
                "or use dry_run=true to preview this modification. "
                "Plan edits based on the latest line numbers, then initiate write again."
            )


async def handle_write(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle write action.

    Uniformly use edits parameter:
      - Full replacement: edits=[{start_line:1, content:"complete file content"}]
      - Partial replacement: edits=[{start_line:5, end_line:10, content:"replacement content"}]
      - Multi-segment replacement: edits=[{start_line:5, end_line:10, content:"..."},
                       {start_line:20, end_line:22, content:"..."}]
      - Delete lines:  edits=[{start_line:10, end_line:15, content:""}]

    Core features:
      - Auto-backup original file to __history (backup=True by default)
      - Auto-detect and preserve original encoding
      - Automatic DFM file handling: binary DFM auto-converted to text -> edit -> convert back to binary
      - Supports auto_format to automatically format code after write
      - Supports dry_run to preview diff without writing to disk

    Line numbers are all 1-indexed inclusive:
      edits=[{start_line:5, end_line:10}]  -> replace lines 5~10
      edits=[{start_line:5}]               -> replace from line 5 to end of file
      edits=[{end_line:10}]                -> replace from line 1 to line 10

    ⚠️ Dirty-marker protection:
       After every write (including auto_format), file line numbers change.
       Before re-reading the file or confirming with dry_run, writing to the same file again is not allowed,
       preventing AI from using stale line numbers and causing misaligned overwrites.
       Duplicate-line detection has been downgraded to a warning and no longer blocks writes.

       When old_content + each edit's original-text validation passes, the dirty marker can be safely skipped.
       allow_dirty=true can bypass the dirty-marker check (at your own risk).
    """
    removed_preview = _reject_removed_preview_argument(arguments)
    if removed_preview:
        return removed_preview

    file_path = arguments.get("file_path")
    edits = arguments.get("edits")
    backup = arguments.get("backup", True)
    encoding = arguments.get("encoding", "auto")
    auto_format = arguments.get("auto_format", False)
    dry_run = arguments.get("dry_run", False)
    force = arguments.get("force", False)
    allow_dirty = arguments.get("allow_dirty", False)
    if not file_path:
        return _wrap_error("Please provide file_path parameter")
    if not edits:
        return _wrap_error("Please provide edits parameter (full replacement: [{start_line:1, content:'...'}])")

    path_err = _validate_path(file_path, arguments.get("project_path"))
    if path_err:
        return _wrap_error("Path safety validation failed: %s" % path_err)

    # Normalize insert-type edits (those with position="before"/"after") into
    # single-line replacements before passing to _handle_write_edits.
    # Without this, an insert edit without end_line is treated as "to end of file"
    # by the overlap detection, causing false-positive "covers to end of file" errors
    # when mixed with later range replacements.
    if edits and any(edit.get("position") is not None for edit in edits):
        if not os.path.isfile(file_path):
            return _wrap_error("New files do not support insert-type edits containing a position field")
        result = await _normalize_insert_edits_for_write(
            file_path, edits, dry_run=dry_run
        )
        if result is None:
            return _wrap_error("Insert edit preprocessing failed")
        err, normalized_edits, cleanup_dir = result
        if err:
            if cleanup_dir:
                shutil.rmtree(cleanup_dir, ignore_errors=True)
            return _wrap_error(err)
        try:
            return await _handle_write_edits(
                file_path=file_path,
                edits=normalized_edits,
                backup=backup,
                encoding=encoding,
                auto_format=auto_format,
                dry_run=dry_run,
                force=force,
                allow_dirty=allow_dirty,
            )
        finally:
            if cleanup_dir:
                shutil.rmtree(cleanup_dir, ignore_errors=True)

    return await _handle_write_edits(
        file_path=file_path,
        edits=edits,
        backup=backup,
        encoding=encoding,
        auto_format=auto_format,
        dry_run=dry_run,
        force=force,
        allow_dirty=allow_dirty,
    )


async def _normalize_insert_edits_for_write(
    file_path: str,
    edits: List[Dict[str, Any]],
    dry_run: bool = False,
):
    """Normalize insert-type edits (those with position field) into single-line replacements.

    When action=write receives a mix of range replacements and position-based inserts,
    this function reads the file, converts each insert edit into a single-line replacement
    (end_line = start_line, content includes both anchor text + inserted text), so that
    _handle_write_edits can apply them correctly with proper overlap detection.

    Returns (error_msg_or_None, normalized_edits, tmp_cleanup_dir).
    """
    detected_encoding = detect_encoding(file_path)
    read_path = file_path
    tmp_cleanup = None
    try:
        if _is_dfm_file(file_path):
            fmt = dfm_utils._detect_dfm_format(file_path)
            if fmt == "binary":
                tmp_cleanup = tempfile.mkdtemp(prefix="filetool_insert_norm_")
                read_path = os.path.join(tmp_cleanup, os.path.basename(file_path) + ".txt")
                conv_result = await dfm_utils.convert_dfm(file_path, read_path, to_text=True)
                if not conv_result.get("success"):
                    return (f"Binary DFM conversion failed: {conv_result.get('message', 'unknown error')}", edits, tmp_cleanup)
        with open(read_path, 'r', encoding=detected_encoding, newline='', buffering=BUFFER_SIZE_1MB) as f:
            lines = f.readlines()
    except Exception as e:
        return (str(e), edits, tmp_cleanup)

    has_crlf = any('\r\n' in line for line in lines)
    total_lines = len(lines)
    normalized: List[Dict[str, Any]] = []

    for i, edit in enumerate(edits):
        position = edit.get("position")
        if position is not None:
            s_1 = edit.get("start_line")
            content = edit.get("content")
            desc = edit.get("description", f"insert #{i}")
            old_content = _get_old_content(edit)

            if s_1 is None or not isinstance(s_1, int):
                return (f"edits[{i}] ({desc}): start_line must be an integer", normalized, tmp_cleanup)
            if s_1 < 1:
                return (f"edits[{i}] ({desc}): start_line ({s_1}) cannot be less than 1", normalized, tmp_cleanup)
            if content is None:
                return (f"edits[{i}] ({desc}): missing required content", normalized, tmp_cleanup)
            if position not in ("before", "after"):
                return (f"edits[{i}] ({desc}): position must be before or after", normalized, tmp_cleanup)

            anchor_idx = s_1 - 1
            if anchor_idx < 0 or anchor_idx >= total_lines:
                return (f"edits[{i}] ({desc}): start_line {s_1} exceeds current total line count {total_lines}", normalized, tmp_cleanup)

            anchor_text = lines[anchor_idx]

            # Validate old_content against anchor line if provided
            if old_content is not None:
                if _normalize_code_for_compare(old_content) != _normalize_code_for_compare(anchor_text):
                    expected_lines = old_content.splitlines(keepends=True) or [""]
                    return ((
                        f"edits[{i}] ({desc}): old_content mismatch for insert anchor [{s_1}, {s_1}]\n"
                        f"  expected: {expected_lines[0].rstrip()}\n"
                        f"  actual: {anchor_text.rstrip()}"
                    ), normalized, tmp_cleanup)

            insert_text = _prepare_insert_content(content, has_crlf)
            if position == "before":
                replacement = insert_text + anchor_text
            else:
                anchor_for_replace = anchor_text
                if not anchor_for_replace.endswith(('\n', '\r\n')):
                    anchor_for_replace += '\r\n' if has_crlf else '\n'
                replacement = anchor_for_replace + insert_text

            normalized.append({
                "start_line": s_1,
                "end_line": s_1,
                "content": replacement,
                "old_content": old_content if old_content is not None else anchor_text,
                "description": desc,
            })
        else:
            normalized.append(edit)

    return (None, normalized, tmp_cleanup)
async def handle_replace(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle action=replace with mandatory old_content for existing files."""
    return await _handle_structured_write_action(arguments, "replace")


async def handle_insert(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle action=insert using old_content as an anchor line guard."""
    return await _handle_structured_write_action(arguments, "insert")


async def handle_delete(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle action=delete with mandatory old_content for existing files."""
    return await _handle_structured_write_action(arguments, "delete")


async def _handle_structured_write_action(arguments: Dict[str, Any], action: str) -> Dict[str, Any]:
    """Normalize replace/insert/delete actions to the existing edit engine."""
    removed_preview = _reject_removed_preview_argument(arguments)
    if removed_preview:
        return removed_preview

    file_path = arguments.get("file_path")
    edits = arguments.get("edits")
    backup = arguments.get("backup", True)
    encoding = arguments.get("encoding", "auto")
    auto_format = arguments.get("auto_format", False)
    dry_run = arguments.get("dry_run", False)
    force = arguments.get("force", False)
    allow_dirty = arguments.get("allow_dirty", False)

    if not file_path:
        return _wrap_error("Please provide file_path parameter")
    if not edits:
        return _wrap_error(f"Please provide edits parameter (action={action})")
    if not isinstance(edits, (list, tuple)):
        return _wrap_error("edits must be a list")

    path_err = _validate_path(file_path, arguments.get("project_path"))
    if path_err:
        return _wrap_error("Path safety validation failed: %s" % path_err)

    if dry_run:
        lock_err = _acquire_read_lock(file_path)
    else:
        lock_err = _acquire_write_lock(file_path)
    if lock_err:
        return _wrap_error(lock_err)

    anchor_tmp_cleanup = None
    try:
        file_exists = os.path.isfile(file_path)
        if not file_exists:
            if action != "replace":
                return _wrap_error(f"New files do not support action={action}, please use action=replace or compatible action=write to create a complete file")
            return await _handle_write_edits(
                file_path=file_path,
                edits=edits,
                backup=backup,
                encoding=encoding,
                auto_format=auto_format,
                dry_run=dry_run,
                force=force,
                allow_dirty=allow_dirty,
                lock_already_held=True,
            )

        if not allow_dirty and not _all_edits_have_old_content(edits):
            try:
                _check_dirty(file_path, dry_run=dry_run)
            except RuntimeError as e:
                return _wrap_error(str(e))

        lines: List[str] = []
        has_crlf = False
        if action == "insert":
            try:
                lines, anchor_tmp_cleanup = await _read_structured_anchor_lines(file_path)
            except RuntimeError as e:
                return _wrap_error(str(e))
            has_crlf = any('\r\n' in line for line in lines)

        normalized_edits: List[Dict[str, Any]] = []
        for i, edit in enumerate(edits):
            if not isinstance(edit, dict):
                return _wrap_error(f"edits[{i}] must be a dict")
            desc = edit.get("description", f"{action} #{i}")
            s_1 = edit.get("start_line")
            e_1 = edit.get("end_line")
            content = edit.get("content")
            old_content = _get_old_content(edit)

            if s_1 is None:
                return _wrap_error(f"edits[{i}] ({desc}): missing required start_line")
            if not isinstance(s_1, int):
                return _wrap_error(f"edits[{i}] ({desc}): start_line must be an integer")
            if s_1 < 1:
                return _wrap_error(f"edits[{i}] ({desc}): start_line ({s_1}) cannot be less than 1")
            if e_1 is not None and not isinstance(e_1, int):
                return _wrap_error(f"edits[{i}] ({desc}): end_line must be an integer")
            if action in ("replace", "delete") and e_1 is not None and s_1 > e_1:
                return _wrap_error(f"edits[{i}] ({desc}): start_line ({s_1}) > end_line ({e_1}), must satisfy start_line ≤ end_line")
            if not _edit_has_non_empty_old_content(edit):
                return _wrap_error(f"edits[{i}] ({desc}): action={action} must provide non-empty old_content")

            if action == "replace":
                if content is None:
                    return _wrap_error(f"edits[{i}] ({desc}): action=replace must provide content")
                new_edit = dict(edit)
            elif action == "delete":
                if content not in (None, ""):
                    return _wrap_error(f"edits[{i}] ({desc}): action=delete does not accept non-empty content")
                new_edit = dict(edit)
                new_edit["content"] = ""
            else:
                if content is None:
                    return _wrap_error(f"edits[{i}] ({desc}): action=insert must provide content")
                if content == "":
                    return _wrap_error(f"edits[{i}] ({desc}): action=insert content cannot be empty")
                if e_1 is not None and e_1 != s_1:
                    return _wrap_error(f"edits[{i}] ({desc}): action=insert does not support end_line spanning multiple lines, the anchor can only be start_line")
                position = edit.get("position", "before")
                if position not in ("before", "after"):
                    return _wrap_error(f"edits[{i}] ({desc}): position must be before or after")
                anchor_idx = s_1 - 1
                if anchor_idx < 0 or anchor_idx >= len(lines):
                    return _wrap_error(f"edits[{i}] ({desc}): start_line {s_1} exceeds current total line count {len(lines)}")
                anchor_text = lines[anchor_idx]
                if _normalize_code_for_compare(old_content or "") != _normalize_code_for_compare(anchor_text):
                    expected_lines = (old_content or "").splitlines(keepends=True)
                    msg = [
                        f"edits[{i}] ({desc}): old_content mismatch for insert anchor [{s_1}, {s_1}]",
                        "expected:",
                    ]
                    msg.extend(_format_line_snippet(expected_lines, 0, len(expected_lines)))
                    msg.append("actual:")
                    msg.extend(_format_line_snippet(lines, anchor_idx, anchor_idx + 1))
                    return _wrap_error("\n".join(msg))
                insert_text = _prepare_insert_content(content, has_crlf)
                if position == "before":
                    replacement = insert_text + anchor_text
                else:
                    anchor_for_replace = anchor_text
                    if not anchor_for_replace.endswith(('\n', '\r\n')):
                        anchor_for_replace += '\r\n' if has_crlf else '\n'
                    replacement = anchor_for_replace + insert_text
                new_edit = {
                    "start_line": s_1,
                    "end_line": s_1,
                    "content": replacement,
                    "old_content": old_content,
                    "description": desc,
                }
            normalized_edits.append(new_edit)

        return await _handle_write_edits(
            file_path=file_path,
            edits=normalized_edits,
            backup=backup,
            encoding=encoding,
            auto_format=auto_format,
            dry_run=dry_run,
            force=force,
            allow_dirty=True,  # Safety: old_content validation already ensures line number correctness, no dirty marker needed
            lock_already_held=True,
        )
    finally:
        if anchor_tmp_cleanup:
            shutil.rmtree(anchor_tmp_cleanup, ignore_errors=True)
        if dry_run:
            _release_read_lock(file_path)
        else:
            _release_write_lock(file_path)


def _format_unchanged_ranges(edit_results: List[Dict[str, Any]], total_lines_before: int) -> str:
    """Derive unchanged ranges from the edit result list and format them as text

    The regions between each edit and at the end are all "unchanged";
    label the offset of that range in the final file, so the AI can look it up without calculating it itself.

    Args:
        edit_results: Record for each edit, containing actual_start (1-indexed), inserted, delta
        total_lines_before: Total line count of the file before editing

    Returns:
        Format such as "  Unchanged: [1, 4] unchanged, [14, 150] +3"
        Returns an empty string when all edits cover the entire text
    """
    parts: List[str] = []
    cursor = 1  # 1-indexed current position
    offset = 0
    for er in edit_results:
        start = er["actual_start"]
        if start > cursor:
            off_str = "unchanged" if offset == 0 else f"{offset:+d}"
            parts.append(f"[{cursor}, {start - 1}] {off_str}")
        # Skip the region covered by the edit
        if er["inserted"] > 0:
            cursor = start + er["inserted"]
        # Delete operations do not advance cursor (no new content occupies the position)
        offset += er["delta"]
    # Trailing unchanged region
    if cursor <= total_lines_before:
        off_str = "unchanged" if offset == 0 else f"{offset:+d}"
        parts.append(f"[{cursor}, {total_lines_before}] {off_str}")

    if not parts:
        return ""
    return f"  Unchanged: {', '.join(parts)}"



async def _handle_write_edits(
    file_path: str,
    edits: List[Dict],
    backup: bool = True,
    encoding: str = "auto",
    auto_format: bool = False,
    dry_run: bool = False,
    force: bool = False,
    allow_dirty: bool = False,
    lock_already_held: bool = False,
) -> Dict[str, Any]:
    """Batch write internal implementation (edits array, using the original file as reference)."""
    if not edits:
        return _wrap_error("Please provide edits list")
    if not isinstance(edits, (list, tuple)):
        return _wrap_error("edits must be a list")

    if not lock_already_held:
        if dry_run:
            lock_err = _acquire_read_lock(file_path)
        else:
            lock_err = _acquire_write_lock(file_path)
        if lock_err:
            return _wrap_error(lock_err)

    bak_path = None
    read_path = file_path
    tmp_cleanup = None
    try:
        if not allow_dirty and not _all_edits_have_old_content(edits):
            try:
                _check_dirty(file_path, dry_run=dry_run)
            except RuntimeError as e:
                return _wrap_error(str(e))

        file_exists = os.path.isfile(file_path)
        if not file_exists:
            if len(edits) != 1:
                return _wrap_error("New files can only have one edit")
            e0 = edits[0]
            if e0.get("start_line", 0) != 1:
                return _wrap_error("New files must start from start_line=1")
            if not e0.get("content"):
                return _wrap_error("New files must provide content")
            # Go directly to full write
            content = e0["content"]
            # If creating a new DFM file, automatically convert Chinese to #XXXX escape sequences
            if _is_dfm_file(file_path):
                content = dfm_utils.escape_dfm_chinese(content)
            original_encoding = encoding if encoding != "auto" else "utf-8-sig"

            # Preview mode
            if dry_run:
                return {
                    "status": "success",
                    "message": (
                        f"[dry_run] would create new file: {os.path.basename(file_path)}, "
                        f"{len(content.encode('utf-8'))} bytes"
                    ),
                }

            # Write new file: first write a temporary file on the same volume, then replace the target after success.
            temp_write_path = _make_temp_write_path(file_path)
            try:
                _write_text_temp(temp_write_path, content, original_encoding)
                record_authorized_write(
                    file_path,
                    tool="delphi_file",
                    operation="write",
                )
                _replace_with_temp(temp_write_path, file_path)
            except Exception as e:
                if os.path.exists(temp_write_path):
                    try:
                        os.remove(temp_write_path)
                    except OSError:
                        pass
                return _wrap_error(f"Failed to create file: {e}")

            _mark_dirty(file_path)
            return {
                "status": "success",
                "message": f"wrote: {os.path.basename(file_path)}, encoding: {original_encoding}",
            }

        is_dfm_binary = False
        if _is_dfm_file(file_path):
            try:
                fmt = dfm_utils._detect_dfm_format(file_path)
                is_dfm_binary = (fmt == "binary")
            except (FileNotFoundError, PermissionError) as e:
                return _wrap_error(str(e))

        detected_encoding = detect_encoding(file_path)
        if encoding == "auto":
            read_enc = detected_encoding
            write_enc = detected_encoding
            encoding_transcoded = False
        else:
            read_enc = detected_encoding
            if _is_encoding_compatible(encoding, detected_encoding):
                write_enc = detected_encoding
            else:
                write_enc = encoding
            encoding_transcoded = not _is_encoding_compatible(encoding, detected_encoding)

        validated_edits = []
        for i, edit in enumerate(edits):
            if not isinstance(edit, dict):
                return _wrap_error(f"edits[{i}] must be a dict")
            s_1 = edit.get("start_line")
            e_1 = edit.get("end_line")
            c = edit.get("content")
            desc = edit.get("description", f"edit #{i}")
            old_content = _get_old_content(edit)
            if s_1 is None:
                return _wrap_error(f"edits[{i}] ({desc}): missing required start_line")
            if c is None:
                return _wrap_error(f"edits[{i}] ({desc}): missing required content")
            if not isinstance(s_1, int):
                return _wrap_error(f"edits[{i}] ({desc}): start_line must be an integer")
            if e_1 is not None and not isinstance(e_1, int):
                return _wrap_error(f"edits[{i}] ({desc}): end_line must be an integer")
            if s_1 < 1:
                return _wrap_error(f"edits[{i}] ({desc}): start_line ({s_1}) cannot be less than 1")
            if e_1 is not None and s_1 > e_1:
                return _wrap_error(f"edits[{i}] ({desc}): start_line ({s_1}) > end_line ({e_1}), must satisfy start_line ≤ end_line")
            validated_edits.append((s_1 - 1, e_1, c, desc, s_1, e_1, old_content))

        validated_edits.sort(key=lambda x: x[0])

        for i in range(len(validated_edits) - 1):
            curr_s_0, curr_e_0, _, _, _, _, _ = validated_edits[i]
            next_s_0, _, _, _, _, _, _ = validated_edits[i + 1]
            if curr_e_0 is None:
                return _wrap_error(
                    f"edits interval overlap: \"{validated_edits[i][3]}\" (start={validated_edits[i][4]}) covers to end of file, "
                    f"overlaps with \"{validated_edits[i+1][3]}\" (start={validated_edits[i+1][4]})"
                )
            if next_s_0 < curr_e_0:
                return _wrap_error(
                    f"edits interval overlap: \"{validated_edits[i][3]}\" [{validated_edits[i][4]},{validated_edits[i][5]}] "
                    f"overlaps with \"{validated_edits[i+1][3]}\" [{validated_edits[i+1][4]},...)"
                )

        if is_dfm_binary:
            tmp_dir = tempfile.mkdtemp(prefix="filetool_")
            text_path = os.path.join(tmp_dir, os.path.basename(file_path) + ".txt")
            conv_result = await dfm_utils.convert_dfm(file_path, text_path, to_text=True)
            if not conv_result.get("success"):
                shutil.rmtree(tmp_dir, ignore_errors=True)
                return _wrap_error(f"Binary DFM conversion failed: {conv_result.get('message', 'Unknown error')}")
            read_path = text_path
            read_enc = detect_encoding(read_path)
            tmp_cleanup = tmp_dir
        with open(read_path, 'r', encoding=read_enc, newline='', buffering=BUFFER_SIZE_1MB) as f:
            lines = f.readlines()

        total = len(lines)
        original_lines = lines[:]
        has_crlf = any('\r\n' in line for line in lines)

        cumulative_offset = 0
        results = []
        edit_results: List[Dict[str, Any]] = []
        all_success = True

        for s_0, e_0, c, desc, s_1, e_1, old_content in validated_edits:
            adj_s = s_0 + cumulative_offset
            adj_e = (e_0 + cumulative_offset) if e_0 is not None else len(lines)

            if adj_s < 0 or adj_s > len(lines):
                results.append(f"  ❌ {desc}: start_line {s_1} (after adjustment {adj_s}) is out of current range")
                all_success = False
                continue
            if adj_e > len(lines):
                results.append(f"  ❌ {desc}: end_line {e_1 or total} (after adjustment {adj_e}) exceeds current total line count {len(lines)}")
                all_success = False
                continue
            if adj_s >= adj_e:
                results.append(f"  ❌ {desc}: adjusted range is empty [{adj_s}, {adj_e})")
                all_success = False
                continue

            old_text = ''.join(lines[adj_s:adj_e])
            if old_content is not None:
                short_warning = _warn_if_old_content_too_short(old_content)
                if short_warning:
                    results.append(f"  ⚠️ {desc}: {short_warning}")
                expected_norm = _normalize_code_for_compare(old_content)
                actual_norm = _normalize_code_for_compare(old_text)
                if expected_norm != actual_norm:
                    expected_lines = old_content.splitlines(keepends=True)
                    results.append(
                        f"  ❌ {desc}: old_content mismatch for [{adj_s + 1}, {adj_e}]"
                    )
                    results.append("    expected:")
                    results.extend(_format_line_snippet(expected_lines, 0, len(expected_lines)))
                    results.append("    actual:")
                    results.extend(_format_line_snippet(lines, adj_s, adj_e))
                    all_success = False
                    continue

            removed = adj_e - adj_s
            removed_lines_dry_run = []

            before_len = len(lines)  # Line count before this edit (including previous edits)
            if c == '':
                if removed > 0 and removed <= 5:
                    actual_lineno = adj_s + 1
                    removed_lines_dry_run = [
                        (actual_lineno + i, lines[adj_s + i].rstrip('\n\r'))
                        for i in range(removed)
                    ]
                lines[adj_s:adj_e] = []
                inserted = 0
                c_lines = []
            else:
                if has_crlf:
                    c = c.replace('\r\n', '\n').replace('\n', '\r\n')
                else:
                    c = c.replace('\r\n', '\n')
                if not c.endswith('\n') and not c.endswith('\r\n'):
                    c = c + ('\r\n' if has_crlf else '\n')

                c_lines = c.splitlines(keepends=True)
                inserted = len(c_lines)

                if removed > 0 and removed <= 5:
                    actual_lineno = adj_s + 1  # Actual 1-indexed starting line number
                    removed_lines_dry_run = [
                        (actual_lineno + i, lines[adj_s + i].rstrip('\n\r'))
                        for i in range(removed)
                    ]

                lines[adj_s:adj_e] = c_lines

            delta = inserted - removed
            prev_cumulative_offset = cumulative_offset  # Cumulative offset before this edit
            cumulative_offset += delta

            # Display actual line number range (add parenthetical note when different from specified line number)
            adj_s_display = adj_s + 1
            adj_e_display = adj_e  # 0-indexed exclusive → 1-indexed inclusive
            range_suffix = "" if adj_s_display == s_1 else f" (specified {s_1})"
            if inserted == 0:
                results.append(
                    f"  [{adj_s_display}, {adj_e_display}] → deleted before line {adj_s_display} "
                    f"(offset: {delta:+d}){range_suffix}  {desc}"
                )
            else:
                results.append(
                    f"  [{adj_s_display}, {adj_e_display}] → [{adj_s_display}, {adj_e_display + delta}] "
                    f"(offset: {delta:+d}){range_suffix}  {desc}"
                )

            # Per-edit diff preview (1-indexed line numbers)
            if removed_lines_dry_run:
                for orig_lineno, rl in removed_lines_dry_run:
                    display = rl if len(rl) <= 80 else rl[:77] + "..."
                    results.append(f"    - L{orig_lineno}: {display}")
            if c_lines:
                max_show = min(len(c_lines), 5)
                for cl in c_lines[:max_show]:
                    display = cl.rstrip('\n\r')
                    display = display if len(display) <= 80 else display[:77] + "..."
                    results.append(f"    + {display}")
                if len(c_lines) > max_show:
                    results.append(f"    + ... (total {len(c_lines)} lines)")

            # Notify AI of actual line number offset when previous edits caused cumulative offset
            if prev_cumulative_offset != 0:
                results.append(
                    f"    ℹ Offset: previous {prev_cumulative_offset:+d} line offset, "
                    f"actual line number = specified line number{prev_cumulative_offset:+d}"
                )

            # Collect edit results for generating "unchanged ranges" hint
            edit_results.append({
                "actual_start": adj_s_display,
                "inserted": inserted,
                "delta": delta,
            })

        new_text = ''.join(lines)
        # For DFM files, automatically convert non-ASCII characters (Chinese) inside single quotes to #XXXX escape sequences
        if _is_dfm_file(file_path):
            new_text = dfm_utils.escape_dfm_chinese(new_text)
        encoding_fallback = False
        fmt_msg = ""

        # Cumulative offset consistency self-check
        expected_total = total + cumulative_offset
        actual_total = len(lines)
        if actual_total != expected_total:
            results.append(
                f"  ❌ Internal error: line count after applying edits {actual_total} ≠ "
                f"original {total} + cumulative offset {cumulative_offset} = {expected_total}, "
                f"please report this issue"
            )
            all_success = False

        if not all_success and not dry_run:
            if bak_path and os.path.exists(bak_path):
                try:
                    os.remove(bak_path)
                except OSError:
                    pass
            summary = [
                "Some edits failed; write to disk cancelled",
                f"failed: {len(validated_edits)} edits, {os.path.basename(file_path)}, encoding: {write_enc}",
                "",
            ]
            summary.extend(results)
            return {"status": "failed", "message": "\n".join(summary)}

        # AI offset error detection
        if not force:
            orig_dup_contents = set()
            for i in range(1, len(original_lines)):
                prev = original_lines[i - 1].rstrip('\r\n')
                curr = original_lines[i].rstrip('\r\n')
                if prev and curr and prev == curr:
                    orig_dup_contents.add(prev)

            new_dup_lines = []
            for i in range(1, len(lines)):
                prev = lines[i - 1].rstrip('\r\n')
                curr = lines[i].rstrip('\r\n')
                if prev and curr and prev == curr and prev not in orig_dup_contents:
                    new_dup_lines.append((i + 1, prev))

            if new_dup_lines:
                dup_msgs = [f"    Line {i}: {txt}" for i, txt in new_dup_lines[:10]]
                if len(new_dup_lines) > 10:
                    dup_msgs.append(f"    ... {len(new_dup_lines) - 10} more")
                warn = (
                    "⚠️ Write completed, but consecutive duplicate lines were detected; please verify the result.\n"
                    f"Total {len(new_dup_lines)} new duplicates:\n" + "\n".join(dup_msgs)
                )
                results.append(warn)
                logger.warning(
                    f"Consecutive duplicate line warning ({os.path.basename(file_path)}): "
                    f"{len(new_dup_lines)} occurrences"
                )

        # Write to disk
        if not dry_run:
            temp_write_path = _make_temp_write_path(file_path)
            text_tmp = None
            try:
                if is_dfm_binary:
                    text_tmp = temp_write_path + ".txt"
                    _write_text_temp(text_tmp, new_text, write_enc)
                    conv_result = await dfm_utils.convert_dfm(text_tmp, temp_write_path, to_text=False)
                    if not conv_result.get("success"):
                        if bak_path and os.path.exists(bak_path):
                            try:
                                os.remove(bak_path)
                            except OSError:
                                pass
                        return _wrap_error(f"Binary DFM conversion failed; write cancelled: {conv_result.get('message', 'Unknown error')}")
                else:
                    try:
                        _write_text_temp(temp_write_path, new_text, write_enc)
                    except UnicodeEncodeError:
                        logger.warning(f"Encoding {write_enc} write failed, falling back to utf-8")
                        _write_text_temp(temp_write_path, new_text, "utf-8")
                        write_enc = "utf-8"
                        encoding_fallback = True

                if backup:
                    bak_path = create_backup(file_path)
                    if not bak_path:
                        return _wrap_error("Failed to create backup; write cancelled")

                record_authorized_write(
                    file_path,
                    tool="delphi_file",
                    operation="write",
                )
                _replace_with_temp(temp_write_path, file_path)
            except Exception as ex:
                return _wrap_error(f"Failed to write file; write cancelled: {ex}")
            finally:
                for cleanup_path in (text_tmp, temp_write_path):
                    if cleanup_path and os.path.exists(cleanup_path):
                        try:
                            os.remove(cleanup_path)
                        except OSError:
                            pass

            # Auto-format after writing
            if auto_format and _is_delphi_file(file_path):
                try:
                    formatted, write_enc, fmt_encoding_fallback, _ = await _apply_auto_format_atomically(
                        file_path, write_enc, has_crlf
                    )
                    if formatted:
                        fmt_msg = ", formatted after write"
                    if fmt_encoding_fallback:
                        encoding_fallback = True
                except Exception as ex:
                    logger.warning(f"Auto-format after writing failed: {ex}")
                    results.append(f"  ⚠ auto_format failed: {ex}")

            # auto_format may additionally change line count (expand uses, adjust blank lines, etc.); recalculate the actual offset
            fmt_diff = 0
            if auto_format and not dry_run and os.path.isfile(file_path) and fmt_msg:
                try:
                    with open(file_path, 'r', encoding=write_enc, newline='',
                              buffering=BUFFER_SIZE_1MB) as f:
                        new_total = sum(1 for _ in f)
                    expected_total = total + cumulative_offset
                    if new_total != expected_total:
                        fmt_diff = new_total - expected_total
                        cumulative_offset += fmt_diff
                except Exception as ex:
                    logger.debug(f"Failed to re-read line count after auto_format: {ex}")
            if fmt_diff:
                results.append(
                    f"  ⚠ auto_format extra offset: {fmt_diff:+d}, cumulative total offset: {cumulative_offset:+d}"
                )

            # Mark dirty
            _mark_dirty(file_path)
        elif all_success:
            results.append("  ℹ dry_run does not clear the dirty marker; subsequent write still requires read or old_content validation")

        # Append "unchanged ranges" hint (not output on failure because line numbers have been polluted)
        if all_success and not dry_run:
            unchanged = _format_unchanged_ranges(edit_results, total)
            if unchanged:
                results.append(unchanged)

        # Summary output
        summary = []
        basename = os.path.basename(file_path)
        action_label = "dry_run" if dry_run else "wrote"
        header_parts = [
            f"{action_label}: {len(validated_edits)} edits, {basename}",
            f"encoding: {write_enc}",
        ]
        if allow_dirty:
            header_parts.append("⚠ allow_dirty: dirty marker bypassed (please ensure line numbers are accurate)")
        if dry_run:
            header_parts.append("dry_run: true (not written to disk)")
            if auto_format:
                header_parts.append("⚠ dry_run does not include auto_format offset")
        if encoding_transcoded:
            header_parts.append(f"ℹ transcoded: {detected_encoding} → {write_enc}")
        if encoding_fallback:
            header_parts.append(f"⚠ fallback: {detected_encoding} → utf-8")
        if not dry_run and bak_path and backup:
            header_parts.append(f"backup: __history\\{os.path.basename(bak_path)}")
        if fmt_msg:
            header_parts.append("formatted: yes")
        if is_dfm_binary:
            header_parts.append("format: binary DFM converted")

        summary.append(", ".join(header_parts))
        summary.append("")
        summary.extend(results)

        if all_success:
            return {
                "status": "success",
                "message": "\n".join(summary),
            }
        else:
            summary.insert(0, "Some edits failed; please check the results above")
            return {"status": "failed", "message": "\n".join(summary)}

    finally:
        if not lock_already_held:
            if dry_run:
                _release_read_lock(file_path)
            else:
                _release_write_lock(file_path)
        if tmp_cleanup:
            shutil.rmtree(tmp_cleanup, ignore_errors=True)

async def handle_format(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle format action — delegates to pasfmt.format_file / format_code.
    """
    file_path = arguments.get("file_path")
    action = arguments.get("mode", "file")
    uses_style = arguments.get("uses_style")
    dry_run = arguments.get("dry_run", False)
    backup_flag = arguments.get("backup", True)

    if action != "code" and file_path:
        path_err = _validate_path(file_path, arguments.get("project_path"))
        if path_err:
            return _wrap_error("Path security validation failed: %s" % path_err)

    if action == "code":
        code = arguments.get("code", "")
        if not code:
            return _wrap_error("Please provide the code parameter")
        raw_result = await pasfmt.format_code(
            code=code,
            config_path=arguments.get("config_path"),
            uses_style=uses_style,
        )
        # format_code returns CallToolResult; convert uniformly to dict
        if isinstance(raw_result, CallToolResult):
            text = raw_result.content[0].text if raw_result.content else ""
            if raw_result.isError:
                result = _wrap_error(text)
            else:
                result = {"status": "success", "message": text, "formatted": True}
        else:
            result = raw_result
    else:
        if not file_path:
            return _wrap_error("Please provide the file_path parameter")
        if action == "check":
            lock_err = _acquire_read_lock(file_path)
            if lock_err:
                return _wrap_error(lock_err)
            try:
                result = await pasfmt.format_file(
                    file_path=file_path,
                    dry_run=True,
                )
            finally:
                _release_read_lock(file_path)
        else:
            if dry_run:
                lock_err = _acquire_read_lock(file_path)
                if lock_err:
                    return _wrap_error(lock_err)
                try:
                    result = await pasfmt.format_file(
                        file_path=file_path,
                        dry_run=True,
                    )
                finally:
                    _release_read_lock(file_path)
            else:
                lock_err = _acquire_write_lock(file_path)
                if lock_err:
                    return _wrap_error(lock_err)
                try:
                    try:
                        detected_enc = detect_encoding(file_path)
                        with open(file_path, 'r', encoding=detected_enc, newline='',
                                  buffering=BUFFER_SIZE_1MB) as f:
                            original_text = f.read()
                        formatted, write_enc, encoding_fallback, backup_path = await _apply_auto_format_atomically(
                            file_path=file_path,
                            encoding=detected_enc,
                            has_crlf='\r\n' in original_text,
                            backup=backup_flag,
                            config_path=arguments.get("config_path"),
                            uses_style=uses_style,
                        )
                        result = {
                            "status": "success",
                            "formatted": formatted,
                            "message": "Code formatted successfully" if formatted else "Code is already formatted",
                            "backup_file": backup_path,
                        }
                        if encoding_fallback:
                            result["message"] += f", encoding fallback: {detected_enc} → {write_enc}"
                    except Exception as ex:
                        result = _wrap_error(f"Formatting failed: {ex}")
                    else:
                        # Formatting succeeded → mark dirty (line numbers changed, force re-read)
                        # ⚠ Do not compute offsets: pasfmt may restructure code (expand uses, adjust begin/end, etc.),
                        #   line numbers before and after formatting have no linear correspondence. AI must trigger re-read via the dirty flag.
                        if result.get("status") == "success" and result.get("formatted"):
                            _mark_dirty(file_path)
                finally:
                    _release_write_lock(file_path)

    # pasfmt.format_file / format_code results are already unified as dict
    return result


async def handle_encode(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle encode action — file encoding conversion.

    Convert a file from one encoding to another.
    Auto-detects the source encoding (from_encoding="auto"), writes to the target encoding (to_encoding required).

    Parameters:
      file_path: file path
      from_encoding: source encoding ("auto"=auto-detect, default "auto")
      to_encoding: target encoding (required), e.g. utf-8/utf-8-sig/gbk/utf-16/utf-16-le/utf-16-be
      backup: whether to back up to __history before conversion (default true)
      dry_run: preview mode (default false)
    """
    removed_preview = _reject_removed_preview_argument(arguments)
    if removed_preview:
        return removed_preview

    file_path = arguments.get("file_path")
    from_encoding = arguments.get("from_encoding", "auto")
    to_encoding = arguments.get("to_encoding")
    backup = arguments.get("backup", True)
    dry_run = arguments.get("dry_run", False)

    if not file_path:
        return _wrap_error("Please provide the file_path parameter")
    if not to_encoding:
        return _wrap_error("Please provide the to_encoding parameter (target encoding)")

    path_err = _validate_path(file_path, arguments.get("project_path"))
    if path_err:
        return _wrap_error("Path security validation failed: %s" % path_err)

    if not os.path.isfile(file_path):
        return _wrap_error(f"File not found: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()
    if ext not in _DELPHI_EXTENSIONS:
        return _wrap_error(f"Unsupported file type: {ext}, only Delphi source files are supported")

    # Acquire write lock (read+write mutual exclusion); use read lock in preview mode
    if dry_run:
        lock_err = _acquire_read_lock(file_path)
    else:
        lock_err = _acquire_write_lock(file_path)
    if lock_err:
        return _wrap_error(lock_err)

    try:
        # Detect source encoding
        detected_enc = detect_encoding(file_path)
        read_enc = detected_enc if from_encoding == "auto" else from_encoding

        # Resolve target encoding (supports "ansi" alias → system ANSI code page)
        target_enc = to_encoding.lower()
        if target_enc == "ansi":
            try:
                target_enc = locale.getpreferredencoding()
            except Exception:
                target_enc = "utf-8"
        else:
            target_enc = to_encoding

        # Validate encoding validity
        try:
            codecs.lookup(read_enc)
        except LookupError:
            return _wrap_error(f"Source encoding '{read_enc}' is not recognized")
        try:
            codecs.lookup(target_enc)
        except LookupError:
            return _wrap_error(f"Target encoding '{target_enc}' is not recognized")

        # Preview mode
        if dry_run:
            read_size = os.path.getsize(file_path)
            return {
                "status": "success",
                "message": (
                    f"[dry_run] would convert: {os.path.basename(file_path)}\n"
                    f"  from: {detected_enc} (detected) / {read_enc} (specified)\n"
                    f"  to:   {target_enc}\n"
                    f"  size: {read_size} bytes"
                ),
            }

        # Read file content
        try:
            with open(file_path, 'r', encoding=read_enc, newline='', buffering=BUFFER_SIZE_1MB) as f:
                text = f.read()
        except UnicodeDecodeError:
            # When user explicitly specified from_encoding fails to decode, fall back automatically to auto-detected result
            if from_encoding != "auto":
                logger.warning(
                    f"User-specified encoding '{read_enc}' failed to decode, falling back to auto-detected '{detected_enc}'"
                )
                try:
                    with open(file_path, 'r', encoding=detected_enc, newline='', buffering=BUFFER_SIZE_1MB) as f:
                        text = f.read()
                    read_enc = detected_enc
                except UnicodeDecodeError:
                    return _wrap_error(
                        f"Neither the specified encoding '{from_encoding}' nor the auto-detected '{detected_enc}' could decode the file. "
                        "Please verify the file encoding and explicitly specify the correct from_encoding"
                    )
            else:
                return _wrap_error(f"Auto-detected encoding '{detected_enc}' failed to decode. Please try explicitly specifying from_encoding")
        except Exception as e:
            return _wrap_error(f"Failed to read file: {e}")

        original_size = len(text.encode(read_enc, errors='replace'))
        new_size = len(text.encode(target_enc, errors='replace'))

        # BOM handling: strip existing BOM on read; output encoding decides whether to re-add it
        text_stripped = text.lstrip('\ufeff')

        # Validate: read back with target encoding first, ensuring conversion is reversible
        try:
            encoded_bytes = text_stripped.encode(target_enc, errors='strict')
            decoded_back = encoded_bytes.decode(target_enc)
            if decoded_back != text_stripped:
                logger.warning(f"Encoding conversion contains irreversible characters")
        except (UnicodeEncodeError, UnicodeDecodeError) as e:
            return _wrap_error(f"Encoding conversion failed: target encoding '{target_enc}' cannot represent some characters in the file: {e}")

        # Create backup
        bak_path = None
        if backup:
            bak_path = create_backup(file_path)
            if not bak_path:
                return _wrap_error("Failed to create backup, conversion cancelled")

        # Write new encoding (using BOM-stripped text, output encoding decides whether to add BOM)
        temp_write_path = _make_temp_write_path(file_path)
        try:
            _write_text_temp(temp_write_path, text_stripped, target_enc)
            record_authorized_write(
                file_path,
                tool="delphi_file",
                operation="encode",
            )
            _replace_with_temp(temp_write_path, file_path)
        except UnicodeEncodeError:
            if os.path.exists(temp_write_path):
                try:
                    os.remove(temp_write_path)
                except OSError:
                    pass
            # Roll back backup and cancel conversion
            if bak_path:
                try:
                    os.remove(bak_path)
                except OSError:
                    pass
            return _wrap_error(f"Failed to write encoding '{target_enc}': there are characters that cannot be encoded")
        except Exception as e:
            if os.path.exists(temp_write_path):
                try:
                    os.remove(temp_write_path)
                except OSError:
                    pass
            if bak_path:
                try:
                    os.remove(bak_path)
                except OSError:
                    pass
            return _wrap_error(f"Failed to write file: {e}")
        finally:
            if os.path.exists(temp_write_path):
                try:
                    os.remove(temp_write_path)
                except OSError:
                    pass

        # Mark dirty (line numbers unchanged but content bytes changed, prevents AI from continuing based on stale content)
        _mark_dirty(file_path)

        # Build return message
        is_bom = target_enc == "utf-8-sig" or "utf-16" in target_enc
        parts = [
            f"converted: {os.path.basename(file_path)}",
            f"from: {read_enc} → to: {target_enc}",
            f"size: {original_size} bytes → {new_size} bytes",
        ]
        if is_bom:
            parts.append("BOM: yes")
        if bak_path:
            parts.append(f"backup: __history\\{os.path.basename(bak_path)}")
        if read_enc != detected_enc:
            parts.append(f"note: detected encoding was {detected_enc}")

        return {
            "status": "success",
            "message": ", ".join(parts),
            "original_encoding": read_enc,
            "new_encoding": target_enc,
            "original_size": original_size,
            "new_size": new_size,
        }
    finally:
        if dry_run:
            _release_read_lock(file_path)
        else:
            _release_write_lock(file_path)


async def handle_backup(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle backup action — backup management.

    Sub-actions:
      create  create backup (default)
      list    list all backup versions
      restore restore a specified version
    """
    file_path = arguments.get("file_path")
    backup_action = arguments.get("backup_action", "create")
    version = arguments.get("version")

    if not file_path:
        return _wrap_error("Please provide the file_path parameter")

    path_err = _validate_path(file_path, arguments.get("project_path"))
    if path_err:
        return _wrap_error("Path security validation failed: %s" % path_err)

    if backup_action == "create":
        lock_err = _acquire_read_lock(file_path)
        if lock_err:
            return _wrap_error(lock_err)
        try:
            bp = create_backup(file_path)
        finally:
            _release_read_lock(file_path)
        if bp:
            return {"status": "success", "message": f"Backup created: {bp}"}
        return _wrap_error(f"Backup failed: {file_path}")

    elif backup_action == "list":
        backups = list_backups(file_path)
        if not backups:
            return {"status": "success", "message": f"No backup files found for {file_path}"}
        lines = [f"File: {file_path}", f"Backup count: {len(backups)}", ""]
        for b in backups:
            from datetime import datetime
            ts = datetime.fromtimestamp(b["mtime"]).strftime("%Y-%m-%d %H:%M:%S")
            size_kb = b["size"] / 1024
            lines.append(f"  v{b['version']}: {ts}  ({size_kb:.1f} KB)  {b['path']}")
        return {"status": "success", "message": "\n".join(lines)}

    elif backup_action == "restore":
        lock_err = _acquire_write_lock(file_path)
        if lock_err:
            return _wrap_error(lock_err)
        try:
            record_authorized_write(
                file_path,
                tool="delphi_file",
                operation="backup_restore",
            )
            bp = restore_backup(file_path, version=version)
        finally:
            _release_write_lock(file_path)
        if bp:
            ver_str = f"v{version}" if version else "latest version"
            return {"status": "success", "message": f"Restored from {ver_str}: {bp}"}
        return _wrap_error(f"Restore failed: {file_path}")

    else:
        return _wrap_error(f"Unknown backup_action: {backup_action}")


# ============================================================
# uses clause operations
# ============================================================

# Regex matching the uses clause: uses Unit1, Unit2; may span multiple lines
# Strip Pascal comments first (braces { } + paren-star (* *)), to avoid ';' inside comments interfering with matching
# Capture groups: (1) uses keyword (2) entire unit list (3) semicolon
_USES_RE = re.compile(
    r'\b(uses)\b\s+(.*?)\s*(;)',
    re.DOTALL | re.IGNORECASE,
)

# Regex matching Pascal comments: braces { ... } (including $ conditional compilation directives) and paren-star (* ... *)
_PASCAL_COMMENTS_RE = re.compile(r'\{[^}]*\}|\(\*.*?\*\)', re.DOTALL)


def _strip_comments_with_offset_map(text: str) -> tuple:
    """Strip Pascal comments (braces + paren-star), building a stripped→original offset map.

    Returns (stripped_text, offset_map):
      - stripped_text: text with comments stripped
      - offset_map: list, length = len(stripped_text) + 1 (including exclusive end sentinel)
        offset_map[i] = position of the corresponding character in the original text

    The offset map maps positions found in stripped text back to original text positions,
    preventing slice misalignment that could corrupt the file when comments/compiler directives precede the uses clause.
    """
    offset_map = []
    stripped_segments = []
    pos = 0  # current position in the original text

    for match in _PASCAL_COMMENTS_RE.finditer(text):
        # Keep the text segment before the comment, recording the original position of each character
        segment = text[pos:match.start()]
        if segment:
            offset_map.extend(range(pos, pos + len(segment)))
            stripped_segments.append(segment)
        pos = match.end()

    # Keep the final text segment
    segment = text[pos:]
    if segment:
        offset_map.extend(range(pos, pos + len(segment)))
        stripped_segments.append(segment)

    # Sentinel: exclusive end position maps to the end of the original text
    offset_map.append(len(text))

    stripped_text = ''.join(stripped_segments)
    return (stripped_text, offset_map)


def _find_uses_section(text: str, section: str) -> Optional[tuple]:
    """Find the uses clause in the specified section (interface/implementation).

    Strip Pascal comments (braces + paren-star) before searching, to avoid ';' inside comments interfering with matching.
    Returned offsets are mapped back to the original text via offset_map, ensuring correct slicing.

    Returns a (uses_start, uses_end, units_text) tuple, or None.
    uses_start/uses_end are offsets based on the original text (mapped back from stripped to original).
    """
    section_lower = section.lower()

    # Strip comments, build offset map (stripped position → original position)
    stripped, offset_map = _strip_comments_with_offset_map(text)

    if section_lower == "interface":
        impl_pos = re.search(r'\bimplementation\b', stripped, re.IGNORECASE)
        end = impl_pos.start() if impl_pos else len(stripped)
        header = re.search(r'\b(?:unit|program|library)\b', stripped[:end], re.IGNORECASE)
        start = header.end() if header else 0
        chunk = stripped[start:end]
        match = _USES_RE.search(chunk)
        if match:
            s_stripped = match.start() + start
            e_stripped = match.end() + start
            # Map back to original text positions via offset_map
            s_original = offset_map[s_stripped]
            e_original = offset_map[e_stripped]
            return (s_original, e_original, match.group(2))
        return None

    elif section_lower == "implementation":
        impl_pos = re.search(r'\bimplementation\b', stripped, re.IGNORECASE)
        if not impl_pos:
            return None
        start = impl_pos.end()
        chunk = stripped[start:]
        match = _USES_RE.search(chunk)
        if match:
            s_stripped = match.start() + start
            e_stripped = match.end() + start
            # Map back to original text positions via offset_map
            s_original = offset_map[s_stripped]
            e_original = offset_map[e_stripped]
            return (s_original, e_original, match.group(2))
        return None

    return None


def _parse_units_from_uses(units_text: str) -> List[str]:
    """Parse individual unit entries from the unit list text of a uses clause.

    Each entry retains the 'in ...' part, e.g. "Unit1 in 'Unit1.pas'".
    """
    flat = units_text.replace('\r\n', ' ').replace('\n', ' ')
    parts = [p.strip() for p in flat.split(',') if p.strip()]
    return parts


def _build_uses_text(unit_names: List[str], original_text: str) -> str:
    """Rebuild uses clause text from a list of unit names, preserving the original line-ending style.
    If the original was a single line, keep it a single line; if it spans multiple lines, one unit per line."""
    line_ending = '\r\n' if '\r\n' in original_text else '\n'
    has_multiline = '\n' in original_text.strip()

    if has_multiline and len(unit_names) > 1:
        # Multi-line format: one unit per line, 2-space indent, comma at end of line
        lines = []
        for i, name in enumerate(unit_names):
            if i < len(unit_names) - 1:
                lines.append(f"  {name},{line_ending}")
            else:
                lines.append(f"  {name}")
        return ''.join(lines)
    else:
        # Single-line format
        return ', '.join(unit_names)


def _is_comment_line(line: str, in_block_comment: bool) -> tuple[bool, bool]:
    """Detect whether a line is a comment line, returning (is_comment, still_in_block).
    
    Supports Delphi comment formats:
    - // line comments
    - { } block comments
    - (* *) block comments
    
    Rules:
    - Line entirely inside a block comment → comment line
    - Line starts with // → comment line
    - Line starts with { or (* (and is not a compiler directive), and the remainder is also comment or empty → comment line
    - Code line containing a comment → code line
    """
    stripped = line.strip()
    
    # If currently inside a block comment
    if in_block_comment:
        # Check whether the block comment ends
        if '*)' in stripped:
            idx = stripped.find('*)')
            before = stripped[:idx].strip()
            after = stripped[idx + 2:].strip()
            if before:
                return False, False
            # Check whether the remainder is also a comment or empty
            if after and not after.startswith('//'):
                return False, False
            return True, False
        if '}' in stripped:
            idx = stripped.find('}')
            before = stripped[:idx].strip()
            after = stripped[idx + 1:].strip()
            if before:
                return False, False
            # Check whether the remainder is also a comment or empty
            if after and not after.startswith('//'):
                return False, False
            return True, False
        return True, True
    
    # Check for line comment
    if stripped.startswith('//'):
        return True, False
    
    # Check for block comment start
    in_block = False
    if stripped.startswith('{'):
        # Check whether it is a compiler directive (e.g. {$IFDEF})
        if len(stripped) > 1 and stripped[1] == '$':
            return False, False
        in_block = True
        # Check whether it ends on the same line
        if '}' in stripped[1:]:
            in_block = False
            idx = stripped.find('}', 1)
            after = stripped[idx + 1:].strip()
            # Check whether the remainder is also a comment or empty
            if after and not after.startswith('//'):
                return False, False
            return True, False
        return True, True
    
    if stripped.startswith('(*'):
        in_block = True
        # Check whether it ends on the same line
        if '*)' in stripped[2:]:
            in_block = False
            idx = stripped.find('*)', 2)
            after = stripped[idx + 2:].strip()
            # Check whether the remainder is also a comment or empty
            if after and not after.startswith('//'):
                return False, False
            return True, False
        return True, True
    
    if in_block:
        return True, True
    
    return False, False


def _count_lines(content: str, exclude_blank: bool = False, exclude_comments: bool = False) -> Dict[str, int]:
    """Count code lines.
    
    Args:
        content: file content
        exclude_blank: whether to exclude blank lines
        exclude_comments: whether to exclude comment lines
    
    Returns:
        Dictionary containing the statistics
    """
    lines = content.splitlines()
    total = len(lines)
    blank = 0
    comment = 0
    code = 0
    in_block_comment = False
    
    for line in lines:
        is_blank = not line.strip()
        is_comment, in_block_comment = _is_comment_line(line, in_block_comment)
        
        if is_blank:
            blank += 1
        elif is_comment:
            comment += 1
        else:
            code += 1
    
    # Compute actual line count
    actual = total
    if exclude_blank:
        actual -= blank
    if exclude_comments:
        actual -= comment
    
    return {
        "total": total,
        "blank": blank,
        "comment": comment,
        "code": code,
        "actual": actual
    }


_NAMESPACE_PRIORITY: dict[str, int] = {
    # Group 0 — implicit always-first
    # Group 1 — System.* (fundamental RTL)
    "system": 10,
    # Group 2 — WinAPI
    "winapi": 20,
    "wintypes": 20,
    "winprocs": 20,
    # Group 3 — VCL
    "vcl": 30,
    # Group 4 — Data
    "data": 40,
    "datasnap": 41,
    # Group 5 — Web/XML/Soap
    "web": 50,
    "xml": 51,
    "soap": 52,
    # Group 6 — FireDAC
    "firedac": 60,
    # Group 7 — REST
    "rest": 70,
    # Group 8 — Everything else
}

_RTL_CORE = {"system", "sysinit", "sysutils", "classes", "types", "variants", "typinfo", "rtlconsts"}


def _uses_sort_key(unit_name: str) -> tuple:
    """Returns a sort key for Delphi uses clause ordering.

    Follows Delphi convention: System.* → Winapi.* → Vcl.* → Data.* → others.
    Within each group, units sort alphabetically by short name.
    """
    name = unit_name.strip().lower()
    # Strip 'in' clause if present (e.g., "Unit1 in 'Unit1.pas'")
    in_match = re.match(r"(\S+)\s+in\s+", name)
    if in_match:
        name = in_match.group(1)

    parts = name.split(".")
    if len(parts) == 1:
        # No namespace: bare unit name
        if name in _RTL_CORE:
            group = 0  # System/SysInit etc → absolute first
        else:
            group = 100  # Unknown bare unit → after all namespaced
        return (group, parts[0], unit_name)
    else:
        ns = parts[0]
        group = _NAMESPACE_PRIORITY.get(ns, 99)
        return (group, parts[-1], parts[0])


def _uses_group(unit_name: str) -> int:
    """Return namespace group number for a unit name.
    
    Lower number = earlier in uses clause.
    Used by handle_uses to insert new units at the correct position
    without reordering existing units.
    """
    name = unit_name.strip().lower()
    in_match = re.match(r"(\S+)\s+in\s+", name)
    if in_match:
        name = in_match.group(1)
    parts = name.split(".")
    if len(parts) == 1:
        if name in _RTL_CORE:
            return 0
        return 100
    ns = parts[0]
    return _NAMESPACE_PRIORITY.get(ns, 99)


def _uses_insert_position(existing: List[str], new_unit: str) -> int:
    """Find the insertion index for new_unit so it stays in namespace group order.
    
    Keeps existing units in their original relative order.
    Only places new_unit at the boundary between its namespace group
    and the next group.
    """
    new_group = _uses_group(new_unit)
    for i, unit in enumerate(existing):
        if _uses_group(unit) > new_group:
            return i
    return len(existing)
    """Rebuild uses clause text from a list of unit names, preserving the original line-ending style.

    If the original was a single line, keep it a single line; if it spans multiple lines, one unit per line.
    """
    line_ending = '\r\n' if '\r\n' in original_text else '\n'
    has_multiline = '\n' in original_text.strip()

    if has_multiline and len(unit_names) > 1:
        # Multi-line format: one unit per line, 2-space indent, comma at end of line
        lines = []
        for i, name in enumerate(unit_names):
            if i < len(unit_names) - 1:
                lines.append(f"  {name},{line_ending}")
            else:
                lines.append(f"  {name}")
        return ''.join(lines)
    else:
        # Single-line format
        return ', '.join(unit_names)

async def handle_uses(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle the uses action — add/remove units in the uses clause.

    Parameters:
      file_path: file path (.pas/.dpr/.dpk)
      uses_action: "add" or "remove"
      unit_name: unit name (e.g. "Vcl.Dialogs"), may include namespace
      uses_section: "interface" or "implementation" (default "interface")
    """
    file_path = arguments.get("file_path")
    uses_action = arguments.get("uses_action", "add")
    unit_name = arguments.get("unit_name", "")
    uses_section = arguments.get("uses_section", "interface")

    if not file_path:
        return _wrap_error("Please provide the file_path parameter")
    if not unit_name:
        return _wrap_error("Please provide the unit_name parameter")

    path_err = _validate_path(file_path, arguments.get("project_path"))
    if path_err:
        return _wrap_error("Path security validation failed: %s" % path_err)
    if uses_action not in ("add", "remove"):
        return _wrap_error("uses_action must be 'add' or 'remove'")

    if not os.path.isfile(file_path):
        return _wrap_error(f"File does not exist: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()
    if ext not in ('.pas', '.dpr', '.dpk', '.inc'):
        return _wrap_error(f"uses operation only supports .pas/.dpr/.dpk/.inc files, {ext} is not supported")

    # Acquire write permission (read+write mutually exclusive)
    lock_err = _acquire_write_lock(file_path)
    if lock_err:
        return _wrap_error(lock_err)
    try:
        # Read the file (always read with the actually detected encoding to avoid garbling; the write encoding is decided by the encoding parameter)
        encoding = arguments.get("encoding", "auto")
        detected_enc = detect_encoding(file_path)
        if encoding == "auto":
            read_enc = detected_enc
            write_enc = detected_enc
        else:
            read_enc = detected_enc
            if _is_encoding_compatible(encoding, detected_enc):
                write_enc = detected_enc
            else:
                write_enc = encoding

        with open(file_path, 'r', encoding=read_enc, newline='',
                  buffering=BUFFER_SIZE_1MB) as f:
            text = f.read()

        # Find the uses clause
        result = _find_uses_section(text, uses_section)
        if not result:
            section_hint = f"{uses_section} section"
            return _wrap_error(
                f"No uses clause found in {section_hint}. "
                "If the file is a new unit, use the write action to write the complete unit structure first"
            )

        uses_start, uses_end, units_text = result
        existing_units = _parse_units_from_uses(units_text)

        # Check whether the unit already exists / does not exist
        unit_name_stripped = unit_name.strip()

        # Extract unit name (without the 'in' clause) for comparison
        def _get_unit_name(entry: str) -> str:
            in_match = re.match(r"(\S+)\s+in\s+", entry, re.IGNORECASE)
            return in_match.group(1) if in_match else entry

        def _get_short_name(name: str) -> str:
            """Extract the short name (strip the namespace prefix), e.g. 'Vcl.Forms' → 'Forms'"""
            return name.rsplit('.', 1)[-1]

        existing_names = [_get_unit_name(e) for e in existing_units]
        existing_names_lower = [n.lower() for n in existing_names]
        unit_name_lower = unit_name_stripped.lower()

        if uses_action == "add":
            if unit_name_lower in existing_names_lower:
                return {"status": "success", "message": f"{unit_name_stripped} is already in {uses_section} uses, no need to add"}
            # Check namespace prefix conflict: only treat as a conflict when the short names match and at least one side has no namespace
            # Forms ↔ Vcl.Forms conflict, Vcl.Forms ↔ FMX.Forms do not (different units)
            new_short = _get_short_name(unit_name_stripped).lower()
            collision_idx = None
            for i, existing in enumerate(existing_names):
                if existing.lower() != unit_name_lower and _get_short_name(existing).lower() == new_short:
                    # Only a conflict when at least one side is a short name (no namespace)
                    if '.' not in unit_name_stripped or '.' not in existing:
                        collision_idx = i
                        break
            if collision_idx is not None:
                if '.' in unit_name_stripped and '.' not in existing_names[collision_idx]:
                    # Long name replaces short name: Vcl.Forms replaces Forms, keeping the original position
                    new_units = existing_units.copy()
                    new_units[collision_idx] = unit_name_stripped
                else:
                    # Short name conflicts with a long name; if the long name already exists, skip
                    return {"status": "success", "message": f"{unit_name_stripped} has the same short name as existing unit {existing_names[collision_idx]}, treated as the same unit, skipping"}
            else:
                # No conflict, insert by namespace group (do not reorder existing units)
                insert_at = _uses_insert_position(existing_units, unit_name_stripped)
                new_units = existing_units.copy()
                new_units.insert(insert_at, unit_name_stripped)
        else:  # remove
            if unit_name_lower not in existing_names_lower:
                return {"status": "success", "message": f"{unit_name_stripped} is not in {uses_section} uses, no need to remove"}
            new_units = [e for e in existing_units if _get_unit_name(e).lower() != unit_name_lower]

        if not new_units:
            return _wrap_error(f"Removing {unit_name_stripped} would leave the uses clause empty, please use the write action to rewrite the file")

        # Rebuild the uses text
        new_units_text = _build_uses_text(new_units, units_text)
        new_uses_clause = f"uses {new_units_text};"

        # Replace the original uses clause
        new_text = text[:uses_start] + new_uses_clause + text[uses_end:]

        # Write out (using write_enc, may differ from the read encoding = transparent transcoding)
        encoding_fallback = False
        backup_path = None
        backup = arguments.get("backup", True)
        temp_write_path = _make_temp_write_path(file_path)
        try:
            try:
                _write_text_temp(temp_write_path, new_text, write_enc)
            except UnicodeEncodeError:
                logger.warning(f"Writing with encoding {write_enc} failed, falling back to utf-8")
                _write_text_temp(temp_write_path, new_text, "utf-8")
                write_enc = "utf-8"
                encoding_fallback = True

            if backup:
                backup_path = create_backup(file_path)
                if not backup_path:
                    return _wrap_error("Failed to create backup, write cancelled")

            record_authorized_write(
                file_path,
                tool="delphi_file",
                operation="uses",
            )
            _replace_with_temp(temp_write_path, file_path)
        except UnicodeEncodeError:
            return _wrap_error("Failed to write file, write cancelled: encoding conversion failed")
        except Exception as ex:
            return _wrap_error(f"Failed to write file, write cancelled: {ex}")
        finally:
            if os.path.exists(temp_write_path):
                try:
                    os.remove(temp_write_path)
                except OSError:
                    pass

        # Auto format
        fmt_msg = ""
        fmt_warning = ""
        if arguments.get("auto_format", False):
            try:
                formatted, write_enc, fmt_encoding_fallback, _ = await _apply_auto_format_atomically(
                    file_path, write_enc, '\r\n' in text
                )
                if formatted:
                    fmt_msg = ", formatted"
                if fmt_encoding_fallback:
                    encoding_fallback = True
            except Exception as ex:
                logger.warning(f"Formatting after uses operation failed: {ex}")
                fmt_warning = f"⚠ auto_format failed: {ex}"

        # Compute the offset (uses modifications also affect line numbers)
        s_0 = text[:uses_start].count('\n')          # 0-indexed: the line where the uses keyword is located
        uses_old_text = text[uses_start:uses_end]
        removed = uses_old_text.count('\n')           # number of lines occupied by the old uses clause
        inserted = new_uses_clause.count('\n')        # number of lines occupied by the new uses clause
        offset = inserted - removed
        # compute exclusive end: the line after the line containing uses_end
        e_0 = text[:uses_end].count('\n') + 1

        action_desc = "added" if uses_action == "add" else "removed"
        # single-line meta (aligned with read/write, 1-indexed)
        basename = os.path.basename(file_path)
        new_e = e_0 + offset
        parts = [
            f"wrote: {basename}",
            f"action: {action_desc} {unit_name_stripped} in {uses_section}",
            f"uses: {', '.join(new_units)}",
            f"1-indexed [{s_0 + 1}, {e_0}] → [{s_0 + 1}, {new_e}] (offset: {offset:+d})",
            f"encoding: {write_enc}",
        ]
        if backup_path:
            parts.append(f"backup: __history\\{os.path.basename(backup_path)}")
        if fmt_msg:
            parts.append("formatted: yes")
        if fmt_warning:
            parts.append(fmt_warning)
        if encoding_fallback:
            parts.append(f"⚠ fallback: {detected_enc} → utf-8")
        if write_enc != detected_enc and not encoding_fallback:
            parts.append(f"ℹ transcoded: {detected_enc} → {write_enc}")

        # uses operation modified the file → mark dirty
        _mark_dirty(file_path)

        return {"status": "success", "message": ", ".join(parts)}
    finally:
        _release_write_lock(file_path)


async def handle_count_lines(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Count the number of lines in a Delphi file.

    Parameters:
      file_path: file path (.pas/.dpr/.dpk/.inc)
      exclude_blank: whether to exclude blank lines (default false)
      exclude_comments: whether to exclude comment lines (default false)

    Returns:
      A dictionary containing the statistics:
      - total: total line count
      - blank: blank line count
      - comment: comment line count
      - code: code line count (excluding blank and comment lines)
      - actual: actual line count (computed based on the exclusion options)
    """
    file_path = arguments.get("file_path")
    exclude_blank = arguments.get("exclude_blank", False)
    exclude_comments = arguments.get("exclude_comments", False)

    if not file_path:
        return _wrap_error("Please provide the file_path parameter")

    path_err = _validate_path(file_path, arguments.get("project_path"))
    if path_err:
        return _wrap_error("Path security validation failed: %s" % path_err)

    if not os.path.isfile(file_path):
        return _wrap_error(f"File does not exist: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()
    if ext not in ('.pas', '.dpr', '.dpk', '.inc'):
        return _wrap_error(f"count_lines only supports .pas/.dpr/.dpk/.inc files, {ext} is not supported")

    try:
        # Read the file
        detected_enc = detect_encoding(file_path)
        with open(file_path, 'r', encoding=detected_enc, newline='',
                  buffering=BUFFER_SIZE_1MB) as f:
            content = f.read()

        # Count lines
        stats = _count_lines(content, exclude_blank, exclude_comments)

        # Build message
        basename = os.path.basename(file_path)
        parts = [
            f"file: {basename}",
            f"total: {stats['total']}",
            f"blank: {stats['blank']}",
            f"comment: {stats['comment']}",
            f"code: {stats['code']}",
        ]

        if exclude_blank or exclude_comments:
            parts.append(f"actual: {stats['actual']}")
            if exclude_blank:
                parts.append("(excluding blank lines)")
            if exclude_comments:
                parts.append("(excluding comment lines)")

        return {"status": "success", "message": ", ".join(parts), "stats": stats}
    except Exception as ex:
        return _wrap_error(f"Failed to count lines: {ex}")


# ============================================================
# Main entry point
# ============================================================


async def handle_fix_garbled(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fix Chinese garbled text in Delphi files.

    Without a BOM, Delphi interprets UTF-8 Chinese bytes as ANSI/GBK, causing garbled text after compilation.
    This action automatically detects the following garbled patterns and fixes them:

    1. UTF-8 without BOM (Delphi misreads as GBK) → add UTF-8 BOM
    2. U+FFFD replacement character (�) → try to recover the original text from residual GBK bytes
    3. UTF-8 bytes stored as GBK (double encoding) → reverse recovery

    Fix steps:
      1. Create a backup in __history
      2. Scan the file for garbled patterns and locations
      3. Apply the corresponding fix based on the pattern
      4. Return a fix summary

    Args:
        file_path: target file path
        backup: whether to create a backup (default True)
        target_encoding: target encoding (default utf-8-sig, i.e. UTF-8 with BOM)
    """
    import chardet

    file_path = arguments.get("file_path")
    if not file_path:
        return _wrap_error("Please provide the file_path parameter")
    path_err = _validate_path(file_path, arguments.get("project_path"))
    if path_err:
        return _wrap_error("Path security validation failed: %s" % path_err)
    backup = arguments.get("backup", True)
    target_enc = arguments.get("target_encoding", "utf-8-sig")

    # Read the raw bytes
    try:
        with open(file_path, 'rb') as f:
            raw = f.read()
    except FileNotFoundError:
        return _wrap_error(f"File does not exist: {file_path}")
    except PermissionError:
        return _wrap_error(f"No permission to read: {file_path}")

    fixes_applied = []
    original_size = len(raw)

    # ── Check 1: are there U+FFFD replacement characters (\xef\xbf\xbd) ──
    fffd_count = raw.count(b'\xef\xbf\xbd')
    if fffd_count > 0:
        fixes_applied.append(f"Found {fffd_count} U+FFFD replacement characters (�), attempting recovery…")

        # Strategy: remove the FFFD sequences and try to decode the residual bytes as GBK
        # U+FFFD usually appears when invalid bytes are replaced during a "GBK→UTF-8 misread"
        cleaned = raw.replace(b'\xef\xbf\xbd', b'')
        recovered_text = None
        for enc in ['gbk', 'gb18030', 'gb2312']:
            try:
                decoded = cleaned.decode(enc)
                # Check whether the decoded result contains meaningful Chinese (ratio of characters in the 4E00-9FFF range)
                cjk_count = sum(1 for c in decoded if '\u4e00' <= c <= '\u9fff')
                total_cjk = sum(1 for c in decoded if ord(c) > 127)
                if cjk_count > 0 and (total_cjk == 0 or cjk_count / total_cjk > 0.3):
                    recovered_text = decoded
                    fixes_applied.append(f"  Recovered {cjk_count} Chinese characters via {enc}")
                    break
            except:
                continue

        if recovered_text:
            # Re-encode to the target encoding
            raw = recovered_text.encode(target_enc)
            fixes_applied.append(f"  Fixed and re-encoded to {target_enc}")
        else:
            fixes_applied.append(f"  Cannot automatically recover U+FFFD content, skipped")

    # ── Check 2: is it UTF-8 without BOM (Delphi may misread as ANSI) ──
    has_bom = raw[:3] == b'\xef\xbb\xbf'
    is_utf16 = raw[:2] in (b'\xff\xfe', b'\xfe\xff')

    if not has_bom and not is_utf16:
        # Detect encoding
        enc_result = chardet.detect(raw)
        detected_enc = enc_result.get('encoding', '').lower()
        confidence = enc_result.get('confidence', 0)

        if 'utf-8' in detected_enc and confidence > 0.8:
            # Check whether the file contains Chinese
            try:
                text = raw.decode('utf-8')
                has_cjk = any('\u4e00' <= c <= '\u9fff' for c in text)
                if has_cjk:
                    raw = b'\xef\xbb\xbf' + raw
                    fixes_applied.append(
                        f"  Encoding detected as UTF-8 (confidence {confidence:.0%}), contains Chinese, no BOM → added UTF-8 BOM"
                    )
            except UnicodeDecodeError:
                pass

    # ── Check 3: encoding detected as GBK but actually UTF-8 (Delphi saved UTF-8 bytes as ANSI) ──
    if not has_bom and not is_utf16:
        enc_result = chardet.detect(raw)
        detected_enc = enc_result.get('encoding', '').lower()
        confidence = enc_result.get('confidence', 0)

        if detected_enc in ('gbk', 'gb2312', 'gb18030') and confidence > 0.6:
            # Try decoding as UTF-8; if there is meaningful Chinese, it means UTF-8 was mistakenly saved as GBK
            try:
                text_utf8 = raw.decode('utf-8')
                cjk_utf8 = sum(1 for c in text_utf8 if '\u4e00' <= c <= '\u9fff')
                if cjk_utf8 > 0:
                    # Already valid UTF-8, just misdetected as another encoding
                    raw = b'\xef\xbb\xbf' + raw
                    fixes_applied.append(
                        f"  File detected as {detected_enc} but is actually UTF-8 (contains {cjk_utf8} Chinese characters), "
                        f"added UTF-8 BOM to prevent Delphi misreading"
                    )
            except UnicodeDecodeError:
                # Try reverse recovery: if UTF-8 bytes were stored as GBK, a reverse fix is needed
                # i.e. convert the characters read from the current file as GBK back to their original UTF-8 encoding
                pass

    # ── Write the fix result ──
    if not fixes_applied:
        return {
            "status": "success",
            "message": f"No garbled text found: {os.path.basename(file_path)} ({original_size} bytes)"
        }

    # Create backup
    bak_path = None
    if backup:
        lock_err = _acquire_read_lock(file_path)
        if not lock_err:
            try:
                bak_path = create_backup(file_path)
            finally:
                _release_read_lock(file_path)

    # Write back the fixed content
    lock_err = _acquire_write_lock(file_path)
    if lock_err:
        return _wrap_error(lock_err)
    try:
        temp_path = _make_temp_write_path(file_path)
        try:
            with open(temp_path, 'wb') as f:
                f.write(raw)
            record_authorized_write(file_path, tool="delphi_file", operation="fix_garbled")
            _replace_with_temp(temp_path, file_path)
        except Exception as e:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            return _wrap_error(f"Failed to write file: {e}")
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
    finally:
        _release_write_lock(file_path)

    _mark_dirty(file_path)

    summary = "\n".join(fixes_applied)
    return {
        "status": "success",
        "message": (
            f"Fix complete: {os.path.basename(file_path)}\n"
            f"Size: {original_size} → {len(raw)} bytes\n"
            f"{summary}"
        ),
        "fixes": fixes_applied,
    }


# ============================================================
# Grep — regex search/replace
# ============================================================

# single character in /pattern/flags format → re constant
_CHAR_FLAG_MAP: Dict[str, int] = {
    "i": re.IGNORECASE,
    "m": re.MULTILINE,
    "s": re.DOTALL,
}

# Match /pattern/flags format (e.g. /TMyClass/i, /^procedure/m)
_PATTERN_FLAGS_RE = re.compile(r'^/(.+)/([a-z]*)$')


def _parse_inline_flags(pattern_str: str) -> tuple[str, int]:
    """Parse the /pattern/flags inline syntax.

    Returns (actual regex, parsed flags).
    If it does not start with /, return pattern_str unchanged, flags=0.
    """
    m = _PATTERN_FLAGS_RE.match(pattern_str)
    if not m:
        return pattern_str, 0
    inner, flag_str = m.group(1), m.group(2)
    flags = 0
    for ch in flag_str:
        mapped = _CHAR_FLAG_MAP.get(ch)
        if mapped is None:
            if ch != 'g':
                raise ValueError(f"Unsupported flag character: '{ch}' (supported: i/m/s/g)")
            continue
        flags |= mapped
    return inner, flags


def _split_glob_patterns(value: Optional[str]) -> List[str]:
    """Split a user supplied glob list while preserving ordinary patterns."""
    if not value:
        return []
    return [part.strip().replace('\\', '/') for part in re.split(r'[;,]', value)
            if part.strip()]


def _glob_matches(relative_path: str, pattern: str) -> bool:
    """Match slash-normalized relative paths with useful ``**/`` semantics."""
    relative_path = relative_path.replace('\\', '/')
    pattern = pattern.replace('\\', '/')
    if fnmatch.fnmatchcase(relative_path, pattern):
        return True
    if pattern.startswith('**/') and fnmatch.fnmatchcase(relative_path, pattern[3:]):
        return True
    if '/' not in pattern and fnmatch.fnmatchcase(os.path.basename(relative_path), pattern):
        return True
    return False


def _glob_files(
    path: str,
    include: Optional[str] = None,
    exclude: Optional[str] = None,
) -> List[str]:
    """Recursively list files matching glob patterns in a directory.

    Args:
        path: root directory path
        include: glob pattern; defaults to Delphi source files
                 (.pas/.dpr/.dpk/.dfm/.fmx/.inc/.dproj/.groupproj)
        exclude: glob pattern to exclude (optional)

    Returns:
        sorted list of matched absolute paths
    """
    path = os.path.abspath(path)
    if not os.path.isdir(path):
        return []

    if include:
        patterns = _split_glob_patterns(include)
    else:
        patterns = [
            "**/*.pas", "**/*.dpr", "**/*.dpk",
            "**/*.dfm", "**/*.fmx", "**/*.inc", "**/*.dproj", "**/*.groupproj",
        ]
    exclude_patterns = _split_glob_patterns(exclude)
    _skip_dirs = {'.git', '__pycache__', '__history', 'node_modules',
                  '.venv', '.mypy_cache', '.pytest_cache'}
    result: List[str] = []

    # Walk with directory pruning.  glob.glob(root_dir=..., recursive=True)
    # enumerates every entry before filtering, which made a broad pattern
    # freeze the MCP event loop and consumed hundreds of thousands of entries.
    for root, dirs, files in os.walk(path):
        rel_root = os.path.relpath(root, path).replace('\\', '/')
        if rel_root == '.':
            rel_root = ''
        kept_dirs = []
        for directory in dirs:
            if directory in _skip_dirs:
                continue
            rel_dir = '/'.join(part for part in (rel_root, directory) if part)
            if any(_glob_matches(rel_dir + '/sentinel', pattern)
                   or _glob_matches(rel_dir, pattern)
                   for pattern in exclude_patterns):
                continue
            kept_dirs.append(directory)
        dirs[:] = kept_dirs

        for filename in files:
            relative_path = '/'.join(part for part in (rel_root, filename) if part)
            if exclude_patterns and any(_glob_matches(relative_path, pattern)
                                        for pattern in exclude_patterns):
                continue
            if patterns and not any(_glob_matches(relative_path, pattern)
                                    for pattern in patterns):
                continue
            result.append(os.path.join(root, filename))
            if len(result) > MAX_GREP_TARGETS:
                return result
    return sorted(result)


def _resolve_grep_targets(arguments: Dict[str, Any]) -> tuple[Optional[List[str]], Optional[str]]:
    """Parse the grep file_path argument and determine the list of target files to search.

    file_path supports two forms:
      - string: automatically detect whether it is a file or a directory and decide the search mode
      - string array: parse each item (each item may be a file or directory path)

    Relative path resolution:
      - when file_path is relative, first try project_path/workspace_root as the base directory
      - if no base directory is found, fall back to os.path.abspath (server CWD)

    include/exclude only take effect in directory mode (string form that is a directory, or an array containing directories).

    Returns:
        (targets_list, None) or (None, error_message)
    """
    raw = arguments.get("file_path")

    if raw is None:
        # When file_path is not specified, automatically fall back to the project root directory
        base = _resolve_project_path(arguments)
        if base and os.path.isdir(base):
            raw = base
        else:
            return None, "Please provide the file_path parameter (file path, directory path, or path array)"

    # Normalize to a list for processing
    if isinstance(raw, str):
        items = [raw]
    elif isinstance(raw, list):
        if len(raw) == 0:
            return None, "file_path array cannot be empty"
        items = raw
    else:
        return None, "file_path must be a string or a string array"

    # Determine the base directory: used to resolve relative paths
    base_dir = _resolve_project_path(arguments)
    if base_dir:
        base_dir = os.path.abspath(base_dir)
        if not os.path.isdir(base_dir):
            base_dir = None  # fall back to CWD when the base directory is unavailable

    include = arguments.get("include")
    exclude = arguments.get("exclude")
    resolved: List[str] = []
    errors: List[str] = []

    for item in items:
        if not isinstance(item, str) or not item.strip():
            errors.append(f"Invalid path: {item!r}")
            continue

        item_stripped = item.strip()
        # Relative path → preferentially resolve relative to project_path/workspace_root
        if not os.path.isabs(item_stripped) and base_dir:
            abs_path = os.path.normpath(os.path.join(base_dir, item_stripped))
        else:
            abs_path = os.path.abspath(item_stripped)

        if os.path.isfile(abs_path):
            resolved.append(abs_path)
        elif os.path.isdir(abs_path):
            file_list = _glob_files(abs_path, include, exclude)
            if len(file_list) > MAX_GREP_TARGETS:
                return None, (
                    f"grep target limit exceeded ({MAX_GREP_TARGETS} files); "
                    "use a narrower file_path/include pattern or exclude build directories"
                )
            if file_list:
                resolved.extend(file_list)
                if len(resolved) > MAX_GREP_TARGETS:
                    return None, (
                        f"grep target limit exceeded ({MAX_GREP_TARGETS} files); "
                        "use fewer paths or narrower include/exclude patterns"
                    )
            else:
                errors.append(f"No files match under directory '{item}'")
        else:
            errors.append(f"Path '{item}' does not exist or is neither a file nor a directory")

    if errors and not resolved:
        return None, "All paths are invalid: " + "; ".join(errors)

    # Deduplicate (preserve order of first occurrence)
    seen: Set[str] = set()
    deduped: List[str] = []
    for p in resolved:
        if p not in seen:
            seen.add(p)
            deduped.append(p)

    result = deduped
    if errors:
        logger.warning(f"grep: some paths are invalid: {'; '.join(errors)}")

    return result, None


def _grep_search_fulltext(
    file_path: str,
    compiled: re.Pattern,
    content: str,
    filter_compiled: Optional[re.Pattern],
    exclude_compiled: Optional[re.Pattern],
    context: int,
    count: int,
    enc: str,
) -> Dict[str, Any]:
    """
    Full-text search — use re.finditer to match in bulk over the entire content.

    Supports cross-line matching (implemented via the DOTALL/MULTILINE flags when the pattern is compiled).
    Match results are presented by line-number ranges.

    filter/exclude apply to the entire matched text.

    Returns:
        matches: [{L<N> or L<N>*: line_content, ...}, ...] each item is a match group
        output:  human-readable text
    """
    filename = os.path.basename(file_path)
    total = 0
    match_groups: List[Dict[str, str]] = []
    lines = content.splitlines(keepends=True)
    total_lines = len(lines)

    for m in re.finditer(compiled, content):
        matched_text = m.group()

        # filter/exclude are checked against the entire matched text
        if filter_compiled and not filter_compiled.search(matched_text):
            continue
        if exclude_compiled and exclude_compiled.search(matched_text):
            continue

        total += 1
        if total > count:
            total -= 1
            break

        start_line = content[:m.start()].count('\n') + 1
        end_line = content[:m.end()].count('\n') + 1
        start_idx = start_line - 1
        end_idx = end_line - 1

        ctx_start = max(0, start_idx - context)
        ctx_end = min(total_lines, end_idx + context + 1)

        group: Dict[str, str] = {}
        for ci in range(ctx_start, ctx_end):
            key = f"L{ci + 1}" + ("*" if start_idx <= ci <= end_idx else "")
            group[key] = lines[ci].rstrip('\r\n')
        match_groups.append(group)

    # output: human-readable format
    output_parts = [f"File: {filename} (encoding: {enc}, {total} matches total)"]
    for g in match_groups:
        for k, v in g.items():
            output_parts.append(f"  {k}:{v}")
        output_parts.append("")

    if total == 0:
        output_parts.append("  (no matches)")

    output = "\n".join(output_parts)

    return {
        "status": "success",
        "message": f"{filename}: {total} matches",
        "total": total,
        "matches": match_groups,
        "output": output,
    }
def _grep_search(
    file_path: str,
    compiled: re.Pattern,
    lines: List[str],
    filter_compiled: Optional[re.Pattern],
    exclude_compiled: Optional[re.Pattern],
    context: int,
    count: int,
    enc: str,
) -> Dict[str, Any]:
    """
    Performs multi-level regex search line by line on lines.

    Args:
        file_path: File path (used only for output)
        compiled: Compiled main pattern object
        lines: Lines of the file (line endings preserved)
        filter_compiled: Secondary filter pattern (optional; line must also match)
        exclude_compiled: Exclude pattern (optional; line must not match)
        context: Number of context lines (N lines before and after)
        count: Maximum number of results to return
        enc: File encoding

    Returns:
        matches: [{L<N> or L<N>*: line_content, ...}, ...] each item is a match group
        output:  Human-readable text
    """
    filename = os.path.basename(file_path)
    total = 0
    match_groups: List[Dict[str, str]] = []
    total_lines = len(lines)

    for i, line in enumerate(lines):
        line_stripped = line.rstrip('\r\n')
        if not compiled.search(line_stripped):
            continue
        if filter_compiled and not filter_compiled.search(line_stripped):
            continue
        if exclude_compiled and exclude_compiled.search(line_stripped):
            continue

        total += 1
        if total > count:
            total -= 1  # Remove the match count that exceeds limit
            break

        ctx_start = max(0, i - context)
        ctx_end = min(total_lines, i + context + 1)
        group: Dict[str, str] = {}
        for ci in range(ctx_start, ctx_end):
            key = f"L{ci + 1}" + ("*" if ci == i else "")
            group[key] = lines[ci].rstrip('\r\n')
        match_groups.append(group)

    # output: Human-readable format
    output_parts = [f"File: {filename} (encoding: {enc}, total {total} matches)"]
    for g in match_groups:
        for k, v in g.items():
            output_parts.append(f"  {k}:{v}")
        output_parts.append("")

    if total == 0:
        output_parts.append("  (no matches)")

    output = "\n".join(output_parts)

    return {
        "status": "success",
        "message": f"{filename}: {total} matches",
        "total": total,
        "matches": match_groups,
        "output": output,
    }


def _grep_replace(
    file_path: str,
    compiled: re.Pattern,
    replace: str,
    content: str,
    enc: str,
    dry_run: bool,
    use_fulltext: bool = False,
) -> Dict[str, Any]:
    """
    Performs regex replacement on file content.

    Args:
        file_path: File path
        compiled: Compiled pattern
        replace: Replacement text
        content: Original file content
        enc: File encoding
        dry_run: True=preview only, do not write to disk
        use_fulltext: True=full-text replacement (supports cross-line), False=line-by-line replacement

    Returns:
        dry_run=True: {"status": "success", "dry_run": True, "diff": [...], ...}
        dry_run=False: {"status": "success", "replaced": int, ...}
    """
    if use_fulltext:
        # ── Full-text replacement (supports cross-line matching)──
        new_content, replaced_count = compiled.subn(replace, content)

        if replaced_count == 0:
            return {"status": "success", "message": "No matches, no replacements made", "replaced": 0}

        # Collect position info for each match
        change_list = []
        for m in re.finditer(compiled, content):
            start_line = content[:m.start()].count('\n') + 1
            end_line = content[:m.end()].count('\n') + 1
            change_list.append({
                "start_lineno": start_line,
                "end_lineno": end_line,
                "matched": m.group(),
            })

        if dry_run:
            output_parts = [
                f"File: {os.path.basename(file_path)} (encoding: {enc})",
                f"Preview replacement: {replaced_count} occurrences",
            ]
            for c in change_list:
                if c["start_lineno"] == c["end_lineno"]:
                    output_parts.append(f"  Line {c['start_lineno']}: {c['matched']}")
                else:
                    output_parts.append(f"  Line {c['start_lineno']}-{c['end_lineno']}: {c['matched']}")
            output_parts.append("(Preview mode, file not modified. Set dry_run=False to perform actual replacement)")

            return {
                "status": "success",
                "message": f"Preview: will replace {replaced_count} occurrences",
                "dry_run": True,
                "replaced": replaced_count,
                "changes": change_list,
                "output": "\n".join(output_parts),
            }

        # Actual write
        bak_path = None
        lock_err = _acquire_read_lock(file_path)
        if not lock_err:
            try:
                bak_path = create_backup(file_path)
            finally:
                _release_read_lock(file_path)

        lock_err = _acquire_write_lock(file_path)
        if lock_err:
            return _wrap_error(lock_err)
        try:
            temp_path = _make_temp_write_path(file_path)
            try:
                _write_text_temp(temp_path, new_content, enc)
                record_authorized_write(file_path, tool="delphi_file", operation="grep_replace")
                _replace_with_temp(temp_path, file_path)
            except Exception as e:
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except OSError:
                        pass
                return _wrap_error(f"Failed to write file: {e}")
            finally:
                if os.path.exists(temp_path):
                    try:
                        os.remove(temp_path)
                    except OSError:
                        pass
        finally:
            _release_write_lock(file_path)

        _mark_dirty(file_path)
        return {
            "status": "success",
            "message": (
                f"Replacement complete: {os.path.basename(file_path)}\n"
                f"Replaced {replaced_count} occurrences in total\n"
                f"Encoding: {enc}"
                + (f"\nBackup: {os.path.basename(bak_path)}" if bak_path else "")
            ),
            "replaced": replaced_count,
            "changes": change_list,
        }

    # ── Line-by-line replacement (backward compatible)──
    lines = content.splitlines(keepends=True)
    replaced_count = 0
    change_list: List[Dict[str, Any]] = []

    for i, line in enumerate(lines):
        new_line, n = compiled.subn(replace, line)
        if n > 0:
            replaced_count += n
            change_list.append({
                "lineno": i + 1,
                "old": line.rstrip('\r\n'),
                "new": new_line.rstrip('\r\n'),
                "count": n,
            })
            lines[i] = new_line

    if replaced_count == 0:
        return {
            "status": "success",
            "message": "No matches, no replacements made",
            "replaced": 0,
        }

    if dry_run:
        # Preview only
        diff_lines = []
        for ch in change_list:
            diff_lines.append(f"  Line {ch['lineno']}: {ch['old']}")
            diff_lines.append(f"       → {ch['new']}")
            diff_lines.append("")
        output = (
            f"File: {os.path.basename(file_path)} (encoding: {enc})\n"
            f"Preview replacement: {replaced_count} occurrences\n"
        )
        if diff_lines:
            output += "\n".join(diff_lines)
        output += "\n(Preview mode, file not modified. Set dry_run=False to perform actual replacement)"

        return {
            "status": "success",
            "message": f"Preview: will replace {replaced_count} occurrences",
            "dry_run": True,
            "replaced": replaced_count,
            "changes": change_list,
            "output": output,
        }

    # ── Actual write ──
    # Backup
    bak_path = None
    lock_err = _acquire_read_lock(file_path)
    if not lock_err:
        try:
            bak_path = create_backup(file_path)
        finally:
            _release_read_lock(file_path)

    # Write
    new_content = "".join(lines)
    lock_err = _acquire_write_lock(file_path)
    if lock_err:
        return _wrap_error(lock_err)
    try:
        temp_path = _make_temp_write_path(file_path)
        try:
            _write_text_temp(temp_path, new_content, enc)
            record_authorized_write(file_path, tool="delphi_file", operation="grep_replace")
            _replace_with_temp(temp_path, file_path)
        except Exception as e:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            return _wrap_error(f"Failed to write file: {e}")
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
    finally:
        _release_write_lock(file_path)

    _mark_dirty(file_path)

    changed_lines = len(change_list)
    return {
        "status": "success",
        "message": (
            f"Replacement complete: {os.path.basename(file_path)}\n"
            f"Replaced {replaced_count} occurrences in total ({changed_lines} lines)\n"
            f"Encoding: {enc}"
            + (f"\nBackup: {os.path.basename(bak_path)}" if bak_path else "")
        ),
        "replaced": replaced_count,
        "changed_lines": changed_lines,
        "changes": change_list,
    }


def _format_batch_output(
    files_result: Dict[str, Dict[str, Any]],
    total_matches: int,
    file_count: int,
    replace: Optional[str] = None,
) -> str:
    """Formats human-readable output for batch grep."""
    if replace is not None:
        parts = [f"Batch replace: replaced {total_matches} occurrences in {file_count} files" if file_count > 0
                 else "Batch replace: no matches, no replacements made"]
    else:
        parts = [f"Batch search: found {total_matches} matches in {file_count} files" if file_count > 0
                 else "Batch search: no matches"]
    for fname, fresult in files_result.items():
        parts.append(f"")
        parts.append(f"File: {fname}")
        if replace is not None:
            parts.append(f"  Replaced: {fresult.get('replaced', 0)} occurrences")
        else:
            parts.append(f"  Matches: {fresult.get('total', 0)} occurrences")
            for g in fresult.get("matches", []):
                for k, v in g.items():
                    if k == "_pattern":
                        continue
                    parts.append(f"  {k}:{v}")
                parts.append("")
    return "\n".join(parts)


def _grep_single_file(
    file_path: str,
    compiled_patterns: List[re.Pattern],
    filter_compiled: Optional[re.Pattern],
    exclude_compiled: Optional[re.Pattern],
    replace: Optional[str],
    dry_run: bool,
    context: int,
    count: int,
    use_fulltext: bool,
    project_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Performs grep search or replacement on a single file.

    With a single pattern, behavior is fully identical to the old version (backward compatible).
    With multiple patterns, searches are combined with OR logic, and matches are tagged with the _pattern field.
    """
    # ── Check .dfm / .fmx ──
    if _is_dfm_file(file_path):
        return {"status": "skipped", "message": f"grep does not support DFM/FMX files: {file_path}"}

    path_err = _validate_path(file_path, project_path)
    if path_err:
        return _wrap_error(f"Path safety validation failed: {path_err}")

    # ── Read file ──
    enc = detect_encoding(file_path)
    if not enc:
        enc = "utf-8"
    try:
        with open(file_path, 'r', encoding=enc, errors='replace') as f:
            content = f.read()
    except FileNotFoundError:
        return _wrap_error(f"File does not exist: {file_path}")
    except PermissionError:
        return _wrap_error(f"No permission to read: {file_path}")
    except Exception as e:
        return _wrap_error(f"Failed to read file: {e}")

    # ── Single pattern — original path (fully backward compatible) ──
    if len(compiled_patterns) == 1:
        compiled = compiled_patterns[0]
        if replace is not None:
            return _grep_replace(file_path, compiled, replace, content, enc, dry_run,
                                 use_fulltext=use_fulltext)
        elif use_fulltext:
            return _grep_search_fulltext(file_path, compiled, content,
                                         filter_compiled, exclude_compiled, context, count, enc)
        else:
            lines = content.splitlines(keepends=True)
            return _grep_search(file_path, compiled, lines,
                                filter_compiled, exclude_compiled, context, count, enc)

    # ── Multi-pattern replacement ──
    if replace is not None:
        if dry_run:
            # Preview: simulate replacement for all patterns on the original content
            preview_content = content
            total_replaced = 0
            all_changes = []
            for compiled in compiled_patterns:
                result = _grep_replace(file_path, compiled, replace, preview_content, enc,
                                       dry_run=True, use_fulltext=use_fulltext)
                n = result.get("replaced", 0)
                total_replaced += n
                if result.get("changes"):
                    for c in result["changes"]:
                        c["_pattern"] = compiled.pattern
                    all_changes.extend(result["changes"])
                if n > 0:
                    preview_content = compiled.sub(replace, preview_content)

            filename = os.path.basename(file_path)
            return {
                "status": "success",
                "message": f"{filename}: preview replace {total_replaced} occurrences ({len(compiled_patterns)} patterns)",
                "replaced": total_replaced,
                "dry_run": True,
                "changes": all_changes,
            }
        else:
            # Actual replace: write to disk pattern by pattern
            total_replaced = 0
            all_changes = []
            for compiled in compiled_patterns:
                re_read_enc = detect_encoding(file_path)
                if not re_read_enc:
                    re_read_enc = "utf-8"
                try:
                    with open(file_path, 'r', encoding=re_read_enc, errors='replace') as f:
                        current_content = f.read()
                except Exception:
                    current_content = ""
                result = _grep_replace(file_path, compiled, replace, current_content, enc,
                                       dry_run=False, use_fulltext=use_fulltext)
                n = result.get("replaced", 0)
                total_replaced += n
                if result.get("changes"):
                    all_changes.extend(result["changes"])

            filename = os.path.basename(file_path)
            return {
                "status": "success",
                "message": f"{filename}: replacement complete, {total_replaced} occurrences total ({len(compiled_patterns)} patterns)",
                "replaced": total_replaced,
                "changes": all_changes,
            }

    # ── Multi-pattern search ──
    all_matches: List[Dict[str, str]] = []
    total = 0

    for compiled in compiled_patterns:
        remaining = max(1, count - total)
        if use_fulltext:
            result = _grep_search_fulltext(file_path, compiled, content,
                                           filter_compiled, exclude_compiled, context, remaining, enc)
        else:
            lines = content.splitlines(keepends=True)
            result = _grep_search(file_path, compiled, lines,
                                  filter_compiled, exclude_compiled, context, remaining, enc)

        n = result.get("total", 0)
        if n > 0:
            for m in result.get("matches", []):
                m["_pattern"] = compiled.pattern
            all_matches.extend(result.get("matches", []))
            total += n

    # Sort by first line number
    def _sort_key(match_group: Dict[str, str]) -> int:
        for k in match_group:
            if k.startswith("L") and not k.endswith("*"):
                return int(k[1:])
        return 0
    all_matches.sort(key=_sort_key)

    filename = os.path.basename(file_path)
    pattern_count = len(compiled_patterns)
    output_parts = [f"File: {filename} (encoding: {enc}, {total} matches, {pattern_count} patterns)"]
    for g in all_matches:
        for k, v in g.items():
            if k == "_pattern":
                continue
            output_parts.append(f"  {k}:{v}")
        output_parts.append("")
    if total == 0:
        output_parts.append("  (no matches)")

    return {
        "status": "success",
        "message": f"{filename}: {total} matches",
        "total": total,
        "matches": all_matches,
        "output": "\n".join(output_parts),
    }


def _grep_batch(
    targets: List[str],
    compiled_patterns: List[re.Pattern],
    filter_compiled: Optional[re.Pattern],
    exclude_compiled: Optional[re.Pattern],
    replace: Optional[str],
    dry_run: bool,
    context: int,
    count_per_file: int,
    use_fulltext: bool,
    project_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Performs grep search or replacement in batch on multiple files."""
    files_result: Dict[str, Dict[str, Any]] = {}
    total_matches = 0
    file_count = 0
    errors: List[str] = []

    for file_path in targets:
        result = _grep_single_file(
            file_path, compiled_patterns, filter_compiled, exclude_compiled,
            replace, dry_run, context, count_per_file, use_fulltext, project_path,
        )

        status = result.get("status")
        if status in ("error", "failed"):
            errors.append(f"{file_path}: {result['message']}")
            continue
        elif status == "skipped":
            continue  # DFM/FMX files silently skipped

        rel_path = os.path.relpath(file_path)

        if replace is not None:
            replaced = result.get("replaced", 0)
            if replaced > 0 or not dry_run:
                files_result[rel_path] = {
                    "replaced": replaced,
                    "changes": result.get("changes", []),
                }
                if replaced > 0:
                    total_matches += replaced
                file_count += 1
        else:
            file_total = result.get("total", 0)
            if file_total > 0:
                files_result[rel_path] = {
                    "total": file_total,
                    "matches": result.get("matches", []),
                }
                total_matches += file_total
                file_count += 1

    output = _format_batch_output(files_result, total_matches, file_count, replace)

    message_parts = []
    if replace is not None:
        if total_matches > 0:
            message_parts.append(f"Replaced {total_matches} occurrences in {file_count} files")
        else:
            message_parts.append("No matches, no replacements made")
    else:
        message_parts.append(f"Found {total_matches} matches in {file_count} files")
    if errors:
        message_parts.append(f"\n{len(errors)} files failed to read")

    return {
        "status": "success" if not errors or file_count > 0 else "error",
        "message": "; ".join(message_parts),
        "total_matches": total_matches,
        "file_count": file_count,
        "files": files_result,
        "errors": errors if errors else None,
        "output": output,
    }


async def handle_grep(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handles the grep action — regex search + multi-level filtering + replacement (supports single file/directory/path array).

    file_path supports three forms:
      - File path → single-file search
      - Directory path → recursively search Delphi files under the directory (can be combined with include/exclude)
      - Path array → resolve each item individually; each item can be a file or directory, with deduplicated results

    == Single-file search ==
        delphi_file(
            action="grep",
            file_path="Unit1.pas",
            pattern="/TMyClass\b/i",       # Main search pattern (/expression/flags)
            filter_pattern="TForm",         # Secondary filter (optional, AND)
            exclude_pattern="deprecated",   # Exclude pattern (optional, NOT)
            context=2,                      # Number of context lines (default 0)
            count=200,                      # Maximum number of results to return (default 200)
        )

    == Single-file replacement ==
        delphi_file(
            action="grep",
            file_path="Unit1.pas",
            pattern="/TMyClass\b/i",
            replace="TNewClass",
            dry_run=True,                   # Default True, preview without writing to disk
        )

    == Recursive directory search ==
        delphi_file(
            action="grep",
            file_path="src/",
            include="**/*.pas",   # glob include pattern (optional, defaults to all Delphi files)
            pattern="/TMyClass/i",
            context=1,
        )

    == Multi-pattern search ==
        delphi_file(
            action="grep",
            file_path="Unit1.pas",
            patterns=["/TMyClass/i", "/TSomeClass/"],
        )

    == Path array search ==
        delphi_file(
            action="grep",
            file_path=["Unit1.pas", "src/"],
            pattern="/TMyClass/i",
        )

    flags inline syntax:
        pattern="/TMyClass/im" → /expression/flag characters
        flag characters: i=ignore_case, m=multiline, s=dot_all, g=ignored (Python global by default)
        multiline/dot_all enable full-text search mode, matches can span lines.
        Without flag characters, line-by-line search is kept (backward compatible).
        filter_pattern/exclude_pattern inherit the main pattern's flags, and can also override them with their own inline syntax.

    Multi-level filtering notes:
        Line-by-line mode: pattern + filter_pattern + exclude_pattern apply to the same line
        Full-text mode: pattern + filter_pattern + exclude_pattern apply to the entire matched text
    """
    removed_preview = _reject_removed_preview_argument(arguments)
    if removed_preview:
        return removed_preview

    # ── Parse pattern / patterns ──
    pattern_str = arguments.get("pattern")
    patterns = arguments.get("patterns")

    if not pattern_str and not patterns:
        return _wrap_error("Please provide the pattern (single pattern) or patterns (multiple patterns) argument")
    if pattern_str and patterns:
        return _wrap_error("pattern and patterns cannot be provided at the same time; please choose one")

    # ── Compile patterns ──
    pattern_strings = [pattern_str] if pattern_str else patterns
    compiled_patterns: List[re.Pattern] = []
    inline_flags = 0
    for ps in pattern_strings:
        try:
            inner_pattern, flags = _parse_inline_flags(ps)
        except ValueError as e:
            return _wrap_error(str(e))
        try:
            compiled = re.compile(inner_pattern, flags)
        except re.error as e:
            return _wrap_error(f"pattern regex compilation failed: {e}")
        compiled_patterns.append(compiled)
        inline_flags |= flags

    use_fulltext = bool(inline_flags & (re.MULTILINE | re.DOTALL))

    # ── Compile filter / exclude ──
    # Inherit the union of all pattern flags
    filter_str = arguments.get("filter_pattern")
    filter_compiled: Optional[re.Pattern] = None
    if filter_str:
        try:
            inner_filter, filter_inline = _parse_inline_flags(filter_str)
            filter_compiled = re.compile(inner_filter, inline_flags | filter_inline)
        except re.error as e:
            return _wrap_error(f"filter_pattern regex compilation failed: {e}")

    exclude_str = arguments.get("exclude_pattern")
    exclude_compiled: Optional[re.Pattern] = None
    if exclude_str:
        try:
            inner_exclude, exclude_inline = _parse_inline_flags(exclude_str)
            exclude_compiled = re.compile(inner_exclude, inline_flags | exclude_inline)
        except re.error as e:
            return _wrap_error(f"exclude_pattern regex compilation failed: {e}")

    replace = arguments.get("replace")
    dry_run = arguments.get("dry_run", True)
    if not isinstance(dry_run, bool):
        return _wrap_error("dry_run must be a boolean value")
    context = arguments.get("context", 0)
    if not isinstance(context, int) or context < 0:
        return _wrap_error("context must be a non-negative integer")
    count = arguments.get("count", 200)
    if not isinstance(count, int) or count < 1:
        count = 200
    project_path = arguments.get("project_path")

    # ── Resolve target file list ──
    targets, err = await asyncio.to_thread(_resolve_grep_targets, arguments)
    if err:
        return _wrap_error(err)

    # ── Routing: single file + single pattern → fast path ──
    # Determine from the original input rather than expanded targets; a directory matching only one file must still return the batch-result contract.
    raw_file_path = arguments.get("file_path")
    resolved_input_path: Optional[str] = None
    if isinstance(raw_file_path, str) and raw_file_path.strip():
        raw_file_path = raw_file_path.strip()
        base_dir = _resolve_project_path(arguments)
        if base_dir:
            base_dir = os.path.abspath(base_dir)
            if not os.path.isdir(base_dir):
                base_dir = None
        if not os.path.isabs(raw_file_path) and base_dir:
            resolved_input_path = os.path.normpath(os.path.join(base_dir, raw_file_path))
        else:
            resolved_input_path = os.path.abspath(raw_file_path)

    is_single_file = (
        resolved_input_path is not None
        and len(targets) == 1
        and os.path.normcase(resolved_input_path) == os.path.normcase(targets[0])
        and os.path.isfile(resolved_input_path)
    )
    if is_single_file and len(compiled_patterns) == 1 and pattern_str:
        if _is_dfm_file(targets[0]):
            return _wrap_error("grep does not support DFM/FMX files (possibly binary format); please use the read action to read them")
        return await asyncio.to_thread(
            _grep_single_file,
            targets[0], compiled_patterns, filter_compiled, exclude_compiled,
            replace, dry_run, context, count, use_fulltext, project_path,
        )

    # ── Batch mode (multiple files, recursive directory, or multiple patterns) ──
    return await asyncio.to_thread(
        _grep_batch,
        targets, compiled_patterns, filter_compiled, exclude_compiled,
        replace, dry_run, context, count, use_fulltext, project_path,
    )


def _record_file_write_to_tracker(arguments: dict, result: dict) -> None:
    """Records file write operations to the experience tracker."""
    try:
        from ..services.experience_tracker import get_tracker
        action = arguments.get("action", "")
        file_path = arguments.get("file_path", "")
        success = result.get("status") != "failed"
        result_text = result.get("message", result.get("error", ""))
        tracker = get_tracker()
        tracker.record(
            name="delphi_file",
            arguments={"action": action, "file_path": file_path},
            success=success,
            result_text=str(result_text) if result_text else "",
        )
    except Exception as e:
        logger.debug("Failed to record file write to tracker (does not affect writing): %s", e)


async def handle_file_tool(arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main entry point for file_tool.
    write uses the edits array to handle single or multiple modifications.
    """
    removed_preview = _reject_removed_preview_argument(arguments)
    if removed_preview:
        return removed_preview

    action = arguments.get("action", "read")

    try:
        if action == "read":
            return await handle_read(arguments)
        elif action == "write":
            result = await handle_write(arguments)
            _record_file_write_to_tracker(arguments, result)
            return result
        elif action == "replace":
            result = await handle_replace(arguments)
            _record_file_write_to_tracker(arguments, result)
            return result
        elif action == "insert":
            result = await handle_insert(arguments)
            _record_file_write_to_tracker(arguments, result)
            return result
        elif action == "delete":
            result = await handle_delete(arguments)
            _record_file_write_to_tracker(arguments, result)
            return result
        elif action == "format":
            return await handle_format(arguments)
        elif action == "backup":
            return await handle_backup(arguments)
        elif action == "encode":
            return await handle_encode(arguments)
        elif action == "uses":
            return await handle_uses(arguments)
        elif action == "fix_garbled":
            return await handle_fix_garbled(arguments)
        elif action == "grep":
            return await handle_grep(arguments)
        elif action == "count_lines":
            return await handle_count_lines(arguments)
        else:
            return _wrap_error(f"Unknown action: {action}. Supported actions: read, write, replace, insert, delete, format, backup, encode, uses, fix_garbled, grep, count_lines")
    finally:
        pass  # ensure clean exit even if recording raises