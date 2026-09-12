"""Runtime configuration sourced from environment variables."""

from __future__ import annotations

import os


def etherscan_api_key() -> str | None:
    """Etherscan API key (free tier). None => synthetic/offline mode."""
    key = os.getenv("VEILGRAPH_ETHERSCAN_API_KEY")
    return key.strip() if key else None


def etherscan_base_url() -> str:
    return os.getenv("VEILGRAPH_ETHERSCAN_URL", "https://api.etherscan.io/api")


def rpc_url() -> str | None:
    """Optional public RPC (not strictly needed; Etherscan covers history)."""
    url = os.getenv("VEILGRAPH_RPC_URL")
    return url.strip() if url else None


def default_tx_limit() -> int:
    try:
        return max(1, min(int(os.getenv("VEILGRAPH_TX_LIMIT", "500")), 10000))
    except ValueError:
        return 500
