"""F5a — leitura estruturada dos comunicados do Copom por três LLMs.

O comunicado é o único texto do BCB que move a curva (F3: 2,2× um dia comum). Cada comunicado
da reunião t é lido para dizer o que ele sinaliza sobre a reunião t+1, separando:

  postura               quão restritiva a política ESTÁ (−3 muito expansionista … +3 muito restritiva)
  direcao_proxima       o que o texto sinaliza para a PRÓXIMA reunião: corte, manutenção, alta, indefinida
  magnitude_pb          tamanho sinalizado do próximo passo, se houver (múltiplo de 25), senão nulo
  guidance_explicito    o texto fala explicitamente das próximas reuniões?
  trecho_guidance       citação literal do trecho, ou vazio
  condicionalidade      0 = compromisso firme … 3 = totalmente dependente de dados

A separação entre postura e direção é a correção do ponto cego da v1.1 (que lia o nível do
aperto e não a direção nos cortes de 2026).

Vazamento: o LLM pode lembrar o que o Copom fez depois. Mitigação parcial: o prompt manda ler
só o texto, e o número e a data da reunião são retirados. Limitação declarada no paper; o
`trecho_guidance` (citação literal, verificável) é a parte menos exposta.

Modelos com versão fixa (corrige a ressalva da v1.1 sobre o alias do Gemini).

Saídas: v2/dados/raw/comunicados_texto.json, v2/dados/leitura_comunicados_{provedor}.csv
Uso:    .venv/bin/python -m v2.f5_comunicados [--teste] [--provedor claude|openai|gemini]
"""

from __future__ import annotations

import json
import re
import sys
import time
from typing import Literal, Optional

import pandas as pd
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from v2 import fontes
from v2.f0_calendario import SAIDA as CAL

load_dotenv(fontes.RAIZ.parent / ".env")

MODELOS = {
    "claude": "claude-haiku-4-5-20251001",
    "openai": "gpt-4.1-mini-2025-04-14",
    "gemini": "gemini-3.5-flash-lite",
}


class LeituraComunicado(BaseModel):
    postura: int = Field(ge=-3, le=3, description="Quão restritiva a política monetária está hoje, segundo o texto: −3 muito expansionista, 0 neutra, +3 muito restritiva.")
    direcao_proxima: Literal["corte", "manutencao", "alta", "indefinida"] = Field(description="O que o texto sinaliza para a PRÓXIMA reunião do Copom.")
    magnitude_pb: Optional[int] = Field(default=None, description="Tamanho do próximo passo sinalizado no texto, em pontos-base (múltiplo de 25). Nulo se o texto não indica tamanho.")
    guidance_explicito: bool = Field(description="O texto fala explicitamente das próximas reuniões ou dos próximos passos?")
    trecho_guidance: str = Field(description="Citação literal do trecho sobre os próximos passos; vazio se não houver.")
    condicionalidade: int = Field(ge=0, le=3, description="0 = compromisso firme com o próximo passo; 3 = próximo passo totalmente dependente de dados.")


SISTEMA = """Você é um economista que lê comunicados do Comitê de Política Monetária (Copom) do Banco Central do Brasil.
Leia APENAS o texto fornecido. Não use o que você sabe sobre decisões posteriores do Copom nem sobre a data do texto.
Separe duas coisas diferentes:
- a POSTURA: quão restritiva a política está agora (nível);
- a DIREÇÃO: o que o texto sinaliza para a PRÓXIMA reunião (movimento).
Uma política muito restritiva pode sinalizar corte; uma política expansionista pode sinalizar alta.
Se o texto não sinaliza nada sobre a próxima reunião, use direcao_proxima = "indefinida"."""


def _limpa(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for t in soup.find_all(["sup", "script", "style"]):
        t.decompose()
    txt = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    # retira identificadores de data e número da reunião
    txt = re.sub(r"\b\d{1,3}ª\s*reuni[ãa]o\b", "nesta reunião", txt, flags=re.I)
    return txt


def textos(nros: list[int]) -> dict[str, str]:
    arq = fontes.RAW / "comunicados_texto.json"
    memo = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {}
    for n in nros:
        if str(n) in memo:
            continue
        r = fontes._get(f"{fontes.SITEBCB}/comunicados_detalhes", {"nro_reuniao": n}).json()["conteudo"]
        memo[str(n)] = _limpa(r[0]["textoComunicado"]) if r else ""
        arq.write_text(json.dumps(memo, ensure_ascii=False, indent=0), encoding="utf-8")
    return memo


def _cadeia_base(provedor: str, max_tokens: int = 600):
    """O LLM do provedor, com versão fixa e temperature 0 (sem schema)."""
    if provedor == "claude":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=MODELOS["claude"], temperature=0, max_tokens=max_tokens, max_retries=3)
    if provedor == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=MODELOS["openai"], temperature=0, timeout=240, max_retries=3, max_tokens=max_tokens)
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(model=MODELOS["gemini"], temperature=0, max_retries=3)


def _cadeia(provedor: str):
    return _cadeia_base(provedor).with_structured_output(LeituraComunicado)


def ler(provedor: str, nros: list[int]) -> pd.DataFrame:
    arq = fontes.RAIZ / "dados" / f"leitura_comunicados_{provedor}.csv"
    feito = pd.read_csv(arq) if arq.exists() else pd.DataFrame(columns=["nro_reuniao"])
    txt = textos(nros)
    cadeia = _cadeia(provedor)
    novos = []
    for n in nros:
        if n in set(feito["nro_reuniao"]) or not txt.get(str(n)):
            continue
        if provedor == "gemini":
            time.sleep(4.5)  # plano gratuito do Gemini: 15 chamadas por minuto
        r: LeituraComunicado = cadeia.invoke([("system", SISTEMA), ("human", f"Comunicado:\n\n{txt[str(n)]}")])
        novos.append({"nro_reuniao": n, "modelo": MODELOS[provedor], **r.model_dump()})
        print(f"  {provedor} {n}: postura={r.postura:+d} dir={r.direcao_proxima} mag={r.magnitude_pb} "
              f"guid={r.guidance_explicito} cond={r.condicionalidade}", flush=True)
        # grava a cada chamada: uma falha no meio não faz pagar de novo
        pd.concat([feito, pd.DataFrame(novos)]).to_csv(arq, index=False)
    return pd.read_csv(arq)


if __name__ == "__main__":
    cal = pd.read_csv(CAL)
    nros = cal["nro_reuniao"].astype(int).tolist()
    if "--teste" in sys.argv:
        nros = [200, 249, 276, 277]  # 2016 início de cortes · 2022 fim de altas · 2026 pausa e 1º corte
    provs = [sys.argv[sys.argv.index("--provedor") + 1]] if "--provedor" in sys.argv else list(MODELOS)
    for p in provs:
        ler(p, nros)
