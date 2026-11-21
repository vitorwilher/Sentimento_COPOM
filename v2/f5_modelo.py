"""F5b — previsão no dia da ata: o comunicado acrescenta algo ao mercado seis semanas antes?

Unidade: reunião-alvo t+1. Informação: tudo o que existe no fechamento do dia da ata de t
(comunicado de t, ata de t, DI e Focus nesse dia).

Variáveis
  di_ata       Δ Selic implícita para t+1 no dia da ata de t
               B3 (ata ≥ out/2019): contrato que cobre só t+1; SGS (antes): swap de 60 dias corridos
  focus_ata    mediana do Focus para t+1 na última leitura até a ata − Selic vigente
  inercia      ΔSelic decidida em t
  com_sinal    sinal do comunicado de t para t+1, média dos 3 LLMs:
               direção (corte −1, manutenção 0, alta +1, indefinida 0) × magnitude (ou 25 pb se omitida)
  com_postura  postura média dos 3 LLMs (−3 … +3)
Alvos
  delta_t1     ΔSelic realizada em t+1 (pb)
  deriva       Δ implícita na véspera de t+1 (F1) − di_ata: para onde o mercado foi depois da ata

Testes
  1. Walk-forward (janela expansiva, treino mínimo de 40 reuniões), OLS e arredondamento a 25 pb:
     B0 di_ata arredondado · B1 OLS(di_ata) · M1 B1 + com_sinal · M2 M1 + com_postura + inercia
  2. Deriva: OLS com HAC, deriva ~ com_sinal + com_postura + (di_ata − com_sinal). O comunicado
     antecipa a correção do mercado?

Uso: .venv/bin/python -m v2.f5_modelo
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

from v2 import fontes
from v2.f0_calendario import SAIDA as CAL
from v2.f1_di import DU, _du_entre, _escolhe_contrato, _proximo_du, _taxa_implicita, _vencimento_util
from v2.f1_di import SAIDA as DI_VESPERA
from v2.f4_dados import implicito

INI_B3 = pd.Timestamp("2019-10-01")
RES = fontes.RAIZ / "resultados"
DIR = {"corte": -1, "manutencao": 0, "alta": 1, "indefinida": 0}


def di_no_dia(a: pd.Timestamp, vig1: pd.Timestamp, vig2: pd.Timestamp | None, cdi: pd.Series, sw60: pd.Series):
    """Δ Selic implícita (pb) para a reunião de vigência vig1, no fechamento de a."""
    if a >= INI_B3:
        di = fontes.di1_dia(a.date())
        if di is None:
            return np.nan, "sem_arquivo"
        linha, flag = _escolhe_contrato(di, vig1, vig2)
        if linha is None:
            return np.nan, flag
        return implicito(linha["taxa"], a, _vencimento_util(pd.Timestamp(linha["vencimento"])), vig1), flag
    if a not in sw60.index or a not in cdi.index:
        return np.nan, "sem_swap"
    fim = a + pd.Timedelta(days=60)
    N, n1 = _du_entre(a, fim), _du_entre(a, vig1)
    if N <= n1:
        return np.nan, "swap_curto"
    x = (_taxa_implicita(sw60[a], cdi[a], N, n1) - cdi[a]) * 100
    return x, ("swap60_cobre_2_reunioes" if vig2 is not None and vig2 < fim else "")


def leitura_comunicados() -> pd.DataFrame:
    partes = []
    for p in ("claude", "openai", "gemini"):
        arq = fontes.RAIZ / "dados" / f"leitura_comunicados_{p}.csv"
        if not arq.exists():
            continue
        d = pd.read_csv(arq)
        d["sinal"] = d["direcao_proxima"].map(DIR) * d["magnitude_pb"].fillna(25).abs()
        d["provedor"] = p
        partes.append(d[["nro_reuniao", "provedor", "sinal", "postura", "guidance_explicito", "condicionalidade"]])
    d = pd.concat(partes)
    m = d.groupby("nro_reuniao").agg(com_sinal=("sinal", "mean"), com_postura=("postura", "mean"),
                                     com_guidance=("guidance_explicito", "mean"),
                                     com_cond=("condicionalidade", "mean"), n_llm=("provedor", "nunique"))
    por = d.pivot_table(index="nro_reuniao", columns="provedor", values="sinal")
    por.columns = [f"sinal_{c}" for c in por.columns]
    return m.join(por).reset_index()


def montar() -> pd.DataFrame:
    cal = pd.read_csv(CAL, parse_dates=["data_decisao", "data_ata", "data_corte"])
    cal["vig"] = cal["data_decisao"].map(_proximo_du)
    cdi, sw60 = fontes.sgs(4389), fontes.sgs(fontes.SWAPS_SGS[60])
    vesp = pd.read_csv(DI_VESPERA)[["nro_reuniao", "delta_impl_pb"]].rename(columns={"delta_impl_pb": "di_vespera"})
    linhas = []
    for i in range(len(cal) - 1):
        t, t1 = cal.iloc[i], cal.iloc[i + 1]
        if pd.isna(t["data_ata"]) or pd.isna(t1["delta_pb"]):
            continue
        a = t["data_ata"]
        vig2 = cal.iloc[i + 2]["vig"] if i + 2 < len(cal) else None
        x, flag = di_no_dia(a, t1["vig"], vig2, cdi, sw60)
        f = fontes.focus_selic_reuniao(t1["rotulo_focus"], a)
        linhas.append({
            "nro_t": t["nro_reuniao"], "nro_t1": t1["nro_reuniao"], "data_ata": a,
            "inercia": t["delta_pb"], "delta_t1": t1["delta_pb"], "di_ata": x, "flag_di": flag,
            "focus_ata": (f["Mediana"] - t["selic_depois"]) * 100 if f else np.nan,
        })
    df = pd.DataFrame(linhas)
    df = df.merge(vesp, left_on="nro_t1", right_on="nro_reuniao", how="left").drop(columns="nro_reuniao")
    df["deriva"] = df["di_vespera"] - df["di_ata"]
    return df.merge(leitura_comunicados(), left_on="nro_t", right_on="nro_reuniao", how="left").drop(columns="nro_reuniao")


def passo(x):
    return np.round(np.asarray(x, float) / 25) * 25


def walk_forward(df: pd.DataFrame, specs: dict, min_treino: int = 40) -> pd.DataFrame:
    d = df.dropna(subset=["di_ata", "com_sinal", "delta_t1"]).sort_values("data_ata").reset_index(drop=True)
    prev = {k: [] for k in specs}
    for i in range(min_treino, len(d)):
        tr, te = d.iloc[:i], d.iloc[[i]]
        for k, cols in specs.items():
            if cols is None:
                prev[k].append(te["di_ata"].iloc[0])
                continue
            m = sm.OLS(tr["delta_t1"], sm.add_constant(tr[cols])).fit()
            prev[k].append(float(m.predict(sm.add_constant(te[cols], has_constant="add")).iloc[0]))
    y = d["delta_t1"].iloc[min_treino:].values
    vir = (np.sign(y) != np.sign(d["inercia"].iloc[min_treino:].values))
    out = []
    for k, p in prev.items():
        p = np.array(p)
        out.append({"modelo": k, "n": len(y),
                    "acerto_exato_%": 100 * (passo(p) == y).mean(),
                    "rmse_pb": float(np.sqrt(((p - y) ** 2).mean())),
                    "acerto_viradas_%": 100 * (passo(p)[vir] == y[vir]).mean(), "n_viradas": int(vir.sum())})
    return pd.DataFrame(out)


if __name__ == "__main__":
    RES.mkdir(exist_ok=True)
    df = montar()
    df.to_csv(fontes.RAIZ / "dados" / "base_dia_ata.csv", index=False)
    print(f"{len(df)} reuniões-alvo; com DI no dia da ata: {df['di_ata'].notna().sum()}; "
          f"com leitura do comunicado: {df['com_sinal'].notna().sum()}")

    specs = {"B0 DI no dia da ata": None, "B1 OLS(DI)": ["di_ata"],
             "M1 DI + comunicado": ["di_ata", "com_sinal"],
             "M2 M1 + postura + inércia": ["di_ata", "com_sinal", "com_postura", "inercia"]}
    wf = walk_forward(df, specs)
    wf.to_csv(RES / "f5_walk_forward.csv", index=False)
    print("\n1. Walk-forward (previsão no dia da ata):\n" + wf.round(1).to_string(index=False))

    d = df.dropna(subset=["deriva", "com_sinal", "di_ata"]).copy()
    d["com_menos_di"] = d["com_sinal"] - d["di_ata"]
    linhas = []
    for nome, cols in {"deriva ~ comunicado − DI": ["com_menos_di"],
                       "deriva ~ comunicado − DI + postura": ["com_menos_di", "com_postura"]}.items():
        m = sm.OLS(d["deriva"], sm.add_constant(d[cols])).fit(cov_type="HAC", cov_kwds={"maxlags": 2})
        for c in cols:
            linhas.append({"especificacao": nome, "variavel": c, "coef": m.params[c], "ep": m.bse[c],
                           "p": m.pvalues[c], "r2": m.rsquared, "n": int(m.nobs)})
    dr = pd.DataFrame(linhas)
    dr.to_csv(RES / "f5_deriva.csv", index=False)
    print("\n2. O comunicado antecipa a deriva do DI até a véspera?\n" + dr.round(3).to_string(index=False))
