from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from bot.security import PAPER_MODE, TRADING_MODE_ENV


@dataclass(frozen=True)
class AppConfig:
    trading_mode: str


@dataclass(frozen=True)
class TradingConfig:
    product_id: str
    start_capital_eur: float


@dataclass(frozen=True)
class RiskConfig:
    max_trade_eur: float
    stop_loss_pct: float
    take_profit_pct: float


@dataclass(frozen=True)
class ExecutionConfig:
    fee_pct: float
    slippage_pct: float


@dataclass(frozen=True)
class StrategyConfig:
    ema_fast: int
    ema_slow: int
    rsi_period: int
    rsi_entry: float
    rsi_exit: float


@dataclass(frozen=True)
class MarketDataConfig:
    candle_granularity: int
    candle_limit: int


@dataclass(frozen=True)
class BotConfig:
    app: AppConfig
    trading: TradingConfig
    risk: RiskConfig
    execution: ExecutionConfig
    strategy: StrategyConfig
    market_data: MarketDataConfig
    poll_interval_seconds: int
    database_path: Path

    @property
    def trading_mode(self) -> str:
        return self.app.trading_mode

    @property
    def product_id(self) -> str:
        return self.trading.product_id

    @property
    def start_capital_eur(self) -> float:
        return self.trading.start_capital_eur

    @property
    def max_trade_eur(self) -> float:
        return self.risk.max_trade_eur

    @property
    def stop_loss_pct(self) -> float:
        return self.risk.stop_loss_pct

    @property
    def take_profit_pct(self) -> float:
        return self.risk.take_profit_pct

    @property
    def fee_pct(self) -> float:
        return self.execution.fee_pct

    @property
    def slippage_pct(self) -> float:
        return self.execution.slippage_pct

    @property
    def ema_fast(self) -> int:
        return self.strategy.ema_fast

    @property
    def ema_slow(self) -> int:
        return self.strategy.ema_slow

    @property
    def rsi_period(self) -> int:
        return self.strategy.rsi_period

    @property
    def rsi_entry(self) -> float:
        return self.strategy.rsi_entry

    @property
    def rsi_exit(self) -> float:
        return self.strategy.rsi_exit

    @property
    def rsi_oversold(self) -> float:
        """Deprecated alias — use rsi_exit."""
        return self.strategy.rsi_exit

    @property
    def rsi_overbought(self) -> float:
        """Deprecated alias — use rsi_entry."""
        return self.strategy.rsi_entry

    @property
    def candle_granularity(self) -> int:
        return self.market_data.candle_granularity

    @property
    def candle_limit(self) -> int:
        return self.market_data.candle_limit

    @classmethod
    def load(cls, path: Path | None = None) -> BotConfig:
        config_path = path or Path(__file__).resolve().parents[2] / "config.yaml"
        with config_path.open(encoding="utf-8") as handle:
            raw: dict[str, Any] = yaml.safe_load(handle)

        app_raw = raw.get("app", {})
        trading_raw = raw["trading"]
        strategy_raw = raw["strategy"]
        data_raw = raw["data"]
        bot_raw = raw["bot"]
        storage_raw = raw["storage"]

        risk_raw = raw.get("risk", {})
        execution_raw = raw.get("execution", {})

        trading_mode = os.environ.get(
            TRADING_MODE_ENV,
            app_raw.get("trading_mode", PAPER_MODE),
        )

        db_path = Path(storage_raw["database_path"])
        if not db_path.is_absolute():
            db_path = config_path.parent / db_path

        return cls(
            app=AppConfig(trading_mode=str(trading_mode)),
            trading=TradingConfig(
                product_id=trading_raw["product_id"],
                start_capital_eur=float(trading_raw["start_capital_eur"]),
            ),
            risk=RiskConfig(
                max_trade_eur=float(
                    risk_raw.get("max_trade_eur", trading_raw.get("max_trade_eur", 10.0))
                ),
                stop_loss_pct=float(
                    risk_raw.get("stop_loss_pct", trading_raw.get("stop_loss_pct", 1.5))
                ),
                take_profit_pct=float(
                    risk_raw.get("take_profit_pct", trading_raw.get("take_profit_pct", 3.0))
                ),
            ),
            execution=ExecutionConfig(
                fee_pct=float(execution_raw.get("fee_pct", trading_raw.get("fee_pct", 0.6))),
                slippage_pct=float(
                    execution_raw.get("slippage_pct", trading_raw.get("slippage_pct", 0.10))
                ),
            ),
            strategy=StrategyConfig(
                ema_fast=int(strategy_raw["ema_fast"]),
                ema_slow=int(strategy_raw["ema_slow"]),
                rsi_period=int(strategy_raw["rsi_period"]),
                rsi_entry=float(strategy_raw.get("rsi_entry", 50.0)),
                rsi_exit=float(strategy_raw.get("rsi_exit", 45.0)),
            ),
            market_data=MarketDataConfig(
                candle_granularity=int(data_raw["candle_granularity"]),
                candle_limit=int(data_raw["candle_limit"]),
            ),
            poll_interval_seconds=int(bot_raw["poll_interval_seconds"]),
            database_path=db_path,
        )
