from __future__ import annotations

from dataclasses import dataclass

from bot.storage import BotState
from bot.strategy import SignalAction, StrategySignal


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    side: str | None
    budget_eur: float
    reason: str
    message: str


class RiskManager:
    """
    Risk layer: position size, cash checks, SL/TP, no shorts/leverage.

    Does not execute trades or compute fees/slippage.
    """

    def __init__(
        self,
        max_trade_eur: float = 10.0,
        stop_loss_pct: float = 1.5,
        take_profit_pct: float = 3.0,
        symbol: str = "BTC-EUR",
    ) -> None:
        self.max_trade_eur = max_trade_eur
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.symbol = symbol

    def position_size_eur(self, cash_eur: float) -> float:
        if cash_eur <= 0:
            return 0.0
        return min(self.max_trade_eur, cash_eur)

    def stop_loss_price(self, entry_price: float) -> float:
        return entry_price * (1 - self.stop_loss_pct / 100)

    def take_profit_price(self, entry_price: float) -> float:
        return entry_price * (1 + self.take_profit_pct / 100)

    def check_exits(self, state: BotState, market_price: float) -> StrategySignal | None:
        """Independent of strategy — close when SL/TP levels are hit."""
        if not state.in_position or state.entry_price is None or state.btc_amount <= 0:
            return None

        stop = self.stop_loss_price(state.entry_price)
        take = self.take_profit_price(state.entry_price)

        if market_price <= stop:
            return StrategySignal(
                action=SignalAction.SELL,
                reason="stop_loss",
                price=market_price,
                ema_fast=0.0,
                ema_slow=0.0,
                rsi=0.0,
            )
        if market_price >= take:
            return StrategySignal(
                action=SignalAction.SELL,
                reason="take_profit",
                price=market_price,
                ema_fast=0.0,
                ema_slow=0.0,
                rsi=0.0,
            )
        return None

    def evaluate_signal(self, state: BotState, signal: StrategySignal) -> RiskDecision:
        if signal.action == SignalAction.HOLD:
            return RiskDecision(False, None, 0.0, signal.reason, signal.reason)

        if signal.action == SignalAction.BUY:
            return self._evaluate_buy(state, signal)
        return self._evaluate_sell(state, signal)

    def _evaluate_buy(self, state: BotState, signal: StrategySignal) -> RiskDecision:
        if state.in_position or state.btc_amount > 0:
            return RiskDecision(
                False,
                "buy",
                0.0,
                signal.reason,
                "Rejected: already in position",
            )
        if state.cash_eur <= 0:
            return RiskDecision(
                False,
                "buy",
                0.0,
                signal.reason,
                "Rejected: no available cash",
            )
        if state.cash_eur < 0:
            return RiskDecision(
                False,
                "buy",
                0.0,
                signal.reason,
                "Rejected: negative cash balance",
            )

        budget = self.position_size_eur(state.cash_eur)
        if budget <= 0:
            return RiskDecision(
                False,
                "buy",
                0.0,
                signal.reason,
                "Rejected: invalid order size",
            )
        if budget > self.max_trade_eur:
            return RiskDecision(
                False,
                "buy",
                0.0,
                signal.reason,
                "Rejected: exceeds max trade size",
            )
        if budget > state.cash_eur:
            return RiskDecision(
                False,
                "buy",
                0.0,
                signal.reason,
                "Rejected: exceeds available cash",
            )

        return RiskDecision(True, "buy", budget, signal.reason, "Approved buy")

    def _evaluate_sell(self, state: BotState, signal: StrategySignal) -> RiskDecision:
        if not state.in_position or state.btc_amount <= 0:
            return RiskDecision(
                False,
                "sell",
                0.0,
                signal.reason,
                "Rejected: no position to sell",
            )
        if state.btc_amount < 0:
            return RiskDecision(
                False,
                "sell",
                0.0,
                signal.reason,
                "Rejected: negative BTC balance",
            )
        return RiskDecision(True, "sell", 0.0, signal.reason, "Approved sell")
