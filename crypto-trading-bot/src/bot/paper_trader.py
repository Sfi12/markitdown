"""Compatibility wrapper — use PaperExecutionProvider via bot.execution."""

from bot.execution.base import ExecutionResult
from bot.execution.paper import PaperExecutionProvider

PaperTradeResult = ExecutionResult
PaperTrader = PaperExecutionProvider

__all__ = ["PaperTrader", "PaperTradeResult", "PaperExecutionProvider"]
