<!-- @when: Controls are destroyed and rebuilt during an operation (rescan/reload/theme switch), requiring safe waiting for rebuild -->
<!-- @part-of: ui-testing -->

#### O. Control Rebuild Safety — Wait for Rebuild After Rescan/Reload

| Element | Content |
|------|------|
| **Goal** | Handle safe access after controls are destroyed and rebuilt during operations (rescan, reload, theme switch) |
| **Strategy** | Do not immediately rget after the operation → first use goto to wait for control rebuild → verify key controls exist → then continue |
| **Key commands** | `goto`, `waitfor`, `rget` (verification after rebuild) |

**Background**: Some Delphi operations destroy and rebuild the entire form or control tree. Typical cases:

| Operation | Behavior | Impact |
|------|------|------|
| Rescan/Re-scan | Close project → reload → rebuild tree view | `TfrmMain` and all its child controls are rebuilt |
| Switch VCL Style | Global resources released → rebuild all forms | All control handles become invalid |
| Project Close/Open | Close current → open new project → reset state | Tree, menus, actions all rebuilt |
| Rebuild index | Clear data → reload → update UI | Dataset-associated controls update |
| Language switch | Release resources → load new language pack → rebuild menu | Menu items may be recreated |

##### O1. Safe Access Pattern After Rebuild (Mandatory)

```
Operation triggered control rebuild
   │
   ├── ① goto TTargetForm
   │     (wait for the form to reappear; default timeout 5s, set 10-15s for rebuild scenarios)
   │
   ├── ② rget key control name
   │     (verify the control has been rebuilt in memory, not just that the window is visible)
   │     assert_expr: "actual in ('True','False')" does not care about value, only that the control exists
   │
   └── ③ Continue subsequent test steps
         (tree node coordinates have changed; offsets need to be recalculated)
```

```json
[
  {"cmd":"click","target":"RescanMenu","note":"Trigger rescan operation"},
  {"phase":"wait","cmd":"waitfor","target":"ProgressBar","prop":"Visible","value":"True","timeout":5000,
   "note":"Wait for Rescan progress bar to appear"},

  {"phase":"wait","cmd":"waitfor","target":"ProgressBar","prop":"Visible","value":"False","timeout":30000,
   "note":"Wait for Rescan progress bar to disappear = operation complete"},

  {"phase":"rebuild","cmd":"goto","target":"TfrmMain","timeout":15000,
   "note":"[Key] Wait for main form controls to rebuild (not just window visibility)"},

  {"phase":"rebuild","cmd":"rget","target":"vstProject.RootNodeCount","note":"Verify tree control has been rebuilt",
   "assert_expr":"actual != ''"},

  {"phase":"rebuild","cmd":"rget","target":"actRescan.Enabled","note":"Verify action has been rebuilt",
   "assert_expr":"actual in ('True','False')"},

  {"phase":"verify","cmd":"capture","target":"rescan_done"},
  {"cmd":"exit"}
]
```

##### O2. `phase: rebuild` Marker

All wait steps after control rebuild must be marked `"phase": "rebuild"`. The meaning of this marker:
- **Audit tool** identifies `rebuild` phase steps and checks whether they contain a `goto` rebuild wait
- If a `rebuild` phase step fails, it **should not** be judged as a test failure, but as an environment/timing issue
- After rebuild, a longer timeout is required than for regular `waitfor` (minimum 10s)

##### O3. Snapshot Comparison Before and After Rebuild

```json
[
  {"phase":"verify","cmd":"capture","target":"before_rescan","note":"Screenshot before rebuild"},
  {"phase":"execute","cmd":"click","target":"BtnRescan"},
  {"phase":"wait","cmd":"waitfor","target":"ProgressBar","prop":"Visible","value":"False","timeout":30000},
  {"phase":"rebuild","cmd":"goto","target":"TfrmMain","timeout":15000},
  {"phase":"verify","cmd":"capture","target":"after_rescan","note":"Screenshot after rebuild"},
  {"cmd":"exit"}
]
```

Python side:
```python
# Use daofy_ocr diff to compare the screen before and after rebuild
diff = daofy_ocr(action="diff", baseline="before_rescan.png", current="after_rescan.png")

# If there is a significant change (diff_pixels > threshold), the rebuild was successful
if diff["diff_pixels"] > 500:
    print(f"✅ Rebuild successful: {diff['diff_pixels']} pixels changed")
else:
    print(f"⚠️ No significant screen change after rebuild: {diff['diff_pixels']} pixels")
```

**Pitfalls**: If `rget` after rebuild returns `NF:xxxx`, it means the control has not been rebuilt yet → increase the `goto` wait time, or retry multiple times; all control references obtained before rebuild become invalid → any `rget` result must not be cached; do not send pipeline commands while the main thread is busy-waiting → first use `waitfor` to wait for async operations to complete.

