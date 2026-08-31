"""Carga de datos para el backtest.

Lee el mismo CSV que produce optimization/extract_data.py (un dump de
FCT_SWING_FEATURES). No asume nada sobre el orden de las filas -- las
agrupa por SYMBOL explícitamente, que es justo lo que optimize_swing.py
no hacía y por qué perdía el 99% de sus salidas (ver
archive/optimize_swing.py).
"""
from __future__ import annotations

import pandas as pd

from .features import PREDICTOR_COLUMNS, EXECUTION_COLUMNS


class InsufficientDataError(RuntimeError):
    pass


def load_symbol_frames(csv_path: str, horizon_hours: int) -> dict[str, pd.DataFrame]:
    """Devuelve {symbol: DataFrame} ordenado por tiempo, uno por símbolo.

    Cada símbolo se procesa de forma completamente independiente en todo
    el paquete -- nunca hay un índice global que salte entre monedas.
    """
    target_col = f"TARGET_RETURN_{horizon_hours}H"
    needed = ["SYMBOL", "TIMESTAMP_CLT", target_col] + PREDICTOR_COLUMNS + EXECUTION_COLUMNS

    df = pd.read_csv(csv_path)
    missing = [c for c in needed if c not in df.columns]
    if missing:
        raise InsufficientDataError(
            f"Al CSV le faltan columnas requeridas: {missing}. "
            f"¿Se generó con optimization/extract_data.py contra el esquema actual?"
        )

    df["TIMESTAMP_CLT"] = pd.to_datetime(df["TIMESTAMP_CLT"])

    frames: dict[str, pd.DataFrame] = {}
    for symbol, g in df.groupby("SYMBOL", sort=False):
        g = g.sort_values("TIMESTAMP_CLT").reset_index(drop=True)
        # Filas sin predictores completos (warmup de indicadores) no sirven
        # ni para entrenar ni para operar.
        g = g.dropna(subset=PREDICTOR_COLUMNS + EXECUTION_COLUMNS)
        if len(g) > 0:
            frames[symbol] = g

    if not frames:
        raise InsufficientDataError("No quedó ningún símbolo con datos utilizables tras el filtrado.")

    return frames
