"""Configuração central da API — caminhos dos caches e constantes do domínio.

A API do MVP é servida **sobre os artefatos já produzidos** pelo pipeline do
paper (`atualizar_indice.py` + `sentimento_copom_IA_base.qmd`): as atas coletadas
e os scores de tom já escorados pelos três LLMs vivem em arquivos de cache na
raiz do projeto. Este módulo resolve esses caminhos por posição relativa, de modo
que a API leia a **mesma fonte de verdade** do paper, sem duplicar dados.
"""

from __future__ import annotations

from pathlib import Path

# src/core/config.py -> src/ -> raiz do projeto (onde ficam os caches).
ROOT = Path(__file__).resolve().parents[2]

# Caches produzidos pelo pipeline do paper (ver atualizar_indice.py).
ATAS_CACHE = ROOT / "atas_cache.json"
SELIC_CACHE = ROOT / "selic_cache.json"

# Os três provedores escorados em paralelo. A ordem é a de referência do paper.
PROVEDORES: tuple[str, ...] = ("gemini", "claude", "openai")


def score_cache(provedor: str) -> Path:
    """Caminho do CSV de scores de um provedor (ex.: `scores_claude_cache.csv`)."""
    return ROOT / f"scores_{provedor}_cache.csv"


# Escala do score de tom (hawkish-dovish), idêntica à do prompt do paper.
SCORE_MIN = -3.0
SCORE_MAX = +3.0

# Série SGS 432 = meta Selic definida pelo Copom (usada na calibração do paper).
SGS_SELIC_META = 432

# Metadados dos modelos, para o endpoint /modelos e para a observability.
MODELOS = {
    "gemini": "gemini-flash-lite-latest",
    "claude": "claude-haiku-4-5",
    "openai": "gpt-4.1-mini",
}
