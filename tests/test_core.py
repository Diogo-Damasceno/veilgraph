"""Tests for veilgraph core logic (no network required)."""

import pytest

from veilgraph.fetcher import synthetic_history
from veilgraph.analysis import analyze, cluster, traceability_score
from veilgraph.obfuscate import simulate
from veilgraph.graph import build_graph, inferred_owner_map


def test_synthetic_history_deterministic():
    a = "0x1111111111111111111111111111111111111111"
    h1 = synthetic_history(a, n=30)
    h2 = synthetic_history(a, n=30)
    assert [t.tx_hash for t in h1] == [t.tx_hash for t in h2]
    assert len(h1) == 30


def test_synthetic_history_has_focus_edges():
    focus = "0x2222222222222222222222222222222222222222"
    h = synthetic_history(focus, n=50)
    assert any(t.source.lower() == focus for t in h)
    assert any((t.target or "").lower() == focus for t in h)


def test_round_trip_heuristic_links_owner():
    focus = "0xaaaa000000000000000000000000000000000001"
    peer = "0xbbbb000000000000000000000000000000000002"
    from veilgraph.models import Tx
    txs = [
        Tx(tx_hash="0x1", source=focus, target=peer, value_eth=1.0, timestamp=1, block=1),
        Tx(tx_hash="0x2", source=peer, target=focus, value_eth=1.0, timestamp=2, block=2),
    ]
    cl = cluster(txs)
    flat = [c for c in cl if focus in c and peer in c]
    assert flat, "round-trip should link focus and peer as same owner"


def test_fan_in_heuristic_links_co_owners():
    focus = "0xccc0000000000000000000000000000000000003"
    s1 = "0xddd1000000000000000000000000000000000004"
    s2 = "0xeee2000000000000000000000000000000000005"
    from veilgraph.models import Tx
    txs = [
        Tx(tx_hash="0xf1", source=s1, target=focus, value_eth=0.4, timestamp=100, block=1),
        Tx(tx_hash="0xf2", source=s2, target=focus, value_eth=0.6, timestamp=110, block=2),
        Tx(tx_hash="0xf3", source=focus, target="0xmerchant", value_eth=1.0, timestamp=200, block=3),
    ]
    cl = cluster(txs)
    co = [c for c in cl if s1 in c and s2 in c and focus in c]
    assert co, "fan-in should link s1,s2,focus as co-owned"


def test_traceability_score_ranges():
    focus = "0xabc00000000000000000000000000000000000aa"
    h = synthetic_history(focus, n=40)
    s = analyze(h, focus)
    assert 0.0 <= s["traceability_score"] <= 100.0


def test_split_payment_lowers_score():
    focus = "0x12340000000000000000000000000000000000ab"
    h = synthetic_history(focus, n=40)
    before = analyze(h, focus)["traceability_score"]
    sim = simulate(focus, h, strategy="split_payment", fan_out=3)
    assert sim["after_score"] < before, (
        f"split_payment should increase hops/distance and lower the score "
        f"({before} -> {sim['after_score']})"
    )


def test_obfuscate_split_reduces_or_keeps_score():
    focus = "0x12340000000000000000000000000000000000ab"
    h = synthetic_history(focus, n=40)
    sim = simulate(focus, h, strategy="split_payment", fan_out=3)
    assert 0.0 <= sim["after_score"] <= 100.0
    assert sim["before_score"] >= 0.0
    # split_payment must remove the direct focus->merchant edge from graph
    direct = [e for e in sim["edges"] if e["source"] == focus and (e["target"] or "").startswith("0xmerchant")]
    assert not direct, "split_payment should hide the direct payment edge"


def test_obfuscate_fan_out_links_siblings():
    focus = "0x99990000000000000000000000000000000000ff"
    h = synthetic_history(focus, n=20)
    sim = simulate(focus, h, strategy="fan_out", fan_out=3)
    # focus funds siblings; graph must contain the simulated nodes
    assert len(sim["nodes"]) > 0
    # fan_out keeps the direct funding edge, so score does not drop below base
    assert sim["after_score"] >= sim["before_score"]


def test_build_graph_and_inferred_map():
    focus = "0xfeed0000000000000000000000000000000000be"
    h = synthetic_history(focus, n=10)
    cl = cluster(h)
    inmap = inferred_owner_map(cl)
    nodes, edges = build_graph(h, focus, inmap)
    assert any(n["id"] == focus for n in nodes)
    assert all("source" in e and "target" in e for e in edges)
