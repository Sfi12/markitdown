from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from typing import Any

from bot.storage import BotState
from bot.strategy import StrategySignal


@dataclass(frozen=True)
class TradeFill:
    """Structured paper-trade fill prepared for Phase E persistence."""

    side: str
    symbol: str
    requested_price: float
    execution_price: float
    quantity: float
    gross_value: float
    fee: float
    slippage: float
    net_value: float
    pnl: float
    reason: str
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExecutionResult:
    executed: bool
    message: str
    fill: TradeFill | None = None

    @property
    def reason(self) -> str:
        if self.fill is not None:
            return self.fill.reason
        return self.message


class ExecutionProvider(ABC):
    """Simulated order execution only (paper)."""

    @abstractmethod
    def portfolio_value(self, state: BotState, price: float) -> float:
        """Compatibility helper — delegates to portfolio ledger."""

    @abstractmethod
    def check_risk_exits(self, state: BotState, price: float) -> StrategySignal | None:
        """Compatibility helper — delegates to risk manager."""

    @abstractmethod
    def execute_signal(
        self,
        state: BotState,
        signal: StrategySignal,
    ) -> tuple[BotState, ExecutionResult]:
        """Validate via risk, simulate fill, apply via portfolio."""
