from __future__ import annotations

from bot.config import BotConfig
from bot.data.base import MarketDataProvider
from bot.data.coinbase_public import CoinbasePublicMarketData
from bot.execution.base import ExecutionProvider
from bot.execution.paper import PaperExecutionProvider
from bot.security import assert_paper_trading_mode
from bot.storage import Storage


def create_market_data_provider(config: BotConfig) -> MarketDataProvider:
    return CoinbasePublicMarketData(product_id=config.product_id)


def create_execution_provider(
    config: BotConfig,
    storage: Storage | None = None,
) -> ExecutionProvider:
    assert_paper_trading_mode(config.trading_mode)
    return PaperExecutionProvider(
        storage=storage or Storage(config.database_path),
        max_trade_eur=config.max_trade_eur,
        stop_loss_pct=config.stop_loss_pct,
        take_profit_pct=config.take_profit_pct,
        fee_pct=config.fee_pct,
        slippage_pct=config.slippage_pct,
    )
