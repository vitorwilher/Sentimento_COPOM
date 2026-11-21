"""Gráficos da v2.0: uma função por figura, usadas pelo paper (v2/paper/paper.qmd) e por este script.

Cada função lê só os CSVs de v2/dados e v2/resultados e devolve a Figure. Nada é reestimado.
Paleta (dataviz, validada para daltonismo): azul, laranja e verde-água; o verde-água tem contraste
abaixo de 3:1 com o fundo, por isso toda figura que o usa traz os valores escritos nas marcas.

Uso: .venv/bin/python -m v2.figuras        (grava PNGs em v2/figuras/)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import sys

import matplotlib

if "ipykernel" not in sys.modules:  # no Jupyter (paper), mantém o backend inline
    matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import statsmodels.api as sm  # noqa: E402

from v2 import fontes  # noqa: E402

D, R = fontes.RAIZ / "dados", fontes.RAIZ / "resultados"
SAIDA = fontes.RAIZ / "figuras"
AZUL, LARANJA, VERDE = "#2a78d6", "#eb6834", "#1baf7a"
AZUL_CLARO, CINZA, TINTA, GRADE = "#9ec5f4", "#8a8a85", "#2b2b28", "#e6e6e2"

plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": CINZA, "axes.labelcolor": TINTA, "xtick.color": TINTA,
                     "ytick.color": TINTA, "axes.grid": True, "grid.color": GRADE, "grid.linewidth": 0.6,
                     "axes.titlesize": 10, "axes.titleweight": "bold", "axes.titlelocation": "left",
                     "legend.frameon": False, "savefig.dpi": 200, "savefig.bbox": "tight"})


def br(x, d=0):
    return f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def passo(x):
    return np.round(np.asarray(x, float) / 25) * 25


def acerto(p, y):
    p, y = np.asarray(p, float), np.asarray(y, float)
    ok = ~np.isnan(p) & ~np.isnan(y)
    return 100 * (passo(p[ok]) == y[ok]).mean()


def _barras_h(ax, nomes, series, cores, rotulos, fmt=lambda v: br(v) + "%", xlim=None):
    """Barras horizontais agrupadas com valor escrito na ponta de cada barra."""
    k = len(series)
    alt = 0.8 / k
    y = np.arange(len(nomes))[::-1]
    for j, (vals, cor, rot) in enumerate(zip(series, cores, rotulos)):
        pos = y + (k - 1) / 2 * alt - j * alt
        ax.barh(pos, vals, alt * 0.9, color=cor, label=rot)
        escala = (xlim[1] - xlim[0]) if xlim else max(map(np.nanmax, series))
        for p_, v in zip(pos, vals):
            if not np.isnan(v):
                ax.text(v + np.sign(v or 1) * escala * 0.01, p_, fmt(v), va="center",
                        ha="left" if v >= 0 else "right", fontsize=7.5, color=TINTA)
    ax.set_yticks(y, nomes)
    ax.grid(axis="y", visible=False)
    if xlim:
        ax.set_xlim(*xlim)


def _legenda_topo(ax, ncol=3):
    """Legenda acima do gráfico, fora da área das barras."""
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=ncol, fontsize=8, borderaxespad=0.3)


# ------------------------------------------------------------------ F2: a régua
def fig_regua():
    f2 = pd.read_csv(R / "f2_baselines.csv")
    rec = {"2005–2026": "2005–2026", "2019–2026": "2019–2026 (DI B3)", "Viradas de ciclo": "pontos de virada"}
    prev = ["inércia", "Focus (mediana)", "DI implícito"]
    nomes = ["Repetir a última decisão", "Focus (mediana)", "DI"]
    series = [[f2.loc[(f2.recorte == r) & (f2.baseline == p), "acerto_exato_%"].iloc[0] for p in prev] for r in rec.values()]
    fig, ax = plt.subplots(figsize=(7.5, 3.4))
    _barras_h(ax, nomes, series, [AZUL, LARANJA, VERDE], list(rec), xlim=(0, 110))
    ax.set_xlabel("acerto do passo exato da Selic (%)")
    ax.set_title("Na véspera, o mercado acerta quase todas as decisões", pad=22)
    _legenda_topo(ax)
    return fig


def fig_horizonte():
    b = pd.read_csv(D / "base_dia_ata.csv", parse_dates=["data_ata"])
    b = b[b["data_ata"] >= "2019-10-01"].dropna(subset=["di_ata", "di_vespera", "delta_t1"])
    nomes = ["Repetir a última decisão", "Focus", "DI"]
    ata = [acerto(b["inercia"], b["delta_t1"]), acerto(b["focus_ata"], b["delta_t1"]), acerto(b["di_ata"], b["delta_t1"])]
    f2 = pd.read_csv(R / "f2_baselines.csv")
    r = "2019–2026 (DI B3)"
    ves = [f2.loc[(f2.recorte == r) & (f2.baseline == p), "acerto_exato_%"].iloc[0] for p in ("inércia", "Focus (mediana)")]
    ves.append(acerto(b["di_vespera"], b["delta_t1"]))
    fig, ax = plt.subplots(figsize=(7.5, 2.8))
    _barras_h(ax, nomes, [ata, ves], [LARANJA, AZUL], ["Dia da ata anterior (~6 semanas antes)", "Véspera da reunião"], xlim=(0, 110))
    ax.set_xlabel("acerto do passo exato (%), 2019–2026")
    ax.set_title("A informação chega entre a ata e a véspera", pad=22)
    _legenda_topo(ax, 2)
    return fig


def fig_linha_tempo():
    b = pd.read_csv(D / "base_dia_ata.csv", parse_dates=["data_ata"])
    cal = pd.read_csv(D / "calendario.csv", parse_dates=["data_decisao"]).set_index("nro_reuniao")
    b = b[b["data_ata"] >= "2019-10-01"].copy()
    b["data"] = b["nro_t1"].map(cal["data_decisao"])
    fig, ax = plt.subplots(figsize=(7.5, 3.4))
    ax.bar(b["data"], b["delta_t1"], width=18, color=GRADE, edgecolor=CINZA, linewidth=0.4, label="Decisão do Copom")
    ax.scatter(b["data"], b["di_ata"], s=16, color=LARANJA, zorder=3, label="DI no dia da ata anterior")
    ax.scatter(b["data"], b["di_vespera"], s=16, color=AZUL, zorder=4, label="DI na véspera")
    ax.axhline(0, color=TINTA, lw=0.8)
    ax.set_ylabel("ΔSelic (pb)")
    ax.set_title("Decisões do Copom e o que o DI precificava, 2019–2026")
    ax.legend(loc="upper left", fontsize=8, ncol=3)
    return fig


# ------------------------------------------------------------------ F3/F4: eventos
def fig_evento():
    f3s = pd.read_csv(R / "f3_evento.csv").set_index("grupo")
    f3b = pd.read_csv(R / "f3_evento_b3.csv").set_index("grupo")
    f4 = pd.read_csv(R / "f4_evento_dados.csv").set_index("grupo")
    linhas = [("Comunicado (2006–2019)", f3s.loc["comunicado"]), ("Ata (2006–2019)", f3s.loc["ata"]),
              ("Ata (2019–2026)", f3b.loc["ata"]), ("Discurso da diretoria (2006–2019)", f3s.loc["relevante"]),
              ("Discurso da diretoria (2019–2026)", f3b.loc["relevante"])]
    linhas += [(f"{g} (2017–2026)", f4.loc[g]) for g in ["IPCA", "IPCA-15", "PIM", "PMS", "PIB", "PNAD", "PMC"]]
    fig, ax = plt.subplots(figsize=(7.5, 4))
    yy = np.arange(len(linhas))[::-1]
    for y_, (nome, r) in zip(yy, linhas):
        sig = r["p_valor_perm"] < 0.05
        ax.barh(y_, r["razao_vs_sem_evento"], 0.6, color=AZUL if sig else AZUL_CLARO)
        ax.text(r["razao_vs_sem_evento"] + 0.03, y_, br(r["razao_vs_sem_evento"], 2) + "×", va="center", fontsize=7.5)
    ax.axvline(1, color=TINTA, lw=1)
    ax.set_yticks(yy, [n for n, _ in linhas])
    ax.set_xlabel("movimento médio da taxa da próxima reunião, relativo a um dia sem evento")
    ax.set_title("Só o comunicado move a curva (escuro: p < 0,05)")
    ax.grid(axis="y", visible=False)
    return fig


# ------------------------------------------------------------------ F5: comunicados
def fig_comunicado():
    b = pd.read_csv(D / "base_dia_ata.csv").dropna(subset=["com_sinal", "delta_t1"])
    itens = [("DI", "di_ata", AZUL), ("Focus", "focus_ata", AZUL), ("Repetir a última decisão", "inercia", AZUL),
             ("Comunicado: Claude", "sinal_claude", LARANJA), ("Comunicado: GPT", "sinal_openai", LARANJA),
             ("Comunicado: Gemini", "sinal_gemini", LARANJA)]
    fig, ax = plt.subplots(figsize=(7.5, 3))
    yy = np.arange(len(itens))[::-1]
    for y_, (nome, col, cor) in zip(yy, itens):
        v = acerto(b[col], b["delta_t1"])
        ax.barh(y_, v, 0.6, color=cor)
        ax.text(v + 1, y_, br(v) + "%", va="center", fontsize=7.5)
    ax.set_yticks(yy, [i[0] for i in itens])
    ax.set_xlim(0, 100)
    ax.set_xlabel("acerto do passo exato na reunião seguinte, com a informação do dia da ata (%)")
    ax.set_title("O comunicado lido por LLMs acerta menos que o mercado")
    ax.grid(axis="y", visible=False)
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=AZUL, label="Mercado e inércia"), Patch(color=LARANJA, label="Comunicado lido por LLM")],
              loc="lower right", fontsize=8)
    return fig


# ------------------------------------------------------------------ F6: fundamentos
def fig_fundamentos():
    fa = pd.read_csv(D / "base_fundamentos.csv").dropna(subset=["gap_taylor_pb", "gap_alvo_pb", "gap_alvo_dsge_pb", "aperto_pp", "delta_t1"])
    itens = [("Regra de Taylor suavizada (MPP)", "gap_taylor_pb"), ("Alvo da regra, neutro HP (MPP)", "gap_alvo_pb"),
             ("Alvo da regra, neutro do DSGE", "gap_alvo_dsge_pb"), ("Aperto vs neutro (DSGE)", "aperto_pp"),
             ("DI no dia da ata", "di_ata")]
    seg = [fa[c].corr(fa["delta_t1"]) for _, c in itens]
    cor = [fa[c].corr(fa["inercia"]) for _, c in itens]
    fig, ax = plt.subplots(figsize=(7.5, 3.4))
    _barras_h(ax, [i[0] for i in itens], [seg, cor], [AZUL, LARANJA],
              ["Correlação com a decisão SEGUINTE", "Correlação com a decisão CORRENTE (inércia)"],
              fmt=lambda v: br(v, 2), xlim=(-1, 1.15))
    ax.axvline(0, color=TINTA, lw=0.8)
    ax.set_xlabel("correlação")
    ax.set_title("Os fundamentos dos modelos medem o ciclo passado, não o próximo passo", pad=22)
    _legenda_topo(ax, 2)
    return fig


# ------------------------------------------------------------------ F7: índice de condicionalidade
def _ic():
    ic = pd.read_csv(D / "indice_condicionalidade.csv", parse_dates=["data_ata", "data_corte"])
    return ic.merge(pd.read_csv(D / "base_dia_ata.csv")[["nro_t1", "di_vespera"]], on="nro_t1", how="left")


def fig_indice_dispersao():
    ic = _ic()
    ok = ic.dropna(subset=["indice_ata", "deriva"])
    c = ic[ic["nro_t1"] == 282].iloc[0]
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    ax.scatter(ok["indice_ata"], ok["deriva"], s=18, color=AZUL, alpha=0.6, edgecolor="white", linewidth=0.5)
    m = sm.OLS(ok["deriva"], sm.add_constant(ok["indice_ata"])).fit()
    xs = np.linspace(ok["indice_ata"].min(), ok["indice_ata"].max(), 50)
    ax.plot(xs, m.params.iloc[0] + m.params.iloc[1] * xs, color=TINTA, lw=1.2)
    ax.scatter([c["indice_ata"]], [c["deriva"]], s=60, color=LARANJA, edgecolor="white", linewidth=1.5, zorder=3)
    ax.annotate("282ª (nov/2026)", (c["indice_ata"], c["deriva"]), xytext=(8, 8), textcoords="offset points", fontsize=8)
    ax.axhline(0, color=CINZA, lw=0.8)
    ax.axvline(0, color=CINZA, lw=0.8)
    ax.set_xlabel("Índice de Condicionalidade da ata (desvios-padrão)")
    ax.set_ylabel("deriva do DI até a véspera (pb)")
    ax.set_title("Quando o que o BC monitora piora, o DI sobe até a véspera")
    return fig


def fig_indice_serie():
    ic = _ic()
    ok = ic[ic["data_ata"] >= "2016-01-01"].dropna(subset=["indice_ata"])
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(7.5, 4.2), sharex=True, gridspec_kw={"hspace": 0.25})
    a1.bar(ok["data_corte"], ok["indice_ata"], width=20, color=np.where(ok["indice_ata"] >= 0, LARANJA, AZUL))
    a1.axhline(0, color=TINTA, lw=0.8)
    a1.set_ylabel("índice (dp)")
    a1.set_title("Índice de Condicionalidade (laranja: condições pioraram; azul: melhoraram)")
    d = ok.dropna(subset=["deriva"])
    a2.bar(d["data_corte"], d["deriva"], width=20, color=CINZA)
    a2.axhline(0, color=TINTA, lw=0.8)
    a2.set_ylabel("pb")
    a2.set_title("Deriva do DI entre a ata e a véspera")
    return fig


NOMES_VAR = {"expectativas_curto": "Expectativas (ano corrente e seguinte)", "expectativas_longo": "Expectativas (2 a 4 anos)",
             "inflacao_corrente": "IPCA 12 meses", "inflacao_servicos": "Inflação de serviços", "nucleos": "Núcleos",
             "atividade": "Atividade (IBC-Br)", "mercado_trabalho": "Desemprego", "cambio": "Câmbio",
             "petroleo": "Petróleo", "fiscal": "Resultado primário esperado", "juros_externos": "Juros dos EUA"}


def fig_contribuicoes(nro_t1: int = 282):
    c = _ic().set_index("nro_t1").loc[nro_t1]
    cs = c.filter(like="contrib_").astype(float)
    cs = cs[cs.abs() >= 0.005].sort_values()
    fig, ax = plt.subplots(figsize=(7.5, 0.35 * len(cs) + 1))
    ax.barh(range(len(cs)), cs.values, 0.6, color=[LARANJA if v > 0 else AZUL for v in cs.values])
    for i, v in enumerate(cs.values):
        ax.text(v + (0.01 if v >= 0 else -0.01), i, br(v, 2), va="center", ha="left" if v >= 0 else "right", fontsize=7.5)
    ax.set_yticks(range(len(cs)), [NOMES_VAR[k.replace("contrib_", "")] for k in cs.index])
    ax.axvline(0, color=TINTA, lw=0.8)
    lo, hi = min(cs.min(), 0), max(cs.max(), 0)
    ax.set_xlim(lo - 0.12 * (hi - lo), hi + 0.08 * (hi - lo))
    ax.set_xlabel("contribuição ao índice (laranja: pede mais aperto)")
    ax.set_title(f"Reunião {nro_t1}: o que mudou entre a ata e a véspera (índice {br(c['indice_ata'], 2)})")
    ax.grid(axis="y", visible=False)
    return fig


# ------------------------------------------------------------------ F8: horizontes
def fig_horizonte_tom():
    """O tom antecipa o erro do mercado sem controles, mas não com a previsão do mercado e a inércia."""
    from scipy.stats import norm
    t = pd.read_csv(R / "f8_horizonte.csv")
    rb = pd.read_csv(R / "f8_robustez.csv")
    tons = [("com_postura", "Postura do comunicado", AZUL), ("ata_postura", "Postura da ata", LARANJA)]
    fig, axs = plt.subplots(1, 2, figsize=(7.5, 3.2), sharey=True)
    for ax, tit, fonte in zip(axs, ("Sem controles", "Controlando pela previsão do mercado\ne pela última decisão (inércia)"),
                              ("simples", "robusto")):
        for k, (c, nome, cor) in enumerate(tons):
            if fonte == "simples":
                d = t[(t["tom"] == c) & (t["alvo"] == "erro")].sort_values("h")
                coef, p = d["coef_pb_por_unidade"], d["p"]
            else:
                d = rb[rb["tom"] == c].sort_values("h")
                coef, p = d["coef_tom"], d["p_tom"]
            ep = (coef / norm.isf(p / 2)).abs()
            x = d["h"] + (k - 0.5) * 0.3
            ax.errorbar(x, coef, yerr=1.645 * ep, fmt="o", color=cor, ms=4, capsize=2, lw=1, label=nome)
        ax.axhline(0, color=TINTA, lw=0.8)
        ax.set_xticks([1, 2, 4, 6, 8])
        ax.set_xlabel("horizonte (reuniões à frente)")
        ax.set_title(tit, fontsize=9)
    axs[0].set_ylabel("pb de erro do mercado por ponto de postura\n(IC 90%)")
    axs[0].legend(fontsize=7.5, loc="upper left")
    fig.suptitle("O tom parece prever o erro do mercado, mas era o ciclo", x=0.01, ha="left", fontsize=10, fontweight="bold")
    fig.tight_layout()
    return fig


def fig_horizonte_rmse():
    """RMSE fora da amostra por horizonte: mercado, + inércia, + inércia + tom da ata."""
    rb = pd.read_csv(R / "f8_robustez.csv")
    d = rb[(rb["tom"] == "ata_postura") & rb["rmse_mercado"].notna()].sort_values("h")
    fig, ax = plt.subplots(figsize=(7.5, 3))
    for col, nome, cor, mk in (("rmse_mercado", "DI no dia da ata", AZUL, "o"),
                               ("rmse_mais_inercia", "DI + última decisão", VERDE, "s"),
                               ("rmse_mais_inercia_tom", "DI + última decisão + tom da ata", LARANJA, "^")):
        ax.plot(d["h"], d[col], marker=mk, color=cor, lw=2, ms=6, label=nome)
    ax.set_xticks(d["h"])
    ax.set_xlabel("horizonte (reuniões à frente)")
    ax.set_ylabel("erro de previsão fora da amostra\n(RMSE, pb)")
    ax.set_title("Fora da amostra, a inércia ajuda no curto prazo; o tom, nunca")
    ax.legend(fontsize=8, loc="upper left")
    return fig


# ------------------------------------------------------------------ F9: clareza
def fig_clareza():
    """Divergência dos analistas do Focus antes do comunicado e depois da ata, por clareza do comunicado.

    Mostra os dados, não coeficientes: média do desvio-padrão das projeções do Focus para a Selic da
    reunião seguinte, na véspera da reunião (antes do comunicado) e no dia da ata (depois).
    """
    d = pd.read_csv(D / "base_clareza.csv", parse_dates=["data_ata"]).dropna(
        subset=["disp_antes", "disp_depois", "com_guidance", "com_cond"])
    grupos = {
        "O comunicado sinaliza os próximos passos?": pd.cut(
            d["com_guidance"], [-0.1, 0.2, 0.8, 1.1], labels=["Não", "Os LLMs divergem", "Sim, explicitamente"]),
        "Quanto o próximo passo depende de dados?": pd.cut(
            d["com_cond"], [0, 2.0, 2.67, 3.1], labels=["Pouco (compromisso)", "Médio", "Totalmente"]),
    }
    fig, axs = plt.subplots(2, 1, figsize=(8, 5.4), sharex=True, gridspec_kw={"hspace": 0.45})
    for ax, (tit, g) in zip(axs, grupos.items()):
        m = d.groupby(g, observed=True).agg(n=("disp_antes", "size"), antes=("disp_antes", "mean"),
                                             depois=("disp_depois", "mean"),
                                             ano=("data_ata", lambda x: int(x.dt.year.median())))
        y = np.arange(len(m))[::-1]
        for y_, (nome, r) in zip(y, m.iterrows()):
            a, b = r["antes"], r["depois"]
            ax.annotate("", xy=(b, y_), xytext=(a, y_),
                        arrowprops=dict(arrowstyle="-|>", color=CINZA, lw=1.4, shrinkA=6, shrinkB=6))
            ax.scatter(a, y_, s=60, color=AZUL_CLARO, zorder=3)
            ax.scatter(b, y_, s=60, color=AZUL, zorder=3)
            esq, dir_ = (b, a) if b <= a else (a, b)
            ax.text(esq - 0.25, y_, br(esq, 1), ha="right", va="center", fontsize=8,
                    color=AZUL if esq == b else CINZA)
            ax.text(dir_ + 0.25, y_, br(dir_, 1), ha="left", va="center", fontsize=8,
                    color=AZUL if dir_ == b else CINZA)
            ax.text(1.01, y_, f"{'+' if b >= a else '−'}{br(abs(b - a), 1)} pb",
                    transform=ax.get_yaxis_transform(), va="center", fontsize=9, fontweight="bold", color=TINTA)
        ax.set_yticks(y, [f"{n}  ({int(r.n)} reuniões; ano mediano {int(r.ano)})" for n, r in m.iterrows()], fontsize=8.5)
        ax.set_ylim(-0.6, len(m) - 0.4)
        ax.set_title(tit, fontsize=9.5)
        ax.grid(axis="y", visible=False)
    axs[1].set_xlim(11, 22)
    axs[1].set_xlabel("divergência entre os analistas do Focus sobre a Selic da reunião seguinte (desvio-padrão, pb)")
    axs[0].text(1.01, 1.02, "mudança", transform=axs[0].transAxes, fontsize=8, color=CINZA)
    from matplotlib.lines import Line2D
    axs[0].legend(handles=[Line2D([], [], marker="o", ls="", color=AZUL_CLARO, ms=8, label="Véspera da reunião (antes do comunicado)"),
                           Line2D([], [], marker="o", ls="", color=AZUL, ms=8, label="Dia da ata (depois da comunicação)")],
                  loc="lower left", bbox_to_anchor=(0, 1.12), ncol=2, fontsize=8.5)
    fig.suptitle("Com guidance explícito, os analistas divergem um pouco menos depois da comunicação",
                 x=0.01, ha="left", fontsize=10.5, fontweight="bold", y=1.0)
    fig.text(0.01, -0.04, "Média por grupo de reuniões, 2006–2026. Com controles (tamanho da decisão, surpresa no DI e presidência do BC),\n"
             "a diferença entre os grupos não é estatisticamente significativa: os comunicados com guidance se concentram nos anos recentes.",
             fontsize=7.5, color=CINZA)
    return fig


FIGURAS = {"01_regua": fig_regua, "02_horizonte": fig_horizonte, "03_linha_tempo": fig_linha_tempo,
           "04_evento": fig_evento, "05_comunicado": fig_comunicado, "06_fundamentos": fig_fundamentos,
           "07_indice_dispersao": fig_indice_dispersao, "08_indice_serie": fig_indice_serie,
           "09_contribuicoes_282": fig_contribuicoes, "10_horizonte_tom": fig_horizonte_tom, "11_horizonte_rmse": fig_horizonte_rmse, "12_clareza": fig_clareza}

if __name__ == "__main__":
    SAIDA.mkdir(exist_ok=True)
    for nome, f in FIGURAS.items():
        try:
            f().savefig(SAIDA / f"{nome}.png")
            plt.close("all")
            print("ok  ", nome)
        except Exception as e:  # F8/F9 dependem de resultados que podem ainda não existir
            print("FALTA", nome, type(e).__name__, e)
