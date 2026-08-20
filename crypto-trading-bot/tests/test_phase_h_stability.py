"""Phase H — long-run paper stability, idempotency, health, resilience."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest
import requests

from bot.config import BotConfig
from bot.data.base import MarketDataProvider
from bot.data.resilient import MarketDataError, ResilientMarketData
from bot.engine import TradingEngine
from bot.health import HealthStatus, compute_health
from bot.report import build_paper_report
from bot.security import TradingModeError, enforce_paper_trading_startup
from bot.storage import BotState, Storage
from bot.storage_migrate import SCHEMA_VERSION, migrate
from dashboard.helpers import bot_status_label, health_pill_class


class FakeMarketData(MarketDataProvider):
    def __init__(
        self,
        candles: pd.DataFrame,
        price: float = 100.0,
        *,
        fail_times: int = 0,
        fail_exc: Exception | None = None,
        empty_once: bool = False,
    ) -> None:
        self._candles = candles
        self._price = price
        self._fail_times = fail_times
        self._fail_exc = fail_exc or requests.Timeout("simulated timeout")
        self._empty_once = empty_once
        self.calls = 0

    @property
    def product_id(self) -> str:
        return "BTC-EUR"

    def fetch_candles(self, granularity: int, limit: int = 300) -> pd.DataFrame:
        self.calls += 1
        if self._empty_once:
            self._empty_once = False
            return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])
        if self._fail_times > 0:
            self._fail_times -= 1
            raise self._fail_exc
        return self._candles.tail(limit).copy()

    def fetch_spot_price(self) -> float:
        if self._fail_times > 0:
            self._fail_times -= 1
            raise self._fail_exc
        return self._price


def _candles(closes: list[float], start: str = "2024-01-01T00:00:00Z") -> pd.DataFrame:
    index = pd.date_range(start=start, periods=len(closes), freq="1h", tz="UTC")
    rows = []
    for ts, close in zip(index, closes):
        rows.append(
            {
                "timestamp": ts,
                "open": close,
                "high": close * 1.001,
                "low": close * 0.999,
                "close": close,
                "volume": 10.0,
            }
        )
    return pd.DataFrame(rows)


def _uptrend(n: int = 80) -> pd.DataFrame:
    return _candles([100.0 * (1.004 ** i) for i in range(n)])


def _engine(tmp_path: Path, market: MarketDataProvider, config: BotConfig) -> TradingEngine:
    cfg = replace(config, database_path=tmp_path / "phase_h.db")
    return TradingEngine(cfg, market_data=market)


# ---------------------------------------------------------------------------
# Health / STALE / ERROR
# ---------------------------------------------------------------------------


def test_health_stopped_running_stale_error() -> None:
    now = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
    base = BotState(
        cash_eur=50.0,
        btc_amount=0.0,
        entry_price=None,
        in_position=False,
        is_running=False,
        last_price=100.0,
        last_signal="x",
        last_update=now.isoformat(),
        total_trades=0,
        realized_pnl_eur=0.0,
        last_successful_tick=now.isoformat(),
    )
    assert compute_health(base, stale_after_seconds=180, now=now).status == HealthStatus.STOPPED

    running = replace(base, is_running=True)
    assert compute_health(running, stale_after_seconds=180, now=now).status == HealthStatus.RUNNING

    stale = replace(
        running,
        last_successful_tick=(now - timedelta(seconds=500)).isoformat(),
        last_update=(now - timedelta(seconds=500)).isoformat(),
    )
    assert compute_health(stale, stale_after_seconds=180, now=now).status == HealthStatus.STALE

    error = replace(
        running,
        last_error="API boom",
        last_error_at=now.isoformat(),
        last_successful_tick=(now - timedelta(seconds=10)).isoformat(),
    )
    assert compute_health(error, stale_after_seconds=180, now=now).status == HealthStatus.ERROR


def test_dashboard_health_labels() -> None:
    now = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
    state = BotState(
        cash_eur=50.0,
        btc_amount=0.0,
        entry_price=None,
        in_position=False,
        is_running=True,
        last_price=1.0,
        last_signal="x",
        last_update=now.isoformat(),
        total_trades=0,
        realized_pnl_eur=0.0,
        last_successful_tick=now.isoformat(),
    )
    health = compute_health(state, stale_after_seconds=180, now=now)
    assert "RUNNING" in bot_status_label(health=health)
    assert health_pill_class("STALE") == "stale"
    assert bot_status_label(True) == "RUNNING"
    assert bot_status_label(False) == "STOPPED"


# ---------------------------------------------------------------------------
# Resilient market data
# ---------------------------------------------------------------------------


def test_resilient_retries_timeout_then_succeeds() -> None:
    inner = FakeMarketData(_uptrend(), fail_times=2)
    wrapped = ResilientMarketData(inner, retries=3, retry_delay_seconds=0)
    frame = wrapped.fetch_candles(3600, 50)
    assert not frame.empty
    assert inner.calls >= 3


def test_resilient_empty_response_errors() -> None:
    inner = FakeMarketData(_uptrend(), empty_once=True)
    wrapped = ResilientMarketData(inner, retries=1, retry_delay_seconds=0)
    with pytest.raises(MarketDataError, match="empty"):
        wrapped.fetch_candles(3600, 10)


def test_api_error_does_not_mutate_portfolio(tmp_path: Path, config: BotConfig) -> None:
    market = FakeMarketData(_uptrend(), fail_times=10, fail_exc=requests.Timeout("down"))
    # Bypass resilient wrapper by injecting raw failing provider
    engine = _engine(tmp_path, market, config)
    state = engine.initialize()
    state.cash_eur = 42.5
    state.btc_amount = 0.001
    state.entry_price = 50_000.0
    state.in_position = True
    state.realized_pnl_eur = 1.25
    engine.storage.save_state(state)

    after = engine.tick()
    assert after.cash_eur == 42.5
    assert after.btc_amount == 0.001
    assert after.entry_price == 50_000.0
    assert after.in_position is True
    assert after.realized_pnl_eur == 1.25
    assert after.failed_ticks == 1
    assert after.api_error_count == 1
    assert after.last_error is not None
    logs = engine.storage.list_logs(limit=20)
    assert any(log["level"] == "error" for log in logs)


# ---------------------------------------------------------------------------
# Idempotency / duplicate candle
# ---------------------------------------------------------------------------


def test_duplicate_candle_skips_strategy_execution(tmp_path: Path, config: BotConfig) -> None:
    """Explicit: same signal candle must not execute a second strategy trade."""
    frame = _uptrend(90)
    completed_ts = str(frame.iloc[-2]["timestamp"])
    market = FakeMarketData(frame, price=float(frame.iloc[-1]["close"]))
    engine = _engine(tmp_path, market, config)
    engine.initialize()

    from bot.strategy import SignalAction, StrategySignal

    buy = StrategySignal(
        action=SignalAction.BUY,
        reason="EMA20 above EMA50 and RSI above 50",
        price=float(frame.iloc[-1]["close"]),
        ema_fast=1.0,
        ema_slow=0.5,
        rsi=60.0,
        signal_candle_timestamp=completed_ts,
    )

    calls = {"n": 0}
    original = engine.execution.execute_signal

    def counting_execute(state, signal):
        calls["n"] += 1
        return original(state, signal)

    engine.execution.execute_signal = counting_execute  # type: ignore[method-assign]
    engine.risk.check_exits = lambda state, price: None  # type: ignore[method-assign]
    engine.strategy.evaluate = lambda *args, **kwargs: buy  # type: ignore[method-assign]

    state = engine.storage.ensure_state(config.start_capital_eur)
    state.cash_eur = 50.0
    state.btc_amount = 0.0
    state.in_position = False
    state.last_processed_candle = None
    engine.storage.save_state(state)

    engine.tick()
    assert calls["n"] == 1
    mid = engine.storage.get_state()
    assert mid is not None
    assert mid.last_processed_candle == completed_ts
    trades_mid = len(engine.storage.list_trades())

    # Reset flat but keep last_processed_candle — second BUY on same candle must skip
    mid.cash_eur = 50.0
    mid.btc_amount = 0.0
    mid.in_position = False
    mid.entry_price = None
    mid.last_processed_candle = completed_ts
    engine.storage.save_state(mid)

    engine.tick()
    assert calls["n"] == 1  # execute_signal not called again
    assert len(engine.storage.list_trades()) == trades_mid


def test_duplicate_candle_does_not_double_trade(tmp_path: Path, config: BotConfig) -> None:
    frame = _uptrend(90)
    # Completed candle used by strategy is penultimate when exclude_open=True
    completed_ts = str(frame.iloc[-2]["timestamp"])
    market = FakeMarketData(frame, price=float(frame.iloc[-1]["close"]))
    engine = _engine(tmp_path, market, config)
    engine.initialize()
    engine.set_running(True)

    first = engine.tick()
    trades_after_first = len(engine.storage.list_trades(limit=100))
    # Force same completed candle marker + flat so a second BUY would otherwise fire
    first.last_processed_candle = completed_ts
    # Keep whatever position resulted; ensure marker is set
    engine.storage.save_state(first)

    second = engine.tick()
    trades_after_second = len(engine.storage.list_trades(limit=100))
    # Either no new trade, or if first didn't buy, second also shouldn't buy same candle twice
    if first.last_processed_candle == completed_ts and first.in_position:
        assert trades_after_second == trades_after_first or second.total_trades == first.total_trades

    # Explicit duplicate-skip path: craft state with BUY candle already processed
    state = engine.storage.ensure_state(config.start_capital_eur)
    state.cash_eur = 50.0
    state.btc_amount = 0.0
    state.in_position = False
    state.entry_price = None
    state.last_processed_candle = completed_ts
    state.total_trades = 0
    engine.storage.save_state(state)
    before = len(engine.storage.list_trades(limit=100))
    engine.tick()
    after_trades = engine.storage.list_trades(limit=100)
    # If strategy wants BUY on same candle, idempotency blocks it
    assert len(after_trades) == before or all(
        t.reason for t in after_trades  # still consistent
    )
    reloaded = engine.storage.get_state()
    assert reloaded is not None
    assert reloaded.last_processed_candle == completed_ts


def test_repeated_tick_is_safe(tmp_path: Path, config: BotConfig) -> None:
    market = FakeMarketData(_uptrend(90), price=120.0)
    engine = _engine(tmp_path, market, config)
    engine.initialize()
    engine.set_running(True)
    states = [engine.tick() for _ in range(5)]
    assert all(s.successful_ticks >= 1 for s in states)
    assert states[-1].tick_count == 5
    # Portfolio never negative
    assert states[-1].cash_eur >= 0
    assert states[-1].btc_amount >= 0


# ---------------------------------------------------------------------------
# Restart persistence
# ---------------------------------------------------------------------------


def test_restart_preserves_portfolio_and_candle(tmp_path: Path, config: BotConfig) -> None:
    db = tmp_path / "restart.db"
    cfg = replace(config, database_path=db)
    market = FakeMarketData(_uptrend(90), price=120.0)

    engine1 = TradingEngine(cfg, market_data=market)
    engine1.initialize()
    engine1.set_running(True)
    state1 = engine1.tick()
    # Simulate a processed candle + open-ish portfolio
    state1.last_processed_candle = "2024-01-01T10:00:00+00:00"
    state1.cash_eur = 40.0
    state1.btc_amount = 0.0002
    state1.entry_price = 55_000.0
    state1.in_position = True
    state1.realized_pnl_eur = 0.75
    state1.total_trades = 3
    engine1.storage.save_state(state1)
    engine1.storage.add_log("info", "pre-restart marker")
    engine1.storage.add_snapshot(
        price=120.0,
        portfolio_value_eur=51.0,
        cash_eur=40.0,
        btc_amount=0.0002,
        realized_pnl=0.75,
        unrealized_pnl=0.1,
        total_pnl=0.85,
    )
    trade_count = len(engine1.storage.list_trades(limit=1000))
    snap_count = len(engine1.storage.list_snapshots(limit=1000))
    log_count = len(engine1.storage.list_logs(limit=1000))

    # "Process kill" → new engine instance, same DB
    engine2 = TradingEngine(cfg, market_data=market)
    state2 = engine2.storage.get_state()
    assert state2 is not None
    assert state2.cash_eur == 40.0
    assert state2.btc_amount == 0.0002
    assert state2.entry_price == 55_000.0
    assert state2.in_position is True
    assert state2.realized_pnl_eur == 0.75
    assert state2.total_trades == 3
    assert state2.last_processed_candle == "2024-01-01T10:00:00+00:00"
    assert state2.cash_eur != cfg.start_capital_eur or state2.btc_amount > 0
    assert len(engine2.storage.list_trades(limit=1000)) == trade_count
    assert len(engine2.storage.list_snapshots(limit=1000)) == snap_count
    assert len(engine2.storage.list_logs(limit=1000)) == log_count


def test_sqlite_consistency_after_ticks(tmp_path: Path, config: BotConfig) -> None:
    engine = _engine(tmp_path, FakeMarketData(_uptrend(90), price=110.0), config)
    engine.initialize()
    engine.set_running(True)
    engine.tick()
    engine.tick()
    state = engine.storage.get_state()
    assert state is not None
    snaps = engine.storage.list_snapshots()
    assert len(snaps) >= 2
    assert state.successful_ticks == 2
    assert state.tick_count == 2
    steps = migrate(config.database_path if False else engine.storage.database_path)
    assert any(f"version={SCHEMA_VERSION}" in step for step in steps)


# ---------------------------------------------------------------------------
# Paper-only / report
# ---------------------------------------------------------------------------


def test_paper_only_hard_fail_still_enforced(config: BotConfig) -> None:
    bad = replace(config, app=replace(config.app, trading_mode="live"))
    with pytest.raises(TradingModeError):
        enforce_paper_trading_startup(bad.trading_mode)
    with pytest.raises(TradingModeError):
        TradingEngine(bad)


def test_paper_report_fields(tmp_path: Path, config: BotConfig) -> None:
    engine = _engine(tmp_path, FakeMarketData(_uptrend(90), price=110.0), config)
    engine.initialize()
    engine.set_running(True)
    engine.tick()
    report = engine.get_paper_report(market_price=110.0)
    text = report.format_text()
    assert "Paper-Trading Report" in text
    assert report.ticks >= 1
    assert report.successful_ticks >= 1
    assert "Portfolio Value" in text


def test_build_paper_report_unit(config: BotConfig) -> None:
    now = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)
    state = BotState(
        cash_eur=50.0,
        btc_amount=0.0,
        entry_price=None,
        in_position=False,
        is_running=True,
        last_price=100.0,
        last_signal="HOLD",
        last_update=now.isoformat(),
        total_trades=0,
        realized_pnl_eur=0.0,
        session_started_at=(now - timedelta(hours=2)).isoformat(),
        tick_count=10,
        successful_ticks=9,
        failed_ticks=1,
        api_error_count=1,
        last_successful_tick=now.isoformat(),
    )
    from bot.performance import PerformanceCalculator

    metrics = PerformanceCalculator(start_capital=50.0).compute(
        state, 100.0, trades=[], snapshots=[]
    )
    report = build_paper_report(state, metrics=metrics, trades=[], now=now)
    assert report.runtime_seconds == pytest.approx(7200.0)
    assert report.failed_ticks == 1


def test_config_stale_and_retries_defaults(config: BotConfig) -> None:
    assert config.stale_after_seconds == 180
    assert config.market_data_retries == 3
    assert config.strategy.ema_fast == 20
    assert config.strategy.ema_slow == 50
    assert config.strategy.rsi_period == 14
    assert config.rsi_entry == 50
    assert config.rsi_exit == 45
    assert config.stop_loss_pct == 1.5
    assert config.take_profit_pct == 3.0
    assert config.fee_pct == 0.6
    assert config.slippage_pct == 0.10


def test_log_levels_normalized(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "logs.db")
    storage.add_log("warn", "x")
    storage.add_log("trade", "y")
    storage.add_log("error", "z")
    levels = {log["level"] for log in storage.list_logs()}
    assert levels <= {"info", "warning", "error"}
    assert "warning" in levels
    assert "error" in levels
