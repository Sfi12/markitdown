from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class DataQualityReport:
    ok: bool
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    candle_count: int = 0
    duplicate_timestamps: int = 0
    missing_bars_estimate: int = 0

    @property
    def has_blocking_errors(self) -> bool:
        return bool(self.errors)


def validate_candles(frame: pd.DataFrame, granularity_seconds: int) -> DataQualityReport:
    report = DataQualityReport(ok=True, candle_count=len(frame))
    if frame.empty:
        report.ok = False
        report.errors.append("Keine Kerzen vorhanden.")
        return report

    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required - set(frame.columns)
    if missing:
        report.ok = False
        report.errors.append(f"Fehlende Spalten: {sorted(missing)}")
        return report

    ts = pd.to_datetime(frame["timestamp"], utc=True)
    if not ts.is_monotonic_increasing:
        report.warnings.append("Zeitstempel waren nicht sortiert — werden sortiert.")
    duplicates = int(ts.duplicated().sum())
    report.duplicate_timestamps = duplicates
    if duplicates:
        report.warnings.append(f"{duplicates} doppelte Zeitstempel gefunden — werden entfernt.")

    for column in ("open", "high", "low", "close", "volume"):
        series = pd.to_numeric(frame[column], errors="coerce")
        if series.isna().any():
            report.ok = False
            report.errors.append(f"Ungültige/NaN-Werte in Spalte {column}.")
        if (series <= 0).any() and column != "volume":
            report.ok = False
            report.errors.append(f"Unrealistische Preiswerte (<= 0) in {column}.")
        if column == "volume" and (series < 0).any():
            report.ok = False
            report.errors.append("Negatives Volumen gefunden.")

    if (frame["high"] < frame["low"]).any():
        report.ok = False
        report.errors.append("High < Low in mindestens einer Kerze.")

    # Gap estimate after sort/dedupe
    cleaned = (
        frame.assign(timestamp=ts)
        .drop_duplicates(subset=["timestamp"], keep="last")
        .sort_values("timestamp")
    )
    if len(cleaned) >= 2:
        deltas = cleaned["timestamp"].diff().dt.total_seconds().iloc[1:]
        expected = float(granularity_seconds)
        large_gaps = deltas[deltas > expected * 1.5]
        if not large_gaps.empty:
            # approximate missing bars
            missing_bars = int(((large_gaps / expected) - 1).clip(lower=0).sum())
            report.missing_bars_estimate = missing_bars
            report.warnings.append(
                f"Datenlücken erkannt (~{missing_bars} fehlende Kerzen geschätzt)."
            )

    if report.errors:
        report.ok = False
    return report


def sanitize_candles(frame: pd.DataFrame) -> pd.DataFrame:
    cleaned = frame.copy()
    cleaned["timestamp"] = pd.to_datetime(cleaned["timestamp"], utc=True)
    cleaned = cleaned.drop_duplicates(subset=["timestamp"], keep="last")
    cleaned = cleaned.sort_values("timestamp").reset_index(drop=True)
    for column in ("open", "high", "low", "close", "volume"):
        cleaned[column] = cleaned[column].astype(float)
    return cleaned
