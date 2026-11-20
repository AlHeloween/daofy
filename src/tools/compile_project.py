"""
Project compilation tool

Provides overall Delphi project compilation functionality
"""

from pathlib import Path
from typing import Optional, List, Dict, Any
from mcp.types import CallToolResult
from ..models.compile_request import ProjectCompileRequest, CompileOptions, TargetPlatform, OutputType, RuntimeLibrary
from ..models.compile_result import CompileResult
from ..services.compiler_service import CompilerService
from ..services.project_settings import load_project_settings
from ..utils.dproj_parser import DprojParser
from ..utils.logger import get_logger
from ..utils.dproj_parser import resolve_target_platform_from_dproj
from ..utils.file_backup import detect_encoding
from ..services.delphi_edit_guard import (
    external_edit_block_message,
    record_authorized_write,
)
import json
import os
import shlex
import subprocess as _subprocess

from ..constants import TIMEOUT_PROCESS_TERMINATE

# Import functions from install_package (reuse existing logic)
try:
    from .install_package import (
        _is_runtime_only_package,
        _get_delphi_version,
        _register_packages_to_ide,
        _compile_single_package
    )
    _has_install_package = True
except ImportError:
    _has_install_package = False

logger = get_logger(__name__)

# Global compiler service instance
_compiler_service: Optional[CompilerService] = None


def _verify_tools_dir() -> Path:
    """Return the directory containing the verification tool units (tools/stacktrace/)."""
    return Path(__file__).parent.parent.parent / "tools" / "stacktrace"


def _compute_verify_exe_path(dproj_path: str, target_platform: str,
                              build_configuration: str) -> Path:
    """Calculate the compiled .exe path (prefer parsing from .dproj, then fall back to default)."""
    proj = Path(dproj_path)
    proj_dir = proj.parent
    plat_map = {"win32": "Win32", "win64": "Win64"}
    lib_dir = plat_map.get(target_platform.lower(), "Win32")
    cfg = build_configuration or "Debug"
    exe_name = proj.stem + ".exe"

    # Prefer reading DCC_ExeOutput from .dproj
    dproj_file = proj if proj.suffix.lower() == '.dproj' else proj.with_suffix('.dproj')
    if dproj_file.exists():
        try:
            parser = DprojParser(str(dproj_file))
            if parser.parse():
                output = parser.get_output_path(config=cfg, platform=lib_dir)
                if output:
                    return Path(output) / exe_name
        except Exception:
            pass

    return proj_dir / lib_dir / cfg / exe_name


def _verify_backup_paths(dproj: Path) -> dict:
    """Generate backup paths for .dproj/.dpr"""
    stem = dproj.stem
    return {
        '.dproj': dproj.with_name(stem + '.dproj.verify_bak'),
        '.dpr': dproj.with_name(stem + '.dpr.verify_bak'),
    }


def _inject_verify_units(dproj_path: str) -> str:
    """Modify .dproj + .dpr to inject StackTrace verification units, return the .dproj backup path.

    Injection content (.dproj):
       1. Add StackTrace.pas to DCCReference
       2. Add tools/stacktrace/ path to DCC_UnitSearchPath
       3. DCC_MapFile=3 (detailed) — generate a complete .map file for stack parsing

    Injection content (.dpr):
       1. Append StackTrace to the uses clause
       2. Insert TStackTraceManager initialization call after the begin block

    Args:
        dproj_path: .dproj file path

    Returns:
        .dproj backup file path
    """
    import shutil

    dproj = Path(dproj_path)
    backs = _verify_backup_paths(dproj)

    # ── Back up .dproj ──
    shutil.copy2(str(dproj), str(backs['.dproj']))

    content = dproj.read_text(encoding="utf-8-sig")

    # ── 1a. Add DCCReference for StackTrace.pas ──
    tools_dir = _verify_tools_dir()
    rel_stacktrace = os.path.relpath(str(tools_dir / "StackTrace.pas"), str(dproj.parent))
    inject_refs = (
        f'    <DCCReference Include="{rel_stacktrace}">\n'
        f'      <Form>False</Form>\n'
        f'    </DCCReference>'
    )
    ig_start = content.find('<ItemGroup>')
    ig_end = content.find('</ItemGroup>', ig_start) if ig_start >= 0 else -1
    if ig_start >= 0 and ig_end > ig_start:
        content = content[:ig_end] + inject_refs + '\n    ' + content[ig_end:]
    else:
        content = content.replace(
            '</Project>',
            '  <ItemGroup>\n' + inject_refs + '\n  </ItemGroup>\n</Project>'
        )

    import re

    # Also add DCC_UnitSearchPath (fallback)
    rel_path = os.path.relpath(str(tools_dir), str(dproj.parent))
    usp_pattern = r'(<DCC_UnitSearchPath>)(.*?)(</DCC_UnitSearchPath>)'
    if re.search(usp_pattern, content, flags=re.DOTALL):
        content = re.sub(
            usp_pattern,
            lambda m: m.group(1) + m.group(2) + (';' if m.group(2).strip() else '') + rel_path + m.group(3),
            content, flags=re.DOTALL
        )
    else:
        content = content.replace(
            '</PropertyGroup>',
            '  <DCC_UnitSearchPath>' + rel_path + '</DCC_UnitSearchPath>\n</PropertyGroup>',
            1
        )

    # ── 1b. DCC_MapFile=3 (detailed map) — for StackTrace to resolve function names + line numbers ──
    # Write into the Base PropertyGroup (the first unconditional PropertyGroup)
    dcc_map_pattern = r'<DCC_MapFile>\d+</DCC_MapFile>'
    if not re.search(dcc_map_pattern, content):
        # Insert before the first </PropertyGroup>
        content = content.replace(
            '</PropertyGroup>',
            '  <DCC_MapFile>3</DCC_MapFile>\n</PropertyGroup>',
            1
        )
    else:
        # If already present, set it to 3
        content = re.sub(dcc_map_pattern, '<DCC_MapFile>3</DCC_MapFile>', content)

    record_authorized_write(
        dproj,
        tool="delphi_project",
        operation="run_verify_inject_dproj",
    )
    dproj.write_text(content, encoding="utf-8-sig")
    logger.info("Injected StackTrace unit into .dproj: %s", dproj_path)

    # ── 2. Back up and modify .dpr (TStackTraceManager initialization) ──
    _inject_dpr_stacktrace(dproj, backs)

    return str(backs['.dproj'])


def _inject_dpr_stacktrace(dproj: Path, backs: dict):
    """Back up .dpr; inject TStackTraceManager initialization code

    Add the StackTrace unit to the uses clause.
    Insert TStackTraceManager initialization call after the begin block.
    """
    import shutil

    dpr_path = dproj.with_suffix('.dpr')
    if not dpr_path.exists():
        logger.warning("No .dpr found, skipping injection: %s", dpr_path)
        return

    original = dpr_path.read_text(encoding='utf-8-sig')
    if '{STACKTRACE_INJECT}' in original or 'TStackTraceManager.Enabled' in original:
        logger.info(".dpr already has TStackTraceManager injected, skipping")
        return

    # Back up .dpr
    shutil.copy2(str(dpr_path), str(backs['.dpr']))

    # ── 1. Append StackTrace in uses ──
    uses_pos = original.lower().find('uses\n') if original.lower().find('uses\n') >= 0 else original.lower().find('uses ')
    if uses_pos >= 0:
        end_uses = original.find(';', uses_pos + 4)
        if end_uses > uses_pos:
            uses_section = original[uses_pos:end_uses]
            if 'StackTrace' not in uses_section:
                original = original[:end_uses] + ', StackTrace' + original[end_uses:]

    # ── 2. Add TStackTraceManager initialization after begin ──
    lines = original.split('\n')
    begin_idx = -1
    for i in range(len(lines)):
        stripped = lines[i].strip()
        if stripped == 'begin':
            begin_idx = i
            break

    if begin_idx < 0:
        logger.warning("main begin not found in .dpr, skipping .dpr injection")
        return

    indent = '  '
    inject_lines = [
        '{STACKTRACE_INJECT}',
        '  TStackTraceManager.Enabled := True;',
        '  TStackTraceManager.Current.EnableDefaultLogger;',
    ]
    for j, line in enumerate(inject_lines):
        lines.insert(begin_idx + 1 + j, line)

    record_authorized_write(
        dpr_path,
        tool="delphi_project",
        operation="run_verify_inject_dpr",
    )
    dpr_path.write_text('\n'.join(lines), encoding='utf-8-sig')
    logger.info("Injected TStackTraceManager initialization into .dpr: %s", dpr_path)


def _restore_dproj(dproj_path: str, backup_path: str):
    """Restore the original .dproj and .dpr files from backup"""
    import shutil
    dproj = Path(dproj_path)
    backs = _verify_backup_paths(dproj)

    dproj_bak = Path(backup_path)
    if dproj_bak.exists():
        record_authorized_write(
            dproj_path,
            tool="delphi_project",
            operation="run_verify_restore_dproj",
        )
        shutil.copy2(str(dproj_bak), str(dproj_path))
        dproj_bak.unlink()
        logger.info("Restored original .dproj")
    else:
        logger.warning("Verification backup file does not exist: %s", backup_path)

    dpr_bak = backs['.dpr']
    if dpr_bak.exists():
        record_authorized_write(
            dproj.with_suffix('.dpr'),
            tool="delphi_project",
            operation="run_verify_restore_dpr",
        )
        shutil.copy2(str(dpr_bak), str(dproj.with_suffix('.dpr')))
        dpr_bak.unlink()
        logger.info("Restored original .dpr")


def set_compiler_service(service: CompilerService):
    """Set the compiler service instance"""
    global _compiler_service
    _compiler_service = service


def _detect_compiler_from_project(project_path: str, target_platform: str) -> Optional[str]:
    """
    Automatically detect the most suitable compiler from the project

    Args:
        project_path: Project file path
        target_platform: Target platform

    Returns:
        Compiler name, or None if detection fails
    """
    project_path_obj = Path(project_path)
    if not project_path_obj.exists():
        logger.warning(f"Project file does not exist: {project_path}")
        return None

    dproj_path = project_path
    if project_path_obj.suffix.lower() == '.dpr':
        dproj_path = str(project_path_obj.with_suffix('.dproj'))

    if not Path(dproj_path).exists():
        logger.warning(f".dproj file not found: {dproj_path}")
        return None

    # Project-level configuration takes precedence: different projects on the same machine may use different Delphi versions,
    # the version declared in .daofy/project.json under the project directory must take precedence over .dproj inference.
    settings = load_project_settings(dproj_path)
    if settings and _compiler_service and _compiler_service.config_manager:
        manager = _compiler_service.config_manager
        if settings.compiler_version:
            compiler = manager.get_compiler(settings.compiler_version)
            if not compiler:
                # Support writing version number/product name into compiler_version (e.g. "11.0", "XE4")
                lookup = getattr(
                    _compiler_service,
                    "_lookup_compiler_by_name_or_version",
                    None,
                )
                if callable(lookup):
                    compiler = lookup(
                        settings.compiler_version,
                        TargetPlatform(target_platform),
                    )
            if compiler:
                logger.info(
                    "Using compiler according to project configuration: %s (source %s)",
                    compiler.name,
                    settings.source,
                )
                return compiler.name
            if settings.delphi_version:
                logger.warning(
                    "Project-configured compiler_version=%r is unavailable, falling back to delphi_version=%s"
                    " (source %s)",
                    settings.compiler_version,
                    settings.delphi_version,
                    settings.source,
                )
                return None
            logger.error(
                "Compiler %r specified by project configuration does not exist (source %s)",
                settings.compiler_version,
                settings.source,
            )
            return None
        if settings.delphi_version:
            # Do not "translate" the project version into some compiler name at the tool layer and pass it back:
            # that would be treated by the compilation service as an explicit compiler_version, overriding the project-declared
            # delphi_version (if the compiler's registry_version in compilers.json
            # is misconfigured, it would mix versions). Leave it empty and let the compilation service resolve by project version.
            logger.info(
                "Project configuration specifies Delphi %s (source %s), leaving it to the compilation service to resolve by that version",
                settings.delphi_version,
                settings.source,
            )
            return None

    parser = DprojParser(dproj_path)
    if not parser.parse():
        logger.error(f"Failed to parse .dproj file: {dproj_path}")
        return None

    project_version = parser.get_project_version()
    if not project_version:
        logger.warning(f"Could not obtain project version number: {dproj_path}")
        return None

    logger.info(f"Project version number: {project_version}")

    if _compiler_service and _compiler_service.config_manager:
        compiler = _compiler_service.config_manager.get_compiler_for_project(project_version, target_platform)
        if compiler:
            logger.info(f"Automatically matched compiler: {compiler.name}")
            return compiler.name

    return None


def _cleanup_project_dcu(project_dir: Path):
    """Recursively clean all .dcu / .dcpp / .dpu cache files under the project directory"""
    patterns = ['**/*.dcu', '**/*.dcpp', '**/*.dpu']
    deleted = 0
    for pattern in patterns:
        for f in Path(project_dir).glob(pattern):
            try:
                f.unlink()
                deleted += 1
            except OSError as e:
                logger.debug(f"Failed to delete cache file: {f}: {e}")
    if deleted > 0:
        logger.info(f"Cleaned {deleted} compiler cache files")


def _check_and_clean_stale_resources(project_path: str, build_configuration: Optional[str] = None, target_platform: str = "win32") -> bool:
    """
    Check whether resource files referenced in .dproj are newer than the generated exe.
    If a resource file is newer, delete the corresponding .res file to force brcc32 to recompile.

    Each <RcItem Include="..."> in .dproj corresponds to a resource source file;
    the compiler compiles it to .res via brcc32 and then links it into the exe.
    However, MSBuild incremental build detection of <RcItem> changes is unreliable,
    so modifying the source file may not trigger recompilation.

    Returns:
        True if resource file changes were found (and handled), False if no handling is needed
    """
    try:
        proj_path = Path(project_path)
        if not proj_path.exists():
            return False

        # Parse .dproj to get resource references
        parser = DprojParser(str(proj_path))
        if not parser.parse():
            return False

        resources = parser.get_resource_items()
        if not resources:
            return False

        # Get output exe path
        config = build_configuration or "Debug"
        platform = target_platform or "win32"
        # Normalize platform name capitalization: win32 → Win32, win64 → Win64
        platform_cap = platform.capitalize() if platform in ("win32", "win64") else platform

        exe_dir_str = parser.get_output_path(config=config, platform=platform_cap)
        if not exe_dir_str:
            # Try to find from the default output path under the dproj directory
            project_dir = proj_path.parent
            exe_dir = project_dir / platform_cap / config
        else:
            exe_dir = Path(exe_dir_str)

        # Find exe
        project_name = proj_path.stem
        exe_path = exe_dir / f"{project_name}.exe"
        if not exe_path.exists():
            return False

        exe_mtime = exe_path.stat().st_mtime

        stale_resources = []
        for res in resources:
            src_path = res["source_path"]
            src_file = Path(src_path)
            if not src_file.exists():
                continue
            # Resource source file is newer than exe → recompile is needed
            if src_file.stat().st_mtime > exe_mtime:
                stale_resources.append(res)

        if not stale_resources:
            return False

        # Resource changes found: delete possibly generated .res files (brcc32 output) and .dcu cache
        res_files_cleaned = 0
        for res in stale_resources:
            # brcc32 output: a .res file with the same name under the project directory
            src_file = Path(res["source_path"])
            possible_res = src_file.with_suffix(".res")
            if possible_res.exists():
                possible_res.unlink()
                res_files_cleaned += 1
                logger.info(f"Resource changed → deleted old .res: {possible_res.name}")

        # Also clean up possible .res caches under the project directory
        # Delphi sometimes generates .res under $(BDS)\lib\$(Platform)\release
        for res in stale_resources:
            res_name = f"{res['resource_id']}.res"
            for cached in proj_path.parent.rglob(res_name):
                try:
                    cached.unlink()
                    logger.info(f"Resource changed → deleted cache: {cached}")
                except Exception as e:
                    logger.debug("Ignoring non-fatal exception: %s", str(e))

        # Also clean .dcu cache (resource changes may affect code paths)
        _cleanup_project_dcu(proj_path.parent)

        logger.info(
            f"Detected {len(stale_resources)} changed resource files: "
            + ", ".join(r["resource_id"] or r["include"] for r in stale_resources)
            + ", cache cleaned; a full rebuild will be performed"
        )
        return True

    except Exception as e:
        logger.warning(f"Resource change detection exception (does not affect compilation): {e}")
        return False


async def compile_project(
    project_path: str,
    target_platform: Optional[str] = None,
    output_path: Optional[str] = None,
    compiler_version: Optional[str] = None,
    timeout: int = 600,
    conditional_defines: Optional[List[str]] = None,
    unit_search_paths: Optional[List[str]] = None,
    resource_search_paths: Optional[List[str]] = None,
    optimize: bool = True,
    debug: bool = False,
    warning_level: int = 2,
    disabled_warnings: Optional[List[str]] = None,
    output_type: str = "gui",
    runtime_library: str = "static",
    build_configuration: Optional[str] = None,
    extra_args: Optional[List[str]] = None,
    auto_install: bool = True,
    run_after_compile: bool = False,
    run_verify: bool = False
) -> CallToolResult:
    """
    Compile a Delphi project

    Args:
        project_path: Project file path (.dproj/.dpr/.dpk/.groupproj)
        target_platform: Target platform (win32/win64/osx64/osxarm64/iosdevice64/android/linux64, etc.; read from .dproj when not passed)
        output_path: Output path
        compiler_version: Compiler version name
        timeout: Timeout (seconds)
        conditional_defines: List of conditional compilation symbols
        unit_search_paths: List of unit search paths
        resource_search_paths: List of resource search paths
        optimize: Whether to enable optimization
        debug: Whether to generate debug information
        warning_level: Warning level (0-4)
        disabled_warnings: List of disabled warnings
        output_type: Output type (console/gui/dll)
        runtime_library: Runtime library linking method (static/dynamic)
        build_configuration: Build configuration name
        extra_args: Complete argument list appended to the actual compilation backend
        auto_install: If it is a design-time package, whether to install automatically (default True)
        run_after_compile: After successful compilation, launch the program with the last run parameters
        run_verify: After successful compilation, launch the program for 3 seconds to verify whether it crashes (automatically terminates the process)

    Returns:
        Compilation result dictionary
    """
    logger.info(f"Received project compilation request: {project_path}")

    if _compiler_service is None:
        logger.error("Compiler service is not initialized")
        return CallToolResult(
            content=[{"type": "text", "text": "Compiler service is not initialized"}],
            isError=True
        )

    try:
        block_message = external_edit_block_message(project_path)
        if block_message:
            return CallToolResult(
                content=[{"type": "text", "text": block_message}],
                isError=True,
            )

        # Check whether it is a .dpk file
        project_ext = Path(project_path).suffix.lower()

        # Lazarus project (.lpi/.lpr): compile directly via lazbuild
        if project_ext in ('.lpi', '.lpr'):
            target_platform = (target_platform or "win32").lower()

            options = CompileOptions(
                target_platform=TargetPlatform(target_platform),
                build_configuration=build_configuration or "Default",
                timeout=timeout,
                compiler_version=compiler_version,
            )
            request = ProjectCompileRequest(
                project_path=project_path,
                options=options,
            )
            result = await _compiler_service.compile_project(request)
            result_dict = result.to_dict()
            result_text = json.dumps(result_dict, ensure_ascii=False, default=str)
            return CallToolResult(
                content=[{"type": "text", "text": result_text}],
                isError=result.status.value != "success",
            )

        if project_ext == '.groupproj':
            # Handle project group file (.groupproj)
            return await _compile_group_project(
                project_path=project_path,
                target_platform=target_platform,
                build_configuration=build_configuration or "Debug",
                timeout=timeout,
                compiler_version=compiler_version,
                extra_args=extra_args,
            )

        if project_ext == '.dpk':
            # Handle DPK package file
            return await _compile_dpk_package(
                project_path=project_path,
                target_platform=target_platform,
                build_configuration=build_configuration or "Debug",
                timeout=timeout,
                auto_install=auto_install,
                extra_args=extra_args,
            )

        # Read from .dproj only when the user did not specify a target platform
        # (explicitly passing win32/win64, etc. must not be overridden by the .dproj Active Platform)
        if not target_platform:
            target_platform = resolve_target_platform_from_dproj(project_path)
            logger.info(f"Read target platform from .dproj: {target_platform}")
        else:
            target_platform = target_platform.lower()
        
        # Automatically detect compiler version (if not specified)
        if not compiler_version:
            detected = _detect_compiler_from_project(project_path, target_platform)
            if detected:
                compiler_version = detected
                logger.info(f"Automatically detected compiler: {compiler_version}")
            else:
                logger.info(
                    "No compiler was automatically detected; the compilation service will resolve it by project configuration/default compiler"
                )

        # Check whether resource files changed (automatically clean cache to force recompilation)
        _check_and_clean_stale_resources(project_path, build_configuration, target_platform)

        # Build compilation options
        options = CompileOptions(
            target_platform=TargetPlatform(target_platform),
            output_path=output_path,
            compiler_version=compiler_version,
            timeout=timeout,
            conditional_defines=conditional_defines or [],
            unit_search_paths=unit_search_paths or [],
            resource_search_paths=resource_search_paths or [],
            optimize=optimize,
            debug=debug,
            warning_level=warning_level,
            disabled_warnings=disabled_warnings or [],
            output_type=OutputType(output_type),
            runtime_library=RuntimeLibrary(runtime_library),
            build_configuration=build_configuration,
            extra_args=extra_args or [],
        )

        # Build compilation request
        request = ProjectCompileRequest(
            project_path=project_path,
            options=options
        )

        # Execute compilation
        result = await _compiler_service.compile_project(request)

        # F2084 Internal Error: compiler internal error, usually caused by corrupted .dcu cache
        # automatically clean .dcu and recompile once
        if (result.status.value == "failed" and result.log and
            ("F2084" in result.log or "Internal Error" in result.log)):
            logger.warning("Detected compiler internal error (F2084), cleaning .dcu cache and recompiling...")
            _cleanup_project_dcu(Path(project_path).parent)
            result = await _compiler_service.compile_project(request)
            if result.status.value == "success":
                logger.info("Compilation succeeded after cleaning .dcu")
            else:
                logger.warning("Compilation still failed after cleaning .dcu")

        # Return result - AI Agent friendly: structured list of output artifact paths
        result_dict = result.to_dict()

        # After successful compilation, launch the program if requested
        if run_after_compile and result.status.value == "success":
            try:
                exe_path = result.output_file
                if exe_path and Path(exe_path).exists():
                    # Read last run parameters from .dproj
                    parser = DprojParser(project_path)
                    run_params = None
                    if parser.parse():
                        plat = (target_platform or "win32").capitalize()
                        cfg = build_configuration or "Debug"
                        run_params = parser.get_debugger_run_params(config=cfg, platform=plat)

                    cmd = [exe_path]
                    if run_params:
                        try:
                            cmd.extend(shlex.split(run_params))
                        except Exception:
                            cmd.extend(run_params.split())

                    proc = _subprocess.Popen(
                        cmd,
                        cwd=Path(exe_path).parent,
                        creationflags=getattr(_subprocess, 'CREATE_NEW_CONSOLE', 0),
                    )
                    result_dict["_launch"] = {
                        "pid": proc.pid,
                        "params": run_params,
                    }
                    logger.info(f"Launching program after compilation: {exe_path} PID={proc.pid} args={run_params}")
                else:
                    logger.warning(f"Launch after compilation: output file not found {exe_path}")
            except Exception as e:
                logger.warning(f"Launch after compilation failed: {e}")

        # ── Run verification (inject StackTrace unit, compile, run and check exception.log) ──
        if run_verify and result.status.value == "success":
            verify_info = {}
            backup_path = None
            try:
                # First compute the exe path
                exe_path = str(_compute_verify_exe_path(
                    project_path,
                    target_platform or "win32",
                    build_configuration or "Debug"
                ))
                if not Path(exe_path).exists():
                    logger.warning("Run verification: output file not found %s", exe_path)
                    verify_info = {"error": "output file not found"}
                else:
                    # 1. Back up and inject StackTrace unit into .dproj
                    backup_path = _inject_verify_units(project_path)

                    # 2. Recompile (the injected .dproj will be read by msbuild)
                    verify_result = await _compiler_service.compile_project(request)

                    if verify_result.status.value != "success":
                        err_detail = verify_result.log or verify_result.error_message or "(no log)"
                        logger.warning("Compilation failed after injecting StackTrace: %s", err_detail[:500])
                        verify_info = {"error": "injected compile failed", "log": err_detail[:1000]}
                    else:
                        # 3. Run the verification exe (no pipe, read exception.log)
                        verify_exe = str(_compute_verify_exe_path(
                            project_path,
                            target_platform or "win32",
                            build_configuration or "Debug"
                        ))
                        if not Path(verify_exe).exists():
                            verify_info = {"error": f"output not found after recompile: {verify_exe}"}
                        else:
                            exe_dir = Path(verify_exe).parent
                            log_path = exe_dir / 'exception.log'
                            if log_path.exists():
                                try:
                                    log_path.unlink()
                                except Exception as e:
                                    logger.debug("Failed to clean exception.log: %s", e)

                            proc = _subprocess.Popen([verify_exe], cwd=exe_dir)
                            try:
                                proc.wait(timeout=TIMEOUT_PROCESS_TERMINATE)
                            except _subprocess.TimeoutExpired:
                                proc.kill()
                                proc.wait()

                            if log_path.exists():
                                try:
                                    enc = detect_encoding(str(log_path))
                                    log_content = log_path.read_text(encoding=enc, errors='replace')
                                    verify_info = {"error": "runtime exception", "log": log_content}
                                    logger.warning("Runtime exception: %s", log_content[:200])
                                except Exception as read_err:
                                    verify_info = {"error": "runtime exception", "read_error": str(read_err)}
                            else:
                                verify_info = {"passed": True}
                                logger.info("Run verification passed")
            except Exception as e:
                logger.warning("Run verification exception: %s", e, exc_info=True)
                verify_info = {"error": str(e)}
            finally:
                if backup_path:
                    try:
                        _restore_dproj(project_path, backup_path)
                    except Exception as e:
                        logger.error("Failed to restore .dproj: %s", e)
                        verify_info.setdefault("errors", []).append(f"restore dproj failed: {e}")

            result_dict["_verify"] = verify_info

        result_text = json.dumps(result_dict, ensure_ascii=False, default=str)
        return CallToolResult(
            content=[{"type": "text", "text": result_text}],
            isError=result.status.value != "success"
        )
    except Exception as e:
        error_msg = f"Exception occurred during compilation: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return CallToolResult(
            content=[{"type": "text", "text": error_msg}],
            isError=True
        )


async def _compile_dpk_package(
    project_path: str,
    target_platform: str,
    build_configuration: str,
    timeout: int,
    auto_install: bool,
    extra_args: Optional[List[str]] = None,
) -> CallToolResult:
    """
    Compile a DPK package file

    Args:
        project_path: DPK file path
        target_platform: Target platform
        build_configuration: Build configuration
        timeout: Timeout
        auto_install: Whether to install design-time package
        extra_args: Complete argument list appended to MSBuild

    Returns:
        Compilation result
    """
    # Find the corresponding .dproj file
    dproj_path = Path(project_path).with_suffix('.dproj')
    
    if not dproj_path.exists():
        # If there is no .dproj, try compiling .dpk directly
        logger.warning(f"Corresponding .dproj file not found: {dproj_path}, trying to compile .dpk directly")
        dproj_path = Path(project_path)
    
    # Use functions in install_package to compile and detect
    if _has_install_package:
        # Reuse the full compilation logic of install_package
        compile_result = await _compile_single_package(
            str(dproj_path),
            target_platform,
            build_configuration,
            timeout,
            extra_args=extra_args,
        )
        
        is_runtime = _is_runtime_only_package(str(dproj_path))
        is_design_package = not is_runtime
        success = compile_result.get("success", False)
        output_file = compile_result.get("output_file", "")
        errors = compile_result.get("errors", [])
        warnings = compile_result.get("warnings", [])
    else:
        # Fallback plan
        is_design_package = _is_design_package_simple(project_path)
        
        options = CompileOptions(
            target_platform=TargetPlatform(target_platform),
            build_configuration=build_configuration,
            timeout=timeout,
            debug=True,
            extra_args=extra_args or [],
        )
        
        request = ProjectCompileRequest(
            project_path=str(dproj_path),
            options=options
        )
        
        result = await _compiler_service.compile_project(request)
        
        success = result.status.value == "success"
        output_file = result.output_file
        errors = result.errors
        warnings = result.warnings
    
    logger.info(f"Package type: {'design-time package' if is_design_package else 'runtime package'}")
    
    # If compilation succeeds and it is a design-time package, install automatically
    if success and is_design_package and auto_install:
        logger.info("Compilation succeeded, starting to install design-time package...")
        
        # Use registration function in install_package
        if _has_install_package:
            version = _get_delphi_version()
            install_success = _register_packages_to_ide([output_file], version)
            install_result = "installed to IDE" if install_success else "auto-install failed, manual install required"
        else:
            install_result = f"Please install manually: {output_file}"
        
        # Scan all output artifacts
        try:
            of = CompilerService._collect_output_files(
                project_path, target_platform, build_configuration,
            )
        except Exception:
            of = []
        output_text = f"Compilation succeeded: {output_file}\n"
        output_text += f"Package type: design-time package\n"
        if of:
            output_text += "\n[Output Files]\n"
            for f in of:
                output_text += f"  {f}\n"
        output_text += f"\nInstallation result: {install_result}"
        
        return CallToolResult(
            content=[{"type": "text", "text": output_text}],
            isError=False
        )
    
    # Return compilation result
    output_text = f"Compilation {'succeeded' if success else 'failed'}\n"
    output_text += f"Output file: {output_file}\n"
    output_text += f"Package type: {'design-time package' if is_design_package else 'runtime package'}\n"

    # Display all output artifact paths (critical for subsequent AI Agent operations)
    if success:
        # Try to scan output artifacts
        try:
            of = CompilerService._collect_output_files(
                project_path,
                target_platform,
                build_configuration,
            )
            if of:
                output_text += "\n[Output Files]\n"
                for f in of:
                    output_text += f"  {f}\n"
        except Exception as e:
            logger.debug("Failed to collect output file list: %s", e)
        
    if errors:
        output_text += f"\nErrors:\n"
        for err in errors:
            output_text += f"  {err}\n"
        
    if warnings:
        output_text += f"\nWarnings:\n"
        for warn in warnings:
            output_text += f"  {warn}\n"
        
    return CallToolResult(
        content=[{"type": "text", "text": output_text}],
        isError=not success
    )


async def _compile_group_project(
    project_path: str,
    target_platform: Optional[str],
    build_configuration: str,
    timeout: int,
    compiler_version: Optional[str] = None,
    extra_args: Optional[List[str]] = None,
) -> CallToolResult:
    """
    Compile all child projects in a project group (.groupproj)

    Parse the .groupproj XML file, extract all Projects entries,
    sort by <BuildOrder>, compile one by one, and aggregate all results.

    Supported XML nodes:
      - <Projects Include="..."> + <Dependencies>  (old format)
      - <ProjectReference Include="...">             (new format)
      - <BuildOrder>                                 (build order)

    Args:
        project_path: .groupproj file path
        target_platform: Target platform
        build_configuration: Build configuration
        timeout: Timeout for a single child project
        compiler_version: Compiler version
        extra_args: Extra compilation arguments

    Returns:
        Aggregated compilation result
    """
    import xml.etree.ElementTree as ET
    from ..utils.groupproj_parser import (
        parse_groupproj,
        get_platform_for_project,
        get_config_for_project,
    )
    from ..utils.dproj_parser import resolve_target_platform_from_dproj

    logger.info("Compiling project group: %s", project_path)
    group_path = Path(project_path)

    try:
        info = parse_groupproj(group_path)
    except FileNotFoundError:
        return CallToolResult(
            content=[{"type": "text", "text": f".groupproj file does not exist: {project_path}"}],
            isError=True,
        )
    except ET.ParseError as e:
        return CallToolResult(
            content=[{"type": "text", "text": f"Failed to parse .groupproj XML: {e}"}],
            isError=True,
        )

    child_projects = info.child_projects

    if not child_projects:
        return CallToolResult(
            content=[{"type": "text", "text": f"No valid child projects found in project group: {project_path}"}],
            isError=True,
        )

    # Use the default configuration in .groupproj (if not specified)
    if not build_configuration or build_configuration == "Debug":
        build_configuration = get_config_for_project(info, fallback=build_configuration or "Debug")

    logger.info(
        "Project group contains %d child projects (BuildOrder: %s): %s",
        len(child_projects),
        "yes" if info.build_order else "no",
        [p.name for p in child_projects],
    )

    # Compile child projects one by one and aggregate results
    total_errors = 0
    total_warnings = 0
    success_count = 0
    skip_count = 0
    results_text_parts: List[str] = []
    all_success = True

    for child in child_projects:
        child_ext = child.suffix.lower()
        logger.info(f"Compiling child project [{child.name}] ...")

        try:
            if child_ext in ('.dproj', '.dpr'):
                # Resolve target platform of child project
                child_platform = (target_platform or "win32").lower()
                if child_ext == '.dproj' or (child_ext == '.dpr' and child.with_suffix('.dproj').exists()):
                    try:
                        resolved = resolve_target_platform_from_dproj(str(child))
                        if resolved:
                            child_platform = resolved
                    except Exception:
                        pass

                # Build CompileOptions
                options = CompileOptions(
                    target_platform=TargetPlatform(child_platform),
                    build_configuration=build_configuration,
                    timeout=timeout,
                    compiler_version=compiler_version,
                    extra_args=extra_args or [],
                )
                request = ProjectCompileRequest(
                    project_path=str(child),
                    options=options,
                )
                result = await _compiler_service.compile_project(request)
                child_success = result.status.value == "success"
                child_errors = result.errors or []
                child_warnings = result.warnings or []

            elif child_ext == '.dpk':
                # DPK packages are compiled via _compile_dpk_package
                dpk_result = await _compile_dpk_package(
                    project_path=str(child),
                    target_platform=target_platform or "win32",
                    build_configuration=build_configuration,
                    timeout=timeout,
                    auto_install=False,
                    extra_args=extra_args,
                )
                # Extract status from dpk_result (CallToolResult)
                child_success = not dpk_result.isError
                child_errors = [dpk_result.content[0].text] if not child_success else []
                child_warnings = []
            else:
                logger.warning(f"Unsupported child project type in project group, skipped: {child} (extension: {child_ext})")
                results_text_parts.append(f"  ⚠ {child.name}: unsupported file type ({child_ext}), skipped")
                skip_count += 1
                continue

            if child_success:
                success_count += 1
                results_text_parts.append(f"  ✅ {child.name}: compilation succeeded")
            else:
                results_text_parts.append(f"  ❌ {child.name}: compilation failed")
                all_success = False

            total_errors += len(child_errors) if isinstance(child_errors, list) else (1 if child_errors else 0)
            total_warnings += len(child_warnings) if isinstance(child_warnings, list) else 0

            # Error details (truncated display)
            if not child_success and child_errors:
                for err in (child_errors[:5] if isinstance(child_errors, list) else [str(child_errors)[:300]]):
                    results_text_parts.append(f"      {err}")
            if child_warnings and len(child_warnings) <= 10:
                for w in child_warnings:
                    results_text_parts.append(f"      ⚠ {w}")

        except Exception as e:
            logger.error(f"Child project {child.name} compilation exception: {e}", exc_info=True)
            results_text_parts.append(f"  ❌ {child.name}: exception — {e}")
            all_success = False
            total_errors += 1

    output_text = (
        f"Project group compilation {'completed' if all_success else 'completed (with partial failure)'}\n"
        f"Project group: {group_path.name}\n"
        f"Child projects: {len(child_projects)}, "
        f"Succeeded: {success_count}, Failed: {len(child_projects) - success_count - skip_count}, Skipped: {skip_count}\n"
        f"Total errors: {total_errors}, Total warnings: {total_warnings}\n\n"
        + "\n".join(results_text_parts)
    )

    return CallToolResult(
        content=[{"type": "text", "text": output_text}],
        isError=not all_success,
    )


def _is_design_package_simple(package_path: str) -> bool:
    """
    Simple detection of whether it is a design-time package (fallback used when install_package is unavailable)

    Args:
        package_path: Package file path

    Returns:
        Whether it is a design-time package
    """
    try:
        with open(package_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read().upper()
        
        # Detect design-time package markers
        design_markers = [
            '{$DESIGNONLY',
            'DSNIDE',
            'DESIGNINTF',
            'DESIGNEDITORS',
        ]
        
        for marker in design_markers:
            if marker in content:
                return True
        
        return False
    except Exception as e:
        logger.error(f"Failed to detect package type: {e}")
        return False