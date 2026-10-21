"""Coleta de atas do Copom e da Selic — extraído do `atualizar_indice.py`.

Mantém byte-a-byte a lógica já validada do paper (mesmos endpoints, mesma
extração das seções A+B, mesma janela dupla da Selic), apenas reorganizada como
módulo importável pela API. Só é acionado pelo `POST /atualizar`.
"""

from __future__ import annotations

import json
import re
import time

import requests
from bs4 import BeautifulSoup

from core import config

BCB_LISTA = "https://www.bcb.gov.br/api/servico/sitebcb/copom/atas"
BCB_DETALHE = "https://www.bcb.gov.br/api/servico/sitebcb/copom/atas_detalhes"
BCB_SELIC = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados"
HEADERS = {"Accept": "application/json", "User-Agent": "SentimentoCopomAPI/1.0"}


def _html_para_texto(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["sup", "script", "style"]):
        tag.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True))


def _extrair_secoes_ab(texto: str, max_chars: int = 4_500) -> str:
    m_a = re.search(r"A\)\s*Atualiza", texto, re.IGNORECASE)
    m_c = re.search(r"C\)\s*(Discuss|Decis|Voto|Condu)", texto, re.IGNORECASE)
    if m_a:
        ini = m_a.start()
        fim = m_c.start() if m_c else ini + max_chars
        return texto[ini:fim][:max_chars]
    return texto[:max_chars]


def coletar_ata(nro_reuniao: int) -> dict | None:
    """Baixa e limpa uma ata (seções A+B). Retorna `{"data", "texto"}` ou None."""
    for tentativa in range(3):
        try:
            resp = requests.get(BCB_DETALHE, params={"nro_reuniao": nro_reuniao},
                                headers=HEADERS, timeout=30)
            resp.raise_for_status()
            item = resp.json()["conteudo"][0]
            texto = _html_para_texto(item.get("textoAta", ""))
            return {"data": item["dataReferencia"][:10],
                    "texto": _extrair_secoes_ab(texto)}
        except Exception as e:
            if tentativa < 2:
                time.sleep(2 ** tentativa)
            else:
                print(f"  [ERRO] Ata {nro_reuniao}: {e}")
                return None


def atas_publicadas() -> list[int]:
    """Números das últimas reuniões publicadas pela API do BCB."""
    resp = requests.get(BCB_LISTA, params={"quantidade": 12},
                        headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return sorted(item["nroReuniao"] for item in resp.json()["conteudo"])


def atualizar_atas() -> list[int]:
    """Coleta atas ainda não presentes no cache e persiste. Retorna as novas."""
    atas = json.loads(config.ATAS_CACHE.read_text(encoding="utf-8"))
    novas = [n for n in atas_publicadas() if str(n) not in atas]
    for nro in novas:
        doc = coletar_ata(nro)
        if doc:
            atas[str(nro)] = doc
            print(f"  + ata {nro} ({doc['data']}) — {len(doc['texto'])} chars")
    if novas:
        config.ATAS_CACHE.write_text(json.dumps(atas, ensure_ascii=False))
    return [n for n in novas if str(n) in atas]


def atualizar_selic() -> None:
    """Atualiza o cache da Selic (SGS 432) — janela dupla (limite de 10 anos)."""
    janelas = [("01/07/2016", "31/12/2021"), ("01/01/2022", None)]
    dados: list[dict] = []
    for ini, fim in janelas:
        params = {"formato": "json", "dataInicial": ini}
        if fim:
            params["dataFinal"] = fim
        resp = requests.get(BCB_SELIC, params=params, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        dados += resp.json()
    vistos: set[str] = set()
    dados = [d for d in dados if not (d["data"] in vistos or vistos.add(d["data"]))]
    config.SELIC_CACHE.write_text(json.dumps(dados, ensure_ascii=False))
