"""
structured_content — the unified read/write/search/modify tool for structured documents.

Supported formats:
  - DFM / LFM / FMX (Delphi / Lazarus forms)
  - XML
  - JSON
  - MessagePack
  - ProtoBuf (the .proto must be compiled in advance)

Core operations:
  read        read a structured file → JSON / Schema
  get_schema  generate a JSON Schema
  set         modify a value by path
  search      search nodes by JSONPath
"""

from __future__ import annotations

import os
import json as _json
from typing import Any, Optional

from .schema import StructuredNode
from .parser import (
    read_file,
    write_file,
    detect_format,
    SUPPORTED_FORMATS,
)
from .path import query, set_value, query_first
from .schema_gen import generate_schema

__all__ = ["handle_structured_content", "SUPPORTED_FORMATS"]


async def handle_structured_content(arguments: dict) -> dict[str, Any]:
    """``structured_content`` — unified read/write/query/modify for structured documents.

    Action:
        read         read the file and return JSON / Schema
        get_schema   generate a JSON Schema
        set          modify a value by path
        search       search by JSONPath

    Args:
        action: the operation type.
        file_path: the file path.
        path: the JSONPath path (default ``$``, i.e. the root).
        value: the new value for the set action.
        format: force a format (dfm/lfm/fmx/xml/json/msgpack/protobuf).
                 Defaults to detection from the file extension.
        output: the output format of the read action ("json" | "schema" | "both").
        proto_file: the .proto file path, for ProtoBuf mode.
        message_name: the message name, for ProtoBuf mode.
    """
    action = arguments.get("action", "read")
    file_path = arguments.get("file_path", "")
    path_expr = arguments.get("path", "$")
    value = arguments.get("value")
    fmt_hint = arguments.get("format")
    output = arguments.get("output", "json")

    if not file_path and action in ("read", "set", "search"):
        return {"error": "file_path is required"}

    # ── Format detection ──
    try:
        fmt = detect_format(file_path, hint=fmt_hint) if file_path else fmt_hint
    except Exception as e:
        return {"status": "failed", "error": f"Format detection failed: {e}"}

    # ── read ────────────────────────────────────────────────────
    if action == "read":
        proto_file = arguments.get("proto_file")
        message_name = arguments.get("message_name")

        if fmt == "protobuf":
            if not proto_file or not message_name:
                return {"error": "ProtoBuf reading requires the proto_file and message_name parameters"}
            from .protobuf_adapter import compile_and_parse
            with open(file_path, "rb") as f:
                raw = f.read()
            node = compile_and_parse(proto_file, message_name, raw)
        else:
            try:
                node, fmt = read_file(file_path, fmt)
            except FileNotFoundError:
                return {"status": "failed", "error": f"File not found: {file_path}"}
            except ValueError as e:
                return {"status": "failed", "error": str(e)}

        # Narrow down by path
        if path_expr and path_expr != "$":
            matched = query(node, path_expr)
            if not matched:
                return {
                    "format": fmt,
                    "path": path_expr,
                    "match_count": 0,
                    "error": f"Path '{path_expr}' matched nothing",
                }
            result_nodes = matched
        else:
            result_nodes = [node]

        # Produced result
        result: dict[str, Any] = {
            "format": fmt,
            "path": path_expr,
            "match_count": len(result_nodes),
        }

        if output in ("schema", "both"):
            result["schema"] = generate_schema(node, title=os.path.basename(file_path))

        if output in ("json", "both"):
            if len(result_nodes) == 1:
                result["value"] = result_nodes[0].to_json_compatible()
            else:
                result["value"] = [n.to_json_compatible() for n in result_nodes]

        return {"status": "success", "data": result}

    # ── get_schema ──────────────────────────────────────────────
    if action == "get_schema":
        try:
            node, fmt = read_file(file_path, fmt)
        except FileNotFoundError:
            return {"status": "failed", "error": f"File not found: {file_path}"}
        except ValueError as e:
            return {"status": "failed", "error": str(e)}
        schema = generate_schema(node, title=os.path.basename(file_path))
        return {
            "status": "success",
            "data": {
                "format": fmt,
                "schema": schema,
            }
        }

    # ── set ─────────────────────────────────────────────────────
    if action == "set":
        if value is None:
            return {"error": "set action requires 'value' parameter"}
        try:
            node, fmt = read_file(file_path, fmt)
        except FileNotFoundError:
            return {"status": "failed", "error": f"File not found: {file_path}"}
        except ValueError as e:
            return {"status": "failed", "error": str(e)}
        count = set_value(node, path_expr, value)
        write_file(node, file_path, fmt)
        return {
            "status": "success",
            "data": {
                "format": fmt,
                "path": path_expr,
                "modified_count": count,
                "message": f"Modified {count} node(s)",
            }
        }

    # ── search ──────────────────────────────────────────────────
    if action == "search":
        try:
            node, fmt = read_file(file_path, fmt)
        except FileNotFoundError:
            return {"status": "failed", "error": f"File not found: {file_path}"}
        except ValueError as e:
            return {"status": "failed", "error": str(e)}
        matched = query(node, path_expr)
        return {
            "status": "success",
            "data": {
                "format": fmt,
                "path": path_expr,
                "match_count": len(matched),
                "matches": [n.to_json_compatible() for n in matched],
            }
        }

    return {"error": f"Unknown action: {action}; supported: read, get_schema, set, search"}
