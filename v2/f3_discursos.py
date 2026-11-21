"""F3a — catálogo de textos, discursos e apresentações da diretoria do BCB (2002 em diante).

Fonte: https://www.bcb.gov.br/acessoinformacao/discursos
  API: sitebcb/discursos?ano=AAAA (endpoint descoberto pelas chamadas da página em 21/11/2026).
  Cada item é um PDF; não há transcrição de entrevistas.

Só metadados aqui: data, título, autores, local, URL do PDF, e uma classificação por regra de
título (tipo e se o assunto é política monetária). O texto dos PDFs só é baixado se o
estudo de evento (f3_evento.py) mostrar que esses dias movem o DI.

Saída: v2/dados/discursos.csv
Uso:   .venv/bin/python -m v2.f3_discursos
"""

from __future__ import annotations

import re
from urllib.parse import quote

import pandas as pd

from v2 import fontes

SAIDA = fontes.RAIZ / "dados" / "discursos.csv"
BASE = "https://www.bcb.gov.br"

# Cargos ligados à decisão de juros. Regra de título, revisável.
RE_PRESIDENTE = re.compile(r"\bPresidente do Banco Central\b|\bPresidente do BC\b|\bPresidente\b", re.I)
RE_DIRPOL = re.compile(r"Diretor[a]? de Pol[ií]tica Econ[ôo]mica|Diretor[a]? de Pol[ií]tica Monet[áa]ria", re.I)
RE_MONETARIO = re.compile(
    r"pol[ií]tica monet[áa]ria|infla[çc][ãa]o|Relat[óo]rio de (Pol[ií]tica Monet[áa]ria|Infla[çc][ãa]o)|"
    r"Copom|juros|Selic|conjuntura|perspectivas|cen[áa]rio econ[ôo]mico|economia brasileira|Comiss[ãa]o de "
    r"Assuntos Econ[ôo]micos|CAE|audi[êe]ncia p[úu]blica", re.I)
RE_NAO_MONETARIO = re.compile(
    r"Estabilidade Financeira|\bPix\b|Drex|Open Finance|cidadania financeira|c[ée]dulas?|moeda comemorativa|"
    r"cooperativ|microcr[ée]dito|Relat[óo]rio de Economia Banc[áa]ria|regula[çc][ãa]o prudencial|Basileia", re.I)


def _baixar_ano(ano: int) -> list[dict]:
    return fontes._cache_json(
        f"discursos_{ano}.json",
        lambda: fontes._get(f"{fontes.SITEBCB.replace('/copom', '')}/discursos", {"ano": ano}).json()["conteudo"],
    )


def tipo(titulo: str) -> str:
    t = titulo.lower()
    for chave in ("discurso", "pronunciamento", "palestra", "apresenta", "entrevista", "texto", "artigo"):
        if chave in t:
            return {"apresenta": "apresentacao"}.get(chave, chave)
    return "outro"


def montar(ano_ini: int = 2002, ano_fim: int = 2026) -> pd.DataFrame:
    linhas = []
    for ano in range(ano_ini, ano_fim + 1):
        for it in _baixar_ano(ano):
            desc = re.sub(r"<br\s*/?>", "\n", it.get("descricao") or "")
            partes = [p.strip() for p in desc.split("\n") if p.strip()]
            url = it.get("Url") or (it.get("arquivo") or {}).get("ServerRelativeUrl") or ""
            titulo = (it.get("titulo") or "").strip()
            linhas.append({
                "id": it.get("Id"),
                # dataReferencia é a data do evento; DataPublicacao pode ser posterior (upload)
                "data": pd.to_datetime(it.get("dataReferencia")).tz_localize(None).normalize(),
                "data_publicacao": pd.to_datetime(it.get("DataPublicacao")).tz_localize(None).normalize(),
                "titulo": titulo,
                "autores": partes[0] if partes else "",
                "local": partes[1] if len(partes) > 1 else "",
                "url_pdf": BASE + quote(url) if url else "",
                "bytes": pd.to_numeric(it.get("Tamanho"), errors="coerce"),
                "tipo": tipo(titulo),
                "presidente": bool(RE_PRESIDENTE.search(titulo)),
                "dir_politica": bool(RE_DIRPOL.search(titulo)),
                "tema_monetario": bool(RE_MONETARIO.search(titulo)) and not RE_NAO_MONETARIO.search(titulo),
            })
    df = pd.DataFrame(linhas).sort_values("data").reset_index(drop=True)
    df["relevante"] = (df["presidente"] | df["dir_politica"]) & df["tema_monetario"]
    return df


if __name__ == "__main__":
    df = montar()
    df.to_csv(SAIDA, index=False)
    print(f"{len(df)} itens -> {SAIDA}")
    print(df.groupby(df["data"].dt.year).agg(itens=("id", "size"), relevantes=("relevante", "sum")).T.to_string())
    print("\ntipos:", df["tipo"].value_counts().to_dict())
    print("\ndefasagem publicação − evento (dias):",
          (df["data_publicacao"] - df["data"]).dt.days.describe()[["50%", "75%", "max"]].to_dict())
    print("\namostra de relevantes:")
    print(df[df["relevante"]].sample(8, random_state=1)[["data", "tipo", "titulo"]].to_string(index=False))
