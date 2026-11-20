"""
Compile request models

Defines the data models related to compile requests.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


def _validate_extra_args(extra_args: List[str]) -> None:
    """Validate the extra compile arguments supplied by the user."""
    if not isinstance(extra_args, list):
        raise ValueError("Extra compile arguments must be a list of strings")
    if any(not isinstance(arg, str) or not arg.strip() for arg in extra_args):
        raise ValueError("Extra compile arguments must be non-empty strings")


class TargetPlatform(Enum):
    """Target platform enum (cross-compilation targets supported by Delphi)"""
    WIN32 = "win32"
    WIN64 = "win64"
    OSX64 = "osx64"
    OSXARM64 = "osxarm64"
    IOSDEVICE64 = "iosdevice64"
    IOSDEVICE = "iosdevice"
    IOSSIMULATOR = "iossimulator"
    ANDROID = "android"
    ANDROID64 = "android64"
    LINUX64 = "linux64"


class OutputType(Enum):
    """Output type enum"""
    CONSOLE = "console"
    GUI = "gui"
    DLL = "dll"


class RuntimeLibrary(Enum):
    """Runtime library linking mode enum"""
    STATIC = "static"
    DYNAMIC = "dynamic"


@dataclass
class CompileOptions:
    """Compile options"""
    target_platform: TargetPlatform = TargetPlatform.WIN32
    output_path: Optional[str] = None
    compiler_version: Optional[str] = None
    timeout: int = 600
    conditional_defines: List[str] = field(default_factory=list)
    unit_search_paths: List[str] = field(default_factory=list)
    resource_search_paths: List[str] = field(default_factory=list)
    optimize: bool = True
    debug: bool = False
    warning_level: int = 2
    disabled_warnings: List[str] = field(default_factory=list)
    output_type: OutputType = OutputType.GUI
    runtime_library: RuntimeLibrary = RuntimeLibrary.STATIC
    build_configuration: Optional[str] = None
    extra_args: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Validate fields"""
        # Validate the warning level
        if not 0 <= self.warning_level <= 4:
            raise ValueError(f"Warning level must be between 0 and 4, current value: {self.warning_level}")

        # Validate the timeout
        if self.timeout <= 0:
            raise ValueError(f"Timeout must be a positive number, current value: {self.timeout}")

        _validate_extra_args(self.extra_args)


@dataclass
class ProjectCompileRequest:
    """Project compile request"""
    project_path: str
    options: CompileOptions = field(default_factory=CompileOptions)

    def __post_init__(self):
        """Validate the project path"""
        if not self.project_path:
            raise ValueError("Project path must not be empty")

        # Validate the file extension (supports Delphi .dproj/.dpr/.dpk and Lazarus .lpi/.lpr)
        if not self.project_path.endswith(('.dproj', '.dpr', '.dpk', '.lpi', '.lpr')):
            raise ValueError(f"Project file must be .dproj, .dpr, .dpk, .lpi or .lpr format, current path: {self.project_path}")


@dataclass
class FileCompileRequest:
    """Single-file compile request"""
    file_path: str
    unit_search_paths: List[str] = field(default_factory=list)
    conditional_defines: List[str] = field(default_factory=list)
    warning_level: int = 2
    disabled_warnings: List[str] = field(default_factory=list)
    compiler_version: Optional[str] = None
    extra_args: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Validate the file path"""
        if not self.file_path:
            raise ValueError("File path must not be empty")

        # Validate the file extension
        if not self.file_path.endswith('.pas'):
            raise ValueError(f"File must be .pas format, current path: {self.file_path}")

        # Validate the warning level
        if not 0 <= self.warning_level <= 4:
            raise ValueError(f"Warning level must be between 0 and 4, current value: {self.warning_level}")

        _validate_extra_args(self.extra_args)
