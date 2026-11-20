# Get Coding Rules — Retrieve Delphi Coding Standards

> Version: v1.1 | Last updated: 2026-07-05

---

## Contents

1. [Overview](#1-overview)
2. [Usage](#2-usage)
3. [Section Index](#3-section-index)
4. [Workflow Integration](#4-workflow-integration)
5. [Troubleshooting](#5-troubleshooting)

---

## 1. Overview

`get_coding_rules` provides on-demand querying of Delphi coding standards. Before writing/modifying any Delphi code, an AI Agent **must first call this tool** to understand the coding standards and ensure the generated code style is consistent with the project.

### Core Rules

> ⚠️ **When you see Delphi files such as `.pas`/`.dfm`/`.dproj`/`.dpk`/`.dpr`/`.inc`/`.res`, you must call this tool first.**
>
> ⚠️ **Before writing/modifying any Delphi code, you must first call `get_coding_rules` to understand the coding standards.**

### Hard Constraints

- None — this tool is a read-only query and does not modify any files

---

## 2. Usage

### Basic Calls

```python
# Get the complete workflow overview + section index (recommended for the first call)
get_coding_rules()

# Get a specified section
get_coding_rules(section="workflow")
get_coding_rules(section="writing")
get_coding_rules(section="review")
get_coding_rules(section="safety")
get_coding_rules(section="ui_layout")
get_coding_rules(section="agent_rules")
```

### Parameter Description

| Parameter | Required | Default | Description |
|------|------|--------|------|
| `project_path` | ❌ | — | Project path. Passing this parameter retrieves project-level custom rules (which take precedence over default rules) |
| `section` | ❌ | — | Section filter. If not passed, returns the workflow overview + index of all sections |
| `source_only` | ❌ | false | Return only rule file contents, without AI interpretation |

---

## 3. Section Index

| Section | Content | Applicable Scenario |
|---------|------|---------|
| workflow | Workflow overview | Read this first when first encountering a project to understand the overall process |
| writing | Delphi code writing rules (naming/formatting/generics) | Must-read before writing/modifying code |
| review / review-guide / review-table | Review code after compilation (including a complete review checklist) | Review after completing code |
| ui_layout / ui_testing | UI layout standards and auditing | Check layout quality after generating or modifying a Delphi form |
| safety | Safety-sensitive operation rules | When involving registry, process, or file operations |
| agent_rules | Agent operation hard rules | Understand AI behavior restrictions |
| compile | Compilation rules and parameter descriptions | Check the meaning of DCC parameters before compiling a project |
| format | Code formatting rules (pasfmt) | Check formatting configuration before formatting |
| cleanup | Cleanup rules | Check cleanup strategy when cleaning up code |
| kb_search | Knowledge base search strategy | Check search priority before using delphi_kb search |
| kb_rebuild | Knowledge base rebuild rules | Check the rebuild process when rebuilding the knowledge base |
| debugging | Complete Delphi debugging methodology (12 subsections) | Check when encountering compilation/runtime errors |
| console-testing | Console testing rules | When using automate_delphi console mode |
| experience | Experience memory usage rules | When saving/searching AI experience |
| maintenance | Maintenance rules | Check maintenance strategy during project maintenance |
| planning | Planning rules | Check planning strategy before starting a new feature |
| human-collab | Human-machine collaboration standards | Check the collaboration process when user intervention is needed |

### Rule Priority

```
Project custom rules > Default rules
```

When `project_path` specifies a concrete project, it first tries to load the custom rule files under that project; if there are no custom rules, it uses the built-in default rules.

---

## 4. Workflow Integration

### Standard Delphi Development Workflow

```
get_coding_rules(section="workflow")          # ① Understand the workflow
    ↓
get_coding_rules(section="writing")           # ② Understand coding standards
    ↓
delphi_kb(query="...")                        # ③ Search API definitions
    ↓
delphi_file(action="read", ...)               # ④ Read source code to confirm modification points
    ↓
delphi_file(action="write", ...)              # ⑤ Write code
    ↓
delphi_file(action="format", ...)             # ⑥ Format
    ↓
delphi_project(action="compile", ...)                # ⑦ Compile and verify
    ↓
get_coding_rules(section="review")            # ⑧ Review code
```

### Quickly Investigate an Existing Project

```python
# First understand the coding standards
get_coding_rules(section="workflow")

# Then understand the code structure
delphi_project(action="ast", base_dir="src")
```

---

## 5. Troubleshooting

| Symptom | Cause | Solution |
|------|------|------|
| Empty result returned | A non-existent section was specified | Omit the section parameter to get the index of all sections |
| Custom rules do not take effect | project_path is incorrect | Confirm the path points to a directory containing `.coding-rules/` |
| Rules are too strict/loose | Default rules do not match the project style | Create custom rules in the project directory to override the default rules |

