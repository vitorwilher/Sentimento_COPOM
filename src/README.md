# Sentimento COPOM — API

O **Índice de Tom** das atas do Copom servido como serviço HTTP (FastAPI +
Docker). A API é construída **sobre os artefatos já produzidos** pelo pipeline do
paper (`../atualizar_indice.py` + `../sentimento_copom_IA_base.qmd`): lê as atas e
os scores já escorados pelos três LLMs dos caches na raiz do projeto.

> **Por que sobe funcional no minuto zero:** os endpoints de leitura são
> offline — servem os 48 scores já calculados (`../scores_*_cache.csv`). Não
> precisam de chave de API nem chamam LLM. Só o `POST /atualizar` toca rede/LLM.

## Endpoints

| Método | Rota | O que faz | Toca LLM? |
|---|---|---|---|
| `GET` | `/health` | Liveness + nº de reuniões em cache | não |
| `GET` | `/modelos` | Provedores/modelos e cobertura de escoragem | não |
| `GET` | `/indice` | Série do Índice de Tom (ensemble + z-score + p.p. de Selic) | não |
| `GET` | `/calibragem` | Calibração OLS ΔSelic ~ score por modelo (α̂, β̂, R²) | não |
| `GET` | `/score/{nro_reuniao}` | Scores por modelo + ensemble de uma reunião | não |
| `POST` | `/atualizar` | Coleta atas novas do BCB e escora as pendentes | **sim** |

Documentação interativa automática em `/docs` (Swagger) e `/redoc`.

## Arquitetura

```
src/
├── app/main.py          # FastAPI — os 5 endpoints
├── core/config.py       # caminhos dos caches + constantes do domínio
├── core/schemas.py      # contratos Pydantic das respostas
├── data/repo.py         # LÊ os caches (fonte de verdade do MVP) — offline
├── index/tone_index.py  # ensemble dos 3 modelos + z-score na amostra
├── index/selic.py       # ponte ata → ΔSelic (janela ±10d) — replica o paper
├── index/calibra.py     # calibração OLS ΔSelic ~ score (α̂, β̂, R²)
├── ingest/collector.py  # coleta BCB (atas + Selic) — extraído do atualizar_indice.py
├── scoring/scorer.py    # escoragem via 3 LLMs — extraído do atualizar_indice.py
├── obs/tracing.py       # latência por request (observability)
└── tests/test_api.py    # 13 testes offline (endpoints, índice, calibração)
```

O código de coleta e escoragem é **o mesmo, byte-a-byte, do
`atualizar_indice.py`** já validado — apenas reorganizado como módulos
importáveis. A API não reimplementa o pipeline; ela o serve.

## Rodar localmente (sem Docker)

```bash
cd src
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

uvicorn app.main:app --reload --port 8000
# abra http://localhost:8000/docs
```

Só para `POST /atualizar`: `cp .env.example .env` e preencha as chaves.

## Testes

```bash
cd src && pytest -q     # 13 testes, todos offline (sem chave, sem rede)
```

## Rodar com Docker

A partir da **raiz do projeto** (o build precisa dos caches). Requer
Docker Compose **v2.24+** (usa `env_file: required: false`):

```bash
docker compose up --build
curl http://localhost:8000/indice
```

## Exemplos

```bash
curl http://localhost:8000/health
# {"status":"ok","reunioes":48}

curl http://localhost:8000/score/279
# {"nro_reuniao":279,"data":"2026-06-17","scores":[...],"ensemble":1.67}

curl -X POST http://localhost:8000/atualizar   # requer chaves no ambiente
```

## Próximos passos

1. **Calibração na Selic** — expor a série em p.p. de Selic (OLS por modelo,
   reusando `../selic_cache.json`), não só o z-score.
2. **Eval harness** — golden set de tom + gate de regressão (espelhando o
   COPOM_RAG_Service), para a escoragem não degradar entre execuções.
3. **Observability real** — somar tokens/custo no caminho de escoragem e exportar.
4. `POST /atualizar` **assíncrono** (background task) — hoje é síncrono.
