"""Observability leve — latência por request via context manager.

Espelha a postura do COPOM_RAG_Service: cada request pode ser envolvido em um
`trace(...)` que mede a latência e registra um evento estruturado. Tokens e custo
de LLM só existem no caminho de escoragem (`POST /atualizar`); os endpoints de
leitura são offline (latência de I/O local apenas).

TODO: emitir para backend real (OpenTelemetry / Prometheus) e somar tokens/custo
quando o scorer for acionado.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field

logger = logging.getLogger("sentimento_copom")


@dataclass
class Span:
    """Métricas de uma operação instrumentada."""

    nome: str
    latencia_ms: float = 0.0
    tokens: int = 0
    meta: dict = field(default_factory=dict)


@contextmanager
def trace(nome: str, **meta):
    """Mede a latência do bloco e loga um evento estruturado ao sair.

    Uso::

        with trace("GET /indice") as span:
            ...
            span.meta["n"] = len(pontos)
    """
    span = Span(nome=nome, meta=dict(meta))
    inicio = time.perf_counter()
    try:
        yield span
    finally:
        span.latencia_ms = (time.perf_counter() - inicio) * 1000.0
        logger.info(
            "trace nome=%s latencia_ms=%.1f tokens=%d meta=%s",
            span.nome, span.latencia_ms, span.tokens, span.meta,
        )
