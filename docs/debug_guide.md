# Delphi Program Debugging Guide — AI Debugging Workflow

> Version: v1.1 | Last updated: 2026-06-26
> Audience: Large language model AIs using Daofy MCP Server to debug Delphi programs

---

## Table of Contents

1. [Core Principles](#1-core-principles)
2. [Environment Confirmation Before Debugging](#2-environment-confirmation-before-debugging)
3. [Compile Error Debugging](#3-compile-error-debugging)
4. [Runtime Crash/Exception Debugging](#4-runtime-crashexception-debugging)
5. [Logic Error Debugging](#5-logic-error-debugging)
6. [GUI/Interface Issue Debugging](#6-guiinterface-issue-debugging)
7. [Runtime Data Inspection (RTTI)](#7-runtime-data-inspection-rtti)
8. [Memory/Resource Leak Debugging](#8-memoryresource-leak-debugging)
9. [Common AI Misjudgment Patterns](#9-common-ai-misjudgment-patterns)
10. [Debugging Workflow Quick Reference](#10-debugging-workflow-quick-reference)
11. [Console Application Debugging](#11-console-application-debugging)
12. [Performance Issue Triage](#12-performance-issue-triage)
13. [Tool Call Exception Recovery](#13-tool-call-exception-recovery)

---

## 1. Core Principles

### 1.1 Gather Evidence First, Conclude Later

**Do not** assert the cause based on experience or a quick scan of the code. Errors in Delphi programs can originate from:

| Error Source | Typical Characteristics | Common AI Mistake |
|-------------|------------------------|-------------------|
| Compiler version/path | Compile fails, .dcu not found | Directly modify code |
| Missing search path | Unit file not found | Judged as "missing unit" → actually a path config issue |
| Conditional compilation symbols | Only fails under specific configurations | Misjudged as code logic error |
| DFM resource issues | Crashes immediately on startup | Misjudged as code null pointer |
| Missing runtime DLL | exe fails to start | Misjudged as code issue |
| Third-party library version mismatch | Link errors or access violations | Misjudged as API misuse |
| Compiler optimization bug | Only occurs in Release | Misjudged as code logic |
| Thread synchronization | Intermittent crashes, UI freezes | Misjudged as infinite loop |

**First principle of debugging**: Collect the evidence chain first, then draw conclusions.

### 1.2 Evidence Chain Priority

```
Compile error → First check compiler output, then use delphi_project(info) to check configuration
Runtime crash → First read exception.log, then use automation tools to reproduce
Logic error → First use RTTI/rget to inspect runtime state, then read source code
UI issue → First capture a screenshot, then use dumpstate to view the control tree
```

### 1.3 Narrow the Scope Step by Step

Do not try to pinpoint the issue in one step. Each step should eliminate a category of possibilities:

```
① Environment problem?    → check_environment
② Configuration problem?  → delphi_project(action="info")
③ Compile problem?        → delphi_project(action="compile")
④ Code logic?             → delphi_file(read) + delphi_kb(search)
⑤ Runtime state?          → automate_delphi(rget) / delphi_rtti(discover)
```

---

## 2. Environment Confirmation Before Debugging

Before starting any debugging, first confirm the compilation environment is healthy.

### 2.1 Check Compiler Status

```python
check_environment(action="check")
```

Returned information includes:
- List of available compilers (name, version, path)
- Default compiler
- Whether pasfmt is installed

### 2.2 Check Project Configuration

```python
# Get full project configuration
delphi_project(action="info", project_path="Project.dproj")
```

Key check items:
- `DCC_UnitSearchPath` — Whether the unit search path is complete
- `DCC_Define` — Whether conditional compilation symbols are correct (Debug/Release)
- `OutputType` — Output type (GUI/Console/DLL)
- `RuntimeLibrary` — Runtime linking method (static/dynamic)
- `TargetPlatform` — Target platform
- Whether the source file list is complete

### 2.3 Check Registry Runtime Environment

```python
delphi_project(action="runtime", base_dir="src")
```

Scans component class names in `.pas`/`.dfm`, detecting whether required uses units are missing.

---

## 3. Compile Error Debugging

### 3.1 Standard Debugging Workflow

```
Compile fails
  │
  ├─ check_environment(action="check")          → ① Compiler available?
  │     ↓ Not available
  │   check_environment(action="detect")         → Re-detect
  │
  ├─ delphi_project(action="info")              → ② Project config correct?
  │     ↓
  │   Check DCC_UnitSearchPath, DCC_Define, etc.
  │
  ├─ delphi_project(action="compile")           → ③ Recompile and see full output
  │     ↓
  │   Record the location and description of the first error
  │
  ├─ delphi_file(action="read", file_path=...)  → ④ Read the file that reported the error
  │
  ├─ delphi_kb(query="...", kb_type="delphi")   → ⑤ Look up API definitions
  │
  └─ Recompile to verify after fixing
```

### 3.2 Common Compile Error Reference

| Compiler Output | Possible Cause | First Troubleshooting Step |
|-----------------|---------------|---------------------------|
| `Fatal: Unable to execute file` | Compiler path error | `check_environment(action="detect")` |
| `Fatal: File not found: xxx.dcu` | Missing search path | `delphi_project(action="info")` to check `DCC_UnitSearchPath` |
| `E1026 File not found: xxx.dproj` | Project path error | Confirm `project_path` points to the correct `.dproj` |
| `E2003 Undeclared identifier: xxx` | Missing uses / typo | `delphi_file(read)` to read the file, check the uses clause |
| `E2010 Incompatible types` | Type mismatch | `delphi_kb(search_type="function")` to look up the function signature |
| `E2029 ')' expected but ',' found` | Generic syntax error | Check whether the Delphi version supports generic syntax |
| `E2037 Record type 'xxx' not found` | Type undefined | Check the record definition location and scope |
| `E2064 Left side cannot be assigned to` | Assigning to a read-only property | `delphi_kb` to check whether the property has a setter |
| `E2198 XE7+ does not support this syntax` | Compiler version mismatch | Check the compiler version configuration in `.dproj` |
| Exit code 2 | Compile event failed or syntax error | Check detailed output to pinpoint |
| `W1000 Symbol 'xxx' is deprecated` | Deprecated API used | `delphi_kb` to look up alternatives |
| `H2443 Inline function 'xxx' has not been expanded` | Inline function not expanded | Add `{$INLINE ON}` or ignore |
| `dcc32 not found` | Compiler not detected | `check_environment(action="detect")` |

### 3.3 Search Path Issue Troubleshooting

When the compiler reports that it cannot find a `.dcu` or `.pas`:

```python
# 1. View the current search path
delphi_project(action="info", project_path="Project.dproj")

# 2. Confirm the third-party library path
# Use delphi_kb to search the knowledge base that the unit belongs to
delphi_kb(query="xxx.pas", kb_type="thirdparty")

# 3. Add the missing directory to the search path
delphi_project(action="set",
    project_path="Project.dproj",
    property_name="DCC_UnitSearchPath",
    value="$(BDSLIB)\$(PLATFORM)\release;..\SharedLib\src",
    config="Debug",
    platform="Win32")
```

**⚠️ Note**: `DCC_UnitSearchPath` contains MSBuild macro variables such as `$(BDS)`, `$(BDSLIB)`, `$(PLATFORM)`. Do not treat them as ordinary paths.

### 3.4 Conditional Compilation Issue Debugging

When code works fine under Debug but fails under Release:

```python
# Compare the compile symbols of the two configurations
delphi_project(action="info", project_path="Project.dproj")
# Check the differences in DCC_Define across configurations

# View the code inside conditional compilation blocks
delphi_file(action="read", file_path="Unit1.pas", start_line=line_no)
```

Common causes:
- Auxiliary code in `{$IFDEF DEBUG}` blocks is skipped in Release
- Optimization enabled in Release causes timing issues
- Code in `{$IFDEF RELEASE}` has hidden bugs

### 3.5 Third-Party Library/Component Package Compile Failure

```python
# 1. Confirm the third-party library knowledge base has been built
delphi_kb(action="stats")

# 2. Search for relevant APIs in the third-party library
delphi_kb(query="TComponentName", kb_type="thirdparty")

# 3. Check the component package installation status
delphi_project(action="info", project_path="Package.dproj")
```

### 3.6 File Encoding Issues

In Chinese localization environments, inconsistent source file encodings can cause compile errors (illegal characters, garbled text).

**Common scenarios**:
- File saved as GBK but compiler expects UTF-8 (or vice versa)
- Missing BOM header causes compiler to misjudge encoding
- Different editors save with different encodings during multi-person collaboration

**Troubleshooting method**:
```python
# Read the file with different encodings to confirm the actual encoding
delphi_file(action="read", file_path="Unit1.pas", encoding="gbk")
delphi_file(action="read", file_path="Unit1.pas", encoding="utf-8")

# Once the encoding is confirmed, it can be converted
delphi_file(action="encode", file_path="Unit1.pas",
    to_encoding="utf-8-sig")  # Recommended to uniformly convert to UTF-8 with BOM
```

**Prevention**: The project should uniformly use UTF-8 with BOM (`utf-8-sig`) encoding to save all `.pas`/`.dfm` files.

---

## 4. Runtime Crash/Exception Debugging

### 4.1 Standard Workflow

```
Program crashes
  │
  ├─ Check exception.log / error dialog
  │     ↓
  │   Record the exception class name, message, address
  │
  ├─ delphi_project(action="compile", run_verify=true)  → Reproduce the crash
  │     ↓ run_verify automatically captures the crash
  │
  ├─ Analyze the exception type:
  │     ├─ EAccessViolation    → Null pointer / dangling reference
  │     ├─ EInvalidPointer     → Double Free / wild pointer
  │     ├─ EOutOfMemory        → Memory leak / large object allocation
  │     ├─ EAssertionFailed    → Assert check failed
  │     ├─ EConvertError       → Type conversion failed
  │     ├─ EExternalException  → External exception (DLL/COM)
  │     └─ EOSError            → Windows API error
  │
  ├─ automate_delphi(gui) start the program and inspect state
  │
  └─ After locating the specific code line, fix it
```

### 4.2 Using run_verify to Automatically Detect Crashes

```python
# Automatically run for 3 seconds after compiling to detect if it crashes on startup
delphi_project(action="compile",
    project_path="App.dproj",
    build_configuration="Debug",
    run_verify=True)  # ← Key parameter
```

`run_verify` automatically:
1. Starts the compiled exe
2. Waits 3 seconds to observe whether the process is alive
3. If it crashes, automatically reads `exception.log` and embeds it in the response

### 4.3 Using Automation Tools to Reproduce Crashes

For complex runtime crashes, use `automate_delphi` to reproduce:

```python
# Start the program and perform operations to reproduce the crash
automate_delphi(
    action="gui",
    app_path="Win32/Debug/App.exe",
    keep_alive=True,
    script=[
        {"cmd": "goto", "target": "TMainForm"},
        {"cmd": "type", "target": "EditName", "value": "test"},
        {"cmd": "click", "target": "BtnSubmit"},
        # Wait 5 seconds to see if it crashes
        {"cmd": "wait", "ms": "5000"},
        {"cmd": "dumpstate"},  # If it hasn't crashed, get state
    ])
```

**⚠️ Relationship between run_verify and automate_delphi:**

| Scenario | Tool to Use | Description |
|----------|------------|-------------|
| Quick verification of startup crash after compiling | `compile(run_verify=true)` | Lightweight, only waits 3 seconds |
| Crash triggered by specific operations | `automate_delphi` | Can perform specific operations to reproduce |
| Crash after long-running operation | `automate_delphi` + `keep_alive` | Keep process running, operate step by step |
| Intermittent crash | Multiple `automate_delphi` | Loop operations to increase reproduction probability |

### 4.4 Common Runtime Exception Analysis

#### EAccessViolation (Access Violation)

```
Possible causes:
  ├─ Object used after being freed     → Check FreeAndNil usage
  ├─ String/array out of bounds        → Check Length and indices
  ├─ Window handle not created         → Check HandleAllocated()
  ├─ Thread synchronization issue      → Check TThread.Synchronize / TMonitor
  ├─ DLL imported function signature mismatch → Check external declaration
  └─ Interface reference counting error → Check _AddRef / _Release balance
```

**Troubleshooting steps**:

```python
# 1. Locate the code region where the error occurs
# Find the relevant unit and line number from the exception address or error description

# 2. Read the relevant source code
delphi_file(action="read", file_path="Unit1.pas", start_line=line_no-20, end_line=line_no+10)

# 3. Check the creation and release of involved objects
# Search for Free/Destroy calls on the object
# Search for FreeAndNil / Free usage

# 4. Look up the API to confirm the object creation method
delphi_kb(query="TStringList", kb_type="delphi")
```

#### EInvalidPointer (Invalid Pointer)

```
Almost always the same cause: Double Free.
Troubleshooting directions:
  ├─ Whether manually Free'd then auto-destructor triggered (Ownership confusion)
  ├─ Whether TObjectList's OwnsObjects is correctly set
  ├─ Repeated release in TComponent.FreeNotification callback
  ├─ Mixed use of interface reference counting + manual Free
  └─ Releasing the same object simultaneously in multiple threads
```

#### EOutOfMemory (Out of Memory)

```
Troubleshooting directions:
  ├─ Memory leak accumulation → Occurs after long-running operation
  ├─ Large file/image loaded all at once → Stream processing
  ├─ Recursion without termination condition → Check recursive functions
  ├─ String concatenation causing memory fragmentation → Use StringBuilder
  └─ Third-party library memory leak
```

### 4.5 Runtime Library/Package Missing Troubleshooting

When the program shows "cannot find xxx.bpl" or "cannot locate program input point" at startup:

```python
# Check the compile linking method
delphi_project(action="info", project_path="Project.dproj")
# Check the RuntimeLibrary property: static / dynamic
```

| Symptom | Cause | Solution |
|---------|-------|----------|
| Cannot find `xxx.bpl` | Dynamic linking but BPL not in PATH | Static linking or distribute BPL |
| "Cannot locate program input point" | DLL version mismatch | Check third-party library version |
| Exits immediately after startup with no prompt | Missing FMX runtime DLL | Static link FMX or prepare runtime environment |
| `XXX.dll missing` | Missing Windows system DLL | Install VC++ runtime or DirectX |

### 4.6 Thread-Related Issue Debugging

Intermittent crashes/random behavior often point to thread synchronization issues. **This type of debugging is completely different from single-threaded debugging.**

**Characteristic identification**:
- Only reproduces under high load/after many operations
- Crash location differs each time
- Does not occur in Debug mode, occurs in Release (optimization exposes race conditions)
- Crash disappears after adding Sleep/MessageBox → Classic race condition indicator

**Troubleshooting directions**:

```python
# 1. Code review: check protection mechanisms for shared variables
# 2. Check whether TThread's terminated flag is checked
# 3. Check whether resources are cleaned up when the thread exits
# 4. Check whether TThread.Synchronize/Queue callbacks access already-freed objects

# Static analysis can detect some thread safety issues
delphi_project(action="audit", base_dir="src")
```

**⚠️ Key point**: `TThread.Synchronize` and `TThread.Queue` callbacks execute on the *main thread*,
so components accessed in the callback may already be in the process of being destructed—need to check the `csDestroying` flag.

---

## 5. Logic Error Debugging

### 5.1 Code Skeleton Analysis

First understand the overall code structure to avoid blindly diving into details:

```python
# Get the project code skeleton (most token-efficient approach)
delphi_project(action="ast", base_dir="src")

# Or view the skeleton of a single file
delphi_project(action="ast", file_path="Unit1.pas")
```

`ast` returns a summary of all classes, methods, and fields, allowing you to quickly locate the relevant code region.

### 5.2 Code Audit

```python
# Run static analysis
delphi_project(action="audit", base_dir="src")
```

50+ static analysis rules cover:
- Null pointer risks
- Resource leaks (File/Handle/GDI/memory)
- Thread safety issues
- Type conversion risks
- Exception safety
- Code quality (methods too long, nesting too deep)

### 5.3 Reading Source Code to Locate

```python
# Locate and read by class name
delphi_file(action="read", search_type="class",
    type_name="TMainForm",
    search_in="project",
    project_path="Project.dproj")

# Locate by function name
delphi_file(action="read", search_type="function",
    function_name="Button1Click",
    search_in="project",
    project_path="Project.dproj")

# Read a specific line range
delphi_file(action="read", file_path="Unit1.pas",
    start_line=50, end_line=100, show_line_numbers=True)
```

### 5.4 API Usage Verification

AIs frequently fabricate Delphi API signatures. **Before assuming an API is being used incorrectly, you must verify with the knowledge base**:

```python
# Look up official Delphi APIs
delphi_kb(query="TStringList.Create", kb_type="delphi")

# Look up APIs in the project code
delphi_kb(query="TMainForm", kb_type="project", project_path="Project.dproj")

# Look up function signatures (exact match)
delphi_kb(query="TStringList.LoadFromFile", search_type="function")

# Look up references (assess modification impact)
delphi_kb(query="TStringList", search_type="reference", kb_type="project")
```

**⚠️ Important**: When the AI is uncertain about the usage of a Delphi API, it must confirm the official definition through `delphi_kb` or `delphi_file(action="read", search_type="class")`. Do not fabricate from the large model's training data memory.

### 5.5 Git History Backtracking

```python
# View recent commits
code_hosting(action="git_log", dir=".", limit=20)

# View modification history of a specific file
code_hosting(action="git_log", dir=".", files=["src/Unit1.pas"], limit=10)

# View changes in a specific commit
code_hosting(action="git_show", dir=".", ref="abc1234")

# Compare current and previous differences
code_hosting(action="git_diff", dir=".", ref="HEAD~1..HEAD")
```

### 5.6 Experience Library Reuse

If a similar problem has been solved before, check the experience library first:

```python
experience(action="search", query="EAccessViolation TStringList")
experience(action="search", query="error on list item deletion")
```

---

## 6. GUI/Interface Issue Debugging

### 6.1 Launching the Automation Environment

Use the GUI mode of `automate_delphi` to interact with a running Delphi program.

**Prerequisite**: The target program has linked the `DaofyAutomation` unit.

```python
# Start the program and capture the UI screenshot
automate_delphi(
    action="gui",
    app_path="App.exe",
    keep_alive=True,
    script=[
        {"cmd": "goto", "target": "TMainForm"},
        {"cmd": "capture", "target": "main_001"},
    ])
```

### 6.2 Inspecting the Interface Structure

```python
# Get the full control tree (most comprehensive state)
automate_delphi(
    action="gui",
    app_path="App.exe",
    script=[
        {"cmd": "goto", "target": "TMainForm"},
        {"cmd": "dumpstate"},  # ← Returns complete control tree JSON
    ])

# List all windows
automate_delphi(
    app_path="App.exe",
    script=[{"cmd": "listwnd"}])

# Inspect a single control
automate_delphi(
    app_path="App.exe",
    script=[{"cmd": "rinspect", "target": "EditName"}])
```

### 6.3 Getting Runtime Property Values

```python
# Read control properties
automate_delphi(
    app_path="App.exe",
    script=[
        {"cmd": "goto", "target": "TMainForm"},
        {"cmd": "rget", "target": "EditName", "prop": "Text"},
        {"cmd": "rget", "target": "ListBox1", "prop": "Items.Count"},
        {"cmd": "rget", "target": "StatusBar", "prop": "Caption"},
    ])
```

### 6.4 Screenshot Comparison Verification

```python
# Screenshot before operation
automate_delphi(
    app_path="App.exe",
    script=[
        {"cmd": "goto", "target": "TMainForm"},
        {"cmd": "capture", "target": "before"},
        {"cmd": "click", "target": "BtnRefresh"},
        {"cmd": "waitfor", "target": "ListView1", "prop": "Items.Count",
         "value": "10", "timeout": "5000"},
        {"cmd": "capture", "target": "after"},
    ])
```

### 6.5 Dialog/Popup Handling

```python
# Scan all popups
automate_delphi(
    app_path="App.exe",
    script=[{"cmd": "msgscan"}])

# Close the popup
automate_delphi(
    app_path="App.exe",
    script=[
        {"cmd": "msgclick", "target": "ok"},
    ])

# Context menu
automate_delphi(
    app_path="App.exe",
    script=[
        {"cmd": "rclick", "target": "Grid1"},
        {"cmd": "dlgscan"},
        {"cmd": "dlgclick", "target": "Copy"},
    ])
```

### 6.6 Process Reuse and State Preservation

```python
# First time: start and keep alive
automate_delphi(app_path="App.exe",
    script=[{"cmd": "goto", "target": "TMainForm"}, {"cmd": "capture", "target": "img1"}],
    keep_alive=True)

# Subsequent operations: reuse the existing process
automate_delphi(app_path="App.exe",
    script=[{"cmd": "rget", "target": "EditName", "prop": "Text"}])

# Cleanup: send exit
automate_delphi(app_path="App.exe",
    script=[{"cmd": "exit"}])
```

**⚠️ Note**: The process will be automatically killed after 5 minutes of no calls. When you need to keep it alive for a long time, pay attention to the frequency of calls.

### 6.7 Control Count Statistics (formsum)

Quickly assess the complexity of forms and frames to locate performance hotspots:

```python
automate_delphi(
    action="gui",
    app_path="App.exe",
    script=[{"cmd": "formsum"}])
```

Returned information includes the total number of controls for each Form/Frame. **When the control count > 100**, loop/iteration operations on that form may be a performance bottleneck.

**Typical scenarios**:
- Iteration operations on large ListView/TreeView
- Recursive rendering caused by deeply nested Panel/Frame
- Dynamically created controls not released in a timely manner

### 6.8 Screenshot Text Recognition (OCR)

When the screenshot contains text information but it cannot be obtained via rget, use OCR recognition:

```python
# First take a screenshot
automate_delphi(
    action="gui",
    app_path="App.exe",
    script=[
        {"cmd": "goto", "target": "TMainForm"},
        {"cmd": "capture", "target": "debug_screen"},
    ])

# Then OCR-recognize the text in the screenshot
ocr(action="recognize", image_path="docs/copyright/snapshots/debug_screen.png")
```

**How OCR works with automate_delphi**:
- `capture` → OCR: Suitable for text content in error dialogs, prompts, etc.
- `capture` before/after → `ocr(diff)`: Compare two screenshots and automatically annotate the difference regions
- OCR is an auxiliary means for GUI debugging; use it when `rget` / `dumpstate` cannot obtain the text content

**Not-suitable scenarios** (prefer rget/dumpstate instead):
- Control Caption/Text properties → `rget`
- Control tree structure → `dumpstate`
- List data → `rcall` to call business methods to get

---

## 7. Runtime Data Inspection (RTTI)

### 7.1 Using delphi_rtti to Discover and Call

When the program is running and has linked the DaofyAutomation unit, you can directly inspect runtime state via RTTI.

```python
# Step 1: Discover capabilities
delphi_rtti(action="discover", app_path="App.exe")

# Step 2: View methods and properties of a specific class
delphi_rtti(action="discover", app_path="App.exe", class_name="TMainForm")

# Step 3: Call business methods to get data
delphi_rtti(action="call",
    app_path="App.exe",
    class_name="TMainForm",
    method="GetOrderList",
    params={"status": "active"})
```

### 7.2 RTTI vs Automation Scripts

| Scenario | Recommended Method | Reason |
|----------|-------------------|--------|
| Read control properties | `automate_delphi(rget)` | Lighter, returns property value directly |
| Call business methods | `delphi_rtti(call)` | Automatic parameter schema validation |
| Understand available methods | `delphi_rtti(discover)` | Returns complete method list + parameters |
| Complex interaction operations | `automate_delphi(click/type)` | Simulates real user operations |
| Full control tree state | `automate_delphi(dumpstate)` | Complete DFM control tree |

---

## 8. Memory/Resource Leak Debugging

### 8.1 Static Analysis Detection

```python
# Run P0-level audit rules
delphi_project(action="audit", base_dir="src", rules="P0")
```

Static analysis can detect:
- Missing Free after TObject.Create
- Missing ReleaseDC after GetWindowDC
- Files not closed after opening
- Interface references not released

### 8.2 Common Resource Leak Patterns

```pascal
// ❌ Exception path leak
procedure TForm1.LoadFile;
var
  SL: TStringList;
begin
  SL := TStringList.Create;
  SL.LoadFromFile('data.txt');  // If this line throws an exception, SL leaks
  // Process data
  SL.Free;  // ← Only executed on the normal path
end;

// ✅ Correct approach
SL := TStringList.Create;
try
  SL.LoadFromFile('data.txt');
  // Process data
finally
  SL.Free;
end;
```

```pascal
// ❌ GDI resource leak
Canvas.Font.Name := 'Arial';  // Creates GDI object each time it is set
// Called frequently without release → GDI objects exhausted

// ✅ Reduce GDI creation
// Set the font in FormCreate, don't repeatedly set it in Paint
```

### 8.3 False Positive Exclusion After Code Audit

Static analysis produces false positives; the AI needs to judge each one:

| False Positive Pattern | Judgment Method |
|------------------------|-----------------|
| Object managed by Owner | Check whether an Owner is set (`TComponent.Create(AOwner)`) |
| Interface reference counting release | Delphi interfaces default to reference counting unless manually interfered |
| Global/singleton objects | Check whether the object is managed in initialization/finalization |
| Released in message/event | Check the PostMessage delayed release pattern |

---

## 9. Common AI Misjudgment Patterns

The following are the most common mistakes AIs make when debugging Delphi programs and **must be actively avoided**:

### Misjudgment 1: Skipping environment check and directly modifying code

```
❌ Wrong approach:
  "Compilation failed, missing TStringList unit → add uses System.Classes"

✅ Correct approach:
  1. check_environment(action="check") → Confirm the compiler is normal
  2. delphi_project(action="info") → Check the search path
  3. Locate the real cause of the error
```

### Misjudgment 2: Fabricating API signatures from memory

```
❌ Wrong approach:
  "I recall that TStringList.LoadFromFile accepts a TEncoding parameter…"

✅ Correct approach:
  delphi_kb(query="TStringList.LoadFromFile", search_type="function")
  → Look at the actual signature before using it
```

### Misjudgment 3: Treating runtime errors as code errors

```
❌ Wrong approach:
  Seeing EAccessViolation → Immediately conclude "somewhere has a null pointer" → Start modifying code

✅ Correct approach:
  1. Use automate_delphi + dumpstate/rget to inspect runtime state
  2. Confirm whether the object is alive at the time of the crash
  3. Then locate the code
```

### Misjudgment 4: Ignoring DFM resource issues

```
❌ Wrong approach:
  Crash on startup → Look for FormCreate / OnCreate event code

✅ Correct approach:
  First troubleshoot DFM resources:
  - Check whether the component classes referenced in the DFM exist
  - Check whether there are binary format compatibility issues in the DFM
  - Check whether the .res resource file exists
```

### Misjudgment 5: Ignoring conditional compilation/platform differences

```
❌ Wrong approach:
  "Debug works fine, Release crashes → Must be a bug in the code"

✅ Correct approach:
  Compare the compile setting differences between Debug/Release:
  - Optimization level (optimization may expose timing bugs)
  - Conditional compilation symbols
  - Runtime checks (range checking, overflow checking)
```

### Misjudgment 6: Treating third-party library version issues as code issues

```
❌ Wrong approach:
  Compile error cannot find xxx.dcu → "Remove the reference to this unit"

✅ Correct approach:
  1. delphi_kb(kb_type="thirdparty") → Search the third-party library
  2. Check the third-party library path configuration
  3. May need to build the third-party library knowledge base
```

### Misjudgment 7: Modifying .dproj configuration without basis

```
❌ Wrong approach:
  "Try adding a search path" → Directly modify the configuration

✅ Correct approach:
  delphi_project(action="info") first view the current configuration
  → Confirm the impact before and after the modification
  → Use delphi_project(action="set") to modify
```

### Misjudgment 8: Modifying multiple code locations at once

```
❌ Wrong approach:
  See one problem → Change 5 places along the way → Compile fails → Don't know which change was wrong

✅ Correct approach:
  Git commit or backup:
  1. Change one place → Compile and verify
  2. Change a second place → Compile and verify
  3. On error, use git diff or delphi_file(backup/restore) to roll back
```

---

## 10. Debugging Workflow Quick Reference

### Quick Reference: Tool Selection

| Debugging Need | Tool to Use | action |
|----------------|-------------|--------|
| Whether the compiler is available | `check_environment` | check/detect |
| Project configuration details | `delphi_project` | info |
| Recompile | `delphi_project` | compile |
| Verify crash after compiling | `delphi_project` | compile + run_verify |
| Code static analysis | `delphi_project` | audit |
| Code skeleton overview | `delphi_project` | ast |
| Read source code | `delphi_file` | read |
| Modify source code | `delphi_file` | replace/insert/delete |
| API definition lookup | `delphi_kb` | search |
| API reference analysis | `delphi_kb` | search(search_type="reference") |
| Coding rules | `get_coding_rules` | (section) |
| Start the program and screenshot | `automate_delphi` | gui |
| Full control tree | `automate_delphi` | gui(dumpstate) |
| Read runtime property | `automate_delphi` | gui(rget) |
| Write runtime property | `automate_delphi` | gui(rset) |
| Call method | `automate_delphi` | gui(rcall) |
| Runtime capability discovery | `delphi_rtti` | discover |
| Runtime method call | `delphi_rtti` | call |
| View Git history | `code_hosting` | git_log/git_show |
| Reuse experience | `experience` | search |
| Console program interaction | `automate_delphi` | console |
| Screenshot text recognition | `ocr` | recognize |
| Screenshot comparison | `ocr` | diff |
| View control tree statistics | `automate_delphi` | gui(formsum) |
| File encoding detection/conversion | `delphi_file` | encode |
| Version rollback | `delphi_file` | backup/restore |
| Format code | `delphi_file` | format |

### Quick Reference: Symptom → First Action

| Symptom | First Step | Second Step |
|---------|-----------|-------------|
| Compile fails, reports missing file | `delphi_project(action="info")` to check search path | `check_environment(action="check")` to confirm compiler |
| Compile fails, syntax error | `delphi_file(action="read")` to read the file that reported the error | `delphi_kb` to look up API usage |
| Program crashes immediately on startup | `compile(run_verify=true)` to capture the exception | `automate_delphi(gui)` to inspect state |
| Specific operation triggers crash | `automate_delphi(gui)` to reproduce the crash | `dumpstate` + `rget` to inspect running state |
| Interface display incorrect | `automate_delphi(capture)` screenshot | `dumpstate` to view control properties |
| Calculation result incorrect | `delphi_project(action="ast")` skeleton analysis | `delphi_file(read)` to read key code |
| Exception after long-running operation | `delphi_project(action="audit")` static analysis | Check resource leaks/thread safety |
| Reports BPL/DLL not found | `delphi_project(action="info")` to check linking method | Static link or prepare runtime environment |
| Debug works fine Release crashes | Compare compile settings of the two configurations | Check optimization level and conditional compilation |
| Third-party library compile failure | `delphi_kb(action="stats")` to check KB status | Rebuild the third-party library KB |
| Console output abnormal | `automate_delphi(console)` interactive testing | Check stdin/stdout handling |
| Interface responds slowly | `automate_delphi(formsum)` to check control count | AST analysis of main-thread time-consuming operations |
| Chinese garbled text/encoding issues | `delphi_file(encode)` to detect encoding | Uniformly save as UTF-8 with BOM |
| Tool call times out/fails | Classify the error type (§13.1) | Switch inspection method or restart |

### Quick Reference: Output Artifacts for Each Debugging Stage

| Stage | Content that should be produced |
|-------|--------------------------------|
| Problem confirmation | Exception information / error description / reproduction steps |
| Environment confirmation | Compiler status / project configuration summary |
| Evidence collection | Code snippets / control tree / property values / screenshots |
| Root cause analysis | Root cause type (configuration/code/environment/third-party library) + evidence chain |
| Fix plan | Specific modification content + expected effect |
| Verification | Compile passes / run_verify passes / screenshot confirmation |

---

## 11. Console Application Debugging

### 11.1 Automation Mode Selection

Console programs have no VCL/FMX window, so use the `console` mode of `automate_delphi` rather than `gui` mode:

```python
# Console interaction: send command + wait for specific output
automate_delphi(
    action="console",
    app_path="Win32/Debug/ConsoleApp.exe",
    input="--help\n",              # Send to stdin
    expect="Usage:",                # Wait for this pattern in stdout
    timeout=15)
```

### 11.2 stdin/stdout Interaction

```python
# Continuous interaction (only the last expect serves as the return condition)
automate_delphi(
    action="console",
    app_path="App.exe",
    input="user\npass123\n",       # Simulate login input
    expect="login successful",
    timeout=10)

# No expect: run until exit and return all stdout+stderr
automate_delphi(
    action="console",
    app_path="BackupTool.exe",
    args=["--backup", "data.db"],
    timeout=30)
```

### 11.3 Process Reuse (keep_alive)

```python
# Start and keep alive
automate_delphi(action="console", app_path="App.exe",
    keep_alive=True, expect="prompt>")

# Subsequent reuse (app_path matches the path of the previous call)
automate_delphi(action="console", app_path="App.exe",
    input="process file.txt\n", expect="OK")

# Exit cleanup
automate_delphi(action="console", app_path="App.exe",
    input="exit\n", keep_alive=False)
```

**⚠️**: The `keep_alive` timeout for console debugging is 5 minutes; the keep_alive of GUI mode and console mode are independent.

### 11.4 Console vs GUI Mode Selection

| Judgment Basis | Use console | Use gui |
|----------------|-------------|---------|
| Has a window interface | — | ✅ |
| Pure command-line tool | ✅ | — |
| Needs screenshot verification | — | ✅ |
| Needs to read control properties | — | ✅ (rget/dumpstate) |
| Only needs stdin/stdout | ✅ | — |
| Not sure | (auto mode automatically detects the PE header) | |

---

## 12. Performance Issue Triage

### 12.1 GUI Performance (formsum)

Calculate the total control count of all Forms/Frames at compile time to predict DFM performance risks:

```python
automate_delphi(
    action="gui",
    app_path="App.exe",
    script=[
        {"cmd": "formsum"},
    ])
```

Returns the control count of each Form/Frame. **Prioritize checking loop/iteration operations in forms with control count > 100**.

### 12.2 Response Delay Diagnosis

```python
# 1. AST skeleton to quickly understand the overall architecture
delphi_project(action="ast", base_dir="src")

# 2. Check whether there are time-consuming operations on the main thread (file/network/database)
# Use delphi_kb to search for TThread.CreateAnonymousThread usage
delphi_kb(query="TThread", search_type="class", kb_type="project")

# 3. Check whether the necessary asynchronous processing pattern is missing
# Large data loading → Pagination / virtual list
# File operations → TTask / TThread
# Database queries → Asynchronous query + callback to update UI
```

### 12.3 Slow Startup

```python
# 1. Check whether the DFM has a large amount of images/data embedded at design time
# 2. Check the initialization logic in FormCreate / OnCreate
# 3. Check whether there are delayed loads of DLL/BPL
delphi_project(action="info", project_path="Project.dproj")
# Check the RuntimeLibrary linking method
```

### 12.4 Tool Selection Quick Reference

| Need | Tool/Command |
|------|-------------|
| Count controls | `automate_delphi(formsum)` |
| Code skeleton | `delphi_project(ast)` |
| Static analysis (including performance mode) | `delphi_project(audit)` |
| Configuration view | `delphi_project(info)` |

---

## 13. Tool Call Exception Recovery

### 13.1 Exception Classification and Handling

When a tool call fails, do not retry or bypass immediately—classify first:

| Error Symptom | Possible Cause | Handling Method |
|--------------|---------------|-----------------|
| `File not found: xxx.dproj` | Wrong project path | Use `delphi_kb` or `Glob` to search for the correct `.dproj` location |
| `Timeout` (30s+) | Compile timeout/process stuck | Increase timeout or check DCC for infinite loop compilation |
| `Access Denied` | File in use | Check whether the IDE has the file open |
| `Invalid JSON response` | Pipe communication exception | Restart the program (exit → relaunch) |
| `Connection lost` | Target program has exited | Use `compile(run_verify=true)` to check whether it crashes on startup |
| `RTTI discovery failed` | Program has not linked DaofyAutomation | Switch to `automate_delphi(gui)` |
| `Unknown command: xxx` | Command spelling error | Async commands in `automate_delphi(gui)` return ACK immediately after execution and return immediately; you need to wait for subsequent commands to verify |
| exit code 2 | Pre/post build event failed | Check detailed output; check git hooks / event scripts |

### 13.2 Asynchronous Command Waiting Strategy

Commands in the `automate_delphi(gui)` script are divided into async and sync. Async commands (click/type/key/rcall/rset/move/drag/dlgclick/msgclick) return ACK immediately after being issued, without waiting for side effects to complete.

**Pitfall**: Immediately executing a sync command that depends on the side effects of an async command may read stale state.

```
❌ Wrong: Screenshot immediately after clicking
  click → capture  → May capture the screen before the UI has updated

✅ Correct: Wait after clicking
  click → wait(ms=500) → capture
  or click → waitfor(target=..., prop=..., value=...) → capture
```

### 13.3 Rollback and Retry Strategy

```python
# First layer: Increase timeout and retry
# Second layer: Switch inspection method
#    automate_delphi(gui) fails → try delphi_rtti or vice versa
# Third layer: Use the experience library to check whether a similar exception has been solved before
experience(action="search", query="tool call exception pipe timeout")
```

### 13.4 Concurrent Write Protection

Multiple tool calls modifying the same file simultaneously will cause conflicts. `delphi_file(action="write")` uses dirty mark detection—files that are attempted to be written without being read will be marked as "dirty" and report an error.

**Safe approach**:
1. `delphi_file(action="read")` to read the file
2. Analyze and determine the modification plan
3. `delphi_file(action="write", edits=[...])` to submit edits
4. Ensure the latest version has been read before each modification

---

## Appendix: Debugging Information Quick Reference

### Delphi Exception Class Hierarchy

```
Exception
  ├─ EAbort                  Silent exception that does not display an error dialog
  ├─ EAccessViolation        Access violation (null pointer/dangling reference)
  ├─ EAssertionFailed        Assert failed
  ├─ EArgumentException      Argument error
  │    ├─ EArgumentOutOfRangeException
  │    └─ EArgumentNilException
  ├─ EConvertError           Type conversion failure (StrToInt, etc.)
  ├─ EDatabaseError          Database error
  ├─ EDivByZero              Integer division by zero
  │    └─ EZeroDivide        Floating point division by zero
  ├─ EExternalException      Windows structured exception wrapper
  ├─ EInvalidCast            Invalid type cast (as operator)
  ├─ EInvalidOperation       Invalid component operation (operating without a Handle)
  ├─ EInvalidPointer         Invalid pointer (usually double free)
  ├─ EOSError                Windows API error
  ├─ EOutOfMemory            Out of memory
  ├─ EOverflow               Integer overflow
  ├─ ERangeError             Range check failure (when {$R+})
  ├─ EStackOverflow          Stack overflow (usually infinite recursion)
  └─ EStringListError        TStringList operation error
```

### Key .dproj Properties

| Property Name | Meaning | Reason to Check During Debugging |
|--------------|---------|----------------------------------|
| `DCC_UnitSearchPath` | Unit search path | When .dcu cannot be found |
| `DCC_Define` | Conditional compilation symbols | Debug/Release behavior differences |
| `DCC_Optimize` | Whether to optimize | Release crashes |
| `DCC_AssertionsAtRuntime` | Runtime Assert | AssertionFailed exception troubleshooting |
| `DCC_RangeChecking` | Range checking | ERangeError troubleshooting |
| `DCC_OverflowChecking` | Overflow checking | EOverflow troubleshooting |
| `RuntimeLibrary` | Runtime library linking method | When BPL cannot be found |
| `OutputType` | Output type | exe/dll related configuration |
| `Base` | Base output directory | Artifact path |

### Debugging-Related Command Lines (For reference only; do not directly use dcc32/msbuild)

| Concept | MSBuild Property | dcc32 Parameter |
|---------|-----------------|-----------------|
| Search path | `DCC_UnitSearchPath` | `-U` |
| Conditional compilation | `DCC_Define` | `-D` |
| Output path | `DCC_ExeOutput` | `-E` |
| Debug information | `DCC_DebugInfoInExe` | `-$D+` |
| Optimization | `DCC_Optimize` | `-$O+` |
| Range checking | `DCC_RangeChecking` | `-$R+` |

### Debug Modification Safety Mechanisms

`delphi_file` has the following safety mechanisms when modifying files. The AI needs to understand and cooperate with the workflow:

| Mechanism | Trigger Condition | AI Response |
|-----------|------------------|-------------|
| **Duplicate detection** | The content being written is the same as the file content | No action needed, operation is skipped |
| **Dirty mark** | The file was read and then modified by another operation, and a write is attempted without re-reading | Re-`read` to get the latest content before submitting edits |
| **Automatic backup** | Automatically creates a backup in `__history` before each write/replace/insert/delete | No manual operation needed; can be recovered with `backup/restore` after a mistaken modification |
| **Preview mode** | `preview=true` | Preview the diff before deciding whether to actually write |

```python
# Roll back to the previous version
delphi_file(action="backup", backup_action="restore",
    file_path="Unit1.pas")

# List all backup versions
delphi_file(action="backup", backup_action="list",
    file_path="Unit1.pas")
```

**Principle**: To prevent the AI from making multiple modifications at once and making backtracking difficult, compile and verify after each modification. When unexpected situations occur, use `backup/restore` to roll back.