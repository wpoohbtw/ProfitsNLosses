from __future__ import annotations

from calendar import monthrange
from contextlib import closing
from datetime import date, datetime
import time
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .db import ensure_user_exchanges, fetch_all, get_connection, initialize_database, rebuild_daily_profit
from .market_data import get_market_funding, get_market_funding_history_sync, get_market_funding_sync, get_market_snapshot, get_market_symbols, stream_market_data
from .portal_identity import get_current_portal_user, get_default_portal_user_id
from .situations import (
    SituationsConfigError,
    append_situation,
    delete_situation,
    get_situations_settings,
    list_situations,
    test_situations_connection,
    update_situation,
    update_situations_settings,
)

app = FastAPI(title="ProfitsNLosses API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class BalanceUpdate(BaseModel):
    balance_usdt: float = Field(ge=0)


class TradeCreate(BaseModel):
    exchange_id: int
    group_id: str = Field(min_length=1, max_length=96)
    symbol: str = Field(min_length=1, max_length=32)
    side: str = Field(pattern="^(long|short)$")
    entry_price: float = Field(gt=0)
    size_value: float = Field(gt=0)
    size_unit: str = Field(pattern="^(USDT|TOKEN)$")
    notional_usdt: float = Field(gt=0)
    margin_usdt: float = Field(gt=0)
    leverage: float = Field(gt=0)
    margin_mode: str = Field(pattern="^(isolated|cross)$")


class TradeClose(BaseModel):
    exit_price: float = Field(gt=0)
    realized_pnl_usdt: float
    group_id: str | None = Field(default=None, max_length=96)
    notional_usdt: float | None = Field(default=None, gt=0)
    leverage: float | None = Field(default=None, gt=0)
    margin_mode: str | None = Field(default=None, pattern="^(isolated|cross)$")


class TradeRealizePnl(BaseModel):
    realized_pnl_usdt: float
    size_value: float | None = Field(default=None, gt=0)
    notional_usdt: float | None = Field(default=None, gt=0)
    margin_usdt: float | None = Field(default=None, gt=0)


class TradeExitOrderPayload(BaseModel):
    order_type: str = Field(pattern="^(take_profit|stop_loss)$")
    trigger_mode: str = Field(default="price", pattern="^(price|pnl_percent)$")
    trigger_price: float = Field(gt=0)
    pnl_percent: float
    size_mode: str = Field(default="percent", pattern="^(percent|usdt)$")
    size_percent: float = Field(gt=0, le=100)
    size_usdt: float = Field(gt=0)


class ExchangeTransfer(BaseModel):
    from_exchange_id: int
    to_exchange_id: int
    amount_usdt: float = Field(gt=0)


class TradeGroupComment(BaseModel):
    comment: str = Field(max_length=80)


class SituationCreate(BaseModel):
    date: str = Field(min_length=1, max_length=32)
    token: str = Field(min_length=1, max_length=32)
    description: str = Field(min_length=1, max_length=1000)
    posts: str = Field(default="", max_length=2000)


class SituationSettingsUpdate(BaseModel):
    credentials_path: str = Field(min_length=1, max_length=300)
    spreadsheet_id: str = Field(default="", max_length=180)
    sheet_name: str = Field(default="Situations", min_length=1, max_length=80)


def portal_user_id(current_user: dict[str, object]) -> int:
    return int(current_user["userId"])


@app.on_event("startup")
def on_startup() -> None:
    initialize_database()


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/me")
def get_me(current_user: dict[str, object] = Depends(get_current_portal_user)) -> dict[str, object]:
    return {
        "userId": portal_user_id(current_user),
        "username": current_user.get("username", ""),
    }


@app.get("/api/v1/situations/settings")
def get_situation_settings() -> dict[str, object]:
    return get_situations_settings()


@app.put("/api/v1/situations/settings")
def save_situation_settings(payload: SituationSettingsUpdate) -> dict[str, object]:
    return update_situations_settings(
        credentials_path=payload.credentials_path,
        spreadsheet_id=payload.spreadsheet_id,
        sheet_name=payload.sheet_name,
    )


@app.post("/api/v1/situations/settings/test")
def test_situation_settings() -> dict[str, object]:
    return test_situations_connection()


@app.get("/api/v1/situations")
def get_situations() -> dict[str, object]:
    try:
        return {"situations": list_situations()}
    except SituationsConfigError as caught_error:
        raise HTTPException(status_code=500, detail=str(caught_error)) from caught_error
    except Exception as caught_error:
        raise HTTPException(status_code=502, detail=f"Не удалось прочитать Google таблицу: {caught_error}") from caught_error


@app.post("/api/v1/situations")
def create_situation(payload: SituationCreate) -> dict[str, object]:
    try:
        return append_situation(
            date_value=payload.date,
            token=payload.token.upper(),
            description=payload.description,
            posts=payload.posts,
        )
    except SituationsConfigError as caught_error:
        raise HTTPException(status_code=500, detail=str(caught_error)) from caught_error
    except Exception as caught_error:
        raise HTTPException(status_code=502, detail=f"Не удалось сохранить ситуацию в Google таблицу: {caught_error}") from caught_error


@app.put("/api/v1/situations/{row_number}")
def edit_situation(row_number: int, payload: SituationCreate) -> dict[str, object]:
    try:
        return update_situation(
            row_number=row_number,
            date_value=payload.date,
            token=payload.token.upper(),
            description=payload.description,
            posts=payload.posts,
        )
    except SituationsConfigError as caught_error:
        raise HTTPException(status_code=500, detail=str(caught_error)) from caught_error
    except Exception as caught_error:
        raise HTTPException(status_code=502, detail=f"Не удалось обновить ситуацию в Google таблице: {caught_error}") from caught_error


@app.delete("/api/v1/situations/{row_number}")
def remove_situation(row_number: int) -> dict[str, object]:
    try:
        return delete_situation(row_number=row_number)
    except SituationsConfigError as caught_error:
        raise HTTPException(status_code=500, detail=str(caught_error)) from caught_error
    except Exception as caught_error:
        raise HTTPException(status_code=502, detail=f"Не удалось удалить ситуацию из Google таблицы: {caught_error}") from caught_error


@app.get("/api/v1/market/symbols")
def market_symbols(
    exchange_slug: str,
    query: str = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> dict[str, object]:
    try:
        return get_market_symbols(exchange_slug=exchange_slug, query=query, limit=limit)
    except ValueError as caught_error:
        raise HTTPException(status_code=400, detail=str(caught_error)) from caught_error
    except RuntimeError as caught_error:
        raise HTTPException(status_code=502, detail=str(caught_error)) from caught_error


@app.get("/api/v1/market/snapshot")
async def market_snapshot(exchange_slug: str, symbol: str) -> dict[str, object]:
    try:
        return await get_market_snapshot(exchange_slug=exchange_slug, symbol=symbol)
    except ValueError as caught_error:
        raise HTTPException(status_code=400, detail=str(caught_error)) from caught_error
    except RuntimeError as caught_error:
        raise HTTPException(status_code=502, detail=str(caught_error)) from caught_error


@app.get("/api/v1/market/funding")
async def market_funding(exchange_slug: str, symbol: str) -> dict[str, object]:
    try:
        return await get_market_funding(exchange_slug=exchange_slug, symbol=symbol)
    except ValueError as caught_error:
        raise HTTPException(status_code=400, detail=str(caught_error)) from caught_error
    except RuntimeError as caught_error:
        raise HTTPException(status_code=502, detail=str(caught_error)) from caught_error


@app.websocket("/api/v1/market/ws")
async def market_ws(websocket: WebSocket, exchange_slug: str, symbol: str) -> None:
    await stream_market_data(websocket=websocket, exchange_slug=exchange_slug, symbol=symbol)


@app.get("/api/v1/exchanges")
def list_exchanges(current_user: dict[str, object] = Depends(get_current_portal_user)) -> dict[str, object]:
    user_id = portal_user_id(current_user)
    with closing(get_connection()) as connection:
        ensure_user_exchanges(connection, user_id)
        rows = connection.execute(
            """
            SELECT id, slug, name, balance_usdt, start_balance_usdt, pnl_reset_at, updated_at
            FROM exchanges
            WHERE user_id = ?
            ORDER BY CASE slug
                WHEN 'binance' THEN 1
                WHEN 'bybit' THEN 2
                WHEN 'mexc' THEN 3
                WHEN 'bingx' THEN 4
                WHEN 'gate' THEN 5
                WHEN 'bitget' THEN 6
                WHEN 'kucoin' THEN 7
                WHEN 'hyperliquid' THEN 8
                WHEN 'aster' THEN 9
                WHEN 'okx' THEN 10
                ELSE 99
            END
            """,
            (user_id,),
        ).fetchall()
        connection.commit()
    return build_exchanges_response(rows)


def build_exchanges_response(rows: list[object]) -> dict[str, object]:
    exchanges = []
    total_balance = 0.0
    total_pnl = 0.0

    for row in rows:
        pnl_total = row["balance_usdt"] - row["start_balance_usdt"]
        total_balance += row["balance_usdt"]
        total_pnl += pnl_total
        exchanges.append(
            {
                "id": row["id"],
                "slug": row["slug"],
                "name": row["name"],
                "balanceUsdt": round(row["balance_usdt"], 2),
                "startBalanceUsdt": round(row["start_balance_usdt"], 2),
                "pnlTotalUsdt": round(pnl_total, 2),
                "pnlResetAt": row["pnl_reset_at"],
                "updatedAt": row["updated_at"],
            }
        )

    return {
        "exchanges": exchanges,
        "summary": {
            "totalBalanceUsdt": round(total_balance, 2),
            "totalPnlUsdt": round(total_pnl, 2),
            "exchangeCount": len(exchanges),
        },
    }


def fetch_exchange_or_404(connection, exchange_id: int, user_id: int | None = None):
    parameters: tuple[object, ...]
    user_clause = ""
    if user_id is not None:
        user_clause = "AND user_id = ?"
        parameters = (exchange_id, user_id)
    else:
        parameters = (exchange_id,)

    row = connection.execute(
        f"""
        SELECT id, user_id, balance_usdt, start_balance_usdt
        FROM exchanges
        WHERE id = ?
        {user_clause}
        """,
        parameters,
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Биржа не найдена")
    return row


def insert_balance_event(
    connection,
    exchange_id: int,
    event_type: str,
    balance_before: float | None,
    balance_after: float,
    start_balance_before: float | None,
    start_balance_after: float,
    note: str | None = None,
    created_at: str | None = None,
    user_id: int | None = None,
) -> None:
    resolved_user_id = user_id
    if resolved_user_id is None:
        row = connection.execute("SELECT user_id FROM exchanges WHERE id = ?", (exchange_id,)).fetchone()
        resolved_user_id = row["user_id"] if row else get_default_portal_user_id()

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
            note,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))
        """,
        (
            exchange_id,
            resolved_user_id,
            event_type,
            balance_before,
            balance_after,
            start_balance_before,
            start_balance_after,
            balance_after - start_balance_after,
            note,
            created_at,
        ),
    )


def add_daily_profit_delta(connection, pnl_delta: float, profit_date: str | None = None, user_id: int | None = None) -> None:
    resolved_user_id = user_id or get_default_portal_user_id()
    connection.execute(
        """
        INSERT INTO daily_profit (user_id, profit_date, pnl_usdt, source)
        VALUES (?, ?, ?, 'trades')
        ON CONFLICT(user_id, profit_date) DO UPDATE
        SET pnl_usdt = pnl_usdt + excluded.pnl_usdt,
            source = 'trades'
        """,
        (resolved_user_id, profit_date or date.today().isoformat(), pnl_delta),
    )


def apply_trade_pnl_delta(
    connection,
    exchange_id: int,
    pnl_delta: float,
    event_type: str,
    note: str,
    created_at: str | None = None,
    profit_date: str | None = None,
) -> None:
    exchange = fetch_exchange_or_404(connection, exchange_id)
    old_balance = exchange["balance_usdt"]
    new_balance = old_balance + pnl_delta
    connection.execute(
        """
        UPDATE exchanges
        SET balance_usdt = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (new_balance, exchange_id),
    )
    insert_balance_event(
        connection=connection,
        exchange_id=exchange_id,
        event_type=event_type,
        balance_before=old_balance,
        balance_after=new_balance,
        start_balance_before=exchange["start_balance_usdt"],
        start_balance_after=exchange["start_balance_usdt"],
        note=note,
        created_at=created_at,
        user_id=exchange["user_id"],
    )
    add_daily_profit_delta(connection, pnl_delta, profit_date, exchange["user_id"])


def calculate_trade_price_pnl(side: str, entry_price: float, exit_price: float, size_value: float, size_unit: str) -> float:
    quantity = size_value / entry_price if size_unit == "USDT" else size_value
    if side == "short":
        return (entry_price - exit_price) * quantity
    return (exit_price - entry_price) * quantity


def serialize_exit_order(row) -> dict[str, object]:
    return {
        "id": row["id"],
        "tradeId": row["trade_id"],
        "orderType": row["order_type"],
        "triggerMode": row["trigger_mode"],
        "triggerPrice": row["trigger_price"],
        "pnlPercent": row["pnl_percent"],
        "sizeMode": row["size_mode"],
        "sizePercent": row["size_percent"],
        "sizeUsdt": row["size_usdt"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def funding_interval_ms(exchange_slug: str) -> int:
    hours = 1 if exchange_slug == "hyperliquid" else 8
    return hours * 60 * 60 * 1000


def timestamp_ms_to_sqlite(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000).strftime("%Y-%m-%d %H:%M:%S")


def timestamp_ms_to_date(timestamp_ms: int) -> str:
    return datetime.fromtimestamp(timestamp_ms / 1000).date().isoformat()


def parse_sqlite_timestamp_ms(value: str | None) -> int:
    if not value:
        return int(time.time() * 1000)
    try:
        return int(datetime.fromisoformat(value.replace(" ", "T")).timestamp() * 1000)
    except ValueError:
        return int(time.time() * 1000)


def get_missed_funding_times(last_applied_at: int, next_funding_time: int, interval_ms: int, now_ms: int) -> list[int]:
    if not next_funding_time or interval_ms <= 0:
        return []

    funding_time = next_funding_time - interval_ms
    missed = []
    while funding_time > last_applied_at and funding_time <= now_ms and len(missed) < 180:
        missed.append(funding_time)
        funding_time -= interval_ms
    return list(reversed(missed))


def calculate_funding_pnl(notional_usdt: float, side: str, funding_rate: float) -> float:
    direction = -1 if side == "long" else 1
    return round(float(notional_usdt) * funding_rate * direction, 8)


def apply_funding_event(
    connection,
    trade,
    funding_time: int,
    funding_rate: float,
    source: str,
) -> bool:
    funding_pnl = calculate_funding_pnl(trade["notional_usdt"], trade["side"], funding_rate)
    existing = connection.execute(
        """
        SELECT id, funding_rate, amount_usdt, source
        FROM funding_events
        WHERE trade_id = ? AND funding_time = ?
        """,
        (trade["id"], funding_time),
    ).fetchone()

    if existing is not None:
        if existing["source"] == "historical" or source != "historical":
            return False
        delta = funding_pnl - existing["amount_usdt"]
        if abs(delta) <= 0.00000001:
            connection.execute(
                """
                UPDATE funding_events
                SET funding_rate = ?, notional_usdt = ?, amount_usdt = ?, source = ?
                WHERE id = ?
                """,
                (funding_rate, trade["notional_usdt"], funding_pnl, source, existing["id"]),
            )
            return False

        connection.execute(
            """
            UPDATE funding_events
            SET funding_rate = ?, notional_usdt = ?, amount_usdt = ?, source = ?
            WHERE id = ?
            """,
            (funding_rate, trade["notional_usdt"], funding_pnl, source, existing["id"]),
        )
        connection.execute(
            """
            UPDATE trades
            SET realized_pnl_usdt = realized_pnl_usdt + ?,
                last_funding_applied_at = MAX(COALESCE(last_funding_applied_at, 0), ?)
            WHERE id = ?
            """,
            (delta, funding_time, trade["id"]),
        )
        apply_trade_pnl_delta(
            connection=connection,
            exchange_id=trade["exchange_id"],
            pnl_delta=delta,
            event_type="funding",
            note=f"Funding correction {trade['symbol']} trade #{trade['id']} at rate {funding_rate}",
            created_at=timestamp_ms_to_sqlite(funding_time),
            profit_date=timestamp_ms_to_date(funding_time),
        )
        return True

    connection.execute(
        """
        INSERT INTO funding_events (
            trade_id,
            exchange_id,
            user_id,
            symbol,
            funding_time,
            funding_rate,
            notional_usdt,
            side,
            amount_usdt,
            source,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            trade["id"],
            trade["exchange_id"],
            trade["user_id"],
            trade["symbol"],
            funding_time,
            funding_rate,
            trade["notional_usdt"],
            trade["side"],
            funding_pnl,
            source,
            timestamp_ms_to_sqlite(funding_time),
        ),
    )
    connection.execute(
        """
        UPDATE trades
        SET realized_pnl_usdt = realized_pnl_usdt + ?,
            last_funding_applied_at = MAX(COALESCE(last_funding_applied_at, 0), ?)
        WHERE id = ?
        """,
        (funding_pnl, funding_time, trade["id"]),
    )
    apply_trade_pnl_delta(
        connection=connection,
        exchange_id=trade["exchange_id"],
        pnl_delta=funding_pnl,
        event_type="funding",
        note=f"Funding {trade['symbol']} trade #{trade['id']} at rate {funding_rate}",
        created_at=timestamp_ms_to_sqlite(funding_time),
        profit_date=timestamp_ms_to_date(funding_time),
    )
    return True


def fetch_trade_funding_history(trade, start_ms: int, end_ms: int) -> list[dict[str, object]]:
    try:
        history = get_market_funding_history_sync(trade["exchange_slug"], trade["symbol"], start_ms, end_ms)
    except Exception:
        history = []
    return [
        event
        for event in history
        if start_ms < int(event.get("fundingTime") or 0) <= end_ms
    ]


def sync_funding_for_trade(connection, trade, end_ms: int, prefer_history: bool = True) -> None:
    opened_ms = parse_sqlite_timestamp_ms(trade["opened_at"])
    if end_ms <= opened_ms:
        return

    if prefer_history:
        history = fetch_trade_funding_history(trade, opened_ms, end_ms)
        if history:
            for event in history:
                apply_funding_event(
                    connection=connection,
                    trade=trade,
                    funding_time=int(event["fundingTime"]),
                    funding_rate=float(event.get("fundingRate") or 0),
                    source="historical",
                )
            return

    try:
        funding_info = get_market_funding_sync(trade["exchange_slug"], trade["symbol"])
    except Exception:
        return

    funding_rate = float(funding_info.get("fundingRate") or 0)
    next_funding_time = int(funding_info.get("nextFundingTime") or 0)
    last_applied_at = trade["last_funding_applied_at"] or opened_ms
    missed_times = get_missed_funding_times(
        last_applied_at=last_applied_at,
        next_funding_time=next_funding_time,
        interval_ms=funding_interval_ms(trade["exchange_slug"]),
        now_ms=end_ms,
    )
    for funding_time in missed_times:
        apply_funding_event(connection, trade, funding_time, funding_rate, "current_fallback")


def sync_funding_for_trades(connection, user_id: int, status: str = "open") -> None:
    trades = connection.execute(
        """
        SELECT
            trades.id,
            trades.exchange_id,
            trades.user_id,
            exchanges.slug AS exchange_slug,
            trades.symbol,
            trades.side,
            trades.notional_usdt,
            trades.status,
            trades.opened_at,
            trades.closed_at,
            trades.last_funding_applied_at
        FROM trades
        JOIN exchanges ON exchanges.id = trades.exchange_id
        WHERE trades.user_id = ?
            AND trades.status = ?
        """,
        (user_id, status),
    ).fetchall()
    now_ms = int(time.time() * 1000)

    for trade in trades:
        end_ms = parse_sqlite_timestamp_ms(trade["closed_at"]) if status == "closed" else now_ms
        sync_funding_for_trade(connection, trade, end_ms=end_ms, prefer_history=True)


def sync_funding_for_open_trades(connection, user_id: int) -> None:
    sync_funding_for_trades(connection, user_id=user_id, status="open")


def sync_funding_for_closed_trades(connection, user_id: int) -> None:
    sync_funding_for_trades(connection, user_id=user_id, status="closed")


@app.post("/api/v1/funding/reconcile")
def reconcile_funding(current_user: dict[str, object] = Depends(get_current_portal_user)) -> dict[str, str]:
    user_id = portal_user_id(current_user)
    with closing(get_connection()) as connection:
        sync_funding_for_open_trades(connection, user_id)
        sync_funding_for_closed_trades(connection, user_id)
        rebuild_daily_profit(connection, user_id)
        connection.commit()
    return {"status": "reconciled"}


@app.put("/api/v1/exchanges/{exchange_id}/balance")
def update_balance(exchange_id: int, payload: BalanceUpdate, current_user: dict[str, object] = Depends(get_current_portal_user)) -> dict[str, object]:
    user_id = portal_user_id(current_user)
    with closing(get_connection()) as connection:
        row = fetch_exchange_or_404(connection, exchange_id, user_id)
        old_balance = row["balance_usdt"]
        start_balance = row["start_balance_usdt"]

        connection.execute(
            """
            UPDATE exchanges
            SET balance_usdt = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (payload.balance_usdt, exchange_id),
        )
        insert_balance_event(
            connection=connection,
            exchange_id=exchange_id,
            event_type="balance_update",
            balance_before=old_balance,
            balance_after=payload.balance_usdt,
            start_balance_before=start_balance,
            start_balance_after=start_balance,
            note="Manual balance update",
        )
        connection.commit()

    return {"status": "saved"}


@app.post("/api/v1/exchanges/{exchange_id}/reset-pnl")
def reset_exchange_pnl(exchange_id: int, current_user: dict[str, object] = Depends(get_current_portal_user)) -> dict[str, object]:
    user_id = portal_user_id(current_user)
    with closing(get_connection()) as connection:
        row = fetch_exchange_or_404(connection, exchange_id, user_id)
        current_balance = row["balance_usdt"]
        old_start_balance = row["start_balance_usdt"]

        connection.execute(
            """
            UPDATE exchanges
            SET start_balance_usdt = ?, pnl_reset_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (current_balance, exchange_id),
        )
        insert_balance_event(
            connection=connection,
            exchange_id=exchange_id,
            event_type="pnl_reset",
            balance_before=current_balance,
            balance_after=current_balance,
            start_balance_before=old_start_balance,
            start_balance_after=current_balance,
            note="Manual PnL reset",
        )
        connection.commit()

    return {"status": "reset"}


@app.post("/api/v1/exchanges/transfer")
def transfer_between_exchanges(payload: ExchangeTransfer, current_user: dict[str, object] = Depends(get_current_portal_user)) -> dict[str, object]:
    if payload.from_exchange_id == payload.to_exchange_id:
        raise HTTPException(status_code=400, detail="Выберите разные биржи")

    user_id = portal_user_id(current_user)
    with closing(get_connection()) as connection:
        from_exchange = fetch_exchange_or_404(connection, payload.from_exchange_id, user_id)
        to_exchange = fetch_exchange_or_404(connection, payload.to_exchange_id, user_id)
        if payload.amount_usdt > from_exchange["balance_usdt"]:
            raise HTTPException(status_code=400, detail="Недостаточно баланса на бирже-источнике")

        from_balance_after = from_exchange["balance_usdt"] - payload.amount_usdt
        from_start_after = from_exchange["start_balance_usdt"] - payload.amount_usdt
        to_balance_after = to_exchange["balance_usdt"] + payload.amount_usdt
        to_start_after = to_exchange["start_balance_usdt"] + payload.amount_usdt

        connection.execute(
            """
            UPDATE exchanges
            SET balance_usdt = ?, start_balance_usdt = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (from_balance_after, from_start_after, payload.from_exchange_id),
        )
        connection.execute(
            """
            UPDATE exchanges
            SET balance_usdt = ?, start_balance_usdt = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (to_balance_after, to_start_after, payload.to_exchange_id),
        )
        insert_balance_event(
            connection=connection,
            exchange_id=payload.from_exchange_id,
            event_type="transfer_out",
            balance_before=from_exchange["balance_usdt"],
            balance_after=from_balance_after,
            start_balance_before=from_exchange["start_balance_usdt"],
            start_balance_after=from_start_after,
            note=f"Transfer out {payload.amount_usdt} USDT to exchange #{payload.to_exchange_id}",
        )
        insert_balance_event(
            connection=connection,
            exchange_id=payload.to_exchange_id,
            event_type="transfer_in",
            balance_before=to_exchange["balance_usdt"],
            balance_after=to_balance_after,
            start_balance_before=to_exchange["start_balance_usdt"],
            start_balance_after=to_start_after,
            note=f"Transfer in {payload.amount_usdt} USDT from exchange #{payload.from_exchange_id}",
        )
        connection.commit()

    return {"status": "transferred"}


@app.post("/api/v1/trades")
def create_trade(payload: TradeCreate, current_user: dict[str, object] = Depends(get_current_portal_user)) -> dict[str, object]:
    user_id = portal_user_id(current_user)
    with closing(get_connection()) as connection:
        exchange = fetch_exchange_or_404(connection, payload.exchange_id, user_id)
        if payload.margin_usdt > exchange["balance_usdt"]:
            raise HTTPException(status_code=400, detail="Недостаточно баланса на бирже")

        cursor = connection.execute(
            """
            INSERT INTO trades (
                exchange_id,
                user_id,
                group_id,
                symbol,
                side,
                entry_price,
                size_value,
                size_unit,
                notional_usdt,
                margin_usdt,
                leverage,
                margin_mode,
                last_funding_applied_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.exchange_id,
                user_id,
                payload.group_id,
                payload.symbol.upper(),
                payload.side,
                payload.entry_price,
                payload.size_value,
                payload.size_unit,
                payload.notional_usdt,
                payload.margin_usdt,
                payload.leverage,
                payload.margin_mode,
                int(time.time() * 1000),
            ),
        )
        connection.commit()

    return {"status": "created", "tradeId": cursor.lastrowid}


@app.get("/api/v1/trades")
def list_trades(status: str | None = "open", current_user: dict[str, object] = Depends(get_current_portal_user)) -> dict[str, object]:
    user_id = portal_user_id(current_user)
    parameters: list[object] = [user_id]
    where_clause = "WHERE trades.user_id = ?"
    if status is not None:
        if status not in {"open", "closed", "deleted"}:
            raise HTTPException(status_code=400, detail="Некорректный статус сделки")
        where_clause += " AND trades.status = ?"
        parameters.append(status)

    if status == "open":
        with closing(get_connection()) as connection:
            sync_funding_for_open_trades(connection, user_id)
            connection.commit()
    elif status == "closed":
        with closing(get_connection()) as connection:
            sync_funding_for_closed_trades(connection, user_id)
            connection.commit()

    rows = fetch_all(
        f"""
        SELECT
            trades.id,
            trades.group_id,
            trades.exchange_id,
            exchanges.slug AS exchange_slug,
            exchanges.name AS exchange_name,
            trades.symbol,
            trades.side,
            trades.status,
            trades.entry_price,
            trades.exit_price,
            trades.size_value,
            trades.size_unit,
            trades.notional_usdt,
            trades.margin_usdt,
            trades.leverage,
            trades.margin_mode,
            trades.realized_pnl_usdt,
            trades.last_funding_applied_at,
            trades.comment,
            trades.opened_at,
            trades.closed_at,
            trades.deleted_at
        FROM trades
        JOIN exchanges ON exchanges.id = trades.exchange_id
        {where_clause}
        ORDER BY trades.id DESC
        """,
        tuple(parameters),
    )
    trade_ids = [row["id"] for row in rows]
    exit_orders_by_trade: dict[int, list[dict[str, object]]] = {int(trade_id): [] for trade_id in trade_ids}
    if trade_ids:
        placeholders = ",".join("?" for _ in trade_ids)
        exit_order_rows = fetch_all(
            f"""
            SELECT
                id,
                trade_id,
                order_type,
                trigger_mode,
                trigger_price,
                pnl_percent,
                size_mode,
                size_percent,
                size_usdt,
                created_at,
                updated_at
            FROM trade_exit_orders
            WHERE user_id = ? AND trade_id IN ({placeholders})
            ORDER BY order_type ASC, trigger_price ASC, id ASC
            """,
            (user_id, *trade_ids),
        )
        for order_row in exit_order_rows:
            exit_orders_by_trade.setdefault(order_row["trade_id"], []).append(serialize_exit_order(order_row))

    trades = [
        {
            "id": row["id"],
            "groupId": row["group_id"],
            "exchangeId": row["exchange_id"],
            "exchangeSlug": row["exchange_slug"],
            "exchangeName": row["exchange_name"],
            "symbol": row["symbol"],
            "side": row["side"],
            "status": row["status"],
            "entryPrice": row["entry_price"],
            "exitPrice": row["exit_price"],
            "sizeValue": row["size_value"],
            "sizeUnit": row["size_unit"],
            "notionalUsdt": row["notional_usdt"],
            "marginUsdt": row["margin_usdt"],
            "leverage": row["leverage"],
            "marginMode": row["margin_mode"],
            "realizedPnlUsdt": row["realized_pnl_usdt"],
            "lastFundingAppliedAt": row["last_funding_applied_at"],
            "comment": row["comment"],
            "exitOrders": exit_orders_by_trade.get(row["id"], []),
            "openedAt": row["opened_at"],
            "closedAt": row["closed_at"],
            "deletedAt": row["deleted_at"],
        }
        for row in rows
    ]
    return {"trades": trades}


@app.put("/api/v1/trade-groups/{group_id}/comment")
def update_trade_group_comment(group_id: str, payload: TradeGroupComment, current_user: dict[str, object] = Depends(get_current_portal_user)) -> dict[str, object]:
    user_id = portal_user_id(current_user)
    with closing(get_connection()) as connection:
        cursor = connection.execute(
            """
            UPDATE trades
            SET comment = ?
            WHERE user_id = ? AND group_id = ?
            """,
            (payload.comment, user_id, group_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Группа сделок не найдена")
        connection.commit()

    return {"status": "saved"}


def fetch_open_trade_for_exit_order(connection, trade_id: int, user_id: int):
    trade = connection.execute(
        """
        SELECT id, user_id, status, notional_usdt
        FROM trades
        WHERE id = ? AND user_id = ?
        """,
        (trade_id, user_id),
    ).fetchone()
    if trade is None:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    if trade["status"] != "open":
        raise HTTPException(status_code=400, detail="TP/SL можно менять только у открытой сделки")
    return trade


@app.post("/api/v1/trades/{trade_id}/exit-orders")
def create_trade_exit_order(
    trade_id: int,
    payload: TradeExitOrderPayload,
    current_user: dict[str, object] = Depends(get_current_portal_user),
) -> dict[str, object]:
    user_id = portal_user_id(current_user)
    with closing(get_connection()) as connection:
        fetch_open_trade_for_exit_order(connection, trade_id, user_id)
        cursor = connection.execute(
            """
            INSERT INTO trade_exit_orders (
                trade_id,
                user_id,
                order_type,
                trigger_mode,
                trigger_price,
                pnl_percent,
                size_mode,
                size_percent,
                size_usdt
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trade_id,
                user_id,
                payload.order_type,
                payload.trigger_mode,
                payload.trigger_price,
                payload.pnl_percent,
                payload.size_mode,
                payload.size_percent,
                payload.size_usdt,
            ),
        )
        row = connection.execute(
            """
            SELECT id, trade_id, order_type, trigger_mode, trigger_price, pnl_percent, size_mode, size_percent, size_usdt, created_at, updated_at
            FROM trade_exit_orders
            WHERE id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()
        connection.commit()
    return {"status": "created", "exitOrder": serialize_exit_order(row)}


@app.put("/api/v1/trades/{trade_id}/exit-orders/{order_id}")
def update_trade_exit_order(
    trade_id: int,
    order_id: int,
    payload: TradeExitOrderPayload,
    current_user: dict[str, object] = Depends(get_current_portal_user),
) -> dict[str, object]:
    user_id = portal_user_id(current_user)
    with closing(get_connection()) as connection:
        fetch_open_trade_for_exit_order(connection, trade_id, user_id)
        cursor = connection.execute(
            """
            UPDATE trade_exit_orders
            SET order_type = ?,
                trigger_mode = ?,
                trigger_price = ?,
                pnl_percent = ?,
                size_mode = ?,
                size_percent = ?,
                size_usdt = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND trade_id = ? AND user_id = ?
            """,
            (
                payload.order_type,
                payload.trigger_mode,
                payload.trigger_price,
                payload.pnl_percent,
                payload.size_mode,
                payload.size_percent,
                payload.size_usdt,
                order_id,
                trade_id,
                user_id,
            ),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="TP/SL не найден")
        row = connection.execute(
            """
            SELECT id, trade_id, order_type, trigger_mode, trigger_price, pnl_percent, size_mode, size_percent, size_usdt, created_at, updated_at
            FROM trade_exit_orders
            WHERE id = ?
            """,
            (order_id,),
        ).fetchone()
        connection.commit()
    return {"status": "saved", "exitOrder": serialize_exit_order(row)}


@app.delete("/api/v1/trades/{trade_id}/exit-orders/{order_id}")
def delete_trade_exit_order(
    trade_id: int,
    order_id: int,
    current_user: dict[str, object] = Depends(get_current_portal_user),
) -> dict[str, str]:
    user_id = portal_user_id(current_user)
    with closing(get_connection()) as connection:
        fetch_open_trade_for_exit_order(connection, trade_id, user_id)
        cursor = connection.execute(
            """
            DELETE FROM trade_exit_orders
            WHERE id = ? AND trade_id = ? AND user_id = ?
            """,
            (order_id, trade_id, user_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="TP/SL не найден")
        connection.commit()
    return {"status": "deleted"}


@app.post("/api/v1/trades/{trade_id}/close")
def close_trade(trade_id: int, payload: TradeClose, current_user: dict[str, object] = Depends(get_current_portal_user)) -> dict[str, object]:
    user_id = portal_user_id(current_user)
    with closing(get_connection()) as connection:
        sync_funding_for_open_trades(connection, user_id)
        trade = connection.execute(
            """
            SELECT
                id,
                exchange_id,
                status,
                symbol,
                side,
                entry_price,
                size_value,
                size_unit,
                realized_pnl_usdt
            FROM trades
            WHERE id = ? AND user_id = ?
            """,
            (trade_id, user_id),
        ).fetchone()
        if trade is None:
            raise HTTPException(status_code=404, detail="Сделка не найдена")
        if trade["status"] != "open":
            raise HTTPException(status_code=400, detail="Сделка уже не открыта")

        price_pnl = calculate_trade_price_pnl(
            side=trade["side"],
            entry_price=trade["entry_price"],
            exit_price=payload.exit_price,
            size_value=trade["size_value"],
            size_unit=trade["size_unit"],
        )
        total_realized_pnl = trade["realized_pnl_usdt"] + price_pnl

        connection.execute(
            """
            UPDATE trades
            SET status = 'closed',
                exit_price = ?,
                realized_pnl_usdt = ?,
                group_id = COALESCE(?, group_id),
                notional_usdt = COALESCE(?, notional_usdt),
                leverage = COALESCE(?, leverage),
                margin_mode = COALESCE(?, margin_mode),
                closed_at = CURRENT_TIMESTAMP
            WHERE id = ? AND user_id = ?
            """,
            (
                payload.exit_price,
                total_realized_pnl,
                payload.group_id,
                payload.notional_usdt,
                payload.leverage,
                payload.margin_mode,
                trade_id,
                user_id,
            ),
        )
        connection.execute("DELETE FROM trade_exit_orders WHERE trade_id = ? AND user_id = ?", (trade_id, user_id))
        apply_trade_pnl_delta(
            connection=connection,
            exchange_id=trade["exchange_id"],
            pnl_delta=price_pnl,
            event_type="trade_close",
            note=f"Closed {trade['symbol']} trade #{trade_id}",
        )
        connection.commit()

    return {"status": "closed"}


@app.post("/api/v1/trades/{trade_id}/realize-pnl")
def realize_trade_pnl(trade_id: int, payload: TradeRealizePnl, current_user: dict[str, object] = Depends(get_current_portal_user)) -> dict[str, object]:
    user_id = portal_user_id(current_user)
    with closing(get_connection()) as connection:
        sync_funding_for_open_trades(connection, user_id)
        trade = connection.execute(
            """
            SELECT id, exchange_id, status, symbol, realized_pnl_usdt
            FROM trades
            WHERE id = ? AND user_id = ?
            """,
            (trade_id, user_id),
        ).fetchone()
        if trade is None:
            raise HTTPException(status_code=404, detail="Сделка не найдена")
        if trade["status"] != "open":
            raise HTTPException(status_code=400, detail="Сделка уже не открыта")

        connection.execute(
            """
            UPDATE trades
            SET realized_pnl_usdt = ?,
                size_value = COALESCE(?, size_value),
                notional_usdt = COALESCE(?, notional_usdt),
                margin_usdt = COALESCE(?, margin_usdt)
            WHERE id = ? AND user_id = ?
            """,
            (
                trade["realized_pnl_usdt"] + payload.realized_pnl_usdt,
                payload.size_value,
                payload.notional_usdt,
                payload.margin_usdt,
                trade_id,
                user_id,
            ),
        )
        apply_trade_pnl_delta(
            connection=connection,
            exchange_id=trade["exchange_id"],
            pnl_delta=payload.realized_pnl_usdt,
            event_type="trade_partial_close",
            note=f"Partial close {trade['symbol']} trade #{trade_id}",
        )
        connection.commit()

    return {"status": "realized"}


@app.post("/api/v1/trades/{trade_id}/revert-close")
def revert_closed_trade(trade_id: int, current_user: dict[str, object] = Depends(get_current_portal_user)) -> dict[str, object]:
    user_id = portal_user_id(current_user)
    with closing(get_connection()) as connection:
        trade = connection.execute(
            """
            SELECT id, exchange_id, status, symbol, realized_pnl_usdt
            FROM trades
            WHERE id = ? AND user_id = ?
            """,
            (trade_id, user_id),
        ).fetchone()
        if trade is None:
            raise HTTPException(status_code=404, detail="Сделка не найдена")
        if trade["status"] != "closed":
            raise HTTPException(status_code=400, detail="Удалять с откатом баланса можно только закрытую сделку")

        apply_trade_pnl_delta(
            connection=connection,
            exchange_id=trade["exchange_id"],
            pnl_delta=-trade["realized_pnl_usdt"],
            event_type="trade_delete",
            note=f"Deleted closed {trade['symbol']} trade #{trade_id}",
        )
        connection.execute(
            """
            UPDATE trades
            SET status = 'deleted',
                deleted_at = CURRENT_TIMESTAMP
            WHERE id = ? AND user_id = ?
            """,
            (trade_id, user_id),
        )
        connection.execute("DELETE FROM trade_exit_orders WHERE trade_id = ? AND user_id = ?", (trade_id, user_id))
        connection.commit()

    return {"status": "reverted"}


@app.delete("/api/v1/trades/{trade_id}")
def delete_trade(trade_id: int, current_user: dict[str, object] = Depends(get_current_portal_user)) -> dict[str, object]:
    user_id = portal_user_id(current_user)
    with closing(get_connection()) as connection:
        row = connection.execute(
            """
            SELECT
                id,
                exchange_id,
                status,
                symbol,
                side,
                entry_price,
                size_value,
                size_unit,
                realized_pnl_usdt
            FROM trades
            WHERE id = ? AND user_id = ?
            """,
            (trade_id, user_id),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Сделка не найдена")

        if row["status"] == "open" and abs(row["realized_pnl_usdt"]) > 0.00000001:
            apply_trade_pnl_delta(
                connection=connection,
                exchange_id=row["exchange_id"],
                pnl_delta=-row["realized_pnl_usdt"],
                event_type="trade_delete",
                note=f"Deleted open {row['symbol']} trade #{trade_id}",
            )

        connection.execute(
            """
            UPDATE trades
            SET status = 'deleted', deleted_at = CURRENT_TIMESTAMP
            WHERE id = ? AND user_id = ?
            """,
            (trade_id, user_id),
        )
        connection.execute("DELETE FROM trade_exit_orders WHERE trade_id = ? AND user_id = ?", (trade_id, user_id))
        connection.commit()

    return {"status": "deleted"}


@app.get("/api/v1/balance-events")
def list_balance_events(
    exchange_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    current_user: dict[str, object] = Depends(get_current_portal_user),
) -> dict[str, object]:
    user_id = portal_user_id(current_user)
    parameters: list[object] = [user_id]
    where_clause = "WHERE balance_events.user_id = ?"
    if exchange_id is not None:
        where_clause += " AND balance_events.exchange_id = ?"
        parameters.append(exchange_id)
    parameters.append(limit)

    rows = fetch_all(
        f"""
        SELECT
            balance_events.id,
            balance_events.exchange_id,
            exchanges.slug,
            exchanges.name,
            balance_events.event_type,
            balance_events.balance_before_usdt,
            balance_events.balance_after_usdt,
            balance_events.start_balance_before_usdt,
            balance_events.start_balance_after_usdt,
            balance_events.pnl_after_usdt,
            balance_events.note,
            balance_events.created_at
        FROM balance_events
        JOIN exchanges ON exchanges.id = balance_events.exchange_id
        {where_clause}
        ORDER BY balance_events.id DESC
        LIMIT ?
        """,
        tuple(parameters),
    )

    events = [
        {
            "id": row["id"],
            "exchangeId": row["exchange_id"],
            "exchangeSlug": row["slug"],
            "exchangeName": row["name"],
            "eventType": row["event_type"],
            "balanceBeforeUsdt": row["balance_before_usdt"],
            "balanceAfterUsdt": row["balance_after_usdt"],
            "startBalanceBeforeUsdt": row["start_balance_before_usdt"],
            "startBalanceAfterUsdt": row["start_balance_after_usdt"],
            "pnlAfterUsdt": round(row["pnl_after_usdt"], 2),
            "note": row["note"],
            "createdAt": row["created_at"],
        }
        for row in rows
    ]
    return {"events": events}


@app.get("/api/v1/profit-calendar")
def profit_calendar(
    year: int | None = None,
    month: int | None = None,
    current_user: dict[str, object] = Depends(get_current_portal_user),
) -> dict[str, object]:
    user_id = portal_user_id(current_user)
    today = date.today()
    target_year = year or today.year
    target_month = month or today.month

    if target_month < 1 or target_month > 12:
        raise HTTPException(status_code=400, detail="Некорректный месяц")

    days_in_month = monthrange(target_year, target_month)[1]
    start_date = date(target_year, target_month, 1)
    end_date = date(target_year, target_month, days_in_month)

    with closing(get_connection()) as connection:
        rebuild_daily_profit(connection, user_id)
        connection.commit()
        rows = connection.execute(
            """
            SELECT profit_date, pnl_usdt, source
            FROM daily_profit
            WHERE user_id = ? AND profit_date BETWEEN ? AND ?
            ORDER BY profit_date ASC
            """,
            (user_id, start_date.isoformat(), end_date.isoformat()),
        ).fetchall()
    by_date = {row["profit_date"]: row for row in rows}
    days = []

    for day_number in range(1, days_in_month + 1):
        current_date = date(target_year, target_month, day_number).isoformat()
        row = by_date.get(current_date)
        days.append(
            {
                "date": current_date,
                "day": day_number,
                "pnlUsdt": round(row["pnl_usdt"], 2) if row else 0,
                "source": row["source"] if row else "empty",
            }
        )

    total = sum(day["pnlUsdt"] for day in days)
    return {
        "year": target_year,
        "month": target_month,
        "days": days,
        "totalPnlUsdt": round(total, 2),
    }
