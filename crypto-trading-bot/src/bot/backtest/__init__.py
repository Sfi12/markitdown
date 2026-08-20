"""Backtesting package — strategy validation without parameter optimization."""

from bot.backtest.benchmark import BuyAndHoldResult, compute_buy_and_hold
from bot.backtest.data_quality import DataQualityReport, sanitize_candles, validate_candles
from bot.backtest.engine import ExtendedBacktestResult, StrategyBacktester, sample_size_note
from bot.backtest.periods import INTERVALS, PERIODS, resolve_window

__all__ = [
    "BuyAndHoldResult",
    "compute_buy_and_hold",
    "DataQualityReport",
    "sanitize_candles",
    "validate_candles",
    "ExtendedBacktestResult",
    "StrategyBacktester",
    "sample_size_note",
    "INTERVALS",
    "PERIODS",
    "resolve_window",
]
