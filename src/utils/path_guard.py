"""Centralized absolute-path validation for tool path arguments.

Validated at the MCP interface boundary (server.call_tool) to avoid CWD
inconsistencies caused by relative paths. Only fields that genuinely represent
filesystem paths are enforced; JSONPath and project-relative fields (such as
delphi_project.sources) are skipped.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional, Tuple


# Path fields to validate per tool (a field value may be a string or a list[str])
# Whitelist approach: fields not listed here are not required to be absolute.
# Intentionally excluded project-relative fields: delphi_project.sources/form_units/source_file/main_source,
# structured_content.path (JSONPath), code_hosting.dir/files (repository-relative or current directory).
TOOL_PATH_FIELDS: Dict[str, Tuple[str, ...]] = {
    # Delphi
    "delphi_file": ("file_path", "project_path", "config_path"),
    "file_tool": ("file_path", "project_path", "config_path"),
    "delphi_project": ("project_path", "file_path", "base_dir", "output_path"),
    "compile_project": ("project_path", "file_path", "base_dir", "output_path"),
    "delphi_kb": ("project_path", "file_path", "directory"),
    "manage_component": ("target_dfm", "target_pas"),
    "package": ("package_path",),
    "check_environment": ("install_dir",),
    "automate_delphi": ("app_path", "snapshots_dir", "script"),
    "delphi_rtti": ("app_path",),
    # Core
    "structured_content": ("file_path", "proto_file"),
    "generate_copyright": ("project_path", "output_dir"),
    "ocr": ("image_path", "template_path", "baseline", "current", "output_dir"),
    # Lazarus
    "lazarus_compile": ("project_path",),
    "lazarus_project": ("project_path",),
    "lazarus_file": ("file_path",),
    "lazarus_kb": ("file_path",),
}


# Project-relative fields intentionally excluded (not added to the whitelist above):
#   delphi_project.sources / form_units / source_file / main_source
#   structured_content.path (JSONPath)
#   code_hosting.dir / files (current directory or repository-relative paths)


def _is_path_like_string(s: str) -> bool:
    """Tell whether a string could be a filesystem path (rather than JSON, a script and so on)."""
    if not s:
        return False
    # Script JSON usually starts with { or [
    stripped = s.lstrip()
    if stripped and stripped[0] in "{[":
        return False
    # Obviously a whole JSON string
    if (stripped.startswith('"') and stripped.endswith('"')) or (
        stripped.startswith("'") and stripped.endswith("'")
    ):
        # Possibly escaped JSON; try to parse it first
        try:
            loaded = json.loads(stripped)
            if isinstance(loaded, (dict, list)):
                return False
        except (json.JSONDecodeError, TypeError):
            pass
    # A path separator or a common extension makes it more path-like
    lower = s.lower()
    if "\\" in s or "/" in s:
        return True
    if lower.endswith((
        ".pas",
        ".dfm",
        ".dpr",
        ".dpk",
        ".dproj",
        ".groupproj",
        ".lpr",
        ".lpi",
        ".inc",
        ".fmx",
        ".lfm",
        ".exe",
        ".dll",
        ".bpl",
        ".json",
        ".xml",
        ".proto",
        ".png",
        ".jpg",
        ".jpeg",
        ".bmp",
        ".txt",
    )):
        return True
    # Windows drive letter
    if len(s) >= 2 and s[1] == ":":
        return True
    # UNC path
    if s.startswith("\\\\"):
        return True
    return False


def _is_absolute_path(p: str) -> bool:
    """Tell whether a path is absolute (Windows drive/UNC and POSIX styles)."""
    if not isinstance(p, str):
        return True  # Non-strings are left to the caller
    p_stripped = p.strip()
    if not p_stripped:
        return True  # Empty values are skipped
    # Windows drive letter
    if len(p_stripped) >= 2 and p_stripped[1] == ":" and p_stripped[0].isalpha():
        # Drive-absolute path (C:\... or C:/...)
        rest = p_stripped[2:]
        if rest and rest[0] in "\\/":
            return True
        # A bare "C:" is an incomplete absolute form; treating it as relative is safer
        return False
    # UNC path \\server\share
    if p_stripped.startswith("\\\\"):
        return True
    # POSIX absolute path
    if p_stripped.startswith("/"):
        return True
    # URLs and the like are not local filesystem paths
    if "://" in p_stripped:
        return False
    return False


def _validate_single_path(tool_name: str, field: str, value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        # Lists are iterated by the caller
        return None
    if not isinstance(value, str):
        return None
    v = value.strip()
    if not v:
        return None
    # automate_delphi.script is validated only when it looks like a file path
    if tool_name == "automate_delphi" and field == "script":
        if not _is_path_like_string(v):
            return None
    if _is_absolute_path(v):
        return None
    # Relative path -> reject
    if os.name == "nt":
        example = "C:\\project\\Unit1.pas"
    else:
        example = "/home/user/project/Unit1.pas"
    return (
        f"Tool '{tool_name}' argument '{field}' must be an absolute path "
        f"(MCP cannot obtain the client's current working directory). "
        f"Current value: '{v}'. Use an absolute path such as '{example}'."
    )


def validate_tool_paths(tool_name: str, arguments: Dict[str, Any]) -> Optional[str]:
    """Validate that filesystem path fields in a tool's arguments are absolute.

    Args:
        tool_name: MCP tool name.
        arguments: Dictionary of arguments passed to that tool.

    Returns:
        Optional[str]: An error message ready to show the user when validation
        fails; None when it passes.
    """
    if not isinstance(arguments, dict):
        return None
    fields = TOOL_PATH_FIELDS.get(tool_name)
    if not fields:
        return None
    for field in fields:
        if field not in arguments:
            continue
        value = arguments.get(field)
        if value is None:
            continue
        # List
        if isinstance(value, (list, tuple)):
            # automate_delphi's script list is a list of steps, not a list of paths
            if tool_name == "automate_delphi" and field == "script":
                continue
            for item in value:
                if isinstance(item, str):
                    err = _validate_single_path(tool_name, field, item)
                    if err:
                        return err
            continue
        if isinstance(value, str):
            err = _validate_single_path(tool_name, field, value)
            if err:
                return err
        # Other types are ignored
    return None
