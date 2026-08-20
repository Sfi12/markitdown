from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class BuyAndHoldResult:
    label: str
    start_capital: float
    end_capital: float
    total_return: float
    total_pnl: float
    fees: float
    slippage_cost: float
    equity_curve: list[dict[str, float | str]]


def compute_buy_and_hold(
    candles: pd.DataFrame,
    *,
    start_capital: float,
    fee_pct: float,
    slippage_pct: float,
) -> BuyAndHoldResult:
    """
    Simple buy-and-hold benchmark for the same window.

    Buys once at the first close (with buy slippage + fee),
    marks to market on subsequent closes, no strategy exits.
    """
    if candles.empty:
        raise ValueError("Buy & Hold benötigt Kerzen.")

    first = float(candles.iloc[0]["close"])
    buy_price = first * (1 + slippage_pct / 100)
    fee = start_capital * (fee_pct / 100)
    net = start_capital - fee
    if net <= 0 or buy_price <= 0:
        raise ValueError("Buy & Hold Trade ungültig nach Gebühren.")
    qty = net / buy_price
    slippage_cost = (buy_price - first) * qty

    equity: list[dict[str, float | str]] = []
    end_capital = start_capital
    for _, row in candles.iterrows():
        price = float(row["close"])
        end_capital = qty * price
        equity.append(
            {
                "label": "Buy & Hold Equity",
                "timestamp": str(row["timestamp"]),
                "portfolio_value": end_capital,
            }
        )

    total_pnl = end_capital - start_capital
    total_return = total_pnl / start_capital if start_capital else 0.0
    return BuyAndHoldResult(
        label="Buy & Hold Benchmark",
        start_capital=start_capital,
        end_capital=end_capital,
        total_return=total_return,
        total_pnl=total_pnl,
        fees=fee,
        slippage_cost=slippage_cost,
        equity_curve=equity,
    )
