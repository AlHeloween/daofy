"""
DFM/LFM/FMX format adapter — reads and writes Delphi/Lazarus form files ↔ StructuredNode.

Reuses the DfmComponent/DfmProperty parser of ``src.tools.dfm_parser``
and maps the component tree into a unified StructuredNode.
"""

from __future__ import annotations

from typing import Any, Optional

from .schema import StructuredNode

# Import dfm_parser lazily (avoids a circular import and loading the KB at startup)
_DFM_PARSER = None


def _get_parser():
    global _DFM_PARSER
    if _DFM_PARSER is None:
        from src.tools.dfm_parser import (
            parse_dfm_text,
            serialize_component,
            DfmComponent,
            DfmProperty,
        )
        _DFM_PARSER = (parse_dfm_text, serialize_component, DfmComponent, DfmProperty)
    return _DFM_PARSER


def parse(text: str) -> StructuredNode:
    """Parse DFM/LFM text into a StructuredNode."""
    parse_dfm_text, serialize_component, DfmComponent, DfmProperty = _get_parser()
    root_comp = parse_dfm_text(text)
    if root_comp is None:
        raise ValueError("DFM parsing failed")
    return _component_to_node(root_comp)


def _component_to_node(comp) -> StructuredNode:
    """DfmComponent → StructuredNode。"""
    from src.tools.dfm_parser import DfmProperty

    node = StructuredNode(key=comp.name, kind="object")
    node.attributes["class_name"] = comp.class_name

    # Properties
    for prop in comp.properties:
        val = prop.raw_value
        # Try to infer the type
        if val.isdigit():
            child = StructuredNode(key=prop.name, kind="number", value=int(val))
        elif val.replace(".", "", 1).isdigit() and val.count(".") <= 1:
            try:
                child = StructuredNode(key=prop.name, kind="number", value=float(val))
            except ValueError:
                child = StructuredNode(key=prop.name, kind="string", value=val)
        elif val.lower() in ("true", "false"):
            child = StructuredNode(key=prop.name, kind="boolean", value=val.lower() == "true")
        else:
            child = StructuredNode(key=prop.name, kind="string", value=val)
        if prop.is_event:
            child.attributes["event"] = "1"
        node.children.append(child)

    # Child components — grouped by class_name
    child_classes: dict[str, list] = {}
    for child_comp in comp.children:
        cc = child_comp.class_name
        child_classes.setdefault(cc, []).append(child_comp)

    for cc, items in child_classes.items():
        if len(items) == 1:
            node.children.append(_component_to_node(items[0]))
        else:
            arr = StructuredNode(key=cc, kind="array")
            for item in items:
                arr.children.append(_component_to_node(item))
            node.children.append(arr)

    return node


def serialize(node: StructuredNode) -> str:
    """Serialize a StructuredNode into DFM text.

    Note: this function produces simplified DFM text. For exact DFM text,
    use the official dfm_parser.serialize_component through the manage_component tool.
    """
    lines: list[str] = []
    _node_to_dfm(node, lines, 0)
    return "\n".join(lines)


def _node_to_dfm(node: StructuredNode, lines: list[str], indent: int) -> None:
    """StructuredNode → DFM text lines."""
    pad = "  " * indent
    class_name = node.attributes.get("class_name", "")
    if class_name:
        lines.append(f"{pad}object {node.key}: {class_name}")
    else:
        lines.append(f"{pad}object {node.key}")

    for child in node.children:
        key = child.key

        # Skip meta properties beginning with @
        if key.startswith("@"):
            continue

        if child.attributes.get("event"):
            lines.append(f"{pad}  {key} = {child.value or ''}")
        elif child.kind in ("object", "array"):
            _node_to_dfm(child, lines, indent + 1)
        elif child.kind == "number":
            lines.append(f"{pad}  {key} = {child.value}")
        elif child.kind == "boolean":
            lines.append(f"{pad}  {key} = {str(child.value).lower()}")
        else:
            val = str(child.value or "")
            # Simple escaping
            if " " in val or "'" in val:
                val = val.replace("'", "''")
                val = f"'{val}'"
            lines.append(f"{pad}  {key} = {val}")

    lines.append(f"{pad}end")


def can_parse(text: str) -> bool:
    """Check whether the text is in the DFM/LFM format."""
    text = text.strip()
    if not text.startswith("object ") and not text.startswith("inherited "):
        return False
    try:
        parse_dfm_text, serialize_component, DfmComponent, DfmProperty = _get_parser()
        root = parse_dfm_text(text)
        return root is not None
    except Exception:
        return False


def detect_format(file_path: str) -> Optional[str]:
    """Detect the concrete format from the file extension."""
    ext = file_path.lower()
    if ext.endswith(".dfm"):
        return "dfm"
    if ext.endswith(".lfm"):
        return "lfm"
    if ext.endswith(".fmx"):
        return "fmx"
    return None
