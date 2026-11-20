# UIA Integration Work Plan — Phase 1

> **⚠️ Deprecation notice: this plan (v1.0) has been superseded by `docs/uia-implementation-plan.md` v3.0.**
> **Reason for deprecation: an architecture change — the original plan used COM UIA on the Delphi side, the new plan uses the Python-side `uiautomation` library.**
> **The new approach requires no change to any Delphi-side code and cuts the effort from 9.5 person-days to 3 person-days. See the new plan.**

> A Phase 1 implementation plan produced from an assessment of the existing automation architecture under `tools/auto/`.
> Objective: introduce Windows UI Automation as an optional enhancement channel with minimal intrusion, without changing the behaviour of the existing non-UIA commands.

---

## Overall Strategy

```
Existing architecture:
  TAutomationProcessorBase (base class)
    ├── Vcl.TAutomationProcessor
    └── Fmx.TAutomationProcessor

Phase 1 additions:
  Optional UIA channel (standalone units, conditional uses)
    ├── DaofyAutomation.UIA.pas          ← UIA COM wrapper + utility functions
    └── DaofyAutomation.UIA.Commands.pas  ← UIA command implementations (uiagoto/uiaclick/uiaget/uiascan/uiawait)
```

**Design principles:**
- UIA commands coexist with the existing commands through their own `uia` prefix (`goto` vs `uiagoto`)
- The UIA dependency (`UIAutomationCore.dll`) is delay-loaded, so a machine without it does not block startup
- No code path of the existing non-UIA commands is modified
- The Python side of `automation_service.py` supports automatic fallback: a failing UIA command degrades back to RTTI

---

## Effort Estimate

| Task | Estimated person-days | Dependency |
|---|---|---|
| T1. Create `DaofyAutomation.UIA.pas` — COM Import Type Library + delay loading | 2 | none |
| T2. Create `DaofyAutomation.UIA.Commands.pas` — implementation of the 6 UIA commands | 3 | T1 |
| T3. Base-class extension: add a uia command dispatch branch to `DaofyAutomation.Base.pas` | 0.5 | T2 |
| T4. Modify `Vcl.DaofyAutomation.pas` — handle the uia commands in the concrete framework context | 1 | T3 |
| T5. Modify `Fmx.DaofyAutomation.pas` — same as above | 1 | T3 |
| T6. Python side of `automation_service.py` — command mapping + fallback logic | 1.5 | T3 |
| T7. Integration tests — test scripts + on-machine verification | 2 | T6 |
| **Total** | **~11 person-days** | | |

---

## Detailed Design per Task

### T1. `DaofyAutomation.UIA.pas`

```pascal
unit DaofyAutomation.UIA;

interface

uses Winapi.Windows, System.SysUtils, System.Variants;

// ── UIA COM interface definitions (imported from UIAutomationCore.dll, not a source-code dependency) ──

type
  IUIAutomation = interface ... // import type library or hand-write key interfaces
  IUIAutomationElement = interface ...
  // Core Control Patterns:
  IInvokeProvider = interface ...    // button click
  IValueProvider = interface ...     // read/write text
  IToggleProvider = interface ...    // check box
  ISelectionProvider = interface ... // list selection
  IRangeValueProvider = interface ...// slider/progress bar

// ── Delay-load UIAutomationCore.dll ──

function IsUIAvailable: Boolean;      // check whether it can be loaded
function GetUIAutomation: IUIAutomation; // singleton

// ── Utility functions ──

function FindElementByAutomationId(Root: IUIAutomationElement; const AId: string): IUIAutomationElement;
function FindElementByName(Root: IUIAutomationElement; const AName: string): IUIAutomationElement;
function FindElementByControlType(Root: IUIAutomationElement; AType: Integer): TArray<IUIAutomationElement>;
function GetElementRect(Root: IUIAutomationElement): TRect;

// ── Control Pattern utilities ──

function TryGetInvokePattern(Elem: IUIAutomationElement; out Pattern: IInvokeProvider): Boolean;
function TryGetValuePattern(Elem: IUIAutomationElement; out Pattern: IValueProvider): Boolean;
function TryGetTogglePattern(Elem: IUIAutomationElement; out Pattern: IToggleProvider): Boolean;

implementation

var
  _UIAInstance: THandle = 0;
  _UIAutomation: IUIAutomation = nil;

function IsUIAvailable: Boolean;
begin
  // CoCreateInstance(CLSID_CUIAutomation, ...) delay loading
  Result := Assigned(_UIAutomation);
end;

// ...rest of implementation
```

**Key design decisions:**
- Use the COM `CoCreateInstance` instead of statically linking `UIAutomationCore.dll`, so that a system with UIA not installed can still run
- Every exported helper function takes an `IUIAutomationElement` rather than a `HWND` as its input, preserving the abstraction
- The Control Pattern interfaces are trimmed to the 4–5 that the current Phase 1 needs

### T2. `DaofyAutomation.UIA.Commands.pas`

```pascal
unit DaofyAutomation.UIA.Commands;

interface

uses DaofyAutomation.UIA;

// 6 UIA commands, all return JSON strings (compatible with the base class WriteResp format)

function UiaGoto(const ReqId, Target: string): string;
  // Locate window: activate the specified UIA window by Name/AutomationId

function UiaClick(const ReqId, Target: string): string;
  // Semantic click: find control → InvokePattern.Invoke or simulate mouse click

function UiaGet(const ReqId, Target, Prop: string): string;
  // Read value: ValuePattern.Value / TogglePattern.ToggleState / property table

function UiaScan(const ReqId: string): string;
  // Scan current UIA tree, return JSON-format control summary (similar to dumpstate but through UIA)

function UiaWait(const ReqId, Target, Condition: string; TimeoutMs: Integer): string;
  // Wait for condition: control appears / property satisfied / state changes

function UiaSet(const ReqId, Target, Value: string): string;
  // Set value: ValuePattern.SetValue input text
```

**Key design decisions:**
- Each command function is self-contained and stateless (the UI Automation Element is acquired and released within a single call)
- The return format is exactly the same as the base class `WriteResp`, so higher layers need not distinguish whether UIA was used
- `UiaScan` returns only the key properties (Name/AutomationId/ControlType/Role) and not the full RTTI property table

### T3. Base-class extension `DaofyAutomation.Base.pas`

Add a new branch to the `ExecCmd` method:

```pascal
// ── Insert before the framework-related command section of ExecCmd ──

else if Cmd = 'uiagoto' then
  Result := WriteResp(ReqId, 'ok', DaofyAutomation.UIA.Commands.UiaGoto(ReqId, Target))

else if Cmd = 'uiaclick' then
  Result := WriteResp(ReqId, 'ok', DaofyAutomation.UIA.Commands.UiaClick(ReqId, Target))

else if Cmd = 'uiaget' then
  Result := WriteResp(ReqId, 'ok', DaofyAutomation.UIA.Commands.UiaGet(ReqId,
    Target, GetJSONStr(J, 'prop', '')))

else if Cmd = 'uiascan' then
  Result := WriteResp(ReqId, 'ok', DaofyAutomation.UIA.Commands.UiaScan(ReqId))

else if Cmd = 'uiawait' then
  Result := WriteResp(ReqId, 'ok', DaofyAutomation.UIA.Commands.UiaWait(ReqId,
    Target, GetJSONStr(J, 'condition', ''), StrToIntDef(GetJSONStr(J, 'timeout', '5000'), 5000)))

else if Cmd = 'uiaset' then
  Result := WriteResp(ReqId, 'ok', DaofyAutomation.UIA.Commands.UiaSet(ReqId,
    Target, GetJSONStr(J, 'value', '')))
```

The `uses` clause needs a conditional reference — it is imported only where UIA is available:

```pascal
implementation

uses
  // ... existing uses ...
  DaofyAutomation.UIA.Commands;
// Uses is placed in the implementation section and linked only at compile time. If UIAutomationCore.dll does not exist,
// CoCreateInstance returns an error at runtime, and the function internally degrades gracefully to `WriteResp(reqId, 'err', 'UIA_unavailable')`
```

**Key design decisions:**
- The `timer` list definition for the new commands (the cmd branch table of `ExecCmd`) must match the existing sync/async convention: `uiaclick`/`uiaset` are asynchronous, the rest synchronous
- Add `uiaclick` and `uiaset` to the values returned by `IsAsyncCmd`

### T4/T5. Concrete VCL/FMX Implementation Adjustments

**Vcl.DaofyAutomation.pas** and **Fmx.DaofyAutomation.pas** need almost no modification — the UIA commands are COM-level operations and do not depend on the VCL/FMX framework.

Points to watch:
- `UiaGoto` can locate the window handle through UIA and then call `SetForegroundWindow` on the VCL side, while VCL's `HandleCmdGoto` already uses `Screen.Forms[I].BringToFront`, so the UIA commands need no framework context
- The screenshot command `uicapture` is not implemented for now — UIA provides no screenshot capability, and screenshots in complex scenarios are left to a later DXGI phase

### T6. Python-side `automation_service.py` Extension

```python
# New UIA command set
_UIA_CMDS = frozenset({
    'uiagoto', 'uiaclick', 'uiaget', 'uiascan', 'uiawait', 'uiaset',
})

# Add to `_is_async_cmd`:
_ASYNC_CMDS = _ASYNC_CMDS | frozenset({'uiaclick', 'uiaset'})
_UI_ASYNC_CMDS = _UI_ASYNC_CMDS | frozenset({'uiaclick', 'uiaset'})

# Add uia-prefix branch to command construction logic (in the cmd branch table of `_execute_script_unlocked`:
if cmd in ('uiaget',):
    # parse target.prop syntax
elif cmd == 'uiawait':
    req['condition'] = step.get('condition', '')
```

### T7. Integration Tests

```
Test script directory: tests/scripts/
New: tests/scripts/uia-basic-test.json

Test content:
  1. uiascan — scan the desktop UIA tree (verify the returned JSON format is correct)
  2. uiagoto — locate Calculator/Notepad window
  3. uiaclick — click a standard button on the window
  4. uiget — read properties of Edit and Button
  5. uiawait — wait for a window to open

Test method:
  - Manually start a Delphi test program with standard controls (or directly use notepad.exe)
  - Call execute_script through an mcp test or pytest
```

---

## Risks and Mitigation

| Risk | Probability | Mitigation |
|---|---|---|
| `UIAutomationCore.dll` is unavailable on some stripped-down Windows editions | Low | When `CoCreateInstance` fails, `'UIA_unavailable'` is returned and the existing commands are unaffected |
| An incomplete COM interface import causes compile problems | Medium | Hand-write the key interfaces rather than importing the whole type library, importing only the interfaces and patterns Phase 1 needs |
| The timing of control properties read through UIA does not match RTTI | Medium | Add a 200 ms `wait` buffer at the test level and adjust once more data has accumulated |
| A cross-process window that needs administrator rights cannot be operated through UIA | Medium | A failed UIA operation returns a specific error code (`E_ACCESSDENIED`), and a test script can fall back to `capture` + `note` |

---

## Subsequent Phase Roadmap (for reference)

| Phase | Content | Priority |
|---|---|---|
| **Phase 2** | DXGI Desktop Duplication API replacing GDI BitBlt screenshots | High (solves the black-frame problem) |
| **Phase 3** | Implementation guide for UIA Providers on Delphi custom controls | Medium (on demand) |
| **Phase 4** | `action="auto"` hybrid mode — automatic selection of UIA/RTTI/messages | Low (after enough experience has accumulated) |
| **Phase 5** | Aligning OCR output with UIA location — mapping OCR-recognised text positions onto UIA control rectangles | Low |

---

## Reference Documents

- Existing architecture base class: `tools/auto/DaofyAutomation.Base.pas`
- VCL implementation: `tools/auto/Vcl.DaofyAutomation.pas`
- FMX implementation: `tools/auto/Fmx.DaofyAutomation.pas`
- Python automation service: `src/services/automation_service.py`
- Assessment report: `docs/uia-integration-plan.md` (this document)
- Microsoft UIA documentation: https://learn.microsoft.com/en-us/windows/win32/winauto/entry-uiauto-win32
- UIA Control Patterns: https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-controlpatternsoverview

