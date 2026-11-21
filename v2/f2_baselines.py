"""F2 — baselines sem texto: a régua que o modelo da v2.0 precisa vencer.

Alvo: delta_pb da reunião t. Toda previsão usa só informação com data <= data_corte(t).

  inercia   repete a decisão da reunião t-1
  focus     mediana do Focus para a reunião t (última leitura até o corte) − Selic vigente
  di        Δ implícita na curva de DI no corte (f1_di.py)

Previsões pontuais. Para o acerto exato, arredondam ao múltiplo de 25 pb mais próximo.
As métricas de distribuição (log score, Brier) entram na F5, quando houver modelo probabilístico.

Saídas: v2/dados/baselines_por_reuniao.csv e v2/resultados/f2_baselines.csv

Uso: .venv/bin/python -m v2.f2_baselines
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from v2 import fontes
from v2.f0_calendario import SAIDA as CAL
from v2.f1_di import SAIDA as DI

RES = fontes.RAIZ / "resultados"
RES.mkdir(exist_ok=True)


def passo25(x):
    return (np.round(np.asarray(x, dtype=float) / 25) * 25)


def montar() -> pd.DataFrame:
    cal = pd.read_csv(CAL, parse_dates=["data_decisao", "data_corte"])
    cal = cal.dropna(subset=["delta_pb"]).copy()
    cal["prev_inercia"] = cal["delta_pb"].shift(1)

    focus = []
    for _, r in cal.iterrows():
        f = fontes.focus_selic_reuniao(r["rotulo_focus"], r["data_corte"])
        focus.append({
            "focus_data": f and f["Data"], "focus_mediana": f and f["Mediana"],
            "focus_media": f and f["Media"], "focus_dp": f and f["DesvioPadrao"],
        })
    cal = pd.concat([cal.reset_index(drop=True), pd.DataFrame(focus)], axis=1)
    cal["prev_focus"] = (cal["focus_mediana"] - cal["selic_antes"]) * 100
    cal["prev_focus_media"] = (cal["focus_media"] - cal["selic_antes"]) * 100

    di = pd.read_csv(DI)[["nro_reuniao", "delta_impl_pb", "fonte_di", "flag",
                          "surpresa_comunicado_pb", "surpresa_comunicado_caminho_pb", "surpresa_ata_pb"]]
    cal = cal.merge(di, on="nro_reuniao", how="left").rename(columns={"delta_impl_pb": "prev_di"})

    # ponto de virada: a direção da decisão muda em relação à reunião anterior
    sinal = np.sign(cal["delta_pb"])
    cal["virada"] = sinal != np.sign(cal["prev_inercia"])
    return cal


def metricas(df: pd.DataFrame, col: str) -> dict:
    d = df.dropna(subset=[col, "delta_pb"])
    y, p = d["delta_pb"].astype(float), d[col].astype(float)
    return {
        "n": len(d),
        "acerto_exato_%": 100 * (passo25(p) == y).mean(),
        "acerto_direcao_%": 100 * (np.sign(passo25(p)) == np.sign(y)).mean(),
        "rmse_pb": float(np.sqrt(((p - y) ** 2).mean())),
        "mae_pb": float((p - y).abs().mean()),
    }


def tabela(cal: pd.DataFrame) -> pd.DataFrame:
    recortes = {
        "2005–2026": cal,
        "2016–2026": cal[cal["data_decisao"] >= "2016-01-01"],
        "2019–2026 (DI B3)": cal[cal["data_decisao"] >= "2019-01-01"],
        "pontos de virada": cal[cal["virada"]],
    }
    prev = {"inércia": "prev_inercia", "Focus (mediana)": "prev_focus", "DI implícito": "prev_di"}
    linhas = []
    for nome_r, d in recortes.items():
        comum = d.dropna(subset=list(prev.values()))  # mesma amostra para os três
        for nome_p, col in prev.items():
            linhas.append({"recorte": nome_r, "baseline": nome_p, **metricas(comum, col)})
    return pd.DataFrame(linhas)


if __name__ == "__main__":
    cal = montar()
    cal.to_csv(fontes.RAIZ / "dados" / "baselines_por_reuniao.csv", index=False)
    t = tabela(cal)
    t.to_csv(RES / "f2_baselines.csv", index=False)
    pd.set_option("display.width", 160)
    print(t.round(1).to_string(index=False))
    sem_focus = cal.loc[cal["focus_mediana"].isna(), "nro_reuniao"].tolist()
    print(f"\nreuniões sem Focus no corte: {sem_focus}")
