"""
.groupproj file parser

Provides unified parsing of Delphi project group files (.groupproj), shared by
compile_project and install_package.

Supported XML nodes:
  - <Projects Include="...">           (XE/XE2 legacy format, with <Dependencies>)
  - <ProjectReference Include="...">   (newer format)
  - <BuildOrder>                       (build order)
  - <Platforms>                        (list of supported platforms)
  - <Config>/<Platform>                (default configuration)
  - <PropertyGroup>/<ProjectGuid>      (project GUID)
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from ..utils.logger import get_logger

logger = get_logger(__name__)

MSBUILD_NS = "http://schemas.microsoft.com/developer/msbuild/2003"


@dataclass
class GroupProjectInfo:
    """Structured information parsed from a .groupproj"""

    # Child project paths (sorted by BuildOrder, deduplicated)
    child_projects: List[Path] = field(default_factory=list)

    # Dependency list per child project (key = file name, value = dependency file names)
    dependencies: dict[str, List[str]] = field(default_factory=dict)

    # Build order defined in BuildOrder (list of file names, may be empty)
    build_order: List[str] = field(default_factory=list)

    # Supported platforms (from the <Platforms> node)
    supported_platforms: List[str] = field(default_factory=list)

    # Default configuration (from the <Config> node)
    default_config: Optional[str] = None

    # Default platform (from the <Platform> node)
    default_platform: Optional[str] = None

    # Project GUID
    project_guid: Optional[str] = None


def _tag(ns: str, local: str) -> str:
    """Build a namespaced tag name"""
    return f"{{{ns}}}{local}"


def _find_all_with_fallback(
    root: ET.Element, ns: str, tag: str
) -> List[ET.Element]:
    """Recursively search elements both with and without the namespace (the .// prefix keeps nested children in scope)"""
    results = []
    results.extend(root.findall(f".//{_tag(ns, tag)}"))
    results.extend(root.findall(f".//{tag}"))
    return results


def parse_groupproj(
    group_path: str | Path,
) -> GroupProjectInfo:
    """
    Parse a .groupproj file and return its structured information.

    Supported XML nodes:
      - <Projects Include="..."> + <Dependencies>  (legacy format)
      - <ProjectReference Include="...">             (new format)
      - <BuildOrder>                                 (build order)
      - <Platforms>                                  (supported platforms)
      - <Config>/<Platform>                          (default configuration)
      - <PropertyGroup>/<ProjectGuid>                (project GUID)

    Args:
        group_path: .groupproj file path

    Returns:
        GroupProjectInfo structured information

    Raises:
        FileNotFoundError: The file does not exist
        ET.ParseError: XML parsing failed
    """
    group_path = Path(group_path)
    group_dir = group_path.parent

    tree = ET.parse(str(group_path))  # noqa: S318 - .groupproj is a trusted local file; XXE risk is contained
    root = tree.getroot()
    info = GroupProjectInfo()

    # -- 1. PropertyGroup / ProjectGuid --
    for pg in _find_all_with_fallback(root, MSBUILD_NS, "PropertyGroup"):
        guid_elem = pg.find(_tag(MSBUILD_NS, "ProjectGuid"))
        if guid_elem is None:
            guid_elem = pg.find("ProjectGuid")
        if guid_elem is not None and guid_elem.text:
            info.project_guid = guid_elem.text.strip()
            break

    # -- 2. Config / Platform defaults --
    for pg in _find_all_with_fallback(root, MSBUILD_NS, "PropertyGroup"):
        config_elem = pg.find(_tag(MSBUILD_NS, "Config"))
        if config_elem is None:
            config_elem = pg.find("Config")
        if config_elem is not None and config_elem.text:
            info.default_config = config_elem.text.strip()

        platform_elem = pg.find(_tag(MSBUILD_NS, "Platform"))
        if platform_elem is None:
            platform_elem = pg.find("Platform")
        if platform_elem is not None and platform_elem.text:
            info.default_platform = platform_elem.text.strip()

    # -- 3. ItemGroup -> Projects / ProjectReference (collect the child references) --
    seen: set[str] = set()
    deps_map: dict[str, List[str]] = {}

    # 3a. <Projects Include="..."> legacy format (XE/XE2)
    for proj_elem in _find_all_with_fallback(root, MSBUILD_NS, "Projects"):
        include = proj_elem.get("Include", "")
        if not include:
            continue
        child_path = (group_dir / include).resolve()
        child_key = str(child_path)
        if child_path.exists():
            if child_key not in seen:
                seen.add(child_key)
                info.child_projects.append(child_path)
            # Parse <Dependencies>
            deps_elem = proj_elem.find(_tag(MSBUILD_NS, "Dependencies"))
            if deps_elem is None:
                deps_elem = proj_elem.find("Dependencies")
            if deps_elem is not None and deps_elem.text:
                deps_map[child_path.name] = [
                    d.strip() for d in deps_elem.text.split(";") if d.strip()
                ]
        else:
            logger.warning("File referenced by the project group does not exist; skipped: %s", child_path)

    # 3b. <ProjectReference Include="..."> newer format
    for proj_elem in _find_all_with_fallback(root, MSBUILD_NS, "ProjectReference"):
        include = proj_elem.get("Include", "")
        if not include:
            continue
        child_path = (group_dir / include).resolve()
        child_key = str(child_path)
        if child_path.exists():
            if child_key not in seen:
                seen.add(child_key)
                info.child_projects.append(child_path)
        else:
            logger.warning("File referenced by the project group does not exist; skipped: %s", child_path)

    info.dependencies = deps_map

    # -- 4. BuildOrder --
    for bo in _find_all_with_fallback(root, MSBUILD_NS, "BuildOrder"):
        for ref in bo:
            text = (ref.text or "").strip()
            if text:
                info.build_order.append(text)

    # -- 5. ProjectExtensions -> Platforms --
    for pe in _find_all_with_fallback(root, MSBUILD_NS, "ProjectExtensions"):
        for bp in _find_all_with_fallback(pe, MSBUILD_NS, "BorlandProject"):
            for platforms in _find_all_with_fallback(bp, MSBUILD_NS, "Platforms"):
                for plat in _find_all_with_fallback(platforms, MSBUILD_NS, "Platform"):
                    value = plat.get("value", "")
                    if value:
                        info.supported_platforms.append(value)

    # -- 6. Sort the child projects by BuildOrder --
    _sort_by_build_order(info)

    return info


def _sort_by_build_order(info: GroupProjectInfo) -> None:
    """
    Sort the child projects by BuildOrder.

    Sorting logic:
      1. Projects listed in BuildOrder keep their declared order
      2. Projects not in BuildOrder are appended at the end
      3. If BuildOrder references a child project that does not exist, that entry is ignored
    """
    if not info.build_order or not info.child_projects:
        return

    # Build the name -> index map (order in BuildOrder)
    order_map: dict[str, int] = {}
    for i, name in enumerate(info.build_order):
        order_map[name.lower()] = i

    # Sort by BuildOrder; projects absent from it go last
    info.child_projects.sort(
        key=lambda p: order_map.get(p.name.lower(), len(info.build_order))
    )


def build_dependency_graph(info: GroupProjectInfo) -> dict[str, List[str]]:
    """
    Build the dependency graph from <Dependencies>.

    Returns {child project file name: [dependency file names]}.
    When no <Dependencies> are declared, an empty dictionary is returned.

    Args:
        info: Structured information returned by parse_groupproj

    Returns:
        Dependency graph dictionary
    """
    return info.dependencies


def topological_sort(
    info: GroupProjectInfo,
) -> List[Path]:
    """
    Topologically sort the child projects (based on <Dependencies> + <BuildOrder>).

    Sorting priority:
      1. When BuildOrder exists, use its order directly
      2. Otherwise topologically sort on <Dependencies>
      3. When neither exists, keep the original order

    Args:
        info: Structured information returned by parse_groupproj

    Returns:
        Sorted list of child project paths
    """
    # When BuildOrder exists, use it directly (already sorted)
    if info.build_order:
        return list(info.child_projects)

    # When Dependencies exist, topologically sort
    if info.dependencies:
        return _topo_sort_with_deps(info)

    # Keep the original order
    return list(info.child_projects)


def _topo_sort_with_deps(info: GroupProjectInfo) -> List[Path]:
    """Topologically sort on Dependencies"""
    # Build the name -> Path map
    name_to_path: dict[str, Path] = {}
    for p in info.child_projects:
        name_to_path[p.name.lower()] = p

    # Build the adjacency list (dependency -> dependents)
    graph: dict[str, List[str]] = {}
    for name, deps in info.dependencies.items():
        key = name.lower()
        graph.setdefault(key, [])
        for dep in deps:
            dep_key = dep.lower()
            graph.setdefault(dep_key, [])
            graph[dep_key].append(key)

    # Kahn's algorithm for the topological sort
    in_degree: dict[str, int] = {n: 0 for n in graph}
    for node, neighbors in graph.items():
        for neighbor in neighbors:
            in_degree[neighbor] = in_degree.get(neighbor, 0) + 1

    queue = deque(n for n, d in in_degree.items() if d == 0)
    sorted_names: List[str] = []

    while queue:
        node = queue.popleft()
        sorted_names.append(node)
        for neighbor in graph.get(node, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    # Convert to Path; append projects outside the graph at the end
    result: List[Path] = []
    for name in sorted_names:
        if name in name_to_path:
            result.append(name_to_path[name])

    # Append projects that are not in the dependency graph
    sorted_set = set(sorted_names)
    for p in info.child_projects:
        if p.name.lower() not in sorted_set:
            result.append(p)

    return result


def get_platform_for_project(
    info: GroupProjectInfo, fallback: str = "win32"
) -> str:
    """
    Get the default platform from a .groupproj.

    Priority:
      1. The <Platform> node
      2. The first platform in <Platforms>
      3. fallback

    Args:
        info: Structured information returned by parse_groupproj
        fallback: Default platform

    Returns:
        Platform name (lowercase)
    """
    if info.default_platform:
        return info.default_platform.lower()
    if info.supported_platforms:
        return info.supported_platforms[0].lower()
    return fallback.lower()


def get_config_for_project(
    info: GroupProjectInfo, fallback: str = "Debug"
) -> str:
    """
    Get the default configuration from a .groupproj.

    Priority:
      1. The <Config> node
      2. fallback

    Args:
        info: Structured information returned by parse_groupproj
        fallback: Default configuration

    Returns:
        Configuration name
    """
    if info.default_config:
        return info.default_config
    return fallback
