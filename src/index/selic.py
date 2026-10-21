"""Ponte ata → variação da Selic — replica `selic_na_reuniao` do paper.

Lê o cache `selic_cache.json` (série diária SGS 432, formato `dd/mm/aaaa` +
`valor` string) e, dada a data de uma reunião, devolve a variação da meta Selic
associada, numa janela de ±10 dias — exatamente a regra do paper. É a variável
dependente da calibração OLS.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from functools import lru_cache

from core import config


@lru_cache(maxsize=1)
def _serie_selic() -> list[tuple[datetime, float]]:
    """Série `(data, valor)` ordenada por data, sem duplicatas."""
    if not config.SELIC_CACHE.exists():
        return []
    bruto = json.loads(config.SELIC_CACHE.read_text(encoding="utf-8"))
    vistos: set[str] = set()
    serie: list[tuple[datetime, float]] = []
    for d in bruto:
        if d["data"] in vistos:
            continue
        vistos.add(d["data"])
        serie.append((datetime.strptime(d["data"], "%d/%m/%Y"), float(d["valor"])))
    serie.sort(key=lambda x: x[0])
    return serie


def variacao_na_reuniao(data_ata: str) -> float:
    """Variação da Selic (p.p.) na reunião da ata; 0.0 se manteve.

    Janela de ±10 dias ao redor da data de referência, primeira variação
    não-nula — idêntico a `selic_na_reuniao` do paper.
    """
    serie = _serie_selic()
    if not serie or not data_ata:
        return 0.0
    alvo = datetime.strptime(data_ata[:10], "%Y-%m-%d")
    ini, fim = alvo - timedelta(days=10), alvo + timedelta(days=10)

    valores = [(dt, val) for dt, val in serie if ini <= dt <= fim]
    for i in range(1, len(valores)):
        delta = round(valores[i][1] - valores[i - 1][1], 4)
        if abs(delta) > 0.01:
            return float(delta)
    return 0.0


def invalidar_cache() -> None:
    """Descarta a série em memória — chamado após atualização da Selic."""
    _serie_selic.cache_clear()
