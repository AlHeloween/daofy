<!-- @when: Verify positional relationships of controls on a form: left alignment, consistent spacing, no overlap -->
<!-- @part-of: ui-testing -->

#### L. Visual Layout Alignment

| Element | Content |
|------|------|
| **Goal** | Verify positional relationships of controls on a form: left alignment, consistent spacing, no overlap, label-field pairing |
| **Strategy** | Prefer `rget` to precisely read BoundsRect of key controls; when there are many controls, use `dumpstate props=...` for batch collection; for non-VCL controls fall back to `detect` text boxes to infer positions |
| **Key commands** | `rget`, `dumpstate`, `detect` |

**Background**: Layout issues in Delphi GUI are extremely difficult to find through compilation. Typical scenarios: Label and Edit misaligned, spacing deformed under different DPI, controls overlapping due to incorrect `Align`/`Anchors` property configuration, Chinese characters expanding Labels and squeezing adjacent controls. Reading `BoundsRect` via RTTI is a pixel-precise method, far better than judging by screenshot with the naked eye.

**Static prerequisite**: Before runtime collection, first use `delphi_project(action="layout", base_dir="...")` to audit overlap, out-of-bounds, same-column alignment, Label-field spacing, and TabOrder in the DFM. After static checks pass, use this scenario to verify real runtime effects and cross-DPI stability.

##### L1. Collect control positions — `rget` / `dumpstate` via pipeline RTTI

```python
# rget BoundsRect for a single control
r = daofy_automate(action="gui", app_path="App.exe", script=[
    {"cmd": "goto", "target": "TMainForm"},
    {"cmd": "rget", "target": "EditName.BoundsRect"},
    {"cmd": "rget", "target": "EditPhone.BoundsRect"},
    {"cmd": "rget", "target": "EditAddr.BoundsRect"},
    {"cmd": "rget", "target": "LabelName.BoundsRect"},
    {"cmd": "exit"},
])
# BoundsRect returns: (left, top, right, bottom)
# → (x, y, x+w, y+h)
```

You can also use `dumpstate` with the `props` parameter to batch-get all form control positions:

```python
r = daofy_automate(action="gui", app_path="App.exe", script=[
    {"cmd": "goto", "target": "TMainForm"},
    {"cmd": "dumpstate", "props": "name,left,top,width,height,class"},
    {"cmd": "exit"},
])
```

Afterwards parse the control tree returned by `dumpstate` on the Python side and extract layout coordinates for each control.

##### L2. Left alignment detection — same-column controls have consistent Left

```python
controls = {
    "EditName":  {"left": 120, "top": 10, "width": 200, "height": 24},
    "EditPhone": {"left": 120, "top": 40, "width": 200, "height": 24},
    "EditAddr":  {"left": 120, "top": 70, "width": 200, "height": 24},
}

left_values = [c["left"] for c in controls.values()]
if max(left_values) - min(left_values) <= 2:
    print(f"✅ Left alignment consistent: Left={left_values[0]}")
else:
    print(f"⚠️ Left alignment deviation: {left_values}")
```

##### L3. Spacing consistency detection — vertical spacing between adjacent controls

```python
# Sort by top, calculate adjacent gaps
sorted_controls = sorted(controls.values(), key=lambda c: c["top"])
gaps = []
for i in range(len(sorted_controls) - 1):
    gap = sorted_controls[i + 1]["top"] - (
        sorted_controls[i]["top"] + sorted_controls[i]["height"]
    )
    gaps.append(gap)

if gaps:
    avg_gap = sum(gaps) / len(gaps)
    max_deviation = max(abs(g - avg_gap) for g in gaps)
    if max_deviation <= 2:
        print(f"✅ Spacing consistent: {avg_gap:.0f}px (max deviation {max_deviation}px)")
    else:
        print(f"⚠️ Spacing inconsistent: {gaps} (expected ~{avg_gap:.0f}px)")
```

##### L4. Overlap detection — BoundsRect intersection

```python
def bounds_intersect(a, b):
    """Return whether the BoundsRects of two controls overlap."""
    ax1, ay1, ax2, ay2 = (a["left"], a["top"],
                           a["left"] + a["width"], a["top"] + a["height"])
    bx1, by1, bx2, by2 = (b["left"], b["top"],
                           b["left"] + b["width"], b["top"] + b["height"])
    return (ax1 < bx2 and ax2 > bx1 and ay1 < by2 and ay2 > by1)

# Check all control pairs
items = list(controls.items())
overlaps = []
for i in range(len(items)):
    for j in range(i + 1, len(items)):
        name_a, ctrl_a = items[i]
        name_b, ctrl_b = items[j]
        if bounds_intersect(ctrl_a, ctrl_b):
            overlaps.append((name_a, name_b))

if overlaps:
    for a, b in overlaps:
        print(f"❌ Overlap: {a} and {b}")
else:
    print("✅ No overlap")
```

##### L5. Label-field pairing — Label right side and Edit left side aligned

```python
pairs = [
    ("LabelName", "EditName"),
    ("LabelPhone", "EditPhone"),
    ("LabelAddr", "EditAddr"),
]

misalignments = []
for label_name, edit_name in pairs:
    lbl = controls[label_name]
    edt = controls[edit_name]
    label_right = lbl["left"] + lbl["width"]
    gap = edt["left"] - label_right
    if not (4 <= gap <= 12):
        misalignments.append((label_name, edit_name, gap))

if misalignments:
    for lbl, edt, gap in misalignments:
        print(f"⚠️ {lbl}→{edt} spacing abnormal: {gap}px (expected 4~12px)")
else:
    print("✅ All label-field spacing normal")
```

##### L6. Cross-DPI layout stability — same formula checked under different DPI

```python
def check_layout(controls: dict, dpi_label: str):
    """Check layout metrics under specified DPI."""
    print(f"\n--- {dpi_label} ---")

    # L2: Left alignment
    lefts = [c["left"] for c in controls.values()]
    if max(lefts) - min(lefts) > 2:
        print(f"  ⚠️ Left alignment deviation: {lefts}")
    else:
        print(f"  ✅ Left alignment: Left={lefts[0]}")

    # L3: Spacing
    sorted_ctrl = sorted(controls.values(), key=lambda c: c["top"])
    gaps = []
    for i in range(len(sorted_ctrl) - 1):
        gap = sorted_ctrl[i + 1]["top"] - (
            sorted_ctrl[i]["top"] + sorted_ctrl[i]["height"]
        )
        gaps.append(gap)
    if gaps:
        print(f"  {'✅' if max(gaps)-min(gaps)<=2 else '⚠️'} Spacing: {gaps}")

    # L4: Overlap
    items = list(controls.items())
    over = 0
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a = items[i][1]; b = items[j][1]
            if (a["left"] < b["left"]+b["width"] and
                a["left"]+a["width"] > b["left"] and
                a["top"] < b["top"]+b["height"] and
                a["top"]+a["height"] > b["top"]):
                over += 1
    print(f"  {'✅' if over==0 else '❌'} Overlap: {over} places")

# Pass in control coordinates collected under 100%, 125%, and 150% DPI respectively
check_layout(controls_100, "100% DPI")
check_layout(controls_125, "125% DPI")
check_layout(controls_150, "150% DPI")
```

**DPI expected relationship**: If the Delphi form has `Scaled=True` enabled (default), control `Left` and `Width` should scale precisely by 1.5x from 100%→150%. A deviation >2px indicates abnormal Scaled configuration or incorrect `Anchors` settings:

```python
for name in controls_100