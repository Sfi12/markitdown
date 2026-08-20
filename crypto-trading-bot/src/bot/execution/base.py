from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from bot.storage import BotState
from bot.strategy import StrategySignal


@dataclass(frozen=True)
class ExecutionResult:
    executed: bool
    message: str


class ExecutionProvider(ABC):
    """Simulated or live order execution."""

    @abstractmethod
    def portfolio_value(self, state: BotState, price: float) -> float:
        """Calculate total portfolio value at the given price."""

    @abstractmethod
    def check_risk_exits(self, state: BotState, price: float) -> StrategySignal | None:
        """Return a forced exit signal when stop-loss or take-profit triggers."""

    @abstractmethod
    def execute_signal(
        self,
        state: BotState,
        signal: StrategySignal,
    ) -> tuple[BotState, ExecutionResult]:
        """Execute a strategy signal and return updated state."""
