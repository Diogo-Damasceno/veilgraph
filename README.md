# VeilGraph

Analisador de grafo de transações on-chain + simulador de ofuscação de privacidade para EVM (Ethereum). **Read-only**: lê o histórico real de transações de um endereço (via Etherscan API) e roda heurísticas de análise de cadeia para medir o quão rastreável uma carteira é — e então sobrepõe um modelo de ofuscação (split_payment, fan_out, peeling) para mostrar o quanto cada estratégia *realmente* reduz a rastreabilidade e onde ela vaza.

> ⚠️ Ferramenta educacional/defensiva. Nenhuma transação é criada ou transmitida. O módulo de ofuscação é puramente um simulador sobre o grafo real.

## O que ele faz

- **Análise de grafo (`/analyze`)**: busca o histórico de um endereço e aplica 3 heurísticas clássicas de surveillance:
  - *Common-input / fan-in*: carteiras que financiam a mesma carteira com valores que somam um pagamento posterior são ligadas como mesmo dono.
  - *Round-trip / change-address*: fluxos A→B e B→A indicam mesmo dono.
  - *Score de rastreabilidade* (0 = rastro quebrado, 100 = trivialmente rastreável).
- **Simulador de ofuscação (`/obfuscate`)**: modelo dual-view. Mostra o grafo real, depois o grafo "ofuscado" e o novo score — evidenciando por que `split_payment` quebra a aresta direta mas vaza por correlação de valor.

## Stack

Python 3.11+, FastAPI, networkx, httpx, vis-network (UI). Sem banco de dados.

## Uso local

```bash
pip install -e ".[dev]"
# opcional: habilita dados reais da Ethereum
export VEILGRAPH_ETHERSCAN_API_KEY=sua_key_gratuita
uvicorn veilgraph.api:app --host 0.0.0.0 --port 8000
# abra http://localhost:8000
```

Sem a API key, o modo cai automaticamente para **synthetic** (histórico fake determinístico, 100% offline).

CLI:

```bash
veilgraph analyze 0x... --api-key SUAKEY
veilgraph obfuscate 0x... --strategy split_payment --fan-out 3
```

## Testes

```bash
pytest
```

## Deploy (Docker / Render / Railway)

```bash
docker build -t veilgraph .
docker run -p 8000:8000 -e VEILGRAPH_ETHERSCAN_API_KEY=... veilgraph
```

No Render/Railway: aponte o build para este repo e o start command é `uvicorn veilgraph.api:app --host 0.0.0.0 --port $PORT`.

## Estrutura

```
src/veilgraph/
  fetcher.py    leitura (live Etherscan) + modo synthetic
  analysis.py   heurísticas de clusterização e scoring
  obfuscate.py  simulador de estratégias de privacidade
  graph.py      montagem de nodes/edges p/ a UI
  api.py        endpoints FastAPI
  cli.py        interface de linha de comando
static/index.html   UI (vis-network)
tests/          testes (sem rede)
```

## Licença

MIT
