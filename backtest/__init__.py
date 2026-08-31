"""Honest validation harness for the swing trading strategy.

Replaces the role optimization/optimize_swing.py used to play (see
archive/optimize_swing.py for why that script is unusable: real
lookahead bias in `pred_72h`, plus an orphaned-position bug that
silently dropped ~99% of the exits). This package exists so a positive
or negative result can be trusted, not so the strategy "wins" the
backtest.

Usage:
    python -m backtest --dry-run
    python -m backtest --report
"""
