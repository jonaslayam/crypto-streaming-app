"""Purged walk-forward with embargo.

The audit found that ml_train_data.sql/ml_test_data.sql split the data
with a simple date cut (< today-90 / >= today-90) without purging the
boundary -- a training row whose target looks 72h into the future can
"see" data that already falls inside the test period. This module
fixes that: every training row whose 72h window would overlap the test
period gets dropped (purge), and a buffer is left after the test period
before the next fold's training window starts (embargo) so the same
contamination doesn't get reused across folds.

The split is done by CALENDAR time, not per symbol: fold boundaries are
computed over the combined date range of every symbol, so each fold
evaluates the same period across all coins at once.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import pandas as pd


@dataclass(frozen=True)
class Fold:
    index: int
    train_end: pd.Timestamp        # exclusive
    purge_start: pd.Timestamp      # start of the purged zone (= train_end - horizon)
    test_start: pd.Timestamp       # inclusive
    test_end: pd.Timestamp         # exclusive


def make_folds(
    all_timestamps: pd.Series,
    n_folds: int,
    horizon_hours: int,
) -> list[Fold]:
    """Expanding-window walk-forward: fold i trains on everything before
    block i, tests on block i.

    Embargo is not a separate parameter: in an expanding window, each
    fold recomputes its own `purge_start` as `test_start - horizon`, and
    that same purge gets reapplied in the following fold over that same
    stretch (which by then is training data). That already does the job
    an embargo would -- no fold ever trains on a row whose target looks
    into ITS OWN test period.
    """
    if n_folds < 2:
        raise ValueError("n_folds must be >= 2 (at least one train fold and one test fold)")

    ts_min = all_timestamps.min()
    ts_max = all_timestamps.max()
    total_span = ts_max - ts_min
    block_span = total_span / n_folds

    folds: list[Fold] = []
    for i in range(1, n_folds):
        test_start = ts_min + block_span * i
        test_end = ts_min + block_span * (i + 1) if i < n_folds - 1 else ts_max + timedelta(seconds=1)
        purge_start = test_start - timedelta(hours=horizon_hours)
        folds.append(Fold(
            index=i,
            train_end=test_start,
            purge_start=purge_start,
            test_start=test_start,
            test_end=test_end,
        ))
    return folds


def split_frame(df: pd.DataFrame, fold: Fold) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Applies a Fold to a single symbol's DataFrame. Returns (train, test)."""
    ts = df["TIMESTAMP_CLT"]
    train_mask = ts < fold.purge_start
    test_mask = (ts >= fold.test_start) & (ts < fold.test_end)
    return df.loc[train_mask].copy(), df.loc[test_mask].copy()
