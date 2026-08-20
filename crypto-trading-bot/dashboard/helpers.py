"""Pure dashboard helpers — testable without Streamlit runtime."""

from __future__ import annotations

from typing import Any

from bot.performance import PerformanceMetrics
from bot.risk.manager import RiskManager
from bot.storage import BotState, TradeRecord


def format_eur(value: float | None, signed: bool = False) -> str:
    if value is None:
        return "—"
    if signed:
        return f"{value:+,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{value:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def format_pct(value: float | None, signed: bool = True) -> str:
    if value is None:
        return "—"
    pct = value * 100 if abs(value) <= 1.5 else value
    return f"{pct:+.2f} %" if signed else f"{pct:.2f} %"


def format_btc(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.8f} BTC"


def pnl_class(value: float | None) -> str:
    if value is None or value == 0:
        return ""
    return "positive" if value > 0 else "negative"


def paper_mode_badge(trading_mode: str) -> str:
    mode = (trading_mode or "").strip().lower()
    if mode != "paper":
        return "UNSICHERER MODUS"
    return "PAPER TRADING"


def bot_status_label(is_running: bool) -> str:
    return "RUNNING" if is_running else "STOPPED"


def humanize_reason(reason: str | None) -> str:
    if not reason:
        return "—"
    mapping = {
        "stop_loss": "Stop-Loss",
        "take_profit": "Take-Profit",
        "strategy_exit": "Strategie-Exit",
        "EMA20 above EMA50 and RSI above 50": "EMA20 über EMA50 und RSI über 50",
        "EMA20 below EMA50": "EMA20 unter EMA50",
        "RSI below 45": "RSI unter 45",
    }
    return mapping.get(reason, reason)


def build_overview_cards(metrics: PerformanceMetrics) -> list[dict[str, str]]:
    return [
        {
            "label": "Portfolio-Wert",
            "value": format_eur(metrics.portfolio_value),
            "css": pnl_class(metrics.total_pnl),
        },
        {
            "label": "Verfügbares EUR",
            "value": format_eur(metrics.cash_eur),
            "css": "",
        },
        {
            "label": "BTC-Bestand",
            "value": format_btc(metrics.btc_amount),
            "css": "",
        },
        {
            "label": "Tages-P&L",
            "value": format_eur(metrics.daily_pnl, signed=True),
            "css": pnl_class(metrics.daily_pnl),
        },
        {
            "label": "Gesamt-P&L",
            "value": format_eur(metrics.total_pnl, signed=True),
            "css": pnl_class(metrics.total_pnl),
        },
        {
            "label": "Rendite",
            "value": format_pct(metrics.total_return),
            "css": pnl_class(metrics.total_return),
        },
    ]


def build_position_cards(
    state: BotState,
    market_price: float,
    risk: RiskManager,
) -> list[dict[str, str]] | None:
    if not state.in_position or state.entry_price is None or state.btc_amount <= 0:
        return None
    position_value = state.btc_amount * market_price
    unrealized = (market_price - state.entry_price) * state.btc_amount
    return [
        {"label": "Entry Price", "value": format_eur(state.entry_price), "css": ""},
        {"label": "Aktueller Preis", "value": format_eur(market_price), "css": ""},
        {"label": "Positionswert", "value": format_eur(position_value), "css": ""},
        {
            "label": "Unrealisiertes P&L",
            "value": format_eur(unrealized, signed=True),
            "css": pnl_class(unrealized),
        },
        {
            "label": "Stop-Loss",
            "value": format_eur(risk.stop_loss_price(state.entry_price)),
            "css": "negative",
        },
        {
            "label": "Take-Profit",
            "value": format_eur(risk.take_profit_price(state.entry_price)),
            "css": "positive",
        },
    ]


def trade_activity_cards(trades: list[TradeRecord], limit: int = 20) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for trade in trades[:limit]:
        cards.append(
            {
                "kind": trade.side.upper(),
                "timestamp": trade.timestamp,
                "price": format_eur(trade.execution_price or trade.price),
                "quantity": format_btc(trade.quantity or trade.amount_btc),
                "fee": format_eur(trade.fee if trade.fee is not None else trade.fee_eur),
                "slippage": (
                    format_eur(trade.slippage, signed=False)
                    if trade.slippage is not None
                    else "—"
                ),
                "pnl": format_eur(trade.pnl, signed=True) if trade.pnl is not None else "—",
                "reason": humanize_reason(trade.reason),
            }
        )
    return cards


def filter_logs(logs: list[dict[str, str]], level: str | None) -> list[dict[str, str]]:
    if not level or level.upper() == "ALL":
        return logs
    wanted = level.upper()
    aliases = {
        "INFO": {"INFO", "TRADE"},
        "WARNING": {"WARNING", "WARN"},
        "ERROR": {"ERROR", "CRITICAL"},
    }
    accepted = aliases.get(wanted, {wanted})
    return [log for log in logs if str(log.get("level", "")).upper() in accepted]


def settings_rows(config: Any) -> list[tuple[str, str]]:
    return [
        ("Trading Mode", paper_mode_badge(config.trading_mode)),
        ("Startkapital", format_eur(config.start_capital_eur)),
        ("Trading Pair", config.product_id),
        ("Max Trade", format_eur(config.max_trade_eur)),
        ("Stop Loss", f"{config.stop_loss_pct:.1f} %"),
        ("Take Profit", f"{config.take_profit_pct:.1f} %"),
        ("Fee", f"{config.fee_pct:.2f} %"),
        ("Slippage", f"{config.slippage_pct:.2f} %"),
        ("Timezone", config.timezone),
        ("EMA Fast", str(config.ema_fast)),
        ("EMA Slow", str(config.ema_slow)),
        ("RSI Period", str(config.rsi_period)),
        ("RSI Entry", str(config.rsi_entry)),
        ("RSI Exit", str(config.rsi_exit)),
        ("Backtest Period", str(getattr(config, "backtest_period", "n/a"))),
        ("Backtest Interval", str(getattr(config, "backtest_interval", "n/a"))),
    ]


def format_backtest_summary(result: Any) -> dict[str, Any]:
    """Thin prep for a future dashboard backtest view — no UI here."""
    metrics = getattr(result, "metrics", None)
    buy_hold = getattr(result, "buy_and_hold", None)
    window = getattr(result, "window", None)
    return {
        "period": getattr(window, "period", None),
        "interval": getattr(window, "interval", None),
        "candle_count": getattr(result, "candle_count", 0),
        "insufficient_data": getattr(result, "insufficient_data", False),
        "strategy_return_pct": getattr(result, "total_return_pct", None),
        "buy_and_hold_return_pct": (
            None if buy_hold is None else buy_hold.total_return * 100.0
        ),
        "closed_trades": getattr(result, "total_trades", 0),
        "sample_note": getattr(result, "sample_note", ""),
        "max_drawdown_pct": getattr(result, "max_drawdown_pct", None),
        "total_fees": None if metrics is None else metrics.total_fees,
        "equity_curve_label": "Strategy Equity",
        "benchmark_label": None if buy_hold is None else buy_hold.label,
        "warnings": list(getattr(result, "warnings", [])),
    }
