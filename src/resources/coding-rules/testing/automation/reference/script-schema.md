<!-- @when: Writing or modifying an automate_delphi GUI script -->
<!-- @chain: after=script-generation-workflow.md -->

# Automation Script Format Specification

The script passed to `automate_delphi(action="gui", script=...)` can be:

- a complete script object containing a `steps` array;
- a step object array directly;
- a JSON string or file path in either of the above shapes.

When saving reusable scripts, the complete object is recommended; Daofy will preserve fields other than `steps` as `script_metadata` for use in execution results.

MCP resource URI: `delphi://automation/script-schema`.

## Script Metadata

Reusable scripts should declare the test level:

```json
{
  "test_name": "customer-create-smoke",
  "test_level": "black-box",
  "callgraph_diagnostics": false,
  "env": {
    "DEEPSEEK_API_KEY": "temporary value for this run"
  },
  "steps": []
}
```

`env` / `environment` are optional top-level script fields for temporary child-process
environment overrides. They are applied only when the tested application process is
started, are not persisted to User/Machine environment variables, and returned reports
redact values to `{count, names}`. Passing `null` unsets an inherited variable for the
tested process. With `keep_alive=true`, a cached tested process is reused only when the
requested environment is the same; changing `env` restarts the tested process.

Test level descriptions:
- `black-box` — real user workflows through visible UI entry points.
- `gray-box` — use RTTI reads/calls for diagnostics, fixtures, or project-specific probes.
- `white-box` — directly inspect business methods or the data layer.

Black-box `execute` steps must not use `rcall`, `rset`, or `delphi_rtti(action="call")`. These commands bypass the real UI path. If a script needs them, mark it `gray-box` or `white-box` and explain why in `goal` or `note`.

**Compliance check**: run `grep 'rcall' tests/**/*.json` to confirm no Black-box script contains RTTI execution commands. Zero matches means compliant.

When `callgraph_diagnostics=true`, if a failed step declares `handler` / `entry` / `callgraph_target`, Daofy appends a `callgraph(direction=callers)` query before automatic exit and writes the summary into `report.first_failure.diagnostics.callgraph`. It is disabled by default to avoid extra overhead for ordinary UI tests.

Optional global configuration:

```json
{
  "callgraph_diagnostics": true,
  "callgraph_options": {
    "max_depth": 2,
    "edge_limit": 20,
    "project_only": true,
    "include_prefixes": ["main."]
  },
  "steps": [
    {"cmd": "click", "target": "btnSave", "handler": "main.TfrmMain.SaveIfModified"}
  ]
}
```

## Step Fields

```json
{
  "phase": "perceive | execute | verify",
  "cmd": "rget",
  "target": "BtnSave.Caption",
  "handler": "main.TfrmMain.SaveIfModified",
  "expected": "Save button caption is correct",
  "assert_expr": "actual == '保存'",
  "note": "Explanation for human and AI planning"
}
```

Field descriptions:
- `phase` — used for report grouping.
- `cmd` — Daofy automation command.
- `target` and command-specific fields (`prop`, `value`, `timeout`, `text`, `params`, `props`, etc.).
- `expected` — human-readable expected behavior.
- `assert_expr` — Python assertion expression evaluated by Daofy.
- `note` — reasoning process or source-derived context.
- `handler` / `entry` / `callgraph_target` — optional source entry function name, used for attaching callgraph diagnostics to failure reports and test selection.
- `callgraph_diff` steps may use `baseline` or `baseline_path`, `compare_by=name|addr|full`, `save_as`; `save_as` must be a relative JSON path under `snapshots_dir`, and file-based snapshot inputs such as `baseline_path` must resolve to a path still within `snapshots_dir`.
- When `cmd` has the `uia.xxx` prefix, it is executed through Python UIA (uiautomation library) and does not go through the Delphi pipe. All `uia.xxx` commands run inside the Python process and can access any UIA-compatible control—Delphi, Win32, WPF, Qt, Chrome, system dialogs, etc. **Non-injection black-box**: no need to modify the application under test.
  > The `via` field (old approach) is deprecated; use the `uia.xxx` command prefix uniformly. `via: "uia"` is compatible during migration, but new scripts must not use it.

> See `delphi://automation/uia-commands` for the complete UIA command table.

### dumpstate Property Whitelist

`dumpstate` accepts a `props` parameter (comma-separated property name list); the Delphi inline unit outputs only these properties (skipping the `IsSkippedProp` blacklist). This avoids pipe overflow and speeds up responses:

```json
{"cmd": "dumpstate", "props": "caption,enabled"}
{"cmd": "dumpstate", "props": "name,class,caption,items"}
{"cmd": "dumpstate"}  // outputs all properties by default
```

When using Daofy MCP tools, `props` is forwarded from the step JSON to the Delphi pipe. For tools that only send `cmd`/`target`, the property list can be passed through the `target` field:

```json
{"cmd": "dumpstate", "target": "caption,enabled"}
```

### Generic RTTI Item Click

`click` supports the `ControlName@ItemCaption` syntax, finding and clicking items in any `TCollection` property through generic RTTI without calculating coordinates:

```json
{"cmd": "click", "target": "cbMenus@打开工程..."}
```

The Delphi inline unit uses pure RTTI to read each item's `Caption` (or fall back to `Text`) and `Bounds` (Left/Top/Right/Bottom), then clicks the center of the matching item. No VCL type binding is required; any `TCollection`-based control is supported.

### Coordinate Click

Coordinates for coordinate clicks are client-area coordinates relative to the target control. The recommended format is `"target": "ControlName@x,y"` so scripts are reusable—the Delphi inline unit recognizes it directly. Newer Daofy also accepts the `"target": "ControlName", "x": 10, "y": 20` format for `click` and automatically converts it to the same wire protocol.

**Prefer title-based clicks** (menus, lists, category buttons, and other collection controls), as they are more robust to layout changes and DPI scaling.

### textbounds Locates Control Bounds by Text

`textbounds` locates the client-area bounding rectangle of matching text in a control by intercepting GDI/GDI+ text drawing functions (paint-hook), replacing OCR. Two modes:

- `paint` — paint-hook only (intercepts text drawing, generic, supports any control including third-party/custom-drawn/FMX)
- `type` — type-bound only (dispatches by control type, covering standard VCL controls: TListBox/TComboBox/TTreeView/TListView/TPageControl/TTabControl/TMemo/TRichEdit)
- `auto` — paint-hook first, fall back to type-bound on failure (default)

```json
{"cmd": "textbounds", "target": "ListBox1@打开工程", "mode": "auto"}
{"cmd": "textbounds", "target": "Panel1", "text": "保存", "mode": "paint", "include_invisible": false}
```

Field descriptions:
- `target` — control name (the old `ControlName@searchText` syntax is compatible; text can also be provided separately via the `text` field).
- `text` — search text (choose one of this and the text after `@` in `target`).
- `mode` — `paint`/`type`/`auto`, default `auto`.
- `include_invisible` — whether to include completely invisible records (default `false`, for diagnostics only).

Return value (`response.state` is automatically deserialized):
- Simple mode (type-bound): `{"x":..,"y":..,"width":..,"height":..}`
- Rich mode (paint-hook) additionally contains:
  - `visible_state` — `full`/`partial`/`invisible`/`unknown` (text visibility)
  - `clipped` — whether clipped (`true`/`false`)
  - `clip_x`/`clip_y`/`clip_width`/`clip_height` — clipping rectangle (when clipped=true)
  - `visible_x`/`visible_y`/`visible_width`/`visible_height` — visible rectangle
  - `api` — source API (`ExtTextOutW`/`DrawTextExW`/`GdipDrawString`, etc.)

Error codes: `NO_TARGET`/`NO_TEXT`/`NO_FORM`/`NF:<control name>`/`TXT_NF`/`PAINT_NF` (paint mode not found).

#### Scope and Limitations (Must Read)

The `textbounds` paint-hook only intercepts **GDI (gdi32.dll) and GDI+ (gdiplus.dll)** text drawing functions. **It does not cover Direct2D / DirectWrite / MIL / Skia / Blink / Qt RHI or other rendering stacks.**

Coverage by UI stack:

| UI Stack | Rendering Method | textbounds Coverage | Recommended Tool |
|--------|---------|:---:|------|
| VCL standard/custom-drawn controls | GDI | ✅ | `textbounds` |
| Third-party GDI libraries (DevExpress/TMS, etc.) | GDI | ✅ | `textbounds` |
| FMX (Windows platform) | GDI+ | ✅ | `textbounds` |
| **DirectUI** (Win8+ system components, Ribbon, modern view of new file dialogs) | Direct2D + DirectWrite | ❌ | `uiascan`/`uiaget` (DirectUI implements UIA Provider) |
| **WPF** | MIL/Direct2D | ❌ | `uia.*` commands |
| **UWP / WinUI 3** | XAML + Direct2D | ❌ | `uia.*` commands |
| **Electron / WebView2** | Blink / Skia | ❌ | `capture` + `daofy_ocr` |
| **Qt Quick** | OpenGL / RHI | ❌ | `capture` + `daofy_ocr` |
| **Legacy system dialogs** (`GetOpenFileName`, `MessageBox`, classic view of `TOpenDialog`) | GDI | ✅ | `textbounds` (but see the trap below when mixed with modern views) |

**DirectUI mixed-rendering trap**: Modern Windows 8+ file dialogs (`IFileOpenDialog`) and similar are **mixed-rendering**—the dialog frame and classic controls use GDI, but the new-style view in the file list area uses DirectUI. `textbounds` can only obtain the GDI part and cannot get the text of file list items. In this scenario, use `uiascan`.

**When not to choose textbounds**:
- The target control is inside WebView/browser → use `capture` + `daofy_ocr`
- The target is a WPF/UWP/Electron/Qt window → use `uia.*` or `capture` + `daofy_ocr`
- The target is a file list item in a system dialog (DirectUI part) → use `uiascan`, not `textbounds`
- The target control is known to be a standard VCL type (TListBox/TComboBox/TTreeView/TListView/TPageControl, etc.) and text can be read through RTTI → use `rget` directly, faster and more accurate

## Assertion Rules

`assert_expr` is an expression evaluable in Python; `__builtins__` is empty, and the explicitly available variables are:

| Variable | Meaning |
|------|------|
| `actual` | String value extracted from the command response |
| `re` | Python `re` module |
| `len`, `str`, `int`, `float`, `bool` | Explicitly provided helper functions |

Examples:

```json
{"cmd": "rget", "target": "EditName.Text", "assert_expr": "actual == '张三'"}
{"cmd": "rget", "target": "BtnSave.Enabled", "assert_expr": "actual == 'True'"}
{"cmd": "waitfor", "target": "StatusBar", "prop": "Caption", "value": "完成", "assert_expr": "actual == 'ok'"}
{"cmd": "rget", "target": "PhoneEdit.Text", "assert_expr": "re.search(r'^1\\\d{10}$', actual)"}
```

Natural language must not be written in `assert_expr`. Put explanatory text in `expected`, and add real verification steps:

```json
{"cmd": "msgscan", "expected": "No unexpected dialogs", "assert_expr": "actual == 'NOD'"}
```

`msgscan` returns `NOD` when there is no MessageBox, and returns `OK` when there is a MessageBox, writing the dialog JSON to `_formstate.json` for use by `response.state`.

## OCR / Visual Verification

For native OS dialogs or custom-drawn controls that cannot be read via `rget`/`msgscan`, use `capture` + `daofy_ocr` for verification:

```json
{"cmd": "capture", "expected": "Dialog screenshot for OCR", "note": "After execution, read with daofy_ocr recognize"}
```

**Selected-row detection** (color threshold):
- After `capture`, use `daofy_ocr color region=[x,y,w,h] threshold=0.5`.
- `light_brightness` < 0.98 and no `>` expander = selected.
- Best granularity: `8x8` blocks, left edge `X=105` (to avoid text interference).

See `delphi://automation/script-generation-workflow` for complete native dialog handling patterns.

## Cached Test Files

Persist reusable scripts under the tested project root:

```
<project-root>\Tests\<测试类型>\<测试名>.json
```

Common category directories: `黑盒测试`, `回归测试`, `灰盒测试`, `白盒测试`, `冒烟测试`.

File format:

```json
{
  "test_name": "Create Customer - Success Path",
  "app_path": "C:/App/CustomerApp.exe",
  "target_form": "TNewCustomerForm",
  "version": 1,
  "created": "2026-06-27T10:30:00",
  "updated": "2026-06-27T10:35:00",
  "run_count": 0,
  "source_hash": "a1b2c3d4e5f6a7b8",
  "source_files": ["UnitCustomer.pas", "UnitCustomer.dfm"],
  "steps": []
}
```
## Cached Test File

Persist reusable scripts under the tested project root:

```text
<project-root>\Tests\<测试类型>\<测试名>.json
```

Common test type directories are `黑盒测试`, `回归测试`, `灰盒测试`, `白盒测试`,
and `冒烟测试`. Choose the directory by the long-term rerun purpose.

Use this file shape:

```json
{
  "test_name": "Create Customer - Success Path",
  "app_path": "C:/App/CustomerApp.exe",
  "target_form": "TNewCustomerForm",
  "version": 1,
  "created": "2026-06-27T10:30:00",
  "updated": "2026-06-27T10:35:00",
  "run_count": 0,
  "source_hash": "a1b2c3d4e5f6a7b8",
  "source_files": ["UnitCustomer.pas", "UnitCustomer.dfm"],
  "steps": []
}
```

