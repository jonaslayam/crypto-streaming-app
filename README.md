# crypto-streaming-app

[![CI](https://github.com/jonaslayam/crypto-streaming-app/actions/workflows/ci.yml/badge.svg)](https://github.com/jonaslayam/crypto-streaming-app/actions/workflows/ci.yml)

A real-time crypto market data pipeline (Binance → Redpanda → Oracle Autonomous Data Warehouse → dbt → Oracle ML) built to evaluate swing-trading opportunities on a days-to-weeks horizon — not high-frequency trading.

This README is written in three parts most portfolio projects skip: what it does, how to run it, and — the part that matters most — what I found wrong with it, how I found it, and how I fixed it. That last section is not an afterthought; it's the actual point of this repository.

## What it does

The pipeline ingests 1-hour candles for 10 USDT pairs (BTC, ETH, SOL, BNB, ADA, XRP, DOT, DOGE, AVAX, LINK) from Binance, keeps a live stream flowing through Kafka/Redpanda while a separate backfill process keeps 2 years of history current in Oracle, then runs a dbt project on top of that data to build technical-indicator features (RSI, ATR, Bollinger Bands, z-scores, volume ratios), trains an XGBoost regression model inside Oracle (`DBMS_DATA_MINING`) to predict 72-hour forward returns, and turns those predictions into rule-based entry/exit signals.

It does **not** place real orders. There is no execution layer anywhere in this repo — that's deliberate, explained in the findings section below.

## Architecture

```
Binance WebSocket ──┬──► live queue ──► Redpanda (Kafka) ──► processor ──► Oracle ADW (CRYPTO_CANDLES_1H)
                     │
                     └──► SmartDeepBackfill (direct write, no Kafka) ──► Oracle ADW (CRYPTO_CANDLES_1H)

Oracle ADW ──► dbt (staging → intermediate → marts) ──► fct_swing_features
                                                              │
                                        ┌─────────────────────┴─────────────────────┐
                                        ▼                                           ▼
                              ml_train_data / ml_test_data              fct_trading_signals
                              (curated, leak-free feature set)          (PREDICTION() against the
                                        │                                trained model, rule-based
                                        ▼                                entry/exit logic)
                        DBMS_DATA_MINING.CREATE_MODEL
                        → SWING_XGB_72H_V2 (XGBoost)
```

Two producers write to the same table concurrently: a `websocket_loop` streaming live candles through Redpanda for the `processor` service to persist, and a `SmartDeepBackfill` state machine writing directly to Oracle to keep 2 years of history intact and patrol for gaps every 30 minutes. Both paths insert through the same idempotent statement (`IGNORE_ROW_ON_DUPKEY_INDEX`), so replays and overlapping writes never duplicate a candle.

Infrastructure (VCN, an ARM compute instance, the Autonomous Database, IAM, budget alerts) lives in a separate repository: **[crypto-streaming-iac](https://github.com/jonaslayam/crypto-streaming-iac)**, provisioned with Terraform against OCI's Always Free tier.

## Running it

```bash
cp .env.example .env   # fill in your own Binance/Oracle credentials
docker compose up -d   # redpanda, console, redis, producer, processor
```

The producer runs the live WebSocket stream and the 2-year backfill concurrently on first start; subsequent starts only fill whatever gap accumulated while it was down.

On a fresh Oracle instance, run the bootstrap once first — it creates the `TRADER_DATA` (raw ingestion) and `DBT_ANALYTICS` (dbt + OML) schemas the rest of the project connects as, and grants `DBT_ANALYTICS` read access to `TRADER_DATA`'s candle table:

```bash
python database/scripts/bootstrap.py
```

To build the dbt models and train the model, from `transform/`:

```bash
dbt run
```

(a `profiles.yml` pointing at the `DBT_ANALYTICS` schema is required and is not included — see `.env.example` for the connection fields it needs)

To run the honest backtest (no Oracle connection needed — it reads a CSV export):

```bash
python optimization/extract_data.py     # dumps fct_swing_features to optimization/data/crypto_history.csv
python -m backtest --dry-run            # sanity-checks the engine's mechanics
python -m backtest --report             # the real thing: IC, corrected t-stat, buy&hold benchmark
```

To run the test suite (no Oracle or Redis connection needed — Redis is faked, Oracle is mocked at the client boundary):

```bash
pip install -r requirements-dev.txt -r producer/requirements.txt -r backtest/requirements.txt
pytest
```

## What I found, and how I tested it

I audited this project against its own data and its own code, then built the tooling to prove — not assert — what was actually wrong. Three bugs, independently discovered, that compounded into a number that looked plausible enough to never get questioned.

### 1. Lookahead bias in the parameter search

`archive/optimize_swing.py` (kept, not deleted, specifically so this claim is checkable) optimized 8 strategy thresholds with Optuna against a backtest where line 12 read:

```python
df['pred_72h'] = df['TARGET_RETURN_72H']
```

That's not a prediction. That's the actual realized 72-hour return, used as if it were the model's forecast. The "optimized" thresholds derived from this were pure noise dressed up as a tuned strategy.

### 2. An orphaned-position bug that quietly hid bug #1

The same script's simulation loop tracked one open position across a CSV sorted by timestamp — which meant its 10 symbols were interleaved row by row. The symbol changed on **98.81%** of consecutive rows, and the loop silently dropped the open position (no P&L recorded) every time that happened. Result: 30,520 positions opened, 26 closed. The two bugs partially cancelled each other out in the final headline number, which is exactly why neither one got caught — a $1,000 balance that becomes $1,247 (~11%/year) doesn't look broken. It looks like a mediocre but plausible bot. Fixing lookahead bias alone (keeping the orphaning bug) produces $8.6×10²⁸ from $1,000; fixing the orphaning bug alone (keeping the lookahead bias) collapses back toward a small, unremarkable number. Neither result on its own would have raised an eyebrow.

### 3. Train/serve skew from `select *`

`ml_train_data.sql`, `ml_test_data.sql`, and `fct_trading_signals.sql` all pulled every column from `fct_swing_features` — including the very `TARGET_RETURN_*` columns the model was supposed to predict, and the other-horizon targets (24h, 168h), which correlate with the 72h target strongly enough (0.576 and 0.645) to have functioned as leaked predictors during training. At inference time, the live candle's own target column is `NULL` by construction — a mismatch between what the model saw in training and what it sees in production. The signals layer also called a model name (`CRYPTO_MODEL_72H_V2`) and described an algorithm ("SVM de AutoML") that don't match what the repo actually trains (`SWING_XGB_72H_V2`, XGBoost).

**Fix:** `transform/macros/feature_set.sql` now defines the canonical predictor list — 6 already-normalized features (RSI, z-scores, a range-position ratio, relative volume), explicitly excluding both the leaked targets and non-stationary absolute price/volume levels that don't generalize across a $79,000 BTC and a $0.20 ADA in the same training run. Both the training views and the inference query call the same macro, so they cannot drift apart again.

### The honest replacement: `backtest/`

Fixing the leaks doesn't tell you whether there's a real strategy underneath — it just stops lying about it. `backtest/` is a from-scratch validation harness built to answer that question properly:

- **Purged walk-forward, expanding window** (`backtest/splits.py`) — no random `train_test_split` on time series. Every fold drops training rows whose label window would overlap into that fold's own test period.
- **Per-symbol simulation** (`backtest/engine.py`) — the structural fix for bug #2: there is no shared index between symbols to begin with, so a position can no longer close silently because a different coin's row came next.
- **t-stat corrected for overlap** (`backtest/metrics.py`) — a signal evaluated on every candle produces trades that share almost their entire holding window with their neighbors. The textbook t-stat (`sqrt(n_trades)`) treats those as independent observations and inflates significance. The correction collapses the effective sample size to `n_trades / horizon_hours`.
- **Information Coefficient and a buy&hold benchmark**, because a return in isolation — positive or negative — says nothing without both.

Run against the full 2-year, 10-symbol history (175,200 candles, backfilled fresh for this validation):

| Horizon | Trades | IC | t (naive) | t (corrected) | Significant? |
|---|---|---|---|---|---|
| 24h | 6,036 | -0.0065 | -4.85 | -0.99 | No |
| 72h | 3,168 | +0.0223 | -2.56 | -0.30 | No |
| 168h | 1,738 | +0.0211 | -2.09 | -0.17 | No |

Buy&hold benchmark over the same period: **-35.2%** (the market fell hard during this window). None of the three horizons survive the correction — the naive 24h t-stat (-4.85) looks close to damning on its own, which is precisely the trap the correction exists to catch. `entry_threshold` is deliberately left at its uncalibrated default (`0.0`): searching for the best threshold against the same folds used to report this result would reintroduce leakage through parameter selection, just one layer higher than bug #1. Full numbers, per-fold breakdown, and an equity/IC chart are in `backtest/results/`.

One thing worth not glossing over: at 72h and 168h the IC is small but *positive*, even though the naive entry rule still loses money net of fees. That's not a conclusion — with this few independent observations it isn't statistically distinguishable from noise either — but it's an honest asymmetry in the data that a smoothed-over report would have hidden.

### What's genuinely solid

Not everything here needed fixing. Worth pointing out explicitly, because it doesn't show up anywhere unless someone reads the code directly:

- **Atomic compare-and-set in Redis** (`producer/state.py`) — a Lua script guarantees the "update only if newer" check-and-set is race-free, no lock needed.
- **Binance rate-limit tracking** (`producer/backfill.py`) — a Redis counter with a 60-second TTL mirrors Binance's own weight window, so the backfill throttles itself before Binance does it for you.
- **Resumable, self-healing backfill** — `SmartDeepBackfill` resumes from the last timestamp actually in Oracle, and a perpetual 30-minute monitor loop re-reads `settings.yaml` on every pass, so adding a ticker to the config is a hot-reload, not a redeploy.
- **Idempotent inserts** (`database/oracle_manager.py`) — `IGNORE_ROW_ON_DUPKEY_INDEX` means the live stream and the backfill can write the same candle twice without ever duplicating a row.

### What's still out of scope, on purpose

- **No execution layer.** Nothing in this repo places an order. `fct_trading_signals.sql` produces a recommendation, and that's where it stops.
- **No re-tuned strategy parameters.** The 8 thresholds in `transform/dbt_project.yml` that drive `fct_trading_signals.sql`'s entry/exit rules came out of the same broken Optuna run described above and are flagged in the file itself as unvalidated placeholders — they're kept only because dbt won't compile without them, not because they mean anything. Nothing has replaced them with a validated alternative, and — per the leakage argument above — nothing will, on this dataset, without a properly nested validation split and a lot more independent data than 2 years of hourly candles provides.
- **On-chain data, whale tracking, graph models.** Directionally reasonable ideas, but a separate project: the data acquisition cost alone (a paid vendor, or running a full node) usually exceeds what a strategy like this one would realistically earn.
