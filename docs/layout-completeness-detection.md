# UI Layout Completeness Detection — Technical Research and Solution Design

> Goal: Automatically detect complete layout structure information from UI screenshots (element type, position, text, hierarchy),
> output structured JSON/DFM, for LLMs to reference when generating Delphi interface code.

---

## 1. Background and Motivation

The current project already has:

| Capability | Tool | Limitation |
|------|------|--------|
| PP-OCRv6 text recognition | `ocr` tool | Only recognizes text, does not understand element types and structure |
| Text boundary capture | `textbounds` (paint-hook) | Only captures GDI/GDI+ text, does not distinguish element types |
| Image difference comparison | `ocr diff` | Can only compare differences between two images, does not analyze a single layout |
| Static DFM audit | `layout_audit` | Requires DFM source code, cannot work from screenshots |
| Control tree extraction | `dumpstate` / `formsum` | Requires Delphi runtime, cannot work from screenshots |
| DFM generation | `manage_component` / `create_component_dfm` | Requires Pascal code, cannot work from screenshots |

**Core gap**: the reverse pipeline from screenshot → DFM, i.e. inferring a Delphi DFM description file from a UI screenshot.

Unlike general CV tasks of "detecting elements in screenshots", Delphi DFM contains a large amount of information that **cannot be inferred from pixels**:

| Information | Difficulty of recovery from screenshot | Source |
|------|:-------------:|------|
| **Position / Size** (Left/Top/Width/Height) | ⭐ Easy | Precise measurement of pixel coordinates |
| **Text content** (Caption/Text/Items) | ⭐⭐ | OCR extraction, needs matching to controls |
| **Hierarchy** (Panel→GroupBox→Button) | ⭐⭐ | Spatial containment + spacing analysis inference |
| **Control type** (TButton/TcxGrid...) | ⭐⭐⭐ | Visual style → classification (requires training) |
| **Property values** (Enabled/ReadOnly/Visible) | ⭐⭐⭐⭐ | Color/grayscale hints, not fully reliable |
| **Event bindings** (OnClick etc.) | ⭐⭐⭐⭐⭐ | Pure code logic, invisible in screenshots |
| **Control name** (Name property) | ⭐⭐⭐⭐⭐ | Cannot be inferred without naming convention |

---

## 2. Recommended Solution: Synthetic Data + ONNX Inference

### 2.1 Core Idea

The project's unique advantage is that **`dumpstate` + `capture` can automatically generate annotated data at zero cost**:

```
Training data generation (only needs to run once):
  capture(screenshot) + dumpstate(labels)
        ↓                        ↓
    screenshot (PNG) ∪ precise labels (control type + bbox + text + hierarchy)
        ↓
    train YOLO → export ONNX → inference only needs 11MB weights

Inference pipeline (each call):
  new_screenshot → YOLOv11n ONNX → element boxes + types → OCR → hierarchy inference → DFM
```

### 2.2 Pipeline Architecture

```
Input: UI screenshot (PNG/JPEG)
         │
         ▼
┌─────────────────────────────────────────┐
│ Layer 1: Element detection               │
│ ───────────────────────                  │
│ Method A: Traditional CV (OpenCV) — zero-dependency baseline │
│   Sobel/Canny → morphological closing → contour extraction │
│   → classify by aspect ratio/area        │
│                                          │
│ Method B: YOLOv11n ONNX — precise detection (recommended) │
│   onnxruntime inference → 8400 candidates → NMS │
│   → output element types + bbox + confidence │
│                                          │
│ → Output: [{class_id, bbox, confidence},...]│
├─────────────────────────────────────────┤
│ Layer 2: Text extraction                 │
│ ─────────────────────                    │
│ PP-OCRv6 (already in project)            │
│   for each detected element region → OCR text │
│   match text to corresponding element    │
│                                          │
│ → Output: [{..., text}, ...]             │
├─────────────────────────────────────────┤
│ Layer 3: Hierarchy inference             │
│ ───────────────────────                  │
│ spatial containment analysis → container-child element relationships │
│ alignment cluster analysis → HStack/VStack/Grid │
│ spacing analysis → infer equal-spacing layout type │
│ form pairing → Label-Input association   │
│                                          │
│ → Output: hierarchical layout tree       │
├─────────────────────────────────────────┤
│ Layer 4: DFM generation                  │
│ ─────────────────                        │
│ build DFM tree with DfmComponent data structure │
│ control type → Delphi class name mapping │
│ default property filling (TabOrder, Align, Anchors...) │
│ serialize_component() → DFM text         │
│                                          │
│ → Output: DFM text (directly compilable) │
└─────────────────────────────────────────┘
```

### 2.3 Dependency and Accuracy Comparison of Three Solutions

| Solution | New dependency | Disk increment | Accuracy | Applicable scenarios |
|------|---------|:--------:|:----:|---------|
| **Traditional CV** (OpenCV morphology) | None (already available) | **0 MB** | 60-70% | Baseline, rough positioning |
| **YOLOv11n ONNX** ⭐ | `onnx` + weights | **~19 MB** | 85-95%* | **Recommended — lightweight and precise** |
| **YOLOv11n + PyTorch full** | `torch` + `torchvision` | **~1.2 GB** | 85-95%* | Only needed for training, unnecessary for inference |

*Note: 85-95% refers to accuracy after training with Delphi synthetic data. If using general Rico pretrained weights (without Delphi controls), accuracy will decrease significantly.

---

## 3. Synthetic Data Generation Pipeline

This is the core competitiveness of this solution — **no manual annotation required**.

### 3.1 Principle

Using the project's existing `automate_delphi` capability, automatically execute:

```python
# Synthetic data generation pseudocode
for form_name in all_forms:
    for state in states:           # different data filling
        for dpi in dpis:           # DPI variants
            # 1. Navigate to form
            cmd_goto(form_name)
            
            # 2. Fill different data
            type_data(state.data)
            
            # 3. Synchronously collect screenshot + dumpstate
            screenshot = capture(form_name)     # → training image
            labels = dumpstate(form_name)       # → ground truth
            
            # 4. Label format conversion: dumpstate → YOLO format
            yolo_labels = convert_to_yolo(labels)
            save(screenshot, yolo_labels)
```

### 3.2 Annotation Output per Form

Using a typical customer management form as an example:

| dumpstate field | YOLO label usage |
|----------------|--------------|
| `class`: "TcxButton" → `category_id: 1` | Element type |
| `props.Left / Top / Width / Height` → `[cx, cy, w, h]` | Normalized bbox |
| `props.Caption`: "Save" → ignored during training (OCR used instead at inference) | Text content |
| `props.Enabled`: True/False → can additionally annotate disabled state | State property |
| `children[...]` nesting relationship → training hierarchy is not a YOLO task (leave for Phase 3) | Layout structure |

### 3.3 Production Estimate

| Data source | Output per form |
|----------|---------|
| Control instances | 30-80 (depending on form complexity) |
| State variants | 3 (empty data / little data / large data) |
| DPI variants | 2 (100% / 150%) |
| **Total per form** | **~180-480 annotated instances** |

**Generation speed**: about 500ms per form (goto + capture + dumpstate + format conversion)

```
50 forms × 3 states × 2 DPI × 0.5s = 150s ≈ 2.5 minutes
Output: ~9,000-24,000 annotated instances
```

**2.5 minutes is enough to produce tens of thousands of Delphi-specific annotated data**.

### 3.4 Delphi Control → YOLO Class Mapping (Example)

Initial training recommends covering the 15-20 most common control types:

| class_id | Delphi control class | Visual features | Corresponding DFM properties |
|:--------:|--------------|---------|--------------|
| 0 | `background` (background) | background region of the entire screenshot | — |
| 1 | `TButton` / `TcxButton` / `TBitBtn` | rectangular raised button | Caption, ModalResult |
| 2 | `TEdit` / `TcxTextEdit` / `TMaskEdit` | hollow rectangular input box | Text, MaxLength |
| 3 | `TLabel` / `TcxLabel` / `TStaticText` | pure text label | Caption, FocusControl |
| 4 | `TComboBox` / `TcxComboBox` | box with drop-down arrow | Items, ItemIndex |
| 5 | `TCheckBox` / `TcxCheckBox` | with check box | Checked, State |
| 6 | `TRadioButton` / `TcxRadioButton` | circular radio button | Checked |
| 7 | `TListBox` / `TcxListBox` | list area | Items, ItemIndex |
| 8 | `TMemo` / `TRichEdit` / `TcxMemo` | multi-line text area | Lines, ScrollBars |
| 9 | `TPanel` / `TcxGroupBox` / `TGroupBox` | container/panel | Caption, Align |
| 10 | `TPageControl` / `TcxPageControl` | tab strip | Pages, ActivePage |
| 11 | `TStringGrid` / `TcxGrid` / `TDBGrid` | table | Cells, ColCount |
| 12 | `TTreeView` / `TcxTreeList` | tree control | Items, Selected |
| 13 | `TDateTimePicker` / `TcxDateEdit` | date/time picker | Date, Time |
| 14 | `TProgressBar` / `TcxProgressBar` | progress bar | Position, Max |
| 15 | `TScrollBar` / scrollbar | scrollbar | Position, Min, Max |
| 16 | `TMainMenu` / menu bar | top menu | Items |
| 17 | `TToolBar` / `TCoolBar` / toolbar | button strip | Buttons |
| 18 | `TStatusBar` | bottom status bar | Panels |
| 19 | `TImage` / `TcxImage` | image/icon | Picture |
| 20+ | other third-party controls | each has its own features | extend as needed |

### 3.5 Training Process (Requires PyTorch Environment, Can Be Done on Another Machine)

```
Training phase (requires GPU / or slow CPU run):
  ┌─────────────────────────────────────────────┐
  │ conda create -n yolo-train python=3.11        │
  │ pip install ultralytics torch torchvision     │  ← ~1.2 GB, training only
  │                                               │
  │ yolo train                                     │
  │   model=yolo11n.pt                             │  ← transfer from COCO pretraining
  │   data=delphi_dataset.yaml                     │
  │   epochs=200                                   │
  │   imgsz=640                                    │
  │                                               │
  │ Output: best.pt → export best.onnx (~11MB)     │
  └─────────────────────────────────────────────┘

Inference phase (ONNX only, no PyTorch):
  ┌─────────────────────────────────────────────┐
  │ pip install onnxruntime onnx                  │  ← +~15 MB, only needed once
  │ download best.onnx (~11MB)                    │
  │                                               │
  │ # onnxruntime inference, no torch needed      │
  │ session = ort.InferenceSession("best.onnx")    │
  │ outputs = session.run(None, {input_name: img}) │
  └─────────────────────────────────────────────┘
```

---

## 4. Hierarchy Inference Algorithm

YOLO detection output is a **flat bbox list**, which needs post-processing to build a hierarchy tree.

### 4.1 Spatial Containment Detection

```python
def build_hierarchy(detections: list[Detection]) -> TreeNode:
    """Build element tree via spatial containment relationships."""
    # Sort by area descending (ensure containers are processed first)
    sorted_dets = sorted(detections, key=lambda d: d.area, reverse=True)
    roots = []
    
    for det in sorted_dets:
        parent = find_container(det, roots)
        if parent:
            parent.children.append(det)
        else:
            roots.append(TreeNode(element=det))
    return roots

def find_container(det: Detection, roots: list[TreeNode]) -> TreeNode | None:
    """Find the smallest container that contains det."""
    candidates = []
    for root in roots:
        if contains(root.bbox, det.bbox):
            # Recursively search subtrees for a more precise parent container
            sub = find_container_in_tree(det, root)
            if sub:
                candidates.append(sub)
            else:
                candidates.append(root)
    # Return the smallest (most precise) container
    return min(candidates, key=lambda n: n.area) if candidates else None
```

### 4.2 Layout Type Inference

```python
def infer_layout_type(elements: list[Detection]) -> str:
    """Infer the layout arrangement of a group of child elements."""
    if len(elements) < 2:
        return "single"
    
    centers_x = [e.cx for e in elements]
    centers_y = [e.cy for e in elements]
    tops = [e.top for e in elements]
    lefts = [e.left for e in elements]
    
    y_spread = max(centers_y) - min(centers_y)
    x_spread = max(centers_x) - min(centers_x)
    avg_h = sum(e.h for e in elements) / len(elements)
    avg_w = sum(e.w for e in elements) / len(elements)
    
    # HStack: Y centers are close
    if y_spread < avg_h * 0.5:
        return "hstack"
    # VStack: X centers are close
    if x_spread < avg_w * 0.5:
        return "vstack"
    # Grid: check row/column spacing consistency
    if is_uniform_spacing(tops, lefts):
        return "grid"
    return "zstack"
```

### 4.3 Form Field Pairing (Label-Input Association)

```python
def pair_form_fields(elements: list[Detection]) -> list[FormField]:
    """Identify label + input box pairs."""
    labels = [e for e in elements if e.class_id == 3]   # TLabel
    inputs = [e for e in elements if e.class_id in (2, 4)]  # TEdit, TComboBox
    
    pairs = []
    for label in labels:
        # Find the nearest input box to the right of or directly below the label
        nearest = find_nearest_right_below(label, inputs)
        if nearest and vertical_align_tolerance(label, nearest, pixels=5):
            pairs.append(FormField(label=label, input=nearest))
    return pairs
```

---

## 5. ONNX Inference Code Template

```python
"""src/detection/yolo_onnx.py — YOLOv11n ONNX inference wrapper"""

import numpy as np
import cv2
import onnxruntime as ort
from dataclasses import dataclass

@dataclass
class Detection:
    class_id: int
    confidence: float
    x: int      # left
    y: int      # top
    w: int      # width
    h: int      # height

class YOLOONNXDetector:
    """Pure ONNX Runtime YOLO detector, no PyTorch dependency."""
    
    def __init__(self, model_path: str, conf_thresh: float = 0.25):
        self.session = ort.InferenceSession(model_path)
        self.input_name = self.session.get_inputs()[0].name
        self.conf_thresh = conf_thresh
        
        # YOLOv11n output shape: [1, 84, 8400] (cx,cy,w,h + 80 COCO class probs)
        # After replacing with custom classes, output shape: [1, N+4, 8400]
    
    def preprocess(self, image: np.ndarray) -> np.ndarray:
        """Preprocess: resize to 640×640 + normalization."""
        h, w = image.shape[:2]
        scale = min(640 / w, 640 / h)
        nw, nh = int(w * scale), int(h * scale)
        resized = cv2.resize(image, (nw, nh))
        
        # pad to 640×640
        dw, dh = (640 - nw) // 2, (640 - nh) // 2
        padded = cv2.copyMakeBorder(
            resized, dh, dh + (640 - nh) % 2,
            dw, dw + (640 - nw) % 2,
            cv2.BORDER_CONSTANT, value=(114, 114, 114)
        )
        # HWC → CHW, BGR → RGB, normalization
        blob = padded.astype(np.float32) / 255.0
        blob = np.transpose(blob, (2, 0, 1))[np.newaxis, ...]
        return blob, scale, dw, dh
    
    def postprocess(self, outputs: np.ndarray, scale: float, dw: int, dh: int,
                    orig_shape: tuple) -> list[Detection]:
        """Postprocess: decode bbox + NMS."""
        # outputs shape: [1, 84+N, 8400]
        outputs = outputs[0]  # [84+N, 8400]
        
        # Extract bbox (cx, cy, w, h) and class probs
        bboxes = outputs[:4, :]    # [4, 8400]
        scores = outputs[4:, :]    # [N, 8400]
        class_ids = scores.argmax(axis=0)
        confs = scores.max(axis=0)
        
        # Filter low confidence
        mask = confs > self.conf_thresh
        if not mask.any():
            return []
        
        bboxes = bboxes[:, mask]
        class_ids = class_ids[mask]
        confs = confs[mask]
        
        # Convert back to original coordinates
        detections = []
        for i in range(len(class_ids)):
            cx, cy, w, h = bboxes[:, i]
            # Remove padding
            cx = (cx - dw) / scale
            cy = (cy - dh) / scale
            w = w / scale
            h = h / scale
            
            x = int(cx - w / 2)
            y = int(cy - h / 2)
            
            detections.append(Detection(
                class_id=int(class_ids[i]),
                confidence=float(confs[i]),
                x=max(0, x), y=max(0, y),
                w=int(w), h=int(h),
            ))
        
        # NMS deduplication
        return self._nms(detections)
    
    def detect(self, image_path: str) -> list[Detection]:
        """Complete inference pipeline."""
        img = cv2.imread(image_path)
        orig = img.shape[:2]
        blob, scale, dw, dh = self.preprocess(img)
        outputs = self.session.run(None, {self.input_name: blob})
        return self.postprocess(outputs[0], scale, dw, dh, orig)
```

---

## 6. DFM Generation (Detection Results → DFM Text)

```python
"""src/detection/dfm_generator.py — Detection results → DFM conversion"""

from src.tools.dfm_parser import DfmComponent, DfmProperty, serialize_component

# Delphi control class name mapping
CLASS_MAP = {
    1:  "TButton",   2:  "TEdit",      3:  "TLabel",
    4:  "TComboBox", 5:  "TCheckBox",  6:  "TRadioButton",
    7:  "TListBox",  8:  "TMemo",      9:  "TPanel",
    10: "TPageControl", 11: "TStringGrid",
    # ...
}

def detections_to_dfm(detections: list[Detection],
                      hierarchy: list[TreeNode],
                      screen_w: int, screen_h: int) -> str:
    """Convert detection results to DFM text."""
    
    def build(node) -> DfmComponent:
        det = node.element
        cls_name = CLASS_MAP.get(det.class_id, "TControl")
        comp = DfmComponent(
            name=_gen_name(cls_name, node),  # Button1, Edit2, ...
            class_name=cls_name,
            properties=[
                DfmProperty(name="Left",   raw_value=str(det.x)),
                DfmProperty(name="Top",    raw_value=str(det.y)),
                DfmProperty(name="Width",  raw_value=str(det.w)),
                DfmProperty(name="Height", raw_value=str(det.h)),
                DfmProperty(name="TabOrder", raw_value="0"),  # Default, needs adjustment
            ]
        )
        if cls_name in ("TButton", "TLabel", "TCheckBox", "TRadioButton"):
            comp.properties.append(
                DfmProperty(name="Caption", raw_value=det.text or cls_name))
        elif cls_name in ("TEdit", "TMemo", "TComboBox"):
            comp.properties.append(
                DfmProperty(name="Text", raw_value=det.text or ""))
        for child in node.children:
            comp.children.append(build(child))
        return comp
    
    # Create Form root node
    form = DfmComponent(
        name="Form1", class_name="TForm",
        properties=[
            DfmProperty(name="Left", raw_value="0"),
            DfmProperty(name="Top", raw_value="0"),
            DfmProperty(name="Width", raw_value=str(screen_w)),
            DfmProperty(name="Height", raw_value=str(screen_h)),
        ]
    )
    for root in hierarchy:
        form.children.append(build(root))
    
    return serialize_component(form)

def _gen_name(cls_name: str, node) -> str:
    """Generate control name (remove T prefix + sequence number)."""
    prefix = cls_name[1:] if cls_name.startswith("T") else cls_name
    # Simple implementation: use global counter
    return f"{prefix}{_name_counter[cls_name]}"
```

---

## 7. Output JSON Schema (for LLM Reference)

```json
{
  "schema_version": "1.0",
  "canvas": {"width": 1920, "height": 1080},
  
  "children": [
    {
      "type": "container",
      "role": "sidebar",
      "class_hint": "TPanel",
      "rect": {"x": 0, "y": 56, "width": 240, "height": 1024},
      "layout": "vstack",
      "children": [
        {"type": "label", "text": "项目管理", "rect": {...}, "selected": true},
        {"type": "label", "text": "系统设置", "rect": {...}, "selected": false}
      ]
    },
    {
      "type": "container",
      "role": "content",
      "class_hint": "TPanel",
      "rect": {"x": 240, "y": 56, "width": 1680, "height": 1024},
      "layout": "vstack",
      "children": [
        {"type": "label", "text": "客户列表", "class_hint": "TLabel", "rect": {...}},
        {
          "type": "form-row",
          "layout": "hstack",
          "rect": {...},
          "children": [
            {"type": "input", "placeholder": "输入客户名", "class_hint": "TEdit", "rect": {...}},
            {"type": "button", "text": "搜索", "class_hint": "TButton", "rect": {...}}
          ]
        },
        {
          "type": "datagrid",
          "class_hint": "TcxGrid",
          "rect": {...},
          "columns": [
            {"name": "客户名称", "width": 200},
            {"name": "手机号", "width": 150}
          ]
        }
      ]
    }
  ]
}
```

---

## 8. Dependency Changes

### pyproject.toml Increment

```toml
# Add optional dependency group
[project.optional-dependencies]
# ... existing dependencies ...

# Layout detection — ONNX YOLO inference
layout = [
    "onnx>=1.16.0",
]

# Layout detection — full (including training capability, requires GPU or another machine)
layout-full = [
    "daofy-for-delphi[layout]",
    # Training requires PyTorch, but it is done on another machine and is not included here
]
```

### Installation Steps

```bash
# Inference environment (machine where MCP Server runs)
pip install daofy-for-delphi[layout]

# Download ONNX weights (about 11MB)
# Method 1: download best.onnx from training results
# Method 2: use our provided pretrained weights (included in releases)

# Training environment (another machine with GPU, or slow CPU run)
conda create -n yolo-train python=3.11
pip install ultralytics torch torchvision
yolo train model=yolo11n.pt data=delphi_dataset.yaml epochs=200
yolo export model=runs/train/exp/weights/best.pt format=onnx
```

### New Module Structure

```
src/
├── detection/                     # New: layout detection module
│   ├── __init__.py                # analyze_layout() entry point
│   ├── yolo_onnx.py               # ONNX YOLO inference wrapper (no torch dependency)
│   ├── opencv_detector.py         # Traditional CV detection (zero extra dependency baseline)
│   ├── layout_parser.py           # Hierarchy inference
│   ├── dfm_generator.py           # Detection results → DFM conversion
│   ├── text_extractor.py          # Text extraction (calls existing OCR service)
│   └── weights/                   # ONNX weight cache (excluded by .gitignore)
│       └── .gitkeep
```

---

## 9. Implementation Path

### Phase 1: Synthetic Data Generation + Traditional CV Baseline (3-5 person-days)

| Task | Output |
|------|------|
| Synthetic data script | `generate_training_data.py` — automatically capture screenshots + dumpstate collect annotations |
| YOLO format converter | dumpstate JSON → COCO/YOLO label format |
| OpenCV element detection | Sobel/Canny + contours + rectangle filtering → bbox |
| Element classification heuristics | Classify by aspect ratio/area/position (Button/Input/Label/Panel) |
| Simple layout inference | Spatial containment + alignment clustering |

**Dependency increment**: 0 MB (all already available)

### Phase 2: ONNX YOLO Training and Integration (5-8 person-days, training done on another machine)

| Task | Output |
|------|------|
| Install `ultralytics` + `torch` (training machine) | Training environment |
| Prepare Delphi dataset (Phase 1 output) | `dataset.yaml` + annotation files |
| Train YOLOv11n | `best.pt` + `best.onnx` |
| `yolo_onnx.py` ONNX inference wrapper | Pure `onnxruntime` inference, no torch |
| Dual-backend fusion | CV + YOLO result confidence fusion |

**Dependency increment (inference machine)**: ~19 MB (onnx + weights)

### Phase 3: Hierarchy Inference + DFM Generation (3-5 person-days)

| Task | Output |
|------|------|
| `layout_parser.py` | Spatial containment + alignment + form pairing → hierarchy tree |
| `dfm_generator.py` | Detection results → DFM text |
| Schema design | Structured JSON output for LLM reference |
| Property default optimization | Reasonable defaults for TabOrder/Align/Anchors etc. |

### Phase 4: Iterative Optimization (ongoing)

| Task | Output |
|------|------|
| Expand training data categories | Cover more third-party controls (DevExpress, TMS, JVCL) |
| Improve layout type accuracy | Improve inference for Grid/complex nesting |
| Text-control matching | OCR text correctly attributed to corresponding controls |
| Event inference | Button click behavior etc. (VLM assisted) |

---

## 10. Collaboration with Existing Tools

```
Screenshot → layout detection → JSON → LLM → DFM + PAS code
                            ↓
                     manage_component → precisely insert into existing DFM
                            ↓
                     create_component_dfm → verify generated DFM compiles
                            ↓
                     layout_audit → check layout quality (overlap/alignment/spacing)
```

---

## 11. Reference Resources

| Resource | Link |
|------|------|
| YOLOv11 (Ultralytics) | https://docs.ultralytics.com/models/yolo11/ |
| ONNX Runtime | https://onnxruntime.ai/ |
| ONNX export documentation | https://docs.ultralytics.com/integrations/onnx |
| UIED (traditional CV reference) | https://github.com/MulongXie/UIED |
| Rico Dataset | https://interactionmining.org/archive/rico |
| PP-OCRv6 (already in project) | `src/services/ocr_service.py` |
| DFM Parser (already in project) | `src/tools/dfm_parser.py` |
| Layout Audit (already in project) | `src/tools/layout_audit.py` |
| create_component_dfm (already in project) | `src/tools/create_component_dfm.py` |

---

## 12. Conclusion

**Recommended solution: synthetic-data-driven YOLOv11n ONNX inference**, for the following reasons:

1. **Zero-cost synthetic data** — `dumpstate` + `capture` can produce tens of thousands of Delphi-specific annotations in 2.5 minutes
2. **Inference dependency only +19 MB** — `onnxruntime` is already preinstalled in the project, only need to add `onnx` package and ~11MB ONNX weights
3. **No GPU required** — ONNX inference runs on CPU, ~30-100ms/image
4. **Phase 1 can start with zero incremental dependencies** — OpenCV + NumPy already installed
5. **DFM generation reuses existing tools** — `dfm_parser.serialize_component()` directly produces DFM text

---

## 13. Audit Findings and Solution Improvements

### 13.1 ✅ Verified Assumptions

| Assumption | Result | Evidence |
|------|:----:|------|
| YOLO ONNX output format `[1, 4+N, 8400]` | ✅ Correct | Ultralytics documentation confirms; post-processing flow in code template is correct |
| Can export ONNX with embedded NMS (`nms=True`) | ✅ Feasible | Add `nms=True` during export; output simplifies to `[1, max_det, 6]`, eliminating Python-side NMS |
| Synthetic data can control class distribution | ✅ Feasible | Control via sampling weights in dataset.yaml or generation script during training |
| `onnxruntime` already installed | ✅ Already installed in project | `onnxruntime 1.27.0` already exists in OCR optional dependencies |
| **`onnx` package not needed on inference side** | ✅ Confirmed | `onnxruntime` directly loads `.onnx` files for inference; `onnx` package is only for model validation after training |

### 13.2 ⚠️ Audit Issue Summary

#### Issue 1: Small control detection (resolved)

**Problem**: YOLOv11n default input 640×640; if the original screenshot is 1920×1080, scale ratio ~0.33, a 16×16 icon becomes ~5px → undetectable.

**Solution (provided by user)**: During synthetic data generation, **actively resize form screenshots to 640×480** (standard VCL client area size), then feed to YOLO. At this point the scale ratio is 1.0, a 16×16 icon is still 16×16 pixels, covering a 2×2 grid at the P3 feature layer (stride 8) — **more than enough**.

```
Feature layer   Stride   Grid     16×16 coverage cells   Detectable?
P3        8      80×80    2×2             ✅
P4       16      40×40    1×1             ✅
P5       32      20×20    0.5×0.5         ❌ (but this layer is not relied upon)
```

**Note**: Preprocessing for training data and inference data must be consistent — both first resize to 640×480, then pad to 640×640.

#### Issue 2: Dependency increment can be further reduced

The original solution wrote that the `onnx` package (~8MB) needs to be installed. Audit found that **the inference side does not need the `onnx` package** — `onnxruntime` can directly load `.onnx` model files:

```python
import onnxruntime as ort
session = ort.InferenceSession("yolo11n.onnx")  # OK, no onnx package needed
```

Therefore, the **actual new dependency on the inference side is 0 packages**; only the ~11MB ONNX weight file needs to be downloaded.

```diff
- layout = ["onnx>=1.16.0"]
+ # No new packages are needed on the inference side; onnxruntime is already installed
+ # Only need to download weights/best.onnx (~11MB)
```

#### Issue 3: `_gen_name` control naming implementation has a bug

The original code used an uninitialized and unincremented global `_name_counter` dictionary. Fix:

```python
def _gen_name(cls_name: str, seen_names: set[str]) -> str:
    prefix = cls_name[1:] if cls_name.startswith("T") else cls_name
    idx = 1
    while f"{prefix}{idx}" in seen_names:
        idx += 1
    name = f"{prefix}{idx}"
    seen_names.add(name)
    return name
```

#### Issue 4: ONNX export recommends `nms=True`

`model.export(format="onnx", nms=True)` embeds NMS during export, and the output simplifies to `[1, max_det, 6]`; there is no need to implement the NMS algorithm on the Python side.

#### Issue 5: Missing quantitative validation metrics

Need to define clear accuracy targets for judging whether training has converged:

```yaml
# Evaluation metrics
mAP@0.5:      > 0.85   # Target
mAP@0.5:0.95: > 0.65   # Target
Recall:       > 0.90   # Do not miss controls
Precision:    > 0.85   # Do not false positive
Small_AP:     > 0.60   # Accuracy for small controls (area <32²)
Container_AP: > 0.80   # Accuracy for container classes (TPanel)
```

#### Issue 6: Need Plan B alternative

If YOLO training convergence is not ideal (dataset too small, class distribution unbalanced), the backup solution is pure traditional CV:

```
Screenshot → OpenCV morphology → contours → rectangular regions
     → classify by aspect ratio/area heuristics
     → OCR text extraction
     → spatial containment → hierarchy tree
     → DFM generation
```

Accuracy is lower (~60-70%) but **zero extra dependencies, zero training, zero waiting**.

#### Issue 7: Data augmentation strategy needs UI-specific optimization

UI screenshots are not natural images. The following augmentations are **forbidden**:

| Forbidden augmentation | Reason |
|-----------|------|
| GaussianBlur / noise | Blurs text strokes, damages OCR |
| Heavy color jitter | Changes button colors, affects type judgment |
| Random rotation | UI controls never rotate |

Recommended structure-preserving augmentations:

| Augmentation | Description |
|------|------|
| Random crop (0.6-1.0) | Simulates local screenshots at different positions |
| Horizontal flip (p=0.5) | Delphi UI is occasionally symmetric |
| Brightness ±20% | Simulates different monitor brightness |
| Mosaic (p=0.5) | Mosaic augmentation for context diversity |
| Scale ±10% | Simulates different DPI |
| Random erasing (p=0.1) | Simulates controls being occluded |

#### Issue 8: Training data deduplication

Different forms may share controls with identical visual appearance (e.g., 50 forms share the same `TFindUnitDialog`). Mixing them directly for training will cause distribution bias.

**Recommendation**: When generating data, hash the layout features (position + size + type) of each control for deduplication, ensuring the training set does not favor repeatedly appearing controls.

