# v2.0: quanto a Selic muda na próxima reunião

Escopo e decisões: [../docs/ESCOPO_V2.md](../docs/ESCOPO_V2.md). A v1.1 está congelada na tag `v1.1`.

Tudo roda da raiz do repositório com o `.venv` do projeto, sem chave de API.

```bash
.venv/bin/python -m v2.f0_calendario   # calendário ponto-no-tempo -> v2/dados/calendario.csv
.venv/bin/python -m v2.f1_di           # DI: Δ implícita e surpresas -> v2/dados/di_por_reuniao.csv
.venv/bin/python -m v2.f2_baselines    # inércia × Focus × DI -> v2/resultados/f2_baselines.csv
```

| Arquivo | O que é |
|---|---|
| `fontes.py` | Coletores com cache em `dados/raw/`: comunicados e atas (sitebcb), SGS, Focus (Olinda), DI1 da B3 |
| `f0_calendario.py` | Uma linha por reunião desde 2005: decisão, ata, corte de informação, Selic antes e depois |
| `f1_di.py` | Δ Selic implícita no DI na véspera; surpresa do comunicado (decisão e caminho) e da ata |
| `f2_baselines.py` | As réguas sem texto e suas métricas |

## Regras

- **Ponto-no-tempo.** A previsão da reunião *t* só usa dados com data ≤ `data_corte(t)`, o último dia útil antes do primeiro dia da reunião.
- **Cache.** Apagar um arquivo de `dados/raw/` força a recoleta daquele item. Do DI1 da B3 só fica o recorte do dia (`dados/raw/di1/AAAA-MM-DD.csv`), nunca o XML de ~500 MB.

## Cobertura das fontes

| Fonte | Cobre |
|---|---|
| Comunicados e atas | todas as reuniões desde 2005 (104ª em diante) |
| Focus por reunião | reuniões de 2006 em diante |
| Swaps DI × pré, SGS 7801–7806 | até 30/09/2019. Prazos de 30 a 360 dias **inferidos**, validados contra a B3 |
| DI1 da B3 | de jan/2019 em diante |
