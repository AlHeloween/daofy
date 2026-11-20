"""
Lazarus/FPC path detection — single entry point, shared by all modules.

Search order:
  1. PATH environment variable
  2. Common installation directories
  3. Start menu shortcuts (resolve .lnk targets)
  4. Windows registry (Uninstall information)
"""

import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

from ...utils.logger import get_logger

logger = get_logger(__name__)


# ── Common installation directories (shared by all detection logic) ──

_LAZARUS_COMMON_DIRS: List[Path] = [
    Path("C:/lazarus"),
    Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Lazarus",
    Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Lazarus",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Lazarus",
]


# ── Start menu paths (Windows-specific) ──

_START_MENU_DIRS: List[Path] = [
    Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Lazarus",
    Path(os.environ.get("ProgramData", "C:/ProgramData")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Lazarus",
]


def _resolve_lnk_target(lnk_path: Path) -> Optional[str]:
    """Resolve the target path of a .lnk shortcut via PowerShell."""
    try:
        cmd = (
            f'$ws = New-Object -ComObject WScript.Shell; '
            f'$sc = $ws.CreateShortcut("{lnk_path}"); '
            f'Write-Output $sc.TargetPath'
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            target = result.stdout.strip()
            if target and Path(target).exists():
                return target
    except Exception as e:
        logger.debug(f"Failed to resolve .lnk: {lnk_path}: {e}")
    return None


def _resolve_start_menu_lazbuild() -> Optional[Path]:
    """Find the installation path from Lazarus start menu shortcuts."""
    for menu_dir in _START_MENU_DIRS:
        if not menu_dir.is_dir():
            continue
        for lnk in menu_dir.glob("*.lnk"):
            if "lazarus" in lnk.stem.lower() and "uninstall" not in lnk.stem.lower():
                target = _resolve_lnk_target(lnk)
                if target:
                    lazbuild = Path(target).parent / "lazbuild.exe"
                    if lazbuild.exists():
                        logger.info(f"Found lazbuild via Start menu: {lazbuild}")
                        return lazbuild
    return None


def _resolve_registry_lazbuild() -> Optional[Path]:
    """Find the Lazarus installation path from Windows registry Uninstall information."""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        )
        try:
            i = 0
            while True:
                subkey_name = winreg.EnumKey(key, i)
                i += 1
                try:
                    sk = winreg.OpenKey(key, subkey_name)
                    try:
                        name, _ = winreg.QueryValueEx(sk, "DisplayName")
                        if name and "lazarus" in name.lower():
                            install_loc, _ = winreg.QueryValueEx(sk, "InstallLocation")
                            if install_loc:
                                lazbuild = Path(install_loc) / "lazbuild.exe"
                                if lazbuild.exists():
                                    logger.info(f"Found lazbuild via registry: {lazbuild}")
                                    return lazbuild
                    except FileNotFoundError:
                        pass
                    finally:
                        winreg.CloseKey(sk)
                except FileNotFoundError:
                    continue
        except OSError:
            pass
        finally:
            winreg.CloseKey(key)
    except Exception as e:
        logger.debug(f"Registry detection failed: {e}")
    return None


# ── Public API ──


def find_lazbuild() -> List[Path]:
    """Return a list of all found lazbuild.exe paths (deduplicated).
    
    Search order: PATH → common directories → Start menu → registry
    """
    seen: set[str] = set()
    candidates: List[Path] = []

    def _add(p: Path) -> None:
        resolved = str(p.resolve())
        if resolved not in seen:
            seen.add(resolved)
            candidates.append(p)

    # 1. PATH
    path_result = shutil.which("lazbuild")
    if path_result:
        _add(Path(path_result))

    # 2. Common installation directories
    for d in _LAZARUS_COMMON_DIRS:
        lb = d / "lazbuild.exe"
        if lb.exists():
            _add(lb)

    # 3. Start menu
    sm = _resolve_start_menu_lazbuild()
    if sm:
        _add(sm)

    # 4. Registry
    reg = _resolve_registry_lazbuild()
    if reg:
        _add(reg)

    return candidates


def find_lazarus_root() -> Optional[Path]:
    """Return the Lazarus installation root directory (the parent of the directory containing lazbuild.exe)."""
    lazbuild_paths = find_lazbuild()
    if lazbuild_paths:
        return lazbuild_paths[0].parent
    return None


def is_lazarus_available() -> bool:
    """Quickly check whether Lazarus is installed (without resolving .lnk/registry)."""
    # PATH
    if shutil.which("lazbuild"):
        return True
    # Common directories (only check whether the exe exists, without resolving shortcuts)
    for d in _LAZARUS_COMMON_DIRS:
        if (d / "lazbuild.exe").exists():
            return True
    # Start menu (shortcut existence is enough, without resolving the target)
    for menu_dir in _START_MENU_DIRS:
        if menu_dir.is_dir() and any(
            "lazarus" in lnk.stem.lower() and "uninstall" not in lnk.stem.lower()
            for lnk in menu_dir.glob("*.lnk")
        ):
            return True
    # Registry
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        )
        try:
            i = 0
            while True:
                subkey_name = winreg.EnumKey(key, i)
                i += 1
                try:
                    sk = winreg.OpenKey(key, subkey_name)
                    try:
                        name, _ = winreg.QueryValueEx(sk, "DisplayName")
                        if name and "lazarus" in name.lower():
                            return True
                    except FileNotFoundError:
                        pass
                    finally:
                        winreg.CloseKey(sk)
                except FileNotFoundError:
                    continue
        except OSError:
            pass
        finally:
            winreg.CloseKey(key)
    except Exception:
        pass
    return False


def find_lazarus_source_dirs() -> List[dict]:
    """Return the list of Lazarus/FPC source directories (for KB construction)."""
    root = find_lazarus_root()
    if not root:
        return []

    # Ensure root is the Lazarus installation root directory (not the bin directory)
    lazarus_root = root.parent if root.name == "bin" else root
    # Check whether this is the actual Lazarus root directory
    if not (lazarus_root / "lcl").is_dir():
        # root itself may be the Lazarus root
        if (root / "lcl").is_dir():
            lazarus_root = root
        else:
            return []

    sources: List[dict] = []

    # LCL
    lcl = lazarus_root / "lcl"
    if lcl.is_dir():
        sources.append({"path": str(lcl), "label": "LCL (Lazarus Component Library)"})

    # Components
    components = lazarus_root / "components"
    if components.is_dir():
        sources.append({"path": str(components), "label": "Lazarus bundled components"})

    # FPC source
    fpc_root = lazarus_root / "fpc"
    if fpc_root.is_dir():
        for ver_dir in sorted(fpc_root.iterdir(), reverse=True):
            src = ver_dir / "source"
            if src.is_dir():
                sources.append({"path": str(src), "label": f"FPC RTL {ver_dir.name}"})
                break
            elif ver_dir.is_dir():
                sources.append({"path": str(ver_dir), "label": f"FPC {ver_dir.name}"})
                break

    return sources

