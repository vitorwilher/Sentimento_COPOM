"""F8a — tom das atas (postura e direção), com o mesmo schema dos comunicados (F5).

Motivação: Caruso (Santander, 25/02/2026) encontra que o tom das atas responde pela PROFUNDIDADE
do ciclo (pico do efeito a partir da 5ª reunião), enquanto o comunicado responde pelo momento.
A F5 leu só os comunicados. Aqui, as atas completas (f7_condicoes.atas), para o teste de horizonte
em f8_horizonte.py.

Saída: v2/dados/leitura_atas_{provedor}.csv
Uso:   .venv/bin/python -m v2.f8_atas_tom [--provedor claude|openai] [--teste]
"""

from __future__ import annotations

import sys

import pandas as pd

from v2 import fontes
from v2.f0_calendario import SAIDA as CAL
from v2.f5_comunicados import MODELOS, LeituraComunicado, _cadeia_base
from v2.f7_condicoes import atas

SISTEMA = """Você é um economista que lê atas do Comitê de Política Monetária (Copom) do Banco Central do Brasil.
Leia APENAS o texto fornecido. Não use o que você sabe sobre decisões posteriores do Copom nem sobre a data do texto.
Separe duas coisas diferentes:
- a POSTURA: quão restritiva a política está agora (nível);
- a DIREÇÃO: o que a ata sinaliza para a PRÓXIMA reunião (movimento).
Uma política muito restritiva pode sinalizar corte; uma política expansionista pode sinalizar alta.
Se a ata não sinaliza nada sobre a próxima reunião, use direcao_proxima = "indefinida".
O trecho de guidance deve ser uma citação literal curta (até 300 caracteres)."""


def ler(provedor: str, nros: list[int]) -> pd.DataFrame:
    import time
    arq = fontes.RAIZ / "dados" / f"leitura_atas_{provedor}.csv"
    feito = pd.read_csv(arq) if arq.exists() else pd.DataFrame(columns=["nro_reuniao"])
    txt = atas(nros)
    cadeia = _cadeia_base(provedor, max_tokens=1500).with_structured_output(LeituraComunicado)
    linhas = feito.to_dict("records")
    for n in nros:
        if n in set(feito["nro_reuniao"]) or not txt.get(str(n)):
            continue
        if provedor == "gemini":
            time.sleep(4.5)
        try:
            r: LeituraComunicado = cadeia.invoke([("system", SISTEMA), ("human", f"Ata:\n\n{txt[str(n)]}")])
        except Exception as e:  # registra e segue
            print(f"  {provedor} {n}: ERRO {type(e).__name__}", flush=True)
            continue
        d = r.model_dump()
        d["trecho_guidance"] = d["trecho_guidance"][:400]
        linhas.append({"nro_reuniao": n, "modelo": MODELOS[provedor], **d})
        print(f"  {provedor} {n}: postura={r.postura:+d} dir={r.direcao_proxima} mag={r.magnitude_pb} "
              f"guid={r.guidance_explicito} cond={r.condicionalidade}", flush=True)
        pd.DataFrame(linhas).to_csv(arq, index=False)
    return pd.read_csv(arq)


if __name__ == "__main__":
    nros = pd.read_csv(CAL)["nro_reuniao"].astype(int).tolist()
    if "--teste" in sys.argv:
        nros = [200, 276, 282]
    provs = [sys.argv[sys.argv.index("--provedor") + 1]] if "--provedor" in sys.argv else ["claude", "openai"]
    for p in provs:
        ler(p, nros)
