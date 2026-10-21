"""API do Sentimento COPOM — o Índice de Tom das atas servido como serviço.

Expõe, sobre os artefatos já produzidos pelo pipeline do paper, os endpoints:

    GET  /health              — liveness
    GET  /modelos             — provedores/modelos e cobertura de escoragem
    GET  /indice              — série do Índice de Tom (ensemble + z-score)
    GET  /score/{nro_reuniao} — scores por modelo + ensemble de uma reunião
    POST /atualizar           — coleta atas novas do BCB e as escora (LLM)

Os endpoints de leitura são **offline e baratos**: leem os caches (`atas_cache`,
`scores_*_cache`) — os 48 scores já escorados sobem funcionais no primeiro boot,
sem chave de API. Só o `POST /atualizar` toca rede/LLM.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException

from core import config
from core.schemas import (
    Calibragem,
    ModeloInfo,
    ScoreReuniao,
    SerieIndice,
    StatusAtualizacao,
)
from data import repo
from index import calibra, selic, tone_index
from obs.tracing import trace

app = FastAPI(
    title="Sentimento COPOM API",
    description="Índice de Tom hawkish-dovish das atas do Copom via ensemble de LLMs.",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict:
    """Liveness + prontidão de dados (quantas reuniões há em cache)."""
    return {"status": "ok", "reunioes": len(repo.reunioes_disponiveis())}


@app.get("/modelos", response_model=list[ModeloInfo])
def modelos() -> list[ModeloInfo]:
    """Provedores/modelos e quantas reuniões cada um escorou."""
    scores = repo.carregar_scores()
    return [
        ModeloInfo(
            provedor=prov,
            modelo=config.MODELOS[prov],
            reunioes_escoradas=len(scores.get(prov, {})),
        )
        for prov in config.PROVEDORES
    ]


@app.get("/indice", response_model=SerieIndice)
def indice() -> SerieIndice:
    """Série completa do Índice de Tom (ensemble bruto + z-score na amostra)."""
    with trace("GET /indice") as span:
        serie = tone_index.serie_indice()
        span.meta["n"] = serie.n
        return serie


@app.get("/calibragem", response_model=list[Calibragem])
def calibragem() -> list[Calibragem]:
    """Calibração OLS ΔSelic ~ score por modelo + ensemble (α̂, β̂, R²).

    O β̂ é a sensibilidade — quantos p.p. de Selic cada unidade de tom vale.
    """
    with trace("GET /calibragem"):
        return [Calibragem(**linha) for linha in calibra.calibragem_completa()]


@app.get("/score/{nro_reuniao}", response_model=ScoreReuniao)
def score(nro_reuniao: int) -> ScoreReuniao:
    """Scores por modelo + ensemble de uma reunião específica."""
    with trace("GET /score", nro=nro_reuniao):
        resultado = tone_index.scores_por_reuniao(nro_reuniao)
        if resultado is None:
            raise HTTPException(404, f"Sem scores para a reunião {nro_reuniao}.")
        return resultado


@app.post("/atualizar", response_model=StatusAtualizacao)
def atualizar() -> StatusAtualizacao:
    """Coleta atas novas do BCB e escora as pendentes nos três LLMs.

    Único endpoint que consome rede/LLM. Requer as chaves
    (GOOGLE_API_KEY, ANTHROPIC_API_KEY, OPENAI_API_KEY) no ambiente. Sem atas
    novas, é idempotente e barato.
    """
    from ingest import collector
    from scoring import scorer

    with trace("POST /atualizar") as span:
        atas_novas = collector.atualizar_atas()
        collector.atualizar_selic()
        repo.invalidar_cache()   # recarrega atas do disco antes de escorar
        selic.invalidar_cache()  # e a série Selic recém-atualizada

        atas = repo.carregar_atas()
        scores = repo.carregar_scores()
        pendentes = {
            prov: [n for n in atas if n not in scores.get(prov, {})]
            for prov in config.PROVEDORES
        }
        if not any(pendentes.values()):
            return StatusAtualizacao(
                atas_novas=atas_novas, reunioes_escoradas=[],
                detalhe="Nada a escorar — todas as atas já têm score nos três modelos.",
            )

        escoradas = scorer.escorar_pendentes(atas, pendentes)
        repo.invalidar_cache()
        span.meta["escoradas"] = len(escoradas)
        return StatusAtualizacao(
            atas_novas=atas_novas,
            reunioes_escoradas=escoradas,
            detalhe=f"{len(escoradas)} reunião(ões) escorada(s).",
        )
