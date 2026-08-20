from __future__ import annotations

from dataclasses import dataclass

from bot.storage import BotState


@dataclass(frozen=True)
class PortfolioSnapshot:
    cash_eur: float
    btc_amount: float
    entry_price: float | None
    market_price: float
    market_value: float
    portfolio_value: float
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float


class PortfolioLedger:
    """Deterministic portfolio calculations and state updates."""

    def __init__(self, start_capital_eur: float = 50.0) -> None:
        self.start_capital_eur = start_capital_eur

    def market_value(self, btc_amount: float, market_price: float) -> float:
        return btc_amount * market_price

    def portfolio_value(self, cash_eur: float, btc_amount: float, market_price: float) -> float:
        return cash_eur + self.market_value(btc_amount, market_price)

    def unrealized_pnl(
        self,
        btc_amount: float,
        entry_price: float | None,
        market_price: float,
    ) -> float:
        if btc_amount <= 0 or entry_price is None:
            return 0.0
        return (market_price - entry_price) * btc_amount

    def snapshot(self, state: BotState, market_price: float) -> PortfolioSnapshot:
        market_value = self.market_value(state.btc_amount, market_price)
        portfolio_value = state.cash_eur + market_value
        unrealized = self.unrealized_pnl(state.btc_amount, state.entry_price, market_price)
        return PortfolioSnapshot(
            cash_eur=state.cash_eur,
            btc_amount=state.btc_amount,
            entry_price=state.entry_price,
            market_price=market_price,
            market_value=market_value,
            portfolio_value=portfolio_value,
            realized_pnl=state.realized_pnl_eur,
            unrealized_pnl=unrealized,
            total_pnl=state.realized_pnl_eur + unrealized,
        )

    def apply_buy(
        self,
        state: BotState,
        *,
        cash_spent: float,
        btc_bought: float,
        entry_price: float,
        market_price: float,
        reason: str,
        timestamp: str,
    ) -> BotState:
        cash_after = state.cash_eur - cash_spent
        btc_after = state.btc_amount + btc_bought
        if cash_after < -1e-9 or btc_after < -1e-9:
            raise ValueError("Portfolio apply_buy would create negative balances")

        return BotState(
            cash_eur=cash_after,
            btc_amount=btc_after,
            entry_price=entry_price,
            in_position=True,
            is_running=state.is_running,
            last_price=market_price,
            last_signal=reason,
            last_update=timestamp,
            total_trades=state.total_trades + 1,
            realized_pnl_eur=state.realized_pnl_eur,
        )

    def apply_sell(
        self,
        state: BotState,
        *,
        cash_received: float,
        btc_sold: float,
        realized_delta: float,
        market_price: float,
        reason: str,
        timestamp: str,
    ) -> BotState:
        cash_after = state.cash_eur + cash_received
        btc_after = state.btc_amount - btc_sold
        if cash_after < -1e-9 or btc_after < -1e-9:
            raise ValueError("Portfolio apply_sell would create negative balances")

        return BotState(
            cash_eur=cash_after,
            btc_amount=0.0 if abs(btc_after) < 1e-12 else btc_after,
            entry_price=None,
            in_position=False,
            is_running=state.is_running,
            last_price=market_price,
            last_signal=reason,
            last_update=timestamp,
            total_trades=state.total_trades + 1,
            realized_pnl_eur=state.realized_pnl_eur + realized_delta,
        )
