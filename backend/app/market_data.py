from __future__ import annotations

import asyncio
import gzip
import json
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlencode

import requests
import websockets
from fastapi import WebSocket, WebSocketDisconnect


SUPPORTED_MARKET_EXCHANGES = {
    "aster",
    "binance",
    "bingx",
    "bitget",
    "bybit",
    "gate",
    "hyperliquid",
    "kucoin",
    "mexc",
    "okx",
}
SYMBOL_CACHE_TTL_SECONDS = 600
HTTP_TIMEOUT_SECONDS = 10
VISIBLE_BOOK_LEVELS = 5
FULL_SNAPSHOT_REFRESH_SECONDS = 2.0

BINANCE_REST_BASE = "https://fapi.binance.com"
BINANCE_FUTURES_STREAM_URLS = [
    "wss://fstream.binance.com/stream?streams={stream_symbol}@depth5@100ms",
    "wss://fstream.binance.com/ws/{stream_symbol}@depth5@100ms",
    "wss://fstream.binancefuture.com/ws/{stream_symbol}@depth5@100ms",
]

ASTER_REST_BASE = "https://fapi.asterdex.com"
ASTER_WS_BASE = "wss://fstream.asterdex.com"
BYBIT_REST_BASE = "https://api.bybit.com"
BYBIT_WS_URL = "wss://stream.bybit.com/v5/public/linear"
BINGX_REST_BASE = "https://open-api.bingx.com"
BINGX_WS_URL = "wss://open-api-ws.bingx.com/market"
BITGET_REST_BASE = "https://api.bitget.com"
BITGET_WS_URL = "wss://ws.bitget.com/v2/ws/public"
GATE_REST_BASE = "https://api.gateio.ws/api/v4"
GATE_WS_URL = "wss://fx-ws.gateio.ws/v4/ws/usdt"
HYPERLIQUID_REST_URL = "https://api.hyperliquid.xyz/info"
HYPERLIQUID_WS_URL = "wss://api.hyperliquid.xyz/ws"
KUCOIN_REST_BASE = "https://api-futures.kucoin.com"
KUCOIN_UA_REST_BASE = "https://api.kucoin.com"
KUCOIN_WS_URL = "wss://ws-api-futures.kucoin.com"
MEXC_REST_BASE = "https://api.mexc.com"
MEXC_WS_URL = "wss://contract.mexc.com/edge"
OKX_REST_BASE = "https://www.okx.com"
OKX_WS_URL = "wss://ws.okx.com:8443/ws/v5/public"


@dataclass
class SymbolCacheItem:
    expires_at: float
    symbols: list[dict[str, object]]


_symbol_cache: dict[str, SymbolCacheItem] = {}


def is_live_exchange(exchange_slug: str) -> bool:
    return exchange_slug.lower() in SUPPORTED_MARKET_EXCHANGES


def get_market_symbols(exchange_slug: str, query: str = "", limit: int = 30) -> dict[str, object]:
    normalized_exchange = normalize_exchange(exchange_slug)
    normalized_query = query.strip().upper()
    symbols = get_cached_symbols(normalized_exchange)

    if normalized_query:
        symbols = [
            symbol
            for symbol in symbols
            if normalized_query in str(symbol["symbol"]) or normalized_query in str(symbol["displayName"]).upper()
        ]

    return {
        "exchangeSlug": normalized_exchange,
        "symbols": symbols[:limit],
    }


async def get_market_snapshot(exchange_slug: str, symbol: str) -> dict[str, object]:
    normalized_exchange = normalize_exchange(exchange_slug)
    wire_symbol = resolve_wire_symbol(normalized_exchange, symbol)
    fetcher = SNAPSHOT_FETCHERS.get(normalized_exchange)
    if not fetcher:
        raise ValueError(f"Snapshot is not connected for {normalized_exchange}")
    return await asyncio.to_thread(fetcher, wire_symbol)


async def get_market_funding(exchange_slug: str, symbol: str) -> dict[str, object]:
    return await asyncio.to_thread(get_market_funding_sync, exchange_slug, symbol)


def get_market_funding_sync(exchange_slug: str, symbol: str) -> dict[str, object]:
    normalized_exchange = normalize_exchange(exchange_slug)
    wire_symbol = resolve_wire_symbol(normalized_exchange, symbol)
    fetcher = FUNDING_FETCHERS.get(normalized_exchange)
    if not fetcher:
        raise ValueError(f"Funding is not connected for {normalized_exchange}")
    return fetcher(wire_symbol)


def get_market_funding_history_sync(exchange_slug: str, symbol: str, start_time_ms: int, end_time_ms: int) -> list[dict[str, object]]:
    normalized_exchange = normalize_exchange(exchange_slug)
    wire_symbol = resolve_wire_symbol(normalized_exchange, symbol)
    fetcher = FUNDING_HISTORY_FETCHERS.get(normalized_exchange)
    if not fetcher:
        return []
    return fetcher(wire_symbol, start_time_ms, end_time_ms)


async def stream_market_data(websocket: WebSocket, exchange_slug: str, symbol: str) -> None:
    await websocket.accept()
    normalized_exchange = ""
    wire_symbol = ""

    try:
        normalized_exchange = normalize_exchange(exchange_slug)
        wire_symbol = resolve_wire_symbol(normalized_exchange, symbol)
        snapshot = build_snapshot(
            exchange_slug=normalized_exchange,
            wire_symbol=wire_symbol,
            last_price=0,
            bids=[],
            asks=[],
            source="ws",
        )
        await websocket.send_json({"type": "snapshot", **snapshot})
        stream_callback = STREAM_CALLBACKS[normalized_exchange]

        while True:
            try:
                await stream_callback(websocket, wire_symbol, snapshot)
            except WebSocketDisconnect:
                return
            except Exception:
                await safe_send_json(
                    websocket,
                    {
                        "type": "status",
                        "exchangeSlug": normalized_exchange,
                        "symbol": to_display_symbol(normalized_exchange, wire_symbol),
                        "message": "Переподключение live-данных",
                    },
                )
                await poll_snapshots(websocket, normalized_exchange, wire_symbol)
                await asyncio.sleep(1.5)
    except ValueError as caught_error:
        await safe_send_json(websocket, {"type": "error", "message": str(caught_error)})
        await websocket.close(code=1008)
    except WebSocketDisconnect:
        return
    except Exception as caught_error:
        await safe_send_json(
            websocket,
            {
                "type": "error",
                "exchangeSlug": normalized_exchange,
                "symbol": to_display_symbol(normalized_exchange, wire_symbol),
                "message": str(caught_error),
            },
        )
        await websocket.close(code=1011)


async def poll_snapshots(websocket: WebSocket, exchange_slug: str, wire_symbol: str, attempts: int = 5) -> None:
    for _ in range(attempts):
        try:
            snapshot = await get_market_snapshot(exchange_slug, wire_symbol)
            await websocket.send_json({"type": "snapshot", **snapshot})
        except WebSocketDisconnect:
            raise
        except Exception:
            await safe_send_json(
                websocket,
                {
                    "type": "status",
                    "exchangeSlug": exchange_slug,
                    "symbol": to_display_symbol(exchange_slug, wire_symbol),
                    "message": "Ожидание данных",
                },
            )
        await asyncio.sleep(1)


def normalize_exchange(exchange_slug: str) -> str:
    normalized = exchange_slug.strip().lower()
    if normalized not in SUPPORTED_MARKET_EXCHANGES:
        raise ValueError("Live market data is connected only for configured futures exchanges")
    return normalized


def get_cached_symbols(exchange_slug: str) -> list[dict[str, object]]:
    cache_item = _symbol_cache.get(exchange_slug)
    now = time.time()
    if cache_item and cache_item.expires_at > now:
        return cache_item.symbols

    fetcher = SYMBOL_FETCHERS[exchange_slug]
    symbols = fetcher()
    _symbol_cache[exchange_slug] = SymbolCacheItem(expires_at=now + SYMBOL_CACHE_TTL_SECONDS, symbols=symbols)
    return symbols


def fetch_json(url: str) -> Any:
    try:
        response = requests.get(url, headers={"User-Agent": "ProfitsNLosses/0.1"}, timeout=HTTP_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as caught_error:
        raise RuntimeError(f"Market data request failed: {caught_error}") from caught_error


def post_json(url: str, payload: dict[str, object]) -> Any:
    try:
        response = requests.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json", "User-Agent": "ProfitsNLosses/0.1"},
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as caught_error:
        raise RuntimeError(f"Market data request failed: {caught_error}") from caught_error


def fetch_first_successful_json(urls: list[str]) -> Any:
    last_error: Exception | None = None
    for url in urls:
        try:
            return fetch_json(url)
        except Exception as caught_error:
            last_error = caught_error
    raise RuntimeError(f"All market data requests failed: {last_error}")


def make_symbol(exchange_slug: str, symbol: str, wire_symbol: str, base_asset: str, quote_asset: str = "USDT") -> dict[str, object]:
    return {
        "exchangeSlug": exchange_slug,
        "symbol": symbol,
        "wireSymbol": wire_symbol,
        "baseAsset": base_asset,
        "quoteAsset": quote_asset,
        "displayName": f"{symbol}/{quote_asset}",
    }


def fetch_binance_symbols() -> list[dict[str, object]]:
    payload = fetch_json(f"{BINANCE_REST_BASE}/fapi/v1/exchangeInfo")
    return parse_binance_like_symbols("binance", payload)


def fetch_aster_symbols() -> list[dict[str, object]]:
    payload = fetch_json(f"{ASTER_REST_BASE}/fapi/v1/exchangeInfo")
    return parse_binance_like_symbols("aster", payload)


def parse_binance_like_symbols(exchange_slug: str, payload: dict[str, Any]) -> list[dict[str, object]]:
    symbols = []
    for item in payload.get("symbols", []):
        if item.get("status") != "TRADING" or item.get("quoteAsset") != "USDT":
            continue
        contract_type = str(item.get("contractType") or "PERPETUAL").upper()
        if "PERPETUAL" not in contract_type:
            continue
        base_asset = str(item["baseAsset"])
        wire_symbol = str(item["symbol"])
        symbols.append(make_symbol(exchange_slug, base_asset, wire_symbol, base_asset))
    return sorted(symbols, key=lambda item: str(item["symbol"]))


def fetch_bybit_symbols() -> list[dict[str, object]]:
    params = urlencode({"category": "linear", "limit": 1000})
    payload = fetch_json(f"{BYBIT_REST_BASE}/v5/market/instruments-info?{params}")
    symbols = []
    for item in payload.get("result", {}).get("list", []):
        if item.get("status") != "Trading" or item.get("quoteCoin") != "USDT":
            continue
        contract_type = str(item.get("contractType") or "")
        if "Perpetual" not in contract_type:
            continue
        base_asset = str(item.get("baseCoin"))
        wire_symbol = str(item.get("symbol"))
        symbols.append(make_symbol("bybit", base_asset, wire_symbol, base_asset))
    return sorted(symbols, key=lambda item: str(item["symbol"]))


def fetch_bingx_symbols() -> list[dict[str, object]]:
    payload = fetch_json(f"{BINGX_REST_BASE}/openApi/swap/v2/quote/contracts")
    data = payload.get("data", [])
    symbols = []
    for item in data if isinstance(data, list) else []:
        symbol = str(item.get("symbol") or "")
        if not symbol.endswith("-USDT"):
            continue
        if str(item.get("status", "TRADING")).upper() not in {"TRADING", "1", "NORMAL"}:
            continue
        base_asset = symbol.removesuffix("-USDT")
        symbols.append(make_symbol("bingx", base_asset, symbol, base_asset))
    return sorted(symbols, key=lambda item: str(item["symbol"]))


def fetch_bitget_symbols() -> list[dict[str, object]]:
    params = urlencode({"productType": "usdt-futures"})
    payload = fetch_json(f"{BITGET_REST_BASE}/api/v2/mix/market/contracts?{params}")
    symbols = []
    for item in payload.get("data", []):
        if item.get("quoteCoin") != "USDT" or item.get("symbolStatus") not in ("normal", "listed"):
            continue
        if item.get("symbolType") and item.get("symbolType") != "perpetual":
            continue
        base_asset = str(item.get("baseCoin"))
        wire_symbol = str(item.get("symbol"))
        symbols.append(make_symbol("bitget", base_asset, wire_symbol, base_asset))
    return sorted(symbols, key=lambda item: str(item["symbol"]))


def fetch_gate_symbols() -> list[dict[str, object]]:
    payload = fetch_json(f"{GATE_REST_BASE}/futures/usdt/contracts")
    symbols = []
    for item in payload if isinstance(payload, list) else []:
        wire_symbol = str(item.get("name") or "")
        if not wire_symbol.endswith("_USDT") or item.get("in_delisting") is True:
            continue
        base_asset = wire_symbol.removesuffix("_USDT")
        symbols.append(make_symbol("gate", base_asset, wire_symbol, base_asset))
    return sorted(symbols, key=lambda item: str(item["symbol"]))


def fetch_hyperliquid_symbols() -> list[dict[str, object]]:
    payload = post_json(HYPERLIQUID_REST_URL, {"type": "meta"})
    symbols = []
    for item in payload.get("universe", []):
        if item.get("isDelisted"):
            continue
        base_asset = str(item.get("name") or "")
        if base_asset:
            symbols.append(make_symbol("hyperliquid", base_asset, base_asset, base_asset))
    return sorted(symbols, key=lambda item: str(item["symbol"]))


def fetch_kucoin_symbols() -> list[dict[str, object]]:
    payload = fetch_json(f"{KUCOIN_REST_BASE}/api/v1/contracts/active")
    symbols = []
    for item in payload.get("data", []):
        if item.get("quoteCurrency") != "USDT":
            continue
        if item.get("status") not in (None, "Open"):
            continue
        wire_symbol = str(item.get("symbol") or "")
        base_asset = str(item.get("baseCurrency") or wire_symbol.removesuffix("USDTM"))
        display_symbol = "BTC" if base_asset == "XBT" else base_asset
        symbols.append(make_symbol("kucoin", display_symbol, wire_symbol, base_asset))
    return sorted(symbols, key=lambda item: str(item["symbol"]))


def fetch_mexc_symbols() -> list[dict[str, object]]:
    payload = fetch_first_successful_json(
        [
            f"{MEXC_REST_BASE}/api/v1/contract/detail",
            f"{MEXC_REST_BASE}/api/v1/contract/detail/country",
        ]
    )
    data = payload.get("data", [])
    if isinstance(data, dict):
        data = [data]

    symbols = []
    for item in data:
        if not isinstance(item, dict):
            continue
        if item.get("state") not in (None, 0):
            continue
        if item.get("quoteCoin") != "USDT":
            continue
        base_asset = str(item.get("baseCoin") or item.get("symbol", "").replace("_USDT", ""))
        wire_symbol = str(item.get("symbol") or f"{base_asset}_USDT")
        symbols.append(make_symbol("mexc", base_asset, wire_symbol, base_asset))
    return sorted(symbols, key=lambda item: str(item["symbol"]))


def fetch_okx_symbols() -> list[dict[str, object]]:
    payload = fetch_json(f"{OKX_REST_BASE}/api/v5/public/instruments?{urlencode({'instType': 'SWAP'})}")
    symbols = []
    for item in payload.get("data", []):
        if item.get("state") != "live" or item.get("settleCcy") != "USDT":
            continue
        wire_symbol = str(item.get("instId") or "")
        if not wire_symbol.endswith("-USDT-SWAP"):
            continue
        base_asset = wire_symbol.removesuffix("-USDT-SWAP")
        symbols.append(make_symbol("okx", base_asset, wire_symbol, base_asset))
    return sorted(symbols, key=lambda item: str(item["symbol"]))


def resolve_wire_symbol(exchange_slug: str, symbol: str) -> str:
    normalized_symbol = symbol.strip().upper().replace("/", "").replace("-", "_")
    if exchange_slug in {"binance", "bybit", "aster", "bitget"}:
        return normalized_symbol.replace("_", "") if normalized_symbol.endswith("USDT") else f"{normalized_symbol}USDT"
    if exchange_slug == "okx":
        if normalized_symbol.endswith("_USDT_SWAP"):
            return normalized_symbol.replace("_", "-")
        if normalized_symbol.endswith("USDT"):
            return f"{normalized_symbol.removesuffix('USDT')}-USDT-SWAP"
        return f"{normalized_symbol}-USDT-SWAP"
    if exchange_slug in {"gate", "mexc"}:
        if normalized_symbol.endswith("_USDT"):
            return normalized_symbol
        if normalized_symbol.endswith("USDT"):
            return f"{normalized_symbol.removesuffix('USDT')}_USDT"
        return f"{normalized_symbol}_USDT"
    if exchange_slug == "bingx":
        if normalized_symbol.endswith("_USDT"):
            return normalized_symbol.replace("_", "-")
        if normalized_symbol.endswith("USDT"):
            return f"{normalized_symbol.removesuffix('USDT')}-USDT"
        return f"{normalized_symbol}-USDT"
    if exchange_slug == "kucoin":
        if normalized_symbol.endswith("USDTM"):
            return normalized_symbol
        base_asset = "XBT" if normalized_symbol in {"BTC", "XBT"} else normalized_symbol
        return f"{base_asset}USDTM"
    if exchange_slug == "hyperliquid":
        return normalized_symbol.removesuffix("USDT")
    return normalized_symbol


def to_display_symbol(exchange_slug: str, wire_symbol: str) -> str:
    if exchange_slug in {"binance", "bybit", "aster", "bitget"} and wire_symbol.endswith("USDT"):
        return wire_symbol.removesuffix("USDT")
    if exchange_slug in {"gate", "mexc"} and wire_symbol.endswith("_USDT"):
        return wire_symbol.removesuffix("_USDT")
    if exchange_slug == "bingx" and wire_symbol.endswith("-USDT"):
        return wire_symbol.removesuffix("-USDT")
    if exchange_slug == "kucoin" and wire_symbol.endswith("USDTM"):
        base_asset = wire_symbol.removesuffix("USDTM")
        return "BTC" if base_asset == "XBT" else base_asset
    if exchange_slug == "okx" and wire_symbol.endswith("-USDT-SWAP"):
        return wire_symbol.removesuffix("-USDT-SWAP")
    return wire_symbol


def normalize_level(row: Any) -> dict[str, float]:
    if isinstance(row, dict):
        price = row.get("price") or row.get("px") or row.get("p")
        size = row.get("size") or row.get("sz") or row.get("s")
        return {"price": float(price), "size": float(size)}
    return {
        "price": float(row[0]),
        "size": float(row[1]),
    }


def normalize_levels(rows: Any) -> list[dict[str, float]]:
    if not isinstance(rows, list):
        return []
    normalized = []
    for row in rows:
        try:
            normalized.append(normalize_level(row))
        except (TypeError, ValueError):
            continue
    return normalized


def sorted_book(bids: list[dict[str, float]], asks: list[dict[str, float]]) -> tuple[list[dict[str, float]], list[dict[str, float]]]:
    return (
        sorted(dedupe_levels(bids), key=lambda row: row["price"], reverse=True)[:VISIBLE_BOOK_LEVELS],
        sorted(dedupe_levels(asks), key=lambda row: row["price"])[:VISIBLE_BOOK_LEVELS],
    )


def dedupe_levels(rows: list[dict[str, float]]) -> list[dict[str, float]]:
    levels: dict[float, float] = {}
    for row in rows:
        price = row["price"]
        size = row["size"]
        if size <= 0:
            levels.pop(price, None)
        else:
            levels[price] = size
    return [{"price": price, "size": size} for price, size in levels.items()]


def build_snapshot(
    exchange_slug: str,
    wire_symbol: str,
    last_price: float,
    bids: list[dict[str, float]],
    asks: list[dict[str, float]],
    source: str,
    timestamp: int | None = None,
) -> dict[str, object]:
    sorted_bids, sorted_asks = sorted_book(bids, asks)
    best_bid = sorted_bids[0]["price"] if sorted_bids else None
    best_ask = sorted_asks[0]["price"] if sorted_asks else None
    resolved_last_price = last_price or ((best_bid + best_ask) / 2 if best_bid and best_ask else best_bid or best_ask or 0)
    return {
        "exchangeSlug": exchange_slug,
        "symbol": to_display_symbol(exchange_slug, wire_symbol),
        "wireSymbol": wire_symbol,
        "lastPrice": resolved_last_price,
        "bestBid": best_bid,
        "bestAsk": best_ask,
        "bids": sorted_bids,
        "asks": sorted_asks,
        "source": source,
        "updatedAt": timestamp or int(time.time() * 1000),
    }


def fetch_binance_snapshot(wire_symbol: str) -> dict[str, object]:
    return fetch_binance_like_snapshot("binance", BINANCE_REST_BASE, wire_symbol)


def fetch_aster_snapshot(wire_symbol: str) -> dict[str, object]:
    return fetch_binance_like_snapshot("aster", ASTER_REST_BASE, wire_symbol)


def fetch_binance_like_snapshot(exchange_slug: str, rest_base: str, wire_symbol: str) -> dict[str, object]:
    depth = fetch_json(f"{rest_base}/fapi/v1/depth?{urlencode({'symbol': wire_symbol, 'limit': 20})}")
    ticker = fetch_json(f"{rest_base}/fapi/v1/ticker/24hr?{urlencode({'symbol': wire_symbol})}")
    return build_snapshot(
        exchange_slug=exchange_slug,
        wire_symbol=wire_symbol,
        last_price=float(ticker.get("lastPrice") or 0),
        bids=normalize_levels(depth.get("bids", [])),
        asks=normalize_levels(depth.get("asks", [])),
        source="rest",
    )


def fetch_bybit_snapshot(wire_symbol: str) -> dict[str, object]:
    depth = fetch_json(f"{BYBIT_REST_BASE}/v5/market/orderbook?{urlencode({'category': 'linear', 'symbol': wire_symbol, 'limit': 50})}")
    ticker = fetch_json(f"{BYBIT_REST_BASE}/v5/market/tickers?{urlencode({'category': 'linear', 'symbol': wire_symbol})}")
    data = depth.get("result", {})
    ticker_item = first_item(ticker.get("result", {}).get("list", []))
    return build_snapshot("bybit", wire_symbol, float(ticker_item.get("lastPrice") or 0), normalize_levels(data.get("b", [])), normalize_levels(data.get("a", [])), "rest", data.get("ts"))


def fetch_bingx_snapshot(wire_symbol: str) -> dict[str, object]:
    depth = fetch_json(f"{BINGX_REST_BASE}/openApi/swap/v2/quote/depth?{urlencode({'symbol': wire_symbol, 'limit': 20})}")
    ticker = fetch_json(f"{BINGX_REST_BASE}/openApi/swap/v2/quote/ticker?{urlencode({'symbol': wire_symbol})}")
    depth_data = depth.get("data", {})
    ticker_data = ticker.get("data", {})
    if isinstance(ticker_data, list):
        ticker_data = first_item(ticker_data)
    return build_snapshot("bingx", wire_symbol, float(ticker_data.get("lastPrice") or ticker_data.get("last") or 0), normalize_levels(depth_data.get("bids", [])), normalize_levels(depth_data.get("asks", [])), "rest", depth_data.get("ts"))


def fetch_bitget_snapshot(wire_symbol: str) -> dict[str, object]:
    depth = fetch_json(f"{BITGET_REST_BASE}/api/v3/market/orderbook?{urlencode({'category': 'USDT-FUTURES', 'symbol': wire_symbol, 'limit': 20})}")
    ticker = fetch_json(f"{BITGET_REST_BASE}/api/v2/mix/market/ticker?{urlencode({'productType': 'usdt-futures', 'symbol': wire_symbol})}")
    depth_data = depth.get("data", {})
    ticker_data = ticker.get("data", {})
    if isinstance(ticker_data, list):
        ticker_data = first_item(ticker_data)
    return build_snapshot("bitget", wire_symbol, float(ticker_data.get("lastPr") or ticker_data.get("last") or 0), normalize_levels(depth_data.get("b", [])), normalize_levels(depth_data.get("a", [])), "rest", depth_data.get("ts"))


def fetch_gate_snapshot(wire_symbol: str) -> dict[str, object]:
    depth = fetch_json(f"{GATE_REST_BASE}/futures/usdt/order_book?{urlencode({'contract': wire_symbol, 'limit': 20})}")
    tickers = fetch_json(f"{GATE_REST_BASE}/futures/usdt/tickers?{urlencode({'contract': wire_symbol})}")
    ticker = first_item(tickers if isinstance(tickers, list) else [])
    return build_snapshot("gate", wire_symbol, float(ticker.get("last") or 0), normalize_levels(depth.get("bids", [])), normalize_levels(depth.get("asks", [])), "rest", depth.get("t"))


def fetch_hyperliquid_snapshot(wire_symbol: str) -> dict[str, object]:
    depth = post_json(HYPERLIQUID_REST_URL, {"type": "l2Book", "coin": wire_symbol})
    mids = post_json(HYPERLIQUID_REST_URL, {"type": "allMids"})
    levels = depth.get("levels", [[], []])
    return build_snapshot("hyperliquid", wire_symbol, float(mids.get(wire_symbol) or 0), normalize_levels(levels[0] if levels else []), normalize_levels(levels[1] if len(levels) > 1 else []), "rest", depth.get("time"))


def fetch_kucoin_snapshot(wire_symbol: str) -> dict[str, object]:
    depth = fetch_json(f"{KUCOIN_REST_BASE}/api/v1/level2/snapshot?{urlencode({'symbol': wire_symbol})}")
    ticker = fetch_json(f"{KUCOIN_REST_BASE}/api/v1/ticker?{urlencode({'symbol': wire_symbol})}")
    depth_data = depth.get("data", {})
    ticker_data = ticker.get("data", {})
    return build_snapshot("kucoin", wire_symbol, float(ticker_data.get("price") or ticker_data.get("last") or 0), normalize_levels(depth_data.get("bids", [])), normalize_levels(depth_data.get("asks", [])), "rest", depth_data.get("ts"))


def fetch_mexc_snapshot(wire_symbol: str) -> dict[str, object]:
    depth = fetch_json(f"{MEXC_REST_BASE}/api/v1/contract/depth/{wire_symbol}?{urlencode({'limit': 20})}")
    ticker = fetch_json(f"{MEXC_REST_BASE}/api/v1/contract/ticker?{urlencode({'symbol': wire_symbol})}")
    depth_data = depth.get("data", {})
    ticker_data = ticker.get("data", {})
    if isinstance(ticker_data, list):
        ticker_data = first_item(ticker_data)
    return build_snapshot(
        exchange_slug="mexc",
        wire_symbol=wire_symbol,
        last_price=float(ticker_data.get("lastPrice") or 0),
        bids=normalize_levels(depth_data.get("bids", [])),
        asks=normalize_levels(depth_data.get("asks", [])),
        source="rest",
        timestamp=depth_data.get("timestamp") or ticker_data.get("timestamp"),
    )


def fetch_okx_snapshot(wire_symbol: str) -> dict[str, object]:
    depth = fetch_json(f"{OKX_REST_BASE}/api/v5/market/books?{urlencode({'instId': wire_symbol, 'sz': 20})}")
    ticker = fetch_json(f"{OKX_REST_BASE}/api/v5/market/ticker?{urlencode({'instId': wire_symbol})}")
    depth_data = first_item(depth.get("data", []))
    ticker_data = first_item(ticker.get("data", []))
    return build_snapshot(
        exchange_slug="okx",
        wire_symbol=wire_symbol,
        last_price=float(ticker_data.get("last") or 0),
        bids=normalize_levels(depth_data.get("bids") or depth_data.get("b") or []),
        asks=normalize_levels(depth_data.get("asks") or depth_data.get("a") or []),
        source="rest",
        timestamp=depth_data.get("ts") or ticker_data.get("ts"),
    )


def parse_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_timestamp_ms(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        timestamp = float(value)
    except (TypeError, ValueError):
        return None
    if timestamp <= 0:
        return None
    return int(timestamp * 1000) if timestamp < 10_000_000_000 else int(timestamp)


def next_interval_timestamp_ms(hours: int = 8) -> int:
    interval_ms = hours * 60 * 60 * 1000
    now_ms = int(time.time() * 1000)
    return ((now_ms // interval_ms) + 1) * interval_ms


def next_hour_timestamp_ms() -> int:
    now_ms = int(time.time() * 1000)
    hour_ms = 60 * 60 * 1000
    return ((now_ms // hour_ms) + 1) * hour_ms


def build_funding(exchange_slug: str, wire_symbol: str, funding_rate: Any, next_funding_time: Any = None, interval_hours: int = 8) -> dict[str, object]:
    next_time = parse_timestamp_ms(next_funding_time) or next_interval_timestamp_ms(interval_hours)
    return {
        "exchangeSlug": exchange_slug,
        "symbol": to_display_symbol(exchange_slug, wire_symbol),
        "wireSymbol": wire_symbol,
        "fundingRate": parse_float(funding_rate),
        "nextFundingTime": next_time,
        "updatedAt": int(time.time() * 1000),
    }


def fetch_binance_funding(wire_symbol: str) -> dict[str, object]:
    return fetch_binance_like_funding("binance", BINANCE_REST_BASE, wire_symbol)


def fetch_aster_funding(wire_symbol: str) -> dict[str, object]:
    return fetch_binance_like_funding("aster", ASTER_REST_BASE, wire_symbol)


def fetch_binance_like_funding(exchange_slug: str, rest_base: str, wire_symbol: str) -> dict[str, object]:
    payload = fetch_json(f"{rest_base}/fapi/v1/premiumIndex?{urlencode({'symbol': wire_symbol})}")
    return build_funding(exchange_slug, wire_symbol, payload.get("lastFundingRate"), payload.get("nextFundingTime"))


def fetch_bybit_funding(wire_symbol: str) -> dict[str, object]:
    payload = fetch_json(f"{BYBIT_REST_BASE}/v5/market/tickers?{urlencode({'category': 'linear', 'symbol': wire_symbol})}")
    ticker = first_item(payload.get("result", {}).get("list", []))
    return build_funding("bybit", wire_symbol, ticker.get("fundingRate"), ticker.get("nextFundingTime"))


def fetch_binance_funding_history(wire_symbol: str, start_time_ms: int, end_time_ms: int) -> list[dict[str, object]]:
    return fetch_binance_like_funding_history("binance", BINANCE_REST_BASE, wire_symbol, start_time_ms, end_time_ms)


def fetch_aster_funding_history(wire_symbol: str, start_time_ms: int, end_time_ms: int) -> list[dict[str, object]]:
    return fetch_binance_like_funding_history("aster", ASTER_REST_BASE, wire_symbol, start_time_ms, end_time_ms)


def fetch_binance_like_funding_history(exchange_slug: str, rest_base: str, wire_symbol: str, start_time_ms: int, end_time_ms: int) -> list[dict[str, object]]:
    params = urlencode({"symbol": wire_symbol, "startTime": start_time_ms, "endTime": end_time_ms, "limit": 1000})
    payload = fetch_json(f"{rest_base}/fapi/v1/fundingRate?{params}")
    rows = payload if isinstance(payload, list) else []
    return normalize_funding_history(exchange_slug, wire_symbol, rows, ("fundingRate",), ("fundingTime",))


def fetch_bybit_funding_history(wire_symbol: str, start_time_ms: int, end_time_ms: int) -> list[dict[str, object]]:
    params = urlencode({"category": "linear", "symbol": wire_symbol, "startTime": start_time_ms, "endTime": end_time_ms, "limit": 200})
    payload = fetch_json(f"{BYBIT_REST_BASE}/v5/market/funding/history?{params}")
    rows = payload.get("result", {}).get("list", [])
    return normalize_funding_history("bybit", wire_symbol, rows, ("fundingRate",), ("fundingRateTimestamp",))


def fetch_bingx_funding_history(wire_symbol: str, start_time_ms: int, end_time_ms: int) -> list[dict[str, object]]:
    params = urlencode({"symbol": wire_symbol, "startTime": start_time_ms, "endTime": end_time_ms, "limit": 1000})
    payload = fetch_json(f"{BINGX_REST_BASE}/openApi/swap/v2/quote/fundingRate?{params}")
    data = payload.get("data", [])
    rows = data if isinstance(data, list) else [data] if isinstance(data, dict) else []
    return normalize_funding_history(
        "bingx",
        wire_symbol,
        rows,
        ("fundingRate", "lastFundingRate", "rate"),
        ("fundingTime", "time", "settleTime"),
    )


def fetch_bitget_funding_history(wire_symbol: str, start_time_ms: int, end_time_ms: int) -> list[dict[str, object]]:
    params = urlencode({"productType": "USDT-FUTURES", "symbol": wire_symbol, "startTime": start_time_ms, "endTime": end_time_ms, "pageSize": 100})
    payload = fetch_json(f"{BITGET_REST_BASE}/api/v2/mix/market/history-fund-rate?{params}")
    data = payload.get("data", [])
    rows = data if isinstance(data, list) else []
    return normalize_funding_history("bitget", wire_symbol, rows, ("fundingRate",), ("fundingTime", "time"))


def fetch_gate_funding_history(wire_symbol: str, start_time_ms: int, end_time_ms: int) -> list[dict[str, object]]:
    params = urlencode({"contract": wire_symbol, "from": start_time_ms // 1000, "to": end_time_ms // 1000, "limit": 100})
    payload = fetch_json(f"{GATE_REST_BASE}/futures/usdt/funding_rate?{params}")
    rows = payload if isinstance(payload, list) else []
    return normalize_funding_history("gate", wire_symbol, rows, ("r", "rate", "funding_rate"), ("t", "time", "funding_time"))


def fetch_hyperliquid_funding_history(wire_symbol: str, start_time_ms: int, end_time_ms: int) -> list[dict[str, object]]:
    payload = post_json(
        HYPERLIQUID_REST_URL,
        {"type": "fundingHistory", "coin": wire_symbol, "startTime": start_time_ms, "endTime": end_time_ms},
    )
    rows = payload if isinstance(payload, list) else []
    return normalize_funding_history("hyperliquid", wire_symbol, rows, ("fundingRate", "rate"), ("time", "fundingTime"))


def fetch_kucoin_funding_history(wire_symbol: str, start_time_ms: int, end_time_ms: int) -> list[dict[str, object]]:
    params = urlencode({"symbol": wire_symbol, "from": start_time_ms, "to": end_time_ms})
    payload = fetch_json(f"{KUCOIN_REST_BASE}/api/v1/contract/funding-rates?{params}")
    data = payload.get("data", [])
    rows = data if isinstance(data, list) else []
    return normalize_funding_history(
        "kucoin",
        wire_symbol,
        rows,
        ("fundingRate", "fundingFeeRate", "value"),
        ("timepoint", "timePoint", "fundingTime", "time"),
    )


def fetch_mexc_funding_history(wire_symbol: str, start_time_ms: int, end_time_ms: int) -> list[dict[str, object]]:
    params = urlencode({"symbol": wire_symbol, "page_num": 1, "page_size": 100, "start_time": start_time_ms, "end_time": end_time_ms})
    payload = fetch_json(f"{MEXC_REST_BASE}/api/v1/contract/funding_rate/history?{params}")
    data = payload.get("data", [])
    if isinstance(data, dict):
        rows = data.get("resultList") or data.get("records") or data.get("list") or []
    else:
        rows = data
    return normalize_funding_history(
        "mexc",
        wire_symbol,
        rows if isinstance(rows, list) else [],
        ("fundingRate", "rate"),
        ("settleTime", "fundingTime", "time"),
    )


def fetch_okx_funding_history(wire_symbol: str, start_time_ms: int, end_time_ms: int) -> list[dict[str, object]]:
    params = urlencode({"instId": wire_symbol, "before": end_time_ms, "after": start_time_ms, "limit": 100})
    payload = fetch_json(f"{OKX_REST_BASE}/api/v5/public/funding-rate-history?{params}")
    rows = payload.get("data", [])
    return normalize_funding_history("okx", wire_symbol, rows, ("fundingRate",), ("fundingTime",))


def funding_history_value(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = row.get(key)
        if value is not None and value != "":
            return value
    return None


def normalize_funding_history(
    exchange_slug: str,
    wire_symbol: str,
    rows: list[Any],
    rate_key: tuple[str, ...],
    time_key: tuple[str, ...],
) -> list[dict[str, object]]:
    history = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        funding_time = parse_timestamp_ms(funding_history_value(row, time_key))
        if not funding_time:
            continue
        history.append(
            {
                "exchangeSlug": exchange_slug,
                "symbol": to_display_symbol(exchange_slug, wire_symbol),
                "wireSymbol": wire_symbol,
                "fundingRate": parse_float(funding_history_value(row, rate_key)),
                "fundingTime": funding_time,
            }
        )
    return sorted(history, key=lambda item: int(item["fundingTime"]))


def fetch_bingx_funding(wire_symbol: str) -> dict[str, object]:
    payload = fetch_json(f"{BINGX_REST_BASE}/openApi/swap/v2/quote/premiumIndex?{urlencode({'symbol': wire_symbol})}")
    data = payload.get("data", {})
    if isinstance(data, list):
        data = first_item(data)
    if not isinstance(data, dict):
        data = {}
    return build_funding(
        "bingx",
        wire_symbol,
        data.get("lastFundingRate") or data.get("fundingRate"),
        data.get("nextFundingTime") or data.get("nextSettleTime"),
        interval_hours=int(parse_float(data.get("fundingIntervalHours"), 8)),
    )


def fetch_bitget_funding(wire_symbol: str) -> dict[str, object]:
    ticker = fetch_json(f"{BITGET_REST_BASE}/api/v2/mix/market/ticker?{urlencode({'productType': 'usdt-futures', 'symbol': wire_symbol})}")
    data = ticker.get("data", {})
    if isinstance(data, list):
        data = first_item(data)
    if not isinstance(data, dict):
        data = {}
    funding = fetch_json(f"{BITGET_REST_BASE}/api/v2/mix/market/current-fund-rate?{urlencode({'productType': 'usdt-futures', 'symbol': wire_symbol})}")
    funding_data = funding.get("data", {})
    if isinstance(funding_data, list):
        funding_data = first_item(funding_data)
    if isinstance(funding_data, dict):
        data = {**data, **funding_data}
    return build_funding(
        "bitget",
        wire_symbol,
        data.get("fundingRate"),
        data.get("nextUpdate") or data.get("nextFundingTime") or data.get("fundingTime"),
        interval_hours=int(parse_float(data.get("fundingRateInterval"), 8)),
    )


def fetch_gate_funding(wire_symbol: str) -> dict[str, object]:
    contract = fetch_json(f"{GATE_REST_BASE}/futures/usdt/contracts/{wire_symbol}")
    return build_funding("gate", wire_symbol, contract.get("funding_rate"), contract.get("funding_next_apply"))


def fetch_hyperliquid_funding(wire_symbol: str) -> dict[str, object]:
    payload = post_json(HYPERLIQUID_REST_URL, {"type": "metaAndAssetCtxs"})
    universe = payload[0].get("universe", []) if isinstance(payload, list) and payload else []
    contexts = payload[1] if isinstance(payload, list) and len(payload) > 1 else []
    funding_rate = 0.0
    for index, item in enumerate(universe):
        if item.get("name") == wire_symbol and index < len(contexts):
            funding_rate = parse_float(contexts[index].get("funding"))
            break
    return build_funding("hyperliquid", wire_symbol, funding_rate, next_hour_timestamp_ms(), interval_hours=1)


def fetch_kucoin_funding(wire_symbol: str) -> dict[str, object]:
    payload = fetch_json(f"{KUCOIN_UA_REST_BASE}/api/ua/v1/market/funding-rate?{urlencode({'symbol': wire_symbol})}")
    data = payload.get("data", {})
    if not isinstance(data, dict):
        data = {}
    funding_rate = data.get("nextFundingRate") or data.get("fundingFeeRate") or data.get("fundingRate")
    next_time = data.get("fundingTime") or data.get("nextFundingRateTime") or data.get("nextFundingTime")
    interval_ms = parse_float(data.get("currentGranularity") or data.get("newGranularity"), 28_800_000)
    return build_funding("kucoin", wire_symbol, funding_rate, next_time, interval_hours=max(int(interval_ms // 3_600_000), 1))


def fetch_mexc_funding(wire_symbol: str) -> dict[str, object]:
    ticker = fetch_json(f"{MEXC_REST_BASE}/api/v1/contract/ticker?{urlencode({'symbol': wire_symbol})}")
    data = ticker.get("data", {})
    if isinstance(data, list):
        data = first_item(data)
    if not isinstance(data, dict):
        data = {}
    if data.get("fundingRate") is None:
        funding = fetch_json(f"{MEXC_REST_BASE}/api/v1/contract/funding_rate/{wire_symbol}")
        funding_data = funding.get("data", {})
        if isinstance(funding_data, dict):
            data = {**funding_data, **data}
    return build_funding("mexc", wire_symbol, data.get("fundingRate"), data.get("nextSettleTime") or data.get("nextFundingTime"))


def fetch_okx_funding(wire_symbol: str) -> dict[str, object]:
    payload = fetch_json(f"{OKX_REST_BASE}/api/v5/public/funding-rate?{urlencode({'instId': wire_symbol})}")
    data = first_item(payload.get("data", []))
    return build_funding("okx", wire_symbol, data.get("fundingRate"), data.get("nextFundingTime"))


def first_item(rows: list[Any]) -> dict[str, Any]:
    item = rows[0] if rows else {}
    return item if isinstance(item, dict) else {}


async def stream_binance(websocket: WebSocket, wire_symbol: str, snapshot: dict[str, object]) -> None:
    await stream_binance_like(websocket, "binance", wire_symbol, snapshot, BINANCE_FUTURES_STREAM_URLS)


async def stream_aster(websocket: WebSocket, wire_symbol: str, snapshot: dict[str, object]) -> None:
    stream_symbol = wire_symbol.lower()
    await stream_binance_like(
        websocket,
        "aster",
        wire_symbol,
        snapshot,
        [f"{ASTER_WS_BASE}/stream?streams={stream_symbol}@depth5@100ms", f"{ASTER_WS_BASE}/ws/{stream_symbol}@depth5@100ms"],
    )


async def stream_binance_like(websocket: WebSocket, exchange_slug: str, wire_symbol: str, snapshot: dict[str, object], stream_urls: list[str]) -> None:
    stream_symbol = wire_symbol.lower()
    last_error: Exception | None = None

    for stream_template in stream_urls:
        stream_url = stream_template.format(stream_symbol=stream_symbol)
        bids = list(snapshot["bids"])
        asks = list(snapshot["asks"])
        last_price = float(snapshot["lastPrice"])

        try:
            await send_status(websocket, exchange_slug, wire_symbol)
            async with websockets.connect(stream_url, ping_interval=20, ping_timeout=20, open_timeout=5) as upstream:
                async for raw_message in upstream:
                    payload = json.loads(raw_message)
                    data = payload.get("data", payload)
                    if "b" in data and "a" in data:
                        bids = normalize_levels(data.get("b", []))
                        asks = normalize_levels(data.get("a", []))
                    elif "bids" in data and "asks" in data:
                        bids = normalize_levels(data.get("bids", []))
                        asks = normalize_levels(data.get("asks", []))
                    else:
                        continue
                    await websocket.send_json(build_snapshot(exchange_slug, wire_symbol, last_price, bids, asks, "ws", data.get("E")))
        except WebSocketDisconnect:
            raise
        except Exception as caught_error:
            last_error = caught_error

    raise RuntimeError(f"{exchange_slug} futures stream unavailable: {last_error}")


async def stream_bybit(websocket: WebSocket, wire_symbol: str, snapshot: dict[str, object]) -> None:
    bids = {row["price"]: row["size"] for row in snapshot["bids"]}
    asks = {row["price"]: row["size"] for row in snapshot["asks"]}
    last_price = float(snapshot["lastPrice"])

    await send_status(websocket, "bybit", wire_symbol)
    async with websockets.connect(BYBIT_WS_URL, ping_interval=20, ping_timeout=20, open_timeout=5) as upstream:
        await upstream.send(json.dumps({"op": "subscribe", "args": [f"orderbook.50.{wire_symbol}", f"tickers.{wire_symbol}"]}))
        async for raw_message in upstream:
            payload = json.loads(raw_message)
            topic = str(payload.get("topic", ""))
            data = payload.get("data", {})
            if topic.startswith("orderbook."):
                if payload.get("type") == "snapshot":
                    bids = {row["price"]: row["size"] for row in normalize_levels(data.get("b", []))}
                    asks = {row["price"]: row["size"] for row in normalize_levels(data.get("a", []))}
                else:
                    apply_levels(bids, normalize_levels(data.get("b", [])))
                    apply_levels(asks, normalize_levels(data.get("a", [])))
            elif topic.startswith("tickers."):
                last_price = float(data.get("lastPrice") or last_price)
            else:
                continue
            await send_book(websocket, "bybit", wire_symbol, last_price, bids, asks, payload.get("ts"))


async def stream_bingx(websocket: WebSocket, wire_symbol: str, snapshot: dict[str, object]) -> None:
    await stream_snapshot_polling(websocket, "bingx", wire_symbol, fetch_bingx_snapshot, interval_seconds=0.8)


def decode_bingx_message(raw_message: str | bytes) -> str:
    if isinstance(raw_message, bytes):
        return gzip.decompress(raw_message).decode("utf-8")
    return raw_message


async def stream_bitget(websocket: WebSocket, wire_symbol: str, snapshot: dict[str, object]) -> None:
    last_price = float(snapshot["lastPrice"])
    await send_status(websocket, "bitget", wire_symbol)
    async with websockets.connect(BITGET_WS_URL, ping_interval=None, open_timeout=5) as upstream:
        await upstream.send(
            json.dumps(
                {
                    "op": "subscribe",
                    "args": [
                        {"instType": "USDT-FUTURES", "channel": "books5", "instId": wire_symbol},
                        {"instType": "USDT-FUTURES", "channel": "ticker", "instId": wire_symbol},
                    ],
                }
            )
        )
        async for raw_message in upstream:
            if raw_message == "pong":
                continue
            payload = json.loads(raw_message)
            data = first_item(payload.get("data", []))
            channel = payload.get("arg", {}).get("channel")
            if channel == "books5":
                await websocket.send_json(build_snapshot("bitget", wire_symbol, last_price, normalize_levels(data.get("bids", data.get("b", []))), normalize_levels(data.get("asks", data.get("a", []))), "ws", data.get("ts")))
            elif channel == "ticker":
                last_price = float(data.get("lastPr") or data.get("last") or last_price)


async def stream_gate(websocket: WebSocket, wire_symbol: str, snapshot: dict[str, object]) -> None:
    bids = {row["price"]: row["size"] for row in snapshot["bids"]}
    asks = {row["price"]: row["size"] for row in snapshot["asks"]}
    last_price = float(snapshot["lastPrice"])
    last_full_snapshot_at = 0.0
    last_depth_id: int | None = None
    await send_status(websocket, "gate", wire_symbol)

    try:
        fresh_snapshot = await asyncio.to_thread(fetch_gate_snapshot, wire_symbol)
        bids = {row["price"]: row["size"] for row in fresh_snapshot["bids"]}
        asks = {row["price"]: row["size"] for row in fresh_snapshot["asks"]}
        last_price = float(fresh_snapshot["lastPrice"] or last_price)
        last_full_snapshot_at = time.monotonic()
        await send_book(websocket, "gate", wire_symbol, last_price, bids, asks, int(time.time() * 1000))
    except Exception:
        pass

    async with websockets.connect(GATE_WS_URL, ping_interval=20, ping_timeout=20, open_timeout=5) as upstream:
        now = int(time.time())
        await upstream.send(json.dumps({"time": now, "channel": "futures.order_book_update", "event": "subscribe", "payload": [wire_symbol, "100ms", "100"]}))
        await upstream.send(json.dumps({"time": now, "channel": "futures.tickers", "event": "subscribe", "payload": [wire_symbol]}))
        async for raw_message in upstream:
            payload = json.loads(raw_message)
            result = payload.get("result", {})
            if payload.get("channel") == "futures.order_book_update" and payload.get("event") == "update":
                update_id = int(result.get("u") or 0)
                first_update_id = int(result.get("U") or 0)
                if result.get("full") is True:
                    bids = {row["price"]: row["size"] for row in normalize_levels(result.get("b", []))}
                    asks = {row["price"]: row["size"] for row in normalize_levels(result.get("a", []))}
                    last_depth_id = update_id or last_depth_id
                elif last_depth_id is not None and first_update_id and first_update_id != last_depth_id + 1:
                    apply_levels(bids, normalize_levels(result.get("b", [])))
                    apply_levels(asks, normalize_levels(result.get("a", [])))
                    last_depth_id = update_id or last_depth_id
                else:
                    apply_levels(bids, normalize_levels(result.get("b", [])))
                    apply_levels(asks, normalize_levels(result.get("a", [])))
                    last_depth_id = update_id or last_depth_id
            elif payload.get("channel") == "futures.tickers":
                last_price = float(result.get("last") or last_price)
            else:
                continue

            current_time = time.monotonic()
            if current_time - last_full_snapshot_at >= FULL_SNAPSHOT_REFRESH_SECONDS:
                try:
                    fresh_snapshot = await asyncio.to_thread(fetch_gate_snapshot, wire_symbol)
                    bids = {row["price"]: row["size"] for row in fresh_snapshot["bids"]}
                    asks = {row["price"]: row["size"] for row in fresh_snapshot["asks"]}
                    last_price = float(fresh_snapshot["lastPrice"] or last_price)
                    last_full_snapshot_at = current_time
                except Exception:
                    last_full_snapshot_at = current_time

            await send_book(websocket, "gate", wire_symbol, last_price, bids, asks, result.get("t") or payload.get("time_ms"))


async def stream_hyperliquid(websocket: WebSocket, wire_symbol: str, snapshot: dict[str, object]) -> None:
    last_price = float(snapshot["lastPrice"])
    await send_status(websocket, "hyperliquid", wire_symbol)
    async with websockets.connect(HYPERLIQUID_WS_URL, ping_interval=20, ping_timeout=20, open_timeout=5) as upstream:
        await upstream.send(json.dumps({"method": "subscribe", "subscription": {"type": "l2Book", "coin": wire_symbol}}))
        await upstream.send(json.dumps({"method": "subscribe", "subscription": {"type": "activeAssetCtx", "coin": wire_symbol}}))
        async for raw_message in upstream:
            payload = json.loads(raw_message)
            data = payload.get("data", {})
            if payload.get("channel") == "l2Book":
                levels = data.get("levels", [[], []])
                await websocket.send_json(build_snapshot("hyperliquid", wire_symbol, last_price, normalize_levels(levels[0] if levels else []), normalize_levels(levels[1] if len(levels) > 1 else []), "ws", data.get("time")))
            elif payload.get("channel") == "activeAssetCtx":
                ctx = data.get("ctx", data)
                last_price = float(ctx.get("midPx") or ctx.get("markPx") or last_price)


async def stream_kucoin(websocket: WebSocket, wire_symbol: str, snapshot: dict[str, object]) -> None:
    last_price = float(snapshot["lastPrice"])
    await send_status(websocket, "kucoin", wire_symbol)
    async with websockets.connect(KUCOIN_WS_URL, ping_interval=20, ping_timeout=20, open_timeout=5) as upstream:
        request_id = str(int(time.time() * 1000))
        await upstream.send(json.dumps({"id": request_id, "type": "subscribe", "topic": f"/contractMarket/level2Depth50:{wire_symbol}", "response": True}))
        await upstream.send(json.dumps({"id": f"{request_id}-ticker", "type": "subscribe", "topic": f"/contractMarket/ticker:{wire_symbol}", "response": True}))
        async for raw_message in upstream:
            payload = json.loads(raw_message)
            data = payload.get("data", {})
            topic = str(payload.get("topic", ""))
            if "level2Depth50" in topic:
                await websocket.send_json(build_snapshot("kucoin", wire_symbol, last_price, normalize_levels(data.get("bids", [])), normalize_levels(data.get("asks", [])), "ws", data.get("ts") or data.get("timestamp")))
            elif "ticker" in topic:
                last_price = float(data.get("price") or data.get("bestBidPrice") or last_price)


async def stream_snapshot_polling(
    websocket: WebSocket,
    exchange_slug: str,
    wire_symbol: str,
    fetcher: Callable[[str], dict[str, object]],
    interval_seconds: float = 1.0,
) -> None:
    await send_status(websocket, exchange_slug, wire_symbol)
    while True:
        snapshot = await asyncio.to_thread(fetcher, wire_symbol)
        await websocket.send_json({"type": "snapshot", **snapshot})
        await asyncio.sleep(interval_seconds)


async def stream_mexc(websocket: WebSocket, wire_symbol: str, snapshot: dict[str, object]) -> None:
    bids = {row["price"]: row["size"] for row in snapshot["bids"]}
    asks = {row["price"]: row["size"] for row in snapshot["asks"]}
    last_price = float(snapshot["lastPrice"])
    last_full_snapshot_at = 0.0

    await send_status(websocket, "mexc", wire_symbol)
    async with websockets.connect(MEXC_WS_URL, ping_interval=20, ping_timeout=20, open_timeout=5) as upstream:
        await upstream.send(json.dumps({"method": "sub.depth", "param": {"symbol": wire_symbol}, "gzip": False}))
        await upstream.send(json.dumps({"method": "sub.ticker", "param": {"symbol": wire_symbol}, "gzip": False}))

        async for raw_message in upstream:
            payload = json.loads(raw_message)
            channel = payload.get("channel")
            data = payload.get("data", {})

            if channel == "push.depth":
                apply_levels(asks, normalize_levels(data.get("asks", [])))
                apply_levels(bids, normalize_levels(data.get("bids", [])))
            elif channel == "push.ticker":
                last_price = float(data.get("lastPrice") or last_price)
                bid1 = float(data.get("bid1") or 0)
                ask1 = float(data.get("ask1") or 0)
                if bid1 > 0:
                    bids[bid1] = bids.get(bid1, 0)
                if ask1 > 0:
                    asks[ask1] = asks.get(ask1, 0)
            else:
                continue

            now = time.monotonic()
            if now - last_full_snapshot_at >= FULL_SNAPSHOT_REFRESH_SECONDS:
                try:
                    fresh_snapshot = await asyncio.to_thread(fetch_mexc_snapshot, wire_symbol)
                    bids = {row["price"]: row["size"] for row in fresh_snapshot["bids"]}
                    asks = {row["price"]: row["size"] for row in fresh_snapshot["asks"]}
                    last_price = float(fresh_snapshot["lastPrice"] or last_price)
                    last_full_snapshot_at = now
                except Exception:
                    last_full_snapshot_at = now

            await send_book(websocket, "mexc", wire_symbol, last_price, bids, asks, payload.get("ts"))


async def stream_okx(websocket: WebSocket, wire_symbol: str, snapshot: dict[str, object]) -> None:
    last_price = float(snapshot["lastPrice"])
    bids = {row["price"]: row["size"] for row in snapshot["bids"]}
    asks = {row["price"]: row["size"] for row in snapshot["asks"]}
    await send_status(websocket, "okx", wire_symbol)

    try:
        fresh_snapshot = await asyncio.to_thread(fetch_okx_snapshot, wire_symbol)
        bids = {row["price"]: row["size"] for row in fresh_snapshot["bids"]}
        asks = {row["price"]: row["size"] for row in fresh_snapshot["asks"]}
        last_price = float(fresh_snapshot["lastPrice"] or last_price)
        await send_book(websocket, "okx", wire_symbol, last_price, bids, asks, int(time.time() * 1000))
    except Exception:
        pass

    async with websockets.connect(OKX_WS_URL, ping_interval=20, ping_timeout=20, open_timeout=5) as upstream:
        await upstream.send(
            json.dumps(
                {
                    "op": "subscribe",
                    "args": [
                        {"channel": "books5", "instId": wire_symbol},
                        {"channel": "tickers", "instId": wire_symbol},
                    ],
                }
            )
        )
        async for raw_message in upstream:
            payload = json.loads(raw_message)
            if payload.get("event"):
                continue
            data = first_item(payload.get("data", []))
            channel = payload.get("arg", {}).get("channel")
            if channel == "books5":
                bids = {row["price"]: row["size"] for row in normalize_levels(data.get("bids") or data.get("b") or [])}
                asks = {row["price"]: row["size"] for row in normalize_levels(data.get("asks") or data.get("a") or [])}
                await send_book(websocket, "okx", wire_symbol, last_price, bids, asks, data.get("ts"))
            elif channel == "tickers":
                last_price = float(data.get("last") or last_price)
                if bids or asks:
                    await send_book(websocket, "okx", wire_symbol, last_price, bids, asks, data.get("ts"))


def apply_levels(book: dict[float, float], updates: list[dict[str, float]]) -> None:
    for level in updates:
        if level["size"] <= 0:
            book.pop(level["price"], None)
        else:
            book[level["price"]] = level["size"]


async def send_book(websocket: WebSocket, exchange_slug: str, wire_symbol: str, last_price: float, bids: dict[float, float], asks: dict[float, float], timestamp: int | None = None) -> None:
    bid_rows = [{"price": price, "size": size} for price, size in bids.items()]
    ask_rows = [{"price": price, "size": size} for price, size in asks.items()]
    await websocket.send_json(build_snapshot(exchange_slug, wire_symbol, last_price, bid_rows, ask_rows, "ws", timestamp))


async def send_status(websocket: WebSocket, exchange_slug: str, wire_symbol: str) -> None:
    await safe_send_json(
        websocket,
        {
            "type": "status",
            "exchangeSlug": exchange_slug,
            "symbol": to_display_symbol(exchange_slug, wire_symbol),
            "message": f"Подключение {exchange_slug}",
        },
    )


async def safe_send_json(websocket: WebSocket, payload: dict[str, object]) -> None:
    try:
        await websocket.send_json(payload)
    except RuntimeError:
        return


SYMBOL_FETCHERS: dict[str, Callable[[], list[dict[str, object]]]] = {
    "aster": fetch_aster_symbols,
    "binance": fetch_binance_symbols,
    "bingx": fetch_bingx_symbols,
    "bitget": fetch_bitget_symbols,
    "bybit": fetch_bybit_symbols,
    "gate": fetch_gate_symbols,
    "hyperliquid": fetch_hyperliquid_symbols,
    "kucoin": fetch_kucoin_symbols,
    "mexc": fetch_mexc_symbols,
    "okx": fetch_okx_symbols,
}

SNAPSHOT_FETCHERS: dict[str, Callable[[str], dict[str, object]]] = {
    "aster": fetch_aster_snapshot,
    "binance": fetch_binance_snapshot,
    "bingx": fetch_bingx_snapshot,
    "bitget": fetch_bitget_snapshot,
    "bybit": fetch_bybit_snapshot,
    "gate": fetch_gate_snapshot,
    "hyperliquid": fetch_hyperliquid_snapshot,
    "kucoin": fetch_kucoin_snapshot,
    "mexc": fetch_mexc_snapshot,
    "okx": fetch_okx_snapshot,
}

FUNDING_FETCHERS: dict[str, Callable[[str], dict[str, object]]] = {
    "aster": fetch_aster_funding,
    "binance": fetch_binance_funding,
    "bingx": fetch_bingx_funding,
    "bitget": fetch_bitget_funding,
    "bybit": fetch_bybit_funding,
    "gate": fetch_gate_funding,
    "hyperliquid": fetch_hyperliquid_funding,
    "kucoin": fetch_kucoin_funding,
    "mexc": fetch_mexc_funding,
    "okx": fetch_okx_funding,
}

FUNDING_HISTORY_FETCHERS: dict[str, Callable[[str, int, int], list[dict[str, object]]]] = {
    "aster": fetch_aster_funding_history,
    "binance": fetch_binance_funding_history,
    "bingx": fetch_bingx_funding_history,
    "bitget": fetch_bitget_funding_history,
    "bybit": fetch_bybit_funding_history,
    "gate": fetch_gate_funding_history,
    "hyperliquid": fetch_hyperliquid_funding_history,
    "kucoin": fetch_kucoin_funding_history,
    "mexc": fetch_mexc_funding_history,
    "okx": fetch_okx_funding_history,
}

STREAM_CALLBACKS = {
    "aster": stream_aster,
    "binance": stream_binance,
    "bingx": stream_bingx,
    "bitget": stream_bitget,
    "bybit": stream_bybit,
    "gate": stream_gate,
    "hyperliquid": stream_hyperliquid,
    "kucoin": stream_kucoin,
    "mexc": stream_mexc,
    "okx": stream_okx,
}
