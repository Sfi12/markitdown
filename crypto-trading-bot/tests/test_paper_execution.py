from __future__ import annotations

import pytest

from bot.execution.paper import PaperExecutionProvider
from bot.storage import BotState
from bot.strategy import SignalAction, StrategySignal


class MemoryStore:
    def __init__(self) -> None:
        self.trades: list[object] = []
        self.logs: list[tuple[str, str]] = []

    def add_trade(self, trade: object) -> None:
        self.trades.append(trade)

    def add_log(self, level: str, message: str) -> None:
        self.logs.append((level, message))


def make_provider(max_trade_eur: float = 10.0, slippage_pct: float = 0.10) -> PaperExecutionProvider:
    return PaperExecutionProvider(
        storage=MemoryStore(),
        max_trade_eur=max_trade_eur,
        stop_loss_pct=1.5,
        take_profit_pct=3.0,
        fee_pct=0.6,
        slippage_pct=slippage_pct,
    )


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


def test_paper_buy_respects_position_size() -> None:
    provider = make_provider(max_trade_eur=10.0)
    state = base_state()
    updated, result = provider.execute_signal(state, buy_signal(100.0))

    assert result.executed is True
    assert updated.cash_eur == 40.0
    assert updated.in_position is True
    assert updated.btc_amount > 0
    assert result.fill is not None
    assert result.fill.gross_value == 10.0


def test_paper_buy_rejects_when_already_in_position() -> None:
    provider = make_provider()
    state = base_state(in_position=True, btc_amount=0.01)
    updated, result = provider.execute_signal(state, buy_signal())

    assert result.executed is False
    assert updated.btc_amount == 0.01


def test_stop_loss_level_at_98_50() -> None:
    provider = make_provider()
    state = base_state(in_position=True, entry_price=100.0, btc_amount=0.1)
    signal = provider.check_risk_exits(state, 98.50)

    assert signal is not None
    assert signal.action == SignalAction.SELL
    assert signal.reason == "stop_loss"


def test_stop_loss_not_triggered_above_level() -> None:
    provider = make_provider()
    state = base_state(in_position=True, entry_price=100.0, btc_amount=0.1)
    assert provider.check_risk_exits(state, 98.51) is None


def test_take_profit_level_at_103_00() -> None:
    provider = make_provider()
    state = base_state(in_position=True, entry_price=100.0, btc_amount=0.1)
    signal = provider.check_risk_exits(state, 103.00)

    assert signal is not None
    assert signal.action == SignalAction.SELL
    assert signal.reason == "take_profit"


def test_take_profit_not_triggered_below_level() -> None:
    provider = make_provider()
    state = base_state(in_position=True, entry_price=100.0, btc_amount=0.1)
    assert provider.check_risk_exits(state, 102.99) is None


def test_paper_sell_closes_position() -> None:
    provider = make_provider()
    state = base_state(
        cash_eur=40.0,
        btc_amount=0.1,
        entry_price=100.0,
        in_position=True,
        total_trades=1,
    )
    updated, result = provider.execute_signal(state, sell_signal(110.0))

    assert result.executed is True
    assert updated.in_position is False
    assert updated.btc_amount == 0.0
    assert updated.cash_eur > 40.0
    assert result.fill is not None
    assert result.fill.pnl != 0.0


def test_sell_without_position_rejected() -> None:
    provider = make_provider()
    state = base_state(in_position=False)
    updated, result = provider.execute_signal(state, sell_signal())

    assert result.executed is False
    assert updated.in_position is False


def test_portfolio_value() -> None:
    provider = make_provider()
    state = base_state(cash_eur=40.0, btc_amount=0.1)
    assert provider.portfolio_value(state, 100.0) == 50.0


def test_slippage_default_0_10_percent() -> None:
    provider = make_provider(slippage_pct=0.10)
    buy_price = provider.apply_slippage(100.0, "buy")
    sell_price = provider.apply_slippage(100.0, "sell")
    assert buy_price == pytest.approx(100.10)
    assert sell_price == pytest.approx(99.90)


def test_buy_fee_0_60_percent() -> None:
    provider = make_provider()
    _, result = provider.execute_signal(base_state(), buy_signal(100.0))
    assert result.fill is not None
    assert result.fill.fee == pytest.approx(10.0 * 0.006)
    assert result.fill.net_value == pytest.approx(10.0 - result.fill.fee)


def test_sell_fee_0_60_percent() -> None:
    provider = make_provider()
    state = base_state(cash_eur=40.0, btc_amount=0.1, entry_price=100.0, in_position=True)
    _, result = provider.execute_signal(state, sell_signal(100.0))
    assert result.fill is not None
    expected_gross = 0.1 * 99.90
    assert result.fill.gross_value == pytest.approx(expected_gross)
    assert result.fill.fee == pytest.approx(expected_gross * 0.006)


def test_buy_quantity_uses_execution_price() -> None:
    provider = make_provider()
    _, result = provider.execute_signal(base_state(), buy_signal(100.0))
    assert result.fill is not None
    assert result.fill.execution_price == pytest.approx(100.10)
    assert result.fill.quantity == pytest.approx(result.fill.net_value / 100.10)


def test_trade_fill_fields_complete() -> None:
    provider = make_provider()
    _, result = provider.execute_signal(base_state(), buy_signal(100.0))
    fill = result.fill
    assert fill is not None
    for field in (
        "side",
        "symbol",
        "requested_price",
        "execution_price",
        "quantity",
        "gross_value",
        "fee",
        "slippage",
        "net_value",
        "pnl",
        "reason",
        "timestamp",
    ):
        assert hasattr(fill, field)


def test_cash_less_than_10_limits_trade() -> None:
    provider = make_provider()
    state = base_state(cash_eur=7.0)
    updated, result = provider.execute_signal(state, buy_signal(100.0))
    assert result.executed is True
    assert result.fill is not None
    assert result.fill.gross_value == 7.0
    assert updated.cash_eur == 0.0
