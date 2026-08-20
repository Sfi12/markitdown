from __future__ import annotations

from datetime import datetime, timezone

import pytest

from bot.performance import PerformanceCalculator
from bot.storage import BotState, TradeRecord


def make_state(**overrides) -> BotState:
    state = BotState(
        cash_eur=50.0,
        btc_amount=0.0,
        entry_price=None,
        in_position=False,
        is_running=True,
        last_price=100.0,
        last_signal="",
        last_update=None,
        total_trades=0,
        realized_pnl_eur=0.0,
    )
    for key, value in overrides.items():
        setattr(state, key, value)
    return state


def sell(pnl: float, fee: float = 0.06, ts: str = "2026-01-01T12:00:00+00:00") -> TradeRecord:
    return TradeRecord(
        id=None,
        timestamp=ts,
        side="sell",
        reason="test",
        balance_eur_after=50.0,
        balance_btc_after=0.0,
        symbol="BTC-EUR",
        requested_price=100.0,
        execution_price=99.9,
        quantity=0.1,
        gross_value=9.99,
        fee=fee,
        slippage=0.1,
        net_value=9.93,
        pnl=pnl,
        price=99.9,
        amount_eur=9.99,
        amount_btc=0.1,
        fee_eur=fee,
    )


def buy(fee: float = 0.06) -> TradeRecord:
    return TradeRecord(
        id=None,
        timestamp="2026-01-01T11:00:00+00:00",
        side="buy",
        reason="test",
        balance_eur_after=40.0,
        balance_btc_after=0.1,
        symbol="BTC-EUR",
        requested_price=100.0,
        execution_price=100.1,
        quantity=0.1,
        gross_value=10.0,
        fee=fee,
        slippage=0.1,
        net_value=9.94,
        pnl=0.0,
        price=100.1,
        amount_eur=10.0,
        amount_btc=0.1,
        fee_eur=fee,
    )


def test_zero_trades() -> None:
    calc = PerformanceCalculator(start_capital=50.0)
    metrics = calc.compute(make_state(), market_price=100.0, trades=[], snapshots=[])
    assert metrics.closed_trades == 0
    assert metrics.win_rate is None
    assert metrics.profit_factor is None
    assert metrics.best_trade is None
    assert metrics.worst_trade is None
    assert metrics.total_pnl == 0.0
    assert metrics.total_return == 0.0


def test_one_winning_trade() -> None:
    calc = PerformanceCalculator(start_capital=50.0)
    metrics = calc.compute(make_state(), 100.0, trades=[buy(), sell(1.5)])
    assert metrics.closed_trades == 1
    assert metrics.win_rate == pytest.approx(1.0)
    assert metrics.average_win == pytest.approx(1.5)
    assert metrics.average_loss is None
    assert metrics.profit_factor_infinite is True
    assert metrics.best_trade == pytest.approx(1.5)
    assert metrics.worst_trade == pytest.approx(1.5)


def test_only_losing_trades() -> None:
    calc = PerformanceCalculator(start_capital=50.0)
    metrics = calc.compute(make_state(), 100.0, trades=[sell(-1.0), sell(-2.0)])
    assert metrics.win_rate == pytest.approx(0.0)
    assert metrics.average_loss == pytest.approx(-1.5)
    assert metrics.average_win is None
    assert metrics.profit_factor == pytest.approx(0.0)


def test_mixed_trades_profit_factor() -> None:
    calc = PerformanceCalculator(start_capital=50.0)
    metrics = calc.compute(make_state(), 100.0, trades=[sell(2.0), sell(-1.0)])
    assert metrics.win_rate == pytest.approx(0.5)
    assert metrics.profit_factor == pytest.approx(2.0)
    assert metrics.average_win == pytest.approx(2.0)
    assert metrics.average_loss == pytest.approx(-1.0)
    assert metrics.best_trade == pytest.approx(2.0)
    assert metrics.worst_trade == pytest.approx(-1.0)


def test_realized_unrealized_separation() -> None:
    calc = PerformanceCalculator(start_capital=50.0)
    state = make_state(
        cash_eur=40.0,
        btc_amount=0.1,
        entry_price=100.0,
        in_position=True,
        realized_pnl_eur=3.0,
    )
    metrics = calc.compute(state, market_price=110.0, trades=[sell(3.0)])
    assert metrics.realized_pnl == pytest.approx(3.0)
    assert metrics.unrealized_pnl == pytest.approx(1.0)
    # total_pnl = portfolio_value - start_capital = 51 - 50 = 1
    # Note: total_pnl uses portfolio - start, not realized+unrealized necessarily equal
    # when start capital accounting differs — architect says total = realized + unrealized
    # Portfolio snapshot total_pnl from ledger is realized+unrealized = 4
    # Architect section 8: Gesamt-P&L = realisiert + unrealisiert
    # Section 7: Gesamt-P&L = aktueller Portfolio-Wert - Startkapital
    # These can diverge if realized was withdrawn conceptually; we follow section 7 for total_pnl
    # and expose realized/unrealized separately. Documented in report.
    assert metrics.total_pnl == pytest.approx(1.0)
    assert metrics.realized_pnl + metrics.unrealized_pnl == pytest.approx(4.0)


def test_open_position_without_closed_trade() -> None:
    calc = PerformanceCalculator(start_capital=50.0)
    state = make_state(cash_eur=40.0, btc_amount=0.1, entry_price=100.0, in_position=True)
    metrics = calc.compute(state, 105.0, trades=[buy()])
    assert metrics.closed_trades == 0
    assert metrics.unrealized_pnl == pytest.approx(0.5)
    assert metrics.realized_pnl == 0.0


def test_total_fees() -> None:
    calc = PerformanceCalculator()
    metrics = calc.compute(make_state(), 100.0, trades=[buy(0.06), sell(1.0, fee=0.05)])
    assert metrics.total_fees == pytest.approx(0.11)


def test_max_drawdown() -> None:
    calc = PerformanceCalculator()
    dd = calc.max_drawdown_pct([100.0, 110.0, 99.0, 105.0])
    # peak 110 → 99 = 10%
    assert dd == pytest.approx(10.0)


def test_max_drawdown_empty() -> None:
    calc = PerformanceCalculator()
    assert calc.max_drawdown_pct([]) is None
    assert calc.max_drawdown_pct([50.0]) == 0.0


def test_daily_pnl_europe_berlin() -> None:
    calc = PerformanceCalculator(timezone_name="Europe/Berlin")
    now = datetime(2026, 6, 15, 14, 0, tzinfo=timezone.utc)
    # Berlin summer: midnight is 22:00 UTC previous day
    snapshots = [
        {"timestamp": "2026-06-14T21:00:00+00:00", "portfolio_value": 48.0},
        {"timestamp": "2026-06-14T22:00:00+00:00", "portfolio_value": 49.0},
        {"timestamp": "2026-06-15T10:00:00+00:00", "portfolio_value": 50.5},
    ]
    daily = calc.daily_pnl(51.0, snapshots, now=now)
    assert daily == pytest.approx(2.0)  # 51 - 49


def test_daily_pnl_insufficient_data() -> None:
    calc = PerformanceCalculator(timezone_name="Europe/Berlin")
    now = datetime(2026, 6, 15, 14, 0, tzinfo=timezone.utc)
    snapshots = [{"timestamp": "2026-06-10T10:00:00+00:00", "portfolio_value": 50.0}]
    assert calc.daily_pnl(51.0, snapshots, now=now) is None


def test_period_insufficient_data() -> None:
    calc = PerformanceCalculator()
    period = calc.period_metrics([], current_value=50.0, period="1W")
    assert period.insufficient_data is True
    assert period.pnl is None


def test_period_1d_with_data() -> None:
    calc = PerformanceCalculator()
    now = datetime(2026, 6, 15, 14, 0, tzinfo=timezone.utc)
    snapshots = [
        {"timestamp": "2026-06-14T20:00:00+00:00", "portfolio_value": 48.0},
        {"timestamp": "2026-06-15T08:00:00+00:00", "portfolio_value": 49.0},
    ]
    period = calc.period_metrics(snapshots, current_value=50.0, period="1D", now=now)
    assert period.insufficient_data is False
    # cutoff = now - 1 day → 2026-06-14 14:00 UTC; first in-window snap is 48.0
    assert period.start_value == pytest.approx(48.0)
    assert period.pnl == pytest.approx(2.0)


def test_return_when_equal_to_start() -> None:
    calc = PerformanceCalculator(start_capital=50.0)
    metrics = calc.compute(make_state(), 100.0, trades=[])
    assert metrics.total_return == pytest.approx(0.0)
    assert metrics.total_pnl == pytest.approx(0.0)


def test_from_backtest_trades() -> None:
    calc = PerformanceCalculator(start_capital=50.0)
    metrics = calc.from_backtest_trades(
        start_capital=50.0,
        end_capital=52.0,
        sell_pnls=[1.5, -0.5],
        total_fees=0.2,
        equity_curve=[50.0, 51.5, 50.5, 52.0],
    )
    assert metrics.total_return == pytest.approx(0.04)
    assert metrics.win_rate == pytest.approx(0.5)
    assert metrics.profit_factor == pytest.approx(3.0)
    assert metrics.total_fees == pytest.approx(0.2)
    assert metrics.best_trade == pytest.approx(1.5)
    assert metrics.worst_trade == pytest.approx(-0.5)
