from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class BotConfig:
    product_id: str
    start_capital_eur: float
    max_trade_eur: float
    stop_loss_pct: float
    take_profit_pct: float
    fee_pct: float
    slippage_pct: float
    ema_fast: int
    ema_slow: int
    rsi_period: int
    rsi_oversold: float
    rsi_overbought: float
    candle_granularity: int
    candle_limit: int
    poll_interval_seconds: int
    database_path: Path

    @classmethod
    def load(cls, path: Path | None = None) -> BotConfig:
        config_path = path or Path(__file__).resolve().parents[2] / "config.yaml"
        with config_path.open(encoding="utf-8") as handle:
            raw: dict[str, Any] = yaml.safe_load(handle)

        trading = raw["trading"]
        strategy = raw["strategy"]
        data = raw["data"]
        bot = raw["bot"]
        storage = raw["storage"]

        db_path = Path(storage["database_path"])
        if not db_path.is_absolute():
            db_path = config_path.parent / db_path

        return cls(
            product_id=trading["product_id"],
            start_capital_eur=float(trading["start_capital_eur"]),
            max_trade_eur=float(trading["max_trade_eur"]),
            stop_loss_pct=float(trading["stop_loss_pct"]),
            take_profit_pct=float(trading["take_profit_pct"]),
            fee_pct=float(trading["fee_pct"]),
            slippage_pct=float(trading["slippage_pct"]),
            ema_fast=int(strategy["ema_fast"]),
            ema_slow=int(strategy["ema_slow"]),
            rsi_period=int(strategy["rsi_period"]),
            rsi_oversold=float(strategy["rsi_oversold"]),
            rsi_overbought=float(strategy["rsi_overbought"]),
            candle_granularity=int(data["candle_granularity"]),
            candle_limit=int(data["candle_limit"]),
            poll_interval_seconds=int(bot["poll_interval_seconds"]),
            database_path=db_path,
        )
