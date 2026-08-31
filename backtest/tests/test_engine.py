import numpy as np
import pandas as pd
import pytest

from backtest.engine import BacktestEngine, EngineConfig


def _frame(n, price_fn, atr=1.0, start="2026-01-01"):
    times = pd.date_range(start, periods=n, freq="h")
    return pd.DataFrame({
        "TIMESTAMP_CLT": times,
        "CLOSE_PRICE": [price_fn(i) for i in range(n)],
        "ATR_14": [atr] * n,
    })


def test_entry_executes_on_next_candle_not_the_signal_candle():
    """La señal en la fila i no puede ejecutarse al precio de la fila i --
    eso sería mirar el futuro dentro del propio candle de la señal."""
    df = _frame(10, price_fn=lambda i: 100.0 + i)  # precio sube 1 por vela
    preds = np.zeros(10)
    preds[2] = 1.0  # señal en i=2

    engine = BacktestEngine(EngineConfig(horizon_hours=100, stop_loss_atr_mult=1000))
    trades = engine._simulate_symbol("TEST", df, preds)

    assert len(trades) == 1
    # precio en i=2 es 102, en i=3 (vela siguiente) es 103
    assert trades[0].entry_price == pytest.approx(103.0)
    assert trades[0].entry_time == df["TIMESTAMP_CLT"].iloc[3]


def test_no_orphaned_positions_regardless_of_symbol_count():
    """El bug de optimize_swing.py: posiciones que quedaban sin cerrar
    (sin P&L) al cambiar de símbolo en un índice global compartido. Acá
    cada símbolo tiene su propio DataFrame, así que no hay índice
    compartido posible -- se prueba igual, con muchos símbolos y muchas
    señales, que TODO lo que se abre se cierra."""
    engine = BacktestEngine(EngineConfig(horizon_hours=5, stop_loss_atr_mult=2.0))
    rng = np.random.default_rng(0)

    total_opened = 0
    total_closed = 0
    for s in range(10):
        n = 80
        prices = 100 + np.cumsum(rng.normal(0, 1, n))
        df = _frame(n, price_fn=lambda i, p=prices: float(p[i]), atr=2.0)
        preds = rng.normal(0, 1, n)  # ~50% de las velas disparan entrada
        trades = engine._simulate_symbol(f"SYM{s}", df, preds)
        total_opened += len(trades)
        total_closed += sum(1 for t in trades if t.is_closed)

    assert total_opened > 0
    assert total_opened == total_closed


def test_stop_loss_closes_before_horizon():
    df = _frame(10, price_fn=lambda i: 100.0 if i < 3 else 100.0 - 10 * (i - 2))
    preds = np.zeros(10)
    preds[0] = 1.0
    engine = BacktestEngine(EngineConfig(horizon_hours=100, stop_loss_atr_mult=1.0))
    trades = engine._simulate_symbol("TEST", df, preds)

    assert len(trades) == 1
    assert trades[0].exit_reason == "stop_loss"


def test_unclosed_position_at_data_end_is_marked_not_dropped():
    df = _frame(5, price_fn=lambda i: 100.0 + i)
    preds = np.zeros(5)
    preds[0] = 1.0
    engine = BacktestEngine(EngineConfig(horizon_hours=1000, stop_loss_atr_mult=1000))
    trades = engine._simulate_symbol("TEST", df, preds)

    assert len(trades) == 1
    assert trades[0].is_closed
    assert trades[0].exit_reason == "data_end"
