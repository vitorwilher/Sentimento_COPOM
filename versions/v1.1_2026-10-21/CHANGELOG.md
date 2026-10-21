# Changelog

Histórico de versões do paper *Mesmo Sinal, Calibrações Diferentes: Um Índice de Tom das Atas do Copom com Múltiplos LLMs*.

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).

## [Unreleased]

## [v1.1] — 2026-10-21

Extensão da amostra para 50 atas (reuniões 232–281, ago/2020–set/2026) e reescrita
dos resultados. A tese central se mantém, mas a validação fora da amostra ganha um
achado novo e a vantagem dos LLMs sobre o baseline fica mais estreita.

### Added
- `atualizar_indice.py`: escoragem incremental sem re-render do paper — replica o
  pipeline do qmd (mesmo prompt, mesmos modelos, temperature=0, saída Pydantic).
  Executado em 2026-07-05 para as atas **278** (29/04/2026) e **279** (17/06/2026)
  — Gemini +1,5/+1,5, Claude +1,5/+1,5, OpenAI +2,0/+2,0 — e em 2026-10-21 para as
  atas **280** (05/08/2026) e **281** (16/09/2026) — Gemini +1,5/+0,5,
  Claude +0,5/+0,5, OpenAI +1,0/−0,5.
- Próximo passo novo (item 2): separar postura de direção no *prompt*.

### Changed
- Resumo, abstract, Análise dos Resultados, Surpresa de Comunicação e Conclusão
  reescritos com os números de 50 atas:
  - *In-sample*: R² 0,51 (OpenAI), 0,37 (Claude), 0,30 (Gemini), antes 0,66/0,43/0,35;
    β̂ de +0,34 a +0,59 (diferença de ~71%); correlações entre scores 0,67–0,77.
  - *Holdout* (atas 276–281): cobre a virada para o ciclo de cortes de 2026. Os três
    LLMs leem as atas como *hawkish* enquanto a Selic cai de 15% para 13,75% —
    medem o **nível** de aperto, não a **direção** da mudança. O ranking se inverte
    (OpenAI pior, RMSE out 0,780) e o baseline léxico vence (0,283).
  - *Walk-forward* (n_pred = 30): GPT-4.1-mini 0,451, baseline 0,496, Claude 0,510,
    Gemini 0,511. Só o GPT supera o baseline (~9%, antes ~32%).
  - Z-score: duas reuniões de concordância *dovish* entre os três modelos
    (dez/2025, que antecedeu o primeiro corte, e set/2026).
- Titlepage: versão 1.1, data 21 de outubro de 2026.
- Autoria: o paper passa a ser de autoria individual de Vítor Wilher Rodrigues de Lima
  (trabalho final da Pós-Graduação em Inteligência Artificial e LLMs da PUC-Rio).
- `README.md` substituído pelo README do trabalho final (modelo PUC-Rio); o guia
  técnico anterior (como rodar, estrutura, versões) foi movido para `REPRODUCAO.md`.
- README e ficha de portfólio (`portfolio/sentimento-copom.qmd`) com a tabela nova;
  gráficos e PDF público do portfólio atualizados.

### Fixed
- `jupyter: python3` no YAML das duas edições — o Quarto escolhia o kernel `atlas`
  (venv de outro projeto).
- Caminho do `.env` compartilhado atualizado para `4. Portfolio/Github_Portfolio/`,
  com fallback para o `.env` local.
- Download da Selic (SGS 432) em duas janelas — a API passou a limitar consultas
  JSON a 10 anos.

## [v1.0] — 2026-04-26

Primeira versão completa do paper, com tese empiricamente sustentada em três camadas de validação.

### Estrutura do paper
- Titlepage com logo Análise Macro, título, subtítulo, autor, data e resumo bilíngue (PT/EN)
- Sumário em página própria
- Seções: Introdução, Revisão da Literatura (4 ondas + literatura brasileira), Metodologia e Dados (com justificativa explícita do recorte amostral), Implementação (4 subseções com chunks comentados), Análise dos Resultados, Surpresa de Comunicação (z-score), Próximos Passos (10 itens), Conclusão, Referências

### Pipeline empírico
- Coleta automatizada das atas do Copom via API do BCB, a partir da reunião 232 (agosto de 2020)
- Cache incremental local em três níveis: `atas_cache.json`, `selic_cache.json`, `scores_{gemini,claude,openai}_cache.csv`
- Pré-processamento: extração das seções A (diagnóstico) e B (cenários e riscos) das atas
- Scoring via três LLMs em paralelo: `gemini-flash-lite-latest`, `claude-haiku-4-5`, `gpt-4.1-mini`
- Saída estruturada via Pydantic (`TomAta.score: float`)
- Baseline metodológico: léxico hawkish/dovish em português adaptado ao Copom (espírito Loughran-McDonald)

### Validação empírica em três camadas
1. **Inferência *in-sample*** via `statsmodels.OLS` — reporta β̂, SE, t, p, IC 95%, R² e R²_adj para os 4 modelos
2. **Holdout fora-da-amostra** das últimas 6 reuniões (RMSE e MAE)
3. **Validação cruzada *walk-forward*** com janela expansiva e treino mínimo de 20 atas (n_pred = 26)

### Tabelas e gráficos
- 3 tabelas booktabs com `threeparttable` (notas alinhadas embaixo da tabela, padrão JEL/AER)
- 2 gráficos plotnine (índice calibrado e z-score), persistidos em PNG via chunks silenciosos

### Achados centrais
- OpenAI GPT-4.1-mini lidera nos três exercícios (R² ≈ 0,66 in-sample; RMSE walk-forward 0,357)
- Claude Haiku 4.5 com maior sensibilidade in-sample (β̂ ≈ +0,62) mas overfit claro (RMSE quase dobra fora da amostra)
- Gemini Flash Lite com leitura mais conservadora; empata Claude out-of-sample
- Baseline léxico ganha holdout (artefato de janela calma) mas volta ao último na walk-forward — confirma que vantagem dos LLMs é genuína sobre o ciclo completo
- Tese consolidada: "concordam sobre a direção do tom, divergem sobre a intensidade"

### Referências
- 11 entradas em `referencias.bib` cobrindo: comunicação de bancos centrais (Blinder et al. 2008, Woodford 2003), literatura de dicionários (Loughran & McDonald 2011, Apel & Grimaldi 2012), modelos de tópicos (Hansen, McMahon & Prat 2018, Picault & Renault 2017, Bholat et al. 2015, Hubert & Labondance 2021), LLMs em comunicação de BC (Hansen & Kazinnik 2023, Hansen & McMahon 2016) e literatura brasileira (Caruso 2026)

### Versão pública
- Arquivo paralelo `sentimento_copom_IA_publico.qmd` com `echo: false` no YAML
- Esconde todos os chunks de código mantendo prosa, tabelas e gráficos visíveis
- Destinado ao leitor que quer ler o paper sem ver a implementação

---

## Convenções de versionamento

- **Major (vX.0)** — nova rodada metodológica completa (ex.: probit ordenado, ensemble, modelos maiores, holdout walk-forward implementado)
- **Minor (v1.X)** — novos próximos passos atacados, novos achados empíricos, expansão da revisão de literatura
- **Patch (v1.0.X)** — correções de prosa, ajustes editoriais, correções de bibliografia

Cada release recebe snapshot completo em `versions/vX.Y_YYYY-MM-DD/` para preservar reprodutibilidade.
