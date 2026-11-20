# Daofy Update — Daofy Self-Update Management

> Version: v1.1 | Last updated: 2026-07-05

---

## Table of Contents

1. [Overview](#1-overview)
2. [Action Quick Reference](#2-action-quick-reference)
3. [Usage](#3-usage)
4. [Workflow Scenarios](#4-workflow-scenarios)
5. [Troubleshooting](#5-troubleshooting)

---

## 1. Overview

`daofy_update` manages version checking and updating for the Daofy MCP Server itself. It supports updates for two installation modes:

| Installation Method | Update Method |
|---------|---------|
| **git clone** source installation | `git pull` to fetch the latest code |
| **pip install** installation | Prompts to use `pip install --upgrade daofy-for-delphi` |

### Automatic Check Mechanism

When Daofy starts, it automatically checks the latest GitHub Release in the background. When a new version is available, it intelligently notifies the AI through tool responses.

> After the AI sees an update notification, it should proactively ask the user whether they want to update.

### Hard Constraints

- After the update is complete, you need to **restart Daofy or the AI Agent** for the new version to take effect

---

## 2. Action Quick Reference

| Action | Purpose | Required Parameters |
|--------|------|---------|
| `check` | Check the latest GitHub Release | — |
| `check_retry` | Force background retry check after failure (returns task_id) | — |
| `update` | Execute git pull to update code | — |
| `update_retry` | Execute git pull with automatic retry (after failure, retry every retry_interval seconds, up to max_retries times) | — |
| `version` | Display current version number and installation method | — |

---

## 3. Usage

### 3.1 `check` — Check for Updates

Checks the latest GitHub Release and returns current version/latest version/whether an update is available.

```python
daofy_update(action="check")
```

**Returned Information**:
- Current installed version
- Latest GitHub version
- Whether an available update exists
- Installation method (git/pip)

### 3.2 `update` — Execute Update

```python
# git installation mode: automatically git pull
daofy_update(action="update")
```

- **git installation mode**: Automatically executes `git pull` to fetch the latest code
- **pip installation mode**: Does not update automatically; prompts the user to run `pip install --upgrade daofy-for-delphi`

### 3.3 `version` — View Version

```python
daofy_update(action="version")
```

Returns:
- Current version number
- Installation method (git/pip)
- Last update date

---

## 4. Workflow Scenarios

### Received an Update Notification

```
AI: "A new Daofy version v2026.07.05 is available; current version v2026.06.22. Do you want to update?"
User: "Yes, update it"
AI: daofy_update(action="check")       # Confirm version
     daofy_update(action="update")      # Execute update
     "Update complete. Please restart Daofy or the AI Agent for the new version to take effect."
```

### Manually Check Version

```python
# View current version
daofy_update(action="version")

# Check whether an update is available
daofy_update(action="check")
```

### Updating for pip Installation Users

```python
# 1. Check version
daofy_update(action="check")
# → Returns: current v2026.06.22, latest v2026.07.05, installation method pip

# 2. Manually update
# pip install --upgrade daofy-for-delphi
```

---

## 5. Troubleshooting

| Symptom | Cause | Solution |
|------|------|------|
| `update` fails | Uncommitted local changes in git installation mode | First use `code_hosting(action="git_status")` to check, then commit or stash and retry |
| Tools do not take effect after update | Daofy process has not been restarted | Restart the AI Agent or MCP Server |
| pip users call `update` | Installation method does not support git pull | Use `pip install --upgrade daofy-for-delphi` |
| `check` returns network error | Cannot access GitHub | Check network/proxy settings |
| Version number displays abnormally | Non-standard installation | Confirm the installation method and reinstall |

### Common Post-Update Actions

```json
{
  "Update Type": "Action",
  "git pull": "Restart Daofy process",
  "pip upgrade": "Restart AI Agent client",
  "Config file changes": "Check whether config/*.json needs merging"
}
```