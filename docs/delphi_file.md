# Delphi File — Dedicated Operations for Delphi Files

> Last updated: 2026-07-06

`delphi_file` is a dedicated tool in Daofy for reading and writing Delphi source and form files. It supports `.pas`, `.dpr`, `.dpk`, `.dfm`, `.fmx`, `.inc`, `.dproj`, and automatically handles encoding detection, `__history` backups, DFM/FMX binary conversion, and same-file read/write mutual exclusion.

Tool routing rules: When an AI Agent sees `.pas/.dfm/.dproj/.dpk/.dpr/.inc/.fmx` paths, even if it is only reading, it should call MCP `delphi_file`. Do not use the Agent's built-in `Read/Edit/Write`, `apply_patch`, shell, or Python to directly read/write these files.

## Agent Skill Auto-Sync

When the MCP Server starts, it makes a best effort to sync the Agent Skill provided by Daofy to the user-level shared directory:

```text
%USERPROFILE%\.agents\skills\daofy\SKILL.md
```

This skill is used to support clients that support Agent Skills, reinforcing the routing rules that Delphi files must go through `delphi_file` and Git must go through `code_hosting`. During sync, `.daofy_skill_manifest.json` is written to record the hashes of managed files. On subsequent startups, if the packaged skill has an update, it will be updated automatically when the installed file has not been manually modified by the user. If it detects that the user has modified an installed file, Daofy will skip that file and log a warning, without overwriting the user's content.

It can be controlled via environment variables:

| Variable | Description |
|------|------|
| `DAOFY_AGENT_SKILL_INSTALL=off` | Disable Agent Skill auto-sync at startup |
| `DAOFY_AGENT_SKILLS_DIR=<path>` | Specify the shared skills root directory, default `%USERPROFILE%\.agents\skills` |

## Action Quick Reference

| Action | Purpose |
|--------|------|
| `read` | Read by path, or locate by class name/function name/record and then read |
| `replace` | ⭐ Recommended replacement, replace by line range (requires `old_content` validation) |
| `insert` | ⭐ Recommended insertion, insert at anchor line (requires `old_content` validation) |
| `delete` | ⭐ Recommended deletion, delete by line range (requires `old_content` validation) |
| `write` | Compatible write interface, uses `edits=[...]` (new calls should prefer `replace`/`insert`/`delete`) |
| `format` | Format with pasfmt |
| `backup` | Create, list, restore `__history` backups |
| `uses` | Add or remove units in the uses clause |
| `grep` | Regex search + multi-level filtering + replacement, supports inline `/pattern/flags` syntax |

## Line Number Rules

All line number parameters and output of `read`/`write`/`uses` are **1-indexed inclusive**.

| Example | Meaning |
|------|------|
| `start_line=1` | Start from line 1 |
| `start_line=5, end_line=10` | Lines 5 through 10, inclusive |
| `write` without `end_line` | Replace from `start_line` to end of file |

## Read

```python
delphi_file(action="read", file_path="Unit1.pas")
delphi_file(action="read", file_path="Unit1.pas", start_line=5, end_line=15)
delphi_file(action="read", file_path="Unit1.pas", show_line_numbers=True)
```

Search by type:

```python
delphi_file(action="read", search_type="class", type_name="TButton")
delphi_file(action="read", search_type="function", function_name="Create")
delphi_file(action="read", search_type="record", record_name="TPoint")
```

Project source search requires a project path:

```python
delphi_file(
    action="read",
    search_type="class",
    type_name="TMainForm",
    search_in="project",
    project_path="Project.dproj")
```

`search_in` options: `all`, `delphi`, `project`, `thirdparty`. `project` requires `project_path`.

Example first line of read output:

```text
# encoding: utf-8, 1-index