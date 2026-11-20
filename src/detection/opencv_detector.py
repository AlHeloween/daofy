"""
opencv_detector — OpenCV traditional CV UI element detection

Zero-extra-dependency baseline solution, usable for rapid prototype validation.
Uses OpenCV morphological operations to detect UI element boundaries and classify heuristically.

Dependencies: opencv-python-headless, numpy (included in the project's optional OCR dependencies)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class Detection:
    """A single detected UI element."""

    class_id: int          # YOLO-compatible class ID
    class_name: str        # Human-readable class name
    confidence: float      # Confidence (0-1)
    x: int                 # left
    y: int                 # top
    w: int                 # width
    h: int                 # height
    text: str = ""         # Text extracted by OCR (initially empty, filled later)

    @property
    def area(self) -> int:
        return self.w * self.h

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    def to_dict(self) -> dict:
        return {
            "class_id": self.class_id,
            "class_name": self.class_name,
            "confidence": self.confidence,
            "x": self.x, "y": self.y,
            "w": self.w, "h": self.h,
            "text": self.text,
        }


# Heuristic classification rules: determine element type by aspect ratio and area
_CLASS_RULES = [
    # (min_w/h_ratio, max_w/h_ratio, min_area, max_area, class_id, class_name)
    # Button: aspect ratio between 1.5 and 6, moderate area
    (1.5, 6.0,  400,  50000,  1, "TButton"),
    # Edit: aspect ratio > 3, moderate area
    (3.0, 20.0, 500,  80000,  2, "TEdit"),
    # Label: relatively small aspect ratio, small area
    (0.5, 6.0,  50,   30000,  3, "TLabel"),
    # Combo box: aspect ratio > 3, with arrow feature on the right
    (3.0, 15.0, 600,  60000,  4, "TComboBox"),
    # Checkbox: nearly square
    (0.8, 1.5,  80,   2500,   5, "TCheckBox"),
    # Radio button: nearly square
    (0.8, 1.5,  80,   2500,   6, "TRadioButton"),
    # List: very large vertical rectangle
    (0.3, 4.0,  5000, 500000, 7, "TListBox"),
    # Panel/container: large area
    (0.3, 5.0,  8000, 999999, 9, "TPanel"),
]


class OpenCVDetector:
    """UI element detector based on traditional OpenCV CV.

    Uses morphological operations + contour analysis to detect control boundaries,
    then classifies heuristically by aspect ratio/area.
    """

    def __init__(self, min_element_area: int = 50):
        """
        Args:
            min_element_area: Minimum element area; contours smaller than this are ignored.
        """
        self.min_area = min_element_area

    def detect(self, image_path: str) -> List[Detection]:
        """Detect UI elements in a screenshot.

        Args:
            image_path: Path to the screenshot file.

        Returns:
            List of detected elements, sorted by area descending.
        """
        img = cv2.imread(image_path)
        if img is None:
            raise FileNotFoundError(f"Unable to read image: {image_path}")

        h, w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # 1. Adaptive threshold binarization
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 21, 5,
        )

        # 2. Morphological closing: merge text regions into blocks
        kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 1))
        kernel_v = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 3))
        closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel_h, iterations=2)
        closed = cv2.morphologyEx(closed, cv2.MORPH_CLOSE, kernel_v, iterations=1)

        # 3. Dilation: expand edges and connect adjacent regions
        kernel_dilate = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        dilated = cv2.dilate(closed, kernel_dilate, iterations=2)

        # 4. Contour extraction
        contours, _ = cv2.findContours(
            dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE,
        )

        detections: List[Detection] = []

        for contour in contours:
            x, y, cw, ch = cv2.boundingRect(contour)
            if cw < 8 or ch < 8:  # Skip regions that are too small
                continue
            area = cw * ch
            if area < self.min_area:
                continue

            # Take the interior region from the original grayscale image to assist classification
            roi = gray[y : y + ch, x : x + cw]
            mean_brightness = float(np.mean(roi))
            std_brightness = float(np.std(roi))

            class_id, class_name = self._classify(cw, ch, area, mean_brightness, std_brightness)
            if class_id < 0:
                continue

            detections.append(Detection(
                class_id=class_id,
                class_name=class_name,
                confidence=0.5,  # Traditional CV uses a uniform 0.5
                x=x, y=y, w=cw, h=ch,
            ))

        # 5. Sort by area descending (containers first)
        detections.sort(key=lambda d: d.area, reverse=True)

        # 6. Merge highly overlapping detection boxes (simplified NMS)
        detections = self._merge_overlapping(detections)

        logger.info(
            "OpenCV detection complete: %d elements (original image %dx%d)",
            len(detections), w, h,
        )
        return detections

    def _classify(
        self, cw: int, ch: int, area: int,
        mean_brightness: float, std_brightness: float,
    ) -> tuple[int, str]:
        """Heuristic classification: determine element type by aspect ratio, area, and brightness features.

        Returns:
            (class_id, class_name), or (-1, "") if unknown.
        """
        ratio = cw / max(ch, 1)

        # Nearly square tiny element → checkbox or radio button
        if 0.8 <= ratio <= 1.5 and 80 <= area <= 2500:
            # Higher brightness and larger standard deviation → checkbox (check boxes usually have a brighter background)
            if mean_brightness > 150 and std_brightness > 40:
                return (5, "TCheckBox")
            return (6, "TRadioButton")

        # Large flat region → panel
        if area > 8000 and cw > 100 and ch > 50:
            return (9, "TPanel")

        # Match against the rule table
        for min_r, max_r, min_a, max_a, cid, cname in _CLASS_RULES:
            if min_r <= ratio <= max_r and min_a <= area <= max_a:
                return (cid, cname)

        # Unable to classify
        return (-1, "")

    def _merge_overlapping(self, detections: List[Detection],
                           iou_thresh: float = 0.6) -> List[Detection]:
        """Merge highly overlapping detection boxes (keep the larger-area one)."""
        if not detections:
            return []

        keep = [True] * len(detections)
        for i in range(len(detections)):
            if not keep[i]:
                continue
            for j in range(i + 1, len(detections)):
                if not keep[j]:
                    continue
                iou = self._iou(detections[i], detections[j])
                if iou > iou_thresh:
                    # Keep the box with the larger area
                    if detections[i].area >= detections[j].area:
                        keep[j] = False
                    else:
                        keep[i] = False
                        break

        return [d for i, d in enumerate(detections) if keep[i]]

    @staticmethod
    def _iou(a: Detection, b: Detection) -> float:
        """Compute the IoU of two detection boxes."""
        x1 = max(a.x, b.x)
        y1 = max(a.y, b.y)
        x2 = min(a.x + a.w, b.x + b.w)
        y2 = min(a.y + a.h, b.y + b.h)
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        union = a.area + b.area - inter
        return inter / max(union, 1)

