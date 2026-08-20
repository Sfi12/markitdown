"""Compatibility wrapper — use CoinbasePublicMarketData via bot.data."""

from bot.data.coinbase_public import CoinbasePublicMarketData

MarketDataClient = CoinbasePublicMarketData

__all__ = ["MarketDataClient", "CoinbasePublicMarketData"]
