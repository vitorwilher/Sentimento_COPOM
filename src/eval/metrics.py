"""Métricas de qualidade do scoring de tom — verdade = Selic realizada.

A "nota" de um modelo de tom não é dada por um juiz subjetivo: é o quanto o score
**prevê a variação da Selic que de fato ocorreu**. Três métricas, todas objetivas
e reprodutíveis a partir dos caches (score do LLM × ΔSelic da reunião):

- **R²**       — fração da variância da ΔSelic explicada pelo score (ajuste OLS).
- **RMSE**     — erro quadrático médio da ΔSelic prevista pela reta calibrada (p.p.).
- **Spearman** — correlação de posto entre score e ΔSelic: atas mais *hawkish*
  tendem a mais aperto? É a régua correta para um índice **contínuo** — mede
  associação monotônica sem forçar uma classificação artificial de direção.
  (Score é um *nível* de tom; ΔSelic é uma *mudança* de taxa — uma ata hawkish
  pode coexistir com Selic mantida, então "acerto de direção" por sinal cru
  mediria mal a qualidade do tom.)

Nenhuma métrica chama LLM — o eval é offline e barato, como o resto da leitura.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from statistics import mean

from core import config
from data import repo
from index import selic


@dataclass
class MetricasModelo:
    """Qualidade de um provedor (ou ensemble) contra a Selic realizada."""

    provedor: str
    modelo: str
    n: int
    r2: float
    rmse: float
    spearman: float  # correlação de posto score × ΔSelic, em [-1, 1]


def _spearman(x: np.ndarray, y: np.ndarray) -> float:
    """Correlação de Spearman = Pearson sobre os postos (sem scipy)."""
    if len(x) < 2:
        return 0.0
    rx = np.argsort(np.argsort(x)).astype(float)
    ry = np.argsort(np.argsort(y)).astype(float)
    sx, sy = rx.std(), ry.std()
    if sx == 0 or sy == 0:
        return 0.0
    return float(np.corrcoef(rx, ry)[0, 1])


def _pares(scores: dict[int, float]) -> tuple[list[float], list[float]]:
    """Alinha `{nro: score}` com a ΔSelic realizada da reunião."""
    xs, ys = [], []
    for nro, score in scores.items():
        data = repo.data_da_reuniao(nro)
        if not data:
            continue
        xs.append(score)
        ys.append(selic.variacao_na_reuniao(data))
    return xs, ys


def _avaliar(x: list[float], y: list[float]) -> tuple[float, float, float]:
    """Retorna (R², RMSE, Spearman) para pares score×ΔSelic."""
    n = len(x)
    if n < 2:
        return 0.0, 0.0, 0.0
    xa, ya = np.asarray(x, float), np.asarray(y, float)
    beta, alpha = np.polyfit(xa, ya, 1)
    y_hat = alpha + beta * xa

    ss_res = float(np.sum((ya - y_hat) ** 2))
    ss_tot = float(np.sum((ya - ya.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    rmse = float(np.sqrt(ss_res / n))
    return r2, rmse, _spearman(xa, ya)


def _ensemble_scores() -> dict[int, float]:
    """`{nro: média dos provedores}` por reunião."""
    por_provedor = repo.carregar_scores()
    ens: dict[int, float] = {}
    for nro in repo.reunioes_disponiveis():
        vals = [s[nro] for s in por_provedor.values() if nro in s]
        if vals:
            ens[nro] = mean(vals)
    return ens


def avaliar_todos() -> list[MetricasModelo]:
    """Métricas de cada provedor + ensemble contra a Selic realizada."""
    resultados: list[MetricasModelo] = []
    por_provedor = repo.carregar_scores()

    for prov in config.PROVEDORES:
        scores = por_provedor.get(prov)
        if not scores:
            continue
        x, y = _pares(scores)
        r2, rmse, sp = _avaliar(x, y)
        resultados.append(MetricasModelo(
            provedor=prov, modelo=config.MODELOS[prov],
            n=len(x), r2=r2, rmse=rmse, spearman=sp,
        ))

    x, y = _pares(_ensemble_scores())
    r2, rmse, sp = _avaliar(x, y)
    resultados.append(MetricasModelo(
        provedor="ensemble", modelo="média dos 3",
        n=len(x), r2=r2, rmse=rmse, spearman=sp,
    ))
    return resultados
