"""F8b — horizontes longos: o tom do Copom antecipa a Selic de 2 a 8 reuniões à frente além do DI?

Caruso (Santander, 25/02/2026), num VAR em amostra, acha que a surpresa de tom (tom menos o que os
fundamentos explicam) antecipa a Selic: o comunicado com pico em 2 reuniões, a ata a partir da 5ª.
O VAR não controla pelo preço de mercado. Aqui, no dia da ata de t:

  mercado_h   Selic precificada para logo depois da reunião t+h, menos o CDI do dia (pb):
              taxa a termo de 21 dias úteis a partir da vigência de t+h, na curva zero do dia
              (DI1 da B3 a partir de out/2019; swaps DI × pré do SGS, 30 a 360 dias, antes)
  realizado_h meta Selic depois de t+h − meta depois de t (pb)
  erro_h      realizado_h − mercado_h

Tom no dia da ata de t (média de Claude e GPT): postura e sinal (direção × magnitude) do comunicado
de t (F5) e da ata de t (F8a). Surpresa à la Caruso: resíduo do tom numa regressão em fundamentos
observados no dia (expectativa Focus do ano seguinte − meta, IBC-Br 12 meses, variação do câmbio
em 3 meses), em amostra, como no relatório.

Testes por horizonte: realizado_h ~ tom (o resultado do Caruso, sem mercado) e erro_h ~ tom
(o tom antecipa o que o mercado erra?), HAC com h defasagens; walk-forward do RMSE.

Uso: .venv/bin/python -m v2.f8_horizonte
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

from v2 import fontes
from v2.f0_calendario import SAIDA as CAL
from v2.f1_di import DU, _du_entre, _proximo_du, _vencimento_util
from v2.f5_modelo import DIR
from v2.f7_indice import Series

HORIZ = [1, 2, 4, 6, 8]
INI_B3 = pd.Timestamp("2019-10-01")
RES = fontes.RAIZ / "resultados"


# ------------------------------------------------------------------ curva zero e termo
def curva(d: pd.Timestamp, cache: dict) -> list[tuple[int, float]] | None:
    """[(dias úteis, log-fator acumulado)] no fechamento de d, com o ponto (0, 0)."""
    if d in cache:
        return cache[d]
    pts = [(0, 0.0)]
    if d >= INI_B3:
        di = fontes.di1_dia(d.date())
        if di is None:
            cache[d] = None
            return None
        for _, r in di.iterrows():
            n = _du_entre(d, _vencimento_util(pd.Timestamp(r["vencimento"])))
            if n > 0:
                pts.append((n, n / 252 * np.log1p(r["taxa"] / 100)))
    else:
        for prazo, cod in fontes.SWAPS_SGS.items():
            s = fontes.sgs(cod)
            if d in s.index:
                n = _du_entre(d, d + pd.Timedelta(days=prazo))
                pts.append((n, n / 252 * np.log1p(s[d] / 100)))
    pts = sorted(set(pts))
    cache[d] = pts if len(pts) >= 3 else None
    return cache[d]


def termo(pts, a: int, b: int) -> float:
    """Taxa a termo (% a.a., base 252) entre a e b dias úteis; nan se b passa do último vértice."""
    x, y = zip(*pts)
    if b > x[-1]:
        return np.nan
    la, lb = np.interp(a, x, y), np.interp(b, x, y)
    return (np.exp((lb - la) / ((b - a) / 252)) - 1) * 100


# ------------------------------------------------------------------ tom
def tom() -> pd.DataFrame:
    partes = []
    for doc, pref in (("comunicados", "com"), ("atas", "ata")):
        for p in ("claude", "openai"):
            arq = fontes.RAIZ / "dados" / f"leitura_{doc}_{p}.csv"
            if not arq.exists():
                continue
            d = pd.read_csv(arq)
            d["sinal"] = d["direcao_proxima"].map(DIR) * d["magnitude_pb"].fillna(25).abs()
            partes.append(d.assign(doc=pref)[["nro_reuniao", "doc", "postura", "sinal"]])
    t = pd.concat(partes).groupby(["nro_reuniao", "doc"])[["postura", "sinal"]].mean().unstack("doc")
    t.columns = [f"{doc}_{v}" for v, doc in t.columns]
    return t.reset_index()


# ------------------------------------------------------------------ montagem
def montar() -> pd.DataFrame:
    cal = pd.read_csv(CAL, parse_dates=["data_decisao", "data_ata"])
    cal["vig"] = cal["data_decisao"].map(_proximo_du)
    cdi = fontes.sgs(4389)
    meta = fontes.sgs(13521, inicio="2004-01-01")  # meta de inflação do CMN (anual)
    S, cache = Series(), {}
    linhas = []
    for i in range(len(cal)):
        t = cal.iloc[i]
        a = t["data_ata"]
        if pd.isna(a) or a not in cdi.index:
            continue
        pts = curva(a, cache)
        y = a.year
        meta_y1 = meta[meta.index.year == y + 1]
        lin = {"nro_t": int(t["nro_reuniao"]), "data_ata": a,
               # fundamentos no dia da ata (para a surpresa à la Caruso)
               "f_expect_gap": S.valor("expectativas_curto", a, y) - (meta_y1.iloc[0] if len(meta_y1) else np.nan),
               "f_atividade": S.valor("atividade", a, y),
               "f_cambio_3m": S.valor("cambio", a, y) - S.valor("cambio", a - pd.Timedelta(days=91), y)}
        for h in HORIZ:
            if i + h >= len(cal):
                continue
            th = cal.iloc[i + h]
            lin[f"realizado_{h}"] = (th["selic_depois"] - t["selic_depois"]) * 100
            if pts is None:
                continue
            ini = _du_entre(a, th["vig"])
            fwd = termo(pts, ini, ini + 21)
            lin[f"mercado_{h}"] = (fwd - cdi[a]) * 100
        linhas.append(lin)
    df = pd.DataFrame(linhas).merge(tom(), left_on="nro_t", right_on="nro_reuniao", how="left").drop(columns="nro_reuniao")
    for h in HORIZ:
        if f"mercado_{h}" in df:
            df[f"erro_{h}"] = df[f"realizado_{h}"] - df[f"mercado_{h}"]
    # surpresa de tom à la Caruso: resíduo do tom nos fundamentos (em amostra)
    F = ["f_expect_gap", "f_atividade", "f_cambio_3m"]
    for c in ["com_postura", "ata_postura", "com_sinal", "ata_sinal"]:
        if c not in df:
            continue
        ok = df[F + [c]].dropna().index
        m = sm.OLS(df.loc[ok, c], sm.add_constant(df.loc[ok, F])).fit()
        df.loc[ok, f"surpresa_{c}"] = m.resid
    return df


if __name__ == "__main__":
    RES.mkdir(exist_ok=True)
    df = montar()
    df.to_csv(fontes.RAIZ / "dados" / "base_horizonte.csv", index=False)
    tons = [c for c in ["com_postura", "com_sinal", "ata_postura", "ata_sinal",
                        "surpresa_com_postura", "surpresa_ata_postura"] if c in df]
    linhas = []
    for h in HORIZ:
        if f"erro_{h}" not in df:
            continue
        d = df.dropna(subset=[f"erro_{h}", f"mercado_{h}"])
        cor = d[f"mercado_{h}"].corr(d[f"realizado_{h}"])
        for c in tons:
            dd = d.dropna(subset=[c])
            for alvo in (f"realizado_{h}", f"erro_{h}"):
                m = sm.OLS(dd[alvo], sm.add_constant(dd[c])).fit(cov_type="HAC", cov_kwds={"maxlags": max(h, 1)})
                linhas.append({"h": h, "tom": c, "alvo": alvo.split("_")[0], "coef_pb_por_unidade": m.params[c],
                               "p": m.pvalues[c], "r2": m.rsquared, "n": int(m.nobs),
                               "corr_mercado_realizado": cor,
                               "rmse_mercado": float(np.sqrt((d[f"erro_{h}"] ** 2).mean()))})
    t = pd.DataFrame(linhas)
    t.to_csv(RES / "f8_horizonte.csv", index=False)
    pd.set_option("display.width", 170)
    print(t[t["alvo"] == "realizado"].pivot_table(index="tom", columns="h", values="p").round(3)
          .to_string(header=True), "\n← p-valor: tom antecipa a Selic acumulada (sem mercado, como no Caruso)\n")
    print(t[t["alvo"] == "erro"].pivot_table(index="tom", columns="h", values="p").round(3)
          .to_string(), "\n← p-valor: tom antecipa o ERRO do mercado\n")
    print(t[t["alvo"] == "erro"].pivot_table(index="tom", columns="h", values="coef_pb_por_unidade").round(1).to_string(),
          "\n← coeficiente (pb de erro por unidade de tom)\n")
    print(t.drop_duplicates("h")[["h", "n", "corr_mercado_realizado", "rmse_mercado"]].round(2).to_string(index=False))


# ------------------------------------------------------------------ robustez: o tom sobrevive a viés da curva e inércia?
def robustez(df: pd.DataFrame, min_treino: int = 60) -> pd.DataFrame:
    """erro_h ~ tom + mercado_h + inércia (HAC h) e walk-forward: realizado_h ~ mercado_h [+ inércia] [+ tom].

    Duas explicações alternativas: (1) o viés da curva varia com o ciclo (a termo subestima ciclos
    longos), e o tom só marca o ciclo; (2) inércia (o mercado subprecifica a persistência).
    """
    cal = pd.read_csv(CAL)
    df = df.merge(cal[["nro_reuniao", "delta_pb"]].rename(columns={"nro_reuniao": "nro_t", "delta_pb": "inercia"}),
                  on="nro_t", how="left").sort_values("data_ata").reset_index(drop=True)
    linhas = []
    for h in HORIZ:
        for tom_c in ("com_postura", "ata_postura", "com_sinal", "ata_sinal"):
            cols = [tom_c, f"mercado_{h}", "inercia"]
            d = df.dropna(subset=cols + [f"erro_{h}"])
            if len(d) < 40:
                continue
            m = sm.OLS(d[f"erro_{h}"], sm.add_constant(d[cols])).fit(cov_type="HAC", cov_kwds={"maxlags": max(h, 1)})
            # walk-forward: só observações cujo realizado já era conhecido na data (i − h), sem vazamento
            prev = {"mercado": [], "+inércia": [], "+inércia+tom": []}
            y = []
            for i in range(min_treino, len(d)):
                tr = d.iloc[: max(i - h + 1, 0)]
                te = d.iloc[[i]]
                y.append(te[f"realizado_{h}"].iloc[0])
                prev["mercado"].append(te[f"mercado_{h}"].iloc[0])
                for nome, xs in (("+inércia", [f"mercado_{h}", "inercia"]), ("+inércia+tom", [f"mercado_{h}", "inercia", tom_c])):
                    mm = sm.OLS(tr[f"realizado_{h}"], sm.add_constant(tr[xs])).fit()
                    prev[nome].append(float(mm.predict(sm.add_constant(te[xs], has_constant="add")).iloc[0]))
            y = np.array(y)
            rm = {k: float(np.sqrt(((np.array(v) - y) ** 2).mean())) for k, v in prev.items()}
            linhas.append({"h": h, "tom": tom_c, "coef_tom": m.params[tom_c], "p_tom": m.pvalues[tom_c],
                           "coef_mercado": m.params[f"mercado_{h}"], "p_mercado": m.pvalues[f"mercado_{h}"],
                           "coef_inercia": m.params["inercia"], "p_inercia": m.pvalues["inercia"], "n": int(m.nobs),
                           "rmse_mercado": rm["mercado"], "rmse_mais_inercia": rm["+inércia"],
                           "rmse_mais_inercia_tom": rm["+inércia+tom"], "n_wf": len(y)})
    return pd.DataFrame(linhas)


if __name__ == "__main__":
    rb = robustez(df)
    rb.to_csv(RES / "f8_robustez.csv", index=False)
    print("\nRobustez: erro_h ~ tom + mercado_h + inércia (HAC) e RMSE fora da amostra (walk-forward)")
    print(rb.round(3).to_string(index=False))
