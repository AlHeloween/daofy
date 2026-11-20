<!-- @when: Before writing Delphi code, confirm coding/naming/formatting conventions -->
<!-- @chain: before=delphi-file-rules.md, after=workflow.md -->

## ③ Writing Delphi Code

**Blocker entry point**: When encountering an error, being unsure of the solution, or repeatedly trying the same solution → first check ⑩ Pre-flight self-check.

### File Encoding (required before modification)
- Confirm the file encoding before modification to avoid garbled Chinese
- Delphi files must be read/written/searched/regex-matched+replaced with `delphi_file`; do not use built-in `Read/Edit/Write/grep`
- ⭐ Prefer `delphi_file(action="read", file_path=...)` (auto-detects encoding/BOM/GBK)
- Preserve the original encoding when writing back; use `utf-8-sig` for new files (UTF-8 with BOM, eliminates W1057 warnings)
- Preserve BOM for files that contain BOM

### Automatic Backup
- `delphi_file(action="write", backup=True)` automatically backs up to `__history/` by default
- ❌ Do not directly use Agent built-in Read/Edit/Write/grep, shell/Python to modify/search `.pas/.dfm/.dproj/.dpk/.dpr/.inc/.fmx/.groupproj`
- Manual operations:
  ```python
  delphi_file(action="backup", file_path="src/Unit1.pas")                                # Manual backup
  delphi_file(action="backup", backup_action="list", file_path="src/Unit1.pas")          # List versions
  delphi_file(action="backup", backup_action="restore", file_path="src/Unit1.pas", version=3)
  ```

### Naming Rules
| Category | Convention | Example |
|------|------|------|
| Class/Interface/Exception | T/I/E/P prefix | `TMyClass`, `IMyInterface` |
| Field | F prefix | `FName: string;` |
| Property/Method | UpperCamelCase | `property Name` / `procedure CalculateTotal` |
| Event | On→Form suffix | `Form1Create` |
| Parameter | A prefix | `procedure SetName(AName: string);` |
| Enum | Type prefix abbreviation | `taLeft, taRight, taCenter` |
| Constant | ALL CAPS | `MAX_BUFFER_SIZE` |

### Formatting
- Indent 2 spaces, line width ≤120
- `begin` on its own line; spaces after operators/commas, none inside parentheses
- `uses` grouped + group-end comments + alphabetical within groups

### Generics
- Descriptive parameter names `TKey, TValue`; one constraint per line in `where`
- Use a type alias for nesting ≥3 levels: `type TStringArrayList = TArray<TList<string>>`

### Operator Overloading
- Define only for records; semantics must be intuitive
- When defining `Implicit`/`Explicit`, also provide named conversion methods

### Async and Multithreading
- UI control access must be synchronized on the main thread; lock shared resources
- Clean up resources when tasks are canceled/fail; avoid async callbacks directly referencing objects

### Code Organization
- Unit ≤500 lines, single responsibility
- `interface`: uses → types → constants → variables → declarations
- `implementation`: uses → helper functions → interface implementations

### Version Compatibility
- Wrap cross-version differences in conditional compilation and note version numbers
- When using new APIs, provide fallback implementations for older versions

