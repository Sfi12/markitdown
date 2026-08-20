from __future__ import annotations

import pandas as pd


def compute_ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential moving average using pandas ewm(span=period)."""
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """
    RSI on close prices using Wilder's smoothing (ewm alpha=1/period).

    Returns NaN until `period` closes are available.
    """
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))
    # No losses over the window -> RSI 100; flat series -> RSI 50
    rsi = rsi.mask((avg_loss == 0) & (avg_gain > 0), 100.0)
    rsi = rsi.mask((avg_gain == 0) & (avg_loss == 0), 50.0)
    return rsi


def minimum_completed_bars_required(ema_slow: int, rsi_period: int) -> int:
    """Minimum number of completed candles before indicators are valid."""
    return max(ema_slow, rsi_period)


def completed_candles_only(frame: pd.DataFrame) -> pd.DataFrame:
    """
    Exclude the last candle, which may still be open on live feeds.

    Strategy signals MUST be derived from completed candles only to avoid
    look-ahead bias from the currently forming bar.
    """
    if frame.empty:
        return frame.copy()
    if len(frame) == 1:
        return frame.iloc[0:0].copy()
    return frame.iloc[:-1].copy()


def add_indicators(
    frame: pd.DataFrame,
    ema_fast: int,
    ema_slow: int,
    rsi_period: int,
) -> pd.DataFrame:
    enriched = frame.copy()
    enriched["ema_fast"] = compute_ema(enriched["close"], ema_fast)
    enriched["ema_slow"] = compute_ema(enriched["close"], ema_slow)
    enriched["rsi"] = compute_rsi(enriched["close"], rsi_period)
    return enriched


def indicators_ready(
    enriched: pd.DataFrame,
    ema_slow: int,
    rsi_period: int,
) -> bool:
    if len(enriched) < minimum_completed_bars_required(ema_slow, rsi_period):
        return False
    signal_row = enriched.iloc[-1]
    return not (
        pd.isna(signal_row["ema_fast"])
        or pd.isna(signal_row["ema_slow"])
        or pd.isna(signal_row["rsi"])
    )
