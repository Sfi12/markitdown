"""Resilient market-data wrapper — retries without inventing candles."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Callable

import pandas as pd
import requests

from bot.data.base import MarketDataProvider


class MarketDataError(RuntimeError):
    """Raised when market data cannot be fetched after retries."""


class ResilientMarketData(MarketDataProvider):
    """
    Wraps a MarketDataProvider with retries for timeouts / network / empty data.

    Never fabricates OHLCV rows. Empty or corrupt payloads are errors.
    """

    def __init__(
        self,
        inner: MarketDataProvider,
        *,
        retries: int = 3,
        retry_delay_seconds: float = 2.0,
        on_retry: Callable[[str, int, BaseException], None] | None = None,
    ) -> None:
        self._inner = inner
        self.retries = max(1, retries)
        self.retry_delay_seconds = max(0.0, retry_delay_seconds)
        self.on_retry = on_retry

    @property
    def product_id(self) -> str:
        return self._inner.product_id

    def fetch_candles(self, granularity: int, limit: int = 300) -> pd.DataFrame:
        return self._with_retry(
            "fetch_candles",
            lambda: self._validate_candles(self._inner.fetch_candles(granularity, limit)),
        )

    def fetch_candles_range(
        self,
        granularity: int,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        fetch_range = getattr(self._inner, "fetch_candles_range", None)
        if not callable(fetch_range):
            raise MarketDataError("Underlying provider has no fetch_candles_range")
        return self._with_retry(
            "fetch_candles_range",
            lambda: self._validate_candles(fetch_range(granularity, start, end)),
        )

    def fetch_spot_price(self) -> float:
        return self._with_retry(
            "fetch_spot_price",
            lambda: self._validate_price(self._inner.fetch_spot_price()),
        )

    def _with_retry(self, operation: str, fn: Callable[[], object]) -> object:
        last_error: BaseException | None = None
        for attempt in range(1, self.retries + 1):
            try:
                return fn()
            except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as exc:
                last_error = exc
                self._notify(operation, attempt, exc)
            except MarketDataError as exc:
                last_error = exc
                self._notify(operation, attempt, exc)
            except ValueError as exc:
                last_error = MarketDataError(str(exc))
                self._notify(operation, attempt, last_error)
            except Exception as exc:  # noqa: BLE001 — convert to market-data failure
                last_error = MarketDataError(f"{type(exc).__name__}: {exc}")
                self._notify(operation, attempt, last_error)
            if attempt < self.retries and self.retry_delay_seconds:
                time.sleep(self.retry_delay_seconds)
        raise MarketDataError(
            f"{operation} failed after {self.retries} attempts: {last_error}"
        ) from last_error

    def _notify(self, operation: str, attempt: int, exc: BaseException) -> None:
        if self.on_retry is not None:
            self.on_retry(operation, attempt, exc)

    @staticmethod
    def _validate_candles(frame: pd.DataFrame) -> pd.DataFrame:
        if frame is None or frame.empty:
            raise MarketDataError("empty candle response")
        required = {"timestamp", "open", "high", "low", "close", "volume"}
        missing = required - set(frame.columns)
        if missing:
            raise MarketDataError(f"corrupt candle payload, missing columns: {sorted(missing)}")
        if frame["close"].isna().any() or (frame["close"] <= 0).any():
            raise MarketDataError("corrupt candle payload: invalid close prices")
        return frame

    @staticmethod
    def _validate_price(price: float) -> float:
        value = float(price)
        if value <= 0 or value != value:  # NaN check
            raise MarketDataError(f"invalid spot price: {price}")
        return value
