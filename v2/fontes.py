"""Coleta das fontes da v2.0, com cache local em v2/dados/raw/.

Fontes (todas públicas, sem chave):
- BCB sitebcb: lista de comunicados e de atas do Copom (datas de decisão e de publicação).
- BCB SGS: 432 (meta Selic), 4389 (CDI anualizado base 252), 7801–7806 (swaps DI × pré).
- BCB Olinda: ExpectativasMercadoSelic (Focus, Selic por reunião).
- B3: arquivo diário de preços (PRyymmdd.zip, BVBG.086.01), só as linhas do DI1.

Cada chamada consulta o cache antes da rede. Apagar um arquivo em v2/dados/raw/ força a recoleta.
"""

from __future__ import annotations

import io
import json
import re
import time
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import urllib.parse as up

import requests

RAIZ = Path(__file__).resolve().parent
RAW = RAIZ / "dados" / "raw"
RAW.mkdir(parents=True, exist_ok=True)
(RAW / "di1").mkdir(exist_ok=True)

UA = {"User-Agent": "SentimentoCopom/2.0 (pesquisa academica)", "Accept": "application/json"}

SITEBCB = "https://www.bcb.gov.br/api/servico/sitebcb/copom"
SGS = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{cod}/dados"
OLINDA_SELIC = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/ExpectativasMercadoSelic"
B3_PR = "https://www.b3.com.br/pesquisapregao/download?filelist=PR{yymmdd}.zip"

# Swaps DI × pré do SGS, encerrados em 30/09/2019.
# EVIDÊNCIA: as séries 7801–7806 formam uma curva decrescente em 30/09/2019
#   (5,38 · 5,19 · 5,07 · 4,96 · 4,87 · 4,85) com CDI de 5,40 e corte de 50 pb esperado para 30/10.
# INTERPRETAÇÃO: prazos de 30, 60, 90, 120, 180 e 360 dias corridos.
# INCERTEZA: o SGS não devolve metadados pela API; o mapeamento é inferido.
# DECISÃO: usar o mapeamento e validá-lo contra o DI1 da B3 na sobreposição jan–set/2019 (f1_di.py).
SWAPS_SGS = {30: 7801, 60: 7802, 90: 7803, 120: 7804, 180: 7805, 360: 7806}


def _get(url: str, params: dict | None = None, tentativas: int = 4, **kw) -> requests.Response:
    for i in range(tentativas):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=60, **kw)
            if r.status_code == 200:
                return r
            if r.status_code == 404:
                return r
        except requests.RequestException:
            pass
        time.sleep(2 ** i)
    raise RuntimeError(f"falha ao baixar {url} {params}")


def _cache_json(nome: str, baixar):
    arq = RAW / nome
    if arq.exists():
        return json.loads(arq.read_text(encoding="utf-8"))
    dados = baixar()
    arq.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
    return dados


# ---------------------------------------------------------------- BCB: reuniões
def lista_comunicados(atualizar: bool = False) -> pd.DataFrame:
    if atualizar:
        (RAW / "comunicados_lista.json").unlink(missing_ok=True)
    d = _cache_json(
        "comunicados_lista.json",
        lambda: _get(f"{SITEBCB}/comunicados", {"quantidade": 2000}).json()["conteudo"],
    )
    df = pd.DataFrame(d).rename(columns={"nro_reuniao": "nro_reuniao", "dataReferencia": "data_decisao"})
    df["data_decisao"] = pd.to_datetime(df["data_decisao"])
    return df[["nro_reuniao", "data_decisao", "titulo"]]


def lista_atas(atualizar: bool = False) -> pd.DataFrame:
    if atualizar:
        (RAW / "atas_lista.json").unlink(missing_ok=True)
    d = _cache_json(
        "atas_lista.json",
        lambda: _get(f"{SITEBCB}/atas", {"quantidade": 2000}).json()["conteudo"],
    )
    df = pd.DataFrame(d).rename(
        columns={"nroReuniao": "nro_reuniao", "dataReferencia": "data_ref_ata", "dataPublicacao": "data_ata"}
    )
    for c in ("data_ref_ata", "data_ata"):
        df[c] = pd.to_datetime(df[c])
    return df[["nro_reuniao", "data_ref_ata", "data_ata"]]


# ---------------------------------------------------------------- BCB: SGS
def sgs(cod: int, inicio: str = "2004-01-01", fim: str | None = None, atualizar: bool = False) -> pd.Series:
    """Série diária do SGS. A API limita a 10 anos por chamada: baixa em blocos de 5 anos."""
    arq = RAW / f"sgs_{cod}.csv"
    if arq.exists() and not atualizar:
        s = pd.read_csv(arq, parse_dates=["data"]).set_index("data")["valor"]
        return s
    ini = pd.Timestamp(inicio)
    fim_ts = pd.Timestamp(fim) if fim else pd.Timestamp(date.today())
    partes = []
    while ini <= fim_ts:
        f = min(ini + pd.DateOffset(years=5) - pd.Timedelta(days=1), fim_ts)
        r = _get(
            SGS.format(cod=cod),
            {"formato": "json", "dataInicial": ini.strftime("%d/%m/%Y"), "dataFinal": f.strftime("%d/%m/%Y")},
        )
        if r.status_code == 200:
            partes.extend(r.json())
        ini = f + pd.Timedelta(days=1)
    df = pd.DataFrame(partes)
    df["data"] = pd.to_datetime(df["data"], format="%d/%m/%Y")
    df["valor"] = pd.to_numeric(df["valor"])
    df = df.drop_duplicates("data").sort_values("data")
    df.to_csv(arq, index=False)
    return df.set_index("data")["valor"]


# ---------------------------------------------------------------- Focus
def focus_selic_reuniao(rotulo: str, data_corte: pd.Timestamp) -> dict | None:
    """Última leitura do Focus (base de cálculo 0, todos os respondentes nos últimos 30 dias)
    para a reunião `rotulo` (ex.: 'R8/2026') com Data <= data_corte.

    Cobertura: reuniões de 2006 em diante (em 2005 o Focus já perguntava pelas de 2006)."""
    cache = RAW / "focus_selic.json"
    memo = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
    chave = f"{rotulo}|{data_corte.date()}"
    if chave in memo:
        return memo[chave]
    filtro = f"Reuniao eq '{rotulo}' and Data le '{data_corte.date()}' and baseCalculo eq 0"
    # O Olinda não aceita '+' como espaço no $filter: codifica com %20.
    q = up.urlencode(
        {"$filter": filtro, "$orderby": "Data desc", "$top": 1, "$format": "json",
         "$select": "Data,Reuniao,Media,Mediana,DesvioPadrao,Minimo,Maximo,numeroRespondentes"},
        quote_via=up.quote,
    )
    r = _get(f"{OLINDA_SELIC}?{q}")
    v = r.json().get("value", [])
    memo[chave] = v[0] if v else None
    cache.write_text(json.dumps(memo, ensure_ascii=False, indent=0), encoding="utf-8")
    return memo[chave]


# ---------------------------------------------------------------- B3: DI1
_RE_BLOCO = re.compile(r"<PricRpt>(.*?)</PricRpt>", re.S)
_RE_TAG = lambda t: re.compile(rf"<{t}[^>]*>([^<]*)</{t}>")  # noqa: E731
_TAGS = {k: _RE_TAG(k) for k in ("Dt", "TckrSymb", "AdjstdQtTax", "PrvsAdjstdQtTax", "OpnIntrst", "FinInstrmQty")}
_MESES = "FGHJKMNQUVXZ"  # códigos de vencimento B3: jan..dez


def _venc_di1(ticker: str) -> date:
    """DI1F27 -> 1º dia de jan/2027. O vencimento é o 1º dia útil; o ajuste para dia útil é feito em f1_di."""
    mes = _MESES.index(ticker[3]) + 1
    ano = 2000 + int(ticker[4:6])
    return date(ano, mes, 1)


def di1_dia(dia: date) -> pd.DataFrame | None:
    """Taxas de ajuste do DI1 num pregão: uma linha por vencimento.

    Grava só o recorte do DI1 em v2/dados/raw/di1/AAAA-MM-DD.csv; o zip e o XML (até ~500 MB
    descompactados) não ficam em disco. Retorna None se a B3 não tem arquivo para a data
    (feriado, fim de semana ou fora da janela histórica, que começa em 2019).
    """
    arq = RAW / "di1" / f"{dia.isoformat()}.csv"
    vazio = RAW / "di1" / f"{dia.isoformat()}.vazio"
    if arq.exists():
        return pd.read_csv(arq, parse_dates=["vencimento"])
    if vazio.exists():
        return None
    r = _get(B3_PR.format(yymmdd=dia.strftime("%y%m%d")))
    if r.status_code != 200 or len(r.content) < 1000:
        vazio.touch()
        return None
    # O zip externo traz um zip interno com os XML; tolera também XML direto no externo.
    z = zipfile.ZipFile(io.BytesIO(r.content))
    if not any(n.endswith(".xml") for n in z.namelist()):
        try:
            z = zipfile.ZipFile(io.BytesIO(z.read(z.namelist()[0])))
        except zipfile.BadZipFile:
            vazio.touch()
            return None
    # Há várias versões do relatório no mesmo dia; a de nome maior é a última publicada.
    xmls = sorted(n for n in z.namelist() if n.endswith(".xml"))
    texto = z.read(xmls[-1]).decode("utf-8", errors="replace")
    linhas = []
    for bloco in _RE_BLOCO.finditer(texto):
        b = bloco.group(1)
        if "<TckrSymb>DI1" not in b:
            continue
        reg = {k: (m.group(1) if (m := rx.search(b)) else None) for k, rx in _TAGS.items()}
        tk = reg["TckrSymb"]
        if not tk or len(tk) != 6 or reg["AdjstdQtTax"] is None:
            continue
        linhas.append({
            "data": reg["Dt"], "ticker": tk, "vencimento": _venc_di1(tk),
            "taxa": float(reg["AdjstdQtTax"]),
            "taxa_ant": float(reg["PrvsAdjstdQtTax"]) if reg["PrvsAdjstdQtTax"] else None,
            "contratos_abertos": float(reg["OpnIntrst"]) if reg["OpnIntrst"] else None,
        })
    if not linhas:
        vazio.touch()
        return None
    df = pd.DataFrame(linhas).sort_values("vencimento")
    df.to_csv(arq, index=False)
    return pd.read_csv(arq, parse_dates=["vencimento"])
