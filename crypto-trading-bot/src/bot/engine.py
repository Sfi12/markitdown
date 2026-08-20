from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

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
from bot.portfolio.ledger import PortfolioLedger
from bot.risk.manager import RiskManager
from bot.security import enforce_paper_trading_startup
from bot.storage import BotState, Storage
from bot.storage import utc_now
from bot.strategy import EmaRsiStrategy, SignalAction, add_indicators


@dataclass(frozen=True)
class BacktestResult:
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
    def __init__(
        self,
        config: BotConfig,
        market_data: MarketDataProvider | None = None,
    ) -> None:
        enforce_paper_trading_startup(config.trading_mode)
        self.config = config
        self.market_data = market_data or create_market_data_provider(config)
        self.risk = create_risk_manager(config)
        self.portfolio = create_portfolio_ledger(config)
        self.performance = PerformanceCalculator(
            start_capital=config.start_capital_eur,
            timezone_name=config.timezone,
        )
        self.strategy = EmaRsiStrategy(
            ema_fast=config.ema_fast,
            ema_slow=config.ema_slow,
            rsi_period=config.rsi_period,
            rsi_entry=config.rsi_entry,
            rsi_exit=config.rsi_exit,
        )
        self.execution = create_execution_provider(
            config,
            storage=_NullStorage(),
            risk=self.risk,
            portfolio=self.portfolio,
        )

    @property
    def market(self) -> MarketDataProvider:
        return self.market_data

    @property
    def trader(self) -> ExecutionProvider:
        return self.execution

    def run(self, candles: pd.DataFrame | None = None) -> BacktestResult:
        frame = candles
        if frame is None:
            frame = self.market_data.fetch_candles(
                granularity=self.config.candle_granularity,
                limit=self.config.candle_limit,
            )
        enriched = add_indicators(
            frame,
            self.config.ema_fast,
            self.config.ema_slow,
            self.config.rsi_period,
        )

        cash_eur = self.config.start_capital_eur
        btc_amount = 0.0
        entry_price: float | None = None
        in_position = False
        trades: list[dict[str, float | str]] = []
        sell_pnls: list[float] = []
        total_fees = 0.0
        equity_curve: list[float] = [self.config.start_capital_eur]
        winning = 0
        losing = 0

        warmup = max(self.config.ema_slow, self.config.rsi_period) + 2
        for index in range(warmup, len(enriched)):
            window = enriched.iloc[: index + 1].copy()
            price = float(window.iloc[-1]["close"])
            state = BotState(
                cash_eur=cash_eur,
                btc_amount=btc_amount,
                entry_price=entry_price,
                in_position=in_position,
                is_running=True,
                last_price=price,
                last_signal="",
                last_update=None,
                total_trades=len(trades),
                realized_pnl_eur=sum(sell_pnls),
            )

            risk_signal = self.risk.check_exits(state, price)
            signal = risk_signal or self.strategy.evaluate(
                window,
                in_position=in_position,
                exclude_open_candle=False,
            )
            if signal.action in (SignalAction.BUY, SignalAction.SELL):
                signal = signal.__class__(
                    action=signal.action,
                    reason=signal.reason,
                    price=price,
                    ema_fast=signal.ema_fast,
                    ema_slow=signal.ema_slow,
                    rsi=signal.rsi,
                )
                state, result = self.execution.execute_signal(state, signal)
                if result.executed and result.fill is not None:
                    fill = result.fill
                    total_fees += fill.fee
                    if signal.action == SignalAction.SELL:
                        pnl = float(fill.pnl)
                        sell_pnls.append(pnl)
                        if pnl >= 0:
                            winning += 1
                        else:
                            losing += 1
                        trades.append(
                            {
                                "timestamp": str(window.iloc[-1]["timestamp"]),
                                "side": "sell",
                                "price": price,
                                "pnl_eur": pnl,
                                "fee": fill.fee,
                                "reason": signal.reason,
                            }
                        )
                    else:
                        trades.append(
                            {
                                "timestamp": str(window.iloc[-1]["timestamp"]),
                                "side": "buy",
                                "price": price,
                                "pnl_eur": 0.0,
                                "fee": fill.fee,
                                "reason": signal.reason,
                            }
                        )
                    cash_eur = state.cash_eur
                    btc_amount = state.btc_amount
                    entry_price = state.entry_price
                    in_position = state.in_position

            portfolio_value = cash_eur + (btc_amount * price)
            equity_curve.append(portfolio_value)

        final_price = float(enriched.iloc[-1]["close"])
        end_capital = cash_eur + (btc_amount * final_price)
        metrics = self.performance.from_backtest_trades(
            start_capital=self.config.start_capital_eur,
            end_capital=end_capital,
            sell_pnls=sell_pnls,
            total_fees=total_fees,
            equity_curve=equity_curve,
        )
        total_return_pct = (metrics.total_return or 0.0) * 100.0

        return BacktestResult(
            start_capital_eur=self.config.start_capital_eur,
            end_capital_eur=end_capital,
            total_return_pct=total_return_pct,
            total_trades=len(sell_pnls),
            winning_trades=winning,
            losing_trades=losing,
            max_drawdown_pct=metrics.max_drawdown_pct or 0.0,
            trades=trades,
            metrics=metrics,
        )


class _NullStorage:
    def add_trade(self, trade: object) -> None:
        return None

    def add_log(self, level: str, message: str) -> None:
        return None
