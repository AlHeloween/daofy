# AGENTS.md - Agent Coding Guidelines

Daofy — Python 3.10-3.14, Windows, pytest.

## Quick Command Reference

| Action | Command |
|--------|---------|
| Install deps | `pip install -r requirements.txt && pip install -e ".[dev]"` |
| Install file watcher | `pip install daofy-for-delphi[watcher]` (optional, automatic incremental KB) |
| Install embedding | `pip install daofy-for-delphi[embedding]` (optional, semantic search) |
| Run all tests | `pytest` (or `python tests/run_all_tests.py` for the basic set) |
| Run one test | `pytest tests/test_validator.py -v` |
| Lint/type | `mypy src/` |
| Environment | Always set `$env:PYTHONIOENCODING='utf-8'` on Windows |
| Run server | `python src/server.py` |

## Project Structure

```
src/
├── server.py              # MCP entry point
├── plugins/               # Language plugin system (base, registry, delphi/, lazarus/, core/)
├── tools/                 # MCP tool implementations (delphi_file, code_hosting, delphi_project, delphi_kb, ...)
├── services/              # Business logic
│   ├── compiler_service.py, config_manager.py, process_manager.py, args_generator.py
│   ├── automation_service.py     # Delphi GUI/Console automation testing service
│   ├── copyright_service.py      # Software copyright document generation service
│   ├── delphi_edit_guard.py      # Delphi file edit protection (dirty-flag detection)
│   ├── experience_service.py     # AI experience memory service
│   ├── ocr_service.py            # Image analysis service
│   ├── rtti_bridge.py            # Delphi RTTI bridge service
│   └── knowledge_base/           # KB modules (schema, smart_cache, project, thirdparty, scan, embedding, async_task_manager)
├── models/                # Pydantic/dataclass models
└── utils/                 # Utilities (delphi_env, dproj_parser, lpi_parser, validator, logger, parser)
```

## Knowledge base automatic lifecycle

The project knowledge base (`.delphi-kb/`) has the following automatic mechanisms:

| Mechanism | Trigger | Description |
|------|---------|------|
| **Automatic build on start-up** | MCP Server start | Detects the `.dproj` under the CWD and submits a background incremental KB build (without blocking MCP readiness) |
| **Hot-swap rebuild** | Manual rebuild by the user | Builds into a temporary directory `.delphi-kb-tmp-{ts}/`, keeps the old KB queryable during the build, then swaps atomically |
| **File change watching** | The user saves `.pas/.dfm/.dproj` and similar | Requires `pip install daofy-for-delphi[watcher]`; triggers an incremental update after a 3-second debounce |

**File change watching dependency**: the optional `watchdog` package; when it is not installed the feature degrades silently and nothing else is affected.
**Checking server state**: the MCP resource `delphi://health` returns the version, the uptime and the listener state.

## Tool usage rules

### Git operations must go through code_hosting
Every Git operation (status/add/commit/push/clone/push_retry) must go through the `code_hosting` tool; running git commands directly from bash is forbidden. `code_hosting` formats the output consistently and handles asynchronous push retries automatically, which costs fewer tokens than raw bash git.

### Experience library maintenance rules
The `experience` tool de-duplicates automatically (an embedding similarity above 0.85 merges into the existing record instead of adding a new one), but the AI still has to maintain the quality of the experience actively:

0. **Generalize before saving**: before calling `experience(action="save")`, search with `experience(action="search", query=...)` for an abstract experience that already covers the same class of problem. If one exists, merge the current case into it with `action=merge` or `action=update` instead of storing another case-specific record. Example: do not store "redundant output_file after compilation"; merge it into "trim MCP tool interface output", which covers return-value cleanup for any tool.
1. **After finishing a task**: if the problem just solved is closely related to an existing experience but was solved differently, merge the two manually with `action=merge`
2. **Periodic cleanup**: use `action=prune` to list low-value experiences (low hit_count, long untouched), review them, then delete with `action=delete`
3. **Abstract merging**: when several experiences describe the same class of problem (for example "message trimming" across different tools), merge them manually into one abstract experience whose `tags` cover every scenario
4. **Rebuild missing vectors**: if the embedding model is loaded later (it was not loaded on first use), older records have no vector. `search()` triggers `rebuild_embeddings()` automatically when the model is loaded but nothing matches, so no manual call is needed. `experience(action="rebuild_embedding")` also triggers it explicitly.

## Agent coding workflow (in priority order)

### Before editing a Delphi file

> ⚠️ **Tool call rules**: every step below calls the corresponding **MCP tool name**. Each tool name is exactly the name you see in `list_tools()`. If a tool is missing from the list, refresh the MCP connection.

| Step | MCP tool called | Description |
|------|----------------|------|
| ① Environment check | `check_environment(action="check")` | Confirm the compiler is usable |
| ② Coding rules | `get_coding_rules(section="workflow")` | Fetch the coding standard, with `language="delphi"` (default) or `"lazarus"` |
| ③ API search | `delphi_kb(query=...)` | Search API definitions (see `get_coding_rules(section="kb_search")` / section ② of `delphi://coding-rules`) |
| ④ Read the source | `delphi_file(action="read", file_path=...)` | Read the file to confirm the change site |
| ⑤ Write code | `delphi_file(action="write", edits=[...])` | Write the code (automatically backed up to __history) |
| ⑤b Batch write | `delphi_file(action="write", edits=[...])` | Write several places at once (the `edits` order does not matter; automatically backed up to __history) |
| ⑥ Format | `delphi_file(action="format", file_path=...)` | Format the code with pasfmt |
| **⑦ Compile check** | **`delphi_project(action="compile", project_path=...)`** | **Compile a `.dproj`/`.dpr`/`.dpk` project** |
| **⑧ Run check** | **`delphi_project(action="compile", ..., run_verify=True)`** | **Start the exe for 3 seconds after a successful compile and detect a runtime crash** |
| **⑨ Runtime check** | **`delphi_project(action="runtime", base_dir=...)`** | **Scan component class names and detect missing `uses` units** |

Notes on individual steps:

- **⑧ run_verify**: after a successful compile the exe is started for 3 seconds; if the process crashes the check is marked failed (it takes seconds and the process is terminated automatically). When an `exception.log` is detected it is read with `detect_encoding` (the same BOM/encoding detection `delphi_file` uses) and embedded directly in the MCP response, so the AI does not need an extra `delphi_file` call.
- **⑨ runtime check**: scans component class names in .pas/.dfm, matches them against the `src/rules/runtime_registry.json` rule table and detects missing required `uses` units (such as FireDAC.DApt). It is independent of the compile step and works purely at source level.

> The detailed KB search strategy, priority rules, `kb_type` scope and Entity Kind Codes are in `get_coding_rules(section="kb_search")` / section ② of `delphi://coding-rules`.

### Before editing a Lazarus/FPC file

| Step | MCP tool called | Description |
|------|----------------|------|
| ① Coding rules | `get_coding_rules(language="lazarus", section="workflow")` | Fetch the Lazarus coding standard |
| ② Project information | `lazarus_project(action="info", project_path=...)` | Inspect the `.lpi` project structure |
| ③ Read the source | `lazarus_file(action="read", file_path=...)` | Read the file to confirm the change site |
| ④ Write code | `lazarus_file(action="write", edits=[...])` | Write the code (automatically backed up to __history) |
| **⑤ Compile check** | **`lazarus_compile(project_path=".lpi")`** | **Compile the project with lazbuild** |
| ⑥ API lookup | `lazarus_kb(action="search", query=...)` | Search LCL/FPC source definitions |

> Note: Lazarus has none of Delphi's proprietary features (DFM, `uses` management, automation testing), so the related tools (`delphi_file`'s format/grep/uses, `manage_component`, `automate_delphi`) are unavailable in the Lazarus workflow. Use `lazarus_file`'s read/write/backup instead.

## Code Style (Python)

- **Types**: type hints everywhere
- **Import order**: stdlib → third-party → local (each group separated by a blank line, alphabetical inside a group)
- **Naming**: `snake_case` for functions/variables, `PascalCase` for classes, `UPPER_SNAKE` for constants, `_` prefix for private members
- **Documentation**: Google-style docstring, mandatory on public functions
- **Exceptions**: use specific exception types, never `except Exception: pass`
- **Tests**: `test_*.py`, functions prefixed `test_`, pytest fixtures, `unittest.mock` for stubbing

## Agent operating hard rules

> Script execution, string formatting, Python pitfalls and other general rules are in `get_coding_rules(section="agent_rules")` / "Agent operating hard rules" in `delphi://coding-rules`.

### Multiprocess workers
- **No `print()` inside a worker**: under MCP, stdout is the JSON-RPC channel; a worker `print()` breaks the protocol boundary and can push a build from 8s to 172s
- Standard worker pattern:
  ```python
  def worker(args):
      import io, sys
      sys.stdout = sys.stderr = io.StringIO()
      try:
          ...  # actual work
          return result
      except:
          return None  # errors travel back through the return value
  ```

### Database
- **DDL in one place**: every table-creation statement lives in `schema.py`, and each builder calls `create_source_tables()`/`create_document_tables()`
- **One journal mode per database file**: this project uses WAL everywhere (`PRAGMA journal_mode=WAL`); switching the mode needs an exclusive lock, and any other open connection makes it locked
- After changing a table, `grep` the whole project for every INSERT/DELETE/SELECT/ALTER that references the old table or column name

### delphi_file usage rules (details in `delphi://coding-rules`)

The detailed rules for line numbers, dirty-flag protection and the output format when editing Delphi files now live in the MCP Resource `delphi://coding-rules` (built-in source: `src/resources/coding-rules.md`). The AI fetches them like this:

```python
get_coding_rules(section="writing")                     # all writing rules
get_coding_rules(section="delphi_file_write_rule")      # line-number rules
get_coding_rules(section="delphi_file_dirty_flag")      # dirty-flag protection
get_coding_rules(section="delphi_file_output_format")   # output format
get_coding_rules(section="delphi_file_usage_tips")      # usage tips
```

**Key points** (the full rules are in the sections above):
- Line numbers are **1-indexed, closed interval at both ends**, and `write` always uses `edits=[...]`
- A file is marked **dirty** after a write, so `read` or `preview` is required before the next write
- The difference in `[s, e] → [s', e']` in a write response is the **line-number offset**
- ❌ Never read or modify `.pas/.dfm/.dproj/.dpk/.dpr/.inc/.fmx` with the agent's built-in `Read/Edit/Write`, a native edit/write tool, or the IDE's default editor
- ❌ Never write `.pas/.dfm/.dproj/.dpk/.dpr/.inc/.fmx` with `apply_patch`, shell redirection, or PowerShell/Python
- ✅ Delphi files may be read and written only through `delphi_file` or another Delphi tool Daofy has registered; the `delphi_file` description in `list_tools()` is the primary cross-agent routing hint
- ⚠️ `DAOFY_EDIT_GUARD=strict` is only a post-hoc backstop: it relies on the Daofy file watcher to spot external writes and cannot stop a built-in tool from getting to the file first

### Compile verification

See `get_coding_rules(section="compile")` / §⑤ Compile in `delphi://coding-rules`:

## Source code audit

### Audit triggers
When the user asks for any of the following, the agent must run the source audit workflow:

| Trigger words | Description |
|--------|------|
| "audit code", "review code", "code review", "audit" | Full audit |
| "security check", "vulnerability scan", "security risk", "security review" | Security-focused audit |
| "performance analysis", "performance audit", "where is it slow", "performance" | Performance-focused audit |
| "resource leak", "memory leak", "handle leak", "resource leak" | Resource management audit |

### Audit workflow

```
① Determine the audit target
   ├─ Delphi code (.pas/.dproj/.dpk) → get_coding_rules(section="review")
   └─ Python project (this MCP Server) → check each item against the Python audit requirements below
② Determine the audit scope (whole project / named files / new code)
③ Search the relevant API definitions and assess their usage (delphi_kb for Delphi, grep/LSP for Python)
④ **Prefer delphi_project(audit/ast)** (degrade to guidance when daudit is unavailable)
   → Use `mode="ast"` (⭐ recommended, `daudit --mode skeleton --compact`) for a quick view of the code structure
   → Use `mode="audit"` when a deep rule check is needed (runs 50+ static-analysis rules)
   → The AI interprets the results, discards false positives and produces repair suggestions
   → Add manual checks (items marked `is_ai_needed=true` by `delphi_project(action="audit")`)
⑤ delphi_project(action="compile") / pytest verification (when code was modified)
⑥ Produce the audit report
```

### Delphi audit

When auditing Delphi code, take the check items directly from the "Review" section of `get_coding_rules(section="review")` / `delphi://coding-rules`:

> **Source of the check items**: `get_coding_rules(section="review")` returns the complete Delphi review table
> (consistency, completeness, resource leaks, Delphi-specific issues, common error patterns, code quality, data conversion, security, performance).

### Python project audit (this MCP Server)

When auditing this MCP Server project (Python code), check each item in the categories below:

#### 1. Security audit
| # | Check item | Description |
|---|--------|------|
| 1.1 | Command/shell injection | `subprocess`/`Popen`/`os.system` arguments built from user input → must pass a list `["cmd", arg]`, never `shell=True` with interpolation |
| 1.2 | Path traversal | A user-supplied path used for file operations without `resolve()`/`abspath()` validation → confine it to permitted directories |
| 1.3 | Registry safety | `winreg` reads and writes touch only the Embarcadero BDS paths under HKLM/HKCU, never critical system locations |
| 1.4 | Sensitive information leakage | Keys or passwords in configuration files such as `compilers.json` → use environment variables; never log a token or a password |
| 1.5 | Temporary file safety | Temporary files created through `tempfile` use `NamedTemporaryFile(delete=True)` to avoid a race |
| 1.6 | Pickle deserialization | `pickle.loads` from an untrusted source is forbidden → use JSON instead |

#### 2. MCP protocol and tool audit
| # | Check item | Description |
|---|--------|------|
| 2.1 | Tool registration consistency | `list_tools()` and `call_tool()` must stay in sync — every tool handled in `call_tool` must be declared in `list_tools` |
| 2.2 | Parameter validation | Tool inputs are validated up front, and a missing required parameter returns a clear error message |
| 2.3 | Exception safety | Every exception inside a tool is caught at the top-level `call_tool` and returned as `CallToolResult(isError=True)`; a traceback is never leaked to the MCP client |
| 2.4 | Uniform return format | Every tool finally returns `CallToolResult(content=[TextContent(...)], isError=...)` and never a bare dict |
| 2.5 | Timeout control | Long operations such as compilation take a `timeout` parameter so the MCP channel (about 60s) cannot time out |
| 2.6 | Subprocess channel protection | When a worker's stdout is already piped as the JSON-RPC channel, `print()` is forbidden; use `sys.stderr` or logging |

#### 3. Concurrency and process audit
| # | Check item | Description |
|---|--------|------|
| 3.1 | Worker print ban | No `print()` inside a `multiprocessing` worker; under MCP stdout is the channel and a print breaks the protocol boundary |
| 3.2 | Subprocess exit cleanup | After `Popen`/`Process`/`ProcessPoolExecutor`, make sure the resource is released on exit (`terminate()`/`join()`/`cancel()`) |
| 3.3 | Race conditions | Shared variables (`_pkb_cache` and similar) are lock-protected with `threading.Lock`, not touched through a bare `global` |
| 3.4 | Cross-platform compatibility | Under Windows `spawn` a child re-imports the module → import lazily under an `if __name__ != '__mp_main__'` guard |
| 3.5 | Long-poll timeout | Compile-status polling stays under 30 seconds; after that it switches to short polling so the MCP request channel is never blocked |

#### 4. Resource management audit
| # | Check item | Description |
|---|--------|------|
| 4.1 | Database connection leaks | SQLite connections are closed with `with` or `try...finally`; watch out for an exclusive lock when `use_wal=False` |
| 4.2 | File handle leaks | `open()` is used inside a `with` block; a manual `f.open()` needs a matching `f.close()` |
| 4.3 | Temporary file cleanup | Temporary `.res`/`.dcu` files created during a build are cleaned up at the end |
| 4.4 | Cache cleanup | `_pkb_cache` is cleared by `_cleanup_resources()` on shutdown, which calls `close()` on every KB instance |
| 4.5 | Leftover processes | A subprocess that times out is `kill()`ed, not just `wait()`ed, to avoid zombies |

#### 5. Error handling audit
| # | Check item | Description |
|---|--------|------|
| 5.1 | Empty except | `except: pass` / `except Exception: pass` — silent swallowing is forbidden, log it |
| 5.2 | Over-broad exceptions | Use specific exception types rather than a bare `except:`, and distinguish IOError/ValueError/KeyError |
| 5.3 | Log completeness | Record an exception in an `except` block with `logger.error(msg, exc_info=True)` so the stack comes with it |
| 5.4 | Missing finally | After acquiring a resource (file/DB/lock) always use `try...finally` to guarantee release |
| 5.5 | External call resilience | Exceptions from a compiler or an external tool are degraded gracefully; an external failure never crashes the MCP Server |

#### 6. Code quality audit
| # | Check item | Description |
|---|--------|------|
| 6.1 | Type hints | Every function/method carries complete type annotations, return type included |
| 6.2 | Import order | stdlib → third-party → local, three groups separated by blank lines, alphabetical inside a group |
| 6.3 | Naming | `snake_case` for functions/variables/methods, `PascalCase` for classes, `UPPER_SNAKE` for constants, `_` prefix for private members |
| 6.4 | Docstrings | Public functions need a Google-style docstring describing Args/Returns/Raises |
| 6.5 | Cyclomatic complexity | A function stays under 50 lines with at most 4 nesting levels; split it when it grows |
| 6.6 | Async patterns | Avoid `time.sleep()` inside an async function; use `asyncio.sleep()` and never block the event loop synchronously |
| 6.7 | String formatting | No f-string with nested dictionary keys (`f'{d["key"]}'`, quote conflict); use `.format()` or a local variable |
| 6.8 | Function-local imports | `from X import Y` inside a function is forbidden (it makes Y a local for the whole function scope); imports go at module top |

#### 7. Configuration and environment audit
| # | Check item | Description |
|---|--------|------|
| 7.1 | Compiler paths | Paths in `compilers.json` are validated at service start-up, and an invalid path degrades gracefully |
| 7.2 | Registry fallback | A failed registry read falls back to the default path list automatically |
| 7.3 | Encoding setup | On Windows, `PYTHONIOENCODING=utf-8` / `PYTHONUTF8=1` must be set |
| 7.4 | Dependency completeness | A new dependency updates both `requirements.txt` and `pyproject.toml` |

### Audit report template

```
## Source code audit report

**Project**: <project name>
**Audit scope**: <whole project / file list>
**Audit date**: <date>

---

### Overview

When the audit scope is Delphi code:

| Category | Findings | Critical | Major | Minor |
|----------|--------|------|------|------|
| Security | N | N | N | N |
| Resource management | N | N | N | N |
| Error handling | N | N | N | N |
| Delphi-specific | N | N | N | N |
| Consistency | N | N | N | N |
| **Total** | **N** | **N** | **N** | **N** |

When the audit scope is the Python MCP Server:

| Category | Findings | Critical | Major | Minor |
|----------|--------|------|------|------|
| Security | N | N | N | N |
| MCP protocol and tools | N | N | N | N |
| Concurrency and processes | N | N | N | N |
| Resource management | N | N | N | N |
| Error handling | N | N | N | N |
| Code quality | N | N | N | N |
| Configuration and environment | N | N | N | N |
| **Total** | **N** | **N** | **N** | **N** |

### Critical issues

1. **[Critical] <file:line>: <issue description>**
   - **Issue**: ...
   - **Risk**: ...
   - **Suggested fix**: ...
   - **Code example**:
     ```pascal
     // current code
     ...
     // after the fix
     ...
     ```

### Major issues

...

### Suggestions

...

### Audit conclusion

<overall assessment: code-quality rating, main risk points, items to fix first>
```

### Audit tooling

```
get_coding_rules(section="review")               → fetch the Delphi review standard
delphi_project(action="ast", base_dir="src")           → ⭐ code skeleton extraction (daudit --mode skeleton --compact, the cheapest in tokens)
delphi_project(action="audit", base_dir=".", rules="P0") → deep static-analysis rule check (optional)
delphi_file(action="read", file_path="unit.pas")   → view Delphi source
delphi_kb(query="TThread", search_type="reference") → look up Delphi API usage
delphi_project(action="compile", project_path="proj.dproj") → compile after a Delphi audit
--- Python project audits use these tools ---
grep / ast_grep_search                      → search Python code for patterns
lsp_diagnostics / lsp_symbols               → type checking and symbol analysis
pytest                                      → run the tests after the audit
```

## Release packaging

### Creating a release package

```powershell
$env:PYTHONIOENCODING='utf-8'
# Required: let PowerShell decode native command output correctly, otherwise Chinese paths are garbled or lost (see "Chinese path pitfall" below)
[Console]::OutputEncoding=[System.Text.Encoding]::UTF8
$OutputEncoding=[System.Text.Encoding]::UTF8

$src="C:\User\delphi-complier-mcp-server"   # repository root (note: must be defined before $7z)
$7z="$src\tools\7z\7z.exe"
$ver="v2026.09.16"  # replace with the current version
$out="$src\releases\daofy-for-delphi-$ver"

# Clean the previous artifacts (7z a appends/updates an existing archive, so leftovers from the previous version survive)
Remove-Item "$src\releases\daofy-for-delphi-$ver.tar","$src\releases\daofy-for-delphi-$ver.7z","$src\releases\daofy-for-delphi-$ver.zip" -Force -ErrorAction SilentlyContinue
if (Test-Path $out) { Remove-Item $out -Recurse -Force }

# Take the files from the git index (which excludes everything .gitignore covers)
# core.quotePath=false is essential: otherwise non-ASCII (Chinese) paths are printed as octal escapes and the copy fails
$sel = @(git -c core.quotePath=false ls-files | Where-Object {
    $_ -notmatch '^\.arts/' -and
    $_ -notmatch '^\.coverage$' -and
    $_ -notmatch '^config/history\.json$' -and
    $_ -notmatch '^src/config/compilers\.json$' -and
    $_ -notmatch '^\.gitignore$' -and
    $_ -notmatch '^tools/daudit/'
})
$copied = 0; $failed = @()
$sel | ForEach-Object {
    $target = Join-Path $out $_
    $dir = Split-Path $target -Parent
    if (!(Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    try { Copy-Item -LiteralPath (Join-Path $src $_) -Destination $target -Force -ErrorAction Stop; $copied++ }
    catch { $failed += $_ }
}
Write-Host "copied=$copied failed=$($failed.Count) expected=$($sel.Count)"
if ($failed.Count -gt 0) { $failed | ForEach-Object { Write-Host "  FAIL: $_" }; throw "release file copy failed" }

# Pack the three formats
& $7z a -ttar "$src\releases\daofy-for-delphi-$ver.tar" "$out\*" -bb0 -bsp0
& $7z a -t7z "$src\releases\daofy-for-delphi-$ver.7z" "$src\releases\daofy-for-delphi-$ver.tar" -mx=9 -m0=LZMA2 -bb0 -bsp0
& $7z a -tzip "$src\releases\daofy-for-delphi-$ver.zip" "$out\*" -mx=9 -bb0 -bsp0
Remove-Item $out -Recurse -Force

# Check: the number of files inside the package must equal $sel.Count, otherwise a file was silently skipped
$cnt = (& $7z l -slt "$src\releases\daofy-for-delphi-$ver.zip" | Select-String '^Attributes = ' | Where-Object { $_ -notmatch 'D' }).Count
Write-Host "zip files=$cnt expected=$($sel.Count)"
```

**Chinese path pitfall**: `git ls-files` defaults to `core.quotePath=true`, which prints non-ASCII (Chinese) paths as octal escapes (such as `tests/\345\206\222...`). PowerShell then treats that literally → `Test-Path`/`Copy-Item` reports "illegal characters in path" and **silently skips** the file (the script does not fail, yet the package is missing files). In the v2026.09.16 packaging run, 435 files produced only 429 entries, losing six Chinese-named files including `tests/冒烟测试/*.json` and `tests/scripts/新建客户-*.json`. The script therefore must: ① set `[Console]::OutputEncoding`/`$OutputEncoding` to UTF-8; ② use `git -c core.quotePath=false`; ③ use `Copy-Item -LiteralPath`; ④ count `copied`/`failed` and `throw` on failure; ⑤ re-check with `zip files=N expected=N` after packing.

**Included automatically**: tool files such as `tools/pasfmt/cli/pasfmt.exe` are picked up by `git ls-files` (they are already under version control) and need no manual step.

**Exclusions**: the files under `tools/daudit/` are a commercial, paid part and are not included in the release package (note that `tools/stacktrace/` is **not** excluded and must ship with the package).

### Release steps

1. Run the packaging script → it produces `.7z` / `.tar` / `.zip`
2. Create the GitHub Release:
   ```bash
   gh release create v2026.05.14 --title "v2026.05.14" --notes-file release_notes.md
   ```
3. Attach the package files to the Release (through the Web UI or `gh release upload`)
4. Publish to PyPI (see below)

### Publishing to PyPI

The PyPI token is stored in `config/pypi.json` (already excluded by `.gitignore`).

```powershell
$env:PYTHONIOENCODING='utf-8'

# 1. Build the package
python -m build

# 2. Upload to PyPI (UTF-8 is required to avoid the Windows GBK problem)
$token = (Get-Content config/pypi.json | ConvertFrom-Json).token
twine upload dist/* -u __token__ -p $token --disable-progress-bar
```

**Notes**:
- `$env:PYTHONIOENCODING='utf-8'` is mandatory; otherwise twine's rich progress bar raises UnicodeEncodeError in a Windows GBK terminal
- `--disable-progress-bar` avoids rich terminal rendering problems
- Token format: `pypi-AgEIcHlwaS5vcmcC...` (the full token is in `config/pypi.json`)

## Refactoring checklist

```
[ ] DDL unified in the schema module
[ ] grep every CRUD reference to the old table/column name
[ ] verify no external caller remains after removing a deprecated method
[ ] check function-local import scope problems
[ ] one journal mode for the same database
[ ] test a zero value with `is not None`
[ ] record metadata (time + duration) at the end of a build
[ ] force a rebuild with DELETE FROM rather than row by row
[ ] full test run + KB build verification
[ ] MCP tool timeout documentation is accurate
[ ] no print() in a multiprocess worker
```
