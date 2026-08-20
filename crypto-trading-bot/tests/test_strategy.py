from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from bot.config import BotConfig
from bot.strategy import (
    EmaRsiStrategy,
    SignalAction,
    add_indicators,
    completed_candles_only,
    compute_ema,
    compute_rsi,
    minimum_completed_bars_required,
)

def make_candles(closes: list[float], start_ts: str = "2026-01-01 00:00:00+00:00") -> pd.DataFrame:
    timestamps = pd.date_range(start_ts, periods=len(closes), freq="h", tz="UTC")
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": closes,
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes],
            "close": closes,
            "volume": [1.0] * len(closes),
        }
    )


def build_trending_candles(count: int = 60, base: float = 100.0, step: float = 0.5) -> pd.DataFrame:
    closes = [base + (i * step) for i in range(count)]
    return make_candles(closes)


def force_indicators(
    ema_fast: float,
    ema_slow: float,
    rsi: float,
    close: float = 100.0,
    count: int = 60,
) -> pd.DataFrame:
    frame = build_trending_candles(count=count)
    enriched = add_indicators(frame, 20, 50, 14)
    enriched.loc[enriched.index[-1], "ema_fast"] = ema_fast
    enriched.loc[enriched.index[-1], "ema_slow"] = ema_slow
    enriched.loc[enriched.index[-1], "rsi"] = rsi
    enriched.loc[enriched.index[-1], "close"] = close
    return enriched


@pytest.fixture
def strategy() -> EmaRsiStrategy:
    return EmaRsiStrategy(
        ema_fast=20,
        ema_slow=50,
        rsi_period=14,
        rsi_entry=50.0,
        rsi_exit=45.0,
    )


def test_config_defaults(config: BotConfig) -> None:
    assert config.ema_fast == 20
    assert config.ema_slow == 50
    assert config.rsi_period == 14
    assert config.rsi_entry == 50.0
    assert config.rsi_exit == 45.0
    assert config.slippage_pct == 0.10


def test_slippage_default_from_config(config: BotConfig) -> None:
    assert config.slippage_pct == pytest.approx(0.10)


def test_minimum_completed_bars_required() -> None:
    assert minimum_completed_bars_required(50, 14) == 50


def test_ema20_ema50_on_known_series() -> None:
    closes = pd.Series([float(i) for i in range(1, 61)])
    ema20 = compute_ema(closes, 20)
    ema50 = compute_ema(closes, 50)
    assert pd.isna(ema20.iloc[18])
    assert not pd.isna(ema20.iloc[19])
    assert pd.isna(ema50.iloc[48])
    assert not pd.isna(ema50.iloc[49])
    assert ema20.iloc[-1] > ema50.iloc[-1]


def test_rsi14_on_monotonic_upward_series() -> None:
    closes = pd.Series([float(i) for i in range(1, 32)])
    rsi = compute_rsi(closes, 14)
    first_valid = rsi.first_valid_index()
    assert first_valid is not None
    assert rsi.loc[first_valid:].eq(100.0).all()


def test_rsi_insufficient_data_returns_nan() -> None:
    closes = pd.Series([100.0, 101.0, 99.0])
    rsi = compute_rsi(closes, 14)
    assert rsi.isna().all()


def test_insufficient_data_yields_no_signal(strategy: EmaRsiStrategy) -> None:
    frame = make_candles([100.0] * 10)
    signal = strategy.evaluate(frame, in_position=False, exclude_open_candle=False)
    assert signal.action == SignalAction.HOLD
    assert "NO_SIGNAL" in signal.reason


def test_buy_signal_when_ema_and_rsi_conditions_met(strategy: EmaRsiStrategy) -> None:
    frame = build_trending_candles(60)
    enriched = add_indicators(frame, 20, 50, 14)
    last = enriched.iloc[-1]
    assert last["ema_fast"] > last["ema_slow"]
    assert last["rsi"] > 50

    signal = strategy.evaluate(frame, in_position=False, exclude_open_candle=False)
    assert signal.action == SignalAction.BUY
    assert signal.reason == "EMA20 above EMA50 and RSI above 50"


def test_hold_when_ema20_not_above_ema50(strategy: EmaRsiStrategy) -> None:
    enriched = add_indicators(build_trending_candles(60), 20, 50, 14)
    enriched.loc[enriched.index[-1], "ema_fast"] = 90.0
    enriched.loc[enriched.index[-1], "ema_slow"] = 100.0
    enriched.loc[enriched.index[-1], "rsi"] = 60.0
    with patch("bot.strategy.ema_rsi.add_indicators", return_value=enriched):
        signal = strategy.evaluate(build_trending_candles(60), in_position=False, exclude_open_candle=False)
    assert signal.action == SignalAction.HOLD


def test_hold_when_rsi_not_above_entry(strategy: EmaRsiStrategy) -> None:
    enriched = add_indicators(build_trending_candles(60), 20, 50, 14)
    enriched.loc[enriched.index[-1], "ema_fast"] = 110.0
    enriched.loc[enriched.index[-1], "ema_slow"] = 100.0
    enriched.loc[enriched.index[-1], "rsi"] = 50.0
    with patch("bot.strategy.ema_rsi.add_indicators", return_value=enriched):
        signal = strategy.evaluate(build_trending_candles(60), in_position=False, exclude_open_candle=False)
    assert signal.action == SignalAction.HOLD


def test_sell_on_ema_cross_down(strategy: EmaRsiStrategy) -> None:
    enriched = add_indicators(build_trending_candles(60), 20, 50, 14)
    enriched.loc[enriched.index[-1], "ema_fast"] = 90.0
    enriched.loc[enriched.index[-1], "ema_slow"] = 100.0
    enriched.loc[enriched.index[-1], "rsi"] = 55.0
    with patch("bot.strategy.ema_rsi.add_indicators", return_value=enriched):
        signal = strategy.evaluate(build_trending_candles(60), in_position=True, exclude_open_candle=False)
    assert signal.action == SignalAction.SELL
    assert signal.reason == "EMA20 below EMA50"


def test_sell_on_rsi_below_exit(strategy: EmaRsiStrategy) -> None:
    enriched = add_indicators(build_trending_candles(60), 20, 50, 14)
    enriched.loc[enriched.index[-1], "ema_fast"] = 110.0
    enriched.loc[enriched.index[-1], "ema_slow"] = 100.0
    enriched.loc[enriched.index[-1], "rsi"] = 44.0
    with patch("bot.strategy.ema_rsi.add_indicators", return_value=enriched):
        signal = strategy.evaluate(build_trending_candles(60), in_position=True, exclude_open_candle=False)
    assert signal.action == SignalAction.SELL
    assert signal.reason == "RSI below 45"


def test_buy_not_emitted_when_already_in_position(strategy: EmaRsiStrategy) -> None:
    frame = build_trending_candles(60)
    signal = strategy.evaluate(frame, in_position=True, exclude_open_candle=False)
    assert signal.action != SignalAction.BUY


def test_sell_not_emitted_when_flat(strategy: EmaRsiStrategy) -> None:
    frame = build_trending_candles(60)
    enriched = add_indicators(frame, 20, 50, 14)
    enriched.loc[enriched.index[-1], "ema_fast"] = 90.0
    enriched.loc[enriched.index[-1], "ema_slow"] = 100.0
    enriched.loc[enriched.index[-1], "rsi"] = 40.0

    signal = strategy.evaluate(
        enriched[["timestamp", "open", "high", "low", "close", "volume"]],
        in_position=False,
        exclude_open_candle=False,
    )
    assert signal.action != SignalAction.SELL


def test_completed_candles_only_excludes_open_bar() -> None:
    frame = make_candles([100.0, 101.0, 102.0, 103.0])
    completed = completed_candles_only(frame)
    assert len(completed) == 3
    assert completed.iloc[-1]["close"] == 102.0


def test_live_mode_uses_penultimate_completed_candle(strategy: EmaRsiStrategy) -> None:
    frame = build_trending_candles(61)
    poisoned = frame.copy()
    poisoned.loc[poisoned.index[-1], "close"] = 999.0

    signal = strategy.evaluate(poisoned, in_position=False, exclude_open_candle=True)
    assert signal.signal_candle_timestamp is not None
    assert signal.price != 999.0


def test_no_look_ahead_signal_ignores_last_open_candle(strategy: EmaRsiStrategy) -> None:
    base = build_trending_candles(61)
    poisoned = base.copy()
    poisoned.loc[poisoned.index[-1], "close"] = 1_000_000.0

    signal_open = strategy.evaluate(poisoned, in_position=False, exclude_open_candle=True)
    signal_closed = strategy.evaluate(base.iloc[:-1], in_position=False, exclude_open_candle=False)

    assert signal_open.action == signal_closed.action
    assert signal_open.price == signal_closed.price
    assert signal_open.ema_fast == pytest.approx(signal_closed.ema_fast)


def test_backtest_and_live_share_same_strategy_class() -> None:
    from bot.engine import Backtester, TradingEngine

    config = BotConfig.load()
    engine_strategy = TradingEngine(config).strategy
    backtest_strategy = Backtester(config).strategy
    assert type(engine_strategy) is type(backtest_strategy) is EmaRsiStrategy
