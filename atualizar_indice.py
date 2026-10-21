"""
Atualização incremental do Índice de Tom — atas novas do Copom (pós-release v1.0).

Replica EXATAMENTE o pipeline do sentimento_copom_IA_base.qmd (mesmo prompt,
mesmos modelos, temperature=0, saída estruturada Pydantic via LangChain), mas em
forma de script para escoragem incremental sem re-renderizar o paper:

  1. Descobre na API do BCB as atas publicadas após a última do cache local.
  2. Atualiza atas_cache.json (texto A+B) e selic_cache.json (SGS 432).
  3. Escora as atas novas nos três provedores e faz append nos
     scores_{gemini,claude,openai}_cache.csv.

Chaves: lidas do ambiente ou de um .env nesta pasta (GOOGLE_API_KEY,
ANTHROPIC_API_KEY, OPENAI_API_KEY). Sem chaves, roda só as etapas 1–2
(use --sem-llm para suprimir o aviso).

Uso:
    python atualizar_indice.py            # tudo
    python atualizar_indice.py --sem-llm  # só caches de atas e Selic
"""

import json
import os
import re
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

ROOT = Path(__file__).resolve().parent

BCB_LISTA   = "https://www.bcb.gov.br/api/servico/sitebcb/copom/atas"
BCB_DETALHE = "https://www.bcb.gov.br/api/servico/sitebcb/copom/atas_detalhes"
BCB_SELIC   = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados"
HEADERS     = {"Accept": "application/json", "User-Agent": "CopomToneIndex/2.0"}


# --------------------------------------------------------------------------- #
# Coleta de atas — idêntico ao paper (chunk "Coleta e preparação")
# --------------------------------------------------------------------------- #
def _html_para_texto(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["sup", "script", "style"]):
        tag.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True))


def _extrair_secoes_ab(texto: str, max_chars: int = 4_500) -> str:
    m_a = re.search(r"A\)\s*Atualiza", texto, re.IGNORECASE)
    m_c = re.search(r"C\)\s*(Discuss|Decis|Voto|Condu)", texto, re.IGNORECASE)
    if m_a:
        ini = m_a.start()
        fim = m_c.start() if m_c else ini + max_chars
        return texto[ini:fim][:max_chars]
    return texto[:max_chars]


def coletar_ata(nro_reuniao: int) -> dict | None:
    for tentativa in range(3):
        try:
            resp = requests.get(BCB_DETALHE, params={"nro_reuniao": nro_reuniao},
                                headers=HEADERS, timeout=30)
            resp.raise_for_status()
            item = resp.json()["conteudo"][0]
            texto = _html_para_texto(item.get("textoAta", ""))
            return {"data": item["dataReferencia"][:10],
                    "texto": _extrair_secoes_ab(texto)}
        except Exception as e:
            if tentativa < 2:
                time.sleep(2 ** tentativa)
            else:
                print(f"  [ERRO] Ata {nro_reuniao}: {e}")
                return None


def atas_publicadas() -> list[int]:
    resp = requests.get(BCB_LISTA, params={"quantidade": 12},
                        headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return sorted(item["nroReuniao"] for item in resp.json()["conteudo"])


def atualizar_atas() -> tuple[dict, list[int]]:
    cache_path = ROOT / "atas_cache.json"
    atas = json.loads(cache_path.read_text())
    ultimas = atas_publicadas()
    novas = [n for n in ultimas if str(n) not in atas]
    for nro in novas:
        doc = coletar_ata(nro)
        if doc:
            atas[str(nro)] = doc
            print(f"  + ata {nro} ({doc['data']}) — {len(doc['texto'])} chars")
    if novas:
        cache_path.write_text(json.dumps(atas, ensure_ascii=False))
    print(f"Atas: {len(novas)} nova(s); cache com {len(atas)} atas.")
    return atas, novas


def atualizar_selic() -> None:
    # A API SGS limita consultas JSON a 10 anos; buscamos em duas janelas.
    janelas = [("01/07/2016", "31/12/2021"), ("01/01/2022", None)]
    dados = []
    for ini, fim in janelas:
        params = {"formato": "json", "dataInicial": ini}
        if fim:
            params["dataFinal"] = fim
        resp = requests.get(BCB_SELIC, params=params, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        dados += resp.json()
    vistos = set()
    dados = [d for d in dados if not (d["data"] in vistos or vistos.add(d["data"]))]
    (ROOT / "selic_cache.json").write_text(json.dumps(dados, ensure_ascii=False))
    print(f"Selic: cache atualizado — {len(dados)} obs., última {dados[-1]['data']}.")


# --------------------------------------------------------------------------- #
# Escoragem LLM — idêntica ao paper (schema, prompt e modelos)
# --------------------------------------------------------------------------- #
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


def escorar_novas(atas: dict, pendentes_por_cache: dict[str, list[int]]) -> None:
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
        model="gemini-flash-lite-latest", temperature=0, max_retries=2
    ).with_structured_output(TomAta, method="json_schema")

    claude_llm = ChatAnthropic(model="claude-haiku-4-5", temperature=0,
                               max_tokens=300, max_retries=6, timeout=60.0
                               ).with_structured_output(TomAta)

    def chamar_claude(documento: str) -> TomAta:
        system_blocks = [{"type": "text", "text": INSTRUCOES_SISTEMA,
                          "cache_control": {"type": "ephemeral"}}]
        return claude_llm.invoke([SystemMessage(content=system_blocks),
                                  HumanMessage(content=f"TRECHO DA ATA:\n{documento}")])

    openai_chain = prompt | ChatOpenAI(model="gpt-4.1-mini", temperature=0,
                                       max_retries=3, timeout=45.0
                                       ).with_structured_output(TomAta)

    provedores = {
        "gemini": lambda txt: gemini.invoke({"DOCUMENTO": txt}),
        "claude": chamar_claude,
        "openai": lambda txt: openai_chain.invoke({"DOCUMENTO": txt}),
    }

    for nome, chamar in provedores.items():
        pendentes = pendentes_por_cache[nome]
        if not pendentes:
            print(f"[{nome}] nada a escorar.")
            continue
        cache_path = ROOT / f"scores_{nome}_cache.csv"
        df = pd.read_csv(cache_path)
        linhas = []
        for nro in pendentes:
            texto = atas[str(nro)]["texto"]
            try:
                r = chamar(texto)
                score = float(np.clip(r.score, -3.0, 3.0))
                linhas.append({"nro_reuniao": nro, "score": score})
                print(f"  ✓ [{nome}] reunião {nro} | score: {score:+.2f}")
            except Exception as e:
                print(f"  ✗ [{nome}] reunião {nro} | {type(e).__name__}: {e}")
            time.sleep(0.6)
        if linhas:
            novas = pd.DataFrame(linhas)
            # scores_gemini_cache.csv tem coluna extra 'data' — preservar schema
            if "data" in df.columns:
                novas["data"] = [atas[str(n)]["data"] for n in novas["nro_reuniao"]]
            df = (pd.concat([df, novas[df.columns.tolist()]])
                  .drop_duplicates("nro_reuniao").sort_values("nro_reuniao"))
            df.to_csv(cache_path, index=False)
            print(f"[{nome}] cache atualizado: +{len(linhas)}, total {len(df)}.")


def main() -> None:
    atas, _ = atualizar_atas()
    atualizar_selic()

    pendentes = {}
    for nome in ["gemini", "claude", "openai"]:
        df = pd.read_csv(ROOT / f"scores_{nome}_cache.csv")
        feitas = set(df["nro_reuniao"].astype(int))
        pendentes[nome] = sorted(int(n) for n in atas if int(n) not in feitas)
    todas_pendentes = sorted(set().union(*pendentes.values()))

    if "--sem-llm" in sys.argv:
        print(f"Pendentes de escoragem (não executado, --sem-llm): {todas_pendentes}")
        return
    if not todas_pendentes:
        print("Nenhuma ata pendente de escoragem.")
        return

    faltam = [k for k in ("GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY")
              if not os.getenv(k)]
    if faltam:
        sys.exit(f"Chaves ausentes: {', '.join(faltam)} — defina no ambiente ou "
                 f"num .env nesta pasta. Pendentes: {todas_pendentes}")

    escorar_novas(atas, pendentes)


if __name__ == "__main__":
    main()
