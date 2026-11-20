"""
Format detection and dispatch — detect a file's format automatically and call the matching adapter.
"""

from __future__ import annotations

import os
from typing import Any, Optional

from .schema import StructuredNode

# ── Format enumeration ───────────────────────────────────────────────

SUPPORTED_FORMATS = [
    "dfm",
    "lfm",
    "fmx",
    "xml",
    "json",
    "msgpack",
    "protobuf",
]

TEXT_FORMATS = {"dfm", "lfm", "fmx", "xml", "json"}
BINARY_FORMATS = {"msgpack", "protobuf"}

# ── Extension mapping ────────────────────────────────────────────────

EXTENSION_MAP: dict[str, str] = {
    ".dfm": "dfm",
    ".lfm": "lfm",
    ".fmx": "fmx",
    ".xml": "xml",
    ".xsd": "xml",
    ".svg": "xml",
    ".json": "json",
    ".msgpack": "msgpack",
    ".msgp": "msgpack",
    ".proto": "protobuf",
    ".pb": "protobuf",
}


def detect_format(
    file_path: str,
    content: Optional[bytes] = None,
    hint: Optional[str] = None,
) -> Optional[str]:
    """Detect the file format.

    Args:
        file_path: the file path.
        content: the file content (optional; when given, content sniffing runs).
        hint: force a specific format.

    Returns:
        The format name (dfm/lfm/fmx/xml/json/msgpack/protobuf), or None.
    """
    if hint and hint in SUPPORTED_FORMATS:
        return hint

    ext = os.path.splitext(file_path)[1].lower()
    fmt = EXTENSION_MAP.get(ext)
    if fmt:
        return fmt

    # With no extension, fall back to content sniffing
    if content:
        return sniff_format(content)

    return None


def sniff_format(content: bytes) -> Optional[str]:
    """Detect the format from the content's leading bytes."""
    text = content.decode("utf-8", errors="replace").strip()

    # JSON
    if text.startswith("{") or text.startswith("["):
        try:
            import json
            json.loads(text)
            return "json"
        except (json.JSONDecodeError, ValueError):
            pass

    # XML
    if text.startswith("<"):
        try:
            import xml.etree.ElementTree as ET
            ET.fromstring(text)
            return "xml"
        except ET.ParseError:
            pass

    # DFM/LFM
    if text.startswith("object ") or text.startswith("inherited "):
        return "dfm"  # dfm and lfm share one format; the extension tells them apart

    # MessagePack (binary prefix 0x8_, 0x9_, 0x_ and so on)
    if content[:1] in (b"\x80", b"\x90", b"\xa0", b"\xc0"):
        try:
            import msgpack
            msgpack.unpackb(content, raw=False)
            return "msgpack"
        except Exception:
            pass

    return None


# ── Format reading ───────────────────────────────────────────────────


def read_file(file_path: str, fmt: Optional[str] = None) -> tuple[StructuredNode, str]:
    """Read a file and parse it into a StructuredNode.

    Args:
        file_path: the file path.
        fmt: the format (None = auto-detect).

    Returns:
        (root_node, detected_format).
    """
    with open(file_path, "rb") as f:
        raw = f.read()

    fmt = detect_format(file_path, raw, fmt)
    if fmt is None:
        raise ValueError(f"Unable to detect the file format: {file_path}")

    if fmt in ("dfm", "lfm", "fmx"):
        text = raw.decode("utf-8", errors="replace")
        from .dfm_adapter import parse as dfm_parse
        return dfm_parse(text), fmt

    if fmt == "xml":
        text = raw.decode("utf-8", errors="replace")
        from .xml_adapter import parse as xml_parse
        return xml_parse(text), fmt

    if fmt == "json":
        text = raw.decode("utf-8", errors="replace")
        from .json_adapter import parse as json_parse
        return json_parse(text), fmt

    if fmt == "msgpack":
        from .msgpack_adapter import parse as msgpack_parse
        return msgpack_parse(raw), fmt

    if fmt == "protobuf":
        raise NotImplementedError(
            "A ProtoBuf file needs the message_name and proto_file parameters. "
            "Use structured_content(action='read', format='protobuf', "
            "proto_file='...', message_name='...')"
        )

    raise ValueError(f"Unsupported format: {fmt}")


def write_file(
    node: StructuredNode,
    file_path: str,
    fmt: Optional[str] = None,
) -> None:
    """Serialize a StructuredNode and write it to a file.

    Args:
        node: the StructuredNode.
        file_path: the output path.
        fmt: the format (None = inferred from the extension).
    """
    fmt = detect_format(file_path, hint=fmt)
    if fmt is None:
        raise ValueError(f"Unable to infer the format: {file_path}")

    if fmt in ("dfm", "lfm", "fmx"):
        from .dfm_adapter import serialize as dfm_ser
        text = dfm_ser(node)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(text)
        return

    if fmt == "xml":
        from .xml_adapter import serialize as xml_ser
        text = xml_ser(node)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(text)
        return

    if fmt == "json":
        from .json_adapter import serialize as json_ser
        text = json_ser(node)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(text)
        return

    if fmt == "msgpack":
        from .msgpack_adapter import serialize as msgpack_ser
        data = msgpack_ser(node)
        with open(file_path, "wb") as f:
            f.write(data)
        return

    if fmt == "protobuf":
        raise NotImplementedError(
            "Writing ProtoBuf needs the message_class parameter. "
            "Use structured_content(action='write', format='protobuf', ...)"
        )

    raise ValueError(f"Unsupported format: {fmt}")
