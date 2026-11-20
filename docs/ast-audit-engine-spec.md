# Delphi AST Semantic Analysis Engine — Knowledge Base Enhancement + Code Audit Specification

> Version: v1.0
> Purpose: Development specification for the Daofy MCP Server companion AST parser (daudit.exe)
> Integration: Delphi console program → subprocess JSON pipe → Python KB service

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Integration Protocol](#2-integration-protocol)
3. [Knowledge Base Enhancement Interface](#3-knowledge-base-enhancement-interface)
4. [Complete Audit Rule List](#4-complete-audit-rule-list)
5. [Database Schema Extension](#5-database-schema-extension)
6. [Python Integration Changes](#6-python-integration-changes)
7. [Implementation Roadmap](#7-implementation-roadmap)

---

## 1. Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                     daudit.exe (Delphi Console)                   │
│                                                                   │
│  ┌──────────┐   ┌──────────────────┐   ┌───────────────────────┐  │
│  │  Lexer   │ → │   Parser (AST)    │ → │  Semantic Analysis   │  │
│  └──────────┘   └────────┬─────────┘   │ · Scope Resolution   │  │
│                          │             │ · Type Binding       │  │
│                          │             │ · Reference Tracking │  │
│                          │             │ · Audit Rule Engine  │  │
│                          │             └──────────┬────────────┘  │
│                          │                        │               │
│                          ▼                        ▼               │
│                    ┌────────────────────────────────────────┐     │
│                    │         JSON Output (stdout)           │     │
│                    │ · --mode audit Code audit violation report │ │
│                    │ · --mode ast  AST syntax parsing       │     │
│                    └──────────────────┬─────────────────────┘     │
└───────────────────────────────────────┼───────────────────────────┘
                                        │ stdout (JSON)
                                        ▼
┌──────────────────────────────────────────────────────────────────┐
│                    Python MCP Server Side                          │
│                                                                   │
│  smart_cache_knowledge_base.py  ← consume JSON, write to SQLite    │
│  tools/knowledge_base.py        ← search interface, return results to AI │
│  tools/audit.py (new)           ← audit interface, return violation report to AI │
└──────────────────────────────────────────────────────────────────┘
```

### Core Layers

| Layer | Responsibility | Technical Carrier |
|----|------|---------|
| **AST parsing** | Parse Delphi source into a syntax tree, covering all syntax structures such as class/record/interface/function/property/field/const/enum | daudit.exe `--mode ast` |
| **Semantic analysis** | Scope resolution (entity ownership), type binding (type name→definition), reference tracking (who uses whom), inheritance chain resolution | daudit.exe `--mode ast` |
| **Audit engine** | Run predefined rule sets on AST + semantic analysis results and output violation reports | daudit.exe `--mode audit` |
| **AI decision-making** | Consume audit reports, classify severity, eliminate false positives, generate fix suggestions, output final report | MCP Server + LLM |

---

## 2. Integration Protocol

### 2.1 Command-Line Interface

```bash
# ── Mode 1: AST syntax parsing (entity extraction) ──
daudit.exe --mode ast "C:\Dev\Unit1.pas" [--format json] [--compact]

# ── Mode 2: Code audit (returns violation list) ──
# Full project audit
daudit.exe --mode audit --source-dir "C:\Project\src" --output "audit_report.json" [--rules P0,P1]

# Specify rules
daudit.exe --mode audit --source-dir "C:\Project\src" --rules C001,C002,R001

# Incremental audit (only audit git-changed files)
daudit.exe --mode audit --git-diff HEAD~1 --source-dir "C:\Project\src"
```

### 2.2 STDIO Protocol Standard

```
stdin:   In batch mode, receives file list JSON
stdout:  JSON (main output channel; one complete JSON per line or overall batch JSON)
stderr:  Logs/diagnostics (does not affect the MCP communication pipe)
exit:    0 = all success, 1 = partial file failure, 2 = severe error
```

### 2.3 Batch Input Format

```json
{
  "files": [
    "C:\\Project\\src\\Unit1.pas",
    "C:\\Project\\src\\Unit2.pas",
    "C:\\Project\\src\\Unit3.pas"
  ],
  "options": {
    "threads": 4,
    "timeout_ms": 30000
  }
}
```

---

## 3. AST Syntax Parsing Output Format (`--mode ast`)

### 3.1 Output JSON Schema

```json
{
  "file": "System.Classes.pas",
  "status": "ok",
  "error_msg": null,

  "unit_name": "System.Classes",
  "file_hash": "md5_or_mtime_size",
  "parse_time_ms": 45,

  "file_stats": {
    "total_lines": 16789,
    "total_entities": 342
  },

  "uses": {
    "interface": ["System.SysUtils", "System.Types"],
    "implementation": ["System.Variants", "System.RTLConsts"]
  },

  "entities": [
    {
      "kind": "TC",
      "name": "TStringList",
      "name_lower": "tstringlist",
      "parent_scope": null,
      "visibility": "published",
      "modifiers": ["sealed"],

      "start_line": 1234,
      "end_line": 1456,
      "start_offset": 45000,
      "end_offset": 52000,
      "body_length": 7000,
      "code_block": "TStringList = class(TStrings)\n  ...\nend;",

      "definition": "class(TStrings)",
      "signature": "TStringList = class(TStrings)",

      "inherits_from": "TStrings",
      "inheritance_chain": ["TStringList", "TStrings", "TPersistent", "TObject"],

      "members": [
        {"kind": "FF", "name": "Add", "line": 1300},
        {"kind": "MF", "name": "FList", "line": 1280}
      ],
      "member_count": 42,

      "type_refs": [
        {"name": "TStrings", "resolved_kind": "TC"},
        {"name": "TList<string>", "base_type": "TList", "type_args": ["string"]}
      ]
    },
    {
      "kind": "FF",
      "name": "Add",
      "parent_scope": "TStringList",
      "start_line": 1300,
      "end_line": 1320,
      "code_block": "function TStringList.Add(const S: string): Integer;\nbegin\n  ...\nend;",
      "signature": "function Add(const S: string): Integer;",
      "return_type": "Integer",
      "params": [
        {"name": "S", "type": "string", "modifier": "const"}
      ],
      "modifiers": [],
      "visibility": "public",
      "calls": ["Grow", "InsertItem"]
    }
  ],

  "errors": [
    {"line": 567, "message": "Unresolved type: TSomeUndefinedType", "severity": "warning"}
  ]
}
```

### 3.2 Entity Kind Encoding Table

| Code | Meaning | Key Additional Fields |
|------|------|-------------|
| `TC` | Class | inherits_from, inheritance_chain, members, visibility, modifiers |
| `TR` | Record | inherits_from (if any), members |
| `TI` | Interface | inherits_from, guid |
| `TH` | Class/Record Helper | parent_scope = target type |
| `TE` | Enum | values[] |
| `TS` | Set | base_type |
| `TY` | Type Alias | definition, is_pointer, is_array |
| `AT` | Array Type | dimensions, element_type |
| `PT` | Pointer Type | pointed_type |
| `FF` | Function | signature, return_type, params[], calls[] |
| `FP` | Procedure | signature, params[] |
| `OP` | Operator Overload | signature, operator_symbol (Add/Implicit/Explicit/...), return_type |
| `CC` | Const | value |
| `CR` | ResourceString | value |
| `GV` | Global Variable | var_type, visibility |
| `MF` | Field | parent_scope, visibility |
| `MP` | Property | parent_scope, prop_type, read_spec, write_spec |
| `MM` | Method Pointer/Type | signature |
| `ME` | Event | parent_scope, event_type |
| `UI` | Unit (uses) | — |
| `KS` | String Literal | value |
| `DF` | DFM Property | prop_name, decoded_value |
| `AB` | Custom Attribute | attribute_name, params |

---

## 4. Complete Audit Rule List (`--mode audit`)

### 4.1 Rule Summary Table

Three priority levels: **P0 = must implement**, P1 = high value, P2 = future iteration.

Each rule includes:
- Detection mechanism: tells the AST engine what to look for in the syntax tree
- Output format: unified `AuditViolation` JSON
- is_ai_needed: false = AST directly concludes, true = requires AI to judge further

---

#### P0 Rules (21 rules, highest ROI)

| ID | Category | Rule | Detection Method | is_ai_needed |
|----|------|------|---------|:-----------:|
| **C001** | Error pattern | `with` statement detection | Find all `WithStatement` nodes | false |
| **C002** | Error pattern | Empty `except` block | `ExceptBlock` contains no statements | false |
| **C003** | Error pattern | `as` without preceding `is` check | No `IsExpression` within 5 lines before `AsExpression` | false |
| **C004** | Error pattern | No logging before `raise` | `ExceptBlock` contains only `raise;`, no logging call | false |
| **R001** | Resource leak | `Create`/`Free` mismatch | Count Create:N vs Free/FreeAndNil:N within class scope | false |
| **R002** | Resource leak | `TFileStream`/`THandle` not released | No `.Free`/`.Close` on variable path | false |
| **R003** | Resource leak | `TObjectList.OwnsObjects` not set | `TObjectList.Create` without parameter or not assigned | false |
| **R004** | Resource leak | `TStringBuilder`/`TEncoding` not released | Temporarily created instance has no `.Free` after use | false |
| **Q001** | Code quality | Method too long >80 lines | `end_line - start_line > 80` | false |
| **Q002** | Code quality | Cyclomatic complexity >3 | Recursively count `if/for/while/case/try` nesting depth | false |
| **Q003** | Code quality | Magic numbers | Numeric literals filtered for `0/1/-1/True/False/named constants/type boundaries` | false |
| **Q004** | Code quality | Method parameters >5 | `MethodDeclaration.params.length > 5` | false |
| **Q005** | Code quality | Class methods >50 | `ClassDeclaration.methods.length > 50` | false |
| **D001** | Delphi | String `+` inside loop | `BinaryExpression(op='+', string)` inside loop body | false |
| **D002** | Delphi | `Create` inside loop | `CallExpression(.Create)` inside loop body | false |
| **D003** | Delphi | Missing enum case | `CaseStatement` branch count < enum element count | true |
| **D004** | Delphi | override missing `inherited` | Method with `modifiers:['override']` has no `InheritedCall` in body | true |
| **S001** | Security | SQL string concatenation | `SQL.Add`/`SQL.Text` + `+` concatenation expression | false |
| **S002** | Security | Missing function return value | Multiple `if/else` paths but some paths lack `Result:=` assignment | false |
| **S003** | Security | Unannotated output parameters | Reference-passed parameters (non-string/record/interface) without `var`/`out` | false |
| **U001** | Consistency | Unreferenced uses | Units in uses list never appear in AST symbol references | false |

#### P1 Rules (15 rules, require basic semantic analysis)

| ID | Category | Rule | Detection Method | Dependency |
|----|------|------|---------|------|
| **R005** | Resource | try not immediately after acquisition | Next statement after resource creation is not `try` | AST adjacency check |
| **R006** | Resource | Database connection not closed | `TSQLConnection`/`TADOConnection` variable has no `.Close`/`.Free` | Type binding |
| **C005** | Error | Event not set to nil | No `OnXxx := nil` in `destructor` | Class property table + destructor body |
| **C006** | Error | Anonymous method loop capture | `AnonymousMethod` inside loop references loop variable | Scope analysis |
| **C007** | Error | Thread accesses VCL | VCL control access in `TThread.Execute` call chain | Call graph + type binding |
| **D005** | Delphi | class helper conflict | Multiple helpers for same target type define methods with same name | Cross-file registry |
| **D006** | Delphi | published non-streamable | `published` section contains generic/non-streamable types | Type binding |
| **D007** | Delphi | AnsiString/WideString | All AnsiString/WideString declarations | Type binding |
| **D008** | Delphi | Variant usage | All Variant declarations and assignments | Type binding |
| **Q006** | Quality | Inefficient IntToStr | `IntToStr` appears in loop string concatenation | Call tracking |
| **Q007** | Quality | Repeated `as` inside loop | Same-type `AsExpression` inside loop body | Expression matching |
| **S004** | Security | Hard-coded credentials | String literal contains `password`/`secret`/`api.key` patterns | String analysis |
| **S005** | Security | Hard-coded user strings | `ShowMessage`/`MessageDlg` parameter is a literal | Function call analysis |
| **P001** | Performance | Repeated `as` inside loop | Same as Q007, marked with higher severity | Expression matching |
| **P002** | Performance | High-frequency RTTI calls | Multiple `GetType`/`GetDeclaredMethods` and other RTTI calls within a method (each creates an interface wrapper with overhead) | Call counting |

#### P2 Rules (9 rules, future iteration)

| ID | Category | Rule | Description |
|----|------|------|------|
| **R007** | Resource | Interface circular reference | Type reference graph A→B→A; AST marks suspicious cases |
| **R008** | Resource | TComponent double Free | Double release along Owner/Parent chain |
| **C008** | Error | Empty `finally` block | No operation inside finally |
| **D009** | Delphi | init/finalization leak | Create without Free in section |
| **D010** | Delphi | Hard type cast `Type(x)` | Find all HardCast |
| **Q008** | Quality | Code clone | AST subtree similarity matching |
| **Q009** | Quality | Naming convention | Configurable naming convention checks |
| **S006** | Security | Buffer overflow | Move/CopyMemory destination size check |
| **A001** | Comprehensive | Impact scope analysis | Mark all affected files when an entity changes |

### 4.2 Audit Violation JSON Format

```json
{
  "audit_summary": {
    "source_dir": "C:\\Project\\src",
    "total_files": 25,
    "total_lines": 48900,
    "total_violations": 42,
    "by_severity": {"critical": 3, "warning": 15, "suggestion": 24},
    "by_rule": {"C001": 5, "R001": 3, "Q003": 12, ...},
    "scan_time_ms": 28500
  },

  "violations": [
    {
      "rule_id": "C001",
      "rule_name": "with statement",
      "severity": "suggestion",
      "category": "Common error patterns",
      "file": "Unit1.pas",
      "line": 42,
      "column": 3,
      "code_snippet": "with StringList do",
      "message": "Using a with statement may cause name conflicts and reduce readability",
      "is_ai_needed": false,
      "fix_example": "for I := 0 to StringList.Count - 1 do\n  StringList[I] := ...;"
    },
    {
      "rule_id": "R001",
      "rule_name": "Create/Free mismatch",
      "severity": "critical",
      "category": "Resource leak",
      "file": "Unit2.pas",
      "line": 85,
      "code_snippet": "FBitmap := TBitmap.Create;",
      "context_code": "...\nconstructor TMyClass.Create;\nbegin\n  FBitmap := TBitmap.Create;\nend;\n\ndestructor TMyClass.Destroy;\nbegin\n  // FBitmap.Free;  ← missing\n  inherited;\nend;",
      "message": "TBitmap.Create is called in TMyClass constructor, but there is no corresponding Free in the destructor",
      "is_ai_needed": false,
      "fix_example": "destructor TMyClass.Destroy;\nbegin\n  FBitmap.Free;\n  inherited;\nend;"
    },
    {
      "rule_id": "D003",
      "rule_name": "Missing enum case",
      "severity": "warning",
      "category": "Delphi-specific",
      "file": "Unit3.pas",
      "line": 200,
      "code_snippet": "case Color of\n  Red: ...;\n  Green: ...;\nend;",
      "message": "Enum TColor has 4 values, but case covers only 2; missing: Blue, Yellow",
      "is_ai_needed": true,
      "extra_data": {
        "enum_name": "TColor",
        "enum_values": ["Red", "Green", "Blue", "Yellow"],
        "covered_values": ["Red", "Green"],
        "missing_values": ["Blue", "Yellow"]
      },
      "fix_example": "case Color of\n  Red: ...;\n  Green: ...;\n  Blue: ...;\n  Yellow: ...;\nelse\n  raise Exception.Create('Unknown color');\nend;"
    }
  ],

  "context_data": {
    "inheritance_trees": [
      {"class": "TMyForm", "ancestors": ["TMyForm", "TForm", "TCustomForm", "TWinControl", "TControl", "TComponent", "TPersistent", "TObject"]}
    ],
    "dependency_graph": {
      "nodes": [...],
      "edges": [...]
    }
  }
}
```

### 4.3 Severity Level Definitions

| Level | Meaning | AI Handling |
|------|------|-----------|
| `critical` | Will inevitably cause resource leaks/crashes/security vulnerabilities | Must fix; AI directly produces fix plan |
| `warning` | High probability of being a problem | AI verifies, then produces fix plan |
| `suggestion` | Style/quality suggestion | AI decides whether to adopt; included in report "Suggestions" section |

---

## 5. Database Schema Extension

### 5.1 New Columns in vocabularies Table

```sql
-- Existing knowledge base table vocabularies; add AST enhancement fields
ALTER TABLE vocabularies ADD COLUMN end_line INTEGER;
ALTER TABLE vocabularies ADD COLUMN end_offset INTEGER;
ALTER TABLE vocabularies ADD COLUMN body_length INTEGER;
ALTER TABLE vocabularies ADD COLUMN code_block TEXT;
ALTER TABLE vocabularies ADD COLUMN signature TEXT;
ALTER TABLE vocabularies ADD COLUMN modifiers TEXT;         -- JSON: ["virtual", "override"]
ALTER TABLE vocabularies ADD COLUMN visibility TEXT;        -- "private"|"protected"|"public"|"published"
ALTER TABLE vocabularies ADD COLUMN type_refs TEXT;         -- JSON: [{"name":"TList","resolved_kind":"TC"}]
ALTER TABLE vocabularies ADD COLUMN member_count INTEGER;
ALTER TABLE vocabularies ADD COLUMN inheritance_chain TEXT; -- JSON: ["TStringList","TStrings","TPersistent","TObject"]
ALTER TABLE vocabularies ADD COLUMN generics TEXT;          -- JSON: {"T":"class,constructor"}
ALTER TABLE vocabularies ADD COLUMN values TEXT;            -- Enum values/constant values JSON
ALTER TABLE vocabularies ADD COLUMN params TEXT;            -- Function parameter JSON
ALTER TABLE vocabularies ADD COLUMN return_type TEXT;       -- Function return type
ALTER TABLE vocabularies ADD COLUMN calls TEXT;             -- Function call list JSON
ALTER TABLE vocabularies ADD COLUMN ref_count INTEGER;      -- Reference count (populated by semantic analysis)
ALTER TABLE vocabularies ADD COLUMN source TEXT;            -- "ast" | "regex" (identifies data source)
```

### 5.2 New entity_refs Table (Reference Graph)

```sql
CREATE TABLE IF NOT EXISTS entity_refs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL,          -- vocabularies.id (referrer)
    target_name TEXT NOT NULL,            -- Referenced entity name
    target_kind TEXT,                     -- Referenced entity kind (TC/FF/...)
    target_file_id INTEGER,              -- File where the referenced target is located
    ref_type TEXT NOT NULL,               -- 'type_ref' | 'call' | 'inherits' | 'uses' | 'access'
    line INTEGER,                         -- Line number where reference occurs
    code_snippet TEXT,                    -- Code snippet at reference (short)
    FOREIGN KEY (source_id) REFERENCES vocabularies(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_entity_refs_source ON entity_refs(source_id);
CREATE INDEX IF NOT EXISTS idx_entity_refs_target ON entity_refs(target_name, target_kind);
CREATE INDEX IF NOT EXISTS idx_entity_refs_target_file ON entity_refs(target_file_id);
```

### 5.3 New audit_results Table (Audit Result Cache)

```sql
CREATE TABLE IF NOT EXISTS audit_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_path TEXT NOT NULL,
    file_path TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    severity TEXT NOT NULL,               -- 'critical' | 'warning' | 'suggestion'
    line INTEGER,
    code_snippet TEXT,
    message TEXT,
    is_ai_confirmed INTEGER DEFAULT 0,   -- 0=AST automatic, 1=AI confirmed, 2=fixed and verified
    fix_suggestion TEXT,
    scan_timestamp REAL,
    created_at REAL DEFAULT (julianday('now')),
    UNIQUE(project_path, file_path, rule_id, line)
);

CREATE INDEX IF NOT EXISTS idx_audit_project ON audit_results(project_path);
CREATE INDEX IF NOT EXISTS idx_audit_severity ON audit_results(severity);
CREATE INDEX IF NOT EXISTS idx_audit_rule ON audit_results(rule_id);
```

---

## 6. Python Integration Changes

### 6.1 Knowledge Base Parsing Function Replacement

File: `src/services/knowledge_base/smart_cache_knowledge_base.py`

```python
@staticmethod
def _parse_delphi_file_static(file_path_str: str) -> Tuple[str, List[Dict], int, List[str]]:
    """Parse Delphi file: prefer AST engine, fallback to regex on failure"""
    
    ast_result = _call_daudit_kb(file_path_str)
    
    if ast_result and ast_result["status"] == "ok":
        items = []
        for ent in ast_result["entities"]:
            item = {
                'type': ent['kind'],
                'name': ent['name'],
                'line': ent['start_line'],
                'base_class': ent.get('inherits_from'),
                'description': ent.get('definition', ''),
                # AST enhancement fields
                'end_line': ent.get('end_line'),
                'code_block': ent.get('code_block', ''),
                'signature': ent.get('signature', ''),
                'modifiers': json.dumps(ent.get('modifiers', []), ensure_ascii=False),
                'visibility': ent.get('visibility', 'published'),
                'type_refs': json.dumps(ent.get('type_refs', []), ensure_ascii=False),
                'inheritance_chain': json.dumps(ent.get('inheritance_chain', []), ensure_ascii=False),
                'params': json.dumps(ent.get('params', []), ensure_ascii=False),
                'return_type': ent.get('return_type', ''),
                'calls': json.dumps(ent.get('calls', []), ensure_ascii=False),
                'source': 'ast',
            }
            items.append(item)
        
        uses = ast_result.get('uses', {})
        uses_list = uses.get('interface', []) + uses.get('implementation', [])
        total_lines = ast_result.get('file_stats', {}).get('total_lines', 0)
        
        return (file_path_str, items, total_lines, uses_list)
    
    # fallback: current regex logic
    return _regex_fallback(file_path_str)


def _call_daudit_kb(file_path: str) -> Optional[Dict]:
    """Call daudit.exe --mode kb single-file mode"""
    ```python
    import subprocess, json
    
    daudit_path = _find_daudit()
    if not daudit_path:
        return None
    
    try:
        result = subprocess.run(
            [daudit_path, "--mode", "kb", "--input", file_path, "--format", "json"],
            capture_output=True, text=True, timeout=60,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError) as e:
        logger.warning("AST parsing failed %s: %s", file_path, e)
    
    return None


def _find_daudit() -> Optional[str]:
    """Find daudit.exe path"""
    candidates = [
        Path(__file__).parent.parent.parent.parent / "tools" / "daudit" / "daudit.exe",
        Path.cwd() / "tools" / "daudit" / "daudit.exe",
    ]
    for p in candidates:
        if p.exists():
            return str(p.resolve())
    return None
```

### 6.2 New Audit MCP Tool

File: `src/tools/audit.py` (new)

```python
"""
Audit MCP tool

Provides an AI Agent invocation interface for daudit --mode=audit.
"""

import json
import subprocess
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from mcp.types import CallToolResult, TextContent

logger = logging.getLogger(__name__)


def _find_daudit() -> Optional[str]:
    """Find daudit.exe"""
    candidates = [
        Path(__file__).parent.parent.parent / "tools" / "daudit" / "daudit.exe",
        Path.cwd() / "tools" / "daudit" / "daudit.exe",
    ]
    for p in candidates:
        if p.exists():
            return str(p.resolve())
    return None


def _call_audit(source_dir: str, rules: Optional[str] = None) -> Optional[Dict]:
    """Call daudit.exe --mode=audit"""
    daudit = _find_daudit()
    if not daudit:
        return None
    
    cmd = [daudit, "--mode=audit", "--source-dir", source_dir]
    if rules:
        cmd.extend(["--rules", rules])
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=300,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        if result.returncode in (0, 1) and result.stdout.strip():
            return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError) as e:
        logger.error("Audit failed: %s", e)
    
    return None


async def run_audit(arguments: Dict[str, Any]) -> CallToolResult:
    """
    Execute code audit
    
    Parameters:
    - source_dir: source directory (required)
    - rules: rule set, e.g. "P0" / "P0,P1" / "C001,R001" (optional, default P0)
    - severity: minimum severity "suggestion" | "warning" | "critical" (optional, default suggestion)
    - output_format: "report" | "json" (optional, default report)
    """
    source_dir = arguments.get("source_dir", "")
    rules = arguments.get("rules", "P0")
    severity = arguments.get("severity", "suggestion")
    output_format = arguments.get("output_format", "report")
    
    if not source_dir:
        return CallToolResult(
            content=[TextContent(text="The source_dir parameter is required")],
            isError=True,
        )
    
    # Call AST engine
    result = _call_audit(source_dir, rules)
    if not result:
        return CallToolResult(
            content=[TextContent(text="Audit execution failed; please check whether daudit.exe is available")],
            isError=True,
        )
    
    if output_format == "json":
        return CallToolResult(content=[TextContent(text=json.dumps(result, indent=2, ensure_ascii=False))])
    
    # Format as readable report
    return CallToolResult(content=[TextContent(text=_format_audit_report(result, severity))])


def _format_audit_report(result: Dict, min_severity: str) -> str:
    """Format audit results as a Markdown report"""
    summary = result.get("audit_summary", {})
    violations = result.get("violations", [])
    
    severity_level = {"suggestion": 0, "warning": 1, "critical": 2}
    min_level = severity_level.get(min_severity, 0)
    
    report = []
    report.append("# Code Audit Report")
    report.append("")
    report.append(f"**Scanned directory**: {summary.get('source_dir', 'N/A')}")
    report.append(f"**File count**: {summary.get('total_files', 0)}")
    report.append(f"**Total violations**: {summary.get('total_violations', 0)}")
    report.append(f"**Scan duration**: {summary.get('scan_time_ms', 0)}ms")
    report.append("")
    
    # Group by severity
    groups = {"critical": [], "warning": [], "suggestion": []}
    for v in violations:
        lv = severity_level.get(v.get("severity", "suggestion"), 0)
        if lv >= min_level:
            groups[v.get("severity", "suggestion")].append(v)
    
    for severity_label in ["critical", "warning", "suggestion"]:
        items = groups[severity_label]
        if not items:
            continue
        label_map = {"critical": "🔴 Critical", "warning": "🟡 General", "suggestion": "🔵 Suggestion"}
        report.append(f"## {label_map[severity_label]} ({len(items)} items)")
        report.append("")
        
        for v in items:
            report.append(f"### [{v['rule_id']}] {v['rule_name']}")
            report.append(f"- **File**: {v['file']}:{v['line']}")
            report.append(f"- **Description**: {v['message']}")
            if v.get('code_snippet'):
                report.append(f"- **Code**:")
                report.append(f"  ```pascal")
                report.append(f"  {v['code_snippet']}")
                report.append(f"  ```")
            if not v.get('is_ai_needed', True):
                report.append(f"- **Fix example**:")
                report.append(f"  ```pascal")
                report.append(f"  {v.get('fix_example', '')}")
                report.append(f"  ```")
            report.append("")
    
    return "\n".join(report)
```

### 6.3 Server Registration

File: `src/server.py` (append)

```python
from src.tools.audit import run_audit

# Register in list_tools() as the project tool (merged in 2026.05):
tools.append(Tool(
    name="project",
    description="Project lifecycle management: compile/configure/audit",
    inputSchema={
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["compile", "audit", "ast", "runtime", ...]},
            "project_path": {"type": "string", "description": "Project file path"},
        },
        "additionalProperties": True,
        "required": ["action"],
    },
))

# Dispatch in call_tool():
# delphi_project(action="audit", ...) routes to run_audit(arguments)
```

> **Note**: After the 2026.05 refactor, `run_audit`, `compile_project`, and `dproj_tool` have been merged into the `project` tool,
> switching functions via the action parameter. See `tool_help("project")` for details.

---

## 7. Implementation Roadmap

### Phase 0 — Basic Capabilities (1-2 weeks)

Goal: AST engine can run end-to-end and replace the current regex parser

```
[ ] Lexer + Parser basic skeleton
[ ] Support parsing class/record/interface/function/procedure/const/enum
[ ] --mode ast single-file/batch mode
[ ] --mode audit audit mode
[ ] Python integration: _parse_delphi_file_static dual channel (AST + fallback)
[ ] 6 P0 audit rules: C001, C002, Q003, Q001, R001, D004
```

### Phase 1 — Scope + Semantics (2-3 weeks)

Goal: entity ownership, inheritance chains, basic type binding

```
[ ] Scope resolution: each entity knows its parent_scope
[ ] Inheritance chain resolution: class → all ancestor classes
[ ] Basic type binding: TMyVar: TStringList → type_ref
[ ] --mode=audit full-project mode
[ ] Implement all 21 P0 rules
```

### Phase 2 — Complete Audit (2-3 weeks)

Goal: audit engine can be put into production

```
[ ] Implement 15 P1 rules
[ ] Cross-file type registry (class helper conflicts, enum references)
[ ] Reference graph (entity_refs table)
[ ] AI Agent audit report formatting (run_audit MCP tool)
[ ] Incremental audit (git diff mode)
```

### Phase 3 — Graph + Advanced (continuous iteration)

```
[ ] Implement 9 P2 rules
[ ] Code clone detection
[ ] Impact scope analysis
[ ] Audit result history tracking (audit_results table comparison)
```

---

## Appendix: `CODING_RULES.mdc` Audit Checklist Mapping

The following is the complete mapping from the CODING_RULES.mdc audit checklist to AST rule IDs, used to track coverage:

| CODING_RULES Check Item | AST Rule ID | Coverage |
|--------------------|------------|--------|
| Naming conventions | Q009 (P2) | Partial coverage |
| Exception patterns | — (AI only) | 0% |
| OleVariant vs Variant | D008 (P1) | 100% |
| Platform compatibility | — | 0% (cannot automate) |
| Event release (multithreading) | C005 (P1) | Partial coverage |
| All paths | S002 (P0) | Partial coverage (function return values) |
| Boundary conditions | — (AI only) | 0% |
| Input validation | — (AI only) | 0% |
| **Resource release paths** | **R001-R004 (P0)** | **100%** |
| **Concurrency safety** | **C007 (P1)** | **Partial coverage (thread→VCL)** |
| **Function return values** | **S002 (P0)** | **100%** |
| const/out/in parameters | S003 (P0) | 100% |
| Initialization/finalization sections | D009 (P2) | Partial coverage |
| **Create/Free pairing** | **R001 (P0)** | **100%** |
| try/finally | R005 (P1) | 100% |
| Files/handles | R002 (P0) | 100% |
| Database connections | R006 (P1) | 100% |
| GDI/system resources | R002 (P0) | 100% |
| Interface references | R007 (P2) | Partial coverage |
| **TObjectList.OwnsObjects** | **R003 (P0)** | **100%** |
| **String concatenation** | **D001 (P0)** | **100%** |
| published section | D006 (P1) | 100% |
| **RTTI** | **P002 (P1)** | **Partial coverage (high-frequency call detection)** |
| **Enum case** | **D003 (P0)** | **100%** |
| Class Helper conflicts | D005 (P1) | 100% |
| **Empty except** | **C002 (P0)** | **100%** |
| **Type conversion safety** | **C003 (P0)** | **100%** |
| Event release | C005 (P1) | 100% |
| **Anonymous method capture** | **C006 (P1)** | **100%** |
| **Thread accessing VCL** | **C007 (P1)** | **100%** |
| **with statement** | **C001 (P0)** | **100%** |
| **Function/method size** | **Q001 (P0)** | **100%** |
| **Cyclomatic complexity** | **Q002 (P0)** | **100%** |
| **Magic numbers** | **Q003 (P0)** | **100%** |
| Code duplication | Q008 (P2) | 100% |
| **SQL injection** | **S001 (P0)** | **100%** |
| Hard-coded credentials | S004 (P1) | 100% |
| Internationalization | S005 (P1) | Partial coverage |
| **Memory allocation inside loop** | **D002 (P0)** | **100%** |
| **String operations** | **D001 (P0)** | **100%** |

**Bold** = high priority (P0/P1); approximately 35 items in total can be automated, covering about 70% of CODING_RULES check items.

---

> This document is the technical specification for AST engine development.
> Subsequent development should start here: **Phase 0's AST parser core + 6 P0 rules for first validation**.