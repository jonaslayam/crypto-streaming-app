"""Statistics on the backtest results.

Everything here answers one real problem the audit found: with
OVERLAPPING returns -- a signal can be evaluated on every candle, and
each trade has a horizon_hours-long window -- the textbook t-stat (the
one that uses sqrt(n_trades)) artificially inflates significance,
because it counts things as independent observations when they
actually share almost all of their information. It's the same family
of leak as the model's lookahead bias, just at the evaluation layer
instead of the feature layer.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass

import pandas as pd


@dataclass
class TStatResult:
    n_trades: int
    effective_n: int
    mean_return: float
    std_return: float
    naive_t: float
    corrected_t: float

    @property
    def significant(self) -> bool:
        """Conventional |t| > 2 (~95% confidence) threshold -- applied
        to the CORRECTED t-stat. The naive one doesn't count for this:
        it's precisely the number that misleads."""
        return abs(self.corrected_t) > 2.0

    def to_dict(self) -> dict:
        return {
            "n_trades": self.n_trades,
            "effective_n_independent": self.effective_n,
            "mean_return_pct": round(self.mean_return * 100, 4),
            "naive_t_stat": round(self.naive_t, 3),
            "corrected_t_stat": round(self.corrected_t, 3),
            "significant_at_95pct": self.significant,
        }


def corrected_t_stat(returns: list[float], horizon_hours: int) -> TStatResult:
    """One-sample t-stat (H0: mean return = 0), corrected for overlap.

    The engine can evaluate a signal on every candle, so two trades that
    open an hour apart share up to horizon_hours-1 hours of their
    window -- almost all of their information. The number of truly
    independent "blocks" of information is, in the worst case (one
    signal per candle), n_trades / horizon_hours. Same logic already
    used in the audit: thousands of overlapping 72h trades collapse
    down to a handful of genuinely independent ones.
    """
    n = len(returns)
    if n == 0:
        return TStatResult(0, 0, 0.0, 0.0, 0.0, 0.0)

    mean = statistics.fmean(returns)
    std = statistics.pstdev(returns) if n > 1 else 0.0
    effective_n = max(1, math.ceil(n / horizon_hours))

    naive_t = mean / (std / math.sqrt(n)) if std > 0 else 0.0
    corrected_t = mean / (std / math.sqrt(effective_n)) if std > 0 else 0.0

    return TStatResult(n, effective_n, mean, std, naive_t, corrected_t)


def information_coefficient(preds: pd.Series, actuals: pd.Series) -> float | None:
    """Rank correlation (Spearman) between the prediction and the return
    that actually happened. Computed over ALL test rows, not just the
    ones that triggered an entry -- it measures the model's raw
    predictive power, not the entry rule sitting on top of it. None if
    there aren't enough rows with a known target (the "live" candles at
    the end of the data don't have a target yet).
    """
    paired = pd.DataFrame({"pred": preds, "actual": actuals}).dropna()
    if len(paired) < 3:
        return None
    ic = paired["pred"].corr(paired["actual"], method="spearman")
    return float(ic) if pd.notna(ic) else None


def buy_and_hold_benchmark(frames: dict[str, pd.DataFrame], start: pd.Timestamp, end: pd.Timestamp) -> float | None:
    """Buy-and-hold return, equal-weighted across symbols, over the same
    calendar stretch the backtest evaluated. Without this, a strategy
    return -- positive or negative -- says nothing on its own; what
    matters is what it's being compared against.
    """
    returns = []
    for df in frames.values():
        window = df[(df["TIMESTAMP_CLT"] >= start) & (df["TIMESTAMP_CLT"] < end)]
        if len(window) < 2:
            continue
        first_price = window["CLOSE_PRICE"].iloc[0]
        last_price = window["CLOSE_PRICE"].iloc[-1]
        returns.append((last_price - first_price) / first_price)

    if not returns:
        return None
    return sum(returns) / len(returns)
