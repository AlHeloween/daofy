# UIA Integration Work Plan — Phase 1

> **⚠️ Deprecation notice: this plan (v1.0) has been superseded by `docs/uia-implementation-plan.md` v3.0.**
> **Reason for deprecation: an architecture change — the original plan used COM UIA on the Delphi side, the new plan uses the Python-side `uiautomation` library.**
> **The new approach requires no change to any Delphi-side code and cuts the effort from 9.5 person-days to 3 person-days. See the new plan.**

> A Phase 1 implementation plan produced from an assessment of the existing automation architecture under `tools/auto/`.
> Objective: introduce Windows UI Automation as an optional enhancement channel with minimal intrusion, without changing the behaviour of the existing non-UIA commands.

---

## Overall Strategy

```
现有架构：
  TAutomationProcessorBase (基类)
    ├── Vcl.TAutomationProcessor
    └── Fmx.TAutomationProcessor

Phase 1 新增：
  可选 UIA 通道（独立单元，条件 uses）
    ├── DaofyAutomation.UIA.pas          ← UIA COM 包装 + 工具函数
    └── DaofyAutomation.UIA.Commands.pas  ← UIA 命令实现 (uiagoto/uiaclick/uiaget/uiascan/uiawait)
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
| **Total** | **~11 person-days** | |

---

## Detailed Design per Task

### T1. `DaofyAutomation.UIA.pas`

```pascal
unit DaofyAutomation.UIA;

interface

uses Winapi.Windows, System.SysUtils, System.Variants;

// ── UIA COM 接口定义（从 UIAutomationCore.dll 导入，非源代码依赖）──

type
  IUIAutomation = interface ... // 导入类型库或手写关键接口
  IUIAutomationElement = interface ...
  // 核心 Control Patterns:
  IInvokeProvider = interface ...    // 按钮点击
  IValueProvider = interface ...     // 读写文本
  IToggleProvider = interface ...    // 复选框
  ISelectionProvider = interface ... // 列表选择
  IRangeValueProvider = interface ...// 滑块/进度条

// ── 延迟加载 UIAutomationCore.dll ──

function IsUIAvailable: Boolean;      // 检测是否可加载
function GetUIAutomation: IUIAutomation; // 单例

// ── 工具函数 ──

function FindElementByAutomationId(Root: IUIAutomationElement; const AId: string): IUIAutomationElement;
function FindElementByName(Root: IUIAutomationElement; const AName: string): IUIAutomationElement;
function FindElementByControlType(Root: IUIAutomationElement; AType: Integer): TArray<IUIAutomationElement>;
function GetElementRect(Root: IUIAutomationElement): TRect;

// ── Control Pattern 工具 ──

function TryGetInvokePattern(Elem: IUIAutomationElement; out Pattern: IInvokeProvider): Boolean;
function TryGetValuePattern(Elem: IUIAutomationElement; out Pattern: IValueProvider): Boolean;
function TryGetTogglePattern(Elem: IUIAutomationElement; out Pattern: IToggleProvider): Boolean;

implementation

var
  _UIAInstance: THandle = 0;
  _UIAutomation: IUIAutomation = nil;

function IsUIAvailable: Boolean;
begin
  // CoCreateInstance(CLSID_CUIAutomation, ...) 延迟加载
  Result := Assigned(_UIAutomation);
end;

// ...其余实现
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

// 6 个 UIA 命令，全部返回 JSON 字符串（与基类 WriteResp 格式兼容）

function UiaGoto(const ReqId, Target: string): string;
  // 定位窗口：按 Name/AutomationId 激活指定 UIA 窗口

function UiaClick(const ReqId, Target: string): string;
  // 语义化点击：找到控件 → InvokePattern.Invoke 或模拟鼠标点击

function UiaGet(const ReqId, Target, Prop: string): string;
  // 读值：ValuePattern.Value / TogglePattern.ToggleState / 属性表

function UiaScan(const ReqId: string): string;
  // 扫描当前 UIA 树，返回 JSON 格式的控件摘要（类似 dumpstate 但走 UIA）

function UiaWait(const ReqId, Target, Condition: string; TimeoutMs: Integer): string;
  // 等待条件：控件出现 / 属性满足 / 状态变化

function UiaSet(const ReqId, Target, Value: string): string;
  // 设置值：ValuePattern.SetValue 输入文本
```

**Key design decisions:**
- Each command function is self-contained and stateless (the UI Automation Element is acquired and released within a single call)
- The return format is exactly the same as the base class `WriteResp`, so higher layers need not distinguish whether UIA was used
- `UiaScan` returns only the key properties (Name/AutomationId/ControlType/Role) and not the full RTTI property table

### T3. Base-class extension `DaofyAutomation.Base.pas`

Add a new branch to the `ExecCmd` method:

```pascal
// ── 在 ExecCmd 的框架相关命令段之前插入 ──

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
  // ... 现有 uses ...
  DaofyAutomation.UIA.Commands;
// Uses 放在 implementation 段，仅在编译时链接。若 UIAutomationCore.dll 不存在，
// CoCreateInstance 在运行时返回错误，函数内部优雅降级为 `WriteResp(reqId, 'err', 'UIA_unavailable')`
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
# 新增 UIA 命令集合
_UIA_CMDS = frozenset({
    'uiagoto', 'uiaclick', 'uiaget', 'uiascan', 'uiawait', 'uiaset',
})

# `_is_async_cmd` 增加：
_ASYNC_CMDS = _ASYNC_CMDS | frozenset({'uiaclick', 'uiaset'})
_UI_ASYNC_CMDS = _UI_ASYNC_CMDS | frozenset({'uiaclick', 'uiaset'})

# 命令构造逻辑增加 uia 前缀分支（在 `_execute_script_unlocked` 的 cmd 分支表中：
if cmd in ('uiaget',):
    # 解析 target.prop 语法
elif cmd == 'uiawait':
    req['condition'] = step.get('condition', '')
```

### T7. Integration Tests

```
测试脚本目录: tests/scripts/
新增: tests/scripts/uia-basic-test.json

测试内容:
  1. uiascan — 扫描桌面 UIA 树（验证返回 JSON 格式正确）
  2. uiagoto — 定位计算器/记事本窗口
  3. uiaclick — 点击窗口上的标准按钮
  4. uiget — 读取 Edit 和 Button 的属性
  5. uiawait — 等待窗口打开

测试方式:
  - 手动启动一个带标准控件的 Delphi 测试程序（或直接用 notepad.exe）
  - 通过 mcp 测试或 pytest 调用 execute_script
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
