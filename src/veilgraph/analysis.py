"""Chain-analysis heuristics: cluster wallets by inferred common ownership.

Implements three classic, well-documented heuristics used by blockchain
surveillance tooling:

1. Common-input (multi-input) heuristic
   Inputs to a single transaction are controlled by the same owner, so all
   input addresses are linked. (We approximate using value-correlation when
   explicit multi-input data is unavailable.)

2. Change-address heuristic
   In an outgoing tx, the output that is not the destination is likely the
   sender's own change address -> link sender and change.

3. Value-correlation / fan-in heuristic
   When several addresses send amounts that sum (within tolerance) to a later
   outgoing payment, they are linked as co-owners funding the same wallet.

The output is a set of clusters (lists of addresses inferred to share an
owner) plus a traceability score (0=untraceable .. 100=trivially traced).
"""

from __future__ import annotations

from collections import defaultdict

from .models import Tx


def _union(clusters: list[set], a: str, b: str) -> list[set]:
    """Merge the sets containing a and/or b; create one if neither present."""
    merged = set()
    rest = []
    for c in clusters:
        if a in c or b in c:
            merged |= c
        else:
            rest.append(c)
    # ensure both endpoints are in the merged set
    merged.add(a)
    merged.add(b)
    if not merged:
        merged = {a, b}
    rest.append(merged)
    return rest


def cluster(txs: list[Tx], value_tol: float = 1e-4) -> list[list[str]]:
    """Return list of clusters (each a list of addresses sharing an owner)."""
    clusters: list[set] = []

    directed = set(
        (t.source.lower(), (t.target or "").lower()) for t in txs if t.target
    )
    senders = {t.source.lower() for t in txs}

    # Heuristic 2: change address / round-trip. For x->y and y->x both exist,
    # link them as same owner. Also, in a single outgoing tx where the target
    # never appears as a sender anywhere, treat as a pure destination (peer),
    # not change.
    for t in txs:
        if not t.target:
            continue
        s, d = t.source.lower(), t.target.lower()
        if (d, s) in directed:
            clusters = _union(clusters, s, d)
        elif d not in senders:
            # d only ever receives -> it's a leaf/destination, no ownership link
            pass
    # Group incoming txs to the same target; if two sources s1,s2 both fund
    # target T within a time window and later T makes an outgoing payment whose
    # amount ~= sum of those fundings, link s1,s2,T as co-owned.
    by_target: dict[str, list[Tx]] = defaultdict(list)
    for t in txs:
        if t.target:
            by_target[t.target.lower()].append(t)

    for target, ins in by_target.items():
        ins = sorted(ins, key=lambda x: x.timestamp)
        for i in range(len(ins)):
            for j in range(i + 1, len(ins)):
                a, b = ins[i], ins[j]
                if a.source == b.source:
                    continue
                # same source cluster already implied
                window = abs(a.timestamp - b.timestamp)
                if window > 6 * 3600:
                    continue
                pair_sum = a.value_eth + b.value_eth
                # scan all outgoing txs from target near that sum
                for o in txs:
                    if o.source.lower() == target and o.timestamp > max(a.timestamp, b.timestamp):
                        if abs(o.value_eth - pair_sum) <= value_tol + 1e-6:
                            clusters = _union(clusters, a.source.lower(), b.source.lower())
                            clusters = _union(clusters, a.source.lower(), target)
                            clusters = _union(clusters, b.source.lower(), target)
                            break

    return [sorted(c) for c in clusters]


def traceability_score(clusters: list[list[str]], txs: list[Tx], focus: str) -> float:
    """0 = focus wallet fully isolated; 100 = trivially linked to many peers.

    Score combines two signals:
      1. Graph distance (BFS hops) from the focus wallet to the nearest
         "sink" node (a wallet that only ever receives, e.g. an exchange
         deposit or merchant). Direct payment = distance 1 = max exposure;
         multi-hop obfuscation pushes the distance up and lowers the score.
      2. Cluster penalty: if the focus is pulled into a multi-address
         co-ownership cluster, traceability rises.
    """
    focus = focus.lower()
    if not txs:
        return 0.0

    adj: dict[str, set[str]] = {}
    out_deg: dict[str, int] = {}
    for t in txs:
        if not t.target:
            continue
        s, d = t.source.lower(), t.target.lower()
        adj.setdefault(s, set()).add(d)
        out_deg[s] = out_deg.get(s, 0) + 1

    # sinks: nodes that never send (only receive)
    sinks = {n for n in adj if out_deg.get(n, 0) == 0}
    # include nodes that appear only as targets, not as sources
    sources = set(adj.keys())
    for t in txs:
        if t.target and t.target.lower() not in sources:
            sinks.add(t.target.lower())

    # BFS from focus
    if focus not in adj and focus not in sinks:
        # focus present but no outgoing edges -> distance scaled by incoming? treat as isolated-ish
        dist = 1 if focus in sinks else 3
    else:
        dist = _bfs_distance(adj, focus, sinks)

    if dist == 0:
        base = 0.0
    else:
        base = max(0.0, 100.0 - (dist - 1) * 35.0)

    in_cluster = any(focus in c and len(c) > 1 for c in clusters)
    if in_cluster:
        base = min(100.0, base + 20.0)
    return round(base, 1)


def _bfs_distance(adj: dict[str, set[str]], start: str, sinks: set[str]) -> int:
    """Shortest hops from start to any sink. 0 if start is a sink itself."""
    if start in sinks:
        return 0
    seen = {start}
    frontier = [start]
    depth = 1
    while frontier:
        nxt = []
        for node in frontier:
            for nbr in adj.get(node, ()):
                if nbr in sinks:
                    return depth
                if nbr not in seen:
                    seen.add(nbr)
                    nxt.append(nbr)
        frontier = nxt
        depth += 1
        if depth > 20:
            break
    return 20  # unreachable to any sink -> treat as far/obscured



def analyze(txs: list[Tx], focus: str) -> dict:
    focus = focus.lower()
    clusters = cluster(txs)
    score = traceability_score(clusters, txs, focus)
    notes = []
    if any(focus in c and len(c) > 1 for c in clusters):
        big = [c for c in clusters if focus in c][0]
        notes.append(
            f"Heurística de fan-in/round-trip ligou {focus} a "
            f"{len(big) - 1} carteira(s) adicional(is) como mesmo dono."
        )
    if not notes:
        notes.append(
            "Nenhuma heurística de co-propriedade disparou: grafo parece "
            "fragmentado (boa privacidade, ou poucos dados)."
        )
    return {
        "clusters": clusters,
        "traceability_score": score,
        "notes": notes,
    }
