"""Obfuscation simulator.

Given a focus wallet and its real transaction history, simulate what the
graph would look like AFTER applying an obfuscation strategy. This is a
modeling layer only: it does not broadcast anything. It exists to show how
much (or how little) each strategy actually lowers traceability, and where
it leaks.

Strategies:
  - split_payment:    the focus wallet never pays directly. Instead, N sibling
                      wallets each send a fraction to the merchant; the merchant
                      total == original payment. Breaks the direct edge focus->M.
  - fan_out:          focus spreads funds across N fresh wallets, then one of
                      them pays. Decouples the funding origin from the spender.
  - peeling:          a chain of 1-input/1-output hops (peeling chain) that
                      forwards value onward, obscuring the source.

We then re-run the chain-analysis heuristics on the simulated graph to measure
the new traceability score. A good strategy reduces the score; a leaky one
doesn't.
"""

from __future__ import annotations

import hashlib

from .analysis import analyze
from .fetcher import synthetic_history
from .constants import MERCHANT_SINK
from .models import Tx
from .graph import build_graph, inferred_owner_map

PAYMENT_TOKEN = MERCHANT_SINK  # shared sink so before/after graphs are comparable


def _hash_addr(seed: str) -> str:
    h = hashlib.sha256(seed.encode()).hexdigest()
    return "0x" + h[:40]


def simulate(
    focus: str,
    txs: list[Tx],
    strategy: str = "split_payment",
    fan_out: int = 3,
) -> dict:
    """Return simulated graph + before/after traceability.

    The simulated graph adds the obfuscation overlay on top of the focus
    wallet's *outgoing* payments. Incoming history is kept as-is for context.
    """
    focus = focus.lower()
    base_outs = [t for t in txs if t.source.lower() == focus]
    sim: list[Tx] = [t for t in txs if t.source.lower() != focus]  # keep others

    note = ""
    sibling_seeds = [f"{focus}-sib-{i}" for i in range(max(1, fan_out))]
    siblings = [_hash_addr(s) for s in sibling_seeds]

    if strategy == "split_payment":
        note = (
            "split_payment: carteiras-irmãs enviam frações do pagamento direto "
            "à carteira do merchant; a carteira foco não aparece na aresta de "
            "pagamento. Vaza por correlação de valor (soma == pagamento)."
        )
        for t in base_outs:
            total = t.value_eth
            parts = [total / fan_out] * fan_out
            parts[0] += total - sum(parts)  # fix float drift
            for i, sib in enumerate(siblings):
                sim.append(Tx(
                    tx_hash=f"0xsim-split-{t.tx_hash[-8:]}-{i}",
                    source=sib,
                    target=PAYMENT_TOKEN,
                    value_eth=round(parts[i], 6),
                    timestamp=t.timestamp,
                    block=t.block,
                ))
            # The focus wallet funds the siblings a moment earlier.
            for i, sib in enumerate(siblings):
                sim.append(Tx(
                    tx_hash=f"0xsim-fund-{t.tx_hash[-8:]}-{i}",
                    source=focus,
                    target=sib,
                    value_eth=round(parts[i], 6),
                    timestamp=t.timestamp - 1,
                    block=t.block,
                ))

    elif strategy == "fan_out":
        note = (
            "fan_out: a carteira foco espalha fundos em N carteiras novas; uma "
            "delas faz o pagamento. Quebra a aresta direta foco->merchant, mas "
            "a fan-out imediata ainda liga o foco às irmãs (heurística round-trip)."
        )
        for t in base_outs:
            # spread then one sibling pays
            spread = t.value_eth / fan_out
            for i, sib in enumerate(siblings):
                sim.append(Tx(
                    tx_hash=f"0xsim-fan-fund-{t.tx_hash[-8:]}-{i}",
                    source=focus,
                    target=sib,
                    value_eth=round(spread, 6),
                    timestamp=t.timestamp - 2,
                    block=t.block,
                ))
            sim.append(Tx(
                tx_hash=f"0xsim-fan-pay-{t.tx_hash[-8:]}",
                source=siblings[0],
                target=PAYMENT_TOKEN,
                value_eth=round(t.value_eth, 6),
                timestamp=t.timestamp,
                block=t.block,
            ))

    elif strategy == "peeling":
        note = (
            "peeling: cadeia de hops 1-entrada/1-saída encaminha o valor; a "
            "origem some do pagamento final. Vaza se os valores forem iguais "
            "(heurística de change/peeling)."
        )
        for t in base_outs:
            prev = focus
            for hop in range(max(2, fan_out)):
                nxt = _hash_addr(f"{focus}-peel-{t.tx_hash[-8:]}-{hop}")
                sim.append(Tx(
                    tx_hash=f"0xsim-peel-{t.tx_hash[-8:]}-{hop}",
                    source=prev,
                    target=nxt,
                    value_eth=round(t.value_eth, 6),
                    timestamp=t.timestamp - (max(2, fan_out) - hop),
                    block=t.block,
                ))
                prev = nxt
            sim.append(Tx(
                tx_hash=f"0xsim-peel-pay-{t.tx_hash[-8:]}",
                source=prev,
                target=PAYMENT_TOKEN,
                value_eth=round(t.value_eth, 6),
                timestamp=t.timestamp,
                block=t.block,
            ))
    else:
        raise ValueError(f"unknown strategy: {strategy}")

    before = analyze(txs, focus)
    after = analyze(sim, focus)
    inmap = inferred_owner_map(after["clusters"])
    nodes, edges = build_graph(sim, focus, inmap)
    return {
        "focus": focus,
        "strategy": strategy,
        "before_score": before["traceability_score"],
        "after_score": after["traceability_score"],
        "nodes": nodes,
        "edges": edges,
        "notes": [note] + after["notes"],
        "clusters_after": after["clusters"],
    }
