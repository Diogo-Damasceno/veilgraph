"""Command-line interface: run analysis/obfuscation from the terminal."""

from __future__ import annotations

import argparse
import json
import sys

from .banner import print_banner
from .fetcher import fetch_transactions
from .analysis import analyze
from .obfuscate import simulate
from .llm import explain, get_client, redact


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="veilgraph",
        description="On-chain graph analyzer + privacy simulator (read-only).",
    )
    parser.add_argument("--no-banner", action="store_true",
                        help="oculta o banner ASCII")
    sub = parser.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("analyze", help="analyze an address's transaction graph")
    a.add_argument("address")
    a.add_argument("--tx-limit", type=int, default=500)
    a.add_argument("--api-key", default=None)
    a.add_argument("--explain", action="store_true",
                   help="pede ao LLM uma explicacao do grafo (PT-BR)")
    a.add_argument("--llm", choices=["auto", "api", "offline", "anthropic", "openai"],
                   default="auto")

    o = sub.add_parser("obfuscate", help="simulate an obfuscation strategy")
    o.add_argument("address")
    o.add_argument("--strategy", default="split_payment",
                   choices=["split_payment", "fan_out", "peeling"])
    o.add_argument("--fan-out", type=int, default=3)
    o.add_argument("--tx-limit", type=int, default=500)
    o.add_argument("--api-key", default=None)
    o.add_argument("--explain", action="store_true",
                   help="pede ao LLM uma explicacao da simulacao (PT-BR)")
    o.add_argument("--llm", choices=["auto", "api", "offline", "anthropic", "openai"],
                   default="auto")

    m = sub.add_parser("llm", help="mostra/diagnostica o adaptador de LLM")
    m.add_argument("--ping", action="store_true",
                   help="faz uma chamada real de teste ao provedor")
    m.add_argument("--provider", choices=["auto", "openai", "anthropic", "offline"],
                   default="auto")

    args = parser.parse_args(argv)

    if not args.no_banner:
        use_color = hasattr(sys.stdout, "isatty") and sys.stdout.isatty()
        print_banner(color=use_color)

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
        if args.explain:
            blk = explain(out, prefer=args.llm)
            if blk:
                out["llm_summary"] = blk
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
        if args.explain:
            blk = explain(out, prefer=args.llm)
            if blk:
                out["llm_summary"] = blk
        print(json.dumps(out, indent=2))
        return 0

    if args.cmd == "llm":
        from .llm import get_client
        c = get_client(args.provider)
        print(f"  provedor : {args.provider}")
        print(f"  adapter  : {type(c).__name__}")
        print(f"  modelo   : {c.model}")
        if hasattr(c, "base_url"):
            print(f"  base_url : {c.base_url or '(default)'}")
            print(f"  api_key  : {'configurada' if c.available() else 'AUSENTE'}")
        else:
            print("  modo     : offline (heuristica local, sem rede)")
        if args.ping:
            print("\n  enviando chamada de teste...")
            resp = c.complete(
                "Responda sempre em portugues do Brasil.",
                json.dumps({"focus": "0x" + "0" * 40, "traceability_score": 100.0,
                            "clusters": [], "tx_count": 0}),
                timeout=30.0,
            )
            print("  resposta:")
            print("    " + redact(resp).replace("\n", "\n    ")[:800])
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
