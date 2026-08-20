from __future__ import annotations

from bot.config import BotConfig
from bot.performance import PerformanceCalculator, PerformanceMetrics
from bot.risk.manager import RiskManager
from bot.storage import BotState, TradeRecord
from dashboard.helpers import (
    bot_status_label,
    build_overview_cards,
    build_position_cards,
    filter_logs,
    format_eur,
    format_pct,
    humanize_reason,
    paper_mode_badge,
    settings_rows,
    trade_activity_cards,
)


def make_metrics(**overrides) -> PerformanceMetrics:
    base = dict(
        start_capital=50.0,
        portfolio_value=51.0,
        cash_eur=40.0,
        btc_amount=0.1,
        realized_pnl=1.0,
        unrealized_pnl=0.5,
        total_pnl=1.0,
        daily_pnl=0.25,
        total_return=0.02,
        closed_trades=1,
        win_rate=1.0,
        average_win=1.0,
        average_loss=None,
        profit_factor=None,
        profit_factor_infinite=True,
        max_drawdown_pct=1.0,
        total_fees=0.12,
        best_trade=1.0,
        worst_trade=1.0,
        timezone="Europe/Berlin",
    )
    base.update(overrides)
    return PerformanceMetrics(**base)


def test_paper_mode_badge_visible() -> None:
    assert paper_mode_badge("paper") == "PAPER TRADING"
    assert paper_mode_badge("live") == "UNSICHERER MODUS"


def test_bot_status_labels() -> None:
    assert bot_status_label(True) == "RUNNING"
    assert bot_status_label(False) == "STOPPED"


def test_overview_cards_include_pnl() -> None:
    cards = build_overview_cards(make_metrics())
    labels = [card["label"] for card in cards]
    assert "Portfolio-Wert" in labels
    assert "Tages-P&L" in labels
    assert "Gesamt-P&L" in labels
    assert "Rendite" in labels


def test_position_open_and_flat() -> None:
    risk = RiskManager(stop_loss_pct=1.5, take_profit_pct=3.0)
    open_state = BotState(
        cash_eur=40.0,
        btc_amount=0.1,
        entry_price=100.0,
        in_position=True,
        is_running=True,
        last_price=105.0,
        last_signal="hold",
        last_update=None,
        total_trades=1,
        realized_pnl_eur=0.0,
    )
    cards = build_position_cards(open_state, 105.0, risk)
    assert cards is not None
    assert any(card["label"] == "Stop-Loss" for card in cards)

    flat = BotState(
        cash_eur=50.0,
        btc_amount=0.0,
        entry_price=None,
        in_position=False,
        is_running=False,
        last_price=105.0,
        last_signal="hold",
        last_update=None,
        total_trades=0,
        realized_pnl_eur=0.0,
    )
    assert build_position_cards(flat, 105.0, risk) is None


def test_buy_sell_activity_cards() -> None:
    trades = [
        TradeRecord(
            id=1,
            timestamp="2026-01-01T12:00:00+00:00",
            side="buy",
            reason="EMA20 above EMA50 and RSI above 50",
            balance_eur_after=40.0,
            balance_btc_after=0.1,
            symbol="BTC-EUR",
            requested_price=100.0,
            execution_price=100.1,
            quantity=0.1,
            gross_value=10.0,
            fee=0.06,
            slippage=0.1,
            net_value=9.94,
            pnl=0.0,
        ),
        TradeRecord(
            id=2,
            timestamp="2026-01-01T13:00:00+00:00",
            side="sell",
            reason="stop_loss",
            balance_eur_after=49.0,
            balance_btc_after=0.0,
            symbol="BTC-EUR",
            requested_price=98.0,
            execution_price=97.9,
            quantity=0.1,
            gross_value=9.79,
            fee=0.05,
            slippage=0.1,
            net_value=9.74,
            pnl=-0.2,
        ),
    ]
    cards = trade_activity_cards(trades)
    assert cards[0]["kind"] == "BUY"
    assert cards[1]["kind"] == "SELL"
    assert "Stop-Loss" in cards[1]["reason"]


def test_log_filters() -> None:
    logs = [
        {"timestamp": "t1", "level": "info", "message": "ok"},
        {"timestamp": "t2", "level": "warning", "message": "warn"},
        {"timestamp": "t3", "level": "error", "message": "fail"},
        {"timestamp": "t4", "level": "trade", "message": "buy"},
    ]
    assert len(filter_logs(logs, "ALL")) == 4
    assert len(filter_logs(logs, "INFO")) == 2
    assert len(filter_logs(logs, "WARNING")) == 1
    assert len(filter_logs(logs, "ERROR")) == 1


def test_performance_without_trades() -> None:
    calc = PerformanceCalculator(start_capital=50.0)
    state = BotState(
        cash_eur=50.0,
        btc_amount=0.0,
        entry_price=None,
        in_position=False,
        is_running=False,
        last_price=100.0,
        last_signal="",
        last_update=None,
        total_trades=0,
        realized_pnl_eur=0.0,
    )
    metrics = calc.compute(state, 100.0, trades=[], snapshots=[])
    cards = build_overview_cards(metrics)
    assert any(card["label"] == "Gesamt-P&L" and "0,00" in card["value"] for card in cards)


def test_settings_include_paper_mode(config: BotConfig) -> None:
    rows = dict(settings_rows(config))
    assert rows["Trading Mode"] == "PAPER TRADING"
    assert "Europe/Berlin" in rows["Timezone"]


def test_humanize_reasons() -> None:
    assert humanize_reason("take_profit") == "Take-Profit"
    assert "EMA20 über EMA50" in humanize_reason("EMA20 above EMA50 and RSI above 50")


def test_formatters() -> None:
    assert "€" in format_eur(12.5)
    assert format_pct(0.015).endswith("%")
