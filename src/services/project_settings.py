"""Project-level compilation configuration.

Place ``.daofy/project.json`` or ``daofy.project.json`` in the project directory
(or any parent directory) to specify the Delphi version and MSBuild for
**a single project** without affecting other projects on the same machine:

.. code-block:: json

    {
      "delphi_version": "11.0",
      "msbuild_path": "C:\\\\Windows\\\\Microsoft.NET\\\\Framework\\\\v3.5\\\\MSBuild.exe",
      "compiler_version": "Delphi XE4 Win32"
    }

``delphi_version`` also accepts product names (``"XE4"``, ``"Delphi 12 Athens"``);
``msbuild_path`` supports relative paths (resolved relative to the directory
containing the configuration file).

Lookup order: ``<project directory>/.daofy/project.json`` → ``<project directory>/daofy.project.json``
→ search parent directories upward level by level (up to 8 levels). The nearest matching file takes effect.

Priority: explicit tool-call arguments > project configuration > ``msbuild_by_delphi_version`` version mapping
> automatic detection.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional, Union

from ..utils.delphi_versions import normalize_version_key
from ..utils.logger import get_logger

logger = get_logger(__name__)

PROJECT_CONFIG_DIR = ".daofy"
PROJECT_CONFIG_NAME = "project.json"
PROJECT_CONFIG_ALT_NAME = "daofy.project.json"
MAX_PARENT_LOOKUP = 8


@dataclass(frozen=True)
class ProjectSettings:
    """Compilation configuration for a single project.

    Attributes:
        delphi_version: Delphi registry version number (normalized, e.g. ``"11.0"``);
            input also accepts product names (``"XE4"``)
        msbuild_path: MSBuild.exe path used by this project (relative paths are expanded relative to the configuration directory)
        compiler_version: Compiler name used by this project (the name in ``compilers.json``),
            or a version number/product name
        source: Configuration source file path (used for logging/error location)
        error: Error message when the configuration content is invalid (e.g. unrecognized delphi_version)
    """

    delphi_version: Optional[str] = None
    msbuild_path: Optional[str] = None
    compiler_version: Optional[str] = None
    source: Optional[str] = None
    error: Optional[str] = None

    @property
    def is_empty(self) -> bool:
        """Whether no valid item is configured."""
        if self.error:
            return False
        return not (self.delphi_version or self.msbuild_path or self.compiler_version)


def _iter_candidates(directory: Path) -> Iterator[Path]:
    yield directory / PROJECT_CONFIG_DIR / PROJECT_CONFIG_NAME
    yield directory / PROJECT_CONFIG_ALT_NAME


def find_project_config(project_path: Union[str, Path]) -> Optional[Path]:
    """Search upward from the project path for a project-level configuration file.

    Args:
        project_path: ``.dproj`` / ``.dpr`` / ``.dpk`` path, or project directory

    Returns:
        Path of the matched configuration file, or None if not found
    """
    try:
        start = Path(project_path)
    except TypeError:
        return None

    # A directory (even if its name contains a dot, such as MyApp.v2) is used directly as the starting point;
    # a file or non-existent path starts from its parent directory.
    try:
        if start.is_dir() or (not start.exists() and not start.suffix):
            directory = start
        else:
            directory = start.parent
    except OSError:
        return None
    if not directory.exists():
        return None

    try:
        directory = directory.resolve()
    except OSError:
        return None

    for _ in range(MAX_PARENT_LOOKUP):
        for candidate in _iter_candidates(directory):
            if candidate.is_file():
                return candidate
        parent = directory.parent
        if parent == directory:
            break
        directory = parent
    return None


def _read_text(path: Path) -> tuple[Optional[dict], Optional[str]]:
    """Read and parse the project configuration, returning ``(data, error)``."""
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        logger.error("Failed to read project configuration %s: %s", path, exc)
        return None, f"Failed to read project configuration {path}: {exc}"

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("Project configuration is not valid JSON: %s (%s)", path, exc)
        return None, f"Project configuration is not valid JSON {path}: {exc}"

    if not isinstance(data, dict):
        logger.error("Project configuration should be a JSON object: %s", path)
        return None, f"Project configuration should be a JSON object: {path}"
    return data, None


def load_project_settings(
    project_path: Union[str, Path],
) -> Optional[ProjectSettings]:
    """Load the project-level configuration for a project.

    Args:
        project_path: ``.dproj`` / ``.dpr`` / ``.dpk`` path, or project directory

    Returns:
        Project configuration; returns None when there is no configuration file or the configuration is empty. When the configuration file exists but cannot be parsed,
        returns a configuration with ``error``; callers should fail directly instead of silently falling back.
    """
    config_path = find_project_config(project_path)
    if config_path is None:
        return None

    data, read_error = _read_text(config_path)
    if data is None:
        return ProjectSettings(
            source=str(config_path),
            error=read_error or f"Unable to read project configuration {config_path}",
        )

    raw_version = data.get("delphi_version")
    delphi_version = normalize_version_key(raw_version)
    error = None
    if raw_version not in (None, "") and delphi_version is None:
        error = (
            f"Project configuration {config_path} has unrecognized delphi_version={raw_version!r}; "
            "please write it as a registry version number (e.g. 11.0) or product name (e.g. XE4)"
        )
        logger.error(error)

    raw_msbuild = data.get("msbuild_path")
    msbuild_path = str(raw_msbuild).strip() if raw_msbuild else None
    if msbuild_path:
        candidate = Path(msbuild_path).expanduser()
        if not candidate.is_absolute():
            # Relative paths are resolved relative to the directory containing the configuration file, not the current working directory
            candidate = config_path.parent / candidate
        msbuild_path = str(candidate)

    raw_compiler = data.get("compiler_version")
    compiler_version = str(raw_compiler).strip() if raw_compiler else None

    settings = ProjectSettings(
        delphi_version=delphi_version,
        msbuild_path=msbuild_path or None,
        compiler_version=compiler_version or None,
        source=str(config_path),
        error=error,
    )
    if settings.is_empty:
        return None

    logger.info(
        "Loaded project configuration %s: delphi_version=%s, msbuild_path=%s, compiler_version=%s",
        config_path,
        settings.delphi_version or "-",
        settings.msbuild_path or "-",
        settings.compiler_version or "-",
    )
    return settings
