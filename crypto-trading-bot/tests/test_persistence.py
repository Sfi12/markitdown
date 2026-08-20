from __future__ import annotations

from pathlib import Path

from bot.storage import Storage, TradeRecord
from bot.storage_migrate import SCHEMA_VERSION, migrate


def test_migration_adds_tradefill_columns(tmp_path: Path) -> None:
    db = tmp_path / "bot.db"
    # Create legacy schema manually
    import sqlite3

    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE trades (
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
        )
        """
    )
    conn.execute(
        """
        INSERT INTO trades (
            timestamp, side, price, amount_eur, amount_btc, fee_eur, reason,
            balance_eur_after, balance_btc_after
        ) VALUES ('2026-01-01T00:00:00+00:00', 'buy', 100.0, 10.0, 0.1, 0.06, 'test', 40.0, 0.1)
        """
    )
    conn.execute(
        """
        CREATE TABLE snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            price REAL NOT NULL,
            portfolio_value_eur REAL NOT NULL,
            cash_eur REAL NOT NULL,
            btc_amount REAL NOT NULL
        )
        """
    )
    conn.execute(
        """
        INSERT INTO snapshots (timestamp, price, portfolio_value_eur, cash_eur, btc_amount)
        VALUES ('2026-01-01T00:00:00+00:00', 100.0, 50.0, 40.0, 0.1)
        """
    )
    conn.commit()
    conn.close()

    steps = migrate(db)
    assert any("trades.add_column" in step for step in steps)

    storage = Storage(db)
    trades = storage.list_trades()
    assert len(trades) == 1
    trade = trades[0]
    assert trade.execution_price == 100.0
    assert trade.quantity == 0.1
    assert trade.gross_value == 10.0
    assert trade.fee == 0.06
    assert trade.net_value == 9.94
    # Unknown for legacy — not invented
    assert trade.requested_price is None
    assert trade.slippage is None
    assert trade.pnl is None
    assert trade.symbol is None

    snaps = storage.list_snapshots()
    assert snaps[0]["btc_price"] == 100.0
    assert snaps[0]["portfolio_value"] == 50.0
    assert snaps[0]["realized_pnl"] is None


def test_persist_full_tradefill(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "bot.db")
    storage.add_trade(
        TradeRecord(
            id=None,
            timestamp="2026-01-01T12:00:00+00:00",
            side="buy",
            reason="EMA20 above EMA50 and RSI above 50",
            balance_eur_after=40.0,
            balance_btc_after=0.0994,
            symbol="BTC-EUR",
            requested_price=100.0,
            execution_price=100.1,
            quantity=0.0994,
            gross_value=10.0,
            fee=0.06,
            slippage=0.1,
            net_value=9.94,
            pnl=0.0,
            price=100.1,
            amount_eur=10.0,
            amount_btc=0.0994,
            fee_eur=0.06,
        )
    )
    trade = storage.list_trades()[0]
    assert trade.symbol == "BTC-EUR"
    assert trade.requested_price == 100.0
    assert trade.execution_price == 100.1
    assert trade.slippage == 0.1
    assert trade.pnl == 0.0


def test_snapshot_persistence_with_pnl(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "bot.db")
    storage.add_snapshot(
        price=110.0,
        portfolio_value_eur=51.0,
        cash_eur=40.0,
        btc_amount=0.1,
        realized_pnl=1.0,
        unrealized_pnl=1.0,
        total_pnl=2.0,
        timestamp="2026-01-01T12:00:00+00:00",
    )
    snap = storage.list_snapshots()[0]
    assert snap["btc_price"] == 110.0
    assert snap["portfolio_value"] == 51.0
    assert snap["realized_pnl"] == 1.0
    assert snap["unrealized_pnl"] == 1.0
    assert snap["total_pnl"] == 2.0


def test_schema_version_recorded(tmp_path: Path) -> None:
    db = tmp_path / "bot.db"
    migrate(db)
    import sqlite3

    conn = sqlite3.connect(db)
    version = conn.execute(
        "SELECT value FROM schema_meta WHERE key='version'"
    ).fetchone()[0]
    conn.close()
    assert version == str(SCHEMA_VERSION)
