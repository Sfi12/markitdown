"""Strategy package — EMA/RSI paper-trading signals from completed candles only."""

from bot.strategy.ema_rsi import EmaRsiStrategy, SignalAction, StrategySignal, TrendRsiStrategy
from bot.strategy.indicators import (
    add_indicators,
    completed_candles_only,
    compute_ema,
    compute_rsi,
    indicators_ready,
    minimum_completed_bars_required,
)

__all__ = [
    "EmaRsiStrategy",
    "TrendRsiStrategy",
    "SignalAction",
    "StrategySignal",
    "add_indicators",
    "completed_candles_only",
    "compute_ema",
    "compute_rsi",
    "indicators_ready",
    "minimum_completed_bars_required",
]
