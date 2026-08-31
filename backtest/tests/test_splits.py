import pandas as pd
import pytest

from backtest.splits import make_folds, split_frame, Fold


def _hourly(n, start="2026-01-01"):
    return pd.Series(pd.date_range(start, periods=n, freq="h"))


def test_make_folds_requires_at_least_two():
    with pytest.raises(ValueError):
        make_folds(_hourly(100), n_folds=1, horizon_hours=72)


def test_folds_are_contiguous_and_expanding():
    ts = _hourly(1000)
    folds = make_folds(ts, n_folds=4, horizon_hours=72)
    assert len(folds) == 3
    for a, b in zip(folds, folds[1:]):
        assert a.test_end == b.test_start  # no gaps, no overlap
        assert b.train_end > a.train_end   # the training window grows


def test_purge_window_matches_horizon():
    ts = _hourly(1000)
    horizon = 72
    for fold in make_folds(ts, n_folds=4, horizon_hours=horizon):
        assert fold.test_start - fold.purge_start == pd.Timedelta(hours=horizon)


def test_split_frame_excludes_purged_rows_from_train():
    ts = _hourly(200)
    df = pd.DataFrame({"TIMESTAMP_CLT": ts, "value": range(len(ts))})
    fold = Fold(
        index=1,
        train_end=ts[100],
        purge_start=ts[100] - pd.Timedelta(hours=72),
        test_start=ts[100],
        test_end=ts[150],
    )
    train, test = split_frame(df, fold)

    # No training row can fall inside the purged window: its target
    # `horizon` hours ahead would land inside the test set.
    assert (train["TIMESTAMP_CLT"] < fold.purge_start).all()
    assert ((test["TIMESTAMP_CLT"] >= fold.test_start) & (test["TIMESTAMP_CLT"] < fold.test_end)).all()
    # Train and test share no row.
    assert set(train.index).isdisjoint(test.index)
