"""F7b — Índice de Condicionalidade: o BC disse que reagiria a X, e X mudou tanto.

Para cada reunião-alvo t+1:
  1. condições da ata de t (f7_condicoes.py): variáveis, ênfase (1–3) e sinal teórico fixo;
  2. variação de cada variável entre data_ata(t) e data_corte(t+1), só com dado publicado em cada data;
  3. padronização pelo desvio-padrão das variações nas janelas ANTERIORES (expansivo);
  4. índice = Σ sinal·ênfase·z / Σ ênfase   (ênfase média entre os LLMs; variável não citada = 0).
Controle: índice genérico, as mesmas 11 variáveis com peso 1 em todas as atas. Se o índice da ata
não superar o genérico, a leitura do texto não acrescenta nada aos dados.

Séries e ponto-no-tempo (defasagem de divulgação aproximada):
  expectativas_curto  Focus IPCA anual, média dos anos y e y+1 (y = ano da ata), última leitura ≤ data
  expectativas_longo  Focus IPCA anual, média de y+2 a y+4
  inflacao_corrente   IPCA 12 meses, SGS 13522 (mês m conhecido a partir do dia 12 de m+1)
  inflacao_servicos   IPCA serviços, SGS 10844, acumulado em 12 meses (idem)
  nucleos             núcleo IPCA-MS, SGS 4466, acumulado em 12 meses (idem)
  atividade           IBC-Br dessazonalizado, SGS 24364, variação em 12 meses (mês m conhecido em m+45 dias)
  mercado_trabalho    taxa de desocupação PNAD, SGS 24369 (m + 30 dias; a série começa em 2012)
  cambio              R$/US$, SGS 1, log×100
  petroleo            Brent, FRED DCOILBRENTEU, log×100
  fiscal              Focus resultado primário (% do PIB) do ano y
  juros_externos      Treasury 10 anos, FRED DGS10
INTERPRETAÇÃO: os códigos SGS 10844 (serviços) e 4466 (IPCA-MS) seguem a convenção conhecida do
SGS; a API não devolve metadados. A conferir contra a série de núcleos da casa.

Uso: .venv/bin/python -m v2.f7_indice
"""

from __future__ import annotations

import io
import urllib.parse as up

import numpy as np
import pandas as pd
import statsmodels.api as sm

from v2 import fontes
from v2.f0_calendario import SAIDA as CAL
from v2.f5_modelo import passo, walk_forward
from v2.f7_condicoes import SINAL, VARIAVEIS

RES = fontes.RAIZ / "resultados"
OLINDA_ANUAIS = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/ExpectativasMercadoAnuais"
MIN_JANELAS = 12  # janelas anteriores mínimas para padronizar


# ------------------------------------------------------------------ coleta
def focus_anual(indicador: str) -> pd.DataFrame:
    arq = fontes.RAW / f"focus_anual_{indicador.replace(' ', '_').lower()}.csv"
    if arq.exists():
        return pd.read_csv(arq, parse_dates=["Data"])
    partes, skip = [], 0
    while True:
        q = up.urlencode({"$filter": f"Indicador eq '{indicador}' and baseCalculo eq 0 and Data ge '2004-11-01'",
                          "$select": "Data,DataReferencia,Mediana", "$format": "json",
                          "$top": 20000, "$skip": skip, "$orderby": "Data"}, quote_via=up.quote)
        v = fontes._get(f"{OLINDA_ANUAIS}?{q}").json()["value"]
        partes += v
        if len(v) < 20000:
            break
        skip += 20000
    df = pd.DataFrame(partes)
    df["Data"] = pd.to_datetime(df["Data"])
    df["DataReferencia"] = df["DataReferencia"].astype(int)
    df.to_csv(arq, index=False)
    return df


def fred(serie: str) -> pd.Series:
    arq = fontes.RAW / f"fred_{serie}.csv"
    if not arq.exists():
        import requests  # o FRED recusa o Accept: application/json; se travar, baixar com curl para o cache
        r = requests.get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={serie}",
                         headers={"User-Agent": "SentimentoCopom/2.0"}, timeout=90)
        r.raise_for_status()
        arq.write_bytes(r.content)
    d = pd.read_csv(arq)
    d.columns = ["data", "valor"]
    d["data"] = pd.to_datetime(d["data"])
    d["valor"] = pd.to_numeric(d["valor"], errors="coerce")
    return d.dropna().set_index("data")["valor"]


def acum12(mensal: pd.Series) -> pd.Series:
    return ((1 + mensal / 100).rolling(12).apply(np.prod, raw=True) - 1) * 100


class Series:
    """Valor de cada variável conhecido numa data (ponto-no-tempo)."""

    def __init__(self):
        self.ipca = focus_anual("IPCA")
        self.prim = focus_anual("Resultado primário")
        self.mensais = {  # (série mensal indexada pelo mês de referência, defasagem em dias após o fim do mês)
            "inflacao_corrente": (fontes.sgs(13522, inicio="2003-01-01"), 12),
            "inflacao_servicos": (acum12(fontes.sgs(10844, inicio="2003-01-01")), 12),
            "nucleos": (acum12(fontes.sgs(4466, inicio="2003-01-01")), 12),
            "atividade": (fontes.sgs(24364, inicio="2003-01-01").pct_change(12) * 100, 45),
            "mercado_trabalho": (fontes.sgs(24369, inicio="2012-01-01"), 30),
        }
        self.diarias = {
            "cambio": np.log(fontes.sgs(1, inicio="2004-01-01")) * 100,
            "petroleo": np.log(fred("DCOILBRENTEU")) * 100,
            "juros_externos": fred("DGS10"),
        }

    def _focus(self, df, d, anos):
        x = df[(df["Data"] <= d) & df["DataReferencia"].isin(anos)]
        if x.empty:
            return np.nan
        ult = x[x["Data"] == x["Data"].max()]
        return ult["Mediana"].mean() if ult["DataReferencia"].nunique() == len(anos) else np.nan

    def valor(self, var: str, d: pd.Timestamp, y: int) -> float:
        if var == "expectativas_curto":
            return self._focus(self.ipca, d, [y, y + 1])
        if var == "expectativas_longo":
            return self._focus(self.ipca, d, [y + 2, y + 3, y + 4])
        if var == "fiscal":
            return self._focus(self.prim, d, [y])
        if var in self.mensais:
            s, lag = self.mensais[var]
            s = s.dropna()
            conhecido = s.index + pd.offsets.MonthEnd(0) + pd.Timedelta(days=lag) <= d
            return s[conhecido].iloc[-1] if conhecido.any() else np.nan
        s = self.diarias[var]
        s = s[s.index <= d]
        return s.iloc[-1] if len(s) else np.nan


# ------------------------------------------------------------------ montagem
def variacoes() -> pd.DataFrame:
    cal = pd.read_csv(CAL, parse_dates=["data_ata", "data_corte"])
    S = Series()
    linhas = []
    for i in range(len(cal) - 1):
        t, t1 = cal.iloc[i], cal.iloc[i + 1]
        if pd.isna(t["data_ata"]):
            continue
        a, c, y = t["data_ata"], t1["data_corte"], t["data_ata"].year
        linha = {"nro_t": int(t["nro_reuniao"]), "nro_t1": int(t1["nro_reuniao"]), "data_ata": a, "data_corte": c}
        for v in VARIAVEIS:
            linha[f"d_{v}"] = S.valor(v, c, y) - S.valor(v, a, y)
        linhas.append(linha)
    # leitura ao vivo: janela da ata da última reunião até o último dia útil com dado
    t = cal.iloc[-1]
    hoje = fontes.sgs(1).index.max()
    if not pd.isna(t["data_ata"]) and hoje > t["data_ata"]:
        y = t["data_ata"].year
        linha = {"nro_t": int(t["nro_reuniao"]), "nro_t1": int(t["nro_reuniao"]) + 1,
                 "data_ata": t["data_ata"], "data_corte": hoje}
        for v in VARIAVEIS:
            linha[f"d_{v}"] = S.valor(v, hoje, y) - S.valor(v, t["data_ata"], y)
        linhas.append(linha)
    return pd.DataFrame(linhas)


def padroniza(v: pd.DataFrame) -> pd.DataFrame:
    z = v.copy()
    for var in VARIAVEIS:
        x = v[f"d_{var}"]
        sd = x.expanding(MIN_JANELAS).std().shift(1)  # só janelas anteriores
        z[f"z_{var}"] = (x / sd).clip(-4, 4)
    return z


def pesos_atas() -> pd.DataFrame:
    partes = []
    for p in ("claude", "openai"):
        arq = fontes.RAIZ / "dados" / f"condicoes_atas_{p}.csv"
        if arq.exists():
            partes.append(pd.read_csv(arq).dropna(subset=["variavel"]))
    c = pd.concat(partes)
    # o mesmo modelo às vezes repete a variável na ata: fica a maior ênfase
    c = c.groupby(["nro_reuniao", "modelo", "variavel"], as_index=False)["enfase"].max()
    n_mod = c.groupby("nro_reuniao")["modelo"].nunique()
    w = c.pivot_table(index="nro_reuniao", columns="variavel", values="enfase", aggfunc="sum").fillna(0)
    w = w.div(n_mod, axis=0)  # ênfase média entre os LLMs (não citada = 0)
    return w.reindex(columns=list(VARIAVEIS), fill_value=0)


def indices(z: pd.DataFrame, w: pd.DataFrame) -> pd.DataFrame:
    out = z.copy()
    num_a, den_a, num_g, n_g = 0, 0, 0, 0
    for var in VARIAVEIS:
        zz = z[f"z_{var}"].fillna(0) * SINAL[var]
        ok = z[f"z_{var}"].notna().astype(float)
        wa = z["nro_t"].map(w[var]).fillna(0) * ok
        num_a, den_a = num_a + wa * zz, den_a + wa
        num_g, n_g = num_g + zz, n_g + ok
        out[f"contrib_{var}"] = wa * zz
    out["indice_ata"] = num_a / den_a.replace(0, np.nan)
    out["indice_generico"] = num_g / n_g.replace(0, np.nan)
    out.loc[:, [c for c in out if c.startswith("contrib_")]] = out[[c for c in out if c.startswith("contrib_")]].div(den_a.replace(0, np.nan), axis=0)
    return out


if __name__ == "__main__":
    RES.mkdir(exist_ok=True)
    v = variacoes()
    idx = indices(padroniza(v), pesos_atas())
    base = pd.read_csv(fontes.RAIZ / "dados" / "base_dia_ata.csv")
    df = idx.merge(base[["nro_t1", "di_ata", "delta_t1", "deriva", "inercia", "focus_ata", "com_sinal"]],
                   on="nro_t1", how="left")
    df.to_csv(fontes.RAIZ / "dados" / "indice_condicionalidade.csv", index=False)

    d = df.dropna(subset=["indice_ata", "indice_generico", "delta_t1", "di_ata", "deriva"])
    print(f"{len(d)} reuniões-alvo com índice ({int(d['nro_t1'].min())}–{int(d['nro_t1'].max())})\n")
    m = d["delta_t1"] != 0
    print("0. Correlações")
    for c in ["indice_ata", "indice_generico", "di_ata"]:
        print(f"   {c:16s} ΔSelic t+1 {d[c].corr(d['delta_t1']):+.2f} · deriva do DI {d[c].corr(d['deriva']):+.2f} · "
              f"ΔSelic t+1 − DI ata {d[c].corr(d['delta_t1'] - d['di_ata']):+.2f} · ΔSelic t {d[c].corr(d['inercia']):+.2f}")

    linhas = []
    for nome, cols in {"índice da ata": ["indice_ata"], "índice genérico": ["indice_generico"],
                       "ata + genérico": ["indice_ata", "indice_generico"],
                       "índice da ata + DI": ["indice_ata", "di_ata"]}.items():
        mm = sm.OLS(d["deriva"], sm.add_constant(d[cols])).fit(cov_type="HAC", cov_kwds={"maxlags": 2})
        for c in cols:
            linhas.append({"especificacao": nome, "variavel": c, "coef": mm.params[c], "ep": mm.bse[c],
                           "p": mm.pvalues[c], "r2": mm.rsquared, "n": int(mm.nobs)})
    dr = pd.DataFrame(linhas)
    dr.to_csv(RES / "f7_deriva.csv", index=False)
    print("\n1. O índice antecipa a deriva do DI (ata → véspera)?\n" + dr.round(3).to_string(index=False))

    wf = walk_forward(d.rename(columns={"nro_t1": "nro_t1"}).assign(data_ata=d["data_ata"]),
                      {"B0 DI no dia da ata": None, "B1 OLS(DI)": ["di_ata"],
                       "C1 DI + índice da ata": ["di_ata", "indice_ata"],
                       "C2 DI + índice genérico": ["di_ata", "indice_generico"]})
    wf.to_csv(RES / "f7_walk_forward.csv", index=False)
    print("\n2. Walk-forward (previsão no dia da ata):\n" + wf.round(1).to_string(index=False))

    viva = df[df["delta_t1"].isna()].tail(1)
    if len(viva):
        r = viva.iloc[0]
        print(f"\n3. Leitura ao vivo para a {int(r['nro_t1'])}ª: janela {r['data_ata'].date()} → {r['data_corte'].date()}")
        print(f"   índice da ata {r['indice_ata']:+.2f} · genérico {r['indice_generico']:+.2f}")
        for var in VARIAVEIS:
            print(f"   {var:20s} Δ {r[f'd_{var}']:+8.3f}  z {r[f'z_{var}']:+.2f}  contribuição {r[f'contrib_{var}']:+.2f}")
