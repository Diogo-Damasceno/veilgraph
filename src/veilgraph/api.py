"""FastAPI application exposing analyze + obfuscate endpoints."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .fetcher import fetch_transactions
from .analysis import analyze
from .graph import build_graph, inferred_owner_map
from .obfuscate import simulate
from .models import (
    AnalyzeRequest,
    AnalyzeResponse,
    NodeOut,
    EdgeOut,
    ObfuscateRequest,
    ObfuscateResponse,
)

app = FastAPI(
    title="VeilGraph",
    description=(
        "On-chain transaction graph analyzer + privacy/obfuscation simulator "
        "(EVM, read-only). No transactions are ever created or broadcast."
    ),
    version=__version__,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

import os

_STATIC = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.isdir(_STATIC):
    app.mount("/static", StaticFiles(directory=_STATIC), name="static")

    @app.get("/")
    def index():
        return FileResponse(os.path.join(_STATIC, "index.html"))


@app.get("/health")
def health():
    return {"status": "ok", "version": __version__}


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze_endpoint(req: AnalyzeRequest):
    try:
        txs, mode = fetch_transactions(req.address, req.tx_limit, req.api_key)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    res = analyze(txs, req.address)
    inmap = inferred_owner_map(res["clusters"])
    nodes, edges = build_graph(txs, req.address, inmap)
    return AnalyzeResponse(
        focus=req.address.lower(),
        mode=mode,
        nodes=nodes,
        edges=edges,
        clusters=res["clusters"],
        traceability_score=res["traceability_score"],
        notes=res["notes"],
    )


@app.post("/obfuscate", response_model=ObfuscateResponse)
def obfuscate_endpoint(req: ObfuscateRequest):
    try:
        txs, mode = fetch_transactions(req.address, req.tx_limit, req.api_key)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    sim = simulate(req.address, txs, req.strategy, req.fan_out)
    return ObfuscateResponse(
        focus=sim["focus"],
        mode=mode,
        before_score=sim["before_score"],
        after_score=sim["after_score"],
        nodes=sim["nodes"],
        edges=sim["edges"],
        notes=sim["notes"],
    )
