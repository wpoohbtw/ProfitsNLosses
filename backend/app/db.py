from __future__ import annotations

from contextlib import closing
import sqlite3
from pathlib import Path
from typing import Any

from .portal_identity import get_default_portal_user_id

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
        default_user_id = get_default_portal_user_id()
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
        _migrate_user_schema(connection, default_user_id)
        _seed_exchanges(connection, default_user_id)
        _migrate_trades_schema(connection)
        _backfill_balance_events(connection)
        _rebuild_daily_profit_from_trade_events(connection)
        connection.commit()


def ensure_user_exchanges(connection: sqlite3.Connection, user_id: int) -> None:
    _seed_exchanges(connection, user_id)


def _seed_exchanges(connection: sqlite3.Connection, user_id: int) -> None:
    allowed_slugs = [slug for slug, _, _ in EXCHANGE_SEED]
    placeholders = ",".join("?" for _ in allowed_slugs)
    connection.execute(
        f"DELETE FROM exchanges WHERE user_id = ? AND slug NOT IN ({placeholders})",
        (user_id, *allowed_slugs),
    )

    for slug, name, balance in EXCHANGE_SEED:
        existing = connection.execute(
            "SELECT id FROM exchanges WHERE user_id = ? AND slug = ?",
            (user_id, slug),
        ).fetchone()
        if existing:
            connection.execute(
                "UPDATE exchanges SET name = ? WHERE user_id = ? AND slug = ?",
                (name, user_id, slug),
            )
        else:
            connection.execute(
                """
                INSERT INTO exchanges (user_id, slug, name, balance_usdt, start_balance_usdt)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, slug, name, balance, balance),
            )
            exchange_id = connection.execute(
                "SELECT id FROM exchanges WHERE user_id = ? AND slug = ?",
                (user_id, slug),
            ).fetchone()["id"]
            _insert_balance_event(
                connection=connection,
                user_id=user_id,
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
    user_id: int,
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
            user_id,
            event_type,
            balance_before_usdt,
            balance_after_usdt,
            start_balance_before_usdt,
            start_balance_after_usdt,
            pnl_after_usdt,
            note
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            exchange_id,
            user_id,
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
        SELECT id, user_id, balance_usdt, start_balance_usdt
        FROM exchanges
        WHERE id NOT IN (SELECT DISTINCT exchange_id FROM balance_events)
        """
    ).fetchall()

    for row in rows:
        _insert_balance_event(
            connection=connection,
            user_id=row["user_id"],
            exchange_id=row["id"],
            event_type="backfill",
            balance_before=None,
            balance_after=row["balance_usdt"],
            start_balance_before=None,
            start_balance_after=row["start_balance_usdt"],
            note="Backfilled current exchange balance",
        )


def _migrate_user_schema(connection: sqlite3.Connection, default_user_id: int) -> None:
    _add_column_if_missing(connection, "trades", "user_id", "ALTER TABLE trades ADD COLUMN user_id INTEGER")
    _add_column_if_missing(connection, "balance_events", "user_id", "ALTER TABLE balance_events ADD COLUMN user_id INTEGER")
    _add_column_if_missing(connection, "funding_events", "user_id", "ALTER TABLE funding_events ADD COLUMN user_id INTEGER")

    exchange_columns = {row["name"] for row in connection.execute("PRAGMA table_info(exchanges)").fetchall()}
    if "user_id" not in exchange_columns or _table_has_column_unique(connection, "exchanges", "slug"):
        _rebuild_exchanges_for_users(connection, default_user_id)
    else:
        connection.execute("UPDATE exchanges SET user_id = COALESCE(user_id, ?) WHERE user_id IS NULL", (default_user_id,))

    daily_profit_columns = {row["name"] for row in connection.execute("PRAGMA table_info(daily_profit)").fetchall()}
    if "user_id" not in daily_profit_columns or _table_has_column_unique(connection, "daily_profit", "profit_date"):
        _rebuild_daily_profit_for_users(connection, default_user_id)
    else:
        connection.execute("UPDATE daily_profit SET user_id = COALESCE(user_id, ?) WHERE user_id IS NULL", (default_user_id,))

    connection.execute("UPDATE trades SET user_id = COALESCE(user_id, ?) WHERE user_id IS NULL", (default_user_id,))
    connection.execute(
        """
        UPDATE balance_events
        SET user_id = COALESCE(
            user_id,
            (SELECT exchanges.user_id FROM exchanges WHERE exchanges.id = balance_events.exchange_id),
            ?
        )
        WHERE user_id IS NULL
        """,
        (default_user_id,),
    )
    connection.execute(
        """
        UPDATE funding_events
        SET user_id = COALESCE(
            user_id,
            (SELECT trades.user_id FROM trades WHERE trades.id = funding_events.trade_id),
            ?
        )
        WHERE user_id IS NULL
        """,
        (default_user_id,),
    )


def _add_column_if_missing(connection: sqlite3.Connection, table: str, column: str, statement: str) -> None:
    columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        connection.execute(statement)


def _table_has_column_unique(connection: sqlite3.Connection, table: str, column: str) -> bool:
    for index in connection.execute(f"PRAGMA index_list({table})").fetchall():
        if not index["unique"]:
            continue
        columns = [
            row["name"]
            for row in connection.execute(f"PRAGMA index_info({index['name']})").fetchall()
        ]
        if columns == [column]:
            return True
    return False


def _rebuild_exchanges_for_users(connection: sqlite3.Connection, default_user_id: int) -> None:
    connection.execute("PRAGMA foreign_keys = OFF")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS exchanges_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            slug TEXT NOT NULL,
            name TEXT NOT NULL,
            balance_usdt REAL NOT NULL DEFAULT 0,
            start_balance_usdt REAL NOT NULL DEFAULT 0,
            pnl_reset_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, slug)
        )
        """
    )
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(exchanges)").fetchall()}
    user_expr = "COALESCE(user_id, ?)" if "user_id" in columns else "?"
    connection.execute(
        f"""
        INSERT INTO exchanges_new (
            id, user_id, slug, name, balance_usdt, start_balance_usdt, pnl_reset_at, updated_at
        )
        SELECT id, {user_expr}, slug, name, balance_usdt, start_balance_usdt, pnl_reset_at, updated_at
        FROM exchanges
        """,
        (default_user_id,),
    )
    connection.execute("DROP TABLE exchanges")
    connection.execute("ALTER TABLE exchanges_new RENAME TO exchanges")
    connection.execute("PRAGMA foreign_keys = ON")


def _rebuild_daily_profit_for_users(connection: sqlite3.Connection, default_user_id: int) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_profit_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            profit_date TEXT NOT NULL,
            pnl_usdt REAL NOT NULL DEFAULT 0,
            source TEXT NOT NULL DEFAULT 'manual',
            UNIQUE(user_id, profit_date)
        )
        """
    )
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(daily_profit)").fetchall()}
    user_expr = "COALESCE(user_id, ?)" if "user_id" in columns else "?"
    connection.execute(
        f"""
        INSERT INTO daily_profit_new (id, user_id, profit_date, pnl_usdt, source)
        SELECT id, {user_expr}, profit_date, pnl_usdt, source
        FROM daily_profit
        """,
        (default_user_id,),
    )
    connection.execute("DROP TABLE daily_profit")
    connection.execute("ALTER TABLE daily_profit_new RENAME TO daily_profit")


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


def _rebuild_daily_profit_from_trade_events(connection: sqlite3.Connection, user_id: int | None = None) -> None:
    if user_id is None:
        connection.execute("DELETE FROM daily_profit")
        user_filter = ""
        parameters: tuple[Any, ...] = ()
    else:
        connection.execute("DELETE FROM daily_profit WHERE user_id = ?", (user_id,))
        user_filter = "AND trades.user_id = ?"
        parameters = (user_id,)

    connection.execute(
        f"""
        INSERT INTO daily_profit (user_id, profit_date, pnl_usdt, source)
        SELECT
            trades.user_id AS user_id,
            date(funding_events.created_at) AS profit_date,
            ROUND(SUM(funding_events.amount_usdt), 8) AS pnl_usdt,
            'trades' AS source
        FROM funding_events
        JOIN trades ON trades.id = funding_events.trade_id
        WHERE trades.status != 'deleted'
            {user_filter}
        GROUP BY trades.user_id, date(funding_events.created_at)
        HAVING ABS(pnl_usdt) > 0.00000001
        ON CONFLICT(user_id, profit_date) DO UPDATE
        SET pnl_usdt = pnl_usdt + excluded.pnl_usdt,
            source = 'trades'
        """,
        parameters,
    )
    connection.execute(
        f"""
        INSERT INTO daily_profit (user_id, profit_date, pnl_usdt, source)
        SELECT
            trades.user_id AS user_id,
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
            {user_filter}
        GROUP BY trades.user_id, date(trades.closed_at)
        HAVING ABS(pnl_usdt) > 0.00000001
        ON CONFLICT(user_id, profit_date) DO UPDATE
        SET pnl_usdt = pnl_usdt + excluded.pnl_usdt,
            source = 'trades'
        """,
        parameters,
    )


def rebuild_daily_profit(connection: sqlite3.Connection, user_id: int | None = None) -> None:
    _rebuild_daily_profit_from_trade_events(connection, user_id)


def fetch_all(query: str, parameters: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    with closing(get_connection()) as connection:
        return list(connection.execute(query, parameters).fetchall())


def fetch_one(query: str, parameters: tuple[Any, ...] = ()) -> sqlite3.Row | None:
    with closing(get_connection()) as connection:
        return connection.execute(query, parameters).fetchone()
