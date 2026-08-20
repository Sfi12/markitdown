from __future__ import annotations

from bot.config import BotConfig
from bot.data.base import MarketDataProvider
from bot.data.coinbase_public import CoinbasePublicMarketData
from bot.execution.base import ExecutionProvider
from bot.execution.paper import PaperExecutionProvider
from bot.portfolio.ledger import PortfolioLedger
from bot.risk.manager import RiskManager
from bot.security import assert_paper_trading_mode
from bot.storage import Storage


def create_market_data_provider(config: BotConfig) -> MarketDataProvider:
    return CoinbasePublicMarketData(product_id=config.product_id)


def create_risk_manager(config: BotConfig) -> RiskManager:
    return RiskManager(
        max_trade_eur=config.max_trade_eur,
        stop_loss_pct=config.stop_loss_pct,
        take_profit_pct=config.take_profit_pct,
        symbol=config.product_id,
    )


def create_portfolio_ledger(config: BotConfig) -> PortfolioLedger:
    return PortfolioLedger(start_capital_eur=config.start_capital_eur)


def create_execution_provider(
    config: BotConfig,
    storage: Storage | None = None,
    risk: RiskManager | None = None,
    portfolio: PortfolioLedger | None = None,
) -> ExecutionProvider:
    assert_paper_trading_mode(config.trading_mode)
    return PaperExecutionProvider(
        storage=storage or Storage(config.database_path),
        max_trade_eur=config.max_trade_eur,
        stop_loss_pct=config.stop_loss_pct,
        take_profit_pct=config.take_profit_pct,
        fee_pct=config.fee_pct,
        slippage_pct=config.slippage_pct,
        symbol=config.product_id,
        start_capital_eur=config.start_capital_eur,
        risk=risk or create_risk_manager(config),
        portfolio=portfolio or create_portfolio_ledger(config),
    )
