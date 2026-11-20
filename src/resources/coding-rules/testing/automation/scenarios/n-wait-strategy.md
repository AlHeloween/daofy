<!-- @when: Eliminate fixed delays and use conditional waits (waitfor/goto) instead of bare wait -->
<!-- @part-of: ui-testing -->

#### N. Waiting and Conditional Synchronization — Disable Bare Fixed Delays

| Element | Content |
|------|------|
| **Goal** | Eliminate the fragile waiting pattern of `{"cmd": "wait", "ms": fixed value}` and replace it with condition-triggered waiting |
| **Strategy** | `waitfor` property wait → `goto` form wait → `wait` only as last resort |
| **Key commands** | `waitfor`, `goto`, `wait` (fallback only) |

**Background**: Fixed delay `wait 500ms` wastes time on fast machines and is insufficient on slow machines. Test authors cannot predict the performance of the CI environment. Conditional waiting (`waitfor` + property/state) automatically adapts to any execution speed.

##### N1. `waitfor` Priority Rules (Mandatory)

```
Waiting for a state
├─ Wait for a control to become visible/enabled
│  ├─ Has a target form → goto TTargetForm (built-in 5s timeout polling)
│  └─ Need to check a property → waitfor target prop value timeout
├─ Wait for status bar change → waitfor StatusBar Caption "Success" timeout=5000
├─ Wait for dialog to appear → msgscan + assert_expr
├─ Wait for async task to complete
│  ├─ LLM API and other backends → waitfor StatusBar Caption "Done" timeout=120000
│  └─ Cannot poll properties → loop capture + OCR diff to detect screen changes
└─ Wait for a fixed duration (only for non-conditional scenarios)
   └─ wait ms=300 (such as animation playback, input debouncing; maximum 1000ms)
```

| Should avoid ❌ | Should use ✅ |
|-----------|----------|
| `{"cmd":"wait","ms":1200}` | `{"cmd":"goto","target":"TfrmSettings","timeout":5000}` |
| `{"cmd":"wait","ms":3000}` | `{"cmd":"waitfor","target":"StatusBar","prop":"Caption","value":"Ready","timeout":5000}` |
| `{"cmd":"wait","ms":120000}` | `{"cmd":"waitfor","target":"lblStatus","prop":"Caption","value":"Translation complete","timeout":130000}` |
| `{"cmd":"wait","ms":500}` | Only for very small delays for UI animation (`< 1000ms`) |

##### N2. Default Timeout Table

| Scenario | Suggested timeout | Description |
|------|---------|------|
| Main form goto/ready | 10-15s | Includes splash/startup animation |
| Dialog open waitfor/goto | 3-5s | Normal modal dialog |
| Status bar change waitfor after operation | 5s | Regular operations such as save/delete/import |
| File open/save dlgfile | 10s | OpenDialog/SaveDialog |
| Network request/LLM API | 120s+ | Backend response is uncertain; set sufficiently long |
| Right-click menu popup | 2-3s | TPopupMenu popup |
| Data refresh/rebuild | 10-30s | Heavy operations such as Rescan/Reload |

##### N3. Async Operation Waiting Patterns

For operations with uncertain duration such as LLM translation and file batch processing, layered waiting is recommended:

```json
[
  {"cmd":"click","target":"BtnBatchTranslate"},

  {"phase":"perceive","cmd":"waitfor","target":"ProgressBar","prop":"Visible","value":"True","timeout":5000,
   "note":"Wait for progress bar to appear, confirming the task has started"},

  {"phase":"perceive","cmd":"waitfor","target":"StatusBar","prop":"Caption","value":"Translation complete","timeout":180000,
   "note":"Wait for asynchronous translation to complete (up to 3 minutes)"},

  {"phase":"verify","cmd":"rget","target":"vstProject.RootNodeCount","assert_expr":"int(actual)>0","note":"Verify tree data"},
  {"phase":"verify","cmd":"capture","target":"translate_done"}
]
```

If the target process has no visible state property that can be polled, use screenshot comparison:

```python
# Python polling: capture + OCR diff every 5 seconds until the screen is stable or timeout
import time
last_checksum = None
for i in range(36):  # up to 3 minutes
    r = daofy_ocr(action="diff", baseline="prev_screenshot.png", current="current.png")
    if r["diff_pixels"] < 50:  # screen is basically stable
        break
    time.sleep(5)
```

**Pitfalls**: `waitfor` property value comparison is string equality → numeric properties need Python-side assertions; the default `goto` timeout is 5s and can be adjusted with the `timeout` parameter; the minimum granularity allowed for `wait` is 100ms, but it is only used for UI animation synchronization (maximum 1000ms).

