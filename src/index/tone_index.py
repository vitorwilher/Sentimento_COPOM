"""Índice de Tom — agrega os scores dos três LLMs em uma série interpretável.

O paper calibra o tom na variação da Selic (OLS por modelo); para o MVP da API,
a agregação essencial é o **ensemble** (média dos provedores por reunião) e sua
padronização em **z-score** na amostra — a mesma leitura "esta ata é quão mais
hawkish/dovish que a média histórica?" que interessa à mesa. A calibração OLS na
Selic fica como próximo passo, reusando `selic_cache.json`.
"""

from __future__ import annotations

from statistics import mean, pstdev

from core.schemas import PontoIndice, ScoreProvedor, ScoreReuniao, SerieIndice
from core import config
from data import repo
from index import calibra


def scores_por_reuniao(nro: int) -> ScoreReuniao | None:
    """Consolida os scores dos provedores para uma reunião (com ensemble)."""
    por_provedor = repo.carregar_scores()
    linhas: list[ScoreProvedor] = []
    for prov in config.PROVEDORES:
        score = por_provedor.get(prov, {}).get(nro)
        if score is None:
            continue
        linhas.append(ScoreProvedor(provedor=prov, modelo=config.MODELOS[prov], score=score))
    if not linhas:
        return None
    return ScoreReuniao(
        nro_reuniao=nro,
        data=repo.data_da_reuniao(nro),
        scores=linhas,
        ensemble=mean(s.score for s in linhas),
    )


def _ensemble_por_reuniao() -> dict[int, float]:
    """`{nro: ensemble}` para toda reunião com ao menos um score."""
    por_provedor = repo.carregar_scores()
    ensemble: dict[int, float] = {}
    for nro in repo.reunioes_disponiveis():
        vals = [s[nro] for s in por_provedor.values() if nro in s]
        if vals:
            ensemble[nro] = mean(vals)
    return ensemble


def serie_indice() -> SerieIndice:
    """Série completa do Índice de Tom (ensemble + z-score na amostra)."""
    ensemble = _ensemble_por_reuniao()
    nros = sorted(ensemble)
    vals = [ensemble[n] for n in nros]

    mu = mean(vals) if vals else 0.0
    sigma = pstdev(vals) if len(vals) > 1 else 0.0

    # Reta OLS do ensemble, calibrada uma vez para toda a série (p.p. de Selic).
    cal = calibra.calibrar_ensemble()

    pontos = [
        PontoIndice(
            nro_reuniao=n,
            data=repo.data_da_reuniao(n),
            ensemble=ensemble[n],
            zscore=(ensemble[n] - mu) / sigma if sigma else 0.0,
            selic_equivalente_pp=round(cal["alpha"] + cal["beta"] * ensemble[n], 3),
        )
        for n in nros
    ]
    return SerieIndice(n=len(pontos), media=mu, desvio=sigma, pontos=pontos)
