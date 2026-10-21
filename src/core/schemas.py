"""Contratos (Pydantic) das respostas da API.

Toda resposta pública passa por um destes modelos — a API nunca devolve um dict
solto. Isso mantém o contrato estável para clientes internos (mesa, dashboards)
e documenta o schema automaticamente no OpenAPI do FastAPI.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ScoreProvedor(BaseModel):
    """Score de tom de um único provedor para uma reunião."""

    provedor: str = Field(description="gemini | claude | openai")
    modelo: str = Field(description="Identificador do modelo LLM.")
    score: float = Field(description="Tom hawkish-dovish em [-3, +3].")


class ScoreReuniao(BaseModel):
    """Consolidado de uma reunião: score por modelo + ensemble."""

    nro_reuniao: int
    data: str | None = Field(default=None, description="Data da reunião (YYYY-MM-DD).")
    scores: list[ScoreProvedor]
    ensemble: float = Field(description="Média dos scores dos provedores disponíveis.")


class PontoIndice(BaseModel):
    """Um ponto da série do Índice de Tom."""

    nro_reuniao: int
    data: str | None = None
    ensemble: float = Field(description="Score de tom ensemble (bruto, [-3, +3]).")
    zscore: float = Field(description="Ensemble padronizado (z-score) na amostra.")
    selic_equivalente_pp: float = Field(
        description="Tom traduzido em p.p. de Selic pela reta OLS do ensemble."
    )


class Calibragem(BaseModel):
    """Resultado da calibração OLS de um modelo: ΔSelic = α + β·score."""

    provedor: str
    modelo: str
    alpha: float = Field(description="Intercepto α̂ (p.p.).")
    beta: float = Field(description="Sensibilidade β̂ (p.p. de Selic por unidade de score).")
    r2: float = Field(description="R² in-sample da regressão.")
    n: int = Field(description="Número de reuniões usadas na calibração.")


class SerieIndice(BaseModel):
    """Série completa do Índice de Tom + metadados de amostra."""

    n: int = Field(description="Número de reuniões na série.")
    media: float = Field(description="Média do ensemble na amostra.")
    desvio: float = Field(description="Desvio-padrão do ensemble na amostra.")
    pontos: list[PontoIndice]


class ModeloInfo(BaseModel):
    """Descrição de um provedor/modelo e cobertura de escoragem."""

    provedor: str
    modelo: str
    reunioes_escoradas: int


class StatusAtualizacao(BaseModel):
    """Resultado de `POST /atualizar`."""

    atas_novas: list[int]
    reunioes_escoradas: list[int]
    detalhe: str
