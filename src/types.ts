export type Exchange = {
  id: number;
  slug: string;
  name: string;
  balanceUsdt: number;
  startBalanceUsdt: number;
  pnlTotalUsdt: number;
  pnlResetAt: string;
  updatedAt: string;
};

export type ExchangeSummary = {
  totalBalanceUsdt: number;
  totalPnlUsdt: number;
  exchangeCount: number;
};

export type ExchangesResponse = {
  exchanges: Exchange[];
  summary: ExchangeSummary;
};

export type CalendarDay = {
  date: string;
  day: number;
  pnlUsdt: number;
  source: string;
};

export type ProfitCalendarResponse = {
  year: number;
  month: number;
  days: CalendarDay[];
  totalPnlUsdt: number;
};

export type BalanceEvent = {
  id: number;
  exchangeId: number;
  exchangeSlug: string;
  exchangeName: string;
  eventType: "seed" | "backfill" | "balance_update" | "pnl_reset" | "trade_close" | "trade_partial_close" | "trade_delete" | "transfer_in" | "transfer_out";
  balanceBeforeUsdt: number | null;
  balanceAfterUsdt: number;
  startBalanceBeforeUsdt: number | null;
  startBalanceAfterUsdt: number;
  pnlAfterUsdt: number;
  note: string | null;
  createdAt: string;
};

export type BalanceEventsResponse = {
  events: BalanceEvent[];
};

export type TradeSide = "long" | "short";
export type TradeSizeUnit = "USDT" | "TOKEN";
export type TradeStatus = "open" | "closed" | "deleted";

export type TradeCreatePayload = {
  exchange_id: number;
  group_id: string;
  symbol: string;
  side: TradeSide;
  entry_price: number;
  size_value: number;
  size_unit: TradeSizeUnit;
  notional_usdt: number;
  margin_usdt: number;
  leverage: number;
  margin_mode: "isolated" | "cross";
};

export type TradeClosePayload = {
  exit_price: number;
  realized_pnl_usdt: number;
  group_id?: string;
  notional_usdt?: number;
  leverage?: number;
  margin_mode?: "isolated" | "cross";
};

export type TradeRealizePnlPayload = {
  realized_pnl_usdt: number;
};

export type ExchangeTransferPayload = {
  from_exchange_id: number;
  to_exchange_id: number;
  amount_usdt: number;
};

export type Trade = {
  id: number;
  groupId: string;
  exchangeId: number;
  exchangeSlug: string;
  exchangeName: string;
  symbol: string;
  side: TradeSide;
  status: TradeStatus;
  entryPrice: number;
  exitPrice: number | null;
  sizeValue: number;
  sizeUnit: TradeSizeUnit;
  notionalUsdt: number;
  marginUsdt: number;
  leverage: number;
  marginMode: "isolated" | "cross";
  realizedPnlUsdt: number;
  comment: string;
  openedAt: string;
  closedAt: string | null;
  deletedAt: string | null;
};

export type TradesResponse = {
  trades: Trade[];
};

export type Situation = {
  rowNumber: number;
  date: string;
  token: string;
  description: string;
  posts: string;
};

export type SituationsResponse = {
  situations: Situation[];
};

export type SituationCreatePayload = {
  date: string;
  token: string;
  description: string;
  posts: string;
};

export type MarketSymbol = {
  exchangeSlug: string;
  symbol: string;
  wireSymbol: string;
  baseAsset: string;
  quoteAsset: string;
  displayName: string;
};

export type MarketSymbolsResponse = {
  exchangeSlug: string;
  symbols: MarketSymbol[];
};

export type OrderBookLevel = {
  price: number;
  size: number;
};

export type MarketSnapshot = {
  type?: "snapshot" | "update" | "error" | "status";
  exchangeSlug: string;
  symbol: string;
  wireSymbol: string;
  lastPrice: number;
  bestBid: number | null;
  bestAsk: number | null;
  bids: OrderBookLevel[];
  asks: OrderBookLevel[];
  source: "rest" | "ws";
  updatedAt: number;
  message?: string;
};

export type FundingInfo = {
  exchangeSlug: string;
  symbol: string;
  wireSymbol: string;
  fundingRate: number;
  nextFundingTime: number;
  updatedAt: number;
};
