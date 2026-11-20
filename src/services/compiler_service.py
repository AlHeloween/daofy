"""
Compilation Service

Copyright (C) Jilin Province ZuoYou Software Development Co., Ltd.
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
Update & Mod By Crystalxp (Night Killer QQ:281309196)

Core business logic, coordinating components such as parameter generation, process execution, and result parsing
"""

import os
import tempfile
import time
import winreg
from datetime import datetime
from pathlib import Path
from typing import Optional
from ..constants import (
    REG_KEY_EMBARCADERO_BDS,
    TIMEOUT_DELPHI_COMPILE,
    TIMEOUT_MSBUILD_DISCOVERY,
    TIMEOUT_PROCESS_QUERY,
)
from ..models.compile_request import ProjectCompileRequest, FileCompileRequest, TargetPlatform, CompileOptions, OutputType, RuntimeLibrary
from ..models.compile_result import CompileResult, CompileStatus
from ..models.command_args import CommandArgs
from ..models.compile_history import CompileHistoryEntry
from ..models.compiler_config import CompilerConfig
from .args_generator import ArgsGenerator
from .process_manager import ProcessManager
from .config_manager import ConfigManager
from .project_settings import ProjectSettings, load_project_settings
from ..utils import get_console_encoding
from ..utils.delphi_env import (
    EnvOptionsLibraryStatus,
    build_env_options_overlay,
    get_delphi_public_studio_root,
    get_delphi_version as _get_delphi_version_env,
    inspect_env_options_library_paths,
)
from ..utils.delphi_versions import (
    detect_registry_version_from_compiler,
    normalize_registry_version,
    normalize_version_key,
    project_version_to_registry_version,
)
from ..utils.parser import OutputParser
from ..utils.validator import Validator
from ..utils.dproj_parser import DprojParser
from ..utils.unit_dependency_analyzer import SmartLibraryPathResolver
from ..utils.logger import get_logger

logger = get_logger(__name__)


class CompilerService:
    """Compilation Service"""

    def __init__(self, config_manager: ConfigManager):
        """Initialize the compilation service
        
        Args:
            config_manager: Configuration manager
        """
        self.config_manager = config_manager
        self.args_generator = ArgsGenerator()
        self.process_manager = ProcessManager()
        self.output_parser = OutputParser()
        self.validator = Validator()
        self.history: list = []
        
        # MSBuild path (perform a general detection at initialization; re-detect by project version during compilation)
        self.msbuild_path = self._find_msbuild()
        self._msbuild_auto_cache: dict[str, Optional[str]] = {}
        
        logger.info("Compilation service initialization complete")

    def _lookup_compiler_by_version(
        self,
        version: str,
        platform: TargetPlatform,
    ) -> Optional[CompilerConfig]:
        """Look up compiler configuration by Delphi version, compatible with the trimmed config_manager used in tests."""
        config_manager = getattr(self, "config_manager", None)
        getter = getattr(config_manager, "get_compiler_by_registry_version", None)
        if not callable(getter) or not version:
            return None
        try:
            return getter(version, platform.value)
        except TypeError:
            # Compatible with old signatures/stub objects that accept only one positional argument
            try:
                return getter(version)
            except Exception:
                logger.warning("Failed to look up compiler by version: %s", version, exc_info=True)
                return None
        except Exception:
            logger.warning("Failed to look up compiler by version: %s", version, exc_info=True)
            return None

    def _compiler_from_registry_version(
        self,
        version: str,
        platform: TargetPlatform,
    ) -> Optional[CompilerConfig]:
        """Locate the compiler from the registry by version and return a configuration object usable for compilation."""
        path = self._find_compiler_from_registry(platform, version)
        if not path:
            return None
        return CompilerConfig(
            name=f"Delphi {version}",
            path=path,
            registry_version=version,
        )

    def _lookup_compiler_by_name_or_version(
        self,
        value: str,
        platform: TargetPlatform,
    ) -> Optional[CompilerConfig]:
        """Look up by compiler name first; if not found, treat value as a Delphi version and look up again.

        This allows ``compiler_version="11.0"`` / ``"XE4"`` to hit the XE4 compiler,
        instead of directly reporting "compiler does not exist".
        """
        config_manager = getattr(self, "config_manager", None)
        if config_manager is None or not value:
            return None

        getter = getattr(config_manager, "get_compiler", None)
        if callable(getter):
            try:
                compiler = getter(value)
            except Exception:
                logger.warning("Failed to look up compiler configuration: %s", value, exc_info=True)
                compiler = None
            if compiler:
                return compiler

        version = normalize_version_key(value)
        if version:
            return self._lookup_compiler_by_version(version, platform)
        return None

    def _warn_conflicting_project_versions(
        self,
        project_settings: Optional[ProjectSettings],
    ) -> None:
        """Warn when a project configures both compiler_version and delphi_version and the versions are inconsistent."""
        if not project_settings:
            return
        if not project_settings.compiler_version or not project_settings.delphi_version:
            return
        compiler = self._lookup_compiler_by_name_or_version(
            project_settings.compiler_version,
            TargetPlatform.WIN32,
        )
        if not compiler or not compiler.registry_version:
            return
        actual = normalize_registry_version(compiler.registry_version)
        if actual and actual != project_settings.delphi_version:
            logger.warning(
                "Project configuration %s has compiler_version=%r corresponding to Delphi %s, "
                "which is inconsistent with delphi_version=%s; compiler_version will take precedence",
                project_settings.source,
                project_settings.compiler_version,
                actual,
                project_settings.delphi_version,
            )

    def _warn_if_direct_compile_version_mismatch(
        self,
        project_path: str,
        compiler: Optional[CompilerConfig],
    ) -> None:
        """Warn during direct compilation when the .dproj inferred version does not match the actual compiler."""
        if not compiler or not compiler.registry_version:
            return
        dproj = project_path
        if Path(dproj).suffix.lower() in (".dpr", ".dpk"):
            dproj = str(Path(dproj).with_suffix(".dproj"))
        if not Path(dproj).exists():
            return
        try:
            parser = DprojParser(dproj)
            if not parser.parse():
                return
            project_version = parser.get_project_version()
        except Exception:
            logger.debug("Failed to read .dproj ProjectVersion: %s", dproj, exc_info=True)
            return
        target = (
            project_version_to_registry_version(project_version)
            if project_version
            else None
        )
        actual = normalize_registry_version(compiler.registry_version)
        if target and actual and target != actual:
            logger.warning(
                "Project %s has .dproj ProjectVersion=%s corresponding to Delphi %s, "
                "but direct compilation will use compiler %s (Delphi %s); "
                "for strict matching, configure delphi_version in .daofy/project.json in the project directory",
                Path(dproj).name,
                project_version,
                target,
                compiler.name,
                actual,
            )

    def _resolve_project_compiler(
        self,
        project_path: str,
        explicit_name: Optional[str],
        platform: TargetPlatform,
        project_settings: Optional[ProjectSettings] = None,
    ) -> tuple[Optional[CompilerConfig], Optional[str], Optional[str]]:
        """Resolve the compiler actually used by the project.

        Priority: explicit tool parameter > project configuration ``compiler_version`` > project configuration
        ``delphi_version`` > default compiler. If the project configuration specifies a version
        but that version is unavailable, return an error and do not fall back to another Delphi version.

        Returns:
            ``(compiler_config, compiler_path, error_message)``; when normal,
            ``error_message`` is None. When only a path exists without registry configuration,
            ``compiler_config`` is None and ``compiler_path`` has a value.
        """
        settings = (
            project_settings
            if project_settings is not None
            else load_project_settings(project_path)
        )
        if settings and settings.error:
            return None, None, settings.error
        self._warn_conflicting_project_versions(settings)
        name = explicit_name or (settings.compiler_version if settings else None)

        if name:
            compiler = self._lookup_compiler_by_name_or_version(name, platform)
            if compiler:
                if settings is None:
                    self._warn_if_direct_compile_version_mismatch(
                        project_path, compiler
                    )
                return compiler, None, None
            version_hint = normalize_version_key(name)
            if version_hint:
                path = self._find_compiler_from_registry(platform, version_hint)
                if path:
                    return None, path, None
            if not explicit_name and settings and settings.delphi_version:
                logger.warning(
                    "The project-configured compiler_version=%r is unavailable; using delphi_version=%s instead",
                    name,
                    settings.delphi_version,
                )
            elif version_hint:
                return None, None, (
                    f"Specified Delphi version {name!r} is not installed"
                    f" (no {platform.value} compiler found); will not fall back to another version"
                )
            else:
                return None, None, (
                    f"Specified compiler {name!r} does not exist; will not fall back to another Delphi version"
                )

        if settings and settings.delphi_version:
            compiler = self._lookup_compiler_by_version(settings.delphi_version, platform)
            if compiler:
                return compiler, None, None
            path = self._find_compiler_from_registry(platform, settings.delphi_version)
            if path:
                return None, path, None
            return None, None, (
                f"Project configuration specifies Delphi {settings.delphi_version}"
                f" ({settings.source}), but no compiler for this version was found; "
                "will not fall back to another Delphi version"
            )

        config_manager = getattr(self, "config_manager", None)
        getter = getattr(config_manager, "get_effective_compiler", None)
        if callable(getter):
            try:
                compiler = getter(None, platform.value)
            except TypeError:
                compiler = getter(None)
            except Exception:
                logger.warning("Failed to get effective compiler", exc_info=True)
                compiler = None
            if compiler:
                if settings is None:
                    self._warn_if_direct_compile_version_mismatch(
                        project_path, compiler
                    )
                return compiler, None, None

        path = self._find_compiler_from_registry(platform)
        return None, path, None

    def _find_msbuild(self, version: Optional[str] = None) -> Optional[str]:
        """Find the MSBuild executable (automatic detection).

        Search priority:
        1. .NET Framework MSBuild corresponding to older Delphi versions (when a version is specified)
        2. vswhere.exe (official VS 2017+ tool, most accurate)
        3. %ProgramFiles(x86)%/Microsoft Visual Studio/Installer/vswhere.exe
        4. List of common VS installation paths (fallback)
        5. MSBuild bundled with the Delphi installation directory (prefer the specified version)
        6. msbuild.exe in PATH

        Args:
            version: Delphi registry version number, used to prefer the MSBuild bundled with that version

        Returns:
            MSBuild path, or None if not found
        """
        return self._auto_find_msbuild(version)

    def _auto_find_msbuild(self, version: Optional[str] = None) -> Optional[str]:
        """Automatically detect MSBuild (excluding explicit configuration).

        Args:
            version: Delphi registry version number, used to prefer the MSBuild bundled with that version

        Returns:
            MSBuild path, or None if not found
        """
        import subprocess

        # Method 0: Older Delphi versions rely on the MSBuild bundled with .NET Framework.
        # XE4 and earlier use v3.5; XE5–10 Seattle use v4.0.30319;
        # using VS2019/2022 MSBuild to compile these projects usually fails.
        preferred_version = version
        preferred_target = (
            normalize_registry_version(preferred_version) if preferred_version else None
        )
        if preferred_target:
            major = int(preferred_target.split(".")[0])
            if major <= 17:
                framework_version = "v3.5" if major <= 11 else "v4.0.30319"
                windir = os.environ.get("WINDIR", r"C:\Windows")
                framework_msbuild = (
                    Path(windir) / "Microsoft.NET" / "Framework"
                    / framework_version / "MSBuild.exe"
                )
                if framework_msbuild.is_file():
                    logger.info(
                        "Delphi %s corresponds to .NET Framework %s; using MSBuild: %s",
                        preferred_target,
                        framework_version,
                        framework_msbuild,
                    )
                    return str(framework_msbuild)
                logger.warning(
                    "Delphi %s usually requires the .NET Framework %s MSBuild, "
                    "but %s was not found; continuing to try other MSBuild installations (may be incompatible)",
                    preferred_target,
                    framework_version,
                    framework_msbuild,
                )

        # Method 1: Use vswhere.exe to query the MSBuild path of the latest VS
        vswhere_candidates = []
        program_files_x86 = os.environ.get("ProgramFiles(x86)")
        if program_files_x86:
            vswhere_candidates.append(
                Path(program_files_x86) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
            )
        program_files = os.environ.get("ProgramFiles")
        if program_files:
            vswhere_candidates.append(
                Path(program_files) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
            )
        for vswhere in vswhere_candidates:
            if vswhere.exists():
                try:
                    result = subprocess.run(
                        [
                            str(vswhere),
                            "-latest", "-products", "*",
                            "-requires", "Microsoft.Component.MSBuild",
                            "-find", "MSBuild\\**\\Bin\\MSBuild.exe",
                        ],
                        capture_output=True, text=True, timeout=TIMEOUT_MSBUILD_DISCOVERY,
                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                    )

                    if result.returncode == 0 and result.stdout.strip():
                        for line in result.stdout.strip().splitlines():
                            msbuild_path = line.strip()
                            if msbuild_path and Path(msbuild_path).exists():
                                logger.info(f"Found MSBuild via vswhere: {msbuild_path}")
                                return msbuild_path
                except (subprocess.TimeoutExpired, OSError) as e:
                    logger.debug(f"vswhere query failed: {e}")

        # Method 2: List of common VS installation paths (fallback)
        editions = ["BuildTools", "Community", "Professional", "Enterprise"]
        years = ["2019", "2022"]
        possible_paths = []
        for year in years:
            for edition in editions:
                base_root = program_files_x86 if year == "2019" else program_files
                if not base_root:
                    continue
                base = Path(base_root)
                possible_paths.append(
                    str(base / f"Microsoft Visual Studio\\{year}\\{edition}\\MSBuild\\Current\\Bin\\MSBuild.exe")
                )

        for path in possible_paths:
            if Path(path).exists():
                logger.info(f"Found MSBuild: {path}")
                return path

        # Method 3: Fallback to MSBuild bundled with Delphi/RAD Studio
        # On machines without VS, when both vswhere and the VS path list are empty, check whether the Delphi installation directory
        # includes MSBuild, to avoid .dproj failing to compile because MSBuild cannot be found.
        try:
            delphi_roots = self._read_delphi_roots_from_hive(
                winreg.HKEY_CURRENT_USER, "HKCU"
            )
            delphi_roots.extend(
                self._read_delphi_roots_from_hive(winreg.HKEY_LOCAL_MACHINE, "HKLM")
            )

            # Prefer the specified version to avoid XE4 projects mistakenly using MSBuild from another version's directory
            preferred_version = version
            if preferred_version:
                preferred_target = normalize_registry_version(preferred_version)
                delphi_roots.sort(
                    key=lambda item: normalize_registry_version(item[0]) != preferred_target
                )

            for _version_key, root_dir in delphi_roots:
                root_path = Path(root_dir)
                candidates = [
                    root_path / "bin" / "MSBuild.exe",
                    root_path / "bin" / "MSBuild" / "Current" / "Bin" / "MSBuild.exe",
                    root_path / "MSBuild.exe",
                    root_path / "msbuild" / "Current" / "Bin" / "MSBuild.exe",
                ]
                for cand in candidates:
                    if cand.exists():
                        logger.info(f"Found MSBuild via the Delphi installation directory: {cand}")
                        return str(cand)
        except Exception as e:
            logger.debug(f"Search for Delphi-bundled MSBuild failed: {e}")

        # Method 4: msbuild.exe in PATH (last resort; usually ineffective, only a final attempt)
        try:
            import shutil
            on_path = shutil.which("msbuild.exe") or shutil.which("msbuild")
            if on_path:
                logger.info(f"Found MSBuild via PATH: {on_path}")
                return on_path
        except Exception as e:
            logger.debug(f"PATH search for msbuild failed: {e}")

        logger.warning("MSBuild not found; will fall back to direct compilation")
        return None

    def _resolve_msbuild_path(
        self,
        version: Optional[str] = None,
        project_settings: Optional[ProjectSettings] = None,
    ) -> tuple[Optional[str], str, bool]:
        """Resolve the MSBuild to use for this compilation by priority, and return the source description.

        Priority (if an explicit configuration matches but its path is invalid, fail directly and do not silently switch to another version):
        1. ``msbuild_path`` in project configuration ``.daofy/project.json`` / ``daofy.project.json``
        2. ``msbuild_by_delphi_version[<version>]`` in ``compilers.json``
        3. Automatic detection (prefer the project's Delphi version → vswhere → VS → Delphi → PATH)

        Args:
            version: Delphi registry version number resolved for this compilation
            project_settings: Project-level configuration (optional)

        Returns:
            ``(msbuild_path, source, explicit_error)``; when explicit configuration is invalid, path is
            None and explicit_error is True; the caller should fail directly instead of falling back to another
            MSBuild/direct compilation.
        """
        explicit: list[tuple[str, str]] = []

        if project_settings and project_settings.msbuild_path:
            explicit.append(
                (project_settings.msbuild_path, f"Project configuration {project_settings.source}")
            )

        config_manager = getattr(self, "config_manager", None)
        version_getter = getattr(config_manager, "get_msbuild_for_version", None)
        if callable(version_getter) and version:
            try:
                mapped = version_getter(version)
            except Exception:
                logger.warning("Failed to read msbuild_by_delphi_version", exc_info=True)
                mapped = None
            if mapped:
                explicit.append(
                    (
                        mapped,
                        f"compilers.json msbuild_by_delphi_version[{version}]",
                    )
                )

        for raw_path, source in explicit:
            path = Path(raw_path).expanduser()
            if path.is_file():
                logger.info("Using MSBuild specified by configuration (%s): %s", source, path)
                return str(path), source, False
            logger.error(
                "Configured MSBuild path does not exist (%s): %s; "
                "please correct this configuration, or remove it to restore automatic detection",
                source,
                raw_path,
            )
            return None, f"{source} 指向的路径不存在: {raw_path}", True

        # Only auto-detect when there is no explicit configuration. It must be re-detected by this project's Delphi version:
        # the msbuild_path cached at initialization is a generic detection result; reusing it directly
        # would still make a project of another version use the wrong MSBuild.
        fallback = getattr(self, "msbuild_path", None)
        if fallback and not Path(fallback).is_absolute():
            # A bare filename (such as "MSBuild.exe" injected by tests) is treated as explicitly specified by the caller and left to PATH
            return fallback, "Automatic detection", False

        version_key = normalize_registry_version(version) if version else None
        if version_key:
            found = self._auto_find_msbuild_cached(version_key)
            if found:
                return found, f"Automatic detection (prefer Delphi {version_key})", False

        if fallback:
            return fallback, "Automatic detection", False

        # 初始化时未探测到（或对象由测试直接构造）时再尝试一次
        found = self._auto_find_msbuild_cached(version_key)
        if found:
            return found, "Automatic detection", False
        return None, "Automatic detection did not find MSBuild", False

    def _auto_find_msbuild_cached(self, version_key: Optional[str]) -> Optional[str]:
        """Cache automatic detection results by version to avoid launching vswhere on every compilation."""
        cache = getattr(self, "_msbuild_auto_cache", None)
        if cache is None:
            cache = {}
            try:
                self._msbuild_auto_cache = cache
            except AttributeError:  # pragma: no cover - 防御 __slots__ 子类
                pass
        key = version_key or ""
        if key in cache:
            return cache[key]
        found = self._auto_find_msbuild(version_key)
        # Only cache successful results: users do not need to restart the service after installing MSBuild later
        if found:
            cache[key] = found
        return found

    @staticmethod
    def _version_sort_key(version_key: str) -> tuple:
        """Convert a registry version key such as ``"11.0"`` into a comparable numeric tuple.

        Sorting directly by string would place ``"9.0"`` after ``"37.0"``, causing the "latest version"
        to be selected incorrectly, so comparison must be numeric.
        """
        try:
            return tuple(int(part) for part in str(version_key).split("."))
        except (TypeError, ValueError):
            return (0,)

    def _read_delphi_roots_from_hive(self, hive, hive_name: str) -> list:
        """Read Delphi installations (version, RootDir) under a single registry root."""
        roots: list = []
        try:
            key = winreg.OpenKey(
                hive,
                REG_KEY_EMBARCADERO_BDS,
                0,
                winreg.KEY_READ | winreg.KEY_WOW64_32KEY,
            )
        except FileNotFoundError:
            logger.debug("Registry %s\\%s does not exist; skipping", hive_name, REG_KEY_EMBARCADERO_BDS)
            return roots
        except OSError as exc:
            logger.warning("Failed to open registry %s\\%s: %s", hive_name, REG_KEY_EMBARCADERO_BDS, exc)
            return roots

        try:
            index = 0
            while True:
                try:
                    version_key = winreg.EnumKey(key, index)
                    index += 1
                except OSError:
                    break

                try:
                    version_path_key = winreg.OpenKey(key, version_key)
                except OSError as exc:
                    logger.debug(
                        "Failed to open %s\\%s\\%s: %s",
                        hive_name, REG_KEY_EMBARCADERO_BDS, version_key, exc,
                    )
                    continue

                try:
                    root_dir, _ = winreg.QueryValueEx(version_path_key, "RootDir")
                    if root_dir and Path(root_dir).exists():
                        roots.append((version_key, root_dir))
                except OSError:
                    logger.debug("Delphi %s has no available RootDir", version_key)
                finally:
                    winreg.CloseKey(version_path_key)
        finally:
            winreg.CloseKey(key)
        return roots

    def _get_delphi_root_from_registry(self, version: Optional[str] = None) -> Optional[str]:
        """
        Get the Delphi installation root directory from the registry

        Prefer HKCU, fall back to HKLM. If the specified version is not installed, return None and no longer silently fall back to
        the latest version—otherwise specifying XE4 would get the installation directory of Tokyo/XE8.

        Args:
            version: Delphi version number (e.g. "22.0"); if None, use the latest version

        Returns:
            Delphi installation root directory, or None if not found
        """
        try:
            versions = self._read_delphi_roots_from_hive(winreg.HKEY_CURRENT_USER, "HKCU")
            versions.extend(
                self._read_delphi_roots_from_hive(winreg.HKEY_LOCAL_MACHINE, "HKLM")
            )

            if not versions:
                logger.warning("No Delphi installation found in either HKCU or HKLM registry")
                return None

            if version:
                target = normalize_registry_version(version)
                for registered_version, root_dir in versions:
                    if normalize_registry_version(registered_version) == target:
                        return root_dir
                logger.warning("Delphi %s not found in the registry; will not fall back to another version", version)
                return None

            versions.sort(
                key=lambda item: self._version_sort_key(item[0]),
                reverse=True,
            )
            return versions[0][1]

        except Exception as e:
            logger.warning(f"Failed to get Delphi path from registry: {e}")
            return None

    def _get_rsvars_path(self, version: Optional[str] = None) -> Optional[str]:
        """
        Get the rsvars.bat path

        Args:
            version: Delphi version number; if None, use the latest installed version

        Returns:
            Full rsvars.bat path, or None if not found
        """
        root_dir = self._get_delphi_root_from_registry(version)
        if not root_dir and version:
            # When the registry is missing, infer the root directory from the compiler path for that version in compilers.json
            config_manager = getattr(self, "config_manager", None)
            getter = getattr(config_manager, "get_compiler_by_registry_version", None)
            compiler = None
            if callable(getter):
                try:
                    compiler = getter(version)
                except Exception:
                    logger.debug("Failed to look up compiler configuration by version: %s", version, exc_info=True)
            if compiler and compiler.path:
                root_dir = str(Path(compiler.path).parent.parent)
                logger.info(
                    "Delphi %s not found in the registry; inferring root directory from compiler configuration instead: %s",
                    version,
                    root_dir,
                )

        if not root_dir:
            logger.error("Unable to get Delphi installation path from the registry")
            return None

        rsvars_path = Path(root_dir) / "bin" / "rsvars.bat"
        if rsvars_path.exists():
            logger.info(f"Found rsvars.bat: {rsvars_path}")
            return str(rsvars_path)
        else:
            logger.error(f"rsvars.bat does not exist: {rsvars_path}")
            return None

    def _get_effective_delphi_root(self, version: Optional[str] = None) -> Optional[str]:
        """Get the currently effective Delphi installation root directory.

        Args:
            version: Specify the Delphi registry version (e.g. ``"11.0"``); if None, use
                the latest installed version. For package installation/BPL lookup, pass the version from the project configuration to avoid mixing with
                other versions.

        Returns:
            Delphi installation root directory, or None if not found
        """
        root_dir = self._get_delphi_root_from_registry(version)
        if root_dir:
            return root_dir

        # When the registry is unavailable (manually configured compiler/portable version), infer the root directory from the compiler path
        config_manager = getattr(self, "config_manager", None)
        compiler = None
        if version:
            compiler = self._lookup_compiler_by_version(version, TargetPlatform.WIN32)
        else:
            getter = getattr(config_manager, "get_effective_compiler", None)
            if callable(getter):
                try:
                    compiler = getter(None, "win32")
                except Exception:
                    logger.warning("Failed to get effective compiler", exc_info=True)
        if compiler and compiler.path:
            inferred = str(Path(compiler.path).parent.parent)
            logger.info(
                "Delphi %s not found in the registry; inferring root directory from compiler configuration instead: %s",
                version or "default version",
                inferred,
            )
            return inferred
        return None

    def _check_process_running(self, process_name: str) -> Optional[dict]:
        """
        Check whether the specified process is running
        
        Args:
            process_name: Process name (without the .exe extension)
            
        Returns:
            If the process is running, return a dictionary containing process information; otherwise return None
        """
        import subprocess
        import json
        import re
        
        if not re.match(r'^[A-Za-z0-9_.-]+$', process_name):
            logger.warning("Process name contains illegal characters; rejected: %s", process_name)
            return None
        
        try:
            result = subprocess.run(
                ['powershell', '-Command',
                 "Get-Process -Name '%s' -ErrorAction SilentlyContinue | "
                 "Select-Object Id, ProcessName, Path | ConvertTo-Json" % process_name],
                capture_output=True,
                text=True,
                timeout=TIMEOUT_PROCESS_QUERY,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            )
            
            if result.returncode == 0 and result.stdout.strip():
                output = result.stdout.strip()
                
                if output.startswith('['):
                    processes = json.loads(output)
                    if processes:
                        proc = processes[0]
                    else:
                        return None
                elif output.startswith('{'):
                    proc = json.loads(output)
                else:
                    return None
                
                logger.info("Detected running process: %s (PID: %s)", proc.get('ProcessName'), proc.get('Id'))
                return {
                    'pid': proc.get('Id'),
                    'name': proc.get('ProcessName'),
                    'path': proc.get('Path')
                }
            
            return None
            
        except Exception as e:
            logger.warning("Error occurred while checking process: %s", str(e))
            return None

    def _cleanup_dcu_files(self, file_path: str):
        """
        Clean up .dcu files in the directory containing the source file
        
        Args:
            file_path: Source file path
        """
        import glob
        
        file_path_obj = Path(file_path)
        file_dir = file_path_obj.parent
        
        if not file_dir.exists():
            return
        
        dcu_pattern = str(file_dir / "*.dcu")
        dcu_files = glob.glob(dcu_pattern)
        
        if dcu_files:
            logger.info(f"Found {len(dcu_files)} .dcu files in {file_dir}")
            
            total_deleted = 0
            for dcu_file in dcu_files:
                try:
                    os.unlink(dcu_file)
                    logger.debug(f"Deleted: {dcu_file}")
                    total_deleted += 1
                except Exception as e:
                    logger.warning(f"Failed to delete {dcu_file}: {str(e)}")
            
            if total_deleted > 0:
                logger.info(f"Deleted {total_deleted} .dcu files in total")

    def _execute_build_event(self, event_name: str, event_cmd: str, project_dir: str, 
                            ignore_exit_code: bool = False, timeout: int = 60,
                            context: dict = None) -> tuple:
        """
        Execute build event

        Args:
            event_name: Event name (used for logging)
            event_cmd: Event command
            project_dir: Project directory
            ignore_exit_code: Whether to ignore exit code
            timeout: Timeout (seconds)
            context: Context variable dictionary, including project information, etc.

        Returns:
            (success, error_message, output) tuple
        """
        import subprocess
        import tempfile
        import re
        
        logger.info("Executing %s: %s", event_name, event_cmd[:200])
        
        _DANGEROUS_PATTERNS = re.compile(
            r'(?:^|\b)(?:rm\s+/|del\s+/[sq]|format\s+[a-z]:|net\s+user|'
            r'reg(?:edit(?:32)?|\.exe)?\s+add|powershell\s+-enc|'
            r'cmd(?:\.exe)?\s+/c\s*(?:curl|wget|bitsadmin))',
            re.IGNORECASE
        )
        if _DANGEROUS_PATTERNS.search(event_cmd):
            error_msg = "%s command contains dangerous patterns and was rejected: %s" % (event_name, event_cmd[:200])
            logger.error(error_msg)
            return (False, error_msg, None)
        
        # Replace variables supported by Delphi
        if context:
            # Project-related variables
            event_cmd = event_cmd.replace('$(PROJECTDIR)', context.get('project_dir', project_dir))
            event_cmd = event_cmd.replace('$(PROJECTPATH)', context.get('project_path', ''))
            event_cmd = event_cmd.replace('$(PROJECTFILENAME)', context.get('project_filename', ''))
            event_cmd = event_cmd.replace('$(PROJECTNAME)', context.get('project_name', ''))
            
            # Input file-related variables
            event_cmd = event_cmd.replace('$(INPUTPATH)', context.get('input_path', ''))
            event_cmd = event_cmd.replace('$(INPUTFILENAME)', context.get('input_filename', ''))
            event_cmd = event_cmd.replace('$(INPUTEXT)', context.get('input_ext', ''))
            
            # Output file-related variables
            event_cmd = event_cmd.replace('$(OUTPUTDIR)', context.get('output_dir', ''))
            event_cmd = event_cmd.replace('$(OUTPUTPATH)', context.get('output_path', ''))
            event_cmd = event_cmd.replace('$(OUTPUTFILENAME)', context.get('output_filename', ''))
            event_cmd = event_cmd.replace('$(OUTPUTEXT)', context.get('output_ext', ''))
            
            # Configuration-related variables
            event_cmd = event_cmd.replace('$(Config)', context.get('config', 'Debug'))
            event_cmd = event_cmd.replace('$(Platform)', context.get('platform', 'Win32'))
            event_cmd = event_cmd.replace('$(DEFINES)', context.get('defines', ''))
            
            # Path-related variables
            event_cmd = event_cmd.replace('$(DIR)', context.get('dir', project_dir))
            event_cmd = event_cmd.replace('$(INCLUDEPATH)', context.get('include_path', ''))
            event_cmd = event_cmd.replace('$(PATH)', context.get('path', ''))
            
            # Delphi environment variables
            event_cmd = event_cmd.replace('$(BDS)', context.get('bds', ''))
            event_cmd = event_cmd.replace('$(LOCALCOMMAND)', context.get('local_command', ''))
            
            # System variables
            event_cmd = event_cmd.replace('$(SystemRoot)', context.get('system_root', ''))
            event_cmd = event_cmd.replace('$(WINDIR)', context.get('windir', ''))
        
        # Variable replacement compatible with older versions
        event_cmd = event_cmd.replace('$(PROJECTDIR)', project_dir)
        
        try:
            logger.warning("Build event comes from .dproj file configuration; please ensure the project file is trusted")
            # Use console encoding (may be UTF-8 or GBK) to ensure cmd.exe correctly reads Chinese paths
            batch_encoding = get_console_encoding()
            with tempfile.NamedTemporaryFile(
                mode='w', suffix='.bat', delete=False, encoding=batch_encoding
            ) as bat_f:
                bat_f.write('@echo off\n')
                bat_f.write(event_cmd + '\n')
                bat_path = bat_f.name
            
            try:
                result = subprocess.run(
                    ['cmd.exe', '/c', bat_path],
                    cwd=project_dir,
                    capture_output=True,
                    encoding=get_console_encoding(),
                    timeout=timeout,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                )
            finally:
                try:
                    os.unlink(bat_path)
                except OSError:
                    pass
            
            if result.returncode != 0 and not ignore_exit_code:
                error_msg = "%s failed (exit code %d): %s" % (event_name, result.returncode, result.stderr)
                logger.error(error_msg)
                return (False, error_msg, result.stdout + result.stderr)
            
            logger.info("%s executed successfully", event_name)
            if result.stdout:
                logger.debug("%s output: %s", event_name, result.stdout)
            
            return (True, None, result.stdout + result.stderr)
            
        except subprocess.TimeoutExpired:
            error_msg = "%s execution timed out (%d seconds)" % (event_name, timeout)
            logger.error(error_msg)
            return (False, error_msg, None)
        except Exception as e:
            error_msg = "%s execution failed: %s" % (event_name, str(e))
            logger.error(error_msg, exc_info=True)
            return (False, error_msg, None)

    def _extract_config_from_dproj(self, project_path: str, options: 'CompileOptions') -> 'CompileOptions':
        """
        Extract configuration from .dproj file

        Args:
            project_path: Project file path (.dproj or .dpr)
            options: Original compile options

        Returns:
            Merged compile options
        """
        # If a .dpr/.dpk file is passed in, find the corresponding .dproj file
        if project_path.endswith('.dpr') or project_path.endswith('.dpk'):
            ext = '.dpr' if project_path.endswith('.dpr') else '.dpk'
            dproj_path = project_path[:-len(ext)] + '.dproj'
            if not Path(dproj_path).exists():
                logger.info(f"Corresponding .dproj file not found: {dproj_path}")
                return options
        elif project_path.endswith('.dproj'):
            dproj_path = project_path
        else:
            return options

        # Parse .dproj file
        parser = DprojParser(dproj_path)
        if not parser.parse():
            logger.warning(f"Failed to parse .dproj file: {dproj_path}")
            return options

        # Get configuration and platform
        config = options.build_configuration
        platform = "Win64" if options.target_platform == TargetPlatform.WIN64 else "Win32"

        # Extract unit search paths
        # 1. First get base paths (without limiting configuration and platform)
        # 2. Then get platform-specific paths
        # 3. Merge all paths
        base_unit_paths = parser.get_unit_search_paths()
        platform_unit_paths = parser.get_unit_search_paths(config, platform)
        dproj_unit_paths = base_unit_paths + platform_unit_paths
        
        if dproj_unit_paths:
            # Merge user-specified paths and paths from .dproj
            all_paths = list(options.unit_search_paths) + dproj_unit_paths
            # Deduplicate
            options.unit_search_paths = list(dict.fromkeys(all_paths))
            logger.info(f"Extracted {len(dproj_unit_paths)} unit search paths from .dproj file")

        # Extract conditional compilation symbols
        dproj_defines = parser.get_conditional_defines(config, platform)
        if dproj_defines:
            all_defines = list(options.conditional_defines) + dproj_defines
            options.conditional_defines = list(dict.fromkeys(all_defines))
            logger.info(f"Extracted {len(dproj_defines)} conditional compilation symbols from .dproj file")

        # Extract output path
        if not options.output_path:
            dproj_output = parser.get_output_path(config, platform)
            if dproj_output:
                options.output_path = dproj_output
                logger.info(f"Extracted output path from .dproj file: {dproj_output}")

        # Intelligently resolve third-party library paths
        # Note: If the user explicitly passes unit_search_paths, the resolver returns directly and does not perform intelligent analysis
        try:
            logger.info("Starting to resolve third-party library paths...")
            resolver = SmartLibraryPathResolver()
            
            # Resolve registry_version (shares the same strategy as the RTL library search path),
            # so third-party library paths filter the registry by the same Delphi version and avoid mixing versions.
            from ..utils.delphi_versions import resolve_registry_version
            project_settings = load_project_settings(project_path)
            resolver_compiler = options.compiler_version
            if not resolver_compiler and project_settings:
                resolver_compiler = project_settings.compiler_version
            resolver_version = resolve_registry_version(
                resolver_compiler,
                parser.get_project_version(),
                self.config_manager,
                override_version=(
                    project_settings.delphi_version if project_settings else None
                ),
            )
            
            # Pass in user-specified paths; the resolver will determine whether to skip intelligent analysis
            user_provided_paths = list(options.unit_search_paths) if options.unit_search_paths else None
            resolved_paths, info = resolver.resolve_library_paths(
                project_path, 
                platform,
                user_search_paths=user_provided_paths,
                version=resolver_version,
            )
            
            if info.get("mode") == "user_provided":
                logger.info(f"Using {len(resolved_paths)} user-specified paths")
            elif resolved_paths:
                options.unit_search_paths = resolved_paths
                logger.info(f"Intelligent resolution selected {len(resolved_paths)} third-party library paths"
                           f" (filtered from {info.get('total_paths_count', 0)} global paths, "
                           f"resolved {info.get('resolved_units', 0)} unit dependencies)")
                logger.debug(f"Resolution details: {info}")
            
            # Record units that were not found
            if info.get('still_missing_units'):
                logger.warning(f"Still {len(info['still_missing_units'])} units not found: "
                             f"{info['still_missing_units'][:5]}")
                
        except Exception as e:
            logger.warning(f"Failed to intelligently resolve third-party library paths: {e}; using default method")

        return options

    async def compile_dpr_direct(self, request: ProjectCompileRequest) -> CompileResult:
        """
        Compile .dpr file directly using dcc32/dcc64 (without relying on .dproj)

        Args:
            request: Project compile request

        Returns:
            Compile result
        """
        logger.info(f"Compiling .dpr file directly: {request.project_path}")
        start_time = time.time()

        # Direct dcc compilation only supports .dpr/.dpk; .dproj must use MSBuild
        if request.project_path.lower().endswith('.dproj'):
            error_msg = ".dproj files cannot be compiled directly with dcc; MSBuild must be used"
            logger.error(error_msg)
            return CompileResult(
                status=CompileStatus.FAILED,
                error_code="DPROJ_REQUIRES_MSBUILD",
                error_message=error_msg,
                duration=0
            )

        try:
            # 1. Validate project path
            is_valid, error_msg = self.validator.validate_project_path(request.project_path)
            if not is_valid:
                logger.error(f"Project path validation failed: {error_msg}")
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="INVALID_PROJECT_PATH",
                    error_message=error_msg,
                    duration=int((time.time() - start_time) * 1000)
                )

            # 1.5 Extract configuration from .dproj in the same directory (conditional compilation symbols/search paths/output path)
            # Direct DCC compilation does not automatically read .dproj; DCC_Define for that configuration must be merged manually,
            # otherwise conditional compilation symbols in the default configuration (such as Debug) will not take effect and the produced exe will be "plain"
            try:
                self._extract_config_from_dproj(request.project_path, request.options)
            except Exception as e:
                logger.debug("Failed to extract configuration from .dproj (continuing direct compilation): %s", e)

            # 2. Determine output path - defaults to Win32/Debug subdirectory
            project_dir = str(Path(request.project_path).parent)
            project_name = Path(request.project_path).stem

            if request.options.output_path:
                output_base = request.options.output_path
            else:
                # Prefer reading DCC_ExeOutput from .dproj in the same directory
                dproj_path = Path(request.project_path).with_suffix('.dproj')
                dproj_output = None
                if dproj_path.exists():
                    try:
                        from ..utils.dproj_parser import DprojParser
                        parser = DprojParser(str(dproj_path))
                        if parser.parse():
                            plat_map = {"win32": "Win32", "win64": "Win64"}
                            plat_dir = plat_map.get(request.options.target_platform.lower(), "Win32")
                            cfg = request.options.build_configuration or "Debug"
                            dproj_output = parser.get_output_path(config=cfg, platform=plat_dir)
                    except Exception:
                        logger.debug("Failed to read .dproj DCC_ExeOutput; using default path")

                if dproj_output:
                    output_base = dproj_output
                else:
                    from ..services.args_generator import ArgsGenerator
                    lib_dir = ArgsGenerator._PLATFORM_LIB_DIR.get(request.options.target_platform, 'Win32')
                    cfg = request.options.build_configuration or "Debug"
                    output_base = str(Path(project_dir) / lib_dir / cfg)

            # Ensure output directory exists
            Path(output_base).mkdir(parents=True, exist_ok=True)

            # 3. Get compiler configuration (explicit version > project configuration > default compiler)
            # Project-level configuration (.daofy/project.json) takes precedence, ensuring different projects on the same machine
            # use their respectively declared Delphi versions, and if the project-specified version is missing, fail directly without silent fallback.
            project_settings = load_project_settings(request.project_path)
            if project_settings and project_settings.error:
                logger.error(project_settings.error)
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="PROJECT_CONFIG_INVALID",
                    error_message=project_settings.error,
                    duration=int((time.time() - start_time) * 1000),
                )
            compiler_config, compiler_path, compiler_error = self._resolve_project_compiler(
                request.project_path,
                request.options.compiler_version,
                request.options.target_platform,
                project_settings,
            )
            if compiler_error:
                logger.error(compiler_error)
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="COMPILER_NOT_FOUND",
                    error_message=compiler_error,
                    duration=int((time.time() - start_time) * 1000)
                )
            if compiler_config:
                compiler_path = compiler_config.path
            if not compiler_path:
                error_msg = "No default compiler configured and unable to find one automatically"
                logger.error(error_msg)
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="COMPILER_NOT_FOUND",
                    error_message=error_msg,
                    duration=int((time.time() - start_time) * 1000)
                )

            # 4. Select compiler according to target platform
            target_platform = request.options.target_platform
            if target_platform != TargetPlatform.WIN32:
                compiler_name = self._get_platform_compiler_name(target_platform)
                bin_dir = Path(compiler_path).parent
                target_compiler = str(bin_dir / compiler_name)
                if Path(target_compiler).exists():
                    compiler_path = target_compiler
                    logger.info(f"Switched to {target_platform.value} compiler: {compiler_path}")
                else:
                    # Cross-platform compiler does not exist; fall back to lookup (prefer the current compiler version)
                    fallback_version = (
                        compiler_config.registry_version
                        if compiler_config
                        else (project_settings.delphi_version if project_settings else None)
                    )
                    found = self._find_compiler_from_registry(
                        target_platform,
                        fallback_version,
                    )
                    if found:
                        compiler_path = found
                        logger.info(f"Found {target_platform.value} compiler from registry: {compiler_path}")
                    else:
                        logger.warning(f"{target_platform.value} compiler ({compiler_name}) not found; trying to use dcc32")

            # 5. Validate compiler path
            is_valid, error_msg = self.validator.validate_compiler_path(compiler_path)
            if not is_valid:
                logger.error(f"Compiler path validation failed: {error_msg}")
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="INVALID_COMPILER_PATH",
                    error_message=error_msg,
                    duration=int((time.time() - start_time) * 1000)
                )

            # 6. Check whether the target program is running
            running_process = self._check_process_running(project_name)
            if running_process:
                error_msg = f"Target program '{project_name}.exe' is running (PID: {running_process['pid']}) and cannot be compiled. Please close the program and try again."
                logger.warning(error_msg)
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="PROCESS_RUNNING",
                    error_message=error_msg,
                    duration=int((time.time() - start_time) * 1000),
                    log=f"Process information: PID={running_process['pid']}, path={running_process.get('path', 'unknown')}"
                )

            # 7. Generate command-line arguments
            args = self._generate_dpr_args(request.project_path, request.options, output_base, compiler_path)

            # 8. Validate arguments
            if not self.args_generator.validate_args(args):
                logger.error("Argument validation failed")
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="INVALID_ARGS",
                    error_message="Compile arguments contain invalid characters",
                    duration=int((time.time() - start_time) * 1000)
                )

            logger.info(f"Compile command: {compiler_path} {' '.join(args)}")

            # 9. Execute compilation
            try:
                return_code, stdout, stderr = await self.process_manager.execute(
                    compiler_path,
                    args,
                    request.options.timeout
                )

                # 10. Parse output
                errors = self.output_parser.parse_errors(stdout + stderr)
                warnings = self.output_parser.parse_warnings(stdout + stderr)

                # 11. Build result
                duration = int((time.time() - start_time) * 1000)
                output_file = str(Path(output_base) / f"{project_name}.exe")

                if return_code == 0:
                    output_files = self._collect_output_files(
                        request.project_path,
                        request.options.target_platform.value,
                        request.options.build_configuration or "Debug",
                        output_base,
                    )
                    result = CompileResult(
                        status=CompileStatus.SUCCESS,
                        output_file=output_file,
                        output_files=output_files,
                        warnings=warnings,
                        errors=errors,
                        duration=duration,
                        log=stdout + stderr
                    )
                    logger.info(f"Compilation succeeded, output file: {output_file}, duration {duration}ms")
                else:
                    result = CompileResult(
                        status=CompileStatus.FAILED,
                        error_code="COMPILATION_FAILED",
                        error_message=self.output_parser.extract_error_summary(stdout + stderr),
                        warnings=warnings,
                        errors=errors,
                        duration=duration,
                        log=stdout + stderr
                    )
                    logger.error(f"Compilation failed, duration {duration}ms")

                # 12. Save compilation history
                self._save_history(request.project_path, result.status.value, duration, result.error_message)

                return result

            except TimeoutError as e:
                duration = int((time.time() - start_time) * 1000)
                logger.error(f"Compilation timed out: {str(e)}")
                result = CompileResult(
                    status=CompileStatus.TIMEOUT,
                    error_code="COMPILATION_TIMEOUT",
                    error_message=str(e),
                    duration=duration
                )
                self._save_history(request.project_path, result.status.value, duration, str(e))
                return result

        except Exception as e:
            duration = int((time.time() - start_time) * 1000)
            error_msg = f"Exception occurred during direct compilation: {str(e)}"
            logger.error(error_msg, exc_info=True)
            result = CompileResult(
                status=CompileStatus.FAILED,
                error_code="INTERNAL_ERROR",
                error_message=error_msg,
                duration=duration
            )
            self._save_history(request.project_path, result.status.value, duration, error_msg)
            return result

    def _generate_dpr_args(self, project_path: str, options: 'CompileOptions', output_base: str,
                           compiler_path: Optional[str] = None) -> list[str]:
        """Generate direct compilation arguments for .dpr file

        Args:
            project_path: .dpr file path
            options: Compile options
            output_base: Output directory (stores .exe file)
            compiler_path: Actual selected dcc32/dcc64 compiler path (used when registry is unavailable
                to derive RTL library search paths from the compiler's own directory, ensuring -U is always emitted)
        """
        from ..utils.delphi_env import (
            expand_delphi_path_macros,
            get_delphi_library_paths,
            get_delphi_root_dir,
        )

        args = []

        # Project file
        args.append(project_path)

        # Output directory (stores .exe file)
        args.append(f'-E{output_base}')

        # Intermediate file directory (stores .dcu files)
        dcu_dir = None
        dproj_path_dcu = Path(project_path).with_suffix('.dproj')
        project_version = None  # .dproj <ProjectVersion>, used to infer registry_version
        if dproj_path_dcu.exists():
            try:
                from ..utils.dproj_parser import DprojParser
                parser = DprojParser(str(dproj_path_dcu))
                if parser.parse():
                    plat_map = {"win32": "Win32", "win64": "Win64"}
                    plat_dir = plat_map.get(options.target_platform.lower(), "Win32")
                    cfg = options.build_configuration or "Debug"
                    dcu_dir = parser.get_dcu_output_path(config=cfg, platform=plat_dir)
                    project_version = parser.get_project_version()
            except Exception:
                logger.debug("Failed to read .dproj DCC_DcuOutput; using default path")
        if not dcu_dir:
            dcu_dir = output_base
        args.append(f'-N{dcu_dir}')

        # Conditional compilation symbols (note: defines syntax is -D, -$D+ is the debug information switch; the two must not be mixed up)
        if options.conditional_defines:
            defines = ";".join(options.conditional_defines)
            args.append(f'-D{defines}')

        # Namespace search paths - by default add System and other RTL/VCL namespaces,
        # and merge DCC_Namespace from .dproj in the same directory (consistent with compile_file single-file path),
        # so short unit names such as uses SysUtils and uses Classes can resolve to System.SysUtils, etc.
        default_namespaces = ["System", "Winapi", "System.Win", "Vcl", "Vcl.Imaging",
                              "Vcl.Touch", "Vcl.Samples", "Vcl.Shell", "Data", "Datasnap",
                              "Web", "Soap", "Xml",
                              "Common", "Protocol", "Engine", "Security", "Transport",
                              "Integration", "Platforms"]
        project_namespaces: list[str] = []
        if dproj_path_dcu and dproj_path_dcu.exists():
            try:
                from ..utils.dproj_parser import DprojParser
                ns_parser = DprojParser(str(dproj_path_dcu))
                if ns_parser.parse():
                    project_namespaces = ns_parser.get_namespace() or []
            except Exception:
                logger.debug("Failed to read .dproj DCC_Namespace; using only default namespaces")
        if project_namespaces:
            namespaces = list(dict.fromkeys(project_namespaces + default_namespaces))
        else:
            namespaces = default_namespaces
        args.append('-NS' + ";".join(namespaces))

        # Unit search paths - if not provided, automatically obtain Delphi default library search paths
        unit_paths = options.unit_search_paths if options.unit_search_paths else []
        if not unit_paths:
            # Automatically obtain Delphi library search paths
            # Use target platform name (first letter capitalized, used for registry query)
            from ..services.args_generator import ArgsGenerator
            platform = ArgsGenerator._PLATFORM_LIB_DIR.get(options.target_platform, 'Win32')
            # Get the Delphi version number (registry_version) corresponding to the compiler, used to read search paths for that version
            # Shares resolve_registry_version with third-party library path resolution, ensuring consistent version filtering strategy in both places
            from ..utils.delphi_versions import resolve_registry_version
            settings = load_project_settings(project_path)
            resolver_compiler = options.compiler_version
            if not resolver_compiler and settings:
                resolver_compiler = settings.compiler_version
            registry_version = resolve_registry_version(
                resolver_compiler,
                project_version,
                self.config_manager,
                override_version=settings.delphi_version if settings else None,
            )
            # Manually configured compilers may not have registry_version: infer from installation path/compiler output
            if not registry_version and compiler_path:
                for parent in Path(compiler_path).parents:
                    inferred = project_version_to_registry_version(parent.name)
                    if inferred:
                        registry_version = inferred
                        break
                if not registry_version:
                    registry_version = detect_registry_version_from_compiler(
                        compiler_path
                    )
            delphi_lib_paths = get_delphi_library_paths(version=registry_version, platform=platform)
            # Expand macro variables in paths
            for p in delphi_lib_paths:
                expanded = expand_delphi_path_macros(p, version=registry_version, platform=platform)
                if expanded and expanded not in unit_paths:
                    unit_paths.append(expanded)

            # Fallback: when registry/version resolution fails (e.g. no .dproj and the compiler is manually configured/not in the registry),
            # delphi_lib_paths may be empty. dcc32, unlike the IDE, has no built-in default library search paths;
            # if -U is not passed at all, RTL units such as SysUtils/Classes cannot be resolved causing compilation failure.
            # Therefore derive the RTL path from the compiler's own directory: <root>/lib/<platform>/release.
            if not unit_paths:
                rtl_candidates: list[str] = []
                # 1. Derive from the directory containing dcc32/dcc64 (the parent of bin/ is the Delphi root directory)
                if compiler_path:
                    compiler_root = Path(compiler_path).resolve().parent.parent
                    rtl_candidates.append(str(compiler_root / "lib" / platform / "release"))
                    rtl_candidates.append(str(compiler_root / "lib" / "win32" / "release"))
                # 2. Try deriving from the registry root directory
                try:
                    root_dir = get_delphi_root_dir(registry_version) if registry_version else None
                    if not root_dir:
                        root_dir = get_delphi_root_dir()
                    if root_dir:
                        rtl_candidates.append(str(Path(root_dir) / "lib" / platform / "release"))
                except Exception:
                    logger.debug("Failed to derive RTL path from registry root directory")
                for cand in rtl_candidates:
                    cand_path = Path(cand)
                    if cand_path.is_dir() and str(cand_path).lower() not in {
                            p.lower() for p in unit_paths}:
                        unit_paths.append(str(cand_path))
                        logger.info("Derived RTL unit search path from compiler/registry directory: %s", cand_path)
        
        if unit_paths:
            paths = ";".join(unit_paths)
            args.append(f'-U{paths}')

        # Resource search paths
        if options.resource_search_paths:
            paths = ";".join(options.resource_search_paths)
            args.append(f'-R{paths}')

        # Optimization options
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
        args.append(f'-$W{options.warning_level}')

        # Disable warnings
        for warning in options.disabled_warnings:
            args.append(f'-$W-{warning}')

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

        logger.debug(f"Generated .dpr compile arguments: {' '.join(args)}")
        return args

    @staticmethod
    @staticmethod
    def _get_platform_compiler_name(platform: TargetPlatform) -> str:
        """Return the compiler executable name for the target platform"""
        _PLATFORM_COMPILER_MAP = {
            TargetPlatform.WIN32: 'dcc32.exe',
            TargetPlatform.WIN64: 'dcc64.exe',
            TargetPlatform.OSX64: 'dccosx64.exe',
            TargetPlatform.OSXARM64: 'dccosxarm64.exe',
            TargetPlatform.IOSDEVICE64: 'dcciosarm64.exe',
            TargetPlatform.IOSDEVICE: 'dcciosarm64.exe',
            TargetPlatform.IOSSIMULATOR: 'dcciosarm64.exe',
            TargetPlatform.ANDROID: 'dccaarm.exe',
            TargetPlatform.ANDROID64: 'dccaac64.exe',
            TargetPlatform.LINUX64: 'dcclinux64.exe',
        }
        return _PLATFORM_COMPILER_MAP.get(platform, 'dcc32.exe')

    def _find_compiler_from_registry(
        self,
        platform: TargetPlatform,
        version: Optional[str] = None,
    ) -> Optional[str]:
        """Find the compiler path for the specified platform from the registry

        Args:
            platform: Target platform
            version: Delphi registry version number; when None, use the latest installed version
        """
        root_dir = self._get_delphi_root_from_registry(version)
        if not root_dir:
            return None

        compiler_name = self._get_platform_compiler_name(platform)
        compiler_path = Path(root_dir) / "bin" / compiler_name
        if compiler_path.exists():
            return str(compiler_path)

        return None

    def _find_dcc32_from_registry(self) -> Optional[str]:
        """Find the dcc32.exe path from the registry (backward compatible)"""
        return self._find_compiler_from_registry(TargetPlatform.WIN32)

    @staticmethod
    def _parse_msbuild_property(argument: str) -> Optional[tuple[str, str]]:
        """Parse one MSBuild property argument using any supported prefix."""
        lowered = argument.lower()
        for prefix in ("/p:", "-p:", "/property:", "-property:"):
            if not lowered.startswith(prefix):
                continue
            assignment = argument[len(prefix):]
            if "=" not in assignment:
                return None
            name, value = assignment.split("=", 1)
            if not name:
                return None
            return name.lower(), value
        return None

    def _resolve_msbuild_registry_version(
        self,
        request: ProjectCompileRequest,
        parser: DprojParser,
        project_parsed: bool,
        project_settings: Optional[ProjectSettings] = None,
    ) -> Optional[str]:
        """Resolve the one Delphi registry version used by an MSBuild run.

        Priority: explicit compiler version > project settings (compiler_version /
        delphi_version) > .dproj ProjectVersion inference.
        """
        if project_settings is None:
            project_settings = load_project_settings(request.project_path)

        if project_settings and project_settings.error:
            logger.error(project_settings.error)
            return None

        self._warn_conflicting_project_versions(project_settings)
        explicit_compiler = request.options.compiler_version
        project_compiler = project_settings.compiler_version if project_settings else None
        compiler_version = explicit_compiler or project_compiler

        if compiler_version:
            compiler = None
            compiler_getter = getattr(self.config_manager, "get_compiler", None)
            if callable(compiler_getter):
                try:
                    compiler = compiler_getter(compiler_version)
                except Exception:
                    logger.warning(
                        "Failed to find compiler configuration: %s", compiler_version, exc_info=True
                    )
            if compiler and compiler.registry_version:
                return compiler.registry_version
            if compiler and compiler.path:
                for parent in Path(compiler.path).parents:
                    registry_version = project_version_to_registry_version(parent.name)
                    if registry_version:
                        logger.info(
                            "Inferred registry_version from compiler path: %s -> %s",
                            compiler.path,
                            registry_version,
                        )
                        return registry_version
                registry_version = detect_registry_version_from_compiler(compiler.path)
                if registry_version:
                    logger.info(
                        "Inferred registry_version from compiler output: %s -> %s",
                        compiler.path,
                        registry_version,
                    )
                    return registry_version

            # Support writing the version number/product name directly into compiler_version (e.g. "11.0", "XE4")
            version_hint = normalize_version_key(compiler_version)
            if version_hint:
                logger.info(
                    "compiler_version=%r interpreted as Delphi version registry_version=%s",
                    compiler_version,
                    version_hint,
                )
                return version_hint

            # When compiler_version in project config is wrong, delphi_version can still serve as
            # an explicit version declaration; an explicitly passed invalid value from a tool call fails directly to avoid masking the issue.
            if (
                not explicit_compiler
                and project_settings
                and project_settings.delphi_version
            ):
                logger.warning(
                    "Unable to parse project-configured compiler_version=%r, using delphi_version=%s",
                    compiler_version,
                    project_settings.delphi_version,
                )
                return project_settings.delphi_version

            logger.error(
                "Cannot determine registry_version for explicit compiler %s; refusing to fall back to another Delphi version",
                compiler_version,
            )
            return None

        if project_settings and project_settings.delphi_version:
            project_version = parser.get_project_version() if project_parsed else None
            logger.info(
                "Using project config %s delphi_version=%s (ignoring .dproj ProjectVersion=%s)",
                project_settings.source,
                project_settings.delphi_version,
                project_version or "unknown",
            )
            return project_settings.delphi_version

        if project_parsed:
            project_version = parser.get_project_version()
            if project_version:
                registry_version = project_version_to_registry_version(project_version)
                if registry_version:
                    return registry_version

        logger.warning(
            "Cannot determine the Delphi registry_version for the project; "
            "will use the rsvars default selection and skip EnvOptions compatibility handling"
        )
        return None

    @staticmethod
    def _write_env_options_overlay(
        status: EnvOptionsLibraryStatus,
        platform: str,
    ) -> str:
        """Write a short-lived EnvOptions overlay for an MSBuild invocation."""
        content = build_env_options_overlay(
            status.env_options_path,
            status.registry_paths,
            platform,
        )
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".proj",
            prefix="daofy-envoptions-",
            delete=False,
            encoding="utf-8",
            newline="\n",
        ) as overlay:
            overlay.write(content)
            return overlay.name

    @staticmethod
    def _remove_temp_file(file_path: Optional[str]) -> None:
        """Remove a compiler temporary file without hiding cleanup failures."""
        if not file_path:
            return
        try:
            os.unlink(file_path)
        except FileNotFoundError:
            return
        except OSError as exc:
            logger.warning("Failed to delete temporary file %s: %s", file_path, exc)

    async def compile_project_with_msbuild(self, request: ProjectCompileRequest) -> CompileResult:
        """
        Compile a Delphi project using MSBuild

        Args:
            request: Project compile request

        Returns:
            Compile result
        """
        logger.info(f"Compiling project using MSBuild: {request.project_path}")
        start_time = time.time()
        batch_file: Optional[str] = None
        env_options_overlay: Optional[str] = None
        
        try:
            # 1. Validate project path
            is_valid, error_msg = self.validator.validate_project_path(request.project_path)
            if not is_valid:
                logger.error(f"Project path validation failed: {error_msg}")
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="INVALID_PROJECT_PATH",
                    error_message=error_msg,
                    duration=int((time.time() - start_time) * 1000)
                )
            
            # 3. Determine the project file (.dproj)
            if request.project_path.endswith(('.dpr', '.dpk')):
                ext = '.dpr' if request.project_path.endswith('.dpr') else '.dpk'
                dproj_path = request.project_path[:-len(ext)] + '.dproj'
                if not Path(dproj_path).exists():
                    error_msg = f"Corresponding .dproj file not found: {dproj_path}"
                    logger.error(error_msg)
                    return CompileResult(
                        status=CompileStatus.FAILED,
                        error_code="DPROJ_NOT_FOUND",
                        error_message=error_msg,
                        duration=int((time.time() - start_time) * 1000)
                    )
            elif request.project_path.endswith('.dproj'):
                dproj_path = request.project_path
            else:
                error_msg = "Project file must be a .dpr, .dpk, or .dproj file"
                logger.error(error_msg)
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="INVALID_PROJECT_FILE",
                    error_message=error_msg,
                    duration=int((time.time() - start_time) * 1000)
                )
            
            # 3. Load project-level configuration (.daofy/project.json / daofy.project.json)
            # Each project can independently specify the Delphi version and MSBuild to avoid cross-use on multi-version machines.
            project_settings = load_project_settings(dproj_path)
            if project_settings and project_settings.error:
                logger.error(project_settings.error)
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="PROJECT_CONFIG_INVALID",
                    error_message=project_settings.error,
                    duration=int((time.time() - start_time) * 1000),
                )

            # 4. Extract and execute build events
            _PLATFORM_MSBUILD_MAP = {
                TargetPlatform.WIN32: "Win32",
                TargetPlatform.WIN64: "Win64",
                TargetPlatform.OSX64: "OSX64",
                TargetPlatform.OSXARM64: "OSXARM64",
                TargetPlatform.IOSDEVICE64: "iOSDevice64",
                TargetPlatform.IOSDEVICE: "iOSDevice",
                TargetPlatform.IOSSIMULATOR: "iOSSimulator",
                TargetPlatform.ANDROID: "Android",
                TargetPlatform.ANDROID64: "Android64",
                TargetPlatform.LINUX64: "Linux64",
            }
            platform = _PLATFORM_MSBUILD_MAP.get(request.options.target_platform, "Win32")
            config = request.options.build_configuration or "Debug"
            
            # ── Defense: when /p:Platform or /p:Config in extra_args differs from options, extra_args wins ──
            # (the normal path is synchronized by the project.py wrapper; this is a fallback for direct compiler_service calls)

            _extra_args = request.options.extra_args or []
            _found_platform = _found_config = False
            for _ea in reversed(_extra_args):
                _property = self._parse_msbuild_property(_ea)
                if not _property:
                    continue
                _property_name, _property_value = _property
                if not _found_platform and _property_name == 'platform':
                    _extra_plat = _property_value
                    if _extra_plat.lower() != platform.lower():
                        logger.warning(
                            "extra_args /p:Platform=%s conflicts with options.target_platform=%s, "
                            "using extra_args value (MSBuild last-wins)",
                            _extra_plat, platform,
                        )
                        platform = _extra_plat
                        try:
                            request.options.target_platform = TargetPlatform(_extra_plat.lower())
                        except ValueError:
                            pass
                    _found_platform = True
                elif not _found_config and _property_name == 'config':
                    _extra_cfg = _property_value
                    if _extra_cfg != config:
                        logger.warning(
                            "extra_args /p:Config=%s conflicts with build_configuration=%s, "
                            "using extra_args value",
                            _extra_cfg, config,
                        )
                        config = _extra_cfg
                        request.options.build_configuration = _extra_cfg
                    _found_config = True
                if _found_platform and _found_config:
                    break

            parser = DprojParser(dproj_path)
            project_parsed = parser.parse()
            registry_version = self._resolve_msbuild_registry_version(
                request,
                parser,
                project_parsed,
                project_settings,
            )
            if (
                request.options.compiler_version
                or (project_settings and project_settings.compiler_version)
                or (project_settings and project_settings.error)
            ) and not registry_version:
                error_msg = (
                    project_settings.error
                    if project_settings and project_settings.error
                    else (
                        "Cannot determine the Delphi registry version for the specified compiler/project config; "
                        "compilation stopped to avoid mixing another Delphi version"
                    )
                )
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="COMPILER_VERSION_UNRESOLVED",
                    error_message=error_msg,
                    duration=int((time.time() - start_time) * 1000),
                )
            selected_bds = (
                self._get_delphi_root_from_registry(registry_version)
                if registry_version
                else None
            )
            if registry_version:
                logger.info(
                    "MSBuild using Delphi %s, platform %s, configuration %s",
                    registry_version,
                    platform,
                    config,
                )

            # 3.5 Resolve MSBuild per project (project config > version mapping > auto-detection)
            msbuild_path, msbuild_source, msbuild_explicit_error = (
                self._resolve_msbuild_path(registry_version, project_settings)
            )
            if not msbuild_path:
                error_msg = f"No usable MSBuild found ({msbuild_source})"
                logger.error(error_msg)
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code=(
                        "MSBUILD_CONFIG_INVALID"
                        if msbuild_explicit_error
                        else "MSBUILD_NOT_FOUND"
                    ),
                    error_message=error_msg,
                    duration=int((time.time() - start_time) * 1000),
                )

            # 3.6 First confirm the target Delphi version's rsvars.bat is available before executing build events.
            # Otherwise, when the version is not installed, PreBuildEvent will still run with the wrong BDS environment.
            if registry_version:
                logger.info("Locating rsvars.bat for Delphi %s", registry_version)
            rsvars_path = self._get_rsvars_path(registry_version)
            if not rsvars_path:
                error_msg = (
                    f"Unable to find rsvars.bat for Delphi {registry_version or 'default version'}, "
                    "please check whether that version is installed"
                )
                logger.error(error_msg)
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="RSVARS_NOT_FOUND",
                    error_message=error_msg,
                    duration=int((time.time() - start_time) * 1000),
                )
            if not selected_bds:
                selected_bds = str(Path(rsvars_path).parent.parent)
            
            project_dir = str(Path(dproj_path).parent)
            project_path = str(Path(dproj_path).parent)
            project_filename = Path(dproj_path).name
            project_name = Path(dproj_path).stem
            
            # 4.5 Check whether the target program is running
            running_process = self._check_process_running(project_name)
            if running_process:
                error_msg = f"Target program '{project_name}.exe' is running (PID: {running_process['pid']}), cannot compile. Please close the program and try again."
                logger.warning(error_msg)
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="PROCESS_RUNNING",
                    error_message=error_msg,
                    duration=int((time.time() - start_time) * 1000),
                    log=f"Process info: PID={running_process['pid']}, path={running_process.get('path', 'unknown')}"
                )
            
            # Build context variables (os is imported at the top of the module)
            context = {
                # Project-related
                'project_dir': project_dir,
                'project_path': project_path,
                'project_filename': project_filename,
                'project_name': project_name,
                
                # Input file-related (for project compilation, the input file is the project file)
                'input_path': project_path,
                'input_filename': project_filename,
                'input_ext': Path(dproj_path).suffix,
                
                # Output file-related
                'output_dir': request.options.output_path or project_dir,
                'output_path': request.options.output_path or project_dir,
                'output_filename': f"{project_name}.exe",
                'output_ext': '.exe',
                
                # Configuration-related
                'config': config,
                'platform': platform,
                'defines': ';'.join(request.options.conditional_defines) if request.options.conditional_defines else '',
                
                # Path-related
                'dir': project_dir,
                'include_path': ';'.join(request.options.unit_search_paths) if request.options.unit_search_paths else '',
                'path': os.environ.get('PATH', ''),
                
                # Delphi environment variables
                'bds': selected_bds or os.environ.get('BDS') or '',
                'local_command': '',
                
                # System variables
                'system_root': os.environ.get('SystemRoot', r'C:\Windows'),
                'windir': os.environ.get('WINDIR', r'C:\Windows'),
            }
            
            # Parse the .dproj file to get build events
            build_events = {}
            if project_parsed:
                build_events = parser.get_build_events(config, platform)
                
                # Execute PreBuildEvent
                if build_events.get('pre_build'):
                    success, error_msg, output = self._execute_build_event(
                        "PreBuildEvent",
                        build_events['pre_build'],
                        project_dir,
                        build_events.get('pre_build_ignore_exit_code', False),
                        60,
                        context
                    )
                    
                    if not success:
                        return CompileResult(
                            status=CompileStatus.FAILED,
                            error_code="PRE_BUILD_EVENT_FAILED",
                            error_message=error_msg,
                            duration=int((time.time() - start_time) * 1000),
                            log=output or ""
                        )
            
            # 5. Build MSBuild arguments
            args = []
            
            # Project file
            args.append(dproj_path)
            
            # ── Extract property names from extra_args and skip same-named properties generated by the tool ──
            # MSBuild properties in extra_args are the sole source, avoiding duplicate command-line properties and keeping semantics clear.
            _extra_prop_names = set()
            for _ea in (request.options.extra_args or []):
                _property = self._parse_msbuild_property(_ea)
                if _property:
                    _extra_prop_names.add(_property[0])
            
            # Target platform
            if 'platform' not in _extra_prop_names:
                args.append(f"/p:Platform={platform}")
            
            # Configuration (Debug/Release)
            if 'config' not in _extra_prop_names:
                args.append(f"/p:Config={config}")
            
            # Output path
            if request.options.output_path and 'dcc_exeoutput' not in _extra_prop_names:
                args.append(f"/p:DCC_ExeOutput={request.options.output_path}")
            
            # Conditional compilation symbols
            if request.options.conditional_defines and 'dcc_define' not in _extra_prop_names:
                defines = ";".join(request.options.conditional_defines)
                # On the MSBuild command line, semicolon is a property separator and must be escaped as %3B
                # When passed through a batch file, % must be written as %% for cmd.exe to expand correctly
                defines = defines.replace(";", "%%3B")
                args.append(f"/p:DCC_Define={defines}")
            
            # Unit search paths
            if request.options.unit_search_paths and 'dcc_unitsearchpath' not in _extra_prop_names:
                paths = ";".join(request.options.unit_search_paths)
                args.append(f"/p:DCC_UnitSearchPath={paths}")
            
            # Generate a Detailed-level .map file (for StackTrace callgraph parsing)
            if 'dcc_mapfile' not in _extra_prop_names:
                args.append("/p:DCC_MapFile=3")
            
            # Automatically enable response-file compilation for Delphi >= XE5 (registry version >= 12.0)
            # Solves compilation failures caused by an overly long MSBuild command line (>32K)
            if 'dcc_usemsbuildexternally' not in _extra_prop_names:
                try:
                    delphi_ver = registry_version or _get_delphi_version_env()
                    if delphi_ver and float(delphi_ver) >= 12.0:
                        args.append("/p:DCC_UseMSBuildExternally=true")
                        logger.info("Detected Delphi %s (>=XE5), enabled DCC_UseMSBuildExternally", delphi_ver)
                except Exception as e:
                    logger.warning("Failed to detect Delphi version, not enabling DCC_UseMSBuildExternally: %s", e)

            # Other arguments
            args.append("/v:minimal")  # Minimal output level

            # Append user arguments (properties already overridden in extra_args are the sole source here)
            if not self.args_generator.validate_batch_extra_args(request.options.extra_args):
                error_msg = "Extra compile arguments contain disallowed batch metacharacters"
                logger.error(error_msg)
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="INVALID_EXTRA_ARGS",
                    error_message=error_msg,
                    duration=int((time.time() - start_time) * 1000)
                )
            # 5. rsvars.bat has already been located and validated before executing build events (see 3.6)
            explicit_env_properties = {
                "bds",
                "bdsappdatabasedir",
                "envoptions",
                "importenvoptions",
                "delphilibrarypath",
                "productversion",
            }
            if registry_version and not (_extra_prop_names & explicit_env_properties):
                env_status = inspect_env_options_library_paths(
                    registry_version,
                    platform,
                )
                if env_status.state in ("missing", "stale"):
                    env_options_overlay = self._write_env_options_overlay(
                        env_status,
                        platform,
                    )
                    args.append(f"/p:EnvOptions={env_options_overlay}")
                    logger.warning(
                        "EnvOptions state for Delphi %s %s is %s; "
                        "this compilation uses a temporary overlay (registry %d entries, EnvOptions %d entries)",
                        registry_version,
                        platform,
                        env_status.state,
                        len(env_status.registry_paths),
                        len(env_status.env_options_paths),
                    )
                elif env_status.state == "unknown":
                    logger.warning(
                        "Cannot reliably check EnvOptions for Delphi %s %s, skipping automatic override",
                        registry_version,
                        platform,
                    )
                elif env_status.state == "registry_missing":
                    logger.debug(
                        "Delphi %s %s has no registry Library Search Path configured, using EnvOptions",
                        registry_version,
                        platform,
                    )
            elif _extra_prop_names & explicit_env_properties:
                logger.info("Explicit EnvOptions/DelphiLibraryPath arguments detected, skipping automatic compatibility handling")

            args.extend(request.options.extra_args)

            # Log the complete compile arguments
            # Use the resolved absolute MSBuild path instead of bare msbuild (which depends on PATH),
            # to avoid failing to find msbuild.exe when rsvars.bat has not added VS MSBuild to PATH.
            msbuild_cmd = f'"{msbuild_path}" {" ".join(args)}'
            logger.info(f"MSBuild arguments: {msbuild_cmd}")
            
            # 6. Create a temporary batch file to set the environment and execute MSBuild
            # Quote paths in the arguments (to handle spaces)
            quoted_args = []
            for arg in args:
                if ' ' in arg:
                    quoted_args.append('"%s"' % arg)
                else:
                    quoted_args.append(arg)
            # Write batch file using OEM code page encoding; cmd.exe only recognizes OEM encoding (UTF-8 is not supported)
            batch_encoding = get_console_encoding(oem=True)
            with tempfile.NamedTemporaryFile(mode='w', suffix='.bat', delete=False,
                                             encoding=batch_encoding) as f:
                f.write('@echo off\n')
                f.write('call "%s"\n' % rsvars_path)
                f.write('"%s" %s\n' % (msbuild_path, ' '.join(quoted_args)))
                batch_file = f.name
            
            logger.info("Creating batch file: %s", batch_file)
            logger.debug("=== Full compile command ===\n"
                         "rsp: %s\n%s" % (rsvars_path, msbuild_cmd))
            
            # 6. Execute batch file
            try:
                return_code, stdout, stderr = await self.process_manager.execute(
                    'cmd.exe',
                    ['/c', batch_file],
                    request.options.timeout
                )
                
                # Record compiler version/line count info in MSBuild output
                for line in (stdout or '').split('\n'):
                    line = line.strip()
                    if line and ('Embarcadero Delphi' in line or 'dcc' in line.lower() or 'lines' in line.lower()):
                        logger.debug(f"Compiler output: {line}")
                
                # 6. Parse output
                errors = self.output_parser.parse_errors(stdout + stderr)
                warnings = self.output_parser.parse_warnings(stdout + stderr)
                
                # 7. Build result
                duration = int((time.time() - start_time) * 1000)
                
                if return_code == 0:
                    # Compilation succeeded
                    # Execute PostBuildEvent
                    if build_events.get('post_build'):
                        # Check execution conditions
                        execute_when = build_events.get('post_build_execute_when', 'Always')
                        should_execute = False
                        
                        if execute_when == 'Always':
                            should_execute = True
                        elif execute_when == 'TargetOutOfDate':
                            # Execute when target is out of date (successful build means target has been updated)
                            should_execute = True
                        
                        if should_execute:
                            success, error_msg, output = self._execute_build_event(
                                "PostBuildEvent",
                                build_events['post_build'],
                                project_dir,
                                build_events.get('post_build_ignore_exit_code', False),
                                60,
                                context
                            )
                            
                            if not success:
                                logger.warning(f"PostBuildEvent failed, but compilation succeeded: {error_msg}")
                    
                    output_file = self._extract_output_file(stdout, request.options.output_path)
                    output_files = self._collect_output_files(
                        dproj_path,
                        request.options.target_platform.value,
                        config,
                        output_file if (output_file and Path(output_file).parent.exists()) else None,
                    )
                    # If _extract_output_file didn't find it (no Output: line in MSBuild output), backfill from output_files
                    if not output_file and output_files:
                        output_file = output_files[0]
                    result = CompileResult(
                        status=CompileStatus.SUCCESS,
                        output_file=output_file,
                        output_files=output_files,
                        warnings=warnings,
                        errors=errors,
                        duration=duration,
                        log=stdout + stderr
                    )
                    logger.info(f"MSBuild compilation succeeded, took {duration}ms")
                else:
                    # Compilation failed
                    result = CompileResult(
                        status=CompileStatus.FAILED,
                        error_code="COMPILATION_FAILED",
                        error_message=self.output_parser.extract_error_summary(stdout + stderr),
                        warnings=warnings,
                        errors=errors,
                        duration=duration,
                        log=stdout + stderr
                    )
                    logger.error(f"MSBuild compilation failed, took {duration}ms")
                
                # 8. Save compilation history
                self._save_history(request.project_path, result.status.value, duration, result.error_message)
                
                return result
                
            except TimeoutError as e:
                duration = int((time.time() - start_time) * 1000)
                logger.error(f"MSBuild compilation timed out: {str(e)}")
                result = CompileResult(
                    status=CompileStatus.TIMEOUT,
                    error_code="COMPILATION_TIMEOUT",
                    error_message=str(e),
                    duration=duration
                )
                self._save_history(request.project_path, result.status.value, duration, str(e))
                return result
                
        except Exception as e:
            duration = int((time.time() - start_time) * 1000)
            error_msg = f"Exception occurred during MSBuild compilation: {str(e)}"
            logger.error(error_msg, exc_info=True)
            result = CompileResult(
                status=CompileStatus.FAILED,
                error_code="INTERNAL_ERROR",
                error_message=error_msg,
                duration=duration
            )
            self._save_history(request.project_path, result.status.value, duration, error_msg)
            return result
        finally:
            self._remove_temp_file(batch_file)
            self._remove_temp_file(env_options_overlay)

    async def compile_with_lazbuild(self, request: ProjectCompileRequest) -> CompileResult:
        """
        Compile a Lazarus/Free Pascal project using lazbuild

        Args:
            request: Project compile request (project_path is .lpi or .lpr)

        Returns:
            Compilation result
        """
        logger.info(f"Compiling project using lazbuild: {request.project_path}")
        start_time = time.time()

        try:
            # 1. Find lazbuild path
            lazbuild_path = self._find_lazbuild()
            if not lazbuild_path:
                error_msg = ("lazbuild.exe not found. Please install Lazarus IDE."
                             "Download URL: https://www.lazarus-ide.org/")
                logger.error(error_msg)
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="LAZBUILD_NOT_FOUND",
                    error_message=error_msg,
                    duration=int((time.time() - start_time) * 1000)
                )

            # 2. Determine .lpi file path
            project_path = Path(request.project_path)
            ext = project_path.suffix.lower()
            if ext == '.lpr':
                lpi_path = project_path.with_suffix('.lpi')
                if not lpi_path.exists():
                    error_msg = f"Corresponding .lpi file not found: {lpi_path}"
                    logger.error(error_msg)
                    return CompileResult(
                        status=CompileStatus.FAILED,
                        error_code="LPI_NOT_FOUND",
                        error_message=error_msg,
                        duration=int((time.time() - start_time) * 1000)
                    )
            elif ext == '.lpi':
                lpi_path = project_path
            else:
                error_msg = "Lazarus project file must be a .lpi or .lpr file"
                logger.error(error_msg)
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="INVALID_LAZARUS_PROJECT",
                    error_message=error_msg,
                    duration=int((time.time() - start_time) * 1000)
                )

            # 3. Check whether target program is running
            project_name = project_path.stem
            running_process = self._check_process_running(project_name)
            if running_process:
                error_msg = (f"Target program '{project_name}.exe' is running "
                             f"(PID: {running_process['pid']}), cannot compile."
                             "Please close the program and try again.")
                logger.warning(error_msg)
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="PROCESS_RUNNING",
                    error_message=error_msg,
                    duration=int((time.time() - start_time) * 1000),
                    log=f"Process info: PID={running_process['pid']}, "
                        f"Path={running_process.get('path', 'Unknown')}"
                )

            # 4. Build lazbuild command line
            args = [str(lpi_path)]

            # Build mode: --build-mode=Default/Release/Debug
            if request.options.build_configuration:
                args.append(f"--build-mode={request.options.build_configuration}")

            # Platform: --ws=win32/win64
            platform_map = {
                TargetPlatform.WIN32: "win32",
                TargetPlatform.WIN64: "win64",
            }
            ws = platform_map.get(request.options.target_platform)
            if ws:
                args.append(f"--ws={ws}")

            logger.info(f"lazbuild command: {lazbuild_path} {' '.join(args)}")

            # 5. Execute compilation
            return_code, stdout, stderr = await self.process_manager.execute(
                lazbuild_path,
                args,
                request.options.timeout
            )

            # 6. Parse output
            output_text = stdout + stderr
            errors = self.output_parser.parse_errors(output_text)
            warnings = self.output_parser.parse_warnings(output_text)

            # 7. Build result
            duration = int((time.time() - start_time) * 1000)

            if return_code == 0:
                # Find output file
                exe_path = self._find_lazbuild_output(lpi_path)
                result = CompileResult(
                    status=CompileStatus.SUCCESS,
                    output_file=str(exe_path) if exe_path else None,
                    duration=duration,
                    warnings=warnings,
                    log=output_text,
                )
            else:
                error_message = f"lazbuild compilation failed (exit code: {return_code})"
                if errors:
                    error_message += f"\n{errors[0]}"

                result = CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="LAZBUILD_COMPILE_FAILED",
                    error_message=error_message,
                    duration=duration,
                    errors=errors,
                    warnings=warnings,
                    log=output_text,
                )

            self._save_history(request.project_path, result.status.value,
                               duration, result.error_message or "")
            return result

        except Exception as e:
            duration = int((time.time() - start_time) * 1000)
            error_msg = f"lazbuild compilation exception: {str(e)}"
            logger.error(error_msg, exc_info=True)
            result = CompileResult(
                status=CompileStatus.FAILED,
                error_code="INTERNAL_ERROR",
                error_message=error_msg,
                duration=duration,
            )
            self._save_history(request.project_path, result.status.value,
                               duration, error_msg)
            return result

    def _find_lazbuild(self) -> Optional[str]:
        """
        Find lazbuild.exe path

        Search order:
        1. Lazarus compiler path in configuration file
        2. Shared detection module (PATH → common directories → Start Menu → registry)

        Returns:
            lazbuild.exe path, or None if not found
        """
        # 1. Find Lazarus compiler from configuration file
        config = self.config_manager.config
        for compiler in config.compilers:
            if (getattr(compiler, 'compiler_type', None) == 'lazarus'
                    and compiler.path.lower().endswith('lazbuild.exe')):
                if Path(compiler.path).exists():
                    return compiler.path

        # 2. Shared detection module
        from src.plugins.lazarus.detect import find_lazbuild
        paths = find_lazbuild()
        if paths:
            return str(paths[0])

        return None

    def _find_lazbuild_output(self, lpi_path: Path) -> Optional[Path]:
        """
        Find lazbuild compilation output file

        Args:
            lpi_path: .lpi file path

        Returns:
            Output exe path
        """
        project_dir = lpi_path.parent
        project_name = lpi_path.stem
        exe_name = f"{project_name}.exe"

        # Prefer Lazarus default output directories
        output_dirs = [
            project_dir / "lib" / project_name,
            project_dir / "output",
            project_dir,
        ]

        for d in output_dirs:
            exe = d / exe_name
            if exe.exists():
                return exe

        return None

    async def compile_project(self, request: ProjectCompileRequest) -> CompileResult:
        """
        Compile Delphi/Lazarus project
        
        Prefer MSBuild to compile Delphi projects; if MSBuild is unavailable or there is no .dproj file, fall back to directly invoking the compiler
        For Lazarus projects (.lpi/.lpr), use lazbuild to compile

        Args:
            request: Project compile request

        Returns:
            Compilation result
        """
        logger.info(f"Starting project compilation: {request.project_path}")

        # Check project type
        ext = Path(request.project_path).suffix.lower()
        is_source_file = ext in ('.dpr', '.dpk')
        is_dproj = ext == '.dproj'
        is_lpi = ext == '.lpi'
        is_lpr = ext == '.lpr'

        # Lazarus project (.lpi/.lpr) uses lazbuild for compilation
        if is_lpi or is_lpr:
            return await self.compile_with_lazbuild(request)

        # Delphi project (.dproj) uses MSBuild for compilation

        if is_dproj:
            logger.info("Compiling .dproj file using MSBuild")
            # MSBuild availability is resolved by compile_project_with_msbuild according to project configuration,
            # and the globally detected path at initialization is no longer used for a pre-check here (it may differ on machines with multiple versions).
            result = await self.compile_project_with_msbuild(request)
            if result.error_code in ("MSBUILD_NOT_FOUND", "MSBUILD_CONFIG_INVALID"):
                logger.error(
                    "MSBuild is unavailable, cannot compile .dproj file: %s",
                    result.error_message,
                )
            return result

        # Check whether a .dproj file exists
        dproj_exists = False
        if is_source_file:
            dproj_path = request.project_path[:-len(ext)] + '.dproj'
            dproj_exists = Path(dproj_path).exists()
            if not dproj_exists:
                logger.info(f".dproj file not found, will use dcc32 to directly compile {ext} file")

        # .dpr/.dpk with .dproj → prefer MSBuild; fall back to direct dcc compilation when MSBuild is unavailable.
        # However, if an explicitly configured MSBuild path is invalid, it must fail directly; do not silently switch to direct compilation to hide configuration errors.
        if dproj_exists:
            logger.info("Compiling using MSBuild")
            result = await self.compile_project_with_msbuild(request)
            if result.error_code != "MSBUILD_NOT_FOUND":
                return result
            logger.warning(
                "MSBuild is unavailable, falling back to direct dcc compilation: %s",
                result.error_message,
            )

        logger.info(f"Directly compiling {ext} file using dcc")
        return await self.compile_dpr_direct(request)

    async def compile_file(self, request: FileCompileRequest) -> CompileResult:
        """
        Compile a single Delphi unit file (syntax check only)

        Args:
            request: Single-file compile request

        Returns:
            Compilation result
        """
        logger.info(f"Starting file compilation: {request.file_path}")
        start_time = time.time()

        try:
            # 1. Validate file path
            is_valid, error_msg = self.validator.validate_file_path(request.file_path)
            if not is_valid:
                logger.error(f"File path validation failed: {error_msg}")
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="INVALID_FILE_PATH",
                    error_message=error_msg,
                    duration=int((time.time() - start_time) * 1000)
                )

            # 2. Get compiler configuration (explicit version > project configuration > newest installed)
            # The file may belong to a project using an older Delphi version; project-level configuration takes precedence,
            # to avoid false positives/negatives in syntax checking caused by using the newest installed version.
            settings = load_project_settings(request.file_path)
            if settings and settings.error:
                logger.error(settings.error)
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="PROJECT_CONFIG_INVALID",
                    error_message=settings.error,
                    duration=int((time.time() - start_time) * 1000),
                )
            compiler_config = None
            if request.compiler_version:
                compiler_config = self._lookup_compiler_by_name_or_version(
                    request.compiler_version,
                    TargetPlatform.WIN32,
                )
            elif settings and settings.compiler_version:
                compiler_config = self._lookup_compiler_by_name_or_version(
                    settings.compiler_version,
                    TargetPlatform.WIN32,
                )
                if not compiler_config and settings.delphi_version:
                    # When compiler_version is wrong/unavailable, delphi_version is still an explicit declaration
                    compiler_config = (
                        self._lookup_compiler_by_version(
                            settings.delphi_version,
                            TargetPlatform.WIN32,
                        )
                        or self._compiler_from_registry_version(
                            settings.delphi_version,
                            TargetPlatform.WIN32,
                        )
                    )
            elif settings and settings.delphi_version:
                compiler_config = (
                    self._lookup_compiler_by_version(
                        settings.delphi_version,
                        TargetPlatform.WIN32,
                    )
                    or self._compiler_from_registry_version(
                        settings.delphi_version,
                        TargetPlatform.WIN32,
                    )
                )
            else:
                compiler_config = self.config_manager.get_newest_compiler()
            if not compiler_config:
                if settings and (settings.compiler_version or settings.delphi_version):
                    error_msg = (
                        f"Project configuration specifies an unavailable Delphi version"
                        f"（{settings.compiler_version or settings.delphi_version}）；"
                        "will not fall back to other versions"
                    )
                else:
                    error_msg = "No available compiler found"
                logger.error(error_msg)
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="COMPILER_NOT_FOUND",
                    error_message=error_msg,
                    duration=int((time.time() - start_time) * 1000)
                )

            # 3. Find project file and extract configuration
            file_dir = str(Path(request.file_path).parent)
            file_name = Path(request.file_path).stem

            # Try to find project file
            dproj_path = None
            project_unit_paths = []
            project_include_paths = []
            project_namespaces = []

            # Method 1: Find .dproj files in the same directory
            dproj_files = list(Path(file_dir).glob('*.dproj'))
            if dproj_files:
                # Prefer the project matching the file name; otherwise select the first one
                for dproj in dproj_files:
                    if dproj.stem == file_name:
                        dproj_path = str(dproj)
                        break
                if not dproj_path:
                    dproj_path = str(dproj_files[0])

            # Method 2: Check whether the file is in the project's DCCReference
            if dproj_path:
                try:
                    parser = DprojParser(dproj_path)
                    if parser.parse():
                        # Check whether the file belongs to the project
                        if parser.is_file_in_project(Path(request.file_path).name):
                            logger.info(f"File {Path(request.file_path).name} belongs to project {Path(dproj_path).name}")

                            # Extract unit search paths
                            project_unit_paths = parser.get_unit_search_paths()
                            logger.info(f"Extracted {len(project_unit_paths)} unit search paths from project file")

                            # Extract include paths (inferred from unit search paths)
                            for path in project_unit_paths:
                                if 'include' in path.lower():
                                    project_include_paths.append(path)

                            # Extract namespaces
                            project_namespaces = parser.get_namespace()
                            if project_namespaces:
                                logger.info(f"Extracted {len(project_namespaces)} namespaces from project file")
                        else:
                            logger.info(f"File {Path(request.file_path).name} does not belong to project {Path(dproj_path).name}")
                            dproj_path = None
                except Exception as e:
                    logger.warning(f"Failed to parse project file: {e}")
                    dproj_path = None

            # 4. Delete old .dcu files in the source file's directory
            self._cleanup_dcu_files(request.file_path)

            # 5. Prepare namespaces and include paths
            # Merge project namespaces and default namespaces
            default_namespaces = [
                "System", "Winapi", "System.Win", "Vcl", "Vcl.Imaging",
                "Vcl.Touch", "Vcl.Samples", "Vcl.Shell", "Data", "Datasnap",
                "Web", "Soap", "Xml"
            ]
            if project_namespaces:
                # Merge and deduplicate
                namespaces = list(dict.fromkeys(project_namespaces + default_namespaces))
            else:
                namespaces = default_namespaces

            # Merge include paths
            default_include_paths = [
                str(Path(file_dir) / "Thirdpart" / "Jedi" / "Jcl" / "source" / "include"),
                str(Path(file_dir) / "Thirdpart" / "Jedi" / "Jcl" / "source" / "include" / "jedi")
            ]
            if project_include_paths:
                include_paths = list(dict.fromkeys(project_include_paths + default_include_paths))
            else:
                include_paths = default_include_paths

            # Merge unit search paths
            # User-provided paths take precedence
            if project_unit_paths and request.unit_search_paths:
                all_unit_paths = list(dict.fromkeys(request.unit_search_paths + project_unit_paths))
                logger.info(f"Merged unit search paths: {len(request.unit_search_paths)} user + {len(project_unit_paths)} project")
            elif project_unit_paths:
                all_unit_paths = project_unit_paths
            else:
                all_unit_paths = request.unit_search_paths or []

            # Output directory - use a fixed absolute path
            output_dir = str(Path(file_dir) / "Win32" / "Debug")

            # Ensure output directory exists
            Path(output_dir).mkdir(parents=True, exist_ok=True)

            # 5. Get Delphi numeric version from compiler configuration, used for standard library paths
            delphi_version = compiler_config.registry_version
            if not delphi_version:
                # When registry is unavailable (e.g. manually configured compiler), parse from compiler --version output
                from ..utils.delphi_versions import detect_registry_version_from_compiler
                detected = detect_registry_version_from_compiler(compiler_config.path)
                if detected:
                    delphi_version = detected
                    logger.info(f"Detected version from compiler output: {delphi_version}")
                else:
                    delphi_version = None

            args = self.args_generator.generate_for_file(
                request.file_path,
                all_unit_paths,
                request.warning_level,
                request.disabled_warnings,
                namespaces=namespaces,
                include_paths=include_paths if include_paths else None,
                output_dir=output_dir,
                delphi_version=delphi_version,
                conditional_defines=request.conditional_defines,
                extra_args=request.extra_args,
            )

            # 5. Execute compilation
            return_code, stdout, stderr = await self.process_manager.execute(
                compiler_config.path,
                args,
                timeout=TIMEOUT_DELPHI_COMPILE  # 单文件编译超时时间较短
            )

            # 5. Parse output
            errors = self.output_parser.parse_errors(stdout + stderr)
            warnings = self.output_parser.parse_warnings(stdout + stderr)

            # 6. Build result
            duration = int((time.time() - start_time) * 1000)

            if return_code == 0:
                result = CompileResult(
                    status=CompileStatus.SUCCESS,
                    warnings=warnings,
                    errors=errors,
                    duration=duration,
                    log=stdout + stderr
                )
                logger.info(f"File compilation succeeded, took {duration}ms")
            else:
                result = CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="SYNTAX_ERROR",
                    error_message=self.output_parser.extract_error_summary(stdout + stderr),
                    warnings=warnings,
                    errors=errors,
                    duration=duration,
                    log=stdout + stderr
                )
                logger.error(f"File compilation failed, took {duration}ms")

            return result

        except Exception as e:
            duration = int((time.time() - start_time) * 1000)
            error_msg = f"Exception occurred during file compilation: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return CompileResult(
                status=CompileStatus.FAILED,
                error_code="INTERNAL_ERROR",
                error_message=error_msg,
                duration=duration
            )

    def get_args(self, request: ProjectCompileRequest) -> CommandArgs:
        """
        Get command-line arguments (without executing compilation)

        Args:
            request: Project compile request

        Returns:
            Command-line arguments object
        """
        logger.info(f"Generating command-line arguments: {request.project_path}")

        # Get compiler configuration (explicit version > project configuration > default compiler)
        settings = load_project_settings(request.project_path)
        compiler_config, compiler_path, compiler_error = self._resolve_project_compiler(
            request.project_path,
            request.options.compiler_version,
            request.options.target_platform,
            settings,
        )
        if compiler_error:
            raise ValueError(compiler_error)
        if compiler_config:
            compiler_path = compiler_config.path
        if not compiler_path:
            raise ValueError(
                f"Compiler configuration does not exist: "
                f"{request.options.compiler_version or 'default compiler'}"
            )

        # Select compiler according to target platform
        if request.options.target_platform == TargetPlatform.WIN64:
            # Case-insensitive match for dcc32 executable file name (compatible with manually configured names such as DCC32.EXE / Dcc32.exe)
            lower_path = compiler_path.lower()
            idx = lower_path.find('dcc32.exe')
            if idx != -1:
                compiler_path = compiler_path[:idx] + 'dcc64.exe' + compiler_path[idx + len('dcc32.exe'):]

        # Generate arguments
        args = self.args_generator.generate(request.project_path, request.options)

        # Generate full command
        full_command = self.args_generator.format_command(compiler_path, args)

        # Collect warnings
        warnings = []
        if request.options.output_path:
            is_valid, error_msg = self.validator.validate_output_path(request.options.output_path)
            if not is_valid:
                warnings.append(f"Output path warning: {error_msg}")

        return CommandArgs(
            compiler_executable=compiler_path,
            project_file=request.project_path,
            arguments=args,
            full_command=full_command,
            warnings=warnings
        )

    @staticmethod
    def _collect_output_files(
        project_path: str,
        target_platform: str = "win32",
        build_configuration: str = "Debug",
        output_path_override: Optional[str] = None,
    ) -> list[str]:

        """Scan build output directories and collect all generated file paths (exe/dll/bpl/bpi/dcp, etc.)

        Args:
            project_path: .dproj/.dpr/.dpk file path
            target_platform: Target platform (win32/win64, etc.)
            build_configuration: Build configuration (Debug/Release)
            output_path_override: Explicitly specified output path (used first if provided)

        Returns:
            List of all existing output file paths
        """
        proj = Path(project_path)
        project_name = proj.stem
        project_dir = proj.parent

        # Determine candidate output directories
        plat_map = {"win32": "Win32", "win64": "Win64"}
        plat_dir = plat_map.get(target_platform.lower(), "Win32")
        cfg = build_configuration or "Debug"

        dproj_path = proj.with_suffix('.dproj') if proj.suffix.lower() != '.dproj' else proj
        dproj_output = None
        if dproj_path.exists():
            try:
                from ..utils.dproj_parser import DprojParser
                parser = DprojParser(str(dproj_path))
                if parser.parse():
                    dproj_output = parser.get_output_path(config=cfg, platform=plat_dir)
            except Exception as e:
                logger.debug("DProj parsing failed (continuing with candidate directory list): %s", e)

        # Collect all possible output directories (deduplicate, sort by confidence)
        candidate_dirs: list[Path] = []
        if output_path_override:
            candidate_dirs.append(Path(output_path_override))
        if dproj_output:
            candidate_dirs.append(Path(dproj_output))
        candidate_dirs.append(project_dir / plat_dir / cfg)  # Win32/Debug
        candidate_dirs.append(project_dir)                    # Project root directory (MSBuild default output)

        # Output artifact list (StackTrace/callgraph needs .map for symbol resolution; .drc is not needed)
        extensions = ['.exe', '.dll', '.bpl', '.bpi', '.dcp', '.map', '.tds', '.rsm']
        found: list[str] = []

        for output_dir in candidate_dirs:
            if not output_dir.exists():
                continue
            for ext in extensions:
                candidate = output_dir / f"{project_name}{ext}"
                if candidate.exists() and str(candidate.resolve()) not in found:
                    found.append(str(candidate.resolve()))
            # Also glob for .bpl/.bpi/.dcp starting with the project name (platform suffix variants)
            if not any(f.endswith(('.bpl', '.bpi', '.dcp')) for f in found):
                for ext in ('.bpl', '.bpi', '.dcp'):
                    for p in output_dir.glob(f"{project_name}*{ext}"):
                        if p.exists() and str(p.resolve()) not in found:
                            found.append(str(p.resolve()))

        # For .dpk package compilation, bpl may be output to the global Bpl directory
        if proj.suffix.lower() == '.dpk' or dproj_path.suffix.lower() == '.dpk':
            bpl_search_dirs = [Path.home() / "Documents" / "Embarcadero" / "Studio"]
            public_studio_root = get_delphi_public_studio_root()
            if public_studio_root is not None:
                bpl_search_dirs.append(public_studio_root)
            for bpl_base in bpl_search_dirs:
                if bpl_base.exists():
                    for ver_dir in sorted(bpl_base.iterdir(), reverse=True):
                        bpl_dir = ver_dir / "Bpl"
                        if bpl_dir.exists():
                            for ext in ('.bpl', '.bpi', '.dcp'):
                                for p in bpl_dir.glob(f"{project_name}*{ext}"):
                                    if p.exists() and str(p.resolve()) not in found:
                                        found.append(str(p.resolve()))
                            break  # Only check the newest version

        return found

    def _extract_output_file(self, output: str, output_path: Optional[str]) -> Optional[str]:
        """Extract output file path from output"""
        if output_path:
            return output_path
        # Try to parse from dcc32 output line: "Output: C:\path\to\output.exe"
        for line in output.splitlines():
            if 'Output:' in line and '.exe' in line:
                idx = line.index('Output:') + 7
                path = line[idx:].strip().rstrip('.')
                if os.path.exists(path):
                    return path
        return None

    def _save_history(self, project_path: str, status: str, duration: int, error_message: Optional[str]):
        """Save compilation history"""
        entry = CompileHistoryEntry(
            timestamp=datetime.now(),
            project_path=project_path,
            status=status,
            duration=duration,
            error_message=error_message
        )
        self.config_manager.add_history_entry(entry)