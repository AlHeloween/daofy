# StackTrace / StackTracer Migration Plan and Feature Comparison

**Status**: P0b migration complete  
**Date**: 2026-07-03  
**Goal**: Unify the runtime diagnostic capabilities of historical `StackTrace.pas` with the current `StackTracer.pas` callgraph capabilities, to avoid reintroducing problems that already existed in historical versions into the Daofy toolchain.

## 1. Version Inventory

| Path | Time | Size | SHA256 Prefix | Role |
|------|------|------|-------------|------|
| `C:\user\daofy-agent\ddebug\.backup_shortnames\src\Common\StackTrace.pas` | 2026-05-26 | 126.7 KB | `A4B51C61127EE748` | Early backup of old large version |
| `tools/daudit/StackTrace.pas` | 2026-05-29 | 127.7 KB | `4178D489B9742E27` | Old large version in Daofy repository |
| `C:\user\daofy-agent\daudit\Diagnostics\StackTrace.pas` | 2026-06-01 | 129.9 KB | `A466ED907B143476` | daudit diagnostic version |
| `C:\user\daofy-agent\common\StackTrace.pas` | 2026-06-09 | 136.0 KB | `91FCEE43E85633FE` | Newer version of common library |
| `C:\user\qlang\Editor\StackTrace.pas` | 2026-06-26 | 141.1 KB | `8B71D80A1E8E36BF` | Latest large-version candidate baseline |
| `C:\user\daofy-agent\daudit2\StackTracer.pas` | 2026-07-03 15:49 | 17.8 KB | `400350319FDB0B01` | Initial callgraph version |
| `tools/stacktrace/StackTracer.pas` | 2026-07-03 22:53 | 23.6 KB | `8A4BFADD77F82A5B` | Current callgraph version |

Conclusions:

- The large `StackTrace.pas` is the runtime diagnostic engine line: exception hook, MAPDATA, tokenization, local variable snapshot, default `exception.log`.
- The small `StackTracer.pas` is the callgraph line: `.map` parsing, `.text` `$E8` direct call scanning, callees/callers queries.
- The current goal is not to choose one of the two, but to take the large-version diagnostic engine as the main line and merge the small-version callgraph into it as one query capability of the diagnostic engine.

## 2. Feature Matrix

| Capability | ddebug early | daofy daudit | daudit Diagnostics | common | qlang Editor | daudit2 StackTracer | Current StackTracer | Migration strategy |
|------|-------------|--------------|--------------------|--------|--------------|---------------------|------------------|----------|
| `TStackTraceManager` | Yes | Yes | Yes | Yes | Yes | No | No | Must restore |
| Exception hook | Yes | Yes | Yes | Yes | Yes | No | No | Audit and migrate in using `qlang Editor` as baseline |
| Capture before VEH expansion | Yes | Yes | Yes | Yes | Yes | No | No | Migrate in, but must retain reentrancy protection |
| Default `exception.log` | Yes | Yes | Yes | Yes | Yes | No | No | Migrate in and standardize UTF-8 output |
| Symbol resolution + line numbers | Yes | Yes | Yes | Yes | Yes | Simplified | Simplified | Unify to prefer tokenized MAPDATA, with external `.map` fallback |
| `TMapDataSerializer` | Yes | Yes | Yes | Yes | Yes | No | No | Must migrate in |
| Tokenized symbol table | Yes | Yes | Yes | Yes | Yes | No | No | Must migrate in, reduce memory |
| Compress/decompress MAPDATA | Yes | Yes | Yes | Yes | Yes | No | No | Must migrate in |
| Embed in EXE resource | Yes | Yes | Yes | Yes | Yes | No | No | Migrate in but do not auto-self-write by default |
| Local variable snapshot | Yes | Yes | Yes | Yes | Yes | No | No | Migrate in in phases, disabled by default |
| Overlay symbol provider | None/weak | Yes | Yes | Yes | Yes | No | No | Keep interface, do not strongly depend on it for now |
| callgraph forward | No | No | No | No | No | Yes | Yes | Merge into new main line |
| callgraph reverse | No | No | No | No | No | No | Yes | Keep current implementation |
| callgraph JSON | No | No | No | No | No | Simplified | Current version more complete | Maintain compatibility |
| `LastError` / `MapLoadError` | No | No | No | No | No | Weak | Yes | Keep and merge into diagnostic state |

## 3. Candidate Baseline Selection

Recommended baseline: `C:\user\qlang\Editor\StackTrace.pas`.

Reasons:

- Latest time, largest size, includes patches after `common`.
- Already shows clearer VEH reentrancy protection than earlier versions: `VEHReentrancyGuard` prevents AV recursion inside handler.
- Logger exceptions are no longer completely silent; some paths write to `OutputDebugString`.
- If source path resolution fails, it writes to `LAstDbg`, which is more auditable than early empty `except`.

Reasons it cannot be directly overwritten:

- The file is still called `unit StackTrace`; early automated callgraph once used `unit StackTracer`, now unified to `uses StackTrace`, and the independent compatibility shell has been deleted.
- Does not include current `GetCallerChain`, `CallChainToJSON(root, direction)`, `LastError`, `MapLoadError`.
- Source path resolution has removed hardcoded `BDS\22.0` / `BDS\23.0` registry version numbers, changed to enumerate `Software\Embarcadero\BDS` subkeys and select the highest available installation; recursive scan logic will continue to be tightened according to Daofy configuration/environment service semantics.
- `EmbedMapData` involves modifying EXE resources, must be explicitly called, and cannot be an automatic behavior upon import.

## 4. Historical Issue List

| Risk | Source evidence | Handling requirement |
|------|----------|----------|
| Empty `except` swallowing errors | Early versions such as `common` have empty handlers in dproj parsing, registry fallback, recursive search | Forbidden to migrate in as-is; all exceptions must at least write to debug diagnostics or status fields |
| Hardcoded registry version | Large version explicitly reads `BDS\22.0`, then falls back to `BDS\23.0` | Already changed to iterate available BDS keys and select highest valid `RootDir` |
| VEH handler reentrancy | Old large version reads EBP chain inside VEH; if it AVs itself may recurse | Must adopt reentrancy protection idea from `qlang Editor`, and add minimal stress test |
| Logger failure silent | Early logger call exceptions are swallowed | Logger exceptions write `OutputDebugString`, and must not affect original exception propagation |
| Local variable stack read risk | `ReadStackVarValue`, EBP offset reads may go out of bounds or read invalid objects | `CaptureVariables` disabled by default; when enabled limit types, size, frame count, and catch read errors |
| EXE self-write risk | `EmbedMapData` / `EmbedFinalize` write EXE resources | Can only be explicitly called; runtime defaults to read-only resources and `.map` |
| Recursive path search overhead | Large-version source file resolution uses `TDirectory.GetFiles(... soAllDirectories)` | Already disabled by default; only enabled when `DAOFY_STACKTRACE_RECURSIVE_SOURCE_LOOKUP=1`; by default prefer dproj search path and known Delphi source path |
| Old version does not contain callgraph | All large `StackTrace.pas` versions do not have `ScanCallGraph` | callgraph is merged in as a new module, not derived from old versions |
| Small version memory inefficiency | Current `StackTracer.pas` stores full string arrays and does linear search | Use tokenized symbol table instead of direct string table, keep compatible facade |
| Insufficient Win64 coverage | Current callgraph mainly validated against Win32 PE/map semantics | Win64 is a separate milestone, not mixed into P0 |

## 5. Naming Decision

The final main unit uses `tools/stacktrace/StackTrace.pas`, with unit name `StackTrace`.

Reasons:

- This is the continuation of the old runtime diagnostic engine; core capabilities are exception stack trace, MAPDATA, symbol resolution, and local variable snapshot. `StackTrace` is closer to the functional boundary than `StackTracer`.
- Existing `run_verify`, documentation, and historical projects have already established the mental model around `uses StackTrace; TStackTraceManager...`; continuing to use this name has the lowest migration cost.
- `StackTracer` is more like a temporary name for the current small callgraph version, not suitable as the final public diagnostic unit.

Compatibility strategy:

- `tools/stacktrace/StackTrace.pas` is the only main implementation, providing both `TStackTraceManager` and `TStackTracer`.
- The temporary thin compatibility shell `tools/stacktrace/StackTracer.pas` has been deleted; callers uniformly use `uses StackTrace`, and continue to use `TStackTracer` / `TCallEdge` from `StackTrace.pas`.
- It is forbidden to add both `StackTrace.pas` from `tools/daudit` and `tools/stacktrace` to the search path of the same Delphi project at the same time, to avoid unit name conflicts.

Subsequent naming migration is not executed in this round. If the unit is renamed in the future, follow Delphi namespaced unit / file name rules and use the `Daofy.xxx.pas` form, e.g. `Daofy.Diagnostics.pas`, `Daofy.StackTrace.pas`, or a finer `Daofy.Diagnostics.StackTrace.pas`. This round does not adopt that solution because it would break the old API and injection chain; after all functions and verification are closed out, do a centralized search-and-replace.

## 6. Target Architecture

Main file `tools/stacktrace/StackTrace.pas` exposes two compatibility layers:

1. `TStackTraceManager`: old large-version main API, responsible for exception hook, MAPDATA, symbol resolution, local variable snapshot.
2. `TStackTracer`: current callgraph facade, continues to provide `GetCallChain`, `GetCallerChain`, `CallChainToJSON`, `LastError`, `MapLoadError`.

Internal structure suggestion:

| Component | Responsibility |
|------|------|
| map parser | Parse Detailed `.map`, generate `TMapSymbol` / `TLineInfo` |
| MAPDATA serializer | Tokenization, delta address, compression, validation, deserialization |
| symbol resolver | Runtime address to function name/source line; prefer MAPDATA resource, then external `.map` |
| exception manager | Install/uninstall Delphi RTL hook and VEH |
| exception logger | Output `exception.log`, stable format, UTF-8 |
| variable snapshot | Optionally capture local variables/parameters, disabled by default |
| callgraph scanner | Build graph based on symbol resolver and `.text` direct call scanning |

## 7. Migration Phases

### P0 - Baseline Merge and Read-Only Diagnostics

Goal: migrate in the old large-version tokenized MAPDATA and exception reporting main trunk, without enabling high-risk writes and local variable reads.

Tasks:

1. Using the `qlang Editor` version as baseline, create `tools/stacktrace/StackTrace.pas`, restore `TStackTraceManager`, `TMapDataSerializer`, exception hook, default logger.
2. P0a first keeps the current `TStackTracer` callgraph implementation unchanged, to avoid overlapping risks of exception diagnostics migration and callgraph behavior rewrite.
3. P0b then merges the `TStackTracer` facade into `StackTrace.pas`, and deletes the independent `tools/stacktrace/StackTracer.pas` compatibility shell.
4. Reconfirm the strategy for enabling hook by default: tool injection scenarios can enable it; whether ordinary references auto-enable needs explicit configuration.
5. `EmbedMapData` is migrated in for now but not called by default.
6. `CaptureVariables` defaults to `False`.

Acceptance:

- A minimal Delphi console program referencing `StackTrace` can generate `exception.log`.
- Log contains exception class, message, at least one symbolized stack frame.
- Current `callgraph` / `callgraph_diff` Python tests continue to pass.
- Existing QLangEditor callgraph actual tests still return callers/callees.

### P1 - MAPDATA Resources and Memory Optimization

Goal: Let production runtime preferentially use embedded compressed tokenized MAPDATA, reducing symbol table memory usage.

Tasks:

1. Restore `Serialize` / `Deserialize` / `Validate` / `DetectVersion` / `Merge` coverage tests.
2. Add MAPDATA file-level fixtures, verify symbols and line numbers are consistent after roundtrip of the same map.
3. `TryLoadMapFromResource` first, external `.map` fallback.
4. Compare memory estimates of direct string table and tokenized table, form regression metric.

Acceptance:

- MAPDATA roundtrip tests pass.
- Failure to load resource will not affect external `.map` fallback.
- Symbol resolution results are consistent with old large-version baseline.

### P2 - Local Variable Snapshot

Goal: Restore old-version local variable/parameter capture, but confine crash risk inside a feature switch that is off by default.

Tasks:

1. Migrate in `LocalVarExtractor`, `ReadFunctionPrologue`, `ComputeVarOffsets`, `ReadStackVarValue`.
2. Add type whitelist and maximum read byte count.
3. Add guards for string, object, pointer reads; on failure return `<read-error>`, do not throw.
4. Add formatting tests for `Params` / `Locals` in exception log.
5. Use manual `SetLocalVarData` metadata and simulated frame buffer to verify Win32/Win64 local variable read chain.
6. daudit/AST extractor integration is deferred as an independent task, not a condition for completion of current StackTrace migration.

Acceptance:

- When `CaptureVariables=False`, local variables are not read.
- When `CaptureVariables=True`, basic integers, booleans, strings can be output; current acceptance uses manual metadata + simulated frame smoke to lock down StackTrace's own chain.
- Deliberately constructing illegal objects/pointers does not cause a second crash, and returns stable `<invalid>` / address formatting output.
- Unknown TypeKind no longer dereferences as pointer, uniformly returns `<unsupported type>`; string reads are limited by `MaxCapturedStringChars`.
- Exception log formatting is controlled at a single point by `TStackTraceManager.FormatExceptionContext`; `CaptureVariables=True` outputs `Params` / `Locals`, `False` hides variables.

### P3 - callgraph Deep Integration

Goal: Turn current callgraph into a formal capability of the diagnostic engine, rather than an independent small tool.

Tasks:

1. callgraph uses `TStackTraceManager`'s symbol table and line table.
2. Keep `GetCallChain`, `GetCallerChain`, `CallChainToJSON` signatures.
3. Add call site line numbers, edge deduplication, indexing, and stable diff comparison.
4. Align with P0/P1 in `docs/callgraph-enhancement-plan.md`.

Acceptance:

- `DaofyAutomation.CallGraph.pas` does not need call-site protocol changes.
- QLangEditor `SaveIfModified callers` and `actNewProjectExecute callees` regressions pass.

### P4 - Compilation/Release Pipeline Replacement

Goal: Daofy's `run_verify` and release packages both use the unified `tools/stacktrace/StackTrace.pas`.

Tasks:

1. `src/tools/compile_project.py` switches from `tools/daudit/StackTrace.pas` to `tools/stacktrace/StackTrace.pas`.
2. Injection code continues to use `uses StackTrace`, initialization API remains `TStackTraceManager`.
3. Documentation's commercial `tools/daudit` wording is updated to the current open-source/built-in path.
4. Release exclusion rules are rechecked to avoid missing diagnostic units.

Acceptance:

- `delphi_project(action="compile", run_verify=True)` can use the new unit to capture startup exceptions.
- Generated package contains necessary `tools/stacktrace` files and does not depend on `tools/daudit`.

## 8. Trade-offs for Historical Implementation

| Module | Trade-off |
|------|------|
| `TMapDataSerializer` | Migrate in. It is the core of memory optimization, but must add roundtrip/validate tests. |
| `TStackTraceManager` hook | Migrate in. Use `qlang Editor` version as baseline, retain reentrancy protection. |
| `TDefaultExceptionLogger` | Migrate in and adjust. Output format remains compatible, but error paths must not be silent. |
| `EmbedMapData` | Migrate in but isolated. Forbid automatically writing EXE in initialization. |
| `LocalVarExtractor` | Migrate in interface. Currently only verify manual metadata pathway; daudit/AST extractor deferred as independent integration item. |
| Registry source path discovery | Rewrite. Cannot retain hardcoded `BDS\22.0/23.0`. |
| Recursive source lookup | Already downgraded to optional. By default do not recursively scan the whole project; requires explicit `DAOFY_STACKTRACE_RECURSIVE_SOURCE_LOOKUP=1`. |
| `TStackTracer` callgraph | Keep current version, and gradually switch to large-version symbol table. |
| `daudit2` callgraph initial version | For historical reference only, not a migration source. |

## 9. Test Plan

### Delphi Actual Test

1. Minimal console exception project:
   - Reference `StackTrace`.
   - Call `TStackTraceManager.Current.EnableDefaultLogger`.
   - Actively raise `Exception.Create('stacktrace smoke')`.
   - Verify `exception.log` contains exception class, message, function name, source line.

2. QLangEditor regression:
   - Compile `C:\user\qlang\editor\qlangeditor.dproj`.
   - `callgraph SaveIfModified direction=callers project_only=true`.
   - `callgraph actNewProjectExecute direction=callees project_only=true`.

3. Local variable snapshot:
   - When disabled by default, log does not contain variables.
   - When enabled, basic variables can be output.
   - Both Win32/Win64 use manual local variable metadata and simulated frame buffer to verify reading `Integer`, boolean enum, `UnicodeString`.
   - Illegal object returns `<invalid>`; illegal pointer only formats address, does not dereference, does not cause secondary exception.
   - Unknown TypeKind returns `<unsupported type>`; long strings first check length limit, then copy content.
   - `FormatExceptionContext` verifies parameter/local variable display and hiding under `CaptureVariables=True/False` respectively.

### Python Tests

```powershell
$env:PYTHONIOENCODING='utf-8'
pytest tests\test_console_automation.py -q -p no:cacheprovider
pytest tests\test_doc_consistency.py -q -p no:cacheprovider
```

Need to add:

- MAPDATA serializer fixture tests.
- `run_verify` injection path tests.
- callgraph facade compatibility tests.

## 10. Rollback Strategy

| Failure point | Rollback method |
|--------|----------|
| New `StackTrace.pas` fails to compile | Restore current 23.6 KB small `StackTracer.pas`, keep callgraph usable |
| Exception hook causes startup crash | Disable `TStackTraceManager.Enabled` by default, only allow run_verify to explicitly enable |
| MAPDATA parsing fails | Fall back to external `.map` loading |
| Local variable snapshot unstable | Keep `CaptureVariables=False`, defer P2 |
| callgraph results regress | Temporarily let facade use current small-version scanning logic |

## 11. Execution Order Suggestions

1. Copy the large `qlang Editor` version to a temporary comparison file; do not directly overwrite the target.
2. Create `tools/stacktrace/StackTrace.pas` as the main implementation, keep unit name `StackTrace`.
3. P0a keeps current `StackTracer.pas` carrying callgraph; first verify exception reporting and run_verify chain of new `StackTrace.pas`.
4. P0b merges current `TStackTracer` API as a facade into `StackTrace.pas`, then deletes `StackTracer.pas` compatibility shell.
5. Compile minimal console project, only verify exception log without callgraph.
6. Then integrate callgraph, run Python protocol tests and QLangEditor actual tests.
7. Finally replace the run_verify injection path in `compile_project.py`.

## 12. Definition of Done

P0a completion must simultaneously satisfy:

- `tools/stacktrace/StackTrace.pas` provides `TStackTraceManager`, MAPDATA/tokenized symbol structures, exception hook, and default logger.
- The run_verify injection path in `src/tools/compile_project.py` is switched to `tools/stacktrace/StackTrace.pas`.
- Exception log capability no longer depends on `tools/daudit/StackTrace.pas`.
- Current callgraph protocol is not broken; `StackTracer.pas` temporarily keeps existing implementation.

Final migration completion must simultaneously satisfy:

- `tools/stacktrace/StackTrace.pas` provides both `TStackTraceManager` and `TStackTracer`.
- Independent `tools/stacktrace/StackTracer.pas` has been deleted, all callers uniformly use `StackTrace.pas`.
- Exception log capability does not depend on `tools/daudit/StackTrace.pas`.
- Tokenized MAPDATA is available, with roundtrip tests.
- Current callgraph protocol is not broken.
- Historical risks such as empty `except`, hardcoded BDS, automatic EXE writing have been fixed or isolated.

## 13. P0a Implementation Record

- Copied `C:\user\qlang\Editor\StackTrace.pas` to `tools/stacktrace/StackTrace.pas`; SHA256 prefix remains `8B71D80A1E8E36BF`.
- Switched the run_verify injection directory in `src/tools/compile_project.py` from `tools/daudit` to `tools/stacktrace`.
- Synchronized the run_verify path description in `src/resources/coding-rules.md` and `src/resources/coding-rules/compile.md`.
- Added run_verify injection path unit test to prevent regression to `tools/daudit`.
- Verified `tools/stacktrace/StackTrace.pas` can compile as a single file.
- Used minimal console project to execute `run_verify=True`, confirmed it can generate and read back `exception.log`; log contains `stacktrace smoke` and source line number.
- 2026-07-04 retest: same minimal crash project passes `run_verify=True` reading back exception log on both Win32/Win64