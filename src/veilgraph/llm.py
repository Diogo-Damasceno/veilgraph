"""Adaptadores de LLM — SDKs oficiais (openai / anthropic).

Mesma interface do redteam-cli, adaptada ao dominio do VeilGraph: o LLM
recebe o resumo do grafo (clusters, score de rastreabilidade) e devolve uma
explicacao em portugues do Brasil.

Config (variaveis de ambiente)
  OpenRouter (default):
    VEILGRAPH_LLM_BASE_URL   https://openrouter.ai/api/v1
    VEILGRAPH_LLM_API_KEY    (ou OPENROUTER_API_KEY)
    VEILGRAPH_LLM_MODEL      ex: deepseek/deepseek-r1, openai/gpt-4o-mini
  Anthropic:
    ANTHROPIC_API_KEY        (ou ANTHROPIC_AUTH_TOKEN)
    ANTHROPIC_MODEL          ex: claude-sonnet-4-5

Privacidade: apenas numeros agregados e IDs de endereco vao no prompt.
Nenhuma chave de API da Etherscan e enviada.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

SYSTEM_PROMPT = (
    "Voce e um analista de chain (blockchain forensics) explicando o grafo de "
    "transacoes de uma carteira para um usuario tecnico. Receba os dados em "
    "JSON e devolva, em portugues do Brasil, apenas um objeto JSON valido com "
    "as chaves: 'resumo' (2-4 frases sobre quao rastreavel a carteira e), "
    "'observacoes' (lista de strings com achados relevantes do grafo), "
    "'recomendacoes' (lista de strings de como reduzir a rastreabilidade). "
    "Nao invente transacoes nem enderecos. Baseie-se apenas nos dados "
    "recebidos. Nunca instrua atividade ilicita."
)

SECRET_RE = re.compile(
    r"(?i)\b(password|passwd|senha|api[_-]?key|secret|token)\b(\s*[=:]\s*)\S+"
)

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "openai/gpt-4o-mini"
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-5"

TIMEOUT = 60.0


def redact(text: str) -> str:
    """Substitui o VALOR de possiveis segredos por [REDACTED].

    Corta tudo depois do separador (= ou :), nao so o ultimo caractere:
    'api_key=SUPERSEGREDO123 resto' -> 'api_key=[REDACTED] resto'.
    """
    return SECRET_RE.sub(lambda m: m.group(1) + m.group(2) + "[REDACTED]", text)


def _offline_payload(data: dict, motivo: str = "") -> dict:
    """Explicacao heuristica local: nunca deixa o comando sem resposta."""
    score = data.get("traceability_score", 0.0)
    n_clusters = len(data.get("clusters") or [])
    n_tx = data.get("tx_count", 0)

    if score >= 80:
        faixa = "extremamente rastreavel"
    elif score >= 50:
        faixa = "moderadamente rastreavel"
    elif score >= 20:
        faixa = "parcialmente ofuscada"
    else:
        faixa = "bem isolada"

    resumo = (
        f"A carteira analisada tem score de rastreabilidade {score}/100, "
        f"o que a torna {faixa}. Foram avaliadas {n_tx} transacoes e "
        f"{n_clusters} cluster(s) de co-propriedade inferidos."
    )
    if motivo:
        resumo += f" Analise gerada OFFLINE (heuristica). Motivo: {motivo}"

    obs = []
    if n_clusters:
        obs.append(
            f"{n_clusters} cluster(s) de enderecos ligados por round-trip ou fan-in."
        )
    if score >= 80:
        obs.append("Pagamentos diretos a destinatarios finais encurtam a distancia no grafo.")
    if n_tx == 0:
        obs.append("Nenhuma transacao disponivel para analise.")

    rec = []
    if score >= 50:
        rec.append("Aumentar a distancia entre a carteira e o destinatario final (mais hops).")
        rec.append("Evitar reutilizar enderecos que ja receberam de exchanges.")
    rec.append("Reduzir a correlacao de valor entre entradas e saidas.")

    return {"resumo": resumo, "observacoes": obs, "recomendacoes": rec}


@dataclass
class LLMClient:
    """Interface comum: `complete` e `available`."""

    model: str = "offline"

    def complete(self, system: str, user: str, timeout: float = TIMEOUT) -> str:
        raise NotImplementedError

    def available(self) -> bool:
        return True


class OfflineClient(LLMClient):
    """Sem rede/sem chave: heuristica local."""

    def __init__(self, motivo: str = ""):
        self.motivo = motivo
        super().__init__(model="offline")

    def available(self) -> bool:
        return True

    def complete(self, system: str, user: str, timeout: float = TIMEOUT) -> str:
        try:
            data = json.loads(user)
        except Exception:
            data = {}
        return json.dumps(_offline_payload(data, self.motivo), ensure_ascii=False)


class OpenAICompatClient(LLMClient):
    """SDK oficial `openai` contra OpenRouter (ou qualquer endpoint compativel)."""

    def __init__(self, base_url: str | None = None, api_key: str | None = None,
                 model: str | None = None):
        self.base_url = (
            base_url
            or os.getenv("VEILGRAPH_LLM_BASE_URL")
            or os.getenv("LLM_API_BASE")
            or DEFAULT_BASE_URL
        ).rstrip("/")
        self.api_key = (
            api_key
            or os.getenv("VEILGRAPH_LLM_API_KEY")
            or os.getenv("OPENROUTER_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or ""
        )
        super().__init__(
            model=model
            or os.getenv("VEILGRAPH_LLM_MODEL")
            or os.getenv("OPENROUTER_MODEL")
            or DEFAULT_MODEL
        )

    def available(self) -> bool:
        return bool(self.api_key)

    def complete(self, system: str, user: str, timeout: float = TIMEOUT) -> str:
        if not self.available():
            return json.dumps(
                _offline_payload({}, "sem VEILGRAPH_LLM_API_KEY configurada"),
                ensure_ascii=False,
            )
        try:
            from openai import OpenAI
        except ImportError:
            return json.dumps(
                _offline_payload({}, "SDK openai nao instalado (pip install openai)"),
                ensure_ascii=False,
            )
        try:
            client = OpenAI(api_key=self.api_key, base_url=self.base_url, timeout=timeout)
            resp = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": redact(user)},
                ],
                temperature=0.2,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            return json.dumps(
                _offline_payload({}, f"falha na chamada ({type(e).__name__})"),
                ensure_ascii=False,
            )


class AnthropicClient(LLMClient):
    """SDK oficial `anthropic` (Claude)."""

    def __init__(self, api_key: str | None = None, model: str | None = None,
                 base_url: str | None = None):
        self.api_key = (
            api_key
            or os.getenv("ANTHROPIC_API_KEY")
            or os.getenv("ANTHROPIC_AUTH_TOKEN")
            or ""
        )
        self.base_url = base_url or os.getenv("ANTHROPIC_BASE_URL") or None
        super().__init__(
            model=model or os.getenv("ANTHROPIC_MODEL") or DEFAULT_ANTHROPIC_MODEL
        )

    def available(self) -> bool:
        return bool(self.api_key)

    def complete(self, system: str, user: str, timeout: float = TIMEOUT) -> str:
        if not self.available():
            return json.dumps(
                _offline_payload({}, "sem ANTHROPIC_API_KEY configurada"),
                ensure_ascii=False,
            )
        try:
            from anthropic import Anthropic
        except ImportError:
            return json.dumps(
                _offline_payload({}, "SDK anthropic nao instalado (pip install anthropic)"),
                ensure_ascii=False,
            )
        try:
            kwargs: dict[str, Any] = {"api_key": self.api_key, "timeout": timeout}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            resp = Anthropic(**kwargs).messages.create(
                model=self.model,
                max_tokens=2048,
                system=system,
                messages=[{"role": "user", "content": redact(user)}],
            )
            return "".join(
                getattr(b, "text", "")
                for b in resp.content
                if getattr(b, "type", "") == "text"
            )
        except Exception as e:
            return json.dumps(
                _offline_payload({}, f"falha na chamada ({type(e).__name__})"),
                ensure_ascii=False,
            )


def get_client(prefer: str = "auto") -> LLMClient:
    """auto = anthropic se configurado, senao openai-compat, senao offline."""
    if prefer == "offline":
        return OfflineClient()

    if prefer in ("auto", "anthropic", "claude"):
        a = AnthropicClient()
        if a.available():
            return a
        if prefer != "auto":
            return OfflineClient("ANTHROPIC_API_KEY ausente")

    if prefer in ("auto", "api", "openai", "openrouter"):
        o = OpenAICompatClient()
        if o.available():
            return o
        if prefer != "auto":
            return OfflineClient("nenhuma chave de LLM configurada")

    return OfflineClient()


def build_prompt(result: dict[str, Any]) -> str:
    """Monta o prompt com apenas dados agregados do grafo."""
    slim = {
        "focus": result.get("focus"),
        "mode": result.get("mode"),
        "tx_count": result.get("tx_count", 0),
        "traceability_score": result.get("traceability_score"),
        "clusters": [
            {"size": len(c), "addresses": c[:8]} for c in (result.get("clusters") or [])
        ],
        "notes": result.get("notes") or [],
        "strategy": result.get("strategy"),
        "before_score": result.get("before_score"),
        "after_score": result.get("after_score"),
    }
    return json.dumps(slim, ensure_ascii=False)


def explain(result: dict[str, Any], prefer: str = "auto") -> dict | None:
    """Chama o LLM e devolve o bloco parseado (ou None se nao der)."""
    from .llm import get_client, build_prompt, SYSTEM_PROMPT
    import json

    client = get_client(prefer)
    raw = client.complete(SYSTEM_PROMPT, build_prompt(result))
    if not raw:
        return None
    try:
        start, end = raw.find("{"), raw.rfind("}")
        if start >= 0 and end > start:
            return json.loads(raw[start:end + 1])
    except Exception:
        pass
    return None
