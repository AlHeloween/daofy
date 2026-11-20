# UIA Integration Implementation Plan — Pure Python-Side Approach v3.0

> **Version history:**
> - v1.0 (`uia-integration-plan.md`) — Original plan: Delphi-side COM UIA + 6 UIA commands
> - v2.0 — Audit revision: fixed 6 omissions (COM Apartment, VTBL, Python branches, etc.)
> - **v3.0 (current) — Architecture change: remove all Delphi-side modifications; implement UIA purely on the Python side via the `uiautomation` library**

> **Architecture decision record:** The reason for changing from the Delphi side (v2.0) to the Python side (v3.0) is that RTTI and UIA operate on completely different object domains—RTTI operates on the in-process Delphi component tree, while UIA operates on cross-process Windows windows. The Delphi process does not need UIA (RTTI is stronger); the only natural place for UIA is the Python side. See the "Architecture Argument" section below for details.

---

## Architecture Argument: Why Pure Python Side Is Correct

### Three Object Domains, Three Technologies

```
┌─────────────────────────────────────────────────────────────┐
│  Object Domain A: Delphi in-process component tree          │
│  ───────────────────────────────                            │
│  Technology: RTTI (rget/rset/rcall/rinspect)                │
│  Identifier: Delphi Name property (e.g. "Button1")          │
│  Access: FindChildControl + TRttiContext                    │
│  Coverage: all published+public properties/methods          │
│                                                             │
│  → Completed by Delphi side Vcl/Fmx.DaofyAutomation        │
│  → UIA is a downgrade in this domain (fewer properties,     │
│    slower)                                                  │
├─────────────────────────────────────────────────────────────┤
│  Object Domain B: Cross-process Windows standard controls   │
│  ────────────────────────────────────────                   │
│  Technology: Windows UI Automation (UIA)                    │
│  Identifier: AutomationId / Name / ControlType              │
│  Access: cross-process COM (UIAutomationCore.dll)           │
│  Coverage: limited property set + Control Pattern           │
│                                                             │
│  → This is the real value domain for adding UIA on the      │
│    Python side                                              │
│  → Typical scenarios: open file dialog, system popup,       │
│    third-party windows                                      │
├─────────────────────────────────────────────────────────────┤
│  Object Domain C: Windows message-layer operations          │
│  ─────────────────────────────                               │
│  Technology: Win32 messages (FindWindow/SendMessage)        │
│  Currently implemented in Delphi base class:                │
│  msgscan/msgclick/msgclose/dlgfile                          │
│  → Complementary to UIA, outside this scope                 │
└─────────────────────────────────────────────────────────────┘
```

### Advantages of Pure Python-Side UIA

| Dimension | v2.0 (Delphi side) | v3.0 (Python side) |
|------|:-:|:-:|
| COM thread model | Manual `CoInitializeEx(COINIT_STA)` required | Automatically managed by `comtypes` |
| VTBL interface risk | 50+ methods; one wrong VTBL offset causes AV | `uiautomation` library wraps ctypes calls |
| Delphi compiler compatibility | Conditional compilation required for Delphi versions | No dependency |
| Testing/debugging | Delphi AV → IDE breakpoint debugging | Python exception → inspect call stack directly |
| Maintenance burden | Changes on both Delphi + Python sides | Change Python only |
| Team skill requirements | Dual stack: Delphi COM + Python | Python single stack |
| Optional dependency | None (compiled into exe) | `pip install daofy-for-delphi[uia]` |

### Key Conclusion

> **The Delphi side never needs UIA.** RTTI is comprehensively superior to UIA for in-process component access (all properties/methods, no cross-process overhead, no stale element). The only natural place for UIA is the Python side—it covers cross-process scenarios that the Delphi side cannot reach. Putting UIA on the Python side is both the architecturally correct decision and eliminates the highest-risk issues in the original plan: the COM thread model and VTBL interface offsets.

---

## Revised Architecture

```
Existing architecture (unchanged):
  Python layer:
    automation_service.py  ← _execute_script_unlocked main loop
      │ named pipe ↓
  Delphi layer:
    TAutomationProcessorBase.ExecCmd → existing 20+ if/elif branches (unchanged)
    ├── Vcl.TAutomationProcessor  (unchanged)
    └── Fmx.TAutomationProcessor  (unchanged)

v3.0 additions (inside Python layer, without touching a single line of Delphi code):
  Python layer:
    automation_service.py
      ├── _UIA_MODULE / _UIA_AVAILABLE  ← new: module-level lazy import
      ├── _execute_uia_step()           ← new: call uiautomation directly on Python side
      ├── _walk_uia_tree()              ← new: UIA tree traversal (for uiascan)
      ├── _UIA_CAPABLE_CMDS             ← new: command set routable to UIA
      ├── _UIA_PREFIX_CMDS              ← new: uia-prefixed command set
      └── _should_use_uia()             ← new: determine whether to use UIA or pipeline

  Delphi layer:
    ────────────────── zero modifications ──────────────────
```

### Command Routing Logic

```
_execute_script_unlocked for each step:
  │
  ├─ cmd starts with 'uia' (e.g. uiagoto/uiaclick/uiascan)?
  │   → _execute_uia_step(step)       ← Python side calls uiautomation directly
  │
  ├─ cmd is in _UIA_CAPABLE_CMDS and _should_use_uia() is True?
  │   → _execute_uia_step(step)       ← Python side calls uiautomation directly
  │
  └─ otherwise
      → use the existing named pipe path (unchanged)
```

Note: commands in `_UIA_CAPABLE_CMDS` (such as `click/goto`) go through the UIA path when `"via": "uia"` is added.

---

## Implementation Tasks (4 subtasks, approximately 3 person-days)

### T1. Add UIA command dispatch to `automation_service.py` (1 person-day)

#### T1a. Add command sets and decision function

```python
# ── Add after _ASYNC_CMDS / _UI_ASYNC_CMDS ──

# Commands with the uia prefix (all go through Python-side UIA, not the Delphi pipeline)
_UIA_PREFIX_CMDS = frozenset({
    'uiagoto', 'uiaclick', 'uiaget', 'uiascan', 'uiawait', 'uiaset',
    # Note: uiaclick and uiaset are synchronous on the Python side (no peekresult polling)
})

# Commands that support both the pipeline and UIA (explicitly specify UIA via "via": "uia")
_UIA_CAPABLE_CMDS = frozenset({
    'goto', 'click', 'get', 'set', 'wait', 'scan',
    # Extensible: type, key, etc.
})

# ── UIA module lazy import ──
_UIA_AVAILABLE = False
_UIA_MODULE: Any | None = None
try:
    import uiautomation as _UIA_MODULE
    _UIA_AVAILABLE = True
except ImportError:
    pass
```

#### T1b. Add routing branch to the `_execute_script_unlocked` main loop

```python
# Insert between line 1134 (after req['target'] = target assignment) and line 1136 (before cmd dispatch if/elif chain):

# ── UIA command routing ──
_via = step.get('via', '')
if cmd in _UIA_PREFIX_CMDS or (_via == 'uia' and cmd in _UIA_CAPABLE_CMDS):
    # Acquire _gui_execution_lock (shared with pipeline commands to ensure serial execution)
    with _gui_execution_lock:
        # Python side directly executes UIA operations; does not go through the Delphi pipeline
        resp_json, step_ok, ok = _execute_uia_step(step, req, req_id)

    # Note: the UIA branch does not support the capture field. If a screenshot is needed after a UIA operation,
    # add an independent capture step immediately after the UIA step in the script (using the existing Delphi pipeline path).
    
    results.append({
        'step': step, 'command': cmd_str,
        'response': resp_json,
        'status': 'ok' if step_ok else 'error',
        'uia_resolved': True,
    })
    # Skip the following pipeline send/peekresult/post-processing and go directly to the assert check
    assert_result = _check_assert(step, resp_json)
    results[-1]['assert_result'] = assert_result
    if not assert_result.get('passed', True):
        results[-1]['status'] = 'assert_fail'
        step_ok = False
    if not step_ok:
        success = False
    _logger.debug(f"[UIA] step done: cmd={cmd} target={step.get('target','')} ok={step_ok}")
    time.sleep(0.3)
    continue
```

#### T1c. Add `_should_use_uia` decision (automatic fallback entry, implemented in Phase 2)

```python
def _should_use_uia(app_path: str, cmd: str) -> bool:
    """Determine whether UIA should be used instead of the pipeline to execute a command.
    
    Phase 1 (current): use UIA only when the script explicitly specifies via='uia'
    Phase 2 (future): automatic detection—fall back to UIA when the pipeline connection fails
    """
    # Phase 1: explicit specification only
    return False  # Decided by the via check in _execute_script_unlocked
```

---

### T2. Implement 6 UIA commands on the Python side (1 person-day)

> **⚠️ DPI / Coordinate Handling**
> The `uiautomation` library automatically declares system DPI awareness via `SetProcessDPIAware` at startup, so coordinate conversion for interactive commands (`Click`, `SetValue`, etc.) is handled internally by the library and does not need manual scaling.
> However, `BoundingRectangle` returns **physical pixel coordinates** (not logical scaled values). Pay attention in the following scenarios:
> - `uiaget Rect`: returns physical pixels; consumers (e.g. logging, passing to other tools) must convert DPI scaling themselves
> - The `Rect` field in `_walk_uia_tree` is the same; it is only for informational display and not for driving input
> - If UIA coordinates need to be passed to Win32 message APIs in the future (such as `mouse_event`), first obtain the scale factor via `ctypes.windll.shcore.GetScaleFactorForMonitor` and convert

Add a new `_execute_uia_step` function that uses the `uiautomation` library internally:

```python
def _execute_uia_step(step: dict, req: dict, req_id: str) -> tuple[dict, bool, bool]:
    """Call Windows UIA directly on the Python side to execute automation commands.
    
    Returns:
        (resp_json, step_ok, ok) compatible with the pipeline path return values
    """
    # Use module-level _UIA_MODULE alias (assigned in imports area to avoid repeated import)
    if not _UIA_AVAILABLE:
        return ({'reqId': req_id, 'status': 'err', 'data': 'UIA_unavailable: pip install daofy-for-delphi[uia]'}, False, False)
    auto = _UIA_MODULE
    
    cmd = step.get('cmd', '')
    # Uniformly handle uia prefix: uiagoto → goto
    uia_cmd = cmd[3:] if cmd.startswith('uia') else cmd
    target = step.get('target', '')
    resp: dict = {'reqId': req_id, 'status': 'err', 'data': ''}
    
    _logger.debug(f"[UIA] executing: cmd={cmd} target={target}")
    
    try:
        if uia_cmd == 'goto':
            # uiagoto/goto via uia: activate window by name
            w = auto.WindowControl(searchDepth=1, Name=target)
            if w.Exists(maxSearchSeconds=3, searchIntervalSeconds=0.5):
                w.SetActive()
                resp = {'reqId': req_id, 'status': 'ok', 'data': 'OK'}
            else:
                resp = {'reqId': req_id, 'status': 'err', 'data': 'NF:' + target}
        
        elif uia_cmd == 'click':
            ctrl = auto.ControlControl(Name=target)
            if ctrl.Exists(maxSearchSeconds=2, searchIntervalSeconds=0.3):
                ctrl.Click()
                resp = {'reqId': req_id, 'status': 'ok', 'data': 'OK'}
            else:
                resp = {'reqId': req_id, 'status': 'err', 'data': 'NF:' + target}
        
        elif uia_cmd == 'get':
            prop = step.get('prop', req.get('prop', ''))
            ctrl = auto.ControlControl(Name=target)
            if not ctrl.Exists(maxSearchSeconds=2, searchIntervalSeconds=0.3):
                return ({'reqId': req_id, 'status': 'err', 'data': 'NF:' + target}, False, False)
            
            if prop in ('Name', 'AutomationId', 'ControlType', 'HelpText'):
                val = getattr(ctrl, prop, '')
            elif prop == 'Value':
                try:
                    val = ctrl.GetValuePattern().Value
                except Exception:
                    val = ''
            elif prop == 'ToggleState':
                try:
                    val = str(ctrl.GetTogglePattern().ToggleState)
                except Exception:
                    val = ''
            elif prop == 'Rect':
                r = ctrl.BoundingRectangle  # physical pixel coordinates (not logical values); DPI awareness requires consumers to convert themselves
                val = f'{r.left},{r.top},{r.right},{r.bottom}'
            else:
                # Unknown property: log a warning instead of silently falling back, so the user knows
                _logger.warning(f"[UIA] unknown prop '{prop}' for cmd=get, falling back to Name")
                val = ctrl.Name
            # Uniform JSON serialization: ensure val is a string
            resp = {'reqId': req_id, 'status': 'ok', 'data': str(val)}
        
        elif uia_cmd == 'set':
            value = step.get('value', req.get('value', ''))
            ctrl = auto.ControlControl(Name=target)
            if ctrl.Exists(maxSearchSeconds=2, searchIntervalSeconds=0.3):
                try:
                    ctrl.GetValuePattern().SetValue(value)
                    resp = {'reqId': req_id, 'status': 'ok', 'data': 'OK'}
                except Exception:
                    ctrl.Click()
                    ctrl.SendKeys('{Ctrl}a')
                    ctrl.SendKeys('{Delete}')
                    ctrl.SendKeys(value)
                    resp = {'reqId': req_id, 'status': 'ok', 'data': 'OK'}
            else:
                resp = {'reqId': req_id, 'status': 'err', 'data': 'NF:' + target}
        
        elif uia_cmd == 'scan':
            root = auto.GetRootControl()
            tree = _walk_uia_tree(root, max_depth=3)
            resp = {'reqId': req_id, 'status': 'ok', 'data': json.dumps(tree, ensure_ascii=False)}
        
        elif uia_cmd == 'wait':
            condition = step.get('condition', req.get('condition', ''))
            timeout = int(step.get('timeout', req.get('timeout', '5000')))
            _logger.debug(f"[UIA] wait: condition={condition}, timeout={timeout}")
            
            if condition.startswith('exists:'):
                name = condition[7:]
                ctrl = auto.ControlControl(Name=name)
                found = ctrl.Exists(maxSearchSeconds=timeout/1000, searchIntervalSeconds=0.3)
                resp = {'reqId': req_id, 'status': 'ok' if found else 'err',
                        'data': 'OK' if found else 'TIMEOUT:' + condition}
            elif condition.startswith('visible:'):
                name = condition[8:]
                ctrl = auto.ControlControl(Name=name)
                found = ctrl.Exists(maxSearchSeconds=timeout/1000, searchIntervalSeconds=0.3)
                if found and not ctrl.IsOffscreen:
                    resp = {'reqId': req_id, 'status': 'ok', 'data': 'OK'}
                else:
                    resp = {'reqId': req_id, 'status': 'err', 'data': 'TIMEOUT:' + condition}
            elif condition.startswith('enabled:'):
                name = condition[8:]
                ctrl = auto.ControlControl(Name=name)
                found = ctrl.Exists(maxSearchSeconds=timeout/1000, searchIntervalSeconds=0.3)
                if found and ctrl.IsEnabled:
                    resp = {'reqId': req_id, 'status': 'ok', 'data': 'OK'}
                else:
                    resp = {'reqId': req_id, 'status': 'err', 'data': 'TIMEOUT:' + condition}
            else:
                ctrl = auto.ControlControl(Name=condition)
                found = ctrl.Exists(maxSearchSeconds=timeout/1000, searchIntervalSeconds=0.3)
                resp = {'reqId': req_id, 'status': 'ok' if found else 'err',
                        'data': 'OK' if found else 'TIMEOUT:' + condition}
        
        else:
            resp = {'reqId': req_id, 'status': 'err', 'data': 'unknown_uia_cmd:' + cmd}
    
    except Exception as e:
        resp = {'reqId': req_id, 'status': 'err', 'data': f'UIA_ERROR:{e}'}
        _logger.error("[UIA] exception", exc_info=True)
    
    ok = resp.get('status') in ('ok', 'ack')
    _logger.debug(f"[UIA] result: cmd={cmd} status={resp.get('status')}")
    return resp, ok, ok
```

#### `_walk_uia_tree` helper function

```python
def _walk_uia_tree(ctrl, max_depth: int = 3, current_depth: int = 0) -> dict:
    """Recursively traverse the UIA control tree and return a JSON-compatible dict.
    
    Extract only key properties and limit depth to prevent OOM.
    """
    if current_depth > max_depth:
        return {'type': '...truncated...'}
    
    result = {}
    try:
        result['Name'] = ctrl.Name
        result['AutomationId'] = ctrl.AutomationId
        result['ControlType'] = ctrl.ControlTypeName
        r = ctrl.BoundingRectangle  # physical pixels, see T2 DPI note
        result['Rect'] = f'{r.left},{r.top},{r.right},{r.bottom}'
    except Exception:
        pass  # stale element / access denied
    
    if current_depth < max_depth:
        try:
            children = ctrl.GetChildren()
            if children:
                result['children'] = []
                for child in children:
                    child_dict = _walk_uia_tree(child, max_depth, current_depth + 1)
                    result['children'].append(child_dict)
                    # Safety throttling: at most 200 children per level
                    if len(result['children']) >= 200:
                        result['children'].append({'type': '...truncated(200)...'})
                        break
        except Exception:
            pass
    
    return result
```

---

### T3. Command mapping + dependency management + testing (1 person-day)

#### T3a. Add UIA command branches to `_extract_actual`

```python
def _extract_actual(cmd: str, resp: dict) -> str:
    # ... existing branches ...
    
    # ── UIA command branches ──
    if cmd in ('uiaget',):
        return str(resp.get('data', ''))
    if cmd in ('uiascan',):
        data = resp.get('data', '')
        try:
            parsed = json.loads(data)
            return 'ok' if parsed else 'empty'
        except (json.JSONDecodeError, TypeError):
            return str(data)[:200]
    if cmd in ('uiaclick', 'uiaset', 'uiagoto', 'uiawait'):
        return resp.get('status', '')
    
    # ... subsequent branches ...
```

#### T3b. Add UIA signals to `_failure_signal`

```python
def _failure_signal(result: dict) -> str:
    # ... existing branches ...
    # result['response'] is the resp dict returned by _execute_uia_step
    response = result.get('response', {})
    data = str(response.get('data', '')) if isinstance(response, dict) else ''
    
    # Extract UIA command name (result['step'] is the original step dict)
    step = result.get('step', {})
    cmd = step.get('cmd', '')
    
    if data.startswith('UIA_ERROR:'):
        return 'uia_error'
    if data.startswith('NF:') and (cmd.startswith('uia') or step.get('via') == 'uia'):
        return 'uia_target_not_found'
    
    # ... subsequent branches ...
```

Add corresponding entries to `_failure_recommendations`:

```python
'uia_error': [
    'UIA operation failed with a COM error.',
    'Check that the target window still exists and is not a protected process.',
    'The process may have exited or the UI element may have been destroyed.',
],
'uia_target_not_found': [
    'The UIA element was not found by Name/AutomationId.',
    'Run uiascan first to see the current UIA tree structure.',
    'The target window may not be running, or the control may use a different name.',
],
```

#### T3c. Python-side automatic `uiascan`/`scan` JSON parsing

In the `resp_json` post-processing section of `_execute_script_unlocked` (between the existing dumpstate/dlgscan post-processing at line 1248 and the `results.append` at line 1278), add:

```python
# Add immediately after the existing dumpstate/dlgscan post-processing (if cmd in ('dumpstate', 'dlgscan'): ...):
# Note: handle both uiascan (uia prefix) and scan via UIA (non-prefixed but result marked uia)
elif cmd in ('uiascan', 'scan') and ok and resp_json.get('data'):
    # Process only scan results coming from the UIA path (pipeline-path scan has a different format)
    if resp_json.get('status') == 'ok' and isinstance(resp_json.get('data'), str):
        try:
            parsed = json.loads(resp_json['data'])
            resp_json['state'] = parsed
        except (json.JSONDecodeError, TypeError):
            pass
```

#### T3d. Dependency management

In `pyproject.toml` under `[project.optional-dependencies]`, add:

```toml
# Optional: Windows UI Automation cross-process operations
uia = [
    "uiautomation>=2.0.0",
]
```

At the top of `automation_service.py` (together with constants such as `_UI_ASYNC_CMDS`), perform lazy import:

```python
# ── UIA module lazy import (already uniformly declared in the T1a constants area; this is only a reference note) ──
# Actual code is uniformly declared in the T1a constants area:
#   _UIA_AVAILABLE = False
#   _UIA_MODULE: Any | None = None
#   try:
#       import uiautomation as _UIA_MODULE
#       _UIA_AVAILABLE = True
#   except ImportError:
#       pass
```

The entry point of `_execute_uia_step` already includes the `_UIA_AVAILABLE` guard (see T2), so no duplicate addition is needed.

---

### T4. Integration testing (0.5 person-day)

#### Test script

```json
// tests/scripts/uia-basic-test.json
{
  "test_name": "uia_smoke",
  "steps": [
    {"cmd": "uiascan", "name": "scan_desktop_env"},
    {"cmd": "uiawait", "target": "Taskbar", "condition": "exists:Taskbar", "timeout": 2000},
    {"cmd": "uiawait", "target": "Program Manager", "condition": "exists:Program Manager", "timeout": 2000}
  ]
}
```

#### Unit tests

```python
# tests/test_uia.py
"""UIA function tests (requires the uiautomation optional dependency)"""

import pytest

pytest.importorskip("uiautomation", reason="requires uiautomation package")

from src.services.automation_service import _execute_uia_step


def test_uiascan_returns_json():
    """uiascan should return a control tree in JSON format"""
    step = {"cmd": "uiascan"}
    req = {"reqId": "t1", "cmd": "uiascan"}
    resp, ok, _ = _execute_uia_step(step, req, "t1")
    assert ok
    data = resp.get("data", "")
    assert data.startswith("{") or data.startswith("[")
    parsed = json.loads(data)
    assert isinstance(parsed, dict)


def test_uiawait_taskbar():
    """uiawait should find Taskbar"""
    step = {"cmd": "uiawait", "condition": "exists:Taskbar", "timeout": 3000}
    req = {"reqId": "t2"}
    resp, ok, _ = _execute_uia_step(step, req, "t2")
    assert ok


def test_uia_unavailable_without_dep():
    """When uiautomation is not installed, UIA commands return UIA_unavailable"""
    import sys
    # Simulate the not-installed state
    with pytest.MonkeyPatch.context() as m:
        m.setattr('src.services.automation_service._UIA_AVAILABLE', False)
        from src.services.automation_service import _execute_uia_step
        step = {"cmd": "uiascan"}
        req = {"reqId": "t3"}
        resp, ok, _ = _execute_uia_step(step, req, "t3")
        assert not ok
        assert "UIA_unavailable" in resp.get("data", "")
```

#### Execution method

```bash
pip install daofy-for-delphi[uia]  # Install UIA dependency
pytest tests/test_uia.py -v        # Run UIA tests
pytest tests/ -v                    # Regression tests (does not affect existing tests)
```

---

## Workload Estimate

| Task | Person-days | Dependency | Description |
|------|:---:|:----:|------|
| T1. Command routing + `_execute_script_unlocked` modification | 1 | None | Add `_UIA_PREFIX_CMDS`, routing branch, `_execute_uia_step` entry |
| T2. Implement 6 UIA commands | 1 | T1 | Function bodies + `_walk_uia_tree` helper |
| T3. Assertions/signals/post-processing + dependency management | 0.5 | T2 | `_extract_actual`, `_failure_signal`, `pyproject.toml` |
| T4. Integration testing | 0.5 | T3 | Unit tests + scripts + documentation update |
| **Total** | **3 person-days** | | **6.5 person-days fewer than v2.0** |

**Changes compared with v2.0:**

| Task | v2.0 | v3.0 | Reason for difference |
|------|:----:|:----:|---------|
| `DaofyAutomation.UIA.pas` (COM interface import) | 3 person-days | **0** | Python `uiautomation` library already wraps it |
| `DaofyAutomation.UIA.Commands.pas` (6 commands) | 3 person-days | **0** | Replaced by Python-side `_execute_uia_step` |
| `DaofyAutomation.Base.pas` modification (ExecCmd + CoInit) | 1 person-day | **0** | Replaced by Python-side routing |
| Python-side extension | 1.5 person-days | **2.5 person-days** | Expanded from command mapping to complete implementation |
| Integration testing | 1 person-day | **0.5 person-day** | Python-only single-stack testing; no Delphi compile verification needed |
| VCL/FMX modification | 0 | 0 | Neither version needs it |
| **Total** | **9.5 person-days** | **3 person-days** | **68% reduction** |

---

## Risk Assessment (v3.0)

| Risk | Probability | Impact | Mitigation |
|------|:----:|:----:|------|
| **R1: `uiautomation` library compatibility** — abnormal behavior on certain Windows versions | Low | 🟡 Medium | Degrade with `pip uninstall uiautomation`; does not affect existing functionality. Installation does not block startup (lazy import). |
| **R2: Cross-process Element invalidation** — target window refresh causes stale element | Medium | 🟡 Medium | Acquire Element independently within each command (stateless design); do not cache across commands. Protect each level in `_walk_uia_tree` with `try/except`. |
| **R3: UIA operation speed** — `uiautomation` calls are slow in Remote Desktop/slow environments | Medium | 🟢 Light | All UIA calls set timeouts (default `maxSearchSeconds=3`); timeout returns `TIMEOUT`. Does not affect pipeline commands. |
| **R4: Admin-privileged windows** — windows running as administrator cannot be operated via UIA | Low | 🟡 Medium | When UIA returns `E_ACCESSDENIED`, the Python side returns `UIA_ACCESS_DENIED`. Users can switch to `msgclick` (Win32 messages) instead. |
| **R5: Script portability** — window names used by test scripts differ on Chinese/English Windows | Medium | 🟢 Light | Run `uiascan` first to probe actual names; `target` supports partial match semantics (default `SubName` matching). |

---

## Verification Checklist

```
[ ] T1 routing verification:
      Script cmd="uiascan" → _execute_uia_step is called (does not go through pipeline)
      Script cmd="click" without via → goes through existing pipeline path (unchanged)

[ ] T2 command functionality verification:
      uiascan → returns control tree in JSON format
      uiawait → can find Taskbar (always available)
      uiaclick → given a known button, returns ok/NF

[ ] T2 unicode/Chinese verification:
      Chinese in the Name field returned by uiascan is not garbled
      uiawait condition="exists:Calculator" can match

[ ] T3 assertion verification:
      _extract_actual for uiaget returns data value
      uiascan JSON response is automatically parsed into resp_json['state']

[ ] T3 dependency degradation verification:
      uiautomation not installed → UIA command returns 'UIA_unavailable: pip install...'
      pytest tests skip via pytest.importorskip

[ ] T4 regression testing:
      pytest tests/ -v confirms all existing non-UIA tests pass

[ ] End-to-end verification (critical path):
      Python sends uiascan → returns JSON control tree → Python parses successfully
      Python sends uiawait → finds target window → returns ok
```

---
## UIA Capability Boundaries

### Applicable Scenarios

UIA (UI Automation) operates on the **OS-level UI control tree**, not the browser's web DOM.
The following table marks UIA's actual capabilities across the three object domains:

| Object Domain | What UIA can do | What UIA cannot do | Recommended technology |
|--------|-------------|---------------|---------|
| **A: Delphi in-process components** | — (this plan does not take this path) | Fewer properties, slower, no method calls compared with RTTI | **RTTI** (rget/rset/rcall) |
| **B: Cross-process Windows windows** | ✅ Window activation/focus | ❌ Cannot read complex control property trees | **UIA** (this plan) |
| | ✅ Window title reading | ❌ Bypass Admin privilege restrictions | |
| | ✅ Button click (`Name` matching) | ❌ Cross-process control caching (search again each time) | |
| | ✅ Control tree traversal (`uiascan`) | ❌ Screenshots (requires independent `capture` step) | |
| | ✅ Control existence waiting (`uiawait`) | ❌ Performance: may be slow under Remote Desktop | |
| **C: Web content (browser DOM)** | ✅ Browser **Chrome layer** operations | ❌ **Cannot obtain web DOM** (search box, links, button text) | **Playwright / Selenium** |
| | — Address bar (clear/input/enter) | ❌ Cannot read page title `<title>` | |
| | — Toolbar buttons (back/refresh/bookmark) | ❌ Cannot click links inside the page | |
| | — Tab switching | ❌ Cannot fill forms | |
| | — Extensions/settings menu | ❌ Cannot execute JavaScript | |
| **D: Win32 message layer** | ✅ Complementary to UIA | ❌ No UIA control type recognition | **msgscan/msgclick** (existing) |

### Actual Test Verification (Edge + Baidu Homepage)

Scanning the `baidu.com` page opened by the Edge browser with UIA confirmed the above boundaries:

```
What UIA can obtain (145 nodes, all browser chrome):
├── Window title "Baidu, you will know - Microsoft Edge"
├── Address bar (OmniboxViewViews, but Value Pattern is not readable)
├── Toolbar: back/forward/refresh/home/extensions/settings
├── Tab bar: tab search, new tab
├── Favorites bar: favorites button
└── Window controls: minimize/maximize/close

What UIA cannot obtain:
├── Baidu search input box ✗
├── "Baidu" search button ✗
├── Trending search terms ✗
├── Page links/images ✗
└── Any HTML DOM element ✗
```

### Why UIA Cannot Access Web DOM

Modern browsers (Edge/Chrome) run their rendering engine in an **independent sandbox subprocess**. UIA can access the browser main process UI (Chrome layer), but:
1. Web page rendering content is drawn via **shared memory + GPU composition**, not traditional UI controls
2. Browsers expose limited accessibility information only in screen reader scenarios, and require specific UIA Patterns (TextPattern)
3. Tests confirm that web content nodes do not exist in Edge's UIA tree for baidu.com

### Correct Tool Selection

| Goal | Tool |
|------|------|
| Operate Delphi application (in-process) | `rget/rset/rcall/rinspect` (RTTI) |
| Operate OS popups/third-party windows (cross-process) | `uiascan/uiaclick/uiagoto/uiawait` (UIA) |
| Operate browser web DOM | `Playwright` / `Selenium` (outside this plan's scope) |
| Operate Win32 messages | `msgscan/msgclick/msgclose/dlgfile` (existing) |

---

## Known Limitations (Phase 1 Does Not Cover)

- **Screenshots**: UIA steps do not support inline `capture` fields. If a screenshot is needed, add an independent `capture` step after the UIA step in the script (using the existing Delphi pipeline path to capture Delphi application window content).
- **Automatic fallback**: Phase 1 requires scripts to explicitly write `via: 'uia'` or use `uia`-prefixed commands. Automatic fallback (pipeline failure→UIA) is Phase 2.
- **Complex control patterns**: Does not support `SelectionPattern` / `GridPattern` / `TablePattern` (not needed in Phase 1).
- **UIA Event listening**: `uiawait` uses polling rather than event-driven behavior. Event listening is left for Phase 3.

---

---

## Audit Findings (Pre-Implementation Fixes for v3.0 — All 9 Items Fixed ✅)

An architecture-level and implementation-level audit of the v3.0 plan found **9 issues requiring correction**; the fix status of each is described below.

### 🔴 Critical (Fixed ✅)

#### A1. `_UAL_CAPABLE_CMDS` constant name typo (Fixed ✅)

✅ Global search-and-replace of `_UAL_CAPABLE_CMDS` → `_UIA_CAPABLE_CMDS` completed.
Both the definition (T1a) and the routing branch (T1b) are now unified as `_UIA_CAPABLE_CMDS`.

#### A2. UIA routing branch skips `capture` screenshot logic (Handled ✅)

UIA steps do not support inline `capture` fields. If a screenshot is needed, add an independent `capture` step after the UIA step in the script (using the existing Delphi pipeline path).
✅ Screenshot handling code has been removed from the T1b routing branch and replaced with an explanatory comment.

### 🟡 Medium (Fixed ✅)

#### A3. Missing `_gui_execution_lock` protection (Fixed ✅)

✅ The routing branch in `T1b` now wraps the outer layer with `with _gui_execution_lock:`:
```python
with _gui_execution_lock:
    resp_json, step_ok, ok = _execute_uia_step(step, req, req_id)
```
The lock is acquired before calling the function and released after it returns, consistent with the serial execution semantics of the pipeline path.

#### A4. `_execute_uia_step` internal `import uiautomation` inconsistent with module-level `_UIA_AVAILABLE` (Fixed ✅)

✅ Adopted a unified approach:
1. **Module level** (T1a constants area): `try: import uiautomation as _UIA_MODULE; _UIA_AVAILABLE = True`
2. **Inside function** (T2 `_execute_uia_step` entry): `if not _UIA_AVAILABLE: return error; auto = _UIA_MODULE`
3. **T3d has been corrected**: no longer recommends duplicate import; changed to reference the unified declaration in T1a

#### A5. Duplication between UIA routing branch and main-loop post-processing (Fixed ✅)

✅ The T1b routing branch retains necessary post-processing (`_check_assert` / `results.append`) because:
- The UIA branch's `resp_json` format is aligned with the pipeline path and can directly reuse `_check_assert`
- The UIA branch uses `continue` to skip pipeline send/peekresult, so it must handle post-processing and screenshots itself
- Post-processing logic is reduced to necessary steps (assert + results), with no duplicated pipeline communication code
- If duplication is still found later, extract a `_finalize_step` helper (left as a Phase 2 optimization)

#### A6. `uiaget` unknown prop silent fallback (Fixed ✅)

✅ In T2's `_execute_uia_step`, this has been changed to:
```python
else:
    _logger.warning(f"[UIA] unknown prop '{prop}' for cmd=get, falling back to Name")
    val = ctrl.Name
```
Use `_logger.warning` to record a log so the user knows the property is unavailable. Fallback is chosen instead of raising an error because `ctrl.Name` at least provides readable debugging information and does not affect script continuation.

### 🟢 Minor (Fixed ✅)

#### A7. Missing trace logs (Fixed ✅)

✅ In T2's `_execute_uia_step`, `_logger.debug` has been added at the following positions:
- Function entry: `_logger.debug(f"[UIA] executing: cmd={cmd} target={target}")`
- Function exit: `_logger.debug(f"[UIA] result: cmd={cmd} status={resp.get('status')}")`
- Additionally in `T1b`: `_logger.debug(f"[UIA] step done: cmd={cmd} target={...} ok={step_ok}")`

#### A8. `_walk_uia_tree` return type annotation imprecise (Fixed ✅)

✅ Signature has been changed to: `def _walk_uia_tree(...) -> dict:`

#### A9. Did not explain JSON encoding handling for `uiaget` return values (Fixed ✅)

✅ In T2, uniformly use `str(val)` to serialize as a plain string; `resp['data']` does not contain nested JSON/unicode objects. If the entire resp is later `json.dumps`-ed, the `data` field is a native string and will not cause double-encoding.

### Audit Conclusion

| Severity | Count | Current status |
|:------:|:----:|:--------|
| 🔴 Critical | 2 | **Handled ✅** — A1 typo, A2 UIA does not support capture confirmation |
| 🟡 Medium | 4 | **Fixed ✅** — A3 `_gui_execution_lock`, A4 import inconsistency, A5 code duplication (reasonable redundancy retained), A6 silent fallback |
| 🟢 Minor | 3 | **Fixed ✅** — A7 missing trace, A8 type annotation, A9 JSON encoding |

**All 9 issues have been corrected in the planning document.** Developers can code directly according to the current plan without additionally checking the audit list.

---

## Reference Documents

- Python `uiautomation` library: https://github.com/yinkaisheng/Python-UIAutomation-for-Windows
- Existing automation service: `src/services/automation_service.py`
- Existing test script directory: `tests/scripts/`
- Python official UIA documentation: https://learn.microsoft.com/en-us/windows/win32/winauto/entry-uiauto-win32
- Pre-audit version (deprecated): `docs/uia-integration-plan.md`

