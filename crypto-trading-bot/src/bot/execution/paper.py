from __future__ import annotations

from typing import Protocol

from bot.execution.base import ExecutionProvider, ExecutionResult, TradeFill
from bot.portfolio.ledger import PortfolioLedger
from bot.risk.manager import RiskManager
from bot.storage import BotState, TradeRecord, utc_now
from bot.strategy import SignalAction, StrategySignal


class TradeStorage(Protocol):
    def add_trade(self, trade: TradeRecord) -> None: ...

    def add_log(self, level: str, message: str) -> None: ...


class PaperExecutionProvider(ExecutionProvider):
    """
    Paper-only execution.

    Flow: Risk validates → simulate fee/slippage → Portfolio applies → optional storage.
    Never sends network trading orders.
    """

    def __init__(
        self,
        storage: TradeStorage,
        max_trade_eur: float,
        stop_loss_pct: float,
        take_profit_pct: float,
        fee_pct: float,
        slippage_pct: float,
        symbol: str = "BTC-EUR",
        start_capital_eur: float = 50.0,
        risk: RiskManager | None = None,
        portfolio: PortfolioLedger | None = None,
    ) -> None:
        self.storage = storage
        self.fee_pct = fee_pct
        self.slippage_pct = slippage_pct
        self.symbol = symbol
        self.risk = risk or RiskManager(
            max_trade_eur=max_trade_eur,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            symbol=symbol,
        )
        self.portfolio = portfolio or PortfolioLedger(start_capital_eur=start_capital_eur)
        # Compatibility attributes used by older tests
        self.max_trade_eur = max_trade_eur
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct

    def portfolio_value(self, state: BotState, price: float) -> float:
        return self.portfolio.portfolio_value(state.cash_eur, state.btc_amount, price)

    def check_risk_exits(self, state: BotState, price: float) -> StrategySignal | None:
        return self.risk.check_exits(state, price)

    def apply_slippage(self, price: float, side: str) -> float:
        factor = self.slippage_pct / 100
        if side == "buy":
            return price * (1 + factor)
        return price * (1 - factor)

    def execute_signal(
        self,
        state: BotState,
        signal: StrategySignal,
    ) -> tuple[BotState, ExecutionResult]:
        if signal.action == SignalAction.HOLD:
            return state, ExecutionResult(False, signal.reason)

        decision = self.risk.evaluate_signal(state, signal)
        if not decision.approved:
            self.storage.add_log("warning", decision.message)
            return state, ExecutionResult(False, decision.message)

        if decision.side == "buy":
            return self._buy(state, signal, decision.budget_eur)
        return self._sell(state, signal)

    def _buy(
        self,
        state: BotState,
        signal: StrategySignal,
        budget_eur: float,
    ) -> tuple[BotState, ExecutionResult]:
        requested_price = signal.price
        execution_price = self.apply_slippage(requested_price, "buy")
        slippage_cost = execution_price - requested_price
        fee_eur = budget_eur * (self.fee_pct / 100)
        net_eur = budget_eur - fee_eur
        if net_eur <= 0 or execution_price <= 0:
            message = "Rejected: invalid order size after fees"
            self.storage.add_log("warning", message)
            return state, ExecutionResult(False, message)

        quantity = net_eur / execution_price
        timestamp = utc_now().isoformat()
        fill = TradeFill(
            side="buy",
            symbol=self.symbol,
            requested_price=requested_price,
            execution_price=execution_price,
            quantity=quantity,
            gross_value=budget_eur,
            fee=fee_eur,
            slippage=slippage_cost,
            net_value=net_eur,
            pnl=0.0,
            reason=signal.reason,
            timestamp=timestamp,
        )

        updated = self.portfolio.apply_buy(
            state,
            cash_spent=budget_eur,
            btc_bought=quantity,
            entry_price=execution_price,
            market_price=requested_price,
            reason=signal.reason,
            timestamp=timestamp,
        )
        self._persist_fill(fill, updated)
        self.storage.add_log(
            "info",
            f"Kauf: {quantity:.8f} BTC @ {execution_price:.2f} EUR ({signal.reason})",
        )
        return updated, ExecutionResult(True, signal.reason, fill)

    def _sell(
        self,
        state: BotState,
        signal: StrategySignal,
    ) -> tuple[BotState, ExecutionResult]:
        requested_price = signal.price
        execution_price = self.apply_slippage(requested_price, "sell")
        slippage_cost = requested_price - execution_price
        quantity = state.btc_amount
        gross_eur = quantity * execution_price
        fee_eur = gross_eur * (self.fee_pct / 100)
        net_eur = gross_eur - fee_eur
        cost_basis = (state.entry_price or execution_price) * quantity
        realized_delta = net_eur - cost_basis
        timestamp = utc_now().isoformat()

        fill = TradeFill(
            side="sell",
            symbol=self.symbol,
            requested_price=requested_price,
            execution_price=execution_price,
            quantity=quantity,
            gross_value=gross_eur,
            fee=fee_eur,
            slippage=slippage_cost,
            net_value=net_eur,
            pnl=realized_delta,
            reason=signal.reason,
            timestamp=timestamp,
        )

        updated = self.portfolio.apply_sell(
            state,
            cash_received=net_eur,
            btc_sold=quantity,
            realized_delta=realized_delta,
            market_price=requested_price,
            reason=signal.reason,
            timestamp=timestamp,
        )
        self._persist_fill(fill, updated)
        self.storage.add_log(
            "info",
            f"Verkauf: {quantity:.8f} BTC @ {execution_price:.2f} EUR "
            f"(PnL {realized_delta:+.2f} EUR, {signal.reason})",
        )
        return updated, ExecutionResult(True, signal.reason, fill)

    def _persist_fill(self, fill: TradeFill, state: BotState) -> None:
        """Persist TradeFill fields; legacy columns mirrored for compatibility."""
        self.storage.add_trade(
            TradeRecord(
                id=None,
                timestamp=fill.timestamp,
                side=fill.side,
                reason=fill.reason,
                balance_eur_after=state.cash_eur,
                balance_btc_after=state.btc_amount,
                symbol=fill.symbol,
                requested_price=fill.requested_price,
                execution_price=fill.execution_price,
                quantity=fill.quantity,
                gross_value=fill.gross_value,
                fee=fill.fee,
                slippage=fill.slippage,
                net_value=fill.net_value,
                pnl=fill.pnl,
                price=fill.execution_price,
                amount_eur=fill.gross_value,
                amount_btc=fill.quantity,
                fee_eur=fill.fee,
            )
        )
