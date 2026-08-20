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
    metrics = result.metrics

    print("=== Backtest Ergebnis ===")
    print(f"Startkapital:     {result.start_capital_eur:.2f} EUR")
    print(f"Endkapital:       {result.end_capital_eur:.2f} EUR")
    print(f"Rendite:          {result.total_return_pct:+.2f} %")
    print(f"Abgeschlossene Trades: {result.total_trades}")
    print(f"Gewinner:         {result.winning_trades}")
    print(f"Verlierer:        {result.losing_trades}")
    print(f"Max Drawdown:     {result.max_drawdown_pct:.2f} %")
    if metrics is not None:
        wr = "n/a" if metrics.win_rate is None else f"{metrics.win_rate * 100:.1f} %"
        avg_w = "n/a" if metrics.average_win is None else f"{metrics.average_win:+.4f} EUR"
        avg_l = "n/a" if metrics.average_loss is None else f"{metrics.average_loss:+.4f} EUR"
        if metrics.profit_factor_infinite:
            pf = "inf (no losses)"
        elif metrics.profit_factor is None:
            pf = "n/a"
        else:
            pf = f"{metrics.profit_factor:.3f}"
        best = "n/a" if metrics.best_trade is None else f"{metrics.best_trade:+.4f} EUR"
        worst = "n/a" if metrics.worst_trade is None else f"{metrics.worst_trade:+.4f} EUR"
        print(f"Win Rate:         {wr}")
        print(f"Average Win:      {avg_w}")
        print(f"Average Loss:     {avg_l}")
        print(f"Profit Factor:    {pf}")
        print(f"Total Fees:       {metrics.total_fees:.4f} EUR")
        print(f"Best Trade:       {best}")
        print(f"Worst Trade:      {worst}")
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
