"""
JSON format adapter — reads and writes JSON files ↔ StructuredNode.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from .schema import StructuredNode


def parse(text: str) -> StructuredNode:
    """Parse JSON text into a StructuredNode."""
    data = json.loads(text)
    return StructuredNode.from_json_compatible(data, key="")


def serialize(node: StructuredNode, indent: int = 2) -> str:
    """Serialize a StructuredNode into JSON text."""
    data = node.to_json_compatible()
    return json.dumps(data, ensure_ascii=False, indent=indent)


def can_parse(text: str) -> bool:
    """Check whether the text is valid JSON."""
    text = text.strip()
    if not (text.startswith("{") or text.startswith("[")):
        return False
    try:
        json.loads(text)
        return True
    except (json.JSONDecodeError, ValueError):
        return False
