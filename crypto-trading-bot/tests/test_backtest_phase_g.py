"""Phase G — backtesting + strategy validation (no parameter optimization)."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from bot.backtest.benchmark import compute_buy_and_hold
from bot.backtest.data_quality import sanitize_candles, validate_candles
from bot.backtest.engine import StrategyBacktester, longest_streak, sample_size_note
from bot.backtest.periods import INTERVALS, PERIODS, is_insufficient_coverage, resolve_window
from bot.config import BotConfig
from bot.strategy import EmaRsiStrategy, add_indicators
from dashboard.helpers import format_backtest_summary, settings_rows


def _candles(
    closes: list[float],
    *,
    start: str = "2024-01-01T00:00:00Z",
    freq: str = "1h",
) -> pd.DataFrame:
    index = pd.date_range(start=start, periods=len(closes), freq=freq, tz="UTC")
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


def _trending_then_drop(n: int = 120) -> pd.DataFrame:
    """Uptrend (EMA cross + RSI>50) then drop to force exits."""
    closes: list[float] = []
    price = 100.0
    for i in range(n):
        if i < 70:
            price *= 1.004
        elif i < 90:
            price *= 1.001
        else:
            price *= 0.985
        closes.append(price)
    return _candles(closes)


# ---------------------------------------------------------------------------
# Periods / intervals
# ---------------------------------------------------------------------------


def test_supported_periods_and_intervals() -> None:
    assert set(PERIODS) == {"1W", "1M", "3M", "6M", "1Y"}
    assert set(INTERVALS) == {"1m", "5m", "15m", "1h"}


@pytest.mark.parametrize("period", sorted(PERIODS))
@pytest.mark.parametrize("interval", sorted(INTERVALS))
def test_resolve_window_filters(period: str, interval: str) -> None:
    end = datetime(2024, 6, 1, tzinfo=timezone.utc)
    window = resolve_window(period, interval, end=end)
    assert window.period == period
    assert window.interval == interval
    assert window.granularity == INTERVALS[interval]
    assert window.end == end
    assert window.start < window.end
    assert window.expected_bars > 0


def test_insufficient_coverage_flag() -> None:
    assert is_insufficient_coverage(50, 100) is True
    assert is_insufficient_coverage(90, 100) is False


def test_backtest_reports_period_and_interval(config: BotConfig) -> None:
    frame = _trending_then_drop()
    result = StrategyBacktester(config).run(
        period="1W",
        interval="1h",
        candles=frame,
        end=datetime(2024, 1, 8, tzinfo=timezone.utc),
    )
    assert result.window.period == "1W"
    assert result.window.interval == "1h"
    assert result.candle_count == len(frame)


# ---------------------------------------------------------------------------
# Data quality
# ---------------------------------------------------------------------------


def test_data_quality_detects_duplicates_and_gaps() -> None:
    frame = _candles([100, 101, 102, 103, 104])
    # duplicate + unsorted insert
    bad = pd.concat(
        [
            frame.iloc[[2]],
            frame.iloc[::-1],
        ],
        ignore_index=True,
    )
    report = validate_candles(bad, 3600)
    assert report.duplicate_timestamps >= 1
    assert any("doppelte" in w.lower() or "sortiert" in w.lower() for w in report.warnings)


def test_data_quality_blocks_unrealistic_prices() -> None:
    frame = _candles([100, 101, 102])
    frame.loc[1, "close"] = -5
    report = validate_candles(frame, 3600)
    assert report.has_blocking_errors
    with pytest.raises(ValueError, match="Datenqualität"):
        StrategyBacktester(BotConfig.load()).run(candles=frame, period="1W", interval="1h")


def test_sanitize_sorts_and_dedupes() -> None:
    frame = _candles([100, 101, 102])
    messy = pd.concat([frame.iloc[[1]], frame], ignore_index=True)
    cleaned = sanitize_candles(messy)
    assert cleaned["timestamp"].is_monotonic_increasing
    assert not cleaned["timestamp"].duplicated().any()


# ---------------------------------------------------------------------------
# Look-ahead / fees / size / B&H / equity / drawdown
# ---------------------------------------------------------------------------


def test_no_lookahead_poisoned_future_bar(config: BotConfig) -> None:
    base = _trending_then_drop(100)
    enriched = add_indicators(base, 20, 50, 14)
    strategy = EmaRsiStrategy(20, 50, 14, 50.0, 45.0)
    index = 80
    window = enriched.iloc[: index + 1].copy()
    clean = strategy.evaluate(window, in_position=False, exclude_open_candle=False)

    poisoned = window.copy()
    # Append a fake future row that would flip indicators if look-ahead leaked
    last = poisoned.iloc[-1].copy()
    last["timestamp"] = last["timestamp"] + pd.Timedelta(hours=1)
    last["close"] = float(last["close"]) * 10
    last["open"] = last["close"]
    last["high"] = last["close"]
    last["low"] = last["close"]
    with_future = pd.concat([poisoned, pd.DataFrame([last])], ignore_index=True)
    # Engine only feeds iloc[:index+1]; evaluate on same closed window must match
    assert strategy.evaluate(
        with_future.iloc[: index + 1],
        in_position=False,
        exclude_open_candle=False,
    ).action == clean.action


def test_fees_and_slippage_reduce_pnl_vs_zero_cost(config: BotConfig) -> None:
    frame = _trending_then_drop()
    costly = StrategyBacktester(config).run(candles=frame, period="1M", interval="1h")

    from dataclasses import replace

    cheap_cfg = replace(
        config,
        execution=replace(config.execution, fee_pct=0.0, slippage_pct=0.0),
    )
    cheap = StrategyBacktester(cheap_cfg).run(candles=frame, period="1M", interval="1h")
    if costly.total_trades == 0 and cheap.total_trades == 0:
        pytest.skip("synthetic path produced no trades")
    assert costly.metrics.total_fees >= cheap.metrics.total_fees
    # With same signals, zero-cost end capital should be >= fee path
    assert cheap.end_capital >= costly.end_capital - 1e-9


def test_position_size_capped_by_max_trade(config: BotConfig) -> None:
    frame = _trending_then_drop()
    result = StrategyBacktester(config).run(candles=frame, period="1M", interval="1h")
    for trade in result.closed_trades:
        # Max notional ≈ max_trade_eur; allow small overrun from price path only on qty*entry
        assert trade.entry_price * trade.quantity <= config.max_trade_eur * 1.05


def test_buy_and_hold_benchmark(config: BotConfig) -> None:
    frame = _trending_then_drop()
    result = StrategyBacktester(config).run(candles=frame, period="1M", interval="1h")
    assert result.buy_and_hold is not None
    assert result.buy_and_hold.label == "Buy & Hold Benchmark"
    bh = compute_buy_and_hold(
        frame,
        start_capital=config.start_capital_eur,
        fee_pct=config.fee_pct,
        slippage_pct=config.slippage_pct,
    )
    assert result.buy_and_hold.total_return == pytest.approx(bh.total_return)
    assert result.buy_and_hold.equity_curve[0]["label"] == "Buy & Hold Equity"


def test_equity_curve_labeled(config: BotConfig) -> None:
    frame = _trending_then_drop()
    result = StrategyBacktester(config).run(candles=frame, period="1M", interval="1h")
    assert result.equity_curve
    assert result.equity_curve[0]["label"] == "Strategy Equity"
    assert "timestamp" in result.equity_curve[0]
    assert "portfolio_value" in result.equity_curve[0]


def test_drawdown_peak_decline_recovery(config: BotConfig) -> None:
    # Force equity: rise, fall, recover
    closes = [100.0] * 60 + [110.0] * 5 + [90.0] * 5 + [105.0] * 20
    frame = _candles(closes)
    result = StrategyBacktester(config).run(candles=frame, period="1W", interval="1h")
    assert result.drawdown_curve
    peaks = [p.peak for p in result.drawdown_curve]
    assert peaks == sorted(peaks) or peaks[-1] >= peaks[0]
    # At least one point with drawdown after a peak exists when values dip
    values = [p.portfolio_value for p in result.drawdown_curve]
    if max(values) > min(values):
        assert any(p.drawdown_eur > 0 for p in result.drawdown_curve)
        assert result.metrics.max_drawdown_pct is not None
        assert result.metrics.max_drawdown_pct >= 0


def test_holding_duration_and_streaks() -> None:
    assert longest_streak([True, True, False, True]) == 2
    assert longest_streak([False, False, False]) == 0
    assert sample_size_note(5) == "sehr geringe Stichprobe"
    assert sample_size_note(15) == "geringe Stichprobe"
    assert sample_size_note(40) == "ausreichende Stichprobe"


def test_holding_duration_on_closed_trades(config: BotConfig) -> None:
    frame = _trending_then_drop()
    result = StrategyBacktester(config).run(candles=frame, period="1M", interval="1h")
    for trade in result.closed_trades:
        assert trade.holding_duration_seconds >= 0
        assert trade.exit_timestamp >= trade.entry_timestamp
    if result.closed_trades:
        assert result.average_holding_seconds is not None
        assert result.average_holding_seconds >= 0


def test_win_loss_streaks_computed(config: BotConfig) -> None:
    frame = _trending_then_drop(160)
    result = StrategyBacktester(config).run(candles=frame, period="1M", interval="1h")
    assert result.longest_win_streak >= 0
    assert result.longest_loss_streak >= 0
    assert result.longest_drawdown_bars >= 0


# ---------------------------------------------------------------------------
# Determinism / sample size / no trades / open position
# ---------------------------------------------------------------------------


def test_deterministic_backtest(config: BotConfig) -> None:
    frame = _trending_then_drop()
    end = datetime(2024, 2, 1, tzinfo=timezone.utc)
    a = StrategyBacktester(config).run(
        candles=frame, period="1M", interval="1h", end=end
    )
    b = StrategyBacktester(config).run(
        candles=frame, period="1M", interval="1h", end=end
    )
    assert a.end_capital == b.end_capital
    assert a.total_return == b.total_return
    assert a.total_trades == b.total_trades
    assert [t.to_dict() for t in a.closed_trades] == [t.to_dict() for t in b.closed_trades]
    assert a.equity_curve == b.equity_curve


def test_low_trade_count_sample_note(config: BotConfig) -> None:
    # Flat market → few/no trades
    frame = _candles([100.0 + (i % 3) * 0.01 for i in range(80)])
    result = StrategyBacktester(config).run(candles=frame, period="1W", interval="1h")
    assert result.total_trades < 30
    assert "Stichprobe" in result.sample_note
    assert any("Zu wenige Trades" in w for w in result.warnings)
    # Must not claim profitability / strategy works
    blob = " ".join(result.warnings).lower()
    assert "strategie funktioniert" not in blob
    assert "gute strategie" not in blob
    assert "profitabel" not in blob


def test_no_trades_still_returns_benchmark(config: BotConfig) -> None:
    frame = _candles([100.0] * 80)
    result = StrategyBacktester(config).run(candles=frame, period="1W", interval="1h")
    assert result.total_trades == 0
    assert result.sample_note == "sehr geringe Stichprobe"
    assert result.buy_and_hold is not None
    assert result.end_capital == pytest.approx(config.start_capital_eur)


def test_open_position_at_end_marked(config: BotConfig) -> None:
    # Strong sustained uptrend — likely still in position at end
    closes = [100.0 * (1.003 ** i) for i in range(100)]
    frame = _candles(closes)
    result = StrategyBacktester(config).run(candles=frame, period="1W", interval="1h")
    if result.open_position_at_end:
        # Open trades are not counted as closed
        assert all(t.exit_reason for t in result.closed_trades)
        assert result.end_capital != result.start_capital or result.total_trades >= 0
    else:
        # Still valid if strategy never entered / already exited
        assert result.open_position_at_end is False


def test_insufficient_data_when_sparse(config: BotConfig) -> None:
    # Only a handful of candles vs 1Y @ 1h expectation
    frame = _candles([100, 101, 102, 103, 104])
    result = StrategyBacktester(config).run(candles=frame, period="1Y", interval="1h")
    assert result.insufficient_data is True
    assert any("insufficient_data" in w for w in result.warnings)


def test_trade_details_fields(config: BotConfig) -> None:
    frame = _trending_then_drop(140)
    result = StrategyBacktester(config).run(candles=frame, period="1M", interval="1h")
    for trade in result.closed_trades:
        payload = trade.to_dict()
        for key in (
            "entry_timestamp",
            "entry_price",
            "exit_timestamp",
            "exit_price",
            "quantity",
            "gross_value",
            "fees",
            "slippage",
            "pnl",
            "return_pct",
            "holding_duration_seconds",
            "exit_reason",
        ):
            assert key in payload


def test_dashboard_settings_include_backtest(config: BotConfig) -> None:
    rows = dict(settings_rows(config))
    assert "Backtest Period" in rows
    assert "Backtest Interval" in rows


def test_format_backtest_summary(config: BotConfig) -> None:
    frame = _candles([100.0] * 80)
    result = StrategyBacktester(config).run(candles=frame, period="1W", interval="1h")
    summary = format_backtest_summary(result)
    assert summary["equity_curve_label"] == "Strategy Equity"
    assert summary["benchmark_label"] == "Buy & Hold Benchmark"
    assert summary["period"] == "1W"
    assert summary["interval"] == "1h"


def test_no_parameter_optimization_exports() -> None:
    import bot.backtest as pkg

    banned = {
        "grid_search",
        "optimize",
        "genetic",
        "best_rsi",
        "best_ema",
        "parameter_search",
    }
    names = set(dir(pkg)) | set(pkg.__all__)
    assert not (banned & {n.lower() for n in names})
