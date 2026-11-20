---
source: coding-rules
section: kb_search
---

## ② KB Search (required before coding)

Before coding, check API definitions first to avoid modifying Delphi code from memory.

### Recommended Order

| Priority | Query | Use Case |
|---|---|---|
| 1 | `delphi_kb(query="TStringList")` | Known class name, function name, or constant name |
| 2 | `delphi_kb(query="TfrmMain", kb_type="project", project_path="Project.dproj")` | Search current project source |
| 3 | `delphi_kb(query="E2003", kb_type="document", search_type="semantic")` | Query compiler errors or official documentation |
| 4 | `delphi_file(action="read", search_type="function", function_name="...")` | Read source after locating project symbols |

### Constraints

- When unsure about Delphi APIs, VCL/FMX/RTL types, or third-party component usage, query the KB before changing code.
- When searching project source, prefer explicitly passing `project_path` to avoid searching the wrong project due to CWD changes.
- If search results are insufficient, narrow the keywords to class names, function names, error codes, or unit names.