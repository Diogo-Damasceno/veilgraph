"""Pydantic data models shared across the API and core engine."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Tx(BaseModel):
    tx_hash: str
    source: str = Field(alias="from")
    target: str = Field(alias="to")
    value_eth: float = 0.0
    timestamp: int = 0  # unix seconds
    block: int = 0

    model_config = {"populate_by_name": True}

    def as_edge(self) -> dict:
        return {
            "source": self.source.lower(),
            "target": (self.target or "0x0").lower(),
            "tx_hash": self.tx_hash,
            "value_eth": self.value_eth,
            "timestamp": self.timestamp,
            "block": self.block,
        }


class AnalyzeRequest(BaseModel):
    address: str
    tx_limit: int = 500
    api_key: str | None = None
    explain: bool = False
    llm: str = "auto"  # auto | api | offline | anthropic | openai


class NodeOut(BaseModel):
    id: str
    is_focus: bool = False
    inferred_owner: int | None = None  # cluster id from heuristics


class EdgeOut(BaseModel):
    source: str
    target: str
    value_eth: float
    tx_hash: str | None = None
    kind: str = "flow"  # 'flow' | 'inferred' (same-owner guess)


class AnalyzeResponse(BaseModel):
    focus: str
    mode: str  # 'live' | 'synthetic'
    nodes: list[NodeOut]
    edges: list[EdgeOut]
    clusters: list[list[str]]
    traceability_score: float  # 0 (untraceable) .. 100 (trivially traced)
    notes: list[str]
    llm_summary: dict[str, Any] | None = None


class ObfuscateRequest(BaseModel):
    address: str
    strategy: str = "split_payment"  # split_payment | fan_out | peeling
    fan_out: int = 3
    tx_limit: int = 500
    api_key: str | None = None
    explain: bool = False
    llm: str = "auto"  # auto | api | offline | anthropic | openai


class ObfuscateResponse(BaseModel):
    focus: str
    mode: str
    before_score: float
    after_score: float
    nodes: list[NodeOut]
    edges: list[EdgeOut]
    notes: list[str]
    llm_summary: dict[str, Any] | None = None
