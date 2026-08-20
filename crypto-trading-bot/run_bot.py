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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crypto Paper-Trading Bot")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Nur einen Tick ausführen und beenden",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = BotConfig.load(ROOT / "config.yaml")
    engine = TradingEngine(config)
    state = engine.initialize()
    engine.set_running(True)

    print(f"Paper-Trading gestartet für {config.product_id}")
    print(f"Startkapital: {config.start_capital_eur:.2f} EUR")

    try:
        while True:
            state = engine.tick()
            portfolio = engine.trader.portfolio_value(state, state.last_price or 0.0)
            print(
                f"[{state.last_update}] Preis={state.last_price:.2f} EUR | "
                f"Portfolio={portfolio:.2f} EUR | Signal={state.last_signal}"
            )
            if args.once:
                break
            time.sleep(config.poll_interval_seconds)
    except KeyboardInterrupt:
        engine.set_running(False)
        print("\nBot gestoppt.")


if __name__ == "__main__":
    main()
