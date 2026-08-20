from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import pandas as pd


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


def compute_rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))


def add_indicators(
    frame: pd.DataFrame,
    ema_fast: int,
    ema_slow: int,
    rsi_period: int,
) -> pd.DataFrame:
    enriched = frame.copy()
    enriched["ema_fast"] = enriched["close"].ewm(span=ema_fast, adjust=False).mean()
    enriched["ema_slow"] = enriched["close"].ewm(span=ema_slow, adjust=False).mean()
    enriched["rsi"] = compute_rsi(enriched["close"], rsi_period)
    return enriched


class TrendRsiStrategy:
    def __init__(
        self,
        ema_fast: int,
        ema_slow: int,
        rsi_period: int,
        rsi_oversold: float,
        rsi_overbought: float,
    ) -> None:
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought

    def evaluate(self, frame: pd.DataFrame, in_position: bool) -> StrategySignal:
        enriched = add_indicators(
            frame,
            self.ema_fast,
            self.ema_slow,
            self.rsi_period,
        )
        latest = enriched.iloc[-1]
        previous = enriched.iloc[-2]
        price = float(latest["close"])
        ema_fast = float(latest["ema_fast"])
        ema_slow = float(latest["ema_slow"])
        rsi = float(latest["rsi"])

        bullish_cross = (
            previous["ema_fast"] <= previous["ema_slow"]
            and latest["ema_fast"] > latest["ema_slow"]
        )
        bearish_cross = (
            previous["ema_fast"] >= previous["ema_slow"]
            and latest["ema_fast"] < latest["ema_slow"]
        )

        if not in_position:
            if bullish_cross and self.rsi_oversold <= rsi <= self.rsi_overbought:
                return StrategySignal(
                    action=SignalAction.BUY,
                    reason="EMA20 kreuzt EMA50 nach oben, RSI im Einstiegsbereich",
                    price=price,
                    ema_fast=ema_fast,
                    ema_slow=ema_slow,
                    rsi=rsi,
                )
            if ema_fast > ema_slow and rsi <= self.rsi_oversold:
                return StrategySignal(
                    action=SignalAction.BUY,
                    reason="Aufwärtstrend + RSI überverkauft",
                    price=price,
                    ema_fast=ema_fast,
                    ema_slow=ema_slow,
                    rsi=rsi,
                )
            return StrategySignal(
                action=SignalAction.HOLD,
                reason="Kein Kaufsignal",
                price=price,
                ema_fast=ema_fast,
                ema_slow=ema_slow,
                rsi=rsi,
            )

        if bearish_cross or rsi >= self.rsi_overbought:
            reason = (
                "EMA20 kreuzt EMA50 nach unten"
                if bearish_cross
                else "RSI überkauft"
            )
            return StrategySignal(
                action=SignalAction.SELL,
                reason=reason,
                price=price,
                ema_fast=ema_fast,
                ema_slow=ema_slow,
                rsi=rsi,
            )

        return StrategySignal(
            action=SignalAction.HOLD,
            reason="Position halten",
            price=price,
            ema_fast=ema_fast,
            ema_slow=ema_slow,
            rsi=rsi,
        )
