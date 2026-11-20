# Callgraph Split Implementation Plan

**Plan Status**: Implemented
**Audit Date**: 2026-07-03
**Scope**: the new `callgraph` capability of `automate_delphi(gui)`, the Delphi automation inline units, the StackTrace diagnostic units, documentation and tests.

## P0.1 Requirements Clarification

| Check Item | Content |
|--------|------|
| Explicit requirement | Split `callgraph` out of `DaofyAutomation.Base.pas` into an optional diagnostic capability, and produce an auditable plan following the Daofy convention. |
| Implicit requirement | Ordinary VCL/FMX automation users must not gain a new compile dependency because callgraph is not enabled; when `callgraph` is available it must return reliable error semantics and verifiable data. |
| Boundary scope | This plan only splits out and corrects the callgraph diagnostic capability; it does not rewrite the existing automation commands such as UIA, RTTI, screenshots, msgscan/dlgscan. |
| Input/Output | The input is the GUI script step `{ "cmd": "callgraph", "target": "<function name>", "max_depth": N }`; the output is a JSON graph structure or an explicit error. |
| Implementation choice | The main implementation is unified into `tools/stacktrace/StackTrace.pas`; the standalone `tools/stacktrace/StackTracer.pas` compatibility shell has been removed. |
| Performance requirement | The first scan of `.text` may carry a one-off cost, but a single `callgraph` target query must reuse the cache; for a typical GUI program the first scan of the target should stay within 2 seconds and subsequent queries within 200 ms. |
| Security requirement | No arbitrary user-specified path is read; by default only the `.map` named after the target exe is read. No external command is executed and no target project source is written. |
| Documentation requirement | Synchronize `tool_docs.py`, the automation resource, `docs/automate_test_guide.md`, the tutorial examples and the release notes. |
## P0.2 Impact Analysis

| File/Area | Evidence before implementation | Change | Risk |
|-----------|----------|--------|------|
| `tools/auto/DaofyAutomation.Base.pas` | Before implementation, line 19 unconditionally did `uses StackTracer`; line 704 dispatched `callgraph` | The `StackTracer` dependency and the `callgraph` branch were removed, restoring Base to carrying only the base protocol | Must ensure ordinary automation command behaviour is unchanged |
| `tools/stacktrace/StackTrace.pas` | `TStackTracer.ScanCallGraph` / `GetCallChain` / `GetCallerChain` | Serves as the unified main diagnostic unit, carrying the exception report, tokenized MAPDATA and the callgraph facade | Delphi PE/map parsing differs between Win32 and Win64 |
| New `tools/auto/DaofyAutomation.CallGraph.pas` | Did not exist before implementation | A new optional command unit has been created that registers the `callgraph` handler and calls `StackTrace.TStackTracer` | A minimally invasive command extension interface had to be designed |
| `src/services/automation_service.py` | Line 1303 builds the step request; line 1456 deserializes `callgraph` data | Passes `max_depth` through, validates the range, keeps JSON state parsing | Protocol field changes need tests |
| `src/tool_docs.py` | Lines 847/857/908 declare `callgraph` in the documentation | States explicitly that `callgraph` requires enabling the optional Delphi unit and a Detailed map | Avoid misleading ordinary GUI users |
| `src/server.py` prepare | Line 1481 returns `tools/auto` + `tools/stacktrace` | The prepare output must state that callgraph is an optional capability; ordinary automation does not force stacktrace | Stay compatible with the paths already registered |
| `src/tools/compile_project.py` | run_verify uses `tools/stacktrace/StackTrace.pas`; callgraph also exposes the `TStackTracer` facade through `StackTrace.pas` | Keeps run_verify's diagnostic capability and the callgraph query capability in the same main StackTrace unit | The standalone `StackTracer.pas` is no longer shipped |
| docs/resources/tutorial | Several places mention only `tools/auto` | Adds the optional callgraph integration route: reference `DaofyAutomation.CallGraph` + `tools/stacktrace` | The docs and resource mirrors must be synchronized |
| tests | There is currently no `callgraph` coverage | Adds Python protocol tests, documentation consistency tests and map parser fixture tests | A real Delphi compile test may depend on the environment |
## P0.2.1 Source Code Verification

- Before implementation, `tools/auto/DaofyAutomation.Base.pas:19` placed `StackTracer` in the interface `uses`, so the dependency propagated to every VCL/FMX automation project.
- Before implementation, `tools/auto/DaofyAutomation.Base.pas:704` handled `callgraph` inside the base command dispatch and had no optional-enable boundary.
- The old `tools/stacktrace/StackTracer.pas` recorded the addresses of scanned edges and compared the entry address directly inside a linear BFS; after P0b this part has been migrated to the `TStackTracer` facade in `StackTrace.pas`.
- `src/services/automation_service.py:1303` through `1414` had no `callgraph`-specific request-construction branch, so `max_depth` was not passed through.
- `src/tool_docs.py:908` publicly declared `max_depth` to be controllable; the current implementation did not satisfy that.
- Before implementation, `src/resources/automation/reference/inline-unit.md:38` recommended adding only `tools\auto`, which was inconsistent with the `StackTracer` dependency at that time.
## P0.3 Solution Design

### Overall Approach

Split `callgraph` out of the base automation protocol into an optional diagnostic extension: an ordinary project references only `Vcl.DaofyAutomation` / `Fmx.DaofyAutomation`; when a call graph is needed it additionally references `DaofyAutomation.CallGraph` and `StackTrace`, and the preconditions are stated explicitly in the documentation and tool tips.

### Technical Solution

1. **Command extension boundary**
   - Add a lightweight extension registration point to `DaofyAutomation.Base.pas`, for example `RegisterCommandHandler(Cmd, Handler)` or the virtual method `TryHandleExtraCommand`.
   - Base does not directly `uses StackTrace` / `StackTracer`; it calls the extension hook only before a command is treated as unknown.
   - The new unit `DaofyAutomation.CallGraph.pas` registers the `callgraph` handler in its initialization.

2. **Optional Delphi unit**
   - Create `tools/auto/DaofyAutomation.CallGraph.pas`.
   - That unit does `uses StackTrace` and is responsible for reading `target/max_depth`, calling `TStackTracer.GetCallChain`, and returning unified JSON.
   - Ordinary VCL/FMX units do not depend on callgraph.

3. **StackTrace callgraph facade correction**
   - Unify the address model on RVA: map entries, E8 targets, caller/callee and the BFS queue all use RVA.
   - `LoadMap` supports the segment:offset form of a Detailed map and allows base/offset to be 0.
   - `ScanCallGraph` records only near calls whose target lies inside the `.text` range, avoiding treating an `$E8` byte in data or an external thunk as an internal call.
   - `GetCallChain` returns structured errors: `map_missing`, `entry_not_found`, `no_edges`, `scan_failed`.
4. **Python protocol layer**
   - Add a `cmd == "callgraph"` branch in `automation_service.py` that passes `target` and `max_depth` through.
   - `max_depth` is limited to `0..20`; an illegal value returns an error directly on the Python side, avoiding an excessive scan on the Delphi side.
   - Keep the JSON state deserialization at line 1456.

5. **Documentation and tool tips**
   - In `tool_docs.py`, mark callgraph as an optional diagnostic command and state that it requires `DaofyAutomation.CallGraph` and a Detailed `.map`.
   - Add an optional integration block to `inline-unit.md` / `base.md` / `docs/automate_test_guide.md`.
   - Add a separate callgraph example under the sample dpr/dproj, without polluting the basic AutoTest example.

6. **Test strategy**
   - Python unit tests: verify the `max_depth` pass-through, the range validation, and parsing of the returned `state`.
   - Delphi static/fixture tests: use fixed map text to verify `LoadMap` parsing of segment:offset.
   - Documentation consistency tests: the basic integration documentation must not require an ordinary project to reference `StackTracer`; the callgraph documentation must declare the optional dependency.
   - On a machine where it is available, run one VCL demo: ordinary automation compiles; after additionally referencing callgraph, `callgraph` returns a non-empty result or an explicit error.

### Subtask List

| Phase | Task | Acceptance Criteria |
|------|------|----------|
| T1 | Add the command extension hook to Base, remove the `StackTracer` uses and the inline `callgraph` branch | `tools/auto/DaofyAutomation.Base.pas` no longer mentions `StackTracer`; the ordinary automation command path is unchanged |
| T2 | Add `DaofyAutomation.CallGraph.pas` | `StackTrace` is depended on in that unit only; once the unit is referenced, `callgraph` can be dispatched |
| T3 | Correct the callgraph facade address model and the map parsing in `StackTrace.pas` | The fixture tests cover the entry function, internal call edges, the empty graph and a missing entry |
| T4 | Correct the Python request construction and input validation | `max_depth` is passed through; an illegal range returns a clear error |
| T5 | Synchronize the documentation, resources, tool tips and examples | The documentation states that ordinary integration and optional callgraph integration are separated |
| T6 | Verification and regression | The targeted Python tests pass; on a machine with Delphi available, both the ordinary demo and the callgraph demo compile |

### Verification Commands

```powershell
$env:PYTHONIOENCODING='utf-8'
pytest tests\test_console_automation.py tests\test_doc_consistency.py tests\test_mcp_resources.py -q -p no:cacheprovider
```

If Delphi units were modified:

```python
delphi_project(action="compile", project_path="<demo>.dproj")
delphi_project(action="compile", project_path="<callgraph-demo>.dproj", run_verify=True)
```

### Rollback Plan

- T1/T2 fails: restore the `DaofyAutomation.Base.pas` backup and remove the new `DaofyAutomation.CallGraph.pas`.
- T3 fails: keep the split boundary but disable the `callgraph` registration, and mark the capability in the documentation as experimental and unavailable.
- T4/T5 fails: roll back the Python protocol and documentation changes; ordinary GUI automation is unaffected.

## P0.4 Plan Self-Review

| # | Review Item | Conclusion |
|---|--------|------|
| 1 | Requirement coverage | Pass. Covers the split, the protocol, the Delphi implementation, documentation and tests. |
| 2 | Source verification | Pass. The plan rests on specific files and line numbers. |
| 3 | Existing-pattern match | Pass. Follows the `tools/auto` layering and the `automate_delphi` JSON protocol. |
| 4 | Chain reactions | Pass. Defines clearly the boundary between ordinary automation and the optional diagnostic dependency. |
| 5 | Risk containment | Pass. The PE/map parsing risk is confined to `StackTrace.pas` and the fixture tests. |
| 6 | Interface compatibility | Pass. Ordinary commands stay compatible; `callgraph` keeps its original cmd name. |
| 7 | Edge-case handling | Pass. Covers a missing map, a missing entry, an illegal depth and an empty graph. |
| 8 | Security compliance | Pass. Introduces no arbitrary path read and no external command execution. |
| 9 | Performance target | Pass. Defines the first-scan and subsequent-query budgets and requires cache reuse. |
| 10 | Observability completeness | Pass. Requires structured error codes and JSON state. |
| 11 | Documentation synchronization | Pass. Lists every document and example that must be synchronized. |
| 12 | Test completeness | Pass. Lists the Python, fixture, documentation-consistency and Delphi demo verification. |
| 13 | Technical debt containment | Pass. After the split, callgraph is hardened independently through `StackTrace.pas` only and does not pollute the base protocol. |
| 14 | Subtask soundness | Pass. Every phase can be verified and rolled back independently. |
### Audit Conclusion

**Pass**. This plan satisfies the P0.4 requirements and has completed the P0b migration: `StackTrace.pas` is the unified main implementation, and the standalone `StackTracer.pas` compatibility shell has been removed.

