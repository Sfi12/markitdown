"""Performance metrics — deterministic, shared by live paper trading and backtest."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence
from zoneinfo import ZoneInfo

from bot.portfolio.ledger import PortfolioLedger
from bot.storage import BotState, TradeRecord


# ---------------------------------------------------------------------------
# Mathematical definitions (documented for architects / tests)
#
# total_pnl        = portfolio_value - start_capital
# total_return     = total_pnl / start_capital   (ratio; *100 for %)
# win_rate         = winning_closed_trades / closed_trades   (None if 0 closed)
# average_win      = sum(positive pnl) / count(positive)     (None if none)
# average_loss     = sum(negative pnl) / count(negative)     (None if none)
# profit_factor    = sum_wins / abs(sum_losses)
#                    None if no closed trades
#                    float('inf') conceptually → we return None and set
#                    profit_factor_infinite=True when there are wins and no losses
# max_drawdown_pct = max over t of (peak_t - value_t) / peak_t * 100
# daily_pnl        = portfolio_value_now - portfolio_value_at_start_of_local_day
#                    (Europe/Berlin by default; None if no snapshot/history)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PerformanceMetrics:
    start_capital: float
    portfolio_value: float
    cash_eur: float
    btc_amount: float
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float
    daily_pnl: float | None
    total_return: float | None
    closed_trades: int
    win_rate: float | None
    average_win: float | None
    average_loss: float | None
    profit_factor: float | None
    profit_factor_infinite: bool
    max_drawdown_pct: float | None
    total_fees: float
    best_trade: float | None
    worst_trade: float | None
    timezone: str
    insufficient_history: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PeriodMetrics:
    period: str
    start_value: float | None
    end_value: float | None
    pnl: float | None
    return_pct: float | None
    insufficient_data: bool


class PerformanceCalculator:
    """Pure functions over trades + snapshots + current state."""

    PERIODS: dict[str, timedelta] = {
        "1D": timedelta(days=1),
        "1W": timedelta(weeks=1),
        "1M": timedelta(days=30),
        "3M": timedelta(days=90),
        "6M": timedelta(days=180),
        "1Y": timedelta(days=365),
    }

    def __init__(
        self,
        start_capital: float = 50.0,
        timezone_name: str = "Europe/Berlin",
    ) -> None:
        self.start_capital = start_capital
        self.timezone_name = timezone_name
        self.tz = ZoneInfo(timezone_name)
        self.ledger = PortfolioLedger(start_capital_eur=start_capital)

    def closed_trade_pnls(self, trades: Sequence[TradeRecord]) -> list[float]:
        """PnL of closed (sell) trades only. Skips rows without pnl."""
        pnls: list[float] = []
        for trade in trades:
            if trade.side != "sell":
                continue
            if trade.pnl is None:
                continue
            pnls.append(float(trade.pnl))
        return pnls

    def total_fees(self, trades: Sequence[TradeRecord]) -> float:
        return sum(float(trade.fee if trade.fee is not None else trade.fee_eur) for trade in trades)

    def win_rate(self, pnls: Sequence[float]) -> float | None:
        if not pnls:
            return None
        wins = sum(1 for pnl in pnls if pnl > 0)
        return wins / len(pnls)

    def average_win(self, pnls: Sequence[float]) -> float | None:
        wins = [pnl for pnl in pnls if pnl > 0]
        if not wins:
            return None
        return sum(wins) / len(wins)

    def average_loss(self, pnls: Sequence[float]) -> float | None:
        losses = [pnl for pnl in pnls if pnl < 0]
        if not losses:
            return None
        return sum(losses) / len(losses)

    def profit_factor(self, pnls: Sequence[float]) -> tuple[float | None, bool]:
        if not pnls:
            return None, False
        gains = sum(pnl for pnl in pnls if pnl > 0)
        losses = sum(pnl for pnl in pnls if pnl < 0)
        if losses == 0:
            if gains > 0:
                return None, True
            return None, False
        return gains / abs(losses), False

    def max_drawdown_pct(self, equity_curve: Sequence[float]) -> float | None:
        if len(equity_curve) < 2:
            return None if not equity_curve else 0.0
        peak = equity_curve[0]
        max_dd = 0.0
        for value in equity_curve:
            peak = max(peak, value)
            if peak <= 0:
                continue
            drawdown = (peak - value) / peak * 100.0
            max_dd = max(max_dd, drawdown)
        return max_dd

    def _parse_ts(self, value: str) -> datetime:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    def start_of_local_day(self, now: datetime | None = None) -> datetime:
        current = now or datetime.now(timezone.utc)
        local = current.astimezone(self.tz)
        start_local = local.replace(hour=0, minute=0, second=0, microsecond=0)
        return start_local.astimezone(timezone.utc)

    def daily_pnl(
        self,
        current_portfolio_value: float,
        snapshots: Sequence[dict[str, Any]],
        now: datetime | None = None,
    ) -> float | None:
        """
        Tages-P&L (Europe/Berlin by default):

        portfolio_value_now - first_portfolio_value_at_or_after_local_midnight

        If no snapshot exists for today → None (insufficient data).
        """
        day_start = self.start_of_local_day(now)
        candidates: list[tuple[datetime, float]] = []
        for snap in snapshots:
            ts = self._parse_ts(str(snap["timestamp"]))
            if ts < day_start:
                continue
            value = snap.get("portfolio_value")
            if value is None:
                value = snap.get("portfolio_value_eur")
            if value is None:
                continue
            candidates.append((ts, float(value)))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0])
        return current_portfolio_value - candidates[0][1]

    def compute(
        self,
        state: BotState,
        market_price: float,
        trades: Sequence[TradeRecord],
        snapshots: Sequence[dict[str, Any]] | None = None,
        now: datetime | None = None,
    ) -> PerformanceMetrics:
        snap = self.ledger.snapshot(state, market_price)
        pnls = self.closed_trade_pnls(trades)
        pf, pf_inf = self.profit_factor(pnls)
        equity = [float(s.get("portfolio_value") or s.get("portfolio_value_eur") or 0.0) for s in (snapshots or [])]
        if equity and equity[-1] != snap.portfolio_value:
            equity = [*equity, snap.portfolio_value]
        elif not equity:
            equity = [self.start_capital, snap.portfolio_value]

        total_pnl = snap.portfolio_value - self.start_capital
        total_return = total_pnl / self.start_capital if self.start_capital else None
        daily = self.daily_pnl(snap.portfolio_value, snapshots or [], now=now)

        return PerformanceMetrics(
            start_capital=self.start_capital,
            portfolio_value=snap.portfolio_value,
            cash_eur=state.cash_eur,
            btc_amount=state.btc_amount,
            realized_pnl=snap.realized_pnl,
            unrealized_pnl=snap.unrealized_pnl,
            total_pnl=total_pnl,
            daily_pnl=daily,
            total_return=total_return,
            closed_trades=len(pnls),
            win_rate=self.win_rate(pnls),
            average_win=self.average_win(pnls),
            average_loss=self.average_loss(pnls),
            profit_factor=pf,
            profit_factor_infinite=pf_inf,
            max_drawdown_pct=self.max_drawdown_pct(equity),
            total_fees=self.total_fees(trades),
            best_trade=max(pnls) if pnls else None,
            worst_trade=min(pnls) if pnls else None,
            timezone=self.timezone_name,
            insufficient_history=not bool(snapshots),
        )

    def period_metrics(
        self,
        snapshots: Sequence[dict[str, Any]],
        current_value: float,
        period: str,
        now: datetime | None = None,
    ) -> PeriodMetrics:
        if period not in self.PERIODS:
            raise ValueError(f"Unknown period: {period}")
        if not snapshots:
            return PeriodMetrics(period, None, None, None, None, True)

        current = now or datetime.now(timezone.utc)
        cutoff = current - self.PERIODS[period]
        points: list[tuple[datetime, float]] = []
        for snap in snapshots:
            value = snap.get("portfolio_value")
            if value is None:
                value = snap.get("portfolio_value_eur")
            if value is None:
                continue
            points.append((self._parse_ts(str(snap["timestamp"])), float(value)))
        points.sort(key=lambda item: item[0])
        in_window = [p for p in points if p[0] >= cutoff]
        if not in_window:
            return PeriodMetrics(period, None, current_value, None, None, True)

        start_value = in_window[0][1]
        end_value = current_value
        pnl = end_value - start_value
        ret = (pnl / start_value * 100.0) if start_value else None
        return PeriodMetrics(period, start_value, end_value, pnl, ret, False)

    def from_backtest_trades(
        self,
        *,
        start_capital: float,
        end_capital: float,
        sell_pnls: Sequence[float],
        total_fees: float,
        equity_curve: Sequence[float],
    ) -> PerformanceMetrics:
        pnls = list(sell_pnls)
        pf, pf_inf = self.profit_factor(pnls)
        total_pnl = end_capital - start_capital
        return PerformanceMetrics(
            start_capital=start_capital,
            portfolio_value=end_capital,
            cash_eur=end_capital,
            btc_amount=0.0,
            realized_pnl=sum(pnls),
            unrealized_pnl=0.0,
            total_pnl=total_pnl,
            daily_pnl=None,
            total_return=total_pnl / start_capital if start_capital else None,
            closed_trades=len(pnls),
            win_rate=self.win_rate(pnls),
            average_win=self.average_win(pnls),
            average_loss=self.average_loss(pnls),
            profit_factor=pf,
            profit_factor_infinite=pf_inf,
            max_drawdown_pct=self.max_drawdown_pct(list(equity_curve) or [start_capital, end_capital]),
            total_fees=total_fees,
            best_trade=max(pnls) if pnls else None,
            worst_trade=min(pnls) if pnls else None,
            timezone=self.timezone_name,
            insufficient_history=len(equity_curve) < 2,
        )
