<!-- @when: When you need to choose an automation command/tool based on the scenario -->
<!-- @see: controls-operation-reference.md (look up recommended commands and pitfalls by control type) -->
# Automation Capability Selection Matrix

MCP URI: `delphi://automation/capability-matrix`

## Automation Capability Classification Table

When selecting automation commands, the LLM should first determine the scenario using the flow below, then choose a capability from the scenario table.

### Quick Decision Flow

```
Is the target UI inside the Delphi process?
  ├─ Yes → Has RTTI/source? →RTTI (rget/rset/rcall/rinspect) | No→black-box (click/type/key/waitfor/capture)
  ├─ No → OS dialog? →File→dlgfile | Folder→dlgfile path=directory | Message→msgscan+msgclick/close | Other→UIA
  ├─ No → Browser? →Chrome layer→UIA | Web page DOM→Playwright/Selenium | Visible in screenshot→OCR
  └─ No → Third-party Windows app? →Has UIA→UIA | Win32 messages only→msgscan/click/close | Neither available→OCR
```

### Scenario → Capability Mapping

| # | Scenario | Test Type | Recommended Command | Optional/Fallback | Not Usable | Rationale |
|---|------|---------|---------|----------|-------|------|
| 1 | **Read Delphi component properties** | White-box/gray-box | `rget` | — | `uia.get` | RTTI exposes all published properties; UIA reads only Name/Value/ControlType |
| 2 | **Modify Delphi component properties** | White-box/gray-box | `rset` | `click` (Toggle only) | `uia.set` | RTTI writes properties directly; black-box tests should use click to simulate user actions |
| 3 | **Call Delphi component methods** | White-box/gray-box | `rcall` | — | `click` | RTTI method invocation is the most precise; use only for test fixture initialization/diagnostics |
| 4 | **Inspect Delphi component structure** | White-box/gray-box | `rinspect` (supports visibility parameter) | — | `uia.scan` | RTTI returns complete type information; UIA returns only limited properties |
| 4b | **RTTI unit testing** | White-box/gray-box | `automate_delphi(action="test")` | `run_tests` (underlying protocol) | `rcall` (single step) | Dual mode via `target/className`; supports `RegisterTestClass`, `RegisterFixture`, constructor/method parameters, overloads, `expected`, `expected_exception`, `assert_expr`, per-case timeout, and stable statistics. For details, see `delphi://automation/rtti-test-runner` |
| 5 | **Operate Delphi controls as black box** | Black-box | `click` | — | `rcall`/`rset` | click simulates real user actions and does not depend on internal implementation |
| 6 | **Enter text into a Delphi input box** | Black-box | `type` | — | `rset` | Black-box testing should simulate the complete user typing behavior |
| 7 | **Send keyboard keys** | Black-box | `key` | — | — | key sends virtual-key codes |
| 8 | **Wait for control state** | All | `waitfor` | — | `time.sleep` | waitfor performs internal polling + timeout and does not block the event loop |
| 9 | **Get a Delphi window UI snapshot** | All | `formsum`/`dumpstate` | — | `uia.scan` | Returns structured JSON including component hierarchy/property values |
| 10 | **List all top-level windows** | All | `listwnd` | `uia.scan` | — | listwnd enumerates all visible HWNDs |
| 11 | **Drag controls** | Black-box | `drag` | — | — | The pipeline natively supports drag |
| 12 | **Screenshot comparison regression verification** | All | `capture` + OCR `diff` | — | — | capture takes pipeline screenshots; diff compares pixels |
| 13 | **OS file open/save dialog** | All | `dlgfile` | — | `click` to locate the file name box | dlgfile operates via HWND |
| 14 | **Locate control bounds by displayed text** (replaces OCR) | All | `textbounds` | `capture`+OCR `recognize` or `uia.*` | — | ⚠️ **Covers only the GDI/GDI+ rendering stack** (VCL/FMX Windows/third-party GDI libraries); **does not cover DirectUI/WPF/UWP/Electron/Qt Quick** (use `uia.*`), and does not cover WebView (use OCR). See the "Scope and Limitations" section of textbounds in `script-schema.md` |

### OS Dialog Special Cases

| # | Dialog Type | Recommended Strategy | Steps |
|---|---------|---------|------|
| 14 | **MessageBox/confirmation dialog** | `msgscan` + `msgclick`/`msgclose` | ① msgscan polling; ② msgclick (button text) or msgclose (WM_CLOSE) |
| 15 | **Open file dialog** (TOpenDialog) | `msgscan` + `dlgfile` | ① msgscan detection; ② dlgfile path="C:\\file.txt" |
| 16 | **Save file dialog** (TSaveDialog) | Same as above | Same as above; automatically creates the file if it does not exist |
| 17 | **SHBrowseForFolder folder selection** | `dlgfile path=directory` | Prefer dlgfile; if unsupported → uia.scan to find TreeView (classic)/uia.get to find the address bar Combobox → type path → key Enter |
| 18 | **System color/font dialog** | `uia.xxx` (fallback OCR) | First probe with uia.scan; when UIA is unavailable, use OCR visual localization |
| 19 | **UAC elevation dialog** | ❌ Cannot be automated | It is on the secure desktop; UIA/messages/OCR cannot access it |

### Full UIA Command Set (Non-Injected Black Box)

Operate UIA-compatible controls cross-process via the Python uiautomation library, without modifying the source code of the application under test.

| Command | Purpose | Key Parameters |
|------|------|---------|
| `uia.click` | Left-click control | target, timeout |
| `uia.rclick` | Right-click control | target, timeout |
| `uia.dblclick` | Double-click control | target, timeout |
| `uia.hover` | Hover over control | target, timeout |
| `uia.drag` | Drag to offset | target, x, y |
| `uia.set` | Set text value | target, text, timeout |
| `uia.type` | Keyboard typing | target, text, timeout |
| `uia.key` | Send keys | keys |
| `uia.toggle` | Toggle switch state | target, timeout |
| `uia.select` | Select list item | target, item, timeout |
| `uia.expand` | Expand node | target, timeout |
| `uia.collapse` | Collapse node | target, timeout |
| `uia.invoke` | Invoke default action | target, timeout |
| `uia.goto` | Activate/focus window | target, timeout |
| `uia.find` | Find control | target, condition, depth |
| `uia.scan` | Scan control tree | target, depth, props |
| `uia.list` | List child controls | target, depth |
| `uia.get` | Read property | target, prop, timeout |
| `uia.exists` | Determine existence | target, timeout |
| `uia.state` | Read window state | target, timeout |
| `uia.close` | Close window | target, timeout |
| `uia.minimize` | Minimize | target, timeout |
| `uia.maximize` | Maximize | target, timeout |
| `uia.restore` | Restore window | target, timeout |
| `uia.move` | Move window | target, x, y |
| `uia.resize` | Resize | target, width, height |
| `uia.scroll` | Scroll control | target, direction, amount |
| `uia.wheel` | Mouse wheel | delta |
| `uia.scrollinto` | Scroll item into view | target, item |
| `uia.screenshot` | Screenshot | target, path |
| `uia.wait` | Wait for condition | target, timeout, condition |
| `uia.rect` | Get bounding rectangle | target |

### OCR Visual Capabilities (pip install daofy-for-delphi[ocr])

| Command | Purpose | Applicable Scenarios | Not Suitable For |
|------|------|---------|-------|
| `recognize` | Recognize text in images | Web page content, custom-drawn controls, virtualized desktops, UI unreachable by UIA | Hundreds of milliseconds; accuracy drops when text is occluded or too small |
| `detect` | Detect text box positions in images | When you need to click a specific text area by coordinates | For pure structural verification, prefer rget/uia.get |
| `color` | Analyze the color of a specified region | Verify indicator light state, UI theme color, abnormal color alerts | Exact color values require a baseline |
| `match` | Icon template matching | Find the image position of a specific icon/button | Matching fails when icon size/color varies greatly |
| `diff` | Compare two screenshots | Pixel-level UI differences in regression testing | Animations/short-lived state transitions cause false positives |

## Capability Selection: Scenario-Based Decision Guide

Format: **first choice → fallback → last resort**, with ❌ marking forbidden options.

### Delphi In-Process Control Operations

| Scenario | Gray-box (with RTTI/source) | Black-box (UI entry only) | Forbidden |
|------|---------------------|-------------------|------|
| **Click buttons/menus/links** | `click` | `click` | ❌ `rcall`/`rset` |
| **Read properties** | `rget` → `uia.get` | `rget` → `uia.get` | ❌ Black-box rcall/rset; rget is read-only and can be used |
| **Write to input box** | `rset` → `type` | `type` → `uia.set` | ❌ Black-box rset |
| **Wait for control readiness** | `waitfor` | `waitfor` → `uia.wait` | ❌ Bare `time.sleep` |
| **Get UI snapshot** | `dumpstate`/`formsum` | `dumpstate` (safe properties only) → `uia.scan` | ❌ Black-box rcall triggering getters |
| **Send keyboard keys** | `key` | `key` | — |
| **Drag** | `drag` | `drag` → `uia.drag` | — |
| **Context menu** | `rclick` | `rclick` → `uia.rclick` | — |

### Dialog Handling

| Dialog Type | Identification | Operation | Fallback | Forbidden |
|---------|------|------|------|------|
| **MessageBox** | `msgscan` | `msgclick`/`msgclose` | — | ❌ Direct uia.click by coordinates |
| **VCL Form modal** (fsModal) | `dlgscan` | `dlgclick` | `uia.scan` + `uia.click` | ❌ Bare coordinate click |
| **TTaskDialog** | `uia.scan` | `uia.click` (button text) | — | ❌ msgscan cannot detect it |
| **IFileDialog** (Win10+) | `uia.goto` (find title) | `uia.set` (file name) + `uia.click` (confirm) | `capture` + OCR | ❌ msgscan/dlgfile |
| **TOpenDialog/TSaveDialog** (classic) | `msgscan` | `dlgfile path=...` | `uia.goto` + `uia.set` + `uia.click` | ❌ Coordinate click on file name box |
| **SHBrowseForFolder** | `uia.scan` | `dlgfile path=target directory` | `uia.scan` to find TreeView + `uia.type` address bar + `key` Enter | ❌ Bare keyboard navigation |
| **Color/font dialog** | `uia.scan` | `uia.click`/`uia.set` | `capture` + OCR | ❌ msgscan |
| **VCL Style themed dialog** | `msgscan`/`dlgscan` | Regular pipeline commands | — | — |
| **UAC elevation dialog** | ❌ Cannot be automated | Requires disabling UAC or manual confirmation | — | — |

### Cross-Process / Third-Party Application Operations

| Scenario | First Choice | Fallback | Forbidden |
|------|------|------|------|
| **Activate/focus external window** | `uia.goto` | — | ❌ `goto` (Delphi in-process only) |
| **Click external control** | `uia.click` | `uia.invoke` (when click fails) | ❌ `msgclick` |
| **Read external control text** | `uia.get` | OCR `recognize` | ❌ `rget` |
| **Scan external window control tree** | `uia.scan` | — | ❌ `dump