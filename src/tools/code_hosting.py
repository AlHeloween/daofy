"""Unified code hosting platform tool — compatible with Gitea / GitHub / GitLab / Gitee / GitCode + local Git operations

Dispatch operations via the action parameter; switch backends via the platform parameter.
Supported platforms:
  - gitea   : Self-hosted Gitea
  - github  : GitHub (github.com)
  - gitlab  : GitLab CE/EE (gitlab.com)
  - gitee   : Gitee (gitee.com) — API v5, GitHub-compatible style
  - gitcode : GitCode (gitcode.net) — GitLab-compatible style

API authentication methods:
  Platform  | Auth header                     | base_url example
  ----------|---------------------------------|------------------------
  gitea     | Authorization: token {token}     | https://your-gitea.com
  github    | Authorization: Bearer {token}    | https://api.github.com
  gitlab    | PRIVATE-TOKEN: {token}           | https://gitlab.com
  gitee     | Authorization: Bearer {token}    | https://gitee.com/api/v5
  gitcode   | PRIVATE-TOKEN: {token}           | https://gitcode.net

Git-related operations (no platform parameter required):
  - git_clone  Clone a remote repository (supports GitHub mirrors)
  - git_status View repository status
  - git_diff   View working tree/staging area differences
  - git_show   View commit or object contents
  - git_log    View commit history
  - git_add    Stage files
  - git_commit Create a commit
  - git_fetch  Fetch remote refs
  - git_pull   Pull and merge remote branch
  - git_branch / git_switch / git_merge / git_restore / git_unstage / git_stash / git_tag
  - git_push   Push to remote (depends on the user's own network/proxy/SSH configuration)

GitHub / Gitee access from mainland China:
  - Pull: git_clone supports the mirror parameter to specify a mirror source
  - Push: depends on the user's own configuration (SSH/HTTPS proxy/VPN); the tool makes no assumptions

Usage:
  code_hosting(platform="gitee", action="create_issue", ...)
  code_hosting(platform="gitcode", action="list_issues", ...)
  code_hosting(action="git_clone", repo_url="https://github.com/...", mirror="https://hub.fastgit.xyz")
  code_hosting(action="git_push", dir=".", branch="main")
"""

import base64
import logging
import os
import re
import subprocess
import time
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from ..constants import (
    MAX_RETRIES_GIT_PUSH,
    RETRY_INTERVAL_GIT_PUSH,
    TIMEOUT_GIT_FETCH_PULL,
    TIMEOUT_GIT_LOCAL_SLOW,
    TIMEOUT_GIT_PUSH,
    TIMEOUT_GIT_QUICK,
    TIMEOUT_GIT_REMOTE_SYNC,
    TIMEOUT_GIT_REV_PARSE,
    TIMEOUT_NETWORK_REQUEST,
)

# Reuse the project's existing async task manager
try:
    from ..services.knowledge_base.async_task_manager import get_task_manager
except ImportError:
    get_task_manager = None

logger = logging.getLogger(__name__)

# ============================================================
# Path safety — prevent directory traversal
# ============================================================

_ALLOWED_BASE = os.path.abspath(".")  # Default: current working directory


def _resolve_safe_dir(dir_path: str) -> str:
    """Resolve a user-supplied directory path and prevent path traversal attacks.

    Rules:
    - Relative paths are resolved based on _ALLOWED_BASE (current working directory) to prevent .. escape
    - Absolute paths may point to existing local repositories/directories, but are not created automatically
    - Non-existent relative paths are created automatically, facilitating operations such as git_clone
    - If safety cannot be determined, raise a clear error to avoid falling back to the current repository and causing accidental operations

    Args:
        dir_path: User-supplied directory path

    Returns:
        Safe absolute path
    """
    if not dir_path:
        return _ALLOWED_BASE

    if '\0' in dir_path:
        raise ValueError("dir parameter contains invalid characters")

    # Absolute path: allow existing local repositories/directories, but do not silently create arbitrary system paths
    if os.path.isabs(dir_path):
        resolved = os.path.normpath(dir_path)
        if not os.path.exists(resolved):
            raise ValueError(f"dir absolute path does not exist: {resolved}")
        if not os.path.isdir(resolved):
            raise ValueError(f"dir is not a directory: {resolved}")
        return resolved

    # Relative path: resolve based on _ALLOWED_BASE, prevent .. escape
    resolved = os.path.abspath(os.path.join(_ALLOWED_BASE, dir_path))
    resolved = os.path.normpath(resolved)
    resolved_lower = resolved.lower()
    allowed_lower = os.path.normpath(_ALLOWED_BASE).lower()

    if not resolved_lower.startswith(allowed_lower + os.sep) and resolved_lower != allowed_lower:
        logger.warning("Path traversal blocked: %s -> %s (base: %s)", dir_path, resolved, _ALLOWED_BASE)
        raise ValueError("dir parameter cannot escape the current working directory")

    if not os.path.exists(resolved):
        try:
            os.makedirs(resolved, exist_ok=True)
        except OSError as exc:
            raise ValueError(f"Unable to create dir directory: {resolved}") from exc
    if not os.path.isdir(resolved):
        raise ValueError(f"dir is not a directory: {resolved}")

    return resolved


# ============================================================
# Platform API path templates
# ============================================================

_API_PATHS = {
    "gitea": {
        "create_token": "/api/v1/users/{username}/tokens",
        "list_labels":  "/api/v1/repos/{owner}/{repo}/labels",
        "create_label": "/api/v1/repos/{owner}/{repo}/labels",
        "create_issue": "/api/v1/repos/{owner}/{repo}/issues",
        "edit_issue":   "/api/v1/repos/{owner}/{repo}/issues/{index}",
        "add_comment":  "/api/v1/repos/{owner}/{repo}/issues/{index}/comments",
        "list_issues":  "/api/v1/repos/{owner}/{repo}/issues",
        "list_pulls":   "/api/v1/repos/{owner}/{repo}/pulls",
        "create_pull":  "/api/v1/repos/{owner}/{repo}/pulls",
        "get_pull":     "/api/v1/repos/{owner}/{repo}/pulls/{index}",
        "edit_pull":    "/api/v1/repos/{owner}/{repo}/pulls/{index}",
        "merge_pull":   "/api/v1/repos/{owner}/{repo}/pulls/{index}/merge",
        "list_releases": "/api/v1/repos/{owner}/{repo}/releases",
        "create_release": "/api/v1/repos/{owner}/{repo}/releases",
        "get_release":  "/api/v1/repos/{owner}/{repo}/releases/{release_id}",
        "get_release_by_tag": "/api/v1/repos/{owner}/{repo}/releases/tags/{tag_name}",
        "edit_release": "/api/v1/repos/{owner}/{repo}/releases/{release_id}",
        "delete_release": "/api/v1/repos/{owner}/{repo}/releases/{release_id}",
    },
    "github": {
        "create_token": None,  # GitHub does not support creating tokens via API
        "list_labels":  "/repos/{owner}/{repo}/labels",
        "create_label": "/repos/{owner}/{repo}/labels",
        "create_issue": "/repos/{owner}/{repo}/issues",
        "edit_issue":   "/repos/{owner}/{repo}/issues/{index}",
        "add_comment":  "/repos/{owner}/{repo}/issues/{index}/comments",
        "list_issues":  "/repos/{owner}/{repo}/issues",
        "list_pulls":   "/repos/{owner}/{repo}/pulls",
        "create_pull":  "/repos/{owner}/{repo}/pulls",
        "get_pull":     "/repos/{owner}/{repo}/pulls/{index}",
        "edit_pull":    "/repos/{owner}/{repo}/pulls/{index}",
        "merge_pull":   "/repos/{owner}/{repo}/pulls/{index}/merge",
        "list_releases": "/repos/{owner}/{repo}/releases",
        "create_release": "/repos/{owner}/{repo}/releases",
        "get_release":  "/repos/{owner}/{repo}/releases/{release_id}",
        "get_release_by_tag": "/repos/{owner}/{repo}/releases/tags/{tag_name}",
        "edit_release": "/repos/{owner}/{repo}/releases/{release_id}",
        "delete_release": "/repos/{owner}/{repo}/releases/{release_id}",
    },
    "gitlab": {
        "create_token": None,
        "list_labels":  "/api/v4/projects/{encoded}/labels",
        "create_label": "/api/v4/projects/{encoded}/labels",
        "create_issue": "/api/v4/projects/{encoded}/issues",
        "edit_issue":   "/api/v4/projects/{encoded}/issues/{index}",
        "add_comment":  "/api/v4/projects/{encoded}/issues/{index}/notes",
        "list_issues":  "/api/v4/projects/{encoded}/issues",
        "list_pulls":   "/api/v4/projects/{encoded}/merge_requests",
        "create_pull":  "/api/v4/projects/{encoded}/merge_requests",
        "get_pull":     "/api/v4/projects/{encoded}/merge_requests/{index}",
        "edit_pull":    "/api/v4/projects/{encoded}/merge_requests/{index}",
        "merge_pull":   "/api/v4/projects/{encoded}/merge_requests/{index}/merge",
        "list_releases": "/api/v4/projects/{encoded}/releases",
        "create_release": "/api/v4/projects/{encoded}/releases",
        "get_release":  "/api/v4/projects/{encoded}/releases/{tag_name}",
        "get_release_by_tag": "/api/v4/projects/{encoded}/releases/{tag_name}",
        "edit_release": "/api/v4/projects/{encoded}/releases/{tag_name}",
        "delete_release": "/api/v4/projects/{encoded}/releases/{tag_name}",
    },
    "gitee": {
        "create_token": None,
        "list_labels":  "/repos/{owner}/{repo}/labels",
        "create_label": "/repos/{owner}/{repo}/labels",
        "create_issue": "/repos/{owner}/{repo}/issues",
        "edit_issue":   "/repos/{owner}/{repo}/issues/{number}",
        "add_comment":  "/repos/{owner}/{repo}/issues/{number}/comments",
        "list_issues":  "/repos/{owner}/{repo}/issues",
        "list_pulls":   "/repos/{owner}/{repo}/pulls",
        "create_pull":  "/repos/{owner}/{repo}/pulls",
        "get_pull":     "/repos/{owner}/{repo}/pulls/{number}",
        "edit_pull":    "/repos/{owner}/{repo}/pulls/{number}",
        "merge_pull":   "/repos/{owner}/{repo}/pulls/{number}/merge",
        "list_releases": "/repos/{owner}/{repo}/releases",
        "create_release": "/repos/{owner}/{repo}/releases",
        "get_release":  "/repos/{owner}/{repo}/releases/{release_id}",
        "get_release_by_tag": "/repos/{owner}/{repo}/releases/tags/{tag_name}",
        "edit_release": "/repos/{owner}/{repo}/releases/{release_id}",
        "delete_release": "/repos/{owner}/{repo}/releases/{release_id}",
    },
    "gitcode": {
        "create_token": None,
        "list_labels":  "/api/v4/projects/{encoded}/labels",
        "create_label": "/api/v4/projects/{encoded}/labels",
        "create_issue": "/api/v4/projects/{encoded}/issues",
        "edit_issue":   "/api/v4/projects/{encoded}/issues/{index}",
        "add_comment":  "/api/v4/projects/{encoded}/issues/{index}/notes",
        "list_issues":  "/api/v4/projects/{encoded}/issues",
        "list_pulls":   "/api/v4/projects/{encoded}/merge_requests",
        "create_pull":  "/api/v4/projects/{encoded}/merge_requests",
        "get_pull":     "/api/v4/projects/{encoded}/merge_requests/{index}",
        "edit_pull":    "/api/v4/projects/{encoded}/merge_requests/{index}",
        "merge_pull":   "/api/v4/projects/{encoded}/merge_requests/{index}/merge",
        "list_releases": "/api/v4/projects/{encoded}/releases",
        "create_release": "/api/v4/projects/{encoded}/releases",
        "get_release":  "/api/v4/projects/{encoded}/releases/{tag_name}",
        "get_release_by_tag": "/api/v4/projects/{encoded}/releases/{tag_name}",
        "edit_release": "/api/v4/projects/{encoded}/releases/{tag_name}",
        "delete_release": "/api/v4/projects/{encoded}/releases/{tag_name}",
    },
}

# ============================================================
# Label definitions — four-dimensional software workflow categories
# ============================================================

ISSUE_LABELS = {
    "priority": [
        {"name": "Priority/Urgent", "color": "e53e3e", "description": "Needs immediate attention", "exclusive": True},
        {"name": "Priority/High",   "color": "ed8936", "description": "Important issue; should be handled as soon as possible", "exclusive": True},
        {"name": "Priority/Medium", "color": "ecc94b", "description": "Regular issue", "exclusive": True},
        {"name": "Priority/Low",    "color": "a0aec0", "description": "Can be deferred", "exclusive": True},
    ],
    "review": [
        {"name": "Review/Pending Review", "color": "4299e1", "description": "Awaiting code review", "exclusive": True},
        {"name": "Review/Changes Required", "color": "ed8936", "description": "Review found issues; changes required", "exclusive": True},
        {"name": "Review/Approved", "color": "48bb78", "description": "Review passed", "exclusive": True},
        {"name": "Review/Rejected", "color": "e53e3e", "description": "Review rejected", "exclusive": True},
    ],
    "status": [
        {"name": "Status/Pending Confirmation",   "color": "a0aec0", "description": "Pending confirmation of validity", "exclusive": True},
        {"name": "Status/In Progress",   "color": "4299e1", "description": "Being fixed", "exclusive": True},
        {"name": "Status/Verified",   "color": "48bb78", "description": "Fix verified", "exclusive": True},
        {"name": "Status/Closed",   "color": "718096", "description": "Issue closed", "exclusive": True},
        {"name": "Status/Cannot Reproduce", "color": "9f7aea", "description": "Cannot reproduce", "exclusive": True},
    ],
    "type": [
        {"name": "Type/Defect", "color": "e53e3e", "description": "Functional defect", "exclusive": True},
        {"name": "Type/Requirement", "color": "48bb78", "description": "New feature requirement", "exclusive": True},
        {"name": "Type/Improvement", "color": "4299e1", "description": "Optimization/refactoring", "exclusive": True},
        {"name": "Type/Documentation", "color": "ecc94b", "description": "Documentation related", "exclusive": True},
        {"name": "Type/Testing", "color": "9f7aea", "description": "Testing related", "exclusive": True},
    ],
}


# ============================================================
# HTTP requests (with exponential backoff retry)
# ============================================================

def _request(base_url, token, method, path, body=None, params=None, platform="gitea", basic_auth=None, _retries=3):
    """Send an HTTP request, supporting exponential backoff retries (5xx and network errors).

    Note: _retries is an internal parameter and should not be used by external callers.
    """
    url = f"{base_url.rstrip('/')}{path}"
    if params:
        clean = {k: v for k, v in params.items() if v is not None}
        if clean:
            url += "?" + urlencode(clean)

    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if basic_auth:
        raw = f"{basic_auth[0]}:{basic_auth[1]}".encode()
        headers["Authorization"] = f"Basic {base64.b64encode(raw).decode()}"
    elif platform in ("github", "gitee"):
        headers["Authorization"] = f"Bearer {token}"
        if platform == "github":
            headers["X-GitHub-Api-Version"] = "2022-11-28"
    elif platform in ("gitlab", "gitcode"):
        headers["PRIVATE-TOKEN"] = token
    else:
        headers["Authorization"] = f"token {token}"

    if not token and not basic_auth:
        raise ValueError("Please provide token or basic_auth credentials")

    data = json.dumps(body).encode("utf-8") if body else None
    req = Request(url, data=data, headers=headers, method=method)

    last_exception = None
    for attempt in range(_retries):
        try:
            with urlopen(req, timeout=TIMEOUT_NETWORK_REQUEST) as resp:
                raw = resp.read().decode("utf-8")
                if resp.status == 204:
                    return {"success": True}
                return json.loads(raw) if raw else {"success": True}
        except HTTPError as e:
            last_exception = e
            detail = e.read().decode("utf-8", errors="replace") if e.fp else ""
            # 5xx errors are retryable; 4xx are not
            if e.code >= 500 and attempt < _retries - 1:
                wait = 2 ** attempt
                logger.warning("API %d error (attempt %d/%d), retrying after %ds", e.code, attempt + 1, _retries, wait)
                time.sleep(wait)
                continue
            # Sanitize: error details may contain token information
            safe_detail = detail[:300]
            raise RuntimeError(f"API {e.code}: {safe_detail}")
        except URLError as e:
            last_exception = e
            if attempt < _retries - 1:
                wait = 2 ** attempt
                logger.warning("Network error (attempt %d/%d), retrying after %ds: %s", attempt + 1, _retries, wait, e)
                time.sleep(wait)
                continue
            raise RuntimeError(f"Unable to connect to {base_url}: {e}")


# ============================================================
# Unified entry point
# ============================================================

def code_hosting(**kwargs) -> dict:
    """Unified entry point for code hosting platform operations.

    platform: gitea / github / gitlab / gitee / gitcode (default: gitea)
    action:
      - create_token  Create an access token (Gitea only)
      - init_labels   Batch initialize four-dimensional workflow labels
      - create_issue  Create an issue
      - get_issue     View an issue
      - edit_issue    Edit an issue
      - set_labels    Set issue labels
      - create/get/list/edit_pull       PR/MR operations
      - create/get/list/edit/delete_release  Release operations
      - close_issue   Close an issue
      - add_comment   Add a comment
      - list_issues   List issues
      - git_status/diff/show/log/add/commit/fetch/pull/branch/switch/merge/restore/unstage/stash/tag/push/clone
    """
    platform = kwargs.pop("platform", "gitea").lower()
    action = kwargs.pop("action", "")

    if platform not in _API_PATHS:
        return _err(f"Unsupported platform: {platform}, options: {', '.join(_API_PATHS.keys())}")
    handler = _DISPATCH.get(action)
    if not handler:
        return _err(f"Unsupported action: {action}, options: {', '.join(_DISPATCH.keys())}")

    try:
        # Pre-validation: required parameters for API actions
        if action in _API_ACTIONS:
            if "base_url" not in kwargs:
                return _err(f"{action} requires base_url parameter")
            if action != "create_token" and "token" not in kwargs:
                return _err(f"{action} requires token parameter")
        return handler(platform, **kwargs)
    except Exception as e:
        logger.exception("code_hosting error")
        return _err(str(e))


_API_ACTIONS = {
    "create_token",
    "init_labels",
    "create_issue",
    "get_issue",
    "edit_issue",
    "set_labels",
    "create_pull",
    "get_pull",
    "list_pulls",
    "edit_pull",
    "merge_pull",
    "close_pull",
    "reopen_pull",
    "create_release",
    "get_release",
    "list_releases",
    "edit_release",
    "delete_release",
    "close_issue",
    "add_comment",
    "list_issues",
}


_DISPATCH = {}


def _reg(name):
    """Decorator: register an action handler"""
    def _(fn):
        _DISPATCH[name] = fn
        return fn
    return _


def _err(msg):
    return {"message": msg, "status": "failed"}


def _ok(msg):
    return {"message": msg, "status": "ok"}


def _truncate_output(text: str, limit: int = 12000) -> str:
    """Limit command output so MCP responses stay readable."""
    if text is None:
        return ""
    if limit <= 0 or len(text) <= limit:
        return text
    omitted = len(text) - limit
    return f"{text[:limit]}\n... <truncated {omitted} chars>"


def _split_ref(ref: str) -> list[str]:
    """Split a user-supplied revision range into safe git args."""
    ref = (ref or "").strip()
    if not ref:
        return []
    if re.search(r"[\r\n\0]", ref):
        raise ValueError("ref parameter contains invalid characters")
    parts = ref.split()
    if any(part.startswith("-") for part in parts):
        raise ValueError("ref parameter cannot be a Git option")
    return parts


def _validate_git_arg(name: str, value: str, *, allow_empty: bool = False) -> str:
    """Validate a user-supplied git argument that appears before '--'."""
    value = (value or "").strip()
    if not value:
        if allow_empty:
            return ""
        raise ValueError(f"{name} parameter cannot be empty")
    if re.search(r"[\r\n\0]", value):
        raise ValueError(f"{name} parameter contains invalid characters")
    if value.startswith("-"):
        raise ValueError(f"{name} parameter cannot be a Git option")
    return value


def _require_files(kw: dict, action: str) -> list[str]:
    """Return explicit file list for workspace-changing commands."""
    files = kw.get("files") or []
    if not files:
        raise ValueError(f"{action} requires files parameter to avoid modifying the entire workspace")
    return _validate_git_paths(files, action)


def _validate_git_paths(files: list[str], action: str) -> list[str]:
    """Validate user-supplied git pathspecs placed after '--'."""
    if isinstance(files, str) or not isinstance(files, (list, tuple)):
        raise ValueError(f"{action} files parameter must be a list of paths")
    result = []
    for file_path in files:
        if file_path is None:
            raise ValueError(f"{action} files parameter cannot contain empty paths")
        value = str(file_path)
        if not value:
            raise ValueError(f"{action} files parameter cannot contain empty paths")
        if re.search(r"[\r\n\0]", value):
            raise ValueError(f"{action} files parameter contains invalid characters")
        result.append(value)
    return result


def _coerce_bool(value, default: bool = False) -> bool:
    """Coerce bool-like tool arguments."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "y", "on")


def _split_repo(repo: str):
    """Split the repo parameter string into owner + repo.

    Note:
    - GitHub/Gitea: owner/repo (simple split, no nesting)
    - GitLab: group/subgroup/project (supports nested groups)
      _repo_path URL-encodes for GitLab (quote(f"{owner}/{repo}", safe="")),
      so nested group scenarios are also handled correctly. The owner returned here is the top-level group name.
    """
    parts = repo.split("/", 1)
    if len(parts) != 2:
        raise ValueError("Repository format should be owner/repo (e.g. chinawsb/daofy)")
    return parts[0], parts[1]


def _repo_path(platform, action, owner, repo, index=None, **extra):
    tmpl = _API_PATHS[platform].get(action)
    if tmpl is None:
        raise ValueError(f"{platform} does not support {action}")
    kw = {"owner": owner, "repo": repo}
    if index is not None:
        # Gitee uses {number}; other platforms use {index}
        if platform == "gitee":
            kw["number"] = index
        else:
            kw["index"] = index
    kw.update(extra)
    if "release_id" in extra:
        kw["release_id"] = extra["release_id"]
    if "tag_name" in extra:
        kw["tag_name"] = quote(str(extra["tag_name"]), safe="")
    if platform in ("gitlab", "gitcode") and "{encoded}" in tmpl:
        kw["encoded"] = quote(f"{owner}/{repo}", safe="")
    return tmpl.format(**kw)


def _issue_edit_method(platform):
    """Return the issue update method for each platform family."""
    if platform in ("gitlab", "gitcode"):
        return "PUT"
    return "PATCH"


def _state_filter(platform, state):
    """Map public state names to platform filter values."""
    if platform in ("gitlab", "gitcode") and state == "open":
        return "opened"
    if state == "merged" and platform not in ("gitlab", "gitcode"):
        return "closed"
    return state


def _pull_is_merged(item: dict) -> bool:
    """Return whether a PR/MR response represents a merged item."""
    if item.get("merged") is True:
        return True
    if item.get("merged_at"):
        return True
    return item.get("state") == "merged"


def _state_update_payload(platform, state):
    """Map public state names to platform update payload fields."""
    if not state or state == "all":
        return {}
    if state == "merged":
        raise ValueError("state=merged is read-only; use merge_pull")
    if platform in ("gitlab", "gitcode"):
        if state == "closed":
            return {"state_event": "close"}
        if state == "open":
            return {"state_event": "reopen"}
    return {"state": state}


def _validate_issue_state(state):
    """Reject PR/MR-only states for issue actions."""
    if state == "merged":
        raise ValueError("state=merged is only valid for list_pulls; issues use open/closed/all")


def _issue_body_key(platform):
    """Return the issue body field name used by each platform."""
    if platform in ("gitlab", "gitcode"):
        return "description"
    return "body"


def _label_payload(platform, base_url, token, owner, repo, label_names, allow_empty=False):
    """Build issue label payload for different platforms."""
    label_names = list(label_names or [])
    if not label_names:
        if not allow_empty:
            return {}
        return {"labels": ""} if platform in ("gitlab", "gitcode") else {"labels": []}

    if platform != "gitea":
        if platform in ("gitlab", "gitcode"):
            return {"labels": ",".join(label_names)}
        return {"labels": label_names}

    lp = _repo_path(platform, "list_labels", owner, repo)
    existing = _request(base_url, token, "GET", lp, platform=platform)
    n2id = {lb["name"]: lb["id"] for lb in existing} if isinstance(existing, list) else {}
    unknown = [name for name in label_names if name not in n2id]
    if unknown:
        raise ValueError(f"Gitea labels not found: {', '.join(unknown)}")
    return {"labels": [n2id[name] for name in label_names]}


def _html_url(result):
    """Return the public URL field used by each platform."""
    return result.get("html_url", result.get("web_url", result.get("url", "")))


def _label_names(labels):
    """Return label names from platform issue payloads."""
    names = []
    for label in labels or []:
        if isinstance(label, dict):
            names.append(label.get("name", label.get("title", "")))
        else:
            names.append(str(label))
    return [name for name in names if name]


def _pull_number(result, fallback=""):
    """Return PR/MR number from a platform response."""
    return result.get("number") or result.get("iid") or result.get("id") or fallback


def _pull_payload(platform, kw, require_branches=True):
    """Build create/edit PR or MR payload."""
    payload = {}
    if "title" in kw and kw["title"] is not None:
        payload["title"] = kw["title"]
    if "body" in kw and kw["body"] is not None:
        payload["description" if platform in ("gitlab", "gitcode") else "body"] = kw["body"]
    if require_branches or kw.get("source_branch"):
        source_branch = kw.get("source_branch")
        if not source_branch:
            raise ValueError("create_pull requires source_branch parameter")
        payload["source_branch" if platform in ("gitlab", "gitcode") else "head"] = source_branch
    if require_branches or kw.get("target_branch"):
        target_branch = kw.get("target_branch")
        if not target_branch:
            raise ValueError("create_pull requires target_branch parameter")
        payload["target_branch" if platform in ("gitlab", "gitcode") else "base"] = target_branch
    payload.update(_state_update_payload(platform, kw.get("state")))
    return payload


def _release_key(platform, kw):
    """Return the release path key for release get/edit/delete actions."""
    tag_name = kw.get("tag_name") or kw.get("tag")
    if platform in ("gitlab", "gitcode"):
        if not tag_name:
            raise ValueError("release operation requires tag_name or tag parameter")
        return {"tag_name": tag_name}
    release_id = kw.get("release_id")
    if release_id is not None:
        return {"release_id": release_id}
    if tag_name:
        return {"tag_name": tag_name}
    raise ValueError("release operation requires release_id, tag_name, or tag parameter")


def _release_payload(platform, kw, require_tag=False):
    """Build release payload for different platforms."""
    payload = {}
    tag_name = kw.get("tag_name") or kw.get("tag")
    if require_tag and not tag_name:
        raise ValueError("create_release requires tag_name or tag parameter")
    if tag_name:
        payload["tag_name"] = tag_name
    if kw.get("target_commitish") and platform not in ("gitlab", "gitcode"):
        payload["target_commitish"] = kw["target_commitish"]
    if kw.get("ref") and platform in ("gitlab", "gitcode"):
        payload["ref"] = kw["ref"]
    if kw.get("name"):
        payload["name"] = kw["name"]
    if "body" in kw and kw["body"] is not None:
        payload["description" if platform in ("gitlab", "gitcode") else "body"] = kw["body"]
    if "draft" in kw and platform not in ("gitlab", "gitcode"):
        payload["draft"] = _coerce_bool(kw.get("draft"), False)
    if "prerelease" in kw and platform not in ("gitlab", "gitcode"):
        payload["prerelease"] = _coerce_bool(kw.get("prerelease"), False)
    return payload


def _resolve_release_id(base_url, token, platform, owner, repo, key):
    """Resolve a tag-based release key to a numeric release id when needed."""
    if "release_id" in key or platform in ("gitlab", "gitcode"):
        return key
    tag_name = key.get("tag_name")
    if not tag_name:
        return key
    path = _repo_path(platform, "get_release_by_tag", owner, repo, tag_name=tag_name)
    result = _request(base_url, token, "GET", path, platform=platform)
    release_id = result.get("id")
    if release_id is None:
        raise ValueError(f"release not found by tag: {tag_name}")
    return {"release_id": release_id}


# ============================================================
# Action: create_token
# ============================================================

@_reg("create_token")
def _act_create_token(platform, **kw):
    base_url, username, password = kw["base_url"], kw["username"], kw["password"]
    name = kw.get("token_name", "delphi-mcp")

    path = _repo_path(platform, "create_token", None, None, username=username)
    body = {"name": name, "scopes": ["write:repository", "write:issue"]}
    result = _request(base_url, "", "POST", path, body=body, platform=platform,
                      basic_auth=(username, password))
    token_val = result.get("sha1") or result.get("token", "")
    masked = "%s...%s" % (token_val[:8], token_val[-4:]) if len(token_val) > 12 else "***"
    d = _ok("token created | platform: %s | name: %s | masked: %s" % (platform, result.get('name', name), masked))
    d["token"] = token_val
    return d


# ============================================================
# Action: init_labels
# ============================================================

@_reg("init_labels")
def _act_init_labels(platform, **kw):
    base_url, token = kw["base_url"], kw["token"]
    owner, repo = _split_repo(kw["repo"])

    list_path = _repo_path(platform, "list_labels", owner, repo)
    existing = _request(base_url, token, "GET", list_path, platform=platform)
    exist_names = {lb.get("name") for lb in existing} if isinstance(existing, list) else set()

    created = 0
    skipped = 0
    for group in ISSUE_LABELS.values():
        for label in group:
            if label["name"] in exist_names:
                skipped += 1
                continue
            cp = _repo_path(platform, "create_label", owner, repo)
            _request(base_url, token, "POST", cp, body=label, platform=platform)
            created += 1

    return _ok(f"labels initialized | created: {created} | skipped: {skipped} | total: {created + skipped}")


# ============================================================
# Action: create_issue
# ============================================================

@_reg("create_issue")
def _act_create_issue(platform, **kw):
    base_url, token = kw["base_url"], kw["token"]
    owner, repo = _split_repo(kw["repo"])
    title = kw["title"]
    body = kw.get("body", "")
    label_names = kw.get("labels") or []

    payload = {"title": title}
    if body:
        payload[_issue_body_key(platform)] = body
    payload.update(_label_payload(platform, base_url, token, owner, repo, label_names))

    cp = _repo_path(platform, "create_issue", owner, repo)
    result = _request(base_url, token, "POST", cp, body=payload, platform=platform)

    num = result.get("number") or result.get("iid", "")
    html = _html_url(result)
    st = result.get("state", "")
    return _ok(f"issue #{num} created | state: {st} | title: {title} | labels: {', '.join(label_names) if label_names else 'none'} | url: {html}")


# ============================================================
# Action: get_issue
# ============================================================

@_reg("get_issue")
def _act_get_issue(platform, **kw):
    base_url, token = kw["base_url"], kw["token"]
    owner, repo = _split_repo(kw["repo"])
    num = kw["issue_number"]

    ep = _repo_path(platform, "edit_issue", owner, repo, index=num)
    result = _request(base_url, token, "GET", ep, platform=platform)
    label_names = _label_names(result.get("labels") or [])
    issue_no = result.get("number") or result.get("iid", num)
    html = result.get("html_url", result.get("web_url", ""))
    return _ok(
        f"issue #{issue_no} [{result.get('state', '')}] {result.get('title', '')}"
        f" | labels: {', '.join(label_names) if label_names else 'none'}"
        f" | url: {html}"
    )


# ============================================================
# Action: edit_issue / set_labels
# ============================================================

def _edit_issue(platform, **kw):
    base_url, token = kw["base_url"], kw["token"]
    owner, repo = _split_repo(kw["repo"])
    num = kw["issue_number"]

    payload = {}
    if "title" in kw and kw["title"] is not None:
        payload["title"] = kw["title"]
    if "body" in kw and kw["body"] is not None:
        payload[_issue_body_key(platform)] = kw["body"]
    _validate_issue_state(kw.get("state"))
    payload.update(_state_update_payload(platform, kw.get("state")))

    label_names = kw.get("labels")
    if label_names is not None:
        payload.update(
            _label_payload(
                platform,
                base_url,
                token,
                owner,
                repo,
                label_names,
                allow_empty=True,
            )
        )

    if not payload:
        return _err("edit_issue requires at least one of title/body/state/labels")

    ep = _repo_path(platform, "edit_issue", owner, repo, index=num)
    result = _request(base_url, token, _issue_edit_method(platform), ep, body=payload, platform=platform)
    issue_no = result.get("number") or result.get("iid", num)
    html = result.get("html_url", result.get("web_url", ""))
    return _ok(f"issue #{issue_no} edited | state: {result.get('state', '')} | url: {html}")


@_reg("edit_issue")
def _act_edit_issue(platform, **kw):
    return _edit_issue(platform, **kw)


@_reg("set_labels")
def _act_set_labels(platform, **kw):
    if "labels" not in kw:
        return _err("set_labels requires labels parameter")
    return _edit_issue(platform, **kw)


# ============================================================
# Action: pull request / merge request
# ============================================================

@_reg("create_pull")
def _act_create_pull(platform, **kw):
    base_url, token = kw["base_url"], kw["token"]
    owner, repo = _split_repo(kw["repo"])
    payload = _pull_payload(platform, kw, require_branches=True)
    if "title" not in payload:
        return _err("create_pull requires title parameter")

    path = _repo_path(platform, "create_pull", owner, repo)
    result = _request(base_url, token, "POST", path, body=payload, platform=platform)
    num = _pull_number(result)
    return _ok(f"pull #{num} created | state: {result.get('state', '')} | title: {result.get('title', kw.get('title', ''))} | url: {_html_url(result)}")


@_reg("get_pull")
def _act_get_pull(platform, **kw):
    base_url, token = kw["base_url"], kw["token"]
    owner, repo = _split_repo(kw["repo"])
    num = kw["pull_number"]

    path = _repo_path(platform, "get_pull", owner, repo, index=num)
    result = _request(base_url, token, "GET", path, platform=platform)
    pull_no = _pull_number(result, num)
    return _ok(f"pull #{pull_no} [{result.get('state', '')}] {result.get('title', '')} | url: {_html_url(result)}")


@_reg("list_pulls")
def _act_list_pulls(platform, **kw):
    base_url, token = kw["base_url"], kw["token"]
    owner, repo = _split_repo(kw["repo"])
    state = kw.get("state", "open")
    page_size_key = "limit" if platform == "gitea" else "per_page"
    params = {"page": str(kw.get("page", 1)), page_size_key: str(kw.get("limit", 20))}
    if state and state != "all":
        params["state"] = _state_filter(platform, state)

    path = _repo_path(platform, "list_pulls", owner, repo)
    result = _request(base_url, token, "GET", path, params=params, platform=platform)
    if state == "merged" and platform not in ("gitlab", "gitcode") and isinstance(result, list):
        result = [item for item in result if _pull_is_merged(item)]
    if not isinstance(result, list) or not result:
        return _ok(f"no pulls ({platform}, {state})")

    items = [
        f"#{_pull_number(item)} [{item.get('state', '')}] {item.get('title', '')}"
        for item in result
    ]
    return _ok(f"{len(items)} pulls ({platform}, {state}): " + "; ".join(items))


@_reg("edit_pull")
def _act_edit_pull(platform, **kw):
    base_url, token = kw["base_url"], kw["token"]
    owner, repo = _split_repo(kw["repo"])
    num = kw["pull_number"]
    payload = _pull_payload(platform, kw, require_branches=False)
    if not payload:
        return _err("edit_pull requires at least one of title/body/state/source_branch/target_branch")

    path = _repo_path(platform, "edit_pull", owner, repo, index=num)
    result = _request(base_url, token, _issue_edit_method(platform), path, body=payload, platform=platform)
    pull_no = _pull_number(result, num)
    return _ok(f"pull #{pull_no} edited | state: {result.get('state', '')} | url: {_html_url(result)}")


def _change_pull_state(platform, state: str, **kw):
    """Close or reopen a PR/MR through the existing edit endpoint."""
    kw = dict(kw)
    kw["state"] = state
    return _act_edit_pull(platform, **kw)


def _merge_pull_payload(platform, kw):
    """Build merge PR/MR payload with only fields supported by each platform."""
    payload = {}
    message = kw.get("message")
    if message:
        if platform in ("gitlab", "gitcode"):
            payload["merge_commit_message"] = message
        elif platform in ("github", "gitee"):
            payload["commit_title"] = message
        elif platform == "gitea":
            payload["MergeTitleField"] = message
    if platform in ("github", "gitee") and kw.get("body"):
        payload["commit_message"] = kw["body"]
    if platform == "gitea":
        payload.setdefault("Do", "merge")
        if kw.get("body"):
            payload["MergeMessageField"] = kw["body"]
    return payload


def _merge_pull_method(platform):
    """Return the merge endpoint method for each platform."""
    if platform == "gitea":
        return "POST"
    return "PUT"


@_reg("merge_pull")
def _act_merge_pull(platform, **kw):
    base_url, token = kw["base_url"], kw["token"]
    owner, repo = _split_repo(kw["repo"])
    num = kw["pull_number"]

    path = _repo_path(platform, "merge_pull", owner, repo, index=num)
    result = _request(
        base_url,
        token,
        _merge_pull_method(platform),
        path,
        body=_merge_pull_payload(platform, kw),
        platform=platform,
    )
    pull_no = _pull_number(result, num)
    merged = _pull_is_merged(result) or result.get("merged") is True
    status = "merged" if merged else result.get("state", "merge requested")
    return _ok(f"pull #{pull_no} {status} | url: {_html_url(result)}")


@_reg("close_pull")
def _act_close_pull(platform, **kw):
    return _change_pull_state(platform, "closed", **kw)


@_reg("reopen_pull")
def _act_reopen_pull(platform, **kw):
    return _change_pull_state(platform, "open", **kw)


# ============================================================
# Action: release
# ============================================================

@_reg("create_release")
def _act_create_release(platform, **kw):
    base_url, token = kw["base_url"], kw["token"]
    owner, repo = _split_repo(kw["repo"])
    payload = _release_payload(platform, kw, require_tag=True)

    path = _repo_path(platform, "create_release", owner, repo)
    result = _request(base_url, token, "POST", path, body=payload, platform=platform)
    release_id = result.get("id", result.get("tag_name", payload.get("tag_name", "")))
    return _ok(f"release {release_id} created | tag: {result.get('tag_name', payload.get('tag_name', ''))} | url: {_html_url(result)}")


@_reg("get_release")
def _act_get_release(platform, **kw):
    base_url, token = kw["base_url"], kw["token"]
    owner, repo = _split_repo(kw["repo"])
    key = _release_key(platform, kw)

    action = "get_release_by_tag" if "tag_name" in key else "get_release"
    path = _repo_path(platform, action, owner, repo, **key)
    result = _request(base_url, token, "GET", path, platform=platform)
    release_id = result.get("id", result.get("tag_name", key.get("tag_name", key.get("release_id", ""))))
    return _ok(f"release {release_id} | tag: {result.get('tag_name', '')} | name: {result.get('name', '')} | url: {_html_url(result)}")


@_reg("list_releases")
def _act_list_releases(platform, **kw):
    base_url, token = kw["base_url"], kw["token"]
    owner, repo = _split_repo(kw["repo"])
    page_size_key = "limit" if platform == "gitea" else "per_page"
    params = {"page": str(kw.get("page", 1)), page_size_key: str(kw.get("limit", 20))}

    path = _repo_path(platform, "list_releases", owner, repo)
    result = _request(base_url, token, "GET", path, params=params, platform=platform)
    if not isinstance(result, list) or not result:
        return _ok(f"no releases ({platform})")

    items = [
        f"{item.get('id', item.get('tag_name', ''))} {item.get('tag_name', '')} {item.get('name', '')}".strip()
        for item in result
    ]
    return _ok(f"{len(items)} releases ({platform}): " + "; ".join(items))


@_reg("edit_release")
def _act_edit_release(platform, **kw):
    base_url, token = kw["base_url"], kw["token"]
    owner, repo = _split_repo(kw["repo"])
    key = _release_key(platform, kw)
    key = _resolve_release_id(base_url, token, platform, owner, repo, key)
    payload = _release_payload(platform, kw, require_tag=False)
    if not payload:
        return _err("edit_release requires at least one of name/body/draft/prerelease")

    path = _repo_path(platform, "edit_release", owner, repo, **key)
    result = _request(base_url, token, _issue_edit_method(platform), path, body=payload, platform=platform)
    release_id = result.get("id", result.get("tag_name", key.get("tag_name", key.get("release_id", ""))))
    return _ok(f"release {release_id} edited | tag: {result.get('tag_name', '')} | url: {_html_url(result)}")


@_reg("delete_release")
def _act_delete_release(platform, **kw):
    base_url, token = kw["base_url"], kw["token"]
    owner, repo = _split_repo(kw["repo"])
    key = _release_key(platform, kw)
    key = _resolve_release_id(base_url, token, platform, owner, repo, key)

    path = _repo_path(platform, "delete_release", owner, repo, **key)
    _request(base_url, token, "DELETE", path, platform=platform)
    release_id = key.get("tag_name", key.get("release_id", ""))
    return _ok(f"release {release_id} deleted")


# ============================================================
# Action: close_issue
# ============================================================

@_reg("close_issue")
def _act_close_issue(platform, **kw):
    base_url, token = kw["base_url"], kw["token"]
    owner, repo = _split_repo(kw["repo"])
    num = kw["issue_number"]
    # Compatibility with comment_body alias (older tests/clients may use)
    comment = kw.get("comment", kw.get("comment_body", ""))

    if comment:
        cpath = _repo_path(platform, "add_comment", owner, repo, index=num)
        _request(base_url, token, "POST", cpath, body={"body": comment}, platform=platform)

    ep = _repo_path(platform, "edit_issue", owner, repo, index=num)
    result = _request(
        base_url,
        token,
        _issue_edit_method(platform),
        ep,
        body=_state_update_payload(platform, "closed"),
        platform=platform,
    )
    html = _html_url(result)
    return _ok(f"issue #{num} closed | url: {html}" + (f" | comment: {comment[:80]}" if comment else ""))


# ============================================================
# Action: add_comment
# ============================================================

@_reg("add_comment")
def _act_add_comment(platform, **kw):
    base_url, token = kw["base_url"], kw["token"]
    owner, repo = _split_repo(kw["repo"])
    num = kw["issue_number"]
    text = kw["body"]

    cp = _repo_path(platform, "add_comment", owner, repo, index=num)
    result = _request(base_url, token, "POST", cp, body={"body": text}, platform=platform)
    return _ok(f"comment added (id: {result.get('id', '')}) | issue: #{num}")


# ============================================================
# Action: list_issues
# ============================================================

@_reg("list_issues")
def _act_list_issues(platform, **kw):
    base_url, token = kw["base_url"], kw["token"]
    owner, repo = _split_repo(kw["repo"])
    state = kw.get("state", "open")
    _validate_issue_state(state)

    lp = _repo_path(platform, "list_issues", owner, repo)
    # Pagination parameter name varies by platform: gitea=limit, others=per_page
    page_size_key = "limit" if platform == "gitea" else "per_page"
    # GitLab/GitCode do not support state=all; omitting state returns all by default
    params_state = _state_filter(platform, state) if not (platform in ("gitlab", "gitcode") and state == "all") else None
    params = {}
    if params_state:
        params["state"] = params_state
    params["page"] = str(kw.get("page", 1))
    params[page_size_key] = str(kw.get("limit", 20))
    result = _request(base_url, token, "GET", lp, params=params, platform=platform)
    if platform == "github" and isinstance(result, list):
        result = [item for item in result if not item.get("pull_request")]

    if not isinstance(result, list) or not result:
        return _ok(f"no issues ({platform}, {state})")

    items = []
    for i in result:
        n = i.get("number") or i.get("iid", "")
        ls = _label_names(i.get("labels") or [])
        items.append(f"#{n} [{i.get('state','')}] {i.get('title','')}{' ' + ','.join(ls) if ls else ''}")

    return _ok(f"{len(items)} issues ({platform}, {state}): " + "; ".join(items))


# ============================================================
# Git local operations (no platform parameter required)
# ============================================================


def _git_human_error(err_text: str, cmd_str: str) -> str:
    """Convert raw Git error messages into user-friendly Chinese hints."""
    err_lower = err_text.lower()

    # ── Authentication related ──
    if re.search(r"could not read (username|password)", err_lower):
        return (
            "Git authentication required, but MCP environment does not support interactive input.\n"
            "  Solutions (choose one):\n"
            "    1. Configure credential manager: git config --global credential.helper manager\n"
            "    2. Use SSH key: git remote set-url origin git@github.com:owner/repo.git\n"
            "    3. Write credentials in .netrc file\n"
            f"  Original error: {err_text[:200]}"
        )
    if re.search(r"authentication failed|access denied|invalid username or password|auth fail", err_lower):
        return f"Authentication failed, please check whether username/password or Token is correct:\n  {err_text[:200]}"
    if "permission denied (publickey)" in err_lower:
        return (
            "SSH authentication failed, please check SSH key configuration:\n"
            "    1. Confirm the public key has been added to the Git platform\n"
            "    2. Confirm the private key is available locally: ssh -T git@github.com\n"
            f"  Original error: {err_text[:200]}"
        )

    # ── Network related ──
    if re.search(r"could not resolve host|couldn'?t resolve host|name or service not known", err_lower):
        return f"Unable to resolve host address, please check network connection or proxy configuration:\n  {err_text[:200]}"
    if re.search(r"connection refused|could not connect to|connect.*timed out|connection timed out", err_lower):
        return f"Connection refused or timed out, please check network/proxy/firewall settings:\n  {err_text[:200]}"

    # ── Repository issues ──
    if "repository not found" in err_lower:
        return f"Repository does not exist or access is denied, please check whether the repo address is correct:\n  {err_text[:200]}"
    if "not a git repository" in err_lower:
        return f"Current directory is not a Git repository (or the parent directory is missing .git), please confirm the dir parameter points to the correct repository:\n  {err_text[:200]}"
    if re.search(r"pathspec.*did not match any", err_lower):
        return f"The specified file path does not exist in the repository:\n  {err_text[:200]}"
    if re.search(r"unknown switch|unrecognized argument|error: unknown option", err_lower):
        return f"Invalid Git command parameters, please check parameter spelling:\n  {err_text[:200]}"

    # ── Large files/disk ──
    if re.search(r"file too large|large file detected|exceeds github|file size", err_lower):
        return f"File size exceeds the limit, please use Git LFS to manage large files:\n  {err_text[:200]}"
    if re.search(r"disk quota|no space left|insufficient disk", err_lower):
        return f"Insufficient disk space:\n  {err_text[:200]}"

    # ── Default: return first 500 characters of raw error
    return err_text[:500]


def _git_run(work_dir, *args, timeout=TIMEOUT_GIT_PUSH, env=None):
    """Execute a git command in the specified directory and return the output.

    On Windows, use utf-8 encoding to decode output to avoid gbk decoding errors.

    Args:
        work_dir: Working directory (automatically resolves to prevent path traversal)
        timeout: Timeout seconds, default 300 (5 minutes, suitable for cloning large projects)
        env: Additional environment variable dictionary (optional), merged into the subprocess environment
    """
    safe_dir = _resolve_safe_dir(work_dir) if work_dir else None
    cwd = safe_dir if (safe_dir and os.path.isdir(safe_dir)) else None
    cmd = ["git"] + list(args)

    # Build subprocess environment: inherit current environment + force non-interactive
    proc_env = os.environ.copy()
    proc_env["GIT_TERMINAL_PROMPT"] = "0"  # Disable git credential prompt
    proc_env["GIT_PAGER"] = ""              # Disable pager (e.g. less)
    proc_env["PAGER"] = ""                  # Also disable global pager
    proc_env["GIT_EDITOR"] = ":"            # Disable opening editor
    if env:
        proc_env.update(env)

    try:
        r = subprocess.run(
            cmd, capture_output=True, cwd=cwd,
            stdin=subprocess.DEVNULL,        # Prevent git from reading MCP's JSON-RPC pipe and causing deadlock
            timeout=timeout,
            env=proc_env,
        )
        
        # Specify utf-8 decoding to avoid Windows gbk encoding issues
        def _decode(data):
            if isinstance(data, str):
                return data  # Test mocks may pass str; no decoding needed
            for enc in ("utf-8", "gbk", "gb2312", "latin-1"):
                try:
                    return data.decode(enc)
                except (UnicodeDecodeError, UnicodeError):
                    continue
            return data.decode("utf-8", errors="replace")
        
        stdout = _decode(r.stdout)
        stderr = _decode(r.stderr)
        
        if r.returncode != 0:
            err_text = stderr.strip()[:500]
            cmd_str = ' '.join(args)
            raise RuntimeError(f"git {cmd_str} failed:\n{_git_human_error(err_text, cmd_str)}")
        return stdout.strip()
    except FileNotFoundError:
        raise RuntimeError("git command not found, please make sure Git is installed")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"git operation timeout ({timeout}s)")
    except OSError as e:
        raise RuntimeError(f"git execution failed: {e}")



# ============================================================
# Async Git tasks (reuse AsyncTaskManager)
# ============================================================


def _submit_git_task(name: str, fn, **kw) -> tuple:
    """Submit a background git task via AsyncTaskManager."""
    if get_task_manager is None:
        return "", _err("async task manager not available")
    on_complete = kw.pop('_on_complete', None)
    task_id = get_task_manager().submit_task(
        name, fn,
        on_complete=on_complete,
        **kw,
    )
    resp = _ok(f"task {task_id} | action: {name}")
    resp["task_id"] = task_id
    return task_id, resp


GIT_REMOTE_SYNC_TIMEOUT = TIMEOUT_GIT_REMOTE_SYNC
GIT_REMOTE_ASYNC_TIMEOUT = TIMEOUT_GIT_PUSH


def _run_git_remote_action(action: str, work_dir: str, args: list[str], success_message: str, **kw) -> dict:
    """Run a potentially slow git remote action synchronously or as a task."""
    async_mode = _coerce_bool(kw.get("async_mode", kw.get("async")), False)
    if async_mode:
        def _do_git_remote(**task_kw):
            progress_cb = task_kw.get("_progress_callback")
            cancel_check = task_kw.get("_cancellation_check")
            if cancel_check:
                cancel_check()
            if progress_cb:
                progress_cb(10, f"{action} started")
            raw = _git_run(work_dir, *args, timeout=GIT_REMOTE_ASYNC_TIMEOUT)
            if progress_cb:
                progress_cb(100, f"{action} finished")
            return _ok(raw or success_message)

        task_id, resp = _submit_git_task(action, _do_git_remote, **kw)
        if resp.get("status") != "ok":
            return resp
        result = _ok(f"{action} task {task_id} | use async_task(action=status, task_id=...)")
        result["task_id"] = task_id
        return result

    try:
        raw = _git_run(work_dir, *args, timeout=GIT_REMOTE_SYNC_TIMEOUT)
    except RuntimeError as exc:
        message = str(exc)
        if "超时" in message or "timeout" in message.lower():
            return _err(f"{message}; retry with async_mode=True and query via async_task")
        raise
    return _ok(raw or success_message)


# ============================================================
# Git local operations — fast operations (synchronous)
# ============================================================


def _compact_git_status(raw: str) -> str:
    """Compress git status --porcelain=v1 -b output into a one-line summary."""
    lines = raw.splitlines()
    branch = "?"
    sync = ""
    staged, unstaged, untracked = [], [], []

    for line in lines:
        if not line:
            continue
        if line.startswith("## "):
            header = line[3:].strip()
            if "..." in header:
                branch_part, sync_part = header.split("...", 1)
                branch = branch_part.strip() or "?"
                sync = sync_part.strip()
            else:
                branch = header.strip() or "?"
            continue

        if len(line) < 4:
            continue
        index_status, worktree_status = line[0], line[1]
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if index_status == "?" and worktree_status == "?":
            untracked.append(path)
            continue
        if index_status != " ":
            staged.append(path)
        if worktree_status != " ":
            unstaged.append(path)

    parts = [branch]
    if sync:
        parts.append(sync)
    if not staged and not unstaged and not untracked:
        parts.append("clean")
    if staged:
        parts.append(f"staged({len(staged)}): {' '.join(staged)}")
    if unstaged:
        parts.append(f"modified({len(unstaged)}): {' '.join(unstaged)}")
    if untracked:
        parts.append(f"untracked({len(untracked)}): {' '.join(untracked)}")
    return " | ".join(parts)


@_reg("git_status")
def _act_git_status(platform=None, **kw):
    """View repository status (synchronous, instantaneous)."""
    work_dir = kw.get("dir", ".")
    raw = _git_run(work_dir, "status", "--porcelain=v1", "-b", timeout=TIMEOUT_GIT_QUICK)
    return _ok(_compact_git_status(raw))


@_reg("git_diff")
def _act_git_diff(platform=None, **kw):
    """View diff (synchronous, read-only)."""
    work_dir = kw.get("dir", ".")
    staged = _coerce_bool(kw.get("staged"), False)
    stat = _coerce_bool(kw.get("stat"), False)
    name_only = _coerce_bool(kw.get("name_only"), False)
    ref = kw.get("ref", "")
    files = kw.get("files") or []
    limit = int(kw.get("limit", 12000))

    args = ["diff", "--no-ext-diff"]
    if staged:
        args.append("--cached")
    if stat:
        args.append("--stat")
    if name_only:
        args.append("--name-only")
    args.extend(_split_ref(ref))
    if files:
        args.append("--")
        args.extend(files)

    raw = _git_run(work_dir, *args, timeout=TIMEOUT_GIT_QUICK)
    return _ok(_truncate_output(raw or "(no diff)", limit))


@_reg("git_show")
def _act_git_show(platform=None, **kw):
    """View commit/object contents (synchronous, read-only)."""
    work_dir = kw.get("dir", ".")
    ref = kw.get("ref", "HEAD")
    stat = _coerce_bool(kw.get("stat"), False)
    name_only = _coerce_bool(kw.get("name_only"), False)
    limit = int(kw.get("limit", 12000))

    args = ["show", "--no-ext-diff"]
    if stat:
        args.append("--stat")
    if name_only:
        args.append("--name-only")
    args.extend(_split_ref(ref))

    raw = _git_run(work_dir, *args, timeout=TIMEOUT_GIT_QUICK)
    return _ok(_truncate_output(raw, limit))


@_reg("git_log")
def _act_git_log(platform=None, **kw):
    """View commit history (synchronous, read-only)."""
    work_dir = kw.get("dir", ".")
    count = int(kw.get("limit", 20))
    ref = kw.get("ref", "")
    files = kw.get("files") or []

    args = ["log", "--oneline", "--decorate", f"-n{count}"]
    args.extend(_split_ref(ref))
    if files:
        args.append("--")
        args.extend(files)

    raw = _git_run(work_dir, *args, timeout=TIMEOUT_GIT_QUICK)
    return _ok(raw or "(no commits)")


@_reg("git_add")
def _act_git_add(platform=None, **kw):
    """Stage files (synchronous)."""
    work_dir = kw.get("dir", ".")
    files = _validate_git_paths(kw.get("files", []), "git_add")
    if not files:
        return _err("specify files via 'files' parameter")
    _git_run(work_dir, "add", "--", *files, timeout=TIMEOUT_GIT_QUICK)
    return _ok(f"staged: {' '.join(files)}")


@_reg("git_commit")

def _act_git_commit(platform=None, **kw):
    """Create a commit (synchronous, local operation is very fast)."""
    work_dir = kw.get("dir", ".")
    msg = kw.get("message", "")
    if not msg:
        return _err("specify message via 'message' parameter")
    _git_run(work_dir, "commit", "-m", msg, timeout=TIMEOUT_GIT_QUICK)
    try:
        h = _git_run(work_dir, "rev-parse", "HEAD", timeout=TIMEOUT_GIT_REV_PARSE)
        return _ok(f"committed {h[:12]}: {msg}")
    except RuntimeError:
        return _ok(f"committed: {msg}")


@_reg("git_fetch")
def _act_git_fetch(platform=None, **kw):
    """Fetch remote refs (synchronous)."""
    work_dir = kw.get("dir", ".")
    remote = _validate_git_arg("remote", kw.get("remote", "origin"))
    branch = _validate_git_arg("branch", kw.get("branch", ""), allow_empty=True)
    prune = _coerce_bool(kw.get("prune"), False)

    args = ["fetch"]
    if prune:
        args.append("--prune")
    args.append(remote)
    if branch:
        args.append(branch)
    return _run_git_remote_action(
        "git_fetch",
        work_dir,
        args,
        f"fetched {remote}{'/' + branch if branch else ''}",
        **kw,
    )


@_reg("git_pull")
def _act_git_pull(platform=None, **kw):
    """Pull and merge remote branch (synchronous)."""
    work_dir = kw.get("dir", ".")
    remote = _validate_git_arg("remote", kw.get("remote", "origin"))
    branch = _validate_git_arg("branch", kw.get("branch", ""), allow_empty=True)
    rebase = _coerce_bool(kw.get("rebase"), False)
    ff_only = _coerce_bool(kw.get("ff_only"), False)

    args = ["pull"]
    if rebase:
        args.append("--rebase")
    if ff_only:
        args.append("--ff-only")
    args.append(remote)
    if branch:
        args.append(branch)
    return _run_git_remote_action(
        "git_pull",
        work_dir,
        args,
        f"pulled {remote}{'/' + branch if branch else ''}",
        **kw,
    )


@_reg("git_branch")
def _act_git_branch(platform=None, **kw):
    """List or create branches (synchronous)."""
    work_dir = kw.get("dir", ".")
    branch = _validate_git_arg("branch", kw.get("branch", ""), allow_empty=True)
    start_point = _validate_git_arg("start_point", kw.get("start_point", ""), allow_empty=True)
    delete = _coerce_bool(kw.get("delete"), False)
    remote = _coerce_bool(kw.get("remote_branches"), False)

    if delete:
        if not branch:
            return _err("git_branch delete requires branch parameter")
        _git_run(work_dir, "branch", "-d", branch, timeout=TIMEOUT_GIT_QUICK)
        return _ok(f"branch deleted: {branch}")

    if branch:
        args = ["branch", branch]
        if start_point:
            args.append(start_point)
        _git_run(work_dir, *args, timeout=TIMEOUT_GIT_QUICK)
        return _ok(f"branch created: {branch}{' from ' + start_point if start_point else ''}")

    args = ["branch"]
    if remote:
        args.append("-a")
    raw = _git_run(work_dir, *args, timeout=TIMEOUT_GIT_QUICK)
    return _ok(raw or "(no branches)")


@_reg("git_switch")
def _act_git_switch(platform=None, **kw):
    """Switch or create branches (synchronous)."""
    work_dir = kw.get("dir", ".")
    branch = _validate_git_arg("branch", kw.get("branch", ""), allow_empty=True)
    create = _coerce_bool(kw.get("create"), False)
    start_point = _validate_git_arg("start_point", kw.get("start_point", ""), allow_empty=True)
    if not branch:
        return _err("git_switch requires branch parameter")

    args = ["switch"]
    if create:
        args.extend(["-c", branch])
        if start_point:
            args.append(start_point)
    else:
        args.append(branch)
    raw = _git_run(work_dir, *args, timeout=TIMEOUT_GIT_QUICK)
    return _ok(raw or f"switched to {branch}")


@_reg("git_merge")
def _act_git_merge(platform=None, **kw):
    """Merge branches (synchronous). Default no-ff=false, supports ff_only."""
    work_dir = kw.get("dir", ".")
    branch = _validate_git_arg("branch", kw.get("branch", ""), allow_empty=True)
    ff_only = _coerce_bool(kw.get("ff_only"), False)
    no_commit = _coerce_bool(kw.get("no_commit"), False)
    if not branch:
        return _err("git_merge requires branch parameter")

    args = ["merge"]
    if ff_only:
        args.append("--ff-only")
    if no_commit:
        args.append("--no-commit")
    args.append(branch)
    return _run_git_remote_action(
        "git_merge",
        work_dir,
        args,
        f"merged {branch}",
        **kw,
    )


@_reg("git_restore")
def _act_git_restore(platform=None, **kw):
    """Restore an explicit file list (synchronous, destructive, files is required)."""
    work_dir = kw.get("dir", ".")
    files = _require_files(kw, "git_restore")
    staged = _coerce_bool(kw.get("staged"), False)
    source = _validate_git_arg("source", kw.get("source", ""), allow_empty=True)

    args = ["restore"]
    if staged:
        args.append("--staged")
    if source:
        args.extend(["--source", source])
    args.append("--")
    args.extend(files)
    _git_run(work_dir, *args, timeout=TIMEOUT_GIT_QUICK)
    return _ok(f"restored: {' '.join(files)}")


@_reg("git_unstage")
def _act_git_unstage(platform=None, **kw):
    """Unstage an explicit file list (synchronous, files is required)."""
    work_dir = kw.get("dir", ".")
    files = _require_files(kw, "git_unstage")
    _git_run(work_dir, "restore", "--staged", "--", *files, timeout=TIMEOUT_GIT_QUICK)
    return _ok(f"unstaged: {' '.join(files)}")


@_reg("git_stash")
def _act_git_stash(platform=None, **kw):
    """Manage stash (synchronous)."""
    work_dir = kw.get("dir", ".")
    op = kw.get("op", kw.get("stash_action", "push"))
    message = kw.get("message", "")
    files = kw.get("files") or []
    include_untracked = _coerce_bool(kw.get("include_untracked"), False)

    if op == "list":
        raw = _git_run(work_dir, "stash", "list", timeout=TIMEOUT_GIT_QUICK)
        return _ok(raw or "(no stashes)")
    if op in ("pop", "apply", "drop", "show"):
        ref = _validate_git_arg("ref", kw.get("ref", "stash@{0}"))
        args = ["stash", op]
        if op == "show":
            args.append("--stat")
        args.append(ref)
        raw = _git_run(work_dir, *args, timeout=TIMEOUT_GIT_LOCAL_SLOW)
        return _ok(raw or f"stash {op}: {ref}")
    if op != "push":
        return _err("git_stash op options: push/list/pop/apply/drop/show")

    args = ["stash", "push"]
    if include_untracked:
        args.append("--include-untracked")
    if message:
        args.extend(["-m", message])
    if files:
        args.append("--")
        args.extend(files)
    raw = _git_run(work_dir, *args, timeout=TIMEOUT_GIT_LOCAL_SLOW)
    return _ok(raw or "stash saved")


@_reg("git_tag")
def _act_git_tag(platform=None, **kw):
    """List or create tags (synchronous)."""
    work_dir = kw.get("dir", ".")
    tag = _validate_git_arg("tag", kw.get("tag", ""), allow_empty=True)
    ref = _validate_git_arg("ref", kw.get("ref", "HEAD"))
    message = kw.get("message", "")
    delete = _coerce_bool(kw.get("delete"), False)

    if delete:
        if not tag:
            return _err("git_tag delete requires tag parameter")
        _git_run(work_dir, "tag", "-d", tag, timeout=TIMEOUT_GIT_QUICK)
        return _ok(f"tag deleted: {tag}")
    if tag:
        args = ["tag"]
        if message:
            args.extend(["-a", tag, ref, "-m", message])
        else:
            args.extend([tag, ref])
        _git_run(work_dir, *args, timeout=TIMEOUT_GIT_QUICK)
        return _ok(f"tag created: {tag}")
    raw = _git_run(work_dir, "tag", "--list", timeout=TIMEOUT_GIT_QUICK)
    return _ok(raw or "(no tags)")


# ============================================================
# Git remote operations — time-consuming operations (asynchronous)
# ============================================================


@_reg("git_clone")
def _act_git_clone(platform=None, **kw):
    """Clone a remote repository (asynchronous; large projects may take several minutes).

    Supports GitHub mirror sources (solves access issues in mainland China):
      Set mirror="https://hub.fastgit.xyz"
      Automatically replaces github.com in repo_url with the mirror address.

    Submits a background task and automatically pushes TaskStatusNotification to the MCP client when complete.
    """
    url = kw["repo_url"]
    work_dir = kw.get("dir", ".")
    branch = _validate_git_arg("branch", kw.get("branch", ""), allow_empty=True)
    mirror = kw.get("mirror", "")

    # GitHub mirror replacement — replace only domain (netloc), do not contaminate path
    if mirror and "github.com" in url.lower():
        from urllib.parse import urlparse, urlunparse
        parsed = urlparse(url)
        # Replace only when netloc contains github.com
        if "github.com" in parsed.netloc.lower():
            mirror_netloc = mirror.rstrip("/").replace("https://", "").replace("http://", "")
            parsed = parsed._replace(netloc=mirror_netloc, scheme="https")
            url = urlunparse(parsed)

    target_dir = os.path.join(work_dir, url.split("/")[-1].replace(".git", ""))
    _resolve_safe_dir(work_dir)

    def _do_clone(**_kw):
        args = ["clone"]
        if branch:
            args.extend(["-b", branch])
        args.append(url)
        args.append(target_dir)
        _git_run(work_dir, *args)
        return _ok(f"cloned to {target_dir}")

    task_id, status = _submit_git_task("git_clone", _do_clone, **kw)
    if status.get("status") != "ok":
        return status
    resp = _ok(f"clone task {task_id} | url: {url} | target: {target_dir}")
    resp["task_id"] = task_id
    return resp


@_reg("git_push")
def _act_git_push(platform=None, **kw):
    """Push to remote (asynchronous, single attempt)."""
    work_dir = kw.get("dir", ".")
    remote = _validate_git_arg("remote", kw.get("remote", "origin"))
    branch = _validate_git_arg("branch", kw.get("branch", ""), allow_empty=True)

    def _do_push(**kw2):
        cancel_check = kw2.get('_cancellation_check')
        if cancel_check:
            cancel_check()
        args = ["push", remote]
        if branch:
            args.append(branch)
        _git_run(work_dir, *args, timeout=TIMEOUT_GIT_FETCH_PULL)
        return _ok(f"pushed to {remote}{'/' + branch if branch else ''}")

    tid, resp = _submit_git_task("git_push", _do_push, **kw)
    if resp.get("status") == "ok":
        resp.setdefault("task_id", tid)
    return resp


@_reg("git_push_retry")
def _act_git_push_retry(platform=None, **kw):
    """Automatically retry push in the background until success or max attempts.

    Retry every N seconds (default 300 seconds = 5 minutes), max M attempts (default 12 attempts = 1 hour).
    Submits a background task; each step result automatically pushes TaskStatusNotification to the MCP client.
    """
    work_dir = kw.get("dir", ".")
    remote = _validate_git_arg("remote", kw.get("remote", "origin"))
    branch = _validate_git_arg("branch", kw.get("branch", ""), allow_empty=True)
    # Default 5-minute interval, 12 attempts ≈ 1 hour
    interval = int(kw.get("retry_interval", RETRY_INTERVAL_GIT_PUSH))
    max_retries = int(kw.get("max_retries", MAX_RETRIES_GIT_PUSH))

    def _do_retry_push(**kw2):
        progress_cb = kw2.get('_progress_callback')
        cancel_check = kw2.get('_cancellation_check')

        last_error = None
        for attempt in range(1, max_retries + 1):
            if cancel_check:
                cancel_check()

            try:
                args = ["push", remote]
                if branch:
                    args.append(branch)
                _git_run(work_dir, *args, timeout=TIMEOUT_GIT_FETCH_PULL)

                if progress_cb:
                    progress_cb(100, f"pushed to {remote} (attempt {attempt})")
                return _ok(f"pushed to {remote}{'/' + branch if branch else ''} (attempt {attempt})")

            except RuntimeError as e:
                last_error = e
                logger.warning("push failed (attempt %s/%s): %s", attempt, max_retries, e)

                if progress_cb:
                    pct = (attempt / max_retries) * 100
                    if attempt < max_retries:
                        eta_total = (interval * max_retries) // 60
                        progress_cb(pct, f"attempt {attempt} failed: {str(e)[:80]} | retry in {interval}s | eta ~{eta_total}min")
                    else:
                        progress_cb(pct, f"max retries ({max_retries}) reached, push failed")

                if attempt < max_retries:
                    time.sleep(interval)

        eta_total = (interval * max_retries) // 60
        raise RuntimeError(f"push failed after {max_retries} retries (~{eta_total}min): {last_error}")

    tid, resp = _submit_git_task("git_push_retry", _do_retry_push, **kw)
    if resp.get("status") != "ok":
        return resp

    eta_total = (interval * max_retries) // 60
    resp_message = f"auto-retry push task {tid} | interval: {interval}s | max: {max_retries} | eta: ~{eta_total}min"
    resp = _ok(resp_message)
    resp["task_id"] = tid
    return resp