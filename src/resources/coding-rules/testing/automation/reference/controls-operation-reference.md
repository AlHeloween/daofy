<!-- @when: When choosing which automation command to execute on a Delphi control (click/type/textbounds/rget/rset/rcall/uia.*/capture) -->
<!-- @chain: after=capability-matrix.md; before=script-schema.md -->

# Control Operation Reference Manual

Provides **recommended commands + fallbacks + available RTTI properties/methods + textbounds applicability + common pitfalls** by control type. Covers:
- VCL standard controls (System.Classes / Vcl.StdCtrls / Vcl.ComCtrls / Vcl.ExtCtrls / Vcl.Mask / Vcl.Buttons / Vcl.Grids / Vcl.Samples.Calendar etc.)
- UI control libraries under Thirdpart: jvcl / SynEdit / VirtualTreeView / cnvcl / RxLib / IOComp / picshow / Image32 / RVMedia
- FMX controls with the same names (FMX.TButton/TLabel/TMemo/TListView/TTreeView/TStringGrid etc.); operation recommendations match corresponding VCL controls, but **FMX has no type-bound implementation** ([Fmx.DaofyAutomation.pas:780](file:///c:/user/daofy-agent/daofy/tools/auto/Fmx.DaofyAutomation.pas#L780) explicitly returns UNSUP); FMX controls must use mode=auto or mode=paint.

MCP resource URI: `delphi://automation/controls-reference`.

---

## 0. Required Reading: Rendering Stack Determines Command Selection

The `textbounds` paint-hook only intercepts **GDI (gdi32.dll) and GDI+ (gdiplus.dll)** text drawing functions. **It does not cover Direct2D / DirectWrite / MIL / Skia / Blink / Qt RHI or other rendering stacks.**

| Rendering Stack | Typical Controls | textbounds | Recommended Commands |
|--------|---------|:---:|---------|
| **GDI** | VCL standard controls, jvcl, cnvcl, RxLib, SynEdit (default), SynEdit default rendering | ✅ | textbounds / rget / click |
| **GDI+** | FMX Windows default, IOComp, VirtualTreeView GDI+ backend | ✅ | textbounds / rget / click |
| **Direct2D / DirectWrite** | VirtualTreeView Direct2D backend, when SynDWrite is enabled, WPF/UWP | ❌ | uia.* / rget (RTTI only) |
| **Custom-drawn + API mixed** | Image32 experimental controls, custom TGraphicControl | ⚠️ depends on implementation | rget + capture + OCR fallback |
| **Skia / Blink / RHI** | WebView2 / Electron / Qt Quick | ❌ | uia.* / capture + daofy_ocr |

**Methods to determine a control's rendering stack**:
1. Check whether uses imports `Vcl.Graphics` (GDI) / `System.Drawing` or GDI+ units (GDI+) / `D2D1` / `Winapi.D2D1` / `DWDirect2D` / `Vcl.Direct2D` (Direct2D)
2. Call `rinspect` to see whether the control ancestor class inherits from `TGraphicControl`/`TWinControl` (GDI) or uses a custom Canvas
3. Try `textbounds`; if it fails, fall back to `uia.*` or `capture + OCR`

---

## 0.1 Operation Command Levels (Important)

All "recommended commands" in the table below list only **black-box commands** by default; the `rset`/`rcall` in the "Fallback" column are only for gray-box/white-box test scenarios.

| Level | Commands | Description |
|------|------|------|
| **Black-box** (user perspective) | `click` / `type` / `key` / `drag` / `hover` / `move` / `textbounds` / `capture` / `waitfor` / `wait` / `msgscan` / `msgclick` / `dlgfile` / `uia.*` / `rget` (read-only verification) | Simulate real user operations or read visible state; **black-box tests use only this class by default** |
| **Gray-box** (RTTI intervention) | `rset` / `rcall` / `rinspect` / `run_tests` / `dumpstate` / `formsum` | Bypass the UI to directly change properties/call methods; **disabled for black-box**, only for gray-box/white-box tests or fixture initialization |
| **White-box** (deep RTTI) | `delphi_rtti(action=call)` | Directly call internal methods; **disabled for black-box**, only for white-box diagnostics |

**Core principles**:
- If `rset` / `rcall` appears in a black-box script, it is considered a level violation and must be changed to the corresponding `click` / `type` / `key` operation
- `rget` is read-only and **available to black-box** (used to read state for assertion verification)
- When the test level (`test_level`) is `black-box`, Daofy reports a compliance warning for `rcall`/`rset`

---

## 1. Command Selection Decision Tree

```
What do you want to do?
├─ Read a control's text/caption/value
│   ├─ Is a published property (Caption/Text/Items/Cells[...]) → rget (read-only, available to black-box)
│   ├─ Control is derived from TCollection (list/tree/tabs) → rget ControlName.Items.Text or rget ControlName.Items[I].Caption
│   └─ Not published (custom-drawn/grid content) → textbounds or dumpstate
├─ Modify control text
│   ├─ Black-box → type (input box) / click ControlName@ItemCaption (list/tree selection) / click date cell (calendar) / click tab caption (tab switch)
│   └─ Gray-box fallback → rset Text/Caption/Cells/ItemIndex/ActivePageIndex (only gray-box/white-box tests or fixture initialization)
├─ Call methods (scroll/select/custom)
│   ├─ Black-box → key PageDown/Up/Down (scroll) / click scrollbar / key Ctrl+G etc. (editor go-to-line)
│   └─ Gray-box fallback → rcall (only gray-box/white-box tests or fixture initialization)
├─ Click a control
│   ├─ The control itself (focus/activate) → click ControlName
│   ├─ A specific item of a TCollection-derived control (TListBox/TTreeView/TPageControl etc.) → click ControlName@ItemCaption
│   ├─ Switch/toggle-type controls (TToggleSwitch/TJvSwitch/TiSwitch*/custom-drawn switches) → follow the probe flow in §2.1 (read state → click opposite side → verify), do not directly click the center
│   ├─ Visible text on a custom-drawn/Panel → textbounds + click ControlName@x,y (use visible_* coordinates)
│   ├─ A label on a GDI/GDI+ control → textbounds + click
│   ├─ DirectUI/WPF/UWP/Electron/WebView → uiaclick
│   └─ None work → capture + daofy_ocr recognize + click @x,y
├─ Verify whether text is truncated
│   ├─ GDI/GDI+ → textbounds (visible_state=full means no truncation) + rget compare full value
│   └─ Others → capture + OCR
└─ Capture screenshot for evidence → capture
```

---

## 2. Buttons / Check Boxes / Radio Buttons

### 2.1 VCL Standard

| Control | Recommended Command | Fallback | Available RTTI Properties | textbounds | Pitfalls |
|------|---------|------|--------------|:---:|------|
| TButton | `click` | — | Caption, ModalResult, Enabled, Visible, Default, Cancel | ✅ GDI | When TButton.Enabled=False, click is ignored; assert `rget Enabled=False`; black-box should not bypass via rset Enabled |
| TBitBtn | `click` | — | Caption, Kind, Glyph, Layout, Margin, NumGlyphs, Spacing, ModalResult | ✅ GDI | Kind=bkClose/bkOK etc. automatically responds with ModalResult; the window closes after click, and the next step may fail listwnd |
| TSpeedButton | `click` | — | Caption, GroupIndex, Down, AllowAllUp, Flat, Glyph, Layout | ✅ GDI | When GroupIndex>0, Down is state and click toggles it; when Flat=True, the border is shown only on hover, but textbounds can still capture |
| TButtonControl (base class) | — | Gray-box: `rset Checked` | Checked | — | Abstract base class, not used directly |
| TCheckBox | `click` | Gray-box: `rset Checked` | Caption, Checked, State, AllowGrayed, Enabled | ✅ GDI | When AllowGrayed=True, State=cbGrayed; Checked cannot distinguish the gray state; black-box uses click to toggle and rget to verify Checked |
| TRadioButton | `click` | Gray-box: `rset Checked` | Caption, Checked, Enabled | ✅ GDI | Within the same group, clicking one automatically unchecks the others; no need to iterate |
| TToggleSwitch | `click` (follow the general probe flow below) | `rset State` (only gray-box/white-box when skipping UI) | Caption, State, ShowText, OnText, OffText | ✅ GDI | The hit area is the slider itself, not the Caption; clicking the control center hits the slider but does not toggle; black-box should use "read state → click left/right side → read state and verify" to establish the mapping between left/right and on/off |

**Black-box click probe flow for switch-type controls** (generic; applicable to TToggleSwitch / TJvSwitch / TiSwitchLed / TiSwitchPanel / TiSwitchRotary / TiSwitchSlider / TiSwitchToggle / TCheckboxCtrl / TRadioBtnCtrl and all switch/toggle controls where "hit area ≠ control center"):

```json
[
  {"cmd": "rget", "target": "<ControlName>.<StateProp>", "note": "Record initial state baseline (StateProp takes the corresponding property from the table below)"},
  {"cmd": "click", "target": "<ControlName>", "x": "<Width*0.25>", "y": "<Height/2>", "note": "Click left half (avoid slider/knob)"},
  {"cmd": "rget", "target": "<ControlName>.<StateProp>", "assert_expr": "actual != '<previous initial value>'", "note": "Verify state change and establish 'left half → toggle direction' mapping; if unchanged, left half is the same side as the current state"},
  {"cmd": "click", "target": "<ControlName>", "x": "<Width*0.75>", "y": "<Height/2>", "note": "Click right half for reverse verification"},
  {"cmd": "rget", "target": "<ControlName>.<StateProp>", "assert_expr": "actual == '<initial value>'", "note": "Right half should toggle back to the original state, establishing 'right half → reverse' mapping"}
]
```

Applicable controls and state property mapping:

| Control | Library | StateProp | Values | Notes |
|------|----|----------|------|------|
| TToggleSwitch | VCL | `State` | tgOn / tgOff | Standard ToggleSwitch |
| TJvSwitch | jvcl | `State` | tgOn / tgOff | Similar to TToggleSwitch |
| TiSwitchLed / TiSwitchPanel / TiSwitchRotary / TiSwitchSlider / TiSwitchToggle | IOComp | `Value` or `State` | Control-specific (see rinspect) | Industrial switches; some use Value (Boolean), some use State |
| TCheckboxCtrl / TRadioBtnCtrl | Image32 | `Checked` | True / False | Experimental, rendering stack uncertain |
| TSpeedButton (GroupIndex>0) | VCL | `Down` | True / False | Same-group mutually exclusive toggle |
| Custom-drawn switch controls | Any | See specific implementation | — | Use rinspect to find the state property, then apply this flow |

Through this probe you can confirm: for the current control instance, clicking the left/right half corresponds to On or Off respectively (may differ across Delphi versions/themes/control libraries); subsequent clicks can use the established mapping to directly click the opposite side.

### 2.2 Third-party

| Control | Library | Recommended Command | textbounds | Pitfalls |
|------|----|-----|:---:|------|
| TJvBitBtn/TJvButton/TJvArrowButton/TJvBitmapButton/TJvHTButton | jvcl | `click` | ✅ GDI | TJvHTButton supports HTML tags in Caption; textbounds gets the rendered plain text |
| TJvCaptionButton | jvcl | `click` | ⚠️ unreliable | Title-bar button; drawing goes through the NC area, and the paint-hook does not intercept non-client-area drawing |
| TJvSwitch/TJvRollOut | jvcl | `click` (follow the general probe flow above) / `rset State` (gray-box only) | ✅ GDI | TJvSwitch is similar to TToggleSwitch; hit area ≠ center, so black-box uses the probe flow; TJvRollOut is a collapsible panel, clicking the Caption area expands/collapses it |
| TRxSpeedButton/TRxAnimBitBtn | RxLib | `click` | ✅ GDI | TRxAnimBitBtn has an animated Glyph; click timing is sensitive |
| TiSwitchLed/TiSwitchPanel/TiSwitchRotary/TiSwitchSlider/TiSwitchToggle | IOComp | `click` (follow the general probe flow above) / `rset Value` (gray-box only) | ✅ GDI+ | Industrial switches; the hit area is the knob/slider itself, not the control center, so black-box uses the probe flow; gray-box can use rset Value/State to directly change |
| TButtonCtrl/TRoundedBtnCtrl/TEllipseBtnCtrl/TImageBtnCtrl | Image32 | `click` (gray-box fallback: `rcall DoClick`) | ⚠️ custom-drawn | Experimental controls, no standard published Caption; black-box clicks the control center, and if the hit area is not the center use textbounds to locate |
| TCheckboxCtrl/TRadioBtnCtrl | Image32 | `click` (follow the general probe flow above; gray-box fallback: `rcall Toggle`) | ⚠️ custom-drawn | Experimental, rendering stack uncertain; black-box uses the probe flow (use `Checked` as StateProp) |

---

## 3. Input Box / Edit Box

### 3.1 VCL Standard

| Control | Recommended Command | Available RTTI Properties | textbounds | Pitfalls |
|------|---------|--------------|:---:|------|
| TEdit | `type` (write) / `rget Text` (read verification) | Text, MaxLength, PasswordChar, ReadOnly, CharCase, NumbersOnly, SelStart, SelLength, SelText | ✅ GDI | type simulates a real keyboard, black-box preferred; rset Text is a gray-box fallback and does not trigger OnKeyPress/OnChange |
| TMemo | `type` (write) / `rget Lines.Text` (read verification) | Text, Lines (TStrings), SelStart, SelLength, SelText, ScrollBars, WordWrap, CaretPos | ✅ GDI | type-bound uses `EM_POSFROMCHAR` + `EM_LINEINDEX` to precisely calculate line-start Y and line height (instead of hardcoded 16 pixels), so the rectangle is accurate when the font changes; line height prioritizes the next line's Y difference, and the last line uses `GetTextMetrics` font height |
| TMaskEdit | `type` (write) / `rget EditText` (read verification) | Text, EditMask, MaxLength, EditText | ✅ GDI | EditText is the value without mask characters; Text may contain mask characters; tests should preferably rget EditText |
| TLabeledEdit | `type` (write) / `rget Text` (read verification) | Text, EditLabel.Caption, LabelPosition, LabelSpacing | ✅ GDI | EditLabel is a child control; clicking EditLabel does not focus Edit |
| TButtonedEdit | `type` (write) / `rget Text` (read verification) | Text, LeftButton.Visible, RightButton.Visible, Images | ✅ GDI | Clicking the left/right buttons requires using textbounds to locate the button icon position and then clicking; gray-box fallback `rcall` calls OnLeftButtonClick/OnRightButtonClick |
| TSpinEdit | `type` (write number) / `click` up/down arrows / `rget Value` (read verification) | Text, Value, MinValue, MaxValue, Increment | ✅ GDI | Black-box uses type to input a number or clicks the up/down arrow buttons; rset Value is a gray-box fallback |
| TComboBox | `click ControlName@ItemCaption` (option) / `type` (input when csDropDown) / `rget ItemIndex` (read verification) | Items, Text, Style, ItemIndex, DropDownCount, Sorted | ✅ GDI | When Style=csDropDownList, only items in Items can be selected; type cannot be used; **type-bound calculates only visible items**: when the dropdown is not expanded, it matches only the selected item and returns the Edit box rectangle (otherwise `DROPDOWN_CLOSED`); when expanded, it checks by `CB_GETTOPINDEX` + visible item count, and returns `NOT_VISIBLE` if not visible (need to scroll first) |
| TComboBoxEx | `click ControlName@ItemCaption` | ItemsEx, Images, Style, DropDownCount | ✅ GDI | ItemsEx is TComboExItems; each item contains ImageIndex/SelectedImageIndex/OverlayImageIndex/Indent |
| TColorBox | `click ControlName@ColorName` | Selected, Style, Colors, DefaultColorColor, CustomColors | ✅ GDI | Selected is TColor; black-box should click the list item; gray-box fallback `rset Selected` |

### 3.2 Third-party

| Control | Library | Recommended Command | textbounds | Pitfalls |
|------|----|-----|:---:|------|
| TJvEdit/TJvCheckedMaskEdit | jvcl | `type` (write) / `rget Text` (read verification) | ✅ GDI | For TJvCheckedMaskEdit's CheckBox state, black-box uses click to toggle it; gray-box fallback rset Checked |
| TJvIPAddress | jvcl | `type` segment by segment (use `key` TAB to switch fields) | ✅ GDI | Text is in `1.2.3.4` format; black-box types each field and uses key TAB to switch; gray-box fallback `rcall FocusField(idx)` |
| TJvComboBox/TJvCheckedComboBox/TJvColorComboBox/TJvFontComboBox | jvcl | `click ControlName@ItemCaption` | ✅ GDI | TJvCheckedComboBox is multi-select; black-box clicks each item to toggle the check; gray-box fallback `rset Checked[I]` |
| TJvComboListBox | jvcl | `click ControlName@ItemCaption` | ✅ GDI | It is derived from ListBox, not ComboBox |
| TCustomNumEdit/TCurrencyEdit/TRxCalcEdit | RxLib | `type` (write number) / `rget Value` (read verification) | ✅ GDI | Black-box types a numeric string; rset Value is a gray-box fallback |
| TRxDBComboBox/TDBIndexCombo | RxLib | `click ControlName@ItemCaption` | ✅ GDI | Data-aware; black-box clicks the list item |
| TSynHotKey | SynEdit | `key` (key combination, e.g. Ctrl+A) | ✅ GDI | Black-box uses key to press the key combination; HotKey is a TShortcut property; gray-box fallback `rset HotKey` |
| TiEdit/TiModeComboBox | IOComp | `type` (write) / `click` option | ✅ GDI+ | Industrial controls; black-box uses type/click; rset Value/Text is a gray-box fallback |
| TEditCtrl/TMemoCtrl | Image32 | `type` (write) | ⚠️ custom-drawn | Experimental; rset Text is a gray-box fallback |

---

## 4. Lists / Grids

### 4.1 VCL Standard

| Control | Recommended Command | Available RTTI Properties | textbounds | Pitfalls |
|------|---------|--------------|:---:|------|
| TListBox | `click ControlName@ItemCaption` | Items (TStrings), ItemIndex, TopIndex, Count, Sorted, MultiSelect, Selected[I], ItemHeight | ✅ GDI | When MultiSelect=True, the Selected array can be toggled independently; black-box uses key Ctrl+click or Shift+click to simulate multi-select |
| TCheckListBox | `click ControlName@ItemCaption` (toggle check) | Items, ItemIndex, Checked[I], State[I], AllowGrayed | ✅ GDI | **⚠️ The type-bound implementation only matches `Ctl is TListBox`; TCheckListBox does not hit this branch** (it inherits from TCustomListBox rather than TListBox), so use mode=auto to let the paint-hook take over; black-box uses click on an item to toggle the check, and rget Checked[I] to verify |
| TComboBox (already listed under input boxes) | same as above | same as above | ✅ GDI | same as above |
| TListView | `click ControlName@ItemCaption` | Items, Columns, ViewStyle, Selected, TopItem, ItemIndex, SortType, SmallImages, LargeImages | ✅ GDI | **type-bound matches only Caption and does not check SubItems**; to locate subcolumn text you must use mode=auto; when ViewStyle=vsReport, the item text is Caption and subcolumns are SubItems |
| TDrawGrid | `click ControlName@x,y` (locate via textbounds first) | ColCount, RowCount, FixedCols, FixedRows, Selection, TopRow, LeftCol, DefaultColWidth, DefaultRowHeight | ⚠️ custom-drawn | DrawGrid has no built-in text and must be custom-drawn in the OnDrawCell event; textbounds can capture if GDI text APIs are used in OnDrawCell, while custom icons/GDI+ depend on the situation |
| TStringGrid | `click ControlName@x,y` (locate cell via textbounds first) / `rget Cells[col,row]` (read verification) | Cells[col,row], Rows[row], Cols[col], Objects[col,row], ColCount, RowCount, FixedCols, FixedRows, Selection | ✅ GDI | Black-box uses textbounds to locate the cell and then clicks; rget Cells for read verification; rset Cells is a gray-box fallback |
| TValueListEditor | `click ControlName@x,y` (locate via textbounds first) / `rget Values['Key']` (read verification) | Strings (TStrings), Keys[I], Values[I], ItemProps, TitleCaptions | ✅ GDI | Similar to TStringGrid but each row is Key=Value; black-box clicks the cell and then types to modify; rset Values is a gray-box fallback |

### 4.2 Third-party

| Control | Library | Recommended Command | textbounds | Pitfalls |
|------|----|-----|:---:|------|
| TVirtualStringTree | VirtualTreeView | `click` node (locate via textbounds first) / `rget` node text | ⚠️ depends on backend | **Virtual tree, no built-in Items collection**; text is provided through the OnGetText event; the Default backend is GDI (✅), while the Direct2D/GDI+ backend depends on the control's RenderStyle setting; black-box uses textbounds to locate the node and then clicks, gray-box fallback `rcall FocusedNode` |
| TVirtualDrawTree | VirtualTreeView | `click` node (locate via textbounds first) | ⚠️ depends on backend | Fully custom-drawn, with no text concept; black-box uses textbounds to locate the node and then clicks, and must first ensure the rendering backend is GDI |
| TJvListBox/TJvCheckListBox | jvcl | `click ControlName@ItemCaption` | ✅ GDI | Same as standard TListBox |
| TTextListBox/TRxCheckListBox | RxLib | `click ControlName@ItemCaption` | ✅ GDI | Same as standard |
| TJvDBGrid | jvcl | `click` cell (locate via textbounds first) / `rget SelectedField.Value` (read verification) | ✅ GDI | Data-aware; black-box uses textbounds to locate and then clicks; SelectedField is the current selected field |
| TiLinkedListBox/TiModeComboBoxDisplay | IOComp | `click ControlName@ItemCaption` | ✅ GDI+ | Industrial controls; black-box clicks the item; gray-box fallback `rset ItemIndex` |
| TListCtrl/TScrollingCtrl | Image32 | `click` item (locate via textbounds first) | ⚠️ custom-drawn | Experimental |

---

## 5. Trees

### 5.1 VCL Standard

| Control | Recommended Command | Available RTTI Properties | textbounds | Pitfalls |
|------|---------|--------------|:---:|------|
| TTreeView | `click ControlName@NodeText` (expand parent node first) | Items (TTreeNodes), Selected, TopItem, ShowButtons, ShowLines, ShowRoot, Indent, SortType | ✅ GDI | **type-bound traverses all Items flat and does not filter expanded state**; DisplayRect(True) returns an invalid rectangle for hidden nodes; to locate child nodes in the collapsed state you must use mode=auto; black-box uses `click` on the parent node's expand icon to expand and then clicks the child node; gray-box fallback `rcall Items.GetFirstNode` |

### 5.2 Third-party

| Control | Library | Recommended Command | textbounds | Pitfalls |
|------|----|-----|:---:|------|
| TVirtualStringTree | VirtualTreeView | `click` node (locate via textbounds first) | ⚠️ depends on backend | **Virtual tree, nodes are not pre-created**; text is obtained through OnGetNodeText; black-box uses textbounds to locate the node and then clicks; gray-box fallback `rcall FullExpand` / `rcall FocusedNode := Node` / `rcall EnsureVisible` |
| TJvTreeView/TJvCheckTreeView | jvcl | `click ControlName@NodeText` (toggle check) | ✅ GDI | TJvCheckTreeView black-box clicks the node to toggle the check; gray-box fallback `rset Checked[Node]` |

---

## 6. Tabs / Wizards

### 6.1 VCL Standard

| Control | Recommended Command | Available RTTI Properties | textbounds | Pitfalls |
|------|---------|--------------|:---:|------|
| TPageControl | `click ControlName@TabCaption` | Pages, ActivePage, ActivePageIndex, PageCount, TabHeight, TabWidth, TabPosition, Style, MultiLine | ✅ GDI | When TabPosition=tpBottom/tpLeft/tpRight, the TabRect coordinates differ, but type-bound still hits; black-box clicks the tab to switch, and rget ActivePageIndex to verify; rset ActivePageIndex is a gray-box fallback |
| TTabControl | `click ControlName@TabCaption` | Tabs, TabIndex, TabWidth, TabHeight, Style, MultiLine | ✅ GDI | Unlike TPageControl, TTabControl has no Pages collection; it is just a tab strip; rset TabIndex is a gray-box fallback |
| TTabSheet | `rget Caption` (read verification) | Caption, PageControl, PageIndex, TabVisible, ImageIndex, Highlighted | ✅ GDI | Directly clicking TTabSheet does not switch tabs; you must click the parent TPageControl's TabRect |
| TNotebook | No black-box switching method | Pages, ActivePage, PageIndex | ⚠️ unreliable | Old control with no visible tab strip; black-box cannot switch; gray-box fallback `rset ActivePage` |

### 6.2 Third-party

| Control | Library | Recommended Command | textbounds | Pitfalls |
|------|----|-----|:---:|------|
| TJvTabControl/TJvPageControl/TJvTabBar | jvcl | `click ControlName@TabCaption` | ✅ GDI | TJvTabBar is Outlook style; rset ActivePageIndex is a gray-box fallback |
| JvgPage/JvgTab | jvcl | `click ControlName@TabCaption` | ✅ GDI | Globus series; rset ActivePage is a gray-box fallback |
| TJvWizard | jvcl | `click` Next/Previous button | ✅ GDI | Black-box clicks the Next/Previous buttons on the wizard interface; gray-box fallback `rcall NextPage` / `rcall PriorPage` |
| TCnVSNETTabPageControl/TCnVIDTabPageControl | cnvcl | `click ControlName@TabCaption` | ✅ GDI | Docking-style tabs; rset ActivePage is a gray-box fallback |
| TPageTabCtrl/TPagePnlCtrl/TPageCtrl | Image32 | `click` tab (locate via textbounds first) | ⚠️ custom-drawn | Experimental; rset ActivePageIndex is a gray-box fallback |

---

## 7. Containers / Panels

### 7.1 VCL Standard

| Control | Recommended Command | Available RTTI Properties | textbounds | Pitfalls |
|------|---------|--------------|:---:|------|
| TPanel | `rget Caption` | Caption, Alignment, BevelInner, BevelOuter, BevelWidth, BorderStyle, FullRepaint, Locked, ParentBackground | ✅ GDI | To click a Label on a Panel, directly click LabelName rather than clicking PanelName |
| TGroupBox | `rget Caption` | Caption | ✅ GDI | Same as TPanel |
| TScrollBox | `click` scrollbar / `key` PageDown/Up | HorzScrollBar, VertScrollBar, AutoScroll | ✅ GDI | When child controls exceed the visible area, before clicking first use the black-box scrollbar or key paging; gray-box fallback `rcall ScrollInView` |
| TControlBar | `rget ButtonCount` | ButtonCount, Buttons[I], RowCount, AutoSize, Picture | ✅ GDI | Child controls with draggable layout |
| TFlowPanel | Operate via child controls | FlowStyle, AutoWrap, LastWrapBreak | ✅ GDI | Automatically arranges child controls |
| TGridPanel | Operate via child controls | ColumnCollection, RowCollection, ExpandStyle | ✅ GDI | Grid layout |
| TSplitter | `rget MinSize` | MinSize, MinSize, ResizeStyle, AutoSnap | ✅ GDI | Drag using `drag SplitterName` |
| THeader | `rget Section[I].Text` | Sections, Section[I].Text, Section[I].Width | ⚠️ old control | Old control; recommend THeaderControl |
| THeaderControl | `rget Sections[I].Text` | Sections, Sections[I].Text, Sections[I].Width, Sections[I].MinWidth, Sections[I].MaxWidth | ✅ GDI | Drag the separator to change width using `drag HeaderControl1@x,y` |

### 7.2 Third-party

| Control | Library | Recommended Command | textbounds | Pitfalls |
|------|----|-----|:---:|------|
| TJvPanel/TJvCaptionPanel/TJvBehaviorLabel | jvcl | `rget Caption` | ✅ GDI | TJvCaptionPanel can drag its title bar |
| TJvBackgrounds/TJvFooter/TJvContentScroller/TJvSpacer/TJvShape/TJvSticker | jvcl | — | ✅ GDI | Decorative containers |
| TJvCoolBar/TJvControlBar/TJvToolBar | jvcl | — | ✅ GDI | Toolbars |
| TJvLookOut/TJvOutlookBar/TJvNavigationPane | jvcl | `click` navigation item | ✅ GDI | Outlook-style navigation; black-box clicks an item to switch; rset ActivePage is a gray-box fallback |
| TCnVSNETDockPanel/TCnVIDDockPanel | cnvcl | `rget VisibleDockClients` | ✅ GDI | Dock panels with dockable child controls |
| TRxPanel/TRxProgress | RxLib | `rget Caption` / `rget Position` | ✅ GDI | TRxProgress is a progress bar (display-type; black-box can only rget it, cannot change it) |
| TSecretPanel | RxLib | `rget Caption` | ✅ GDI | Scrollable marquee panel (display-type); rset Active is a gray-box fallback |
| TiAboutPanel/TiStripChart/TiGradient | IOComp | `rget Caption` / `rget TitleText` | ✅ GDI+ | Industrial controls (display-type; black-box can only rget) |
| TPanelCtrl/TRootCtrl | Image32 | No black-box modification method | ⚠️ custom-drawn | Experimental; rset Caption is a gray-box fallback |

---

## 8. Labels / Display

### 8.1 VCL Standard

| Control | Recommended Command | Available RTTI Properties | textbounds | Pitfalls |
|------|---------|--------------|:---:|------|
| TLabel | `rget Caption` | Caption, Alignment, Layout, WordWrap, AutoSize, Transparent, FocusControl | ✅ GDI | Clicking TLabel does not focus it (no handle); to trigger FocusControl's GotFocus you must click FocusControl itself |
| TStaticText | `rget Caption` | Caption, Alignment, BorderStyle, ShowAccelChar | ✅ GDI | TLabel with a handle |
| TLinkLabel | `rget Caption` | Caption | ✅ GDI | Caption contains `<a>` HTML tags and is rendered as plain text; textbounds gets the plain text |
| TPaintBox | — | Canvas, Anchors, Hint | ⚠️ custom-drawn | No Caption/Text; drawing content is determined by the OnPaint event; textbounds captures only if GDI text APIs are used in OnPaint |

### 8.2 Third-party

| Control | Library | Recommended Command | textbounds | Pitfalls |
|------|----|-----|:---:|------|
| TJvLabel/TJvBehaviorLabel/TJvHtmlLabel | jvcl | `rget Caption` | ✅ GDI | TJvHtmlLabel supports HTML tags; textbounds gets the rendered plain text |
| JvgLabel/JvgDigits/JvgShadow | jvcl | `rget Caption` | ✅ GDI | Globus series, effect labels |
| TRxLabel/TRxCustomLabel | RxLib | `rget Caption` | ✅ GDI | — |
| TiLabel/TiImageDisplay | IOComp | `rget Caption` | ✅ GDI+ | Industrial controls |
| TLabelCtrl/TStatusbarCtrl | Image32 | `rget Caption` (display-type, no black-box modification) | ⚠️ custom-drawn | Experimental; rset Caption is a gray-box fallback |

---

## 9. Images / Animations

### 9.1 VCL Standard

| Control | Recommended Command | Available RTTI Properties | textbounds | Pitfalls |
|------|---------|--------------|:---:|------|
| TImage | `rget Picture` | Picture, Stretch, Proportional, Center, Transparent, AutoSize | ❌ no text | No Caption/Text; only displays an image |
| TShape | `rget Shape` | Shape, Brush, Pen | ❌ no text | No text |
| TBevel | `rget Shape` | Shape, Style | ❌ no text | — |
| TAnimate | `rget FileName` / `rget Active` (read verification) | FileName, CommonAVI, Active, StartFrame, StopFrame, Repetitions | ❌ no text | AVI animation; black-box has no user operation entry (unless there is OnClick); gray-box fallback `rset Active=True` |
| TImageList | `rget Count` | Count, Width, Height, AllocBy, BkColor, BlendColor | ❌ no text | Non-visual |
| TTimer | `rget Enabled` (read verification) | Enabled, Interval | ❌ no text | Non-visual; black-box has no user operation entry; gray-box fallback `rset Enabled=True` |

### 9.2 Third-party

| Control | Library | Recommended Command | textbounds | Pitfalls |
|------|----|-----|:---:|------|
| TJvImage/TJvBaseThumbImage/TJvBaseThumbnail/TJvBaseThumbView | jvcl | `rget Picture` | ❌ no text | — |
| TJvAnimate/TJvAnimatedImage/TJvBmpAnimator/TJvGIFCtrl | jvcl | `rget Active` (read verification) | ❌ no text | Animation controls; black-box has no standard user operation entry; gray-box fallback `rset Active=True` |
| TJvPicClip/TJvZoom | jvcl | — | ❌ no text | TJvZoom is a magnifier effect |
| TPicShow/TDBPicShow | picshow | `rget Picture` (read verification) | ❌ no text | Image transition display; the screen changes quickly during transition; black-box has no standard operation entry; gray-box fallback `rset Picture` / `rset Step=0` |
| TImage32Panel/TNotifyImage32/TBaseImgPanel | Image32 | `rget Bitmap` (read verification) | ❌ no text | GDI displays images; black-box has no standard operation entry; gray-box fallback `rset Bitmap` |
| TRVCamView/TRVCamMultiView | RVMedia | `rget Active` (read verification) | ❌ no text | Video stream display; dynamic image; black-box has no standard operation entry; gray-box fallback `rset Active=True` |

---

## 10. Editors (Code / Rich Text)

| Control | Library | Recommended Command | Available RTTI Properties | textbounds | Pitfalls |
|------|-----|---------|----|:---:|------|
| TRichEdit | VCL | `type` (write) / `rget Lines.Text` / `rget SelText` (read verification) | Lines, Text, SelStart, SelLength, SelText, SelAttributes, Paragraph | ✅ GDI | Black-box uses `type` to write and `rget` to read verification; **type-bound uses ClassNameIs instead of is**, because it does not want to uses Vcl.ComCtrls; same as TMemo, uses `EM_POSFROMCHAR` to precisely calculate line height (RichEdit 2.0+'s `EM_POSFROMCHAR` parameter semantics differ from EDIT: wParam=@Point, lParam=CharIdx); gray-box fallback `rset SelText` |
| TSynEdit/TDBSynEdit | SynEdit | `type` (write) / `rget Lines.Text` / `rget CaretXY` (read verification) / `key` Ctrl+G go to line (black-box GotoLine) | Lines, Text, SelStart, SelLength, SelText, CaretXY, TopLine, LinesInWindow, BlockBegin, BlockEnd, Highlighter | ✅ GDI (default) / ❌ Direct2D (when SynDWrite enabled) | Black-box uses `type`/`key`; **code editor, line height/font height varies**, type-bound is not applicable, be sure to use mode=auto or paint; when SynDWrite is enabled the paint-hook fails, and black-box uses `key` Ctrl+G → `type` line number → `key` Enter instead of go-to-line; gray-box fallback `rset SelText` / `rcall GotoLineAndCenter` |
| TJvEditor/TJvMemo | jvcl | `type` (write) / `rget Lines.Text` (read verification) | Lines, Text, CaretX, CaretY, TopLine, LeftChar | ✅ GDI | TJvEditor is a simple code editor; black-box uses `type` to write |
| TJvHTButton class HTML label display control | jvcl | `rget Caption` | Caption | ✅ GDI | HTML rendered plain text |
| TRichView (not in Thirdpart but common) | — | `rget RVData.GetText` | RVData, Style, BackgroundBitmap | ⚠️ depends on implementation | Rich text; drawing goes through GDI but content has multiple paragraphs, and textbounds gets the first matching segment |
| THexDump | RxLib | `rget DataSize` | Data, DataSize, BytesPerRow, OffsetFormat | ✅ GDI | Hex viewer |

---

## 11. Gauges / Industrial Controls (IOComp-specific)

All IOComp controls use GDI+ rendering (wrapped by iGPFunctions.pas), and textbounds ✅ is available. These controls are mainly **display-type** — properties such as Value/Position are usually driven by external data sources (PLC/sensors/business code), **not triggered by users directly operating the UI**. Therefore:

- **Black-box testing**: can only use `rget` to read values and verify the display effect; cannot change Value/Position via `click`/`type` (unless the control itself has an interactive entry such as mouse-drag knob or virtual keyboard keys)
- **Gray-box testing**: can use `rset` to directly change property values to simulate data source changes and verify display correctness

| Control | Category | Black-box Recommended Command | Gray-box Fallback | Key RTTI Properties |
|------|------|---------|------|--------------|
| TiAnalogDisplay/TiAnalogOutput/TiIntegerOutput | Digital display | `rget Value` (read verification) | `rset Value` | Value, ValueFormat, Alignment |
| TiAngularGauge/TiAngularLogGauge/TiLinearGauge/TiLogGauge | Gauge | `rget Value` (read verification) | `rset Value` | Value, Min, Max, PointerColor |
| TiLed/TiLedArrow/TiLedDiamond/TiLedRectangle/TiLedRound/TiLedSpiral | LED indicator | `rget Active` (read verification) | `rset Active=True` | Active, Color, Beveled |
| TiLedBar/TiLedMatrix/TiLCDMatrix/TiLCDCharacter | LED bar/matrix | `rget Value` (read verification) | `rset Value` | Value, SegmentColor |
| TiSevenSegmentDisplay/Clock/ClockSMPTE/Analog/Binary/Character/Hexadecimal/Integer | Seven-segment display | `rget Value` (read verification) | `rset Value` | Value, ColorOn, ColorOff |
| TiKnob/TiSlider/TiCompass/TiDualCompass/TiMotor/TiThermometer/TiOdometer | Knob/slider/compass/thermometer/odometer | `drag` knob/slider (some support) / `rget Value` / `rget Position` (read verification) | `rset Value` / `rset Position` | Value, Position, Min, Max |
| TiSwitchLed/TiSwitchPanel/TiSwitchRotary/TiSwitchSlider/TiSwitchToggle | Switch | `click` (follow §2.1 probe flow) / `rget Value` / `rget State` (read verification) | `rset Value` / `rset State` | Value, State |
| TiKeyBoard | Virtual keyboard | `click` key (black-box simulates user key press) | — | Keys |
| TiCheckBox | Checkbox | `click` (black-box toggle) | `rset Checked=True` | Checked, Caption |
| TiEdit/TiModeComboBox | Input box | `type` (write) / `click ControlName@ItemCaption` | `rset Text` | Text, Value |
| TiLabel/TiImageDisplay/TiGradient/TiAboutPanel/TiStripChart | Display/chart | `rget Caption` / `rget TitleText` (read verification) | `rset Caption` / `rset TitleText` | Caption, TitleText |
| TiPlotComponent/TiScope | Advanced plotting | `rget Channel[I].Value` (read verification) | `rset Channel[I].Value` | Channels, Channel[I].Value |

---

## 12. Date / Time

### 12.1 VCL Standard

| Control | Recommended Command | Available RTTI Properties | textbounds | Pitfalls |
|------|---------|--------------|:---:|------|
| TMonthCalendar | `click` date cell (black-box selects date) / `rget Date` / `rget EndDate` (read verification) | Date, EndDate, MinDate, MaxDate, MultiSelect, FirstDayOfWeek, ShowToday, ShowTodayCircle | ✅ GDI | Black-box clicks a date cell to select a date; for multi-select click the start date + Shift+click the end date; gray-box fallback `rset Date` / `rset EndDate` |
| TDateTimePicker | `click` dropdown arrow to expand calendar / `type` input date or time (black-box) / `rget Date` / `rget Time` (read verification) | Date, Time, DateTime, Format, Kind, ShowCheckbox, Checked, CalAlignment | ✅ GDI | Black-box clicks the dropdown arrow to expand the calendar and then clicks a date, or directly uses `type` to input a date/time string; when Kind=dtkTime only time is displayed, but the Date property still contains the date part; when ShowCheckbox=True click the checkbox to toggle enable; gray-box fallback `rset Date` / `rset Time` / `rset Format` |
| TCalendar (Vcl.Samples.Calendar) | `click` date cell (black-box select) / `rget Year` / `rget Month` / `rget Day` (read verification) | Year, Month, Day, StartOfWeek, UseCurrentDate | ✅ GDI | Old control; black-box clicks the date cell; gray-box fallback `rset Year` / `rset Month` / `rset Day` |

---

## 13. Dialogs / Popups

| Control / Type | Recommended Command | Pitfalls |
|------|---------|------|
| TOpenDialog/TSaveDialog | `dlgfile` (execute) + `dlgfile path="..."` (fill path) | Windows 8+ modern-view file list goes through DirectUI; textbounds does not cover that area, so list item clicks use `uiaclick` instead |
| TFontDialog | `uiascan` + `uiaclick` | System dialog, DirectUI/GDI mixed rendering |
| TColorDialog | `uiascan` | Same as above |
| TPrintDialog | `uiascan` | Same as above |
| TFindDialog/TReplaceDialog | `uiascan` + `uiatype`/`uiaclick` (black-box fills text/clicks buttons) | These are modeless dialogs; black-box uses uia.* to operate the Find/Replace input boxes and buttons; gray-box fallback `rset FindText` / `rset ReplaceText` / `rcall CloseDialog` |
| MessageBox / Application.MessageBox | `msgscan` + `msgclick` | Standard GDI popup via the `MessageBox` API |
| TTaskDialog | `uiascan` + `uiaclick` (DirectUI rendering) | Newer task dialog |
| TJvCommonDialog series derivatives | `click` trigger button (black-box calls Execute) + `uiascan`/`uiaclick` operate popup | Third-party dialogs; black-box triggers Execute via the click trigger button and uses uia.* inside the popup; gray-box fallback `rcall Execute` |

---

## 14. Common Operations Quick Reference

### 14.1 Scroll into view

**Black-box method** (recommended):

```json
{"cmd": "key", "target": "TreeView1", "key": "PageDown", "note": "Page until the target node is visible"}
{"cmd": "key", "target": "ListBox1", "key": "Down", "note": "Move down item by item until the target item is visible"}
{"cmd": "click", "target": "ScrollBox1", "x": "<Width-8>", "y": "<Height-8>", "note": "Click the vertical scrollbar down arrow"}
{"cmd": "key", "target": "ScrollBox1", "key": "PageDown"}
```

**Gray-box fallback** (only gray-box/white-box tests or fixture initialization):

```json
{"cmd": "rcall", "target": "TreeView1.Selected.EnsureVisible"}
{"cmd": "rcall", "target": "ListBox1.TopIndex = 5"}
{"cmd": "rcall", "target": "VirtualStringTree1.FocusedNode.EnsureVisible"}
{"cmd": "rcall", "target": "ScrollBox1.ScrollInView(Panel1)"}
```

### 14.2 Selected item

| Control | Black-box Recommended Command | Gray-box Fallback |
|------|---------|------|
| TListBox | `click ListBox1@<item text>` | `rset ListBox1.ItemIndex = 5` |
| TComboBox | `click ComboBox1@<item text>` | `rset ComboBox1.ItemIndex = 5` |
| TListView | `click ListView1@<item text>` | `rset ListView1.Selected = ListView1.Items[5]` |
| TTreeView | `click TreeView1@<node text>` (expand parent node first) | `rset TreeView1.Selected = TreeView1.Items[5]` |
| TPageControl | `click PageControl1@<tab caption>` | `rset PageControl1.ActivePageIndex = 2` |
| TStringGrid | `click StringGrid1@x,y` (locate cell via textbounds first) | `rset StringGrid1.Selection = TRect.Create(0,5,0,5)` (row=5, column=0) |
| TVirtualStringTree | `click VirtualStringTree1@x,y` (locate node via textbounds first) | `rcall VirtualStringTree1.FocusedNode := Node` |

### 14.3 Text truncation verification (GDI/GDI+ only)

```json
[
  {"cmd": "rget", "target": "Label1.Caption", "note": "Get full text"},
  {"cmd": "textbounds", "target": "Label1", "text": "<full text>", "mode": "auto"},
  {"cmd": "assert_expr", "actual": "<textbounds.state.visible_state>", "expr": "actual == 'full'"}
]
```

For non-GDI/GDI+ controls: use `capture + daofy_ocr` recognition + string comparison.

---

## Appendix A: List of Controls Covered by Type-bound (VCL only)

Source: [Vcl.DaofyAutomation.pas](file:///c:/user/daofy-agent/daofy/tools/auto/Vcl.DaofyAutomation.pas) `TypeBoundFallback` function (L652-830).

| Control | Item Text Lookup | Item Rectangle | Known Limitations |
|------|----------|-------|---------|
| TListBox | Items[I] | ItemRect(I) | Only matches `Ctl is TListBox`; **TCheckListBox does not hit** (inherits from TCustomListBox) |
| TComboBox | Items[I] | Visible item area: when not expanded, only the selected item is matched and the Edit box rectangle is returned; when expanded, manually calculates by `CB_GETTOPINDEX` + visible item count `Rect(0, (I-TopIdx)*ItemHeight, Width, (I-TopIdx+1)*ItemHeight)` | **When not expanded and the item is non-selected, returns `DROPDOWN_CLOSED`; when expanded but the item is not visible, returns `NOT_VISIBLE` (need to scroll first)** |
| TTreeView | Items[I].Text | DisplayRect(True) | **Does not filter expanded state**; hidden node rectangle is invalid |
| TListView | Items[I].Caption | DisplayRect(drBounds) | **Does not check SubItems**; to locate subcolumns you must use mode=auto |
| TPageControl | Pages[I].Caption | TabRect(I) | Still hits when TabPosition=tpBottom/tpLeft/tpRight |
| TTabControl | Tabs[I] | TabRect(I) | — |
| TMemo | Lines[I] (SameText + Pos dual match) | `EM_POSFROMCHAR` + `EM_LINEINDEX` precisely calculate `Rect(2, StartY, Width-2, StartY+LH)` | Line height prioritizes the next line's first-character Y difference; the last line uses `GetTextMetrics` font height; when WordWrap has multiple visual lines, the rectangle covers the entire block |
| TRichEdit | Same as TMemo (ClassNameIs cast to TMemo) | Same as TMemo (IsRichEdit=True; `EM_POSFROMCHAR` parameter semantics differ) | Same as TMemo; ClassNameIs bypasses the is check to avoid uses Vcl.ComCtrls |
| TWinControl generic fallback | RTTI `IsPublishedProp('Caption')` + `GetStrProp` | ChildCtl.Left/Top/Width/Height | Only covers direct child controls, not recursive; non-published Text properties cannot hit |

**FMX has no type-bound implementation** ([Fmx.DaofyAutomation.pas:780](file:///c:/user/daofy-agent/daofy/tools/auto/Fmx.DaofyAutomation.pas#L780) explicitly returns UNSUP); FMX must use mode=auto or mode=paint.

---

## Appendix B: Third-party UI Libraries Quick Reference

| Library | Rendering | Category Coverage | Entry Path |
|----|:---:|---------|---------|
| jvcl | GDI | All categories (buttons/input/lists/trees/editors/images/containers/animations/wizards/toolbars/navigation) | `C:\user\Thirdpart\jvcl\run\` |
| SynEdit | GDI (default) / Direct2D (SynDWrite) | Code editor + 50+ highlighters | `C:\user\Thirdpart\SynEdit\Source\` |
| VirtualTreeView | GDI/GDI+/Direct2D (multiple backends) | Virtual tree/grid | `C:\user\Thirdpart\virtualtreeview\Source\` |
| cnvcl | GDI custom-drawn | Skinned controls + docking controls | `C:\user\Thirdpart\cnvcl-master\Source\Skin\`, `Source\NonVisual\` |
| picshow | GDI custom-drawn | Image transition display | `C:\user\Thirdpart\picshow\` |
| RxLib v2.75 | GDI | Classic UI control enhancements (buttons/input/lists/labels/calculators) | `C:\user\Thirdpart\RxLib v2.75\units\` |
| IOComp v404Sp2 | GDI+ | Industrial gauges (gauges/LED/seven-segment/oscilloscope) | `C:\user\Thirdpart\IOComp v404Sp2\Source\` |
| Image32-main | Custom-drawn | Image processing + experimental UI controls | `C:\user\Thirdpart\Image32-main\source\`, `Examples\Experimental\` |
| RVMedia 93FS | GDI custom-drawn | Camera/video display | `C:\user\Thirdpart\RVMedia 93FS\Source\` |

---

## Appendix C: When Switch-type Controls Need the Probe Flow

When a control meets any of the following conditions, **do not directly click the control center**; instead follow the "Black-box click probe flow for switch-type controls" in §2.1:

| Condition | Example Controls |
|------|---------|
| The hit area is the slider/knob itself; clicking the control center hits the slider but does not toggle | TToggleSwitch / TJvSwitch / TiSwitchSlider / TiSwitchRotary |
| The control has "switch" semantics but is rendered as a draggable element such as a