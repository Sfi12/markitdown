#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from bot.config import BotConfig
from bot.engine import Backtester
from bot.security import enforce_paper_trading_startup


def main() -> None:
    config = BotConfig.load(ROOT / "config.yaml")
    enforce_paper_trading_startup(config.trading_mode)
    result = Backtester(config).run()

    print("=== Backtest Ergebnis ===")
    print(f"Startkapital:     {result.start_capital_eur:.2f} EUR")
    print(f"Endkapital:       {result.end_capital_eur:.2f} EUR")
    print(f"Rendite:          {result.total_return_pct:+.2f} %")
    print(f"Abgeschlossene Trades: {result.total_trades}")
    print(f"Gewinner:         {result.winning_trades}")
    print(f"Verlierer:        {result.losing_trades}")
    print(f"Max Drawdown:     {result.max_drawdown_pct:.2f} %")
    print()
    print("Letzte Trades:")
    for trade in result.trades[-10:]:
        pnl = trade.get("pnl_eur", 0.0)
        if trade["side"] == "sell":
            print(
                f"  {trade['timestamp']} | {trade['side'].upper()} @ "
                f"{trade['price']:.2f} | PnL {float(pnl):+.2f} EUR | {trade['reason']}"
            )
        else:
            print(
                f"  {trade['timestamp']} | {trade['side'].upper()} @ "
                f"{trade['price']:.2f} | {trade['reason']}"
            )


if __name__ == "__main__":
    main()
