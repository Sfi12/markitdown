"""Bot health / watchdog status for paper long-run monitoring."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from bot.storage import BotState


class HealthStatus(str, Enum):
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    STALE = "STALE"
    ERROR = "ERROR"


STATUS_EMOJI = {
    HealthStatus.RUNNING: "🟢",
    HealthStatus.STALE: "🟡",
    HealthStatus.ERROR: "🔴",
    HealthStatus.STOPPED: "⚪",
}


@dataclass(frozen=True)
class HealthSnapshot:
    status: HealthStatus
    label: str
    emoji: str
    last_successful_tick: str | None
    last_error: str | None
    stale_after_seconds: int
    seconds_since_success: float | None

    @property
    def display(self) -> str:
        return f"{self.emoji} {self.label}"


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def compute_health(
    state: BotState,
    *,
    stale_after_seconds: int = 180,
    now: datetime | None = None,
) -> HealthSnapshot:
    """
    Derive cockpit health from persisted state.

    Priority while flagged running:
      1. ERROR  — last tick failed more recently than last success
      2. STALE  — no successful tick within stale_after_seconds
      3. RUNNING
    When is_running is False → STOPPED.
    """
    now_ts = now or datetime.now(timezone.utc)
    success_ts = state.last_successful_tick or state.last_update
    success_dt = _parse_ts(success_ts)
    error_dt = _parse_ts(state.last_error_at)

    seconds_since: float | None = None
    if success_dt is not None:
        seconds_since = max(0.0, (now_ts - success_dt).total_seconds())

    if not state.is_running:
        status = HealthStatus.STOPPED
    elif state.last_error and (
        success_dt is None or (error_dt is not None and error_dt > success_dt)
    ):
        status = HealthStatus.ERROR
    elif success_dt is None or (
        seconds_since is not None and seconds_since > stale_after_seconds
    ):
        status = HealthStatus.STALE
    else:
        status = HealthStatus.RUNNING

    return HealthSnapshot(
        status=status,
        label=status.value,
        emoji=STATUS_EMOJI[status],
        last_successful_tick=success_ts,
        last_error=state.last_error,
        stale_after_seconds=stale_after_seconds,
        seconds_since_success=seconds_since,
    )
