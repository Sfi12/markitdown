from __future__ import annotations

from dataclasses import dataclass

from bot.storage import BotState, Storage, TradeRecord, utc_now
from bot.strategy import SignalAction, StrategySignal


@dataclass(frozen=True)
class PaperTradeResult:
    executed: bool
    message: str


class PaperTrader:
    def __init__(
        self,
        storage: Storage,
        max_trade_eur: float,
        stop_loss_pct: float,
        take_profit_pct: float,
        fee_pct: float,
        slippage_pct: float,
    ) -> None:
        self.storage = storage
        self.max_trade_eur = max_trade_eur
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.fee_pct = fee_pct
        self.slippage_pct = slippage_pct

    def portfolio_value(self, state: BotState, price: float) -> float:
        return state.cash_eur + (state.btc_amount * price)

    def apply_slippage(self, price: float, side: str) -> float:
        multiplier = 1 + (self.slippage_pct / 100)
        if side == "buy":
            return price * multiplier
        return price / multiplier

    def check_risk_exits(self, state: BotState, price: float) -> StrategySignal | None:
        if not state.in_position or state.entry_price is None:
            return None

        change_pct = ((price - state.entry_price) / state.entry_price) * 100
        if change_pct <= -self.stop_loss_pct:
            return StrategySignal(
                action=SignalAction.SELL,
                reason=f"Stop-Loss ({self.stop_loss_pct:.1f}%)",
                price=price,
                ema_fast=0.0,
                ema_slow=0.0,
                rsi=0.0,
            )
        if change_pct >= self.take_profit_pct:
            return StrategySignal(
                action=SignalAction.SELL,
                reason=f"Take-Profit ({self.take_profit_pct:.1f}%)",
                price=price,
                ema_fast=0.0,
                ema_slow=0.0,
                rsi=0.0,
            )
        return None

    def execute_signal(
        self,
        state: BotState,
        signal: StrategySignal,
    ) -> tuple[BotState, PaperTradeResult]:
        if signal.action == SignalAction.HOLD:
            return state, PaperTradeResult(False, signal.reason)

        if signal.action == SignalAction.BUY:
            return self._buy(state, signal)
        return self._sell(state, signal)

    def _buy(
        self,
        state: BotState,
        signal: StrategySignal,
    ) -> tuple[BotState, PaperTradeResult]:
        if state.in_position:
            return state, PaperTradeResult(False, "Bereits in Position")

        trade_budget = min(self.max_trade_eur, state.cash_eur)
        if trade_budget <= 0:
            return state, PaperTradeResult(False, "Kein verfügbares EUR-Guthaben")

        execution_price = self.apply_slippage(signal.price, "buy")
        fee_eur = trade_budget * (self.fee_pct / 100)
        net_eur = trade_budget - fee_eur
        if net_eur <= 0:
            return state, PaperTradeResult(False, "Trade zu klein nach Gebühren")

        btc_amount = net_eur / execution_price
        updated = BotState(
            cash_eur=state.cash_eur - trade_budget,
            btc_amount=state.btc_amount + btc_amount,
            entry_price=execution_price,
            in_position=True,
            is_running=state.is_running,
            last_price=signal.price,
            last_signal=signal.reason,
            last_update=utc_now().isoformat(),
            total_trades=state.total_trades + 1,
            realized_pnl_eur=state.realized_pnl_eur,
        )
        self.storage.add_trade(
            TradeRecord(
                id=None,
                timestamp=updated.last_update,
                side="buy",
                price=execution_price,
                amount_eur=trade_budget,
                amount_btc=btc_amount,
                fee_eur=fee_eur,
                reason=signal.reason,
                balance_eur_after=updated.cash_eur,
                balance_btc_after=updated.btc_amount,
            )
        )
        self.storage.add_log("trade", f"Kauf: {btc_amount:.8f} BTC @ {execution_price:.2f} EUR")
        return updated, PaperTradeResult(True, signal.reason)

    def _sell(
        self,
        state: BotState,
        signal: StrategySignal,
    ) -> tuple[BotState, PaperTradeResult]:
        if not state.in_position or state.btc_amount <= 0:
            return state, PaperTradeResult(False, "Keine Position zum Verkaufen")

        execution_price = self.apply_slippage(signal.price, "sell")
        gross_eur = state.btc_amount * execution_price
        fee_eur = gross_eur * (self.fee_pct / 100)
        net_eur = gross_eur - fee_eur
        cost_basis = (state.entry_price or execution_price) * state.btc_amount
        realized_delta = net_eur - cost_basis

        updated = BotState(
            cash_eur=state.cash_eur + net_eur,
            btc_amount=0.0,
            entry_price=None,
            in_position=False,
            is_running=state.is_running,
            last_price=signal.price,
            last_signal=signal.reason,
            last_update=utc_now().isoformat(),
            total_trades=state.total_trades + 1,
            realized_pnl_eur=state.realized_pnl_eur + realized_delta,
        )
        self.storage.add_trade(
            TradeRecord(
                id=None,
                timestamp=updated.last_update,
                side="sell",
                price=execution_price,
                amount_eur=gross_eur,
                amount_btc=state.btc_amount,
                fee_eur=fee_eur,
                reason=signal.reason,
                balance_eur_after=updated.cash_eur,
                balance_btc_after=updated.btc_amount,
            )
        )
        self.storage.add_log(
            "trade",
            f"Verkauf: {state.btc_amount:.8f} BTC @ {execution_price:.2f} EUR "
            f"(PnL {realized_delta:+.2f} EUR)",
        )
        return updated, PaperTradeResult(True, signal.reason)
