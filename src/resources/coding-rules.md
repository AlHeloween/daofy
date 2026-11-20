# Delphi Coding Standards
> Last updated: 2026-07-17 | Version: 1.14.0

## Workflow Overview
```
Environment check → Query KB to confirm API → Write code (auto-backup) → Format → Compile & verify → Code review → Cleanup
  ①                    ②                        ③                        ④          ⑤                  ⑥            ⑦
                                                                                                  ↓ Optional
                                                              ┌──────────────────────────────────────┐
                                                              │  ⑧ Automated UI interaction testing    │
                                                              │  ⑨ Console program interaction verify  │
                                                              └──────────────────────────────────────┘

    Invoke tool      →  (MCP tool name)
  ① Environment check →  check_environment / get_coding_rules
  ② Query KB to confirm API →  delphi_kb / delphi_file
  ③ Write code       →  delphi_file(action="write")
  ④ Format           →  delphi_file(action="format")
  ⑤ Compile & verify →  delphi_project(action="compile")
  ⑥ Code review      →  get_coding_rules(section="review")
  ⑦ Cleanup          →  delphi_file
  ⑧ Automated UI test →  automate_delphi
  ⑨ Console test     →  subprocess (Python side)
  🔧 Supplementary references:
     Human-AI collaboration →  get_coding_rules(section="human_collab")   (§⑩ Request intervention at blockers)
     Experience library      →  get_coding_rules(section="experience")     (§⑪ Record solutions)
```

---

## 📁 Directory Constraints

AI Agents must follow the directory conventions below to facilitate later cleanup and maintenance.

### Standard Directory Structure

```
project/
├── src/                    ← Source code (Python/Delphi)
├── tests/                  ← Test cases (test_*.py, run_*.py)
├── docs/                   ← Documentation (user manuals, design docs)
├── scripts/                ← Auxiliary scripts (build/deploy/tool scripts)
├── tools/                  ← Tool programs (pasfmt/7z/daudit etc.)
├── data/                   ← Knowledge base data (runtime-generated, gitignore)
├── logs/                   ← Log files (runtime-generated, gitignore)
├── config/                 ← Configuration files (compilers.json etc.)
├── releases/               ← Release packages (gitignore)
├── benchmarks/             ← Performance benchmarks (gitignore)
└── .tmp/                   ← Temporary working directory (gitignore)
```

### Directory Usage Constraints

| Directory | Purpose | Cleanup strategy | gitignore |
|-----------|---------|------------------|-----------|
| `tests/` | Formal test cases (test_*.py) | Maintained with the project | ❌ Version controlled |
| `tests/tmp_*` | Temporary test scripts | **Delete after use** | ✅ `tmp_*.py` |
| `.tmp/` | Agent temporary work files | **Clean up when task ends** | ✅ `.*/` |
| `.pytest-tmp-*/` | pytest temporary directory | **Auto-cleanup when test ends** | ✅ `.*/` |
| `docs/` | Formal documentation | Maintained with the project | ❌ Version controlled |
| `docs/todos.md` | Personal notes | Not committed | ✅ |
| `scripts/` | Reusable scripts | Maintained with the project | ❌ Version controlled |
| `_dump_*.py` | One-off debug scripts | **Delete after use** | ✅ `_dump_*.py` |
| `_debug_*.py` | Debug scripts | **Delete after use** | ✅ `_debug_*.py` |
| `logs/` | Runtime logs | **Clean up periodically** | ✅ |
| `data/` | Knowledge base data | Rebuild as needed | ✅ |
| `snapshots/` | UI screenshot snapshots | **Delete after use** | ✅ |
| `__history/` | Delphi file backups | Managed automatically by IDE | ✅ |
| `Win32/` `Win64/` | Delphi compile output | **Clean up after compiling** | ✅ |

### Naming Conventions

| Type | Naming pattern | Example |
|------|----------------|---------|
| Formal tests | `test_*.py` | `test_compiler.py` |
| Temporary tests | `tmp_test_*.py` | `tmp_test_new_feature.py` |
| Debug scripts | `_debug_*.py` / `_dump_*.py` | `_dump_ast.py` |
| Temporary output | `tmp_*` / `test_*.png` | `tmp_output.txt` |

### Cleanup Rules

```
Must clean up when task completes:
1. Temporary files → delete tmp_*, _dump_*, _debug_*
2. Temporary directories → delete .tmp/, .pytest-tmp-*
3. Compile output → delete Win32/, Win64/, *.dcu, *.exe
4. Debug artifacts → delete test_*.png, temp_*.json
```

### ⚠️ Prohibitions

- ❌ Creating temporary files or test scripts under `src/`
- ❌ Scattering temporary scripts in the project root (use `.tmp/` or `scripts/`)
- ❌ Naming temporary files without a prefix (e.g. `test.py` instead of `tmp_test.py`)
- ❌ Keeping `.pytest-tmp-*` directories after the task ends

---

<!-- Automated test architecture content has been migrated to src/resources/coding-rules/testing/automation/architecture.md -->
<!-- Detailed technical reference: MCP Resource delphi://automation/index (entry), delphi://automation/architecture (architecture methodology) -->

## ⚙ Automated Test Architecture

The complete methodology for automated testing (RTTI/OCR decision matrix, perceive-plan-execute-feedback loop, code-aware testing, prompt templates, experience loop, assertion system, etc.) has been migrated to a separate directory:

```
resources/coding-rules/testing/automation/
├── index.md              ← Main entry (@when: during automated testing)
├── architecture.md       ← Architecture methodology (original coding-rules.md §§A-J)
├── reference/            ← Framework reference (script format/protocol/repair loop)
└── scenarios/            ← Scenario templates (A-O, including reusable JSON)
```

**Entry**: `get_coding_rules(section="automation")` → automatically reads `resources/coding-rules/testing/automation/index.md`
**Architecture method**: `resources/coding-rules/testing/automation/architecture.md`
**Command reference**: `delphi://automation/script-schema` (MCP Resource)
**Scenario templates**: `resources/coding-rules/testing/automation/scenarios/` (files A-O)


<!-- The detailed content of §§A-J automated architecture below has been migrated to resources/coding-rules/testing/automation/architecture.md -->
<!-- No longer duplicated here -->

## ① Environment Check
```python
check_environment(action="check")       # Confirm compiler status
get_coding_rules()                       # Get workflow overview + section index (default)
get_coding_rules(section="writing")      # Before coding: pull coding standards
get_coding_rules(section="review")       # After compiling: pull review checklist
get_coding_rules(section="list")         # List all available section names
```

---

## ② KB Search (mandatory before coding)
**Before writing any code that references an API, query the KB to confirm the API definition. Never fabricate.**

### Search Priority
| Priority | Method | Applicable |
|----------|--------|------------|
| ⭐1 | `delphi_kb(query="TStringList")` exact class name | Known class name |
| ⭐2 | Try alternative names `TMainForm`→`TfrmMain` | First attempt returned nothing |
| ⭐3 | `search_type="function"` search functions (FF+FP) | Looking up functions |
| ⭐4 | `search_type="reference"` search references | Assessing impact of changes |
| ⭐5 | `search_type="semantic"` Chinese fallback | Exact search fails |

> `search_type="function"` matches both functions (FF) and procedures (FP). `search_type="procedure"` matches procedures only.

### Knowledge Base Scope
| Parameter | Target | project_path |
|-----------|--------|--------------|
| `kb_type="delphi"` | VCL/FMX/RTL official | Not required |
| `kb_type="project"` | Project's own code | **Required** (or auto-detect CWD .dproj) |
| `kb_type="thirdparty"` | Third-party components | Not required |
| `kb_type="document"` | Delphi help documentation (ZVec full-text index) | Not required |
| Default (unspecified) | All three libraries | — |

### Automatic Project Path Detection
```python
# When project_path is omitted, automatically scans CWD and parent directories for .dproj
# When a unique .dproj is found, uses it automatically; when multiple exist, matches by directory name
delphi_kb(query="TfrmMain", kb_type="project")  # Relies on auto-detection
delphi_kb(query="TfrmMain", kb_type="project", project_path="C:/MyProject/Project.dproj")  # Explicitly specified
```

### Reading Source Code
```python
delphi_file(action="read", search_type="class", type_name="TButton")              # Delphi official source
delphi_file(action="read", search_type="function", function_name="Create")         # Delphi official
delphi_file(action="read", search_type="class", type_name="TfrmMain", search_in="project", project_path="...")  # Project source
delphi_file(action="read", file_path="...", start_line=100, limit=200)             # Read by path
```

### Troubleshooting When KB Finds Nothing
```
Class/function not found → Check whether kb_type is correct (use project for project code)
             → Try partial matching (class name only, without namespace)
             → Check whether third-party library is installed/built
             → Search directly by file path System.SysUtils → search by file name
```

---

## ③ Writing Delphi Code

> **Blocker entry**: When you encounter errors, uncertain approaches, repeatedly trying the same solution, or insufficient information requiring guesses while writing code → first consult **§⑩ Pre-check**, and evaluate the trigger conditions to decide whether to request human intervention.

### File Encoding Check (mandatory before modification)
- **Before modifying any Delphi source file, you must first confirm the file encoding to avoid garbled Chinese characters.**
- **Tool routing rule**: Delphi files must be read/written/searched/regex-matched+replaced using `delphi_file`, not the built-in `Read/Edit/Write/grep`.
- ⭐ Prefer `delphi_file(action="read", file_path=...)` to read files (auto-detects encoding, supports BOM/UTF-16/GBK, no manual handling needed)
- When `delphi_file` is unavailable (e.g., operating files directly in bash/python scripts), fall back to manual detection:
  ```python
  # Manual encoding detection (fallback only when delphi_file is unavailable)
  try:
      raw.decode('utf-8')
      encoding = 'utf-8'
  except UnicodeDecodeError:
      encoding = 'gbk'  # Common on Chinese Windows
  ```
- **When writing back, the original encoding must be preserved**; do not force a GBK file to be written as UTF-8
- Using `delphi_file(action="write")` automatically backs up and preserves the original encoding by default; `delphi_file(action="format")` automatically backs up by default
- If the file contains a BOM (UTF-8 BOM / UTF-16 LE/BE), preserve the BOM; do not remove it
- **New Delphi files should uniformly use `utf-8-sig` (UTF-8 with BOM)**: The Delphi compiler treats Chinese string literals in files without a BOM as `AnsiString`, triggering the `W1057 Implicit string cast from 'AnsiString' to 'string'` warning. Writing a BOM with `encoding="utf-8-sig"` makes the compiler correctly recognize it as `UnicodeString`, eliminating this warning. Uniform use also avoids the ambiguity of "whether it contains Chinese".

### Automatic Backup
- `delphi_file(action="write", backup=True)` **is enabled by default** and automatically creates a backup in the `__history` directory before writing, no manual call needed
- Backup file naming: `filename.~version~` (compatible with Delphi IDE)
- Backups of binary DFM files are the original binary version, 100% restorable
- ❌ Delphi files must use `delphi_file`, not the built-in `Read/Edit/Write/grep`
- ❌ Do not use `apply_patch`, shell redirection, PowerShell/Python to write `.pas/.dfm/.dproj/.dpk/.dpr/.inc/.fmx/.groupproj` directly
- ✅ Delphi files must be written via `delphi_file` or Delphi tools registered inside Daofy; the Daofy edit guard records warnings for external writes that bypass Daofy when file monitoring is enabled
- Manual backup/restore/list:
  ```python
  delphi_file(action="backup", file_path="src/Unit1.pas")                           # Manually create a backup
  delphi_file(action="backup", backup_action="list", file_path="src/Unit1.pas")     # List backup versions
  delphi_file(action="backup", backup_action="restore", file_path="src/Unit1.pas", version=3)  # Restore
  ```

### Naming
- **Types**: `T` prefix for classes, `I` for interfaces, `E` for exceptions, `P` for pointers
- **Fields**: `F` prefix `FName: string;`
- **Properties**: PascalCase `property Name: string read FName;`
- **Methods**: PascalCase `procedure CalculateTotal;`
- **Events**: `OnCreate`→`Form1Create`; keep `Before`/`After`
- **Parameters**: add `A` prefix if not already starting with A `procedure SetName(AName: string);`
- **Enums**: value prefix taken from the abbreviation of the enum type name with T removed, e.g. `TAlignment → taLeft, taRight, taCenter`
- **Constants**: ALL CAPS `MAX_BUFFER_SIZE`; scoped constants follow the same rule

### Formatting
- Indent 2 spaces, line width ≤120
- Spaces around assignment/operators, after commas, none inside parentheses
- `begin` on its own line; generic nesting `>>` needs no extra space in modern Delphi
- `uses` clause merged into a single line by default (`format_delphi`'s `uses_style="compact"`);
  pass `uses_style="pasfmt_default"` for pasfmt's default expanded style
```delphi
uses System.SysUtils, System.Classes,  // System
     Vcl.Forms, Vcl.Controls,          // VCL/FMX
     madBasic, madDisAsm,              // Third-party
     MyUnit1, MyUnit2;                 // Project
```

### Generics
- Use descriptive names for generic parameters `TKey, TValue`, not single letters like `T`
- For multi-constraint generics, put each `where` clause constraint on its own line to improve readability
- Avoid deeply nested generics; use a type alias to simplify when nesting exceeds 2 levels: `type TStringArrayList = TArray<TList<string>>`
- Ensure signature ambiguity can be correctly resolved by the compiler when overloading generic methods

### Operator Overloading
- Define operator overloads only for value types (record), avoid for class types
- Operator semantics must be intuitive; do not change conventional meanings (e.g. `+` must not represent subtraction)
- When defining type conversion operators (`Implicit`/`Explicit`), also provide named conversion methods for explicit invocation

### Asynchrony and Multithreading
- Background threads must operate UI controls via the main thread synchronization mechanism
- Access to shared resources must be lock-protected; keep lock granularity small to avoid deadlocks
- Async task lifecycle must be explicitly managed; ensure allocated resources are cleaned up when a task is canceled or fails
- Avoid directly referencing objects in async callbacks; use interface references or weak reference patterns to prevent dangling pointers

### Code Organization
- Each unit should have a single responsibility; avoid "god units"; a unit's code should ideally not exceed 500 lines
- In the `interface` section, arrange in the order: `uses` → type declarations → constants → variables → procedure/function declarations
- In the `implementation` section, arrange in the order: `uses` → auxiliary procedures/functions → interface method implementations
- Group `uses` clauses, separate groups with blank lines, alphabetical order within groups, annotate the group name at the end of each group (as in the example above)

### Version Compatibility
- Wrap cross-version differences in conditional compilation and comment the targeted version: `{$IFDEF VER370} // Delphi 13`
- The target version range should be declared uniformly in the project file or config file, not scattered in code
- Provide a fallback implementation for older versions when using new APIs, to avoid forcing a compiler upgrade

### delphi_file Write Rules

**All line number parameters and outputs of `delphi_file` are 1-indexed, left-closed right-closed intervals.**

| Parameter | Description |
|-----------|-------------|
| `start_line=1` | Start from line 1 of the file (line 1 = 1) |
| `start_line=5, end_line=10` | Replace lines 5~10 (1-indexed `[5, 10]`) |
| `start_line=4, end_line=4` | Replace only line 4 (1-indexed `[4, 4]`) |

**write uniformly uses the edits parameter:**
```python
# Create a new file (auto-created when the file does not exist)
delphi_file(action="write", file_path="Unit1.pas", edits=[{"start_line": 1, "content": "unit Unit1;\n\ninterface\n\nimplementation\n\nend.\n"}])

# Full replacement of an existing file
delphi_file(action="write", file_path="Unit1.pas", edits=[{"start_line": 1, "content": "unit ..."}])

# Partial replacement (replace lines 5~10)
delphi_file(action="write", file_path="Unit1.pas", edits=[{"start_line": 5, "end_line": 10, "content": "new content"}])

# Multi-segment replacement (order doesn't matter, sorted internally)
delphi_file(action="write", file_path="Unit1.pas", edits=[
    {"start_line": 10, "end_line": 12, "content": "..."},
    {"start_line": 5, "end_line": 7, "content": "..."},
])

# Preview mode (does not write to disk, does not clear dirty marker)
delphi_file(action="write", file_path="Unit1.pas", edits=[{"start_line": 5, "end_line": 10, "content": "new content"}], dry_run=True)
```

### Consecutive Editing and Dirty-Marker Protection (v2026.06.12+)

**After a write / format / uses operation the file is marked dirty**; a direct second write receives an error prompt:

```
Please call read first to get the latest line numbers, or use dry_run=true to preview this modification.
```

**Ways to continue writing:**
- Call `read` (automatically clears the dirty marker)
- Provide a non-empty `old_content` in each edit (validates the hit range before writing)
- Call `write(dry_run=True)` to preview the diff only; dry_run does not clear the dirty marker
- Call `write(allow_dirty=True)` (at your own risk; only when you are sure the line numbers are accurate)

**Line-number offset algorithm for consecutive edits:**

Each `write` returns offset information:
```
wrote: Unit1.pas, 1-indexed [5, 10] → [5, 13] (offset: +3) (specified 6), encoding: utf-8
```
- `[5, 10] → [5, 13] (offset: +3)`: **actual line range** → line numbers after writing, offset explicitly given as `+3`
- If the specified line numbers differ from the actual line numbers, `(specified N)` is appended to indicate the AI's line number adjustment
- If `auto_format=True` is enabled, the returned offset **already includes line count changes caused by formatting** (uses expansion, blank line adjustments, etc.), no additional accumulation needed
- When previous edits have accumulated offsets, `ℹ Offset: previous +N line offset, actual line numbers = specified line numbers+N` is appended at the bottom of the diff

The Agent calculates subsequent line numbers based on the following rules:

```
Let a certain write return the post-edit line range [s, e_new]
Then calculate new line numbers for subsequent original line numbers L:
  L < s     → new line number = L         (before the edit region, unchanged)
  L ≥ e_old → new line number = L + offset  (after the edit region, accumulate offset)
  s ≤ L < e_old → the line has been replaced/deleted, cannot be used as a subsequent edit target
```

With multiple writes, the dirty marker blocks the second write; you must read first to confirm line numbers.
Different files can be written in parallel.

**Two fatal errors (never make them):**
1. ❌ Passing `start_line=5` in a write operation thinking it means starting from line 5 → Correct (1-indexed), but don't confuse it with 0-indexed
2. ❌ Forcing continuation after the dirty marker blocks → line numbers are stale; you must read, dry_run, or set allow_dirty=true (only when sure the line numbers are accurate)

**Note: The `uses` action also marks the file dirty and shifts line numbers.**
The offset format returned by `delphi_file(action="uses", ...)` is the same as for write.

**Recommended practice:**
- One modification → `read` → `write(edits=[...])`
- Multiple non-consecutive modifications → `read` → plan all edits → one `write(edits=[...])`
- Add a uses unit → use `delphi_file(action="uses", ...)`, don't compute line numbers manually
- Unsure about line numbers → `read` first, then write

### delphi_file Compact Output Format (v2026.06.12+)

**read output**:
```
# encoding: utf-8, 1-indexed [1, 200] (truncated)
```
| Field | Description |
|-------|-------------|
| `encoding:` | File encoding (utf-8 / utf-16-le / utf-16 / gbk / etc.) |
| `1-indexed [s, e]` | The 1-indexed, left-closed right-closed interval returned this time |
| `(truncated)` | The file exceeds 2000 lines and was truncated (optional marker) |

**write output** (edits):
```
wrote: 1 edits, Unit1.pas, encoding: utf-8, backup: __history\Unit1.pas.~1~

  [5, 10] → [5, 13]  edit #0
    - L5_old
    - L6_old
    + L5_new
    + L6_new
    + L7_new
```
- `wrote: N edits` = number of successful edits
- Each edit is followed by a `- / +` diff preview (full when ≤5 lines, otherwise elided)
- DFM conversion / encoding fallback appends extra markers: `ℹ transcoded: utf-16 → utf-8` / `⚠ fallback: gbk → utf-8` / `format: binary DFM converted` / `formatted: yes`

**dry_run output**:
```
dry_run: 1 edits, Unit1.pas, encoding: utf-8, dry_run: true (not written to disk)

  [5, 10] → [5, 13]  edit #0
    - L5_old
    + L5_new
```

**uses output**:
```
wrote: Unit1.pas, action: added System.SysUtils in interface, uses: SysUtils, 1-indexed [2, 3] → [2, 4], encoding: utf-8
```

### write Usage Recommendations

| Scenario | Recommendation |
|----------|----------------|
| Change 1~2 non-consecutive locations at once | `read` → `write(edits=[...])` |
| Change 3+ non-consecutive locations at once | `read` → `write(edits=[...])` (batch writes are already merged into write) |
| Involves uses unit changes | `uses` action (dedicated to the uses clause, auto-computes offsets) |
| Change 1 complete method/procedure | `read` → note the line numbers → `write(edits=[{start_line:N, end_line:M, content:"..."}])` |

**Be sure to verify the `- / +` preview in the write response**: if you see a mismatch like `- L4_old` paired with `+ L3_NEW`, immediately `read` the file to confirm the target line numbers, then re-plan the edits.

---

## ④ Formatting
```python
delphi_file(action="format", file_path="src/Unit1.pas")
# Formats using pasfmt, automatically handling generic nesting `>>` formatting
```

## ⑤ Compiling
```python
delphi_project(action="compile", project_path="Project.dproj")                         # Full compile
delphi_project(action="compile_file", project_path="Unit1.pas")                        # Single-file syntax check
delphi_project(action="compile", project_path="Project.dproj", build_configuration="Release", target_platform="win64")
# Optional parameters: conditional_defines=["DEBUG"], unit_search_paths=["..."], output_path="..."
```

### Additional Compile Parameters (extra_args)

`extra_args` is a complete parameter array, interpreted by the actual compile backend and appended after the built-in parameters:

```python
# .dproj / .dpr with a same-named .dproj: MSBuild parameters, request TDS/RSM generation
delphi_project(action="compile", project_path="Project.dproj",
        extra_args=["/p:DCC_DebugInfoInTds=true", "/p:DCC_RemoteDebug=true"])

# .dpr without a same-named .dproj: DCC parameters directly
delphi_project(action="compile", project_path="Project.dpr", extra_args=["-VT", "-VR"])
```

Each array element is a complete parameter; do not add outer quotes yourself. If the compiler generates `.tds`/`.rsm`, they will be listed in `output_files`.

### Run Verification (run_verify)
```python
delphi_project(action="compile", project_path="Project.dproj", run_verify=True)
```

After a successful compile, automatically launches the exe to detect runtime crashes:

**① Inject the StackTrace unit** — temporarily modifies `.dproj`/`.dpr`, automatically restores after verification:
- `.dproj`: add a `DCCReference` pointing to `tools/stacktrace/StackTrace.pas`, append `tools/stacktrace/` to `DCC_UnitSearchPath`, force `DCC_MapFile=3` (Detailed map)
- `.dpr`: append `, StackTrace` to `uses`, insert after `begin`:
  ```pascal
  TStackTraceManager.Enabled := True;
  TStackTraceManager.Current.EnableDefaultLogger;
  ```

**② Recompile** (after injecting StackTrace)

**③ Run the exe** — `Popen + wait(timeout=5)`, auto `kill()` after 5-second timeout

**④ Check `exception.log`**:
- File exists → read with `detect_encoding()`, embed contents into the compile result
- File does not exist → mark as `passed`

**⑤ Restore** — restore `.dproj`/`.dpr` from the `.verify_bak` backup

**Return value `_verify` field**:
```json
{"_verify": {"passed": true}}                                          // Passed
{"_verify": {"error": "runtime exception", "log": "exception log content..."}}    // Exception present
{"_verify": {"error": "injected compile failed", "log": "..."}}        // Injected compile failed
```

> **Note**: `StackTrace.pas` is located at `tools/stacktrace/`; run_verify uses this built-in diagnostic unit to capture the call stack.
> Local variable value snapshots are currently disabled by default. To capture local variables, additionally set `TStackTraceManager.CaptureVariables := True`.

### Compile Failure Handling

Compile failures are the most frequent scenario in debugging; handle them with a structured process:

```
Compile failure
  │
  ├─ ① Confirm compiler status
  │   └─ check_environment(action="check")
  │
  ├─ ② Classify error severity
  │   ├─ Fatal → handle first (usually a missing path/config)
  │   ├─ Error → the main repair target
  │   └─ Warning/Hint only → can be deferred (see §8.8 error classification table)
  │
  ├─ ③ Incremental vs full
  │   ├─ First failure → check the most recently modified code
  │   ├─ Suspect cache corruption → delete .dcu/.map/.dres then full recompile
  │   └─ Full compile passes but incremental fails → incremental cache issue
  │
  ├─ ④ Path/config check
  │   ├─ Does DCC_UnitSearchPath contain all third-party library paths
  │   ├─ Does DCCReference register all dependent units
  │   └─ Do the conditional compilation symbols match the current configuration (DEBUG/RELEASE)
  │
  ├─ ⑤ Single-file isolation
  │   ├─ Errors concentrated in a few units → compile_file single-file verification
  │   ├─ Many errors → start from the first Error (subsequent are often cascading)
  │   └─ Tricky errors → binary-search isolation (see §8.9)
  │
  ├─ ⑥ Query the experience library
  │   └─ experience(search, query="DCC {error number} {keyword}")
  │
  ├─ ⑦ Hypothesis-driven analysis (§8.7)
  │   └─ Enter the hypothesis-driven loop → generate 2~3 hypotheses → verify in parallel
  │
  ├─ ⑧ Binary-search isolation (§8.9)
  │   └─ Compile-error binary search / runtime-crash binary search / regression localization
  │
  ├─ ⑨ Maintain a debug log (§8.10)
  │   └─ Update after each attempt: hypothesis→verification→result→inference
  │
  └─ ⑩ Still unresolved after 3 failures → go to §8.1 to evaluate human intervention
      └─ Check §8.14 escalation checkpoints; confirm all conditions are met before requesting intervention
```

> **Compile events**: PreBuildEvent/PostBuildEvent/PreLinkEvent in the .dproj are executed automatically. When a compile fails you can temporarily disable events to rule out interference: comment out the relevant `<Event>` lines in the dproj.
> **Compile safety**: record `logger.warning` before executing events with `shell=True`; long polling ≤30 seconds, switch to short polling after timeout.

## ⑥ Code Review

**After a successful compile, review the code item by item using the review checklist below.** Focus on:

| Dimension | Key points |
|-----------|------------|
| Consistency | Uniformity of naming/exception patterns/layout |
| Completeness | Branch coverage, boundary conditions, input validation, resource release |
| Resource leaks | Create/Free pairing, handle/interface release |
| Delphi-specific pitfalls | Interface reference counting, string types, TComponent ownership, etc. |
| Code quality | Cyclomatic complexity, magic numbers, duplicated code |
| Security | SQL injection, hardcoded credentials, buffer overflows |

> Specific review-table check items are in the "Review" section below.

## ⑦ Cleanup & Verification
- **Backup verification**: `delphi_file(action="write")` automatically backs up to `__history` by default; after modification use `delphi_file(action="backup", backup_action="list", file_path=...)` to confirm the backup exists
- **Tidy up**: delete unused variables/imports/functions/classes (delete directly, no manual confirmation needed)
- **Existing dead code**: mark as deprecated (add a comment annotation); wait for manual confirmation before cleanup
- **Encoding**: keep the file's original encoding; after modification run `delphi_file(action="format", ...)`

---

## Review

### Consistency

| Check item | Description |
|------------|-------------|
| `__history` backup integrity | Confirm the backups of files modified this time exist in the `__history` directory, and the version number ≥ 1 |
| Naming conventions | Type/field/method/parameter naming conforms to rules; old and new code styles are consistent |
| Exception patterns | Exception handling within the same module is consistent (all check return values or all throw exceptions); `try...finally` for resource release (always executed regardless of exception), `try...except` for exception handling (executed only on exception); when mixed, comment the responsibilities of each |
| Layout | Indentation, spacing, begin/end style consistent with the project's existing code |
| Error handling | Similar scenarios use the same error handling pattern |
| OleVariant vs Variant | Clearly distinguish usage scenarios; use `OleVariant` for COM interaction, `Variant` for general logic |
| Platform compatibility details | Behavior differences of `SizeOf` vs `Length` across platforms, byte-order issues, `NativeInt`/`NativeUInt` instead of Integer |
| Event release (multithreaded) | Check for multithreaded races when setting to nil; lock or use atomic operations if necessary |

### Completeness

| Check item | Description |
|------------|-------------|
| All paths | if/else, case/else, try/except cover all branches |
| Boundary conditions | Zero-length arrays, nil objects, empty strings, MaxInt values |
| Input validation | Validate externally passed parameters/files/streams for legality |
| Resource release paths | finally blocks ensure resources are released even on exception paths |
| Concurrency safety | Lock protection of shared variables, deadlock risk, resource cleanup on thread exit |
| Function return values | Functions must have explicit return values; do not implicitly return an uninitialized Result; uniform naming of `Result` |
| const/out/in parameters | Annotate output parameters with `out`/`var`; `const` parameters must not be modified; audit consistency of parameter passing |
| Assert usage | Debug assertions for pre/post-condition checks; note that `Assert` is stripped in Release via `{$DEFINES}` |
| Initialization/finalization sections | Check for resource leaks or ordering dependencies in `initialization`/`finalization` sections |
| Log output | Logs should distinguish levels (debug/info/warning/error); production should output only necessary levels; each log entry includes timestamp, severity level, and context that locates the problem; exception logs need the exception type and call stack |
| False-pass detection in tests | Whether test cases contain skips like `Assert(True)` / `assert True`, abnormally short execution time (100 operations <5 seconds), or assertions that only verify "no exception" rather than specific state |
| External dependency tests | When depending on external components (WebView2/Runtime/COM/DLL), whether the degraded path when the component is unavailable is tested; whether build scripts return a non-zero exit code when external tools are missing |
| Resource lifecycle tests | Whether COM interfaces/IStream/IWebView2 references verify the full acquire→use→release lifecycle; whether streams wrapped and then WebView2 reads are confirmed complete before release |
| Audit evidence completeness | Whether functional audit conclusions are supported by runtime evidence (screenshots/logs/test reports); "DESIGN" markers cannot be used to conclude "COMPLETE" |

### Resource Leaks

| Check item | Description |
|------------|-------------|
| Create/Free pairing | Every Create has a corresponding Free/FreeAndNil; a record's Create is not a class |
| try/finally | After resource acquisition, immediately enter try, release in finally |
| Files/handles | TFileStream, THandle, TMemoryStream, etc. are closed after use |
| Database connections | TSQLConnection, TADOConnection, etc. are released after use |
| GDI/system resources | TFont, TBitmap, TPen, TBrush, TCanvas, HPEN, HBRUSH |
| Interface references | Ensure references are released before interface variables go out of scope, avoiding circular references |
| Strings/arrays | Promptly clear large strings/dynamic arrays that are no longer used to free memory (`SetLength(s, 0)`) |
| TObjectList/TList | `OwnsObjects` set correctly; ensure objects are released with the container |

### Delphi-Specific

| Check item | Description |
|------------|-------------|
| Interface reference counting | Interface assignment automatically calls `_AddRef`; scope exit automatically `_Release`; avoid manual intervention |
| Circular references | Two objects referencing each other via interfaces cause memory leaks; use weak references or `[weak]` to break |
| TComponent ownership | Owner receives `Free` notification; child components are freed with the Owner; do not Free twice |
| String types | string=UnicodeString auto-managed; AnsiString/WideString require attention to encoding conversion |
| String concatenation | Use `TStringBuilder` for large string concatenation in loops, not `+` |
| Variant | Prefer concrete types over Variant; pay attention to reference counting when Variant is involved with COM |
| published section | Properties/events for streaming load stay public or published |
| RTTI | `TRttiContext` must be released after use to avoid leaks |
| Platform compatibility | Pointer/handle size differences under Win32/Win64; use `NativeInt`/`NativeUInt` instead of Integer |
| Record methods and references | Records are value types; modifications to fields within methods affect only the copy; pay attention to reference semantics when passing to var/out parameters |
| Enums and subranges | case statements cover all enum values (recommend adding `else raise`); subrange types need attention to boundary overflow |
| Set types | Set element limit 256; element type must be an ordinal type; empty Set uses `[]` not `nil` |
| Class Helper conflicts | Extension method name conflicts from multiple Helpers on the same class cause compile errors; audit naming uniqueness |
| Delegate method lifecycle | Anonymous methods/delegates capturing variables: pay attention to lifecycle; releasing local variables after being referenced causes dangling pointers |

### Common Error Patterns

| Check item | Description |
|------------|-------------|
| Empty exception handling | `except` blocks must at least log; **empty `except...end` is forbidden** as it swallows exceptions |
| Type conversion safety | `as` conversions throw exceptions; check with `is` before `as`; avoid hard casts `Type(x)` |
| Event release | Set event fields to nil before releasing objects (`OnClick := nil`) to avoid dangling event callbacks |
| Anonymous method capture | When creating anonymous methods inside loops, capture a local variable copy rather than referencing the loop variable |
| Thread access to VCL | Background threads operating VCL/FMX controls must use `TThread.Queue`/`Synchronize` |
| `with` statements | **Avoid using `with`** as it causes naming conflicts and reduces readability |
| Mixing dynamic arrays | Clearly distinguish `array of T` / `TArray<T>` / open array parameters; do not arbitrarily convert them |
| Record managed fields | When a record contains `string`/`TArray`/`IInterface`, note that assignment semantics are by value (copied, not referenced) |

### Code Quality

| Check item | Description |
|------------|-------------|
| Function/method size | A single method should ideally not exceed 80 lines, with a single responsibility; split if too long |
| Cyclomatic complexity | Nesting depth no more than 3 levels (if/for/while/case nesting); simplify with guard clauses or extracted methods if too deep |
| Magic numbers | Hardcoded magic numbers are forbidden; extract to named constants (`MAX_RETRY = 3`) |
| Comment conventions | Key logic, algorithms, TODO/FIXME need comments; promptly clean up outdated/misleading comments; meaningless line-by-line comments are forbidden |
| Code duplication | Extract identical or similar logic blocks into common methods; copy-paste is forbidden (DRY principle) |
| Test method naming | Test method names should clearly describe the behavior under test and expected result, format like `Test_[method name]_[condition]_[expected]`; test code is held to the same quality standard as production code |

### Data Conversion

| Check item | Description |
|------------|-------------|
| Conversion isolation | Conversions between data and external formats (JSON/XML/binary) use a dedicated layer or helper functions; don't manipulate format details directly in business logic |
| Field mapping | Avoid hand-written field-by-field mapping; prefer declarative mapping or automated mechanisms to reduce omissions |
| Input validation | Validate structure and range of data on deserialization/import; do not trust external sources |
| Encoding consistency | Explicitly specify character encoding during text data conversion; do not rely on the system default encoding |

### Security

| Check item | Description |
|------------|-------------|
| SQL injection | Dynamically concatenated SQL must use parameterized queries (`Params.ParamByName`); **direct string concatenation is forbidden** |
| Hardcoded credentials | **Forbidden** to hardcode passwords, keys, API Keys, or other sensitive information in code; use configuration/environment variables |
| Internationalization (i18n) | User-visible strings must not be hardcoded; use resource strings (`resourcestring`) |
| Buffer overflows | Boundary checks on arrays/buffers, especially copy operations related to external input (`Move`/`CopyMemory`) |
| Input sanitization | External data (file/network/user input) requires format and range validation |

### Performance

| Check item | Description |
|------------|-------------|
| In-loop memory allocation | Do not create objects/allocate large memory within loops; pre-allocate outside the loop |
| String operations | Use `TStringBuilder` for long string concatenation; evaluate performance of `StringReplace` on large data |
| Unnecessary type conversions | Avoid repeated `as`/`Type()` conversions in loops; cache conversion results |
| Avoid unnecessary RTTI | `TRttiContext` creation is expensive; cache type information in high-frequency call paths |
### Review Result Confirmation

For modifications found during review, the AI **must wait for user confirmation before making changes**, and must not modify anything on its own.

| Category | Handling |
|------|---------|
| 🔴 Issues affecting logic/architecture | Must be marked "needs user confirmation" in the report, wait for confirmation before changing |
| 🟡 Design decisions/ambiguous issues | List options for the user to choose, change only after confirmation |
| 🟢 Obvious coding errors (type mismatch, missing references, etc.) | May fix first and report after, noting in the report that it has been fixed |

---

## Knowledge Base Rebuild
```python
# Delphi source KB (~1 minute, 163737 classes / 300228 functions)
delphi_kb(action="build", kb_type="delphi", rebuild=True, async_mode=true)
# Third-party library KB (~6 seconds, 5606 classes / 51265 functions)
delphi_kb(action="build", kb_type="thirdparty", rebuild=True, async_mode=true)
# Documentation KB (~6 minutes; includes DCC compiler error descriptions from Delphi CHM, ~1278 error/warning documents total)
# After building, use delphi_kb(query="E2003", kb_type="document") to look up official compiler error explanations
# ⚠️ rebuild=True will clear all content in the existing documentation KB; add confirm=True if confirmation is needed
delphi_kb(action="build", kb_type="document", rebuild=True, confirm=True, async_mode=true)
# Project KB
delphi_kb(action="build", kb_type="project", project_path="Project.dproj", rebuild=True)

# Poll progress with action=result (returns immediately, zero wait, recommended)
async_task(action="result", task_id="task_xxx")
# Or use short polling action=status (long_poll ≤30s, switch to short polling on timeout)
async_task(action="status", task_id="task_xxx")
```

> **Documentation KB rebuild safety mechanism**: When setting `rebuild=True` for the documentation KB, if the KB already contains documents (non-empty), the system will return current KB statistics and require adding `confirm=True` to proceed. This prevents accidentally clearing existing document content (such as previously crawled web documents). If you want to keep the old content, you can pass the old document sources together in the new build parameters, or remove `rebuild` and use incremental building instead.

---

## Agent Operation Hard Rules

### Script Execution
- ❌ Never use `python -c "..."` (PowerShell quote escaping will always break)
- ✅ Always use `write` to create a `.py` file → `bash` to run `python script.py` → `Remove-Item script.py` to clean up

### String Formatting
- ❌ f-string with embedded dict `f'{d["key"]}'` (quote conflict)
- ✅ Use `.format()` or `%`

### Python Pitfalls
- **Do not use local `import` inside functions**: any `from X import Y` anywhere in a function makes `Y` a local variable throughout the function scope. References imported at the top will also raise `UnboundLocalError`. Always place them at the top of the module.
- **`if x:` vs `if x is not None:`**: 0, `""`, `[]` are all False. Use `Optional[int]` for optional numeric parameters and check with `is not None`.
- **`$()` macro expansion**: registry variable key names (e.g. `SKIADIR`) do not include the `$()` prefix; when adding to the `macros` dict you must use `macros[f'$({k})'] = v`. Using `update(dict)` will cause `str.replace('SKIADIR', ...)` to incorrectly match `$(SKIADIR)` → broken path.

---

## ⑧ Automated UI Interaction Testing

After compilation passes (optionally also `run_verify` passes), perform interactive operations and screenshot verification on GUI programs.

### Integration

Add the automation unit to the Delphi program's `.dpr`:
```pascal
uses
  Vcl.DaofyAutomation in 'path\to\tools\auto\Vcl.DaofyAutomation.pas',
  DaofyAutomation.Base in 'path\to\tools\auto\DaofyAutomation.Base.pas';

begin
  Vcl.DaofyAutomation.AutoStart;   // Start named pipe thread
  Application.Initialize;
  Application.CreateForm(TMainForm, MainForm);
  Application.Run;
  Vcl.DaofyAutomation.AutoStop;
end.
```
`AutoStart`, when invoked, creates the named pipe `\\.\pipe\daofy_auto` in the program under test and waits for external commands.

### Tool Invocation
```python
# Auto-detect: GUI exe → named pipe, Console exe → subprocess
automate_delphi(app_path="App.exe", script=[...])
automate_delphi(app_path="App.exe", script="script.json", keep_alive=True)

# Or explicitly specify the mode
automate_delphi(action="gui", app_path="App.exe", script=[...])
automate_delphi(action="console", app_path="Tool.exe", input="Y\n", expect="Continue?")
```
`action="auto"` (default) automatically detects the PE header Subsystem field to distinguish GUI/console programs.
Scripts consist of an array of JSON commands, each structured as: `{"cmd": "...", "target": "...", ...}`.

### Communication Architecture

```
Python (automation_service.py)              Delphi (TAutomationProcessorBase)
  ── CreateFile(\\.\pipe\daofy_auto) ──→      pipe thread receives JSON request
  ── WriteFile(JSON request)          ──→     main thread executes operation
  ←── ReadFile(JSON response)         ────    returns result/ACK
```
Transport layer: Windows named pipe (named pipe JSON request/response), zero external dependencies.

### Command List

> Detailed descriptions, typical scenarios, and priorities for each command are in §A Tool Classification (perceive/execute/verify).
> This table only supplements **synchronous/asynchronous** properties (not marked in §A).

| Command | Sync/Async | Description |
|------|-----------|----------|
| `goto` / `snapdir` / `exit` / `dlgfile` | Sync | Menu-level state change, must confirm completion |
| `capture` / `dumpstate` / `listwnd` / `formsum` | Sync | Perception commands, must wait for complete data return |
| `wait` / `waitfor` | Sync | Timing control, designed to block |
| `dlgscan` / `msgscan` / `msgclose` | Sync | Popup scanning requires complete results |
| `rget` / `rinspect` | Sync | RTTI reads require return values |
| `click` / `rclick` / `dblclick` | Async | UI operations do not block the pipe |
| `hover` / `move` / `drag` | Async | Mouse events submitted asynchronously |
| `type` / `key` | Async | Input queue pushed asynchronously |
| `rcall` / `rset` | Async | RTTI calls do not wait for business completion |
| `msgclick` / `dlgclick` | Async | Popup button clicks ACK immediately |

### keep_alive Mechanism

- With `keep_alive=True`, the process keeps running and subsequent calls reuse it
- Processes are automatically cleaned up after 5 minutes of inactivity
- The first call to a new process automatically sets `snapdir` to the screenshot directory

### Protocol Details
- Synchronous commands (goto/capture/waitfor/wait/dumpstate/listwnd/dlgscan/msgscan/msgclose/dlgfile/snapdir/exit/rget/rinspect) block and wait for a return
- Asynchronous commands (click/rclick/dblclick/hover/move/drag/msgclick/dlgclick/rcall/key/rset/type) immediately return ACK; results are obtained in subsequent steps via peekresult (in-memory results, no file writes)
- Response format: `{"reqId":"step_0","status":"ok","data":"OK"}`
- Messages larger than 64KB are automatically chunked (`ERROR_MORE_DATA` loop reads)
- Timeout support: `waitfor` command has built-in `timeout`/`interval` parameters (in ms)

### Test Script Example
```json
[
  {"cmd": "goto", "target": "TMainForm"},
  {"cmd": "capture", "target": "main_initial"},
  {"cmd": "click", "target": "BtnLogin"},
  {"cmd": "waitfor", "target": "StatusBar", "prop": "Caption", "value": "登录成功", "timeout": 5000},
  {"cmd": "capture", "target": "main_logged_in"},
  {"cmd": "exit"}
]
```

---

## ⑨ Console Program Interaction Verification

For console-type Delphi programs, use the `automate_delphi` tool's console mode for stdin/stdout interaction.
**No changes needed on the Delphi side** — console I/O is entirely handled on the Python side.

`action="auto"` automatically detects the PE header Subsystem field: GUI=named pipe, Console=subprocess.
You can also explicitly specify `action="console"`.

### Tool Invocation
```python
# Auto-detect (recommended)
automate_delphi(app_path="Tool.exe", input="Y\n", expect="Continue?")

# Explicit specification
automate_delphi(action="console", app_path="Tool.exe", input="Y\n", expect="Continue?")
automate_delphi(action="console", app_path="Deploy.exe", args=["--silent"], timeout=60)
```

### Test Modes

```
Python (subprocess)                           Console Delphi exe
  ── Popen(stdin=PIPE, stdout=PIPE) ──→       begin..end. launch
  ── proc.stdin.write("input\n")     ──→       ReadLn receives
  ←── proc.stdout.read()             ────     WriteLn outputs
  ←── proc.wait(timeout=5)           ────     exit
```

### Basic Usage
```python
import subprocess

proc = subprocess.Popen(
    [exe_path, "--arg1", "value"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    cwd=work_dir,
)
stdout, stderr = proc.communicate(input=b"user input\n", timeout=10)
```

### Step-by-step Interaction (keep_alive mode)
```python
proc = subprocess.Popen(
    [exe_path],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
)

# Send input
proc.stdin.write(b"Y\n")
proc.stdin.flush()

# Read output (wait for prompt to appear)
import select
while True:
    line = proc.stdout.readline()
    if not line:
        break
    if b"Continue?" in line:
        proc.stdin.write(b"N\n")
        proc.stdin.flush()
        break

proc.wait(timeout=5)
```

### expect-style Waiting (wait for a specified output pattern)
```python
def expect_output(proc: subprocess.Popen, pattern: str, timeout: float = 5.0) -> list[str]:
    """Wait for the specified pattern to appear in stdout."""
    import re
    deadline = time.time() + timeout
    lines: list[str] = []
    while time.time() < deadline:
        import select
        reads, _, _ = select.select([proc.stdout], [], [], 0.5)
        if reads:
            line = proc.stdout.readline()
            if not line:
                break
            decoded = line.decode("utf-8", errors="replace")
            lines.append(decoded)
            if re.search(pattern, decoded):
                return lines
    raise TimeoutError(f"Pattern not matched within {timeout}s: {pattern}")
```

### Applicable Scenarios
- Functional testing of command-line tools (argument parsing, output formatting)
- Step-by-step operation of batch processing flows (menu selection, confirmation prompts)
- Unattended automation of installation programs
- Output monitoring of long-running tasks

### Notes
- **Timeout control**: `communicate(timeout=...)` or `wait(timeout=...)` must be set to avoid the process hanging
- **Pipe buffering**: When there is a lot of output, watch out for the system pipe buffer size (default 4KB-64KB); use `readline()` to read line by line to avoid deadlock
- **stderr**: Recommend `stderr=subprocess.STDOUT` to merge output, or capture separately
- **exit code**: Determine whether the program exited normally via `proc.returncode`
- **Encoding**: Windows console output is usually `gbk`; use `.decode('gbk', errors='replace')` to handle

---

## ⑩ Human-Machine Collaboration — Exception Diagnosis and Human Intervention

### Overview

AI Agents are not omnipotent. When encountering problems that cannot be solved independently, requesting human intervention in a timely and high-quality manner is more efficient than struggling on. This section defines the diagnostic process for exceptions, trigger conditions for human intervention, and handover standards.

### Pre-check (common to all tasks)

When starting execution or hitting a blocker, pause and self-check against the checklist below, verifying one by one whether the trigger conditions in §10.1 are met:

- 🔴 Tool returns an error or abnormal result → cross-verify once; if still abnormal, pause and check
- 🟡 Unsure which option to choose next → check whether the "solution selection ambiguity" condition is triggered
- 🟡 When preparing to retry, find that it is essentially the same as the last attempt → triggers the "consecutive homogeneous solutions" condition
- 🟡 Missing key information that requires guessing → triggers the "guessing with insufficient information" condition

**Execute by trigger condition priority**: 🔴 P0 stop immediately → 🔴 P1 stop → 🟡 P2 stop → otherwise continue.

### 8.1 Human Intervention Trigger Conditions

When any of the following conditions is met, the AI Agent **must proactively stop trying and request human intervention**:

| Priority | Trigger Condition | Example |
|--------|---------|------|
| 🔴 P0 | 3+ consecutive fix attempts all fail (AI should stop and request intervention after 3 failures) | Compilation error unresolved after 3 attempts |
| 🔴 P0 | Error cause points to closed source code/environment AI cannot access | Third-party closed-source DLL crash, hardware driver issue |
| 🔴 P1 | Problem involves a design decision requiring human confirmation | Architecture change, API compatibility trade-off |
| 🟡 P2 | Error message incomplete, cannot determine root cause | Memory corruption (Access Violation without call stack) |
| 🟡 P2 | Need to access external restricted resources | Enterprise internal Git, VPN environment, License server |
| 🟡 P2 | 2+ viable solutions but unsure which is better (solution selection ambiguity) | API call has 3 equivalent forms, fix strategy has 2 different paths |
| 🟡 P2 | Two consecutive attempts are essentially similar solutions (only changing parameters/order) | Changing a flag after compile failure, changing order to read the file again |
| 🟡 P2 | Guessing when information is insufficient | Error message only says "file not found" without a path, AI guesses a path to try |
| 🟡 P2 | Same tool fails 2 consecutive times | project(compile) reports compiler errors 2 consecutive times, AI still calls compile instead of changing approach |
| 🟢 P3 | Problem itself is simple but AI verification environment doesn't match | User-specific registry state, DLL version differences |

> **Exception**: If the failure cause is an AI coding error (such as an obvious logic bug, missing reference unit), it does not belong to the scope of human intervention and should continue to be fixed.

**Supplementary details**:

- **Solution selection ambiguity**: When `list_tools()` contains multiple tools that can accomplish the same goal, or when the same problem has multiple equivalent fix paths, do not default to one. Must list options and decision criteria within 1 round and request human intervention to choose. Example: "Option A: ..., Option B: ..., please choose"
- **Do not guess with insufficient information**: When the result returned by the tool or the error message lacks decisive information, first try other tools to complete the information (e.g., use `delphi_file(action="read")` to read the source code), and if still insufficient, ask the user, and do not fabricate missing information. If guessing consecutively 2 times and still wrong → request human intervention.
- **Switch direction when the same tool fails consecutively**: When the same tool fails 2 consecutive times, first check whether the wrong tool was used, and try replacing it with another tool or a completely different strategy direction. If still ineffective → request human intervention.
- **Verify abnormal results**: When the tool returns `success` but the result is clearly unreasonable (such as an empty list, 0 lines read, empty content), must call other tools to re-read or cross-verify, and continue only after confirmation. When suspecting data issues, prefer retrying once (to rule out transients) rather than directly requesting human intervention.

**Priority interaction description**:
- P2 (same tool 2 times) triggers first → change direction → if it fails again after changing direction, total 3+ times → enter P0 for direct intervention
- P2 (insufficient information) after 2 wrong guesses → enter P0 for direct intervention
- P2 after changing direction resolves → no need to reach P0

### 8.2 Six-step Exception Diagnosis Method (Analyze→Plan→Audit→Backup→Execute→Verify)

When an exception occurs, execute the following six steps. **When audit finds a problem, must roll back to analysis/plan to correct; when verification fails, must roll back to analysis to re-investigate.**

> Non-code fix scenarios (only changing configuration/registry/environment variables/updating DLLs, without modifying source code) can skip ④ backup and ⑤ execute, and go directly to ⑥ verify, but must explicitly record the reason and rationale for skipping.

```
        ┌─────────────────────────────────────────────────┐
        │  ① Analyze                                      │
        │  Collect info → locate root cause → determine problem nature │
        └──────────────────────┬──────────────────────────┘
          ▲                    │
          │  Audit return(🔴)  │  ← Verify return direction
          │  Plan return(🟡)   │    (⑥ fail → back to ①)
          │                    │
        ┌─┼──────────────────────────┐
        │ ② Plan                     │
        │ Design solution → multi-solution comparison → verification criteria │
        └───────────┬────────────────┘
                    │ Audit return(🟡 boundary/norm)
                    ▼
        ┌──────────────────────────────┐
        │ ③ Audit                      │
        │ Review solution item by item per detailed checklist │
        │ ├─ ✅ Pass → continue         │
        │ └─ ❌ Problem → roll back to ① analyze or ② plan │
        └───────────┬──────────────────┘
                    │
                    ▼
        ┌──────────────────────────────┐
        │ ④ Backup                     │
        │ __history backup + WIP commit│
        └───────────┬──────────────────┘
                    │
                    ▼
        ┌──────────────────────────────┐
        │ ⑤ Execute                    │
        │ Preview→modify→format→compile→commit │
        └───────────┬──────────────────┘
                    │
                    ▼
        ┌──────────────────────────────┐
        │ ⑥ Verify                     │
        │ Verify per standards→cleanup→save experience │
        │ ├─ ✅ Pass → done             │
        │ └─ ❌ Fail → back to ① analyze │
        └──────────────────────────────┘
```

| Step | Goal | Method and specifics | Tools/Commands | Key checkpoints | Deliverables |
|------|------|--------------|-----------|-----------|-------|
| **① Analyze**<br>(Analyze) | Completely understand the problem, locate root cause, distinguish problem type | **1. Collect on-site info** (per §8.3 template: exception type/message/call stack/environment/key variable values)<br>**2. Reproduce confirmation**: determine whether the problem can be stably reproduced, record reproduction steps<br>**3. Check recent changes**: `git log --oneline -10` + `git diff` to view recent modifications<br>**4. Search experience base**: `experience(search, query="<problem keyword>")` to look up similar problems<br>**5. Confirm problem nature**: classify as compilation error (§8.8)/runtime crash (§8.13)/logic error/environment issue, then per §8.11 select the corresponding tool<br>**6. Deep search**: compilation errors → §8.8 DCC classification + `delphi_kb(query="<error number>", kb_type="document")`<br>**7. Mark problem severity**: P0 (crash/data loss)/P1 (functional anomaly)/P2 (experience/minor)<br>**8. Generate root cause hypotheses**: refer to §8.7 hypothesis-driven debugging, generate 2~3 mutually exclusive hypotheses<br>**9. Hypothesis verification**: verify the most likely hypothesis with the fewest operations<br>**10. Determine whether to fix independently**: code defect→continue; environment/permission/closed-source→go to §8.1 intervention | `delphi_project(compile)`<br>`delphi_file(read)`<br>`delphi_kb(query=...)`<br>`experience(search, ...)`<br>`git log/diff/bisect`<br>`lsp_diagnostics`<br>`automate_delphi(msgscan)` | 🔴 Did you distinguish code defect vs environment issue?<br>🔴 Did you check the experience base? (must before 2nd failure)<br>🔴 Did you mark problem severity?<br>🟡 Are hypotheses falsifiable? (non-falsifiable → refine)<br>🟡 Did you check recent code changes?<br>🟡 Is it a single problem or the result of a chain problem? | Root cause hypotheses (with confidence)<br>Problem classification+severity label<br>List of excluded candidate causes<br>Judgment of whether it can be fixed independently |
| **② Plan**<br>(Plan) | Design a clear, minimized fix plan, define verification criteria | **1. Determine fix scope**: which files and lines to modify (minimization principle, do not fix unrelated code)<br>**2. Verify API usage**: `delphi_kb(query="<API name>", search_type="function")` to confirm API signature and behavior<br>**3. Multi-solution comparison**: when 2+ viable solutions exist, list a comparison table (solution/effort/risk/rollback difficulty/recommendation)<br>**4. Assess impact scope**: which callers will be affected by the change? Any compatibility issues?<br>**5. Define verification criteria**: clarify the observable conditions for "fix successful" (e.g., compile 0 Error + a function returns a specific value + a popup no longer appears)<br>**6. List all modification points**: each modification specified to start_line/end_line and content<br>**7. Confirm compilation configuration**: Debug/Release/DCC_Define differences<br>**8. Check coding style consistency**: naming/format/pattern consistent with project conventions<br>**9. Non-code fix**: if only configuration/registry/environment variables/DLL updates are needed, can skip ④~⑤ and go directly to ⑥ verify<br>**10. If it is an environment problem** → go to §8.1 to request human intervention, do not fix independently | `delphi_kb(search_type="function"/"class")`<br>`delphi_file(read)`<br>`get_coding_rules(section="review")`<br>`delphi_project(info)` | 🔴 Does every modification point have a basis rather than a guess?<br>🔴 Is the fix scope minimal? (do not fix unrelated code)<br>🔴 Are verifiable "fix successful" criteria defined?<br>🟡 Are alternatives compared when multiple solutions exist?<br>🟡 Is API behavior confirmed? (check KB first when unsure)<br>🟡 Are Debug/Release differences considered?<br>🟡 Are 32/64-bit platform differences considered? | Fix plan list (file→line→content)<br>Multi-solution comparison table (if any)<br>Verification criteria definition<br>Impact scope assessment<br>API confirmation record |
| **③ Audit**<br>(Audit) | Review the solution item by item per detailed checklist for root cause match, safety risks, completeness, consistency, and impact scope, and intercept potential problems | **Audit dimension classification**:<br>├─ **Solution-root cause match**: whether the solution targets the root cause (not the symptom), whether it oversteps, whether it misses chained problems<br>├─ **Safety and risk**: whether it introduces new crash paths, rollback reversibility, interface/data/concurrency safety<br>├─ **Solution completeness**: branch coverage, boundary conditions, resource release, input validation, verification criteria<br>├─ **Coding style consistency**: naming, exception patterns, style, comments<br>├─ **Impact scope**: compile/platform/version compatibility, public function impact, documentation updates, configuration changes<br>├─ **Experience and records**: experience base queried, debug log updated, intervention conditions met<br><br>**Audit conclusion**: pass / roll back to analysis (🔴 item fails) / roll back to plan (🟡 ≥2 items fail) | `get_coding_rules(section="review")`<br>`get_coding_rules(section="consistency")`<br>`get_coding_rules(section="safety")`<br>`delphi_kb(search_type="reference")`<br>`lsp_find_references` | 🔴 Any 🔴 item fails? → **must roll back**<br>🔴 Modified public utility functions/base class? → check all callers<br>🔴 Verification criteria undefined? → roll back to supplement<br>🟡 🟡 items fail ≥2? → roll back to plan | Audit conclusion (pass/roll back)<br>Issue list (each item: pass/fail/not applicable)<br>Rollback target (analysis/plan) |
| **④ Backup**<br>(Backup) | Ensure code can be safely rolled back, reducing execution risk | **1. Confirm version control status**: `git status` to check whether the working tree is clean<br>**2. Mark all involved files**: list all files involved in this modification (.pas/.dfm/.dproj, etc.)<br>**3. Back up each modified file one by one**: execute `delphi_file(action="backup", backup_action="create", ...)` for each file<br>**4. Stash/commit current work when needed**: `git stash` or `git commit -m "WIP: <problem description> before fix"` to preserve the pre-modification state (this is a WIP marker, not a final commit; after ⑤ execute passes, it will be formally committed again)<br>**5. Record pre-modification snapshot**: take screenshots/save original file copies if necessary<br>**6. Confirm all files are successfully backed up**: verify each file's backup exists in the `__history/` directory | `delphi_file(backup, create)`<br>`code_hosting(git_status)`<br>`code_hosting(git_stash)` | 🔴 Do all involved files have __history backups?<br>🔴 For multi-file modifications, was each confirmed backed up?<br>🟡 Any important uncommitted changes in the working tree?<br>🟡 Modification involves binary files like .dfm/.res? → confirm they are backed up | Backup confirmation list<br>Involved file list<br>Working tree status record |
| **⑤ Execute**<br>(Execute) |
### 8.4 Manual Intervention Handoff Checklist

When requesting manual intervention, the following information must be provided (**none may be omitted**):

```
┌────────────────────────────────────────────────────────────┐
│                Manual Intervention Request                   │
├────────────────────────────────────────────────────────────┤
│ [1] Problem Summary                                          │
│   Describe the problem in one sentence                       │
│                                                              │
│ [2] Attempted Solutions (listed one by one)                  │
│   ① What was tried → what was the result → why it failed     │
│   ② ...                                                      │
│   ③ ...                                                      │
│                                                              │
│ [3] Exception Scene (see 8.3 template)                       │
│   ├─ Full exception message + call stack                     │
│   ├─ Values of key variables                                 │
│   └─ Reproduction steps (shortest path from launch to exception) │
│                                                              │
│ [4] Environment Information                                  │
│   ├─ Daofy version, Python version, OS version               │
│   ├─ Delphi compiler version                                 │
│   ├─ Project type (VCL/FMX/Console) and key configuration    │
│   └─ Recent changes (code/config changes related to the problem) │
│                                                              │
│ [5] Expected Result                                          │
│   What you want the human to do for you                      │
│   e.g.: "Please confirm whether this DLL export function signature is correct" │
│         "Please provide the license file for the XXX component" │
│                                                              │
│ [6] Minimal Reproducible Example (MRE)                       │
│   If a minimal standalone reproduction case can be extracted, attach the code │
└────────────────────────────────────────────────────────────┘
```

### 8.5 Collaborative Workflow

```
  AI Agent                        Human (Developer)
     │                                 │
     │─── Attempt to solve independently ──→  │  (P0/P1 problems triggered automatically)
     │                                 │
     │─── Submit intervention request ──→  │
     │    (per 8.4 checklist)          │
     │                                 │
     │←── Human response ──────────────── │
     │    (locate root cause / provide info / │
     │     grant access / correct design) │
     │                                 │
     │─── Continue fixing based on human feedback ──→  │
     │    Verify after completion      │
     │                                 │
     │←── Acceptance confirmation ──────── │
     │    (pass / needs adjustment)    │
     │                                 │
```

**Key Rules**:

1. **AI must proactively request intervention** — Do not keep grinding; trigger immediately once any condition in 8.1 is met. Wasting time is worse than "appearing incompetent."
2. **Intervention requests must be complete** — If any item in the 8.4 checklist is missing, the human may request supplements before processing.
3. **AI continues to follow up after human response** — Once the human provides information/solutions, the AI is responsible for continuing the fix and verification.
4. **Experience deposition** — After the problem is resolved, use `experience(action="save")` to save the resolution process as experience, so that the AI can solve similar problems on its own next time without requesting manual intervention.
5. **Update rules after intervention** — If manual intervention reveals blind spots in the coding standards/process, update `src/resources/coding-rules.md` (MCP Resource: `delphi://coding-rules`) to avoid repeated intervention for similar problems.

### 8.6 Exception Handling Conventions for MCP Tools

| Layer | Exception Handling |
|------|-------------|
| `tools/*.py` handler | Catch specific exceptions, return `{"error": "..."}` + attach `exc_info=True` logging; do not throw |
| `server.py call_tool` | Top-level fallback catches all exceptions, formats them as `CallToolResult(isError=True)` and returns; bare throws are prohibited |
| `services/*.py` | Business exceptions use custom exception classes, preserve the full call chain; log but **do not swallow exceptions** |
| `utils/*.py` | Utility functions typically do not catch internally; let upper layers handle uniformly |

---

### 8.7 Hypothesis-Driven Debugging Loop

When facing a problem whose root cause has not yet been identified, do not jump into a random fix loop of "guess → modify → verify." Adopt a hypothesis-driven approach to systematically narrow the scope:

```
┌─ Step ①: Information Gathering ────────────────┐
│  Collect all available clues without presupposing any cause │
│  ├─ Full error message + error number/exception type │
│  ├─ Call stack (symbolicated/non-symbolicated)  │
│  ├─ Environment info (Delphi version/OS/platform/config) │
│  ├─ Reproduction steps (determine if reliably reproducible) │
│  ├─ Recent changes (git log --oneline -10 to check recent modifications) │
│  └─ Check experience DB: experience(search, query="...") │
└──────────────────────────────────────────────────┘
                         ↓
┌─ Step ②: Generate 2~3 independent hypotheses ────────────┐
│  H1: Hypothesis cause A → expect to observe A' → verification method V1 │
│  H2: Hypothesis cause B → expect to observe B' → verification method V2 │
│  H3: Hypothesis cause C → expect to observe C' → verification method V3 │
│                                                    │
│  Hypothesis requirements:                          │
│  ├─ Must be based on evidence from step ①, not groundless guessing │
│  ├─ Mutually exclusive or at least independent (not interdependent) │
│  └─ Sort by easiest to verify > most likely true  │
└──────────────────────────────────────────────────┘
                         ↓
┌─ Step ③: Parallel Verification ────────────────┐
│  ├─ Simultaneously verify non-dependent hypotheses │
│  ├─ Minimal operations per verification (minimize code changes) │
│  ├─ For compile errors, verify single files with compile_file, not full builds │
│  └─ For runtime problems, quick verification with rget/delphi_rtti │
└──────────────────────────────────────────────────┘
                         ↓
┌─ Step ④: Analyze Results → Decide ───────────────┐
│  ├─ H confirmed → proceed to fix                  │
│  ├─ All H disproven → return to ① to gather more info or trigger intervention │
│  └─ Partially confirmed → adjust hypothesis to narrow scope, re-enter loop │
└──────────────────────────────────────────────────┘

If root cause still cannot be located after at most 3 rounds → trigger §8.1 P0 manual intervention.
```

**Key Rules**:
1. **Zero-hypothesis fixes prohibited** — Do not modify code before forming a hypothesis
2. **Verify only one hypothesis at a time** — Do not make multiple changes simultaneously, otherwise you won't know which one took effect
3. **Hypotheses must be falsifiable** — If a verification method cannot be designed for a hypothesis, the hypothesis is not specific enough and needs refinement
4. **Maintain a debug log** — Record attempted solutions per §8.10 to avoid repeated homogeneous solutions from §8.1

---

### 8.8 DCC Compilation Error Classification and Decoding

#### Document Knowledge Base Search (Preferred Solution)

The Delphi official CHM help documentation (`topics.chm`) contains **official explanations** of all DCC compiler errors/warnings/hints (approximately 1278 HTML files total, covering 875 EXXXX errors + 20 FXXXX fatal errors + W/H series).
Using the document knowledge base to search DCC errors is the most accurate solution (no need to hardcode all error codes):

```
Prerequisite: The document knowledge base must be built from Delphi CHM (only once)
delphi_kb(action="build", kb_type="document", async_mode=true)
# Automatically detects .chm files under C:\Program Files\Embarcadero\Studio\<version>\Help\Doc\
# Searchable once complete

# To force rebuild (clears all existing documents in the KB):
# delphi_kb(action="build", kb_type="document", rebuild=True, confirm=True, async_mode=true)
# ⚠️ rebuild=True clears all existing documents in the KB; please confirm the old content is no longer needed or is included in the new document source first

# Search for a specific DCC error number (returns official explanation + fix suggestions)
delphi_kb(query="E2003", kb_type="document", search_type="semantic")
delphi_kb(query="E2010 incompatible types", kb_type="document", search_type="semantic")
delphi_kb(query="F2613 unit not found", kb_type="document", search_type="semantic")

# Search by topic
delphi_kb(query="Delphi Compiler Errors Index", kb_type="document")
delphi_kb(query="Error and Warning Messages (Delphi)", kb_type="document")
delphi_kb(query="Fatal errors", kb_type="document")
```

> Once the document KB is built, any `delphi_kb(kb_type="document")` query directly returns the official explanation of the DCC error code,
> eliminating the need for the AI to fix based on guesses.

#### Error Level Quick Reference

| Level | Prefix | Meaning | Handling Strategy |
|------|------|------|---------|
| **Fatal** | Fxxxx | Compiler cannot continue; must be resolved first | Fix path/configuration issues first, then handle other errors |
| **Error** | Exxxx | Syntax/semantic error | Read the source of the error line → check document KB → fix |
| **Warning** | Wxxxx | Potential problem | Assess whether it affects functionality; known warnings (e.g., W1057) may be ignored |
| **Hint** | Hxxxx | Style/type suggestion | Only handle when tidying code; can skip during debugging |

#### Common DCC Error Quick Reference (8 commonly used, full list in document KB)

| Error No. | Typical Message | Common Cause | Resolution Direction |
|--------|---------|---------|---------|
| E2003 | Undeclared identifier: 'X' | Missing uses unit / spelling error | Check uses clause + identifier case |
| E2010 | Incompatible types: 'X' and 'Y' | Type mismatch | Check assignment/parameter types, use explicit casts if necessary |
| E2029 | Statement expected but 'X' found | Syntax structure error | Check bracket/semicolon/begin..end pairing |
| E2037 | Record, object or class type required | Using '.' access on a non-object type | Check variable type declaration |
| E2066 | Missing operator or semicolon | Missing semicolon on the previous line | Look back at the end of the line before the error line |
| E2251 | Ambiguous overloaded call to 'X' | Ambiguous overloaded function match | Use explicit type casts to disambiguate |
| E2506 | Unit 'X' not compiled (Y.dcu out of date) | DCU cache out of date | Full rebuild or delete .dcu files |
| F2613 | Unit 'X' not found | Search path does not include target unit | Check DCC_UnitSearchPath / add DCCReference |

#### Compilation Error Handling Flow

```
Compilation fails
  │
  ├─ ① Classify error level
  │   ├─ Fatal → handle first (usually path/config issues)
  │   ├─ Error → main fix target
  │   └─ Warning/Hint only → may defer
  │
  ├─ ② Single file vs. full build
  │   ├─ Incremental build error → clean first (delete .dcu/.map/.dres) then full rebuild
  │   ├─ Errors concentrated in a few units → verify single files with compile_file
  │   └─ Many errors → start from the first Error (subsequent errors are often cascading)
  │
  ├─ ③ Error localization (priority high to low)
  │   1️⃣ delphi_kb(query="{error number}", kb_type="document")  → check official explanation
  │   2️⃣ delphi_kb(query="{keyword}", kb_type="document")  → semantic search
  │   3️⃣ Reference DCC quick reference + read source context at error line
  │   4️⃣ delphi_kb(search_type="function") to look up API definitions
  │   5️⃣ Verify with incremental build after fixing
  │
  └─ ④ Difficult/repeated failures
      ├─ Bisection isolation (see §8.9)
      ├─ Check experience DB: experience(search, query="DCC Exxxx ...")
      └─ 3 failures → escalate to §8.1 P0 manual intervention
```

#### Incremental Build Cache Issues

- Corrupted `.dcu`/`.map`/`.dres` caches can cause ghost errors (error line does not match reality)
- **Symptom**: Same error still reported after fixing the error line, or error points to deleted code
- **Resolution**: Delete cache files then full rebuild
- On Windows, `.map` files may be locked when the IDE has the project open; close the IDE first

---

### 8.9 Bisection and Isolation Debugging

When facing large projects, complex functions, or errors difficult to locate, do not try to understand all the code at once.
Use bisection (Binary Search) to quickly narrow down the suspect scope:

```
Compile error bisection (file level):
  ① Split the file into upper and lower halves from the middle
  ② Comment out the upper half with {$IFDEF DEBUG_SKIP}...{$ENDIF} → compile
  ③ Error disappears → error is in the upper half; still present → error is in the lower half
  ④ Recursively bisect the half containing the error until the specific line is located

Runtime crash bisection (code path level):
  ① Determine the minimal operation path that triggers the crash
  ② Insert Exit / early return at the midpoint of the call chain
  ③ Crash disappears → problem is in the latter half; still present → problem is in the former half
  ④ Recursively narrow the scope until the specific function is located

Multi-module isolation (project level):
  ① Temporarily disable all build events (PreBuild/PostBuild)
  ② Remove DCCReference entries from dproj one by one to locate the missing unit
  ③ Comment out uses clauses in batches to locate circular references
  ④ Turn off {$DEFINE} conditional compilation symbols, then enable them progressively

Regression localization (change level):
  git bisect is the most reliable regression localization tool:
  ① git bisect start
  ② git bisect bad          # current version has the problem
  ③ git bisect good <tag>   # last known good version
  ④ git bisect run <script> # automatic bisection build verification script
  ⑤ Locate the commit that introduced the problem

  Without git: manually record the "last good" time point, test versions one by one along the changelog.
```

**Isolation Principles**:
- Change **only one variable at a time** for each isolation (comment out one block / disable one unit)
- Confirm the isolation result before proceeding to the next step (do not make multiple changes at once)
- The optimal complexity of bisection is O(log N); do not substitute a linear scan
- Use `{$IFDEF}` for compile error isolation rather than deleting code, to facilitate restoration

---

### 8.10 Debug State Log

During debugging, the AI Agent **must maintain a structured debug log** to explicitly track attempted solutions and results.
This directly prevents the "consecutive homogeneous solutions" trigger in the §8.1 manual intervention trigger table (P2 level, triggered on the 2nd failure) — with a log, the AI can accurately judge whether the current attempt is essentially different from previous ones.

```
[Debug Log] <Problem Summary>
═══════════════════════════════════════
Problem Description: {one-sentence description}

Attempted Solutions:
  #1: Hypothesis H1=... → Verification method=... → Result=disproven → Inference=exclude cause A
  #2: Hypothesis H2=... → Verification method=... → Result=confirmed → Inference=cause B → Fixed
  #3: ...

Current Scope:
  Excluded: [module X, module Y, file Z, ...]
  Remaining suspects: [module W, ...]
  Current most likely hypothesis: {hypothesis description + basis}

Next Plan: {specific content to be verified}
Whether to trigger manual intervention: Yes/No (trigger reason)
═══════════════════════════════════════
```

**Usage Rules**:
- Create the log before starting to debug any problem
- Update the log after each attempt (hypothesis → verification → result → inference)
- Before entering the next hypothesis loop, review the log to confirm that the new hypothesis is **essentially different** from previously disproven hypotheses
- The log itself is not saved to a file; it serves only as working memory for the current debug session
- The log can be discarded once the problem is resolved, but the experience must be persisted via `experience(save)`

---

### 8.11 Debug Tool Selection Decision Tree

For problems of different natures, choose the most efficient tool combination:

```
Encountering a problem
  │
  ├─ Compile error (DCC error)
  │   ├─ ⭐ delphi_project(action="compile") — full/incremental build
  │   ├─ ⭐ delphi_project(action="compile", compile_file=...) — single file syntax check
  │   ├─ ☆ delphi_file(action="read") — read source context at error line
  │   ├─ ☆ delphi_kb(query=...) — look up API definitions to confirm usage
  │   └─ ☆ experience(search, query="DCC ...") — check experience with similar compile errors
  │
  ├─ Runtime crash (Access Violation / exception popup)
  │   ├─ ⭐ First classify the crash subtype → refer to §8.13
  │   ├─ ⭐ automate_delphi(cmd="msgscan") — capture exception popup content
  │   ├─ ⭐ StackTrace.pas / madExcept — obtain full symbolicated call stack
  │   ├─ ⭐ delphi_rtti(action="discover") — check runtime object state
  │   ├─ ☆ guide user in IDE (F7/F8/F9) — guide user to set breakpoints and debug manually
  │   └─ ☆ experience(search, query="...crash...") — check experience with similar crashes
  │
  ├─ Logic error (wrong result / abnormal UI display)
  │   ├─ ⭐ delphi_file(action="read") — read source to confirm business logic
  │   ├─ ⭐ delphi_kb(query=...) — confirm whether API behavior matches expectations
  │   ├─ ⭐ LSP diagnostics / lsp_symbols — check code symbols
  │   ├─ ☆ automate_delphi(cmd="rget") — read runtime control property values
  │   ├─ ☆ automate_delphi(cmd="capture") — screenshot visual comparison
  │   └─ ☆ experience(search, query="...")
  │
  └─ Environment problem (path/version/config)
      ├─ ⭐ check_environment(action="check") — confirm compiler status
      ├─ ⭐ delphi_project(action="info") — view dproj configuration
      ├─ ☆ git diff — check recent configuration changes
      └─ ☆ experience(search, query="environment ...")
```

**Priority**: ⭐ try first → ☆ backup or auxiliary

**General Principles**:
- **Check the experience DB before acting**: `experience(search, query="...")` may provide the answer within 30 seconds
- **Confirm the API before fixing code**: When unsure of API behavior, use `delphi_kb` to look up the definition first; do not modify based on guesses
- **Single-file verification first**: For compile errors, prefer `compile_file` for quick verification, avoiding a full build each time
- **Isolate errors before analysis**: After narrowing the scope with §8.9 bisection, then analyze specific code in depth

---

### 8.12 Post-Fix Retrospective — From Debugging to Defense

After the fix is verified, you must perform a post-mortem to deposit the results of this debug session as long-term assets:

```
┌─ Post-Fix Retrospective Checklist ──────────────────┐
│                                                      │
│ ① Root Cause Classification                          │
│    ├─ Coding error (logic defect/syntax error)       │
│    ├─ API misuse (parameter error/lifecycle/convention misunderstanding) │
│    ├─ Environment difference (Delphi version/OS/third-party library version) │
│    ├─ Concurrency/timing issue (race condition/deadlock/event order) │
│    └─ External dependency change (API deprecation/behavior change) │
│                                                      │
│ ② Evaluate Defensive Measures                        │
│    ├─ Add Assert to catch at development stage?      │
│    │   → Root cause is precondition not satisfied → add Assert │
│    ├─ Add logging to make future debugging faster?   │
│    │   → Root cause is insufficient info causing difficulty locating → add logging │
│    ├─ Add automated tests to prevent regression?     │
│    │   → Business logic error → add test cases       │
│    └─ Update CODING_RULES to benefit all AIs?        │
│        → Common pattern → add rule (see §⑫)          │
│                                                      │
│ ③ Experience Save (must execute)                     │
│    └─ experience(action="save", ...)                  │
│       problem: "{generalized problem description}"   │
│       solution: "{fix steps + key code}"             │
│       tags: ["debug", "{error category}", "{module name}"] │
│                                                      │
│ ④ Rule Linkage Check                                 │
│    ├─ Experience reused hit_count ≥ 3?               │
│    │   → Evaluate whether to upgrade to CODING_RULES formal rule │
│    └─ This debug session revealed a rule blind spot? │
│        → Add/update rule per §⑫ template             │
│                                                      │
└──────────────────────────────────────────────────────┘
```

**Principles**:
- **Every fix is accompanied by a retrospective**: Fixing is not just changing code, it is improving the development process
- **The half-life of experience is 30 days**: Unrecorded experience loses value over time (see §9.5)
- **Rules are crystallized experience**: Experience with hit_count ≥ 3 should be upgraded to formal rules
- **Retrospective is not optional**: This is the last step of the debugging process and cannot be skipped

---

### 8.13 Classification and Troubleshooting of Delphi Runtime Crashes

Delphi runtime crashes have 4 fundamentally different root cause patterns; classifying first is much faster than general troubleshooting:

#### Type A: Access Violation — Interface Reference Counting Issue

**Characteristics**: AV when calling interface methods, but calling object methods works fine. Common when an interface reference is passed across objects and the original object is later freed.

```
Symptom: AV occurs in the interface method call chain
Call stack: TMyClass.SomeMethod → [Interface Dispatch] → AV
```

Troubleshooting Steps:
```
① Confirm whether it is an interface call: check whether the call stack passes through Interface Dispatch
② Check the source of the interface reference:
   ├─ Is it obtained from an already F reed object? (Object Free occurs before interface use)
   ├─ Does the interface correctly implement _Release/_AddRef (when manually managed)
   └─ Was an interface reference passed across threads? (Thread A freed the object but thread B still holds an interface reference)
③ Fix directions:
   ├─ Ensure object lifetime ≥ interface usage period
   ├─ Or promote the interface reference to a global/owning object field
   └─ Or use a weak reference pattern to avoid circular references
```

#### Type B: Access Violation — TComponent Ownership/Lifecycle Violation

**Characteristics**: Accessing an already-freed TComponent-derived object, usually manifesting as AV after Form close or in the destruction chain.

```
Symptom: AV in TForm.Destroy or TComponent.Notification
Typical scenario: A Timer/Socket event callback accesses a component whose Owner has been freed
```

Troubleshooting Steps:
```
① Check the source line corresponding to the AV address (via StackTrace.pas or madExcept)
② Confirm whether the component has already been Free / Release'd
③ Check whether component event registration/unregistration is paired:
   ├─ Asynchronous event callbacks such as OnTimer / OnSocketData access Self/component
   ├─ Whether OnNotify / FreeNotification is unregistered before destruction
   └─ TThread.Synchronize/Queue callbacks accessed an already-freed Form
④ Fix directions:
   ├─ Unregister all external event callbacks in Form.OnDestroy
   ├─ Check Assigned(Self) / csDestroying flag in asynchronous callbacks
   └─ Use TComponent.FreeNotification to receive destruction notifications
```

#### Type C: DFM Streaming Error — Class Not Found / Property Error

**Characteristics**: IDE reports errors when opening a Form, or DFM streaming exception occurs at runtime.

```
Typical errors:
  "Class TMyFrame not found"        → missing uses or not RegisterClass'd
  "Property Caption does not exist" → property name spelling or type mismatch in DFM
  "Error reading X: ..."            → binary data corruption or version incompatibility in DFM
```

Troubleshooting Steps:
```
① Class Not Found:
   ├─ Confirm the unit has been added to the uses clause (check both implementation and interface sections)
   ├─ Custom Frame/Component needs to call RegisterClass in initialization
   └─ Check whether the class name in DFM matches the class name in PAS (case-sensitive!)
② Property Error:
   ├─ Compare the erroring property in DFM with the PAS class declaration; check whether property name/type match
   ├─ Whether the property is declared in the published section
   └─ Check whether the object class name in DFM matches PAS (sometimes the IDE writes the wrong inheritance chain)
③ DFM file corruption:
   ├─ Try Save As text DFM (Form → Right Click → Text DFM) then restore
   ├─ Or restore from __history/ backup
   └─ Runtime error → check TReader/TWriter custom serialization logic
```

#### Type D: Package/Dynamic Library Loading Error

**Characteristics**: Errors when starting or loading BPL/DLL.

```
Typical errors:
  "Cannot load package XXX"            → BPL not on search path or version mismatch
  "The procedure entry point YYY..."   → exported function signature mismatch
  "Module not found" / "DLL not found" → dependency DLL missing
  "Runtime error 216/217"              → initialization exception or dependencies not ready
```

Troubleshooting Steps:
```
① Package loading error:
   ├─ check_environment(action="check") — confirm BPL path is included in system PATH
   ├─ delphi_project(action="info") — check RuntimePackages configuration
   ├─ Confirm all dependent packages are compiled and version-matched (build number + compiler version)
   └─ Whether there are circular dependencies in the requires chain
② Entry Point Not Found:
   ├─ Check whether the exported function name spelling/C calling convention matches
   ├─ Delphi package → check exports clause
   └─ Compiler version mismatch (Delphi 11 BPL cannot be loaded in Delphi 12)
③ Runtime error 216/217 (common in DPK initialization and DLL loading):
   ├─ Runtime error 216 = Access Violation (initialization order issue)
   ├─ Runtime error 217 = unhandled exception (exception thrown in unit initialization)
   ├─ Check whether initialization/finalization of all units have exceptions
   └─ Trace back recently modified units from __history/
```

#### Crash Classification Decision Tree

```
Runtime crash
  ├─ Exception type clear → jump directly to matching type A/B/C/D
  ├─ Call stack passes through Interface Dispatch → use A
  ├─ Call stack in TComponent.Notification or Form destruction → use B
  ├─ Error contains "Class ... not found" or "Property ..." → use C
  ├─ Error contains "Cannot load package" / "entry point" / "216" / "217" → use D
  └─ Cannot classify → generic troubleshooting (obtain full call stack via StackTrace.pas, then re-classify)
```

---

### 8.14 Attempt Escalation Checkpoints

§8.1 uses "3 failures" as a one-size-fits-all trigger for manual intervention, but lacks mid-way checkpoints. This section defines **checkpoints after each attempt** to ensure a reasonable shift mechanism before 3 failures:

#### First Attempt Failed

```
┌─ □ Checkpoint 1 ──────────────────────────────────────────┐
│  ① Confirm whether the plan is essentially different from the previous failed plan │
│     → If it only changes parameters/order and retries → §8.1 P2 "homogeneous solution" → change direction immediately │
│                                                          │
│  ② Check whether the right tool was used                  │
│     → Refer to §8.11 decision tree; has the ⭐ tool for the current problem category been used? │
│                                                          │
│  ③ Create a structured debug log (§8.10)                 │
│     → Record: hypothesis → verification method → failure result → what was excluded │
│                                                          │
│  ④ Update hypothesis                                     │
│     → Adjust hypothesis based on failure result and generate new verification plan │
└──────────────────────────────────────────────────────────┘
```

#### Second Attempt Failed

```
┌─ □ Checkpoint 2 ──────────────────────────────────────────┐
│  ① Check experience DB (mandatory)                        │
│     → experience(search, query="{problem keywords} {error type}") │
│     → If matching experience found → apply directly without reinventing the wheel │
│                                                          │
│  ② Bisection isolation assessment                        │
│     → Can §8.9 bisection be used to narrow the scope?    │
│     → Compile problem → file-level/line-level bisection  │
│     → Runtime problem → call chain bisection             │
│     → If bisection not previously attempted → this is the best time │
│                                                          │
│  ③ Try different tools or methods                        │
│     → Same tool failing twice consecutively → §8.1 P2 "same tool 2 times" → switch tools │
│     → Compile problem: full build → single file → syntax check → manual review │
│     → Runtime: msgscan → StackTrace → RTTI → manual guidance │
│                                                          │
│  ④ Update debug log                                      │
│     → Update excluded scope / remaining suspects / current hypothesis │
└──────────────────────────────────────────────────────────┘
```

#### Third Attempt Failed (Before Triggering Intervention)

```
┌─ □ Checkpoint 3 — Pre-Trigger Manual Intervention Check ─┐
│  ① Debug log completeness check                          │
│     → Ensure the log contains: problem description / all attempt records / excluded scope │
│                                                          │
│  ② Experience search has been executed                   │
│     → Confirm that the experience DB has been searched and results recorded in the debug log │
│                                                          │
│  ③ Exception scene info complete                         │
│     → Ensure exception message/call stack/environment info collected per §8.3 template │
│     → Error message incomplete? Trace and supplement first; do not skip │
│                                                          │
│  ④ Bisection has been attempted                          │
│     → If the problem is suitable for bisection isolation but not attempted → force bisection first │
│     → Escalating directly without bisection → human may reject (wastes intervention resources) │
│                                                          │
│  ⑤ Build manual intervention request                     │
│     → Fill in item by item per §8.4 checklist            │
│     → Include minimal reproducible example (MRE) or at least precise reproduction steps │
│                                                          │
│  ✅ All above satisfied → submit intervention request    │
│  ❌ Any item unsatisfied → return to corresponding step to supplement before requesting │
└──────────────────────────────────────────────────────────┘
```

#### Overall Escalation Flowchart

```
Attempt #1 failed
  │
  ├─ Homogeneous solution? → change direction immediately (don't waste #2)
  │
  └─ Checkpoint 1 → update log → update hypothesis → enter #2
         │
Attempt #2 failed
  │
  ├─ Check experience DB + bisection assessment
  ├─ Switch tools? → §8.1 same tool 2 times rule
  │
  └─ Checkpoint 2 → update log → change direction → enter #3
         │
Attempt #3 failed
  │
  └─ Checkpoint 3 (pre-intervention check)
      ├─ Pass → request manual intervention per §8.4
      └─ Fail → supplement and retry (does not consume #4 count)
```

**Key Rules**:
- Between the 1st and 2nd attempts, must **change direction** (different hypothesis/different tool/different method)
- Between the 2nd and 3rd attempts, must **check experience DB + evaluate bisection**
- If any checkpoint discovers a "homogeneous solution" → **immediately** trigger P2 direction change, without waiting for 3 times
- Strictly distinguish "attempt count" from "solution count": 3 different methods each failing once = 3 different solutions (may continue); same solution with modified parameters tried 3 times = 1 solution with 3 homogeneous attempts (must change direction)

---

## ⑪ Experience Saving — Depositing Knowledge into the Experience Knowledge Base

### Overview

The `experience` tool persists effective methods the AI Agent used to solve problems into Daofy's experience knowledge base, so that the AI can directly reuse them the next time it encounters similar problems, without re-exploring or requesting manual intervention.

The experience base is based on semantic vector retrieval and supports automatic deduplication (merging into old records when similarity > 0.85).

### 9.1 Scenarios Where Experience Must Be Saved

| Scenario | Description | Priority |
|------|------|--------|
| After manual intervention resolves | See 8.5 Key Rule ④; save immediately after the problem is resolved | 🔴 Must |
| Non-obvious Bug fix | Fix where the root cause is not intuitive and the troubleshooting process is tortuous | 🔴 Must |
| Compiler/toolchain compatibility issue | Special handling for specific Delphi versions and third-party libraries | 🟡 Recommended |
| Uncommon API usage | Edge usages and parameter combinations not covered by official documentation | 🟡 Recommended |
| New coding rule triggered | Also save experience when a new rule is created due to the problem | 🟡 Recommended |

### 9.2 Save Flow (Search → Generalize → Save)

```
Step ① Search whether similar experience already exists
        └─ experience(action="search", query="...", tags=...)
        Result: exists → skip to step ③ merge/update
              none   → skip to step ②

Step ② Generalize the problem description
        └─ Abstract to a general scenario, rather than specific file/variable names
        Good example: "MSBuild compilation of UI project reports EAccessViolation because CFG condition is empty in dproj"
        Bad example: "Project1.dproj compilation error at line 42"

Step ③ Save/Merge
        └─ No duplicate → experience(action="save", problem=..., solution=..., tags=...)
        Duplicate exists → experience(action="update", id=..., ...)
        Multiple related → experience(action="merge", ids=[...], ...)

Step ④ Rebuild vectors (optional; auto-completed when model is loaded later)
        └─ Auto: triggered automatically on first search() with no results after the model loads
        └─ Manual: experience(action="rebuild_embedding")
        Note: If the embedding model is not loaded on first use, saved records lack vectors.
        After loading the model via delphi_kb(action=build_embedding), the first semantic search
        automatically generates vectors for all records WHERE embedding IS NULL, then retries.

Step ⑤ Verify
        └─ experience(action="search", query="...") to confirm semantic recall works
```

`experience(action="save")` is not a simple INSERT, but a smart "search then decide" flow:

```
save(problem, solution)
  │
  ├─ embedding semantic search for similar records
  │   │
  │   ├─ similarity > 0.85 ──→ auto-merge into old record (no new record)
  │   │   ├─ solution: old solution + new solution concatenated
  │   │   ├─ tags: deduplicated merge
  │   │   ├─ tools_used: deduplicated merge
  │   │   ├─ score: +0.05 (not exceeding 1.0)
  │   │   └─ hit_count: unchanged
  │   │
  │   ├─ similarity > 0.7 (non-force mode) ──→ intercept + prompt
  │   │     Return similar record list; suggest AI manually merge using merge/update
  │   │     Pass force=true to skip this check and save directly
  │   │
  │   └─ similarity ≤ 0.7 ──→ create new record ✅
  │
  └─ embedding unavailable ──→ create directly (no dedup, degraded to LIKE search)
```

**Design Intent**:

| Threshold | Meaning | Handling |
|------|------|---------|
| > 0.85 | Almost the same problem | Auto-merge, zero friction |
| > 0.7 | Possibly related | Prompt AI to judge manually |
| ≤ 0.7 | Different problem | Create normally |

### 9.3 Save Examples

```python
# Save experience
experience(
    action="save",
    problem="MSBuild compilation of UI project fails midway, exit code non-zero, because dproj configuration condition is empty string causing invalid DCC_Define",
    solution="""1. Check whether <PropertyGroup Condition="'$(CFG)'!=''"> in dproj matches the actual configuration name
2. Ensure the condition string is non-empty, e.g., Condition="'$(CFG)'=='Debug|Win32'"
3. Clean .dcu cache then rebuild""",
    tags=["compile", "MSBuild", "dproj", "CFG condition"],
)

# Search existing experience
experience(
    action="search",
    query="MSBuild compilation failure DCC_Define condition",
    tags=["compile"],
)

# Merge multiple similar experiences into one abstract experience
experience(
    action="merge",
    ids=["exp_id_1", "exp_id_2"],
)

# Clean up low-value experience
experience(
    action="prune",
    limit=20,  # List 20 lowest-value experiences
)
```

### 9.4 Experience Quality Specification

| Dimension | Requirement | Bad Example |
|------|------|------|
| **problem** | Generalize the general scenario, including key trigger conditions | `Form1 reports error` (too specific) |
| **solution** | Step-by-step, reproducible, with commands/code | `just change the config` (vague) |
| **tags** | 3~5 tags covering different search angles | `["bug"]` (too broad) |
| **generalization** | Strip project/file-level specific names | Use `{project name}` instead of `Project1.dproj` |

### 9.5 Periodic Maintenance

#### 9.5.1 prune — Clean up low-value experience

`experience(action="prune")` lists candidate entries for deletion in ascending order of value score, for the AI to `delete` after manual judgment.

**Value Calculation Formula**:

```
value = hit_count × score × time_decay
```

- `hit_count`: Number of times viewed/reused (higher is more valuable)
- `score`: Quality score (higher is more valuable)
- `time_decay`: If not updated for more than 30 days, decay by half-life (× 0.5 per 30 days)

**Typical Low-Value Patterns**:

| Pattern | Description | Handling |
|------|------|------|
| hit_count=1 and not updated for a long time | Saved but never used | Consider deleting |
| Content too specific | Can be generalized to a more abstract experience | Delete after merging into abstract experience |
| Already covered by other experience | Redundant record describing the same problem | Keep the best, delete the rest |

#### 9.5.2 merge — Merge similar experience

When multiple experiences describe the same type of problem, use `merge` to combine them into one abstract experience, with `tags` covering all scenarios.

```python
# Merge into target record (keep target, delete the rest)
experience(action="merge",
    ids=["exp_id_1", "exp_id_2", "exp_id_3"],
    keep="exp_id_1")

# Merge into a new record (delete all, create new)
experience(action="merge",
    ids=["exp_id_1", "exp_id_2"])
```

**Merge Rules**: problem/solution concatenated, tags/tools_used deduplicated, hit_count accumulated.

#### 9.5.3 Experience Maintenance Best Practices

| Timing | Practice | Description |
|------|------|------|
| Before saving | **Generalize first** | Call `search(query=...)` to confirm whether similar experience already exists; if found, use `merge`/`update` to merge, do not save another specific scenario |
| Task completion | **Proactively merge** | If the just-resolved solution is related to existing experience but done differently, merge manually to avoid independent fragmentation |
| Periodic | **Clean up with prune** | Execute `prune` monthly to list low-value records, review then `delete`; keep the experience base concise |
| Duplicate found | **Abstract merge** | When multiple experiences describe the same type of problem (e.g., "message condensing" for different tools), merge into one abstract experience with `tags` covering all scenarios |

#### 9.5.4 Rule Linkage

Problems repeatedly hit 3+ times in experience should be considered for upgrading to formal rules in the built-in coding rule resources, so that all AI Agents benefit, rather than relying on experience recall.

```
Experience with hit_count ≥ 3 → evaluate whether it can be ruled → update src/resources/coding-rules.md → keep experience as reference case
```

---

### 9.6 Embedding Degradation Strategy

The experience base remains fully usable without a vector model; only search accuracy is reduced. Degradation flow:

```
search(query)
  │
  ├─ embedding model loaded?
  │   ├─ Yes → semantic search (cosine similarity sorting)
  │   │      └─ No results? → auto rebuild_embeddings() then retry
  │   └─ No → LIKE keyword degradation search (%query%)
  │
  └─ Return results
```

**Key Points**:

- **Model not loaded**: `save()` does not save embedding (BLOB is NULL), `search()` uses LIKE degradation
- **Model loaded later**: After calling `delphi_kb(action=build_embedding)`, the first `search()` automatically triggers generation of missing vectors
- **rebuild_embedding**: Can also be called manually via `experience(action="rebuild_embedding")` to supplement vectors for all `embedding IS NULL` records
- **Degradation is fully transparent**: Upper layers need not care which search mode is currently in use

---

### 9.7 Quality Assurance System

| Assurance Mechanism | Layer | Description |
|----------|------|------|
| Auto dedup merge | save() | similarity > 0.85 auto-merge, > 0.7 intercept + prompt |
| Auto rebuild vectors | search() | Auto-triggered when model loaded but no results |
| Time decay | prune() | Value of experience not updated for 30 days decays by half-life |
| Usage count | get() | hit_count incremented each time viewed |
| Timeout protection | server.py | 30-second timeout to prevent embedding loading from blocking MCP |
| Thread safety | Connection layer | Per-thread independent SQLite connections, WAL mode to prevent locks |

> The unique identifier of the experience base is the ID (short UUID), which cannot be manually modified. All management operations go through the experience tool; directly manipulating SQLite files is prohibited.

---

## ⑫ Rule Maintenance
After fixing a bug, summarize it as a rule and add it to the project rule file. Before adding, check whether the same rule already exists. After modification, update the date version number at the top.

### New Rule Template
```markdown
#### [Category] [Title]
- **Problem**: What problem this rule is meant to prevent
- **Rule**: Specific constraints or practices
- **Positive Example**: ```delphi {code conforming to the rule} ```
- **Negative Example**: ```delphi {code violating the rule} ```
```
Example:
```markdown
#### Common Error Pattern Empty except Block
- **Problem**: An empty `except...end` swallows all exceptions, causing errors to be silently ignored
- **Rule**: Within an `except` block, must at least log and re-raise, or perform meaningful handling
- **Positive Example**: `except on E: Exception do Logger.Error(E); raise; end;`
- **Negative Example**: `except end;`
```
