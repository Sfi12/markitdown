from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


INTERVALS: dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
}

PERIODS: dict[str, timedelta] = {
    "1W": timedelta(days=7),
    "1M": timedelta(days=30),
    "3M": timedelta(days=90),
    "6M": timedelta(days=180),
    "1Y": timedelta(days=365),
}


@dataclass(frozen=True)
class BacktestWindow:
    period: str
    interval: str
    granularity: int
    start: datetime
    end: datetime
    expected_bars: int

    @property
    def label(self) -> str:
        return f"{self.period} @ {self.interval}"


def resolve_window(
    period: str,
    interval: str,
    *,
    end: datetime | None = None,
) -> BacktestWindow:
    if period not in PERIODS:
        raise ValueError(f"Unsupported period: {period}. Allowed: {sorted(PERIODS)}")
    if interval not in INTERVALS:
        raise ValueError(f"Unsupported interval: {interval}. Allowed: {sorted(INTERVALS)}")

    end_ts = end or datetime.now(timezone.utc)
    if end_ts.tzinfo is None:
        end_ts = end_ts.replace(tzinfo=timezone.utc)
    start_ts = end_ts - PERIODS[period]
    granularity = INTERVALS[interval]
    expected = int(PERIODS[period].total_seconds() // granularity)
    return BacktestWindow(
        period=period,
        interval=interval,
        granularity=granularity,
        start=start_ts,
        end=end_ts,
        expected_bars=expected,
    )


def coverage_ratio(actual_bars: int, expected_bars: int) -> float:
    if expected_bars <= 0:
        return 0.0
    return actual_bars / expected_bars


def is_insufficient_coverage(actual_bars: int, expected_bars: int, min_ratio: float = 0.85) -> bool:
    """Require at least 85% of expected bars for the requested window."""
    return coverage_ratio(actual_bars, expected_bars) < min_ratio
