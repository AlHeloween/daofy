---
name: delphi-automation-script-generation
description: >-
  Generate automation test scripts from Delphi source/DFM analysis. Covers native dialog handling,
  composition strategies, and model-script communication.
---

# Script Generation Workflow

<!-- @when: Generating automation scripts from Delphi source/DFM analysis -->
<!-- @chain: after=workflow.md, before=script-schema.md -->

MCP resource URI: `delphi://automation/script-generation-workflow`.

## Client Boundary

This is a Delphi script generation resource from Daofy MCP Server for external MCP clients.
DaofyCoding does not read `delphi://` resources, nor does it use Daofy MCP Server as a runtime dependency.
In DaofyCoding, Delphi/Lazarus/other languages use the `automation_run` provider specified by the language profile;
use host `structured_content` only when structured queries are needed; script execution and process inspection use native host capabilities;
other languages use explicit steps and `external-driver` and do not apply Delphi-specific script fields.

External MCP clients generate `automate_delphi` scripts according to this document. When the connected client is DaofyCoding,
the Server hides `automate_delphi`, `delphi_rtti`, and `structured_content` from the tool catalog; do not attempt to bypass the hiding policy—use native DaofyCoding tools directly.

## Core Principles

1. **Source-driven**: All targets (control names, property paths) must be extracted from `.pas/.dfm` source; do not guess or rely on memory.
2. **Read source files first → then write scripts**: Before generating a script, you must read the target `.pas` and `.dfm`.
3. **Prefer pipe commands**: For controls inside the Delphi process, prefer pipe RTTI commands (`rget`/`click`/`waitfor`, etc.); fall back to `uia.xxx` or OCR when they cannot cover the case.
4. **Non-injection black-box**: `uia.xxx` commands use the cross-process UIA protocol and do not modify the application under test.

## Workflow

### Step 1: Read Source

Read `.dfm` and `.pas`, and extract the following information:

| Source Element | Extracted Content | Used in Script |
|----------|---------|-----------|
| `object BtnSave: TButton` | Name `BtnSave` | `target: "BtnSave"` |
| `Caption = '保存'` | Caption string | `expected`, `assert_expr` |
| `OnClick = BtnSaveClick` | Event handler name | Verify its trigger through `StatusBar.Caption` |
| `DataSource1.DataSet` | Data binding | Assert through `DataSource1.DataSet.Modified` after saving |
| `TMyForm = class(TForm)` | Form class name | `goto "TMyForm"` |
| `ActionList / PopupMenu` | Named actions/items | `click "cbMenus@打开工程..."` |

**Black-box testing note**: Non-intrusive testing only reads `.dfm`/`.pas` during script generation. Runtime scripts may only use `uia.xxx`/`click`/`type`/`key`/`waitfor`/`capture`—RTTI write commands (`rcall`/`rset`) must not be used.

### Step 2: Determine Dialog Strategy

Select appropriate commands for each dialog or window in the test according to the UI automation decision flow. See `delphi://automation/capability-matrix` for the complete capability selection matrix.

### Step 3: Assemble Script

1. Specify the `App.exe` path.
2. Set `keep_alive=true` for multi-step flows.
3. Arrange steps by `phase: "perceive | execute | verify | wait | rebuild"`.
4. Add an `expected` description and `assert_expr` to every verification step.
5. Functional cases must cover boundary scenarios: normal path, failure/cancel path, empty/invalid/oversized input, extreme count, missing permission or dependency, asynchronous timeout, control rebuild, DPI/layout, file dialog fallback, etc., as applicable; write the reason in `note` for inapplicable items.
6. Save reusable passing scripts under the tested project root `Tests\<测试类型>\`.

### Step 4: Execute

```python
automate_delphi(
    app_path="C:/App/App.exe",
    keep_alive=True,
    stop_on_failure=True,
    script=[...]
)
```

After execution, check:

```text
result.status
result.resolved_action
result.report.first_failure
result.report.solution
result.report.steps
```

Failure signal responses:

| Signal | Response Strategy |
|------|---------|
| `target_not_found` | Run `formsum/dumpstate`; update the script target or fix the missing control |
| `property_not_found` | Run `rinspect`; update the property path |
| `method_not_found` (error reported by rcall/run_tests) | Run `rinspect`(with visibility=private,protected,public,published to view all methods); confirm the method name and visibility |
| `assertion_failed` | Compare the expected behavior derived from source with the actual value |
| `timeout` | Capture state, run `msgscan/formsum`, then decide whether to wait or fix code |
| `command_error` | Check `response_data`; prefer low-risk evidence commands |
| `capture_failed` | Check whether snapshots_dir is writable; ensure the window is visible |
| `uia_error` | Run `uia.scan` to verify the UIA tree; use inspect.exe to confirm control identification |
| `uia_not_available` | `pip install daofy-for-delphi[uia]`, restart the service |
| `skipped` | Fix the preceding failure before rerunning dependent steps |

If the expected behavior derived from source is not met, switch to coding mode:

1. `get_coding_rules(section="writing")`
2. `delphi_file(action="read", ...)`
3. `delphi_file(action="write", edits=[...])`
4. `delphi_file(action="format", ...)`
5. `delphi_project(action="compile", project_path=...)`
6. Rerun the same automation script

## Final Output Format

When reporting to the user, include:

```markdown
**Script**
- File or inline steps
- app_path and resolved_action

**Run Result**
- Total/passed/failed/skipped
- Elapsed time
- First failure (if any)

**Solution**
- Script adjustment or code repair
- Specific file/command changes

**Verification**
- Compile result
- Rerun result
```

