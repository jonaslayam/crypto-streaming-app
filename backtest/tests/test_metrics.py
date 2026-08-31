import math

import pandas as pd
import pytest

from backtest.metrics import buy_and_hold_benchmark, corrected_t_stat, information_coefficient


def test_corrected_t_stat_shrinks_toward_zero_confidence_with_overlap():
    """The same set of returns, evaluated with a longer horizon (more
    overlap), must give a SMALLER corrected t-stat -- because there is
    less independent information behind the same number of trades."""
    returns = [0.01, 0.015, -0.005, 0.02, 0.01, -0.01, 0.012, 0.008] * 5  # n=40

    short = corrected_t_stat(returns, horizon_hours=2)
    long = corrected_t_stat(returns, horizon_hours=40)

    assert short.effective_n > long.effective_n
    assert abs(short.corrected_t) > abs(long.corrected_t)
    # The naive t-stat doesn't change with the horizon -- that's exactly
    # what's wrong with it.
    assert short.naive_t == long.naive_t


def test_corrected_t_stat_empty():
    result = corrected_t_stat([], horizon_hours=72)
    assert result.n_trades == 0
    assert result.corrected_t == 0.0
    assert not result.significant


def test_corrected_t_stat_effective_n_matches_known_case():
    """The audit's concrete case: ~2233 overlapping 72h trades collapse
    to a handful of independent ones, not thousands."""
    returns = [0.001] * 2233
    result = corrected_t_stat(returns, horizon_hours=72)
    assert result.effective_n == math.ceil(2233 / 72) == 32
    assert result.effective_n < 40  # order of magnitude "tens", not "thousands"


def test_information_coefficient_perfect_correlation():
    preds = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    actuals = pd.Series([1.1, 2.2, 2.9, 4.3, 5.1])
    ic = information_coefficient(preds, actuals)
    assert ic == pytest.approx(1.0)


def test_information_coefficient_ignores_missing_targets():
    """'Live' candles (no target yet) must not contaminate the IC."""
    preds = pd.Series([1.0, 2.0, 3.0, 4.0])
    actuals = pd.Series([1.0, 2.0, 3.0, None])
    ic = information_coefficient(preds, actuals)
    assert ic == pytest.approx(1.0)


def test_information_coefficient_none_when_too_few_rows():
    assert information_coefficient(pd.Series([1.0]), pd.Series([1.0])) is None


def test_buy_and_hold_benchmark_equal_weighted():
    df_a = pd.DataFrame({
        "TIMESTAMP_CLT": pd.date_range("2026-01-01", periods=3, freq="h"),
        "CLOSE_PRICE": [100.0, 105.0, 110.0],  # +10%
    })
    df_b = pd.DataFrame({
        "TIMESTAMP_CLT": pd.date_range("2026-01-01", periods=3, freq="h"),
        "CLOSE_PRICE": [50.0, 45.0, 45.0],  # -10%
    })
    bh = buy_and_hold_benchmark(
        {"A": df_a, "B": df_b},
        start=df_a["TIMESTAMP_CLT"].iloc[0],
        end=df_a["TIMESTAMP_CLT"].iloc[-1] + pd.Timedelta(seconds=1),
    )
    assert bh == pytest.approx(0.0, abs=1e-9)
