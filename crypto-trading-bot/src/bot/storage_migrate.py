"""SQLite schema migrations for paper-trading persistence."""

from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA_VERSION = 2


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}


def _add_column_if_missing(
    connection: sqlite3.Connection,
    table: str,
    column: str,
    definition: str,
) -> None:
    if column not in _columns(connection, table):
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def migrate(database_path: Path) -> list[str]:
    """
    Apply additive migrations. Never deletes tables or rows.

    Field mapping for legacy trades (schema v1 → v2):
      price       → execution_price
      amount_eur  → gross_value
      amount_btc  → quantity
      fee_eur     → fee
      net_value   ← amount_eur - fee_eur  (derivable from stored columns)
      symbol / requested_price / slippage / pnl ← NULL (unknown for legacy rows)

    Snapshots:
      price → also exposed as btc_price (column added; legacy `price` kept)
      realized_pnl / unrealized_pnl / total_pnl ← NULL for legacy rows
    """
    steps: list[str] = []
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS bot_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                cash_eur REAL NOT NULL,
                btc_amount REAL NOT NULL,
                entry_price REAL,
                in_position INTEGER NOT NULL,
                is_running INTEGER NOT NULL,
                last_price REAL,
                last_signal TEXT NOT NULL,
                last_update TEXT,
                total_trades INTEGER NOT NULL,
                realized_pnl_eur REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                side TEXT NOT NULL,
                price REAL NOT NULL,
                amount_eur REAL NOT NULL,
                amount_btc REAL NOT NULL,
                fee_eur REAL NOT NULL,
                reason TEXT NOT NULL,
                balance_eur_after REAL NOT NULL,
                balance_btc_after REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                level TEXT NOT NULL,
                message TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                price REAL NOT NULL,
                portfolio_value_eur REAL NOT NULL,
                cash_eur REAL NOT NULL,
                btc_amount REAL NOT NULL
            );
            """
        )
        steps.append("ensure_base_tables")

        # --- trades: TradeFill fields (additive) ---
        for column, definition in (
            ("symbol", "TEXT"),
            ("requested_price", "REAL"),
            ("execution_price", "REAL"),
            ("quantity", "REAL"),
            ("gross_value", "REAL"),
            ("fee", "REAL"),
            ("slippage", "REAL"),
            ("net_value", "REAL"),
            ("pnl", "REAL"),
        ):
            before = column in _columns(connection, "trades")
            _add_column_if_missing(connection, "trades", column, definition)
            if not before:
                steps.append(f"trades.add_column.{column}")

        # Backfill only from known legacy columns — no invented market data.
        connection.execute(
            """
            UPDATE trades
            SET execution_price = COALESCE(execution_price, price),
                quantity = COALESCE(quantity, amount_btc),
                gross_value = COALESCE(gross_value, amount_eur),
                fee = COALESCE(fee, fee_eur),
                net_value = COALESCE(net_value, amount_eur - fee_eur)
            WHERE execution_price IS NULL
               OR quantity IS NULL
               OR gross_value IS NULL
               OR fee IS NULL
               OR net_value IS NULL
            """
        )
        steps.append("trades.backfill_from_legacy")

        # --- snapshots: performance reconstruction fields ---
        for column, definition in (
            ("btc_price", "REAL"),
            ("portfolio_value", "REAL"),
            ("realized_pnl", "REAL"),
            ("unrealized_pnl", "REAL"),
            ("total_pnl", "REAL"),
        ):
            before = column in _columns(connection, "snapshots")
            _add_column_if_missing(connection, "snapshots", column, definition)
            if not before:
                steps.append(f"snapshots.add_column.{column}")

        connection.execute(
            """
            UPDATE snapshots
            SET btc_price = COALESCE(btc_price, price),
                portfolio_value = COALESCE(portfolio_value, portfolio_value_eur)
            WHERE btc_price IS NULL OR portfolio_value IS NULL
            """
        )
        steps.append("snapshots.backfill_from_legacy")

        connection.execute(
            "INSERT INTO schema_meta(key, value) VALUES('version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(SCHEMA_VERSION),),
        )
        steps.append(f"schema_meta.version={SCHEMA_VERSION}")
        connection.commit()
    finally:
        connection.close()
    return steps
