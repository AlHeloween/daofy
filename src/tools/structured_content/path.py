"""
JSONPath query engine — evaluates simplified JSONPath expressions over a StructuredNode tree.

Supported syntax subset:
  $               the root node
  .key            access a child node by key name
  ["key"]         bracketed key name
  [N]             array index
  [*]             wildcard (all child nodes or array elements)
  ..key           recursive descent lookup
  [?(expr)]       filter expression (simplified: @.key op val)

Not supported (to be added as needed):
  slices [start:end:step]
  multiple keys ["a","b"]
  script expressions
"""

from __future__ import annotations

import re
from typing import Any, Optional

from .schema import StructuredNode


# ── Tokenise ─────────────────────────────────────────────────────────

_TOKEN_RE = re.compile(
    r"""
    \$                                           # root
    |\.\.(?P<descendant>[a-zA-Z_][\w]*)         # ..key (recursive descent)
    |\.(?P<dotkey>[a-zA-Z_][\w]*)               # .key (direct child)
    |\[\s*(?P<bracket>\*|[0-9]+)\s*\]            # [*] or [N]
    |\[\s*\?\s*\((?P<filter>[^)]*)\)\s*\]        # [?(expr)]
    |\["(?P<qkey>[^"]+)"\]                       # ["key"]
    """,
    re.VERBOSE,
)


def _tokenise(expression: str) -> list[tuple[str, str]]:
    """Parse a JSONPath expression into a token list: (type, value)."""
    tokens: list[tuple[str, str]] = []
    pos = 0
    while pos < len(expression):
        # Skip whitespace
        if expression[pos] in " \t\r\n":
            pos += 1
            continue

        m = _TOKEN_RE.match(expression, pos)
        if m is None:
            raise ValueError(f"Unable to parse JSONPath at position {pos}: {expression[pos:]!r}")

        if m.group() == "$":
            tokens.append(("root", "$"))
        elif m.lastgroup == "descendant":
            tokens.append(("descendant", m.group("descendant")))
        elif m.lastgroup == "dotkey":
            tokens.append(("key", m.group("dotkey")))
        elif m.lastgroup == "qkey":
            tokens.append(("key", m.group("qkey")))
        elif m.lastgroup == "bracket":
            val = m.group("bracket")
            if val == "*":
                tokens.append(("wildcard", "*"))
            else:
                tokens.append(("index", int(val)))
        elif m.lastgroup == "filter":
            tokens.append(("filter", m.group("filter")))

        pos = m.end()
    return tokens


# ── Evaluator ────────────────────────────────────────────────────────


def _apply_filter(node: StructuredNode, expr: str) -> bool:
    """Evaluate a simplified filter expression: @.key op val."""
    # expr looks like "@.name == 'Button1'" or "@.Left > 100"
    m = re.match(
        r"""@\.(?P<key>[a-zA-Z_][\w]*)
        \s*(?P<op>==|!=|>=|<=|>|<|=~)\s*
        ['"]?(?P<val>[^'"]+)['"]?
        """,
        expr.strip(),
    )
    if not m:
        return True  # a filter that cannot be parsed passes by default
    key, op, val_str = m.group("key"), m.group("op"), m.group("val")
    actual = node.child_by_key(key)
    if actual is None:
        return False
    actual_val = actual.value if actual.value is not None else (
        actual.to_json_compatible() if actual.kind in ("object", "array") else ""
    )
    # Type coercion
    try:
        if actual_val is not None and val_str.isdigit():
            actual_val = int(actual_val)
            val_str = int(val_str)
    except (ValueError, TypeError):
        pass

    if op == "==":
        return actual_val == val_str
    if op == "!=":
        return actual_val != val_str
    if op == ">":
        return isinstance(actual_val, (int, float)) and actual_val > val_str
    if op == "<":
        return isinstance(actual_val, (int, float)) and actual_val < val_str
    if op == ">=":
        return isinstance(actual_val, (int, float)) and actual_val >= val_str
    if op == "<=":
        return isinstance(actual_val, (int, float)) and actual_val <= val_str
    return True


def _query_single(node: StructuredNode, token: tuple[str, str]) -> list[StructuredNode]:
    """Apply one token to a single node and return the list of matching child nodes."""
    typ, val = token

    if typ == "root":
        return [node]

    if typ == "key":
        if val == node.key:  # used to match the key after recursion
            return [node]
        c = node.child_by_key(val)
        return [c] if c else []

    if typ == "index":
        if node.kind == "array" and isinstance(val, int) and val < len(node.children):
            return [node.children[val]]
        return []

    if typ == "wildcard":
        return list(node.children)

    if typ == "descendant":
        return node.find_all(val)

    if typ == "filter":
        return [c for c in node.children if _apply_filter(c, val)]

    return []


def query(node: StructuredNode, expression: str) -> list[StructuredNode]:
    """Run a JSONPath query over a StructuredNode tree.

    Args:
        node: the root node.
        expression: the JSONPath expression, e.g. ``$.components[0].name``.

    Returns:
        The list of matching nodes.
    """
    tokens = _tokenise(expression)
    if not tokens:
        return []

    candidates = [node]
    for token in tokens:
        next_candidates: list[StructuredNode] = []
        for c in candidates:
            next_candidates.extend(_query_single(c, token))
        candidates = next_candidates
        if not candidates:
            break
    return candidates


def query_first(node: StructuredNode, expression: str) -> Optional[StructuredNode]:
    """Return the first matching node."""
    results = query(node, expression)
    return results[0] if results else None


def set_value(node: StructuredNode, expression: str, value: Any) -> int:
    """Set a node's value through a JSONPath expression.

    Args:
        node: the root node.
        expression: the JSONPath expression.
        value: the new value (a string or a JSON-compatible type).

    Returns:
        The number of nodes changed.
    """
    targets = query(node, expression)
    for t in targets:
        t.value = value
        if not isinstance(value, (str, int, float, bool)):
            t.kind = "string"
            t.value = str(value)
    return len(targets)


def set_value_by_path_keys(root: StructuredNode, keys: list[str], value: Any) -> bool:
    """Set a value through a chain of keys (the path="a.b.c" style of the set action)."""
    node = root
    for k in keys[:-1]:
        child = node.child_by_key(k)
        if child is None:
            child = StructuredNode(key=k, kind="object")
            node.children.append(child)
        node = child
    last_key = keys[-1]
    existing = node.child_by_key(last_key)
    if existing:
        existing.value = value
        existing.kind = type(value).__name__ if isinstance(value, (str, int, float, bool)) else "string"
    else:
        node.children.append(StructuredNode(
            key=last_key,
            kind=type(value).__name__ if isinstance(value, (str, int, float, bool)) else "string",
            value=value,
        ))
    return True
