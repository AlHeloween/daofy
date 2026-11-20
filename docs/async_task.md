# Async Task — Asynchronous Task Management

> Version: v1.0 | Last updated: 2026-06-08

---

## Contents

1. [Overview](#1-overview)
2. [Action Quick Reference](#2-action-quick-reference)
3. [Status — Query progress](#3-status--query-progress)
4. [Result — Fetch the result](#4-result--fetch-the-result)
5. [List — List tasks](#5-list--list-tasks)
6. [Cancel — Cancel a task](#6-cancel--cancel-a-task)
7. [Start — Start a task](#7-start--start-a-task)
8. [Notification Mechanism](#8-notification-mechanism)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Overview

`async_task` manages the **background asynchronous tasks** in Daofy. Long-running operations (knowledge base builds, document scans, vector index builds) execute in the background and do not block the MCP channel. With this tool you can query progress, fetch the result or cancel a task.

> A knowledge base build is normally triggered automatically by `delphi_kb(action="build", async_mode=True)`; there is no need to call `async_task(action="start")` by hand.

---

## 2. Action Quick Reference

| Action | Purpose |
|--------|------|
| `start` | Start an asynchronous task (normally triggered automatically, no manual call needed) |
| `status` | Query task status (progress percentage + state) |
| `result` | Fetch the task result |
| `list` | List every task |
| `cancel` | Cancel a running task |

---

## 3. Status — Query progress

Queries the execution progress of an asynchronous task. Both **long polling** (wait for a while, then return) and **short polling** (return immediately) are supported.

```python
# Short polling (returns immediately)
async_task(action="status", task_id="task_xxx")

# Long polling (wait up to 30 seconds, return immediately when a result is available)
async_task(action="status", task_id="task_xxx", long_poll_seconds=30)
```

**Returned information**:
- `status`: pending/running/completed/failed/cancelled
- `progress`: 0~100 percentage
- `message`: description of the current stage

### Long polling

```
Long polling ≤30 seconds → MCP request channel times out after about 60s
  ↓ timeout
Switch to short polling → poll once every N seconds
```

---

## 4. Result — Fetch the task result

Fetches the final result once the task has completed.

```python
async_task(action="result", task_id="task_xxx")
```

---

## 5. List — List tasks

Lists every asynchronous task, completed and running alike.

```python
async_task(action="list")
```

---

## 6. Cancel — Cancel a task

Cancels a running task.

```python
async_task(action="cancel", task_id="task_xxx")
```

---

## 7. Start — Start a task

Long-running operations normally trigger an asynchronous task automatically, so there is no need to call `start` by hand. To start one manually:

```python
async_task(action="start",
    task_type="build_embedding",
    task_params={"project_path": "..."})
```

**Supported task types**:

| task_type | Description |
|-----------|------|
| `build_knowledge_base` | Build the Delphi source knowledge base |
| `build_thirdparty_knowledge_base` | Build the third-party library knowledge base |
| `init_project_knowledge_base` | Initialize the project knowledge base |
| `build_document_knowledge_base` | Build the document knowledge base |
| `build_embedding` | Build the vector index |

---

## 8. Notification Mechanism

Daofy supports **TaskStatusNotification push notifications**:

> When any asynchronous task (knowledge base build, document scan, embedding, …) completes, fails or is cancelled, a `TaskStatusNotification` is pushed to the MCP client automatically — **no polling required**.

The AI Agent only needs to:
1. Start the task (triggered automatically or by hand)
2. Wait for the push notification
3. Fetch the result through `async_task(action="result", task_id="...")`

---

## 9. Troubleshooting

| Symptom | Cause | Fix |
|------|------|------|
| Task stays pending for a long time | Insufficient resources | Check system resources and retry later |
| Task failed | The build process hit an error | Read the error message with `action="result"` |
| Task is stuck | Large data volume | Wait patiently, or `cancel` and retry |
| No push notification received | The MCP client does not support it | Poll `action="status"` manually |