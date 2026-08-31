"""Simulation engine: trains per fold, trades per symbol.

Structural fix for the optimize_swing.py bug: here every symbol runs
through its own loop, with its own position state. It's impossible for
a BTCUSDT entry to be closed as a "ghost" because the next CSV row
belonged to ETHUSDT -- that cross-symbol jump simply doesn't exist in
this structure, since there is never a single index shared between coins.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from .features import PREDICTOR_COLUMNS, target_column
from .splits import Fold, make_folds, split_frame


@dataclass
class Trade:
    symbol: str
    entry_time: pd.Timestamp
    entry_price: float
    predicted_return: float
    exit_time: pd.Timestamp | None = None
    exit_price: float | None = None
    exit_reason: str | None = None

    @property
    def is_closed(self) -> bool:
        return self.exit_time is not None

    def net_return(self, fee_bps: float) -> float | None:
        """Return net of fees (0.1%/side = 10 bps by default)."""
        if not self.is_closed:
            return None
        gross = (self.exit_price - self.entry_price) / self.entry_price
        fee = fee_bps / 10_000.0
        return gross - 2 * fee


@dataclass
class EngineConfig:
    horizon_hours: int = 72
    entry_threshold: float = 0.0
    stop_loss_atr_mult: float = 2.0
    fee_bps: float = 10.0
    n_folds: int = 4
    min_train_rows: int = 200


@dataclass
class FoldReport:
    fold: Fold
    n_train: int
    n_test: int
    trades: list[Trade] = field(default_factory=list)
    # Prediction vs. real target for EVERY test row, not just the ones
    # that triggered an entry -- N4 uses these for the Information
    # Coefficient, which measures the model's raw predictive power, not
    # the entry rule sitting on top of it.
    test_preds: "pd.Series | None" = None
    test_actuals: "pd.Series | None" = None


@dataclass
class BacktestResult:
    trades: list[Trade]
    folds: list[FoldReport]
    config: EngineConfig

    @property
    def n_opened(self) -> int:
        return len(self.trades)

    @property
    def n_closed(self) -> int:
        return sum(1 for t in self.trades if t.is_closed)

    @property
    def n_abandoned(self) -> int:
        """Must always be 0 -- an open position that never closes is
        exactly the bug this package exists to not repeat."""
        return self.n_opened - self.n_closed


class BacktestEngine:
    def __init__(self, config: EngineConfig | None = None):
        self.config = config or EngineConfig()

    def run(self, frames: dict[str, pd.DataFrame]) -> BacktestResult:
        cfg = self.config
        target_col = target_column(cfg.horizon_hours)

        all_ts = pd.concat([df["TIMESTAMP_CLT"] for df in frames.values()], ignore_index=True)
        folds = make_folds(all_ts, cfg.n_folds, cfg.horizon_hours)

        all_trades: list[Trade] = []
        fold_reports: list[FoldReport] = []

        for fold in folds:
            train_parts, test_parts = [], {}
            for symbol, df in frames.items():
                train, test = split_frame(df, fold)
                train = train.dropna(subset=[target_col])
                if len(train) == 0 or len(test) == 0:
                    continue
                train_parts.append(train)
                test_parts[symbol] = test

            if not train_parts:
                continue
            train_all = pd.concat(train_parts, ignore_index=True)
            if len(train_all) < cfg.min_train_rows:
                continue

            model = HistGradientBoostingRegressor(random_state=42)
            model.fit(train_all[PREDICTOR_COLUMNS].to_numpy(), train_all[target_col].to_numpy())

            fold_trades: list[Trade] = []
            fold_preds: list[float] = []
            fold_actuals: list[float] = []
            for symbol, test in test_parts.items():
                preds = model.predict(test[PREDICTOR_COLUMNS].to_numpy())
                fold_trades.extend(self._simulate_symbol(symbol, test, preds))
                fold_preds.extend(preds)
                fold_actuals.extend(test[target_col].to_numpy())

            all_trades.extend(fold_trades)
            fold_reports.append(FoldReport(
                fold=fold,
                n_train=len(train_all),
                n_test=sum(len(t) for t in test_parts.values()),
                trades=fold_trades,
                test_preds=pd.Series(fold_preds),
                test_actuals=pd.Series(fold_actuals),
            ))

        return BacktestResult(trades=all_trades, folds=fold_reports, config=cfg)

    def _simulate_symbol(self, symbol: str, df: pd.DataFrame, preds) -> list[Trade]:
        cfg = self.config
        prices = df["CLOSE_PRICE"].to_numpy()
        atrs = df["ATR_14"].to_numpy()
        times = df["TIMESTAMP_CLT"].to_numpy()
        n = len(df)

        trades: list[Trade] = []
        open_trade: Trade | None = None
        stop_loss = None

        i = 0
        while i < n:
            if open_trade is None:
                if preds[i] > cfg.entry_threshold:
                    # Entry executes on the NEXT candle after the signal,
                    # never the signal's own -- the signal at i is only
                    # known at i's close.
                    entry_idx = i + 1
                    if entry_idx >= n:
                        break
                    open_trade = Trade(
                        symbol=symbol,
                        entry_time=pd.Timestamp(times[entry_idx]),
                        entry_price=float(prices[entry_idx]),
                        predicted_return=float(preds[i]),
                    )
                    stop_loss = prices[entry_idx] - cfg.stop_loss_atr_mult * atrs[i]
                    i = entry_idx + 1
                    continue
                i += 1
                continue

            hours_held = (pd.Timestamp(times[i]) - open_trade.entry_time).total_seconds() / 3600.0
            if prices[i] <= stop_loss:
                open_trade.exit_time = pd.Timestamp(times[i])
                open_trade.exit_price = float(prices[i])
                open_trade.exit_reason = "stop_loss"
                trades.append(open_trade)
                open_trade = None
            elif hours_held >= cfg.horizon_hours:
                open_trade.exit_time = pd.Timestamp(times[i])
                open_trade.exit_price = float(prices[i])
                open_trade.exit_reason = "horizon"
                trades.append(open_trade)
                open_trade = None
            i += 1

        # A position still open when we run out of available data gets
        # closed explicitly at the last known price, with its reason
        # marked -- it is never dropped silently.
        if open_trade is not None:
            open_trade.exit_time = pd.Timestamp(times[-1])
            open_trade.exit_price = float(prices[-1])
            open_trade.exit_reason = "data_end"
            trades.append(open_trade)

        return trades
