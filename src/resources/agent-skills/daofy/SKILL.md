---
name: daofy
description: >-
  Daofy for Delphi usage skill (loaded on demand). Use when you actually need to call delphi_file to write/modify Delphi files,
  need to run compilation/audit/automated tests, or encounter clients such as Trae that only expose a run_mcp wrapper.
  The mandatory routing rule (Delphi files must use delphi_file) is guaranteed at all times by the Daofy Rule and initialize.instructions; this skill only covers "how to use".
---

<!-- daofy-managed-skill: true -->
<!-- daofy-managed-skill-version: 2026.08.06 -->

# Daofy for Delphi — Usage Skill (loaded on demand)

> This skill is an **on-demand** detailed usage manual, not a persistent rule.
> The mandatory routing constraint (Delphi files must use `delphi_file`; built-in Read/Edit/Write/grep are prohibited) is already guaranteed at all times by
> the Daofy Rule (installed into the client's rules directory) and the MCP `initialize.instructions`; it is not repeated here
> to avoid duplicate injection with the Rule. This skill only supplements the "client wrappers" and "workflows" that the Rule does not cover.

## Client wrappers

- Clients that expose MCP tools directly: when calling `delphi_file`, pass only Daofy parameters, e.g.
  `action/file_path/start_line/end_line`.
- Clients such as Trae that only expose `run_mcp`: the outer layer takes `server_name` and `tool_name`, and only the inner
  `args` holds the Daofy parameters; `server_name` is the Daofy service alias in that client's MCP configuration,
  fill it in according to the actual configuration — it is not a fixed Daofy value; do not mix `server_name/tool_name`
  into the `delphi_file` parameter object.

```python
run_mcp({
  "server_name": "<client-configured-daofy-server-name>",
  "tool_name": "delphi_file",
  "args": {
    "action": "read",
    "file_path": "C:\\path\\Unit1.pas",
    "start_line": 1,
    "end_line": 100
  }
})
```

## Workflow

1. **To determine the Delphi compiler/environment, call `check_environment(action="detect")`**
   (call `action="check"` before the first compile), and **do not** use the shell to run probe commands such as
   `where dcc32` / `dcc64 --version` — compiler paths/versions are uniformly detected and cached by Daofy.
   If you are unsure about tool parameters, use `tool_help` or `get_coding_rules` instead.
2. When reading Delphi files, call `delphi_file(action="read", file_path=...)`.
3. When writing Delphi files, use `delphi_file(action="write", edits=[...])`; merge multiple changes to the same
   file into a single write.
4. After writing, call `delphi_file(action="format", file_path=...)` as needed.
5. For compilation, auditing, layout, and runtime uses checks, use `delphi_project`.
6. For automated testing, use `automate_delphi`; when you need the complete workflow, read
   `delphi://automation/workflow`.
7. For in-depth coding/compilation/review standards, use `get_coding_rules(section=..., examples=...)` to load them on demand; do not pile standards into the persistent context.

## On-demand loading of coding rules

`get_coding_rules` supports on-demand loading along the two dimensions `section` and `examples`, avoiding injecting all rules at once:

```python
# Load only the code-writing rules
get_coding_rules(section="writing")

# Load only a single subsection
get_coding_rules(section="delphi_file_write_rule")

# Load code-writing rules + naming convention examples
get_coding_rules(section="writing", examples="naming")

# Load compilation rules + formatting examples
get_coding_rules(section="compile", examples="formatting")
```

**Common sections**: `writing`, `compile`, `review`, `agent_rules`, `kb_search`,
`delphi_file_write_rule`, `delphi_file_dirty_flag`, `delphi_file_output_format`,
`delphi_file_usage_tips`

**Common examples**: `naming`, `formatting`, `documentation`, `error-handling`

## Chinese content in DFM

When editing DFM files, Chinese content (Caption, Text, Hint, etc.) **is written as-is, with no escaping needed**:

```python
# ✅ Correct: write Chinese directly
delphi_file(action="write", file_path="MainForm.dfm", edits=[
    {"start_line": 5, "end_line": 5, "new_text": '    Caption = "中文标题"'}
])

# ❌ Wrong: do not manually escape Unicode
delphi_file(action="write", file_path="MainForm.dfm", edits=[
    {"start_line": 5, "end_line": 5, "new_text": '    Caption = \u4e2d\u6587\u6807\u9898'}
])
```

Rationale: `delphi_file` automatically handles encoding (GBK/UTF-8/BOM) when reading and writing; Chinese content is written as-is.

## Relationship with other IDE skills

If the Kai/RAD Studio IDE skill is also present, still obey Daofy's tool
routing rules for Delphi files first. Daofy's `delphi_file` handles encoding detection, backup, DFM conversion, dirty flags, and edit guard;
if the Daofy tools are missing, refresh the MCP connection or ask the user — do not silently fall back to ordinary file editing.

## Scope not restricted

Daofy MCP Server's own Python, Markdown, tests, and configuration files can be handled by the current Agent's normal code
editing process; the direct read/write restriction in this skill applies only to Delphi source and project files.

