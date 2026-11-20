<!-- Daofy persistent Rule (installed into each MCP client's rules directory).
     This file is the authoritative persistent copy of the "mandatory routing": all Delphi-related tasks must be routed to Daofy tools.
     Layering (to avoid duplicate injection):
       - Protocol-level fallback: MCP initialize.instructions (covers all clients that honor instructions)
       - Detailed usage: daofy skill (loaded on demand, does not contain this constraint)
       - In-depth standards: get_coding_rules(section=...) (loaded on demand)
     This file only holds the routing constraints that "must always be present", not detailed usage. -->
# Daofy Delphi Mandatory Routing Rule (all Delphi tasks must go through Daofy; no bare shell / IDE built-ins)

**Any Delphi-related operation must be completed through the tools provided by the currently connected Daofy MCP Server.**
**It is prohibited to use shell (PowerShell)/Python to directly execute Delphi commands such as dcc32/dcc64/msbuild/bcc,**
and it is also prohibited to use the Agent / IDE built-in Read / Edit / Write / grep to directly read or write Delphi files.

Applicable extensions:
`.pas` `.dpr` `.dpk` `.dfm` `.fmx` `.inc` `.dproj` `.groupproj`

## Task → Daofy tool mapping (route by this, do not guess)
| Task | Must use | Prohibited |
| --- | --- | --- |
| Read / write / search / regex replace Delphi files | `daofy.delphi_file(action=read/write/replace/insert/delete/grep)` | built-in Read/Edit/Write/grep, shell cat/sed |
| **Detect compiler / DCC environment** (e.g. where dcc32/dcc64 are, whether they exist) | `daofy.check_environment(action="detect")` (call `check` before the first compile) | shell probes such as `where dcc32`, `dcc64 --version` |
| **Compile / build Delphi projects** | `daofy.delphi_project(action="compile"/"compile_file"/"dry_run")` | manual `dcc32` / `msbuild` |
| Project configuration view / audit / AST / layout | `daofy.delphi_project(action=info/audit/ast/layout/runtime)` | — |
| Look up API / class / function / project symbols | `daofy.delphi_kb` | — |
| Coding / pre-compile standards | `daofy.get_coding_rules(section=...)` | — |
| All Git operations | `daofy.code_hosting` | running `git ...` directly in the shell |

## Why
- **File read/write**: Delphi source commonly uses UTF-8 BOM / GBK / ANSI; default tools rewrite it as BOM-less UTF-8 or the system ANSI,
  causing BOM loss, garbled Chinese text, and rewritten line endings. `delphi_file` automatically preserves the original encoding/BOM and provides
  backup, edit guard, and other protections.
- **Environment/compilation**: Delphi compiler paths, versions, and SDK dependencies are uniformly detected and cached by Daofy; running `dcc32/msbuild` bare
  easily fails or builds the wrong target due to inconsistent PATH, registry, platform (win32/win64), and conditional compilation symbols.

## Exceptions
- Non-Delphi files (Python / Markdown / configuration / test scripts) can be handled through the normal flow.
- Pure information queries (e.g. viewing Daofy tool parameters) can use `daofy.tool_help(tool_name=...)`; not covered by this restriction.

<!-- daofy-managed-rule: true -->

