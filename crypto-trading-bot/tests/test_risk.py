from __future__ import annotations

from bot.risk.manager import RiskManager
from bot.storage import BotState
from bot.strategy import SignalAction, StrategySignal


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


def buy_signal(price: float = 100.0) -> StrategySignal:
    return StrategySignal(
        action=SignalAction.BUY,
        reason="EMA20 above EMA50 and RSI above 50",
        price=price,
        ema_fast=1.0,
        ema_slow=0.5,
        rsi=55.0,
    )


def sell_signal(price: float = 100.0, reason: str = "EMA20 below EMA50") -> StrategySignal:
    return StrategySignal(
        action=SignalAction.SELL,
        reason=reason,
        price=price,
        ema_fast=0.5,
        ema_slow=1.0,
        rsi=40.0,
    )


def test_max_trade_capped_at_10_eur() -> None:
    risk = RiskManager(max_trade_eur=10.0)
    assert risk.position_size_eur(50.0) == 10.0


def test_cash_less_than_max_trade() -> None:
    risk = RiskManager(max_trade_eur=10.0)
    assert risk.position_size_eur(7.0) == 7.0


def test_no_buy_when_already_in_position() -> None:
    risk = RiskManager()
    state = base_state(in_position=True, btc_amount=0.01, cash_eur=40.0)
    decision = risk.evaluate_signal(state, buy_signal())
    assert decision.approved is False
    assert "already in position" in decision.message


def test_no_sell_without_position() -> None:
    risk = RiskManager()
    decision = risk.evaluate_signal(base_state(), sell_signal())
    assert decision.approved is False
    assert "no position" in decision.message


def test_negative_cash_rejected() -> None:
    risk = RiskManager()
    decision = risk.evaluate_signal(base_state(cash_eur=-1.0), buy_signal())
    assert decision.approved is False


def test_approved_buy_budget() -> None:
    risk = RiskManager(max_trade_eur=10.0)
    decision = risk.evaluate_signal(base_state(cash_eur=50.0), buy_signal())
    assert decision.approved is True
    assert decision.budget_eur == 10.0


def test_stop_loss_levels() -> None:
    risk = RiskManager(stop_loss_pct=1.5, take_profit_pct=3.0)
    assert risk.stop_loss_price(100.0) == 98.5
    assert risk.take_profit_price(100.0) == 103.0


def test_stop_loss_exit_signal() -> None:
    risk = RiskManager(stop_loss_pct=1.5)
    state = base_state(in_position=True, entry_price=100.0, btc_amount=0.1)
    signal = risk.check_exits(state, 98.5)
    assert signal is not None
    assert signal.reason == "stop_loss"


def test_take_profit_exit_signal() -> None:
    risk = RiskManager(take_profit_pct=3.0)
    state = base_state(in_position=True, entry_price=100.0, btc_amount=0.1)
    signal = risk.check_exits(state, 103.0)
    assert signal is not None
    assert signal.reason == "take_profit"
