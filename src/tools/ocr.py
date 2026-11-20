"""MCP Tool: ocr — image analysis (text recognition + visual analysis)

Uses PP-OCRv6 medium model for image text detection and recognition.
Pure ONNX Runtime implementation, zero PaddlePaddle dependency.
Models are automatically downloaded to data/ocr-models/ on first use.

Actions:
  recognize  — full OCR: detection + recognition, returns [{text, confidence, box}]
  detect     — text box detection only, returns [{box, score}]
  status     — model loading status
  diff       — screenshot difference comparison: compares two screenshots, returns visually changed regions
  color      — region color analysis: analyzes average color / dominant color / brightness of a specified region
  match      — icon template matching: finds a specified icon/pattern in a screenshot
  analyze    — [unified screenshot analysis] chains OCR + OpenCV detection + layout + color,
               returns structured element list (with type/text/rect/state/paired_label),
               for the LLM to infer UI structure directly from text without a multimodal model.
"""

import logging
import os

from src.services.ocr_service import get_ocr_service

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# Visual analysis functions (pure Pillow/OpenCV, no PP-OCR model dependency)
# ═══════════════════════════════════════════════════════════════


def _image_diff(baseline_path: str, current_path: str,
                threshold: int = 10, output_dir: str = "") -> dict:
    """Compare two screenshots and find visually different regions.

    Args:
        baseline_path: baseline screenshot path
        current_path: current screenshot path
        threshold: pixel difference threshold (0-255, default 10)
        output_dir: difference image output directory (empty means do not save)

    Returns:
        dict: {changed, diff_pixels, diff_percent, regions, diff_image?}
    """
    import cv2
    import numpy as np

    img1 = cv2.imread(baseline_path)
    img2 = cv2.imread(current_path)

    if img1 is None:
        raise FileNotFoundError(f"Cannot read baseline image: {baseline_path}")
    if img2 is None:
        raise FileNotFoundError(f"Cannot read current image: {current_path}")

    # When sizes differ, resize current image to match baseline
    if img1.shape != img2.shape:
        img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]))

    diff = cv2.absdiff(img1, img2)
    gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)

    diff_pixels = int(np.sum(thresh > 0))
    total_pixels = thresh.size
    diff_percent = round(diff_pixels / total_pixels * 100, 4)

    # Connected component analysis to find changed regions
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL,
                                    cv2.CHAIN_APPROX_SIMPLE)

    regions = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if w * h < 16:  # Filter tiny noise points
            continue
        area_pct = round((w * h) / total_pixels * 100, 4)
        mean_diff = float(np.mean(gray[y:y + h, x:x + w]))
        regions.append({
            "bbox": [int(x), int(y), int(x + w), int(y + h)],
            "area_pct": area_pct,
            "mean_diff": round(mean_diff, 1),
        })

    regions.sort(key=lambda r: r["area_pct"], reverse=True)

    result = {
        "changed": diff_pixels > 0,
        "diff_pixels": int(diff_pixels),
        "diff_percent": diff_percent,
        "regions": regions[:50],
    }

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        base = os.path.splitext(os.path.basename(baseline_path))[0]
        diff_path = os.path.join(output_dir, f"diff_{base}.png")
        cv2.imwrite(diff_path, diff)
        result["diff_image"] = diff_path

    return result


def _region_color(image_path: str,
                  region: list | None = None,
                  threshold: float | None = None) -> dict:
    """Analyze color characteristics of a specified image region.

    Args:
        image_path: image path
        region: [x, y, w, h] analysis region; analyzes full image when not passed
        threshold: brightness threshold (0~1). When set, splits pixels into dark/light groups by brightness,
                   computes avg_color separately, to separate text color and background color.

    Returns:
        dict: {avg_color, median_color, brightness, is_grayscale,
               dark_avg?, light_avg?, dark_count?, light_count?}
    """
    from PIL import Image
    import numpy as np

    img = Image.open(image_path).convert("RGB")

    if region:
        x, y, w, h = region
        img = img.crop((x, y, x + w, y + h))

    pixels = np.array(img, dtype=np.float32)

    # Brightness weighted formula: 0.299 R + 0.587 G + 0.114 B
    brightness_map = (pixels[:, :, 0] * 0.299 +
                      pixels[:, :, 1] * 0.587 +
                      pixels[:, :, 2] * 0.114) / 255.0

    avg = [round(float(pixels[:, :, i].mean())) for i in range(3)]
    median = [round(float(np.median(pixels[:, :, i]))) for i in range(3)]
    stddev = [float(pixels[:, :, i].std()) for i in range(3)]

    is_gray = bool(all(s < 15 for s in stddev)
                   and max(avg) - min(avg) < 30)
    brightness = round(sum(avg) / (255 * 3), 3)

    result = {
        "avg_color": {"r": avg[0], "g": avg[1], "b": avg[2]},
        "median_color": {"r": median[0], "g": median[1], "b": median[2]},
        "brightness": brightness,
        "is_grayscale": is_gray,
        "region": {"w": img.width, "h": img.height},
    }

    # Brightness threshold separation: split pixels by brightness into dark group (text/foreground) and light group (background/highlight)
    if threshold is not None:
        dark_mask = brightness_map < threshold
        light_mask = ~dark_mask

        dark_count = int(dark_mask.sum())
        light_count = int(light_mask.sum())

        if dark_count > 0:
            dark_avg = [round(float(pixels[:, :, i][dark_mask].mean()))
                        for i in range(3)]
            result["dark_avg"] = {"r": dark_avg[0], "g": dark_avg[1],
                                  "b": dark_avg[2]}
        result["dark_count"] = dark_count

        if light_count > 0:
            light_avg = [round(float(pixels[:, :, i][light_mask].mean()))
                         for i in range(3)]
            light_brightness = round(
                (light_avg[0] * 0.299 + light_avg[1] * 0.587 +
                 light_avg[2] * 0.114) / 255.0, 3)
            result["light_avg"] = {"r": light_avg[0], "g": light_avg[1],
                                   "b": light_avg[2]}
            result["light_brightness"] = light_brightness
        result["light_count"] = light_count

    return result


def _template_match(image_path: str, template_path: str,
                    threshold: float = 0.8) -> dict:
    """Find a template icon/pattern in a screenshot.

    Args:
        image_path: screenshot path
        template_path: template image path
        threshold: matching threshold (0-1, default 0.8)

    Returns:
        dict: {found, match_count, matches[{bbox, confidence}]}
    """
    import cv2
    import numpy as np

    img = cv2.imread(image_path)
    tpl = cv2.imread(template_path)

    if img is None:
        raise FileNotFoundError(f"Cannot read image: {image_path}")
    if tpl is None:
        raise FileNotFoundError(f"Cannot read template: {template_path}")

    if img.shape[0] < tpl.shape[0] or img.shape[1] < tpl.shape[1]:
        return {"found": False, "match_count": 0, "matches": [],
                "error": "Template size is larger than screenshot"}

    result_mat = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
    locations = np.where(result_mat >= threshold)

    h, w = tpl.shape[:2]
    raw_matches = []
    for pt in zip(*locations[::-1]):
        x, y = pt
        raw_matches.append({
            "bbox": [int(x), int(y), int(x + w), int(y + h)],
            "confidence": round(float(result_mat[y, x]), 3),
        })

    # Non-maximum suppression (NMS) deduplication
    raw_matches.sort(key=lambda m: m["confidence"], reverse=True)
    kept = []
    for m in raw_matches:
        overlapping = False
        for k in kept:
            if _bbox_overlap(m["bbox"], k["bbox"]) > 0.5:
                overlapping = True
                break
        if not overlapping:
            kept.append(m)

    return {
        "found": len(kept) > 0,
        "match_count": len(kept),
        "matches": kept[:20],
        "threshold_used": threshold,
    }


def _bbox_overlap(a: list, b: list) -> float:
    """Calculate the IoU of two bboxes."""
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    xi1, yi1 = max(ax1, bx1), max(ay1, by1)
    xi2, yi2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0, xi2 - xi1) * max(0, yi2 - yi1)
    a_area = (ax2 - ax1) * (ay2 - ay1)
    b_area = (bx2 - bx1) * (by2 - by1)
    union = a_area + b_area - inter
    return inter / union if union > 0 else 0


# ═══════════════════════════════════════════════════════════════
# Unified screenshot analysis (chains OCR + Detection + Layout + Color)
# ═══════════════════════════════════════════════════════════════


def _bbox_iou(a_box: list, b_box: list) -> float:
    """Calculate the IoU of two bboxes, compatible with OCR four-point format [[x1,y1],[x2,y2],...]."""
    # Compatible with four-point format → [x1,y1,x2,y2]
    def _to_xyxy(box):
        if isinstance(box[0], list):
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            return [min(xs), min(ys), max(xs), max(ys)]
        return box

    a = _to_xyxy(a_box)
    b = _to_xyxy(b_box)
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    xi1 = max(ax1, bx1)
    yi1 = max(ay1, by1)
    xi2 = min(ax2, bx2)
    yi2 = min(ay2, by2)
    inter = max(0, xi2 - xi1) * max(0, yi2 - yi1)
    a_area = (ax2 - ax1) * (ay2 - ay1)
    b_area = (bx2 - bx1) * (by2 - by1)
    union = a_area + b_area - inter
    return inter / union if union > 0 else 0


def _infer_element_state(img, x: int, y: int, w: int, h: int) -> str:
    """Infer UI element state (enabled/disabled) based on color analysis.
    
    Simple heuristic: low average brightness + low standard deviation + low saturation → disabled.
    """
    import numpy as np

    img_h, img_w = img.shape[:2]
    x = max(0, x)
    y = max(0, y)
    w = min(w, img_w - x)
    h = min(h, img_h - y)
    if w <= 0 or h <= 0:
        return "enabled"

    roi = img[y:y + h, x:x + w].astype(np.float32)
    brightness = (roi[:, :, 0] * 0.299 + roi[:, :, 1] * 0.587 + roi[:, :, 2] * 0.114) / 255.0
    avg_b = float(np.mean(brightness))
    std_b = float(np.std(brightness))

    # Saturation
    r, g, b = roi[:, :, 0], roi[:, :, 1], roi[:, :, 2]
    max_rgb = np.maximum(np.maximum(r, g), b).astype(float)
    min_rgb = np.minimum(np.minimum(r, g), b).astype(float)
    sat = float(np.mean((max_rgb - min_rgb) / (max_rgb + 1e-6)))

    # Dark + low contrast → disabled
    if avg_b < 0.45 and std_b < 20 and sat < 0.15:
        return "disabled"
    return "enabled"


def _pair_labels_with_inputs(elements: list[dict]):
    """Pair label text with adjacent input boxes (in-place modification).
    
    Rules:
    - Label detection: text ending with ':'/'：'/':'
    - Input box is to the right of the label, with similar vertical alignment
    """
    labels = []
    inputs = []
    for elem in elements:
        text = elem.get("text", "").strip()
        if text.endswith(":") or text.endswith("：") or text.endswith(":"):
            labels.append(elem)
            elem["role"] = "label"
        elif elem.get("type") in ("edit", "combobox", "listbox", "memo", "textbox", "dropdown"):
            inputs.append(elem)

    for label in labels:
        lr = label["rect"]
        cy = lr["y"] + lr["h"] / 2
        right = lr["x"] + lr["w"]

        best = None
        best_dist = float("inf")
        for inp in inputs:
            ir = inp["rect"]
            in_cy = ir["y"] + ir["h"] / 2
            if ir["x"] < right - 5:
                continue
            y_dist = abs(cy - in_cy)
            if y_dist > max(lr["h"], ir["h"]) * 2:
                continue
            dist = (ir["x"] - right) + y_dist * 2
            if dist < best_dist:
                best_dist = dist
                best = inp

        if best:
            best["paired_label"] = text.rstrip(":： ").strip()
            best["paired_label_rect"] = label["rect"]


def _get_detector():
    """Automatically select detection backend: custom-trained model → general YOLO → OpenCV (fallback).
    
    Returns:
        (detector, backend_name) 
    """
    base = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    
    # 1. Prefer custom-trained Delphi model
    custom_path = os.path.join(base, "data", "yolo_models", "daofy_train.onnx")
    if os.path.isfile(custom_path):
        try:
            from src.detection.yolo_onnx import YOLOONNXDetector
            class_names = {
                0: "TButton", 1: "TEdit", 2: "TLabel", 3: "TComboBox",
                4: "TCheckBox", 5: "TRadioButton", 6: "TListBox", 7: "TPanel",
                8: "TGroupBox", 9: "TPageControl", 10: "TTabSheet", 11: "TStringGrid",
                12: "TMemo", 13: "TListView", 14: "TTreeView", 15: "TProgressBar",
                16: "TTrackBar", 17: "TScrollBar", 18: "TScrollBox", 19: "TStatusBar",
            }
            return YOLOONNXDetector(custom_path, conf_thresh=0.3, class_names=class_names), "yolo+custom"
        except Exception as e:
            logger.warning(f"Failed to load custom model, trying general model: {e}")

    # 2. Fall back to general Windows UI model
    yolo_path = os.path.join(base, "data", "yolo_models", "windows-ui-locator.onnx")
    if os.path.isfile(yolo_path):
        try:
            from src.detection.yolo_onnx import YOLOONNXDetector
            class_names = {
                0: "button", 1: "textbox", 2: "checkbox",
                3: "dropdown", 4: "icon", 5: "tab", 6: "menu_item",
            }
            return YOLOONNXDetector(yolo_path, conf_thresh=0.3, class_names=class_names), "yolo"
        except Exception as e:
            logger.warning(f"Failed to load general YOLO, falling back to OpenCV: {e}")

    from src.detection.opencv_detector import OpenCVDetector
    return OpenCVDetector(), "opencv"


def _analyze_screenshot(image_path: str) -> dict:
    """Unified screenshot analysis: chains OCR + YOLO/OpenCV detection + layout + color.
    
    Args:
        image_path: screenshot path
        
    Returns:
        {
            elements: [{type, class_hint, text, rect, state, paired_label?}],
            layout: {tree layout},
            summary: "N elements in total: ...",
            ...
        }
    """
    import cv2

    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Cannot read image: {image_path}")

    h, w = img.shape[:2]

    # 1. OCR text recognition
    svc = get_ocr_service()
    ocr_results = svc.recognize(image_path)

    # 2. UI element detection (YOLO → OpenCV fallback)
    from src.detection.layout_parser import LayoutParser

    detector, backend = _get_detector()
    detections = detector.detect(image_path)

    # 3. Merge OCR → detection results
    elements = []
    for det in detections:
        det_box = [det.x, det.y, det.x + det.w, det.y + det.h]
        matched = [(ocr["text"], _bbox_iou(det_box, ocr["box"]))
                   for ocr in ocr_results if _bbox_iou(det_box, ocr["box"]) > 0.1]
        text = max(matched, key=lambda x: x[1])[0] if matched else ""

        state = _infer_element_state(img, det.x, det.y, det.w, det.h)

        elements.append({
            "type": det.class_name.removeprefix("T").lower(),
            "class_hint": det.class_name,
            "text": text,
            "rect": {"x": det.x, "y": det.y, "w": det.w, "h": det.h},
            "confidence": det.confidence,
            "state": state,
        })

    # 4. Label-Input pairing
    _pair_labels_with_inputs(elements)

    # 5. Layout tree
    parser = LayoutParser()
    layout_roots = parser.build_hierarchy(detections)
    layout_json = parser.to_json(layout_roots, image_path) if layout_roots else {}

    # 6. Summary
    type_counts: dict[str, int] = {}
    enabled = disabled = 0
    for el in elements:
        t = el["type"]
        type_counts[t] = type_counts.get(t, 0) + 1
        if el["state"] == "disabled":
            disabled += 1
        else:
            enabled += 1

    parts = [f"{c} {t}" for t, c in sorted(type_counts.items(), key=lambda x: x[1], reverse=True)]

    return {
        "status": "ok",
        "action": "analyze",
        "backend": backend,
        "image": os.path.basename(image_path),
        "dimensions": {"width": w, "height": h},
        "element_count": len(elements),
        "elements": elements,
        "layout": layout_json,
        "state_summary": f"{enabled} enabled / {disabled} disabled",
        "summary": f"{len(elements)} elements in total: {', '.join(parts)}",
    }


# ═══════════════════════════════════════════════════════════════
# MCP Tool Handler
# ═══════════════════════════════════════════════════════════════


def handle_ocr(arguments: dict) -> dict:
    """Handle OCR tool calls.

    Args:
        arguments: tool parameters
            action: "recognize"|"detect"|"status"|"diff"|"color"|"match"|"analyze"
            image_path: image path
            baseline/current: the two images for diff
            template_path: template image for match
            region: analysis region for color [x,y,w,h]
            threshold: diff threshold (default 10) / match threshold (default 0.8)
            output_dir: diff image output directory

    Returns:
        dict: processing result
    """
    action = arguments.get("action", "recognize")
    image_path = arguments.get("image_path", "")

    try:
        # === Visual analysis actions (do not depend on PP-OCR model) ===

        if action == "diff":
            baseline = arguments.get("baseline", "")
            current = arguments.get("current", "")
            if not baseline or not current:
                return {"status": "failed",
                        "error": "diff requires baseline and current parameters"}
            threshold = int(arguments.get("threshold", 10))
            output_dir = arguments.get("output_dir", "")
            result = _image_diff(baseline, current, threshold, output_dir)
            result.update({"status": "ok", "action": "diff"})
            return result

        if action == "color":
            if not image_path or not os.path.isfile(image_path):
                return {"status": "failed",
                        "error": "color requires a valid image_path"}
            region = arguments.get("region")
            threshold = arguments.get("threshold")
            if threshold is not None:
                threshold = float(threshold)
            result = _region_color(image_path, region, threshold)
            result.update({"status": "ok", "action": "color"})
            return result

        if action == "match":
            template_path = arguments.get("template_path", "")
            if not image_path or not template_path:
                return {"status": "failed",
                        "error": "match requires image_path and template_path"}
            threshold = float(arguments.get("threshold", 0.8))
            result = _template_match(image_path, template_path, threshold)
            result.update({"status": "ok", "action": "match"})
            return result

        # === Original OCR actions (depend on PP-OCR model) ===

        svc = get_ocr_service()

        if action == "status":
            return svc.status()

        if not image_path:
            return {"status": "failed", "error": "Missing required parameter: image_path"}

        if not os.path.isfile(image_path):
            return {"status": "failed", "error": f"File does not exist: {image_path}"}

        if action == "recognize":
            results = svc.recognize(image_path)
            return {"status": "ok", "action": "recognize",
                    "count": len(results), "results": results}

        elif action == "detect":
            results = svc.detect(image_path)
            return {"status": "ok", "action": "detect",
                    "count": len(results), "results": results}

        elif action == "analyze":
            return _analyze_screenshot(image_path)

        else:
            return {"status": "failed",
                    "error": "Unknown action, supported: recognize/detect/status/diff/color/match/analyze"}

    except FileNotFoundError as e:
        return {"status": "failed", "error": str(e)}
    except ImportError as e:
        return {"status": "failed",
                "error": f"Missing dependency: {e}. Please install: pip install daofy-for-delphi[ocr]"}
    except Exception as e:
        logger.error(f"OCR processing failed: {e}", exc_info=True)
        return {"status": "failed", "error": f"OCR processing failed: {e}"}

