"""
synthetic_data_generator — Automatic YOLO training data generation

Two modes:
  1. Automatic collection from a Delphi application (capture + dumpstate) — requires an exe linked with DaofyAutomation
  2. Programmatic synthesis (OpenCV draws simulated UI) — no Delphi environment required, used for baseline validation

Output format:
  images/              ← Screenshots (PNG)
  labels/              ← YOLO-format labels (TXT)
  dataset.yaml         ← Ultralytics training configuration file

YOLO label format (one element per line):
  <class_id> <x_center> <y_center> <width> <height>
  Coordinates normalized to [0, 1] (relative to image width and height)

Usage (Delphi mode):
  python -c "
  from src.detection.synthetic_data_generator import DelphiDataCollector
  collector = DelphiDataCollector(
      app_path='C:/App/MyApp.exe',
      output_dir='./yolo_dataset',
      forms=['TMainForm', 'TLoginForm', 'TSettingsForm'],
  )
  collector.collect_all()
  "

Usage (synthetic mode):
  python -c "
  from src.detection.synthetic_data_generator import SyntheticDataGenerator
  gen = SyntheticDataGenerator(output_dir='./yolo_dataset')
  gen.generate(num_samples=100)
  "
"""

from __future__ import annotations

import json
import logging
import os
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Import class_id mapping from dfm_generator (single source of truth)
from .dfm_generator import _CLASS_MAP as _DFM_CLASS_MAP

# Delphi control type → YOLO class_id mapping (automatically inverted from dfm_generator)
_DELPHI_CLASS_MAP: dict[str, int] = {
    cls_name: cid - 1 for cid, (cls_name, _, _) in _DFM_CLASS_MAP.items()
}

# Reverse mapping
_CLASS_ID_TO_NAME = {v: k for k, v in _DELPHI_CLASS_MAP.items()}

# Visual parameters for each control type in synthetic mode
_SYNTHETIC_CONTROLS: dict[str, dict] = {
    "TButton": {
        "min_size": (60, 22), "max_size": (160, 36),
        "color_range": ((180, 180, 180), (220, 220, 220)),
        "border": True,
    },
    "TEdit": {
        "min_size": (100, 20), "max_size": (300, 28),
        "color_range": ((250, 250, 250), (255, 255, 255)),
        "border": True,
    },
    "TLabel": {
        "min_size": (30, 14), "max_size": (200, 20),
        "color_range": ((235, 235, 235), (245, 245, 245)),
        "border": False,
    },
    "TCheckBox": {
        "min_size": (15, 15), "max_size": (22, 22),
        "color_range": ((230, 230, 230), (255, 255, 255)),
        "border": True,
    },
    "TPanel": {
        "min_size": (200, 100), "max_size": (600, 400),
        "color_range": ((230, 230, 230), (245, 245, 245)),
        "border": True,
    },
    "TGroupBox": {
        "min_size": (200, 80), "max_size": (500, 300),
        "color_range": ((235, 235, 235), (245, 245, 245)),
        "border": True,
    },
}

# Control generation weights (to control distribution)
_SYNTHETIC_WEIGHTS: dict[str, float] = {
    "TButton": 0.20,
    "TEdit": 0.18,
    "TLabel": 0.20,
    "TCheckBox": 0.08,
    "TPanel": 0.04,
    "TGroupBox": 0.03,
}


# ============================================================
# Delphi mode — automatic collection from a running Delphi application
# ============================================================

class DelphiDataCollector:
    """Collect training data from a Delphi application via automate_delphi.

    Prerequisites:
      - The Delphi exe is linked with the DaofyAutomation unit
      - The Python environment can run automate_delphi (gui mode)
    """

    def __init__(
        self,
        app_path: str,
        output_dir: str = "./yolo_dataset",
        forms: Optional[List[str]] = None,
    ):
        """
        Args:
            app_path: Path to the Delphi exe.
            output_dir: Output directory.
            forms: List of form class names to collect; None means collect all available forms.
        """
        self.app_path = app_path
        self.output_dir = Path(output_dir)
        self.forms = forms
        self.image_dir = self.output_dir / "images"
        self.label_dir = self.output_dir / "labels"

    def collect_all(self) -> Dict[str, int]:
        """Execute the complete collection process.

        Returns:
            {"total_images": N, "total_labels": M, ...}
        """
        try:
            from src.services.automation_service import execute_automation
        except ImportError:
            raise ImportError(
                "The automate_delphi tool is unavailable. Please ensure it is run in the Daofy MCP Server environment."
            )

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.image_dir.mkdir(exist_ok=True)
        self.label_dir.mkdir(exist_ok=True)

        forms_to_capture = self.forms or ["auto"]
        collected = {"total_images": 0, "total_labels": 0}

        for form_name in forms_to_capture:
            logger.info("Collecting form: %s", form_name)

            # 1. Switch to the target form
            if form_name != "auto":
                nav_script = [{"cmd": "goto", "target": form_name}]
                execute_automation(
                    action="gui",
                    app_path=self.app_path,
                    script=nav_script,
                )

            # 2. Synchronized capture + dumpstate collection
            script = [
                {"cmd": "capture", "reqId": "img"},
                {"cmd": "dumpstate", "reqId": "labels"},
            ]
            result = execute_automation(
                action="gui",
                app_path=self.app_path,
                script=script,
                snapshots_dir=str(self.image_dir),
            )

            # 3. Parse result
            self._process_result(result, form_name, collected)

        # 4. Generate dataset.yaml
        self._write_dataset_yaml()

        logger.info(
            "Collection complete: %d images, %d annotations",
            collected["total_images"], collected["total_labels"],
        )
        return collected

    def _process_result(
        self, result: dict, form_name: str, collected: Dict[str, int],
    ) -> None:
        """Process the result of one capture + dumpstate collection."""
        steps = result.get("steps", [])
        capture_path = ""
        dumpstate_data = None

        for step in steps:
            if step.get("cmd") == "capture":
                capture_path = (step.get("response") or {}).get("path", "")
            elif step.get("cmd") == "dumpstate":
                dumpstate_data = step.get("response") or {}

        if not capture_path:
            logger.warning("Collection skipped: capture failed (%s)", form_name)
            return

        labels = self._dumpstate_to_yolo(dumpstate_data)
        if not labels:
            logger.warning("Collection skipped: dumpstate detected no controls (%s)", form_name)
            return

        # YOLO label file name matches the image name
        img_name = Path(capture_path).name
        label_name = Path(img_name).with_suffix(".txt")
        label_path = self.label_dir / label_name

        with open(label_path, "w", encoding="utf-8") as f:
            for line in labels:
                f.write(line + "\n")

        # Optional: copy the image to the unified image directory
        # Skip if capture has already saved it to image_dir
        if Path(capture_path).parent != self.image_dir:
            dest = self.image_dir / img_name
            if not dest.exists():
                import shutil
                shutil.copy2(capture_path, dest)

        collected["total_images"] += 1
        collected["total_labels"] += len(labels)

    def _dumpstate_to_yolo(self, data: dict) -> List[str]:
        """Convert dumpstate JSON to YOLO-format label lines.

        dumpstate returns:
          {
            "form": {"class": "TMainForm", "Left": 0, "Top": 0,
                     "Width": 800, "Height": 600},
            "controls": [
              {"name": "Button1", "class": "TButton",
               "Left": 10, "Top": 20, "Width": 100, "Height": 30},
              ...
            ]
          }
        """
        if not data:
            return []

        # Get form size (used for coordinate normalization)
        form = data.get("form", {})
        fw = form.get("Width", 640) or 640
        fh = form.get("Height", 480) or 480
        if fw <= 0 or fh <= 0:
            fw, fh = 640, 480

        controls = data.get("controls", [])
        if not controls:
            # It may also be in form.controls
            controls = form.get("controls", [])

        labels: List[str] = []
        for ctrl in controls:
            cls_name = ctrl.get("class", "")
            class_id = _DELPHI_CLASS_MAP.get(cls_name)
            if class_id is None:
                continue  # Skip unmapped control types

            left = ctrl.get("Left", 0)
            top = ctrl.get("Top", 0)
            w = ctrl.get("Width", 0)
            h = ctrl.get("Height", 0)

            if w <= 2 or h <= 2:
                continue  # Skip controls that are too small

            # YOLO format: <class_id> <x_center> <y_center> <width> <height>
            # Coordinates normalized to [0, 1]
            x_center = (left + w / 2) / fw
            y_center = (top + h / 2) / fh
            norm_w = w / fw
            norm_h = h / fh

            labels.append(f"{class_id} {x_center:.6f} {y_center:.6f} {norm_w:.6f} {norm_h:.6f}")

        return labels

    def _write_dataset_yaml(self) -> None:
        """Create the Ultralytics dataset.yaml file."""
        names = {v: k for k, v in _DELPHI_CLASS_MAP.items()}
        nc = len(names)

        yaml_path = self.output_dir / "dataset.yaml"
        with open(yaml_path, "w", encoding="utf-8") as f:
            f.write(f"# YOLO dataset configuration — auto-generated\n")
            f.write(f"path: {self.output_dir.resolve().as_posix()}\n")
            f.write(f"train: images\n")
            f.write(f"val: images\n\n")
            f.write(f"nc: {nc}\n")
            f.write(f"names:\n")
            for cid in sorted(names.keys()):
                f.write(f"  {cid}: {names[cid]}\n")

        logger.info("dataset.yaml generated: %s", yaml_path)


# ============================================================
# Synthetic mode — generate simulated UI screenshots with OpenCV (no Delphi environment required)
# ============================================================

class SyntheticDataGenerator:
    """Synthesize simulated Delphi UI screenshots + YOLO labels with OpenCV.

    Used for:
      - Training pipeline validation (test the training flow without a Delphi environment)
      - Baseline dataset for data augmentation
      - Fast iteration on model architecture
    """

    def __init__(
        self,
        output_dir: str = "./yolo_dataset",
        canvas_size: Tuple[int, int] = (640, 480),
        class_map: Optional[Dict[str, int]] = None,
    ):
        """
        Args:
            output_dir: Output directory.
            canvas_size: Synthetic canvas size (w, h).
            class_map: Control name → class_id mapping; defaults to _DELPHI_CLASS_MAP.
        """
        self.output_dir = Path(output_dir)
        self.image_dir = self.output_dir / "images"
        self.label_dir = self.output_dir / "labels"
        self.canvas_w, self.canvas_h = canvas_size
        self.class_map = class_map or _DELPHI_CLASS_MAP

    def generate(self, num_samples: int = 100) -> Dict[str, int]:
        """Generate a synthetic dataset.

        Args:
            num_samples: Number of screenshots to generate.

        Returns:
            {"total_images": N, "total_labels": M}
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.image_dir.mkdir(exist_ok=True)
        self.label_dir.mkdir(exist_ok=True)

        total_labels = 0
        control_names = list(self.class_map.keys())
        weights = [_SYNTHETIC_WEIGHTS.get(n, 0.05) for n in control_names]
        # Normalize weights
        total_w = sum(weights)
        weights = [w / total_w for w in weights]

        for i in range(num_samples):
            img = np.ones((self.canvas_h, self.canvas_w, 3), dtype=np.uint8) * 240

            # Randomly determine the number of controls to include in this image
            num_controls = random.randint(3, min(12, len(control_names)))

            # Choose control types (weighted random)
            chosen = random.choices(control_names, weights=weights, k=num_controls)

            labels: List[str] = []
            occupied: List[Tuple[int, int, int, int]] = []

            # Place containers first (Panel/GroupBox — larger areas take priority)
            containers = [n for n in chosen if n in ("TPanel", "TGroupBox")]
            others = [n for n in chosen if n not in ("TPanel", "TGroupBox")]

            # Place non-container controls
            for ctrl_name in others:
                rect = self._place_element(ctrl_name, occupied)
                if rect is None:
                    continue
                x, y, w, h = rect
                occupied.append((x - 5, y - 5, w + 10, h + 10))  # Add some margin to avoid overlap

                self._draw_element(img, ctrl_name, x, y, w, h)

                class_id = self.class_map.get(ctrl_name)
                if class_id is not None:
                    x_center = (x + w / 2) / self.canvas_w
                    y_center = (y + h / 2) / self.canvas_h
                    labels.append(
                        f"{class_id} {x_center:.6f} {y_center:.6f} "
                        f"{w / self.canvas_w:.6f} {h / self.canvas_h:.6f}"
                    )

            # Place containers (as background, draw them first and then draw child elements on top)
            # Simplified version: containers are just large frames
            for ctrl_name in containers:
                rect = self._place_element(ctrl_name, occupied)
                if rect is None:
                    continue
                x, y, w, h = rect
                self._draw_element(img, ctrl_name, x, y, w, h)
                occupied.append((x, y, w, h))

                class_id = self.class_map.get(ctrl_name)
                if class_id is not None:
                    x_center = (x + w / 2) / self.canvas_w
                    y_center = (y + h / 2) / self.canvas_h
                    labels.append(
                        f"{class_id} {x_center:.6f} {y_center:.6f} "
                        f"{w / self.canvas_w:.6f} {h / self.canvas_h:.6f}"
                    )

            # Save image
            img_name = f"synth_{i:05d}.png"
            cv2.imwrite(str(self.image_dir / img_name), img)

            # Save labels
            if labels:
                label_path = self.label_dir / f"synth_{i:05d}.txt"
                with open(label_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(labels) + "\n")
                total_labels += len(labels)

        # Generate dataset.yaml
        self._write_dataset_yaml()

        logger.info(
            "Synthetic data generation complete: %d images, %d annotations", num_samples, total_labels,
        )
        return {"total_images": num_samples, "total_labels": total_labels}

    def _place_element(
        self, ctrl_name: str,
        occupied: List[Tuple[int, int, int, int]],
        max_attempts: int = 50,
    ) -> Optional[Tuple[int, int, int, int]]:
        """Find a non-overlapping position on the canvas to place a control."""
        params = _SYNTHETIC_CONTROLS.get(ctrl_name, _SYNTHETIC_CONTROLS["TLabel"])

        for _ in range(max_attempts):
            w = random.randint(params["min_size"][0], params["max_size"][0])
            h = random.randint(params["min_size"][1], params["max_size"][1])

            x = random.randint(10, max(self.canvas_w - w - 10, 10))
            y = random.randint(10, max(self.canvas_h - h - 10, 10))

            # Check whether it overlaps with already placed controls
            new_rect = (x, y, w, h)
            if not self._overlaps(new_rect, occupied, min_gap=5):
                return new_rect

        return None

    @staticmethod
    def _overlaps(
        rect: Tuple[int, int, int, int],
        others: List[Tuple[int, int, int, int]],
        min_gap: int = 5,
    ) -> bool:
        """Check whether a rectangle overlaps existing rectangles (including minimum gap)."""
        rx, ry, rw, rh = rect
        for ox, oy, ow, oh in others:
            if (
                rx < ox + ow + min_gap
                and rx + rw + min_gap > ox
                and ry < oy + oh + min_gap
                and ry + rh + min_gap > oy
            ):
                return True
        return False

    def _draw_element(
        self, img: np.ndarray,
        ctrl_name: str,
        x: int, y: int, w: int, h: int,
    ) -> None:
        """Draw the appearance of a control on the canvas."""
        params = _SYNTHETIC_CONTROLS.get(ctrl_name, _SYNTHETIC_CONTROLS["TLabel"])
        low_bgr, high_bgr = params["color_range"]
        color = (
            random.randint(low_bgr[0], high_bgr[0]),  # B
            random.randint(low_bgr[1], high_bgr[1]),  # G
            random.randint(low_bgr[2], high_bgr[2]),  # R
        )

        # Fill
        cv2.rectangle(img, (x, y), (x + w, y + h), color, -1)

        # Border
        if params["border"]:
            cv2.rectangle(img, (x, y), (x + w, y + h), (100, 100, 100), 1)

        # Button-specific effect: light background + slightly darker gradient
        if ctrl_name == "TButton":
            for i in range(h // 2):
                alpha = i / (h // 2)
                darker = tuple(int(c * (1 - alpha * 0.15)) for c in color)
                cv2.line(img, (x, y + i), (x + w, y + i), darker, 1)

        # Edit-specific effect: white background + sunken border
        elif ctrl_name == "TEdit":
            cv2.rectangle(img, (x, y), (x + w, y + h), (255, 255, 255), -1)
            cv2.rectangle(img, (x, y), (x + w, y + h), (180, 180, 180), 1)

    def _write_dataset_yaml(self) -> None:
        """Create the Ultralytics dataset.yaml file."""
        names = {v: k for k, v in self.class_map.items()}
        nc = len(names)

        yaml_path = self.output_dir / "dataset.yaml"
        with open(yaml_path, "w", encoding="utf-8") as f:
            f.write("# YOLO dataset configuration — synthetic data\n")
            f.write(f"path: {self.output_dir.resolve().as_posix()}\n")
            f.write("train: images\n")
            f.write("val: images\n\n")
            f.write(f"nc: {nc}\n")
            f.write("names:\n")
            for cid in sorted(names.keys()):
                f.write(f"  {cid}: {names[cid]}\n")

        logger.info("dataset.yaml generated: %s", yaml_path)
