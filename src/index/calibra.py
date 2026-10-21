"""Calibração OLS por modelo — traduz o score de tom em p.p. de Selic.

Replica o exercício central do paper::

    ΔSelic_t = α + β·Score_t + ε_t

estimado por OLS **para cada provedor** (e para o ensemble). O β̂ é a
sensibilidade: quantos pontos percentuais de Selic cada unidade de score
representa. É o número que transforma o índice qualitativo na leitura que a mesa
quer — "este tom equivale a quantos p.p. de Selic?".

OLS via numpy (mínimos quadrados fechados), sem `statsmodels`: o MVP entrega
α̂, β̂ e R². Erros-padrão, IC e as três camadas de validação do paper ficam
como próximo passo (ver README).
"""

from __future__ import annotations

from statistics import mean

import numpy as np

from core import config
from data import repo
from index import selic


def _ols(x: list[float], y: list[float]) -> dict:
    """OLS simples y = α + β·x. Retorna α, β, R² e n."""
    n = len(x)
    if n < 2:
        return {"alpha": 0.0, "beta": 0.0, "r2": 0.0, "n": n}
    xa, ya = np.asarray(x, float), np.asarray(y, float)
    beta, alpha = np.polyfit(xa, ya, 1)
    y_hat = alpha + beta * xa
    ss_res = float(np.sum((ya - y_hat) ** 2))
    ss_tot = float(np.sum((ya - ya.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return {"alpha": float(alpha), "beta": float(beta), "r2": r2, "n": n}


def _pares_score_selic(scores: dict[int, float]) -> tuple[list[float], list[float]]:
    """Alinha `{nro: score}` com a ΔSelic da reunião correspondente."""
    xs, ys = [], []
    for nro, score in scores.items():
        data = repo.data_da_reuniao(nro)
        if not data:
            continue
        xs.append(score)
        ys.append(selic.variacao_na_reuniao(data))
    return xs, ys


def calibrar_modelo(provedor: str) -> dict | None:
    """Calibra ΔSelic ~ score para um provedor. None se sem dados."""
    scores = repo.carregar_scores().get(provedor)
    if not scores:
        return None
    x, y = _pares_score_selic(scores)
    return {"provedor": provedor, "modelo": config.MODELOS[provedor], **_ols(x, y)}


def calibrar_ensemble() -> dict:
    """Calibra ΔSelic ~ ensemble (média dos provedores por reunião)."""
    por_provedor = repo.carregar_scores()
    ensemble: dict[int, float] = {}
    for nro in repo.reunioes_disponiveis():
        vals = [s[nro] for s in por_provedor.values() if nro in s]
        if vals:
            ensemble[nro] = mean(vals)
    x, y = _pares_score_selic(ensemble)
    return {"provedor": "ensemble", "modelo": "média dos 3", **_ols(x, y)}


def calibragem_completa() -> list[dict]:
    """Calibração de cada provedor + ensemble, para o endpoint /calibragem."""
    linhas = [calibrar_modelo(p) for p in config.PROVEDORES]
    linhas = [l for l in linhas if l is not None]
    linhas.append(calibrar_ensemble())
    return linhas


def selic_equivalente(score_ensemble: float) -> float:
    """Converte um score ensemble em p.p. de Selic via a reta do ensemble."""
    cal = calibrar_ensemble()
    return round(cal["alpha"] + cal["beta"] * score_ensemble, 3)
