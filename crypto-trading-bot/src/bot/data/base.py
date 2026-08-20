from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class MarketDataProvider(ABC):
    """Read-only market data access."""

    @property
    @abstractmethod
    def product_id(self) -> str:
        """Trading pair identifier, e.g. BTC-EUR."""

    @abstractmethod
    def fetch_candles(self, granularity: int, limit: int = 300) -> pd.DataFrame:
        """Return OHLCV candles sorted by timestamp ascending."""

    @abstractmethod
    def fetch_spot_price(self) -> float:
        """Return the current spot price for the configured product."""
