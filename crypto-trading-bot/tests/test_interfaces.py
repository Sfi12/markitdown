from __future__ import annotations

import inspect

from bot.data.base import MarketDataProvider
from bot.data.coinbase_public import CoinbasePublicMarketData
from bot.execution.base import ExecutionProvider
from bot.execution.paper import PaperExecutionProvider


def test_market_data_provider_is_abstract() -> None:
    assert inspect.isabstract(MarketDataProvider)
    assert hasattr(MarketDataProvider, "fetch_candles")
    assert hasattr(MarketDataProvider, "fetch_spot_price")


def test_execution_provider_is_abstract() -> None:
    assert inspect.isabstract(ExecutionProvider)
    assert hasattr(ExecutionProvider, "execute_signal")
    assert hasattr(ExecutionProvider, "check_risk_exits")


def test_coinbase_public_implements_market_data_provider() -> None:
    provider = CoinbasePublicMarketData("BTC-EUR")
    assert isinstance(provider, MarketDataProvider)
    assert provider.product_id == "BTC-EUR"


def test_paper_execution_implements_execution_provider() -> None:
    class _Store:
        def add_trade(self, trade: object) -> None:
            return None

        def add_log(self, level: str, message: str) -> None:
            return None

    provider = PaperExecutionProvider(
        storage=_Store(),
        max_trade_eur=10.0,
        stop_loss_pct=1.5,
        take_profit_pct=3.0,
        fee_pct=0.6,
        slippage_pct=0.05,
    )
    assert isinstance(provider, ExecutionProvider)
