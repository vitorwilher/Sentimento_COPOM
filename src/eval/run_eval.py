"""Gate de qualidade do scoring de tom — o eval harness.

Espelha a postura do COPOM_RAG_Service: qualidade tratada como **contrato
verificável em CI**, não como impressão. Aqui a verdade é a **Selic realizada** —
o eval mede se o Índice de Tom prevê a variação da Selic que de fato ocorreu, e
**falha com exit code 1** se a qualidade do ensemble regride abaixo dos
thresholds. Plugado numa GitHub Action, esse exit code bloqueia um merge que
degrade o scoring (troca de modelo, mudança de prompt, etc.).

O gate avalia o **ensemble** (o índice publicado). As linhas por modelo são
informativas — ajudam a diagnosticar qual provedor puxou a regressão.

Uso::

    python -m eval.run_eval                          # thresholds padrão
    python -m eval.run_eval --min-r2 0.45            # gate de R² customizado
    python -m eval.run_eval --min-spearman 0.60      # gate de correlação customizado
"""

from __future__ import annotations

import argparse
import sys

from eval.metrics import MetricasModelo, avaliar_todos

# Thresholds padrão do gate, sobre o ENSEMBLE. Calibrados um pouco abaixo do
# desempenho atual (R² ~0,49, Spearman ~0,70) para pegar regressão real sem
# reprovar ruído estatístico normal.
DEFAULT_MIN_R2 = 0.40
DEFAULT_MIN_SPEARMAN = 0.55


def print_report(resultados: list[MetricasModelo], min_r2: float, min_sp: float) -> None:
    """Relatório por modelo + ensemble, com os thresholds aplicados."""
    print("\n=== Sentimento COPOM — Eval do Scoring de Tom (verdade: Selic realizada) ===\n")
    print(f"{'MODELO':<10}{'N':>4}{'R²':>8}{'RMSE':>9}{'SPEARMAN':>10}")
    print("-" * 45)
    for m in resultados:
        marca = "  <- gate" if m.provedor == "ensemble" else ""
        print(f"{m.provedor:<10}{m.n:>4}{m.r2:>8.3f}{m.rmse:>9.3f}"
              f"{m.spearman:>10.3f}{marca}")
    print("-" * 45)
    print(f"thresholds do gate (ensemble): R² ≥ {min_r2:.2f}  e  Spearman ≥ {min_sp:.2f}")


def run(min_r2: float, min_sp: float) -> int:
    """Roda o eval e retorna o exit code (0 passou / 1 reprovou)."""
    resultados = avaliar_todos()
    print_report(resultados, min_r2, min_sp)

    ensemble = next((m for m in resultados if m.provedor == "ensemble"), None)
    if ensemble is None:
        print("\nRESULTADO: FALHOU — sem dados para avaliar o ensemble.\n")
        return 1

    passou_r2 = ensemble.r2 >= min_r2
    passou_sp = ensemble.spearman >= min_sp
    passou = passou_r2 and passou_sp

    print()
    if not passou_r2:
        print(f"  ✗ R² do ensemble {ensemble.r2:.3f} < {min_r2:.2f}")
    if not passou_sp:
        print(f"  ✗ Spearman do ensemble {ensemble.spearman:.3f} < {min_sp:.2f}")
    print(f"\nRESULTADO: {'PASSOU' if passou else 'FALHOU'} "
          f"(ensemble R²={ensemble.r2:.3f}, Spearman={ensemble.spearman:.3f})\n")
    return 0 if passou else 1


def main() -> None:
    """Ponto de entrada CLI: parseia thresholds e sai com o código do gate."""
    parser = argparse.ArgumentParser(description="Eval do scoring de tom do Sentimento COPOM.")
    parser.add_argument("--min-r2", type=float, default=DEFAULT_MIN_R2,
                        help=f"R² mínimo do ensemble (default {DEFAULT_MIN_R2}).")
    parser.add_argument("--min-spearman", type=float, default=DEFAULT_MIN_SPEARMAN,
                        help=f"Spearman mínimo do ensemble (default {DEFAULT_MIN_SPEARMAN}).")
    args = parser.parse_args()
    sys.exit(run(args.min_r2, args.min_spearman))


if __name__ == "__main__":
    main()
