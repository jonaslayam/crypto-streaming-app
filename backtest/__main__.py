"""Backtest harness CLI.

    python -m backtest --dry-run
    python -m backtest --report

--dry-run runs the engine for ONE horizon and checks the non-negotiable
property: every open position must end up closed. --report runs all
three horizons (24h/72h/168h) and does the statistical work that
actually matters -- IC, overlap-corrected t-stat, and a buy&hold
benchmark -- saving the result under backtest/results/.
"""
from __future__ import annotations

import argparse
import sys

from .data import InsufficientDataError, load_symbol_frames
from .engine import BacktestEngine, EngineConfig
from .report import build_report, save_chart, save_report


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m backtest", description=__doc__)
    p.add_argument("--data", default="optimization/data/crypto_history.csv",
                    help="Feature CSV (the one optimization/extract_data.py produces)")
    p.add_argument("--horizon", type=int, default=72, choices=[24, 72, 168],
                    help="Target horizon in hours (only applies to --dry-run)")
    p.add_argument("--folds", type=int, default=4, help="Number of walk-forward folds")
    p.add_argument("--entry-threshold", type=float, default=0.0,
                    help="Enter when the predicted return exceeds this threshold (uncalibrated, see README)")
    p.add_argument("--stop-loss-atr-mult", type=float, default=2.0)
    p.add_argument("--fee-bps", type=float, default=10.0, help="Fee per side, in basis points")
    p.add_argument("--results-dir", default="backtest/results")
    p.add_argument("--dry-run", action="store_true",
                    help="Run the engine at one horizon and check that no position is orphaned")
    p.add_argument("--report", action="store_true",
                    help="Run all 3 horizons and save metrics + a chart under --results-dir")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not args.dry_run and not args.report:
        print("Nothing to do: pass --dry-run or --report.", file=sys.stderr)
        return 2

    if args.dry_run:
        rc = _run_dry_run(args)
        if rc != 0:
            return rc

    if args.report:
        return _run_report(args)

    return 0


def _run_dry_run(args) -> int:
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

    print(f"Symbols: {len(frames)} | Folds evaluated: {len(result.folds)}")
    print(f"Positions opened: {result.n_opened} | closed: {result.n_closed} | orphaned: {result.n_abandoned}")

    if result.n_abandoned != 0:
        print("❌ There are unclosed positions -- this should never happen.", file=sys.stderr)
        return 1

    print("✅ dry-run OK: every open position ended up closed.")
    return 0


def _run_report(args) -> int:
    try:
        report = build_report(
            args.data,
            n_folds=args.folds,
            entry_threshold=args.entry_threshold,
            stop_loss_atr_mult=args.stop_loss_atr_mult,
            fee_bps=args.fee_bps,
        )
    except (InsufficientDataError, FileNotFoundError) as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1

    metrics_path = save_report(report, out_dir=args.results_dir)
    chart_path = save_chart(report, out_dir=args.results_dir)

    src = report["data_source"]
    print(f"Data: {src['csv_path']}")
    print(f"  {src['n_symbols']} symbols ({', '.join(src['symbols'])}), "
          f"{src['date_range']['start'][:10]} to {src['date_range']['end'][:10]}")
    print(f"\n(entry_threshold={args.entry_threshold} -- {report['config']['entry_threshold_note']})\n")

    for horizon, h in report["horizons"].items():
        print(f"=== {horizon}h horizon ===")
        print(f"  Trades: {h['n_opened']} opened / {h['n_closed']} closed / {h['n_abandoned']} orphaned")
        if h["winrate_pct"] is not None:
            print(f"  Winrate: {h['winrate_pct']}%  |  Avg net return: {h['avg_net_return_pct']}%")
        ic = h["information_coefficient"]
        print(f"  Information Coefficient: {ic if ic is not None else 'n/a'}")
        t = h["t_stat"]
        flag = "✅ significant" if t["significant_at_95pct"] else "⚠️  NOT significant"
        print(f"  t-stat: naive={t['naive_t_stat']}  corrected={t['corrected_t_stat']}"
              f" (n={t['n_trades']} -> effective_n={t['effective_n_independent']})  {flag}")
        print()

    if "buy_and_hold_benchmark_pct" in report and report["buy_and_hold_benchmark_pct"] is not None:
        print(f"Buy&hold benchmark (same 72h period): {report['buy_and_hold_benchmark_pct']}%\n")

    print(f"Saved: {metrics_path}")
    if chart_path:
        print(f"Saved: {chart_path}")
    else:
        print("(matplotlib is not installed -- metrics.json was saved but not the chart)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
