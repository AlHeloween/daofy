"""
ProtoBuf format adapter — reads and writes .proto / .pb files ↔ StructuredNode.

Supports two modes:
  1. Compile a .proto file on the fly → serialize/deserialize with the generated XXX_pb2 module
  2. Parse an existing .proto descriptor file directly into a Schema

Requires: pip install protobuf
"""

from __future__ import annotations

import os
import re
import tempfile
from typing import Any, Optional

from .schema import StructuredNode


# ═════════════════════════════════════════════════════════════════════
#  Part 1: parse a .proto file into descriptive JSON
# ═════════════════════════════════════════════════════════════════════

PROTO_MESSAGE_RE = re.compile(
    r"message\s+(\w+)\s*\{"
)
PROTO_FIELD_RE = re.compile(
    r"(repeated\s+|optional\s+|required\s+)?"
    r"(?P<type>[\w.]+)"
    r"\s+(?P<name>\w+)\s*=\s*(?P<tag>\d+)"
)


def parse_proto_descriptor(proto_text: str) -> list[dict[str, Any]]:
    """Parse the message definitions of a .proto file and return a list of descriptors."""
    messages: list[dict[str, Any]] = []
    pos = 0
    while True:
        m = PROTO_MESSAGE_RE.search(proto_text, pos)
        if not m:
            break
        msg_name = m.group(1)
        # Find the matching closing brace (simple handling; nested messages unsupported)
        brace_start = m.end()
        depth = 1
        p = brace_start
        while depth > 0 and p < len(proto_text):
            if proto_text[p] == "{":
                depth += 1
            elif proto_text[p] == "}":
                depth -= 1
            p += 1
        body = proto_text[brace_start : p - 1]

        fields: list[dict[str, Any]] = []
        for fm in PROTO_FIELD_RE.finditer(body):
            fields.append({
                "repeated": bool(fm.group(1) and "repeated" in fm.group(1)),
                "type": fm.group("type"),
                "name": fm.group("name"),
                "tag": int(fm.group("tag")),
            })

        messages.append({"name": msg_name, "fields": fields})
        pos = p

    return messages


# ═════════════════════════════════════════════════════════════════════
#  Part 2: a known protobuf message ↔ dict
# ═════════════════════════════════════════════════════════════════════


def message_to_dict(msg_obj) -> dict[str, Any]:
    """Convert a protobuf message object into a JSON-compatible dict.

    Args:
        msg_obj: a protobuf message instance (e.g. my_pb2.MyMessage()).
    """
    try:
        from google.protobuf.json_format import MessageToDict
        return MessageToDict(
            msg_obj,
            preserving_proto_field_name=True,
            including_default_value_fields=False,
        )
    except ImportError:
        raise ImportError("the protobuf library is required: pip install protobuf")


def dict_to_message(data: dict[str, Any], msg_class) -> Any:
    """Rebuild a protobuf message from a JSON-compatible dict."""
    try:
        from google.protobuf.json_format import ParseDict
        return ParseDict(data, msg_class())
    except ImportError:
        raise ImportError("the protobuf library is required: pip install protobuf")


# ═════════════════════════════════════════════════════════════════════
#  Part 3: parse() / serialize() — through on-the-fly .proto compilation
# ═════════════════════════════════════════════════════════════════════


def compile_and_parse(
    proto_file: str,
    message_name: str,
    binary_data: bytes,
) -> StructuredNode:
    """Compile a .proto file and use it to deserialize binary data.

    Args:
        proto_file: path to the .proto file.
        message_name: top-level message name (e.g. "MyMessage").
        binary_data: Protobuf-serialized bytes.

    Returns:
        A StructuredNode.
    """
    import importlib
    import sys

    from google.protobuf import descriptor_pb2, compiler

    # Compile the .proto into a temporary directory
    tmp_dir = tempfile.mkdtemp(prefix="proto_")
    try:
        # protoc --python_out=tmp_dir proto_file
        proto_base = os.path.basename(proto_file)
        proto_module_name = proto_base.replace(".proto", "_pb2")

        compiler.main([
            "protoc",
            f"--proto_path={os.path.dirname(proto_file) or '.'}",
            f"--python_out={tmp_dir}",
            proto_file,
        ])

        sys.path.insert(0, tmp_dir)
        try:
            pb2_module = importlib.import_module(proto_module_name)
        finally:
            sys.path.pop(0)

        msg_class = getattr(pb2_module, message_name)
        msg_obj = msg_class()
        msg_obj.ParseFromString(binary_data)

        d = message_to_dict(msg_obj)
        return StructuredNode.from_json_compatible(d, key="")

    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


def serialize_message(msg_class, data: dict[str, Any]) -> bytes:
    """Build a protobuf message from a dict and serialize it.

    Args:
        msg_class: the protobuf message class (e.g. MyMessage).
        data: a JSON-compatible dict.

    Returns:
        The serialized bytes.
    """
    msg = dict_to_message(data, msg_class)
    return msg.SerializeToString()
