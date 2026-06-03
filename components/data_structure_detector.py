"""
TraceX — Runtime Data Structure Detector

Analyzes Python runtime variable values and classifies them into
known data structure types. Works on actual Python objects (not strings).

Supported types:
  ARRAY        — 1D list of primitives
  MATRIX       — 2D list of lists (rectangular)
  DP_TABLE     — 2D list used for dynamic programming
  STACK        — list used as a LIFO stack (name hint + ops)
  QUEUE        — deque / list used as FIFO queue
  LINKED_LIST  — object chain with .next / {"val":..,"next":..} dicts
  TREE         — binary tree (.left/.right or {"left":..,"right":..})
  GRAPH        — dict of lists (adjacency list) or 2D adjacency matrix
  DICT         — plain dictionary
  SET          — Python set
  STRING       — str variable
  PRIMITIVE    — int / float / bool
  UNKNOWN      — anything else
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from collections import deque
from typing import Any
import re


# ── Structure Types ───────────────────────────────────────────

class StructureType(str, Enum):
    ARRAY       = "Array"
    MATRIX      = "Matrix"
    DP_TABLE    = "DP Table"
    STACK       = "Stack"
    QUEUE       = "Queue"
    LINKED_LIST = "Linked List"
    TREE        = "Tree"
    GRAPH       = "Graph"
    DICT        = "Dict"
    SET         = "Set"
    STRING      = "String"
    PRIMITIVE   = "Primitive"
    UNKNOWN     = "Unknown"


@dataclass
class StructureInfo:
    name:      str              # variable name
    kind:      StructureType
    value:     Any              # raw Python value (for rendering)
    summary:   str              # short human-readable summary
    meta:      dict = field(default_factory=dict)
    # meta keys depend on kind:
    #   ARRAY/STACK/QUEUE → {"length": int, "elements": list}
    #   MATRIX/DP_TABLE   → {"rows": int, "cols": int, "cells": list[list]}
    #   LINKED_LIST       → {"nodes": list, "length": int}
    #   TREE              → {"nodes": list[dict], "depth": int}
    #   GRAPH             → {"nodes": list, "edges": list[tuple]}
    #   DICT              → {"keys": list, "length": int}
    #   SET               → {"elements": list, "length": int}


# ── Name-hint keyword sets ─────────────────────────────────────

_STACK_NAMES  = {"stack", "stk", "s"}
_QUEUE_NAMES  = {"queue", "q", "bfs", "fifo"}
_DP_NAMES     = {"dp", "memo", "cache", "table", "dp_table", "f", "tab"}
_GRAPH_NAMES  = {"graph", "adj", "adjacency", "g", "edges", "neighbors"}
_TREE_NAMES   = {"tree", "root", "node", "bst"}
_LL_NAMES     = {"head", "node", "tail", "ll", "linked"}


def _name_hint(name: str, hint_set: set[str]) -> bool:
    """Return True if variable name (lowercased) is in the hint set OR
    ends with / equals one of the hints. Avoids false positives like
    'nums' matching 'n' or 'sum' matching 's'."""
    n = name.lower()
    # Exact match first
    if n in hint_set:
        return True
    # Suffix / contains match only for multi-char hints
    return any(len(h) >= 3 and (n == h or n.endswith(h) or n.startswith(h))
               for h in hint_set)


# ── Primitive helpers ──────────────────────────────────────────

def _is_primitive(v: Any) -> bool:
    return isinstance(v, (int, float, bool, str, type(None)))


def _safe_len(v: Any) -> int:
    try:
        return len(v)
    except Exception:
        return 0


def _trim(lst: list, max_n: int = 20) -> list:
    return lst[:max_n]


# ── Tree / Linked List node detection ─────────────────────────

def _is_node_like(v: Any) -> bool:
    """True if v looks like a ListNode / TreeNode class instance."""
    if not hasattr(v, "__dict__"):
        return False
    attrs = set(v.__dict__.keys())
    return bool(attrs & {"next", "left", "right", "val", "value", "data"})


def _is_dict_node(v: Any) -> bool:
    """True if v is a dict with val+next or val+left+right keys."""
    if not isinstance(v, dict):
        return False
    keys = set(v.keys())
    return bool(keys & {"next", "left", "right"}) and bool(keys & {"val", "value", "data"})


def _is_tree_node(v: Any) -> bool:
    """True if v has .left / .right or is a dict with left/right."""
    if _is_dict_node(v):
        keys = set(v.keys())
        return bool(keys & {"left", "right"})
    return _is_node_like(v) and hasattr(v, "left") or hasattr(v, "right")


def _is_ll_node(v: Any) -> bool:
    """True if v has .next (but NOT .left/.right)."""
    if _is_dict_node(v):
        return "next" in v
    if not _is_node_like(v):
        return False
    return hasattr(v, "next") and not (hasattr(v, "left") or hasattr(v, "right"))


def _traverse_ll(head: Any, max_nodes: int = 30) -> list:
    nodes = []
    seen  = set()
    cur   = head
    while cur is not None and len(nodes) < max_nodes:
        uid = id(cur)
        if uid in seen:
            nodes.append("→ (cycle)")
            break
        seen.add(uid)
        val = None
        for attr in ("val", "value", "data"):
            if hasattr(cur, attr):
                val = getattr(cur, attr)
                break
            if isinstance(cur, dict) and attr in cur:
                val = cur[attr]
                break
        nodes.append(val)
        cur = getattr(cur, "next", None) or (cur.get("next") if isinstance(cur, dict) else None)
    return nodes


def _traverse_tree(root: Any, max_nodes: int = 63) -> list[dict]:
    """BFS traversal; returns list of {val, depth, index} for rendering."""
    if root is None:
        return []
    nodes = []
    queue: list[tuple[Any, int, int]] = [(root, 0, 1)]
    while queue and len(nodes) < max_nodes:
        node, depth, idx = queue.pop(0)
        if node is None:
            continue
        val = None
        for attr in ("val", "value", "data", "key"):
            v = getattr(node, attr, None) or (node.get(attr) if isinstance(node, dict) else None)
            if v is not None:
                val = v
                break
        nodes.append({"val": val, "depth": depth, "index": idx})
        left  = getattr(node, "left",  None) or (node.get("left")  if isinstance(node, dict) else None)
        right = getattr(node, "right", None) or (node.get("right") if isinstance(node, dict) else None)
        queue += [(left, depth + 1, idx * 2), (right, depth + 1, idx * 2 + 1)]
    return nodes


# ── Main detector ──────────────────────────────────────────────

def detect_structure(name: str, value: Any) -> StructureInfo:
    """
    Analyse a runtime variable and return a StructureInfo.
    This is the main public API — call it for every variable per step.
    """

    # ── Primitives ────────────────────────────────────────────
    if isinstance(value, bool):
        return StructureInfo(name, StructureType.PRIMITIVE, value,
                             f"{name} = {value}", {"kind": "bool"})
    if isinstance(value, (int, float)):
        return StructureInfo(name, StructureType.PRIMITIVE, value,
                             f"{name} = {value}", {"kind": type(value).__name__})
    if isinstance(value, str):
        summary = f'{name} = "{value[:30]}{"..." if len(value) > 30 else ""}"'
        return StructureInfo(name, StructureType.STRING, value, summary,
                             {"length": len(value)})

    # ── Linked List node ─────────────────────────────────────
    if _is_ll_node(value) or _name_hint(name, _LL_NAMES) and _is_ll_node(value):
        nodes = _traverse_ll(value)
        summary = f"{name}: {' → '.join(str(v) for v in nodes[:8])}{'→...' if len(nodes) > 8 else ''}"
        return StructureInfo(name, StructureType.LINKED_LIST, value, summary,
                             {"nodes": nodes, "length": len(nodes)})

    # ── Tree node ────────────────────────────────────────────
    if _is_tree_node(value) or _name_hint(name, _TREE_NAMES) and _is_node_like(value):
        tree_nodes = _traverse_tree(value)
        depth = max((n["depth"] for n in tree_nodes), default=0)
        summary = f"{name}: Tree  depth={depth}  nodes={len(tree_nodes)}"
        return StructureInfo(name, StructureType.TREE, value, summary,
                             {"nodes": tree_nodes, "depth": depth})

    # ── deque → Queue ────────────────────────────────────────
    if isinstance(value, deque):
        elems = _trim(list(value))
        summary = f"{name}: Queue  [{', '.join(str(e) for e in elems[:6])}{',...' if len(elems)>6 else ''}]"
        return StructureInfo(name, StructureType.QUEUE, value, summary,
                             {"length": len(value), "elements": elems})

    # ── set ──────────────────────────────────────────────────
    if isinstance(value, (set, frozenset)):
        elems = _trim(sorted(value, key=str))
        summary = f"{name}: {{{', '.join(str(e) for e in elems[:6])}{',...' if len(elems)>6 else ''}}}"
        return StructureInfo(name, StructureType.SET, value, summary,
                             {"elements": elems, "length": len(value)})

    # ── list / tuple ─────────────────────────────────────────
    if isinstance(value, (list, tuple)):
        lst = list(value)
        n   = len(lst)

        # Empty
        if n == 0:
            return StructureInfo(name, StructureType.ARRAY, value,
                                 f"{name}: [] (empty)", {"length": 0, "elements": []})

        # 2-D Matrix / DP Table
        if all(isinstance(row, (list, tuple)) for row in lst):
            rows = len(lst)
            cols_set = {len(r) for r in lst}
            cols = max(cols_set) if cols_set else 0
            cells = [list(r[:20]) for r in lst[:20]]  # cap for rendering

            # DP Table heuristic: name hint OR all numeric + square/rect
            is_dp = (_name_hint(name, _DP_NAMES)
                     or (all(isinstance(c, (int, float, bool))
                             for row in lst for c in row)
                         and rows <= 50 and cols <= 50))
            kind = StructureType.DP_TABLE if is_dp else StructureType.MATRIX
            summary = f"{name}: {'DP Table' if is_dp else 'Matrix'}  {rows}×{cols}"
            return StructureInfo(name, kind, value, summary,
                                 {"rows": rows, "cols": cols, "cells": cells})

        # Stack heuristic
        if _name_hint(name, _STACK_NAMES):
            elems = _trim(lst)
            summary = f"{name}: Stack  top={lst[-1] if lst else 'empty'}  depth={n}"
            return StructureInfo(name, StructureType.STACK, value, summary,
                                 {"length": n, "elements": elems})

        # Queue heuristic
        if _name_hint(name, _QUEUE_NAMES):
            elems = _trim(lst)
            summary = f"{name}: Queue  front={lst[0] if lst else 'empty'}  len={n}"
            return StructureInfo(name, StructureType.QUEUE, value, summary,
                                 {"length": n, "elements": elems})

        # Plain 1-D Array
        elems = _trim(lst)
        summary = f"{name}: [{', '.join(str(e) for e in elems[:8])}{',...' if n>8 else ''}]  len={n}"
        return StructureInfo(name, StructureType.ARRAY, value, summary,
                             {"length": n, "elements": elems})

    # ── dict ─────────────────────────────────────────────────
    if isinstance(value, dict):
        vals = list(value.values())

        # Graph as adjacency list: dict[node] = list[neighbor]
        if (len(value) > 0
                and all(isinstance(v2, (list, set)) for v2 in vals)
                or _name_hint(name, _GRAPH_NAMES)):
            nodes_list = list(value.keys())[:20]
            edges = []
            for src, neighbors in list(value.items())[:20]:
                if isinstance(neighbors, (list, set)):
                    for dst in list(neighbors)[:10]:
                        edges.append((src, dst))
            summary = f"{name}: Graph  nodes={len(value)}  edges={len(edges)}"
            return StructureInfo(name, StructureType.GRAPH, value, summary,
                                 {"nodes": nodes_list, "edges": edges[:30]})

        # Plain dict
        keys = list(value.keys())[:10]
        summary = f"{name}: {{{', '.join(f'{k}:{v}' for k,v in list(value.items())[:4])}{',...' if len(value)>4 else ''}}}"
        return StructureInfo(name, StructureType.DICT, value, summary,
                             {"keys": keys, "length": len(value)})

    # ── Fallback ──────────────────────────────────────────────
    return StructureInfo(name, StructureType.UNKNOWN, value,
                         f"{name}: {type(value).__name__}", {})


# ── Batch detector ────────────────────────────────────────────

def detect_all(variables_raw: dict[str, Any]) -> dict[str, StructureInfo]:
    """
    Run detect_structure on every variable in the raw locals dict.
    Returns {var_name: StructureInfo}.
    """
    result = {}
    for name, value in variables_raw.items():
        # Skip builtins, dunder names, and internal Python variables
        if name.startswith("__") or name == "builtins":
            continue
        try:
            result[name] = detect_structure(name, value)
        except Exception:
            pass
    return result


def structures_to_json(infos: dict[str, StructureInfo]) -> list[dict]:
    """Serialize StructureInfo objects to JSON-safe dicts for the timeline."""
    out = []
    for name, info in infos.items():
        # Truncate cells/elements for JSON
        meta = {}
        for k, v in info.meta.items():
            if k in ("cells",):
                meta[k] = [[str(c) for c in row[:10]] for row in v[:10]]
            elif k in ("elements", "nodes", "keys"):
                meta[k] = [str(e) for e in v[:15]]
            elif k == "edges":
                meta[k] = [(str(a), str(b)) for a, b in v[:20]]
            else:
                meta[k] = v
        out.append({
            "name":    name,
            "kind":    info.kind.value,
            "summary": info.summary,
            "meta":    meta,
        })
    return out
