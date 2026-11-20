<!-- @when: When consulting the UIAutomation command reference -->

# UIAutomation Command Reference
MCP resource URI: delphi://automation/uia-commands

#### Clicking and Mouse Interaction

| Command | Purpose | Key Parameters |
|------|------|---------|
| `uia.click` | Left-click a control | target, [timeout=10] |
| `uia.rclick` | Right-click a control | target, [timeout=10] |
| `uia.dblclick` | Double-click a control | target, [timeout=10] |
| `uia.hover` | Hover over a control (triggers Tooltip) | target, [timeout=10] |
| `uia.drag` | Drag from target to offset coordinates | target, x, y, [timeout=10] |

Example:
```json
{"cmd": "uia.click", "target": "打开(&O)"}
{"cmd": "uia.drag", "target": "ScrollBar1", "x": 0, "y": 50}
```

#### Value Operations and Input

| Command | Purpose | Key Parameters |
|------|------|---------|
| `uia.set` | Set control value (ValuePattern) | target, text, [timeout=10] |
| `uia.type` | Simulate keyboard typing (SendKeys) | target, text, [timeout=10] |
| `uia.key` | Send keystrokes (Enter/Tab/Esc/Ctrl+S, etc.) | keys, [target] |
| `uia.toggle` | Toggle switch state (CheckBox/RadioButton) | target, [timeout=10] |

Example:
```json
{"cmd": "uia.set", "target": "文件名(N):", "text": "C:\\data\\import.xlsx"}
{"cmd": "uia.key", "keys": "{Enter}"}
```

#### Lists, Trees, and Options

| Command | Purpose | Key Parameters |
|------|------|---------|
| `uia.select` | Select an item (ComboBox/ListBox/Tab/RadioGroup) | target, [item], [timeout=10] |
| `uia.expand` | Expand a collapsible node (Tree/ComboBox dropdown) | target, [timeout=10] |
| `uia.collapse` | Collapse a node | target, [timeout=10] |
| `uia.invoke` | Invoke a control's default action (InvokePattern) | target, [timeout=10] |

Example:
```json
{"cmd": "uia.select", "target": "ComboBox1", "item": "选项二"}
{"cmd": "uia.invoke", "target": "确定"}
```

#### Navigation and Exploration

| Command | Purpose | Key Parameters |
|------|------|---------|
| `uia.goto` | Find and activate a top-level window | target, [timeout=10] |
| `uia.find` | Find a control by condition, return identification info | target, [condition], [scope], [timeout=10] |
| `uia.scan` | Scan the control tree, return structured JSON | [target], [depth=3], [props], [timeout=10] |
| `uia.list` | List child controls (name + type + rectangle) | target, [depth=1], [controltype] |

Example:
```json
{"cmd": "uia.goto", "target": "打开", "timeout": 5000}
{"cmd": "uia.scan", "target": "TTaskDialog", "depth": 5, "props": "name,class,rect"}
```

#### Window Operations

| Command | Purpose | Key Parameters |
|------|------|---------|
| `uia.close` | Close a window | target, [timeout=10] |
| `uia.minimize` | Minimize a window | target, [timeout=10] |
| `uia.maximize` | Maximize a window | target, [timeout=10] |
| `uia.restore` | Restore a window to normal size | target, [timeout=10] |
| `uia.move` | Move a window to specified coordinates | target, x, y, [timeout=10] |
| `uia.resize` | Resize a window | target, width, height, [timeout=10] |
| `uia.state` | Read window state (normal/minimized/maximized) | target, [timeout=10] |

Example:
```json
{"cmd": "uia.close", "target": "TMainForm"}
{"cmd": "uia.move", "target": "TMainForm", "x": 100, "y": 100}
```

#### Scrolling and Viewport

| Command | Purpose | Key Parameters |
|------|------|---------|
| `uia.scroll` | Scroll a control (direction + amount) | target, direction, [amount], [timeout=10] |
| `uia.wheel` | Scroll with the mouse wheel | delta, [target] |
| `uia.scrollinto` | Scroll a child item into the visible area | target, item, [timeout=10] |

Example:
```json
{"cmd": "uia.scroll", "target": "ListBox1", "direction": "down", "amount": 3}
{"cmd": "uia.scrollinto", "target": "ListView1", "item": "最后一条"}
```

#### Property and State Reading

| Command | Purpose | Key Parameters |
|------|------|---------|
| `uia.get` | Read common control properties | target, [prop], [timeout=10] |
| `uia.exists` | Check whether a control exists (does not throw) | target, [timeout=10] |
| `uia.rect` | Get the control's bounding rectangle | target, [timeout=10] |

Supported `prop` values for `uia.get`: `name`, `value`, `enabled`, `automationid`, `classname`, `controltype`, `processid`, `runtimeid`, `isoffscreen`, `iskeyboardfocusable`, `haskeyboardfocus`, `acceleratorkey`, `accesskey`, `helptext`, `itemtype`, `itemstatus`, `culture`, `ispassword`, `labeledby`, `localizedcontroltype`, `orientation`, `frameworkid`, `providerdescription`, `issynchronizedinput`, `boundingrectangle`. When `prop` is omitted, the default return is `name` + `value` + `enabled` + `boundingrectangle`.

Example:
```json
{"cmd": "uia.get", "target": "Edit1", "prop": "value"}
{"cmd": "uia.exists", "target": "保存(&S)", "timeout": 3}
```

#### Visualization

| Command | Purpose | Key Parameters |
|------|------|---------|
| `uia.screenshot` | Capture a screenshot of a control/window region | target, [path], [region], [timeout=10] |

`region` parameter format: `[left, top, width, height]`, relative to the target control's client area coordinates. When `region` is omitted, the full control area is captured.

**Screenshot Fallback Strategy**: `uia.screenshot` is based on UIA `CaptureToImage()` and may output a black screen for DirectX 3D scenes. When a black screen is detected, fall back using the following process:
1. `uia.rect` → get the target's screen pixel rectangle
2. `mss` screenshot → capture that region by pixel coordinates (DXGI/BitBlt, can capture 3D content)
3. If `mss` still shows a black screen → the rendering layer is OpenGL / hardware overlay / DRM-protected content and cannot currently be automated

Example:
```json
{"cmd": "uia.screenshot", "target": "TMainForm", "path": "mainform.png"}
{"cmd": "uia.screenshot", "target": "TMainForm", "region": [0, 0, 200, 50], "path": "titlebar.png"}
```

#### Waiting and Synchronization

| Command | Purpose | Key Parameters |
|------|------|---------|
| `uia.wait` | Wait for a control to satisfy a condition | target, [timeout=30], [condition=exist] |

`condition` values: `exist` (default, wait for appearance), `notexist` (wait for disappearance), `enabled` (wait for enabled), `visible` (wait for visible), `ready` (wait for idle, `WindowPattern.WaitForInputIdle()`).

Example:
```json
{"cmd": "uia.wait", "target": "保存(&S)", "timeout": 15, "condition": "enabled"}
{"cmd": "uia.wait", "target": "进度对话框", "timeout": 60, "condition": "notexist"}
```

#### Find Strategies

| Method | Format | Description |
|------|------|------|
| Control text (Name) | `"target text"` | Match by the control's Name property (most common) |
| AutomationId | `#idValue` | Exact match by AutomationId |
| Class name | `.ClassName` | Match by ClassName, case-insensitive |
| Control type | `@ControlType` | Find by UIA ControlType |
| Composite condition | `condition1 && condition2` | Match both text and class name, joined with `&&` |
| Coordinate point (nearest first) | `(x,y)` | Find the nearest control upward from the specified point |

Example:
```json
{"cmd": "uia.click", "target": "打开(&O)"}
{"cmd": "uia.click", "target": "#btnSave"}
```

#### Common Parameters

All `uia.xxx` commands share the following optional parameters:

| Parameter | Type | Default | Description |
|------|------|--------|------|
| `timeout` | int | 10 | Control lookup timeout (seconds); throws if not found before timeout |
| `condition` | string | — | Used only by `uia.wait`; ignored by other commands |
| `depth` | int | — | Lookup depth; if unspecified, searches all depths |
| `scope` | string | `"children"` | Search scope for `uia.find` / `uia.scan`: `children` / `descendants` / `all` |
| `found_index` | int | 1 | Which match to select when multiple are found (1-indexed) |

Example:
```json
{"cmd": "uia.click", "target": "打开(&O)", "timeout": 15, "depth": 3}
{"cmd": "uia.get", "target": ".Edit", "prop": "value", "found_index": 2}
```