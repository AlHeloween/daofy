"""
Configuration Manager

Copyright (C) Jilin Province ZuoYou Software Development Co., Ltd.
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
Update & Mod By Crystalxp (Dark Night Killer QQ:281309196)

Responsible for reading and writing compiler configuration and compile history
"""

import json
import os
import re
import shutil
import subprocess
import winreg
from pathlib import Path
from typing import Optional, List
from datetime import datetime
from ..constants import REG_KEY_EMBARCADERO_BDS
from ..models.compiler_config import CompilerConfig, ConfigFile
from ..models.compile_history import CompileHistoryEntry, HistoryFile
from ..utils.delphi_versions import (
    PROJECT_VERSION_PREFIX_MAP,
    get_version_name,
    normalize_registry_version,
    normalize_version_key,
    project_version_to_registry_version,
)
from ..utils.logger import get_logger

logger = get_logger(__name__)


class ConfigManager:
    """Configuration manager"""

    def __init__(self, config_path: Optional[str] = None, history_path: Optional[str] = None):
        """
        Initialize configuration manager

        Args:
            config_path: Compiler configuration file path; by default auto-searched from src/config/ or project root config/
                (both candidate locations are supported; chosen automatically based on existence and a notice is output)
            history_path: Compile history file path; defaults to history.json in the same directory as config_path
        """
        if config_path is None:
            # Self-healing path: AGENTS.md documentation and historical deployment location are inconsistent
            # Candidates: (1) src/config/compilers.json  (2) <project root>/config/compilers.json
            # Choose the first existing one; if neither exists, fall back to (1) so that _auto_detect_compilers can write later
            _default_root = Path(__file__).parent.parent  # src/
            _candidates = [
                _default_root / "config" / "compilers.json",           # src/config/  (historically built-in)
                _default_root.parent / "config" / "compilers.json",    # project root config/ (as described in AGENTS.md)
            ]
            config_path = str(_candidates[0])  # Default: src/config/
            for _candidate in _candidates:
                if _candidate.exists():
                    config_path = str(_candidate)
                    if _candidate != _candidates[0]:
                        # Only output a notice when switching to a non-default location (first launch/after migration)
                        logger.info(
                            "compilers.json default path (%s) does not exist; self-healed to: %s",
                            _candidates[0], config_path,
                        )
                    break
            else:
                logger.debug(
                    "compilers.json candidate paths do not exist; using default location: %s (_auto_detect_compilers will create it)",
                    config_path,
                )
        if history_path is None:
            if config_path is None:
                _default_root = Path(__file__).parent.parent
            else:
                _default_root = Path(config_path).parent
            history_path = str(_default_root / "history.json")
        self.config_path = Path(config_path)
        self.history_path = Path(history_path)
        self.config: ConfigFile = self._load_config()
        self.history: HistoryFile = self._load_history()

        for removed_env in ("DAOFY_MSBUILD", "DAOFY_DELPHI_VERSION"):
            if os.environ.get(removed_env, "").strip():
                logger.warning(
                    "Environment variable %s has been removed and is ignored; please use project-level .daofy/project.json instead",
                    removed_env,
                )

        # Auto-detect only when the configuration file does not exist (first launch of a fresh install).
        # Do not auto-overwrite when the user has manually edited compilers.json, to avoid clearing
        # user-specified custom paths (such as Lazarus d:\win\lazarus in a non-default location).
        if not self.config_path.exists():
            logger.info("Configuration file does not exist; starting auto-detection of compilers...")
            self._auto_detect_compilers()

        logger.info(f"Configuration manager initialized")
        logger.debug(f"Configuration file path: {self.config_path}")
        logger.debug(f"History file path: {self.history_path}")

    def _load_config(self) -> ConfigFile:
        """Load compiler configuration"""
        if not self.config_path.exists():
            logger.info("Configuration file does not exist; creating default configuration")
            return ConfigFile()

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for removed_key in ("msbuild_path", "default_registry_version"):
                    if removed_key in data:
                        logger.warning(
                            "compilers.json %s has been removed and is ignored; "
                            "please use project-level .daofy/project.json instead",
                            removed_key,
                        )
                config = ConfigFile.from_dict(data)
                logger.info(f"Configuration loaded successfully, {len(config.compilers)} compiler configurations")
                return config
        except Exception as e:
            logger.error(f"Failed to load configuration: {str(e)}", exc_info=True)
            return ConfigFile()

    def _load_history(self) -> HistoryFile:
        """Load compile history"""
        if not self.history_path.exists():
            logger.info("History file does not exist; creating empty history")
            return HistoryFile()

        try:
            with open(self.history_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                history = HistoryFile.from_dict(data)
                logger.info(f"History loaded successfully, {len(history.entries)} records")
                return history
        except Exception as e:
            logger.error(f"Failed to load history: {str(e)}", exc_info=True)
            return HistoryFile()

    def save_config(self):
        """Save compiler configuration"""
        try:
            # Ensure directory exists
            self.config_path.parent.mkdir(parents=True, exist_ok=True)

            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config.to_dict(), f, indent=2, ensure_ascii=False)

            logger.info(f"Configuration saved successfully: {self.config_path}")
        except Exception as e:
            logger.error(f"Failed to save configuration: {str(e)}")
            raise

    def save_history(self):
        """Save compile history"""
        try:
            # Ensure directory exists
            self.history_path.parent.mkdir(parents=True, exist_ok=True)

            with open(self.history_path, 'w', encoding='utf-8') as f:
                json.dump(self.history.to_dict(), f, indent=2, ensure_ascii=False)

            logger.debug(f"History saved successfully: {self.history_path}")
        except Exception as e:
            logger.error(f"Failed to save history: {str(e)}")
            raise

    def get_compiler(self, name: Optional[str] = None) -> Optional[CompilerConfig]:
        """
        Get compiler configuration

        Args:
            name: Compiler name; if None, return the default compiler

        Returns:
            Compiler configuration; returns None if it does not exist
        """
        if name:
            compiler = self.config.get_compiler(name)
            if compiler:
                logger.debug(f"Getting compiler configuration: {name}")
            else:
                logger.warning(f"Compiler configuration does not exist: {name}")
            return compiler
        else:
            compiler = self.config.get_default_compiler()
            if compiler:
                logger.debug(f"Getting default compiler configuration: {compiler.name}")
            else:
                logger.warning("No default compiler configured")
            return compiler

    PROJECT_VERSION_MAP = PROJECT_VERSION_PREFIX_MAP.copy()

    def _resolve_config_path(self, value: str) -> str:
        """Expand relative paths in compilers.json based on the configuration file's directory."""
        path = Path(str(value).strip()).expanduser()
        if not path.is_absolute():
            path = self.config_path.parent / path
        return str(path)

    def get_msbuild_for_version(self, version: Optional[str]) -> Optional[str]:
        """Find the corresponding MSBuild path by Delphi registry version.

        Used for scenarios where multiple Delphi versions on the same machine each have their own MSBuild, e.g.
        ``{"11.0": "C:\\Windows\\Microsoft.NET\\Framework\\v3.5\\MSBuild.exe"}``.
        The key can be either a registry version number (``"11.0"``), a product name (``"XE4"``),
        or a ``.dproj ProjectVersion`` (``"14.6"`` → registry 14.0).

        Args:
            version: Delphi registry version number (e.g. ``"11.0"``); None means unknown

        Returns:
            The MSBuild path corresponding to that version; returns None if not configured
        """
        if not version:
            return None
        target = normalize_version_key(version)
        if not target:
            return None

        mapping = self.config.msbuild_by_delphi_version or {}
        for key, value in mapping.items():
            if not value:
                continue
            key_text = str(key).strip()
            candidates = {
                normalize_version_key(key_text),
                project_version_to_registry_version(key_text),
            }
            if target in candidates:
                value_text = str(value).strip()
                return self._resolve_config_path(value_text) if value_text else None

        if mapping:
            # A version mapping is explicitly configured but did not match: the user must see this,
            # otherwise it silently falls back to auto-detection, meaning the configuration is ignored.
            logger.warning(
                "No entry for Delphi %s in msbuild_by_delphi_version (configured: %s); "
                "this time it will be handled by auto-detection",
                target,
                ", ".join(str(k) for k in mapping),
            )
        return None

    @staticmethod
    def _matches_product_name(text: Optional[str], product_name: Optional[str]) -> bool:
        """Match product names by word boundary to avoid "Delphi XE" matching "Delphi XE8".

        Allows platform/suffix after the product name (``"Delphi XE4 Win32"``), but requires that the boundary is not
        a letter or digit, preventing prefix mismatches among XE/XE2/…/XE8, Delphi 1/Delphi 12, etc.
        """
        if not text or not product_name:
            return False
        pattern = (
            r"(?<![0-9a-z])"
            + re.escape(product_name.lower())
            + r"(?![0-9a-z])"
        )
        return re.search(pattern, text.lower()) is not None

    def get_compiler_by_registry_version(
        self,
        registry_version: str,
        platform: Optional[str] = None,
    ) -> Optional[CompilerConfig]:
        """Find compiler configuration by registry version number.

        Args:
            registry_version: Registry version number, e.g. ``"11.0"``
            platform: Target platform (win32/win64); if provided, prefer the corresponding platform

        Returns:
            Matching compiler configuration; returns None if not found
        """
        target = normalize_registry_version(registry_version)
        if not target:
            return None
        candidates = [
            c for c in self.config.compilers
            if c.registry_version
            and normalize_registry_version(c.registry_version) == target
        ]
        if not candidates:
            # Manually configured compilers may not have registry_version, so fall back to matching by product name
            # (e.g. "11.0" -> "Delphi XE4"), avoiding a project-specified version becoming invalid due to a missing field.
            # Must match by word boundary, otherwise "Delphi XE" (8.0) would incorrectly match
            # "Delphi XE8" (16.0), and "Delphi 12" would incorrectly match "Delphi 12 Athens".
            version_name = get_version_name(target).lower()
            candidates = [
                c for c in self.config.compilers
                if self._matches_product_name(c.version, version_name)
                or self._matches_product_name(c.name, version_name)
            ]
            if not candidates:
                modern_prefix = re.match(r"^(delphi \d+(?:\.\d+)?)", version_name)
                if modern_prefix:
                    prefix_name = modern_prefix.group(1)
                    candidates = [
                        c for c in self.config.compilers
                        if self._matches_product_name(c.version, prefix_name)
                        or self._matches_product_name(c.name, prefix_name)
                    ]
        if not candidates:
            return None
        if platform:
            return self._select_by_platform(candidates, platform)
        return candidates[0]

    @staticmethod
    def _select_by_platform(candidates: List[CompilerConfig], platform: str) -> CompilerConfig:
        """Select from candidate compilers by platform preference."""
        if platform == "win64":
            for c in candidates:
                if "win64" in c.name.lower():
                    return c
            return candidates[0]
        for c in candidates:
            if "win32" in c.name.lower():
                return c
        return candidates[0]

    def get_effective_compiler(
        self,
        name: Optional[str] = None,
        platform: str = "win32",
    ) -> Optional[CompilerConfig]:
        """Get the compiler actually used for compilation.

        Priority: explicit compiler name > default compiler.

        Args:
            name: Explicitly specified compiler name; None means not specified
            platform: Target platform (win32/win64)

        Returns:
            Compiler configuration; returns None if it cannot be determined
        """
        if name:
            return self.get_compiler(name)
        return self.get_compiler(None)

    def get_compiler_for_project(self, project_version: str, platform: str = "win32") -> Optional[CompilerConfig]:
        """
        Automatically match the best compiler based on project version

        Args:
            project_version: Project version number (e.g. "19.2", "21.0", etc.)
            platform: Target platform (win32/win64), default win32

        Returns:
            Best-matching compiler configuration; if not found, return the default compiler

        Matching strategy (in priority order):
          1. Exact match: registry_version exactly matches the project version prefix
          2. Exact match (by product name): version field contains the target Delphi name (e.g. "Delphi 11")
          3. Fallback: compiler with version >= target, choose the closest one, ensuring higher versions can compile lower-version projects

        Note: When a specific version must be strictly specified, use the project-level
        ``delphi_version`` in ``.daofy/project.json``.
        """
        if not project_version:
            logger.warning("Project version is empty; using newest compiler")
            return self.get_newest_compiler() or self.get_compiler()

        # Extract version prefix from project version (e.g. "19.2" → "19")
        version_prefix = project_version.split(".")[0]
        if not version_prefix or not version_prefix.isdigit():
            logger.warning(f"Unrecognized project version: {project_version}; using newest compiler")
            return self.get_newest_compiler() or self.get_compiler()

        # Convert version prefix to registry_version format (e.g. "19" → "19.0")
        target_registry_version = f"{version_prefix}.0"

        # Target Delphi product name (e.g. "Delphi 11 Alexandria"), used for matching by name/version
        delphi_name = self._map_project_version_to_delphi(project_version)
        # Numeric part of product name (e.g. "Delphi 11") used for fuzzy matching in version field
        delphi_num_name = None
        if version_prefix.isdigit():
            # Get the "Delphi N" numeric prefix from the separated version name
            from ..utils.delphi_versions import DELPHI_VERSION_NAMES, PROJECT_VERSION_PREFIX_MAP
            # registry_version → product name
            product_name = DELPHI_VERSION_NAMES.get(target_registry_version)
            if product_name:
                # Extract e.g. "Delphi 12" / "Delphi 10.4"
                m = re.match(r"^(Delphi \d+(?:\.\d+)?)", product_name)
                if m:
                    delphi_num_name = m.group(1).lower()

        compilers = self.config.compilers
        if not compilers:
            logger.warning("No compilers configured")
            return None

        # ── 1. Exact match registry_version ──
        exact_matches = [c for c in compilers if c.registry_version == target_registry_version]
        if exact_matches:
            pick = self._select_by_platform(exact_matches, platform)
            logger.info(f"Exact-matched compiler: {pick.name} (registry_version={pick.registry_version})")
            return pick

        # ── 2. Exact match product name (version or name field) ──
        name_matches = []
        if delphi_name:
            name_matches = [
                c for c in compilers
                if self._matches_product_name(c.version, delphi_name)
                or self._matches_product_name(c.name, delphi_name)
            ]
        if name_matches:
            pick = self._select_by_platform(name_matches, platform)
            logger.info(f"Product name exact-matched compiler: {pick.name}")
            return pick

        # ── 3. Numeric prefix fuzzy match (e.g. when delphi_name is "Delphi 11...", match "Delphi 11") ──
        num_matches = []
        if delphi_num_name:
            num_matches = [
                c for c in compilers
                if self._matches_product_name(c.version, delphi_num_name)
                or self._matches_product_name(c.name, delphi_num_name)
            ]
        if num_matches:
            pick = self._select_by_platform(num_matches, platform)
            logger.info(f"Numeric prefix matched compiler: {pick.name}")
            return pick

        # ── 4. Fallback: version >= target, choose the closest ──
        # Parse target version number for comparison
        try:
            target_ver = float(target_registry_version)
        except ValueError:
            target_ver = 0

        # Derive numeric version for each compiler (registry_version first, then from version/name)
        compatible_compilers = []
        for c in compilers:
            ver = self._compiler_numeric_version(c, target_ver)
            if ver is not None and ver >= target_ver:
                compatible_compilers.append((ver, c))

        if compatible_compilers:
            # Sort by version ascending, choose the closest to target
            compatible_compilers.sort(key=lambda x: x[0])
            best = self._select_by_platform([c for _, c in compatible_compilers], platform)
            logger.warning(
                "No exact compiler found for Delphi %s; falling back to higher version %s; "
                "configure the project delphi_version if strict matching is required",
                target_registry_version,
                best.name,
            )
            return best

        logger.warning(f"No compiler found matching version {target_registry_version}; using newest compiler")
        return self.get_newest_compiler() or self.get_compiler()

    def _compiler_numeric_version(self, compiler, target_ver: float) -> Optional[float]:
        """
        Extract the compiler's numeric version number for comparison.

        Priority:
          1. registry_version (e.g. "22.0")
          2. Number in the version field (e.g. "Delphi 11 Alexandria" → 22.0)
          3. Number in the name field

        Args:
            compiler: CompilerConfig
            target_ver: Target version number (used for numeric prefix derivation)

        Returns:
            Numeric version number (registry_version format); returns None if it cannot be derived
        """
        import re as _re

        # 1. registry_version
        if compiler.registry_version:
            try:
                return float(compiler.registry_version)
            except (ValueError, TypeError):
                pass

        # 2/3. Parse "Delphi N" from version or name → registry_version
        #     Delphi N → registry.0, e.g. "Delphi 11" → 22.0
        from ..utils.delphi_versions import PROJECT_VERSION_PREFIX_MAP
        texts = [compiler.version or "", compiler.name or ""]
        for text in texts:
            m = _re.search(r"Delphi\s+(\d+)(?:\s|$)", text, _re.IGNORECASE)
            if m:
                prefix = m.group(1)
                # PROJECT_VERSION_PREFIX_MAP keys are .dproj version prefixes (same as registry version)
                # but the product number "Delphi 11" → its registry version prefix is different
                # needs reverse mapping: product number → registry_version
                reg_ver = self._map_delphi_num_to_registry(prefix)
                if reg_ver:
                    try:
                        return float(reg_ver)
                    except ValueError:
                        pass

        return None

    @staticmethod
    def _map_delphi_num_to_registry(delphi_num: str) -> Optional[str]:
        """
        Map the "Delphi N" product number to registry_version.

        For example: "11" → "22.0", "12" → "23.0", "13" → "37.0"

        Args:
            delphi_num: Delphi product number (e.g. "11", "12")

        Returns:
            registry_version (e.g. "22.0"); returns None if mapping fails
        """
        from ..utils.delphi_versions import PROJECT_VERSION_PREFIX_MAP
        # Product number → registry version (registry_version)
        # Mapping table: based on version history, registry version number corresponding to product number N
        num_to_registry = {
            "13": "37.0",   # Delphi 13 Florence
            "12": "23.0",   # Delphi 12 Athens
            "11": "22.0",   # Delphi 11 Alexandria
            "10": "21.0",   # Delphi 10.4 Sydney (latest in the 10 series)
            "10.4": "21.0",
            "10.3": "20.0",
            "10.2": "19.0",
            "10.1": "18.0",
        }
        return num_to_registry.get(delphi_num)

    def _map_project_version_to_delphi(self, project_version: str) -> Optional[str]:
        """
        Map project version number to Delphi version name

        Args:
            project_version: Project version number

        Returns:
            Delphi version name
        """
        version_prefix = project_version.split(".")[0]
        return self.PROJECT_VERSION_MAP.get(version_prefix)

    def add_compiler(self, compiler: CompilerConfig):
        """
        Add compiler configuration

        Args:
            compiler: Compiler configuration
        """
        # If there is no registry_version, try to detect it from the compiler --version output
        if not compiler.registry_version and compiler.path:
            try:
                from ..utils.delphi_versions import detect_registry_version_from_compiler
                detected = detect_registry_version_from_compiler(compiler.path)
                if detected:
                    compiler.registry_version = detected
                    logger.info(f"Detected version from compiler output: {compiler.name} → {detected}")
            except Exception:
                logger.debug("Failed to detect version from compiler output: %s", compiler.path, exc_info=True)

        self.config.add_compiler(compiler)
        self.save_config()
        logger.info(f"Added compiler configuration: {compiler.name}")

    def update_compiler(self, name: str, compiler: CompilerConfig):
        """
        Update compiler configuration

        Args:
            name: Original compiler name
            compiler: New compiler configuration
        """
        # Remove old configuration
        self.config.remove_compiler(name)
        # Add new configuration
        self.config.add_compiler(compiler)
        self.save_config()
        logger.info(f"Updated compiler configuration: {name} -> {compiler.name}")

    def remove_compiler(self, name: str) -> bool:
        """
        Remove compiler configuration

        Args:
            name: Compiler name

        Returns:
            Whether removal succeeded
        """
        result = self.config.remove_compiler(name)
        if result:
            self.save_config()
            logger.info(f"Removed compiler configuration: {name}")
        else:
            logger.warning(f"Failed to remove compiler configuration; does not exist: {name}")
        return result

    def set_default_compiler(self, name: str) -> bool:
        """
        Set default compiler

        Args:
            name: Compiler name

        Returns:
            Whether setting succeeded
        """
        result = self.config.set_default_compiler(name)
        if result:
            self.save_config()
            logger.info(f"Set default compiler: {name}")
        else:
            logger.warning(f"Failed to set default compiler; does not exist: {name}")
        return result

    def get_newest_compiler(self) -> Optional[CompilerConfig]:
        """
        Get the newest installed compiler (the one with the largest registry_version numeric value).

        When the user does not specify a compiler version, use the newest version by default rather than the "default compiler".
        """
        compilers = self.config.compilers
        if not compilers:
            return None

        def sort_key(c: CompilerConfig) -> tuple:
            if c.registry_version:
                try:
                    parts = c.registry_version.split('.')
                    return (int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
                except (ValueError, IndexError):
                    return (0, 0)
            return (0, 0)

        return max(compilers, key=sort_key)

    def get_all_compilers(self) -> List[CompilerConfig]:
        """Get all compiler configurations"""
        return self.config.compilers

    def get_show_timing(self) -> bool:
        """Whether tool returns include a timing field"""
        return self.config.show_timing

    def add_history_entry(self, entry: CompileHistoryEntry):
        """
        Add compile history entry

        Args:
            entry: Compile history entry
        """
        self.history.add_entry(entry)
        self.save_history()
        logger.debug(f"Added compile history entry: {entry.project_path}")

    def get_history(self, limit: int = 10) -> List[CompileHistoryEntry]:
        """
        Get compile history records

        Args:
            limit: Maximum number of records

        Returns:
            List of compile history records
        """
        return self.history.get_recent_entries(limit)

    def clear_history(self):
        """Clear compile history"""
        self.history.clear()
        self.save_history()
        logger.info("Cleared compile history")

    def _auto_detect_compilers(self):
        # ruff: noqa: D205
        """Automatically detect Delphi and Lazarus compilers (merge-style, does not overwrite existing configuration).

        Unlike the old version that cleared and rebuilt, this version:
        - Keeps configured compilers whose paths still exist (including user-specified custom paths,
          such as Lazarus ``d:\\win\\lazarus\\bin\\lazbuild.exe`` in a non-default install location).
        - Only discards old configurations whose paths are no longer valid (pointing to files that no longer exist on disk).
        - Appends newly detected compilers that are not yet configured (deduplicated by normalized path).
        - Keeps the default compiler unchanged if the existing default is still valid; otherwise falls back to the newest/first.

        This avoids the regression where "auto-detection wipes out the user's hand-written paths entirely".
        """
        # Snapshot existing compilers: keep those whose paths are still valid, clean up invalid entries
        existing_valid: List[CompilerConfig] = []
        for compiler in list(self.config.compilers):
            if compiler.path and os.path.exists(compiler.path):
                existing_valid.append(compiler)
            else:
                logger.info(
                    "Discarding compiler configuration with invalid path: %s (%s)",
                    compiler.name, compiler.path,
                )
        self.config.compilers = existing_valid

        # Record the existing default compiler name (to keep it as default after detection)
        existing_default = self.config.default_compiler
        if existing_default and not self.config.get_compiler(existing_default):
            existing_default = None

        # Detect Delphi installation paths via registry
        delphi_installations = self._detect_delphi_from_registry()

        for version, install_path in delphi_installations.items():
            logger.info(f"Detected Delphi {version}: {install_path}")
            compilers = self._detect_compilers_from_path(install_path, version)
            self._merge_detected(compilers)

        # Detect Lazarus/FPC installation
        lazarus_compilers = self._detect_lazarus()
        self._merge_detected(lazarus_compilers)

        if self.config.compilers:
            # Default compiler: keep existing valid default; otherwise fall back to newest/first
            if existing_default:
                self.config.set_default_compiler(existing_default)
            else:
                default = self.get_newest_compiler() or self.config.compilers[0]
                self.config.set_default_compiler(default.name)
                logger.info(f"Set default compiler: {default.name}")

            # Save configuration
            self.save_config()
            logger.info(
                "Auto-detection complete, %d compilers in total (%d existing kept, %d newly added)",
                len(self.config.compilers),
                len(existing_valid),
                len(self.config.compilers) - len(existing_valid),
            )
        else:
            logger.warning("No compilers detected; please configure manually")

    def _merge_detected(self, detected: List[CompilerConfig]) -> None:
        """Merge newly detected compilers into configuration, deduplicating by normalized path."""
        existing_paths = {
            self._normalize_compiler_path(c.path).casefold()
            for c in self.config.compilers if c.path
        }
        for compiler in detected:
            if not compiler.path:
                continue
            key = self._normalize_compiler_path(compiler.path).casefold()
            if key in existing_paths:
                logger.debug("Skipping already configured compiler: %s", compiler.path)
                continue
            self.config.add_compiler(compiler)
            existing_paths.add(key)
            logger.info(f"Auto-configured compiler: {compiler.name}")

    @staticmethod
    def _normalize_compiler_path(path: str) -> str:
        """Normalize compiler path for deduplication comparison."""
        try:
            return str(Path(path).resolve())
        except Exception:
            return os.path.normcase(os.path.normpath(path))

    def _detect_delphi_from_registry(self) -> dict:
        """
        Detect Delphi installation paths from the registry

        Scans both HKCU (user-level) and HKLM (system-level); HKCU has higher priority
        (a user's RAD Studio settings usually override machine-level configuration).

        Returns:
            Dictionary with version number as key and installation path as value
        """
        installations: Dict[str, str] = {}

        # Scan order: HKCU first (user-level priority), HKLM second (system-level fallback)
        # Combined with the "version not in installations" skip logic below,
        # for the same version number the HKCU path wins and HKLM is skipped.
        registry_roots = [
            (winreg.HKEY_CURRENT_USER, REG_KEY_EMBARCADERO_BDS, "HKCU"),
            (winreg.HKEY_LOCAL_MACHINE, REG_KEY_EMBARCADERO_BDS, "HKLM"),
        ]

        for hive, subkey, hive_name in registry_roots:
            try:
                key = winreg.OpenKey(
                    hive,
                    subkey,
                    0,
                    winreg.KEY_READ | winreg.KEY_WOW64_32KEY,
                )
            except FileNotFoundError:
                logger.debug(f"Registry {hive_name}\\{subkey} does not exist; skipping")
                continue
            except Exception as e:
                logger.warning(f"Failed to open registry {hive_name}\\{subkey}: {e}")
                continue

            try:
                # Enumerate all subkeys (version numbers)
                index = 0
                while True:
                    try:
                        version = winreg.EnumKey(key, index)
                        index += 1
                    except OSError:
                        # Enumeration finished
                        break

                    try:
                        version_key = winreg.OpenKey(key, version)
                    except Exception as e:
                        logger.debug(f"Failed to open {hive_name}\\{subkey}\\{version}: {e}")
                        continue

                    try:
                        # Read RootDir value
                        try:
                            root_dir, _ = winreg.QueryValueEx(version_key, "RootDir")
                        except FileNotFoundError:
                            logger.debug(f"Delphi {version} has no RootDir value")
                            continue

                        if root_dir and os.path.exists(root_dir):
                            if version not in installations:
                                installations[version] = root_dir
                                logger.debug(f"Detected Delphi {version} from {hive_name}: {root_dir}")
                            else:
                                logger.debug(
                                    f"Delphi {version} is already registered with HKCU priority; skipping {hive_name} path: {root_dir}"
                                )

                    finally:
                        try:
                            winreg.CloseKey(version_key)
                        except Exception:
                            pass
            finally:
                try:
                    winreg.CloseKey(key)
                except Exception:
                    pass

        if not installations:
            logger.debug("No Embarcadero BDS installation found in HKLM/HKCU")

        return installations

    def _detect_compilers_from_path(self, delphi_path: str, registry_version: str = None) -> List[CompilerConfig]:
        """
        Detect compilers from Delphi installation path

        Args:
            delphi_path: Delphi installation path
            registry_version: Version number obtained from the registry (use it first if available)

        Returns:
            List of detected compiler configurations
        """
        compilers = []
        bin_path = os.path.join(delphi_path, "bin")

        if not os.path.exists(bin_path):
            logger.warning(f"bin directory does not exist: {bin_path}")
            return compilers

        # Detect compiler version name and registry version number
        effective_registry_version = registry_version
        if not effective_registry_version:
            from ..utils.delphi_versions import detect_registry_version_from_compiler
            # First try --version detection via any dcc*.exe under bin
            if os.path.exists(bin_path):
                for fname in os.listdir(bin_path):
                    if fname.lower().startswith('dcc') and fname.lower().endswith('.exe'):
                        detected = detect_registry_version_from_compiler(os.path.join(bin_path, fname))
                        if detected:
                            effective_registry_version = detected
                            logger.info(f"Detected version from compiler output: {effective_registry_version}")
                        break

        if effective_registry_version:
            from src.utils.delphi_versions import get_version_name
            version_name = get_version_name(effective_registry_version)
        else:
            version_name = self._get_delphi_version_name(delphi_path)
        # Note: this mapping should stay consistent with compiler_service._get_platform_compiler_name
        # both places must be updated synchronously when adding a new platform
        filename_to_platform = {
            "dcc32": "Win32",
            "dcc64": "Win64",
            "dccaarm": "Android32",
            "dccaarm64": "Android64",
            "dccaac64": "Android64",     # Delphi 12+ 新增
            "dcclinux64": "Linux64",
            "dccosx64": "OSX64",
            "dccosxarm64": "OSXARM64",
            "dcciosarm64": "iOSARM64",
            "dcciossimarm64": "iOSSimARM64",
            "dccarm": "ARM32",
            "dccarm64": "ARM64",
            "dcclinux": "Linux64",
        }

        # Scan all dcc*.exe in the bin directory and automatically identify the platform
        if os.path.exists(bin_path):
            for filename in os.listdir(bin_path):
                lower_filename = filename.lower()
                if lower_filename.startswith("dcc") and lower_filename.endswith(".exe"):
                    base_name = lower_filename[:-4]  # Remove .exe
                    platform_name = filename_to_platform.get(base_name)
                    if not platform_name:
                        platform_name = base_name.replace("dcc", "").upper()

                    full_path = os.path.join(bin_path, filename)
                    compiler = CompilerConfig(
                        name=f"{version_name} {platform_name}",
                        path=full_path,
                        is_default=False,
                        version=version_name,
                        registry_version=effective_registry_version,
                    )
                    compilers.append(compiler)
                    logger.debug(f"Detected {platform_name} compiler: {full_path}")

        return compilers

    def _get_delphi_version_name(self, delphi_path: str) -> str:
        """
        Get Delphi version name

        Args:
            delphi_path: Delphi installation path

        Returns:
            Delphi version name
        """
        from src.utils.delphi_versions import get_version_name_from_path
        return get_version_name_from_path(delphi_path)

    def _detect_lazarus(self) -> List[CompilerConfig]:
        """
        Detect Lazarus/FPC compiler installation

        Delegates unified lookup to src.plugins.lazarus.detect.find_lazbuild(),
        then supplements version number and FPC path detection.
        """
        from src.plugins.lazarus.detect import find_lazbuild

        compilers: List[CompilerConfig] = []
        candidates = find_lazbuild()

        if not candidates:
            logger.debug("No Lazarus/FPC installation detected")
            return compilers

        for lazbuild_path in candidates:
            lazarus_dir = lazbuild_path.parent
            version = self._get_lazarus_version(str(lazbuild_path))
            compiler_name = f"Lazarus FPC {version}" if version else "Lazarus FPC"

            fpc_path = self._find_fpc_in_lazarus(lazarus_dir)

            compilers.append(CompilerConfig(
                name=compiler_name,
                path=str(lazbuild_path),
                is_default=False,
                version=version,
                compiler_type="lazarus",
            ))
            if fpc_path:
                compilers.append(CompilerConfig(
                    name=f"FPC {version}" if version else "FPC",
                    path=str(fpc_path),
                    is_default=False,
                    version=version,
                    compiler_type="lazarus",
                ))
            logger.debug(f"Detected Lazarus: {lazbuild_path}, version={version}")

        return compilers

    def _get_lazarus_version(self, lazbuild_path: str) -> str:
        """Get Lazarus version via lazbuild --version"""
        import subprocess
        try:
            result = subprocess.run(
                [lazbuild_path, "--version"],
                capture_output=True, text=True, timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            for line in result.stdout.splitlines():
                line = line.strip()
                # Output looks like "Lazarus 4.8"
                if line.lower().startswith("lazarus"):
                    parts = line.split()
                    if len(parts) >= 2:
                        return parts[1]
        except Exception as e:
            logger.debug(f"Failed to get Lazarus version: {e}")
        return ""

    def _find_fpc_in_lazarus(self, lazarus_dir: Path) -> Optional[str]:
        """Find fpc.exe in the Lazarus installation directory"""
        fpc_base = lazarus_dir / "fpc"
        if not fpc_base.exists():
            return None
        # Directory structure: fpc/<version>/bin/x86_64-win64/fpc.exe
        for ver_dir in sorted(fpc_base.iterdir(), reverse=True):
            if not ver_dir.is_dir():
                continue
            for arch_dir in (ver_dir / "bin").glob("*"):
                fpc_exe = arch_dir / "fpc.exe"
                if fpc_exe.exists():
                    return str(fpc_exe)
        return None