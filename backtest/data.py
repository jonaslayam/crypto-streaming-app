"""Data loading for the backtest.

Reads the same CSV that optimization/extract_data.py produces (a dump
of FCT_SWING_FEATURES). Makes no assumption about row ordering -- it
groups by SYMBOL explicitly, which is exactly what optimize_swing.py
did not do and why it lost ~99% of its exits (see
archive/optimize_swing.py).
"""
from __future__ import annotations

import pandas as pd

from .features import PREDICTOR_COLUMNS, EXECUTION_COLUMNS


class InsufficientDataError(RuntimeError):
    pass


def load_symbol_frames(csv_path: str, horizon_hours: int) -> dict[str, pd.DataFrame]:
    """Returns {symbol: DataFrame}, sorted by time, one per symbol.

    Every symbol is processed completely independently throughout the
    whole package -- there is never a global index that jumps between
    coins.
    """
    target_col = f"TARGET_RETURN_{horizon_hours}H"
    needed = ["SYMBOL", "TIMESTAMP_CLT", target_col] + PREDICTOR_COLUMNS + EXECUTION_COLUMNS

    df = pd.read_csv(csv_path)
    missing = [c for c in needed if c not in df.columns]
    if missing:
        raise InsufficientDataError(
            f"CSV is missing required columns: {missing}. "
            f"Was it generated with optimization/extract_data.py against the current schema?"
        )

    df["TIMESTAMP_CLT"] = pd.to_datetime(df["TIMESTAMP_CLT"])

    frames: dict[str, pd.DataFrame] = {}
    for symbol, g in df.groupby("SYMBOL", sort=False):
        g = g.sort_values("TIMESTAMP_CLT").reset_index(drop=True)
        # Rows without complete predictors (indicator warmup) are
        # useless both for training and for trading.
        g = g.dropna(subset=PREDICTOR_COLUMNS + EXECUTION_COLUMNS)
        if len(g) > 0:
            frames[symbol] = g

    if not frames:
        raise InsufficientDataError("No symbol had usable data left after filtering.")

    return frames
