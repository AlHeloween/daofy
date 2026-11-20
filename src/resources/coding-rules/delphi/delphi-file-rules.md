<!-- @when: When using delphi_file to write or modify Delphi files -->
<!-- @chain: before=format.md, after=writing.md -->

## delphi_file Writing Rules

**Tool routing rule**: Delphi files must be read/written/searched and regex-matched + replaced with `delphi_file`; do not use built-in `Read/Edit/Write/grep`.

**Line numbers are uniformly 1-indexed, closed on both ends.** write uniformly uses `edits=[...]`.

### DFM Chinese Content (Important)

Chinese content in DFM files (property values such as Caption, Text, Hint) **should be written directly as original text and does not need to be escaped**.

```python
# ✅ Correct: write Chinese directly
delphi_file(action="write", file_path="MainForm.dfm", edits=[
    {"start_line": 5, "end_line": 5, "new_text": '    Caption = #20013#25991#26631#39064'}
])

# ✅ Simpler: use a Chinese string directly (delphi_file handles encoding automatically)
delphi_file(action="write", file_path="MainForm.dfm", edits=[
    {"start_line": 5, "end_line": 5, "new_text": '    Caption = "中文标题"'}
])

# ❌ Wrong: do not manually escape Unicode
delphi_file(action="write", file_path="MainForm.dfm", edits=[
    {"start_line": 5, "end_line": 5, "new_text": '    Caption = \u4e2d\u6587\u6807\u9898'}
])
```

**Principle**: `delphi_file` automatically handles encoding (GBK/UTF-8/BOM) when reading and writing; Chinese content is written as original text, and the tool handles encoding conversion internally.

📋 Example: examples/delphi-file/write-edits.md — write(edits=[...]) batch write example (create/full/partial/multiple sections/preview)

### Dirty Flag Protection (v2026.06.12+)

📋 Example: examples/delphi-file/dirty-flag.md — dirty flag protection example (read/preview flow before and after writing)