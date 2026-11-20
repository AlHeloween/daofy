"""
MessagePack format adapter — reads and writes .msgpack files ↔ StructuredNode.

Requires: pip install msgpack
"""

from __future__ import annotations

import json
from typing import Any, Optional

from .schema import StructuredNode


def parse(data: bytes) -> StructuredNode:
    """Parse MessagePack bytes into a StructuredNode."""
    import msgpack
    decoded = msgpack.unpackb(data, raw=False)
    return StructuredNode.from_json_compatible(decoded, key="")


def serialize(node: StructuredNode) -> bytes:
    """Serialize a StructuredNode into MessagePack bytes."""
    import msgpack
    data = node.to_json_compatible()
    return msgpack.packb(data, default=str)


def can_parse(data: bytes) -> bool:
    """Check whether the data is valid MessagePack."""
    if not isinstance(data, bytes) or len(data) < 2:
        return False
    try:
        import msgpack
        msgpack.unpackb(data, raw=False)
        return True
    except (ImportError, msgpack.UnpackException, Exception):
        return False


def parse_text(text: str) -> StructuredNode:
    """Parse from Base64-encoded MessagePack text."""
    import base64
    try:
        data = base64.b64decode(text)
    except Exception:
        # Try plain hex instead
        data = bytes.fromhex(text.strip())
    return parse(data)


def serialize_text(node: StructuredNode) -> str:
    """Serialize into Base64-encoded text."""
    import base64
    data = serialize(node)
    return base64.b64encode(data).decode("ascii")
