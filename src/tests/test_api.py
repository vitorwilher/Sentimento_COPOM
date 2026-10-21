"""Testes do MVP da API — 100% offline, sobre os caches já escorados.

Nenhum teste chama LLM ou rede: exercitam apenas o caminho de leitura (o MVP),
que serve os scores já produzidos pelo pipeline do paper. Rodar::

    cd src && pytest -q
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from core import config
from data import repo
from index import calibra, selic, tone_index

client = TestClient(app)


# --------------------------------------------------------------------------- #
# Repositório (leitura dos caches)
# --------------------------------------------------------------------------- #
def test_ha_reunioes_em_cache():
    assert len(repo.reunioes_disponiveis()) > 0


def test_todos_provedores_tem_scores():
    scores = repo.carregar_scores()
    for prov in config.PROVEDORES:
        assert prov in scores and scores[prov], f"{prov} sem scores"


def test_scores_dentro_da_escala():
    for scores in repo.carregar_scores().values():
        for s in scores.values():
            assert config.SCORE_MIN <= s <= config.SCORE_MAX


# --------------------------------------------------------------------------- #
# Endpoints de leitura
# --------------------------------------------------------------------------- #
def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["reunioes"] == len(repo.reunioes_disponiveis())


def test_modelos():
    r = client.get("/modelos")
    assert r.status_code == 200
    provedores = {m["provedor"] for m in r.json()}
    assert provedores == set(config.PROVEDORES)


def test_indice_estrutura_e_ordenacao():
    r = client.get("/indice")
    assert r.status_code == 200
    j = r.json()
    assert j["n"] == len(j["pontos"]) > 0
    nros = [p["nro_reuniao"] for p in j["pontos"]]
    assert nros == sorted(nros), "série deve vir ordenada por reunião"


def test_indice_ensemble_e_media_dos_provedores():
    """O ensemble de um ponto é a média dos scores dos provedores disponíveis."""
    r = client.get("/indice")
    ponto = r.json()["pontos"][-1]
    nro = ponto["nro_reuniao"]
    por_prov = repo.carregar_scores()
    vals = [s[nro] for s in por_prov.values() if nro in s]
    assert ponto["ensemble"] == pytest.approx(sum(vals) / len(vals))


def test_score_reuniao_ok():
    nro = repo.reunioes_disponiveis()[-1]
    r = client.get(f"/score/{nro}")
    assert r.status_code == 200
    j = r.json()
    assert j["nro_reuniao"] == nro
    assert j["scores"], "deve ter ao menos um provedor"
    scores = [s["score"] for s in j["scores"]]
    assert j["ensemble"] == pytest.approx(sum(scores) / len(scores))


def test_score_reuniao_inexistente_404():
    r = client.get("/score/999999")
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# Calibração na Selic
# --------------------------------------------------------------------------- #
def test_calibragem_endpoint():
    r = client.get("/calibragem")
    assert r.status_code == 200
    linhas = r.json()
    provedores = {l["provedor"] for l in linhas}
    assert "ensemble" in provedores
    assert set(config.PROVEDORES).issubset(provedores)


def test_calibragem_beta_positivo():
    """Sinal econômico: tom mais hawkish ⇒ ΔSelic maior. β̂ deve ser > 0."""
    ens = calibra.calibrar_ensemble()
    assert ens["beta"] > 0, "β̂ do ensemble deveria ser positivo (hawkish→alta)"
    assert 0.0 <= ens["r2"] <= 1.0


def test_selic_equivalente_monotonico():
    """Traduzir score→Selic deve ser monotônico crescente (β̂>0)."""
    assert calibra.selic_equivalente(2.0) > calibra.selic_equivalente(-2.0)


def test_variacao_selic_conhecida_e_finita():
    """A ΔSelic de uma reunião com data válida é um float finito."""
    nro = repo.reunioes_disponiveis()[-1]
    data = repo.data_da_reuniao(nro)
    if data:
        v = selic.variacao_na_reuniao(data)
        assert isinstance(v, float)
        assert -5.0 < v < 5.0  # variação de Selic por reunião é modesta
