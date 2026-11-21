"""F4 — o que move o DI entre a ata e a véspera: os dados divulgados pelo IBGE?

O DI acerta 72% dos passos no dia da ata anterior e 97% na véspera (F2). Os textos da
diretoria não movem a curva (F3). Aqui se testam as divulgações de dados.

Divulgações (calendário oficial do IBGE, servicodados v3/calendario, cobre 2017 em diante):
  IPCA 9256 · IPCA-15 9260 · PIB 9300 · PMC 9227 · PMS 9229 · PIM-PF 9294 · PNAD Contínua 9171
  O IBGE divulga às 9h, antes do pregão: a variação de 1 dia (fechamento de d − fechamento de d−1)
  captura a reação.

Três medidas:
  1. Estudo de evento: |Δ 1 dia| da taxa que cobre a próxima reunião, por tipo de divulgação,
     contra dias sem divulgação nem evento do Copom (permutação).
     2017 a set/2019: swap 60d do SGS; out/2019 em diante: DI1 da B3 (contrato da próxima reunião).
  2. Deriva entre reuniões (2019+): para a janela (ata t, corte t+1], variação total da Δ Selic
     implícita para t+1 (contrato fixo) e a soma das variações nos dias de divulgação.
  3. Surpresa do IPCA: IPCA divulgado (SGS 433) − mediana do Focus mensal na véspera, contra Δ do DI.

Uso: .venv/bin/python -m v2.f4_dados
"""

from __future__ import annotations

import json
import urllib.parse as up

import numpy as np
import pandas as pd

from v2 import fontes
from v2.f0_calendario import SAIDA as CAL
from v2.f1_di import DU, _du_entre, _escolhe_contrato, _proximo_du, _taxa_implicita, _vencimento_util
from v2.f3_evento import permutacao

PRODUTOS = {9256: "IPCA", 9260: "IPCA-15", 9300: "PIB", 9227: "PMC", 9229: "PMS",
            9294: "PIM", 9171: "PNAD"}
INI = pd.Timestamp("2017-01-02")
INI_B3 = pd.Timestamp("2019-10-01")
FIM_SGS = pd.Timestamp("2019-09-30")
IBGE_CAL = "https://servicodados.ibge.gov.br/api/v3/calendario/{id}?qtd=500"
OLINDA_MENSAL = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/ExpectativaMercadoMensais"
RES = fontes.RAIZ / "resultados"


# ------------------------------------------------------------------ calendário IBGE
def divulgacoes() -> pd.DataFrame:
    linhas = []
    for pid, nome in PRODUTOS.items():
        itens = fontes._cache_json(f"ibge_cal_{pid}.json", lambda pid=pid: fontes._get(IBGE_CAL.format(id=pid)).json()["items"])
        for it in itens:
            d = pd.to_datetime(it["data_divulgacao"], format="%d/%m/%Y %H:%M:%S").normalize()
            linhas.append({"data": d, "produto": nome,
                           "ref": f"{it['mes_referencia_inicio']:02d}/{it['ano_referencia_inicio']}"})
    df = pd.DataFrame(linhas)
    hoje = pd.Timestamp.today().normalize()
    return df[(df["data"] >= INI) & (df["data"] < hoje)].sort_values("data").reset_index(drop=True)


# ------------------------------------------------------------------ Copom
def copom():
    cal = pd.read_csv(CAL, parse_dates=["data_decisao", "data_ata", "data_corte"])
    cal["vig"] = cal["data_decisao"].map(_proximo_du)
    com = set(cal["data_decisao"]) | set(cal["vig"])
    ata = set(cal["data_ata"].dropna())
    return cal, com | ata


def contrato_do_dia(d: pd.Timestamp, vig: list) -> tuple:
    """(vigência da próxima reunião, da seguinte) vistas de d."""
    i = next((k for k, v in enumerate(vig) if v > d), None)
    if i is None:  # depois da última reunião do calendário
        return None, None
    return vig[i], (vig[i + 1] if i + 1 < len(vig) else None)


CDI = fontes.sgs(4389)


def implicito(taxa: float, d: pd.Timestamp, venc: pd.Timestamp, v1: pd.Timestamp) -> float:
    """Δ Selic implícita (pb) para a reunião com vigência v1, lida no fechamento de d.

    Usar a taxa bruta do contrato mistura informação com o efeito mecânico do tempo: a cada
    dia sai da conta um dia à taxa antiga e o contrato anda sozinho em direção à taxa nova.
    """
    cdi = CDI.get(d, np.nan)
    N, n1 = _du_entre(d, venc), _du_entre(d, v1)
    if np.isnan(cdi) or N <= n1:
        return np.nan
    return (_taxa_implicita(taxa, cdi, N, n1) - cdi) * 100


def var_1d(d: pd.Timestamp, vig: list, sw60: pd.Series, ticker: str | None = None) -> tuple[float, str]:
    """Δ 1 dia em pb. SGS (até set/2019): taxa do swap de 60 dias, prazo constante.
    B3: variação da Δ Selic implícita para a próxima reunião no contrato que a cobre
    (ou no `ticker` dado), já sem o efeito mecânico do tempo."""
    if d <= FIM_SGS:
        if d not in sw60.index:
            return np.nan, ""
        ant = DU[DU.searchsorted(d) - 1]
        return (sw60[d] - sw60.get(ant, np.nan)) * 100, "swap60"
    di = fontes.di1_dia(d.date())
    if di is None:
        return np.nan, ""
    if ticker is None:
        v1, v2 = contrato_do_dia(d, vig)
        if v1 is None:
            return np.nan, ""
        linha, _ = _escolhe_contrato(di, v1, v2)
        if linha is None:
            return np.nan, ""
    else:
        sel = di[di["ticker"] == ticker]
        if sel.empty:
            return np.nan, ""
        linha = sel.iloc[0]
    if pd.isna(linha["taxa_ant"]):
        return np.nan, linha["ticker"]
    v1, _ = contrato_do_dia(d, vig)
    venc = _vencimento_util(pd.Timestamp(linha["vencimento"]))
    ant = DU[DU.searchsorted(d) - 1]
    x = implicito(linha["taxa"], d, venc, v1) - implicito(linha["taxa_ant"], ant, venc, v1)
    return x, linha["ticker"]


# ------------------------------------------------------------------ 1. estudo de evento
def estudo_evento(div: pd.DataFrame, cal: pd.DataFrame, excl: set) -> pd.DataFrame:
    vig = cal["vig"].tolist()
    sw60 = fontes.sgs(fontes.SWAPS_SGS[60])
    dias_div = sorted(set(div["data"]) - excl)
    linhas = []
    for d in dias_div:
        x, tk = var_1d(d, vig, sw60)
        prods = "+".join(sorted(div.loc[div["data"] == d, "produto"]))
        linhas.append({"data": d, "grupo": prods, "var_pb": x, "contrato": tk})
        print(f"  {d.date()} {prods:14s} {x:+.1f}", flush=True)
    # controle: dias úteis já em cache (ou da série do SGS) sem divulgação nem Copom
    em_cache = {pd.Timestamp(p.stem) for p in (fontes.RAW / "di1").glob("*.csv")}
    cand = [d for d in DU[(DU >= INI) & (DU <= pd.Timestamp.today())]
            if d not in excl and d not in set(div["data"]) and (d <= FIM_SGS or d in em_cache)]
    for d in cand:
        x, tk = var_1d(d, vig, sw60)
        linhas.append({"data": d, "grupo": "sem_evento", "var_pb": x, "contrato": tk})
    return pd.DataFrame(linhas).dropna(subset=["var_pb"])


def resumo_evento(ev: pd.DataFrame) -> pd.DataFrame:
    ev = ev.copy()
    ev["abs"] = ev["var_pb"].abs()
    base = ev.loc[ev["grupo"] == "sem_evento", "abs"].values
    out = []
    # cada produto conta em todos os dias em que saiu (dias com dois produtos entram nos dois)
    for p in list(PRODUTOS.values()) + ["sem_evento"]:
        if p == "sem_evento":
            x = base
        else:
            x = ev.loc[ev["grupo"].str.split("+").map(lambda g: p in g), "abs"].values
        out.append({"grupo": p, "dias": len(x), "media_abs_pb": x.mean(), "p90_pb": np.percentile(x, 90),
                    "razao_vs_sem_evento": x.mean() / base.mean(),
                    "p_valor_perm": np.nan if p == "sem_evento" else permutacao(x, base)})
    return pd.DataFrame(out)


# ------------------------------------------------------------------ 2. deriva entre reuniões
def deriva(div: pd.DataFrame, cal: pd.DataFrame, excl: set) -> pd.DataFrame:
    vig = cal["vig"].tolist()
    sw60 = fontes.sgs(fontes.SWAPS_SGS[60])
    linhas = []
    for i in range(len(cal) - 2):
        t, t1 = cal.iloc[i], cal.iloc[i + 1]
        a, c = t["data_ata"], t1["data_corte"]
        if pd.isna(a) or a < INI_B3:
            continue
        da, dc = fontes.di1_dia(a.date()), fontes.di1_dia(c.date())
        if da is None or dc is None:
            continue
        linha, _ = _escolhe_contrato(da, t1["vig"], cal.iloc[i + 2]["vig"])
        if linha is None:
            continue
        tk = linha["ticker"]
        fim = dc.loc[dc["ticker"] == tk, "taxa"]
        if fim.empty:
            continue
        venc = _vencimento_util(pd.Timestamp(linha["vencimento"]))
        total = implicito(fim.iloc[0], c, venc, t1["vig"]) - implicito(linha["taxa"], a, venc, t1["vig"])
        janela = div[(div["data"] > a) & (div["data"] <= c) & ~div["data"].isin(excl)]
        por_prod = {p: 0.0 for p in PRODUTOS.values()}
        soma = 0.0
        for d in sorted(set(janela["data"])):
            x, _ = var_1d(d, vig, sw60, ticker=tk)
            if np.isnan(x):
                continue
            soma += x
            prods = janela.loc[janela["data"] == d, "produto"].tolist()
            for p in prods:  # dia com 2 produtos: divide igualmente
                por_prod[p] += x / len(prods)
        linhas.append({"reuniao_alvo": t1["nro_reuniao"], "data_ata": a.date(), "data_corte": c.date(),
                       "contrato": tk, "deriva_total_pb": total, "deriva_dias_dados_pb": soma,
                       "dias_dados": janela["data"].nunique(),
                       "dias_uteis_janela": int(DU.searchsorted(c, side="right") - DU.searchsorted(a, side="right")),
                       **{f"pb_{p}": v for p, v in por_prod.items()}})
        print(f"  {t1['nro_reuniao']} total={total:+.1f} dados={soma:+.1f}", flush=True)
    return pd.DataFrame(linhas)


# ------------------------------------------------------------------ 3. surpresa do IPCA
def focus_ipca_mes(ref: str, ate: pd.Timestamp) -> float | None:
    """Mediana do Focus para o IPCA do mês `ref` (MM/AAAA), última leitura antes de `ate`."""
    cache = fontes.RAW / "focus_ipca_mensal.json"
    memo = json.loads(cache.read_text()) if cache.exists() else {}
    k = f"{ref}|{ate.date()}"
    if k not in memo:
        f = (f"Indicador eq 'IPCA' and DataReferencia eq '{ref}' and Data lt '{ate.date()}' "
             f"and baseCalculo eq 0")
        q = up.urlencode({"$filter": f, "$orderby": "Data desc", "$top": 1, "$format": "json",
                          "$select": "Data,Mediana"}, quote_via=up.quote)
        v = fontes._get(f"{OLINDA_MENSAL}?{q}").json().get("value", [])
        memo[k] = v[0]["Mediana"] if v else None
        cache.write_text(json.dumps(memo))
    return memo[k]


def surpresa_ipca(div: pd.DataFrame, ev: pd.DataFrame) -> pd.DataFrame:
    ipca = fontes.sgs(433, inicio="2016-01-01")
    out = []
    for _, r in div[div["produto"] == "IPCA"].iterrows():
        mes = pd.Timestamp(f"{r['ref'][3:]}-{r['ref'][:2]}-01")
        if mes not in ipca.index:
            continue
        esp = focus_ipca_mes(r["ref"], r["data"])
        dv = ev.loc[ev["data"] == r["data"], "var_pb"]
        out.append({"data": r["data"], "ref": r["ref"], "ipca": ipca[mes], "focus": esp,
                    "surpresa_pp": None if esp is None else ipca[mes] - esp,
                    "var_di_pb": dv.iloc[0] if len(dv) else np.nan})
    return pd.DataFrame(out)


if __name__ == "__main__":
    import statsmodels.api as sm

    RES.mkdir(exist_ok=True)
    div = divulgacoes()
    cal, excl = copom()
    print(f"{len(div)} divulgações, {div['data'].nunique()} dias, {div['data'].min().date()}–{div['data'].max().date()}")

    ev = estudo_evento(div, cal, excl)
    ev.to_csv(fontes.RAIZ / "dados" / "evento_dados.csv", index=False)
    t1 = resumo_evento(ev)
    t1.to_csv(RES / "f4_evento_dados.csv", index=False)
    print("\n1. Estudo de evento (|Δ 1 dia|):\n" + t1.round(3).to_string(index=False))

    dr = deriva(div, cal, excl)
    dr.to_csv(RES / "f4_deriva.csv", index=False)
    m = sm.OLS(dr["deriva_total_pb"], sm.add_constant(dr["deriva_dias_dados_pb"])).fit(cov_type="HC1")
    print(f"\n2. Deriva ata→véspera (n={len(dr)}): R² da soma dos dias de dados = {m.rsquared:.2f}, "
          f"β = {m.params.iloc[1]:.2f} (ep {m.bse.iloc[1]:.2f})")
    print(f"   dias de dados = {dr['dias_dados'].sum() / dr['dias_uteis_janela'].sum():.0%} dos dias úteis; "
          f"soma |deriva nos dados| / soma |deriva total| = "
          f"{dr['deriva_dias_dados_pb'].abs().sum() / dr['deriva_total_pb'].abs().sum():.0%}")

    sp = surpresa_ipca(div, ev).dropna()
    sp.to_csv(RES / "f4_surpresa_ipca.csv", index=False)
    m2 = sm.OLS(sp["var_di_pb"], sm.add_constant(sp["surpresa_pp"])).fit(cov_type="HC1")
    print(f"\n3. Surpresa do IPCA (n={len(sp)}): Δ DI = {m2.params.iloc[0]:.2f} + {m2.params.iloc[1]:.1f}·surpresa(p.p.)"
          f"  [ep {m2.bse.iloc[1]:.1f}, p = {m2.pvalues.iloc[1]:.3f}, R² = {m2.rsquared:.2f}]")
