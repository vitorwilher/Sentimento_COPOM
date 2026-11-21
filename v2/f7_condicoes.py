"""F7a — a função de reação escrita em cada ata: a que o Copom diz que vai reagir?

A ata não promete um passo; descreve condições ("em ambiente de expectativas desancoradas,
exige-se uma restrição monetária maior"; "reagir com firmeza caso efeitos de segunda ordem se
materializem"). Cada condição é extraída numa lista FIXA de variáveis, para que cada uma tenha
uma série medível entre a ata e a reunião seguinte (f7_indice.py).

Para cada condição o LLM devolve:
  variavel   da lista fixa (VARIAVEIS)
  (o sinal de cada variável é teórico e fixo: SINAL)
  enfase     1 menção de passagem · 2 destaque · 3 condição central da decisão
  trecho     citação literal da ata (auditável)

Entrada: ata completa (todas as seções; corta a lista de presentes). Cache em
v2/dados/raw/atas_texto.json. Saída: v2/dados/condicoes_atas_{provedor}.csv (formato longo).

Uso: .venv/bin/python -m v2.f7_condicoes [--teste] [--provedor claude|openai]
"""

from __future__ import annotations

import json
import re
import sys
from typing import Literal

import pandas as pd
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from v2 import fontes
from v2.f0_calendario import SAIDA as CAL
from v2.f5_comunicados import MODELOS, _cadeia_base  # noqa: F401  (modelos com versão fixa)

# Variável → o que significa "subir" (a série correspondente está em f7_indice.SERIES)
VARIAVEIS = {
    "expectativas_curto": "expectativa de inflação do ano corrente e do seguinte (Focus) sobe",
    "expectativas_longo": "expectativa de inflação de prazos longos, 2 a 4 anos à frente (Focus), sobe: desancoragem",
    "inflacao_corrente": "IPCA acumulado em 12 meses sobe",
    "inflacao_servicos": "inflação de serviços sobe",
    "nucleos": "núcleos de inflação sobem",
    "atividade": "atividade econômica / hiato do produto sobe (economia mais aquecida)",
    "mercado_trabalho": "taxa de desemprego sobe (mercado de trabalho mais folgado)",
    "cambio": "taxa de câmbio R$/US$ sobe (real mais depreciado)",
    "petroleo": "preço do petróleo sobe",
    "fiscal": "resultado primário esperado do governo sobe (política fiscal mais contracionista)",
    "juros_externos": "juros dos EUA sobem / condições financeiras globais mais apertadas",
}

# Sinal teórico: +1 se a variável SUBIR pede política mais restritiva. Fixo, não perguntado ao LLM:
# no teste com 5 atas o Haiku inverteu o sinal de atividade e de mercado de trabalho ao ler riscos
# de baixa ("desaceleração mais acentuada"), que pela regra fixa continuam sinal +1 para atividade.
SINAL = {"expectativas_curto": 1, "expectativas_longo": 1, "inflacao_corrente": 1, "inflacao_servicos": 1,
         "nucleos": 1, "atividade": 1, "mercado_trabalho": -1, "cambio": 1, "petroleo": 1,
         "fiscal": -1, "juros_externos": 1}

Variavel = Literal[tuple(VARIAVEIS)]  # type: ignore[valid-type]


class Condicao(BaseModel):
    variavel: Variavel = Field(description="Variável da lista fixa a que a condição se refere.")
    enfase: Literal[1, 2, 3] = Field(description="1 menção de passagem; 2 destaque; 3 condição central para os próximos passos.")
    trecho: str = Field(max_length=400, description="Citação literal e curta da ata (até 300 caracteres) que sustenta a condição.")


class FuncaoReacao(BaseModel):
    condicoes: list[Condicao] = Field(description="Condições a que o Copom diz reagir nos próximos passos. Uma por variável.")


SISTEMA = """Você é um economista que lê atas do Comitê de Política Monetária (Copom) do Banco Central do Brasil.
Extraia a FUNÇÃO DE REAÇÃO escrita na ata: a que variáveis o Comitê diz que vai reagir nas próximas decisões, e em que sentido.
Use só o texto. Não use o que você sabe sobre decisões posteriores.
Variáveis permitidas e o que significa cada uma SUBIR:
{lista}
Regras:
- Inclua só variáveis que a ata liga aos próximos passos da política (condições, riscos que motivariam reação, o que o Comitê "monitora" para decidir).
- Descrição da conjuntura sem ligação com a decisão não conta.
- Riscos nos dois sentidos contam: "desaceleração mais acentuada da atividade" é uma condição sobre atividade.
- No máximo uma condição por variável; use a ênfase maior quando houver várias menções.
- O trecho deve ser cópia literal da ata."""


def _texto_ata(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for t in soup.find_all(["sup", "script", "style"]):
        t.decompose()
    txt = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    for corte in ("Informações da reunião", "Membros do Copom presentes", "Votaram por essa decisão"):
        i = txt.find(corte)
        if i > len(txt) * 0.5:
            txt = txt[:i]
            break
    return txt


def _texto_pdf(n: int, url: str) -> str:
    """Atas 200–231 (2016–2020) só existem em PDF no site do BCB: baixa e extrai com pdftotext."""
    import subprocess
    pasta = fontes.RAW / "atas_pdf"
    pasta.mkdir(exist_ok=True)
    arq = pasta / f"{n}.pdf"
    if not arq.exists():
        arq.write_bytes(fontes._get(url).content)
    txt = subprocess.run(["pdftotext", "-enc", "UTF-8", str(arq), "-"], capture_output=True, text=True).stdout
    txt = re.sub(r"\s+", " ", txt)
    for corte in ("Informações da reunião", "Membros do Copom presentes", "Votaram por essa decisão"):
        i = txt.find(corte)
        if i > len(txt) * 0.5:
            return txt[:i]
    return txt


def atas(nros: list[int]) -> dict[str, str]:
    arq = fontes.RAW / "atas_texto.json"
    memo = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else {}
    for n in nros:
        if str(n) in memo:
            continue
        r = fontes._get(f"{fontes.SITEBCB}/atas_detalhes", {"nro_reuniao": n}).json()["conteudo"]
        if r and r[0].get("textoAta"):
            memo[str(n)] = _texto_ata(r[0]["textoAta"])
        elif r and r[0].get("urlPdfAta"):
            memo[str(n)] = _texto_pdf(n, r[0]["urlPdfAta"])
        else:
            memo[str(n)] = ""
        arq.write_text(json.dumps(memo, ensure_ascii=False), encoding="utf-8")
    return memo


def extrair(provedor: str, nros: list[int]) -> pd.DataFrame:
    import time
    arq = fontes.RAIZ / "dados" / f"condicoes_atas_{provedor}.csv"
    feito = pd.read_csv(arq) if arq.exists() else pd.DataFrame(columns=["nro_reuniao"])
    txt = atas(nros)
    cadeia = _cadeia_base(provedor, max_tokens=2000).with_structured_output(FuncaoReacao)
    sistema = SISTEMA.format(lista="\n".join(f"- {k}: {v}" for k, v in VARIAVEIS.items()))
    linhas = feito.to_dict("records")
    for n in nros:
        if n in set(feito["nro_reuniao"]) or not txt.get(str(n)):
            continue
        if provedor == "gemini":
            time.sleep(4.5)
        try:
            r: FuncaoReacao = cadeia.invoke([("system", sistema), ("human", f"Ata:\n\n{txt[str(n)]}")])
        except Exception as e:  # registra e segue; a ata fica de fora desse provedor
            print(f"  {provedor} {n}: ERRO {type(e).__name__}", flush=True)
            continue
        if not r.condicoes:  # registra a ata sem condição, para não reprocessar
            linhas.append({"nro_reuniao": n, "modelo": MODELOS[provedor], "variavel": None})
        for c in r.condicoes:
            linhas.append({"nro_reuniao": n, "modelo": MODELOS[provedor], **c.model_dump(),
                           "sinal": SINAL[c.variavel]})
        print(f"  {provedor} {n}: " + ", ".join(f"{c.variavel}:{c.enfase}"
                                                  for c in r.condicoes), flush=True)
        pd.DataFrame(linhas).to_csv(arq, index=False)
    return pd.read_csv(arq)


if __name__ == "__main__":
    cal = pd.read_csv(CAL)
    nros = cal["nro_reuniao"].astype(int).tolist()
    if "--teste" in sys.argv:
        nros = [120, 200, 249, 276, 282]  # 2006 · 2016 · fim das altas 2022 · pausa jan/26 · nov/26
    provs = [sys.argv[sys.argv.index("--provedor") + 1]] if "--provedor" in sys.argv else ["claude", "openai"]
    for p in provs:
        extrair(p, nros)
