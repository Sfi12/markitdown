from __future__ import annotations

import pandas as pd
import requests

from bot.data.base import MarketDataProvider

COINBASE_EXCHANGE_URL = "https://api.exchange.coinbase.com"


class CoinbasePublicMarketData(MarketDataProvider):
    """Public Coinbase Exchange market data — read-only, no API key required."""

    def __init__(self, product_id: str, timeout: float = 15.0) -> None:
        self._product_id = product_id
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "crypto-paper-trading-bot/1.0"})

    @property
    def product_id(self) -> str:
        return self._product_id

    def fetch_candles(self, granularity: int, limit: int = 300) -> pd.DataFrame:
        response = self.session.get(
            f"{COINBASE_EXCHANGE_URL}/products/{self._product_id}/candles",
            params={"granularity": granularity},
            timeout=self.timeout,
        )
        response.raise_for_status()
        rows = response.json()
        if not rows:
            raise ValueError(f"No candle data returned for {self._product_id}")

        frame = pd.DataFrame(
            rows,
            columns=["timestamp", "low", "high", "open", "close", "volume"],
        )
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="s", utc=True)
        frame = frame.sort_values("timestamp").tail(limit).reset_index(drop=True)
        for column in ("open", "high", "low", "close", "volume"):
            frame[column] = frame[column].astype(float)
        return frame

    def fetch_spot_price(self) -> float:
        response = self.session.get(
            f"{COINBASE_EXCHANGE_URL}/products/{self._product_id}/ticker",
            timeout=self.timeout,
        )
        response.raise_for_status()
        return float(response.json()["price"])
