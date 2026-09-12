"""Command-line interface: run analysis/obfuscation from the terminal."""

from __future__ import annotations

import argparse
import json
import sys

from .fetcher import fetch_transactions
from .analysis import analyze
from .obfuscate import simulate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="veilgraph",
        description="On-chain graph analyzer + privacy simulator (read-only).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("analyze", help="analyze an address's transaction graph")
    a.add_argument("address")
    a.add_argument("--tx-limit", type=int, default=500)
    a.add_argument("--api-key", default=None)

    o = sub.add_parser("obfuscate", help="simulate an obfuscation strategy")
    o.add_argument("address")
    o.add_argument("--strategy", default="split_payment",
                   choices=["split_payment", "fan_out", "peeling"])
    o.add_argument("--fan-out", type=int, default=3)
    o.add_argument("--tx-limit", type=int, default=500)
    o.add_argument("--api-key", default=None)

    args = parser.parse_args(argv)

    if args.cmd == "analyze":
        txs, mode = fetch_transactions(args.address, args.tx_limit, args.api_key)
        res = analyze(txs, args.address)
        out = {
            "focus": args.address.lower(),
            "mode": mode,
            "clusters": res["clusters"],
            "traceability_score": res["traceability_score"],
            "notes": res["notes"],
            "tx_count": len(txs),
        }
        print(json.dumps(out, indent=2))
        return 0

    if args.cmd == "obfuscate":
        txs, mode = fetch_transactions(args.address, args.tx_limit, args.api_key)
        sim = simulate(args.address, txs, args.strategy, args.fan_out)
        out = {
            "focus": sim["focus"],
            "mode": mode,
            "strategy": sim["strategy"],
            "before_score": sim["before_score"],
            "after_score": sim["after_score"],
            "notes": sim["notes"],
        }
        print(json.dumps(out, indent=2))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
