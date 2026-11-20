r"""
Delphi RTTI bridge service — manages RTTI capability discovery and invocation for Delphi applications.

Uses the existing automation_service named pipe communication,
converts RTTI discovery results from the Delphi side into an MCP-usable format.

Communication protocol:
  Request: {"reqId":"...", "cmd":"rtti_discover", "target":"TMainForm"}
  Response: {"reqId":"...", "status":"ok", "data":{...JSON...}}

Process registry discovery:
  When a Delphi application starts it writes %TEMP%\daofy-rtti-{PID}.json,
  MCP scans these files to automatically discover running applications.
"""

import glob
import json
import logging
import os
import time
from ctypes import wintypes
from typing import Optional

from src.constants import POLL_INTERVAL_AUTOMATION
from src.services.automation_service import (
    PIPE_NAME,
    _send_command,
    _send_command_to_pipe,
    _ensure_process,
    _process_pipe_name,
    _pool_lock,
    _process_pool,
    _WaitNP,
)

logger = logging.getLogger(__name__)


def _send_rtti_command(app_path: str, command: str) -> str:
    """Send RTTI traffic to the pooled process without breaking legacy mocks."""
    pipe_name = _process_pipe_name(app_path)
    if pipe_name == PIPE_NAME:
        return _send_command(command)
    return _send_command_to_pipe(pipe_name, command)

# ── Registry file discovery (%TEMP%\daofy-rtti-*.json) ──

REGISTRY_PATTERN = "daofy-rtti-*.json"

# ctypes for PID liveness check (OpenProcess)
_k32 = __import__("ctypes", fromlist=[""]).windll.kernel32
_OpenProcess = _k32.OpenProcess
_OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_OpenProcess.restype = wintypes.HANDLE
_CloseHandle = _k32.CloseHandle
_CloseHandle.argtypes = [wintypes.HANDLE]
_CloseHandle.restype = wintypes.BOOL
PROCESS_QUERY_INFORMATION = 0x0400
SYNCHRONIZE = 0x00100000


def _is_pid_alive(pid: int) -> bool:
    """Check whether the PID is alive (via OpenProcess)."""
    h = _OpenProcess(PROCESS_QUERY_INFORMATION | SYNCHRONIZE, False, pid)
    if h:
        _CloseHandle(h)
        return True
    return False


def scan_running_apps() -> list[dict]:
    """Scan registry files and return a list of running Delphi applications.

    Returns:
        list[dict]: [{pipe, pid, name, timestamp}, ...]
    """
    apps = []
    temp_dir = os.environ.get("TEMP", "")
    if not temp_dir:
        return apps

    pattern = os.path.join(temp_dir, REGISTRY_PATTERN)
    for filepath in glob.glob(pattern):
        try:
            with open(filepath, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        pid = data.get("pid")
        pipe = data.get("pipe")
        name = data.get("name", "Unknown")

        if not pid or not pipe:
            continue

        # Check whether the PID is alive
        if not _is_pid_alive(pid):
            continue

        # Verify the pipe is connectable
        try:
            if not _WaitNP(pipe, 1000):
                continue
        except Exception:
            continue

        apps.append({
            "pipe": pipe,
            "pid": pid,
            "name": name,
            "timestamp": data.get("timestamp", 0),
        })

    return apps


class RttiBridge:
    """Manage RTTI bridging for one or more Delphi applications.

    Each app_path corresponds to an independent Delphi process and named pipe.
    Use keep_alive to maintain a long-lived connection and avoid repeated starts.

    Pipe-based discover:
      Discover already-running applications via registry files without manually specifying app_path.
      Use scan_running_apps() → list_running_apps() to get the available application list.
    """

    def __init__(self):
        self._cache: dict[str, dict] = {}  # app_path → discovery result
        self._cache_time: dict[str, float] = {}
        self._cache_ttl: float = 300  # Cache for 5 minutes
        self._pipe_cache: dict[str, dict] = {}  # pipe_name → discovery result
        self._pipe_cache_time: dict[str, float] = {}
        self._app_pipe_map: dict[str, str] = {}  # app_name → pipe_name

    def _is_cache_valid(self, app_path: str) -> bool:
        if app_path not in self._cache:
            return False
        return (time.time() - self._cache_time.get(app_path, 0)) < self._cache_ttl

    def list_running_apps(self) -> dict:
        """List all applications discovered via registry files whose pipes are reachable.

        Returns:
            dict: {status, apps: [{pipe, pid, name, timestamp}, ...]}
        """
        apps = scan_running_apps()
        return {"status": "ok", "apps": apps}

    def discover_from_pipe(self, pipe_name: str, class_name: str = "",
                           force: bool = False) -> dict:
        r"""Discover RTTI capabilities directly by pipe name (does not depend on app_path, only on registry files).

        Args:
            pipe_name: Named pipe path, e.g. \\.\pipe\daofy_auto
            class_name: Qualified class name; empty string scans all
            force: Force cache refresh

        Returns:
            dict: {status, classes: [...], ...}
        """
        cache_key = pipe_name

        # Cache hit
        if not force and cache_key in self._pipe_cache:
            cached = self._pipe_cache[cache_key]
            age = time.time() - self._pipe_cache_time.get(cache_key, 0)
            if age < self._cache_ttl:
                if class_name:
                    for cls in cached.get("classes", []):
                        if cls.get("className") == class_name:
                            return {"status": "ok", "class": cls}
                    return {"status": "ok", "classes": cached.get("classes", [])}
                return {"status": "ok", **cached}

        # Send the rtti_discover command to the specified pipe
        req = {
            "reqId": f"disc_{int(time.time() * 1000)}",
            "cmd": "rtti_discover",
            "target": class_name,
        }
        resp_raw = _send_command_to_pipe(pipe_name, json.dumps(req, ensure_ascii=False))
        if resp_raw.startswith("ERR:"):
            return {"status": "error", "message": resp_raw}

        try:
            resp = json.loads(resp_raw)
        except (json.JSONDecodeError, TypeError) as e:
            return {"status": "error", "message": f"Invalid response: {resp_raw} ({e})"}

        if resp.get("status") != "ok":
            return {"status": "error", "message": resp.get("data", "Unknown error")}

        # Parse the data field
        data_raw = resp.get("data", "{}")
        if isinstance(data_raw, str):
            try:
                data = json.loads(data_raw)
            except (json.JSONDecodeError, TypeError):
                data = {"raw": data_raw}
        elif isinstance(data_raw, dict):
            data = data_raw
        else:
            data = {"raw": str(data_raw)}

        # Update cache
        if not class_name:
            self._pipe_cache[cache_key] = data
            self._pipe_cache_time[cache_key] = time.time()

        return {"status": "ok", **data}

    def auto_discover_all(self, force: bool = False) -> list[dict]:
        """Automatically discover the capabilities of all running Delphi applications.

        Args:
            force: Force cache refresh

        Returns:
            list[dict]: [{pipe, name, status, result}, ...]
        """
        apps = scan_running_apps()
        results = []
        for app in apps:
            pipe = app["pipe"]
            result = self.discover_from_pipe(pipe, "", force)
            results.append({
                "pipe": pipe,
                "name": app["name"],
                "pid": app["pid"],
                "status": result.get("status"),
            })
            if result.get("status") == "ok":
                self._app_pipe_map[app["name"]] = pipe
        return results

    def connect(self, app_path: str, wait_for_pipe: float = 10.0) -> dict:
        """Connect to a Delphi application (start the process or reuse an existing one).

        Args:
            app_path: Delphi exe path
            wait_for_pipe: Timeout in seconds to wait for the pipe to become ready

        Returns:
            dict: {status, reused, message}
        """
        is_new, err = _ensure_process(app_path, wait_for_pipe)
        if err:
            return {"status": "error", "message": err}
        return {"status": "ok", "reused": not is_new}

    def discover(self, app_path: str, class_name: str = "",
                 force: bool = False) -> dict:
        """Discover the RTTI capabilities of a Delphi application.

        Args:
            app_path: Delphi exe path
            class_name: Qualified class name; empty string scans all
            force: Force cache refresh

        Returns:
            dict: {status, classes: [...], ...}
        """
        # Cache hit
        if not force and self._is_cache_valid(app_path):
            cached = self._cache[app_path]
            if class_name:
                for cls in cached.get("classes", []):
                    if cls.get("className") == class_name:
                        return {"status": "ok", "class": cls}
                return {"status": "ok", "classes": cached.get("classes", [])}
            return {"status": "ok", **cached}

        # Ensure the process is running
        _, err = _ensure_process(app_path, 10.0)
        if err:
            return {"status": "error", "message": err}
        time.sleep(POLL_INTERVAL_AUTOMATION)  # Give the pipe a moment to become ready

        # Send the rtti_discover command
        req = {
            "reqId": f"disc_{int(time.time() * 1000)}",
            "cmd": "rtti_discover",
            "target": class_name,
        }
        resp_raw = _send_rtti_command(
            app_path,
            json.dumps(req, ensure_ascii=False),
        )
        if resp_raw.startswith("ERR:"):
            return {"status": "error", "message": resp_raw}

        try:
            resp = json.loads(resp_raw)
        except (json.JSONDecodeError, TypeError) as e:
            return {"status": "error", "message": f"Invalid response: {resp_raw} ({e})"}

        if resp.get("status") != "ok":
            return {"status": "error", "message": resp.get("data", "Unknown error")}

        # Parse the JSON in the data field (WriteResp on the Delphi side serializes data)
        data_raw = resp.get("data", "{}")
        if isinstance(data_raw, str):
            try:
                data = json.loads(data_raw)
            except (json.JSONDecodeError, TypeError):
                data = {"raw": data_raw}
        elif isinstance(data_raw, dict):
            data = data_raw
        else:
            data = {"raw": str(data_raw)}

        # Update cache
        if not class_name:
            self._cache[app_path] = data
            self._cache_time[app_path] = time.time()

        return {"status": "ok", **data}

    def call(self, app_path: str, class_name: str,
             method: str, params: Optional[dict] = None) -> dict:
        """Call an RTTI-exposed method of a Delphi application.

        Args:
            app_path: Delphi exe path
            class_name: Class name
            method: Method name
            params: Parameter dictionary

        Returns:
            dict: {status, data, response}
        """
        # Ensure the process is running
        _, err = _ensure_process(app_path, 10.0)
        if err:
            return {"status": "error", "message": err}

        req = {
            "reqId": f"call_{int(time.time() * 1000)}",
            "cmd": "rcall",
            "target": class_name,
            "method": method,
        }
        if params:
            req["params"] = json.dumps(params, ensure_ascii=False)

        resp_raw = _send_rtti_command(
            app_path,
            json.dumps(req, ensure_ascii=False),
        )
        if resp_raw.startswith("ERR:"):
            return {"status": "error", "message": resp_raw}

        try:
            resp = json.loads(resp_raw)
        except (json.JSONDecodeError, TypeError) as e:
            return {"status": "error", "message": f"Invalid response: {resp_raw} ({e})"}

        return {
            "status": resp.get("status", "error"),
            "data": resp.get("data", ""),
            "response": resp,
        }

    def clear_cache(self, app_path: Optional[str] = None):
        """Clear the cache."""
        if app_path:
            self._cache.pop(app_path, None)
            self._cache_time.pop(app_path, None)
        else:
            self._cache.clear()
            self._cache_time.clear()


# Global singleton
_rtti_bridge = RttiBridge()


def get_rtti_bridge() -> RttiBridge:
    return _rtti_bridge

