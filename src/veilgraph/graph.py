"""Build node/edge representations from transactions for the API/UI."""

from __future__ import annotations

from .models import Tx


def build_graph(txs: list[Tx], focus: str, inferred_owner: dict | None = None):
    """Return (nodes, edges) where each is a list of dicts for the UI."""
    focus = focus.lower()
    inferred_owner = inferred_owner or {}
    nodes_map: dict[str, dict] = {}
    for t in txs:
        for addr in (t.source, t.target):
            if not addr:
                continue
            a = addr.lower()
            if a not in nodes_map:
                nodes_map[a] = {
                    "id": a,
                    "is_focus": a == focus,
                    "inferred_owner": inferred_owner.get(a),
                }
    edges = [t.as_edge() for t in txs if t.target]
    return list(nodes_map.values()), edges


def inferred_owner_map(clusters: list[list[str]]) -> dict:
    m = {}
    for i, c in enumerate(clusters):
        for addr in c:
            m[addr.lower()] = i
    return m
