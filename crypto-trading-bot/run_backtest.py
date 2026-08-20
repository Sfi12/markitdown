#!/usr/bin/env python3
"""Run a deterministic paper backtest — no live orders, no optimization."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from bot.backtest.engine import StrategyBacktester
from bot.backtest.periods import INTERVALS, PERIODS
from bot.config import BotConfig
from bot.security import enforce_paper_trading_startup


def _fmt_pct(ratio: float) -> str:
    return f"{ratio * 100:+.2f} %"


def print_report(result) -> None:
    metrics = result.metrics
    window = result.window

    print("=== Backtest Ergebnis (PAPER ONLY) ===")
    print(f"Datenquelle:      Coinbase Public Exchange API (kein API-Key)")
    print(f"Zeitraum:         {window.period} ({window.start.isoformat()} → {window.end.isoformat()})")
    print(f"Candle-Intervall: {window.interval} (granularity={window.granularity}s)")
    print(f"Kerzen:           {result.candle_count} (erwartet ~{window.expected_bars})")
    print(f"insufficient_data:{result.insufficient_data}")
    print(
        f"Datenqualität:    ok={result.data_quality.ok} | "
        f"warnings={len(result.data_quality.warnings)} | "
        f"errors={len(result.data_quality.errors)} | "
        f"duplicates={result.data_quality.duplicate_timestamps} | "
        f"gaps≈{result.data_quality.missing_bars_estimate}"
    )
    print()
    print("--- Strategie (EMA20/EMA50 + RSI14) ---")
    print(f"Startkapital:     {result.start_capital:.2f} EUR")
    print(f"Endkapital:       {result.end_capital:.2f} EUR")
    print(f"Gesamtrendite:    {_fmt_pct(result.total_return)}")
    print(f"Gesamt-P&L:       {result.total_pnl:+.4f} EUR")
    print(f"Abgeschlossene Trades: {result.total_trades}")
    print(f"Stichprobe:       {result.sample_note}")
    print(f"Gewinner:         {result.winning_trades}")
    print(f"Verlierer:        {result.losing_trades}")
    print(f"Open am Ende:     {result.open_position_at_end}")
    print(f"Exposure:         {result.exposure * 100:.1f} %")
    if result.average_holding_seconds is None:
        print("Ø Haltedauer:     n/a")
    else:
        hours = result.average_holding_seconds / 3600.0
        print(f"Ø Haltedauer:     {hours:.2f} h ({result.average_holding_seconds:.0f}s)")
    print(f"Längste Gewinnserie: {result.longest_win_streak}")
    print(f"Längste Verlustserie:{result.longest_loss_streak}")
    print(f"Längster DD-Abschnitt (Bars): {result.longest_drawdown_bars}")
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

    if result.buy_and_hold is not None:
        bh = result.buy_and_hold
        print()
        print(f"--- {bh.label} ---")
        print(f"Startkapital:     {bh.start_capital:.2f} EUR")
        print(f"Endkapital:       {bh.end_capital:.2f} EUR")
        print(f"Benchmark-Return: {_fmt_pct(bh.total_return)}")
        print(f"Benchmark-P&L:    {bh.total_pnl:+.4f} EUR")
        print(f"Benchmark Fees:   {bh.fees:.4f} EUR")
        print(f"Benchmark Slip:   {bh.slippage_cost:.4f} EUR")
        print(
            f"Strategie vs B&H: {_fmt_pct(result.total_return)} vs {_fmt_pct(bh.total_return)}"
        )

    if result.warnings:
        print()
        print("--- Hinweise ---")
        for warning in result.warnings:
            print(f"  ! {warning}")

    print()
    print(f"Equity Curve Punkte (Strategy): {len(result.equity_curve)}")
    if result.buy_and_hold is not None:
        print(f"Equity Curve Punkte (B&H):      {len(result.buy_and_hold.equity_curve)}")

    print()
    print("Letzte geschlossene Trades:")
    if not result.closed_trades:
        print("  (keine)")
    for trade in result.closed_trades[-10:]:
        print(
            f"  {trade.entry_timestamp} → {trade.exit_timestamp} | "
            f"entry {trade.entry_price:.2f} exit {trade.exit_price:.2f} | "
            f"qty {trade.quantity:.8f} | PnL {trade.pnl:+.4f} EUR "
            f"({trade.return_pct:+.2f} %) | fees {trade.fees:.4f} | "
            f"slip {trade.slippage:.4f} | hold {trade.holding_duration_seconds:.0f}s | "
            f"{trade.exit_reason}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Paper-only strategy backtest (no optimization).")
    parser.add_argument(
        "--period",
        choices=sorted(PERIODS.keys()),
        default=None,
        help="Historical window (default from config.yaml)",
    )
    parser.add_argument(
        "--interval",
        choices=sorted(INTERVALS.keys()),
        default=None,
        help="Candle interval (default from config.yaml)",
    )
    args = parser.parse_args()

    config = BotConfig.load(ROOT / "config.yaml")
    enforce_paper_trading_startup(config.trading_mode)
    period = args.period or config.backtest_period
    interval = args.interval or config.backtest_interval

    result = StrategyBacktester(config).run(period=period, interval=interval)
    print_report(result)


if __name__ == "__main__":
    main()
