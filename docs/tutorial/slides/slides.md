# Daofy
## Dance with AI · Enjoy the AI Era

---

## Table of Contents

1. What is MCP?
2. What Can Daofy Do?
3. Installation (AI Automatic)
4. Knowledge Base Search
5. Compilation and Formatting
6. AI-Assisted Development
7. Advanced Features
8. Complete Workflow Demonstration

---

## What is MCP?

**Model Context Protocol**

- An open protocol proposed by Anthropic
- Allows AI assistants to directly call local tools
- Analogy: AI's "USB interface"

```
AI Assistant ←→ MCP Server ←→ Local Environment
  (Claude, etc.)     (Tools)    (Compiler/File System)
```

---

## What Problem Does MCP Solve?

**Traditional AI-assisted development:**

```
User: "Help me compile the project"
AI: "Please open the command line and enter msbuild..."
```

**With an MCP Server:**

```
User: "Help me compile the project"
AI: ✅ Compilation succeeded (calling MCP tool)
```

AI changes from "giving advice" to "doing it for you".

---

## Daofy Feature Overview

| Module | Function |
|------|------|
| 🔧 Compilation | Project compilation, syntax checking, batch compilation |
| 📚 Knowledge Base | 300k functions, 160k page index |
| 📝 File Operations | Read/write/format/backup/uses management (including pasfmt) |
| 🧩 Component Management | DFM add/remove/modify + .dpk compile/install |
| 📋 Coding Standards | Standards-driven code generation and audit |
| 🛡️ Runtime Verification | Auto-run after compile, detect startup crash |
| 🔍 Runtime Audit | Scan DFM component classes, detect missing uses |
| 🔗 RTTI Bridge | Runtime discover/call Delphi object published+public methods |
| 🤖 Automated Testing | GUI screenshot + Console interaction, automatic PE detection |
| 🧠 Experience Memory | AI experience auto deduplicated save + semantic search |
| 📄 Software Copyright Generation | Source + manual + summary table, browser PDF rendering |
| 🔄 Version Update | One-click check/update Daofy version |

---

## Installation Process

**The user only needs:**

```
User: Help me install Daofy MCP Server
```

**AI automatically completes:**
1. ✅ Check Python/Git/7-Zip
2. ✅ Clone GitHub repository
3. ✅ Create virtual environment + install dependencies
4. ✅ Automatically detect AI client and configure

> 💡 The whole process is completed in the conversation, no manual operation required

---

## Knowledge Base Scale

| Knowledge Base | Files | Classes | Functions | Size |
|--------|--------|--------|----------|------|
| Delphi source code | 2,798 | 163,737 | 300,228 | 260 MB |
| Third-party libraries | 1,800 | 5,724 | 28,801 | 27 MB |
| Documentation (CHM) | 160,328 | — | — | 1,306 MB |

**Total: nearly 170k classes, 330k functions, 160k documentation pages**

---

## Knowledge Base Search

| Search Method | Usage | Example |
|----------|------|------|
| 🎯 Exact search | Known class/function name | `TStringList`, `Split` |
| 🔍 Semantic search | Natural language description | "JSON deep comparison" |
| 🔗 Reference query | Find who references a unit | Which files reference `Vcl.Forms` |

> Search strategy: first guess the exact name → then fall back to semantic search

---

## Semantic Search — Discover Hidden APIs

**Scenario: You don't know what the API is called**

```
User: Does Delphi have a function that can compare whether
      two JSON objects have the same structure?
```

**Traditional way**: browse CHM / Google / StackOverflow

**AI + KB way**:
1. Semantically search 300k functions
2. Hit `TJSONObject.Equals`
3. Confirm signature → use directly

---

## Knowledge Base-Driven Code Generation

**Scenario: Connect to SQLite with FireDAC**

```
User: Help me write a SQLite database management unit
```

**AI's workflow:**

```
① get_coding_rules()         → Get standards
② delphi_kb(TFDConnection)  → Look up API signature
③ delphi_kb(TFDQuery)       → Look up parameter binding
④ delphi_file(action="write", edits=[...]) → Generate code (auto backup)
⑤ delphi_project(action="compile") → Compile verification
```

> 💡 Rather than writing from memory, first check KB to confirm API

---

## Compilation Features

| Capability | Description |
|------|------|
| Project compilation | .dproj / .dpr → exe/dll |
| Single-file check | .pas syntax check |
| Batch compilation | .groupproj → in dependency order |
| Multi-platform | Win32/Win64/OSX/iOS/Android/Linux |
| Configuration | Debug / Release + custom options |

---

## Complex Compilation Error Diagnosis

**Example: E2511 must have a comparer**

```
TDictionary<TCustomKey, string>  // Compile error!
```

**AI's diagnosis chain:**
1. Search KB → `TDictionary` generic constraints
2. Search KB → `TEqualityComparer` base class
3. Root cause: record type has no default comparer
4. Generate `TCustomKeyComparer` → fix → compilation passes

---

## Unified File Operations + Automatic Backup

**Unified file interface `delphi_file`:**

```
delphi_file(action="read")              — Read file (class/function navigation + automatic DFM binary→text conversion)
delphi_file(action="write", edits=[...]) — Write file (edits format, default backup=True)
delphi_file(action="format")            — Format (pasfmt-driven, automatic backup)
delphi_file(action="backup")            — Backup management (create/list/restore)
delphi_file(action="uses")              — uses clause add/remove (add/remove)
manage_component(action="add|remove|modify") — DFM component management + automatic PAS declaration synchronization
```

**Write means backup — no extra steps:**

```
delphi_file(action="write", file_path="Unit1.pas", edits=[{start_line:1, content:"..."}])
                              ↑ backup=True by default, automatically create __history backup
```

**Backup mechanism:**

```
Source file                 __history/
DataProcessor.pas  →  DataProcessor.pas.~1~
                       DataProcessor.pas.~2~  (automatically increments)
```

**Backup management:**
- View backup list `backup_action="list"`
- Restore specified version `backup_action="restore", version=3`
- Compatible with Delphi IDE's History mechanism

> 💡 Legacy interfaces `read_source_file` / `format_delphi` have been merged into this tool

---

## Transparent Handling of Binary DFM Files

**DFM form files also have a binary format, which is troublesome to handle in traditional ways:**

```
Read binary DFM → garbled text → still need manual conversion
Save after editing → wrong format → compiler error
```

**`delphi_file` transparent handling:**

```
delphi_file(action="read",  file_path="Form1.dfm")
  → Binary detected → automatically convert to text → return readable content ✓

delphi_file(action="write", file_path="Form1.dfm", edits=[...])
  → Original file is binary → automatically convert back to binary after writing ✓
```

**Component-level operations: `manage_component` tool — no need to manually edit DFM text**

```
manage_component(action="add",    target_dfm="Form1.dfm",
  new_component_class="TButton", properties={"Caption": "OK"})
  → Add button to DFM + automatically declare field and event in PAS ✓

manage_component(action="modify", component_name="Button1",
  properties={"Caption": "确定", "Enabled": "False"})
  → Modify properties + automatically synchronize PAS ✓

manage_component(action="remove", component_name="Button1")
  → Remove component + automatically clean up PAS declarations ✓
```

**Principle: compile the Delphi converter on demand, call `ObjectResourceToText` / `ObjectTextToResource`**

> 💡 Editors do not need to care about DFM format; read/write interfaces are consistent

---

## Coding Standards Control AI Behavior

**Same requirement, different rules → different code**

```
User: Write a string utility unit
```

| Dimension | Modern standard | Legacy standard |
|----------|----------|--------|
| Naming | T + PascalCase | no-prefix camelCase |
| Parameters | A + PascalCase | Hungarian notation |
| Indentation | 2 spaces | 4 spaces |
| begin | new line | end of line |

> 💡 Rules are not only queried, but also executed

---

## Code Audit + Create Tickets

**Audit dimensions:**
- 🔴 Resource leaks (try/finally)
- 🔴 Deleting elements inside a loop
- 🟡 Magic numbers
- 🟡 Unused variables
- 🔵 Function too long

**Audit results → automatically create Issue**

```
GitHub Issue / Gitee ticket
├── Title: LegacyData.pas code quality issues
├── Problem list (including line numbers/severity/suggestions)
└── Issue link
```

---

## Multi-file Refactoring

**Scenario: TStringList → TArray\<String\>**

```
User: Replace all TStringList in the project
      with TArray<String>
```

**AI workflow:**
1. 🔗 Reference query → assess impact scope
2. 📝 Modify file by file (delphi_file write auto-backup by default)
3. ✅ Compile and verify after each change
4. 🎨 Uniform formatting

> 💡 You make decisions, AI executes + verifies

---

## Batch Multi-Project Compilation

**Scenario: Compile the entire solution**

```
ProjectGroup.groupproj
├── LibProject/ (compile first, because it is depended on)
└── AppProject/ (compile later)
```

```
User: Release / Win64, compile all
AI: ✅ LibUtils → ✅ MainApp  completed in one click
```

> 💡 Automatically parse BuildOrder and compile in dependency order

---

## Practical Search in Documentation Knowledge Base

**After building: search 160k pages of help documentation with one sentence**

```
User: Parameter description of TCanvas.Draw,
      especially the role of DrawOpacity
```

```
Result:
DrawOpacity: Drawing opacity
  0   = Completely transparent
  255 = Completely opaque (default)
```

> 💡 Two orders of magnitude faster than browsing CHM

---

## Install Component Packages

```
User: Install MyComponent.dpk
```

**AI completes:**
1. Compile .dpk
2. Detect whether it is a design-time package
3. Automatically register to IDE registry

```
User: View installed component packages
AI: List all registered BPL packages
```

---

## Complete 0-to-1 Workflow

```
Requirement: JSON configuration file management unit
```

```
① get_coding_rules                       → Get standards
② delphi_kb(TJSON*)                      → Search API to confirm signature
③ delphi_file(action="write", edits=[...]) → Write code (automatically backed up to __history)
④ delphi_file(action="format")           → Format code
⑤ delphi_project(action="compile")              → Compile verification
⑥ delphi_project(action="compile", run_verify=True) → Runtime verification (catch CreateForm stage crashes)
⑦ get_coding_rules(section="review")      → Audit
⑧ delphi_project(action="runtime")              → Runtime registration check (missing uses detection)
⑨ experience(action="save")              → Save experience (AI automatic deduplication)
⑩ Cleanup + confirm backup
```

> 💡 Before rebuilding, check the existing help documentation directory first to avoid duplicate builds

---

## Runtime Startup Crash Detection

**Exceptions during the CreateForm stage cannot be caught by try/except in .dpr**

```
Application.CreateForm(TMainForm, MainForm); // ← exception swallowed internally by VCL
```

**Solution: TStackTraceManager**

```
StackTrace.pas
├── TStackTraceManager (singleton)
│   └── Hook RTL Exception.GetExceptionStackInfoProc
│       → Capture immediately at exception raise time (not dependent on try/except)
├── TDefaultExceptionLogger
│   └── Write to exception.log (UTF-8 BOM)
└── ParseMapFile
    └── Parse .map file → function name + line number
```

---

## run_verify Workflow

```
delphi_project(action="compile", run_verify=True)

① inject_verify_units()
   ├── Back up .dproj / .dpr
   ├── Inject DCCReference + DCC_UnitSearchPath
   └── Inject TStackTraceManager initialization

② Recompile (with StackTrace.pas)

③ Start exe and run for 5 seconds

④ Check exception.log
   ├── Exists → detect_encoding read → embed in MCP response
   └── Does not exist → ✅ Verification passed

⑤ Restore original .dproj / .dpr
```

**Example output:**
```
❌ Runtime verification failed - exception detected:
[2026-05-25 13:02:46] Exception: Test exception: Simulated startup crash
  Vcl.Forms.TCustomForm.DoCreate+$37 [Vcl.Forms.pas:4160]
  TestCrash.TestCrash+$55 [TestCrash.dpr:16]
```

---

## Runtime Registration Check

**Compilation passes ≠ runs correctly** — component runtime registration may be missing

```
delphi_project(action="runtime", project_path="App.dproj")
```

**Check principle:**
```
src/rules/runtime_registry.json rule table
├── "TFDQuery" → requires FireDAC.DApt
├── "TFDMemTable" → requires FireDAC.DApt  
├── "TChart" → requires VCLTee.TeEngine
└── ...
```

**Scan flow:**
```
① Scan component class names in .pas/.dfm
② Match rule table
③ Check whether required units are included in uses clause
④ Report missing items
```

**Zero-config extension:** to add a rule, just edit the JSON file, no code changes required

---

## Example: FireDAC SQLite Employee Information Entry

**Demo project rebuilt from scratch `employee-input/`:**

```
employee-input/
├── EmployeeInput.dproj   # FireDAC SQLite project
├── Form.Main.pas         # Main form 130 lines
├── Form.Main.dfm         # Left-right split layout
└── Win32/Debug/          # Compile output
    ├── EmployeeInput.exe # 3.8 MB code
    └── employees.db      # Automatically created on first run
```

**Key points:**
- `TFDPhysSQLiteDriverLink` + `TFDConnection` → auto create tables
- SQLite DB automatically created in the same directory as the exe
- DBGrid list (read-only) + DBEdit edit panel (left-right split)
- UTF-8 BOM encoding — eliminates `W1057` implicit string conversion warning
- `delphi_project(action="compile", run_verify=True)` — compile → runtime verify one-click pass

---

## Automated Testing — GUI Mode

**Delphi native automation unit `DaofyAutomation` based on Named Pipe**

```
automate_delphi(action="gui", app_path="App.exe",
  script=[{"cmd":"goto","target":"TMainForm"},
          {"cmd":"click","target":"btnOK"},
          {"cmd":"capture","target":"result.png"}])
```

**Protocol: JSON request/response**

| Command | Description |
|------|------|
| goto / click / dblclick | locate/click/double-click components |
| type / key | input text / key press |
| capture / listwnd / dumpstate | screenshot / window list / control tree |
| wait / waitfor | wait timeout / wait for window to appear |
| rcall / rget / rset | call/read/set component properties |

**No manual configuration:** automatically link the DaofyAutomation unit at compile time via `DCC_UnitSearchPath=`

---

## Automated Testing — Console Mode

**Console program interaction based on subprocess stdin/stdout, no Delphi-side modification required**

```
automate_delphi(action="console", app_path="Tool.exe",
  input="Y\n", expect="Continue?")
```

```
automate_delphi(action="auto", app_path="Deploy.exe",
  input="\n", expect="success", args=["--silent"])
```

**Parameters:**
| Parameter | Description |
|------|------|
| input | Text sent to stdin (supports `\n` newline) |
| expect | Expected output pattern (returns only when matched) |
| timeout | Timeout in seconds (default 30s) |
| args | Command-line argument list |

**Windows PE automatic detection:** `action="auto"` reads the EXE header Subsystem field to distinguish GUI/Console, no manual specification required

---

## RTTI Bridge — Discover Delphi Capabilities at Runtime

**Three-step method**: no source code required, discover and call runtime objects through RTTI

```
① delphi_rtti(action="guide")     → Usage guide
② delphi_rtti(action="discover")  → Scan published+public methods+parameters of all classes
③ delphi_rtti(action="call",      → Call specific method
     class_name="TMainForm",
     method="LoadCustomer",
     params={"customerName": "张三"})
```

**Application scenarios:**
- Remote control a running Delphi application
- Directly operate business objects in AI conversation
- Dynamically discover all components and methods of VCL Form
- No additional program modification required (just link DaofyAutomation)

---

## Experience Memory — AI Learns to Remember

**Agent experience accumulates automatically, fewer problems over time**

```
experience(action="save")
  ├─ Auto deduplication: similarity > 0.85 → merge into old record
  ├─ Save successfully solved problems + solution steps
  └─ Automatically search matching experience for subsequent tasks

experience(action="search", query="...")
  └─ Semantically search existing experience to avoid repeating pitfalls

experience(action="merge", ids=[...])
  └─ Merge multiple similar experiences into one abstract experience
```

**Effect**: next time the same problem occurs, AI directly uses the verified solution

---

## Software Copyright Document Generation — One-Click Draft

**Automated tool that meets China software copyright registration requirements**

```
generate_copyright(action="generate")
  ├─ Source code document (page-by-page screenshots + line numbers)
  ├─ User operation manual (organized by scenario)
  └─ Summary table (project information + document list)

generate_copyright(action="validate")
  └─ Check configuration completeness
```

**Features:**
- Browser PDF rendering, WYSIWYG
- Automatically validate document completeness
- Support configuration updates

---

## Version Update — Stay Up to Date

```
daofy_update(action="check")   → Check for new version on GitHub
daofy_update(action="update")  → git pull automatic update
daofy_update(action="version") → Show current version
```

---

## Supported Platforms
| Trae | Automatic |
| CodeArts Agent | Automatic |
| Cursor | Automatic / Manual |
| Windsurf | Automatic |
| Tongyi Lingma | Automatic |
| Doubao | Automatic |
| Kimi | Automatic |
| More... | install.ps1 auto-detection |

---

## Summary

| Capability | One sentence |
|------|--------|
| 🔧 Compilation | Compile + diagnose + batch + run_verify |
| 📚 KB search | Exact + semantic + reference |
| 📝 File operations | Read/write/format/backup/uses management (including pasfmt) |
| 🧩 Component management | DFM add/remove/modify + component package compile/install + PAS synchronization |
| 📋 Standards | Drive generation + drive audit |
| 🛡️ Runtime verification | Startup crash detection + runtime registration audit |
| 🔗 RTTI bridge | Runtime discover/call Delphi object methods |
| 🤖 Automation | Refactor + fix + tickets + automated testing |
| 🧠 Experience memory | AI automatically accumulates experience, deduplication + semantic search |
| 📄 Software copyright generation | Source + manual + summary table, one-click PDF draft |
| 🔄 Version update | One-click check/update Daofy |

---

## Open Source Information

**GitHub**: [github.com/chinawsb/daofy](https://github.com/chinawsb/daofy)

**License**: MIT

**Tech stack**: Python 3.10+ / MCP Protocol

**Communication**: GitHub Issues

---

## Q&A

**Thanks for watching!**

If you find it useful, please give the project a Star ⭐

---

# Appendix: Demo Preparation Checklist

## Pre-recording Preparation
- [ ] Python 3.10+ / Git / Delphi IDE installed
- [ ] Project cloned + dependencies installed
- [ ] AI client configured with MCP Server
- [ ] Documentation knowledge base pre-built
- [ ] All demo assets in the correct directory

## Key Operation Tips
- The installation section is entirely AI conversation; do not show the terminal
- For complex scenarios, recommend picture-in-picture showing VS Code
- Pause for 2-3 seconds when showing audit results
- Complete in advance or accelerate time-consuming operations such as building the documentation KB