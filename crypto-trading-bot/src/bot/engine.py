from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from bot.backtest.engine import ExtendedBacktestResult, StrategyBacktester
from bot.bootstrap import (
    create_execution_provider,
    create_market_data_provider,
    create_portfolio_ledger,
    create_risk_manager,
)
from bot.config import BotConfig
from bot.data.base import MarketDataProvider
from bot.execution.base import ExecutionProvider
from bot.performance import PerformanceCalculator, PerformanceMetrics
from bot.security import enforce_paper_trading_startup
from bot.storage import BotState, Storage
from bot.storage import utc_now
from bot.strategy import EmaRsiStrategy, SignalAction, add_indicators


# Backward-compatible alias used by older imports / dashboard smoke tests.
BacktestResult = ExtendedBacktestResult


@dataclass(frozen=True)
class LegacyBacktestResult:
    start_capital_eur: float
    end_capital_eur: float
    total_return_pct: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    max_drawdown_pct: float
    trades: list[dict[str, float | str]]
    metrics: PerformanceMetrics | None = None


class TradingEngine:
    def __init__(
        self,
        config: BotConfig,
        market_data: MarketDataProvider | None = None,
        execution: ExecutionProvider | None = None,
        risk: RiskManager | None = None,
        portfolio: PortfolioLedger | None = None,
    ) -> None:
        enforce_paper_trading_startup(config.trading_mode)
        self.config = config
        self.storage = Storage(config.database_path)
        self.market_data = market_data or create_market_data_provider(config)
        self.risk = risk or create_risk_manager(config)
        self.portfolio = portfolio or create_portfolio_ledger(config)
        self.execution = execution or create_execution_provider(
            config,
            self.storage,
            risk=self.risk,
            portfolio=self.portfolio,
        )
        self.strategy = EmaRsiStrategy(
            ema_fast=config.ema_fast,
            ema_slow=config.ema_slow,
            rsi_period=config.rsi_period,
            rsi_entry=config.rsi_entry,
            rsi_exit=config.rsi_exit,
        )
        self.performance = PerformanceCalculator(
            start_capital=config.start_capital_eur,
            timezone_name=config.timezone,
        )

    @property
    def market(self) -> MarketDataProvider:
        """Compatibility alias used by the dashboard."""
        return self.market_data

    @property
    def trader(self) -> ExecutionProvider:
        """Compatibility alias used by run_bot.py."""
        return self.execution

    def initialize(self) -> BotState:
        state = self.storage.ensure_state(self.config.start_capital_eur)
        self.storage.add_log("info", "Paper-Trading-Bot initialisiert")
        return state

    def get_performance(self, market_price: float | None = None) -> PerformanceMetrics:
        state = self.storage.ensure_state(self.config.start_capital_eur)
        price = market_price
        if price is None:
            price = state.last_price if state.last_price is not None else 0.0
        return self.performance.compute(
            state=state,
            market_price=float(price),
            trades=self.storage.list_trades(limit=10_000),
            snapshots=self.storage.list_snapshots(limit=10_000),
        )

    def tick(self) -> BotState:
        state = self.storage.ensure_state(self.config.start_capital_eur)
        candles = self.market_data.fetch_candles(
            granularity=self.config.candle_granularity,
            limit=self.config.candle_limit,
        )
        spot_price = self.market_data.fetch_spot_price()

        risk_signal = self.risk.check_exits(state, spot_price)
        if risk_signal is not None:
            signal = risk_signal
        else:
            signal = self.strategy.evaluate(
                candles,
                in_position=state.in_position,
                exclude_open_candle=True,
            )

        state.last_price = spot_price
        state.last_signal = signal.reason
        state.last_update = utc_now().isoformat()

        if signal.action in (SignalAction.BUY, SignalAction.SELL):
            signal = signal.__class__(
                action=signal.action,
                reason=signal.reason,
                price=spot_price,
                ema_fast=signal.ema_fast,
                ema_slow=signal.ema_slow,
                rsi=signal.rsi,
            )
            state, result = self.execution.execute_signal(state, signal)
            if not result.executed and signal.action != SignalAction.HOLD:
                self.storage.add_log("info", result.message)

        snap = self.portfolio.snapshot(state, spot_price)
        self.storage.add_snapshot(
            price=spot_price,
            portfolio_value_eur=snap.portfolio_value,
            cash_eur=state.cash_eur,
            btc_amount=state.btc_amount,
            realized_pnl=snap.realized_pnl,
            unrealized_pnl=snap.unrealized_pnl,
            total_pnl=snap.total_pnl,
        )
        self.storage.save_state(state)
        return state

    def set_running(self, running: bool) -> BotState:
        state = self.storage.ensure_state(self.config.start_capital_eur)
        state.is_running = running
        state.last_update = utc_now().isoformat()
        self.storage.save_state(state)
        message = "Bot gestartet" if running else "Bot gestoppt"
        self.storage.add_log("info", message)
        return state

    def reset(self) -> BotState:
        self.storage.reset(self.config.start_capital_eur)
        return self.storage.ensure_state(self.config.start_capital_eur)

    def get_indicator_frame(self) -> pd.DataFrame:
        candles = self.market_data.fetch_candles(
            granularity=self.config.candle_granularity,
            limit=self.config.candle_limit,
        )
        return add_indicators(
            candles,
            self.config.ema_fast,
            self.config.ema_slow,
            self.config.rsi_period,
        )


class Backtester:
    """Thin wrapper around StrategyBacktester (Phase G). PAPER ONLY."""

    def __init__(
        self,
        config: BotConfig,
        market_data: MarketDataProvider | None = None,
    ) -> None:
        enforce_paper_trading_startup(config.trading_mode)
        self.config = config
        self._inner = StrategyBacktester(config, market_data=market_data)

    @property
    def market(self) -> MarketDataProvider:
        return self._inner.market_data

    @property
    def market_data(self) -> MarketDataProvider:
        return self._inner.market_data

    @property
    def trader(self) -> ExecutionProvider:
        return self._inner.execution

    @property
    def strategy(self) -> EmaRsiStrategy:
        return self._inner.strategy

    def run(self, candles: pd.DataFrame | None = None) -> BacktestResult:
        return self._inner.run(
            candles=candles,
            period=self.config.backtest_period,
            interval=self.config.backtest_interval,
        )
