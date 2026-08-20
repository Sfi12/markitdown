from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_run_bot_once_smoke() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "run_bot.py"), "--once"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Paper-Trading gestartet" in result.stdout


def test_run_backtest_smoke() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "run_backtest.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Backtest Ergebnis" in result.stdout


def test_dashboard_import_smoke() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.path.insert(0, 'src'); "
            "import importlib.util; "
            "spec = importlib.util.spec_from_file_location('dash', 'dashboard/app.py'); "
            "mod = importlib.util.module_from_spec(spec); "
            "spec.loader.exec_module(mod); "
            "assert mod.CONFIG.trading_mode == 'paper'",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_run_bot_rejects_live_mode_smoke(monkeypatch) -> None:
    env = {"TRADING_MODE": "live", **dict(__import__("os").environ)}
    result = subprocess.run(
        [sys.executable, str(ROOT / "run_bot.py"), "--once"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode != 0
    assert "SICHERHEITSSTOPP" in result.stderr or "SICHERHEITSSTOPP" in result.stdout
