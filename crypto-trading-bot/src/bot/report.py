"""Paper-trading session report — no live trading claims."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Sequence

from bot.health import HealthSnapshot, compute_health
from bot.performance import PerformanceCalculator, PerformanceMetrics
from bot.storage import BotState, TradeRecord


@dataclass(frozen=True)
class PaperTradingReport:
    start_time: str | None
    runtime_seconds: float | None
    ticks: int
    successful_ticks: int
    failed_ticks: int
    api_errors: int
    trades: int
    buys: int
    sells: int
    portfolio_value: float
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float
    fees: float
    current_drawdown_pct: float | None
    health: str
    last_successful_tick: str | None
    last_processed_candle: str | None
    last_error: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def format_text(self) -> str:
        runtime = "n/a"
        if self.runtime_seconds is not None:
            hours = self.runtime_seconds / 3600.0
            runtime = f"{self.runtime_seconds:.0f}s ({hours:.2f}h)"
        dd = "n/a" if self.current_drawdown_pct is None else f"{self.current_drawdown_pct:.2f} %"
        return "\n".join(
            [
                "=== Paper-Trading Report ===",
                f"Health:              {self.health}",
                f"Startzeit:           {self.start_time or 'n/a'}",
                f"Laufzeit:            {runtime}",
                f"Ticks:               {self.ticks}",
                f"Erfolgreiche Ticks:  {self.successful_ticks}",
                f"Fehlgeschlagene:     {self.failed_ticks}",
                f"API-Fehler:          {self.api_errors}",
                f"Trades:              {self.trades} (buys={self.buys}, sells={self.sells})",
                f"Portfolio Value:     {self.portfolio_value:.4f} EUR",
                f"Realized P&L:        {self.realized_pnl:+.4f} EUR",
                f"Unrealized P&L:      {self.unrealized_pnl:+.4f} EUR",
                f"Total P&L:           {self.total_pnl:+.4f} EUR",
                f"Fees:                {self.fees:.4f} EUR",
                f"Aktueller Drawdown:  {dd}",
                f"Last successful tick:{self.last_successful_tick or 'n/a'}",
                f"Last processed candle:{self.last_processed_candle or 'n/a'}",
                f"Last error:          {self.last_error or 'n/a'}",
            ]
        )


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def build_paper_report(
    state: BotState,
    *,
    metrics: PerformanceMetrics,
    trades: Sequence[TradeRecord],
    health: HealthSnapshot | None = None,
    stale_after_seconds: int = 180,
    now: datetime | None = None,
) -> PaperTradingReport:
    now_ts = now or datetime.now(timezone.utc)
    start_dt = _parse_ts(state.session_started_at)
    runtime = (now_ts - start_dt).total_seconds() if start_dt else None
    buys = sum(1 for trade in trades if trade.side == "buy")
    sells = sum(1 for trade in trades if trade.side == "sell")
    fees = PerformanceCalculator().total_fees(trades)
    snap = health or compute_health(state, stale_after_seconds=stale_after_seconds, now=now_ts)

    return PaperTradingReport(
        start_time=state.session_started_at,
        runtime_seconds=runtime,
        ticks=state.tick_count,
        successful_ticks=state.successful_ticks,
        failed_ticks=state.failed_ticks,
        api_errors=state.api_error_count,
        trades=len(trades),
        buys=buys,
        sells=sells,
        portfolio_value=metrics.portfolio_value,
        realized_pnl=metrics.realized_pnl,
        unrealized_pnl=metrics.unrealized_pnl,
        total_pnl=metrics.total_pnl,
        fees=fees,
        current_drawdown_pct=metrics.max_drawdown_pct,
        health=snap.display,
        last_successful_tick=state.last_successful_tick,
        last_processed_candle=state.last_processed_candle,
        last_error=state.last_error,
    )
