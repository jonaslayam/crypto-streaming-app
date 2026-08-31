"""CLI del arnés de backtest.

    python -m backtest --dry-run
    python -m backtest --report

--dry-run corre el motor y verifica la propiedad no negociable: toda
posición abierta tiene que quedar cerrada. --report agrega métricas de
retorno (la parte estadística rigurosa -- t-stat corregido por
solapamiento, IC por horizonte, benchmark buy&hold -- se termina de
construir en la siguiente noche del plan de cierre, N4).
"""
from __future__ import annotations

import argparse
import sys

from .data import InsufficientDataError, load_symbol_frames
from .engine import BacktestEngine, EngineConfig


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m backtest", description=__doc__)
    p.add_argument("--data", default="optimization/data/crypto_history.csv",
                    help="CSV de features (el que produce optimization/extract_data.py)")
    p.add_argument("--horizon", type=int, default=72, choices=[24, 72, 168],
                    help="Horizonte del target en horas")
    p.add_argument("--folds", type=int, default=4, help="Cantidad de folds walk-forward")
    p.add_argument("--entry-threshold", type=float, default=0.0,
                    help="Entrar cuando el retorno predicho supere este umbral")
    p.add_argument("--stop-loss-atr-mult", type=float, default=2.0)
    p.add_argument("--fee-bps", type=float, default=10.0, help="Comisión por lado, en basis points")
    p.add_argument("--dry-run", action="store_true",
                    help="Corre el motor y verifica que no queden posiciones huérfanas")
    p.add_argument("--report", action="store_true",
                    help="Corre el motor e imprime métricas de retorno")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not args.dry_run and not args.report:
        print("Nada que hacer: pasa --dry-run o --report.", file=sys.stderr)
        return 2

    try:
        frames = load_symbol_frames(args.data, horizon_hours=args.horizon)
    except (InsufficientDataError, FileNotFoundError) as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1

    config = EngineConfig(
        horizon_hours=args.horizon,
        entry_threshold=args.entry_threshold,
        stop_loss_atr_mult=args.stop_loss_atr_mult,
        fee_bps=args.fee_bps,
        n_folds=args.folds,
    )
    result = BacktestEngine(config).run(frames)

    print(f"Símbolos: {len(frames)} | Folds evaluados: {len(result.folds)}")
    print(f"Posiciones abiertas: {result.n_opened} | cerradas: {result.n_closed} | huérfanas: {result.n_abandoned}")

    if result.n_abandoned != 0:
        print("❌ Hay posiciones sin cerrar -- esto no debería pasar nunca.", file=sys.stderr)
        return 1

    if args.dry_run:
        print("✅ dry-run OK: cada posición abierta quedó cerrada.")

    if args.report:
        _print_report(result)

    return 0


def _print_report(result) -> None:
    closed = [t for t in result.trades if t.is_closed]
    if not closed:
        print("Sin trades cerrados -- no hay nada que reportar.")
        return

    returns = [t.net_return(result.config.fee_bps) for t in closed]
    wins = sum(1 for r in returns if r > 0)
    avg_return = sum(returns) / len(returns)
    print(f"\nTrades cerrados: {len(closed)}")
    print(f"Winrate: {wins}/{len(closed)} ({100 * wins / len(closed):.1f}%)")
    print(f"Retorno neto promedio por trade: {avg_return * 100:.3f}%")
    print("\n(Ver N4 del plan de cierre para el IC por horizonte, el t-stat")
    print(" corregido por solapamiento y el benchmark buy&hold.)")


if __name__ == "__main__":
    raise SystemExit(main())
