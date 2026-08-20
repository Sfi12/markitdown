from __future__ import annotations

PAPER_MODE = "paper"

TRADING_MODE_ENV = "TRADING_MODE"


class TradingModeError(RuntimeError):
    """Raised when the application is not configured for paper trading."""


def assert_paper_trading_mode(trading_mode: str) -> None:
    if trading_mode != PAPER_MODE:
        raise TradingModeError(
            f"SICHERHEITSSTOPP: TRADING_MODE muss '{PAPER_MODE}' sein, "
            f"erhalten: '{trading_mode}'. "
            "Live-Trading ist in diesem Build nicht verfügbar. "
            "Setze TRADING_MODE=paper und starte erneut."
        )


def enforce_paper_trading_startup(trading_mode: str) -> None:
    """Hard fail at startup unless paper trading mode is active."""
    assert_paper_trading_mode(trading_mode)
