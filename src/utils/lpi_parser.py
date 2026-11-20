"""
LPI file parser

Parses Lazarus/Free Pascal project files (.lpi) to extract build configuration.
"""

import xml.etree.ElementTree as ET
from typing import List, Dict, Optional
from pathlib import Path
from ..utils.logger import get_logger

logger = get_logger(__name__)


class LpiParser:
    """Lazarus project file parser"""

    def __init__(self, lpi_path: str):
        """
        Initialize the parser.

        Args:
            lpi_path: .lpi file path
        """
        self.lpi_path = lpi_path
        self.tree = None
        self.root = None

    def parse(self) -> bool:
        """
        Parse the .lpi file.

        Returns:
            Whether parsing succeeded
        """
        try:
            self.tree = ET.parse(self.lpi_path)
            self.root = self.tree.getroot()
            logger.info(f"Successfully parsed .lpi file: {self.lpi_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to parse .lpi file: {str(e)}")
            return False

    def get_unit_search_paths(self, config: str = None) -> List[str]:
        """
        Get the unit search paths.

        Args:
            config: Configuration name (Default/Debug/Release)

        Returns:
            List of unit search paths
        """
        if self.root is None:
            logger.error("The .lpi file has not been parsed")
            return []

        paths = set()

        # Find CompilerOptions under PublishInfo
        compiler_options = self.root.find(".//CompilerOptions")
        if compiler_options is None:
            return []

        # Find SearchPaths
        search_paths = compiler_options.find("SearchPaths")
        if search_paths is None:
            return []

        # Read OtherUnitFiles
        other_unit_files = search_paths.find("OtherUnitFiles")
        if other_unit_files is not None and other_unit_files.text:
            for path in other_unit_files.text.split(";"):
                path = path.strip()
                if path and not path.startswith("$("):
                    if not Path(path).is_absolute():
                        project_dir = Path(self.lpi_path).parent
                        path = str((project_dir / path).resolve())
                    paths.add(path)

        # Read UnitPath
        unit_path = search_paths.find("UnitPath")
        if unit_path is not None and unit_path.text:
            for path in unit_path.text.split(";"):
                path = path.strip()
                if path and not path.startswith("$("):
                    if not Path(path).is_absolute():
                        project_dir = Path(self.lpi_path).parent
                        path = str((project_dir / path).resolve())
                    paths.add(path)

        logger.info(f"Found {len(paths)} unit search paths")
        return list(paths)

    def get_main_source(self) -> Optional[str]:
        """
        Get the main source file name (.lpr).

        Returns:
            Main source file name
        """
        if self.root is None:
            return None

        # Find MainUnit under PublishInfo
        main_unit = self.root.find(".//MainUnit")
        if main_unit is not None:
            filename = main_unit.get("Filename")
            if filename:
                return filename

        return None

    def get_project_info(self) -> Dict:
        """
        Get project information.

        Returns:
            Project information dictionary
        """
        if self.root is None:
            return {}

        info = {
            "project_name": None,
            "main_source": None,
            "unit_count": 0,
        }

        # Find ProjectInfo
        project_info = self.root.find(".//ProjectInfo")
        if project_info is not None:
            title = project_info.find("Title")
            if title is not None and title.text:
                info["project_name"] = title.text.strip()

        # Get the main source file
        info["main_source"] = self.get_main_source()

        # Count the units
        units = self.root.findall(".//Unit")
        info["unit_count"] = len(units)

        return info

    def get_units(self) -> List[Dict[str, str]]:
        """
        Get every unit of the project.

        Returns:
            Unit list; each unit carries Filename and IsPartOfProject
        """
        if self.root is None:
            return []

        units = []
        for unit_elem in self.root.findall(".//Unit"):
            filename = unit_elem.get("Filename")
            is_part = unit_elem.get("IsPartOfProject", "True")
            if filename:
                units.append({
                    "filename": filename,
                    "is_part_of_project": is_part.lower() == "true",
                })

        return units

    def get_compiler_options(self) -> Dict:
        """
        Get the compiler options.

        Returns:
            Compiler options dictionary
        """
        if self.root is None:
            return {}

        options = {
            "target_cpu": None,
            "target_os": None,
            "generate_debugging_info": False,
            "optimization_level": 0,
        }

        compiler_options = self.root.find(".//CompilerOptions")
        if compiler_options is None:
            return options

        # Target
        target = compiler_options.find("Target")
        if target is not None:
            cpu = target.find("CPU")
            if cpu is not None and cpu.text:
                options["target_cpu"] = cpu.text.strip()
            os_elem = target.find("OS")
            if os_elem is not None and os_elem.text:
                options["target_os"] = os_elem.text.strip()

        # Debugging
        debugging = compiler_options.find("Debugging")
        if debugging is not None:
            gen_debug = debugging.find("GenerateDebugInfo")
            if gen_debug is not None:
                options["generate_debugging_info"] = gen_debug.get("Value", "").lower() == "true"

        # Optimization
        optimization = compiler_options.find("Optimization")
        if optimization is not None:
            level = optimization.find("Level")
            if level is not None and level.text:
                try:
                    options["optimization_level"] = int(level.text.strip())
                except ValueError:
                    pass

        return options
