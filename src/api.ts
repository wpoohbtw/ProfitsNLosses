import type {
  BalanceEventsResponse,
  CurrentUser,
  FundingInfo,
  ExchangesResponse,
  MarketSnapshot,
  MarketSymbolsResponse,
  ProfitCalendarResponse,
  ExchangeTransferPayload,
  SituationCreatePayload,
  SituationSettings,
  SituationSettingsPayload,
  SituationSettingsTestResponse,
  SituationsResponse,
  TradeClosePayload,
  TradeCreatePayload,
  TradeExitOrder,
  TradeExitOrderPayload,
  TradeRealizePnlPayload,
  TradesResponse
} from "./types";

const appBase = import.meta.env.BASE_URL.endsWith("/") ? import.meta.env.BASE_URL : `${import.meta.env.BASE_URL}/`;
const API_PREFIX = `${appBase}api/v1`;

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_PREFIX}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...options?.headers
    },
    ...options
  });

  if (!response.ok) {
    const message = await response.text();
    try {
      const payload = JSON.parse(message) as { detail?: unknown };
      if (typeof payload.detail === "string") {
        throw new Error(payload.detail);
      }
    } catch (error) {
      if (error instanceof Error && error.name === "Error") {
        throw error;
      }
    }
    throw new Error(message || "Ошибка API");
  }

  return response.json() as Promise<T>;
}

export function getExchanges(): Promise<ExchangesResponse> {
  return request<ExchangesResponse>("/exchanges");
}

export function getCurrentUser(): Promise<CurrentUser> {
  return request<CurrentUser>("/me");
}

export function updateExchangeBalance(exchangeId: number, balanceUsdt: number): Promise<{ status: string }> {
  return request(`/exchanges/${exchangeId}/balance`, {
    method: "PUT",
    body: JSON.stringify({ balance_usdt: balanceUsdt })
  });
}

export function resetExchangePnl(exchangeId: number): Promise<{ status: string }> {
  return request(`/exchanges/${exchangeId}/reset-pnl`, {
    method: "POST"
  });
}

export function transferBetweenExchanges(payload: ExchangeTransferPayload): Promise<{ status: string }> {
  return request("/exchanges/transfer", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function getProfitCalendar(year?: number, month?: number): Promise<ProfitCalendarResponse> {
  const params = new URLSearchParams();
  if (year) {
    params.set("year", String(year));
  }
  if (month) {
    params.set("month", String(month));
  }
  const query = params.toString();
  return request<ProfitCalendarResponse>(`/profit-calendar${query ? `?${query}` : ""}`);
}

export function getBalanceEvents(exchangeId?: number): Promise<BalanceEventsResponse> {
  const query = exchangeId ? `?exchange_id=${exchangeId}` : "";
  return request<BalanceEventsResponse>(`/balance-events${query}`);
}

export function getSituations(): Promise<SituationsResponse> {
  return request<SituationsResponse>("/situations");
}

export function createSituation(payload: SituationCreatePayload): Promise<{ status: string; updatedRange?: string }> {
  return request("/situations", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function updateSituation(rowNumber: number, payload: SituationCreatePayload): Promise<{ status: string; updatedRange?: string }> {
  return request(`/situations/${rowNumber}`, {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

export function deleteSituation(rowNumber: number): Promise<{ status: string }> {
  return request(`/situations/${rowNumber}`, {
    method: "DELETE"
  });
}

export function getSituationSettings(): Promise<SituationSettings> {
  return request<SituationSettings>("/situations/settings");
}

export function updateSituationSettings(payload: SituationSettingsPayload): Promise<SituationSettings> {
  return request<SituationSettings>("/situations/settings", {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

export function testSituationSettings(): Promise<SituationSettingsTestResponse> {
  return request<SituationSettingsTestResponse>("/situations/settings/test", {
    method: "POST"
  });
}

export function createTrade(payload: TradeCreatePayload): Promise<{ status: string; tradeId: number }> {
  return request("/trades", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function getTrades(status = "open"): Promise<TradesResponse> {
  return request<TradesResponse>(`/trades?status=${status}`);
}

export function updateTradeGroupComment(groupId: string, comment: string): Promise<{ status: string }> {
  return request(`/trade-groups/${encodeURIComponent(groupId)}/comment`, {
    method: "PUT",
    body: JSON.stringify({ comment })
  });
}

export function deleteTrade(tradeId: number): Promise<{ status: string }> {
  return request(`/trades/${tradeId}`, {
    method: "DELETE"
  });
}

export function closeTrade(tradeId: number, payload: TradeClosePayload): Promise<{ status: string }> {
  return request(`/trades/${tradeId}/close`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function realizeTradePnl(tradeId: number, payload: TradeRealizePnlPayload): Promise<{ status: string }> {
  return request(`/trades/${tradeId}/realize-pnl`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function createTradeExitOrder(tradeId: number, payload: TradeExitOrderPayload): Promise<{ status: string; exitOrder: TradeExitOrder }> {
  return request(`/trades/${tradeId}/exit-orders`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function updateTradeExitOrder(tradeId: number, orderId: number, payload: TradeExitOrderPayload): Promise<{ status: string; exitOrder: TradeExitOrder }> {
  return request(`/trades/${tradeId}/exit-orders/${orderId}`, {
    method: "PUT",
    body: JSON.stringify(payload)
  });
}

export function deleteTradeExitOrder(tradeId: number, orderId: number): Promise<{ status: string }> {
  return request(`/trades/${tradeId}/exit-orders/${orderId}`, {
    method: "DELETE"
  });
}

export function revertClosedTrade(tradeId: number): Promise<{ status: string }> {
  return request(`/trades/${tradeId}/revert-close`, {
    method: "POST"
  });
}

export function getMarketSymbols(exchangeSlug: string, query: string, limit = 30): Promise<MarketSymbolsResponse> {
  const params = new URLSearchParams({
    exchange_slug: exchangeSlug,
    query,
    limit: String(limit)
  });
  return request<MarketSymbolsResponse>(`/market/symbols?${params.toString()}`);
}

export function getMarketSnapshot(exchangeSlug: string, symbol: string): Promise<MarketSnapshot> {
  const params = new URLSearchParams({
    exchange_slug: exchangeSlug,
    symbol
  });
  return request<MarketSnapshot>(`/market/snapshot?${params.toString()}`);
}

export function getMarketFunding(exchangeSlug: string, symbol: string): Promise<FundingInfo> {
  const params = new URLSearchParams({
    exchange_slug: exchangeSlug,
    symbol
  });
  return request<FundingInfo>(`/market/funding?${params.toString()}`);
}

export function getMarketWsUrl(exchangeSlug: string, symbol: string): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const isViteDevServer = window.location.port === "5173";
  const host = isViteDevServer ? "127.0.0.1:8001" : window.location.host;
  const path = isViteDevServer ? "/api/v1/market/ws" : `${appBase}api/v1/market/ws`;
  const params = new URLSearchParams({
    exchange_slug: exchangeSlug,
    symbol
  });
  return `${protocol}//${host}${path}?${params.toString()}`;
}
