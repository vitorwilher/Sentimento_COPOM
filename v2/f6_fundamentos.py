"""F6 — os fundamentos dos modelos antecipam o que o DI ainda não precificou no dia da ata?

Insumos (contrato em docs/CONTRATO_EXPORTS.md; nada é recalculado aqui):
  ../MPP_BCB/exports/por_reuniao.csv      gap_taylor_pb, selic_taylor, theta3, ipca_proj_4t_desvio
  ../DSGE_Brasil/exports/por_reuniao.csv  aperto_pp, neutro, real_exante
  v2/dados/base_dia_ata.csv (F5)          di_ata, delta_t1, deriva, inercia, com_sinal

Testes (mesmos da F5, amostra comum onde o MPP tem valor: atas de jul/2008 em diante):
  1. Walk-forward, OLS + arredondamento a 25 pb, treino mínimo de 40 reuniões.
  2. Deriva do DI entre a ata e a véspera ~ fundamentos (HAC). Se o coeficiente for significativo,
     o mercado leva semanas para incorporar o que o modelo já dizia no dia da ata.
  3. Leitura ao vivo para a 283ª (dezembro/2026).

Uso: .venv/bin/python -m v2.f6_fundamentos
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

from v2 import fontes
from v2.f5_modelo import passo, walk_forward

PORTFOLIO = fontes.RAIZ.parents[1]
EXPORTS = {"mpp": PORTFOLIO / "MPP_BCB" / "exports" / "por_reuniao.csv",
           "dsge": PORTFOLIO / "DSGE_Brasil" / "exports" / "por_reuniao.csv"}
RES = fontes.RAIZ / "resultados"


def fundamentos() -> pd.DataFrame:
    partes = []
    for nome, arq in EXPORTS.items():
        d = pd.read_csv(arq)
        w = d.pivot_table(index="nro_reuniao_alvo", columns="variavel", values="valor")
        partes.append(w)
        print(f"{nome}: {arq.name}, vintage {d['vintage'].iloc[0]}")
    return pd.concat(partes, axis=1).reset_index().rename(columns={"nro_reuniao_alvo": "nro_t1"})


def montar() -> pd.DataFrame:
    base = pd.read_csv(fontes.RAIZ / "dados" / "base_dia_ata.csv", parse_dates=["data_ata"])
    return base.merge(fundamentos(), on="nro_t1", how="outer").sort_values("nro_t1")


if __name__ == "__main__":
    df = montar()
    df.to_csv(fontes.RAIZ / "dados" / "base_fundamentos.csv", index=False)
    amostra = df.dropna(subset=["di_ata", "delta_t1", "gap_taylor_pb", "aperto_pp", "com_sinal"])
    print(f"amostra comum: {len(amostra)} reuniões-alvo ({amostra['nro_t1'].min()}–{amostra['nro_t1'].max()})")

    # 0. Sozinhos: a direção do fundamento acerta a direção da decisão?
    print("\n0. Acerto da DIREÇÃO da decisão em t+1 (sinal), amostra comum:")
    y = np.sign(amostra["delta_t1"])
    for c, s in [("di_ata", 1), ("gap_taylor_pb", 1), ("aperto_pp", -1)]:
        x = s * amostra[c]
        prev = np.sign(passo(x)) if c == "di_ata" else np.sign(x)
        print(f"   {c:14s} {100 * (prev == y).mean():.0f}%")

    specs = {"B0 DI no dia da ata": None, "B1 OLS(DI)": ["di_ata"],
             "F1 DI + gap Taylor (MPP)": ["di_ata", "gap_taylor_pb"],
             "F2 DI + aperto (DSGE)": ["di_ata", "aperto_pp"],
             "F3 DI + MPP + DSGE": ["di_ata", "gap_taylor_pb", "aperto_pp"],
             "F4 F3 + comunicado": ["di_ata", "gap_taylor_pb", "aperto_pp", "com_sinal"]}
    wf = walk_forward(amostra, specs)
    wf.to_csv(RES / "f6_walk_forward.csv", index=False)
    print("\n1. Walk-forward (previsão no dia da ata):\n" + wf.round(1).to_string(index=False))

    d = amostra.dropna(subset=["deriva"])
    linhas = []
    for nome, cols in {"MPP": ["gap_taylor_pb"], "DSGE": ["aperto_pp"],
                       "MPP + DSGE": ["gap_taylor_pb", "aperto_pp"],
                       "MPP + DSGE + DI": ["gap_taylor_pb", "aperto_pp", "di_ata"]}.items():
        m = sm.OLS(d["deriva"], sm.add_constant(d[cols])).fit(cov_type="HAC", cov_kwds={"maxlags": 2})
        for c in cols:
            linhas.append({"especificacao": nome, "variavel": c, "coef": m.params[c], "ep": m.bse[c],
                           "p": m.pvalues[c], "r2": m.rsquared, "n": int(m.nobs)})
    dr = pd.DataFrame(linhas)
    dr.to_csv(RES / "f6_deriva.csv", index=False)
    print("\n2. Os fundamentos antecipam a deriva do DI até a véspera?\n" + dr.round(3).to_string(index=False))

    viva = df[df["nro_t1"] == df["nro_t1"].max()].iloc[0]
    print(f"\n3. Leitura para a {int(viva['nro_t1'])}ª (dia da ata da {int(viva['nro_t1']) - 1}ª):")
    for c in ["di_ata", "focus_ata", "com_sinal", "gap_taylor_pb", "selic_taylor", "aperto_pp", "neutro"]:
        print(f"   {c:14s} {viva.get(c, np.nan)}")
