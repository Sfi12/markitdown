from __future__ import annotations

from pathlib import Path

import pytest

from bot.config import BotConfig


@pytest.fixture
def config_path() -> Path:
    return Path(__file__).resolve().parents[1] / "config.yaml"


@pytest.fixture
def config(config_path: Path) -> BotConfig:
    return BotConfig.load(config_path)
