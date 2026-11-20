"""
Automatic update module — version detection / GitHub+PyPI Release query / git pull update

Copyright (C) Jilin Province Zuoyou Software Development Co., Ltd.
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin

Features:
  - get_current_version()       read current version (metadata→pyproject.toml→env var)
  - fetch_latest_release()      query latest GitHub Release (with mirror fallback)
  - fetch_pypi_version()        query latest PyPI version (pip installations only, no auth)
  - compare_versions(a, b)      compare YYYY.MM.DD version numbers
  - check_for_update()          smart version check (pip→PyPI, git→GitHub)
  - check_for_update_retry()    ⭐ asynchronous automatic retry version check (background, cancellable)
  - is_git_installation()       determine whether this is a git source installation
  - is_pip_installation()       determine whether this is a pip installation
  - git_pull_update()           execute git pull update
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
import time as _time
import urllib.error
import urllib.request
from importlib.metadata import version as _get_installed_version, PackageNotFoundError
from pathlib import Path
from typing import Optional

from ..constants import (
    TIMEOUT_SUBPROCESS_SHORT,
    TIMEOUT_UPDATER_GIT_PULL,
)

logger = logging.getLogger(__name__)

# ============================================================
# Repository information
# ============================================================
RELEASE_REPO = "chinawsb/daofy"
RELEASE_API = f"https://api.github.com/repos/{RELEASE_REPO}/releases/latest"

# GitHub domestic mirror proxies
GITHUB_MIRRORS: list[str] = [
    "",  # Original source (tried first)
    "https://ghproxy.com",  # ghproxy new domain
    "https://ghproxy.net",  # ghproxy old domain
]

# PyPI package information
PYPI_PACKAGE = "daofy-for-delphi"
PYPI_JSON_URL = f"https://pypi.org/pypi/{PYPI_PACKAGE}/json"

# PyPI domestic mirrors
PYPI_MIRRORS: list[str] = [
    "",  # PyPI official
    "https://pypi.tuna.tsinghua.edu.cn",  # Tsinghua mirror
    "https://mirrors.aliyun.com/pypi",  # Aliyun mirror
]

# Single request parameters
MAX_RETRY = 3
RETRY_DELAY = 2  # seconds
REQUEST_TIMEOUT = 15  # seconds

# Background automatic retry parameters (check_for_update_retry)
RETRY_INTERVAL = 300     # interval between retries (5 minutes)
MAX_RETRIES = 12          # max retries (≈1 hour)
ETA_MINUTES = (RETRY_INTERVAL * MAX_RETRIES) // 60  # about 60 minutes


# ============================================================
# Version utilities
# ============================================================

def _get_project_root() -> Path:
    """Get the project root directory (where pyproject.toml is located)."""
    # Current file is src/utils/updater.py, go up two levels
    return Path(__file__).resolve().parent.parent.parent


def get_current_version() -> str:
    """Read the current version number.

    Priority:
    1. DAOFY_VERSION environment variable
    2. importlib.metadata (pip installation scenario)
    3. pyproject.toml file (source-run fallback)

    Returns:
        Version string, e.g. "2026.07.18.1"; returns "0.0.0" on read failure.
    """
    # 1. Environment variable
    env_ver = os.environ.get("DAOFY_VERSION")
    if env_ver:
        return env_ver

    # 2. importlib.metadata — standard method after pip installation
    try:
        return _get_installed_version(PYPI_PACKAGE)
    except PackageNotFoundError:
        pass

    # 3. Read pyproject.toml (source-run fallback)
    pyproject_path = _get_project_root() / "pyproject.toml"
    try:
        with open(pyproject_path, "r", encoding="utf-8") as f:
            for line in f:
                line_stripped = line.strip()
                if line_stripped.startswith("version ="):
                    parts = line_stripped.split("=", 1)
                    if len(parts) == 2:
                        ver = parts[1].strip().strip('"').strip("'")
                        if ver:
                            return ver
        logger.debug("version field not found in pyproject.toml")
    except Exception as e:
        logger.warning("Failed to read version number: %s", e)

    return os.environ.get("DAOFY_VERSION", "0.0.0")


def compare_versions(a: str, b: str) -> int:
    """Compare two YYYY.MM.DD version numbers.

    Args:
        a: version number A
        b: version number B

    Returns:
        1  if a > b
        0  if a == b
        -1 if a < b
    """
    try:
        parts_a = [int(x) for x in a.split(".")]
        parts_b = [int(x) for x in b.split(".")]
        # Pad to the same length
        max_len = max(len(parts_a), len(parts_b))
        parts_a += [0] * (max_len - len(parts_a))
        parts_b += [0] * (max_len - len(parts_b))
        for pa, pb in zip(parts_a, parts_b):
            if pa > pb:
                return 1
            if pa < pb:
                return -1
        return 0
    except (ValueError, AttributeError):
        logger.warning(f"Invalid version format: a={a!r}, b={b!r}, falling back to string comparison")
        # Fallback: string comparison
        if a > b:
            return 1
        if a < b:
            return -1
        return 0


# ============================================================
# GitHub API query (reuses install_mcp.py mirror fallback pattern)
# ============================================================

def _build_mirror_urls(url: str) -> list[str]:
    """Expand a GitHub URL into a list of multi-mirror URLs (original source + domestic proxies)."""
    urls: list[str] = []
    for m in GITHUB_MIRRORS:
        if not m:
            urls.append(url)
        else:
            urls.append(f"{m}/{url}")
    # Deduplicate (preserve order)
    seen: set[str] = set()
    result: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            result.append(u)
    return result


def _retry_urlopen(
    url: str,
    headers: Optional[dict] = None,
    timeout: int = REQUEST_TIMEOUT,
    max_retry: int = MAX_RETRY,
) -> bytes:
    """urllib request with retries."""
    last_err: Optional[Exception] = None
    for attempt in range(1, max_retry + 1):
        try:
            req = urllib.request.Request(url, headers=headers or {})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
            last_err = e
            if attempt < max_retry:
                wait = RETRY_DELAY * min(attempt, 5)
                logger.debug(f"Request failed (attempt {attempt}): {e}, retrying in {wait}s...")
                import time
                time.sleep(wait)
    raise last_err  # type: ignore[misc]


# ============================================================
# Public API
# ============================================================

def fetch_latest_release(timeout: int = REQUEST_TIMEOUT) -> Optional[dict]:
    """Query the latest GitHub Release information.

    Args:
        timeout: per-request timeout in seconds

    Returns:
        dict containing tag_name, html_url, body, etc.; None on failure.
    """
    api_urls = _build_mirror_urls(RELEASE_API)
    last_err: Optional[Exception] = None
    for api_url in api_urls:
        try:
            data = json.loads(
                _retry_urlopen(
                    api_url,
                    headers={"User-Agent": "daofy-updater"},
                    timeout=timeout,
                ).decode("utf-8")
            )
            return data
        except urllib.error.HTTPError as e:
            last_err = e
            # Classify HTTP errors
            if e.code == 403:
                logger.warning("GitHub API access restricted (403): %s — may be a network issue or rate limit", api_url)
            elif e.code == 404:
                logger.warning("GitHub Release does not exist (404): %s", api_url)
            else:
                logger.debug("Failed to get Release info from mirror: %s — HTTP %d", api_url, e.code)
            continue
        except Exception as e:
            last_err = e
            logger.debug("Failed to get Release info from mirror: %s — %s", api_url, _categorize_request_error(e))
            continue
    if last_err:
        error_hint = _categorize_request_error(last_err)
        logger.warning("Failed to get Release info from all mirrors: %s", error_hint)
    return None


def get_latest_version() -> Optional[str]:
    """Query the latest GitHub Release version number.

    Returns:
        Version string (e.g. "2026.06.15"), or None on failure.
    """
    data = fetch_latest_release()
    if data:
        return data.get("tag_name")
    return None


def _categorize_request_error(err: Exception) -> str:
    """Classify request errors into user-friendly English hints.

    Args:
        err: exception object

    Returns:
        User-friendly error description
    """
    err_str = str(err).lower()

    # Rate limit (GitHub 403)
    if "403" in err_str or "rate limit" in err_str or "abuse" in err_str:
        return "GitHub API access restricted (may be a network issue or too many requests)"

    # Network connection problems
    if any(kw in err_str for kw in (
        "timed out", "timeout", "connection refused",
        "connection reset", "connection abort",
    )):
        return "Network connection timed out or refused; please check your network connection"

    # DNS resolution failure
    if any(kw in err_str for kw in (
        "resolve", "name or service not known",
        "getaddrinfo", "nodename nor servname",
    )):
        return "Unable to resolve host address; please check DNS or network connection"

    # Blocked/proxy failure
    if any(kw in err_str for kw in (
        "ssl", "certificate", "eof", "connection reset by peer",
    )):
        return "Network connection error (possibly proxy or firewall issue)"

    # Default
    return f"Request failed: {err}"


def fetch_pypi_version(timeout: int = REQUEST_TIMEOUT) -> Optional[str]:
    """Query the latest PyPI version number (no auth required, accessible in China).

    Args:
        timeout: per-request timeout in seconds

    Returns:
        Version string (e.g. "2026.07.17"), or None on failure.
    """
    for mirror in PYPI_MIRRORS:
        try:
            if mirror:
                url = f"{mirror}/pypi/{PYPI_PACKAGE}/json"
            else:
                url = PYPI_JSON_URL
            data = json.loads(
                _retry_urlopen(
                    url,
                    headers={"User-Agent": "daofy-updater"},
                    timeout=timeout,
                ).decode("utf-8")
            )
            version = data.get("info", {}).get("version")
            if version:
                logger.debug("Got version from PyPI: %s (mirror: %s)", version, mirror or "official")
                return version
        except Exception as e:
            logger.debug("Failed to get version from PyPI: %s — %s", url, e)
            continue
    logger.warning("Failed to get version from all PyPI mirrors")
    return None


def check_for_update() -> Optional[dict]:
    """Check whether a new version is available.

    Automatically selects the version source based on installation type:
    - pip installation → prefer PyPI (no auth required, accessible in China)
    - git installation → query GitHub Release

    Returns:
        dict containing current, latest, update_available, release_url, source;
        None if query fails.
    """
    current = get_current_version()
    latest = None
    source = "github"  # default source

    # pip installation: prefer PyPI (no auth, no rate limit)
    if is_pip_installation():
        latest = fetch_pypi_version()
        if latest:
            source = "pypi"
            logger.debug("pip installation: got version %s from PyPI", latest)
        else:
            # PyPI failed, falling back to GitHub
            logger.info("PyPI query failed, falling back to GitHub")
            latest = get_latest_version()
    else:
        # git installation or unknown: query GitHub
        latest = get_latest_version()

    if latest is None:
        return None

    # Strip leading v prefix from version, if present
    latest_clean = latest.lstrip("vV")

    available = compare_versions(latest_clean, current) > 0

    result = {
        "current": current,
        "latest": latest_clean,
        "update_available": available,
        "source": source,
        "release_url": f"https://github.com/{RELEASE_REPO}/releases/tag/{latest}",
    }
    return result


# ============================================================
# Installation type detection
# ============================================================

# ============================================================
# Asynchronous automatic retry version check (similar to code_hosting git_push_retry pattern)
# ============================================================

# Global cache — most recent successful result
_update_cache: Optional[dict] = None
_update_cache_time: float = 0.0
_UPDATE_CACHE_TTL = 3600  # 1-hour cache


def _get_cached_result() -> Optional[dict]:
    """Get the cached version check result (valid within TTL)."""
    if _update_cache is not None:
        elapsed = _time.monotonic() - _update_cache_time
        if elapsed < _UPDATE_CACHE_TTL:
            return _update_cache
    return None


def get_cached_update_result() -> Optional[dict]:
    """Public version — get the cached version check result.

    Returns:
        Cached version check result dict, or None (no cache/expired).
    """
    return _get_cached_result()


def _set_cached_result(result: Optional[dict]) -> None:
    """Set the version check cache."""
    global _update_cache, _update_cache_time
    _update_cache = result
    _update_cache_time = _time.monotonic()


def check_for_update_retry(**kwargs) -> dict:
    """Asynchronous automatic retry version check — runs in background thread, supports progress callback and cancellation.

    Follows the code_hosting git_push_retry pattern.
    Submitted to a background thread via AsyncTaskManager, automatically retries until success or max attempts.

    Args:
        **kwargs: callback parameters injected by AsyncTaskManager:
            _progress_callback: progress callback function
            _cancellation_check: cancellation check function
            _task_id: task ID

    Returns:
        dict: version check result (same format as check_for_update); returns error dict if all retries fail.
    """
    progress_cb = kwargs.get('_progress_callback')
    cancel_check = kwargs.get('_cancellation_check')

    last_error: Optional[str] = None

    for attempt in range(1, MAX_RETRIES + 1):
        # Check cancellation
        if cancel_check:
            try:
                cancel_check()
            except Exception:
                return {"error": "Version check task cancelled", "status": "cancelled"}

        # First check whether the cache is valid
        cached = _get_cached_result()
        if cached is not None:
            if progress_cb:
                progress_cb(100, f"Using cached version info ({cached.get('current', '?')})")
            logger.info("Version check hit cache")
            return cached

        # Report progress
        pct = (attempt / MAX_RETRIES) * 100
        if progress_cb:
            if attempt == 1:
                progress_cb(pct, "Checking for version updates...")
            else:
                eta_remaining = ((MAX_RETRIES - attempt + 1) * RETRY_INTERVAL) // 60
                progress_cb(
                    pct,
                    f"Version check attempt {attempt}/{MAX_RETRIES}"
                    f"{', waiting to retry after failure' if last_error else ''}"
                    f"{', estimated ~' + str(eta_remaining) + 'min remaining' if eta_remaining > 0 else ''}"
                )

        # Perform version check
        try:
            result = check_for_update()
        except Exception as e:
            result = None
            last_error = str(e)
            logger.warning(f"Version check exception (attempt {attempt}): {e}")

        if result is not None:
            # Success: cache result and return
            _set_cached_result(result)
            if progress_cb:
                if result.get("update_available"):
                    progress_cb(100, f"New version v{result['latest']} found (current v{result['current']})")
                else:
                    progress_cb(100, f"Already up to date: v{result['current']}")
            logger.info(
                "Version check succeeded: %s (attempt %d)",
                "update available" if result.get("update_available") else "already up to date",
                attempt,
            )
            return result

        last_error = "Failed to obtain Release info from all mirrors"

        # Retries remain: wait and retry
        if attempt < MAX_RETRIES:
            wait = RETRY_INTERVAL
            logger.info(f"Version check failed (attempt {attempt}), automatically retrying in {wait}s...")
            if progress_cb:
                eta_total = (RETRY_INTERVAL * MAX_RETRIES) // 60
                progress_cb(
                    pct,
                    f"Attempt {attempt}/{MAX_RETRIES} failed, retrying in {wait}s"
                    f" | estimated max ~{eta_total}min"
                )
            _time.sleep(wait)

    # All retries failed
    error_msg = f"Version check failed ({MAX_RETRIES} retries, about {ETA_MINUTES} minutes): {last_error}"
    logger.error(error_msg)
    return {
        "error": error_msg,
        "status": "failed",
        "attempts": MAX_RETRIES,
    }


def is_git_installation() -> bool:
    """Detect whether this is a git source installation (has .git directory and git command)."""
    git_dir = _get_project_root() / ".git"
    if not git_dir.exists():
        return False
    # Check whether git command is available
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["where", "git"],
                capture_output=True, timeout=TIMEOUT_SUBPROCESS_SHORT, check=True,
            )
        else:
            subprocess.run(
                ["which", "git"],
                capture_output=True, timeout=TIMEOUT_SUBPROCESS_SHORT, check=True,
            )
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def is_pip_installation() -> bool:
    """Detect whether this is a pip installation (in site-packages)."""
    # If current file is under site-packages path, it is a pip installation
    module_path = Path(__file__).resolve()
    return "site-packages" in module_path.parts


# ============================================================
# git pull update (sync version — for background threads)
# ============================================================

def git_pull_update_sync() -> dict:
    """Synchronously execute git pull update (for AsyncTaskManager background thread).

    Returns:
        dict containing success, updated, message, output.
    """
    project_root = _get_project_root()
    try:
        logger.info("Executing git pull update (sync)...")
        proc_env = os.environ.copy()
        proc_env["GIT_TERMINAL_PROMPT"] = "0"
        result = subprocess.run(
            ["git", "pull"],
            cwd=str(project_root),
            capture_output=True,
            timeout=TIMEOUT_UPDATER_GIT_PULL,
            env=proc_env,
        )
        stdout_text = result.stdout.decode("utf-8", errors="replace").strip()
        stderr_text = result.stderr.decode("utf-8", errors="replace").strip()

        if result.returncode == 0:
            if "Already up to date" in stdout_text:
                return {
                    "success": True,
                    "updated": False,
                    "message": "Already up to date; no update needed.",
                    "output": stdout_text,
                }
            return {
                "success": True,
                "updated": True,
                "message": "Update succeeded! Please restart Daofy or AI Agent for the new version to take effect.",
                "output": stdout_text,
            }
        else:
            error_msg = stderr_text or stdout_text
            return {
                "success": False,
                "updated": False,
                "message": f"git pull failed: {error_msg}",
                "output": error_msg,
            }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "updated": False,
            "message": "git pull timed out (>60 seconds); please check your network connection and retry.",
            "output": "",
        }
    except FileNotFoundError:
        return {
            "success": False,
            "updated": False,
            "message": "git command not found; please install Git and retry.",
            "output": "",
        }
    except Exception as e:
        logger.error(f"git pull exception: {e}", exc_info=True)
        return {
            "success": False,
            "updated": False,
            "message": f"Update failed: {e}",
            "output": str(e),
        }


# ============================================================
# Background automatic retry git pull update (similar to code_hosting git_push_retry)
# ============================================================

# Update retry parameters
UPDATE_RETRY_INTERVAL = 60       # interval between retries (60 seconds)
UPDATE_MAX_RETRIES = 10           # max retries (≈10 minutes)


def _do_retry_update(**kwargs) -> dict:
    """Background automatic retry git pull update — supports progress callback and cancellation.

    Follows the code_hosting git_push_retry pattern.
    Submitted to a background thread via AsyncTaskManager, automatically retries until success or max attempts.

    Args:
        **kwargs: callback parameters injected by AsyncTaskManager:
            _progress_callback: progress callback function
            _cancellation_check: cancellation check function
            _task_id: task ID

    Returns:
        dict: git pull update result.
    """
    progress_cb = kwargs.get('_progress_callback')
    cancel_check = kwargs.get('_cancellation_check')

    last_error: Optional[str] = None

    for attempt in range(1, UPDATE_MAX_RETRIES + 1):
        # Check cancellation
        if cancel_check:
            try:
                cancel_check()
            except Exception:
                return {"error": "Update task cancelled", "status": "cancelled"}

        # Report progress
        pct = (attempt / UPDATE_MAX_RETRIES) * 100
        if progress_cb:
            if attempt == 1:
                progress_cb(pct, "Executing git pull update...")
            else:
                progress_cb(
                    pct,
                    f"git pull attempt {attempt}/{UPDATE_MAX_RETRIES}"
                    f"{', waiting to retry after failure' if last_error else ''}"
                )

        # Execute git pull
        try:
            result = git_pull_update_sync()
        except Exception as e:
            result = None
            last_error = str(e)
            logger.warning(f"git pull exception (attempt {attempt}): {e}")

        if result is not None and result.get("success"):
            if progress_cb:
                if result.get("updated"):
                    progress_cb(100, f"Update succeeded! Please restart Daofy for the new version to take effect.")
                else:
                    progress_cb(100, "Already up to date; no update needed.")
            logger.info("git pull update succeeded (attempt %d)", attempt)
            return result

        if result is not None:
            last_error = result.get("message", "Unknown error")

        # Retries remain: wait and retry
        if attempt < UPDATE_MAX_RETRIES:
            wait = UPDATE_RETRY_INTERVAL
            logger.info(f"git pull failed (attempt {attempt}), automatically retrying in {wait}s...")
            if progress_cb:
                eta_total = (UPDATE_RETRY_INTERVAL * UPDATE_MAX_RETRIES) // 60
                progress_cb(
                    pct,
                    f"Attempt {attempt}/{UPDATE_MAX_RETRIES} failed, retrying in {wait}s"
                    f" | estimated max ~{eta_total}min"
                )
            _time.sleep(wait)

    # All retries failed
    error_msg = f"git pull update failed ({UPDATE_MAX_RETRIES} retries): {last_error}"
    logger.error(error_msg)
    return {"success": False, "updated": False, "message": error_msg, "status": "failed"}


# ============================================================
# git pull update (async version — for direct await calls)
# ============================================================

async def git_pull_update() -> dict:
    """Execute git pull to update code.

    Returns:
        dict containing success, message, output.
    """
    project_root = _get_project_root()
    try:
        logger.info("Executing git pull update...")
        proc = await asyncio.create_subprocess_exec(
            "git", "pull",
            cwd=str(project_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=TIMEOUT_UPDATER_GIT_PULL,
        )

        stdout_text = stdout.decode("utf-8", errors="replace").strip()
        stderr_text = stderr.decode("utf-8", errors="replace").strip()

        if proc.returncode == 0:
            # Detect whether there was an actual update
            if "Already up to date" in stdout_text:
                return {
                    "success": True,
                    "updated": False,
                    "message": "Already up to date; no update needed.",
                    "output": stdout_text,
                }
            return {
                "success": True,
                "updated": True,
                "message": "Update succeeded! Please restart Daofy or AI Agent for the new version to take effect.",
                "output": stdout_text,
            }
        else:
            error_msg = stderr_text or stdout_text
            return {
                "success": False,
                "updated": False,
                "message": f"git pull failed: {error_msg}",
                "output": error_msg,
            }
    except asyncio.TimeoutError:
        return {
            "success": False,
            "updated": False,
            "message": "git pull timed out (>60 seconds); please check your network connection and retry.",
            "output": "",
        }
    except FileNotFoundError:
        return {
            "success": False,
            "updated": False,
            "message": "git command not found; please install Git and retry.",
            "output": "",
        }
    except Exception as e:
        logger.error(f"git pull exception: {e}", exc_info=True)
        return {
            "success": False,
            "updated": False,
            "message": f"Update failed: {e}",
            "output": str(e),
        }

