from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import pandas as pd

from bot.strategy.indicators import (
    add_indicators,
    completed_candles_only,
    indicators_ready,
)


class SignalAction(str, Enum):
    HOLD = "hold"
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True)
class StrategySignal:
    action: SignalAction
    reason: str
    price: float
    ema_fast: float
    ema_slow: float
    rsi: float
    signal_candle_timestamp: str | None = None


class EmaRsiStrategy:
    """
    Trend + momentum strategy using only completed candles.

    Entry:  EMA20 > EMA50 AND RSI14 > rsi_entry  (flat only)
    Exit:   EMA20 < EMA50 OR RSI14 < rsi_exit     (in position only)

    Stop-loss and take-profit are handled separately by the execution/risk layer.
    """

    def __init__(
        self,
        ema_fast: int = 20,
        ema_slow: int = 50,
        rsi_period: int = 14,
        rsi_entry: float = 50.0,
        rsi_exit: float = 45.0,
    ) -> None:
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.rsi_period = rsi_period
        self.rsi_entry = rsi_entry
        self.rsi_exit = rsi_exit

    def evaluate(
        self,
        frame: pd.DataFrame,
        in_position: bool,
        *,
        exclude_open_candle: bool = True,
    ) -> StrategySignal:
        """
        Evaluate strategy on candle data.

        exclude_open_candle=True (live): drop the last bar, which may still be forming.
        exclude_open_candle=False (backtest): all bars in `frame` are already closed.
        """
        candles = completed_candles_only(frame) if exclude_open_candle else frame.copy()
        if candles.empty:
            return self._hold(0.0, 0.0, 0.0, 0.0, "NO_SIGNAL: insufficient candle data")

        enriched = add_indicators(
            candles,
            self.ema_fast,
            self.ema_slow,
            self.rsi_period,
        )

        if not indicators_ready(enriched, self.ema_slow, self.rsi_period):
            return self._hold(
                float(candles.iloc[-1]["close"]),
                0.0,
                0.0,
                0.0,
                "NO_SIGNAL: insufficient data for EMA50/RSI14",
                signal_candle_timestamp=str(candles.iloc[-1]["timestamp"]),
            )

        signal_row = enriched.iloc[-1]
        price = float(signal_row["close"])
        ema_fast = float(signal_row["ema_fast"])
        ema_slow = float(signal_row["ema_slow"])
        rsi = float(signal_row["rsi"])
        candle_ts = str(signal_row["timestamp"])

        if not in_position:
            if ema_fast > ema_slow and rsi > self.rsi_entry:
                return StrategySignal(
                    action=SignalAction.BUY,
                    reason="EMA20 above EMA50 and RSI above 50",
                    price=price,
                    ema_fast=ema_fast,
                    ema_slow=ema_slow,
                    rsi=rsi,
                    signal_candle_timestamp=candle_ts,
                )
            return self._hold(
                price,
                ema_fast,
                ema_slow,
                rsi,
                "HOLD: no entry signal",
                signal_candle_timestamp=candle_ts,
            )

        if ema_fast < ema_slow:
            return StrategySignal(
                action=SignalAction.SELL,
                reason="EMA20 below EMA50",
                price=price,
                ema_fast=ema_fast,
                ema_slow=ema_slow,
                rsi=rsi,
                signal_candle_timestamp=candle_ts,
            )
        if rsi < self.rsi_exit:
            return StrategySignal(
                action=SignalAction.SELL,
                reason="RSI below 45",
                price=price,
                ema_fast=ema_fast,
                ema_slow=ema_slow,
                rsi=rsi,
                signal_candle_timestamp=candle_ts,
            )

        return self._hold(
            price,
            ema_fast,
            ema_slow,
            rsi,
            "HOLD: maintain position",
            signal_candle_timestamp=candle_ts,
        )

    def _hold(
        self,
        price: float,
        ema_fast: float,
        ema_slow: float,
        rsi: float,
        reason: str,
        signal_candle_timestamp: str | None = None,
    ) -> StrategySignal:
        return StrategySignal(
            action=SignalAction.HOLD,
            reason=reason,
            price=price,
            ema_fast=ema_fast,
            ema_slow=ema_slow,
            rsi=rsi,
            signal_candle_timestamp=signal_candle_timestamp,
        )


TrendRsiStrategy = EmaRsiStrategy
