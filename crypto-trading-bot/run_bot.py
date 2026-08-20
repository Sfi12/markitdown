#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from bot.config import BotConfig
from bot.engine import TradingEngine
from bot.security import enforce_paper_trading_startup


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crypto Paper-Trading Bot")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Nur einen Tick ausführen und beenden",
    )
    parser.add_argument(
        "--report-every",
        type=int,
        default=10,
        help="Paper-Report alle N erfolgreichen Loop-Iterationen (0=nur am Ende)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = BotConfig.load(ROOT / "config.yaml")
    enforce_paper_trading_startup(config.trading_mode)
    engine = TradingEngine(config)
    state = engine.initialize()
    engine.set_running(True)

    print(f"Paper-Trading gestartet für {config.product_id}")
    print(f"Startkapital: {config.start_capital_eur:.2f} EUR")
    print(f"Stale-Grenzwert: {config.stale_after_seconds}s")

    loops = 0
    try:
        while True:
            state = engine.tick()
            health = engine.get_health(state)
            price = state.last_price or 0.0
            portfolio = engine.trader.portfolio_value(state, price)
            print(
                f"[{state.last_update}] {health.display} | "
                f"Preis={price:.2f} EUR | Portfolio={portfolio:.2f} EUR | "
                f"Signal={state.last_signal}"
            )
            loops += 1
            if args.report_every > 0 and loops % args.report_every == 0:
                print(engine.get_paper_report(market_price=price).format_text())
            if args.once:
                break
            time.sleep(config.poll_interval_seconds)
    except KeyboardInterrupt:
        print("\nStoppe Bot…")
    finally:
        engine.set_running(False)
        report = engine.get_paper_report()
        print(report.format_text())
        print("Bot gestoppt.")


if __name__ == "__main__":
    main()
