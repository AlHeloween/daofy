<!-- @when: Detect whether text is fully displayed inside a control (no truncation, ellipsis, overflow), especially across DPI -->
<!-- @part-of: ui-testing -->

#### K. Text Display Completeness Verification — Truncation/Overflow/Ellipsis

| Element | Content |
|------|------|
| **Goal** | Detect whether text is fully displayed within a control (no truncation, no ellipsis, no overflow), especially under different DPI scaling |
| **Strategy** | `recognize` gets text + bounding box → `detect` detects actual rendered text area → compare with control bounds/expected width |
| **Key commands** | `recognize`, `detect`, `color`, `diff` |

**Background**: Delphi controls scale fonts under different DPI scaling (100% / 125% / 150% / 200%) while control sizes may not be adjusted synchronously, causing text truncation. RTTI can only read the original `Caption` value and cannot perceive whether the rendered result is clipped. OCR is the only reliable verification method.

##### K1. Ellipsis detection — text truncated at the end

```python
# Recognize text in target region
r = daofy_ocr(action="recognize", image_path="label_caption.png")
first = r["results"][0] if r["results"] else {"text": ""}

# Check for ellipsis
if "..." in first["text"] or "…" in first["text"]:
    print(f"⚠️ Text truncated: {first['text']}")
elif r["results"]:
    print(f"✅ Text complete: {first['text']}, confidence: {first['confidence']}")
```

Note: Whether Delphi's `TLabel` and `TCaption` truncate with an ellipsis depends on `TLabel.Layout` and Windows automatic truncation behavior when `AutoSize=False`. Some controls may clip directly without adding an ellipsis → need to combine with K2 detection.

##### K2. Rendered width vs control width — detect overflow

```python
# Recognize text and get bounding box
r = daofy_ocr(action="recognize", image_path="label_caption.png")
if not r["results"]:
    print("⚠️ OCR did not recognize text; it may be completely overflowed or the color is too light")
else:
    # box format: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]] clockwise
    box = r["results"][0]["box"]
    render_width = box[1][0] - box[0][0]   # top-right.x - top-left.x
    render_height = box[2][1] - box[1][1]  # bottom-right.y - top-right.y

    # Control's expected rendered area (based on design-time control position and size)
    control_width = 150  # Known Label.Width
    control_outer = 12   # Total left/right padding

    if render_width >= control_width - control_outer:
        print(f"⚠️ Text width {render_width}px is close to control boundary {control_width}px, may overflow")
    else:
        print(f"✅ Text is within control: {render_width}/{control_width}px")
```

##### K3. Multi-line text line count detection — confirm all lines render completely

```python
r = daofy_ocr(action="recognize", image_path="memo_text.png")

# Count detected text lines (each result is one line)
lines = [item["text"] for item in r["results"]]

# Check whether the last line looks incomplete (too short or width significantly less than average)
if len(lines) > 1:
    widths = [
        item["box"][1][0] - item["box"][0][0]
        for item in r["results"]
    ]
    last_width = widths[-1]
    avg_width = sum(widths[:-1]) / (len(widths) - 1)

    if last_width < avg_width * 0.4 and last_width < 50:
        print(f"⚠️ Last line width abnormal ({last_width}px vs avg {avg_width:.0f}px), may be truncated")
    else:
        print(f"✅ Multi-line text complete ({len(lines)} lines)")
else:
    print(f"✅ Single-line text: {lines[0] if lines else 'none'}")
```

##### K4. Cross-DPI comparison — rendering differences of the same control under different scaling

```python
# Pre-capture baseline at a DPI known to have no truncation (e.g., 100%)
baseline = daofy_ocr(action="recognize", image_path="caption_100pct.png")
base_box = baseline["results"][0]["box"]
base_width = base_box[1][0] - base_box[0][0]

# Compare at 150% DPI
current = daofy_ocr(action="recognize", image_path="caption_150pct.png")
cur_box = current["results"][0]["box"]
cur_width = cur_box[1][0] - cur_box[0][0]

# Expected width change = scaling ratio (150%/100% = 1.5x)
expected_width = base_width * 1.5
if cur_width < expected_width * 0.9:
    print(f"⚠️ Text width abnormal at 150% DPI: actual {cur_width:.0f}px < expected {expected_width:.0f}px")
    print("   → Text may be truncated or control did not scale correctly")
elif cur_width > expected_width * 1.1:
    print(f"⚠️ Width exceeds expectation: {cur_width:.0f}px vs {expected_width:.0f}px, risk of exceeding control boundary")
else:
    print(f"✅ DPI scaling normal: {cur_width:.0f}px (expected ~{expected_width:.0f}px)")
```

##### K5. Color contrast check — light text on light background is unreadable

```python
c = daofy_ocr(
    action="color",
    image_path="label_caption.png",
    threshold=0.5  # Brightness threshold separates foreground/background
)

if "dark_avg" in c and "light_brightness" in c:
    # Brightness contrast between text (dark) and background (light)
    text_brightness = 1 - c["brightness"] if c["dark_count"] > c["light_count"] else c["brightness"]
    contrast = abs(c["light_brightness"] - text_brightness)
    if contrast < 0.3:
        print(f"⚠️ Text/background contrast too low: {contrast:.2f} (text may be unreadable on light background)")
    else:
        print(f"✅ Contrast normal: {contrast:.2f}")
```

##### K6. Automation script integration — capture key forms under each DPI

```json
[
  {"cmd":"goto","target":"TMainForm"},
  {"cmd":"capture","target":"main_100pct","note":"Run at 100% DPI"},
  {"cmd":"click","target":"BtnOpenForm"},
  {"cmd":"waitfor","target":"TDataForm","prop":"Visible","value":"True","timeout":3000},
  {"cmd":"capture","target":"dataform_100pct"},
  {"cmd":"exit"}
]
```
Run this script separately at 100% / 125% / 150% system scaling → analyze each set of screenshots with K1-K4 on the Python side.

##### K7. OCR verification integrated into test JSON workflow

OCR calls themselves are Python-side `daofy_ocr` tool calls, **not executed inside the JSON script**. However, the JSON script should provide enough input material for OCR (screenshots + position references), so that the Python side can automatically execute OCR assertions.

**Recommended pattern**: capture → Python OCR → assert, forming a complete test step:

```json
[
  {"cmd":"goto","target":"TfrmMain"},
  {"cmd":"click","target":"BtnOpenSettings"},
  {"cmd":"waitfor","target":"TfrmSettings","prop":"Visible","value":"True","timeout":5000},

  {"cmd":"capture","target":"settings_dialog","note":"For OCR to recognize text of each control in the dialog"},

  {"cmd":"rget","target":"Label5.Left","note":"For Python side as control position reference"},
  {"cmd":"rget","target":"Label5.Width"},
  {"cmd":"rget","target":"cbxLanguages.Left"},

  {"cmd":"exit"}
]
```

Python test orchestrator (or large-model post-processing script):

```python
# 1. Recognize text in screenshot
r = daofy_ocr(action="recognize", image_path="snapshots/settings_dialog.png")

# 2. Verify key label text is complete
for item in r["results"]:
    text = item["text"]
    if "Language" in text and "..." in text:
        print(f"❌ Text truncated: {text}")
        failures.append(f"settings_dialog contains ellipsis in '{text}'")

# 3. Check whether bounding box exceeds expected control range
#    From Label5.Left/Width returned by rget, the control position is known
label5_left = 9    # Obtained from rget result
label5_right = 100 # Calculated from rget result
for item in r["results"]:
    box = item["box"]
    render_right = box[1][0]  # top-right x
    if render_right > label5_right + 5:
        print(f"⚠️ Text rendering exceeds Label5 right boundary: {render_right} > {label5_right}")
```

**OCR post-processing assertion table** (what Python side should check after each capture step):

| capture target | OCR checks to perform | Pass criteria |
|-------------|----------------|---------|
| Regular dialog/form | recognize all visible text, compare against expected keywords | Key field content complete, no ellipsis, confidence >0.6 |
| Error/warning pop-up | recognize pop-up text | Does not contain unexpected error codes, button text correct |
| Screenshot after language switch | detect whether text distribution is complete | No right-boundary truncation, no overlapping text boxes |
| Screenshot after menu drop-down | recognize all menu items | Menu item count >= expected count, no garbled text |
| Screenshot after tree expansion | detect node text line count | Line count >= expected expanded node count |
| Before/after rebuild comparison | diff baseline comparison | diff_pixels within a reasonable range (changes present but not abnormal) |

**K7 rule**: After each `capture` step there must be a corresponding OCR or diff check. A `capture` without OCR post-processing is equivalent to manual review and is not part of automated verification.

**Pitfall**: PP-OCR recognition rate decreases for rotated text and artistic fonts → abandon text detection when `recognize` confidence is below 0.6; `detect` returning empty may mean text color is too close to background (use `color` to check contrast); Delphi's `TLabel.AutoSize=True` does not truncate but may break the layout → need to simultaneously detect whether adjacent controls are squeezed (use `diff` to compare against baseline).

