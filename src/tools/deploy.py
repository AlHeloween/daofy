"""
Delphi deployment tool

Provides Delphi project deployment, supporting:
- Enumerate connected devices (iOS/Android/Windows)
- Deploy a compiled application to a device
- Supports PAServer (iOS/macOS) and ADB (Android) deployment routes
"""

import asyncio
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..services.project_settings import ProjectSettings, load_project_settings
from ..utils.delphi_versions import (
    normalize_version_key,
    project_version_to_registry_version,
    resolve_registry_version,
)
from ..utils.dproj_parser import DprojParser
from ..utils.logger import get_logger

logger = get_logger(__name__)


class DeployService:
    """Delphi deployment service."""

    def __init__(self):
        self._paserver_path: Optional[str] = None
        self._adb_path: Optional[str] = None

    # ─── Device enumeration ────────────────────────────────────────

    async def list_devices(self, platform: Optional[str] = None,
                           project_path: Optional[str] = None) -> Dict[str, Any]:
        """Enumerate connected devices

        Args:
            platform: Target platform (iosdevice64/iossimulator/android64/androidarm64/win32/win64).
                      When omitted, inferred from the project; if that fails, every available platform is enumerated.
            project_path: Project file path (optional; used to infer the target platform)

        Returns:
            Device list dictionary
        """
        platform = self._resolve_platform(platform, project_path)
        devices: List[Dict[str, Any]] = []

        if platform.startswith("ios"):
            devices = await self._list_ios_devices(platform)
        elif platform.startswith("android"):
            devices = await self._list_android_devices()
        elif platform in ("win32", "win64"):
            devices = self._list_windows_devices(platform)
        else:
            # Enumerate every available platform
            all_devices: Dict[str, List[Dict[str, Any]]] = {}
            for plat in ("iosdevice64", "android64", "win32"):
                try:
                    result = await self.list_devices(platform=plat)
                    if result.get("devices"):
                        all_devices[plat] = result["devices"]
                except Exception as e:
                    logger.debug("Failed to enumerate %s devices: %s", plat, e)
            return {
                "status": "ok",
                "platform": "all",
                "devices": all_devices,
            }

        return {
            "status": "ok",
            "platform": platform,
            "devices": devices,
        }

    async def _list_ios_devices(self, platform: str) -> List[Dict[str, Any]]:
        """Enumerate iOS devices (via PAServer or iosdeploy)

        iOS deployment requires either:
        1. PAServer (Platform Assistant Server) running on a Mac
        2. Or the iosdeploy / libimobiledevice tools
        """
        devices: List[Dict[str, Any]] = []

        # Method 1: try iosdeploy (libimobiledevice)
        iosdeploy_path = self._find_iosdeploy()
        if iosdeploy_path:
            try:
                proc = await asyncio.create_subprocess_exec(
                    iosdeploy_path, "--detect",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
                output = stdout.decode("utf-8", errors="replace")
                for line in output.splitlines():
                    # Parse the iosdeploy output format: "Found Apple Device: <UDID> (<Name>)"
                    match = re.search(
                        r"Found\s+(?:Apple\s+)?Device:\s+(\S+)\s+\(([^)]+)\)", line
                    )
                    if match:
                        devices.append({
                            "udid": match.group(1),
                            "name": match.group(2),
                            "platform": platform,
                            "source": "iosdeploy",
                        })
                if devices:
                    return devices
            except (asyncio.TimeoutError, FileNotFoundError, OSError) as e:
                logger.debug("iosdeploy detection failed: %s", e)

        # Method 2: try idevice_id (libimobiledevice)
        idevice_id_path = shutil.which("idevice_id")
        if idevice_id_path:
            try:
                proc = await asyncio.create_subprocess_exec(
                    idevice_id_path, "-l",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
                output = stdout.decode("utf-8", errors="replace")
                for line in output.splitlines():
                    udid = line.strip()
                    if udid:
                        # Get the device name
                        name = await self._get_ios_device_name(idevice_id_path, udid)
                        devices.append({
                            "udid": udid,
                            "name": name or udid,
                            "platform": platform,
                            "source": "libimobiledevice",
                        })
                if devices:
                    return devices
            except (asyncio.TimeoutError, FileNotFoundError, OSError) as e:
                logger.debug("idevice_id detection failed: %s", e)

        # Method 3: try MSBuild's deploy-target probing
        # MSBuild detects connected iOS devices automatically during a build
        logger.info("No iOS device enumeration tool found (iosdeploy/libimobiledevice)")
        logger.info("Hint: make sure the device is connected over USB and trusts this computer")
        logger.info("Hint: you can install libimobiledevice: https://libimobiledevice.org/")
        return devices

    async def _get_ios_device_name(self, idevice_id_path: str, udid: str) -> Optional[str]:
        """Get the iOS device name."""
        idevice_name = shutil.which("ideviceinfo")
        if not idevice_name:
            return None
        try:
            proc = await asyncio.create_subprocess_exec(
                idevice_name, "-u", udid, "-k", "DeviceName",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            output = stdout.decode("utf-8", errors="replace").strip()
            # Output format: "DeviceName: <name>"
            if ": " in output:
                return output.split(": ", 1)[1].strip()
        except Exception:
            pass
        return None

    async def _list_android_devices(self) -> List[Dict[str, Any]]:
        """Enumerate Android devices (via ADB)."""
        devices: List[Dict[str, Any]] = []

        adb_path = self._find_adb()
        if not adb_path:
            logger.info("ADB tool not found")
            logger.info("Hint: install the Android SDK Platform Tools")
            logger.info("Hint: or set the ANDROID_HOME environment variable")
            return devices

        try:
            proc = await asyncio.create_subprocess_exec(
                adb_path, "devices", "-l",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
            output = stdout.decode("utf-8", errors="replace")

            for line in output.splitlines():
                # Skip the header line and blank lines
                if line.startswith("List of") or not line.strip():
                    continue
                # Parse the ADB device output format: "<serial>   device [usb:<path>] [model:<name>]"
                parts = line.split()
                if len(parts) >= 2 and parts[1] == "device":
                    serial = parts[0]
                    # Extract the model
                    model = ""
                    for part in parts[2:]:
                        if part.startswith("model:"):
                            model = part.split(":", 1)[1]
                            break
                    devices.append({
                        "serial": serial,
                        "name": model or serial,
                        "platform": "android",
                        "status": "device",
                        "source": "adb",
                    })
        except asyncio.TimeoutError:
            logger.warning("Timed out while listing ADB devices")
        except FileNotFoundError:
            logger.warning("ADB tool execution failed")

        return devices

    def _list_windows_devices(self, platform: str) -> List[Dict[str, Any]]:
        """List local Windows devices (always returns this machine)."""
        import socket
        hostname = socket.gethostname()
        return [{
            "serial": "local",
            "name": hostname,
            "platform": platform,
            "status": "local",
            "source": "local",
        }]

    # ─── Deployment ────────────────────────────────────────────────

    async def deploy(self, project_path: str, target_platform: str,
                     device_id: Optional[str] = None,
                     build_configuration: str = "Debug",
                     extra_args: Optional[List[str]] = None,
                     timeout: int = 600) -> Dict[str, Any]:
        """Deploy a compiled application to a device

        Args:
            project_path: Project file path (.dproj/.dpr)
            target_platform: Target platform (iosdevice64/android64/win32, etc.)
            device_id: Target device ID (an iOS UDID or an Android serial);
                       deploys to the default device when omitted
            build_configuration: Build configuration (Debug/Release)
            extra_args: Extra arguments passed to MSBuild
            timeout: Timeout in seconds

        Returns:
            Deployment result dictionary
        """
        project_path_obj = Path(project_path)
        if not project_path_obj.exists():
            return {"status": "failed", "message": f"Project file not found: {project_path}"}

        # Resolve the .dproj path
        dproj_path = project_path
        if project_path_obj.suffix.lower() == ".dpr":
            dproj_path = str(project_path_obj.with_suffix(".dproj"))

        if not Path(dproj_path).exists():
            return {"status": "failed", "message": f".dproj file not found: {dproj_path}"}

        target_platform = target_platform.lower()

        # Choose the deployment route by platform
        if target_platform.startswith("ios"):
            return await self._deploy_ios(
                dproj_path, target_platform, device_id,
                build_configuration, extra_args, timeout,
            )
        elif target_platform.startswith("android"):
            return await self._deploy_android(
                dproj_path, target_platform, device_id,
                build_configuration, extra_args, timeout,
            )
        elif target_platform in ("win32", "win64"):
            return await self._deploy_windows(
                dproj_path, target_platform,
                build_configuration, extra_args, timeout,
            )
        else:
            return {
                "status": "failed",
                "message": f"Unsupported deployment platform: {target_platform}. "
                           f"Supported platforms: iosdevice64, android64, win32, win64",
            }

    async def _deploy_ios(self, dproj_path: str, platform: str,
                          device_id: Optional[str], build_configuration: str,
                          extra_args: Optional[List[str]], timeout: int) -> Dict[str, Any]:
        """Deploy to an iOS device

        Deploys through MSBuild's Deploy target.
        Requires PAServer (Platform Assistant Server) running on a Mac.
        """
        # Locate MSBuild
        msbuild_path = self._find_msbuild(dproj_path)
        if not msbuild_path:
            return {
                "status": "failed",
                "message": "MSBuild not found. iOS deployment requires MSBuild.",
            }

        # Build the MSBuild argument list
        msbuild_args = [
            msbuild_path,
            dproj_path,
            "/t:Deploy",
            f"/p:Platform={self._msbuild_platform(platform)}",
            f"/p:Config={build_configuration}",
        ]

        # Add the device ID
        if device_id:
            msbuild_args.append(f"/p:DevId={device_id}")

        # Add the PAServer password (if any)
        paserver_password = os.environ.get("PASERVER_PASSWORD", "")
        if paserver_password:
            msbuild_args.append(f"/p:DevicePassword={paserver_password}")

        # Add the extra arguments
        if extra_args:
            msbuild_args.extend(extra_args)

        logger.info("iOS deploy command: %s", " ".join(msbuild_args))

        try:
            proc = await asyncio.create_subprocess_exec(
                *msbuild_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )

            stdout_text = stdout.decode("utf-8", errors="replace")
            stderr_text = stderr.decode("utf-8", errors="replace")
            return_code = proc.returncode

            if return_code == 0:
                return {
                    "status": "ok",
                    "message": "iOS deployment succeeded",
                    "platform": platform,
                    "device_id": device_id,
                    "log": stdout_text[-2000:] if len(stdout_text) > 2000 else stdout_text,
                }
            else:
                return {
                    "status": "failed",
                    "message": f"iOS deployment failed (exit code: {return_code})",
                    "platform": platform,
                    "device_id": device_id,
                    "log": stdout_text[-2000:] if len(stdout_text) > 2000 else stdout_text,
                    "error": stderr_text[-1000:] if stderr_text else "",
                }
        except asyncio.TimeoutError:
            return {
                "status": "failed",
                "message": f"iOS deployment timed out ({timeout}s)",
                "platform": platform,
            }
        except Exception as e:
            return {
                "status": "failed",
                "message": f"iOS deployment error: {str(e)}",
                "platform": platform,
            }

    async def _deploy_android(self, dproj_path: str, platform: str,
                              device_id: Optional[str], build_configuration: str,
                              extra_args: Optional[List[str]], timeout: int) -> Dict[str, Any]:
        """Deploy to an Android device

        Deploys through MSBuild's Deploy target.
        Requires the Android SDK and ADB.
        """
        msbuild_path = self._find_msbuild(dproj_path)
        if not msbuild_path:
            return {
                "status": "failed",
                "message": "MSBuild not found. Android deployment requires MSBuild.",
            }

        # Build the MSBuild argument list
        msbuild_args = [
            msbuild_path,
            dproj_path,
            "/t:Deploy",
            f"/p:Platform={self._msbuild_platform(platform)}",
            f"/p:Config={build_configuration}",
        ]

        # Add the device ID
        if device_id:
            msbuild_args.append(f"/p:DeviceId={device_id}")

        # Add the extra arguments
        if extra_args:
            msbuild_args.extend(extra_args)

        logger.info("Android deploy command: %s", " ".join(msbuild_args))

        try:
            proc = await asyncio.create_subprocess_exec(
                *msbuild_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )

            stdout_text = stdout.decode("utf-8", errors="replace")
            stderr_text = stderr.decode("utf-8", errors="replace")
            return_code = proc.returncode

            if return_code == 0:
                return {
                    "status": "ok",
                    "message": "Android deployment succeeded",
                    "platform": platform,
                    "device_id": device_id,
                    "log": stdout_text[-2000:] if len(stdout_text) > 2000 else stdout_text,
                }
            else:
                return {
                    "status": "failed",
                    "message": f"Android deployment failed (exit code: {return_code})",
                    "platform": platform,
                    "device_id": device_id,
                    "log": stdout_text[-2000:] if len(stdout_text) > 2000 else stdout_text,
                    "error": stderr_text[-1000:] if stderr_text else "",
                }
        except asyncio.TimeoutError:
            return {
                "status": "failed",
                "message": f"Android deployment timed out ({timeout}s)",
                "platform": platform,
            }
        except Exception as e:
            return {
                "status": "failed",
                "message": f"Android deployment error: {str(e)}",
                "platform": platform,
            }

    async def _deploy_windows(self, dproj_path: str, platform: str,
                              build_configuration: str,
                              extra_args: Optional[List[str]], timeout: int) -> Dict[str, Any]:
        """Local Windows deployment

        A Windows deployment is essentially the built files copied to the target directory.
        """
        # On Windows, "deploy" mainly means ensuring the build output is in the right place
        # The compile action can be called, and it returns the output path
        return {
            "status": "ok",
            "message": "Local Windows deployment: the build output is already local",
            "platform": platform,
            "hint": "Windows needs no remote deployment; run the build directly after compiling",
            "action_required": "Use action='compile' to build the project",
        }

    # ─── Tool lookup ────────────────────────────────────────────────

    def _find_adb(self) -> Optional[str]:
        """Locate the ADB tool."""
        # 1. Check ANDROID_HOME
        android_home = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
        if android_home:
            adb_path = Path(android_home) / "platform-tools" / "adb.exe"
            if adb_path.exists():
                return str(adb_path)

        # 2. Check PATH
        adb_in_path = shutil.which("adb")
        if adb_in_path:
            return adb_in_path

        # 3. Common install paths
        common_paths = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Android" / "Sdk" / "platform-tools" / "adb.exe",
            Path(os.environ.get("PROGRAMFILES", "")) / "Android" / "sdk" / "platform-tools" / "adb.exe",
        ]
        for p in common_paths:
            if p.exists():
                return str(p)

        return None

    def _find_iosdeploy(self) -> Optional[str]:
        """Locate the iosdeploy tool."""
        return shutil.which("iosdeploy")

    def _resolve_project_delphi_version(
        self,
        project_path: Optional[str],
        settings: Optional[ProjectSettings] = None,
    ) -> Optional[str]:
        """Resolve the Delphi registry version the project uses (to pick MSBuild for deployment)."""
        if not project_path:
            return None

        if settings is None:
            settings = load_project_settings(project_path)

        config_manager = None
        try:
            from .compile_project import _compiler_service
            if _compiler_service:
                config_manager = getattr(_compiler_service, "config_manager", None)
        except ImportError:
            config_manager = None

        # Same priority as the compile service: compiler_version > delphi_version
        if settings and settings.compiler_version:
            resolved = resolve_registry_version(
                settings.compiler_version,
                None,
                config_manager,
            )
            if resolved:
                return resolved
            version_hint = normalize_version_key(settings.compiler_version)
            if version_hint:
                return version_hint
            logger.warning(
                "Cannot resolve the project's configured compiler %r; falling back to delphi_version/auto-detection",
                settings.compiler_version,
            )

        if settings and settings.delphi_version:
            return settings.delphi_version

        dproj = project_path
        if Path(dproj).suffix.lower() in (".dpr", ".dpk"):
            dproj = str(Path(dproj).with_suffix(".dproj"))
        if not Path(dproj).exists():
            return None
        parser = DprojParser(dproj)
        if not parser.parse():
            return None
        project_version = parser.get_project_version()
        if not project_version:
            return None
        return project_version_to_registry_version(project_version)

    def _find_msbuild(self, project_path: Optional[str] = None) -> Optional[str]:
        """Locate the MSBuild tool (resolving the version from the project config, so multi-version machines do not cross-use)"""
        # Reuse compiler_service's resolution logic: project config > version mapping > auto-detection;
        # different projects may use different MSBuild versions.
        try:
            from .compile_project import _compiler_service
            if _compiler_service:
                settings = (
                    load_project_settings(project_path) if project_path else None
                )
                if settings and settings.error:
                    logger.error(settings.error)
                    return None
                version = self._resolve_project_delphi_version(
                    project_path, settings
                )
                if settings and settings.compiler_version and not version:
                    logger.error(
                        "The project's configured compiler_version=%r cannot be resolved; "
                        "deployment stopped (no other Delphi version will be used)",
                        settings.compiler_version,
                    )
                    return None
                resolved, source, explicit_error = (
                    _compiler_service._resolve_msbuild_path(
                        version,
                        settings,
                    )
                )
                if resolved:
                    logger.info("Deployment uses MSBuild (%s): %s", source, resolved)
                    return resolved
                if explicit_error:
                    logger.error(
                        "The configured MSBuild is invalid; deployment stopped (no fallback to another version): %s",
                        source,
                    )
                    return None
                logger.warning("Could not resolve MSBuild: %s", source)
        except ImportError:
            pass
        except Exception:
            logger.warning("Failed to resolve MSBuild through the compile service", exc_info=True)

        # Fallback: look for vswhere
        program_files_x86 = os.environ.get("ProgramFiles(x86)", "")
        vswhere = Path(program_files_x86) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
        if vswhere.exists():
            try:
                result = subprocess.run(
                    [
                        str(vswhere),
                        "-latest", "-products", "*",
                        "-requires", "Microsoft.Component.MSBuild",
                        "-find", r"MSBuild\**\Bin\MSBuild.exe",
                    ],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode == 0:
                    paths = result.stdout.strip().splitlines()
                    if paths:
                        return paths[0]
            except Exception:
                pass

        return None

    def _resolve_platform(self, platform: Optional[str],
                          project_path: Optional[str]) -> str:
        """Resolve the target platform."""
        if platform:
            return platform.lower()

        # Try to infer it from the project
        if project_path:
            try:
                from ..utils.dproj_parser import DprojParser
                dproj_path = project_path
                if project_path.lower().endswith(".dpr"):
                    dproj_path = str(Path(project_path).with_suffix(".dproj"))
                parser = DprojParser(dproj_path)
                if parser.parse():
                    target = parser.get_target_platform()
                    if target:
                        return target.lower()
            except Exception:
                pass

        return "win32"

    def _msbuild_platform(self, platform: str) -> str:
        """Convert a platform name to MSBuild form."""
        platform_map = {
            "win32": "Win32",
            "win64": "Win64",
            "iosdevice64": "iOSDevice64",
            "iossimulator": "iOSSimulator",
            "android64": "Android64",
            "androidarm64": "Android64",
            "osx64": "OSX64",
            "osxarm64": "OSXARM64",
            "linux64": "Linux64",
        }
        return platform_map.get(platform, platform.capitalize())


# Global instance
_deploy_service: Optional[DeployService] = None


def get_deploy_service() -> DeployService:
    """Get the deployment service singleton."""
    global _deploy_service
    if _deploy_service is None:
        _deploy_service = DeployService()
    return _deploy_service


# ─── MCP tool entry point ───────────────────────────────────────


async def deploy_project(**kwargs) -> Dict[str, Any]:
    """Deploy a Delphi project to a device

    Args:
        action: Operation type (devices/deploy)
        project_path: Project file path (.dproj/.dpr)
        target_platform: Target platform
        device_id: Target device ID
        build_configuration: Build configuration
        extra_args: Extra arguments
        timeout: Timeout in seconds

    Returns:
        The operation result
    """
    action = kwargs.get("action", "devices")
    service = get_deploy_service()

    try:
        if action == "devices":
            return await service.list_devices(
                platform=kwargs.get("target_platform"),
                project_path=kwargs.get("project_path"),
            )
        elif action == "deploy":
            project_path = kwargs.get("project_path", "")
            if not project_path:
                return {"status": "failed", "message": "Missing required parameter: project_path"}

            target_platform = kwargs.get("target_platform", "")
            if not target_platform:
                return {"status": "failed", "message": "Missing required parameter: target_platform"}

            return await service.deploy(
                project_path=project_path,
                target_platform=target_platform,
                device_id=kwargs.get("device_id"),
                build_configuration=kwargs.get("build_configuration", "Debug"),
                extra_args=kwargs.get("extra_args"),
                timeout=kwargs.get("timeout", 600),
            )
        else:
            return {
                "status": "failed",
                "message": f"Unknown action: {action}. Available actions: devices, deploy",
            }
    except Exception as e:
        logger.exception("Deploy operation failed")
        return {"status": "failed", "message": str(e)}
