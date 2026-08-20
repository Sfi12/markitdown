from __future__ import annotations

import pytest

from bot.portfolio.ledger import PortfolioLedger
from bot.storage import BotState


def base_state(**overrides) -> BotState:
    state = BotState(
        cash_eur=50.0,
        btc_amount=0.0,
        entry_price=None,
        in_position=False,
        is_running=True,
        last_price=None,
        last_signal="",
        last_update=None,
        total_trades=0,
        realized_pnl_eur=0.0,
    )
    for key, value in overrides.items():
        setattr(state, key, value)
    return state


def test_buy_updates_cash_and_btc() -> None:
    ledger = PortfolioLedger()
    state = base_state()
    updated = ledger.apply_buy(
        state,
        cash_spent=10.0,
        btc_bought=0.1,
        entry_price=100.0,
        market_price=100.0,
        reason="test",
        timestamp="2026-01-01T00:00:00+00:00",
    )
    assert updated.cash_eur == 40.0
    assert updated.btc_amount == pytest.approx(0.1)
    assert updated.entry_price == 100.0
    assert updated.in_position is True


def test_sell_updates_cash_and_btc() -> None:
    ledger = PortfolioLedger()
    state = base_state(cash_eur=40.0, btc_amount=0.1, entry_price=100.0, in_position=True)
    updated = ledger.apply_sell(
        state,
        cash_received=10.5,
        btc_sold=0.1,
        realized_delta=0.5,
        market_price=110.0,
        reason="test",
        timestamp="2026-01-01T00:00:00+00:00",
    )
    assert updated.cash_eur == pytest.approx(50.5)
    assert updated.btc_amount == 0.0
    assert updated.in_position is False
    assert updated.realized_pnl_eur == pytest.approx(0.5)


def test_realized_and_unrealized_pnl() -> None:
    ledger = PortfolioLedger(start_capital_eur=50.0)
    state = base_state(
        cash_eur=40.0,
        btc_amount=0.1,
        entry_price=100.0,
        in_position=True,
        realized_pnl_eur=1.0,
    )
    snap = ledger.snapshot(state, market_price=110.0)
    assert snap.market_value == pytest.approx(11.0)
    assert snap.portfolio_value == pytest.approx(51.0)
    assert snap.unrealized_pnl == pytest.approx(1.0)
    assert snap.realized_pnl == pytest.approx(1.0)
    assert snap.total_pnl == pytest.approx(2.0)


def test_apply_buy_rejects_negative_balances() -> None:
    ledger = PortfolioLedger()
    with pytest.raises(ValueError):
        ledger.apply_buy(
            base_state(cash_eur=5.0),
            cash_spent=10.0,
            btc_bought=0.1,
            entry_price=100.0,
            market_price=100.0,
            reason="bad",
            timestamp="t",
        )
