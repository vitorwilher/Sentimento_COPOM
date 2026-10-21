"""Escoragem de tom via três LLMs — extraído do `atualizar_indice.py`.

Reproduz EXATAMENTE a escoragem do paper: mesmo prompt calibrado, mesma escala
[-3, +3], mesma saída estruturada Pydantic via LangChain, temperature=0, cache
de prompt no Claude. É o **único** caminho da API que consome LLM/rede; só roda
no `POST /atualizar` e apenas para reuniões ainda não escoradas.

As dependências pesadas de LangChain são importadas dentro da função, de modo que
a API de leitura (o MVP) suba sem exigi-las instaladas.
"""

from __future__ import annotations

import time

import numpy as np
import pandas as pd

from core import config

INSTRUCOES_SISTEMA = """\
Você é um economista especializado em política monetária do Banco Central do Brasil.
Analise o tom de política monetária implícito no trecho de ata do Copom abaixo.

Retorne um score numérico de -3.0 a +3.0 seguindo rigorosamente esta escala:

  -3.0  Fortemente dovish: cortes grandes e imediatos são certeza;
         linguagem explicitamente acomodatícia; inflação muito benigna;
         expectativas ancoradas; grave deterioração da atividade.
  -2.0  Dovish: balanço de riscos assimétrico para baixo;
         desinflação clara; espaço explícito para cortes.
  -1.0  Levemente dovish: tom inclinado ao afrouxamento, mas com cautela;
         convergência da inflação em curso.
   0.0  Neutro / data-dependent: balanço simétrico; sem sinalização clara;
         linguagem condicional.
  +1.0  Levemente hawkish: atenção crescente à inflação;
         expectativas pressionadas; política deve permanecer contracionista.
  +2.0  Hawkish: inflação acima da meta com riscos altistas;
         expectativas desancoradas; altas sinalizadas.
  +3.0  Fortemente hawkish: inflação fora de controle; altas urgentes e certas;
         linguagem altamente restritiva.

Instruções:
- Avalie APENAS o tom implícito nas seções de diagnóstico e balanço de riscos.
- NÃO se baseie na decisão de taxa já anunciada na ata.
- Foque em: linguagem sobre inflação, ancoragem de expectativas,
  balanço de riscos e sinalização prospectiva (forward guidance).
- Use valores intermediários (ex: -1.5, +0.5) quando o tom for ambíguo.
- Seja consistente: atas com linguagem similar devem receber scores próximos.\
"""


def _montar_provedores():
    """Instancia os três clientes LLM (imports tardios: só quando se escora)."""
    from pydantic import BaseModel, Field
    from langchain_core.prompts import PromptTemplate
    from langchain_core.messages import SystemMessage, HumanMessage
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain_anthropic import ChatAnthropic
    from langchain_openai import ChatOpenAI

    class TomAta(BaseModel):
        score: float = Field(description=(
            "Score de tom de política monetária de -3.0 a +3.0. "
            "Negativo = dovish. Positivo = hawkish. Zero = neutro."))

    template = INSTRUCOES_SISTEMA + "\n\nTRECHO DA ATA:\n{DOCUMENTO}\n"
    prompt = PromptTemplate.from_template(template)

    gemini = prompt | ChatGoogleGenerativeAI(
        model=config.MODELOS["gemini"], temperature=0, max_retries=2
    ).with_structured_output(TomAta, method="json_schema")

    claude_llm = ChatAnthropic(model=config.MODELOS["claude"], temperature=0,
                               max_tokens=300, max_retries=6, timeout=60.0
                               ).with_structured_output(TomAta)

    def chamar_claude(documento: str):
        system_blocks = [{"type": "text", "text": INSTRUCOES_SISTEMA,
                          "cache_control": {"type": "ephemeral"}}]
        return claude_llm.invoke([SystemMessage(content=system_blocks),
                                  HumanMessage(content=f"TRECHO DA ATA:\n{documento}")])

    openai_chain = prompt | ChatOpenAI(model=config.MODELOS["openai"], temperature=0,
                                       max_retries=3, timeout=45.0
                                       ).with_structured_output(TomAta)

    return {
        "gemini": lambda txt: gemini.invoke({"DOCUMENTO": txt}),
        "claude": chamar_claude,
        "openai": lambda txt: openai_chain.invoke({"DOCUMENTO": txt}),
    }


def escorar_pendentes(atas: dict[int, dict], pendentes: dict[str, list[int]]) -> list[int]:
    """Escora reuniões pendentes por provedor e faz append nos CSVs de cache.

    Args:
        atas: `{nro: {"data", "texto"}}` do cache de atas.
        pendentes: `{provedor: [nros a escorar]}`.

    Returns:
        Lista ordenada de reuniões que passaram a ter ao menos um score novo.
    """
    provedores = _montar_provedores()
    escoradas: set[int] = set()

    for nome, chamar in provedores.items():
        alvo = pendentes.get(nome, [])
        if not alvo:
            continue
        caminho = config.score_cache(nome)
        df = pd.read_csv(caminho)
        linhas = []
        for nro in alvo:
            texto = atas[nro]["texto"]
            try:
                r = chamar(texto)
                score = float(np.clip(r.score, config.SCORE_MIN, config.SCORE_MAX))
                linhas.append({"nro_reuniao": nro, "score": score})
                escoradas.add(nro)
                print(f"  ✓ [{nome}] reunião {nro} | score: {score:+.2f}")
            except Exception as e:
                print(f"  ✗ [{nome}] reunião {nro} | {type(e).__name__}: {e}")
            time.sleep(0.6)
        if linhas:
            novas = pd.DataFrame(linhas)
            # gemini_cache tem coluna extra 'data' — preservar o schema do arquivo.
            if "data" in df.columns:
                novas["data"] = [atas[n]["data"] for n in novas["nro_reuniao"]]
            df = (pd.concat([df, novas[df.columns.tolist()]])
                  .drop_duplicates("nro_reuniao").sort_values("nro_reuniao"))
            df.to_csv(caminho, index=False)

    return sorted(escoradas)
