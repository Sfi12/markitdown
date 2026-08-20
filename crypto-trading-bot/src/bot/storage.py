from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class TradeRecord:
    id: int | None
    timestamp: str
    side: str
    price: float
    amount_eur: float
    amount_btc: float
    fee_eur: float
    reason: str
    balance_eur_after: float
    balance_btc_after: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BotState:
    cash_eur: float
    btc_amount: float
    entry_price: float | None
    in_position: bool
    is_running: bool
    last_price: float | None
    last_signal: str
    last_update: str | None
    total_trades: int
    realized_pnl_eur: float


class Storage:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
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

    def ensure_state(self, start_capital_eur: float) -> BotState:
        state = self.get_state()
        if state is not None:
            return state

        initial = BotState(
            cash_eur=start_capital_eur,
            btc_amount=0.0,
            entry_price=None,
            in_position=False,
            is_running=False,
            last_price=None,
            last_signal="Initialisiert",
            last_update=None,
            total_trades=0,
            realized_pnl_eur=0.0,
        )
        self.save_state(initial)
        return initial

    def get_state(self) -> BotState | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM bot_state WHERE id = 1").fetchone()
        if row is None:
            return None
        return BotState(
            cash_eur=float(row["cash_eur"]),
            btc_amount=float(row["btc_amount"]),
            entry_price=row["entry_price"],
            in_position=bool(row["in_position"]),
            is_running=bool(row["is_running"]),
            last_price=row["last_price"],
            last_signal=row["last_signal"],
            last_update=row["last_update"],
            total_trades=int(row["total_trades"]),
            realized_pnl_eur=float(row["realized_pnl_eur"]),
        )

    def save_state(self, state: BotState) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO bot_state (
                    id, cash_eur, btc_amount, entry_price, in_position, is_running,
                    last_price, last_signal, last_update, total_trades, realized_pnl_eur
                ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    cash_eur = excluded.cash_eur,
                    btc_amount = excluded.btc_amount,
                    entry_price = excluded.entry_price,
                    in_position = excluded.in_position,
                    is_running = excluded.is_running,
                    last_price = excluded.last_price,
                    last_signal = excluded.last_signal,
                    last_update = excluded.last_update,
                    total_trades = excluded.total_trades,
                    realized_pnl_eur = excluded.realized_pnl_eur
                """,
                (
                    state.cash_eur,
                    state.btc_amount,
                    state.entry_price,
                    int(state.in_position),
                    int(state.is_running),
                    state.last_price,
                    state.last_signal,
                    state.last_update,
                    state.total_trades,
                    state.realized_pnl_eur,
                ),
            )

    def add_trade(self, trade: TradeRecord) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO trades (
                    timestamp, side, price, amount_eur, amount_btc, fee_eur, reason,
                    balance_eur_after, balance_btc_after
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trade.timestamp,
                    trade.side,
                    trade.price,
                    trade.amount_eur,
                    trade.amount_btc,
                    trade.fee_eur,
                    trade.reason,
                    trade.balance_eur_after,
                    trade.balance_btc_after,
                ),
            )

    def list_trades(self, limit: int = 100) -> list[TradeRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM trades ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            TradeRecord(
                id=int(row["id"]),
                timestamp=row["timestamp"],
                side=row["side"],
                price=float(row["price"]),
                amount_eur=float(row["amount_eur"]),
                amount_btc=float(row["amount_btc"]),
                fee_eur=float(row["fee_eur"]),
                reason=row["reason"],
                balance_eur_after=float(row["balance_eur_after"]),
                balance_btc_after=float(row["balance_btc_after"]),
            )
            for row in rows
        ]

    def add_log(self, level: str, message: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO logs (timestamp, level, message) VALUES (?, ?, ?)",
                (utc_now().isoformat(), level, message),
            )

    def list_logs(self, limit: int = 100) -> list[dict[str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT timestamp, level, message FROM logs ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "timestamp": row["timestamp"],
                "level": row["level"],
                "message": row["message"],
            }
            for row in rows
        ]

    def add_snapshot(
        self,
        price: float,
        portfolio_value_eur: float,
        cash_eur: float,
        btc_amount: float,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO snapshots (timestamp, price, portfolio_value_eur, cash_eur, btc_amount)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    utc_now().isoformat(),
                    price,
                    portfolio_value_eur,
                    cash_eur,
                    btc_amount,
                ),
            )

    def list_snapshots(self, limit: int = 500) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM snapshots ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def reset(self, start_capital_eur: float) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM trades")
            connection.execute("DELETE FROM logs")
            connection.execute("DELETE FROM snapshots")
            connection.execute("DELETE FROM bot_state")
        self.ensure_state(start_capital_eur)
        self.add_log("info", f"Bot zurückgesetzt mit {start_capital_eur:.2f} EUR Startkapital")

    def export_json(self) -> str:
        state = self.get_state()
        payload = {
            "state": asdict(state) if state else None,
            "trades": [trade.to_dict() for trade in self.list_trades(limit=1000)],
            "logs": self.list_logs(limit=200),
        }
        return json.dumps(payload, indent=2, ensure_ascii=False)
