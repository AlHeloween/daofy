# Tool Help — Tool Help Reference

> Version: v1.1 | Last updated: 2026-07-15

---

## Contents

1. [Overview](#1-overview)
2. [Usage](#2-usage)
3. [Returned Content](#3-returned-content)
4. [Workflow Scenarios](#4-workflow-scenarios)
5. [Tool List](#5-tool-list)

---

## 1. Overview

`tool_help` provides **complete help documentation** for any MCP tool in Daofy. When you are unsure how a tool is used in detail, call this tool to get everything: parameter descriptions, examples, trigger words, collaboration chains.

### In one line

> Unsure how a tool is used? → `tool_help(tool_name="...")`

### Relationship to the `docs/` documents

- `tool_help` returns the **inline condensed** help: parameter descriptions, examples, trigger words, collaboration chains
- `docs/*.md` provides the **complete standalone** documentation: workflow scenarios, technical architecture, troubleshooting

The two routes complement each other; `tool_help` uses fewer tokens and suits quick lookups.

---

## 2. Usage

### Basic call

```python
# Get complete help for the delphi_project tool
tool_help(tool_name="delphi_project")

# Get complete help for the delphi_file tool
tool_help(tool_name="delphi_file")
```

### Parameters

| Parameter | Required | Description |
|------|------|------|
| `tool_name` | ✅ | Tool name. Must be a registered MCP tool name |

### Queryable tools

| Tool | Description |
|--------|------|
| `delphi_project` | Full project lifecycle management |
| `delphi_kb` | Knowledge base search / management |
| `delphi_file` | Dedicated Delphi file operations |
| `manage_component` | DFM component management |
| `check_environment` | Build environment diagnostics |
| `async_task` | Asynchronous task management |
| `package` | Component package management |
| `get_coding_rules` | Delphi coding rules |
| `code_hosting` | Git operations / code hosting |
| `tool_help` | This tool itself |
| `experience` | Experience memory management |
| `daofy_update` | Daofy self-update |

---

## 3. Returned Content

The information `tool_help` returns contains the following fields:

| Field | Description |
|------|------|
| `summary` | One-line tool summary |
| `description` | Detailed description |
| `triggers` | Keywords that make the AI trigger this tool automatically |
| `constraints` | Usage constraints (for example: git must not be run through bash) |
| `actions` | Every available action, with its description |
| `action_params` | Per-action parameter details (required / optional / default) |
| `examples` | Usage examples |
| `workflow` | Typical workflow |
| `workflow_hints` | Scenario-based workflow suggestions |

---

## 4. Workflow Scenarios

### When the AI is unfamiliar with a tool

```
tool_help(tool_name="delphi_file")    # View all actions of delphi_file
    ↓
delphi_file(action="read", ...)       # Use according to the help
```

### Reviewing a tool's full parameters

```python
# When you need the parameters of delphi_project's compile action
tool_help(tool_name="delphi_project")
# → Returns compile's required/optional parameters, default values, and examples
```

### Onboarding

```python
# First look at check_environment
tool_help(tool_name="check_environment")

# Then look at delphi_project
tool_help(tool_name="delphi_project")
```

### Deploying to a device

```python
# View deploy action parameters
tool_help(tool_name="delphi_project", action="devices")

# Enumerate devices
delphi_project(action="devices", target_platform="iosdevice64")

# Deploy
delphi_project(action="deploy", project_path="App.dproj", target_platform="iosdevice64")
```

---

## 5. Tool List

Daofy registers 12 MCP tools:

| # | Tool | Domain |
|---|--------|--------|
| 1 | `delphi_project` | Build / configure / audit / deploy |
| 2 | `delphi_kb` | Knowledge base search / build |
| 3 | `delphi_file` | Delphi file operations |
| 4 | `manage_component` | DFM component management |
| 5 | `check_environment` | Environment diagnostics |
| 6 | `async_task` | Background tasks |
| 7 | `package` | Component package management |
| 8 | `get_coding_rules` | Coding rules |
| 9 | `code_hosting` | Git / code hosting |
| 10 | `tool_help` | Help documentation |
| 11 | `experience` | Experience memory |
| 12 | `daofy_update` | Self-update |