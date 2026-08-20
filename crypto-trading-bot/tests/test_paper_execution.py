from __future__ import annotations

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


def make_provider(max_trade_eur: float = 10.0) -> PaperExecutionProvider:
    return PaperExecutionProvider(
        storage=MemoryStore(),
        max_trade_eur=max_trade_eur,
        stop_loss_pct=1.5,
        take_profit_pct=3.0,
        fee_pct=0.6,
        slippage_pct=0.05,
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
        reason="test buy",
        price=price,
        ema_fast=1.0,
        ema_slow=0.5,
        rsi=55.0,
    )


def sell_signal(price: float = 100.0) -> StrategySignal:
    return StrategySignal(
        action=SignalAction.SELL,
        reason="test sell",
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


def test_paper_buy_rejects_when_already_in_position() -> None:
    provider = make_provider()
    state = base_state(in_position=True, btc_amount=0.01)
    updated, result = provider.execute_signal(state, buy_signal())

    assert result.executed is False
    assert updated.btc_amount == 0.01


def test_stop_loss_triggers_sell_signal() -> None:
    provider = make_provider()
    state = base_state(in_position=True, entry_price=100.0, btc_amount=0.1)
    signal = provider.check_risk_exits(state, 98.0)

    assert signal is not None
    assert signal.action == SignalAction.SELL
    assert "Stop-Loss" in signal.reason


def test_take_profit_triggers_sell_signal() -> None:
    provider = make_provider()
    state = base_state(in_position=True, entry_price=100.0, btc_amount=0.1)
    signal = provider.check_risk_exits(state, 104.0)

    assert signal is not None
    assert signal.action == SignalAction.SELL
    assert "Take-Profit" in signal.reason


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


def test_portfolio_value() -> None:
    provider = make_provider()
    state = base_state(cash_eur=40.0, btc_amount=0.1)
    assert provider.portfolio_value(state, 100.0) == 50.0
