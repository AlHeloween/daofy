"""
DFM format conversion tool — compiles a Delphi converter on demand

Converts between text DFM and binary DFM using the Delphi RTL's
ObjectResourceToText / ObjectTextToResource.

The converter is a temporary .dpr generated on the fly; it is destroyed once it has run.
"""

import os
import re
import sys
import tempfile
import subprocess
import shutil
from typing import Optional, Dict, Any, Set, List, Tuple

from ..constants import (
    TIMEOUT_DFM_COMPILE,
    TIMEOUT_DFM_COMPILER_DISCOVERY,
    TIMEOUT_DFM_CONVERT,
)
from ..utils.logger import get_logger

logger = get_logger(__name__)

# Track temporary directories created by ensure_dfm_text for cleanup by _cleanup_dfm_temp_dirs
_dfm_temp_dirs: Set[str] = set()

# DFM string token regex: matches #XXXX escape sequences or '...' single-quoted strings (handles '' escaping)
# Compiled as a module-level constant to avoid repeated compilation
_DFM_TOKEN_RE = re.compile(r"#[0-9]+|'[^']*(?:''[^']*)*'")


def _cleanup_dfm_temp_dirs():
    """Remove every temp directory left behind by ensure_dfm_text. Called on service shutdown."""
    for d in list(_dfm_temp_dirs):
        try:
            shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass
    _dfm_temp_dirs.clear()


# Global compiler search path cache
_compiler_dcc32_path: Optional[str] = None

# Cached path of compiled dfmconv.exe (avoids recompiling dcc32 on every DFM conversion)
_cached_dfmconv_exe: Optional[str] = None


def set_compiler_path(path: str):
    """Set the dcc32.exe path."""
    global _compiler_dcc32_path
    _compiler_dcc32_path = path


def _get_cached_dfmconv() -> Optional[str]:
    """Return the cached dfmconv.exe path when it exists and is valid, otherwise None."""
    global _cached_dfmconv_exe
    if _cached_dfmconv_exe and os.path.isfile(_cached_dfmconv_exe):
        return _cached_dfmconv_exe
    return None


def _find_dcc32() -> Optional[str]:
    """Locate a usable dcc32.exe."""
    if _compiler_dcc32_path and os.path.isfile(_compiler_dcc32_path):
        return _compiler_dcc32_path

    # Search from PATH
    which_cmd = "where" if sys.platform == "win32" else "which"
    try:
        result = subprocess.run(
            [which_cmd, "dcc32.exe" if sys.platform == "win32" else "dcc32"],
            capture_output=True, text=True, timeout=TIMEOUT_DFM_COMPILER_DISCOVERY,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        )
        if result.returncode == 0:
            path = result.stdout.strip().split('\n')[0].strip()
            if path and os.path.isfile(path):
                return path
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def _dfmconv_dpr(cmd: str, in_file: str, out_file: str) -> str:
    """Build the source of the DFM converter .dpr."""
    # Use raw string to avoid path escaping issues
    return f'''program dfmconv;

{{$APPTYPE CONSOLE}}

uses
  System.Classes,
  System.SysUtils;

var
  ins, outs: TFileStream;
  cmd: string;
  inPath, outPath: string;
begin
  cmd := ParamStr(1);
  inPath := ParamStr(2);
  outPath := ParamStr(3);

  if (cmd = '') or (inPath = '') or (outPath = '') then
  begin
    WriteLn('Usage: dfmconv <to-text|to-binary> <input> <output>');
    Halt(1);
  end;

  ins := TFileStream.Create(inPath, fmOpenRead or fmShareDenyWrite);
  try
    outs := TFileStream.Create(outPath, fmCreate);
    try
      if cmd = 'to-text' then
        ObjectResourceToText(ins, outs)
      else if cmd = 'to-binary' then
        ObjectTextToResource(ins, outs)
      else
      begin
        WriteLn('Unknown command: ', cmd);
        Halt(1);
      end;
    finally
      outs.Free;
    end;
  finally
    ins.Free;
  end;
end.
'''

def _find_library_path(dcc32: str) -> Optional[str]:
    """
    Derive the RTL library path from the dcc32 path.

    Standard Delphi directory layout:
      <root>/bin/dcc32.exe
      <root>/lib/win32/release/  (DCU files)

    Args:
        dcc32: Full path to dcc32.exe

    Returns:
        The library path, or None when it cannot be found
    """
    dcc_dir = os.path.dirname(os.path.abspath(dcc32))
    # Try bin/../lib/win32/release
    root = os.path.dirname(dcc_dir)  # <Studio version>/
    candidates = [
        os.path.join(root, "lib", "win32", "release"),
        os.path.join(root, "lib", "Win32", "Release"),
        os.path.join(root, "lib"),
    ]
    for p in candidates:
        if os.path.isdir(p):
            return p
    return None


def _compile_dfmconv_to(exe_path: str, dcc32: str) -> bool:
    """
    Compile the DFM converter to the given path.

    Args:
        exe_path: Target exe path
        dcc32: dcc32.exe path

    Returns:
        Whether the compilation succeeded
    """
    out_dir = os.path.dirname(exe_path)
    dpr_path = os.path.join(out_dir, "dfmconv.dpr")

    with open(dpr_path, "w", encoding="utf-8") as f:
        f.write(_dfmconv_dpr("to-text", "", ""))

    try:
        lib_path = _find_library_path(dcc32)

        # First try without library path (some environments can find it automatically via registry)
        cmd = [dcc32, dpr_path, f"-E{out_dir}", "-Q", "-B"]
        logger.info(f"Compiling DFM converter: {' '.join(cmd)}")
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=TIMEOUT_DFM_COMPILE,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        )

        # If it fails and a library path is available, retry
        first_error = result.stderr if result.returncode != 0 else None
        if result.returncode != 0 and lib_path:
            cmd2 = [dcc32, dpr_path, f"-E{out_dir}", "-Q", "-B", f"-U{lib_path}"]
            logger.info(f"Retrying DFM converter compilation (with -U): {' '.join(cmd2)}")
            result = subprocess.run(
                cmd2, capture_output=True, text=True, timeout=TIMEOUT_DFM_COMPILE,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            )

        if result.returncode != 0:
            err_detail = result.stderr.strip() or first_error or "unknown error"
            logger.error(f"Failed to compile DFM converter: {err_detail}")
            return False

        if os.path.isfile(exe_path):
            return True
        logger.error(f"Executable not found after compilation: {exe_path}")
        return False
    except subprocess.TimeoutExpired:
        logger.error("DFM converter compilation timed out")
        return False
    except Exception as e:
        logger.error(f"DFM converter compilation exception: {e}")
        return False


def _ensure_dfmconv() -> Optional[str]:
    """
    Ensure the DFM converter is compiled and return the executable path.

    It is compiled and cached on the first call; later calls return the cached path, so the
    compilation is never repeated.

    Returns:
        The dfmconv.exe path, or None on failure
    """
    global _cached_dfmconv_exe

    # 1. Check cache
    cached = _get_cached_dfmconv()
    if cached:
        return cached

    # 2. Find dcc32
    dcc32 = _find_dcc32()
    if not dcc32:
        logger.error("dcc32.exe not found, cannot compile DFM converter")
        return None

    # 3. Compile to a fixed cache path (under system temp, persists for process lifetime)
    cache_dir = os.path.join(tempfile.gettempdir(), "daofy_dfmconv_cache")
    os.makedirs(cache_dir, exist_ok=True)
    exe_path = os.path.join(cache_dir, "dfmconv.exe")

    if _compile_dfmconv_to(exe_path, dcc32):
        _cached_dfmconv_exe = exe_path
        logger.info(f"DFM converter compiled and cached: {exe_path}")
        return exe_path

    return None


def _compile_dfmconv(tmp_dir: str) -> Optional[str]:
    """
    Compile the DFM converter (legacy entry point, delegating to the cache mechanism).

    Args:
        tmp_dir: Temporary directory

    Returns:
        The exe path, or None on failure
    """
    exe_path = _ensure_dfmconv()
    if exe_path:
        return exe_path
    # If caching failed but tmp_dir needs the compilation result (fallback path), try compiling directly to tmp_dir
    dcc32 = _find_dcc32()
    if not dcc32:
        return None
    fallback_exe = os.path.join(tmp_dir, "dfmconv.exe")
    if _compile_dfmconv_to(fallback_exe, dcc32):
        return fallback_exe
    return None


def _run_dfmconv(exe_path: str, cmd: str, in_file: str, out_file: str) -> bool:
    """Run the compiled DFM converter."""
    try:
        result = subprocess.run(
            [exe_path, cmd, in_file, out_file],
            capture_output=True, text=True, timeout=TIMEOUT_DFM_CONVERT,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        )
        if result.returncode != 0:
            logger.error(f"DFM conversion failed ({cmd}): {result.stderr or result.stdout}")
            return False
        return True
    except subprocess.TimeoutExpired:
        logger.error("DFM conversion timed out")
        return False
    except Exception as e:
        logger.error(f"DFM conversion exception: {e}")
        return False


def _detect_dfm_format(file_path: str) -> str:
    """
    Detect the format of a DFM file.

    Args:
        file_path: Path to the .dfm file

    Returns:
        "text" or "binary"

    Raises:
        FileNotFoundError: The file does not exist
        PermissionError: No permission to read it
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"DFM file does not exist: {file_path}")
    try:
        with open(file_path, 'rb') as f:
            header = f.read(32)

        # Text DFM starts with object or inherited (ASCII-readable)
        # Binary DFM usually starts with FF FF FF FF or other non-text markers
        # First remove UTF-8 BOM (EF BB BF) to avoid BOM causing ASCII decoding failure
        if header[:3] == b'\xef\xbb\xbf':
            header = header[3:]
        try:
            text = header.decode('ascii', errors='strict')
            text_stripped = text.strip().lower()
            if text_stripped.startswith('object ') or text_stripped.startswith('inherited '):
                return "text"
            return "binary"
        except (UnicodeDecodeError, ValueError):
            return "binary"
    except (FileNotFoundError, PermissionError):
        raise
    except Exception as e:
        logger.warning(f"Failed to detect DFM format: {e}")
        return "text"  # Conservative default: assume text format when unable to determine


async def convert_dfm(in_file: str, out_file: str, to_text: bool = True) -> Dict[str, Any]:
    """
    Convert a DFM file between the text and binary formats.

    A temporary Delphi converter program is compiled on demand, run, then cleaned up.

    Args:
        in_file: Input file path
        out_file: Output file path
        to_text: True = binary → text, False = text → binary

    Returns:
        {"success": bool, "message": str, "source_format": str, "target_format": str}
    """
    source_fmt = "text"
    target_fmt = "binary"
    if to_text:
        source_fmt = "binary"
        target_fmt = "text"

    if not os.path.isfile(in_file):
        return {
            "success": False,
            "message": f"File does not exist: {in_file}",
            "source_format": source_fmt,
            "target_format": target_fmt
        }

    # Check whether source format matches
    actual_format = _detect_dfm_format(in_file)
    if to_text and actual_format != "binary":
        return {
            "success": False,
            "message": f"File is already in text format; no conversion needed",
            "source_format": "text",
            "target_format": "text"
        }
    if not to_text and actual_format != "text":
        return {
            "success": False,
            "message": f"File is already in binary format; no conversion needed",
            "source_format": "binary",
            "target_format": "binary"
        }

    # Use cached DFM converter (compiled once on first call, reused afterward)
    exe_path = _ensure_dfmconv()
    if not exe_path:
        return {
            "success": False,
            "message": "Failed to compile DFM converter, please check whether the Delphi compiler is available",
            "source_format": source_fmt,
            "target_format": target_fmt
        }

    cmd = "to-text" if to_text else "to-binary"
    ok = _run_dfmconv(exe_path, cmd, in_file, out_file)
    if not ok:
        return {
            "success": False,
            "message": f"DFM conversion execution failed ({cmd})",
            "source_format": source_fmt,
            "target_format": target_fmt
        }

    return {
        "success": True,
        "message": f"DFM conversion succeeded: {source_fmt} → {target_fmt}",
        "source_format": source_fmt,
        "target_format": target_fmt
    }


async def ensure_dfm_text(file_path: str) -> Optional[str]:
    """
    Ensure a DFM file is in text format. If it is binary, convert it to text and return the
    temporary path.

    Args:
        file_path: Path to the .dfm file

    Returns:
        The original path when the file is text;
        the path of a temporary text file when it is binary and the conversion succeeded;
        None on failure, with the temporary directory cleaned up

    Note:
        The returned temporary path stays valid for the process lifetime.
        It is cleaned up on service shutdown, or manually via _cleanup_dfm_temp_dirs().
    """
    fmt = _detect_dfm_format(file_path)
    if fmt == "text":
        return file_path

    # Binary → text
    tmp_dir = tempfile.mkdtemp(prefix="dfmconv_")
    tmp_text = os.path.join(tmp_dir, os.path.basename(file_path) + ".txt")
    result = await convert_dfm(file_path, tmp_text, to_text=True)
    if result["success"]:
        _dfm_temp_dirs.add(tmp_dir)
        return tmp_text
    # Clean up immediately on failure
    shutil.rmtree(tmp_dir, ignore_errors=True)
    return None


async def ensure_dfm_binary(text_path: str, original_binary_path: str) -> bool:
    """
    Convert a text DFM back to binary, replacing the target file.

    Used by the write path: once the agent has modified the text DFM content, it must be
    converted back to the original format (binary) for saving.

    Args:
        text_path: Temporary path of the modified text DFM
        original_binary_path: Original binary DFM path (used as the output target)

    Returns:
        Whether it succeeded
    """
    result = await convert_dfm(text_path, original_binary_path, to_text=False)
    return result["success"]


def escape_dfm_chinese(text: str) -> str:
    """
    Convert non-ASCII characters (such as Chinese) inside single-quoted strings in DFM text
    into #XXXX Delphi escape sequences.

    In Delphi DFM files, non-ASCII characters (such as Chinese) should be represented using
    #XXXX (decimal Unicode) form, rather than writing UTF-8 / GBK encoded text directly, to ensure
    encoding-independent portability.

    Conversion rules:
    - For each non-ASCII character (ord > 127) inside single quotes "'...'", replace it with #XXXX (decimal Unicode code point)
    - Adjacent ASCII characters remain in the single-quoted string
    - Handles '' (doubled single-quote escape) in Delphi strings

    Examples:
        "Caption = '<Chinese text>'"         → "Caption = #36827#24230"
        "Text = 'abc<Chinese text>123'"      → "Text = 'abc'#27979#35797'123'"
        "Hint = 'it''s <Chinese text>'"      → "Hint = 'it''s'#27979#35797"

    Args:
        text: DFM text content

    Returns:
        Converted DFM text
    """
    result: list[str] = []
    i = 0
    length = len(text)

    while i < length:
        ch = text[i]
        if ch == "'":
            # Find the end position of the single-quoted string (handles '' escaping)
            start = i
            i += 1
            chars: list[str] = []
            while i < length:
                if text[i] == "'":
                    if i + 1 < length and text[i + 1] == "'":
                        # Escaped single quote ''
                        chars.append("'")
                        i += 2
                    else:
                        # String end
                        i += 1
                        break
                else:
                    chars.append(text[i])
                    i += 1

            string_content = ''.join(chars)

            # Check whether it contains non-ASCII characters
            if any(ord(c) > 127 for c in string_content):
                # Build replacement result: non-ASCII → #XXXX, ASCII stays in quotes
                # Note: in Delphi single quotes are escaped as ''; restore them when rebuilding the ASCII part
                parts: list[str] = []
                ascii_buf: list[str] = []
                for c in string_content:
                    code = ord(c)
                    if code > 127:
                        if ascii_buf:
                            ascii_str = ''.join(ascii_buf)
                            # Restore Delphi single-quote escaping: ' → ''
                            ascii_str = ascii_str.replace("'", "''")
                            parts.append("'" + ascii_str + "'")
                            ascii_buf = []
                        parts.append(f'#{code}')
                    else:
                        ascii_buf.append(c)
                if ascii_buf:
                    ascii_str = ''.join(ascii_buf)
                    ascii_str = ascii_str.replace("'", "''")
                    parts.append("'" + ascii_str + "'")
                result.append(''.join(parts))
            else:
                # No Chinese, keep as-is
                result.append(text[start:i])
        else:
            result.append(ch)
            i += 1

    return ''.join(result)


def _decode_dfm_tokens(tokens: List[Tuple[int, int, str]]) -> str:
    """Decode a group of adjacent DFM tokens (#XXXX and '...') into a single string.

    Args:
        tokens: List of (start, end, token_text) tuples forming a contiguous run.

    Returns:
        Decoded string with all escape sequences resolved.
    """
    chars: list[str] = []
    for _, _, tok in tokens:
        if tok.startswith('#'):
            # #XXXX → Unicode character
            try:
                code = int(tok[1:])
                chars.append(chr(code))
            except (ValueError, OverflowError):
                # Invalid code point (e.g. #999999999 exceeds Unicode range), keep as-is
                chars.append(tok)
        else:
            # Quoted string: remove outer quotes, resolve '' escapes
            inner = tok[1:-1]
            inner = inner.replace("''", "'")
            chars.extend(inner)
    return ''.join(chars)


def unescape_dfm_chinese(text: str) -> str:
    """Restore #XXXX escape sequences in DFM text to actual characters (only handles strings containing non-ASCII code points).

    Inverse operation of escape_dfm_chinese():
      - When reading: #36827#24230 → '<Chinese text>'
      - When writing: '<Chinese text>' → #36827#24230

    Processing rules:
      - Recognize contiguous #XXXX and '...' token combinations
      - If the decoded result contains non-ASCII characters, merge into a quoted string
      - Pure ASCII is left unchanged (kept as-is)

    Examples:
        "Caption = #36827#24230"            → "Caption = '<Chinese text>'"
        "Text = 'abc'#27979#35797'123'"    → "Text = 'abc<Chinese text>123'"
        "Caption = 'Hello'"                 → "Caption = 'Hello'" (unchanged)

    Args:
        text: DFM text content

    Returns:
        Restored DFM text
    """
    # Use module-level cached regex (matches #XXXX or '...', handles '' escaping)
    token_re = _DFM_TOKEN_RE

    # Find all tokens and their positions
    tokens: List[Tuple[int, int, str]] = []
    for m in token_re.finditer(text):
        tokens.append((m.start(), m.end(), m.group()))

    if not tokens:
        return text

    # Group adjacent tokens (previous token's end == next token's start)
    groups: List[List[Tuple[int, int, str]]] = []
    current_group = [tokens[0]]
    for tok in tokens[1:]:
        if tok[0] == current_group[-1][1]:
            current_group.append(tok)
        else:
            groups.append(current_group)
            current_group = [tok]
    groups.append(current_group)

    # Rebuild text, replacing token groups containing non-ASCII
    result_parts: list[str] = []
    last_end = 0
    for group in groups:
        # Non-token text before this group
        if group[0][0] > last_end:
            result_parts.append(text[last_end:group[0][0]])

        # Decode this group
        decoded = _decode_dfm_tokens(group)
        if any(ord(c) > 127 for c in decoded):
            # Contains non-ASCII → restore to a visible quoted string
            # Re-escape single quotes: ' → '' (required by Delphi string literals)
            decoded_escaped = decoded.replace("'", "''")
            result_parts.append("'" + decoded_escaped + "'")
        else:
            # Pure ASCII → keep as-is
            for _, _, tok_text in group:
                result_parts.append(tok_text)

        last_end = group[-1][1]

    # Trailing non-token text
    if last_end < len(text):
        result_parts.append(text[last_end:])

    return ''.join(result_parts)

