"""
Delphi version number and product name mapping utilities

Provides a single place to look up version names, so the mapping is not redefined in
several places. All old and new version mappings are maintained here.
"""

import re
from typing import Optional

# Registry version key → product name (full mapping)
DELPHI_VERSION_NAMES: dict[str, str] = {
    "37.0": "Delphi 13 Florence",
    "23.0": "Delphi 12 Athens",
    "22.0": "Delphi 11 Alexandria",
    "21.0": "Delphi 10.4 Sydney",
    "20.0": "Delphi 10.3 Rio",
    "19.0": "Delphi 10.2 Tokyo",
    "18.0": "Delphi 10.1 Berlin",
    "17.0": "Delphi 10 Seattle",
    "16.0": "Delphi XE8",
    "15.0": "Delphi XE7",
    "14.0": "Delphi XE6",
    "12.0": "Delphi XE5",
    "11.0": "Delphi XE4",
    "10.0": "Delphi XE3",
    "9.0": "Delphi XE2",
    "8.0": "Delphi XE",
    "7.0": "Delphi 2010",
    "6.0": "Delphi 2009",
    "5.0": "Delphi 2007",
    "4.0": "Delphi 2006",
    "3.0": "Delphi 2005",
}

# Product name (lowercase, with the "Delphi " prefix removed) → registry version number
# Lets project configuration/version mappings write readable forms such as "XE4" or "12 Athens"
_VERSION_NAME_ALIASES: dict[str, str] = {}
for _registry_version, _product_name in DELPHI_VERSION_NAMES.items():
    _alias = _product_name.lower()
    if _alias.startswith("delphi "):
        _alias = _alias[len("delphi "):]
    _VERSION_NAME_ALIASES[_alias.strip()] = _registry_version

# .dproj ProjectVersion → registry version number (reverse mapping)
# Most versions are identical in both; only the differing ones are listed here
PROJECT_VERSION_TO_REGISTRY: dict[str, str] = {
    "14.6": "14.0",   # Delphi XE6: .dproj 14.6 → registry 14.0
    "18.2": "18.0",   # Delphi 10.1 Berlin: .dproj 18.2 → registry 18.0
    "19.2": "19.0",   # Delphi 10.2 Tokyo: .dproj 19.2 → registry 19.0
}

# .dproj version prefix (integer part) → product name
# Used by get_compiler_for_project to match a compiler
PROJECT_VERSION_PREFIX_MAP: dict[str, str] = {
    "37": "Delphi 13 Florence",
    "23": "Delphi 12 Athens",
    "22": "Delphi 11 Alexandria",
    "21": "Delphi 10.4 Sydney",
    "20": "Delphi 10.3 Rio",
    "19": "Delphi 10.2 Tokyo",
    "18": "Delphi 10.1 Berlin",
    "17": "Delphi 10 Seattle",
    "16": "Delphi XE8",
    "15": "Delphi XE7",
    "14": "Delphi XE6",
    "12": "Delphi XE5",
    "11": "Delphi XE4",
    "10": "Delphi XE3",
    "9": "Delphi XE2",
    "8": "Delphi XE",
}


def get_version_name(version_key: str) -> str:
    """Get the Delphi product name for a version key"""
    return DELPHI_VERSION_NAMES.get(version_key, f"Delphi {version_key}")


def normalize_registry_version(value: Optional[str]) -> Optional[str]:
    """Normalize a user-supplied Delphi version number to ``major.minor`` form.

    Accepts forms such as ``"11"`` / ``"11.0"`` / ``" 11.0 "`` and always returns ``"11.0"``.
    Returns ``None`` when the value cannot be recognized (non-numeric or out of a reasonable range).

    Args:
        value: user-supplied version number, e.g. ``"11"``, ``"11.0"``

    Returns:
        The normalized version number (e.g. ``"11.0"``), or ``None`` when it cannot be recognized
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    match = re.fullmatch(r"(\d+)(?:\.(\d+))?", text)
    if not match:
        return None
    major = int(match.group(1))
    minor = int(match.group(2) or 0)
    if not 1 <= major <= 99 or not 0 <= minor <= 99:
        return None
    return f"{major}.{minor}"


def normalize_version_key(value: Optional[str]) -> Optional[str]:
    """Normalize a "Delphi version identifier" to a registry version number (``major.minor``).

    Compared with :func:`normalize_registry_version`, this also accepts product-name forms,
    so project configuration/version→MSBuild mappings can write ``"XE4"``, ``"Delphi XE4"``
    or ``"Delphi 12 Athens"`` directly:

    - ``"11"`` / ``"11.0"`` / ``" 11.0 "`` → ``"11.0"``
    - ``"XE4"`` / ``"Delphi XE4"`` → ``"11.0"``
    - ``"14.6"`` / ``"18.2"`` / ``"19.2"`` (.dproj ProjectVersion) → ``"14.0"`` / ``"18.0"`` / ``"19.0"``
    - ``"Delphi 12 Athens"`` → ``"23.0"``

    Plain numbers are still interpreted as registry versions (``"12"`` → ``"12.0"`` = XE5);
    only the known ``.dproj ProjectVersion`` differences (14.6/18.2/19.2) are mapped.
    Non-numeric forms are matched by product name.

    Args:
        value: version number or Delphi product name

    Returns:
        The normalized registry version number, or None when it cannot be recognized
    """
    numeric = normalize_registry_version(value)
    if numeric:
        return PROJECT_VERSION_TO_REGISTRY.get(numeric, numeric)
    if value is None:
        return None

    text = str(value).strip().lower()
    if not text:
        return None

    alias = _VERSION_NAME_ALIASES.get(text)
    if alias:
        return alias
    if text.startswith("delphi "):
        alias = _VERSION_NAME_ALIASES.get(text[len("delphi "):].strip())
        if alias:
            return alias

    # Allow a platform suffix after the product name, e.g. "XE4 Win32", "Delphi 12 Athens Win64"
    for name, registry in _VERSION_NAME_ALIASES.items():
        for suffix in (" win32", " win64", " 32-bit", " 64-bit"):
            if text == name + suffix:
                return registry
    return None


def get_version_name_from_path(delphi_path: str) -> str:
    """Extract the version from an install path (which ends with a version number) and get its name"""
    path = delphi_path.rstrip("\\/")
    match = re.search(r"(\d+\.\d+)$", path)
    if not match:
        return "Delphi Unknown"
    return get_version_name(match.group(1))


def get_project_version_name(version_prefix: str) -> str | None:
    """Get the Delphi product name for a .dproj version prefix"""
    return PROJECT_VERSION_PREFIX_MAP.get(version_prefix)


# ============================================================
# Compiler version in dcc32 --version output → registry version number
# When the registry is unavailable, run the compiler --version and map through this table
# ============================================================
# Example dcc32 --version output:
#   Embarcadero Delphi for Win32 compiler version 35.0
# Compiler version 35.0 → registry version 22.0 (Delphi 11 Alexandria)
DCC_VERSION_TO_REGISTRY: dict[str, str] = {
    "35.0": "22.0",   # Delphi 11 Alexandria
    "36.0": "23.0",   # Delphi 12 Athens
    "37.0": "37.0",   # Delphi 13 Florence
    "34.0": "21.0",   # Delphi 10.4 Sydney
    "33.0": "20.0",   # Delphi 10.3 Rio
    "32.0": "19.0",   # Delphi 10.2 Tokyo
    "31.0": "18.0",   # Delphi 10.1 Berlin
}


def parse_compiler_version_from_output(output: str) -> Optional[str]:
    """
    Extract the compiler version number from dcc32 --version output.

    Args:
        output: stdout of dcc32 --version

    Returns:
        Compiler version number such as "35.0", or None when parsing fails
    """
    match = re.search(r'compiler version (\d+\.\d+)', output)
    return match.group(1) if match else None


def detect_registry_version_from_compiler(compiler_path: str, timeout: int = 10) -> Optional[str]:
    """
    Run the compiler --version and parse its output, mapping it to a registry version number.

    Useful when the registry is unavailable (a manually configured compiler, one found on PATH,
    etc.). The result is cached in CompilerConfig.registry_version, so it need not be called
    repeatedly.

    Args:
        compiler_path: full path to dcc32.exe/dcc64.exe
        timeout: timeout in seconds

    Returns:
        Registry version number such as "22.0", or None when detection fails
    """
    import subprocess
    try:
        result = subprocess.run(
            [compiler_path, '--version'],
            capture_output=True, text=True, timeout=timeout,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        if result.returncode != 0:
            return None

        compiler_ver = parse_compiler_version_from_output(result.stdout)
        if not compiler_ver:
            return None

        # Exact match in the known-version table
        if compiler_ver in DCC_VERSION_TO_REGISTRY:
            return DCC_VERSION_TO_REGISTRY[compiler_ver]

        # Unknown version: try the formula estimate
        # Known pattern: registry_version ≈ compiler_version - 13
        # e.g. 35.0 - 13 = 22.0, 36.0 - 13 = 23.0
        try:
            parts = compiler_ver.split('.')
            major = int(parts[0])
            estimated = major - 13
            if 3 <= estimated <= 40:  # reasonable range
                return f"{estimated}.0"
        except (ValueError, IndexError):
            pass

        return None
    except (subprocess.TimeoutExpired, OSError):
        return None


# Registry version (registry_version) → .dproj ProjectVersion mapping
# Most versions are identical in both; only the differing ones are listed here
REGISTRY_TO_PROJECT_VERSION: dict[str, str] = {
    "14.0": "14.6",   # Delphi XE6: registry 14.0, but the .dproj format marks it as 14.6
    "18.0": "18.2",   # Delphi 10.1 Berlin: registry 18.0, but the .dproj format marks it as 18.2
    "19.0": "19.2",   # Delphi 10.2 Tokyo: registry 19.0, but the .dproj format marks it as 19.2
}


def registry_to_project_version(registry_ver: str) -> str:
    """
    Map a Delphi registry version number to a .dproj ProjectVersion.

    For Delphi 10.2 and newer the ProjectVersion equals the registry version number.
    Delphi 10.1 Berlin is the exception: registry 18.0 → ProjectVersion 18.2.

    Args:
        registry_ver: registry version number, e.g. "22.0"

    Returns:
        The .dproj ProjectVersion value, e.g. "22.0"
    """
    return REGISTRY_TO_PROJECT_VERSION.get(registry_ver, registry_ver)


# .dproj ProjectVersion → registry version number (reverse mapping)
# Defined at the top of the file (normalize_version_key needs it)


def resolve_registry_version(
    compiler_version: Optional[str],
    project_version: Optional[str] = None,
    config_manager: Optional[object] = None,
    override_version: Optional[str] = None,
) -> Optional[str]:
    """
    Resolve the registry version number from compiler_version (or, as a fallback, from the
    .dproj ProjectVersion).

    RTL library search paths and third-party library paths share this policy, so both filter
    the registry by the same Delphi version and avoid a mismatch such as "the default compiler
    is Delphi 12 while the library paths come from Delphi 13".

    Args:
        compiler_version: compiler version name given by the user/configuration
        project_version: .dproj ProjectVersion (optional; fallback when compiler_version is not given)
        config_manager: configuration manager instance (optional; without it only the project_version fallback is available)
        override_version: registry version number set by project-level configuration (e.g. ``"11.0"``),
            used for a single project configuration and not affecting other projects

    Returns:
        Registry version number such as "23.0", or None when it cannot be resolved
    """
    registry_version: Optional[str] = None

    if compiler_version:
        try:
            if config_manager is not None:
                compiler_cfg = config_manager.get_compiler(compiler_version)
                if compiler_cfg is not None:
                    registry_version = compiler_cfg.registry_version
        except Exception:
            registry_version = None

    if not registry_version and override_version:
        registry_version = normalize_version_key(override_version)
    if not registry_version and config_manager is not None:
        # When no compiler is given explicitly, fall back to the "default compiler" — the same
        # choice compile_dpr_direct actually makes through config_manager.get_compiler(None).
        # Returning None here would make the caller get_delphi_library_paths(None) take the
        # library paths of the "newest installed version", while dcc32 actually uses the default
        # compiler; when the default compiler is not the newest version the two disagree, and a
        # Delphi 12 dcc32 ends up finding Delphi 13 .dcu files, so the build fails.
        try:
            default_cfg = config_manager.get_compiler(None)
            if default_cfg is not None:
                registry_version = default_cfg.registry_version
        except Exception:
            registry_version = None

    # Fallback: when compiler_version is not given or cannot be resolved, infer it from the .dproj ProjectVersion
    if not registry_version and project_version:
        registry_version = project_version_to_registry_version(project_version)

    return registry_version


def project_version_to_registry_version(project_ver: str) -> Optional[str]:
    """
    Map a .dproj ProjectVersion to a registry version number (registry_version).

    Used to infer the correct Delphi version from the .dproj file when compiler_version is not
    specified, so that version's library search paths can be obtained.

    For Delphi 10.2 and newer the two are identical.
    Delphi 10.1 Berlin is the exception: .dproj 18.2 → registry 18.0.

    Args:
        project_ver: .dproj ProjectVersion value, e.g. "22.0" or "18.2"

    Returns:
        Registry version number such as "22.0", or None when it cannot be mapped
    """
    # Exact match (handles exceptions such as Berlin)
    if project_ver in PROJECT_VERSION_TO_REGISTRY:
        return PROJECT_VERSION_TO_REGISTRY[project_ver]
    # Most versions are identical; just check that it is known
    if project_ver in DELPHI_VERSION_NAMES:
        return project_ver
    # Try an integer-prefix match (e.g. "19" → "19.0")
    parts = project_ver.split(".")
    if parts and parts[0].isdigit():
        candidate = f"{parts[0]}.0"
        if candidate in DELPHI_VERSION_NAMES:
            return candidate
    return None
