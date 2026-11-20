"""
Package installation tool

Provides Delphi package compilation and installation
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, List, Dict, Any
from mcp.types import CallToolResult
from ..constants import REG_KEY_EMBARCADERO_BDS
from ..models.compile_request import TargetPlatform
from ..services.compiler_service import CompilerService
from ..services.project_settings import load_project_settings
from ..utils.delphi_env import (
    get_delphi_bpl_dir,
    get_delphi_version as detect_delphi_version,
)
from ..utils.delphi_versions import (
    normalize_version_key,
    project_version_to_registry_version,
)
from ..utils.dproj_parser import DprojParser
from ..utils.logger import get_logger

logger = get_logger(__name__)

_compiler_service: Optional[CompilerService] = None


def set_compiler_service(service: CompilerService):
    """Set the compiler service instance."""
    global _compiler_service
    _compiler_service = service


def _resolve_target_version(project_path: Optional[str]) -> Optional[str]:
    """Resolve the Delphi registry version a package project should use.

    Priority matches the compile service: project setting ``compiler_version``
    > project setting ``delphi_version`` > ``.dproj ProjectVersion``. A None
    return means it cannot be determined, and the caller falls back to the
    active compiler / newest installed version.
    """
    if not project_path or _compiler_service is None:
        return None
    settings = load_project_settings(project_path)
    if settings and settings.error:
        logger.error(settings.error)
        return None

    if settings and settings.compiler_version:
        lookup = getattr(
            _compiler_service,
            "_lookup_compiler_by_name_or_version",
            None,
        )
        if callable(lookup):
            compiler = lookup(
                settings.compiler_version,
                TargetPlatform.WIN32,
            )
            if compiler and compiler.registry_version:
                return compiler.registry_version
            if compiler is None:
                version_hint = normalize_version_key(settings.compiler_version)
                if version_hint:
                    return version_hint
    if settings and settings.delphi_version:
        return settings.delphi_version

    dproj = project_path
    if Path(dproj).suffix.lower() in (".dpr", ".dpk"):
        dproj = str(Path(dproj).with_suffix(".dproj"))
    if not Path(dproj).exists():
        return None
    try:
        parser = DprojParser(dproj)
        if not parser.parse():
            return None
        project_version = parser.get_project_version()
    except Exception:
        logger.debug("Failed to read .dproj ProjectVersion: %s", dproj, exc_info=True)
        return None
    if not project_version:
        return None
    return project_version_to_registry_version(project_version)


async def install_package(
    package_path: str,
    target_platform: str = "win32",
    build_configuration: str = "Debug",
    timeout: int = 300,
    install: bool = True
) -> CallToolResult:
    """
    Compile and install a Delphi package

    Args:
        package_path: Package file path (.dproj/.dpk/.groupproj)
        target_platform: Target platform (win32/win64)
        build_configuration: Build configuration (Debug/Release)
        timeout: Timeout in seconds
        install: Whether to install into the IDE automatically

    Returns:
        The compile/install result
    """
    logger.info(f"Received package install request: {package_path}")

    if _compiler_service is None:
        logger.error("Compiler service is not initialized")
        return CallToolResult(
            content=[{"type": "text", "text": "Compiler service is not initialized"}],
            isError=True
        )

    try:
        path_obj = Path(package_path)
        if not path_obj.exists():
            return CallToolResult(
                content=[{"type": "text", "text": f"File not found: {package_path}"}],
                isError=True
            )

        ext = path_obj.suffix.lower()
        if ext == '.groupproj':
            result = await _install_group_project(package_path, target_platform, build_configuration, timeout, install)
        elif ext == '.dproj':
            result = await _install_dproj_package(package_path, target_platform, build_configuration, timeout, install)
        elif ext == '.dpk':
            result = await _install_dpk_package(package_path, target_platform, build_configuration, timeout, install)
        else:
            return CallToolResult(
                content=[{"type": "text", "text": f"Unsupported file type: {ext}, supported: .dproj, .dpk, .groupproj"}],
                isError=True
            )

        return result

    except Exception as e:
        error_msg = f"Exception during package installation: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return CallToolResult(
            content=[{"type": "text", "text": error_msg}],
            isError=True
        )


async def _install_group_project(
    group_path: str,
    target_platform: str,
    build_configuration: str,
    timeout: int,
    install: bool
) -> CallToolResult:
    """
    Handle a project group (.groupproj)

    Supported XML nodes:
      - <Projects Include="..."> + <Dependencies>  (legacy format)
      - <ProjectReference Include="...">             (new format)
      - <BuildOrder>                                 (build order)
    """
    import xml.etree.ElementTree as ET
    from ..utils.groupproj_parser import (
        parse_groupproj,
        get_platform_for_project,
    )

    try:
        info = parse_groupproj(group_path)
    except ET.ParseError as e:
        return CallToolResult(
            content=[{"type": "text", "text": f"Failed to parse .groupproj XML: {e}"}],
            isError=True,
        )
    except FileNotFoundError:
        return CallToolResult(
            content=[{"type": "text", "text": f".groupproj file not found: {group_path}"}],
            isError=True,
        )

    results = []

    for proj_path in info.child_projects:
        proj_str = str(proj_path)
        # Take the default platform from the .groupproj; fall back to the passed platform
        child_platform = target_platform or get_platform_for_project(info, fallback="win32")
        is_runtime = _is_runtime_only_package(proj_str)
        result = await _compile_single_package(
            proj_str, child_platform, build_configuration, timeout
        )
        results.append((proj_str, is_runtime, result))

    if not results:
        return CallToolResult(
            content=[{"type": "text", "text": f"No valid child project found in the project group: {group_path}"}],
            isError=True,
        )

    return _format_group_results(results, install, target_platform)


async def _install_dproj_package(
    dproj_path: str,
    target_platform: str,
    build_configuration: str,
    timeout: int,
    install: bool
) -> CallToolResult:
    """Handle a single project."""
    is_runtime = _is_runtime_only_package(dproj_path)
    result = await _compile_single_package(dproj_path, target_platform, build_configuration, timeout)
    return _format_group_results([(dproj_path, is_runtime, result)], install, target_platform)


async def _install_dpk_package(
    dpk_path: str,
    target_platform: str,
    build_configuration: str,
    timeout: int,
    install: bool
) -> CallToolResult:
    """Handle a dpk package - converted to a dproj."""
    dproj_path = str(Path(dpk_path).with_suffix('.dproj'))
    
    if not Path(dproj_path).exists():
        return CallToolResult(
            content=[{"type": "text", "text": f"No matching .dproj file found: {dproj_path}"}],
            isError=True
        )
    
    result = await _compile_single_package(dproj_path, target_platform, build_configuration, timeout)
    return _format_results([(dproj_path, result)], install, target_platform)


async def _compile_single_package(
    project_path: str,
    target_platform: str,
    build_configuration: str,
    timeout: int,
    extra_args: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Compile a single package project."""
    from ..models.compile_request import ProjectCompileRequest, CompileOptions, TargetPlatform
    
    target_version = _resolve_target_version(project_path)
    existing_bpl = _find_bpl_file(
        project_path,
        target_platform,
        build_configuration,
        version=target_version,
    )
    
    if not extra_args and existing_bpl and Path(existing_bpl).exists():
        return {
            "success": True,
            "output_file": existing_bpl,
            "errors": [],
            "warnings": [],
            "log": f"Using existing BPL: {existing_bpl}",
            "duration": 0
        }
    
    options = CompileOptions(
        target_platform=TargetPlatform(target_platform),
        build_configuration=build_configuration,
        timeout=timeout,
        debug=True,
        extra_args=extra_args or [],
    )
    
    request = ProjectCompileRequest(
        project_path=project_path,
        options=options
    )
    
    result = await _compiler_service.compile_project_with_msbuild(request)
    
    output_file = None
    if result.status.value == "success":
        output_file = _find_bpl_file(
            project_path,
            target_platform,
            build_configuration,
            version=target_version,
        )
    
    return {
        "success": result.status.value == "success",
        "output_file": output_file if output_file else result.output_file,
        "errors": result.errors,
        "warnings": result.warnings,
        "log": result.log,
        "duration": result.duration
    }


async def _compile_dpk(dpk_path: str, target_platform: str, output_dir: str, timeout: int) -> Dict[str, Any]:
    """Compile a DPK package file directly."""
    import subprocess
    import tempfile
    
    if _compiler_service is None:
        return {
            "success": False,
            "output_file": None,
            "errors": [{"message": "Compiler service is not initialized"}],
            "warnings": [],
            "log": "",
            "duration": 0
        }
    
    target_version = _resolve_target_version(dpk_path)
    package_settings = load_project_settings(dpk_path)
    if package_settings and package_settings.error:
        logger.error(package_settings.error)
        return {
            "success": False,
            "output_file": None,
            "errors": [{"message": package_settings.error}],
            "warnings": [],
            "log": "",
            "duration": 0
        }
    rsvars_path = _compiler_service._get_rsvars_path(target_version)
    if not rsvars_path:
        return {
            "success": False,
            "output_file": None,
            "errors": [{"message": "rsvars.bat not found"}],
            "warnings": [],
            "log": "",
            "duration": 0
        }
    
    delphi_root = _compiler_service._get_effective_delphi_root(target_version)
    if not delphi_root:
        return {
            "success": False,
            "output_file": None,
            "errors": [{"message": "Could not get the Delphi installation directory"}],
            "warnings": [],
            "log": "",
            "duration": 0
        }
    
    version_key = target_version or Path(delphi_root).name
    if not re.fullmatch(r"\d+\.\d+", version_key):
        return {
            "success": False,
            "output_file": None,
            "errors": [{
                "message": f"Cannot determine the Delphi version number ({version_key!r}); "
                           "stopped writing to the BPL/DCP directories to avoid mixing versions"
            }],
            "warnings": [],
            "log": "",
            "duration": 0
        }
    public_doc = Path.home() / "Documents" / "Embarcadero" / "Studio" / version_key
    bpl_dir = public_doc / "Bpl" / _platform_to_dir(target_platform)
    dcp_dir = public_doc / "Dcp"
    
    bpl_dir.mkdir(parents=True, exist_ok=True)
    dcp_dir.mkdir(parents=True, exist_ok=True)
    
    platform_dir = _platform_to_dir(target_platform)
    lib_path = Path(delphi_root) / "lib" / platform_dir
    
    project_name = Path(dpk_path).stem.replace('GR32_', 'GR32')
    bpl_output = str(bpl_dir / "%s.bpl" % project_name)
    
    for _p_name, _p_val in [('rsvars_path', rsvars_path), ('dpk_path', dpk_path),
                             ('lib_path', lib_path), ('bpl_dir', bpl_dir), ('dcp_dir', dcp_dir)]:
        if '"' in str(_p_val):
            return {"success": False, "errors": [{"message": "Path contains an illegal character (\"): %s=%s" % (_p_name, _p_val)}],
                    "output_file": None, "warnings": [], "log": ""}
    
    batch_content = '@echo off\ncall "%s"\ndcc32 -b "%s" -U"%s" -LE"%s" -LN"%s"\n' % (
        rsvars_path, dpk_path, lib_path, bpl_dir, dcp_dir)
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.bat', delete=False, encoding='utf-8') as f:
        f.write(batch_content)
        batch_file = f.name
    
    try:
        proc = subprocess.Popen(
            ['cmd.exe', '/c', batch_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=Path(dpk_path).parent,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        )
        
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            return_code = proc.returncode
        except subprocess.TimeoutExpired:
            proc.kill()
            return {
                "success": False,
                "output_file": None,
                "errors": [{"message": f"Compilation timed out ({timeout}s)"}],
                "warnings": [],
                "log": "",
                "duration": timeout * 1000
            }
        
        output = stdout.decode('utf-8', errors='replace') + stderr.decode('utf-8', errors='replace')
        
        bpl_path = Path(bpl_output)
        success = return_code == 0 and bpl_path.exists()
        
        return {
            "success": success,
            "output_file": str(bpl_path) if success else None,
            "errors": [],
            "warnings": [],
            "log": output,
            "duration": 0
        }
        
    finally:
        try:
            os.unlink(batch_file)
        except OSError:
            pass


def _get_delphi_version(version: Optional[str] = None) -> Optional[str]:
    """Get the Delphi version number (preferring the caller's project version)."""
    if version:
        return version
    if _compiler_service:
        root_dir = _compiler_service._get_effective_delphi_root()
        if root_dir:
            version_key = Path(root_dir).name
            # RootDir usually ends with the version number, but some installs are "...\Studio", so it is not a version
            if re.fullmatch(r"\d+\.\d+", version_key):
                return version_key
        config_manager = getattr(_compiler_service, "config_manager", None)
        getter = getattr(config_manager, "get_effective_compiler", None)
        if callable(getter):
            compiler = getter(platform="win32")
            if compiler and compiler.registry_version:
                return compiler.registry_version
    return detect_delphi_version()


def _find_bpl_file(
    project_path: str,
    target_platform: str,
    build_configuration: str,
    version: Optional[str] = None,
) -> Optional[str]:
    """Locate the BPL file produced by the build."""
    version = _get_delphi_version(version)
    if not version:
        return None
    
    search_dirs = []
    public_bpl_dir = get_delphi_bpl_dir(version)
    if public_bpl_dir is not None:
        search_dirs.append(public_bpl_dir)
    search_dirs.append(Path.home() / "Documents" / "Embarcadero" / "Studio" / version / "Bpl")
    
    project_name = Path(project_path).stem
    is_runtime = '_R' in project_name
    
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        
        pattern = "GR32_R*" if is_runtime else "GR32_D*"
        bpl_files = list(search_dir.glob(pattern))
        if bpl_files:
            return str(bpl_files[0])
        
        bpl_files = list(search_dir.glob("GR32_*.bpl"))
        if bpl_files:
            return str(bpl_files[0])
    
    return None


def _platform_to_dir(platform: str) -> str:
    """Convert a platform name to a directory name."""
    mapping = {"win32": "Win32", "win64": "Win64"}
    return mapping.get(platform.lower(), "Win32")


def _is_runtime_only_package(project_path: str) -> bool:
    """Check whether this is a runtime-only package (no IDE installation needed)."""
    import xml.etree.ElementTree as ET
    
    try:
        tree = ET.parse(project_path)
        root = tree.getroot()
        ns = 'http://schemas.microsoft.com/developer/msbuild/2003'
        
        for pg in root.findall(f'.//{{{ns}}}PropertyGroup'):
            for child in pg:
                tag = child.tag.replace(f'{{{ns}}}', '')
                if tag == 'RuntimeOnlyPackage':
                    return child.text.strip().lower() == 'true'
        return False
    except Exception:
        return False


def _format_results(results: List[tuple], install: bool, target_platform: str) -> CallToolResult:
    """
    Format the compile result of a single project.

    Args:
        results: [(project_path, compile_result_dict), ...]
        install: Whether to show the installation guide
        target_platform: Target platform
    """
    grouped = []
    for r in results:
        proj_path = r[0]
        result = r[1]
        # A single project cannot be classified as runtime-only, so default to False (design-time package)
        grouped.append((proj_path, False, result))
    return _format_group_results(grouped, install, target_platform)


def _format_group_results(results: List[tuple], install: bool, target_platform: str) -> CallToolResult:
    """Format project-group compile results (distinguishing runtime and design-time packages)."""
    all_success = all(r[2].get("success", False) for r in results)
    
    output = "=" * 50 + "\n"
    output += "Package Compilation Results\n"
    output += "=" * 50 + "\n\n"
    
    design_bpl_files = []
    
    for proj_path, is_runtime, result in results:
        pkg_type = "runtime package" if is_runtime else "design-time package"
        output += f"Project: {Path(proj_path).name} ({pkg_type})\n"
        output += f"Status: {'success' if result.get('success') else 'failed'}\n"
        
        output_file = result.get("output_file", "")
        if output_file and output_file.endswith('.bpl'):
            output += f"BPL file: {output_file}\n"
            if not is_runtime:
                design_bpl_files.append(output_file)
        elif output_file:
            output += f"Output directory: {output_file}\n"
        
        if result.get("warnings"):
            output += f"Warnings: {len(result['warnings'])}\n"
        if result.get("errors"):
            output += f"Errors: {len(result['errors'])}\n"
        output += "\n"
    
    if install and all_success:
        install_version = None
        for proj_path, _is_runtime, result in results:
            if result.get("success"):
                install_version = _resolve_target_version(proj_path)
                if install_version:
                    break
        install_result = _format_install_guide(
            design_bpl_files,
            results,
            version=install_version,
        )
        output += install_result
    
    return CallToolResult(
        content=[{"type": "text", "text": output}],
        isError=not all_success
    )


def _format_install_guide(
    bpl_files: List[str],
    results: List[tuple],
    version: Optional[str] = None,
) -> str:
    """Build the installation guide."""
    output = "=" * 50 + "\n"
    output += "IDE Installation Guide\n"
    output += "=" * 50 + "\n\n"
    
    version = _get_delphi_version(version)
    
    if bpl_files:
        output += "Found the following BPL files:\n"
        for bpl in bpl_files:
            output += f"  {bpl}\n"
        output += "\n"
        
        if _register_packages_to_ide(bpl_files, version):
            output += "✅ Package installed into the IDE automatically!\n\n"
        else:
            output += "⚠️ Automatic installation failed, please install manually:\n"
    else:
        output += "No precompiled BPL file found\n"
        output += "Please install manually after compiling:\n"
        for proj_path, _is_runtime, result in results:
            if result.get("success"):
                project_name = Path(proj_path).stem.replace('GR32_', 'GR32')
                output += f"  - {project_name}_R.bpl (runtime)\n"
                output += f"  - {project_name}_D.bpl (design-time)\n"
        output += "\n"
    
    output += "Installation steps:\n"
    output += "1. Open the Delphi IDE\n"
    output += "2. Menu: Component → Install Packages...\n"
    output += "3. Click the Add button\n"
    output += "4. Browse to and select the BPL file(s) above\n"
    output += "5. Click OK to finish the installation\n"
    
    return output


def _register_packages_to_ide(bpl_files: List[str], version: Optional[str]) -> bool:
    """Register the packages with the IDE."""
    import winreg

    # Never write the registry with an invalid version: it would create a bogus
    # key such as ...\Studio\Known Packages, report success while nothing is installed.
    if not version or not re.fullmatch(r"\d+\.\d+", str(version)):
        logger.error(
            "Cannot determine the Delphi version number (%r); skipping auto-install to avoid writing a wrong IDE version",
            version,
        )
        return False

    try:
        key_path = f"{REG_KEY_EMBARCADERO_BDS}\\{version}\\Known Packages"
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)
        
        for bpl_path in bpl_files:
            try:
                winreg.SetValueEx(key, bpl_path, 0, winreg.REG_SZ, bpl_path)
                logger.info(f"Registered package: {bpl_path}")
            except Exception as e:
                logger.error(f"Failed to register package {bpl_path}: {e}")
        
        winreg.CloseKey(key)
        return True
    except Exception as e:
        logger.error(f"Failed to register package: {e}")
        return False


async def list_installed_packages() -> CallToolResult:
    """
    List installed packages

    Returns:
        List of installed packages
    """
    import winreg
    
    output = "Installed Delphi packages:\n\n"
    
    try:
        version = _get_delphi_version()
        if not version:
            return CallToolResult(
                content=[
                    {
                        "type": "text",
                        "text": "No Delphi version detected; cannot read the installed packages",
                    }
                ],
                isError=True,
            )

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            f"{REG_KEY_EMBARCADERO_BDS}\\{version}\\Known Packages",
            0,
            winreg.KEY_READ
        )
        
        index = 0
        while True:
            try:
                name, path, _ = winreg.EnumValue(key, index)
                output += f"  - {name}: {path}\n"
                index += 1
            except OSError:
                break
        
        winreg.CloseKey(key)
        
    except Exception as e:
        output += f"Failed to read the registry: {e}\n"
    
    return CallToolResult(content=[{"type": "text", "text": output}])


async def handle_package(**kwargs) -> dict:
    """Unified package tool entry point, dispatched by action.

    Args:
        action: "install" or "list"
        See the corresponding function for the other parameters.

    Returns:
        dict: {"status": "ok"/"failed", "message": ...}
    """
    action = kwargs.get("action", "install")
    try:
        if action == "install":
            result = await install_package(
                package_path=kwargs.get("package_path", ""),
                target_platform=kwargs.get("target_platform", "win32"),
                build_configuration=kwargs.get("build_configuration", "Debug"),
                timeout=kwargs.get("timeout", 300),
                install=kwargs.get("install", True),
            )
            # CallToolResult → dict
            if isinstance(result, CallToolResult):
                text = result.content[0].text if result.content else ""
                return {"status": "failed" if result.isError else "ok", "message": text}
            return {"status": "ok", "message": str(result)}

        elif action == "list":
            result = await list_installed_packages()
            if isinstance(result, CallToolResult):
                text = result.content[0].text if result.content else ""
                return {"status": "ok", "message": text}
            return {"status": "ok", "message": str(result)}

        else:
            return {"status": "failed", "message": f"Unknown action: {action}, available: install/list"}
    except Exception as e:
        logger.exception("package execution failed")
        return {"status": "failed", "message": str(e)}
