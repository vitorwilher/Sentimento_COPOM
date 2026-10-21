"""Testes do eval harness — offline, verdade = Selic realizada."""

from __future__ import annotations

from eval import metrics, run_eval


def test_avaliar_todos_cobre_provedores_e_ensemble():
    res = metrics.avaliar_todos()
    provedores = {m.provedor for m in res}
    assert "ensemble" in provedores
    assert {"gemini", "claude", "openai"}.issubset(provedores)


def test_metricas_em_faixa_valida():
    for m in metrics.avaliar_todos():
        assert 0.0 <= m.r2 <= 1.0
        assert m.rmse >= 0.0
        assert -1.0 <= m.spearman <= 1.0
        assert m.n > 0


def test_spearman_ensemble_positivo():
    """Sinal econômico: atas mais hawkish antecedem mais aperto ⇒ ρ > 0."""
    ens = next(m for m in metrics.avaliar_todos() if m.provedor == "ensemble")
    assert ens.spearman > 0.0


def test_gate_passa_com_threshold_baixo():
    """Com thresholds frouxos, o gate aprova (exit 0)."""
    assert run_eval.run(min_r2=0.0, min_sp=0.0) == 0


def test_gate_reprova_com_threshold_impossivel():
    """Com R² exigido em 0.99, o gate reprova (exit 1) — prova que morde."""
    assert run_eval.run(min_r2=0.99, min_sp=0.0) == 1


def test_gate_default_passa_hoje():
    """Nos dados atuais, os thresholds padrão devem aprovar."""
    assert run_eval.run(run_eval.DEFAULT_MIN_R2, run_eval.DEFAULT_MIN_SPEARMAN) == 0


def test_spearman_helper_sinais():
    """O helper de Spearman: +1 para monotônica crescente, -1 para decrescente."""
    import numpy as np
    x = np.array([1.0, 2.0, 3.0, 4.0])
    assert metrics._spearman(x, x) == 1.0
    assert metrics._spearman(x, x[::-1]) == -1.0
