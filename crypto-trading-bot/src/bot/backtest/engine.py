from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from bot.backtest.benchmark import BuyAndHoldResult, compute_buy_and_hold
from bot.backtest.data_quality import DataQualityReport, sanitize_candles, validate_candles
from bot.backtest.periods import (
    BacktestWindow,
    coverage_ratio,
    is_insufficient_coverage,
    resolve_window,
)
from bot.bootstrap import (
    create_execution_provider,
    create_market_data_provider,
    create_portfolio_ledger,
    create_risk_manager,
)
from bot.config import BotConfig
from bot.data.base import MarketDataProvider
from bot.performance import PerformanceCalculator, PerformanceMetrics
from bot.security import enforce_paper_trading_startup
from bot.storage import BotState
from bot.strategy import EmaRsiStrategy, SignalAction, add_indicators


def sample_size_note(closed_trades: int) -> str:
    if closed_trades < 10:
        return "sehr geringe Stichprobe"
    if closed_trades < 30:
        return "geringe Stichprobe"
    return "ausreichende Stichprobe"


def longest_streak(flags: list[bool]) -> int:
    best = current = 0
    for flag in flags:
        if flag:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


@dataclass(frozen=True)
class ClosedTradeDetail:
    entry_timestamp: str
    entry_price: float
    exit_timestamp: str
    exit_price: float
    quantity: float
    gross_value: float
    fees: float
    slippage: float
    pnl: float
    return_pct: float
    holding_duration_seconds: float
    exit_reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class DrawdownPoint:
    timestamp: str
    portfolio_value: float
    peak: float
    drawdown_eur: float
    drawdown_pct: float


@dataclass
class ExtendedBacktestResult:
    window: BacktestWindow
    candle_count: int
    insufficient_data: bool
    data_quality: DataQualityReport
    start_capital: float
    end_capital: float
    total_return: float
    total_pnl: float
    metrics: PerformanceMetrics
    closed_trades: list[ClosedTradeDetail]
    equity_curve: list[dict[str, float | str]]
    drawdown_curve: list[DrawdownPoint]
    buy_and_hold: BuyAndHoldResult | None
    exposure: float
    average_holding_seconds: float | None
    longest_drawdown_bars: int
    longest_win_streak: int
    longest_loss_streak: int
    open_position_at_end: bool
    sample_note: str
    warnings: list[str] = field(default_factory=list)

    # Compatibility with older CLI fields
    @property
    def start_capital_eur(self) -> float:
        return self.start_capital

    @property
    def end_capital_eur(self) -> float:
        return self.end_capital

    @property
    def total_return_pct(self) -> float:
        return self.total_return * 100.0

    @property
    def total_trades(self) -> int:
        return len(self.closed_trades)

    @property
    def winning_trades(self) -> int:
        return sum(1 for trade in self.closed_trades if trade.pnl > 0)

    @property
    def losing_trades(self) -> int:
        return sum(1 for trade in self.closed_trades if trade.pnl < 0)

    @property
    def max_drawdown_pct(self) -> float:
        return self.metrics.max_drawdown_pct or 0.0

    @property
    def trades(self) -> list[dict[str, Any]]:
        return [trade.to_dict() for trade in self.closed_trades]


class _NullStorage:
    def add_trade(self, trade: object) -> None:
        return None

    def add_log(self, level: str, message: str) -> None:
        return None


class StrategyBacktester:
    """Deterministic paper backtester with buy-and-hold benchmark."""

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

    def load_candles(self, window: BacktestWindow) -> pd.DataFrame:
        fetch_range = getattr(self.market_data, "fetch_candles_range", None)
        if callable(fetch_range):
            frame = fetch_range(
                granularity=window.granularity,
                start=window.start,
                end=window.end,
            )
        else:
            # Fallback: latest N candles only — may be insufficient for long periods.
            needed = window.expected_bars + max(self.config.ema_slow, self.config.rsi_period) + 5
            frame = self.market_data.fetch_candles(
                granularity=window.granularity,
                limit=min(needed, 300),
            )
        return sanitize_candles(frame)

    def run(
        self,
        *,
        period: str | None = None,
        interval: str | None = None,
        candles: pd.DataFrame | None = None,
        end: datetime | None = None,
        clip_to_window: bool | None = None,
    ) -> ExtendedBacktestResult:
        period_key = period or self.config.backtest_period
        interval_key = interval or self.config.backtest_interval
        window = resolve_window(period_key, interval_key, end=end)
        warnings: list[str] = []
        provided = candles is not None
        # Explicit candle frames are used as-is (tests / offline). Remote loads
        # are clipped to the requested window — never invent missing bars.
        should_clip = clip_to_window if clip_to_window is not None else not provided

        if provided:
            raw = sanitize_candles(candles)
        else:
            raw = self.load_candles(window)

        quality = validate_candles(raw, window.granularity)
        if quality.has_blocking_errors:
            raise ValueError(
                "Backtest abgebrochen wegen Datenqualitätsfehlern: "
                + "; ".join(quality.errors)
            )
        warnings.extend(quality.warnings)

        frame = sanitize_candles(raw)
        if should_clip and not frame.empty:
            frame = frame[
                (frame["timestamp"] >= pd.Timestamp(window.start))
                & (frame["timestamp"] <= pd.Timestamp(window.end))
            ].reset_index(drop=True)

        insufficient = is_insufficient_coverage(len(frame), window.expected_bars)
        if insufficient:
            warnings.append(
                f"insufficient_data=true — erwartet ~{window.expected_bars} Kerzen, "
                f"erhalten {len(frame)} "
                f"({coverage_ratio(len(frame), window.expected_bars) * 100:.1f} % Abdeckung)."
            )

        if frame.empty:
            empty_metrics = self.performance.from_backtest_trades(
                start_capital=self.config.start_capital_eur,
                end_capital=self.config.start_capital_eur,
                sell_pnls=[],
                total_fees=0.0,
                equity_curve=[self.config.start_capital_eur],
            )
            return ExtendedBacktestResult(
                window=window,
                candle_count=0,
                insufficient_data=True,
                data_quality=quality,
                start_capital=self.config.start_capital_eur,
                end_capital=self.config.start_capital_eur,
                total_return=0.0,
                total_pnl=0.0,
                metrics=empty_metrics,
                closed_trades=[],
                equity_curve=[],
                drawdown_curve=[],
                buy_and_hold=None,
                exposure=0.0,
                average_holding_seconds=None,
                longest_drawdown_bars=0,
                longest_win_streak=0,
                longest_loss_streak=0,
                open_position_at_end=False,
                sample_note=sample_size_note(0),
                warnings=warnings,
            )

        return self._simulate(frame, window, quality, warnings, insufficient)

    def _simulate(
        self,
        frame: pd.DataFrame,
        window: BacktestWindow,
        quality: DataQualityReport,
        warnings: list[str],
        insufficient: bool,
    ) -> ExtendedBacktestResult:
        enriched = add_indicators(
            frame,
            self.config.ema_fast,
            self.config.ema_slow,
            self.config.rsi_period,
        )

        cash_eur = self.config.start_capital_eur
        btc_amount = 0.0
        entry_price: float | None = None
        entry_ts: str | None = None
        entry_fees = 0.0
        entry_slippage = 0.0
        entry_qty = 0.0
        in_position = False
        closed: list[ClosedTradeDetail] = []
        sell_pnls: list[float] = []
        total_fees = 0.0
        equity_curve: list[dict[str, float | str]] = []
        bars_in_position = 0

        warmup = max(self.config.ema_slow, self.config.rsi_period) + 2
        for index in range(warmup, len(enriched)):
            # No look-ahead: only completed bars up to current index.
            window_df = enriched.iloc[: index + 1]
            price = float(window_df.iloc[-1]["close"])
            ts = str(window_df.iloc[-1]["timestamp"])
            state = BotState(
                cash_eur=cash_eur,
                btc_amount=btc_amount,
                entry_price=entry_price,
                in_position=in_position,
                is_running=True,
                last_price=price,
                last_signal="",
                last_update=None,
                total_trades=len(closed),
                realized_pnl_eur=sum(sell_pnls),
            )

            risk_signal = self.risk.check_exits(state, price)
            signal = risk_signal or self.strategy.evaluate(
                window_df,
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
                    if signal.action == SignalAction.BUY:
                        entry_price = fill.execution_price
                        entry_ts = ts
                        entry_fees = fill.fee
                        entry_slippage = fill.slippage
                        entry_qty = fill.quantity
                    else:
                        holding = 0.0
                        if entry_ts is not None:
                            holding = (
                                pd.Timestamp(ts) - pd.Timestamp(entry_ts)
                            ).total_seconds()
                        cost_basis = (entry_price or fill.execution_price) * fill.quantity
                        ret_pct = (fill.pnl / cost_basis * 100.0) if cost_basis else 0.0
                        closed.append(
                            ClosedTradeDetail(
                                entry_timestamp=entry_ts or ts,
                                entry_price=float(entry_price or fill.execution_price),
                                exit_timestamp=ts,
                                exit_price=fill.execution_price,
                                quantity=fill.quantity,
                                gross_value=fill.gross_value,
                                fees=entry_fees + fill.fee,
                                slippage=entry_slippage + fill.slippage,
                                pnl=float(fill.pnl),
                                return_pct=ret_pct,
                                holding_duration_seconds=holding,
                                exit_reason=signal.reason,
                            )
                        )
                        sell_pnls.append(float(fill.pnl))
                        entry_price = None
                        entry_ts = None
                        entry_fees = 0.0
                        entry_slippage = 0.0
                        entry_qty = 0.0
                    cash_eur = state.cash_eur
                    btc_amount = state.btc_amount
                    entry_price = state.entry_price
                    in_position = state.in_position

            if in_position:
                bars_in_position += 1
            portfolio_value = cash_eur + (btc_amount * price)
            equity_curve.append({"timestamp": ts, "portfolio_value": portfolio_value})

        end_capital = (
            cash_eur + (btc_amount * float(enriched.iloc[-1]["close"]))
            if not enriched.empty
            else cash_eur
        )
        values = [float(point["portfolio_value"]) for point in equity_curve]
        metrics = self.performance.from_backtest_trades(
            start_capital=self.config.start_capital_eur,
            end_capital=end_capital,
            sell_pnls=sell_pnls,
            total_fees=total_fees,
            equity_curve=values or [self.config.start_capital_eur, end_capital],
        )
        drawdown_curve = self._drawdown_curve(equity_curve)
        win_flags = [trade.pnl > 0 for trade in closed]
        loss_flags = [trade.pnl < 0 for trade in closed]
        avg_hold = (
            sum(trade.holding_duration_seconds for trade in closed) / len(closed)
            if closed
            else None
        )
        traded_bars = max(len(enriched) - warmup, 1)
        exposure = bars_in_position / traded_bars

        buy_hold = compute_buy_and_hold(
            frame,
            start_capital=self.config.start_capital_eur,
            fee_pct=self.config.fee_pct,
            slippage_pct=self.config.slippage_pct,
        )

        note = sample_size_note(len(closed))
        if len(closed) < 30:
            warnings.append(
                f"{note}: {len(closed)} abgeschlossene Trades — "
                "Zu wenige Trades für belastbare Aussage."
            )

        return ExtendedBacktestResult(
            window=window,
            candle_count=len(frame),
            insufficient_data=insufficient,
            data_quality=quality,
            start_capital=self.config.start_capital_eur,
            end_capital=end_capital,
            total_return=(end_capital - self.config.start_capital_eur)
            / self.config.start_capital_eur,
            total_pnl=end_capital - self.config.start_capital_eur,
            metrics=metrics,
            closed_trades=closed,
            equity_curve=[{"label": "Strategy Equity", **point} for point in equity_curve],
            drawdown_curve=drawdown_curve,
            buy_and_hold=buy_hold,
            exposure=exposure,
            average_holding_seconds=avg_hold,
            longest_drawdown_bars=self._longest_drawdown_bars(drawdown_curve),
            longest_win_streak=longest_streak(win_flags),
            longest_loss_streak=longest_streak(loss_flags),
            open_position_at_end=in_position,
            sample_note=note,
            warnings=warnings,
        )

    def _drawdown_curve(
        self,
        equity_curve: list[dict[str, float | str]],
    ) -> list[DrawdownPoint]:
        points: list[DrawdownPoint] = []
        peak = 0.0
        for item in equity_curve:
            value = float(item["portfolio_value"])
            peak = max(peak, value)
            dd_eur = peak - value
            dd_pct = (dd_eur / peak * 100.0) if peak > 0 else 0.0
            points.append(
                DrawdownPoint(
                    timestamp=str(item["timestamp"]),
                    portfolio_value=value,
                    peak=peak,
                    drawdown_eur=dd_eur,
                    drawdown_pct=dd_pct,
                )
            )
        return points

    @staticmethod
    def _longest_drawdown_bars(curve: list[DrawdownPoint]) -> int:
        """Longest consecutive stretch with drawdown > 0 (peak → decline → recovery)."""
        best = current = 0
        for point in curve:
            if point.drawdown_pct > 0:
                current += 1
                best = max(best, current)
            else:
                current = 0
        return best
