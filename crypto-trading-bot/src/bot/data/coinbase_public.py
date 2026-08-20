from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

from bot.data.base import MarketDataProvider

COINBASE_EXCHANGE_URL = "https://api.exchange.coinbase.com"
MAX_CANDLES_PER_REQUEST = 300


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
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"No candle data returned for {self._product_id}")
        return self._rows_to_frame(rows).tail(limit).reset_index(drop=True)

    def fetch_candles_range(
        self,
        granularity: int,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """
        Paginate public candles for [start, end].

        Does not invent missing data. If the exchange returns fewer candles
        than expected for the window, the caller must mark insufficient_data.
        """
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        if end <= start:
            raise ValueError("end must be after start")

        collected: list[list[float]] = []
        cursor_end = end
        safety = 0
        while cursor_end > start and safety < 200:
            safety += 1
            chunk_start = max(
                start,
                cursor_end - timedelta(seconds=granularity * MAX_CANDLES_PER_REQUEST),
            )
            response = self.session.get(
                f"{COINBASE_EXCHANGE_URL}/products/{self._product_id}/candles",
                params={
                    "granularity": granularity,
                    "start": chunk_start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                    "end": cursor_end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            rows = response.json()
            if not isinstance(rows, list) or not rows:
                break
            collected.extend(rows)
            oldest = min(int(row[0]) for row in rows)
            next_end = datetime.fromtimestamp(oldest, tz=timezone.utc) - timedelta(
                seconds=granularity
            )
            if next_end >= cursor_end:
                break
            cursor_end = next_end

        if not collected:
            return pd.DataFrame(columns=["timestamp", "low", "high", "open", "close", "volume"])

        frame = self._rows_to_frame(collected)
        mask = (frame["timestamp"] >= pd.Timestamp(start)) & (
            frame["timestamp"] <= pd.Timestamp(end)
        )
        return frame.loc[mask].reset_index(drop=True)

    def fetch_spot_price(self) -> float:
        response = self.session.get(
            f"{COINBASE_EXCHANGE_URL}/products/{self._product_id}/ticker",
            timeout=self.timeout,
        )
        response.raise_for_status()
        return float(response.json()["price"])

    def _rows_to_frame(self, rows: list[list[float]]) -> pd.DataFrame:
        frame = pd.DataFrame(
            rows,
            columns=["timestamp", "low", "high", "open", "close", "volume"],
        )
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="s", utc=True)
        frame = frame.drop_duplicates(subset=["timestamp"], keep="last")
        frame = frame.sort_values("timestamp").reset_index(drop=True)
        for column in ("open", "high", "low", "close", "volume"):
            frame[column] = frame[column].astype(float)
        return frame
