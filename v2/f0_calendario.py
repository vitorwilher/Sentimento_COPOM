"""F0 — calendário ponto-no-tempo das reuniões do Copom, de 2005 em diante.

Uma linha por reunião t, com:
  nro_reuniao, data_decisao (comunicado, à noite), data_ata (publicação, 8h),
  rotulo_focus (Rk/AAAA), data_corte, selic_antes, selic_depois, delta_pb,
  nro_seguinte, data_decisao_seguinte, delta_pb_seguinte (o ALVO da v2.0).

data_corte é o último dia útil ANTES do primeiro dia da reunião t.
  EVIDÊNCIA: as reuniões têm dois dias e a decisão sai no segundo (data do comunicado).
  DECISÃO: data_corte = 2 dias úteis antes de data_decisao. Tudo o que entra para prever a
  reunião t tem data <= data_corte. Nas reuniões de dia único (anteriores a 2006?) o corte fica
  um dia útil mais cedo que o necessário: conservador, não vaza.

Saída: v2/dados/calendario.csv

Uso: .venv/bin/python -m v2.f0_calendario [--atualizar]
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from v2 import fontes

INICIO = "2005-01-01"
SAIDA = fontes.RAIZ / "dados" / "calendario.csv"


def dias_uteis() -> pd.DatetimeIndex:
    """Dias úteis observados = dias com CDI no SGS 4389; à frente do último dado, dias de semana."""
    cdi = fontes.sgs(4389, inicio="2004-01-01")
    obs = pd.DatetimeIndex(cdi.index)
    futuro = pd.bdate_range(obs.max() + pd.Timedelta(days=1), obs.max() + pd.Timedelta(days=365 * 13))  # cobre os DI1 mais longos
    return obs.append(futuro)


def montar(atualizar: bool = False) -> pd.DataFrame:
    com = fontes.lista_comunicados(atualizar)
    atas = fontes.lista_atas(atualizar)
    cal = com.merge(atas, on="nro_reuniao", how="left").sort_values("nro_reuniao")

    # Rótulo do Focus: k-ésima reunião do ano. Calculado sobre TODAS as reuniões do ano
    # (antes do filtro de 2005) para não errar a contagem.
    cal["ano"] = cal["data_decisao"].dt.year
    cal["ordem_no_ano"] = cal.groupby("ano").cumcount() + 1
    cal["rotulo_focus"] = "R" + cal["ordem_no_ano"].astype(str) + "/" + cal["ano"].astype(str)
    cal = cal[cal["data_decisao"] >= INICIO].copy()

    du = dias_uteis()
    pos = du.searchsorted(cal["data_decisao"].values)
    cal["data_corte"] = du[np.maximum(pos - 2, 0)]

    meta = fontes.sgs(432, inicio="2004-01-01", atualizar=atualizar)
    meta = meta.reindex(pd.date_range(meta.index.min(), meta.index.max())).ffill()
    d = cal["data_decisao"]
    cal["selic_antes"] = meta.reindex(d).values
    # A nova meta vale a partir do dia útil seguinte à decisão (ex.: 209ª, 06/09/2017, véspera de feriado).
    cal["selic_depois"] = meta.reindex(du[np.minimum(pos + 1, len(du) - 1)]).values
    cal["delta_pb"] = ((cal["selic_depois"] - cal["selic_antes"]) * 100).round().astype("Int64")

    cal = cal.sort_values("data_decisao").reset_index(drop=True)
    cal["nro_seguinte"] = cal["nro_reuniao"].shift(-1).astype("Int64")
    cal["data_decisao_seguinte"] = cal["data_decisao"].shift(-1)
    cal["delta_pb_seguinte"] = cal["delta_pb"].shift(-1)

    cols = ["nro_reuniao", "data_decisao", "data_ata", "rotulo_focus", "data_corte",
            "selic_antes", "selic_depois", "delta_pb",
            "nro_seguinte", "data_decisao_seguinte", "delta_pb_seguinte", "titulo"]
    return cal[cols]


def checar(cal: pd.DataFrame) -> list[str]:
    """Testes de consistência; devolve a lista de problemas (vazia = ok)."""
    p = []
    if cal["nro_reuniao"].duplicated().any():
        p.append("reunião duplicada")
    buracos = set(range(cal["nro_reuniao"].min(), cal["nro_reuniao"].max() + 1)) - set(cal["nro_reuniao"])
    if buracos:
        p.append(f"reuniões sem comunicado: {sorted(buracos)}")
    if (cal["data_corte"] >= cal["data_decisao"]).any():
        p.append("data_corte não é anterior à decisão")
    sem_ata = cal.loc[cal["data_ata"].isna(), "nro_reuniao"].tolist()
    if sem_ata:
        p.append(f"reuniões sem ata publicada: {sem_ata}")
    if (cal["data_ata"] <= cal["data_decisao"]).any():
        p.append("ata publicada antes da decisão")
    # o título do comunicado recente traz a taxa: confere com o SGS
    m = cal["titulo"].str.extract(r"(\d{1,2},\d{2})\s*%")[0].str.replace(",", ".").astype(float)
    dif = (m - cal["selic_depois"]).abs()
    ruins = cal.loc[dif > 1e-9, "nro_reuniao"].tolist()
    if ruins:
        p.append(f"taxa do título difere do SGS 432: {ruins}")
    por_ano = cal.groupby(cal["data_decisao"].dt.year).size()
    p.append("reuniões por ano: " + ", ".join(f"{a}:{n}" for a, n in por_ano.items()))
    return p


if __name__ == "__main__":
    cal = montar(atualizar="--atualizar" in sys.argv)
    cal.to_csv(SAIDA, index=False)
    print(f"{len(cal)} reuniões ({cal['nro_reuniao'].min()}–{cal['nro_reuniao'].max()}) -> {SAIDA}")
    for linha in checar(cal):
        print(" •", linha)
    print(cal.drop(columns="titulo").tail(4).to_string(index=False))
