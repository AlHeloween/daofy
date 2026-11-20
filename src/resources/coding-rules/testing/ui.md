<!-- @when: After a GUI program compiles successfully, UI interaction verification is required -->
<!-- @chain: before=console.md, after=review-table.md -->

## ⑧ Automated UI Interaction Testing

After compilation passes (optional run_verify), perform interactive operations and screenshot verification on the GUI program.

> After AI generates or modifies a DFM, first run `delphi_project(action="layout", base_dir="...")` for a static layout audit; after it passes, proceed to the runtime UI verification in this chapter.

### Enablement Process

First integration → follow the "Enablement Process" in [automation/scenarios/base.md](automation/scenarios/base.md) (pre-check → modify .dpr → compile → smoke verification).

Key constraints:
- **`AutoStart` must be called before `Application.Initialize`**
- **Prefer direct reference with an `in` clause** (no need to change .dproj configuration; AI can write it directly); projects that already have a search-path system can use the search-path approach
- For projects already configured, skip directly to "Tool Invocation" to start writing scripts

### Tool Invocation
```python
automate_delphi(app_path="App.exe", script=[...])
automate_delphi(action="gui", app_path="App.exe", script=[...])
automate_delphi(action="auto", app_path="App.exe", script="script.json", keep_alive=True)
```
`action="auto"` automatically detects the PE header Subsystem field.

### Communication Architecture
```
Python                              Delphi
  ── CreateFile(\\.\pipe\daofy_auto) → pipe thread receives JSON
  ── WriteFile(JSON request)        → main thread executes
  ←── ReadFile(JSON response)       ← returns result/ACK
```

### Synchronous/Asynchronous Command Classification
| Synchronous | Asynchronous |
|------|------|
| goto, capture, dumpstate, listwnd, formsum | click, rclick, dblclick |
| wait, waitfor, dlgscan, msgscan, msgclose | hover, move, drag |
| dlgfile, snapdir, exit | type, key |
| rget, rinspect | rcall, rset, msgclick, dlgclick |

### keep_alive
- `keep_alive=True` keeps the process running; it is automatically cleaned up after 5 minutes of inactivity
- The first call on a newly created process automatically sets `snapdir`

### Protocol
- Synchronous commands block and wait for a response; asynchronous commands ACK immediately
- Response: `{"reqId":"step_0","status":"ok","data":"OK"}`
- >64KB is automatically chunked (ERROR_MORE_DATA loop read)

---

### Scenario Index

For complete script field definitions, see `delphi://automation/script-schema` (MCP Resource). Each scenario file contains a strategy description and reusable JSON templates:

| Scenario | Corresponding file | Applicable timing |
|------|---------|---------|
| A. Smoke test | [automation/scenarios/a-smoke.md](automation/scenarios/a-smoke.md) | Verify the program can start and the main form is ready |
| B. Login flow | [automation/scenarios/b-login.md](automation/scenarios/b-login.md) | Username/password input, login state switching |
| C. Form data entry | [automation/scenarios/c-data-entry.md](automation/scenarios/c-data-entry.md) | Fill out a form and submit/save |
| D. List/grid row operations | [automation/scenarios/d-grid.md](automation/scenarios/d-grid.md) | Add/edit/delete data rows |
| E. Tree navigation | [automation/scenarios/e-tree-navigation.md](automation/scenarios/e-tree-navigation.md) | Tree node expand/collapse/select |
| F. Search/filter | [automation/scenarios/f-search.md](automation/scenarios/f-search.md) | Search hit, miss, result update |
| G. Modal dialogs | [automation/scenarios/g-modal-dialogs.md](automation/scenarios/g-modal-dialogs.md) | MessageBox / OpenDialog / confirmation dialog |
| H. Multi-step wizard | [automation/scenarios/h-wizard.md](automation/scenarios/h-wizard.md) | Wizard step switching and submission |
| I. Context menu | [automation/scenarios/i-context-menu.md](automation/scenarios/i-context-menu.md) | ContextMenu popup and selection |
| J. DirectUI popups | [automation/scenarios/j-directui.md](automation/scenarios/j-directui.md) | IFileDialog / TTaskDialog / uia.xxx commands |
| K. Text completeness | [automation/scenarios/k-text-completeness.md](automation/scenarios/k-text-completeness.md) | OCR detects truncation/ellipsis/overflow |
| L. Layout visual alignment | [automation/scenarios/l-layout.md](automation/scenarios/l-layout.md) | Left alignment/spacing/overlap/cross-DPI |
| M. Control targeting strategy | [automation/scenarios/m-control-targeting.md](automation/scenarios/m-control-targeting.md) | Text priority/coordinate calibration/DPI factor |
| N. Waiting and condition synchronization | [automation/scenarios/n-wait-strategy.md](automation/scenarios/n-wait-strategy.md) | Prefer waitfor/disallow bare fixed delays |
| O. Control rebuild safety | [automation/scenarios/o-control-rebuild.md](automation/scenarios/o-control-rebuild.md) | Wait for control rebuild after Rescan/Reload |
| Appendix: Checklist | [automation/scenarios/checklist.md](automation/scenarios/checklist.md) | 27 black-box test quality gates |

### Scenario Selection Principles

Run smoke (A) first to confirm the main flow is unobstructed → then choose B-O according to the test objective. The same test file can combine steps from multiple scenarios (e.g., login B → search F → select row D → edit D → DPI anomaly check K → layout alignment L → control targeting calibration M → rebuild safety O).

Generic template (quickly apply to any scenario):
```json
[
  {"cmd":"goto","target":"T<target form>","note":"Wait for form ready"},
  {"cmd":"<command>","target":"<target>","<parameter>":"<value>"},
  {"cmd":"waitfor","target":"<state target>","prop":"<property>","value":"<expected value>","timeout":5000},
  {"cmd":"capture","target":"<screenshot name>"},
  {"cmd":"exit"}
]
```

> Scenario files are located in the `automation/scenarios/` directory and are referenced by relative path. Infrastructure (communication/protocol/tool invocation) is covered in [automation/scenarios/base.md](automation/scenarios/base.md). Architecture methodology is covered in `automation/architecture.md`.

