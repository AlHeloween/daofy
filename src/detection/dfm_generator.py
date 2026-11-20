"""
dfm_generator — layout detection results → Delphi DFM text

Converts Detection and LayoutNode trees into a DfmComponent tree,
then outputs DFM text via dfm_parser.serialize_component.

Dependencies:
  - src.tools.dfm_parser (DfmComponent, DfmProperty, serialize_component)
  - src.detection.opencv_detector (Detection)
  - src.detection.layout_parser (LayoutNode)

Usage:
    from src.detection.dfm_generator import DFMGenerator

    gen = DFMGenerator()
    dfm_text = gen.generate(layout_roots, image_path)
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional, Set

from src.tools.dfm_parser import DfmComponent, DfmProperty, serialize_component
from .opencv_detector import Detection
from .layout_parser import LayoutNode

logger = logging.getLogger(__name__)

# class_id → Delphi property mapping
# key: class_id, value: (class_name, caption_prop, unit_hint)
_CLASS_MAP: dict[int, tuple[str, str, str]] = {
    1:  ("TButton",        "Caption",  "Vcl.StdCtrls"),
    2:  ("TEdit",          "Text",     "Vcl.StdCtrls"),
    3:  ("TLabel",         "Caption",  "Vcl.StdCtrls"),
    4:  ("TComboBox",      "Text",     "Vcl.StdCtrls"),
    5:  ("TCheckBox",      "Caption",  "Vcl.StdCtrls"),
    6:  ("TRadioButton",   "Caption",  "Vcl.StdCtrls"),
    7:  ("TListBox",       "Text",     "Vcl.StdCtrls"),
    8:  ("TListView",      "Text",     "Vcl.ComCtrls"),
    9:  ("TPanel",         "Caption",  "Vcl.ExtCtrls"),
    10: ("TScrollBox",     "",         "Vcl.Forms"),
    11: ("TGroupBox",      "Caption",  "Vcl.StdCtrls"),
    12: ("TPageControl",   "",         "Vcl.ComCtrls"),
    13: ("TTabSheet",      "Caption",  "Vcl.ComCtrls"),
    14: ("TMemo",          "Text",     "Vcl.StdCtrls"),
    15: ("TStringGrid",    "",         "Vcl.Grids"),
    16: ("TcxGrid",        "",         "cxGrid"),
    17: ("TcxButton",      "Caption",  "cxButtons"),
    18: ("TcxTextEdit",    "Text",     "cxEdit"),
    19: ("TcxComboBox",    "Text",     "cxEdit"),
    20: ("TcxCheckBox",    "Caption",  "cxEdit"),
}


def _gen_name(cls_name: str, seen_names: Set[str]) -> str:
    """Generate a unique instance name for the given class name.
    
    TButton → Button1, Button2, ...
    TPanel  → Panel1, Panel2, ...
    """
    prefix = cls_name
    for known in ("T", "Tcx"):
        if cls_name.startswith(known) and len(cls_name) > len(known):
            prefix = cls_name[len(known):]
            break
    if not prefix:
        prefix = cls_name

    idx = 1
    while f"{prefix}{idx}" in seen_names:
        idx += 1
    name = f"{prefix}{idx}"
    seen_names.add(name)
    return name


class DFMGenerator:
    """Convert a layout detection tree into Delphi DFM text."""

    def __init__(self, default_form_class: str = "TForm",
                 default_form_name: str = "Form1"):
        """
        Args:
            default_form_class: Root class name for the generated DFM, default TForm.
            default_form_name: Root instance name for the generated DFM, default Form1.
        """
        self.default_form_class = default_form_class
        self.default_form_name = default_form_name

    def generate(self, roots: List[LayoutNode],
                 image_path: str = "") -> str:
        """Generate DFM text.

        Args:
            roots: List of layout tree root nodes (output of LayoutParser.build_hierarchy).
            image_path: Original screenshot path (used only for logs and metadata).

        Returns:
            DFM-format text string.
        """
        seen_names: Set[str] = set()
        seen_names.add(self.default_form_name)

        form = DfmComponent(
            name=self.default_form_name,
            class_name=self.default_form_class,
            prefix="object",
        )

        # Infer form properties from the screenshot filename
        base = os.path.splitext(os.path.basename(image_path))[0] if image_path else ""
        if base:
            form.properties.append(DfmProperty(
                name="Caption", raw_value=f"'{base}'",
            ))

        form.properties.extend([
            DfmProperty(name="Left", raw_value="0"),
            DfmProperty(name="Top", raw_value="0"),
            DfmProperty(name="Width", raw_value=self._infer_canvas_width(roots)),
            DfmProperty(name="Height", raw_value=self._infer_canvas_height(roots)),
        ])

        # Convert the layout tree to DfmComponent and add it to the form
        for root in roots:
            comp = self._node_to_dfm(root, seen_names)
            if comp is not None:
                form.children.append(comp)

        result = serialize_component(form)
        logger.info("DFM generation complete: %d lines, %d components",
                     result.count("\n") + 1,
                     len(form.children))
        return result

    def _node_to_dfm(self, node: LayoutNode,
                     seen_names: Set[str]) -> Optional[DfmComponent]:
        """Convert a LayoutNode to a DfmComponent."""
        det = node.detection

        class_info = _CLASS_MAP.get(det.class_id)
        if class_info is None:
            logger.debug("Skipping unmapped class_id=%d (%s)",
                         det.class_id, det.class_name)
            return None

        class_name, caption_prop, _ = class_info
        comp_name = _gen_name(class_name, seen_names)

        comp = DfmComponent(
            name=comp_name,
            class_name=class_name,
            prefix="object",
        )

        # Position properties
        comp.properties.extend([
            DfmProperty(name="Left", raw_value=str(det.x)),
            DfmProperty(name="Top", raw_value=str(det.y)),
            DfmProperty(name="Width", raw_value=str(det.w)),
            DfmProperty(name="Height", raw_value=str(det.h)),
        ])

        # Text content
        text = det.text or ""
        if caption_prop and text:
            comp.properties.append(DfmProperty(
                name=caption_prop, raw_value=f"'{text}'",
            ))

        # Visibility state (do not emit Visible for invisible elements because the default is True)
        # Omitted here because Detection has no marker for confidence < threshold.

        # Recursively process child nodes
        for child in node.children:
            child_comp = self._node_to_dfm(child, seen_names)
            if child_comp is not None:
                comp.children.append(child_comp)

        return comp

    @staticmethod
    def _infer_canvas_width(roots: List[LayoutNode]) -> str:
        """Infer canvas width from the layout tree."""
        if not roots:
            return "640"
        max_right = 0
        for node in _walk_all(roots):
            r = node.detection.x + node.detection.w
            if r > max_right:
                max_right = r
        return str(max(int(max_right * 1.1), 640))

    @staticmethod
    def _infer_canvas_height(roots: List[LayoutNode]) -> str:
        """Infer canvas height from the layout tree."""
        if not roots:
            return "480"
        max_bottom = 0
        for node in _walk_all(roots):
            b = node.detection.y + node.detection.h
            if b > max_bottom:
                max_bottom = b
        return str(max(int(max_bottom * 1.1), 480))


def _walk_all(roots):
    """Breadth-first traverse all nodes."""
    stack = list(roots)
    while stack:
        node = stack.pop(0)
        yield node
        stack.extend(node.children)
