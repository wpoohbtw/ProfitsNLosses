from __future__ import annotations

from contextlib import closing
import sqlite3
from pathlib import Path
from typing import Any

DB_DIR = Path(__file__).resolve().parents[1] / "data"
DB_PATH = DB_DIR / "profits_n_losses.sqlite3"


EXCHANGE_SEED = [
    ("binance", "Binance", 12500.0),
    ("bybit", "ByBit", 8300.0),
    ("mexc", "Mexc", 4550.0),
    ("bingx", "BingX", 6200.0),
    ("gate", "Gate", 5400.0),
    ("bitget", "Bitget", 3700.0),
    ("kucoin", "Kucoin", 4900.0),
    ("hyperliquid", "HyperLiquid", 9200.0),
    ("aster", "Aster", 3100.0),
    ("okx", "OKX", 5000.0),
]


def get_connection() -> sqlite3.Connection:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database() -> None:
    with closing(get_connection()) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS exchanges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                balance_usdt REAL NOT NULL DEFAULT 0,
                start_balance_usdt REAL NOT NULL DEFAULT 0,
                pnl_reset_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS daily_profit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                profit_date TEXT NOT NULL UNIQUE,
                pnl_usdt REAL NOT NULL DEFAULT 0,
                source TEXT NOT NULL DEFAULT 'manual'
            );

            CREATE TABLE IF NOT EXISTS balance_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exchange_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                balance_before_usdt REAL,
                balance_after_usdt REAL NOT NULL,
                start_balance_before_usdt REAL,
                start_balance_after_usdt REAL NOT NULL,
                pnl_after_usdt REAL NOT NULL,
                note TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (exchange_id) REFERENCES exchanges(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exchange_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL CHECK (side IN ('long', 'short')),
                status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed', 'deleted')),
                entry_price REAL NOT NULL,
                exit_price REAL,
                size_value REAL NOT NULL,
                size_unit TEXT NOT NULL CHECK (size_unit IN ('USDT', 'TOKEN')),
                margin_usdt REAL NOT NULL,
                realized_pnl_usdt REAL NOT NULL DEFAULT 0,
                opened_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                closed_at TEXT,
                deleted_at TEXT,
                FOREIGN KEY (exchange_id) REFERENCES exchanges(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS funding_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id INTEGER NOT NULL,
                exchange_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                funding_time INTEGER NOT NULL,
                funding_rate REAL NOT NULL,
                notional_usdt REAL NOT NULL,
                side TEXT NOT NULL,
                amount_usdt REAL NOT NULL,
                source TEXT NOT NULL DEFAULT 'current_fallback',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(trade_id, funding_time),
                FOREIGN KEY (trade_id) REFERENCES trades(id) ON DELETE CASCADE,
                FOREIGN KEY (exchange_id) REFERENCES exchanges(id) ON DELETE CASCADE
            );
            """
        )
        _seed_exchanges(connection)
        _migrate_trades_schema(connection)
        _backfill_balance_events(connection)
        _rebuild_daily_profit_from_trade_events(connection)
        connection.commit()


def _seed_exchanges(connection: sqlite3.Connection) -> None:
    allowed_slugs = [slug for slug, _, _ in EXCHANGE_SEED]
    placeholders = ",".join("?" for _ in allowed_slugs)
    connection.execute(
        f"DELETE FROM exchanges WHERE slug NOT IN ({placeholders})",
        allowed_slugs,
    )

    for slug, name, balance in EXCHANGE_SEED:
        existing = connection.execute(
            "SELECT id FROM exchanges WHERE slug = ?",
            (slug,),
        ).fetchone()
        if existing:
            connection.execute(
                "UPDATE exchanges SET name = ? WHERE slug = ?",
                (name, slug),
            )
        else:
            connection.execute(
                """
                INSERT INTO exchanges (slug, name, balance_usdt, start_balance_usdt)
                VALUES (?, ?, ?, ?)
                """,
                (slug, name, balance, balance),
            )
            exchange_id = connection.execute(
                "SELECT id FROM exchanges WHERE slug = ?",
                (slug,),
            ).fetchone()["id"]
            _insert_balance_event(
                connection=connection,
                exchange_id=exchange_id,
                event_type="seed",
                balance_before=None,
                balance_after=balance,
                start_balance_before=None,
                start_balance_after=balance,
                note="Initial exchange balance",
            )


def _insert_balance_event(
    connection: sqlite3.Connection,
    exchange_id: int,
    event_type: str,
    balance_before: float | None,
    balance_after: float,
    start_balance_before: float | None,
    start_balance_after: float,
    note: str | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO balance_events (
            exchange_id,
            event_type,
            balance_before_usdt,
            balance_after_usdt,
            start_balance_before_usdt,
            start_balance_after_usdt,
            pnl_after_usdt,
            note
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            exchange_id,
            event_type,
            balance_before,
            balance_after,
            start_balance_before,
            start_balance_after,
            balance_after - start_balance_after,
            note,
        ),
    )


def _backfill_balance_events(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        """
        SELECT id, balance_usdt, start_balance_usdt
        FROM exchanges
        WHERE id NOT IN (SELECT DISTINCT exchange_id FROM balance_events)
        """
    ).fetchall()

    for row in rows:
        _insert_balance_event(
            connection=connection,
            exchange_id=row["id"],
            event_type="backfill",
            balance_before=None,
            balance_after=row["balance_usdt"],
            start_balance_before=None,
            start_balance_after=row["start_balance_usdt"],
            note="Backfilled current exchange balance",
        )


def _migrate_trades_schema(connection: sqlite3.Connection) -> None:
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(trades)").fetchall()}
    migrations = [
        ("group_id", "ALTER TABLE trades ADD COLUMN group_id TEXT"),
        ("leverage", "ALTER TABLE trades ADD COLUMN leverage REAL NOT NULL DEFAULT 1"),
        ("margin_mode", "ALTER TABLE trades ADD COLUMN margin_mode TEXT NOT NULL DEFAULT 'isolated'"),
        ("notional_usdt", "ALTER TABLE trades ADD COLUMN notional_usdt REAL NOT NULL DEFAULT 0"),
        ("comment", "ALTER TABLE trades ADD COLUMN comment TEXT NOT NULL DEFAULT ''"),
        ("last_funding_applied_at", "ALTER TABLE trades ADD COLUMN last_funding_applied_at INTEGER"),
    ]
    for column_name, statement in migrations:
        if column_name not in columns:
            connection.execute(statement)

    connection.execute(
        """
        UPDATE trades
        SET group_id = COALESCE(group_id, symbol || '-' || id),
            notional_usdt = CASE
                WHEN notional_usdt > 0 THEN notional_usdt
                WHEN size_unit = 'USDT' THEN size_value
                ELSE size_value * entry_price
            END
        WHERE group_id IS NULL OR group_id = '' OR notional_usdt <= 0
        """
    )


def _rebuild_daily_profit_from_trade_events(connection: sqlite3.Connection) -> None:
    connection.execute("DELETE FROM daily_profit")
    connection.execute(
        """
        INSERT INTO daily_profit (profit_date, pnl_usdt, source)
        SELECT
            date(funding_events.created_at) AS profit_date,
            ROUND(SUM(funding_events.amount_usdt), 8) AS pnl_usdt,
            'trades' AS source
        FROM funding_events
        JOIN trades ON trades.id = funding_events.trade_id
        WHERE trades.status != 'deleted'
        GROUP BY date(funding_events.created_at)
        HAVING ABS(pnl_usdt) > 0.00000001
        ON CONFLICT(profit_date) DO UPDATE
        SET pnl_usdt = pnl_usdt + excluded.pnl_usdt,
            source = 'trades'
        """
    )
    connection.execute(
        """
        INSERT INTO daily_profit (profit_date, pnl_usdt, source)
        SELECT
            date(trades.closed_at) AS profit_date,
            ROUND(SUM(trades.realized_pnl_usdt - COALESCE(funding_totals.funding_pnl_usdt, 0)), 8) AS pnl_usdt,
            'trades' AS source
        FROM trades
        LEFT JOIN (
            SELECT trade_id, SUM(amount_usdt) AS funding_pnl_usdt
            FROM funding_events
            GROUP BY trade_id
        ) AS funding_totals ON funding_totals.trade_id = trades.id
        WHERE trades.status = 'closed'
            AND trades.closed_at IS NOT NULL
        GROUP BY date(trades.closed_at)
        HAVING ABS(pnl_usdt) > 0.00000001
        ON CONFLICT(profit_date) DO UPDATE
        SET pnl_usdt = pnl_usdt + excluded.pnl_usdt,
            source = 'trades'
        """
    )


def rebuild_daily_profit(connection: sqlite3.Connection) -> None:
    _rebuild_daily_profit_from_trade_events(connection)


def fetch_all(query: str, parameters: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    with closing(get_connection()) as connection:
        return list(connection.execute(query, parameters).fetchall())


def fetch_one(query: str, parameters: tuple[Any, ...] = ()) -> sqlite3.Row | None:
    with closing(get_connection()) as connection:
        return connection.execute(query, parameters).fetchone()
