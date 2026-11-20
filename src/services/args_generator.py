"""
Argument Generator

Copyright (C) Jilin Province Zuoyou Software Development Co., Ltd.
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
Update & Mod By Crystalxp (Night Killer QQ:281309196)

Generate Delphi compiler command-line arguments according to compile options
"""

import os
from pathlib import Path
from typing import List, Optional
from ..models.compile_request import CompileOptions, OutputType, RuntimeLibrary, TargetPlatform
from ..utils.logger import get_logger

logger = get_logger(__name__)


class ArgsGenerator:
    """Delphi compiler argument generator"""

    # Platform-to-library directory mapping
    _PLATFORM_LIB_DIR = {
        TargetPlatform.WIN32: 'Win32', TargetPlatform.WIN64: 'Win64',
        TargetPlatform.OSX64: 'OSX64', TargetPlatform.OSXARM64: 'OSXARM64',
        TargetPlatform.IOSDEVICE64: 'iOSDevice64', TargetPlatform.IOSDEVICE: 'iOSDevice',
        TargetPlatform.IOSSIMULATOR: 'iOSSimulator',
        TargetPlatform.ANDROID: 'Android', TargetPlatform.ANDROID64: 'Android64',
        TargetPlatform.LINUX64: 'Linux64',
    }

    def _get_platform_lib_path(self, delphi_version: str, platform: TargetPlatform) -> str:
        """Get the library path for the target platform (prefer registry, fall back to default path)"""
        lib_dir = self._PLATFORM_LIB_DIR.get(platform, 'Win32')
        # Prefer getting the library path from the registry via delphi_env (supports non-standard install locations)
        try:
            from ..utils.delphi_env import get_delphi_library_paths, expand_delphi_path_macros
            paths = get_delphi_library_paths(version=delphi_version, platform=lib_dir)
            # Find the Delphi standard library path: contains a \lib\ directory component + release
            for p in paths:
                expanded = expand_delphi_path_macros(p, version=delphi_version, platform=lib_dir)
                if ('\\lib\\' in expanded or '/lib/' in expanded) and 'release' in expanded.lower():
                    return expanded
        except Exception as e:
            logger.debug("Ignoring non-fatal exception: %s", str(e))
        try:
            from ..utils.delphi_env import get_delphi_root_dir
            root_dir = get_delphi_root_dir(delphi_version)
            if root_dir:
                return str(Path(root_dir) / "lib" / lib_dir / "release")
        except Exception as e:
            logger.debug("Ignoring non-fatal exception: %s", str(e))

        program_files_x86 = os.environ.get("ProgramFiles(x86)")
        if not program_files_x86:
            return ""
        return str(
            Path(program_files_x86)
            / "Embarcadero"
            / "Studio"
            / delphi_version
            / "lib"
            / lib_dir
            / "release"
        )

    def generate(self, project_path: str, options: CompileOptions) -> List[str]:
        """Generate compiler argument list"""
        args = []

        # Basic argument: project file (do not add quotes; asyncio.create_subprocess_exec handles it automatically)
        args.append(project_path)

        # Output path
        if options.output_path:
            args.append('-E' + options.output_path)

        # Conditional compilation symbols (note: defines syntax is -D; -$D+ is the debug information switch; do not confuse the two)
        if options.conditional_defines:
            defines = ";".join(options.conditional_defines)
            args.append('-D' + defines)

        # Unit search paths
        if options.unit_search_paths:
            paths = ";".join(options.unit_search_paths)
            args.append('-U' + paths)

        # Resource search paths
        if options.resource_search_paths:
            paths = ";".join(options.resource_search_paths)
            args.append('-R' + paths)

        # Optimization option
        if options.optimize:
            args.append('-$O+')
        else:
            args.append('-$O-')

        # Debug information
        if options.debug:
            args.append('-$D+')
        else:
            args.append('-$D-')

        # Warning level
        args.append('-$W' + str(options.warning_level))

        # Disable warnings
        for warning in options.disabled_warnings:
            args.append('-$W-' + warning)

        # Output type
        output_type_map = {
            OutputType.CONSOLE: "-CC",
            OutputType.GUI: "-CG",
            OutputType.DLL: "-LD"
        }
        args.append(output_type_map[options.output_type])

        # Runtime library
        if options.runtime_library == RuntimeLibrary.DYNAMIC:
            args.append('-$Y+')
        else:
            args.append('-$Y-')

        # Generate a Detailed-level .map file (for StackTrace callgraph parsing)
        args.append('-GD')

        # Append user arguments last, allowing explicit override of earlier compiler switches of the same kind
        args.extend(options.extra_args)

        logger.debug("Generated arguments: " + " ".join(args))
        return args

    def validate_args(self, args: List[str]) -> bool:
        """Validate arguments"""
        path_params = {'-U', '-I', '-R', '-NS', '-LE', '-LN', '-NU', '-NH', '-NO', '-NB', '-NX'}
        
        for arg in args:
            param_prefix = None
            for pf in path_params:
                if arg.startswith(pf):
                    param_prefix = pf
                    break
            
            if '"' in arg and arg.count('"') >= 2:
                parts = arg.split('"')
                for i in range(0, len(parts), 2):
                    if any(char in parts[i] for char in ['|', '&', '`', '<', '>']):
                        logger.error("Argument contains illegal characters: " + arg)
                        return False
            else:
                if param_prefix:
                    if any(char in arg for char in ['|', '&', '`', '<', '>']):
                        logger.error("Argument contains illegal characters: " + arg)
                        return False
                else:
                    if any(char in arg for char in ['|', '&', '`', '(', ')', '<', '>']):
                        logger.error("Argument contains illegal characters: " + arg)
                        return False
            
            if '$' in arg and not arg.startswith('-$'):
                logger.error("Argument contains illegal $ character: " + arg)
                return False
            
            if ';' in arg and param_prefix is None:
                logger.error("Argument contains illegal ; character: " + arg)
                return False

        return True

    def validate_batch_extra_args(self, args: List[str]) -> bool:
        """Validate user arguments that are about to be written to the MSBuild batch file."""
        forbidden_chars = {'"', '%', '!', '&', '|', '<', '>', '^'}
        for arg in args:
            if any(ord(char) < 32 or char in forbidden_chars for char in arg):
                logger.error("MSBuild extra argument contains batch metacharacters: %s", arg)
                return False
        return True

    def format_command(self, executable: str, args: List[str]) -> str:
        """Generate complete command string"""
        if ' ' in executable:
            executable = '"' + executable + '"'

        command = executable + " " + " ".join(args)
        logger.debug("Complete command: " + command)
        return command

    def generate_for_file(self, file_path: str, unit_search_paths: List[str] = None,
                         warning_level: int = 2, disabled_warnings: List[str] = None,
                         namespaces: List[str] = None, include_paths: List[str] = None,
                         output_dir: str = None, delphi_version: Optional[str] = None,
                         conditional_defines: List[str] = None,
                         extra_args: Optional[List[str]] = None) -> List[str]:
        """Generate single-file compilation arguments

        Args:
            file_path: Path of the file to compile
            unit_search_paths: List of unit search paths
            warning_level: Warning level (0-4)
            disabled_warnings: List of warnings to disable
            namespaces: List of namespaces (used to resolve unit names)
            include_paths: List of include file search paths
            output_dir: Output directory (used to store .dcu files)
            delphi_version: Delphi version number; auto-detected by default
            conditional_defines: List of conditional compilation symbols
            extra_args: List of additional compiler arguments
        """
        args = []

        # File path (do not add quotes; asyncio.create_subprocess_exec handles it automatically)
        args.append(file_path)

        # Conditional compilation symbols
        if conditional_defines:
            defines = ";".join(conditional_defines)
            args.append('-D' + defines)

        # Namespaces - this is key! Used to resolve units such as System.Classes
        if namespaces:
            ns_string = ";".join(namespaces)
            args.append('-NS' + ns_string)
        else:
            # Default namespaces
            default_namespaces = [
                "System", "Winapi", "System.Win", "Vcl", "Vcl.Imaging",
                "Vcl.Touch", "Vcl.Samples", "Vcl.Shell", "Data", "Datasnap",
                "Web", "Soap", "Xml"
            ]
            args.append('-NS' + ";".join(default_namespaces))

        # Add Delphi standard library path (by target platform)
        if unit_search_paths is None:
            unit_search_paths = []
        if not delphi_version:
            try:
                from ..utils.delphi_env import get_delphi_version
                delphi_version = get_delphi_version()
            except Exception as e:
                logger.debug("Failed to auto-detect Delphi version: %s", str(e))

        if delphi_version:
            delphi_lib_path = Path(self._get_platform_lib_path(delphi_version, TargetPlatform.WIN32))
            if delphi_lib_path.exists():
                # Add the standard library path to the beginning of the search paths
                unit_search_paths.insert(0, str(delphi_lib_path))

        # Unit search paths
        if unit_search_paths:
            paths = ";".join(unit_search_paths)
            args.append('-U' + paths)

        # Include file search paths
        if include_paths:
            paths = ";".join(include_paths)
            args.append('-I' + paths)

        # Output directory (used to store .dcu files) - do not add quotes; asyncio handles it automatically
        if output_dir:
            args.append('-N' + output_dir)

        # Warning level
        args.append('-$W' + str(warning_level))

        # Disable warnings
        if disabled_warnings:
            for warning in disabled_warnings:
                args.append('-$W-' + warning)

        # Syntax check only
        args.append('-$M-')

        args.extend(extra_args or [])

        logger.debug("Generated single-file compilation arguments: " + " ".join(args))
        return args

