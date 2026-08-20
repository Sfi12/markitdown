from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bot.storage_migrate import migrate


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class TradeRecord:
    """Persisted trade aligned with TradeFill (+ legacy compatibility fields)."""

    id: int | None
    timestamp: str
    side: str
    reason: str
    balance_eur_after: float
    balance_btc_after: float
    # TradeFill fields
    symbol: str | None = None
    requested_price: float | None = None
    execution_price: float | None = None
    quantity: float | None = None
    gross_value: float | None = None
    fee: float | None = None
    slippage: float | None = None
    net_value: float | None = None
    pnl: float | None = None
    # Legacy columns (kept for backward compatibility)
    price: float | None = None
    amount_eur: float | None = None
    amount_btc: float | None = None
    fee_eur: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> TradeRecord:
        keys = set(row.keys())

        def get_float(name: str) -> float | None:
            if name not in keys or row[name] is None:
                return None
            return float(row[name])

        execution_price = get_float("execution_price")
        if execution_price is None:
            execution_price = get_float("price")

        quantity = get_float("quantity")
        if quantity is None:
            quantity = get_float("amount_btc")

        gross_value = get_float("gross_value")
        if gross_value is None:
            gross_value = get_float("amount_eur")

        fee = get_float("fee")
        if fee is None:
            fee = get_float("fee_eur")

        return cls(
            id=int(row["id"]) if row["id"] is not None else None,
            timestamp=row["timestamp"],
            side=row["side"],
            reason=row["reason"],
            balance_eur_after=float(row["balance_eur_after"]),
            balance_btc_after=float(row["balance_btc_after"]),
            symbol=row["symbol"] if "symbol" in keys else None,
            requested_price=get_float("requested_price"),
            execution_price=execution_price,
            quantity=quantity,
            gross_value=gross_value,
            fee=fee,
            slippage=get_float("slippage"),
            net_value=get_float("net_value"),
            pnl=get_float("pnl"),
            price=get_float("price"),
            amount_eur=get_float("amount_eur"),
            amount_btc=get_float("amount_btc"),
            fee_eur=get_float("fee_eur"),
        )


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
        migrate(self.database_path)

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
        execution_price = trade.execution_price if trade.execution_price is not None else trade.price
        quantity = trade.quantity if trade.quantity is not None else trade.amount_btc
        gross_value = trade.gross_value if trade.gross_value is not None else trade.amount_eur
        fee = trade.fee if trade.fee is not None else trade.fee_eur
        if execution_price is None or quantity is None or gross_value is None or fee is None:
            raise ValueError("TradeRecord missing required price/quantity/gross/fee fields")

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO trades (
                    timestamp, side, price, amount_eur, amount_btc, fee_eur, reason,
                    balance_eur_after, balance_btc_after,
                    symbol, requested_price, execution_price, quantity, gross_value,
                    fee, slippage, net_value, pnl
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trade.timestamp,
                    trade.side,
                    execution_price,
                    gross_value,
                    quantity,
                    fee,
                    trade.reason,
                    trade.balance_eur_after,
                    trade.balance_btc_after,
                    trade.symbol,
                    trade.requested_price,
                    execution_price,
                    quantity,
                    gross_value,
                    fee,
                    trade.slippage,
                    trade.net_value,
                    trade.pnl,
                ),
            )

    def list_trades(self, limit: int = 100) -> list[TradeRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM trades ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [TradeRecord.from_row(row) for row in rows]

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
        realized_pnl: float | None = None,
        unrealized_pnl: float | None = None,
        total_pnl: float | None = None,
        timestamp: str | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO snapshots (
                    timestamp, price, portfolio_value_eur, cash_eur, btc_amount,
                    btc_price, portfolio_value, realized_pnl, unrealized_pnl, total_pnl
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp or utc_now().isoformat(),
                    price,
                    portfolio_value_eur,
                    cash_eur,
                    btc_amount,
                    price,
                    portfolio_value_eur,
                    realized_pnl,
                    unrealized_pnl,
                    total_pnl,
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
            "snapshots": self.list_snapshots(limit=1000),
        }
        return json.dumps(payload, indent=2, ensure_ascii=False)
