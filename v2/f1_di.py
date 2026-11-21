"""F1 — DI: Δ Selic implícita na véspera de cada reunião e surpresas nos dias de comunicado e ata.

Para cada reunião t do calendário:

delta_impl_pb
    Δ da meta que a curva de DI precifica para a reunião t, lida em data_corte(t).
    Sem prêmio de risco: a taxa a termo é tratada como expectativa (viés conhecido, pequeno
    no prazo de um mês; registrar no paper).

surpresa_comunicado_pb
    Variação, no dia útil seguinte à decisão (o comunicado sai após o fechamento), da taxa do
    contrato que cobre só a reunião t. Mede a surpresa da DECISÃO (Kuttner, 2001).
surpresa_comunicado_caminho_pb
    A mesma variação no contrato que cobre a reunião t+1. Mede a surpresa sobre o CAMINHO,
    onde entra o forward guidance do comunicado.
surpresa_ata_pb
    Variação no dia da publicação da ata (sai às 8h, antes do pregão) no contrato que cobre t+1.

Fontes:
  • até 2018: swaps DI × pré do SGS (30 dias para a decisão, 60 dias para o caminho e a ata);
  • de 2019 em diante: DI1 da B3 (taxa de ajuste por vencimento).
  • jan–set/2019: as duas, para validar a emenda (saída em v2/dados/di_validacao_emenda.csv).

Uso: .venv/bin/python -m v2.f1_di
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from v2 import fontes
from v2.f0_calendario import SAIDA as CAL, dias_uteis

SAIDA = fontes.RAIZ / "dados" / "di_por_reuniao.csv"
INICIO_B3 = pd.Timestamp("2019-01-02")
FIM_SGS = pd.Timestamp("2019-09-30")
FOLGA = 8  # dias úteis mínimos entre a vigência da nova taxa e o vencimento, para não dividir por ~0

DU = dias_uteis()


def _du_entre(a: pd.Timestamp, b: pd.Timestamp) -> int:
    """Nº de dias úteis em [a, b)."""
    return int(DU.searchsorted(b) - DU.searchsorted(a))


def _proximo_du(d: pd.Timestamp, k: int = 1) -> pd.Timestamp:
    """k-ésimo dia útil depois de d."""
    return DU[DU.searchsorted(d, side="right") + k - 1]


def _du_anterior(d: pd.Timestamp) -> pd.Timestamp:
    return DU[DU.searchsorted(d) - 1]


def _vencimento_util(v: pd.Timestamp) -> pd.Timestamp:
    """O DI1 vence no 1º dia útil do mês. Além do calendário (contratos de 15+ anos, nunca usados
    aqui), devolve a própria data."""
    i = DU.searchsorted(v)
    return DU[i] if i < len(DU) else v


def _taxa_implicita(R: float, cdi: float, N: int, n1: int) -> float:
    """Resolve (1+R)^(N/252) = (1+cdi)^(n1/252) · (1+x)^((N-n1)/252) para x (taxas em % a.a.)."""
    fator = (1 + R / 100) ** (N / 252) / (1 + cdi / 100) ** (n1 / 252)
    return (fator ** (252 / (N - n1)) - 1) * 100


def _escolhe_contrato(di: pd.DataFrame, vigencia: pd.Timestamp, vigencia_seguinte: pd.Timestamp | None):
    """Contrato mais curto que vence ao menos FOLGA dias úteis após `vigencia` e não depois de
    `vigencia_seguinte` (para cobrir uma única reunião). Devolve (linha, flag)."""
    di = di.assign(venc=di["vencimento"].map(_vencimento_util))
    ok = di[di["venc"].map(lambda v: _du_entre(vigencia, v)) >= FOLGA]
    if vigencia_seguinte is not None:
        so_uma = ok[ok["venc"] <= vigencia_seguinte]
        if len(so_uma):
            return so_uma.iloc[0], ""
    if len(ok):
        return ok.iloc[0], "contrato_cobre_2_reunioes"
    return None, "sem_contrato"


# ------------------------------------------------------------------ B3
def b3_implicito(corte, vig, vig_seg, cdi):
    di = fontes.di1_dia(corte.date())
    if di is None:
        return dict(flag="sem_arquivo_b3")
    linha, flag = _escolhe_contrato(di, vig, vig_seg)
    if linha is None:
        return dict(flag=flag)
    N = _du_entre(corte, linha["venc"])
    n1 = _du_entre(corte, vig)
    x = _taxa_implicita(linha["taxa"], cdi, N, n1)
    return dict(delta_impl_pb=(x - cdi) * 100, di_contrato=linha["ticker"], di_taxa=linha["taxa"],
                di_N=N, di_n1=n1, flag=flag)


def b3_variacao(dia, vig, vig_seg):
    """taxa − taxa_ant (pb) do contrato que cobre a reunião de vigência `vig`."""
    di = fontes.di1_dia(dia.date())
    if di is None:
        return np.nan, "sem_arquivo_b3"
    linha, flag = _escolhe_contrato(di, vig, vig_seg)
    if linha is None or pd.isna(linha["taxa_ant"]):
        return np.nan, flag or "sem_taxa_anterior"
    return (linha["taxa"] - linha["taxa_ant"]) * 100, flag


# ------------------------------------------------------------------ SGS
def sgs_implicito(corte, vig, vig_seg, cdi, sw30):
    if corte not in sw30.index:
        return dict(flag="sem_swap_sgs")
    fim = corte + pd.Timedelta(days=30)
    N = _du_entre(corte, fim)
    n1 = _du_entre(corte, vig)
    x = _taxa_implicita(sw30[corte], cdi, N, n1)
    flag = "swap30_cobre_2_reunioes" if (vig_seg is not None and vig_seg < fim) else ""
    return dict(delta_impl_pb=(x - cdi) * 100, di_contrato="swap30_sgs", di_taxa=sw30[corte],
                di_N=N, di_n1=n1, flag=flag)


def sgs_variacao(serie, dia):
    if dia not in serie.index:
        return np.nan
    ant = _du_anterior(dia)
    return (serie[dia] - serie.get(ant, np.nan)) * 100


# ------------------------------------------------------------------ montagem
def montar() -> tuple[pd.DataFrame, pd.DataFrame]:
    cal = pd.read_csv(CAL, parse_dates=["data_decisao", "data_ata", "data_corte", "data_decisao_seguinte"])
    cal["vig"] = cal["data_decisao"].map(_proximo_du)
    cal["vig_seg"] = cal["vig"].shift(-1)
    cal["vig_seg2"] = cal["vig"].shift(-2)
    cdi = fontes.sgs(4389)
    sw30 = fontes.sgs(fontes.SWAPS_SGS[30])
    sw60 = fontes.sgs(fontes.SWAPS_SGS[60])

    linhas, valid = [], []
    for _, r in cal.iterrows():
        corte, vig = r["data_corte"], r["vig"]
        vig_seg = None if pd.isna(r["vig_seg"]) else r["vig_seg"]
        vig_seg2 = None if pd.isna(r["vig_seg2"]) else r["vig_seg2"]
        c = cdi.get(corte, np.nan)
        out = {"nro_reuniao": r["nro_reuniao"], "data_corte": corte.date(), "cdi_corte": c}

        usa_b3 = corte >= INICIO_B3
        if usa_b3:
            out.update(b3_implicito(corte, vig, vig_seg, c))
            out["fonte_di"] = "b3_di1"
        else:
            out.update(sgs_implicito(corte, vig, vig_seg, c, sw30))
            out["fonte_di"] = "sgs_swap"

        # validação da emenda: onde as duas fontes existem, calcula as duas
        if INICIO_B3 <= corte <= FIM_SGS:
            s = sgs_implicito(corte, vig, vig_seg, c, sw30)
            valid.append({"nro_reuniao": r["nro_reuniao"], "data_corte": corte.date(),
                          "b3_pb": out.get("delta_impl_pb"), "sgs_pb": s.get("delta_impl_pb"),
                          "realizado_pb": r["delta_pb"]})

        # surpresas (só para reuniões já ocorridas)
        if vig <= DU[-1] and not pd.isna(r["delta_pb"]):
            if vig >= INICIO_B3:
                out["surpresa_comunicado_pb"], _ = b3_variacao(vig, vig, vig_seg)
                if vig_seg is not None:
                    out["surpresa_comunicado_caminho_pb"], _ = b3_variacao(vig, vig_seg, vig_seg2)
            else:
                out["surpresa_comunicado_pb"] = sgs_variacao(sw30, vig)
                out["surpresa_comunicado_caminho_pb"] = sgs_variacao(sw60, vig)
            ata = r["data_ata"]
            if not pd.isna(ata) and vig_seg is not None:
                if ata >= INICIO_B3:
                    out["surpresa_ata_pb"], _ = b3_variacao(ata, vig_seg, vig_seg2)
                else:
                    out["surpresa_ata_pb"] = sgs_variacao(sw60, ata)
        linhas.append(out)
        print(f"  {r['nro_reuniao']} {corte.date()} {out.get('fonte_di')} "
              f"impl={out.get('delta_impl_pb', np.nan):+.1f} real={r['delta_pb']} {out.get('flag', '')}", flush=True)
    return pd.DataFrame(linhas), pd.DataFrame(valid)


if __name__ == "__main__":
    di, val = montar()
    di.to_csv(SAIDA, index=False)
    val.to_csv(fontes.RAIZ / "dados" / "di_validacao_emenda.csv", index=False)
    print(f"\n-> {SAIDA}")
    print("\nValidação da emenda SGS × B3 (jan–set/2019):")
    print(val.to_string(index=False))
