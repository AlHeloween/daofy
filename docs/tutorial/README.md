# Daofy Tutorial Materials

This directory contains all demo materials needed for recording tutorials, organized by scenario.

---

## Directory Structure

```
docs/tutorial/
├── tutorial_script.md         ← complete demo script (main script)
├── README.md                  ← this file (material index)
│
├── demo-project/              ← Scenarios 4.5 / 4.7 / 5.4 / 4.11
│   ├── DemoApp.dproj          # Sample Delphi project file
│   ├── DemoApp.dpr            # Program entry point
│   ├── MainForm.pas           # Main unit (uses JsonConfigManager)
│   ├── JsonConfigManager.pas  # JSON configuration manager (full implementation)
│   └── CODING_RULES.mdc       # Project coding standards (modern style)
│
├── legacy-project/            ← Scenario 4.11 coding standards comparison
│   ├── LegacyApp.dproj        # Placeholder project file (for project_path parameter)
│   └── CODING_RULES.mdc       # Old project coding standards (Hungarian naming / 4 spaces / begin at end of line)
│
├── review-demo/               ← Scenario 4.7 code audit
│   └── LegacyData.pas         # Code containing 5 types of intentional issues (no hint comments)
│
├── refactor-demo/             ← Scenario 4.9 multi-file refactoring
│   ├── DataProcessor.pas      # Uses TStringList for data parsing
│   ├── ConfigManager.pas      # Uses TStringList to manage configuration
│   └── UserManager.pas        # Uses TStringList to manage users
│
├── compile-error-demo/        ← Scenario 5.3 complex compilation error diagnosis
│   ├── ErrorCode.pas          # TDictionary generic error without a comparer provided
│   └── ErrorCode_Fixed.pas    # Fixed reference version (for the recorder's comparison)
│
├── database-demo/             ← Scenario 4.4 knowledge base-driven code generation
│   └── DatabaseManager.pas    # AI-generated FDConnection + SQLite management unit
│
├── group-project/             ← Scenario 4.12 batch multi-project compilation
│   ├── ProjectGroup.groupproj # Project group file
│   ├── LibProject/            # Shared library project (compiled first)
│   │   ├── LibUtils.dproj
│   │   ├── LibUtils.dpr
│   │   └── LibUtils.pas
│   └── AppProject/            # Application project (compiled later, depends on LibProject)
│       ├── MainApp.dproj
│       ├── MainApp.dpr
│       └── MainApp.pas
│
├── employee-input/            ← Scenario 4.5 FireDAC SQLite employee information entry
│   ├── EmployeeInput.dproj    # FireDAC SQLite project
│   ├── EmployeeInput.dpr      # Program entry point
│   ├── Form.Main.pas          # Main form (DBGrid + DBEdit detail panel)
│   └── Form.Main.dfm          # Form layout (left-right split)
│
├── test-project/              ← Scenario 4.6 single-file syntax check/run_verify verification
│   ├── TestProject.dproj      # Simple VCL project
│   ├── TestProject.dpr
│   ├── Unit1.pas
│   └── Unit1.dfm
│
├── test-verify-crash/         ← Scenario run_verify crash detection demo
│   ├── TestCrash.dproj        # FormCreate throws an exception
│   ├── TestCrash.dpr
│   ├── MainForm.pas
│   ├── MainForm.crash.dproj.bak
│   ├── Form.MainForm.pas
│   └── Form.MainForm.dfm
│
└── workflow-demo/             ← Scenario 5.4 complete workflow
    ├── config.json            # JSON sample configuration file
    └── IniConfigManager.pas   # INI read/write unit
```

---

## Scenario Mapping Table

| Scenario | Material | Highlight |
|------|------|--------|
| 4.3 Semantic search discovers hidden APIs | — | Natural language matching among 300,000 functions |
| 4.4 Knowledge base-driven complex code generation | `database-demo/DatabaseManager.pas` | AI checks the KB to confirm the FDConnection signature before generating |
| 4.5 Compile project | `demo-project/DemoApp.dproj` | One-click compilation |
| 4.6 Single-file syntax check | `demo-project/MainForm.pas` | Quick check |
| 4.7 Coding standards-driven audit + create ticket | `review-demo/LegacyData.pas` | Item-by-item review against the standards + automatically create an Issue |
| 4.8 Reference query | `refactor-demo/*.pas` | Assess the impact of changes |
| 4.9 Multi-file refactoring | `refactor-demo/*.pas` | TStringList → TArray\<String\> |
| 4.10 Code formatting + automatic backup | `refactor-demo/*.pas` | pasfmt formatting + `__history` version backup |
| 4.11 Coding standards control AI behavior | `demo-project/CODING_RULES.mdc` + `legacy-project/CODING_RULES.mdc` | Same requirement → different rules → different code style |
| 4.12 Batch multi-project compilation | `group-project/ProjectGroup.groupproj` | Automatically handles dependency order |
| 5.1a Build documentation KB | — | 160,000-page CHM index |
| 5.1b Practical search in documentation KB | — | Natural language search of help documentation |
| 5.2 Install component package | — | Compile and register .dpk |
| 5.3 Complex compilation error diagnosis | `compile-error-demo/ErrorCode.pas` | Query KB for generic constraints → root-cause fix |
| 5.4 Complete 0-to-1 workflow | `demo-project/*` | Standards → API → coding → compilation → audit → ticket |
| **5.6 Automated testing (GUI)** | GUI program containing the DaofyAutomation unit | Named Pipe screenshots + control interaction |
| **5.6 Automated testing (Console)** | Any console program | subprocess stdin/stdout, no modification required |

---

## Key Scenario Details

### `compile-error-demo/` — Complex Compilation Error Diagnosis

**Error**: `E2511 Type parameter 'TCustomKey' must have a comparer`

**Root cause**: The `TKey` of `TDictionary<TCustomKey, string>` is a record and has no default `IEqualityComparer`.

**AI's diagnostic chain**:
1. Search KB → `TDictionary` class definition → discover that the generic constraint requires a comparer
2. Search KB → `TEqualityComparer` class definition → learn how to subclass
3. Generate `TCustomKeyComparer` + modify the constructor
4. Recompile successfully

`ErrorCode_Fixed.pas` is the fixed reference version (for the recorder's comparison, not provided as input to the AI).

### `review-demo/LegacyData.pas` — 5 Types of Intentional Issues

| # | Issue | Location | Level |
|---|------|------|------|
| 1 | TStringList.Create has no try/finally | ExportData | 🔴 Critical |
| 2 | Delete inside a for loop causes skipped items | ProcessItems | 🔴 Critical |
| 3 | Magic numbers (10/1.5/100/0.95) | CalculateTotal | 🟡 Warning |
| 4 | Value retrieval after finally, fragile logic | GetUserCount | 🟡 Warning |
| 5 | Unused local variable LValue | ExportData | 🔵 Suggestion |

> The code file **contains no hint comments**; all issues are hidden in the logic.

### `refactor-demo/` — Refactorable Patterns

All three units return `TStringList`, making them suitable for overall refactoring to `TArray<String>`:
- **DataProcessor.pas**: ParseCSV / SplitLines / JoinLines
- **ConfigManager.pas**: LoadConfig / GetSectionNames
- **UserManager.pas**: LoadUsers / GetUserEmails / SortUsers

### `group-project/` — Compilation Dependency Order

```
LibProject/LibUtils.dproj → compile first (outputs .dll/.bpl)
        ↓ depends on
AppProject/MainApp.dproj → compile later (references the LibUtils unit)
```

The order is explicitly specified in `<BuildOrder>` of `ProjectGroup.groupproj`.

---

## Pre-recording Preparation Checklist

- [ ] Python 3.10+ / Git / Delphi IDE installed
- [ ] Project cloned, dependencies installed, AI client configured with the MCP Server
- [ ] `demo-project/` copied to a compilable path on the local machine
- [ ] The `ProjectVersion` of `.dproj` matches the local Delphi version (21=10.4 / 22=11 / 23=12)
- [ ] Documentation knowledge base has been pre-built (building takes several minutes; it is recommended to build it before recording)
- [ ] For semantic search scenarios, build embedding in advance: `delphi_kb(action="build_embedding")`
- [ ] For Gitea scenarios, an accessible Gitea instance (e.g., https://code.qdac.cc:3000) and repository permissions are required
- [ ] Before recording each scenario, confirm that the material files are in the correct directory