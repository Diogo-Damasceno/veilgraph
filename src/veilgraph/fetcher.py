"""Transaction history fetcher.

Two modes:
  - live: query Etherscan API (read-only, no tx broadcast).
  - synthetic: generate a deterministic fake history locally (offline).

Both return a list of Tx. The live mode never sends transactions; it only
reads `txlist` (normal transactions) for an address.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import time

import httpx

from .config import etherscan_api_key, etherscan_base_url, default_tx_limit
from .constants import MERCHANT_SINK
from .models import Tx

ETHERSCAN_BASE = etherscan_base_url()


ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


def _normalize(address: str) -> str:
    """Valida e normaliza um endereco EVM (20 bytes = 40 hex apos 0x).

    Antes a checagem era so o prefixo '0x', o que aceitava lixo como '0xzz' e
    seguia adiante (gastando uma chamada de API inutil ou gerando um grafo
    sintetico enganoso). Aqui exigimos o formato real.
    """
    if not isinstance(address, str):
        raise ValueError("address must be a string")
    addr = address.strip()
    if not ADDRESS_RE.match(addr):
        raise ValueError(
            "endereco EVM invalido: esperado '0x' + 40 caracteres hex "
            f"(recebido {addr[:12]!r}...)"
        )
    return addr.lower()


def fetch_live(address: str, tx_limit: int | None = None, api_key: str | None = None) -> list[Tx]:
    """Fetch normal transactions for `address` via Etherscan. Read-only."""
    address = _normalize(address)
    key = api_key or etherscan_api_key()
    if not key:
        raise RuntimeError(
            "No Etherscan API key configured. Set VEILGRAPH_ETHERSCAN_API_KEY "
            "or pass api_key. Alternatively use synthetic mode."
        )
    limit = tx_limit or default_tx_limit()
    params = {
        "module": "account",
        "action": "txlist",
        "address": address,
        "startblock": 0,
        "endblock": 9_999_999_999,
        "page": 1,
        "offset": limit,
        "sort": "asc",
    }
    # Etherscan so aceita a chave como param de query, entao ela inevitavelmente
    # aparece na URL da requisicao. O que podemos (e devemos) fazer e impedir
    # que ela vaze em EXCECOES/LOGS: por isso os erros abaixo nunca incluem a
    # URL completa nem os params — so o status e a mensagem da API.
    if key:
        params["apikey"] = key
    try:
        resp = httpx.get(ETHERSCAN_BASE, params=params, timeout=30.0)
        resp.raise_for_status()
    except httpx.HTTPError as e:
        # IMPORTANTE: str(httpx.HTTPError) contém a URL completa, que inclui
        # a API key como param. Relançamos sem a URL para nao vazar a chave
        # em logs/tracebacks.
        raise RuntimeError(
            f"Etherscan request failed ({type(e).__name__}); "
            "URL omitida para nao expor a chave de API"
        ) from None
    data = resp.json()
    if data.get("status") != "1":
        msg = data.get("message", "query returned no data")
        if msg == "No transactions found" or data.get("result") == "[]":
            return []
        raise RuntimeError(f"Etherscan error: {msg}")
    raw = data["result"]
    txs: list[Tx] = []
    for r in raw:
        try:
            txs.append(
                Tx(
                    tx_hash=r["hash"],
                    source=r["from"],
                    target=r.get("to"),
                    value_eth=int(r["value"]) / 1e18,
                    timestamp=int(r["timeStamp"]),
                    block=int(r["blockNumber"]),
                )
            )
        except (KeyError, ValueError, TypeError):
            continue
    return txs


def _seed(address: str) -> int:
    h = hashlib.sha256(address.encode()).hexdigest()
    return int(h[:16], 16)


def synthetic_history(address: str, n: int = 60) -> list[Tx]:
    """Generate a deterministic fake transaction history for demos/offline use.

    Models the user's scenario: the focus wallet receives income from several
    counterparties (peers), and periodically makes a *direct* payment to a
    merchant sink. This gives the analyzer a clear traceability signal
    (focus -> merchant at distance 1) so the obfuscation simulator has a
    meaningful before/after comparison.
    """
    rng = random.Random(_seed(address))
    focus = _normalize(address)
    peers = [f"0x{i:040x}" for i in range(1, 4)]
    txs: list[Tx] = []
    ts = int(time.time()) - n * 3600
    for i in range(n):
        ts += rng.randint(600, 7200)
        if rng.random() < 0.6:  # incoming payment from a counterparty
            src = rng.choice(peers)
            txs.append(Tx(
                tx_hash=f"0xsyn{i:064x}",
                source=src,
                target=focus,
                value_eth=round(rng.uniform(0.05, 4.0), 4),
                timestamp=ts,
                block=19_000_000 + i,
            ))
        else:  # direct payment to the merchant sink
            txs.append(Tx(
                tx_hash=f"0xsyn{i:064x}",
                source=focus,
                target=MERCHANT_SINK,
                value_eth=round(rng.uniform(0.05, 3.0), 4),
                timestamp=ts,
                block=19_000_000 + i,
            ))
    return txs


def fetch_transactions(
    address: str, tx_limit: int | None = None, api_key: str | None = None
) -> tuple[list[Tx], str]:
    """Return (txs, mode). mode is 'live' or 'synthetic'."""
    try:
        txs = fetch_live(address, tx_limit, api_key)
        return txs, "live"
    except RuntimeError as e:
        if "No Etherscan API key" in str(e):
            return synthetic_history(address, min(tx_limit or 60, 200)), "synthetic"
        # Live query failed for another reason -> fall back to synthetic and
        # annotate via the notes in the caller. We raise a tagged error instead.
        raise
    except (httpx.HTTPError, json.JSONDecodeError):
        return synthetic_history(address, min(tx_limit or 60, 200)), "synthetic"
