# Callgraph Capability Enhancement Plan

**Plan status**: Implementable plan  
**Planning date**: 2026-07-03  
**Scope**: `automate_delphi(gui)`'s `callgraph` / `callgraph_diff` / `callgraph_impact`, Delphi-side `DaofyAutomation.CallGraph.pas` / `StackTrace.pas`, Python protocol layer, documentation and tests. The standalone `StackTracer.pas` compatibility shell has been removed; `StackTrace.pas` is used uniformly.

## 1. Current Baseline

| Capability | Current status | Evidence | Main gap |
|------|----------|------|----------|
| Forward call graph | Supports `direction=callees` | `StackTrace.pas:TStackTracer.GetCallChain`, `DaofyAutomation.CallGraph.pas:233` | Only scans near direct call `$E8` |
| Reverse call graph | Supports `direction=callers` | `StackTrace.pas:TStackTracer.GetCallerChain`, `DaofyAutomation.CallGraph.pas:231` | Traverses all edges at query time; slow for large projects |
| Project filtering | Supports `project_only` and `exclude_prefixes` | `DaofyAutomation.CallGraph.pas:226`, `DaofyAutomation.CallGraph.pas:228` | Only exclude prefixes, no include/category |
| Diff comparison | Supports `callgraph_diff` | `automation_service.py:557`, `automation_service.py:598`, `automation_service.py:1504` | Current comparison key includes addresses, prone to noise after recompilation |
| Structured error output | Fixed; still parses `data` when `status=err` | `automation_service.py:1630` | Still lacks unified error code list |
| Delphi-side local protection | Retains `ReqId` at `HandleCallGraph` layer | `DaofyAutomation.CallGraph.pas:196` | Still need to extend more diagnostic fields |
| Win64 compatibility boundary | Verified with real project smoke | `StackTrace.pas:TStackTracer.ScanCallGraph`, `tests/test_stacktrace_callgraph.py`, `tests/test_stacktrace_callgraph_runtime.py` | Win64 enters shared scan path; QLangEditor Win64 callgraph has returned non-empty call edges |
| Enhanced usage entry points | Supports initial U1-U8 Python-side versions | `automation_service.py`, `tests/test_console_automation.py` | Path output and real project workflows still need polishing |

## 2. Goals

1. Upgrade `callgraph` from "can query a call chain" to a stable diagnostic capability usable for auditing, impact analysis, and regression localization.
2. Keep existing scripts compatible; default `cmd=callgraph` behavior does not break verified QLangEditor use cases.
3. All enhancements must have Python protocol tests, documentation sync, and at least one real-project verification path.

## 3. Non-Goals

1. This phase does not turn the callgraph facade in `StackTrace.pas` into a full disassembler.
2. This phase does not promise full coverage of virtual methods, interface calls, event callbacks, and RTTI dynamic dispatch.
3. This phase does not mix Win64 support and indirect call scanning into P0/P1, to avoid affecting the current Win32 usable baseline.

## 4. Phase Plan

### P0 - Output Stability and Audit Usability

#### P0.1 Add comparison strategy to `callgraph_diff`

**Status**: Implemented. `callgraph_diff` defaults to `compare_by=name`, can explicitly pass `addr` or `full`; invalid values fail at Python layer, no Delphi request sent.

**Problem**: Current `_callgraph_edge_key()` uses `from/name/address + to/name/address`; after recompiling same source, address changes are misjudged as removals and additions.  
**Plan**: Add `compare_by=name|addr|full`, default `name`; `full` retains current behavior.  
**Modification points**:

- `src/services/automation_service.py`: `_callgraph_edge_key(edge, compare_by)`, `_diff_callgraphs(..., compare_by)`, `callgraph_diff` parameter parsing.
- `tests/test_console_automation.py`: cover default name comparison, full comparison, invalid parameter error.
- `docs/automate_test_guide.md`, `src/tool_docs.py`, automation resource mirror sync.

**Acceptance criteria**:

- from/to names same but addresses different, default produces no added/removed.
- `compare_by=full` retains existing address-sensitive result.
- Invalid `compare_by` returns clear error at Python layer, no Delphi request sent.

#### P0.2 Edge deduplication and output limit

**Status**: Implemented. Currently at output layer in `DaofyAutomation.CallGraph.pas`, dedup by caller/callee name, address and `CallAddr`, and truncate by `edge_limit`; preserve different call sites for same caller/callee.

**Problem**: Direct call scan may produce duplicate edges; large functions or framework entries may return overly large JSON.  
**Plan**: Add edge deduplication and `edge_limit`; response includes `truncated=true|false`, `edge_count`, `returned_count`.  
**Modification points**:

- `tools/auto/DaofyAutomation.CallGraph.pas`: at output layer dedup by caller/callee/name/address/callsite.
- `tools/auto/DaofyAutomation.CallGraph.pas`: parse `edge_limit`, trim output and add metadata.
- `src/services/automation_service.py`: validate `edge_limit` range, e.g. `1..5000`.

**Acceptance criteria**:

- Repeated scan results for same caller/callee returned only once.
- When over limit, result usable and clearly marked truncated.
- Existing scripts not passing `edge_limit` remain compatible.

#### P0.3 Add call site file and line number

**Status**: Implemented. `TCallEdge` now has `CallAddr`, `CallFile`, `CallLine`; direct-call scan saves call instruction address and resolves call site line via MAP line table; JSON edge outputs `call_addr`, `call_file`, `call_line`.

**Problem**: Current JSON mainly describes callee symbol location, lacks "which line call happened on", high audit localization cost.  
**Plan**: `TCallEdge` add `CallAddr`, `CallFile`, `CallLine`, use call instruction address to query map line number.  
**Modification points**:

- `tools/stacktrace/StackTrace.pas`: when scanning `$E8`, save call instruction RVA and resolve callsite line number.
- `CallChainToJSON`: output `call_addr`, `call_file`, `call_line`.
- Python diff key still compares by name by default, avoid line changes creating noise.

**Acceptance criteria**:

- In QLangEditor, `SaveIfModified` callers result can give call site line number.
- When no line info, fields empty or 0, does not affect old client parsing.

### P1 - Query Performance and Path Analysis

#### P1.1 Build call edge index

**Status**: Implemented. After scanning, `TStackTracer` builds `FCallerIndex` / `FCalleeIndex`; BFS in `GetCallChain` / `GetCallerChain` retrieves edges related to current node via index, no longer traverses all `FCallEdges` each round. QLangEditor Win32 Debug measured `SaveIfModified` callers returns 3 edges normally, with `main.pas:586`, `main.pas:683`, `main.pas:719` call sites.

**Problem**: `GetCallChain` and `GetCallerChain` traversed all `FCallEdges` during query; performance degrades noticeably as call edges increase.  
**Plan**: After scan, build two indices: `caller_addr -> edges`, `callee_addr -> edges`.  
**Modification points**:

- `tools/stacktrace/StackTrace.pas`: build indices after `EnsureSymbols` or `ScanCallGraph`.
- Keep arrays as raw data; indices used for BFS.

**Acceptance criteria**:

- Callers/callees query results for same target same as current.
- Large project repeated query time significantly reduced; record at least one QLangEditor measured time.

#### P1.2 Add `callgraph_path`

**Problem**: Audits often ask "can entry A affect function B"; existing callgraph requires client manual filtering.  
**Status**: Implemented. Added `cmd=callgraph_path`, inputs `source`, `target`, `max_depth`, `max_paths`, returns `found`, `paths`, `path_count`, `max_paths`, `truncated`. Python layer validates `source`/`target` and `max_paths` before sending.  
**Modification points**:

- Delphi: `DaofyAutomation.CallGraph.pas` registers `callgraph_path`, reuses scanned call edges for bounded BFS path search.
- Python: `automation_service.py` adds request construction, parameter validation and response JSON status parsing.
- Docs/tests: `docs/automate_test_guide.md`, automation resources, `src/tool_docs.py`, `src/server.py` and target tests cover path query.

**Acceptance criteria**:

- Queries like `source=actNewProjectExecute`, `target=SaveIfModified` can return `found` and `paths`.
- When path not found returns `found=false`, not an error.
- `max_paths` can limit result count.
- `tests/test_console_automation.py` covers parameter forwarding, status parsing and local validation; `tests/test_stacktrace_callgraph.py` covers Delphi handler registration and paths JSON serialization.

#### P1.3 include filtering and edge classification

**Problem**: Currently can only exclude framework symbols by prefix, cannot explicitly view only project/third-party/system edges.  
**Status**: Implemented. Added `include_prefixes`, and add `category=project|thirdparty|framework|system|unknown` to each edge in response, also output `from_category`/`to_category`.  
**Modification points**:

- Delphi: extend filter function, keep `exclude_prefixes` compatibility; `category` classifies by callee, `from_category`/`to_category` annotate both ends of edge.
- Python: `callgraph`, `callgraph_diff`, `callgraph_path`, `callgraph_impact` all support list/string `include_prefixes` input.
- Docs: protocol description lists include filtering and classification fields.

**Acceptance criteria**:

- `include_prefixes=["TMainForm."]` only returns edges related to specified scope.
- `project_only=true` keeps existing semantics.
- Edge JSON contains `category`, `from_category`, `to_category`.

### P2 - Audit and Automation Integration

#### P2.1 Change impact analysis

**Problem**: With call graph, still need map "which functions changed" to "which entries are affected".  
**Status**: Initial version implemented. Python layer calls `callgraph(direction=callers)` based on changed file/line or function name, outputs entry function candidates.  
**Modification points**:

- `src/services/automation_service.py`: first made as `callgraph_impact` step.
- Later can combine with `delphi_project(action="ast")` or map line numbers.

**Acceptance criteria**:

- Input function name returns callers summary.
- Input file/line, if unable to resolve function, returns clear diagnostic, no guessing.

#### P2.2 Attach call graph to black-box failure report

**Problem**: When UI automation fails, current report can explain failure steps but cannot directly show related code impact surface.  
**Status**: Implemented and has regression tests. When script enables `callgraph_diagnostics=true` and failed step has `handler` / `entry` / `callgraph_target`, failure report attaches callgraph summary; when callgraph query fails, only appends warning, does not overwrite original UI failure reason.  
**Modification points**:

- Automation report generation logic adds optional `diagnostics.callgraph`.
- Default off, enabled via script metadata or step field, avoid extra overhead.
- Callgraph query executes before automatic `exit`; on failure only records warning, does not overwrite original UI automation failure reason.

**Acceptance criteria**:

- Report for failed step contains target, direction, edge count, truncation status.
- Callgraph failure cannot overwrite original UI automation failure reason.
- `tests/test_console_automation.py` covers success diagnostic and diagnostic failure degradation paths.

#### P2.3 Baseline saving and snapshot directory constraints

**Problem**: Current `callgraph_diff` supports reading baseline but has no standard save path and naming.  
**Status**: Implemented. `callgraph_diff` adds `save_as`; Python layer saves current callgraph JSON and limits write location under `snapshots_dir`; `baseline_path` and use-layer `callgraph_*` file-type JSON inputs also undergo resolve validation, cannot escape `snapshots_dir`.  
**Modification points**:

- Python layer performs saving, avoid Delphi-side file writing.
- `save_as` can only be relative path, automatically append `.json` suffix, successful save returns relative path and `edge_count`.
- `baseline_path`/file-type graph or impact input allows direct JSON or snapshot file path; file path after resolve must remain under `snapshots_dir`.
- Path must undergo resolve validation, prohibit directory traversal.
- Tests cover legal baseline file reading, baseline out-of-bounds rejection, and `save_as` empty value, `../`, absolute path rejection.

**Acceptance criteria**:

- Save success returns relative path and edge_count. ✅
- `..\`, absolute path, empty filename all rejected. ✅

### P3 - Research Items

#### P3.1 Indirect call identification

**Scope**: `FF /2`, virtual methods, interfaces, event callbacks, RTTI dynamic dispatch.  
**Risk**: Static disassembly hard to accurately parse Delphi high-level semantics; false positives and false negatives both high.  
**Recommendation**: Build separate fixture project, validate with AST/RTTI/runtime logs hybrid, not enter P0/P1.

#### P3.2 Win64 support

**Scope**: PE32+, x64 relative call, PDB/map differences, stack trace differences.  
**Risk**: Current QLangEditor measured baseline is Win32; Win64 needs separate validation.  
**Recommendation**: As independent compatibility milestone, do not mix with existing Win32 callgraph. Current phase has removed Win64 fail-closed guard: relevant units can compile for Win64, runtime enters shared scan path; when unable to parse should return structured errors `map_not_loaded`, `text_section_not_found`, `entry_not_found`, `no_edges`, etc.

##### P3.2.1 Current boundary

- `StackTrace.pas`, `DaofyAutomation.CallGraph.pas` verified Win64 single-file compilation passes.
- `TStackTracer.ScanCallGraph` removed `SizeOf(Pointer) <> SizeOf(DWORD)` fail-closed guard, Win64 and Win32 share scan path.
- Python protocol layer covers parsing structured diagnostics to `response.state` even when `status=err`, including old `win64_not_supported` response.
- W64-1 completed runtime address model pre-migration: `TCallEdge`, indices, BFS queue/visited/depth, `FindFuncAddr`, scan assignment and JSON address output changed to `NativeUInt` / pointer-width formatting.
- W64-2 completed `.text` section parsing boundary hardening: `LoadTextRange` explicitly accepts PE32 `$10B` / PE32+ `$20B` OptionalHeader magic, and continues locating section table via `FileHeader.SizeOfOptionalHeader`; test side already has fixed PE32/PE32+ fixtures.
- W64-3 completed direct-call rel32 parsing foundation: `ScanCallGraph` uses `ResolveRelativeCallTarget(ACallSite, ARel32)` to uniformly compute `$E8 rel32` target address; test side already has high x64 address forward/backward call fixture.
- This boundary now relies on MAPDATA v12 RVA address model, `NativeUInt` runtime addresses and PE32+ `.text` parsing jointly ensuring Win64 no longer misuses Win32 `DWORD` address model.

##### P3.2.2 Transformation goals

1. Support direct relative call call-edge scanning under Win64, output format compatible with Win32 `callgraph`.
2. Keep Win32 behavior and performance from regressing.
3. When unable to parse Win64 map or `.text`, continue returning structured errors, no crash, no false success.
4. Establish unified tests for Win32/Win64 shared symbol resolution, address formatting and JSON output.

##### P3.2.3 Technical plan

- **Address model unification**: Migrate callgraph internal address fields from `DWORD` to `NativeUInt`, JSON address output changed to pointer-width formatting; keep old fields `from_addr` / `to_addr`.
- **PE32+ `.text` parsing**: `LoadTextRange` explicitly distinguishes PE32/PE32+, does not rely on Win32 optional header layout assumptions when reading section table.
- **x64 direct call scanning**: Continue recognizing opcode `$E8 rel32`, but use `Int64`/`NativeInt` to calculate target address, avoid 64-bit truncation.
- **Symbol matching**: `ResolveSymbolStart`, `FindFuncAddr`, BFS queues and visited sets uniformly changed to `NativeUInt`.
- **Error semantics**: Win64 no longer defaults to `win64_not_supported`; normal Win64 scan failures should be subdivided into existing error codes such as `text_section_not_found`, `map_not_loaded`, `entry_not_found`, `no_edges`.
- **Compatibility layer**: If `TCallEdge` needs to retain `DWORD` fields, add `NativeUInt` fields and gradually migrate; prioritize avoiding breaking existing `DaofyAutomation.CallGraph.pas` uses.

##### P3.2.3.1 Address type audit checklist

Before Win64 support, must process the following runtime address fields in groups, to avoid only changing local helpers to `NativeUInt` while other paths still truncate:

- ✅ `StackTrace.pas:TCallEdge.CallerAddr/CalleeAddr/CallAddr` migrated from `DWORD` to `NativeUInt`.
- ✅ Index keys, queues, visited, depth dictionaries in `StackTrace.pas:TStackTracer.TEdgeIndex`, `FindFuncAddr`, `AddEdgeIndex`, `GetCallChain`, `GetCallerChain` uniformly changed to `NativeUInt` following `TCallEdge` address fields.
- ✅ In `StackTrace.pas:TStackTracer.ScanCallGraph`, truncation points `DWORD(LCallerStart)`, `DWORD(LCalleeStart)`, `DWORD(LCallSite)` removed; `SizeOf(Pointer) <> SizeOf(DWORD)` fail-closed guard also removed, Win64 enters scan path.
- ✅ `StackTrace.pas:TStackTracer.CallChainToJSON` and `DaofyAutomation.CallGraph.pas:EdgeToJSON` use pointer-width address formatting helper: Win32 outputs 8 hex digits, Win64 outputs 16 hex digits.
- ✅ `DaofyAutomation.CallGraph.pas:PathHasAddr` and `TCallEdge` fields now use same `NativeUInt` model.

Do not blindly change the following fields to `NativeUInt` in W64-1; should retain or list separate validation:

- `StackTrace.pas`'s `TMapSymbol.Addr`, `TLineInfo.Addr`, `TSymbolEntry.Addr`, `TLineEntry.Addr`, `TModuleSymbolTable.NameCache` migrated to `UInt64`, MAPDATA resource format upgraded to v12.
- MAPDATA v12 uniformly uses `WriteVarInt` / `ReadVarInt` names carrying ZigZag `Int64` varint; address fields normalized to module RVA during parsing, read/write as non-negative Int64 varint then stored in `UInt64`. Old MAPDATA resources no longer compatible; dependents need recompile and re-embed resources.
- `ResolveSourceLine`'s `LMapOffset` migrated to `UInt64`; runtime VA converted to MAPDATA RVA then can directly query 64-bit line table.
- `DWORD` in Windows API parameters, resource sizes, `GetCurrentThreadId` return values etc. are not call graph address model, not part of W64-1 truncation fix.
- `TStackSnapshot.ThreadId` currently `Cardinal`, semantically can be changed to Delphi RTL's `TThreadID`. RTL defines as `MSWINDOWS: LongWord`, `POSIX: NativeUInt`; it is not callgraph address field, can be handled separately as semantic cleanup.

##### P3.2.3.2 W64-4 real smoke prerequisites

W64-1 to W64-3, main module preferred-base helper, and MAPDATA v12 RVA address model completed: runtime address container, PE32+ `.text` locating, `$E8 rel32` target address calculation, `FModuleBase`/`FPreferredBase` cache, `MapAddrToRuntimeAddr` / `RuntimeAddrToMapAddr` bidirectional conversion, `ParseMapFile`'s `UInt64` segment/publics/line-number parsing, and `TMapSymbol` / `TLineInfo` / `TSymbolEntry` / `TLineEntry` 64-bit storage all landed. Real Win64 MSBuild `.map` sample confirmed `.text` section base is preferred-base VA like `0000000140001000`, public symbol is segment-local offset; during parsing must normalize segment VA to section RVA via target EXE's PE PreferredBase, then combine with public offset into module RVA. MAPDATA v12 carries this RVA form; runtime no longer guesses VA/RVA. `ScanCallGraph`'s Win64 fail-closed guard removed, real smoke prerequisites converge to:

- Main module address conversion must not fall back to `PreferredImageBase=$00400000` constant formula. `EnumerateFunctions`, `FindSymbolAddress`, `GetFunctionExtent`, `GetFrameSnapshot`, `ResolveFromMap`, `ResolveSourceLine` and `StackInfoStringProc` migrated to unified helper; old private `FormatStackFrame` dead code deleted. Subsequent changes must retain corresponding static tests, prevent reappearance of scattered formulas like `FModuleBase + (... - PreferredImageBase)`.
- Must use minimal Win64 GUI smoke to verify `EnsureSymbols`, `.text` range, symbol binary search, line number locating and JSON address output can connect on real PE32+ project.
- Old MAPDATA resources will be rejected by v12 reader; migration validation must include recompiling/re-embedding resources, cannot test old exe directly.

##### P3.2.4 Subtasks

| Phase | Task | Acceptance criteria |
|------|------|----------|
| W64-1 | Refactor `TCallEdge`, indices, BFS, scan assignment and JSON address formatting to `NativeUInt` model | Completed; Win32/Win64 single-file compilation passes, static tests lock no `DWORD(...)` runtime address truncation |
| W64-2 | Add PE32+ `.text` parsing test | Completed; fixed PE32/PE32+ fixture can parse `.text` start/end range, source guard locks `SizeOfOptionalHeader` locating section table |
| W64-3 | Add x64 `$E8 rel32` scan fixture | Completed; constructed high x64 forward/backward `$E8 rel32` call instructions can resolve to correct target addresses, source guard locks scan loop using unified helper |
| W64-4 | Enable real Win64 smoke | Completed; minimal Win64 console smoke returns `status=ok` under both `.map` fallback and MAPDATA overlay embedding paths, covering `SmokeEntry -> SmokeMiddle -> SmokeLeaf`; added `/DYNAMICBASE` automatic smoke, confirming same call edge still resolves when runtime `ModuleBase != PreferredBase` |
| W64-5 | QLangEditor or equivalent project Win64 regression | Completed; QLangEditor Win64 Debug compiles, `automate_delphi(gui)` returns non-empty call edges: `SaveIfModified` callers=3, `actNewProjectExecute` callees=40, elapsed 2.34s |

##### P3.2.5 Test requirements

- Python: retain old `win64_not_supported` err-data parsing compatibility test, meanwhile add source guard confirming `ScanCallGraph` no longer contains Win64 fail-closed guard; after real smoke add Win64 success/clear empty graph tests.
- Delphi static: `StackTrace.pas` / `DaofyAutomation.CallGraph.pas` must compile as single files under Win32 and Win64.
- Fixture: add PE/map/call instruction parsing tests not depending on local Delphi, covering 32/64-bit addresses.
- Real project: when Delphi Win64 environment available, run minimal callgraph demo, then QLangEditor or equivalent complexity project smoke.

##### P3.2.6 Rollback strategy

- If Win64 scanning introduces false positives or crashes, retain compilation compatibility and restore `win64_not_supported` fail-closed boundary.
- If address type migration affects Win32, first restore `TCallEdge` external fields, then limit `NativeUInt` migration to internal index structures.
- If PE32+ map parsing is unstable, Win64 only opens `ResolveAddr`/symbol query, not call edge scanning.

## 5. Enhanced Use Case Plan

This section records upper-layer use cases to support after callgraph enhancement. Principle: each use case must map to clear input, output, tests and failure semantics, avoid staying at "display call graph".

| Use case | Target users | Input | Output | Dependent capabilities | Acceptance criteria |
|------|----------|------|------|----------|----------|
| U1 change impact analysis | Code audit / PR review | changed function, file/line, git diff summary | affected entry functions, call paths, risk rating | P0.3, P1.1, P1.2, P2.1 | Given `SaveIfModified`, can list upstream entry candidates; when unable to resolve file/line returns clear diagnostic |
| U2 regression test selection | Black-box automation / CI | changed function list, mapping from test scripts to handlers | suggested black-box script set and reasons | U1, P1.2, P2.1 | When save chain modified, can hit dirty-close / save related scripts, not generalize to full test suite |
| U3 failure report enhancement | Black-box automation | failed step, handler, current UI state | `diagnostics.callgraph` summary, related call edges, truncation status | P0.2, P2.2 | callgraph failure does not overwrite original failure reason; on success report contains target, direction, edge count |
| U4 call graph baseline regression | Release / refactoring review | baseline JSON, current callgraph | added/removed/unchanged edges, stable comparison strategy, snapshot path | P0.1, P2.3 | Same source recompile by default does not produce added/removed noise due to address changes |
| U5 architecture boundary check | Code audit | include/exclude/category rules | call edges violating boundaries, e.g. UI directly depending on low-level implementation | P1.3 | `project_only`, `include_prefixes`, `exclude_prefixes` composable, violating edges reproducible |
| U6 refactoring safety check | Refactoring assistance | function to change, target replacement function, max depth | affected callers, paths, dynamic call blind spot hints | P1.1, P1.2, P3.1 | Before rename/split function can list directly and indirectly affected callers |
| U7 dead code and orphan candidates | Maintenance cleanup | full symbol table, entry function set | candidate functions with no caller, candidates only called by tests or framework | P1.1, P1.3 | Output must mark "candidate" rather than auto-kill, avoid event/RTTI missed edges misleading deletion |
| U8 exception stack extended explanation | Runtime diagnostics | exception stack, crash function, callgraph cache | upstream entries and downstream impact summary of crash function | StackTrace P2, P1.2, P2.2 | exception.log can optionally attach call graph summary; when callgraph missing exception log still outputs normally |

### 5.1 U1 Change Impact Analysis

Prioritize `callgraph_impact` as Python-layer auxiliary command, do not require Delphi side to add file writing.

- Input: `functions`, `file` + `line`, or changed symbols later provided by git diff.
- Processing: for each function execute `direction=callers`, combine `max_depth` and `project_only` to output upstream entry candidates.
- Output: `targets`, `entries`, `paths`, `unresolved`, `warnings`.
- Failure semantics: when unable to resolve function from file/line return `unresolved`, do not guess function name.
- Tests: Python unit tests cover function name input, file/line parsing, file/line unable to parse, callgraph returns `entry_not_found`.
- Current initial version: supports `functions`/`targets`/`target`, `file`+`line`/`locations`, and PR/diff style `changes` input (each item may contain `function` or `file`+`start_line/new_line/line`); batch sends `callgraph direction=callers`, aggregates `entries`, `unresolved`, `warnings` and `resolved_locations`.

### 5.2 U2 Regression Test Selection

Build lightweight mapping on U1: black-box scripts can declare `handler` / `entry` / `tags`, impact analysis recommends scripts based on call paths.

- Input: changed function list, script metadata, optional `max_scripts`.
- Output: recommended scripts, hit paths, confidence, uncovered functions.
- Default strategy: prefer returning "needs manual confirmation", do not automatically classify unknown changes as full high confidence.
- Validation: use QLangEditor save/close chain as fixture; when modifying `SaveIfModified` must recommend related dirty-close/save scripts.
- Current initial version: supports `cmd=callgraph_select_tests`, based on `impact` and test `handler`/`tags`/`covers` metadata outputs `selected`, `covered_targets`, `uncovered_targets`; when `handler` hits impacted caller, reverse lookup its covered changed target by impact entry; `covers`/`functions`/`targets` can explicitly declare script coverage.

### 5.3 U3 Failure Report Enhancement

Add optional `diagnostics.callgraph` in black-box failure report, default off, enabled via script parameter.

- Input: failed step's `handler`, `target` or explicit `callgraph_target`.
- Output: call graph summary, do not output overly large full graph; large graph truncated via `edge_limit`.
- Constraint: callgraph diagnostic failure can only be appended warning, cannot change main step failure reason.
- Validation: construct a failed UI step and successful callgraph response, report must retain both UI failure and call graph summary.
- Current initial version: supports `cmd=callgraph_failure_diag`, generates `diagnostics.callgraph` summary from failed step and callgraph state.

### 5.4 U4 Call Graph Baseline Regression

Use `callgraph_diff` as structural change check before/after refactoring/release.

- Input: baseline JSON or `baseline_path` snapshot file, current target, `compare_by=name|addr|full`, optional `save_as`.
- Output: added/removed/unchanged, comparison strategy, save path, edge count.
- Path safety: saving only allowed under `snapshots_dir`, prohibit absolute paths and directory traversal.
- Validation: same name different address default no noise, `compare_by=full` retains old address-sensitive behavior.
- Current initial version: `callgraph_diff` supports `save_as`, save path limited under `snapshots_dir`; read-type snapshot paths also pass same directory boundary validation.

### 5.5 U5 Architecture Boundary Check

Use include/exclude/category rules to apply call graph to boundary audit.

- Input: rule set, e.g. `ui -> service allowed`, `ui -> storage forbidden`.
- Output: violating call edges, call paths, category, suggested entries.
- Classification source: first use naming prefixes and map symbol, later combine project KB / AST.
- Validation: construct an edge where UI directly calls low-level implementation in fixed fixture, must be reported as violation.
- Current initial version: supports `cmd=callgraph_boundary_check`, outputs violations by `from_prefix` / `to_prefix` `forbid` rules; rules can configure `exclude_from_prefixes` / `exclude_to_prefixes` as exceptions, and return `severity` and `message` in violation.

### 5.6 U6 Refactoring Safety Check

Risk scan before rename, extract function, move module.

- Input: function to change, max depth, include/exclude, whether to include framework edges.
- Output: direct callers, indirect callers, downstream dependencies, dynamic call blind spot hints.
- Constraint: virtual methods, events, RTTI calls must be marked "incomplete coverage", cannot claim full coverage.
- Validation: for same target function, existing Win32 results must be compatible with before enhancement.
- Current initial version: supports `cmd=callgraph_refactor_check`, based on impact outputs affected callers, `affected_targets`, `safe_to_refactor`, `unresolved` and static graph blind spot warnings; when unresolved exists risk raised to `high`, avoid treating incomplete graph as safe conclusion.

### 5.7 U7 Dead Code and Orphan Candidates

Use full symbol and caller index to discover candidates, do not make automatic deletion suggestions.

- Input: entry function set, exclude prefixes, optional test entry set.
- Output: no-caller candidates, only-called-by-tests candidates, orphan subgraphs.
- Risk hints: event handlers, RTTI, virtual methods, external exports may miss edges, result can only be candidates.
- Validation: candidate output must carry `confidence` and `reason`, prohibit only function name list.
- Current initial version: supports `cmd=callgraph_orphan_candidates`, outputs low-confidence candidates and forcibly attaches cannot-auto-delete warnings; can pass `test_prefixes` to mark "only called by tests" candidates, and separately give reasons for candidates with completely no caller.

### 5.8 U8 Exception Stack Extended Explanation

Combine StackTrace exception stack and callgraph, help look back at entries from crash point and look forward at impact.

- Input: crash function or stack top function in exception.log.
- Output: upstream entry summary, downstream key calls, whether truncated, callgraph error codes.
- Default: exception log capability first, callgraph missing does not affect exception report generation.
- Validation: in run_verify smoke, even if callgraph unavailable, still outputs original exception stack.
- Current initial version: supports `cmd=callgraph_explain_exception`, extracts function names from exception frames with address, `+offset`, `[file:line]`, then outputs upstream/downstream summary, raw top frame and count summary based on callgraph/impact.

## 6. Recommended Implementation Order

| Milestone | Content | Expected benefit | Risk |
|--------|----------|----------|------|
| A | P0.1 + P0.2 | Diff comparison stable, output won't explode | Low |
| B | P0.3 | Audit localization efficiency significantly improved | Medium |
| C | P1.1 + P1.2 | Support impact path analysis, faster queries | Medium |
| D | P1.3 + P2.1 | Upgrade from call graph to change impact analysis | Medium |
| E | P2.2 + P2.3 | Integrate into black-box report and snapshot workflow | Medium |
| U | U1-U8 Python-side initial versions | Enter auditing, regression selection, failure diagnosis, boundary check and exception explanation workflows | Medium |
| W | P3.2 | Win64 callgraph upgrade from fail-closed to scannable | High |
| R | P3.1 | Expand indirect call coverage | High |

## 7. Verification Plan

### Python Protocol Tests

```powershell
$env:PYTHONIOENCODING='utf-8'
pytest tests\test_console_automation.py -q -p no:cacheprovider
```

### Documentation Consistency Tests

```powershell
$env:PYTHONIOENCODING='utf-8'
pytest tests\test_doc_consistency.py -q -p no:cacheprovider
```

### Real Project Verification

Use `C:\user\qlang\editor` as fixed regression project:

1. Compile `qlangeditor.dproj`.
2. Query `SaveIfModified` callers, confirm returns project callers and call sites.
3. Query `actNewProjectExecute` callees, confirm `project_only` and filter parameters take effect.
4. Execute `callgraph_diff` with saved baseline, confirm added/removed/unchanged stable.

### Win64 Compatibility Verification

Current phase verification goal is Win64 enters shared scan path and maintains structured error parsing:

```powershell
$env:PYTHONIOENCODING='utf-8'
pytest tests\test_console_automation.py tests\test_stacktrace_callgraph.py -q -p no:cacheprovider
```

When Delphi Win64 environment available, also execute:

- `StackTrace.pas` / `DaofyAutomation.CallGraph.pas` Win64 single-file compilation.
- Minimal Win64 callgraph demo must no longer return `win64_not_supported`, at least return `status=ok` or clear `map_not_loaded` / `text_section_not_found` / `entry_not_found` / `no_edges`.
- 2026-07-04 measured: minimal Win64 console smoke returns `OK` JSON under both `.map` fallback and MAPDATA overlay embedding paths, containing `SmokeEntry -> SmokeMiddle -> SmokeLeaf` direct call edges; after embedding PE header remains `MZ`, overlay footer is `MAPOVL01`.
- 2026-07-04 added automatic test: `tests/test_stacktrace_callgraph_runtime.py` compiles Win64 `/DYNAMICBASE` console smoke, confirms disk PE header `IMAGE_DLLCHARACTERISTICS_DYNAMIC_BASE`, after runtime confirms `ModuleBase != PreferredBase` verifies `SmokeEntry -> SmokeMiddle -> SmokeLeaf` call edges.
- 2026-07-04 ASLR path fix: `GetModulePreferredBase(hModule)` no longer reads `OptionalHeader.ImageBase` from mapped module memory header, but locates disk PE via `GetModuleFileName`, then reuses `GetPEFilePreferredBase`. Runtime mapped header after ASLR cannot be source of truth for PreferredBase.
- 2026-07-04 symbol reverse lookup fix: `BuildSymbolNameCache` and multi-module `NameCache` keep first address for duplicate symbol names, no longer trigger `EListError: Duplicates not allowed` due to duplicate symbols in MAP; ASLR smoke restored covering `FindSymbolAddress`.
- 2026-07-04 Win64 GUI smoke: minimal VCL GUI project queries `SmokeEntry` callees with `automate_delphi(gui)`, returns `SmokeMain.SmokeEntry -> SmokeMain.SmokeMiddle` and `SmokeMain.SmokeMiddle -> SmokeMain.SmokeLeaf` two edges, addresses 16 hex digits, line numbers `SmokeMain.pas:36` / `SmokeMain.pas:31`, report elapsed 1.64s.
- 2026-07-04 QLangEditor regression: Win32 Debug compiles; `SaveIfModified` callers returns 3 edges, `actNewProjectExecute` callees returns 37 edges, report elapsed 2.24s. Win64 Debug compiles after adding `DCC_Namespace=Winapi;System.Win;Data.Win;Datasnap.Win;Web.Win;Soap.Win;Xml.Win;Bde;$(DCC_Namespace)` and removing temporary EBP asm debug block; `SaveIfModified` callers returns 3 edges, `actNewProjectExecute` callees returns 40 edges, report elapsed 2.34s.
- 2026-07-04 full Python regression: `pytest -q -p no:cacheprovider` passes, result 1093 passed, 77 skipped, 33 subtests passed. During this, completed the `src/resources/coding-rules/kb-search.md` shard, and switched resource test assertions to the current Chinese heading, avoiding restoring bilingual Chinese/English dual headings.

## 8. Risks and Rollback

| Risk | Control | Rollback |
|------|----------|----------|
| diff default comparison strategy changes | Explicitly add `compare_by=full` to retain old behavior | Change default back to `full` |
| More output fields affect old clients | Only append fields, do not delete old fields | Disable new metadata output or keep empty values |
| callsite line number parsing incomplete | Return 0/empty when missing, not an error | Temporarily only output `call_addr` |
| Index implementation introduces inconsistency | Keep original array, test compare results before/after index | Query logic fall back to traversing array |
| Path query too deep causes time cost | Limit `max_depth` and `max_paths` | Python layer rejects overly large parameters |
| Win64 scan false positive or crash | Keep source guards, compile verification and real smoke | Temporarily restore `win64_not_supported` structured error |
| Enhanced use cases mislead automatic decisions | Output confidence, reason and unresolved, do not auto-delete or skip tests | Disable corresponding use case commands, retain basic callgraph |

## 9. Definition of Done

After P0 complete should satisfy:

- `callgraph_diff` default suitable for source audit, no large false positives due to address drift.
- `callgraph` output has deduplication, truncation marker and call site localization.
- QLang