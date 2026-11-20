"""
Unit dependency analyzer

版权所有 (C) 吉林省左右软件开发有限公司
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
Update & Mod By Crystalxp (黑夜杀手 QQ:281309196)

Analyzes unit dependencies of a Delphi project and resolves the library paths it needs.
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
import json

from ..constants import DEPENDENCY_SCAN_EXCLUDED_DIRS
from ..utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class UnitInfo:
    """Unit information"""
    name: str  # Unit name (such as 'Classes' or 'System.Classes')
    full_name: str  # Full name
    file_path: Optional[str] = None  # File path
    is_namespace: bool = False  # Whether this is a namespace unit (such as System.Classes)
    
    def __hash__(self):
        return hash(self.name.lower())
    
    def __eq__(self, other):
        if isinstance(other, UnitInfo):
            return self.name.lower() == other.name.lower()
        return False


@dataclass
class ProjectDependencies:
    """Project dependency information"""
    project_path: str
    units: Set[UnitInfo] = field(default_factory=set)  # Units referenced directly by the project
    missing_units: Set[str] = field(default_factory=set)  # Units that could not be found
    resolved_paths: Dict[str, str] = field(default_factory=dict)  # Unit name -> file path
    
    def get_unit_names(self) -> Set[str]:
        """Get all unit names (lowercase)"""
        return {u.name.lower() for u in self.units}


class UnitDependencyAnalyzer:
    """Unit dependency analyzer"""
    
    def __init__(self):
        self.file_extensions = {'.pas', '.dpr', '.dpk'}
        # Cache: path -> {unit name -> file path}
        self._path_cache: Dict[str, Dict[str, str]] = {}
        
    def analyze_project(self, project_path: str, 
                       search_paths: Optional[List[str]] = None) -> ProjectDependencies:
        """
        Analyze project dependencies.

        Args:
            project_path: Project file path (.dpr or .dproj)
            search_paths: Additional search paths
            
        Returns:
            Project dependency information
        """
        project_path_obj = Path(project_path)
        deps = ProjectDependencies(project_path=str(project_path_obj))
        
        # Get the project directory
        project_dir = project_path_obj.parent
        
        # 1. Collect all source files in the project
        source_files = self._collect_source_files(project_dir, project_path_obj)
        logger.info(f"Found {len(source_files)} source files")
        
        # 2. Extract every referenced unit
        all_units: Set[UnitInfo] = set()
        for source_file in source_files:
            units = self._extract_uses_from_file(source_file)
            all_units.update(units)
        
        deps.units = all_units
        logger.info(f"Project references {len(all_units)} units")
        
        # 3. Resolve unit locations
        self._resolve_unit_locations(deps, search_paths or [])
        
        return deps
    
    def _collect_source_files(self, project_dir: Path, project_file: Path) -> List[Path]:
        """Collect the source files of the project"""
        source_files = []
        
        # Add the project file itself first
        if project_file.suffix.lower() in self.file_extensions:
            source_files.append(project_file)
        
        # Recursively find every source file under the project directory
        for ext in self.file_extensions:
            for file_path in project_dir.rglob(f"*{ext}"):
                # Exclude a few common directories
                if self._should_include_file(file_path, project_dir):
                    source_files.append(file_path)
        
        return source_files
    
    def _should_include_file(self, file_path: Path, project_dir: Path) -> bool:
        """Decide whether this file should be included"""
        # Convert to a relative path
        try:
            rel_path = file_path.relative_to(project_dir)
            rel_str = str(rel_path).lower()
            
            # Excluded directories
            exclude = DEPENDENCY_SCAN_EXCLUDED_DIRS
            
            parts = rel_str.split(os.sep)
            for part in parts[:-1]:  # Exclude the file name
                if part in exclude:
                    return False
            
            return True
        except ValueError:
            return True
    
    def _extract_uses_from_file(self, file_path: Path) -> Set[UnitInfo]:
        """Extract the units of the uses clause from a file"""
        units = set()
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Skip files that are too large (possibly binary or abnormal)
            if len(content) > 10 * 1024 * 1024:  # 10MB
                logger.warning(f"Skipping oversized file: {file_path} ({len(content)} bytes)")
                return units
            
            # Match the uses clause (multi-line supported)
            # Match the unit list following uses, up to the semicolon
            uses_pattern = r'\buses\s+([^;]+);'
            matches = re.findall(uses_pattern, content, re.IGNORECASE | re.DOTALL)
            
            for match in matches:
                # Strip comments
                match = re.sub(r'\{[^}]*\}', '', match)  # Remove {comment}
                match = re.sub(r'\(\*[^\*]*\*\)', '', match)  # Remove (*comment*)
                match = re.sub(r'//.*$', '', match, flags=re.MULTILINE)  # Remove //comment
                
                # Split the unit names
                unit_names = [u.strip() for u in match.split(',') if u.strip()]
                
                for unit_name in unit_names:
                    # Validate the unit name
                    if not self._is_valid_unit_name(unit_name):
                        continue
                    
                    # Handle namespaces (such as System.Classes)
                    is_namespace = '.' in unit_name
                    simple_name = unit_name.split('.')[-1] if is_namespace else unit_name
                    
                    unit_info = UnitInfo(
                        name=simple_name,
                        full_name=unit_name,
                        is_namespace=is_namespace
                    )
                    units.add(unit_info)
            
        except Exception as e:
            logger.warning(f"Failed to extract uses from {file_path}: {e}")
        
        return units
    
    def _is_valid_unit_name(self, name: str) -> bool:
        """
        Check that this is a valid Pascal unit name.

        Valid unit name rules:
        - Must start with a letter or an underscore
        - May contain only letters, digits and underscores
        - Must not contain spaces or special characters
        - Must not be a common English word (non-Delphi keyword)
        """
        if not name:
            return False
        
        # Strip quotes and the 'in' keyword (handles "in 'filename'")
        name = name.strip().strip("'\"")
        if name.lower().startswith('in '):
            return False
        
        # Check for invalid characters
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*(\.[a-zA-Z_][a-zA-Z0-9_]*)*$', name):
            return False
        
        # Check the length limit
        if len(name) > 64:
            return False
        
        # Check for junk text (common English word combinations)
        name_lower = name.lower()
        garbage_patterns = [
            'the', 'first', 'second', 'third', 'pointer', 'block', 'free',
            'reserved', 'list', 'memory', 'stack', 'heap', 'address',
            'null', 'void', 'integer', 'string', 'char', 'byte', 'word',
            'error', 'warning', 'debug', 'info', 'exception', 'failed'
        ]
        
        # Skip a very short name that is a common word
        if len(name_lower) <= 3 and name_lower in (
            'the', 'for', 'var', 'end', 'not', 'and', 'or', 'but', 'out', 'log',
            'sys', 'obj', 'ini', 'cfg', 'app', 'msg', 'err', 'dbg'
        ):
            return False
        
        # A name made of several long lowercase words is junk text
        parts = name_lower.split('.')
        for part in parts:
            if len(part) > 20:
                return False
        
        return True
    
    def _resolve_unit_locations(self, deps: ProjectDependencies, 
                                additional_paths: List[str]):
        """Resolve unit locations"""
        unit_names = deps.get_unit_names()
        
        # 1. Check the project directory itself first
        project_dir = Path(deps.project_path).parent
        self._scan_path_for_units(project_dir, unit_names, deps, "project directory")
        
        # 2. Check the additional search paths
        for path in additional_paths:
            if Path(path).exists():
                self._scan_path_for_units(Path(path), unit_names, deps, f"search path: {path}")
        
        # 3. Record the units that were not found
        found_units = {u.lower() for u in deps.resolved_paths.keys()}
        deps.missing_units = {u for u in unit_names if u.lower() not in found_units}
        
        if deps.missing_units:
            logger.warning(f"{len(deps.missing_units)} units not found: {list(deps.missing_units)[:10]}")
    
    def _scan_path_for_units(self, path: Path, target_units: Set[str], 
                             deps: ProjectDependencies, source: str):
        """Scan a path for units"""
        path_str = str(path)
        
        # Use the cache
        if path_str in self._path_cache:
            cached_units = self._path_cache[path_str]
            for unit_name in target_units:
                if unit_name.lower() in cached_units and unit_name.lower() not in deps.resolved_paths:
                    deps.resolved_paths[unit_name] = cached_units[unit_name.lower()]
            return
        
        # Scan the directory
        unit_map: Dict[str, str] = {}
        
        try:
            for file_path in path.rglob("*.pas"):
                unit_name = file_path.stem.lower()
                if unit_name not in unit_map:
                    unit_map[unit_name] = str(file_path)
                
                # Check whether this is a target unit
                if unit_name in target_units and unit_name not in deps.resolved_paths:
                    deps.resolved_paths[unit_name] = str(file_path)
                    logger.debug(f"Found unit {unit_name} in {source}: {file_path}")
        except Exception as e:
            logger.warning(f"Failed to scan path {path}: {e}")
        
        # Cache the result
        self._path_cache[path_str] = unit_map


class SmartLibraryPathResolver:
    """Smart library path resolver

    Priority order (highest first):
    1. Units in the project directory (highest priority)
    2. Units introduced later among the global library paths (override earlier ones)
    3. Paths the user passes explicitly (smart analysis is skipped entirely)
    """
    
    def __init__(self, thirdparty_kb_service=None):
        self.analyzer = UnitDependencyAnalyzer()
        self.thirdparty_kb_service = thirdparty_kb_service
        
    def resolve_library_paths(self, project_path: str, 
                             platform: str = "Win32",
                             user_search_paths: Optional[List[str]] = None,
                             version: Optional[str] = None) -> Tuple[List[str], Dict]:
        """
        Smart resolution of the library paths a project needs.

        Args:
            project_path: Project file path
            platform: Target platform
            user_search_paths: Search paths the user passes explicitly (returned as-is when provided)
            version: Delphi registry version number (such as "23.0"), used to filter third-party
                library paths by compiler version; when None the newest installed version is used
                (consistent with the default behaviour when no compiler is specified)
            
        Returns:
            (list of required library paths, detail dictionary)
        """
        # When the user passes paths explicitly, use them and skip the analysis
        if user_search_paths:
            logger.info(f"User supplied {len(user_search_paths)} explicit paths; skipping smart analysis")
            return user_search_paths, {
                "mode": "user_provided",
                "total_paths": len(user_search_paths),
                "paths": user_search_paths
            }
        
        logger.info(f"Starting smart resolution of project library paths: {project_path}")
        
        # 1. Analyze project dependencies
        deps = self.analyzer.analyze_project(project_path)
        
        info = {
            "total_units": len(deps.units),
            "missing_units_before": len(deps.missing_units),
            "missing_unit_names": list(deps.missing_units),
        }
        
        # 2. Get every third-party library path (filtered by version, like the RTL path policy)
        if self.thirdparty_kb_service:
            all_thirdparty_paths = self.thirdparty_kb_service.get_library_paths(version)
        else:
            # Without a service, use the global function
            from ..services.knowledge_base.thirdparty_knowledge_base import ThirdPartyKnowledgeBase
            kb = ThirdPartyKnowledgeBase()
            all_thirdparty_paths = kb.get_library_paths(version)
        
        logger.info(f"Global third-party library path count: {len(all_thirdparty_paths)}")
        
        # 3. Scan every path and build the unit -> path map
        # Priority: project directory > later global paths (later ones override earlier ones)
        project_dir = Path(project_path).parent
        unit_to_path: Dict[str, Tuple[str, int]] = {}  # Unit name -> (path, priority)
        
        # Scan the project directory first (highest priority = 0)
        if deps.missing_units:
            project_units = self._scan_path_for_units_with_priority(
                str(project_dir), deps.missing_units, priority=0
            )
            for unit, path in project_units.items():
                unit_to_path[unit] = (path, 0)
            logger.info(f"The project directory provided {len(project_units)} units")
        
        # Then scan the global library paths (priority increases; later ones override earlier ones)
        remaining_units = deps.missing_units - set(unit_to_path.keys())
        
        for idx, lib_path in enumerate(all_thirdparty_paths):
            if not remaining_units:
                break
            
            # Priority starts at 1 and increases; later entries outrank earlier ones
            priority = idx + 1
            found_units = self._scan_path_for_units_with_priority(
                lib_path, remaining_units, priority=priority
            )
            
            for unit, path in found_units.items():
                # Overwrite an existing unit only when the new priority is >= the old one
                if unit not in unit_to_path or priority >= unit_to_path[unit][1]:
                    unit_to_path[unit] = (path, priority)
                    remaining_units.discard(unit)
        
        # 4. Collect the required paths (deduplicated, in introduction order)
        # Group the paths by priority
        priority_to_paths: Dict[int, Set[str]] = defaultdict(set)
        for unit, (path, priority) in unit_to_path.items():
            priority_to_paths[priority].add(path)
        
        # Sort by priority (0 first, then 1, 2, 3 ...)
        needed_paths = []
        seen_paths = set()
        for priority in sorted(priority_to_paths.keys()):
            for path in priority_to_paths[priority]:
                if path not in seen_paths:
                    needed_paths.append(path)
                    seen_paths.add(path)
        
        resolved_units = set(unit_to_path.keys())
        
        info.update({
            "mode": "smart_resolve",
            "needed_paths_count": len(needed_paths),
            "total_paths_count": len(all_thirdparty_paths),
            "resolved_units": len(resolved_units),
            "still_missing": len(remaining_units),
            "still_missing_units": sorted(remaining_units),
            "selected_paths": needed_paths,
            "unit_to_path": {u: p[0] for u, p in unit_to_path.items()},
        })
        
        logger.info(f"Smart resolution complete: selected {len(needed_paths)} of "
                   f"{len(all_thirdparty_paths)} paths, "
                   f"resolved {len(resolved_units)} unit dependencies, "
                   f"{len(remaining_units)} still missing")
        
        return needed_paths, info
    
    def _scan_path_for_units_with_priority(self, path: str, 
                                           target_units: Set[str],
                                           priority: int) -> Dict[str, str]:
        """
        Scan a path for target units and return a unit name -> path map.

        Args:
            path: Path to scan
            target_units: Set of target units
            priority: Priority (for logging)
            
        Returns:
            Map of found units {unit name: path}
        """
        found = {}
        path_obj = Path(path)
        
        if not path_obj.exists():
            return found
        
        try:
            for file_path in path_obj.rglob("*.pas"):
                unit_name = file_path.stem.lower()
                if unit_name in target_units:
                    found[unit_name] = str(path)
                    logger.debug(f"[priority {priority}] Found unit {unit_name}: {path}")
        except Exception as e:
            logger.warning(f"Failed to scan path {path}: {e}")
        
        return found
    
    def generate_response_file(self, project_path: str, 
                               unit_paths: List[str]) -> str:
        """
        Generate a response file (works around an over-long command line).

        Args:
            project_path: Project path
            unit_paths: List of unit search paths
            
        Returns:
            Response file path
        """
        project_dir = Path(project_path).parent
        response_file = project_dir / "__compile_response__.txt"
        
        with open(response_file, 'w', encoding='utf-8') as f:
            f.write(f"-U{';'.join(unit_paths)}\n")
        
        logger.info(f"Generated response file: {response_file}")
        return str(response_file)


def analyze_project_units(project_path: str) -> Dict:
    """
    Convenience function that analyzes the units of a project.

    Args:
        project_path: Project file path
        
    Returns:
        Analysis result dictionary
    """
    analyzer = UnitDependencyAnalyzer()
    deps = analyzer.analyze_project(project_path)
    
    return {
        "project": project_path,
        "total_units": len(deps.units),
        "units": sorted([u.name for u in deps.units]),
        "missing_units": sorted(deps.missing_units),
        "resolved_units": deps.resolved_paths,
    }


def smart_resolve_library_paths(project_path: str, 
                                platform: str = "Win32",
                                user_search_paths: Optional[List[str]] = None,
                                version: Optional[str] = None) -> Tuple[List[str], Dict]:
    """
    Convenience function that smart-resolves library paths.

    Args:
        project_path: Project file path
        platform: Target platform
        user_search_paths: Search paths the user passes explicitly (returned as-is when provided)
        version: Delphi registry version number (such as "23.0") used to filter third-party
            library paths by compiler version
        
    Returns:
        (list of required library paths, details)
    """
    resolver = SmartLibraryPathResolver()
    return resolver.resolve_library_paths(project_path, platform, user_search_paths, version)
