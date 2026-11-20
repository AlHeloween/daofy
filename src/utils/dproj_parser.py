"""
DPROJ file parser

Copyright (C) Jilin Province Zuoyou Software Development Co., Ltd.
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
Update & Mod By Crystalxp (Night Killer QQ:281309196)

Parse Delphi project files (.dproj) to extract build configurations
"""

import xml.etree.ElementTree as ET
from typing import List, Dict, Optional
from pathlib import Path
from ..utils.logger import get_logger

logger = get_logger(__name__)


class DprojParser:
    """Delphi project file parser"""

    # MSBuild namespace
    MSBUILD_NS = "http://schemas.microsoft.com/developer/msbuild/2003"

    def __init__(self, dproj_path: str):
        """
        Initialize parser

        Args:
            dproj_path: .dproj file path
        """
        self.dproj_path = dproj_path
        self.tree = None
        self.root = None

    def parse(self) -> bool:
        """
        Parse the .dproj file

        Returns:
            Whether parsing succeeded
        """
        try:
            self.tree = ET.parse(self.dproj_path)
            self.root = self.tree.getroot()
            logger.info(f"Successfully parsed .dproj file: {self.dproj_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to parse .dproj file: {str(e)}")
            return False

    def _find_element(self, parent: ET.Element, tag: str) -> Optional[ET.Element]:
        """
        Find element (with namespace)

        Args:
            parent: parent element
            tag: tag name

        Returns:
            Found element, or None if not found
        """
        full_tag = f"{{{self.MSBUILD_NS}}}{tag}"
        return parent.find(full_tag)

    def _find_all_elements(self, parent: ET.Element, tag: str) -> List[ET.Element]:
        """
        Find all elements (with namespace)

        Args:
            parent: parent element
            tag: tag name

        Returns:
            List of found elements
        """
        full_tag = f"{{{self.MSBUILD_NS}}}{tag}"
        return parent.findall(full_tag)

    def get_unit_search_paths(self, config: str = None, platform: str = None) -> List[str]:
        """
        Get unit search paths

        Args:
            config: configuration name (Debug/Release etc.); if None, get all configurations
            platform: platform name (Win32/Win64); if None, get all platforms

        Returns:
            List of unit search paths
        """
        if self.root is None:
            logger.error("Unparsed .dproj file")
            return []

        paths = set()

        # Iterate over all PropertyGroups
        for prop_group in self._find_all_elements(self.root, "PropertyGroup"):
            # Check configuration and platform conditions
            condition = prop_group.get("Condition", "")

            # If config or platform is specified, check whether the condition matches
            if config or platform:
                # Check platform conditions
                if platform:
                    # Support multiple platform condition formats
                    platform_patterns = [
                        f"'$(Platform)'=='{platform}'",
                        f"'$(Base_{platform})'!=''",
                        f"'$(Cfg_1_{platform})'!=''",
                        f"'$(Cfg_2_{platform})'!=''",
                        f"'$(Cfg_3_{platform})'!=''"
                    ]
                    if not any(pattern in condition for pattern in platform_patterns):
                        continue

                # Check configuration conditions
                if config:
                    config_patterns = [
                        f"'$(Config)'=='{config}'",
                        f"'$(Cfg_1)'!=''" if config == "Debug" else "",
                        f"'$(Cfg_2)'!=''" if config == "Release" else "",
                        f"'$(Cfg_3)'!=''" if config == "Dev" else ""
                    ]
                    config_patterns = [p for p in config_patterns if p]  # Remove empty strings
                    if not any(pattern in condition for pattern in config_patterns):
                        continue

            # Find DCC_UnitSearchPath element
            unit_search_path_elem = self._find_element(prop_group, "DCC_UnitSearchPath")
            if unit_search_path_elem is not None and unit_search_path_elem.text:
                # Split paths (semicolon-separated)
                path_str = unit_search_path_elem.text.strip()
                for path in path_str.split(';'):
                    path = path.strip()
                    if path and not path.startswith('$('):  # Ignore MSBuild variables
                        # Convert relative paths to absolute paths
                        if not Path(path).is_absolute():
                            project_dir = Path(self.dproj_path).parent
                            path = str((project_dir / path).resolve())
                        paths.add(path)

        logger.info(f"Found {len(paths)} unit search paths")
        return list(paths)

    def get_namespace(self, config: str = None, platform: str = None) -> List[str]:
        """
        Get namespaces

        Args:
            config: configuration name
            platform: platform name

        Returns:
            List of namespaces
        """
        if self.root is None:
            return []

        namespaces = set()

        for prop_group in self._find_all_elements(self.root, "PropertyGroup"):
            condition = prop_group.get("Condition", "")

            if config or platform:
                if config and f"'$(Config)'=='{config}'" not in condition:
                    continue
                if platform and f"'$(Platform)'=='{platform}'" not in condition:
                    continue

            namespace_elem = self._find_element(prop_group, "DCC_Namespace")
            if namespace_elem is not None and namespace_elem.text:
                ns_str = namespace_elem.text.strip()
                for ns in ns_str.split(';'):
                    ns = ns.strip()
                    if ns and not ns.startswith('$('):
                        namespaces.add(ns)

        return list(namespaces)

    def get_build_events(self, config: str = None, platform: str = None) -> dict:
        """
        Get build events

        Args:
            config: configuration name
            platform: platform name

        Returns:
            Build events dictionary containing PreBuildEvent, PreLinkEvent and PostBuildEvent
        """
        if self.root is None:
            return {}

        events = {
            'pre_build': None,
            'pre_link': None,
            'post_build': None,
            'pre_build_ignore_exit_code': False,
            'pre_link_ignore_exit_code': False,
            'post_build_ignore_exit_code': False,
            'post_build_execute_when': None
        }

        for prop_group in self._find_all_elements(self.root, "PropertyGroup"):
            condition = prop_group.get("Condition", "")

            if config or platform:
                if config and f"'$(Config)'=='{config}'" not in condition:
                    continue
                if platform and f"'$(Platform)'=='{platform}'" not in condition:
                    continue

            # PreBuildEvent
            pre_build_elem = self._find_element(prop_group, "PreBuildEvent")
            if pre_build_elem is not None and pre_build_elem.text:
                events['pre_build'] = pre_build_elem.text.strip()

            # PreLinkEvent
            pre_link_elem = self._find_element(prop_group, "PreLinkEvent")
            if pre_link_elem is not None and pre_link_elem.text:
                events['pre_link'] = pre_link_elem.text.strip()

            # PostBuildEvent
            post_build_elem = self._find_element(prop_group, "PostBuildEvent")
            if post_build_elem is not None and post_build_elem.text:
                events['post_build'] = post_build_elem.text.strip()

            # PreBuildEventIgnoreExitCode
            pre_ignore_elem = self._find_element(prop_group, "PreBuildEventIgnoreExitCode")
            if pre_ignore_elem is not None and pre_ignore_elem.text:
                events['pre_build_ignore_exit_code'] = pre_ignore_elem.text.strip().lower() == 'true'

            # PreLinkEventIgnoreExitCode
            pre_link_ignore_elem = self._find_element(prop_group, "PreLinkEventIgnoreExitCode")
            if pre_link_ignore_elem is not None and pre_link_ignore_elem.text:
                events['pre_link_ignore_exit_code'] = pre_link_ignore_elem.text.strip().lower() == 'true'

            # PostBuildEventIgnoreExitCode
            post_ignore_elem = self._find_element(prop_group, "PostBuildEventIgnoreExitCode")
            if post_ignore_elem is not None and post_ignore_elem.text:
                events['post_build_ignore_exit_code'] = post_ignore_elem.text.strip().lower() == 'true'

            # PostBuildEventExecuteWhen
            post_when_elem = self._find_element(prop_group, "PostBuildEventExecuteWhen")
            if post_when_elem is not None and post_when_elem.text:
                events['post_build_execute_when'] = post_when_elem.text.strip()

        return events

    def get_output_path(self, config: str = None, platform: str = None) -> Optional[str]:
        """
        Get output path (DCC_ExeOutput)

        Args:
            config: configuration name
            platform: platform name

        Returns:
            Output path
        """
        return self._get_config_path("DCC_ExeOutput", config, platform)

    def get_dcu_output_path(self, config: str = None, platform: str = None) -> Optional[str]:
        """
        Get DCU output path (DCC_DcuOutput)

        Args:
            config: configuration name
            platform: platform name

        Returns:
            DCU output path
        """
        return self._get_config_path("DCC_DcuOutput", config, platform)

    def _get_config_path(self, tag: str, config: str = None, platform: str = None) -> Optional[str]:
        """Generic: read the path of the specified tag from PropertyGroup, substitute variables, and convert to an absolute path."""
        if self.root is None:
            return None

        for prop_group in self._find_all_elements(self.root, "PropertyGroup"):
            condition = prop_group.get("Condition", "")

            if config or platform:
                if config and f"'$(Config)'=='{config}'" not in condition:
                    continue
                if platform and f"'$(Platform)'=='{platform}'" not in condition:
                    continue

            elem = self._find_element(prop_group, tag)
            if elem is not None and elem.text:
                path = elem.text.strip()
                if '$(Platform)' in path and platform:
                    path = path.replace('$(Platform)', platform)
                if '$(Config)' in path and config:
                    path = path.replace('$(Config)', config)
                if not Path(path).is_absolute():
                    project_dir = Path(self.dproj_path).parent
                    path = str((project_dir / path).resolve())
                return path

        return None

    def get_conditional_defines(self, config: str = None, platform: str = None) -> List[str]:
        """
        Get conditional compilation symbols

        Args:
            config: configuration name
            platform: platform name

        Returns:
            List of conditional compilation symbols
        """
        if self.root is None:
            return []

        defines = set()

        for prop_group in self._find_all_elements(self.root, "PropertyGroup"):
            condition = prop_group.get("Condition", "")

            if config or platform:
                if config and f"'$(Config)'=='{config}'" not in condition:
                    continue
                if platform and f"'$(Platform)'=='{platform}'" not in condition:
                    continue

            defines_elem = self._find_element(prop_group, "DCC_Define")
            if defines_elem is not None and defines_elem.text:
                define_str = defines_elem.text.strip()
                for define in define_str.split(';'):
                    define = define.strip()
                    if define and not define.startswith('$('):
                        defines.add(define)

        return list(defines)

    def get_main_source(self) -> Optional[str]:
        """
        Get main source file name

        Returns:
            Main source file name (.dpr file name)
        """
        if self.root is None:
            return None

        for prop_group in self._find_all_elements(self.root, "PropertyGroup"):
            main_source_elem = self._find_element(prop_group, "MainSource")
            if main_source_elem is not None and main_source_elem.text:
                return main_source_elem.text.strip()

        return None

    def get_project_info(self) -> Dict:
        """
        Get project information

        Returns:
            Project information dictionary
        """
        if self.root is None:
            return {}

        info = {
            "project_guid": None,
            "project_version": None,
            "framework_type": None,
            "app_type": None,
            "main_source": None,
            "targeted_platforms": None
        }

        for prop_group in self._find_all_elements(self.root, "PropertyGroup"):
            # Read only the first PropertyGroup (usually contains basic information)
            if prop_group.get("Condition"):
                continue

            for key in info.keys():
                elem = self._find_element(prop_group, key.title().replace("_", ""))
                if elem is not None and elem.text:
                    info[key] = elem.text.strip()

            # Special handling for MainSource
            if info["main_source"] is None:
                main_source_elem = self._find_element(prop_group, "MainSource")
                if main_source_elem is not None and main_source_elem.text:
                    info["main_source"] = main_source_elem.text.strip()

        return info

    def get_project_version(self) -> Optional[str]:
        """
        Get project version number

        Returns:
            Project version number (e.g. "19.2"), or None if not found
        """
        info = self.get_project_info()
        return info.get("project_version")

    def is_file_in_project(self, file_name: str) -> bool:
        """
        Check whether a file belongs to the project

        Args:
            file_name: file name (without path)

        Returns:
            Whether the file belongs to the project
        """
        if self.root is None:
            return False

        # Check DCCReference in ItemGroup
        for item_group in self._find_all_elements(self.root, "ItemGroup"):
            for dcc_ref in self._find_all_elements(item_group, "DCCReference"):
                include = dcc_ref.get("Include", "")
                if include:
                    # Extract file name
                    ref_file_name = Path(include).name
                    if ref_file_name.lower() == file_name.lower():
                        return True

        # Check main source file
        main_source = self.get_main_source()
        if main_source and Path(main_source).name.lower() == file_name.lower():
            return True

        return False

    def get_debugger_run_params(self, config: str = None, platform: str = None) -> Optional[str]:
        """
        Get debugger run parameters (Debugger_RunParams).
        Corresponds to Project > Options > Debugger > Parameters in the IDE.

        Args:
            config: configuration name (Debug/Release/Dev)
            platform: platform name (Win32/Win64)

        Returns:
            Parameter string, or None if not found
        """
        if self.root is None:
            return None

        for prop_group in self._find_all_elements(self.root, "PropertyGroup"):
            condition = prop_group.get("Condition", "")

            if config and f"'$(Config)'=='{config}'" not in condition:
                continue
            if platform and f"'$(Platform)'=='{platform}'" not in condition:
                continue

            params_elem = self._find_element(prop_group, "Debugger_RunParams")
            if params_elem is not None and params_elem.text:
                return params_elem.text.strip()

        # If no matching configuration is found, try the first non-empty value
        for prop_group in self._find_all_elements(self.root, "PropertyGroup"):
            params_elem = self._find_element(prop_group, "Debugger_RunParams")
            if params_elem is not None and params_elem.text:
                return params_elem.text.strip()

        return None

    def get_resource_items(self) -> List[Dict[str, str]]:
        """
        Get all resource references (RcItem entries) in the project.
        
        .dproj format:
          <RcItem Include="templates/markdown.html">
            <ContainerId>ResourceItem</ContainerId>
            <ResourceType>RCDATA</ResourceType>
            <ResourceId>Markdown</ResourceId>
          </RcItem>
        
        Returns:
            List of resource items, each containing:
              - include: source file path (relative to .dproj directory)
              - source_path: absolute source file path
              - resource_id: resource ID
              - resource_type: resource type
        """
        if self.root is None:
            return []
        
        project_dir = Path(self.dproj_path).parent
        resources: List[Dict[str, str]] = []
        
        for item_group in self._find_all_elements(self.root, "ItemGroup"):
            for rc_item in self._find_all_elements(item_group, "RcItem"):
                include = rc_item.get("Include", "")
                if not include:
                    continue
                
                resource_id = ""
                resource_type = ""
                
                for child in rc_item:
                    tag = child.tag
                    if '}ResourceId' in tag and child.text:
                        resource_id = child.text.strip()
                    elif '}ResourceType' in tag and child.text:
                        resource_type = child.text.strip()
                
                source_path = str((project_dir / include).resolve())
                
                resources.append({
                    "include": include,
                    "source_path": source_path,
                    "resource_id": resource_id,
                    "resource_type": resource_type,
                })
        
        return resources

    def get_target_platform(self) -> Optional[str]:
        """
        Read target platform from .dproj file.
        
        Find <Platform> element in PropertyGroup, return the first non-empty value.
        Typical .dproj format:
          <PropertyGroup Condition="'$(Base)'!=''">
            <Platform>Win64</Platform>
          </PropertyGroup>
        
        All platforms supported by Delphi:
          Win32, Win64, OSX64, OSXARM64,
          iOSDevice64, iOSDevice, iOSSimulator,
          Android, Android64, Linux64
        
        Returns:
            Platform name (e.g. "Win64", "Android"), or None if not found
        """
        VALID_PLATFORMS = {
            'Win32', 'Win64', 'OSX64', 'OSXARM64',
            'iOSDevice64', 'iOSDevice', 'iOSSimulator',
            'Android', 'Android64', 'Linux64',
        }
        if self.root is None:
            return None

        for prop_group in self._find_all_elements(self.root, "PropertyGroup"):
            platform_elem = self._find_element(prop_group, "Platform")
            if platform_elem is not None and platform_elem.text:
                platform = platform_elem.text.strip()
                if platform in VALID_PLATFORMS:
                    return platform

        return None


def resolve_target_platform_from_dproj(project_path: str, default_platform: str = "win32") -> str:
    """
    Parse target platform from .dproj file, return default on failure.
    
    Encapsulates common try/parse/get_target_platform/fallback logic,
    avoiding duplicate code in compile_project.py and get_args.py.
    
    Args:
        project_path: .dproj file path
        default_platform: default platform when not found
        
    Returns:
        Platform name in lowercase, e.g. "win32", "android", "linux64"
    """
    try:
        parser = DprojParser(project_path)
        if parser.parse():
            platform = parser.get_target_platform()
            if platform:
                return platform.lower()
    except Exception as e:
        logger.debug("Ignoring non-fatal exception: %s", str(e))
    return default_platform