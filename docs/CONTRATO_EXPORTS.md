# Contrato de exportação: MPP_BCB e DSGE_Brasil → Sentimento_COPOM v2.0

21/11/2026. Para abrir **uma sessão em cada projeto** (MPP_BCB e DSGE_Brasil) e entregar este arquivo como pedido. Cada projeto segue as regras do próprio CLAUDE.md. Nada aqui autoriza editar o Sentimento_COPOM a partir deles, nem o contrário.

## Por que

A v2.0 do Sentimento_COPOM testou se o texto do BCB (comunicado, ata, discursos) e os dados do IBGE preveem a próxima decisão do Copom além do mercado de DI. A resposta foi não. Ver `docs/ESCOPO_V2.md`, seções 8 a 8.3.

Resta uma hipótese: **os fundamentos, traduzidos por um modelo, antecipam para onde o DI vai** entre a ata e a véspera da reunião seguinte. O DI acerta 61% do passo no dia da ata e 97% na véspera. A pergunta é se, no dia da ata, a distância da Selic até a regra de Taylor do MPP, ou o aperto em relação ao juro neutro do DSGE, já indica a correção que o mercado faria depois.

## Entrada comum

`Sentimento_COPOM/v2/dados/calendario.csv`, uma linha por reunião (104ª a 282ª). Colunas usadas:

| Coluna | O que é |
|---|---|
| `nro_reuniao` | número da reunião *t* |
| `data_ata` | dia em que a ata de *t* foi publicada (8h). **Data de informação** do teste |
| `nro_seguinte` | número da reunião *t+1*, a reunião-alvo |
| `selic_depois` | meta Selic vigente depois da decisão de *t* (% a.a.) |

Ler o arquivo, não copiá-lo. Amostra a entregar: todas as linhas com `data_ata` de 2006 em diante (~170).

## Regra de ponto-no-tempo (vale para os dois)

Para cada `data_ata`, usar **só** o que estava publicado até essa data:

- **Séries mensais** (IPCA, câmbio, Focus): observações até `data_ata`. O Focus é diário: usar a última leitura com `Data ≤ data_ata`.
- **Séries trimestrais** (PIB, hiato): só os trimestres cujo dado já tinha saído. Regra simples: o PIB do trimestre *q* sai ~60 dias após o fim de *q* (o calendário exato está na API do IBGE, produto 9300, desde 2017).
- **Revisões de dados.** Não há safras históricas dos dados revisados. Usar a série atual, cortada na data, e **declarar** isso no export (`metodo`).
- **Filtros.** HP, Kalman e qualquer outro filtro devem ser **unilaterais**, calculados só com a amostra até a data. Nunca o suavizador, nem o HP de amostra inteira.

## Saída

`<projeto>/exports/por_reuniao.csv`, formato longo:

| Coluna | Tipo | O que é |
|---|---|---|
| `nro_reuniao_alvo` | int | `nro_seguinte` do calendário (*t+1*) |
| `data_info` | data | `data_ata` de *t* |
| `data_ultimo_dado` | data | última observação efetivamente usada |
| `variavel` | texto | nome da variável (tabelas abaixo) |
| `valor` | número | valor |
| `li`, `ls` | número | banda de 90% quando houver, senão vazio |
| `metodo` | texto | o que foi feito e o que fica contaminado (ex.: `reestimado_ate_2015T2; dados_revisados`) |
| `vintage` | texto | commit do git e data da geração |

Uma linha por (reunião-alvo, variável). Linhas sem cálculo possível ficam com `valor` vazio e o motivo em `metodo`.

## MPP_BCB (v2, `small_scale_model_v2.py`)

Decisão já tomada (ESCOPO_V2, seção 9, item 3): **reestimar por safra**. Para cada `data_info`, estimar as 7 equações com a amostra até o último trimestre disponível.

| `variavel` | Definição |
|---|---|
| `selic_taylor` | Selic que a regra de Taylor estimada indica para o trimestre corrente/seguinte, com as defasagens observadas e a expectativa Focus em `data_info` (% a.a.) |
| `gap_taylor_pb` | (`selic_taylor` − `selic_depois`) × 100 |
| `theta3` | coeficiente de reação ao desvio das expectativas na safra (para ver a estabilidade) |
| `selic_alvo` | **(adendo de 21/11)** a Selic-alvo da regra, sem suavização: `jr2hp + âncora + θ3·(eipca12 − âncora)`, com os valores da safra em `data_info` (% a.a.) |
| `gap_alvo_pb` | **(adendo)** (`selic_alvo` − `selic_depois`) × 100 |
| `jr2hp`, `ancora`, `eipca12` | **(adendo)** os três insumos do alvo na safra, para auditoria |
| `ipca_proj_4t_desvio` | projeção do IPCA 4 trimestres à frente menos a meta, no cenário com Selic endógena (p.p.) |

Pontos de atenção do próprio projeto:

- A regra usa o fator `(1 − c1 − c2)` **simples**, não ao quadrado (ver `estimate_taylor`, EVIDÊNCIA/DECISÃO já documentadas).
- `jr2hp` (juro neutro por HP) recalculado com a amostra até a data, de forma unilateral.
- Amostra mínima: se a safra tiver poucos trimestres para estimar, deixar vazio e registrar em `metodo`. Não fixar parâmetros para preencher.

Validação: na última safra, `theta3` e `selic_taylor` têm de bater com a estimação de amostra inteira já publicada no projeto.

### Adendo de 21/11/2026: por que a `selic_alvo`

A `selic_taylor` pedida acima inclui a suavização (`c1·selic(−1) + c2·selic(−2)`, com c1 + c2 ≈ 0,94). Por isso ela fica sempre atrás da Selic: num ciclo de altas, sai abaixo da Selic e o `gap_taylor_pb` fica negativo. Na F6 do Sentimento_COPOM, a correlação do `gap_taylor_pb` com a ΔSelic seguinte foi −0,62, e com a ΔSelic corrente −0,78. Esse gap mede inércia, não fundamento. O erro foi da especificação deste contrato, não da implementação do MPP. A variável que interessa é o alvo da regra, o termo entre colchetes multiplicado por (1 − c1 − c2).

## DSGE_Brasil (variante `tendencia_focus`, `src/copom.py`)

Decisão já tomada: **parâmetros fixos na moda, filtro até a data**. A contaminação dos parâmetros pela amostra inteira vai declarada.

| `variavel` | Definição |
|---|---|
| `neutro` | juro neutro em `data_info`, com o **filtro de Kalman** (não o suavizador) até o último trimestre disponível (% a.a.) |
| `real_exante` | Selic real ex-ante em `data_info`: (1 + Selic esperada 12 meses, Focus por reunião) / (1 + IPCA Focus 12 meses) − 1, como no `copom.py` |
| `aperto_pp` | `real_exante` − `neutro` |

Pontos de atenção:

- O `copom.py` hoje usa `suavizar(...)`, que olha dados futuros. Para este export, usar a estimativa **filtrada** do último período disponível em cada data.
- Bandas (`li`, `ls`) só se forem baratas. Sem cadeias por safra.
- Validação: na última data, `neutro` filtrado e suavizado coincidem no último ponto (no último ponto, filtro e suavizador dão o mesmo resultado).

## O que o Sentimento_COPOM faz com isso

Um script `v2/f6_fundamentos.py` vai ler os dois exports e repetir o teste da F5:

- previsão do passo em *t+1* com DI + `gap_taylor_pb` e com DI + `aperto_pp`, em *walk-forward*;
- deriva do DI entre a ata e a véspera, regredida em (`gap_taylor_pb` − DI) e em `aperto_pp`.

O resultado entra no paper da v2.0 junto com as seções 8 a 8.3 do escopo.
