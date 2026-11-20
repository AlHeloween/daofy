"""
.dproj project file management tool

Supports creating, viewing, and modifying .dproj file configurations and source file references.
Automatically backs up to the __history directory.
"""

import os
import uuid
import re
import shutil
from pathlib import Path
from typing import Optional, List, Any, Tuple
import xml.etree.ElementTree as ET
from datetime import datetime

from mcp.types import CallToolResult, TextContent
from ..utils.dproj_parser import DprojParser
from ..utils.logger import get_logger
from ..services.delphi_edit_guard import record_authorized_write

logger = get_logger(__name__)

# MSBuild 命名空间
MSBUILD_NS = "http://schemas.microsoft.com/developer/msbuild/2003"
ET.register_namespace('', MSBUILD_NS)  # Prevent elements from becoming ns0:-prefixed when written back (MSBuild does not accept it)


def _ns(tag: str) -> str:
    """Add the MSBuild namespace prefix to a tag"""
    if tag.startswith("{"):
        return tag
    return f"{{{MSBUILD_NS}}}{tag}"


def _require(val: Optional[str], name: str = "param") -> str:
    """Assert an Optional[str] is not None, used for type narrowing from entry to handler"""
    if val is None:
        raise ValueError(f"{name} is required")
    return val


def _guarded_write_text(file_path: str | Path, content: str, *, encoding: str) -> None:
    path = Path(file_path)
    record_authorized_write(
        path,
        tool="delphi_project",
        operation="write_text",
    )
    path.write_text(content, encoding=encoding)


def _guarded_tree_write(
    tree: ET.ElementTree,
    file_path: str | Path,
    *,
    encoding: str = "utf-8",
    xml_declaration: bool = True,
) -> None:
    record_authorized_write(
        file_path,
        tool="delphi_project",
        operation="write_xml",
    )
    tree.write(file_path, encoding=encoding, xml_declaration=xml_declaration)


_PLATFORM_NAME_MAP = {
    "win32": "Win32",
    "win64": "Win64",
    "osx32": "OSX32",
    "osx64": "OSX64",
    "osxarm64": "OSXarm64",
    "iosdevice32": "iOSDevice32",
    "iosdevice64": "iOSDevice64",
    "iossimulator": "iOSSimulator",
    "android": "Android",
    "android64": "Android64",
    "linux64": "Linux64",
}


def _normalize_platform_name(platform: Any) -> str:
    """Normalize common platform spellings to Delphi/MSBuild names."""
    text = str(platform).strip()
    key = text.replace("-", "").replace("_", "").lower()
    return _PLATFORM_NAME_MAP.get(key, text)


def _coerce_platforms(platforms: Any) -> Optional[List[str]]:
    """Coerce a string/list platform argument into normalized platform names."""
    if platforms is None:
        return None

    if isinstance(platforms, str):
        raw_items = re.split(r"[,;]", platforms)
    else:
        try:
            raw_items = list(platforms)
        except TypeError:
            raw_items = [platforms]

    normalized: List[str] = []
    for item in raw_items:
        if item is None:
            continue
        name = _normalize_platform_name(item)
        if name and name not in normalized:
            normalized.append(name)
    return normalized or None


def _backup_file(file_path: str) -> Optional[str]:
    """Back up a file to the __history directory, returning the backup path"""
    src = Path(file_path)
    if not src.exists():
        return None

    history_dir = src.parent / "__history"
    history_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"{src.stem}_{timestamp}{src.suffix}"
    backup_path = history_dir / backup_name

    try:
        shutil.copy2(str(src), str(backup_path))
        logger.info(f"Backed up {file_path} → {backup_path}")
        return str(backup_path)
    except Exception as e:
        logger.error(f"Backup failed: {e}")
        return None


def _parse(file_path: str) -> Any:
    """Parse a .dproj file, returning an ElementTree or None"""
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        if root is None:
            logger.error(f"XML root element is empty: {file_path}")
            return None
        if root.tag != _ns("Project"):
            logger.error(f"Root tag is not Project: {root.tag}")
            return None
        return tree
    except ET.ParseError as e:
        logger.error(f"Failed to parse .dproj XML: {e}")
        return None
    except FileNotFoundError:
        logger.error(f".dproj file does not exist: {file_path}")
        return None
    except PermissionError:
        logger.error(f"No permission to read .dproj file: {file_path}")
        return None
    except OSError as e:
        logger.error(f"I/O error reading .dproj file: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error while parsing .dproj file: {e}")
        return None


def _parse_tree(file_path: str) -> Any:
    """Parse a .dproj file, returning (tree, root) or None"""
    tree = _parse(file_path)
    if tree is None:
        return None
    root = tree.getroot()
    if root is None:
        return None
    return tree, root


def _find_pg(root: ET.Element, config: Optional[str] = None, platform: Optional[str] = None) -> List[ET.Element]:
    """Find PropertyGroups matching the criteria. When config/platform=None, returns unconditional groups."""
    groups = root.findall(_ns("PropertyGroup"))
    if config is None and platform is None:
        # Return the first unconditional PropertyGroup
        return [g for g in groups if not g.get("Condition")]

    result = []
    for group in groups:
        condition = group.get("Condition", "")
        match = True
        if config and f"'$(Config)'=='{config}'" not in condition:
            match = False
        if platform and f"'$(Platform)'=='{platform}'" not in condition:
            match = False
        if match:
            result.append(group)
    return result


def _find_or_create(parent: ET.Element, tag: str) -> ET.Element:
    """Find a child element, creating it if it does not exist"""
    full = _ns(tag)
    elem = parent.find(full)
    if elem is None:
        elem = ET.SubElement(parent, full)
    return elem


def _find_or_create_item_group(root: ET.Element) -> ET.Element:
    """Find the first ItemGroup, appending one if it does not exist"""
    groups = root.findall(_ns("ItemGroup"))
    if groups:
        return groups[0]
    # Append at the end of Project (before Import)
    elem = ET.SubElement(root, _ns("ItemGroup"))
    return elem


def _find_dcc_ref(item_group: ET.Element, file_name: str) -> Optional[ET.Element]:
    """Find a DCCReference in an ItemGroup by file name"""
    target = file_name.lower()
    for ref in item_group.findall(_ns("DCCReference")):
        inc = ref.get("Include", "")
        if inc and Path(inc).name.lower() == target:
            return ref
    return None


# ──────────────────────────────────────────────
# .dpk sync utilities (contains / requires)
# ──────────────────────────────────────────────

def _get_dpk_path_from_dproj(dproj_path: str) -> Optional[str]:
    """Get the corresponding .dpk file path from a .dproj file (Package projects only)"""
    try:
        tree = ET.parse(dproj_path)
        root = tree.getroot()
    except Exception:
        return None

    # Check whether AppType is Package
    for pg in root.findall(_ns("PropertyGroup")):
        cond = pg.get("Condition", "")
        if cond:  # Skip conditional PropertyGroups
            continue
        app = pg.find(_ns("AppType"))
        if app is not None and app.text and app.text.lower() == "package":
            ms = pg.find(_ns("MainSource"))
            if ms is not None and ms.text:
                dpk_path = str(Path(dproj_path).parent / ms.text)
                if Path(dpk_path).exists():
                    return dpk_path
    return None


def _dpk_parse_entries(dpk_path: str, section: str = "contains") -> List[str]:
    """Parse each text line of the contains/requires section in a .dpk

    Args:
        dpk_path: .dpk file path
        section: section name "contains" or "requires"

    Returns:
        List of raw text lines (preserving original indentation), excluding section headers, section terminators, comments, and blank lines

    Note:
        The stop condition differs per section:
        - section="requires" stops on "contains" or "end"
        - section="contains" stops on "requires" (never occurs) or "end"
        In both cases a blank line also triggers the stop check (it only really breaks when the previous entry ends with ";")
    """
    try:
        content = Path(dpk_path).read_text(encoding="utf-8-sig")
    except (FileNotFoundError, OSError):
        logger.warning(f".dpk file does not exist or cannot be read: {dpk_path}")
        return []
    lines = content.splitlines()
    section_lower = section.lower()

    in_section = False
    entries: List[str] = []

    for line in lines:
        stripped = line.strip()
        lower = stripped.lower()

        if in_section:
            # Try to terminate on requires / end / blank line
            # When section="contains", requires never appears (contains comes after requires),
            # but the generic parser keeps this condition to handle rare reversed orderings
            if lower.startswith("requires") or lower.startswith("end") or lower == "":
                if entries and entries[-1].rstrip().endswith(";"):
                    break  # Complete entry finished
                continue
            # Skip pure comments
            if lower.startswith("{"):
                continue
            entries.append(line)

        if lower.startswith(section_lower):
            in_section = True

    return entries


def _dpk_contains_entries(dpk_path: str) -> List[Tuple[str, str, str]]:
    """Parse .dpk contains entries

    Args:
        dpk_path: .dpk file path

    Returns:
        List where each item is (raw line, unit name, file path)
        "/" in the file path is uniformly replaced with "\\"
    """
    raw = _dpk_parse_entries(dpk_path, "contains")
    pattern = re.compile(r"^\s*(\w+)\s+in\s+'([^']+)'\s*,?\s*;?\s*$", re.IGNORECASE)
    result: List[Tuple[str, str, str]] = []
    for line in raw:
        m = pattern.match(line)
        if m:
            result.append((line, m.group(1), m.group(2).replace("/", "\\")))
    return result


def _dpk_requires_entries(dpk_path: str) -> List[Tuple[str, str]]:
    """Parse .dpk requires entries

    Args:
        dpk_path: .dpk file path

    Returns:
        List where each item is (raw line, package name)
    """
    raw = _dpk_parse_entries(dpk_path, "requires")
    pattern = re.compile(r"^\s*(\w[\w.]*)\s*,?\s*;?\s*$")
    result: List[Tuple[str, str]] = []
    for line in raw:
        m = pattern.match(line)
        if m:
            result.append((line, m.group(1)))
    return result


def _dpk_add_contains(dpk_path: str, source_file: str, unit_name: str) -> Optional[str]:
    """Add an entry 'UnitName in 'SourceFilePath',' to .dpk contains

    Returns None if it already exists (path match). New entries always go last.

    Args:
        dpk_path: .dpk file path
        source_file: source file path (e.g. Source\\Unit1.pas)
        unit_name: unit name (e.g. Unit1)

    Returns:
        Backup path (on success), None (already exists or on failure)
    """
    # Check whether it already exists
    existing = _dpk_contains_entries(dpk_path)
    norm_path = source_file.replace("/", "\\")
    for _, _, fp in existing:
        if fp.lower() == norm_path.lower():
            return None

    backup_path = _backup_file(dpk_path)

    try:
        content = Path(dpk_path).read_text(encoding="utf-8-sig")
    except (FileNotFoundError, OSError):
        logger.warning(f".dpk file does not exist or cannot be read: {dpk_path}")
        return None

    lines = content.splitlines()
    insert_idx = -1
    in_contains = False
    has_trailing_semicolon = False
    last_entry_idx = -1  # Track the line number of the last entry-like line (even without a separator)

    for i, line in enumerate(lines):
        lower = line.strip().lower()
        if in_contains:
            if lower.startswith("requires") or lower.startswith("end"):
                # If there are contains entries but no separator, fall back to inserting before end.
                if insert_idx == -1 and last_entry_idx >= 0:
                    insert_idx = i
                break
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("{"):
                continue
            # Even without a semicolon/comma, track the position of entries
            if re.match(r"^\s*(\w+)\s+in\s+'([^']+)'", line, re.IGNORECASE):
                last_entry_idx = i
            if stripped.endswith(";"):
                has_trailing_semicolon = True
                insert_idx = i + 1
            elif stripped.endswith(","):
                has_trailing_semicolon = False
                insert_idx = i + 1
        if lower.startswith("contains"):
            in_contains = True

    if insert_idx == -1:
        # No contains section, append
        # Find end. and insert before it
        for i, line in enumerate(lines):
            if line.strip().lower() == "end.":
                # Insert requires and contains before end.
                indent = "  "
                new_lines = [
                    "",
                    "requires",
                    "  rtl;",
                    "",
                    "contains",
                    f"  {unit_name} in '{source_file}';",
                ]
                for j, nl in enumerate(reversed(new_lines)):
                    lines.insert(i, nl)
                break
        else:
            return backup_path  # Cannot parse
    else:
        indent = "  "
        suffix = ";"
        if has_trailing_semicolon:
            # Change the previous entry's semicolon to a comma
            prev_line = lines[insert_idx - 1].rstrip()
            if prev_line.endswith(";"):
                lines[insert_idx - 1] = prev_line[:-1] + ","
            suffix = ";"
        elif insert_idx > 0:
            # Add a comma at the end of the previous entry
            prev_line = lines[insert_idx - 1].rstrip()
            if not prev_line.endswith(",") and not prev_line.endswith(";"):
                lines[insert_idx - 1] = prev_line + ","
            suffix = ";"
        new_line = f"{indent}{unit_name} in '{source_file}'{suffix}"
        lines.insert(insert_idx, new_line)

    _guarded_write_text(dpk_path, "\n".join(lines) + "\n", encoding="utf-8-sig")
    return backup_path


def _dpk_remove_contains(dpk_path: str, source_file: str) -> Optional[str]:
    """Remove entries matching the source file from .dpk contains, fixing the trailing comma/semicolon

    Args:
        dpk_path: .dpk file path
        source_file: source file name (e.g. Unit1.pas) or full path

    Returns:
        Backup path (on success), None (not found or on failure)
    """
    norm_path = source_file.replace("/", "\\").lower()
    try:
        content = Path(dpk_path).read_text(encoding="utf-8-sig")
    except (FileNotFoundError, OSError):
        logger.warning(f".dpk file does not exist or cannot be read: {dpk_path}")
        return None
    lines = content.splitlines()

    # Locate lines to delete via parsed matching to avoid string equality issues
    remove_indices: set[int] = set()
    in_contains = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        lower = stripped.lower()
        if in_contains:
            if lower.startswith("requires") or lower.startswith("end"):
                break
            if not stripped or lower.startswith("{"):
                continue
            m = re.match(r"^\s*(\w+)\s+in\s+'([^']+)'\s*,?\s*;?\s*$", line, re.IGNORECASE)
            if m and m.group(2).replace("/", "\\").lower() == norm_path:
                remove_indices.add(i)
        if lower.startswith("contains"):
            in_contains = True

    if not remove_indices:
        return None

    backup_path = _backup_file(dpk_path)

    # Delete the lines
    new_lines = [line for i, line in enumerate(lines) if i not in remove_indices]

    # Fix separators: find the last remaining entry in contains and make sure it ends with ";"
    in_contains = False
    last_contains_idx = -1
    for i, line in enumerate(new_lines):
        stripped = line.strip()
        lower = stripped.lower()
        if in_contains:
            if lower.startswith("requires") or lower.startswith("end"):
                break
            if not stripped or lower.startswith("{"):
                continue
            m = re.match(r"^\s*(\w+)\s+in\s+'([^']+)'", line, re.IGNORECASE)
            if m:
                last_contains_idx = i
        if lower.startswith("contains"):
            in_contains = True

    if last_contains_idx >= 0:
        last_line = new_lines[last_contains_idx].rstrip()
        if last_line.endswith(","):
            new_lines[last_contains_idx] = last_line[:-1] + ";"

    _guarded_write_text(dpk_path, "\n".join(new_lines) + "\n", encoding="utf-8-sig")
    return backup_path


def _dpk_add_requires(dpk_path: str, package_name: str) -> Optional[str]:
    """Add a package dependency to .dpk requires

    Automatically detects whether the new entry is the last one (next line is contains/end);
    if so it ends with ";", otherwise with ",".
    #2 Returns None if it already exists (same-name match).

    Args:
        dpk_path: .dpk file path
        package_name: package name (e.g. vcl, rtl)

    Returns:
        Backup path (on success), None (if it already exists)
    """
    existing = _dpk_requires_entries(dpk_path)
    for _, name in existing:
        if name.lower() == package_name.lower():
            return None

    backup_path = _backup_file(dpk_path)
    try:
        content = Path(dpk_path).read_text(encoding="utf-8-sig")
    except (FileNotFoundError, OSError):
        logger.warning(f".dpk file does not exist or cannot be read: {dpk_path}")
        return None
    lines = content.splitlines()
    insert_idx = -1
    in_requires = False

    for i, line in enumerate(lines):
        lower = line.strip().lower()
        if in_requires:
            if lower.startswith("contains") or lower.startswith("end"):
                break
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.endswith(","):
                insert_idx = i + 1
            elif stripped.endswith(";"):
                insert_idx = i + 1
        if lower.startswith("requires"):
            in_requires = True

    if insert_idx == -1:
        # No requires section, insert before end.
        for i, line in enumerate(lines):
            if line.strip().lower() == "end.":
                new_lines = ["", "requires", f"  {package_name};"]
                for j, nl in enumerate(reversed(new_lines)):
                    lines.insert(i, nl)
                break
    else:
        # Determine whether the new entry is the last one (next line is contains/end)
        is_last = True
        if insert_idx < len(lines):
            next_line = lines[insert_idx].strip().lower()
            if not (next_line.startswith("contains") or next_line.startswith("end") or next_line == ""):
                is_last = False
        # Change the previous entry to a comma (only needed when the previous entry ends with a semicolon)
        if insert_idx > 0:
            prev = lines[insert_idx - 1].rstrip()
            if prev.endswith(";"):
                lines[insert_idx - 1] = prev[:-1] + ","
            elif not prev.endswith(",") and prev.strip():
                lines[insert_idx - 1] = prev + ","
        suffix = ";" if is_last else ","
        lines.insert(insert_idx, f"  {package_name}{suffix}")

    _guarded_write_text(dpk_path, "\n".join(lines) + "\n", encoding="utf-8-sig")
    return backup_path


def _dpk_remove_requires(dpk_path: str, package_name: str) -> Optional[str]:
    """Remove a package dependency from .dpk requires

    Utility function; currently not called automatically from handlers (requires is
    managed manually by the user and does not change automatically with source file
    additions/removals). Provided for script/manual use.

    Args:
        dpk_path: .dpk file path
        package_name: package name

    Returns:
        Backup path (on success), None (not found)
    """
    existing = _dpk_requires_entries(dpk_path)
    to_remove = [line for line, name in existing if name.lower() == package_name.lower()]
    if not to_remove:
        return None

    backup_path = _backup_file(dpk_path)
    content = Path(dpk_path).read_text(encoding="utf-8-sig")
    lines = content.splitlines()
    remove_set = set()
    for rm_line in to_remove:
        for i, line in enumerate(lines):
            if line.rstrip() == rm_line.rstrip():
                remove_set.add(i)
                break

    new_lines = [line for i, line in enumerate(lines) if i not in remove_set]
    _guarded_write_text(dpk_path, "\n".join(new_lines) + "\n", encoding="utf-8-sig")
    return backup_path


# ──────────────────────────────────────────────
# Per-action handlers
# ──────────────────────────────────────────────

def _infer_app_type(framework_type: str, app_type: Optional[str] = None) -> str:
    """Infer AppType, defaulting to Application"""
    if app_type:
        return app_type
    if framework_type == "None":
        return "Console"
    return "Application"


def _sanitized_project_name(main_source: str) -> str:
    """Extract the project name from the main source file name (removing the extension)"""
    return Path(main_source).stem


def _default_namespace(framework_type: str) -> str:
    """Return the default namespace based on the framework type"""
    if framework_type == "VCL":
        return "System;System.Win;Winapi;Xml;Data;Datasnap;Web;Soap;Vcl"
    elif framework_type == "FMX":
        return "System;System.Win;Winapi;Xml;Data;Datasnap;Web;Soap;FMX"
    else:
        # None (Console / Library / Package) — no GUI references
        return "System;Xml;Data;Datasnap;Web;Soap"


def _is_package(app_type: str) -> bool:
    """Determine whether this is a component package"""
    return app_type.lower() == "package"


def _add_property_group_hierarchy(
    root: ET.Element,
    project_name: str,
    configs: List[str],
    namespace: str,
    framework_type: str,
    app_type: str,
    platforms: List[str],
    unit_search_paths: Optional[List[str]] = None,
    old_format: bool = False,
) -> None:
    """Build the PropertyGroup inheritance hierarchy for a Delphi .dproj

    When old_format=True, all platform sub-PGs are skipped (suitable for older projects with ProjectVersion < 17.0).

    Output PropertyGroup order:
      1. Base config PG
      2. Base + platform PGs (skip if old_format)
      3. Cfg_1 config PG
      4. Cfg_1 + platform PGs (skip if old_format)
      5. Cfg_2 config PG
      6. Cfg_2 + platform PGs (skip if old_format)
      7. '$(Base)'!='' — shared project properties
      8. '$(Base_{platform})'!='' — per-platform shared properties (skip if old_format)
      9. '$(Cfg_1)'!='' — Cfg_1 compile properties
      10. '$(Cfg_2)'!='' — Cfg_2 compile properties
    """

    is_pkg = _is_package(app_type)
    is_console = app_type == "Console"

    def _cfg_is_debug(name: str) -> bool:
        return name.lower() in ("debug", "debug_", "dbg")

    def _cfg_is_release(name: str) -> bool:
        return name.lower() in ("release", "release_", "rel")

    def _cfg_bt_buildtype(name: str) -> str:
        return "Debug" if _cfg_is_debug(name) else "Release"

    # ── 1. Base config PropertyGroup ──
    pg_base = ET.SubElement(root, _ns("PropertyGroup"))
    pg_base.set("Condition", "'$(Config)'=='Base' or '$(Base)'!=''")
    ET.SubElement(pg_base, _ns("Base")).text = "true"

    # ── 2. Base + platform PropertyGroups (iterates all platforms) ──
    if not old_format:
        for plat in platforms:
            plat_cond = (
                f"('$(Platform)'=='{plat}' and '$(Base)'=='true')"
                f" or '$(Base_{plat})'!=''"
            )
            pg_bp = ET.SubElement(root, _ns("PropertyGroup"))
            pg_bp.set("Condition", plat_cond)
            ET.SubElement(pg_bp, _ns(f"Base_{plat}")).text = "true"
            ET.SubElement(pg_bp, _ns("CfgParent")).text = "Base"
            ET.SubElement(pg_bp, _ns("Base")).text = "true"

    # ── 3-4. Config-specific PropertyGroups (Cfg_1 = configs[0]) ──
    cfg1_name = configs[0]
    pg_cfg1 = ET.SubElement(root, _ns("PropertyGroup"))
    pg_cfg1.set("Condition", f"'$(Config)'=='{cfg1_name}' or '$(Cfg_1)'!=''")
    ET.SubElement(pg_cfg1, _ns("Cfg_1")).text = "true"
    ET.SubElement(pg_cfg1, _ns("CfgParent")).text = "Base"
    ET.SubElement(pg_cfg1, _ns("Base")).text = "true"

    # Cfg_1 + platform PGs
    if not old_format:
        for plat in platforms:
            plat_cond = (
                f"('$(Platform)'=='{plat}' and '$(Cfg_1)'=='true')"
                f" or '$(Cfg_1_{plat})'!=''"
            )
            pg_cfg1p = ET.SubElement(root, _ns("PropertyGroup"))
            pg_cfg1p.set("Condition", plat_cond)
            ET.SubElement(pg_cfg1p, _ns(f"Cfg_1_{plat}")).text = "true"
            ET.SubElement(pg_cfg1p, _ns("CfgParent")).text = "Cfg_1"
            ET.SubElement(pg_cfg1p, _ns("Cfg_1")).text = "true"
            ET.SubElement(pg_cfg1p, _ns("Base")).text = "true"

    # ── 5-6. Config-specific PropertyGroups (Cfg_2 = configs[1], if exists) ──
    if len(configs) > 1:
        cfg2_name = configs[1]
        pg_cfg2 = ET.SubElement(root, _ns("PropertyGroup"))
        pg_cfg2.set("Condition", f"'$(Config)'=='{cfg2_name}' or '$(Cfg_2)'!=''")
        ET.SubElement(pg_cfg2, _ns("Cfg_2")).text = "true"
        ET.SubElement(pg_cfg2, _ns("CfgParent")).text = "Base"
        ET.SubElement(pg_cfg2, _ns("Base")).text = "true"

        # Cfg_2 + platform PGs
        if not old_format:
            for plat in platforms:
                plat_cond = (
                    f"('$(Platform)'=='{plat}' and '$(Cfg_2)'=='true')"
                    f" or '$(Cfg_2_{plat})'!=''"
                )
                pg_cfg2p = ET.SubElement(root, _ns("PropertyGroup"))
                pg_cfg2p.set("Condition", plat_cond)
                ET.SubElement(pg_cfg2p, _ns(f"Cfg_2_{plat}")).text = "true"
                ET.SubElement(pg_cfg2p, _ns("CfgParent")).text = "Cfg_2"
                ET.SubElement(pg_cfg2p, _ns("Cfg_2")).text = "true"
                ET.SubElement(pg_cfg2p, _ns("Base")).text = "true"

    # ── 7. '$(Base)'!='' — shared project properties ──
    pg_base_shared = ET.SubElement(root, _ns("PropertyGroup"))
    pg_base_shared.set("Condition", "'$(Base)'!=''")
    ET.SubElement(pg_base_shared, _ns("SanitizedProjectName")).text = project_name
    ET.SubElement(pg_base_shared, _ns("DCC_Namespace")).text = namespace
    ET.SubElement(pg_base_shared, _ns("DCC_DcuOutput")).text = ".\\$(Platform)\\$(Config)"
    ET.SubElement(pg_base_shared, _ns("DCC_ExeOutput")).text = ".\\$(Platform)\\$(Config)"

    # DCC_E/N/S/F/K — differs between Package and App
    if is_pkg:
        ET.SubElement(pg_base_shared, _ns("DCC_E")).text = "false"
        ET.SubElement(pg_base_shared, _ns("DCC_N")).text = "false"
        ET.SubElement(pg_base_shared, _ns("DCC_S")).text = "true"
        ET.SubElement(pg_base_shared, _ns("DCC_F")).text = "true"
        ET.SubElement(pg_base_shared, _ns("DCC_K")).text = "false"
        ET.SubElement(pg_base_shared, _ns("DCC_BRCC")).text = "true"
        ET.SubElement(pg_base_shared, _ns("DCC_Bsc")).text = "false"
        ET.SubElement(pg_base_shared, _ns("DCC_UseDesignIde")).text = "true"
        ET.SubElement(pg_base_shared, _ns("DCC_SymbolReferenceInfo")).text = "0"
        ET.SubElement(pg_base_shared, _ns("DCC_Define")).text = "DEBUG"
        ET.SubElement(
            pg_base_shared, _ns("DCC_DcuPackage")
        ).text = f"{project_name}.dcp"
        ET.SubElement(
            pg_base_shared, _ns("DCC_BplOutput")
        ).text = "..\\..\\$(Platform)\\$(Config)"
        ET.SubElement(
            pg_base_shared, _ns("DCC_DcpOutput")
        ).text = ".\\$(Platform)\\$(Config)"
        # Package signature elements
        ET.SubElement(pg_base_shared, _ns("GenPackage")).text = "true"
        ET.SubElement(pg_base_shared, _ns("RuntimeOnlyPackage")).text = "true"
        ET.SubElement(pg_base_shared, _ns("GenDll")).text = "true"
    else:
        ET.SubElement(pg_base_shared, _ns("DCC_E")).text = "false"
        ET.SubElement(pg_base_shared, _ns("DCC_N")).text = "false"
        ET.SubElement(pg_base_shared, _ns("DCC_S")).text = "false"
        ET.SubElement(pg_base_shared, _ns("DCC_F")).text = "false"
        ET.SubElement(pg_base_shared, _ns("DCC_K")).text = "false"

    if unit_search_paths:
        ET.SubElement(
            pg_base_shared, _ns("DCC_UnitSearchPath")
        ).text = ";".join(unit_search_paths)

    # ── 8. '$(Base_{platform})'!='' — per-platform shared properties ──
    if not old_format:
        for plat in platforms:
            pg_bp_shared = ET.SubElement(root, _ns("PropertyGroup"))
            pg_bp_shared.set("Condition", f"'$(Base_{plat})'!=''")

            if plat == "Win32":
                win32_ns = "Winapi;System.Win;Data.Win;Datasnap.Win;Web.Win;Soap.Win;Xml.Win;Bde"
            else:
                win32_ns = "Winapi;System.Win;Data.Win;Datasnap.Win;Web.Win;Soap.Win;Xml.Win"
            ET.SubElement(
                pg_bp_shared, _ns("DCC_Namespace")
            ).text = f"{win32_ns};$(DCC_Namespace)"

            if framework_type in ("VCL", "FMX") and not is_pkg:
                ET.SubElement(pg_bp_shared, _ns("AppEnableRuntimeThemes")).text = "true"
                ET.SubElement(
                    pg_bp_shared, _ns("Manifest_File")
                ).text = "$(BDS)\\bin\\default_app.manifest"
            elif app_type == "Library":
                pass  # DLLs usually have no manifest

            if app_type == "Library":
                ET.SubElement(pg_bp_shared, _ns("GenDll")).text = "true"

            # BT_BuildType: IDE debugging aid
            ET.SubElement(pg_bp_shared, _ns("BT_BuildType")).text = "Debug"

            # DCC_ConsoleTarget: Console application
            if is_console:
                ET.SubElement(pg_bp_shared, _ns("DCC_ConsoleTarget")).text = "true"

    # ── 9. Cfg_1 specific compile properties (configs[0]) ──
    cfg1_debug = _cfg_is_debug(cfg1_name)
    cfg1_release = _cfg_is_release(cfg1_name)
    pg_cfg1_props = ET.SubElement(root, _ns("PropertyGroup"))
    pg_cfg1_props.set("Condition", "'$(Cfg_1)'!=''")
    if cfg1_debug:
        ET.SubElement(pg_cfg1_props, _ns("BT_BuildType")).text = "Debug"
        ET.SubElement(pg_cfg1_props, _ns("DCC_Define")).text = "DEBUG;$(DCC_Define)"
        ET.SubElement(pg_cfg1_props, _ns("DCC_DebugDCUs")).text = "true"
        ET.SubElement(pg_cfg1_props, _ns("DCC_Optimize")).text = "false"
        ET.SubElement(pg_cfg1_props, _ns("DCC_GenerateStackFrames")).text = "true"
        ET.SubElement(pg_cfg1_props, _ns("DCC_DebugInfoInExe")).text = "true"
    elif cfg1_release:
        ET.SubElement(pg_cfg1_props, _ns("BT_BuildType")).text = "Release"
        ET.SubElement(pg_cfg1_props, _ns("DCC_Define")).text = f"{cfg1_name.upper()};$(DCC_Define)"
        ET.SubElement(pg_cfg1_props, _ns("DCC_Optimize")).text = "true"
        ET.SubElement(pg_cfg1_props, _ns("DCC_DebugInfoInExe")).text = "true"
        ET.SubElement(pg_cfg1_props, _ns("DCC_LocalDebugSymbols")).text = "false"
        ET.SubElement(pg_cfg1_props, _ns("DCC_SymbolReferenceInfo")).text = "0"
        ET.SubElement(pg_cfg1_props, _ns("DCC_DebugInformation")).text = "0"
    else:
        ET.SubElement(pg_cfg1_props, _ns("DCC_Define")).text = f"{cfg1_name.upper()};$(DCC_Define)"
        ET.SubElement(pg_cfg1_props, _ns("DCC_Optimize")).text = "true"
        ET.SubElement(pg_cfg1_props, _ns("DCC_DebugInfoInExe")).text = "true"

    # ── 10. Cfg_2 specific compile properties (configs[1], if exists) ──
    if len(configs) > 1:
        cfg2_name = configs[1]
        cfg2_debug = _cfg_is_debug(cfg2_name)
        cfg2_release = _cfg_is_release(cfg2_name)
        pg_cfg2_props = ET.SubElement(root, _ns("PropertyGroup"))
        pg_cfg2_props.set("Condition", "'$(Cfg_2)'!=''")
        if cfg2_debug:
            ET.SubElement(pg_cfg2_props, _ns("BT_BuildType")).text = "Debug"
            ET.SubElement(pg_cfg2_props, _ns("DCC_Define")).text = "DEBUG;$(DCC_Define)"
            ET.SubElement(pg_cfg2_props, _ns("DCC_DebugDCUs")).text = "true"
            ET.SubElement(pg_cfg2_props, _ns("DCC_Optimize")).text = "false"
            ET.SubElement(pg_cfg2_props, _ns("DCC_GenerateStackFrames")).text = "true"
            ET.SubElement(pg_cfg2_props, _ns("DCC_DebugInfoInExe")).text = "true"
        elif cfg2_release:
            ET.SubElement(pg_cfg2_props, _ns("BT_BuildType")).text = "Release"
            ET.SubElement(pg_cfg2_props, _ns("DCC_Define")).text = "RELEASE;$(DCC_Define)"
            ET.SubElement(pg_cfg2_props, _ns("DCC_LocalDebugSymbols")).text = "false"
            ET.SubElement(pg_cfg2_props, _ns("DCC_SymbolReferenceInfo")).text = "0"
            ET.SubElement(pg_cfg2_props, _ns("DCC_DebugInformation")).text = "0"
        else:
            ET.SubElement(pg_cfg2_props, _ns("DCC_Define")).text = f"{cfg2_name.upper()};$(DCC_Define)"
            ET.SubElement(pg_cfg2_props, _ns("DCC_Optimize")).text = "true"
            ET.SubElement(pg_cfg2_props, _ns("DCC_DebugInfoInExe")).text = "false"


def _form_class_name(form_name: str) -> str:
    """Generate the standard Form class name from a form short name.

    form_units=["Main"] → TMainForm
    form_units=["Unit1"] → TForm1 (compatible with Delphi IDE conventions)
    """
    m = re.match(r'^Unit(\d+)$', form_name, re.IGNORECASE)
    if m:
        return f"TForm{m.group(1)}"
    return f"T{form_name}Form"


def _form_var_name(form_name: str) -> str:
    """Generate the Form global variable name from a form short name.

    form_units=["Main"] → MainForm
    form_units=["Unit1"] → Form1
    """
    m = re.match(r'^Unit(\d+)$', form_name, re.IGNORECASE)
    if m:
        return f"Form{m.group(1)}"
    return f"{form_name}Form"


# Form unit file name prefix (mimicking the Delphi Vcl.Forms.pas naming style)
# form_units=["Main"] → file Form.Main.pas, unit Form.Main
_FORM_UNIT_PREFIX: str = "Form."


def _form_file_stem(form_name: str) -> str:
    """Convert a short name from form_units into a prefixed file stem name.

    Example: "Main" → "Form.Main"
    """
    return f"{_FORM_UNIT_PREFIX}{form_name}"


def _form_var_name(form_name: str) -> str:
    """Generate the Form global variable name from a form short name.

    form_units=["Main"] → MainForm
    form_units=["Unit1"] → Form1
    """
    m = re.match(r'^Unit(\d+)$', form_name, re.IGNORECASE)
    if m:
        return f"Form{m.group(1)}"
    return f"{form_name}Form"


def _generate_form_pas(project_dir: str, form_name: str, framework_type: str) -> str:
    """Generate minimal Form unit .pas file content.

    File naming follows the Form.{Name}.pas style, e.g. Form.Main.pas.
    form_name is the form short name (e.g. "Main"); the class name is automatically T{Name}Form.

    Returns: the path of the written file
    """
    cls_name = _form_class_name(form_name)
    var_name = _form_var_name(form_name)
    file_stem = _form_file_stem(form_name)   # e.g. Form.Main
    file_path = Path(project_dir) / f"{file_stem}.pas"

    if file_path.exists():
        return str(file_path)

    if framework_type == "FMX":
        uses_list = (
            "System.SysUtils, System.Types, System.UITypes, System.Classes,\n"
            "  FMX.Types, FMX.Controls, FMX.Forms, FMX.Dialogs, FMX.StdCtrls"
        )
        pas_content = (
            f"unit {file_stem};\n\n"
            f"interface\n\n"
            f"uses\n  {uses_list};\n\n"
            f"type\n"
            f"  {cls_name} = class(TForm)\n"
            f"  private\n"
            f"    {{ Private declarations }}\n"
            f"  public\n"
            f"    {{ Public declarations }}\n"
            f"  end;\n\n"
            f"var\n"
            f"  {var_name}: {cls_name};\n\n"
            f"implementation\n\n"
            f"{{$R *.fmx}}\n\n"
            f"end.\n"
        )
    else:
        uses_list = (
            "Winapi.Windows, Winapi.Messages, System.SysUtils, System.Variants,\n"
            "  System.Classes, Vcl.Graphics, Vcl.Controls, Vcl.Forms, Vcl.Dialogs"
        )
        pas_content = (
            f"unit {file_stem};\n\n"
            f"interface\n\n"
            f"uses\n  {uses_list};\n\n"
            f"type\n"
            f"  {cls_name} = class(TForm)\n"
            f"  private\n"
            f"    {{ Private declarations }}\n"
            f"  public\n"
            f"    {{ Public declarations }}\n"
            f"  end;\n\n"
            f"var\n"
            f"  {var_name}: {cls_name};\n\n"
            f"implementation\n\n"
            f"{{$R *.dfm}}\n\n"
            f"end.\n"
        )

    _guarded_write_text(file_path, pas_content, encoding="utf-8-sig")
    return str(file_path)
def _generate_form_dfm(project_dir: str, form_name: str, framework_type: str) -> str:
    """Generate minimal Form unit .dfm/.fmx file content (empty Form, no components).

    Returns: path of the file written
    """
    cls_name = _form_class_name(form_name)
    var_name = _form_var_name(form_name)
    file_stem = _form_file_stem(form_name)
    ext = ".fmx" if framework_type == "FMX" else ".dfm"
    file_path = Path(project_dir) / f"{file_stem}{ext}"

    if file_path.exists():
        return str(file_path)

    dfm_content = (
        f"object {var_name}: {cls_name}\n"
        f"  Left = 0\n"
        f"  Top = 0\n"
        f"  Caption = '{cls_name}'\n"
        f"  ClientHeight = 300\n"
        f"  ClientWidth = 400\n"
        f"  Position = poScreenCenter\n"
    )
    if framework_type != "FMX":
        dfm_content += "  TextHeight = 13\n"
    dfm_content += "end\n"

    _guarded_write_text(file_path, dfm_content, encoding="utf-8-sig")
    return str(file_path)


def _generate_dpr(
    project_dir: str,
    main_source: str,
    form_units: List[str],
    framework_type: str,
    app_type: str,
) -> str:
    """Generate a minimal .dpr file.

    Returns: path of the file written
    """
    dpr_path = Path(project_dir) / main_source
    if dpr_path.exists():
        return str(dpr_path)

    unit_includes = []
    create_forms = []
    for form_name in form_units:
        cls_name = _form_class_name(form_name)
        var_name = _form_var_name(form_name)
        file_stem = _form_file_stem(form_name)
        unit_includes.append(f"  {file_stem} in '{file_stem}.pas'")
        create_forms.append(f"  Application.CreateForm({cls_name}, {var_name});")

    uses_includes = ",\n".join(unit_includes)
    create_forms_str = "\n".join(create_forms)

    is_console = app_type == "Console"

    dpr_content = (
        f"program {Path(main_source).stem};\n\n"
        f"uses\n"
        f"  Vcl.Forms,\n"
        f"{uses_includes};\n\n"
        f"{{$R *.res}}\n\n"
        f"begin\n"
        f"  Application.Initialize;\n"
    )
    if not is_console:
        dpr_content += "  Application.MainFormOnTaskbar := True;\n"
    dpr_content += f"{create_forms_str}\n"
    dpr_content += "  Application.Run;\n"
    dpr_content += "end.\n"

    _guarded_write_text(dpr_path, dpr_content, encoding="utf-8-sig")
    return str(dpr_path)


async def _handle_create(
    project_path: str,
    main_source: str,
    project_guid: Optional[str] = None,
    project_version: Optional[str] = None,
    framework_type: str = "VCL",
    app_type: Optional[str] = None,
    unit_search_paths: Optional[List[str]] = None,
    namespace: Optional[str] = None,
    configs: Optional[List[str]] = None,
    sources: Optional[List[str]] = None,
    platforms: Optional[List[str]] = None,
    form_units: Optional[List[str]] = None,
) -> CallToolResult:
    """Create a new .dproj file (IDE-compatible format).

    If form_units is specified, minimal stub code is also generated automatically:
      - .pas (with published TForm subclass declaration + standard uses)
      - .dfm/.fmx (empty Form, no components, framework determined by framework_type)
      - .dpr (with uses + CreateForm calls)
    """
    if Path(project_path).exists():
        return CallToolResult(
            content=[TextContent(type="text", text=f"File already exists: {project_path}")],
            isError=True,
        )

    Path(project_path).parent.mkdir(parents=True, exist_ok=True)

    if not project_guid:
        project_guid = "{" + str(uuid.uuid4()).upper() + "}"
    else:
        if not project_guid.startswith("{"):
            project_guid = "{" + project_guid
        if not project_guid.endswith("}"):
            project_guid = project_guid + "}"

    # When project_version is not specified, auto-detect the current Delphi compiler version
    if not project_version:
        try:
            from ..services.config_manager import ConfigManager
            from ..services.project_settings import load_project_settings
            from ..utils.delphi_env import get_delphi_version
            from ..utils.delphi_versions import (
                normalize_version_key,
                registry_to_project_version,
            )
            # Project config of the workspace/parent directory takes priority: when creating a
            # new project under an old Delphi project directory, it should not default to the
            # ProjectVersion of the newest installed version.
            settings = load_project_settings(str(Path(project_path).parent))
            if settings and settings.delphi_version:
                project_version = registry_to_project_version(settings.delphi_version)
            cm = ConfigManager()
            if not project_version and settings and settings.compiler_version:
                compiler = cm.get_compiler(settings.compiler_version)
                if not compiler:
                    # compiler_version may also be a version number/product name
                    version_hint = normalize_version_key(settings.compiler_version)
                    if version_hint:
                        compiler = cm.get_compiler_by_registry_version(version_hint)
                if compiler and compiler.registry_version:
                    project_version = registry_to_project_version(
                        compiler.registry_version
                    )
            if not project_version:
                newest = cm.get_newest_compiler()
                if newest and newest.registry_version:
                    project_version = registry_to_project_version(newest.registry_version)
            if not project_version:
                registry_version = get_delphi_version()
                if registry_version:
                    project_version = registry_to_project_version(registry_version)
        except Exception as exc:
            logger.warning(f"Failed to auto-detect compiler version: {exc}")

    if not project_version:
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text="No Delphi ProjectVersion detected, please pass the project_version parameter",
                )
            ],
            isError=True,
        )

    if not configs:
        configs = ["Debug", "Release"]
    platforms = _coerce_platforms(platforms)
    if not platforms:
        platforms = ["Win32"]
    if namespace is None:
        namespace = _default_namespace(framework_type)

    resolved_app_type = _infer_app_type(framework_type, app_type)
    project_name = _sanitized_project_name(main_source)
    is_pkg = _is_package(resolved_app_type)

    # Determine whether to use the old format based on ProjectVersion (< 17.0 = pre-XE3 simplified format)
    try:
        project_ver = float(project_version)
    except ValueError:
        project_ver = 18.2
    old_format = project_ver < 17.0

    ET.register_namespace("", MSBUILD_NS)
    root = ET.Element(_ns("Project"))

    # ── Header PropertyGroup (basic project info) ──
    pg = ET.SubElement(root, _ns("PropertyGroup"))
    ET.SubElement(pg, _ns("ProjectGuid")).text = project_guid
    ET.SubElement(pg, _ns("MainSource")).text = main_source
    config_cond = ET.SubElement(pg, _ns("Config"))
    config_cond.set("Condition", "'$(Config)'==''")
    config_cond.text = configs[0]
    ET.SubElement(pg, _ns("ProjectVersion")).text = project_version
    ET.SubElement(pg, _ns("Base")).text = "True"
    ET.SubElement(pg, _ns("AppType")).text = resolved_app_type
    ET.SubElement(pg, _ns("FrameworkType")).text = framework_type

    primary_plat = platforms[0]
    plat_elem = ET.SubElement(pg, _ns("Platform"))
    plat_elem.set("Condition", "'$(Platform)'==''")
    plat_elem.text = primary_plat

    if old_format:
        # Old format: no TargetedPlatforms, with DCC_DCCCompiler
        if primary_plat == "Win32":
            ET.SubElement(pg, _ns("DCC_DCCCompiler")).text = "DCC32"
    else:
        # Modern format: bitmask — 1=Win32, 2=Win64, 4=OSX64, 8=iOSDevice64, ...
        targeted_mask = _compute_targeted_platforms_mask(platforms)
        ET.SubElement(pg, _ns("TargetedPlatforms")).text = str(targeted_mask)
        if primary_plat == "Win32" and resolved_app_type in ("Console", "Library"):
            ET.SubElement(pg, _ns("DCC_DCCCompiler")).text = "DCC32"

    # ── PropertyGroup inheritance hierarchy ──
    _add_property_group_hierarchy(
        root=root,
        project_name=project_name,
        configs=configs,
        namespace=namespace,
        framework_type=framework_type,
        app_type=resolved_app_type,
        platforms=platforms,
        unit_search_paths=unit_search_paths,
        old_format=old_format,
    )

    # ── ItemGroup (source file references + BuildConfiguration) ──
    ig = ET.SubElement(root, _ns("ItemGroup"))

    # DelphiCompile (also required for Package projects, see GR32_R.dproj)
    dc = ET.SubElement(ig, _ns("DelphiCompile"))
    if old_format:
        # Old format uses a literal filename (see HCL D2010, FlexCel D2007)
        dc.set("Include", main_source)
    else:
        dc.set("Include", "$(MainSource)")
    ET.SubElement(dc, _ns("MainSource")).text = "MainSource"

    if sources:
        for src in sources:
            ref = ET.SubElement(ig, _ns("DCCReference"))
            ref.set("Include", src)

    # BuildConfiguration entries (Base first, then each config)
    bc_base = ET.SubElement(ig, _ns("BuildConfiguration"))
    bc_base.set("Include", "Base")
    ET.SubElement(bc_base, _ns("Key")).text = "Base"

    cfg_keys = {configs[0]: "Cfg_1"}
    if len(configs) > 1:
        cfg_keys[configs[1]] = "Cfg_2"

    for cfg_name, cfg_key in cfg_keys.items():
        bc = ET.SubElement(ig, _ns("BuildConfiguration"))
        bc.set("Include", cfg_name)
        ET.SubElement(bc, _ns("Key")).text = cfg_key
        ET.SubElement(bc, _ns("CfgParent")).text = "Base"

    # ── ProjectExtensions ──
    # The IDE needs Borland.Personality to recognize the project type,
    # otherwise it reports "Generic.Personality is not available"
    pe = ET.SubElement(root, _ns("ProjectExtensions"))
    bp = ET.SubElement(pe, _ns("Borland.Personality"))
    bp.text = "Delphi.Personality.12"
    bproj = ET.SubElement(pe, _ns("BorlandProject"))
    dp = ET.SubElement(bproj, _ns("Delphi.Personality"))
    src_elem = ET.SubElement(dp, _ns("Source"))
    src_item = ET.SubElement(src_elem, _ns("Source"))
    src_item.set("Name", "MainSource")
    src_item.text = main_source

    if is_pkg:
        bpt = ET.SubElement(pe, _ns("Borland.ProjectType"))
        bpt.text = "Package"
    else:
        bpt = ET.SubElement(pe, _ns("Borland.ProjectType"))
        if resolved_app_type == "Library":
            bpt.text = "Library"
        elif resolved_app_type == "Console":
            bpt.text = "Application"
        else:
            bpt.text = "Application"

    if is_pkg and not old_format:
        deployment = ET.SubElement(bproj, _ns("Deployment"))
        plat_section = ET.SubElement(bproj, _ns("Platforms"))
        for p in platforms:
            p_node = ET.SubElement(plat_section, _ns("Platform"))
            p_node.set("value", p)
            p_node.text = "True"

    pe_version = ET.SubElement(pe, _ns("ProjectFileVersion"))
    pe_version.text = "12"

    # ── Import ──
    imp = ET.SubElement(root, _ns("Import"))
    imp.set("Project", "$(BDS)\\Bin\\CodeGear.Delphi.Targets")
    imp.set("Condition", "Exists('$(BDS)\\Bin\\CodeGear.Delphi.Targets')")

    imp_ut = ET.SubElement(root, _ns("Import"))
    imp_ut.set(
        "Project",
        "$(APPDATA)\\Embarcadero\\$(BDSAPPDATABASEDIR)\\$(PRODUCTVERSION)\\UserTools.proj",
    )
    imp_ut.set(
        "Condition",
        "Exists('$(APPDATA)\\Embarcadero\\$(BDSAPPDATABASEDIR)\\$(PRODUCTVERSION)\\UserTools.proj')",
    )

    if not is_pkg:
        imp_dp = ET.SubElement(root, _ns("Import"))
        imp_dp.set("Project", "$(MSBuildProjectName).deployproj")
        imp_dp.set("Condition", "Exists('$(MSBuildProjectName).deployproj')")

    tree = ET.ElementTree(root)
    _guarded_tree_write(tree, project_path, encoding="utf-8", xml_declaration=True)

    # ── Generate Form unit stub code (only when the user explicitly passes form_units) ──
    project_dir = str(Path(project_path).parent)
    generated_files: List[str] = []

    if form_units:
        # Automatically add form_units to sources (if not already included)
        sources = list(sources or [])
        names_in_sources = {Path(s).name for s in sources}
        resolved_app_type = _infer_app_type(framework_type, app_type)
        is_pkg = _is_package(resolved_app_type)

        for form_name in form_units:
            file_stem = _form_file_stem(form_name)
            pas_file = f"{file_stem}.pas"
            if pas_file not in names_in_sources:
                sources.append(pas_file)
                # Also update the already-written .dproj
                ig = root.find(f"{_ns('ItemGroup')}")
                if ig is not None:
                    ref = ET.SubElement(ig, _ns("DCCReference"))
                    ref.set("Include", pas_file)

            # Generate .pas
            pas_path = _generate_form_pas(project_dir, form_name, framework_type)
            generated_files.append(pas_path)

            # Generate .dfm/.fmx (empty Form, no components)
            dfm_path = _generate_form_dfm(project_dir, form_name, framework_type)
            generated_files.append(dfm_path)

        # Rewrite the .dproj (after updating sources)
        _guarded_tree_write(tree, project_path, encoding="utf-8", xml_declaration=True)

        # Generate .dpr (only when it does not exist)
        dpr_path = _generate_dpr(
            project_dir, main_source, form_units, framework_type, app_type,
        )
        if dpr_path not in generated_files:
            generated_files.append(dpr_path)

    generated_summary = (
        f"\nGenerated {len(generated_files)} stub files:\n"
        + "\n".join(f"  ⚡ {f}" for f in generated_files)
        if generated_files
        else ""
    )

    return CallToolResult(
        content=[
            TextContent(
                type="text",
                text=f"✅ Created .dproj file: {project_path}\n"
                f"Main source: {main_source}\n"
                f"Project type: {resolved_app_type}\n"
                f"Framework: {framework_type}\n"
                f"Configs: {', '.join(configs)}\n"
                f"Platforms: {', '.join(platforms)}\n"
                f"Source file references ({len(sources or [])}): {', '.join(sources or [])}"
                f"{generated_summary}",
            )
        ],
        isError=False,
    )


def _compute_targeted_platforms_mask(platforms: List[str]) -> int:
    """Compute the TargetedPlatforms bitmask

    As defined by Delphi/MSBuild:
      1=Win32, 2=Win64, 4=OSX32, 8=OSX64/arm64,
      16=iOSDevice32, 32=iOSDevice64, 64=iOSSimulator,
      128=Android, 256=Linux64
    """
    platform_bits = {
        "Win32": 1,
        "Win64": 2,
        "OSX32": 4,
        "OSX64": 8,
        "OSXarm64": 8,
        "iOSDevice32": 16,
        "iOSDevice64": 32,
        "iOSSimulator": 64,
        "Android": 128,
        "Android64": 128,
        "Linux64": 256,
    }
    mask = 0
    for p in platforms:
        bit = platform_bits.get(p, 1)
        mask |= bit
    return mask if mask else 1


async def _handle_info(project_path: str) -> CallToolResult:
    """Read complete .dproj file information"""
    path_obj = Path(project_path)

    # .dpr/.dpk → automatically convert to the corresponding .dproj path
    if path_obj.suffix.lower() in ('.dpr', '.dpk'):
        dproj_path = path_obj.with_suffix('.dproj')
        if dproj_path.exists():
            project_path = str(dproj_path)
        else:
            # No corresponding .dproj; return basic .dpr information
            try:
                content = path_obj.read_text(encoding='utf-8-sig', errors='replace')
            except Exception:
                content = ''
            lines_out = [
                f"📄 File: {project_path}",
                f"Status: standalone .dpr/.dpk file, no corresponding .dproj project file",
                "",
            ]
            # Extract source file type (program/library/package)
            for line in content.split('\n'):
                stripped = line.strip()
                if stripped.startswith(('program ', 'library ', 'package ')):
                    lines_out.append(f"Type: {stripped.split()[0]}")
                    break
            # Extract the uses clause
            in_uses = False
            uses_items = []
            for line in content.split('\n'):
                stripped = line.strip()
                if stripped.lower().startswith('uses'):
                    in_uses = True
                    rest = stripped[4:].strip()
                    if rest:
                        uses_items.append(rest.rstrip(';'))
                elif in_uses:
                    if ';' in stripped:
                        uses_items.append(stripped.rstrip(';'))
                        break
                    elif stripped:
                        uses_items.append(stripped)
                    else:
                        break
            if uses_items:
                uses_joined = ' '.join(uses_items)
                parts = [u.strip() for u in uses_joined.split(',') if u.strip()]
                lines_out.append(f"Referenced units ({len(parts)}): {', '.join(parts[:30])}{'...' if len(parts) > 30 else ''}")
            lines_out.append("")
            lines_out.append(f"💡 You can create the corresponding .dproj via delphi_project(action='create', project_path='{dproj_path}', main_source='{path_obj.name}')")

            return CallToolResult(
                content=[TextContent(type="text", text="\n".join(lines_out))],
                isError=False,
            )

    parser = DprojParser(project_path)
    if not parser.parse():
        return CallToolResult(
            content=[TextContent(type="text", text=f"Failed to parse .dproj: {project_path}")],
            isError=True,
        )

    info = parser.get_project_info()
    main_source = parser.get_main_source()
    platform = parser.get_target_platform()
    project_version = parser.get_project_version()
    search_paths = parser.get_unit_search_paths()
    conditional_defines = parser.get_conditional_defines()
    namespaces = parser.get_namespace()
    debugger_params = parser.get_debugger_run_params()
    build_events = parser.get_build_events()
    resources = parser.get_resource_items()

    # Read the raw XML to get the source file list
    tree = _parse(project_path)
    sources: List[str] = []
    if tree is not None:
        root = tree.getroot()
        for ig in root.findall(_ns("ItemGroup")):
            for ref in ig.findall(_ns("DCCReference")):
                inc = ref.get("Include", "")
                if inc:
                    sources.append(inc)
            for dc in ig.findall(_ns("DelphiCompile")):
                inc = dc.get("Include", "")
                if inc:
                    ms = dc.find(_ns("MainSource"))
                    tag = " [DelphiCompile]" + (f" → {ms.text}" if ms is not None else "")
                    sources.append(f"{inc}{tag}")

    # Which PropertyGroups each configuration has
    tree2 = _parse(project_path)
    config_props: List[str] = []
    if tree2 is not None:
        for pg in tree2.getroot().findall(_ns("PropertyGroup")):
            cond = pg.get("Condition", "")
            if not cond:
                continue
            props = []
            for child in pg:
                tag = child.tag.split("}")[-1]
                props.append(f"{tag}={child.text or ''}")
            config_props.append(f"  [{cond}]")
            for p in props:
                config_props.append(f"    {p}")

    lines = [
        f"📄 Project file: {project_path}",
        f"Main source: {main_source or 'N/A'}",
        f"Project GUID: {info.get('project_guid', 'N/A')}",
        f"Project version: {project_version or 'N/A'}",
        f"Framework type: {info.get('framework_type', 'N/A')}",
        f"Target platform: {platform or 'N/A'}",
        "",
        "── Build configurations ──",
    ]
    if config_props:
        lines.extend(config_props)
    else:
        lines.append("  (no conditional build configurations)")

    lines.append("")
    lines.append(f"Conditional defines: {'; '.join(conditional_defines) if conditional_defines else '(none)'}")

    if search_paths:
        lines.append(f"Unit search paths ({len(search_paths)}):")
        for p in search_paths:
            lines.append(f"  - {p}")

    lines.append(f"Namespace: {namespaces or '(none)'}")
    lines.append(f"Debugger parameters: {debugger_params or '(none)'}")

    if build_events and any(v for v in build_events.values()):
        lines.append("")
        lines.append("── Build events ──")
        event_labels = {
            "pre_build": "PreBuildEvent",
            "pre_link": "PreLinkEvent",
            "post_build": "PostBuildEvent",
        }
        for key, label in event_labels.items():
            val = build_events.get(key)
            if val:
                lines.append(f"  {label}: {val}")

    lines.append("")
    lines.append(f"── Source files ({len(sources)}) ──")
    for s in sources:
        lines.append(f"  {s}")

    if resources:
        lines.append("")
        lines.append(f"── Resource files ({len(resources)}) ──")
        for r in resources:
            lines.append(f"  {r.get('include')} → ID={r.get('resource_id')}, Type={r.get('resource_type')}")

    return CallToolResult(
        content=[TextContent(type="text", text="\n".join(lines))],
        isError=False,
    )


async def _handle_set(
    project_path: str,
    property_name: str,
    value: str,
    config: Optional[str] = None,
    platform: Optional[str] = None,
) -> CallToolResult:
    """Set a .dproj property value (create element or update existing element)"""
    if not Path(project_path).exists():
        return CallToolResult(
            content=[TextContent(type="text", text=f"File does not exist: {project_path}")],
            isError=True,
        )

    result = _parse_tree(project_path)
    if result is None:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Parse failed: {project_path}")],
            isError=True,
        )
    tree, root = result

    backup_path = _backup_file(project_path)

    groups = _find_pg(root, config=config, platform=platform)

    changed = False
    if groups:
        for group in groups:
            elem = _find_or_create(group, property_name)
            elem.text = value
            changed = True
    else:
        # No matching existing PropertyGroup; create a new one
        cond_parts = []
        if config:
            cond_parts.append(f"'$(Config)'=='{config}'")
        if platform:
            cond_parts.append(f"'$(Platform)'=='{platform}'")
        new_pg = ET.SubElement(root, _ns("PropertyGroup"))
        new_pg.set("Condition", " and ".join(cond_parts))
        ET.SubElement(new_pg, _ns(property_name)).text = value
        changed = True

    if not changed:
        return CallToolResult(
            content=[TextContent(type="text", text="No changes made")],
            isError=False,
        )

    _guarded_tree_write(tree, project_path, encoding="utf-8", xml_declaration=True)

    loc = ""
    if config or platform:
        loc = f" (Config={config}, Platform={platform})"
    return CallToolResult(
        content=[
            TextContent(
                type="text",
                text=f"✅ Set {property_name}={value}{loc}\nBackup: {backup_path}",
            )
        ],
        isError=False,
    )


async def _handle_add_config(
    project_path: str,
    config_name: str,
    base_config: Optional[str] = None,
    defines: Optional[str] = None,
    optimize: Optional[bool] = None,
    debug_info: Optional[bool] = None,
) -> CallToolResult:
    """Add a build configuration"""
    if not Path(project_path).exists():
        return CallToolResult(
            content=[TextContent(type="text", text=f"File does not exist: {project_path}")],
            isError=True,
        )

    parsed = _parse_tree(project_path)
    if parsed is None:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Parse failed: {project_path}")],
            isError=True,
        )
    tree, root = parsed

    if _find_pg(root, config=config_name):
        return CallToolResult(
            content=[TextContent(type="text", text=f"Configuration already exists: {config_name}")],
            isError=True,
        )

    backup_path = _backup_file(project_path)

    new_pg = ET.SubElement(root, _ns("PropertyGroup"))
    new_pg.set("Condition", f"'$(Config)'=='{config_name}'")

    set_count = 0

    # If base_config is given, copy its properties
    if base_config:
        base_groups = _find_pg(root, config=base_config)
        if base_groups:
            for child in base_groups[0]:
                tag_local = child.tag.split("}")[-1]
                ET.SubElement(new_pg, child.tag).text = child.text
                set_count += 1

    # Explicit parameters override the values from base_config
    if defines is not None:
        _find_or_create(new_pg, "DCC_Define").text = defines
        set_count += 1
    if optimize is not None:
        _find_or_create(new_pg, "DCC_Optimize").text = "true" if optimize else "false"
        set_count += 1
    if debug_info is not None:
        _find_or_create(new_pg, "DCC_DebugInfoInExe").text = "true" if debug_info else "false"
        set_count += 1

    _guarded_tree_write(tree, project_path, encoding="utf-8", xml_declaration=True)

    detail = f"copied from {base_config}" if base_config else f"default settings"
    return CallToolResult(
        content=[
            TextContent(
                type="text",
                text=f"✅ Added configuration: {config_name} ({detail}, {set_count} properties)\nBackup: {backup_path}",
            )
        ],
        isError=False,
    )


async def _handle_remove_config(project_path: str, config_name: str) -> CallToolResult:
    """Remove a build configuration"""
    if not Path(project_path).exists():
        return CallToolResult(
            content=[TextContent(type="text", text=f"File does not exist: {project_path}")],
            isError=True,
        )

    parsed = _parse_tree(project_path)
    if parsed is None:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Parse failed: {project_path}")],
            isError=True,
        )
    tree, root = parsed

    groups = _find_pg(root, config=config_name)
    if not groups:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Configuration not found: {config_name}")],
            isError=True,
        )

    backup_path = _backup_file(project_path)
    for group in groups:
        root.remove(group)

    _guarded_tree_write(tree, project_path, encoding="utf-8", xml_declaration=True)
    return CallToolResult(
        content=[
            TextContent(
                type="text",
                text=f"✅ Removed configuration: {config_name}\nBackup: {backup_path}",
            )
        ],
        isError=False,
    )


async def _handle_add_source(
    project_path: str,
    source_file: str,
    main_source: bool = False,
) -> CallToolResult:
    """Add a source file reference to an ItemGroup

    .dpr/.dpk files are automatically added as DelphiCompile; other files are added as DCCReference.
    Use main_source=True to force adding as DelphiCompile.
    """
    if not Path(project_path).exists():
        return CallToolResult(
            content=[TextContent(type="text", text=f"File does not exist: {project_path}")],
            isError=True,
        )

    # Path normalization: absolute path → relative path with respect to the .dproj directory
    src_path = Path(source_file)
    if src_path.is_absolute():
        try:
            source_file = os.path.relpath(
                str(src_path.resolve()),
                str(Path(project_path).parent),
            ).replace("/", "\\")
        except ValueError:
            # On different drive letters relpath raises ValueError; keep the original path
            pass
    else:
        source_file = str(src_path).replace("/", "\\")

    parsed = _parse_tree(project_path)
    if parsed is None:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Parse failed: {project_path}")],
            isError=True,
        )
    tree, root = parsed

    ig = _find_or_create_item_group(root)
    backup_path = _backup_file(project_path)

    # Auto-detect: .dpr/.dpk → DelphiCompile, others → DCCReference
    ext = Path(source_file).suffix.lower()
    is_delphi_main = main_source or ext in (".dpr", ".dpk")

    if is_delphi_main:
        # Check whether a DelphiCompile already exists
        existing_dc = ig.findall(_ns("DelphiCompile"))
        if existing_dc:
            return CallToolResult(
                content=[TextContent(type="text", text=f"❌ DelphiCompile reference already exists. A project can only have one main source file (.dpr/.dpk).\nExisting: {existing_dc[0].get('Include', '')}")],
                isError=True,
            )
        dc = ET.SubElement(ig, _ns("DelphiCompile"))
        dc.set("Include", source_file)
        ET.SubElement(dc, _ns("MainSource")).text = "MainSource"
        kind = "DelphiCompile"
        dpk_result = ""
    else:
        # Check whether a DCCReference already exists
        existing = _find_dcc_ref(ig, source_file)
        if existing:
            return CallToolResult(
                content=[TextContent(type="text", text=f"Source file already referenced: {source_file}")],
                isError=True,
            )
        ref = ET.SubElement(ig, _ns("DCCReference"))
        ref.set("Include", source_file)
        kind = "DCCReference"

        # Sync .dpk contains (if this is a Package project and a .pas was added)
        dpk_result = ""
        if ext == ".pas":
            try:
                dpk_path = _get_dpk_path_from_dproj(project_path)
                if dpk_path:
                    unit_name = Path(source_file).stem
                    dpk_backup = _dpk_add_contains(dpk_path, source_file, unit_name)
                    if dpk_backup:
                        dpk_result = f"\n✅ .dpk contains synced: {unit_name} in '{source_file}'"
                    else:
                        dpk_result = f"\nℹ️ .dpk contains already has this entry, skipped"
            except Exception as e:
                dpk_result = f"\n⚠️ .dpk contains sync failed: {e}"

    _guarded_tree_write(tree, project_path, encoding="utf-8", xml_declaration=True)
    return CallToolResult(
        content=[
            TextContent(
                type="text",
                text=f"✅ Added source file reference ({kind}): {source_file}\nBackup: {backup_path}{dpk_result}",
            )
        ],
        isError=False,
    )


async def _handle_remove_source(project_path: str, source_file: str) -> CallToolResult:
    """Remove a source file reference from an ItemGroup"""
    if not Path(project_path).exists():
        return CallToolResult(
            content=[TextContent(type="text", text=f"File does not exist: {project_path}")],
            isError=True,
        )

    parsed = _parse_tree(project_path)
    if parsed is None:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Parse failed: {project_path}")],
            isError=True,
        )
    tree, root = parsed

    backup_path = _backup_file(project_path)

    removed = False
    for ig in root.findall(_ns("ItemGroup")):
        ref = _find_dcc_ref(ig, source_file)
        if ref is not None:
            ig.remove(ref)
            removed = True

        # Also check DelphiCompile
        for dc in ig.findall(_ns("DelphiCompile")):
            inc = dc.get("Include", "")
            if inc and Path(inc).name.lower() == source_file.lower():
                ig.remove(dc)
                removed = True

    if not removed:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Source file reference not found: {source_file}")],
            isError=True,
        )

    _guarded_tree_write(tree, project_path, encoding="utf-8", xml_declaration=True)

    # Sync .dpk contains (if this is a Package project)
    dpk_result = ""
    ext = Path(source_file).suffix.lower()
    if ext == ".pas":
        try:
            dpk_path = _get_dpk_path_from_dproj(project_path)
            if dpk_path:
                dpk_backup = _dpk_remove_contains(dpk_path, source_file)
                if dpk_backup:
                    dpk_result = f"\n✅ .dpk contains removal synced"
        except Exception as e:
            dpk_result = f"\n⚠️ .dpk contains sync failed: {e}"

    return CallToolResult(
        content=[
            TextContent(
                type="text",
                text=f"✅ Removed source file reference: {source_file}\nBackup: {backup_path}{dpk_result}",
            )
        ],
        isError=False,
    )


# ──────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────

async def dproj_tool(
    action: str = "info",
    project_path: Optional[str] = None,
    main_source: Optional[str] = None,
    project_guid: Optional[str] = None,
    project_version: Optional[str] = None,
    framework_type: str = "VCL",
    app_type: Optional[str] = None,
    unit_search_paths: Optional[List[str]] = None,
    namespace: Optional[str] = None,
    configs: Optional[List[str]] = None,
    sources: Optional[List[str]] = None,
    platforms: Optional[List[str]] = None,
    target_platform: Optional[str] = None,
    property_name: Optional[str] = None,
    value: Optional[str] = None,
    config: Optional[str] = None,
    platform: Optional[str] = None,
    config_name: Optional[str] = None,
    base_config: Optional[str] = None,
    defines: Optional[str] = None,
    optimize: Optional[bool] = None,
    debug_info: Optional[bool] = None,
    source_file: Optional[str] = None,
    main_source_flag: bool = False,
    form_units: Optional[List[str]] = None,
) -> CallToolResult:
    """.dproj project file management tool entry point"""

    if not project_path and action in ("set", "add_config", "remove_config", "add_source", "remove_source"):
        return CallToolResult(
            content=[TextContent(type="text", text="❌ project_path parameter is required")],
            isError=True,
        )
    if action == "create" and not project_path:
        return CallToolResult(
            content=[TextContent(type="text", text="❌ create requires the project_path parameter")],
            isError=True,
        )

    handler_map = {
        "create": lambda: _handle_create(
            project_path=_require(project_path, "project_path"),
            main_source=_require(main_source, "main_source"),
            project_guid=project_guid,
            project_version=project_version,
            framework_type=framework_type,
            app_type=app_type,
            unit_search_paths=unit_search_paths,
            namespace=namespace,
            configs=configs,
            sources=sources,
            platforms=platforms or ([target_platform] if target_platform else ([platform] if platform else None)),
            form_units=form_units,
        ),
        "info": lambda: _handle_info(project_path=project_path or ""),
        "set": lambda: _handle_set(
            project_path=_require(project_path, "project_path"),
            property_name=_require(property_name, "property_name"),
            value=_require(value, "value"),
            config=config,
            platform=platform,
        ),
        "add_config": lambda: _handle_add_config(
            project_path=_require(project_path, "project_path"),
            config_name=_require(config_name or config, "config_name"),
            base_config=base_config,
            defines=defines,
            optimize=optimize,
            debug_info=debug_info,
        ),
        "remove_config": lambda: _handle_remove_config(
            project_path=_require(project_path, "project_path"),
            config_name=_require(config_name or config, "config_name"),
        ),
        "add_source": lambda: _handle_add_source(
            project_path=_require(project_path, "project_path"),
            source_file=_require(source_file, "source_file"),
            main_source=main_source_flag,
        ),
        "remove_source": lambda: _handle_remove_source(
            project_path=_require(project_path, "project_path"),
            source_file=_require(source_file, "source_file"),
        ),
    }

    handler = handler_map.get(action)
    if handler:
        return await handler()

    return CallToolResult(
        content=[
            TextContent(
                type="text",
                text=f"❌ Unknown action: {action}. Available: create, info, set, add_config, remove_config, add_source, remove_source",
            )
        ],
        isError=True,
    )