from __future__ import annotations

from calendar import monthrange
from contextlib import closing
from datetime import date
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .db import fetch_all, get_connection, initialize_database
from .market_data import get_market_funding, get_market_snapshot, get_market_symbols, stream_market_data
from .situations import SituationsConfigError, append_situation, delete_situation, list_situations, update_situation

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


@app.on_event("startup")
def on_startup() -> None:
    initialize_database()


@app.get("/api/v1/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


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
def list_exchanges() -> dict[str, object]:
    rows = fetch_all(
        """
        SELECT id, slug, name, balance_usdt, start_balance_usdt, pnl_reset_at, updated_at
        FROM exchanges
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
            ELSE 99
        END
        """
    )
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


def fetch_exchange_or_404(connection, exchange_id: int):
    row = connection.execute(
        """
        SELECT id, balance_usdt, start_balance_usdt
        FROM exchanges
        WHERE id = ?
        """,
        (exchange_id,),
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


def add_daily_profit_delta(connection, pnl_delta: float) -> None:
    connection.execute(
        """
        INSERT INTO daily_profit (profit_date, pnl_usdt, source)
        VALUES (?, ?, 'trades')
        ON CONFLICT(profit_date) DO UPDATE
        SET pnl_usdt = pnl_usdt + excluded.pnl_usdt,
            source = 'trades'
        """,
        (date.today().isoformat(), pnl_delta),
    )


def apply_trade_pnl_delta(
    connection,
    exchange_id: int,
    pnl_delta: float,
    event_type: str,
    note: str,
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
    )
    add_daily_profit_delta(connection, pnl_delta)


@app.put("/api/v1/exchanges/{exchange_id}/balance")
def update_balance(exchange_id: int, payload: BalanceUpdate) -> dict[str, object]:
    with closing(get_connection()) as connection:
        row = fetch_exchange_or_404(connection, exchange_id)
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
def reset_exchange_pnl(exchange_id: int) -> dict[str, object]:
    with closing(get_connection()) as connection:
        row = fetch_exchange_or_404(connection, exchange_id)
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
def transfer_between_exchanges(payload: ExchangeTransfer) -> dict[str, object]:
    if payload.from_exchange_id == payload.to_exchange_id:
        raise HTTPException(status_code=400, detail="Выберите разные биржи")

    with closing(get_connection()) as connection:
        from_exchange = fetch_exchange_or_404(connection, payload.from_exchange_id)
        to_exchange = fetch_exchange_or_404(connection, payload.to_exchange_id)
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
def create_trade(payload: TradeCreate) -> dict[str, object]:
    with closing(get_connection()) as connection:
        exchange = fetch_exchange_or_404(connection, payload.exchange_id)
        if payload.margin_usdt > exchange["balance_usdt"]:
            raise HTTPException(status_code=400, detail="Недостаточно баланса на бирже")

        cursor = connection.execute(
            """
            INSERT INTO trades (
                exchange_id,
                group_id,
                symbol,
                side,
                entry_price,
                size_value,
                size_unit,
                notional_usdt,
                margin_usdt,
                leverage,
                margin_mode
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.exchange_id,
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
            ),
        )
        connection.commit()

    return {"status": "created", "tradeId": cursor.lastrowid}


@app.get("/api/v1/trades")
def list_trades(status: str | None = "open") -> dict[str, object]:
    parameters: list[object] = []
    where_clause = ""
    if status is not None:
        if status not in {"open", "closed", "deleted"}:
            raise HTTPException(status_code=400, detail="Некорректный статус сделки")
        where_clause = "WHERE trades.status = ?"
        parameters.append(status)

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
            "comment": row["comment"],
            "openedAt": row["opened_at"],
            "closedAt": row["closed_at"],
            "deletedAt": row["deleted_at"],
        }
        for row in rows
    ]
    return {"trades": trades}


@app.put("/api/v1/trade-groups/{group_id}/comment")
def update_trade_group_comment(group_id: str, payload: TradeGroupComment) -> dict[str, object]:
    with closing(get_connection()) as connection:
        cursor = connection.execute(
            """
            UPDATE trades
            SET comment = ?
            WHERE group_id = ?
            """,
            (payload.comment, group_id),
        )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Группа сделок не найдена")
        connection.commit()

    return {"status": "saved"}


@app.post("/api/v1/trades/{trade_id}/close")
def close_trade(trade_id: int, payload: TradeClose) -> dict[str, object]:
    with closing(get_connection()) as connection:
        trade = connection.execute(
            """
            SELECT id, exchange_id, status, symbol, realized_pnl_usdt
            FROM trades
            WHERE id = ?
            """,
            (trade_id,),
        ).fetchone()
        if trade is None:
            raise HTTPException(status_code=404, detail="Сделка не найдена")
        if trade["status"] != "open":
            raise HTTPException(status_code=400, detail="Сделка уже не открыта")

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
            WHERE id = ?
            """,
            (
                payload.exit_price,
                payload.realized_pnl_usdt,
                payload.group_id,
                payload.notional_usdt,
                payload.leverage,
                payload.margin_mode,
                trade_id,
            ),
        )
        apply_trade_pnl_delta(
            connection=connection,
            exchange_id=trade["exchange_id"],
            pnl_delta=payload.realized_pnl_usdt - trade["realized_pnl_usdt"],
            event_type="trade_close",
            note=f"Closed {trade['symbol']} trade #{trade_id}",
        )
        connection.commit()

    return {"status": "closed"}


@app.post("/api/v1/trades/{trade_id}/realize-pnl")
def realize_trade_pnl(trade_id: int, payload: TradeRealizePnl) -> dict[str, object]:
    with closing(get_connection()) as connection:
        trade = connection.execute(
            """
            SELECT id, exchange_id, status, symbol, realized_pnl_usdt
            FROM trades
            WHERE id = ?
            """,
            (trade_id,),
        ).fetchone()
        if trade is None:
            raise HTTPException(status_code=404, detail="Сделка не найдена")
        if trade["status"] != "open":
            raise HTTPException(status_code=400, detail="Сделка уже не открыта")

        connection.execute(
            """
            UPDATE trades
            SET realized_pnl_usdt = ?
            WHERE id = ?
            """,
            (trade["realized_pnl_usdt"] + payload.realized_pnl_usdt, trade_id),
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
def revert_closed_trade(trade_id: int) -> dict[str, object]:
    with closing(get_connection()) as connection:
        trade = connection.execute(
            """
            SELECT id, exchange_id, status, symbol, realized_pnl_usdt
            FROM trades
            WHERE id = ?
            """,
            (trade_id,),
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
            WHERE id = ?
            """,
            (trade_id,),
        )
        connection.commit()

    return {"status": "reverted"}


@app.delete("/api/v1/trades/{trade_id}")
def delete_trade(trade_id: int) -> dict[str, object]:
    with closing(get_connection()) as connection:
        row = connection.execute(
            """
            SELECT id, status
            FROM trades
            WHERE id = ?
            """,
            (trade_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Сделка не найдена")

        connection.execute(
            """
            UPDATE trades
            SET status = 'deleted', deleted_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (trade_id,),
        )
        connection.commit()

    return {"status": "deleted"}


@app.get("/api/v1/balance-events")
def list_balance_events(
    exchange_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> dict[str, object]:
    parameters: list[object] = []
    where_clause = ""
    if exchange_id is not None:
        where_clause = "WHERE balance_events.exchange_id = ?"
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
def profit_calendar(year: int | None = None, month: int | None = None) -> dict[str, object]:
    today = date.today()
    target_year = year or today.year
    target_month = month or today.month

    if target_month < 1 or target_month > 12:
        raise HTTPException(status_code=400, detail="Некорректный месяц")

    days_in_month = monthrange(target_year, target_month)[1]
    start_date = date(target_year, target_month, 1)
    end_date = date(target_year, target_month, days_in_month)

    rows = fetch_all(
        """
        SELECT profit_date, pnl_usdt, source
        FROM daily_profit
        WHERE profit_date BETWEEN ? AND ?
        ORDER BY profit_date ASC
        """,
        (start_date.isoformat(), end_date.isoformat()),
    )
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
