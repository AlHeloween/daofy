"""
layout_parser — hierarchy inference

Converts a flat Detection list into a hierarchical layout tree.
Infers layout structure through spatial containment, alignment clustering, and spacing analysis.

Processing flow:
  1. Spatial containment analysis → container-child parent-child relationships
  2. Alignment cluster analysis → HStack/VStack/Grid layout types
  3. Form pairing → Label-Input association
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import cv2

from .opencv_detector import Detection

logger = logging.getLogger(__name__)

# Set of container type class_ids
_CONTAINER_IDS = {9}  # TPanel


@dataclass
class LayoutNode:
    """Layout tree node."""
    detection: Detection
    children: List["LayoutNode"] = field(default_factory=list)
    layout_type: str = "single"  # single / hstack / vstack / grid / zstack
    role: str = ""               # container / form-row / sidebar / ...

    @property
    def area(self) -> int:
        return self.detection.area


class LayoutParser:
    """Layout structure inferrer."""

    def __init__(self, container_tolerance: float = 0.9):
        """
        Args:
            container_tolerance: IoU threshold for container containment checks.
                An element is considered "inside the container" when:
                the IoU between the container and the element >= container_tolerance.
        """
        self.tolerance = container_tolerance

    def build_hierarchy(self, detections: List[Detection]) -> List[LayoutNode]:
        """Build a hierarchical layout tree from a flat Detection list.

        Args:
            detections: List of detected elements (already sorted by area descending).

        Returns:
            List of layout tree root nodes.
        """
        if not detections:
            return []

        # Ensure sorting by area descending (process containers first)
        sorted_dets = sorted(detections, key=lambda d: d.area, reverse=True)
        roots: List[LayoutNode] = []
        assigned: set[int] = set()  # Indices of elements already assigned a parent container

        # First pass: build parent-child relationships, containers first
        nodes = [LayoutNode(detection=d) for d in sorted_dets]

        for i, container_node in enumerate(nodes):
            if i in assigned:
                continue
            if container_node.detection.class_id not in _CONTAINER_IDS:
                continue

            for j, child_node in enumerate(nodes):
                if j in assigned or i == j:
                    continue
                if self._contains(container_node.detection, child_node.detection):
                    container_node.children.append(child_node)
                    assigned.add(j)

        # Second pass: elements not contained by any container become root nodes
        for i, node in enumerate(nodes):
            if i not in assigned:
                roots.append(node)

        # Third pass: infer the layout type of each node
        for root in roots:
            self._infer_layout_type(root)

        return roots

    def _contains(self, container: Detection, child: Detection) -> bool:
        """Determine whether child is inside container (spatial containment)."""
        # child's bbox must be entirely inside container
        child_in_container = (
            child.x >= container.x
            and child.y >= container.y
            and child.x + child.w <= container.x + container.w
            and child.y + child.h <= container.y + container.h
        )
        if not child_in_container:
            return False

        # Child area must not exceed 95% of the container's (otherwise it may be a sibling)
        return child.area < container.area * 0.95

    def _infer_layout_type(self, node: LayoutNode) -> str:
        """Recursively infer the node's layout type."""
        for child in node.children:
            self._infer_layout_type(child)

        if len(node.children) < 2:
            node.layout_type = "single"
            return node.layout_type

        elements = [c.detection for c in node.children]
        layout = self._detect_layout(elements)
        node.layout_type = layout
        return layout

    @staticmethod
    def _detect_layout(elements: List[Detection]) -> str:
        """Infer the layout arrangement of a set of child elements."""
        if len(elements) < 2:
            return "single"

        centers_x = [e.cx for e in elements]
        centers_y = [e.cy for e in elements]
        y_spread = max(centers_y) - min(centers_y)
        x_spread = max(centers_x) - min(centers_x)
        avg_h = sum(e.h for e in elements) / len(elements)
        avg_w = sum(e.w for e in elements) / len(elements)

        # HStack: Y centers are close, distributed horizontally
        if y_spread < avg_h * 0.6 and x_spread > avg_w * 0.5:
            return "hstack"

        # VStack: X centers are close, distributed vertically
        if x_spread < avg_w * 0.6 and y_spread > avg_h * 0.5:
            return "vstack"

        # Grid: check consistency of row/column spacing
        if LayoutParser._is_grid(elements):
            return "grid"

        return "zstack"

    @staticmethod
    def _is_grid(elements: List[Detection]) -> bool:
        """Check whether elements form a grid layout."""
        if len(elements) < 4:
            return False

        # Group by top coordinate (rows)
        tops = sorted(set(e.y for e in elements))
        rows = []
        for t in tops:
            row = [e for e in elements if abs(e.y - t) < 8]
            if len(row) >= 2:
                rows.append(row)

        # Group by left coordinate (columns)
        lefts = sorted(set(e.x for e in elements))
        cols = []
        for l in lefts:
            col = [e for e in elements if abs(e.x - l) < 8]
            if len(col) >= 2:
                cols.append(col)

        # At least 2 rows and at least 2 columns
        return len(rows) >= 2 and len(cols) >= 2

    # Form pairing (Label-Input) recognition — to be added in Phase 3

    def to_json(self, roots: List[LayoutNode], image_path: str) -> dict:
        """Serialize the layout tree into structured JSON (for LLM reference)."""
        img = cv2.imread(image_path)
        h, w = img.shape[:2] if img is not None else (0, 0)

        def node_to_dict(node: LayoutNode) -> dict:
            d = {
                "type": node.detection.class_name.lower().lstrip("t"),
                "class_hint": node.detection.class_name,
                "rect": {
                    "x": node.detection.x,
                    "y": node.detection.y,
                    "w": node.detection.w,
                    "h": node.detection.h,
                },
                "layout": node.layout_type,
                "confidence": node.detection.confidence,
            }
            if node.detection.text:
                d["text"] = node.detection.text
            if node.children:
                d["children"] = [node_to_dict(c) for c in node.children]
            return d

        return {
            "schema_version": "1.0",
            "canvas": {"width": w, "height": h},
            "children": [node_to_dict(r) for r in roots],
        }

