# Template `portfolio/` — Estrutura Padrão para Projetos do Portfólio

Esta pasta é o **template** que será replicado em todos os projetos futuros do portfólio pessoal. O propósito é separar três camadas do mesmo projeto:

1. **Código e dados** (raiz do projeto) — implementação técnica do projeto.
2. **Divulgação no portfólio** (esta pasta) — documentação CRISP-DM em `.qmd` que vai para `Github_Portfolio/projetos/`.
3. **Repositório GitHub** (`README.md` adaptado) — README do repositório do projeto.

## Arquivos obrigatórios

| Arquivo | Função |
|---|---|
| `<slug-do-projeto>.qmd` | Documentação CRISP-DM completa, copiada para `Github_Portfolio/projetos/` |
| `README.md` | README adaptado do `.qmd`, usado no repositório GitHub do projeto |
| `<slug>_*.png` | Imagens de capa e diagramas referenciados no `.qmd` e no README |

## Convenções

- **`.qmd`**: kebab-case (`sentimento-copom.qmd`, `roi-diagnostico.qmd`).
- **YAML do `.qmd`**: deve ter `title`, `date`, `categories`, `description`, `image`, `execute: { eval: false, echo: true }`.
- **Estrutura CRISP-DM**: as 6 fases (Entendimento do Negócio, Entendimento dos Dados, Preparação, Modelagem, Avaliação, Deployment) viram seções numeradas no `.qmd`.
- **README.md**: versão enxuta do `.qmd` — abre com tese central, mostra arquitetura/estrutura, foca em "como rodar" e remove a longa argumentação acadêmica.

## Fluxo de divulgação

```
projeto/
└── portfolio/
    ├── <slug>.qmd ──────────► Github_Portfolio/projetos/<slug>.qmd
    ├── README.md   ────────► usado no repositório GitHub do projeto
    └── *.png       ────────► copiadas junto com o .qmd
```

## Como replicar em projetos futuros

1. Criar `portfolio/` na raiz do novo projeto.
2. Copiar `sentimento-copom.qmd` daqui como ponto de partida; adaptar as 6 fases CRISP-DM ao novo projeto.
3. Adaptar `README.md` para o novo escopo.
4. Adicionar imagens de capa.
5. Copiar `<slug>.qmd` + imagens para `Github_Portfolio/projetos/`.
6. Commit e push em `vitorwilher.github.io`.
