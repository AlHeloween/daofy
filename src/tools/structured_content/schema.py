"""
StructuredNode — the unified data model for structured documents.

Every format (DFM/LFM/FMX/XML/JSON/MessagePack/ProtoBuf)
is normalized into a StructuredNode tree, and the subsequent path queries, schema generation
and modifications all operate on this model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class StructuredNode:
    """Generic node model for a structured document.

    Attributes:
        key: the key name of this node (``""`` for the root).
        kind: value type —  ``"object"`` / ``"array"`` / ``"string"`` /
               ``"number"`` / ``"boolean"`` / ``"null"``.
        value: the leaf node's native value (str / int / float / bool / None).
        children: child node list (non-empty when kind=object/array).
        attributes: format-specific metadata, such as class_name for DFM or namespace for XML.
    """
    key: str = ""
    kind: str = "object"  # object | array | string | number | boolean | null
    value: Any = None
    children: list[StructuredNode] = field(default_factory=list)
    attributes: dict[str, str] = field(default_factory=dict)

    # ── Navigation ────────────────────────────────────────────────

    def child_by_key(self, key: str) -> Optional[StructuredNode]:
        """Find a direct child node by key."""
        for c in self.children:
            if c.key == key:
                return c
        return None

    def find_by_path_keys(self, keys: list[str]) -> Optional[StructuredNode]:
        """Walk down a chain of keys (e.g. root/component/properties/Left)."""
        node: Optional[StructuredNode] = self
        for k in keys:
            if node is None:
                return None
            node = node.child_by_key(k)
        return node

    def find_all(self, predicate) -> list[StructuredNode]:
        """Recursively find every matching node.

        Args:
            predicate: the match condition — a str (matched against key) or a callable (custom condition).

        Returns:
            The list of matching nodes.
        """
        result: list[StructuredNode] = []
        if callable(predicate):
            matches = predicate(self)
        else:
            matches = (self.key == predicate)
        if matches:
            result.append(self)
        for c in self.children:
            result.extend(c.find_all(predicate))
        return result

    # ── Serialization ─────────────────────────────────────────────

    def to_json_compatible(self) -> Any:
        """Convert recursively into JSON native types (dict/list/str/int/float/bool/None)."""
        if self.kind == "object":
            d: dict[str, Any] = {}
            if self.attributes:
                d["@attributes"] = dict(self.attributes)
            for c in self.children:
                d[c.key] = c.to_json_compatible()
            return d
        if self.kind == "array":
            return [c.to_json_compatible() for c in self.children]
        return self.value

    @classmethod
    def from_json_compatible(cls, data: Any, key: str = "") -> StructuredNode:
        """Rebuild a StructuredNode from JSON native types."""
        if isinstance(data, dict):
            node = cls(key=key, kind="object")
            attrs = data.get("@attributes")
            if key and isinstance(attrs, dict):
                node.attributes = dict(attrs)
            for k, v in data.items():
                if k == "@attributes":
                    continue
                node.children.append(cls.from_json_compatible(v, key=k))
            return node
        if isinstance(data, list):
            node = cls(key=key, kind="array")
            for i, item in enumerate(data):
                node.children.append(cls.from_json_compatible(item, key=str(i)))
            return node
        if isinstance(data, str):
            return cls(key=key, kind="string", value=data)
        if isinstance(data, bool):
            return cls(key=key, kind="boolean", value=data)
        if isinstance(data, int):
            return cls(key=key, kind="number", value=data)
        if isinstance(data, float):
            return cls(key=key, kind="number", value=data)
        if data is None:
            return cls(key=key, kind="null", value=None)
        return cls(key=key, kind="string", value=str(data))

    def __repr__(self) -> str:
        v = f"={self.value!r}" if self.value is not None else ""
        children_n = f" [{len(self.children)} children]" if self.children else ""
        attr_s = f" attrs={self.attributes}" if self.attributes else ""
        return f"<Node:{self.key}:{self.kind}{v}{children_n}{attr_s}>"
