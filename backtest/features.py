"""Predictor column list.

Must match predictor_columns() in transform/macros/feature_set.sql
exactly -- that macro is the source of truth for what the production
model uses as features; this list is its Python mirror so the backtest
evaluates the same information the real model sees, no more, no less.
If one drifts from the other, this backtest stops measuring the real
strategy.

Deliberately EXCLUDED (see the dbt macro for the full rationale):
TARGET_RETURN_* except the training target, and absolute price/volume
levels (CLOSE_PRICE, VOLUME, SMA_*, ATR_14, BB_*, STDDEV_20,
MAX_PRICE_48H, MIN_PRICE_48H) -- not stationary across symbols.
"""

PREDICTOR_COLUMNS = [
    "RSI_14",
    "RSI_24",
    "Z_SCORE_20",
    "Z_SCORE_24",
    "RANGE_POS_48H",
    "RVOL_20",
]

# Columns the execution engine needs outside the model (price and ATR
# for the stop-loss). Never passed to the model as predictors.
EXECUTION_COLUMNS = ["CLOSE_PRICE", "ATR_14"]

TARGET_COLUMN_TEMPLATE = "TARGET_RETURN_{h}H"


def target_column(horizon_hours: int) -> str:
    return TARGET_COLUMN_TEMPLATE.format(h=horizon_hours)
