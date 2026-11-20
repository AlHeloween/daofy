# Daofy Automated Testing Guide

LLM-driven Delphi automated testing framework.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                           LLM                               │
│  Analyze requirements → Plan steps → Verify results → Generate report │
└──────────┬──────────────────────────────────────┬──────────┘
           │ automate_delphi tool                   │ delphi_file / ...
           ▼                                        ▼
┌──────────────────────┐              ┌──────────────────────┐
│   Python service layer│              │   Auxiliary tools    │
│  automation_service   │              │   rget / rset /       │
│  ─ Process pool mgmt  │              │   delphi_kb etc.      │
│  ─ Pipe communication │              │                      │
│  ─ ERROR_MORE_DATA    │              └──────────────────────┘
│    Loop read          │
└──────────┬────────────┘
           │ Named pipe \\.\pipe\daofy_auto
           ▼
┌─────────────────────────────────────────────────────────────┐
│                   Delphi program (AUT)                       │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  DaofyAutomation unit (linked into app under test)   │   │
│  │  ─ Pipe thread + JSON protocol                       │   │
│  │  ─ Vcl.DaofyAutomation / Fmx.DaofyAutomation         │   │
│  │  ─ RTTI operations (rget/rset/rcall/rinspect)        │   │
│  │  ─ Screenshot (2D PaintTo / 3D GPU / dialog BitBlt)  │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## Enablement Guide (for Delphi Developers)

> This section is for **developers who need to enable automated testing in their own Delphi projects**.
> After following the steps, your program can be remotely controlled and tested by the `automate_delphi` tool.

### Prerequisite File List

Automation framework files are located in the Daofy installation directory under `tools/auto/`:

| File | Required? | Purpose |
|------|--------|------|
| `DaofyAutomation.Base.pas` | ✅ Required | Named pipe protocol, command dispatch, asynchronous result cache |
| `Vcl.DaofyAutomation.pas` | Required for VCL projects | VCL control lookup, screenshots, RTTI operations |
| `Fmx.DaofyAutomation.pas` | Required for FMX projects | FMX control lookup, screenshots, RTTI operations |
| `DaofyAutomation.RttiDiscovery.pas` | Optional | RTTI capability discovery (used by the `delphi_rtti` tool) |
| `DaofyAutomation.RttiAttributes.pas` | Optional | AI annotation attribute declarations |
| `DaofyAutomation.CallGraph.pas` + `StackTrace.pas` | Optional | `callgraph` / `callgraph_diff` / `callgraph_path` / `callgraph_impact` and purpose-layer `callgraph_*` diagnostic commands |

> ⚠️ `DaofyAutomation.Base.pas` must also be referenced by the project (the VCL/FMX units depend on it).

### Step 1: Add `tools/auto` to the Project Search Path

In the Delphi IDE, open the project → **Project → Options → Delphi Compiler → Search path**, and add:

```
$(DaofyRoot)\tools\auto
```

To use `callgraph`, also add:

```
$(DaofyRoot)\tools\stacktrace
```

`callgraph` supports `direction=callees|callers`, `project_only=true`, `exclude_prefixes`, `include_prefixes` filtering, and `edge_limit` output limits; the response includes `edge_count`, `returned_count`, and `truncated`; each edge includes `call_addr`, `call_file`, and `call_line` for locating where the call occurs (empty/0 when line number information is unavailable), and includes `category`, `from_category`, and `to_category` (`project|thirdparty|framework|system|unknown`). `callgraph_path` accepts `source`, `target`, `max_depth`, `max_paths`, and `include_prefixes`, and returns `found` and `paths`; not finding a path is not an error. `callgraph_diff` uses baseline JSON or a `baseline_path` snapshot file to compare added/removed/unchanged at the edge level with the current call graph; by default `compare_by=name` avoids address drift from recompilation, and `compare_by=addr|full` can be used when necessary; `save_as` can save the current snapshot. `save_as` must be a relative JSON path under `snapshots_dir`; `baseline_path` and file-based graph/impact inputs for purpose-layer commands must also resolve to within `snapshots_dir`. `callgraph_impact` accepts `functions`/`targets`, `file`+`line`/`locations`, and also accepts PR/diff-style `changes` (each item may contain `function` or `file`+`start_line/new_line/line`); it queries callers in batches and summarizes entry candidates and unresolved items. Script metadata for `callgraph_select_tests` can use `handler`/`entry`, `tags`, and `covers`/`functions`/`targets` to explicitly declare coverage scope. `callgraph_boundary_check` supports `from_prefix`/`to_prefix` prohibition rules, `exclude_from_prefixes`/`exclude_to_prefixes` exceptions, and `severity`/`message` output. `callgraph_refactor_check` outputs `safe_to_refactor`, `affected_targets`, `unresolved`, and a conservative risk level. `callgraph_orphan_candidates` accepts `symbols`, entry `entries`, and optional `test_prefixes`, distinguishing caller-less candidates from candidates called only by tests. `callgraph_explain_exception` can extract a function name from exception frames with address/offset/source and output upstream/downstream summaries. Purpose-layer commands also include `callgraph_failure_diag`.

Or use a relative path (assuming Daofy and the project are siblings):

```
..\daofy\tools\auto
```

> **Why?** After adding the directory to the search path, you do not need to write lengthy `in 'path\to\xxx.pas'` clauses in the `.dpr`; just write `uses Vcl.DaofyAutomation;`. All automation units will be resolved automatically.

### Step 2: Modify the `.dpr` File

In the `uses` clause of `program`, add the automation unit, and in the `begin..end.` block add `AutoStart`/`AutoStop` calls:

```pascal
program MyApp;

uses
  Vcl.Forms,
  Vcl.DaofyAutomation,          // ← Add (search path already configured, no in clause needed)
  MainForm in 'MainForm.pas';

begin
  Vcl.DaofyAutomation.AutoStart;    // ← Add: creates named pipe \\.\pipe\daofy_auto
  Application.Initialize;
  Application.CreateForm(TMainForm, MainForm);
  Application.Run;
  Vcl.DaofyAutomation.AutoStop;     // ← Add: cleans up pipe resources
end.
```

**FMX projects** should use `Fmx.DaofyAutomation`:

```pascal
uses
  FMX.Forms,
  Fmx.DaofyAutomation;          // ← FMX version

begin
  Fmx.DaofyAutomation.AutoStart;
  Application.Initialize;
  Application.CreateForm(TMainForm, MainForm);
  Application.Run;
  Fmx.DaofyAutomation.AutoStop;
end.
```

> ⚠️ `AutoStart` **must be called before** `Application.Initialize` to ensure the pipe is ready when the thread starts.

### Step 3: Compile and Verify the Pipe Is Ready

```bash
# Compile in the IDE (Ctrl+F9), or from the command line:
dcc32 MyApp.dproj
```

Start the compiled exe:

```bash
MyApp.exe
# Console program input: MyApp.exe arg1 arg2
```

Verify that the named pipe has been created:

```powershell
# Use PowerShell to check whether the pipe exists
[System.IO.Directory]::GetFiles("\\.\\pipe\\").Where({$_ -match "daofy_auto"})
```

If the output contains `daofy_auto`, the automation unit has been successfully integrated.

### Step 4: Run a Smoke Test to Confirm Communication

Send a simple `goto` + `capture` command through the `automate_delphi` tool to verify the complete chain:

```python
automate_delphi(
    app_path="C:\MyApp\Win32\Debug\MyApp.exe",
    keep_alive=True,
    script=[
        {"cmd": "goto", "target": "TMainForm", "note": "确认主窗体就绪"},
        {"cmd": "capture", "target": "smoke_001"},
        {"cmd": "exit"}
    ]
)
```

**Expected result**:
- Returns `status: "ok"`, `process_alive: false` (exits after exit)
- Generates `smoke_001.jpg` in the `docs/copyright/snapshots/` directory

If you receive `target_not_found`, first use `listwnd` to view the actual form class name:

```python
automate_delphi(
    app_path="C:\MyApp\Win32\Debug\MyApp.exe",
    script=[{"cmd": "listwnd"}]
)
```

### Verification Checklist

```
[ ] The 3 core .pas files in tools/auto/ exist and are readable
[ ] The search path includes the tools/auto directory
[ ] Vcl.DaofyAutomation / Fmx.DaofyAutomation has been added to the .dpr file
[ ] The AutoStart call is before Application.Initialize
[ ] Compilation passes (0 errors, 0 warnings)
[ ] The named pipe \\.\pipe\daofy_auto has been created after the process starts
[ ] The automate_delphi smoke test returns status=ok
```

### Common Integration Issues

| Issue | Cause | Fix |
|------|------|------|
| Compilation error `File not found: 'DaofyAutomation.Base.pas'` | Search path does not include `tools/auto` | Check Project Options → Search path |
| Compilation error `Duplicate resource` | The `.dpr` has both an `in` clause and search path reference | Use the search path consistently and remove the `in` clause |
| Process starts but `automate_delphi` cannot connect to the pipe | `AutoStart` was not called or was skipped due to an exception | Confirm that `AutoStart` runs before `Application.Initialize` |
| Windows Firewall popup | The exe listens on a pipe for the first time | Allow private network access |
| FMX startup crash | Missing FMX runtime DLLs | Ensure PATH contains the FMX runtime directory, or enable static linking |

---

## Quick Start (for AI Agents)

> The following content is for AI agents to write and execute automation test scripts after completing the enablement steps.

---

## Command Reference

### Navigation
```json
{"cmd": "goto", "target": "TMainForm"}
```
Activates the form with the specified class name or Name.

### Mouse Operations
```json
{"cmd": "click", "target": "BtnSave"}                  // RTTI click
{"cmd": "click", "target": "ListBox1@5,5"}             // Coordinate click (relative to control)
{"cmd": "rclick", "target": "EditName"}                // Right-click to open context menu
{"cmd": "dblclick", "target": "ListItem1"}             // Double-click
{"cmd": "hover", "target": "Panel1"}                   // Hover
{"cmd": "move", "target": "BtnSave"}                   // Move mouse to control center
{"cmd": "move", "x": "500", "y": "300"}                // Move mouse to screen coordinates
{"cmd": "drag", "source": "Slider1", "target": "TrackBar1"}  // Drag to target control
{"cmd": "drag", "source": "Header1", "x": "500", "y": "300"} // Drag to coordinates
```

### Keyboard Operations
```json
{"cmd": "type", "target": "EditName", "value": "张三"}        // Enter text
{"cmd": "key", "target": "EditName", "key": "Tab"}            // Press key
{"cmd": "key", "key": "Enter"}
{"cmd": "key", "key": "Esc"}
{"cmd": "key", "key": "F5"}
```
Supported key names: `Tab`, `Enter`, `Esc`, `Back`, `Del`, `Home`, `End`,
`Up`, `Down`, `Left`, `Right`, `Space`, `F1`~`F12`, single characters.

### Waiting
```json
{"cmd": "wait", "ms": "2000"}                                          // Fixed wait
{"cmd": "waitfor", "target": "BtnSave", "prop": "Enabled",            // Wait for condition to be met
                  "value": "True", "timeout": "5000", "interval": "100"}
```
`timeout` defaults to 5000ms, and `interval` defaults to 100ms. Nested properties are supported:
```json
{"cmd": "waitfor", "target": "ListBox1", "prop": "Items.Count", "value": "10", "timeout": "3000"}
```

### Screenshots
```json
{"cmd": "capture", "target": "test_001"}
```
Screenshots are saved to `snapshots_dir/{target}.jpg`. The best method is automatically selected internally:

| Scenario | Method |
|------|------|
| MessageBox/TaskDialog popup | `FindWindowW('#32770')` → GDI BitBlt → JPEG |
| FMX modal dialog | `TFmxFormState.Modal` detection → PaintTo |
| FMX 3D form | `TContext3D.CopyToBitmap` GPU readback |
| FMX 2D form | `TCustomForm.PaintTo(Canvas)` |
| VCL form | `GetWindowDC` + GDI BitBlt |

### Window Enumeration
```json
{"cmd": "listwnd"}
```
Returns the name/class/caption/active status of all windows:
```json
{"status": "ok", "data": "{\"windows\":[{\"name\":\"Form1\",\"class\":\"TForm1\",\"caption\":\"MyApp\",\"active\":\"true\"}]}"}
```

### Full Control Tree
```json
{"cmd": "dumpstate"}
```
Returns the complete control tree JSON through the pipe (including all control properties); no longer writes to a file.

### Popup Menus
```json
{"cmd": "dlgscan"}           // Scan popup menu items
{"cmd": "dlgclick", "target": "复制"}  // Click menu item
```

### MessageBox / Dialogs
```json
{"cmd": "msgscan"}                              // Scan popups
{"cmd": "msgclick", "target": "ok"}             // Click button (supports TaskDialog)
{"cmd": "msgclose", "target": "DaofyAuto"}      // Close popup (match by title)
{"cmd": "dlgfile", "path": "C:\\test.txt", "target": "open"}   // File dialog
{"cmd": "dlgfile", "target": "cancel"}          // Cancel file dialog
```

### RTTI Operations
```json
{"cmd": "rget", "target": "EditName", "prop": "Text"}                        // Read property
{"cmd": "rget", "target": "ListBox1", "prop": "Items.Count"}                 // Nested property
{"cmd": "rset", "target": "EditName", "prop": "Text", "value": "Hello"}      // Write property
{"cmd": "rcall", "target": "EditName", "method": "Clear"}                    // Call parameterless method
{"cmd": "rcall", "target": "ListBox1", "method": "Items.Add",               // Call method with parameters
         "params": ["Hello"]}
{"cmd": "rcall", "target": "Form1", "method": "Close"}                      // Close form
{"cmd": "rinspect", "target": "EditName"}                                    // Inspect member list
```

### Process Management
```json
{"cmd": "snapdir", "target": "D:\\screenshots\\"}    // Set screenshot directory
{"cmd": "exit"}                                        // Exit program
```

---

## Process Reuse Mode

**Problem**: Every call to `automate_delphi` has to start the exe, wait for pipe initialization, execute, and exit—repeated overhead is high.

**Solution**: `keep_alive=true` keeps the process resident:

```
# First time: start and keep alive
automate_delphi(app_path="MyApp.exe", script=[goto, capture], keep_alive=true)
→ Returns process_reused:false, process_alive:true

# Second time: reuse the existing process
automate_delphi(app_path="MyApp.exe", script=[click, capture])
→ Returns process_reused:true, process_alive:true

# Finally: send exit to terminate
automate_delphi(app_path="MyApp.exe", script=[exit])
→ Returns process_alive:false
```

The process pool is managed automatically:
- Automatically reuses the same `app_path`
- Automatically calls `kill()` after **5 minutes without calls**
- Automatically restarts on the next call after a process crash
- Returns `process_reused` / `process_alive` fields so the AI can perceive status

---

## Automation Test Process Template

### Basic Process
```
1. Start the program (keep_alive=true)
2. goto activates the target form
3. listwnd / dumpstate to understand the current UI structure
4. Execute test operations (click / type / key / rcall)
5. Capture screenshots or use rget to verify results
6. `waitfor` waits for asynchronous operations to complete
7. Repeat 4-6 until the test ends
8. exit to quit
```

### Actual Example

```python
# Simulate user login
脚本 = [
    {"cmd": "goto", "target": "TLoginForm"},
    {"cmd": "type", "target": "EditUser", "value": "admin"},
    {"cmd": "key", "target": "EditPwd", "key": "Tab"},
    {"cmd": "type", "target": "EditPwd", "value": "123456"},
    {"cmd": "click", "target": "BtnLogin"},
    {"cmd": "waitfor", "target": "StatusBar", "prop": "Caption",
     "value": "登录成功", "timeout": "5000"},
    {"cmd": "rget", "target": "StatusBar.Caption", "assert_expr": "actual == '登录成功'"},
    {"cmd": "capture", "target": "login_result"},
]

# Verify list loading
脚本2 = [
    {"cmd": "waitfor", "target": "ListView1", "prop": "Items.Count",
     "value": "10", "timeout": "5000"},
    {"cmd": "rget", "target": "ListView1", "prop": "Items[0].Caption"},
]
```

---

## Reporting and Fix Loop

The `report` returned by `automate_delphi` is the entry point for subsequent decisions:

```json
{
  "status": "partial",
  "resolved_action": "gui",
  "report": {
    "first_failure": {
      "index": 3,
      "cmd": "rget",
      "target": "StatusBar.Caption",
      "signal": "assertion_failed"
    },
    "solution": {
      "next_mode": "coding",
      "recommendations": [
        "Compare actual with expected and decide whether the app logic or the test expectation is wrong."
      ]
    }
  }
}
```

Processing rules:

1. When `report.first_failure != null`, stop subsequent dependent steps.
2. When `signal` is `target_not_found/property_not_found`, first use `formsum/rinspect` to fix the script.
3. When `signal` is `assertion_failed/timeout/command_error` and the expectation comes from source code analysis, switch back to coding mode: `get_coding_rules(section="writing")` → `delphi_file` to modify code → `delphi_project(action="compile")` → re-execute the script.
4. After fixing, save the passing script to `tests/scripts/`, and save reusable experience to `experience`.

The default is `stop_on_failure=true`. Steps after the first failure will not continue operating the UI; instead, they are marked as `skip` in `report.steps`. Only explicitly pass `stop_on_failure=false` when you need to explore all steps at once.

When source-level impact analysis is needed, enable it in the full script object:

```json
{
  "callgraph_diagnostics": true,
  "callgraph_options": {"max_depth": 2, "edge_limit": 20, "project_only": true},
  "steps": [
    {"cmd": "click", "target": "btnSave", "handler": "main.TfrmMain.SaveIfModified"}
  ]
}
```

For a failed step, an automatic `callgraph(direction=callers)` is appended before the automatic `exit`, and the summary is written to `report.first_failure.diagnostics.callgraph`. If the callgraph query fails, only a secondary warning is recorded, without overwriting the original UI failure reason.

---

## Framework Differences

| Feature | VCL | FMX 2D | FMX 3D |
|------|-----|--------|--------|
| Screenshot | GDI BitBlt | PaintTo | CopyToBitmap |
| Control lookup | FindChildControl | FindComponent | FindComponent |
| Context menu | TPopupMenu | TPopupMenu (manual scan) | TPopupMenu (manual scan) |
| Click | SendMessage BM_CLICK | RTTI Click / OnClick | RTTI Click / OnClick |
| Coordinate click @x,y | SendMessage WM_LBUTTONDOWN | FormToHWND + SendMessage | FormToHWND + SendMessage |
| Type conversion interface | Generic | Generic | Generic |

---

## Debugging Tips

1. **`listwnd` first, then operate**: See which forms are currently available and confirm the form name.
2. **`rinspect` to understand controls**: See what methods and properties a control has. By default, only public+published methods are shown; to view private/protected, pass `visibility=private,protected,public,published`.
3. **`dumpstate` to get full state**: Troubleshoot control property values.
4. **`capture` for intuitive verification**: Take screenshots to confirm the UI state.
5. **`rget` assertions**: The AI compares expected values itself.
6. **Use `waitfor` instead of fixed wait**: Reduce waiting time and improve stability.
7. **Process leftovers**: Check the `process_alive` field and exit regularly.

---

## FAQ

**Q: `waitfor` keeps timing out with TIMEOUT?**  
A: Check whether the `prop` property name is correct; use `rget` first to confirm.

**Q: `msgclick` cannot close the popup?**  
A: FMX's MessageDlg creates a TaskDialog (`#32770`) on Windows; `msgclick` looks for a window of class `#32770`. Confirm the popup type.

**Q: FMX exe reports missing files at startup?**  
A: FMX runtime DLLs need to be findable by the process. Ensure the PATH environment variable contains the FMX runtime directory, or use static linking.

**Q: `click` clicked but nothing happened?**  
A: Check whether the target control name is correct; use `rinspect` first to see whether the control has a `Click` method or `OnClick` event.

**Q: FileNotFoundError on startup?**  
A: For FMX projects, ensure the Win32\Debug\ directory contains the FMX-dependent DLLs (such as `fmx260.bpl`). You can try using a VCL test project to verify basic functionality.