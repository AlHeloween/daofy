<!-- @when: After compilation passes, UI interaction verification is required for GUI programs. Follow this process when first integrating automated testing -->
<!-- @part-of: testing -->
<!-- @chain: after=../../ui.md, before=a-smoke.md -->

## Automated Testing Infrastructure

### Pre-check

Perform the following checks to determine the current state:

1. Read the target project's `.dpr` file
2. If the `.dpr` `uses` clause already contains `Vcl.DaofyAutomation` or `Fmx.DaofyAutomation` → **skip the enablement steps** and execute the script directly
3. If not included → follow the "Enablement Process" below

### Enablement Process (AI-executable)

#### Step 1: Confirm the framework files exist

Check whether `tools/auto/` contains the required files:

| Framework | Required files |
|------|---------|
| VCL | `DaofyAutomation.Base.pas` + `Vcl.DaofyAutomation.pas` |
| FMX | `DaofyAutomation.Base.pas` + `Fmx.DaofyAutomation.pas` |
| callgraph (optional) | `DaofyAutomation.CallGraph.pas` + `tools\stacktrace\StackTrace.pas` |

> ⚠️ `DaofyAutomation.Base.pas` is the common base dependency for both VCL and FMX; both must reference it.

If the files do not exist, check whether the Daofy installation directory is correct, or copy the `tools/auto/` directory from the source.

#### Step 2: Modify the .dpr

**Option A (recommended): Reference directly with an `in` clause (most reliable; no need to modify .dproj)**

```pascal
program MyApp;

uses
  Vcl.Forms,
  Vcl.DaofyAutomation in '$(DaofyRoot)\tools\auto\Vcl.DaofyAutomation.pas',
  DaofyAutomation.Base in '$(DaofyRoot)\tools\auto\DaofyAutomation.Base.pas',
  MainForm in 'MainForm.pas';

begin
  Vcl.DaofyAutomation.AutoStart;    // ← ⚠️ Must be before Application.Initialize
  Application.Initialize;
  Application.CreateForm(TMainForm, MainForm);
  Application.Run;
  Vcl.DaofyAutomation.AutoStop;
end.
```

FMX version:

```pascal
uses
  FMX.Forms,
  Fmx.DaofyAutomation in '$(DaofyRoot)\tools\auto\Fmx.DaofyAutomation.pas',
  DaofyAutomation.Base in '$(DaofyRoot)\tools\auto\DaofyAutomation.Base.pas';
```

**Option B (if search paths are already configured, or the project does not allow `in` clauses)**

Add the `tools/auto` directory to the project search path (IDE: Project → Options → Delphi Compiler → Search path).
If you need the optional diagnostic commands `callgraph`/`callgraph_diff`/`callgraph_path`/`callgraph_impact` and the purpose-layer `callgraph_*` commands, you also need to add `tools/stacktrace` and add `DaofyAutomation.CallGraph` to the project `uses` clause. `callgraph` supports `direction=callees|callers`, `project_only`, `exclude_prefixes`, `include_prefixes`, and `edge_limit`; the response contains `edge_count`, `returned_count`, and `truncated`; each edge contains `call_addr`, `call_file`, `call_line`, `category`, `from_category`, and `to_category`. `callgraph_path` accepts `source`, `target`, `max_depth`, `max_paths`, and `include_prefixes`, and returns `found` and `paths`. `callgraph_diff` compares current call-edge changes using baseline JSON or a `baseline_path` snapshot file; it defaults to `compare_by=name`, optionally `addr|full`, and can use `save_as` to save the current snapshot; `save_as` must be a relative JSON path under `snapshots_dir`, and read-type snapshot paths must still be within `snapshots_dir` after resolution. `callgraph_impact` accepts `functions`/`targets` or `file`+`line`/`locations`, queries callers in batches, and summarizes entry candidates and unresolved items. Purpose-layer commands include test selection, failure diagnosis, boundary checks, refactoring checks, island candidates, and exception stack interpretation.
Then the `.dpr` only needs the unit name, with no `in` clause:

```pascal
uses
  Vcl.Forms,
  Vcl.DaofyAutomation;          // ← Resolved via search path
```

> Option A does not require changing .dproj configuration and is reliable in any environment; AI can directly use `delphi_file(action="write", edits=[...])` to modify the `.dpr`. If the project already has a search-path system and does not accept `in` clauses, use Option B instead, but a human must confirm that the search path was added correctly.

#### Step 3: Compile and verify

```python
delphi_project(action="compile", project_path="MyApp.dproj")
```

Confirm 0 errors, 0 warnings.

#### Step 4: Smoke test

Start the target program and use `automate_delphi` to send a simple command to verify pipe communication:

```python
automate_delphi(
    app_path="C:\MyApp\Win32\Debug\MyApp.exe",
    keep_alive=True,
    script=[
        {"cmd": "goto", "target": "TMainForm"},
        {"cmd": "capture", "target": "smoke_001"},
        {"cmd": "exit"}
    ]
)
```

If it returns `"status": "ok"` and the screenshot file is generated → **enablement succeeded**.

#### Common Failure Recovery

| Failure symptom | Cause | AI action |
|----------|------|------------|
| `File not found: 'DaofyAutomation.Base.pas'` | Search path does not include `tools/auto` | Check the search path configuration; or use the `in` clause approach instead |
| `automate_delphi` returns `target_not_found` | Form class name does not match | First use `{"cmd": "listwnd"}` to scan the actual form list, then use the returned class to correct target |
| `automate_delphi` cannot connect to the pipe (timeout) | AutoStart was not called, or was skipped by an exception | Read the `.dpr` to confirm AutoStart is before `Application.Initialize`; or manually wait 1–2 seconds after the exe starts |
| Compilation reports `Duplicate resource` | Dual reference via the `in` clause and search path causes duplicate compilation | Remove the `in` clause and use the search path consistently |

#### Pipe Establishment Failure Diagnosis

When `automate_delphi` times out or fails to connect to the pipe, diagnose using the following process. **Note: when the pipe fails, pipe commands such as `listwnd`/`formsum`/`dumpstate` are unavailable, and you must use Python UIA (`uia.xxx`).**

```
Pipe failure
  │
  ├─ Check whether the process exists (tasklist / PowerShell Get-Process)
  │
  ├─ Process does not exist (startup failed or has crashed)
  │   │
  │   └─ Check exception.log
  │       ├─ Exists → read the StackTrace output and locate the crash cause (exception class name + error line number)
  │       └─ Does not exist → the process did not start successfully; check:
  │           ├─ Whether the exe path is correct
  │           ├─ Missing DLL dependencies (check with dumpbin / Dependencies tools)
  │           └─ Windows Defender / antivirus blocking
  │
  └─ Process exists but pipe is unreachable (AutoStart not called or pipe name mismatch)
      │
      ├─ 1. uia.scan scans top-level windows to confirm the program UI has loaded
      │     {"cmd": "uia.scan", "depth": 2, "props": "name,class,rect"}
      │
      ├─ 2. uia.screenshot takes a screenshot + OCR recognizes error information
      │     {"cmd": "uia.screenshot", "path": "pipe_fail_diag.png"}
      │     → daofy_ocr(action="recognize", image_path="pipe_fail_diag.png")
      │
      └─ 3. Determine based on the OCR result:
            ├─ Exception dialog recognized → use the screenshot as evidence and analyze the exception content
            ├─ Permission/UAC prompt recognized → requires running as administrator
            └─ UI is normal but pipe is unreachable → read the .dpr to confirm AutoStart is before Application.Initialize
```

**Diagnostic Tool Comparison**:

| Scenario | Available tools | Unavailable tools |
|------|---------|-----------|
| Process does not exist | `tasklist`, `powershell Get-Process`, read `exception.log` | All pipe commands are unavailable |
| Process exists + pipe fails | `uia.scan`, `uia.screenshot`, `uia.goto`, OCR | `listwnd`, `formsum`, `dumpstate`, `rget` |
| Pipe normal | All commands | — |

**Quick check script** (Python side):
```python
import subprocess, os
# Check whether the process exists
result = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {exe_name}"], 
                       capture_output=True, text=True)
if exe_name not in result.stdout:
    # Process does not exist; check exception.log
    log_path = os.path.join(exe_dir, "exception.log")
    if os.path.exists(log_path):
        # Read StackTrace
        with open(log_path, encoding="utf-8", errors="replace") as f:
            print(f.read())
else:
    # Process exists; use UIA diagnosis
    # uia.scan → uia.screenshot → OCR
    pass
```

### Tool Invocation

```python
automate_delphi(app_path="App.exe", script=[...])
automate_delphi(action="gui", app_path="App.exe", script=[...])
automate_delphi(action="auto", app_path="App.exe", script="script.json", keep_alive=True)
```
`action="auto"` automatically detects the PE header Subsystem field (GUI vs Console).

`action="console"` is used for stdin/stdout interaction with console programs and requires no changes on the Delphi side.

### Communication Architecture

```
Python                              Delphi
  ── CreateFile(\\.\pipe\daofy_auto) → pipe thread receives JSON
  ── WriteFile(JSON request)        → main thread executes
  ←── ReadFile(JSON response)       ← returns result/ACK
```

### Synchronous/Asynchronous Command Classification

| Synchronous | Asynchronous |
|------|------|
| goto, capture, dumpstate, listwnd, formsum | click, rclick, dblclick |
| wait, waitfor, dlgscan, msgscan, msgclose | hover, move, drag |
| dlgfile, snapdir, exit | type, key |
| rget, rinspect | rcall, rset, msgclick, dlgclick |

### keep_alive

- `keep_alive=True` keeps the process running; it is automatically cleaned up after 5 minutes of inactivity
- The first call on a newly created process automatically sets `snapdir`
- Returns `process_reused` / `process_alive` fields so the AI can perceive the state

### Test Quality Red Lines

> ⚠️ **The following 6 items are veto red lines. Violating any one of them makes the test case unacceptable; it must be modified and resubmitted. Applies to all test cases (Delphi automated tests, pytest unit tests, integration tests).**

#### Red Line 1: No Skip-style Passing

- ❌ When a runtime/component is unavailable, mix `Assert(True)` / `assert True` into the passed count
- ❌ After initialization fails, silently perform no-ops and finally assert "no exception"
- ✅ Detect preconditions → if not met, **explicitly skip + explain why**, or **Fail + explain why**

```
// ❌ Delphi incorrect example
{"cmd":"rget","target":"WebView2.IsAvailable","assert_expr":"true","note":"Skip check"}

// ✅ Delphi correct example
{"cmd":"rget","target":"WebView2.IsAvailable","assert_expr":"actual=='True'",
 "on_fail":"skip","skip_reason":"WebView2 Runtime not installed"}
```

```python
# ❌ pytest incorrect example
def test_webview2_create():
    try:
        wv = CreateWebView2()
    except:
        pass
    assert True  # false pass

# ✅ pytest correct example
@pytest.mark.skipif(not is_webview2_available(), reason="WebView2 Runtime not installed")
def test_webview2_create():
    wv = CreateWebView2()
    assert wv IsNot None
    assert wv.NativeWindow > 0
```

#### Red Line 2: Assertions Must Verify Specific State

- ❌ `assert_expr: "true"` / `assert_expr: "actual != ''"` — uninformative; cannot locate the problem
- ✅ `assert_expr: "len(actual) > 0"` / `assert_expr: "actual == 'ExpectedValue'"` / `assert_expr: "FileExists(actual)"`
- **Criterion**: If the assertion fails, can you locate **which specific state is wrong**? If not = the assertion is invalid

#### Red Line 3: Screenshots Must Have Content Verification

- ❌ `exit` directly after `capture`; the screenshot is saved but not checked
- ❌ In pytest, `screenshot()` is not followed by calling `image_diff` / `ocr` / `pixel_assert`
- ✅ Follow `capture` with `recognize`/`detect`/`diff`/`match`, or at least use `rget` to verify the screenshot-related UI state

#### Red Line 4: External Dependencies Must Test Degradation Paths

When depending on external components such as WebView2/Runtime/COM/DLL:

1. **Positive test**: verify the function works when the component is available
2. **Degradation test**: verify program behavior when the component is unavailable (error/degrade/skip); must not silently do nothing

When build scripts call external tools (`brcc32`/`dcc32`/`msbuild`):

- ❌ Return exit code 0 when the tool is missing
- ✅ Return a non-zero exit code + output an error message to stderr when the tool is missing

#### Red Line 5: Execution Time Must Match the Amount of Work

| Operation scale | Minimum duration | Description |
|---------|---------|------|
| Single goto + capture + exit | ≥ 2 seconds | Includes process startup/pipe establishment/screenshot |
| 10 loop operations | ≥ 5 seconds | Includes intermediate verification |
| 100 loop operations | ≥ 30 seconds | It is impossible to complete 100 real operations in 1 second |

- If actual duration is far below expectations, you must explain why in `note` (mock/stub/environment differences)
- The test report must include the **actual execution time**; do not report only passed/failed counts

#### Red Line 6: Audit Conclusions Must Be Supported by Runtime Evidence

- ❌ Design doc says "supports external URI rejection" → conclusion "feature complete"
- ✅ Runtime evidence: test script actually requests an external URI → returns 403/404 → screenshots/logs corroborate
- Meaning of markers in audit reports:

| Audit marker | Meaning | Can it lead to COMPLETE |
|---------|------|------------------|
| `DESIGN` | Design review only, not actually run | ❌ No |
| `IMPLEMENTED` | Code implemented, compiled successfully | ❌ No |
| `TESTED` | Tests have been run, with screenshot/log evidence | ✅ Yes |

### Protocol

- Synchronous commands block and wait for a response; asynchronous commands ACK immediately
- Response: `{"reqId":"step_0","status":"ok","data":"OK"}`
- >64KB is automatically chunked (ERROR_MORE_DATA loop read)

### Test Scenario Overview

See [index.md](../index.md) for the scenario file index. Each scenario file provides a strategy description + reusable JSON templates.

