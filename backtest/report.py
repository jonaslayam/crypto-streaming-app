"""Builds the N4 report: IC and overlap-corrected t-stat per horizon,
buy&hold benchmark, saved to backtest/results/metrics.json + a chart.

Deliberately kept separate from --dry-run (N3): --dry-run just needs to
run fast and verify the engine's mechanics for ONE horizon; this runs
all three horizons and does the statistical work that actually decides
whether there's anything here worth looking at.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .data import load_symbol_frames
from .engine import BacktestEngine, EngineConfig
from .metrics import buy_and_hold_benchmark, corrected_t_stat, information_coefficient

HORIZONS = (24, 72, 168)


def build_report(
    csv_path: str,
    n_folds: int = 4,
    entry_threshold: float = 0.0,
    stop_loss_atr_mult: float = 2.0,
    fee_bps: float = 10.0,
) -> dict:
    report: dict = {
        "config": {
            "n_folds": n_folds,
            "entry_threshold": entry_threshold,
            "entry_threshold_note": (
                "default value, deliberately NOT calibrated -- see the "
                "closing plan's log (N4): searching for the best "
                "threshold against the same folds used to report the "
                "result would reintroduce leakage through parameter "
                "selection."
            ),
            "stop_loss_atr_mult": stop_loss_atr_mult,
            "fee_bps": fee_bps,
        },
        "horizons": {},
        "equity_curve_72h": [],
    }

    benchmark_frames = None
    benchmark_start = None
    benchmark_end = None

    for horizon in HORIZONS:
        frames = load_symbol_frames(csv_path, horizon_hours=horizon)

        if "data_source" not in report:
            all_ts = pd.concat([df["TIMESTAMP_CLT"] for df in frames.values()])
            report["data_source"] = {
                "csv_path": csv_path,
                "symbols": sorted(frames.keys()),
                "n_symbols": len(frames),
                "rows_per_symbol": {s: len(df) for s, df in frames.items()},
                "date_range": {
                    "start": all_ts.min().isoformat(),
                    "end": all_ts.max().isoformat(),
                },
            }

        config = EngineConfig(
            horizon_hours=horizon,
            entry_threshold=entry_threshold,
            stop_loss_atr_mult=stop_loss_atr_mult,
            fee_bps=fee_bps,
            n_folds=n_folds,
        )
        result = BacktestEngine(config).run(frames)
        closed = [t for t in result.trades if t.is_closed]
        returns = [t.net_return(fee_bps) for t in closed]

        tstat = corrected_t_stat(returns, horizon)

        ic_per_fold = [
            information_coefficient(fr.test_preds, fr.test_actuals)
            for fr in result.folds
        ]
        ic_per_fold = [ic for ic in ic_per_fold if ic is not None]
        avg_ic = sum(ic_per_fold) / len(ic_per_fold) if ic_per_fold else None

        wins = sum(1 for r in returns if r > 0)

        report["horizons"][str(horizon)] = {
            "n_opened": result.n_opened,
            "n_closed": result.n_closed,
            "n_abandoned": result.n_abandoned,
            "winrate_pct": round(100 * wins / len(returns), 1) if returns else None,
            "avg_net_return_pct": round(sum(returns) / len(returns) * 100, 4) if returns else None,
            "information_coefficient": round(avg_ic, 4) if avg_ic is not None else None,
            "ic_per_fold": [round(ic, 4) for ic in ic_per_fold],
            "t_stat": tstat.to_dict(),
        }

        if horizon == 72 and result.folds:
            benchmark_frames = frames
            benchmark_start = result.folds[0].fold.test_start
            benchmark_end = result.folds[-1].fold.test_end

            equity = 0.0
            curve = []
            for trade in sorted(closed, key=lambda t: t.exit_time):
                equity += trade.net_return(fee_bps) or 0.0
                curve.append({"exit_time": trade.exit_time.isoformat(), "cumulative_return_pct": round(equity * 100, 4)})
            report["equity_curve_72h"] = curve

    if benchmark_frames is not None:
        bh = buy_and_hold_benchmark(benchmark_frames, benchmark_start, benchmark_end)
        report["buy_and_hold_benchmark_pct"] = round(bh * 100, 4) if bh is not None else None
        report["benchmark_period"] = {
            "start": benchmark_start.isoformat(),
            "end": benchmark_end.isoformat(),
        }

    return report


def save_report(report: dict, out_dir: str = "backtest/results") -> Path:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    metrics_path = out_path / "metrics.json"
    metrics_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return metrics_path


def save_chart(report: dict, out_dir: str = "backtest/results") -> Path | None:
    """Equity chart (72h) + IC per horizon. None if matplotlib isn't
    installed -- the JSON report doesn't depend on this."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    chart_path = out_path / "equity_and_ic.png"

    fig, (ax_equity, ax_ic) = plt.subplots(1, 2, figsize=(11, 4))

    curve = report.get("equity_curve_72h", [])
    if curve:
        times = pd.to_datetime([p["exit_time"] for p in curve])
        values = [p["cumulative_return_pct"] for p in curve]
        ax_equity.plot(times, values, linewidth=1.2)
        ax_equity.axhline(0, color="gray", linewidth=0.8, linestyle="--")
        ax_equity.set_title("Cumulative equity (72h, net of fees)")
        ax_equity.set_ylabel("Cumulative %")
        fig.autofmt_xdate()
    else:
        ax_equity.set_title("Cumulative equity (72h) -- no closed trades")

    horizons = list(report.get("horizons", {}).keys())
    ic_values = [report["horizons"][h]["information_coefficient"] or 0.0 for h in horizons]
    colors = ["#3B6B47" if v >= 0 else "#9E4230" for v in ic_values]
    ax_ic.bar([f"{h}h" for h in horizons], ic_values, color=colors)
    ax_ic.axhline(0, color="gray", linewidth=0.8)
    ax_ic.set_title("Information Coefficient by horizon")

    fig.tight_layout()
    fig.savefig(chart_path, dpi=140)
    plt.close(fig)
    return chart_path
