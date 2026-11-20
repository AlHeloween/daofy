# delphi_file write(edits=[...]) Batch Write Examples

## Basic Usage

```python
# Create a new file
delphi_file(action="write", file_path="Unit1.pas", edits=[{"start_line": 1, "content": "unit Unit1;\n\ninterface\n\nimplementation\n\nend.\n"}])

# Full replacement
delphi_file(action="write", file_path="Unit1.pas", edits=[{"start_line": 1, "content": "unit ..."}])

# Partial replacement
delphi_file(action="write", file_path="Unit1.pas", edits=[{"start_line": 5, "end_line": 10, "content": "new content"}])

# Multiple replacements (order does not matter; automatically sorted)
delphi_file(action="write", file_path="Unit1.pas", edits=[{"start_line": 10, "end_line": 12, "content": "..."}, {"start_line": 5, "end_line": 7, "content": "..."}])

# Preview mode
delphi_file(action="write", file_path="Unit1.pas", edits=[{"start_line": 5, "end_line": 10, "content": "new content"}], dry_run=True)
```

## Line Number Offset Handling (v2026.07+)

The end of the write return includes an "unchanged" region hint:
```
  [5, 10] → [5, 13] (+3)  replaced login logic
  [20, 25] → [26, 28] (+3)  updated error handling
  Unchanged: [1, 4] unchanged, [14, 150] +3
```

**Just use the lookup table; do not calculate**:
- Which `[start, end]` interval your target line number falls into → add the corresponding offset
- Lines not in any interval → already replaced, cannot be used again
- Safest approach: read after write to refresh line numbers

## Recommended Practices

| Scenario | Approach |
|----------|----------|
| 1-2 changes | `read` → `write(edits=[...])` |
| ≥3 non-contiguous changes | `read` → plan all edits → one write |
| uses changes | Use the `uses` action; do not manually calculate line numbers |
| Replace an entire method | `read` → note line numbers → write |

