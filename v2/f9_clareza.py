"""F9 — clareza da comunicação e coordenação das expectativas (Lima, 2015, dissertação UFF).

A dissertação aplicou índices de legibilidade (Flesch) às atas e achou que mais clareza (i) vem
quando as expectativas aceleram, (ii) reduz a dispersão das expectativas e (iii) ancora melhor
as expectativas à meta. A v2.0 mostrou que o texto não antecipa o NÍVEL da Selic além do DI;
aqui a pergunta é se ele COORDENA o mercado.

Desenho (contra a causalidade reversa do achado i): variação em torno da comunicação de t.
  Δdisp    dispersão (desvio-padrão) do Focus para a Selic da reunião t+1, do corte de t
           (antes do comunicado) ao dia da ata de t (depois do comunicado e da ata), em pb
  Δancora  |expectativa Focus de 2 a 4 anos − meta|, do corte de t ao corte de t+1, em p.p.
Clareza de t:
  guidance  o texto fala explicitamente dos próximos passos (média dos LLMs, comunicado e ata)
  cond      condicionalidade 0 (compromisso) … 3 (dependente de dados), comunicado e ata
  flesch    Flesch adaptado ao português (Martins et al., 1996), comunicado e ata
Controles: |ΔSelic de t|, |surpresa da decisão no DI| (F1) e o nível da dispersão no corte.

Uso: .venv/bin/python -m v2.f9_clareza
"""

from __future__ import annotations

import json
import re

import numpy as np
import pandas as pd
import statsmodels.api as sm

from v2 import fontes
from v2.f0_calendario import SAIDA as CAL
from v2.f1_di import SAIDA as DI
from v2.f7_indice import Series

RES = fontes.RAIZ / "resultados"


def flesch_pt(t: str) -> float:
    """Flesch adaptado ao português (Martins et al., 1996): 248,835 − 1,015·(pal/frase) − 84,6·(síl/pal)."""
    if not t:
        return np.nan
    frases = max(1, len(re.findall(r"[.!?;]+\s", t)))
    pal = re.findall(r"[A-Za-zÀ-ÿ]+", t)
    sil = sum(max(1, len(re.findall(r"[aeiouáéíóúâêôãõàü]+", p.lower()))) for p in pal)
    return 248.835 - 1.015 * len(pal) / frases - 84.6 * sil / max(1, len(pal))


def leituras(doc: str) -> pd.DataFrame:
    partes = [pd.read_csv(a) for p in ("claude", "openai", "gemini")
              if (a := fontes.RAIZ / "dados" / f"leitura_{doc}_{p}.csv").exists()]
    d = pd.concat(partes)
    d["guidance_explicito"] = d["guidance_explicito"].astype(str).str.lower().eq("true").astype(float)
    return d.groupby("nro_reuniao")[["guidance_explicito", "condicionalidade"]].mean()


def montar() -> pd.DataFrame:
    cal = pd.read_csv(CAL, parse_dates=["data_ata", "data_corte"])
    com_txt = json.loads((fontes.RAW / "comunicados_texto.json").read_text(encoding="utf-8"))
    ata_txt = json.loads((fontes.RAW / "atas_texto.json").read_text(encoding="utf-8"))
    lc, la = leituras("comunicados"), leituras("atas")
    surp = pd.read_csv(DI).set_index("nro_reuniao")["surpresa_comunicado_pb"]
    meta = fontes.sgs(13521, inicio="2004-01-01")
    S = Series()

    def desancoragem(d):
        y = d.year
        m = meta[meta.index.year.isin([y + 2, y + 3, y + 4])]
        exp = S.valor("expectativas_longo", d, y)
        return abs(exp - m.mean()) if len(m) else np.nan

    linhas = []
    for i in range(len(cal) - 1):
        t, t1 = cal.iloc[i], cal.iloc[i + 1]
        if pd.isna(t["data_ata"]):
            continue
        n = int(t["nro_reuniao"])
        antes = fontes.focus_selic_reuniao(t1["rotulo_focus"], t["data_corte"])
        depois = fontes.focus_selic_reuniao(t1["rotulo_focus"], t["data_ata"])
        linhas.append({
            "nro_t": n, "data_ata": t["data_ata"],
            "disp_antes": antes and antes["DesvioPadrao"] * 100, "disp_depois": depois and depois["DesvioPadrao"] * 100,
            "desanc_antes": desancoragem(t["data_corte"]), "desanc_depois": desancoragem(t1["data_corte"]),
            "abs_delta_t": abs(t["delta_pb"]), "abs_surpresa": abs(surp.get(n, np.nan)),
            "com_guidance": lc["guidance_explicito"].get(n, np.nan), "com_cond": lc["condicionalidade"].get(n, np.nan),
            "ata_guidance": la["guidance_explicito"].get(n, np.nan), "ata_cond": la["condicionalidade"].get(n, np.nan),
            "com_flesch": flesch_pt(com_txt.get(str(n), "")), "ata_flesch": flesch_pt(ata_txt.get(str(n), "")),
        })
    df = pd.DataFrame(linhas)
    df["d_disp"] = df["disp_depois"] - df["disp_antes"]
    df["d_desanc"] = df["desanc_depois"] - df["desanc_antes"]
    return df


PRESIDENCIAS = [("Tombini", "2011-01-01"), ("Goldfajn", "2016-06-09"), ("Campos Neto", "2019-02-28"),
                ("Galípolo", "2025-01-01")]  # base: Meirelles (até 2010)


def dummies(df):
    for nome, ini in PRESIDENCIAS:
        df[f"pres_{nome}"] = (df["data_ata"] >= ini).astype(float)  # degraus acumulados = efeito por período
    return [f"pres_{n}" for n, _ in PRESIDENCIAS]


def regride(df, y, x, controles, espec="sem período"):
    d = df.dropna(subset=[y] + x + controles)
    m = sm.OLS(d[y], sm.add_constant(d[x + controles])).fit(cov_type="HAC", cov_kwds={"maxlags": 2})
    return [{"espec": espec, "alvo": y, "variavel": c, "coef": m.params[c], "ep": m.bse[c], "p": m.pvalues[c],
             "r2": m.rsquared, "n": int(m.nobs)} for c in x]


if __name__ == "__main__":
    RES.mkdir(exist_ok=True)
    df = montar()
    df.to_csv(fontes.RAIZ / "dados" / "base_clareza.csv", index=False)
    ctrl = ["abs_delta_t", "abs_surpresa"]
    pres = dummies(df)
    linhas = []
    for x in (["com_guidance", "com_cond"], ["ata_guidance", "ata_cond"], ["com_flesch", "ata_flesch"]):
        for espec, extra in (("sem período", []), ("com presidência", pres)):
            linhas += regride(df, "d_disp", x, ctrl + ["disp_antes"] + extra, espec)
            linhas += regride(df, "disp_depois", x, ctrl + extra, espec)
            linhas += regride(df, "d_desanc", x, ctrl + ["desanc_antes"] + extra, espec)
    t = pd.DataFrame(linhas)
    t.to_csv(RES / "f9_clareza.csv", index=False)
    pd.set_option("display.width", 160)
    print(t.round(3).to_string(index=False))
