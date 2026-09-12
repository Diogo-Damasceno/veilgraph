"""Testes do adaptador de LLM do VeilGraph.

Nenhum teste faz chamada de rede: o SDK openai e substituido por
monkeypatch e as chaves sao removidas do ambiente.
"""

import json
import sys
import types

import pytest

from veilgraph import llm


@pytest.fixture(autouse=True)
def _env_limpo(monkeypatch):
    for v in ("VEILGRAPH_LLM_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY",
              "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "VEILGRAPH_LLM_BASE_URL",
              "VEILGRAPH_LLM_MODEL", "ANTHROPIC_MODEL", "LLM_API_BASE"):
        monkeypatch.delenv(v, raising=False)


def test_redact_corta_valor_do_segredo():
    out = llm.redact("api_key=SUPERSEGREDO123")
    assert "SUPERSEGREDO123" not in out
    assert "[REDACTED]" in out


def test_offline_devolve_bloco_com_tres_chaves():
    c = llm.OfflineClient()
    payload = json.dumps({
        "focus": "0xabc", "traceability_score": 92.0,
        "clusters": [["0xa", "0xb"]], "tx_count": 10,
    })
    out = json.loads(c.complete(llm.SYSTEM_PROMPT, payload))
    assert set(out) == {"resumo", "observacoes", "recomendacoes"}
    assert "92" in out["resumo"]
    assert out["observacoes"]


def test_offline_score_alto_recomenda_mais_hops():
    out = json.loads(llm.OfflineClient().complete(
        llm.SYSTEM_PROMPT,
        json.dumps({"traceability_score": 95.0, "clusters": [], "tx_count": 5}),
    ))
    assert any("distancia" in r for r in out["recomendacoes"])


def test_offline_sobrevive_a_json_invalido():
    out = json.loads(llm.OfflineClient().complete(llm.SYSTEM_PROMPT, "lixo"))
    assert set(out) == {"resumo", "observacoes", "recomendacoes"}


def test_offline_client_e_padrao_sem_chave():
    assert isinstance(llm.get_client("auto"), llm.OfflineClient)
    assert isinstance(llm.get_client("offline"), llm.OfflineClient)


def test_openai_client_com_chave_openrouter(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-teste")
    c = llm.OpenAICompatClient()
    assert c.available() is True
    assert c.base_url == "https://openrouter.ai/api/v1"
    assert c.model == "openai/gpt-4o-mini"


def test_anthropic_tem_prioridade_no_auto(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-teste")
    assert isinstance(llm.get_client("auto"), llm.AnthropicClient)


def test_auto_cai_para_openai_quando_so_openrouter(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-teste")
    assert isinstance(llm.get_client("auto"), llm.OpenAICompatClient)


class _Msg:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content):
        self.message = _Msg(content)


class _Resp:
    def __init__(self, content):
        self.choices = [_Choice(content)]


def _fake_openai_module(monkeypatch, registro):
    """Instala um modulo `openai` falso que grava as chamadas."""

    class FakeCompletions:
        def create(self, **kw):
            registro.update(kw)
            return _Resp('{"resumo":"ok","observacoes":[],"recomendacoes":[]}')

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class FakeOpenAI:
        def __init__(self, **kw):
            registro["init"] = kw

        @property
        def chat(self):
            return FakeChat()

    fake = types.ModuleType("openai")
    fake.OpenAI = FakeOpenAI          # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "openai", fake)


def test_chamada_openai_envia_modelo_e_system(monkeypatch):
    reg = {}
    _fake_openai_module(monkeypatch, reg)
    c = llm.OpenAICompatClient(api_key="sk-teste", model="deepseek/deepseek-r1")
    out = c.complete("sys", '{"focus":"0xabc"}')
    assert json.loads(out)["resumo"] == "ok"
    assert reg["model"] == "deepseek/deepseek-r1"
    assert reg["messages"][0]["role"] == "system"
    assert reg["init"]["base_url"] == "https://openrouter.ai/api/v1"


def test_chamada_openai_nao_vaza_segredo(monkeypatch):
    reg = {}
    _fake_openai_module(monkeypatch, reg)
    c = llm.OpenAICompatClient(api_key="sk-teste")
    c.complete("sys", '{"nota":"token: hunter2"}')
    assert "hunter2" not in json.dumps(reg)


def test_falha_de_rede_devolve_json_valido(monkeypatch):
    class FakeOpenAI:
        def __init__(self, **kw):
            pass

        @property
        def chat(self):
            raise RuntimeError("boom")

    fake = types.ModuleType("openai")
    fake.OpenAI = FakeOpenAI          # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "openai", fake)

    c = llm.OpenAICompatClient(api_key="sk-teste")
    out = json.loads(c.complete("sys", "{}"))
    assert "resumo" in out


def test_build_prompt_manda_apenas_agregados():
    res = {
        "focus": "0xabc",
        "mode": "synthetic",
        "tx_count": 7,
        "traceability_score": 65.0,
        "clusters": [["0x1", "0x2", "0x3"]],
        "notes": ["nota"],
    }
    out = json.loads(llm.build_prompt(res))
    assert out["tx_count"] == 7
    assert out["traceability_score"] == 65.0
    assert out["clusters"][0]["size"] == 3
    assert set(out["clusters"][0]) == {"size", "addresses"}


def test_explain_parseia_resposta_do_llm(monkeypatch):
    reg = {}
    _fake_openai_module(monkeypatch, reg)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-teste")
    res = {"focus": "0xabc", "traceability_score": 50.0, "clusters": [], "tx_count": 3}
    out = llm.explain(res, prefer="openai")
    assert out is not None
    assert out["resumo"] == "ok"


def test_explain_devolve_none_em_resposta_nao_json(monkeypatch):
    class FakeCompletions:
        def create(self, **kw):
            return _Resp("desculpe, nao entendi")

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class FakeOpenAI:
        def __init__(self, **kw):
            pass

        @property
        def chat(self):
            return FakeChat()

    fake = types.ModuleType("openai")
    fake.OpenAI = FakeOpenAI          # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "openai", fake)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-teste")

    assert llm.explain({"focus": "0xabc"}, prefer="openai") is None
