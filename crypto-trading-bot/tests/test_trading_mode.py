from __future__ import annotations

import os
import sys

import pytest

from bot.config import BotConfig
from bot.engine import Backtester, TradingEngine
from bot.security import (
    PAPER_MODE,
    TradingModeError,
    assert_paper_trading_mode,
    enforce_paper_trading_startup,
)


def test_default_trading_mode_is_paper(config: BotConfig) -> None:
    assert config.trading_mode == PAPER_MODE


def test_assert_paper_trading_mode_accepts_paper() -> None:
    assert_paper_trading_mode(PAPER_MODE)


def test_assert_paper_trading_mode_rejects_live() -> None:
    with pytest.raises(TradingModeError, match="SICHERHEITSSTOPP"):
        assert_paper_trading_mode("live")


def test_enforce_paper_trading_startup_rejects_non_paper() -> None:
    with pytest.raises(TradingModeError):
        enforce_paper_trading_startup("live")


def test_trading_engine_rejects_non_paper_mode(config: BotConfig, monkeypatch) -> None:
    monkeypatch.setenv("TRADING_MODE", "live")
    bad_config = BotConfig.load()
    with pytest.raises(TradingModeError):
        TradingEngine(bad_config)


def test_backtester_rejects_non_paper_mode(config: BotConfig, monkeypatch) -> None:
    monkeypatch.setenv("TRADING_MODE", "live")
    bad_config = BotConfig.load()
    with pytest.raises(TradingModeError):
        Backtester(bad_config)


def test_run_bot_main_rejects_non_paper_mode(monkeypatch) -> None:
    monkeypatch.setenv("TRADING_MODE", "live")
    monkeypatch.setattr(sys, "argv", ["run_bot.py", "--once"])
    from run_bot import main

    with pytest.raises(TradingModeError):
        main()


def test_env_trading_mode_overrides_yaml(config_path, monkeypatch) -> None:
    monkeypatch.setenv("TRADING_MODE", "paper")
    config = BotConfig.load(config_path)
    assert config.trading_mode == PAPER_MODE

    monkeypatch.setenv("TRADING_MODE", "live")
    config_live = BotConfig.load(config_path)
    assert config_live.trading_mode == "live"
    with pytest.raises(TradingModeError):
        enforce_paper_trading_startup(config_live.trading_mode)
