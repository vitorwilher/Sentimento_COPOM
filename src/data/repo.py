"""Repositório de leitura — a fonte de verdade do MVP.

Lê os artefatos já produzidos pelo pipeline do paper (atas + scores dos três
LLMs + Selic) dos caches na raiz do projeto e os expõe como estruturas Python
limpas. **Não chama LLM nem rede** — é 100% offline e barato, o que faz a API
subir funcional lendo os scores que já foram gastos uma única vez.

Escrita (coleta de atas novas, nova escoragem) fica em `ingest/` e `scoring/`,
acionadas só pelo `POST /atualizar`.
"""

from __future__ import annotations

import csv
import json
from functools import lru_cache

from core import config


@lru_cache(maxsize=1)
def carregar_atas() -> dict[int, dict]:
    """Retorna `{nro_reuniao: {"data": ..., "texto": ...}}` do cache de atas."""
    if not config.ATAS_CACHE.exists():
        return {}
    bruto = json.loads(config.ATAS_CACHE.read_text(encoding="utf-8"))
    return {int(nro): doc for nro, doc in bruto.items()}


@lru_cache(maxsize=1)
def carregar_scores() -> dict[str, dict[int, float]]:
    """Lê os scores de cada provedor.

    Returns:
        `{provedor: {nro_reuniao: score}}`. Provedores sem CSV são omitidos.
        Tolera o schema extra do gemini (coluna `data`) lendo apenas as colunas
        `nro_reuniao` e `score`.
    """
    por_provedor: dict[str, dict[int, float]] = {}
    for prov in config.PROVEDORES:
        caminho = config.score_cache(prov)
        if not caminho.exists():
            continue
        scores: dict[int, float] = {}
        with caminho.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                scores[int(row["nro_reuniao"])] = float(row["score"])
        por_provedor[prov] = scores
    return por_provedor


def data_da_reuniao(nro: int) -> str | None:
    """Data (YYYY-MM-DD) de uma reunião, se a ata estiver em cache."""
    ata = carregar_atas().get(nro)
    return ata.get("data") if ata else None


def reunioes_disponiveis() -> list[int]:
    """Reuniões com ao menos um score, em ordem crescente."""
    nros: set[int] = set()
    for scores in carregar_scores().values():
        nros.update(scores)
    return sorted(nros)


def invalidar_cache() -> None:
    """Descarta os caches em memória — chamado após uma atualização."""
    carregar_atas.cache_clear()
    carregar_scores.cache_clear()
