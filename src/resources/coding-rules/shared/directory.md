<!-- @when: Before work starts, to learn the directory conventions, or when files must be created/cleaned up -->
<!-- @chain: after=workflow.md, before=agent-rules.md -->

## 📁 Directory Constraints

While working, the AI Agent must follow the directory conventions below, so that later cleanup and maintenance stay easy.

### Standard Directory Structure

```
project/
├── src/                    ← Source code (Python/Delphi)
├── tests/                  ← Test cases (test_*.py, run_*.py)
├── docs/                   ← Documentation (user manuals, design documents)
├── scripts/                ← Helper scripts (build/deploy/tool scripts)
├── tools/                  ← Tool programs (pasfmt/7z/daudit etc.)
├── data/                   ← Knowledge base data (generated at runtime, gitignore)
├── logs/                   ← Log files (generated at runtime, gitignore)
├── config/                 ← Configuration files (compilers.json etc.)
├── releases/               ← Release packages (gitignore)
├── benchmarks/             ← Performance benchmarks (gitignore)
└── .tmp/                   ← Temporary working directory (gitignore)
```

### Directory Purpose Constraints

| Directory | Purpose | Cleanup policy | gitignore |
|------|------|----------|-----------|
| `tests/` | Formal test cases (test_*.py) | Maintained with the project | ❌ Version controlled |
| `tests/tmp_*` | Temporary test scripts | **Delete after use** | ✅ `tmp_*.py` |
| `.tmp/` | Agent temporary working files | **Clean up when the task ends** | ✅ `.*/` |
| `.pytest-tmp-*/` | pytest temporary directories | **Cleaned up automatically when tests finish** | ✅ `.*/` |
| `docs/` | Formal documentation | Maintained with the project | ❌ Version controlled |
| `docs/todos.md` | Personal notes | Not committed | ✅ |
| `scripts/` | Reusable scripts | Maintained with the project | ❌ Version controlled |
| `_dump_*.py` | One-off debug scripts | **Delete after use** | ✅ `_dump_*.py` |
| `_debug_*.py` | Debug scripts | **Delete after use** | ✅ `_debug_*.py` |
| `logs/` | Runtime logs | **Clean up periodically** | ✅ |
| `data/` | Knowledge base data | Rebuild as needed | ✅ |
| `snapshots/` | UI screenshot snapshots | **Delete after use** | ✅ |
| `__history/` | Delphi file backups | Managed automatically by the IDE | ✅ |
| `Win32/` `Win64/` | Delphi compile output | **Clean up after compiling** | ✅ |

### Naming Conventions

| Type | Naming pattern | Example |
|------|---------|------|
| Formal tests | `test_*.py` | `test_compiler.py` |
| Temporary tests | `tmp_test_*.py` | `tmp_test_new_feature.py` |
| Debug scripts | `_debug_*.py` / `_dump_*.py` | `_dump_ast.py` |
| Temporary output | `tmp_*` / `test_*.png` | `tmp_output.txt` |

### Cleanup Rules

```
Cleanup is mandatory once the task is complete:
1. Temporary files → delete tmp_*, _dump_*, _debug_*
2. Temporary directories → delete .tmp/, .pytest-tmp-*
3. Compile output → delete Win32/, Win64/, *.dcu, *.exe
4. Debug artifacts → delete test_*.png, temp_*.json
```

### ⚠️ Prohibitions

- ❌ Creating temporary files or test scripts under `src/`
- ❌ Scattering temporary scripts in the project root (use `.tmp/` or `scripts/`)
- ❌ Naming temporary files without a prefix (e.g. `test.py` instead of `tmp_test.py`)
- ❌ Leaving `.pytest-tmp-*` directories behind after the task ends

