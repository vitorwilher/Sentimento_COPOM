"""F3b — estudo de evento: os textos e apresentações da diretoria movem a curva de juros?

Antes de pagar por extração e escoragem de PDFs, mede-se se há informação nesses dias.

Variável: variação em 2 dias do swap DI × pré de 60 dias (SGS 7802), |r(d+1) − r(d−1)| em pb.
  O swap de 60 dias cobre a próxima reunião durante quase toda a janela entre reuniões.
  2 dias porque o horário do evento é desconhecido (pode ser depois do fechamento).
Amostra: dias úteis de 2006 a set/2019 (fim da série do SGS), fora das janelas do comunicado
  (decisão e dia seguinte) e da ata (véspera e dia), que têm efeito próprio conhecido.
Grupos:
  relevante      presidente ou diretor de política econômica, tema monetário (regra de título)
  outros_textos  demais itens do catálogo
  sem_evento     dias úteis sem item do catálogo
  ata, comunicado  referência: quanto os documentos oficiais movem a curva
Teste: diferença de médias contra sem_evento, p-valor por permutação (10.000 sorteios).

Uso: .venv/bin/python -m v2.f3_evento          (SGS, 2006–2019)
     .venv/bin/python -m v2.f3_evento --b3     (DI1 da B3, 2019–2026)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from v2 import fontes
from v2.f0_calendario import SAIDA as CAL
from v2.f1_di import DU
from v2.f3_discursos import SAIDA as DISC

FIM = pd.Timestamp("2019-09-27")
INI = pd.Timestamp("2006-01-02")


def variacao_2d() -> pd.Series:
    sw = fontes.sgs(fontes.SWAPS_SGS[60])
    sw = sw[(sw.index >= INI - pd.Timedelta(days=10)) & (sw.index <= FIM + pd.Timedelta(days=10))]
    return ((sw.shift(-1) - sw.shift(1)).abs() * 100).loc[INI:FIM].dropna()


def montar() -> pd.DataFrame:
    v = variacao_2d().rename("abs_var_pb").to_frame()
    cal = pd.read_csv(CAL, parse_dates=["data_decisao", "data_ata"])
    disc = pd.read_csv(DISC, parse_dates=["data"])

    def prox(d):
        return DU[DU.searchsorted(d, side="right")]

    def ant(d):
        return DU[DU.searchsorted(d) - 1]

    com = set(cal["data_decisao"]) | {prox(d) for d in cal["data_decisao"]}
    ata = set(cal["data_ata"].dropna()) | {ant(d) for d in cal["data_ata"].dropna()}
    rel = set(disc.loc[disc["relevante"], "data"])
    outros = set(disc.loc[~disc["relevante"], "data"])

    def grupo(d):
        if d in com:
            return "comunicado"
        if d in ata:
            return "ata"
        if d in rel:
            return "relevante"
        if d in outros:
            return "outros_textos"
        return "sem_evento"

    v["grupo"] = [grupo(d) for d in v.index]
    return v


def permutacao(a: np.ndarray, b: np.ndarray, n: int = 10_000, seed: int = 0) -> float:
    """p-valor unicaudal de mean(a) > mean(b)."""
    rng = np.random.default_rng(seed)
    obs = a.mean() - b.mean()
    tudo = np.concatenate([a, b])
    k = len(a)
    cont = 0
    for _ in range(n):
        rng.shuffle(tudo)
        cont += (tudo[:k].mean() - tudo[k:].mean()) >= obs
    return (cont + 1) / (n + 1)


def _main_b3():
    v = b3_evento()
    v.to_csv(fontes.RAIZ / "dados" / "evento_di1_b3.csv", index=False)
    t = resumo(v)
    t.to_csv(fontes.RAIZ / "resultados" / "f3_evento_b3.csv", index=False)
    print(t.round(3).to_string(index=False))


# ---------------------------------------------------------------- era B3 (2019–2026)
def b3_evento(n_controle: int = 160, seed: int = 0) -> pd.DataFrame:
    """Mesma medida com o DI1 da B3: |r(d+1) − r(d−1)| no contrato que cobre só a próxima reunião.

    Usa dois arquivos por dia (d e d+1); r(d−1) é a taxa_ant do arquivo de d. Controle: sorteio
    de `n_controle` dias úteis sem evento. Baixa ~2 arquivos da B3 por dia (minutos por centena).
    """
    from v2.f1_di import _escolhe_contrato, _proximo_du

    cal = pd.read_csv(CAL, parse_dates=["data_decisao", "data_ata"])
    vig = cal["data_decisao"].map(_proximo_du).tolist()
    disc = pd.read_csv(DISC, parse_dates=["data"])
    ini, fim = pd.Timestamp("2019-01-03"), cal["data_decisao"].max()
    dias = DU[(DU >= ini) & (DU <= fim)]

    com = set(cal["data_decisao"]) | {DU[DU.searchsorted(d, side="right")] for d in cal["data_decisao"]}
    ata = set(cal["data_ata"].dropna()) | {DU[DU.searchsorted(d) - 1] for d in cal["data_ata"].dropna()}
    rel = set(disc.loc[disc["relevante"], "data"])
    outros = set(disc.loc[~disc["relevante"], "data"])
    excluir = com | ata | rel | outros
    ctrl = pd.Series([d for d in dias if d not in excluir]).sample(n_controle, random_state=seed)

    alvo = ([(d, "relevante") for d in sorted(rel) if ini <= d <= fim and d not in com | ata]
            + [(d, "ata") for d in sorted(ata) if ini <= d <= fim and d in set(cal["data_ata"])]
            + [(d, "sem_evento") for d in sorted(ctrl)])
    linhas = []
    for d, g in alvo:
        i = next(k for k, v in enumerate(vig) if v > d + pd.Timedelta(days=1))  # próxima reunião
        if i + 1 >= len(vig):
            continue
        d1 = DU[DU.searchsorted(d, side="right")]
        a, b = fontes.di1_dia(d.date()), fontes.di1_dia(d1.date())
        if a is None or b is None:
            continue
        ca, _ = _escolhe_contrato(a, vig[i], vig[i + 1])
        if ca is None:
            continue
        rb = b.loc[b["ticker"] == ca["ticker"], "taxa"]
        if rb.empty or pd.isna(ca["taxa_ant"]):
            continue
        linhas.append({"data": d, "grupo": g, "contrato": ca["ticker"],
                       "abs_var_pb": abs(rb.iloc[0] - ca["taxa_ant"]) * 100})
        print(f"  {d.date()} {g:11s} {ca['ticker']} {linhas[-1]['abs_var_pb']:.1f}", flush=True)
    return pd.DataFrame(linhas)


def resumo(v: pd.DataFrame) -> pd.DataFrame:
    base = v.loc[v["grupo"] == "sem_evento", "abs_var_pb"].values
    out = []
    for g in [x for x in ["comunicado", "ata", "relevante", "outros_textos", "sem_evento"] if x in set(v["grupo"])]:
        x = v.loc[v["grupo"] == g, "abs_var_pb"].values
        out.append({"grupo": g, "dias": len(x), "media_abs_pb": x.mean(), "mediana_abs_pb": np.median(x),
                    "p90_pb": np.percentile(x, 90), "razao_vs_sem_evento": x.mean() / base.mean(),
                    "p_valor_perm": np.nan if g == "sem_evento" else permutacao(x, base)})
    return pd.DataFrame(out)


def _main_sgs():
    v = montar()
    v.to_csv(fontes.RAIZ / "dados" / "evento_swap60.csv")
    base = v.loc[v["grupo"] == "sem_evento", "abs_var_pb"].values
    linhas = []
    for g in ["comunicado", "ata", "relevante", "outros_textos", "sem_evento"]:
        x = v.loc[v["grupo"] == g, "abs_var_pb"].values
        linhas.append({
            "grupo": g, "dias": len(x), "media_abs_pb": x.mean(), "mediana_abs_pb": np.median(x),
            "p90_pb": np.percentile(x, 90),
            "razao_vs_sem_evento": x.mean() / base.mean(),
            "p_valor_perm": np.nan if g == "sem_evento" else permutacao(x, base),
        })
    t = pd.DataFrame(linhas)
    (fontes.RAIZ / "resultados").mkdir(exist_ok=True)
    t.to_csv(fontes.RAIZ / "resultados" / "f3_evento.csv", index=False)
    print(t.round(3).to_string(index=False))


if __name__ == "__main__":
    _main_b3() if "--b3" in __import__("sys").argv else _main_sgs()
