"""veilgraph: on-chain transaction graph analyzer + privacy simulator.

Read-only: fetches real EVM transaction history (via Etherscan API) and
runs chain-analysis heuristics to show how traceable a wallet is, then
simulates obfuscation strategies on top to measure how much privacy they
actually buy. No transactions are ever created or broadcast.
"""

__version__ = "0.1.0"
