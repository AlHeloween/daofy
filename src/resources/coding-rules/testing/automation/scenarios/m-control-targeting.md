<!-- @when: Ensure control targeting is stable and reliable across various DPI/resolutions and avoid hard-coded pixel coordinates -->
<!-- @part-of: ui-testing -->

#### M. Control Targeting Strategy — Text First, Coordinate Calibration, DPI Scale Factor

| Element | Content |
|------|------|
| **Goal** | Ensure control targeting is stable and reliable across various DPI/resolutions, avoiding the fragility caused by hard-coded pixel coordinates |
| **Strategy** | ① Text targeting first → ② Name + offset calibration targeting → ③ Coordinate + DPI factor dynamic calculation |
| **Key concepts** | `@text`, `@x,y`, `coord_scale`, calibration script |

**Background**: DaofyAutomation supports three control targeting methods, with priority as follows:

| Targeting method | Syntax | Applicable scenarios | Stability |
|---------|------|------|------|
| Control name | `BtnSave` | Standard VCL controls such as buttons, edit boxes, combo boxes | 🟢 Highest (independent of coordinates/text) |
| Text matching | `cbCity@Beijing` / `TreeView1@Customer Management` | Combo box options, tree nodes, menu items | 🟢 High (depends on text not changing) |
| Pixel coordinates | `cbMenus@50,43` / `vstProject@25,10` | Self-drawn controls without independent HWND, VirtualStringTree | 🟡 Low (offset changes when DPI changes) |

##### M1. Targeting Priority Rules (Mandatory)

```
When encountering a control that needs targeting
├─ Has a unique control name (such as BtnSave, EditName) → Use the control name directly, do not add @
├─ Is a list item/tree node/dropdown option/menu item
│  ├─ Displayed text is stable → ControlName@displayed text (such as cbCity@Beijing)
│  ├─ Displayed text is dynamic → ControlName@0-based index (such as cbCity@2)
│  └─ Text matching not supported → ControlName@x,y (last resort)
└─ Is an internal area of a self-drawn control (no HWND)
   ├─ Use goto to locate the control first → @x,y relative to the control client area
   └─ **Must** verify coordinate validity in 00-calibration
```

##### M2. Coordinate Calibration Script (Mandatory)

Each test suite must include `00-calibration.json`, verifying the validity of coordinate targeting before running other tests:

```json
[
  {"cmd":"goto","target":"TfrmMain","note":"Confirm main form can open"},

  {"cmd":"rget","target":"frmMain.ClientWidth","note":"Record current window width for DPI inference"},
  {"cmd":"rget","target":"frmMain.ClientHeight","note":"Record current window height"},

  {"cmd":"rget","target":"BtnSave.Enabled","note":"Verify standard control is accessible","assert_expr":"actual in ('True','False')"},
  {"cmd":"rget","target":"StatusBar.Panels[0].Text","note":"Verify status bar is readable"},
  {"cmd":"capture","target":"calibration_main","note":"Baseline screenshot"},

  {"cmd":"exit"}
]
```

After the calibration script executes, the Python side should calculate the expected DPI scale factor:
```python
# Assume the baseline ClientWidth at 96 DPI (100%) is known as baseline_width
baseline_width = 832    # 100% DPI baseline value
actual_width = result["frmMain.ClientWidth"]     # current runtime value
coord_scale = actual_width / baseline_width       # scale factor

# All subsequent @x,y coordinates are multiplied by this factor
def scaled(coord_str: str, scale: float) -> str:
    """Adjust @x,y according to the scale factor."""
    x, y = map(int, coord_str.lstrip("@").split(","))
    return f"@{int(x * scale)},{int(y * scale)}"

# Usage example
target = scaled("@50,43", coord_scale)  # → "@50,43" or "@75,64" (150% DPI)
```

##### M3. Menu Item Targeting — Text First, Coordinates Second

Menu items in menus (`TMainMenu`, `TPopupMenu`) do not have independent control names. Targeting methods:

```json
[
  {"cmd":"click","target":"cbMenus@50,43","note":"Click the entire menu by coordinate (fragile)"},
  {"cmd":"exit"}
]
```

**Recommended instead** (if DaofyAutomation supports text matching for menus):
```json
[
  {"cmd":"click","target":"@File(&F)","note":"Click the menu title"},
  {"cmd":"click","target":"@Open(&O)...","note":"Click the Open menu item"},
  {"cmd":"exit"}
]
```

**If text matching is not supported**, when coordinates must be used:
- Record the actual coordinate offsets of each menu item in the calibration script
- Dynamically calculate offset = baseline offset × `coord_scale`
- Output a coordinate comparison table for each menu item in the calibration report

##### M4. Virtual Tree Node Targeting — VirtualStringTree

`TVirtualStringTree` nodes usually have no independent HWND and can only be targeted by coordinate clicks. Rules:

```json
[
  {"cmd":"goto","target":"TfrmMain"},
  {"cmd":"dblclick","target":"vstProject@25,10","note":"Expand root node (offset relative to the tree control client area)"},
  {"cmd":"wait","ms":300},
  {"cmd":"click","target":"vstProject@65,64","note":"Select leaf node"},
  {"cmd":"exit"}
]
```

**Best practices**:
- Tree node coordinates are relative to the `vstProject` control client area (0,0 is at the control's top-left corner)
- First verify tree node positions in the calibration script (read `vstProject.RootNodeCount` + `GetNodeAt`)
- Tree node row height scales under different DPI, so coordinate offsets should be multiplied by `coord_scale`
- Tree node text may be truncated; prefer index coordinates (Nth row) over pixel values

**Pitfalls**: `@x,y` coordinate system is relative to the control, not a common coordinate system → confirm the tree control is not nested inside a scrollbox/panel (nesting changes the relative coordinate origin); after the menu bar pops up, coordinate offsets change → open the menu first, then `capture`, and locate menu items via OCR.

