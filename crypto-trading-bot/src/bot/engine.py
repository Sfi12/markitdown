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
from bot.data.resilient import MarketDataError
from bot.execution.base import ExecutionProvider
from bot.health import HealthSnapshot, compute_health
from bot.performance import PerformanceCalculator, PerformanceMetrics
from bot.portfolio.ledger import PortfolioLedger
from bot.report import PaperTradingReport, build_paper_report
from bot.risk.manager import RiskManager
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

        def _on_retry(operation: str, attempt: int, exc: BaseException) -> None:
            self.storage.add_log(
                "warning",
                f"Retry {attempt}/{config.market_data_retries} for {operation}: {type(exc).__name__}",
            )

        self.market_data = market_data or create_market_data_provider(
            config,
            on_retry=_on_retry,
        )
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

    def get_health(self, state: BotState | None = None) -> HealthSnapshot:
        current = state or self.storage.ensure_state(self.config.start_capital_eur)
        return compute_health(
            current,
            stale_after_seconds=self.config.stale_after_seconds,
        )

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

    def get_paper_report(self, market_price: float | None = None) -> PaperTradingReport:
        state = self.storage.ensure_state(self.config.start_capital_eur)
        metrics = self.get_performance(market_price=market_price)
        return build_paper_report(
            state,
            metrics=metrics,
            trades=self.storage.list_trades(limit=10_000),
            health=self.get_health(state),
            stale_after_seconds=self.config.stale_after_seconds,
        )

    def tick(self) -> BotState:
        state = self.storage.ensure_state(self.config.start_capital_eur)
        state.tick_count += 1
        now = utc_now().isoformat()

        try:
            candles = self.market_data.fetch_candles(
                granularity=self.config.candle_granularity,
                limit=self.config.candle_limit,
            )
            spot_price = self.market_data.fetch_spot_price()
        except (MarketDataError, Exception) as exc:  # noqa: BLE001 — keep portfolio intact
            return self._fail_tick(state, now, exc)

        portfolio_before = (
            state.cash_eur,
            state.btc_amount,
            state.entry_price,
            state.in_position,
            state.realized_pnl_eur,
            state.total_trades,
        )

        try:
            risk_signal = self.risk.check_exits(state, spot_price)
            if risk_signal is not None:
                signal = risk_signal
            else:
                signal = self.strategy.evaluate(
                    candles,
                    in_position=state.in_position,
                    exclude_open_candle=True,
                )

            self.storage.add_log("info", f"Signal: {signal.action.value} | {signal.reason}")

            state.last_price = spot_price
            state.last_signal = signal.reason
            state.last_update = now

            candle_ts = signal.signal_candle_timestamp
            should_trade = signal.action in (SignalAction.BUY, SignalAction.SELL)
            duplicate_candle = (
                should_trade
                and candle_ts is not None
                and candle_ts == state.last_processed_candle
                and signal.reason not in ("stop_loss", "take_profit")
            )

            if duplicate_candle:
                self.storage.add_log(
                    "warning",
                    f"Idempotenz: Kerze {candle_ts} bereits verarbeitet — Trade übersprungen",
                )
            elif should_trade:
                signal = signal.__class__(
                    action=signal.action,
                    reason=signal.reason,
                    price=spot_price,
                    ema_fast=signal.ema_fast,
                    ema_slow=signal.ema_slow,
                    rsi=signal.rsi,
                    signal_candle_timestamp=candle_ts,
                )
                state, result = self.execution.execute_signal(state, signal)
                if result.executed:
                    self.storage.add_log(
                        "info",
                        f"Trade: {signal.action.value} | {result.message}",
                    )
                    if candle_ts is not None and signal.reason not in (
                        "stop_loss",
                        "take_profit",
                    ):
                        state.last_processed_candle = candle_ts
                    # Persist portfolio immediately after a fill so restarts cannot
                    # lose cash/BTC/entry while a trade row already exists.
                    self.storage.save_state(state)
                elif signal.action != SignalAction.HOLD:
                    self.storage.add_log("info", result.message)
            elif candle_ts is not None and state.last_processed_candle != candle_ts:
                # Mark evaluated HOLD candle so a restart cannot re-fire a later
                # phantom trade on the same completed bar if state drifts.
                # Only advance marker when flat evaluation completed without trade.
                pass

            # Advance last_processed_candle after a successful strategy evaluation
            # when a trade executed OR when we intentionally skipped a duplicate.
            # For HOLD, do not advance — a later tick on a NEW completed candle trades.
            # For strategy BUY/SELL that executed, already set above.
            # For risk exits, do not bind to candle idempotency.

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
            state.successful_ticks += 1
            state.last_successful_tick = now
            state.last_error = None
            state.last_error_at = None
            self.storage.save_state(state)
            self.storage.add_log("info", "Tick erfolgreich")
            return state
        except Exception as exc:  # noqa: BLE001 — never leave half-applied portfolio
            # Roll back in-memory mutations if portfolio fields changed unexpectedly
            (
                state.cash_eur,
                state.btc_amount,
                state.entry_price,
                state.in_position,
                state.realized_pnl_eur,
                state.total_trades,
            ) = portfolio_before
            return self._fail_tick(state, now, exc)

    def _fail_tick(self, state: BotState, now: str, exc: BaseException) -> BotState:
        message = f"{type(exc).__name__}: {exc}"
        # Strip accidental secrets if any sneaks into exception text
        safe = message.replace("\n", " ")[:500]
        state.failed_ticks += 1
        state.api_error_count += 1
        state.last_error = safe
        state.last_error_at = now
        state.last_update = now
        self.storage.save_state(state)
        level = "error"
        if "Timeout" in type(exc).__name__ or "timeout" in safe.lower():
            self.storage.add_log(level, f"API-Timeout/Netzwerk: {safe}")
        elif "empty" in safe.lower() or "corrupt" in safe.lower():
            self.storage.add_log(level, f"Datenproblem: {safe}")
        else:
            self.storage.add_log(level, f"API-Fehler/Exception: {safe}")
        return state

    def set_running(self, running: bool) -> BotState:
        state = self.storage.ensure_state(self.config.start_capital_eur)
        state.is_running = running
        state.last_update = utc_now().isoformat()
        if running:
            if state.session_started_at is None:
                state.session_started_at = state.last_update
            self.storage.add_log("info", "Bot gestartet")
        else:
            self.storage.add_log("info", "Bot gestoppt")
        self.storage.save_state(state)
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
