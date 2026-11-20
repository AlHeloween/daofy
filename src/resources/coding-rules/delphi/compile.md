<!-- @when: Coding is complete, preparing for compile verification -->
<!-- @chain: before=review-guide.md, after=format.md -->

## ⑤ Compile

```python
delphi_project(action="compile", project_path="Project.dproj")
delphi_project(action="compile_file", project_path="Unit1.pas")    # Single-file syntax check
delphi_project(action="compile", project_path="Project.dproj", build_configuration="Release", target_platform="win64")
```

### Additional Compile Arguments (extra_args)

`extra_args` is a complete argument array, interpreted by the actual compile backend and appended after the built-in arguments:

```python
# .dproj / a .dpr with a same-named .dproj: MSBuild arguments, request TDS/RSM generation
delphi_project(action="compile", project_path="Project.dproj",
        extra_args=["/p:DCC_DebugInfoInTds=true", "/p:DCC_RemoteDebug=true"])

# .dpr without a same-named .dproj: direct DCC arguments
delphi_project(action="compile", project_path="Project.dpr", extra_args=["-VT", "-VR"])
```

Each array element is one complete argument; do not add outer quotes yourself. If the compiler generates `.tds`/`.rsm`, they will be listed in `output_files`.

### Run Verification (run_verify)

```python
delphi_project(action="compile", project_path="Project.dproj", run_verify=True)
```

After a successful compile, automatically launch the exe to detect runtime crashes:

**① Inject StackTrace** — temporarily modify `.dproj`/`.dpr`; automatically restore after verification
**② Recompile** (after injection)
**③ Run exe** — Popen + timeout(5s), kill on timeout
**④ Check exception.log** — if present, embed in result; otherwise passed
**⑤ Restore** — restore `.dproj`/`.dpr` from `.verify_bak`

> StackTrace.pas is located in tools/stacktrace/; run_verify uses this built-in diagnostic unit to capture call stacks; local variable snapshots are disabled by default.

### Compile Failure Handling Flow

```
Failure
 ├─ ① check_environment(action="check")
 ├─ ② Classify: Fatal → fix first / Error → primary target / Warning → defer
 ├─ ③ First failure → check recent changes; suspect cache → clean .dcu and do a full build
 ├─ ④ Path/config check: search paths / DCCReference / conditional compilation
 ├─ ⑤ Single-file isolation: compile_file; for a large number of errors, start from the first Error
 ├─ ⑥ Search experience library: experience(search, query="DCC {error code}")
 ├─ ⑦ Hypothesis-driven loop: 2–3 hypotheses → verify in parallel
 ├─ ⑧ Binary-search isolation / regression localization
 ├─ ⑨ Maintain a debug log
 └─ ⑩ Still unresolved after 3 failures → evaluate manual intervention
```

> **Events**: PreBuildEvent/PostBuildEvent execute automatically. If compilation fails, temporarily comment out `<Event>` lines to eliminate interference.
> **Safety**: Log `logger.warning` before executing events with `shell=True`; long polling ≤30s.

