# Mesmo Sinal, Calibrações Diferentes: Um Índice de Tom das Atas do Copom com Múltiplos LLMs

### Comparação entre Gemini Flash Lite, Claude Haiku 4.5 e GPT-4.1-mini

#### Aluno: [Vítor Wilher Rodrigues de Lima](https://github.com/vitorwilher)
#### Orientadora: Evelyn Conceição Santos Batista.

---

Trabalho apresentado ao curso de Pós-Graduação em Inteligência Artificial e LLMs da PUC-Rio como pré-requisito para conclusão de curso.

- [Link para o código](sentimento_copom_IA_base.qmd).

- [Link para a monografia](sentimento_copom_IA_publico.pdf).

- Trabalhos relacionados:
    - [Can ChatGPT Decipher Fedspeak? (Hansen e Kazinnik, 2023)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4399406).
    - [Transparency and Deliberation Within the FOMC: A Computational Linguistics Approach (Hansen, McMahon e Prat, 2018)](https://doi.org/10.1093/qje/qjx045).

---

### Resumo

A comunicação dos bancos centrais é, em si, um instrumento de política monetária, e as atas do Comitê de Política Monetária (Copom) do Banco Central do Brasil concentram, em escolhas sutis de linguagem, informação relevante sobre a direção futura da Selic. Este trabalho constrói um Índice de Tom *hawkish-dovish* das atas do Copom utilizando três modelos de linguagem de grande porte (LLMs) — Gemini Flash Lite (Google), Claude Haiku 4.5 (Anthropic) e GPT-4.1-mini (OpenAI) — em um *pipeline* reprodutível em Python, com saída estruturada via Pydantic e cache local incremental que torna a atualização contínua do índice viável a custo marginal próximo de zero.

O mesmo *prompt* é aplicado aos mesmos textos pelos três provedores, e os *scores* brutos são calibrados em pontos percentuais equivalentes da Selic via regressão linear. A robustez é testada em três camadas de validação: inferência *in-sample* (erros-padrão, *p*-valores e intervalos de confiança), *holdout* das últimas seis reuniões e validação cruzada *walk-forward* sobre toda a amostra. Para as 50 reuniões entre a 232 (agosto de 2020) e a 281 (setembro de 2026), o GPT-4.1-mini lidera tanto *in-sample* (R² ≈ 0,51) quanto na *walk-forward* (RMSE 0,451, cerca de 9% melhor que um baseline léxico), seguido do Claude Haiku 4.5 (R² ≈ 0,37) e do Gemini Flash Lite (R² ≈ 0,30).

Os três modelos concordam sobre a direção do tom (correlações de 0,67 a 0,77 entre os *scores*), mas divergem sobre a intensidade com que essa direção se traduz em variação da Selic: a sensibilidade β̂ varia de +0,34 a +0,59 p.p. por unidade de *score*. O *holdout* revela ainda um ponto cego comum aos três LLMs: no início do ciclo de cortes de 2026, a partir de uma Selic de 15%, a linguagem das atas segue restritiva e os modelos leem o nível de aperto monetário, não a direção da próxima decisão.

### Abstract

Central bank communication is, in itself, a monetary policy instrument, and the minutes of Brazil's Monetary Policy Committee (Copom) concentrate, in subtle language choices, meaningful information about the future path of the Selic rate. This work builds a hawkish-dovish Tone Index of Copom minutes using three large language models (LLMs) — Gemini Flash Lite (Google), Claude Haiku 4.5 (Anthropic), and GPT-4.1-mini (OpenAI) — within a reproducible Python pipeline featuring Pydantic-based structured output and incremental local caching, which makes continuous updating of the index viable at near-zero marginal cost.

The same prompt is applied to the same texts by all three providers, and the raw scores are calibrated in percentage-point equivalents of the Selic rate via linear regression. Robustness is tested through three validation layers: in-sample inference (standard errors, p-values, and confidence intervals), a holdout of the last six meetings, and walk-forward cross-validation over the full sample. Over the 50 meetings from 232 (August 2020) to 281 (September 2026), GPT-4.1-mini leads both in-sample (R² ≈ 0.51) and in walk-forward (RMSE 0.451, around 9% better than a lexicon baseline), followed by Claude Haiku 4.5 (R² ≈ 0.37) and Gemini Flash Lite (R² ≈ 0.30).

The three models agree on the direction of the tone (correlations of 0.67 to 0.77 among scores) but diverge on the intensity with which it translates into Selic-rate changes: the sensitivity β̂ ranges from +0.34 to +0.59 percentage points per unit of score. The holdout also reveals a blind spot shared by all three LLMs: at the start of the 2026 easing cycle, from a 15% Selic rate, the minutes' language remains restrictive and the models read the level of monetary tightening, not the direction of the next decision.

### 1. Introdução

Desde a virada da transparência nos bancos centrais, a comunicação passou a ser tratada como instrumento de política monetária em si: o que o comitê diz sobre inflação, expectativas e balanço de riscos move preços de ativos e expectativas antes mesmo da próxima decisão de juros. No Brasil, as atas do Copom são o principal veículo dessa comunicação. A literatura de análise de texto aplicada a bancos centrais evoluiu de dicionários de palavras (no espírito de Loughran e McDonald) para modelos de tópicos e, mais recentemente, para LLMs capazes de ler o tom em contexto — mas a evidência para o português e para o Copom ainda é escassa.

Este trabalho busca mensurar o tom das atas do Copom em uma escala interpretável, calibrada em pontos percentuais da Selic, e responder a uma pergunta prática para quem pretende usar esse tipo de índice em produção: a escolha do provedor de LLM importa? Para isso, três LLMs comerciais de baixo custo leem os mesmos textos com o mesmo *prompt*, e suas leituras são comparadas entre si e contra um baseline léxico.

### 2. Modelagem

O projeto segue o fluxo CRISP-DM. Os dados são coletados automaticamente das APIs públicas do Banco Central: as atas do Copom a partir da reunião 232 (agosto de 2020) e a meta Selic (série SGS 432). Cada ata passa por limpeza de HTML e extração das seções A (atualização da conjuntura) e B (cenários e balanço de riscos), que concentram o diagnóstico do comitê sem a decisão de juros já anunciada. A variável-alvo é a variação da Selic decidida na reunião correspondente.

Na etapa de modelagem, um *prompt* único pede a cada LLM um *score* de −3 (fortemente *dovish*) a +3 (fortemente *hawkish*), com âncoras descritivas para cada nível. A saída é estruturada via Pydantic e orquestrada com LangChain, com `temperature = 0` e cache incremental por provedor — só as atas novas são escoradas a cada atualização. Os *scores* de cada modelo são então calibrados por regressão OLS contra a variação da Selic, o que transforma o tom em pontos percentuais equivalentes e permite comparar sensibilidade (β̂) e ajuste (R²) entre os modelos. Um baseline léxico de termos *hawkish* e *dovish* em português serve de piso de comparação.

### 3. Resultados

Os três LLMs entregam coeficientes positivos e estatisticamente significativos (*p* < 0,01, *t* entre 4,6 e 7,1, *n* = 50), todos acima do baseline léxico em R² e sensibilidade. O GPT-4.1-mini tem o melhor ajuste (R² ≈ 0,51, β̂ ≈ +0,43), o Claude Haiku 4.5 a maior sensibilidade (β̂ ≈ +0,59, R² ≈ 0,37) e o Gemini Flash Lite a leitura mais conservadora (β̂ ≈ +0,34, R² ≈ 0,30). Na validação *walk-forward* (30 predições fora da amostra), o GPT-4.1-mini é o único LLM que supera o baseline léxico (RMSE 0,451 contra 0,496); Claude e Gemini empatam entre si (≈ 0,51), apesar de sensibilidades muito diferentes, o que mostra que maior β̂ *in-sample* não se converte em poder preditivo.

O *holdout* das últimas seis atas coincide com a virada para o ciclo de cortes de 2026 — uma manutenção em 15% seguida de cinco cortes de 0,25 p.p. Nessa janela, os três LLMs continuam atribuindo *scores* *hawkish* enquanto o Copom corta juros, porque as atas seguem descrevendo a política monetária como "restritiva por período prolongado"; o ranking se inverte e o baseline léxico, com predições achatadas, vence. Já a medida de surpresa de comunicação (*z-score*) mostra duas reuniões em que os três modelos convergem para uma leitura mais *dovish* do que o habitual — dezembro de 2025, que antecedeu em três meses o primeiro corte, e setembro de 2026.

### 4. Conclusões

Os LLMs transformam textos complexos e subjetivos em um indicador quantitativo, tempestivo e economicamente interpretável, a custo marginal próximo de zero. A escolha do provedor, porém, não é neutra: os modelos concordam sobre a direção do tom, mas divergem sobre sua intensidade, e só o GPT-4.1-mini mantém vantagem sobre o baseline léxico ao longo do ciclo completo. Para monitorar a direção relativa do tom, qualquer um dos três serve; para usar o índice como variável quantitativa em um modelo macroeconômico, como uma regra de Taylor, a escolha do modelo altera o resultado de forma material.

O principal achado da versão 1.1 é uma limitação: o índice mede o nível de aperto comunicado, não a direção da próxima decisão, e por isso atrasa a leitura de afrouxamentos graduais a partir de juros altos. Os próximos passos incluem separar postura e direção no *prompt*, reespecificar a regressão de forma preditiva (ata em *t* contra a Selic em *t*+1), testar a robustez a variações de *prompt* e construir um índice *ensemble* dos três provedores.

---

Matrícula: 251.100866

Pontifícia Universidade Católica do Rio de Janeiro

Curso de Pós-Graduação em *Inteligência Artificial e LLMs*
