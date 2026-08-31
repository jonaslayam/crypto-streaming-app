"""Walk-forward purgado con embargo.

La auditoría encontró que ml_train_data.sql/ml_test_data.sql partían los
datos con un simple corte de fecha (< hoy-90 / >= hoy-90) sin purgar la
frontera -- una fila de entrenamiento cuyo target mira 72h hacia adelante
puede "ver" datos que ya caen dentro del período de test. Acá se corrige:
toda fila de train cuya ventana de 72h se meta en el test se descarta
(purge), y además se deja un colchón después del test antes de que
empiece el siguiente fold de train (embargo) para no reusar la misma
contaminación en folds sucesivos.

El split es por CALENDARIO, no por símbolo: los folds se calculan sobre el
rango de fechas combinado de todos los símbolos, así que cada fold
evalúa el mismo período para todas las monedas a la vez.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import pandas as pd


@dataclass(frozen=True)
class Fold:
    index: int
    train_end: pd.Timestamp        # exclusivo
    purge_start: pd.Timestamp      # inicio de la zona purgada (= train_end - horizonte)
    test_start: pd.Timestamp       # inclusivo
    test_end: pd.Timestamp         # exclusivo


def make_folds(
    all_timestamps: pd.Series,
    n_folds: int,
    horizon_hours: int,
) -> list[Fold]:
    """Walk-forward de ventana expansiva: fold i entrena con todo lo
    anterior al bloque i, evalúa sobre el bloque i.

    El embargo no es un parámetro aparte: en una ventana expansiva, cada
    fold recalcula su propio `purge_start` como `test_start - horizonte`,
    y esa purga se aplica de nuevo en el fold siguiente sobre ese mismo
    tramo (que para entonces ya es train). Eso ya cumple el rol del
    embargo -- ningún fold entrena jamás con una fila cuyo target mire
    hacia dentro de SU PROPIO período de test.
    """
    if n_folds < 2:
        raise ValueError("n_folds debe ser >= 2 (al menos un fold de train y uno de test)")

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
    """Aplica un Fold a un DataFrame de un símbolo. Devuelve (train, test)."""
    ts = df["TIMESTAMP_CLT"]
    train_mask = ts < fold.purge_start
    test_mask = (ts >= fold.test_start) & (ts < fold.test_end)
    return df.loc[train_mask].copy(), df.loc[test_mask].copy()
