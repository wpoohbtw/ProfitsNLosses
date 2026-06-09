import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { FocusEvent, ReactNode } from "react";
import {
  ArrowDown,
  ArrowUp,
  ArrowRightLeft,
  AlertTriangle,
  BarChart3,
  CalendarDays,
  ChevronDown,
  ClipboardList,
  History,
  Home,
  Landmark,
  Layers3,
  LayoutDashboard,
  Plus,
  RotateCcw,
  Save,
  Search,
  Settings2,
  SquarePen,
  Trash2,
  TrendingUp,
  Wallet,
  X
} from "lucide-react";
import {
  closeTrade,
  createTradeExitOrder,
  createSituation,
  createTrade,
  deleteSituation,
  deleteTradeExitOrder,
  deleteTrade,
  getExchanges,
  getCurrentUser,
  getMarketFunding,
  getMarketSymbols,
  getMarketWsUrl,
  getProfitCalendar,
  getSituationSettings,
  getSituations,
  getTrades,
  realizeTradePnl,
  resetExchangePnl,
  revertClosedTrade,
  testSituationSettings,
  transferBetweenExchanges,
  updateTradeGroupComment,
  updateTradeExitOrder,
  updateSituation,
  updateSituationSettings,
  updateExchangeBalance
} from "./api";
import type {
  CalendarDay,
  CurrentUser,
  Exchange,
  ExchangeSummary,
  FundingInfo,
  MarketSnapshot,
  MarketSymbol,
  ProfitCalendarResponse,
  Situation,
  SituationSettings,
  SituationSettingsTestResponse,
  Trade,
  TradeExitOrder,
  TradeExitOrderPayload,
  TradeSide,
  TradeSizeUnit
} from "./types";

type PageId = "exchanges" | "trades" | "deals" | "situations";

type TokenMock = {
  symbol: string;
  name: string;
  lastPrice: number;
  wireSymbol?: string;
};

type TradeTicket = {
  id: number;
  exchangeId: number | "";
  tokenQuery: string;
  symbol: string;
  side: TradeSide;
  marginMode: "isolated" | "cross";
  leverage: string;
  price: string;
  size: string;
  sizeUnit: TradeSizeUnit;
  percent: number;
  message: string | null;
};

type OpenPosition = {
  id: number;
  groupId: string;
  tradeId: number | null;
  exchangeId: number;
  exchangeSlug: string;
  exchangeName: string;
  symbol: string;
  side: TradeSide;
  marginMode: "isolated" | "cross";
  leverage: number;
  entryPrice: number;
  sizeValue: number;
  sizeUnit: TradeSizeUnit;
  notionalUsdt: number;
  marginUsdt: number;
  realizedPnlUsdt: number;
  realizedPricePnlUsdt: number;
  lastFundingAppliedAt: number | null;
  exitOrders: TradeExitOrder[];
  openedAt: string;
};

type ClosedPosition = {
  id: number;
  groupId: string;
  tradeId: number | null;
  exchangeId: number;
  exchangeSlug: string;
  exchangeName: string;
  symbol: string;
  side: TradeSide;
  marginMode: "isolated" | "cross";
  leverage: number;
  entryPrice: number;
  exitPrice: number;
  sizeValue: number;
  sizeUnit: TradeSizeUnit;
  notionalUsdt: number;
  marginUsdt: number;
  realizedPnlUsdt: number;
  comment: string;
  openedAt: string;
  closedAt: string;
};

type OpenTradeDraft = {
  ticket: TradeTicket;
  exchange: Exchange;
  symbol: string;
  quoteAsset: string;
  entryPrice: number;
  markPrice: number;
  sizeValue: number;
  notionalUsdt: number;
  marginUsdt: number;
  leverage: number;
  marginMode: "isolated" | "cross";
  liquidationPrice: number | null;
};

type CloseTradeDraft = {
  position: OpenPosition;
  priceMode: "market" | "custom";
  customExitPrice: string;
  percentValue: string;
  usdtValue: string;
};

type ExitOrderMetricMode = "roe" | "pnl";

type ExitOrderLegDraft = {
  triggerMode: TradeExitOrder["triggerMode"];
  metricMode: ExitOrderMetricMode;
  triggerPrice: string;
  pnlPercent: string;
  pnlUsdt: string;
  sizeMode: TradeExitOrder["sizeMode"];
  sizePercent: string;
  sizeUsdt: string;
};

type ExitOrderDraft = {
  position: OpenPosition;
  order: TradeExitOrder | null;
  orderType: TradeExitOrder["orderType"];
  triggerMode: TradeExitOrder["triggerMode"];
  triggerPrice: string;
  pnlPercent: string;
  sizeMode: TradeExitOrder["sizeMode"];
  sizePercent: string;
  sizeUsdt: string;
  positionScope: "full" | "partial";
  legs: Record<TradeExitOrder["orderType"], ExitOrderLegDraft>;
};

type DepositDraft = {
  fromExchangeId: number | "";
  toExchangeId: number | "";
  amount: string;
};

type CalendarRange = {
  start: string | null;
  end: string | null;
};

type SituationDraft = {
  date: string;
  token: string;
  description: string;
  posts: string;
};

type SituationModalState = {
  mode: "create" | "edit";
  rowNumber?: number;
};

type SituationSettingsDraft = {
  credentialsPath: string;
  spreadsheetId: string;
  sheetName: string;
};

const EXCHANGE_ORDER = [
  "binance",
  "bybit",
  "mexc",
  "bingx",
  "gate",
  "bitget",
  "kucoin",
  "hyperliquid",
  "aster",
  "okx"
];

const TOKENS: TokenMock[] = [
  { symbol: "BTC", name: "Bitcoin", lastPrice: 104250 },
  { symbol: "ETH", name: "Ethereum", lastPrice: 3420 },
  { symbol: "SOL", name: "Solana", lastPrice: 182.4 },
  { symbol: "BNB", name: "BNB", lastPrice: 684.2 },
  { symbol: "XRP", name: "XRP", lastPrice: 2.18 },
  { symbol: "DOGE", name: "Dogecoin", lastPrice: 0.238 },
  { symbol: "TON", name: "Toncoin", lastPrice: 6.42 },
  { symbol: "LINK", name: "Chainlink", lastPrice: 18.74 },
  { symbol: "ARB", name: "Arbitrum", lastPrice: 1.12 },
  { symbol: "OP", name: "Optimism", lastPrice: 2.34 }
];

const emptySummary: ExchangeSummary = {
  totalBalanceUsdt: 0,
  totalPnlUsdt: 0,
  exchangeCount: 0
};

const MAINTENANCE_MARGIN_TIERS = [
  { maxNotionalUsdt: 50_000, rate: 0.004 },
  { maxNotionalUsdt: 250_000, rate: 0.005 },
  { maxNotionalUsdt: 1_000_000, rate: 0.01 },
  { maxNotionalUsdt: 5_000_000, rate: 0.025 },
  { maxNotionalUsdt: Number.POSITIVE_INFINITY, rate: 0.05 }
];
const LIQUIDATION_FEE_BUFFER_RATE = 0.0005;

const currencyFormatter = new Intl.NumberFormat("ru-RU", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 2
});

const compactFormatter = new Intl.NumberFormat("ru-RU", {
  maximumFractionDigits: 2
});

const sizeUsdtFormatter = new Intl.NumberFormat("ru-RU", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 2
});

const ACTIVE_PAGE_STORAGE_KEY = "profits-n-losses-active-page";
const TRADE_TICKETS_STORAGE_KEY = "profits-n-losses-trade-tickets";
const OPEN_POSITIONS_STORAGE_KEY = "profits-n-losses-open-positions";
const LIVE_EXCHANGE_SLUGS = new Set(["aster", "binance", "bingx", "bitget", "bybit", "gate", "hyperliquid", "kucoin", "mexc", "okx"]);
const ORDERBOOK_VISIBLE_LEVELS = 5;
const SHOW_EXIT_ORDER_CONTROLS = false;

function formatMoney(value: number): string {
  return currencyFormatter.format(value);
}

function formatPrice(value: number): string {
  const absoluteValue = Math.abs(value);
  const minimumFractionDigits = absoluteValue >= 1000 ? 2 : absoluteValue >= 1 ? 4 : 6;
  const maximumFractionDigits = absoluteValue >= 1000 ? 4 : absoluteValue >= 1 ? 6 : 8;
  return new Intl.NumberFormat("ru-RU", {
    minimumFractionDigits,
    maximumFractionDigits
  }).format(value);
}

function formatSigned(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${formatMoney(value)}`;
}

function formatPercent(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(value)}%`;
}

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}

function getMonthName(calendar: ProfitCalendarResponse | null): string {
  if (!calendar) {
    return "Текущий месяц";
  }

  return new Intl.DateTimeFormat("ru-RU", {
    month: "long",
    year: "numeric"
  }).format(new Date(calendar.year, calendar.month - 1, 1));
}

function getExchangeIconPath(slug: string): string {
  const basePath = import.meta.env.BASE_URL.endsWith("/") ? import.meta.env.BASE_URL : `${import.meta.env.BASE_URL}/`;
  return `${basePath}exchange-icons/${slug}.svg`;
}

function sortExchanges(exchanges: Exchange[]): Exchange[] {
  return [...exchanges].sort((left, right) => {
    const leftIndex = EXCHANGE_ORDER.indexOf(left.slug);
    const rightIndex = EXCHANGE_ORDER.indexOf(right.slug);
    const normalizedLeft = leftIndex === -1 ? Number.MAX_SAFE_INTEGER : leftIndex;
    const normalizedRight = rightIndex === -1 ? Number.MAX_SAFE_INTEGER : rightIndex;
    return normalizedLeft - normalizedRight;
  });
}

function numberFromInput(value: string): number {
  return Number(value.replace(",", "."));
}

function getResolvedTicketSymbol(ticket: TradeTicket): string {
  return (ticket.symbol || ticket.tokenQuery).trim().toUpperCase();
}

function isLiveExchange(exchange: Exchange | undefined): boolean {
  return Boolean(exchange && LIVE_EXCHANGE_SLUGS.has(exchange.slug));
}

function createTicket(id: number): TradeTicket {
  return {
    id,
    exchangeId: "",
    tokenQuery: "",
    symbol: "",
    side: "long",
    marginMode: "isolated",
    leverage: "10",
    price: "",
    size: "",
    sizeUnit: "USDT",
    percent: 0,
    message: null
  };
}

function getUserStorageKey(key: string, user: CurrentUser): string {
  const username = user.username || "user";
  return `${key}:${user.userId}:${username}`;
}

function getStoredValue(key: string, user: CurrentUser | null): string | null {
  if (!user) {
    return window.localStorage.getItem(key);
  }

  const scopedValue = window.localStorage.getItem(getUserStorageKey(key, user));
  if (scopedValue !== null) {
    return scopedValue;
  }

  return user.username === "wpoohbtw" ? window.localStorage.getItem(key) : null;
}

function getInitialPage(user: CurrentUser | null = null): PageId {
  const savedPage = getStoredValue(ACTIVE_PAGE_STORAGE_KEY, user);
  return savedPage === "exchanges" || savedPage === "trades" || savedPage === "deals" || savedPage === "situations"
    ? savedPage
    : "exchanges";
}

function getInitialTickets(user: CurrentUser | null = null): TradeTicket[] {
  const storedTickets = getStoredValue(TRADE_TICKETS_STORAGE_KEY, user);
  if (!storedTickets) {
    return [];
  }

  try {
    const parsedTickets = JSON.parse(storedTickets) as TradeTicket[];
    if (!Array.isArray(parsedTickets)) {
      return [];
    }
    return parsedTickets
      .filter((ticket) => Number.isFinite(ticket.id) && typeof ticket.tokenQuery === "string")
      .map((ticket) => ({
        ...ticket,
        marginMode: ticket.marginMode === "cross" ? "cross" : "isolated",
        leverage: ticket.leverage || "1"
      }));
  } catch {
    return [];
  }
}

function getInitialOpenPositions(user: CurrentUser | null = null): OpenPosition[] {
  const storedPositions = getStoredValue(OPEN_POSITIONS_STORAGE_KEY, user);
  if (!storedPositions) {
    return [];
  }

  try {
    const parsedPositions = JSON.parse(storedPositions) as OpenPosition[];
    if (!Array.isArray(parsedPositions)) {
      return [];
    }
    return parsedPositions
      .filter((position) => Number.isFinite(position.id) && typeof position.symbol === "string")
      .map((position) => {
        const leverage = Number.isFinite(position.leverage) && position.leverage > 0 ? position.leverage : 1;
        const notionalUsdt = Number.isFinite(position.notionalUsdt)
          ? position.notionalUsdt
          : position.sizeUnit === "USDT"
            ? position.sizeValue
            : position.sizeValue * position.entryPrice;
        return {
          ...position,
          groupId: typeof position.groupId === "string" ? position.groupId : `${position.symbol}-${position.openedAt ?? position.id}`,
          marginMode: position.marginMode === "cross" ? "cross" : "isolated",
          leverage,
          notionalUsdt,
          realizedPnlUsdt: Number.isFinite(position.realizedPnlUsdt) ? position.realizedPnlUsdt : 0,
          realizedPricePnlUsdt: Number.isFinite(position.realizedPricePnlUsdt) ? position.realizedPricePnlUsdt : 0,
          lastFundingAppliedAt: Number.isFinite(position.lastFundingAppliedAt) ? position.lastFundingAppliedAt : null,
          exitOrders: Array.isArray(position.exitOrders) ? position.exitOrders : []
        };
      });
  } catch {
    return [];
  }
}

function tradeToClosedPosition(trade: Trade): ClosedPosition | null {
  if (trade.status !== "closed" || !trade.closedAt || trade.exitPrice === null) {
    return null;
  }

  return {
    id: trade.id,
    groupId: trade.groupId,
    tradeId: trade.id,
    exchangeId: trade.exchangeId,
    exchangeSlug: trade.exchangeSlug,
    exchangeName: trade.exchangeName,
    symbol: trade.symbol,
    side: trade.side,
    marginMode: trade.marginMode,
    leverage: trade.leverage,
    entryPrice: trade.entryPrice,
    exitPrice: trade.exitPrice,
    sizeValue: trade.sizeValue,
    sizeUnit: trade.sizeUnit,
    notionalUsdt: trade.notionalUsdt,
    marginUsdt: trade.marginUsdt,
    realizedPnlUsdt: trade.realizedPnlUsdt,
    comment: trade.comment,
    openedAt: trade.openedAt,
    closedAt: trade.closedAt
  };
}

function tradeToOpenPosition(trade: Trade): OpenPosition | null {
  if (trade.status !== "open") {
    return null;
  }

  return {
    id: trade.id,
    groupId: trade.groupId,
    tradeId: trade.id,
    exchangeId: trade.exchangeId,
    exchangeSlug: trade.exchangeSlug,
    exchangeName: trade.exchangeName,
    symbol: trade.symbol,
    side: trade.side,
    marginMode: trade.marginMode,
    leverage: trade.leverage,
    entryPrice: trade.entryPrice,
    sizeValue: trade.sizeValue,
    sizeUnit: trade.sizeUnit,
    notionalUsdt: trade.notionalUsdt,
    marginUsdt: trade.marginUsdt,
    realizedPnlUsdt: trade.realizedPnlUsdt,
    realizedPricePnlUsdt: trade.realizedPnlUsdt,
    lastFundingAppliedAt: trade.lastFundingAppliedAt,
    exitOrders: trade.exitOrders ?? [],
    openedAt: trade.openedAt
  };
}

function getNextTicketId(tickets: TradeTicket[]): number {
  return tickets.reduce((maxId, ticket) => Math.max(maxId, ticket.id), 0) + 1;
}

function getNextPositionId(positions: OpenPosition[]): number {
  return positions.reduce((maxId, position) => Math.max(maxId, position.id), 0) + 1;
}

function ExchangeIcon({ exchange, className = "" }: { exchange: Pick<Exchange, "slug" | "name">; className?: string }) {
  return (
    <div className={`exchange-mark ${className}`.trim()}>
      <img
        src={getExchangeIconPath(exchange.slug)}
        alt=""
        onError={(event) => {
          event.currentTarget.style.display = "none";
        }}
      />
      <span>{exchange.name.slice(0, 2).toUpperCase()}</span>
    </div>
  );
}

function ExchangeNetworkWarning({ exchange }: { exchange: Exchange | undefined }) {
  if (exchange?.slug !== "hyperliquid") {
    return null;
  }

  return (
    <span className="exchange-warning" title="HyperLiquid может требовать VPN для live-данных">
      <AlertTriangle size={14} />
    </span>
  );
}

function getPositionQuantity(position: OpenPosition): number {
  return position.sizeUnit === "TOKEN" ? position.sizeValue : position.sizeValue / position.entryPrice;
}

function getTradeQuantity(sizeValue: number, sizeUnit: TradeSizeUnit, entryPrice: number): number {
  if (!Number.isFinite(entryPrice) || entryPrice <= 0) {
    return 0;
  }
  return sizeUnit === "TOKEN" ? sizeValue : sizeValue / entryPrice;
}

function getTradePricePnlUsdt(side: TradeSide, entryPrice: number, exitPrice: number, sizeValue: number, sizeUnit: TradeSizeUnit): number {
  const quantity = getTradeQuantity(sizeValue, sizeUnit, entryPrice);
  const direction = side === "long" ? 1 : -1;
  return roundInput((exitPrice - entryPrice) * quantity * direction);
}

function getPositionClosePrice(position: OpenPosition, snapshot: MarketSnapshot | null): number {
  if (position.side === "long") {
    return snapshot?.bestBid || snapshot?.lastPrice || position.entryPrice;
  }
  return snapshot?.bestAsk || snapshot?.lastPrice || position.entryPrice;
}

function getPositionPnl(position: OpenPosition, snapshot: MarketSnapshot | null): { pnlUsdt: number; pnlPercent: number; closePrice: number } {
  const closePrice = getPositionClosePrice(position, snapshot);
  return getPositionPnlAtPrice(position, closePrice);
}

function getPositionPnlAtPrice(position: OpenPosition, closePrice: number): { pnlUsdt: number; pnlPercent: number; closePrice: number } {
  const quantity = getPositionQuantity(position);
  const direction = position.side === "long" ? 1 : -1;
  const pnlUsdt = (closePrice - position.entryPrice) * quantity * direction;
  const pnlPercent = position.marginUsdt > 0 ? (pnlUsdt / position.marginUsdt) * 100 : 0;
  return { pnlUsdt, pnlPercent, closePrice };
}

function getPositionPriceForPnlPercent(position: OpenPosition, pnlPercent: number): number {
  const quantity = getPositionQuantity(position);
  const direction = position.side === "long" ? 1 : -1;
  if (!Number.isFinite(quantity) || quantity <= 0 || !Number.isFinite(pnlPercent)) {
    return position.entryPrice;
  }
  const pnlUsdt = position.marginUsdt * (pnlPercent / 100);
  return Math.max(position.entryPrice + pnlUsdt / (quantity * direction), 0);
}

function getPositionCloseNotional(position: OpenPosition): number {
  return position.notionalUsdt > 0 ? position.notionalUsdt : position.sizeUnit === "USDT" ? position.sizeValue : position.sizeValue * position.entryPrice;
}

function formatFundingRate(rate: number): string {
  return `${(rate * 100).toFixed(4)}%`;
}

function formatFundingCountdown(nextFundingTime: number | null, now: number): string {
  if (!nextFundingTime) {
    return "--:--:--";
  }
  const remainingSeconds = Math.max(Math.floor((nextFundingTime - now) / 1000), 0);
  const hours = Math.floor(remainingSeconds / 3600);
  const minutes = Math.floor((remainingSeconds % 3600) / 60);
  const seconds = remainingSeconds % 60;
  return [hours, minutes, seconds].map((item) => String(item).padStart(2, "0")).join(":");
}

function getMaintenanceMarginRate(notionalUsdt: number): number {
  const tier = MAINTENANCE_MARGIN_TIERS.find((item) => notionalUsdt <= item.maxNotionalUsdt);
  return tier?.rate ?? MAINTENANCE_MARGIN_TIERS[MAINTENANCE_MARGIN_TIERS.length - 1].rate;
}

function getRiskBufferRate(notionalUsdt: number): number {
  return getMaintenanceMarginRate(notionalUsdt) + LIQUIDATION_FEE_BUFFER_RATE;
}

function getPositionMaintenanceBuffer(position: OpenPosition, price = position.entryPrice): number {
  const quantity = getPositionQuantity(position);
  const notionalAtPrice = Math.max(quantity * price, 0);
  return notionalAtPrice * getRiskBufferRate(notionalAtPrice);
}

function getUsedInitialMargin(positions: OpenPosition[], exchangeId: number, excludePositionId?: number): number {
  return positions
    .filter((position) => position.exchangeId === exchangeId && position.id !== excludePositionId)
    .reduce((sum, position) => sum + position.marginUsdt, 0);
}

function getFreeMargin(exchange: Exchange, positions: OpenPosition[], excludePositionId?: number): number {
  return Math.max(exchange.balanceUsdt - getUsedInitialMargin(positions, exchange.id, excludePositionId), 0);
}

function getCrossCollateral(exchange: Exchange, positions: OpenPosition[], excludePositionId?: number): number {
  const sameExchangePositions = positions.filter((position) => position.exchangeId === exchange.id && position.id !== excludePositionId);
  const isolatedReserved = sameExchangePositions
    .filter((position) => position.marginMode === "isolated")
    .reduce((sum, position) => sum + position.marginUsdt, 0);
  const otherCrossMaintenance = sameExchangePositions
    .filter((position) => position.marginMode === "cross")
    .reduce((sum, position) => sum + getPositionMaintenanceBuffer(position), 0);
  return Math.max(exchange.balanceUsdt - isolatedReserved - otherCrossMaintenance, 0);
}

function getClosePercent(draft: CloseTradeDraft): number {
  const rawValue = numberFromInput(draft.percentValue);
  if (!Number.isFinite(rawValue) || rawValue <= 0) {
    return 0;
  }
  return Math.min(rawValue, 100);
}

function getClosePriceSelection(
  draft: CloseTradeDraft,
  position: OpenPosition,
  snapshot: MarketSnapshot | null
): { marketPrice: number; exitPrice: number; isCustomPriceValid: boolean; isCustomPriceSelected: boolean } {
  const marketPrice = getPositionClosePrice(position, snapshot);
  if (draft.priceMode === "market") {
    return {
      marketPrice,
      exitPrice: marketPrice,
      isCustomPriceValid: true,
      isCustomPriceSelected: false
    };
  }

  const customExitPrice = numberFromInput(draft.customExitPrice);
  const isCustomPriceValid = Number.isFinite(customExitPrice) && customExitPrice > 0;
  return {
    marketPrice,
    exitPrice: isCustomPriceValid ? customExitPrice : marketPrice,
    isCustomPriceValid,
    isCustomPriceSelected: true
  };
}

function getSnapshotMarkPrice(snapshot: MarketSnapshot | null, fallback: number): number {
  return snapshot?.lastPrice || snapshot?.bestBid || snapshot?.bestAsk || fallback;
}

function solveLiquidationPrice(entryPrice: number, quantity: number, side: TradeSide, collateralUsdt: number, riskRate: number): number {
  const entryValue = entryPrice * quantity;
  if (side === "long") {
    return (entryValue - collateralUsdt) / (quantity * (1 - riskRate));
  }
  return (entryValue + collateralUsdt) / (quantity * (1 + riskRate));
}

function getLiquidationPrice({
  collateralUsdt,
  entryPrice,
  quantity,
  side
}: {
  collateralUsdt: number;
  entryPrice: number;
  quantity: number;
  side: TradeSide;
}): number | null {
  if (
    !Number.isFinite(entryPrice) ||
    !Number.isFinite(quantity) ||
    !Number.isFinite(collateralUsdt) ||
    entryPrice <= 0 ||
    quantity <= 0 ||
    collateralUsdt <= 0
  ) {
    return null;
  }

  let liquidationPrice = solveLiquidationPrice(
    entryPrice,
    quantity,
    side,
    collateralUsdt,
    getRiskBufferRate(entryPrice * quantity)
  );

  for (let index = 0; index < 6; index += 1) {
    if (!Number.isFinite(liquidationPrice)) {
      return null;
    }
    const notionalAtLiquidation = Math.max(liquidationPrice * quantity, 0);
    const nextPrice = solveLiquidationPrice(entryPrice, quantity, side, collateralUsdt, getRiskBufferRate(notionalAtLiquidation));
    if (Math.abs(nextPrice - liquidationPrice) < 0.0000001) {
      break;
    }
    liquidationPrice = nextPrice;
  }

  if (!Number.isFinite(liquidationPrice)) {
    return null;
  }
  return Math.max(liquidationPrice, 0);
}

function getTicketQuantity(ticket: TradeTicket): number {
  const price = numberFromInput(ticket.price);
  const size = numberFromInput(ticket.size);
  if (!Number.isFinite(price) || !Number.isFinite(size) || price <= 0 || size <= 0) {
    return 0;
  }
  return ticket.sizeUnit === "TOKEN" ? size : size / price;
}

function getTicketLiquidationPrice(ticket: TradeTicket, exchange: Exchange | undefined, positions: OpenPosition[]): number | null {
  const entryPrice = numberFromInput(ticket.price);
  const quantity = getTicketQuantity(ticket);
  const collateralUsdt =
    ticket.marginMode === "cross" && exchange ? getCrossCollateral(exchange, positions) : getTicketMargin(ticket);
  return getLiquidationPrice({
    collateralUsdt,
    entryPrice,
    quantity,
    side: ticket.side
  });
}

function getPositionLiquidationPrice(position: OpenPosition, positions: OpenPosition[], exchange: Exchange | undefined): number | null {
  const collateralUsdt =
    position.marginMode === "cross" && exchange ? getCrossCollateral(exchange, positions, position.id) : position.marginUsdt;
  return getLiquidationPrice({
    collateralUsdt,
    entryPrice: position.entryPrice,
    quantity: getPositionQuantity(position),
    side: position.side
  });
}

function App() {
  const today = new Date();
  const [activePage, setActivePage] = useState<PageId>(getInitialPage);
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [exchanges, setExchanges] = useState<Exchange[]>([]);
  const [summary, setSummary] = useState<ExchangeSummary>(emptySummary);
  const [calendar, setCalendar] = useState<ProfitCalendarResponse | null>(null);
  const [calendarMonth, setCalendarMonth] = useState(() => ({ year: today.getFullYear(), month: today.getMonth() + 1 }));
  const [calendarRange, setCalendarRange] = useState<CalendarRange>({ start: null, end: null });
  const [isCalendarRangeEnabled, setIsCalendarRangeEnabled] = useState(false);
  const [selectedExchange, setSelectedExchange] = useState<Exchange | null>(null);
  const [balanceDraft, setBalanceDraft] = useState("");
  const [tickets, setTickets] = useState<TradeTicket[]>(getInitialTickets);
  const [nextTicketId, setNextTicketId] = useState(() => getNextTicketId(getInitialTickets()));
  const [openPositions, setOpenPositions] = useState<OpenPosition[]>(getInitialOpenPositions);
  const [closedPositions, setClosedPositions] = useState<ClosedPosition[]>([]);
  const [nextPositionId, setNextPositionId] = useState(() => getNextPositionId(getInitialOpenPositions()));
  const [positionSnapshots, setPositionSnapshots] = useState<Record<number, MarketSnapshot>>({});
  const [expandedSymbols, setExpandedSymbols] = useState<Record<string, boolean>>({});
  const [situations, setSituations] = useState<Situation[]>([]);
  const [situationSettings, setSituationSettings] = useState<SituationSettings | null>(null);
  const [situationSettingsDraft, setSituationSettingsDraft] = useState<SituationSettingsDraft>({
    credentialsPath: "backend/google-service-account.json",
    spreadsheetId: "",
    sheetName: "Situations"
  });
  const [situationSettingsCheck, setSituationSettingsCheck] = useState<SituationSettingsTestResponse | null>(null);
  const [isSituationSettingsOpen, setIsSituationSettingsOpen] = useState(false);
  const [situationDraft, setSituationDraft] = useState<SituationDraft>({
    date: new Date().toISOString().slice(0, 10),
    token: "",
    description: "",
    posts: ""
  });
  const [situationModal, setSituationModal] = useState<SituationModalState | null>(null);
  const [situationDeleteDraft, setSituationDeleteDraft] = useState<Situation | null>(null);
  const [openTradeDraft, setOpenTradeDraft] = useState<OpenTradeDraft | null>(null);
  const [closeTradeDraft, setCloseTradeDraft] = useState<CloseTradeDraft | null>(null);
  const [exitOrderDraft, setExitOrderDraft] = useState<ExitOrderDraft | null>(null);
  const [depositDraft, setDepositDraft] = useState<DepositDraft | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSituationsLoading, setIsSituationsLoading] = useState(false);
  const [isSituationSettingsLoading, setIsSituationSettingsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadCalendar(targetMonth = calendarMonth) {
    setError(null);
    try {
      const calendarPayload = await getProfitCalendar(targetMonth.year, targetMonth.month);
      setCalendar(calendarPayload);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Не удалось загрузить календарь");
    }
  }

  async function loadData(targetMonth = calendarMonth) {
    setIsLoading(true);
    setError(null);
    try {
      const [userPayload, exchangePayload, calendarPayload, openTradesPayload, closedTradesPayload] = await Promise.all([
        getCurrentUser(),
        getExchanges(),
        getProfitCalendar(targetMonth.year, targetMonth.month),
        getTrades("open"),
        getTrades("closed")
      ]);
      const sortedExchanges = sortExchanges(exchangePayload.exchanges);
      const backendOpenPositions = openTradesPayload.trades.map(tradeToOpenPosition).filter((position): position is OpenPosition => position !== null);
      const restoredTickets = getInitialTickets(userPayload).map((ticket) => normalizeTicketExchange(ticket, sortedExchanges));
      setCurrentUser(userPayload);
      setActivePage(getInitialPage(userPayload));
      setExchanges(sortedExchanges);
      setSummary(exchangePayload.summary);
      setCalendar(calendarPayload);
      setOpenPositions(backendOpenPositions);
      setNextPositionId(getNextPositionId(backendOpenPositions));
      setClosedPositions(closedTradesPayload.trades.map(tradeToClosedPosition).filter((position): position is ClosedPosition => position !== null));
      setTickets(restoredTickets);
      setNextTicketId(getNextTicketId(restoredTickets));
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Не удалось загрузить данные");
    } finally {
      setIsLoading(false);
    }
  }

  async function loadSituations() {
    setIsSituationsLoading(true);
    setError(null);
    try {
      const payload = await getSituations();
      setSituations(payload.situations);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Не удалось загрузить ситуации");
    } finally {
      setIsSituationsLoading(false);
    }
  }

  function applySituationSettings(settings: SituationSettings) {
    setSituationSettings(settings);
    setSituationSettingsDraft({
      credentialsPath: settings.credentialsPath || "backend/google-service-account.json",
      spreadsheetId: settings.spreadsheetId || "",
      sheetName: settings.sheetName || "Situations"
    });
  }

  async function loadSituationSettings() {
    setIsSituationSettingsLoading(true);
    setError(null);
    try {
      const settings = await getSituationSettings();
      applySituationSettings(settings);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Не удалось загрузить настройки ситуаций");
    } finally {
      setIsSituationSettingsLoading(false);
    }
  }

  async function openSituationSettingsModal() {
    setIsSituationSettingsOpen(true);
    setSituationSettingsCheck(null);
    await loadSituationSettings();
  }

  function closeSituationSettingsModal() {
    if (isSaving || isSituationSettingsLoading) {
      return;
    }
    setIsSituationSettingsOpen(false);
    setSituationSettingsCheck(null);
  }

  async function handleSaveSituationSettings() {
    setIsSaving(true);
    setError(null);
    try {
      const settings = await updateSituationSettings({
        credentials_path: situationSettingsDraft.credentialsPath.trim() || "backend/google-service-account.json",
        spreadsheet_id: situationSettingsDraft.spreadsheetId.trim(),
        sheet_name: situationSettingsDraft.sheetName.trim() || "Situations"
      });
      applySituationSettings(settings);
      setSituationSettingsCheck(null);
      await loadSituations();
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Не удалось сохранить настройки ситуаций");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleTestSituationSettings() {
    setIsSituationSettingsLoading(true);
    setError(null);
    try {
      const result = await testSituationSettings();
      setSituationSettingsCheck(result);
      applySituationSettings(result.settings);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Не удалось проверить Google Sheets");
    } finally {
      setIsSituationSettingsLoading(false);
    }
  }

  useEffect(() => {
    void loadData(calendarMonth);
  }, []);

  useEffect(() => {
    if (!currentUser) {
      return;
    }
    window.localStorage.setItem(getUserStorageKey(ACTIVE_PAGE_STORAGE_KEY, currentUser), activePage);
  }, [activePage, currentUser]);

  useEffect(() => {
    if (activePage === "situations") {
      void loadSituations();
      const refreshTimer = window.setInterval(() => {
        void loadSituations();
      }, 30000);
      return () => window.clearInterval(refreshTimer);
    }
    return undefined;
  }, [activePage]);

  useEffect(() => {
    if (!currentUser) {
      return;
    }
    window.localStorage.setItem(getUserStorageKey(TRADE_TICKETS_STORAGE_KEY, currentUser), JSON.stringify(tickets));
  }, [tickets, currentUser]);

  useEffect(() => {
    if (!currentUser) {
      return;
    }
    window.localStorage.setItem(getUserStorageKey(OPEN_POSITIONS_STORAGE_KEY, currentUser), JSON.stringify(openPositions));
  }, [openPositions, currentUser]);

  function normalizeTicketExchange(ticket: TradeTicket, nextExchanges: Exchange[]): TradeTicket {
    if (ticket.exchangeId === "") {
      return ticket;
    }
    if (ticket.exchangeId && nextExchanges.some((exchange) => exchange.id === ticket.exchangeId)) {
      return ticket;
    }
    return { ...ticket, exchangeId: "" };
  }

  function openBalanceModal(exchange: Exchange) {
    setSelectedExchange(exchange);
    setBalanceDraft(String(exchange.balanceUsdt));
  }

  function closeModal() {
    if (isSaving) {
      return;
    }
    setSelectedExchange(null);
    setBalanceDraft("");
  }

  async function handleSaveBalance() {
    if (!selectedExchange) {
      return;
    }

    const parsedBalance = numberFromInput(balanceDraft);
    if (!Number.isFinite(parsedBalance) || parsedBalance < 0) {
      setError("Введите корректный баланс");
      return;
    }

    setIsSaving(true);
    setError(null);
    try {
      await updateExchangeBalance(selectedExchange.id, parsedBalance);
      await loadData();
      setSelectedExchange(null);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Не удалось сохранить баланс");
    } finally {
      setIsSaving(false);
    }
  }

  async function handleResetPnl() {
    if (!selectedExchange) {
      return;
    }

    setIsSaving(true);
    setError(null);
    try {
      await resetExchangePnl(selectedExchange.id);
      await loadData();
      setSelectedExchange(null);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Не удалось сбросить PnL");
    } finally {
      setIsSaving(false);
    }
  }

  function openDepositModal() {
    setDepositDraft({
      fromExchangeId: exchanges[0]?.id ?? "",
      toExchangeId: exchanges[1]?.id ?? "",
      amount: ""
    });
  }

  function closeDepositModal() {
    if (isSaving) {
      return;
    }
    setDepositDraft(null);
  }

  async function handleSaveDeposit() {
    if (!depositDraft || depositDraft.fromExchangeId === "" || depositDraft.toExchangeId === "") {
      return;
    }
    const amount = numberFromInput(depositDraft.amount);
    if (!Number.isFinite(amount) || amount <= 0) {
      setError("Введите корректную сумму перевода");
      return;
    }

    setIsSaving(true);
    setError(null);
    try {
      await transferBetweenExchanges({
        from_exchange_id: depositDraft.fromExchangeId,
        to_exchange_id: depositDraft.toExchangeId,
        amount_usdt: amount
      });
      await loadData();
      setDepositDraft(null);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Не удалось выполнить перевод");
    } finally {
      setIsSaving(false);
    }
  }

  function getEmptySituationDraft(): SituationDraft {
    return {
      date: new Date().toISOString().slice(0, 10),
      token: "",
      description: "",
      posts: ""
    };
  }

  function openCreateSituationModal() {
    setSituationDraft(getEmptySituationDraft());
    setSituationModal({ mode: "create" });
  }

  function openEditSituationModal(situation: Situation) {
    setSituationDraft({
      date: situation.date,
      token: situation.token,
      description: situation.description,
      posts: situation.posts
    });
    setSituationModal({ mode: "edit", rowNumber: situation.rowNumber });
  }

  function closeSituationModal() {
    if (isSaving) {
      return;
    }
    setSituationModal(null);
    setSituationDraft(getEmptySituationDraft());
  }

  async function handleSaveSituation() {
    const payload = {
      date: situationDraft.date.trim(),
      token: situationDraft.token.trim().toUpperCase(),
      description: situationDraft.description.trim(),
      posts: situationDraft.posts.trim()
    };
    if (!payload.date || !payload.token || !payload.description) {
      setError("Заполните дату, токен и описание ситуации");
      return;
    }

    setIsSaving(true);
    setError(null);
    try {
      if (situationModal?.mode === "edit" && situationModal.rowNumber) {
        await updateSituation(situationModal.rowNumber, payload);
      } else {
        await createSituation(payload);
      }
      setSituationModal(null);
      setSituationDraft(getEmptySituationDraft());
      await loadSituations();
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Не удалось сохранить ситуацию");
    } finally {
      setIsSaving(false);
    }
  }

  function requestDeleteSituation(situation: Situation) {
    setSituationDeleteDraft(situation);
  }

  function closeSituationDeleteModal() {
    if (isSaving) {
      return;
    }
    setSituationDeleteDraft(null);
  }

  async function handleDeleteSituation() {
    if (!situationDeleteDraft) {
      return;
    }

    setIsSaving(true);
    setError(null);
    try {
      await deleteSituation(situationDeleteDraft.rowNumber);
      setSituationDeleteDraft(null);
      await loadSituations();
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Не удалось удалить ситуацию");
    } finally {
      setIsSaving(false);
    }
  }

  function shiftCalendarMonth(delta: number) {
    setCalendarRange({ start: null, end: null });
    const nextDate = new Date(calendarMonth.year, calendarMonth.month - 1 + delta, 1);
    const nextMonth = {
      year: nextDate.getFullYear(),
      month: nextDate.getMonth() + 1
    };
    setCalendarMonth(nextMonth);
    void loadCalendar(nextMonth);
  }

  function selectCalendarDate(dateValue: string) {
    if (!isCalendarRangeEnabled) {
      return;
    }
    setCalendarRange((current) => {
      if (!current.start || current.end) {
        return { start: dateValue, end: null };
      }
      if (current.start === dateValue) {
        return { start: dateValue, end: null };
      }
      return { start: current.start, end: dateValue };
    });
  }

  function toggleCalendarRangeMode() {
    setIsCalendarRangeEnabled((current) => {
      if (current) {
        setCalendarRange({ start: null, end: null });
      }
      return !current;
    });
  }

  function addTicket() {
    setTickets((current) => [...current, createTicket(nextTicketId)]);
    setNextTicketId((current) => current + 1);
  }

  function updateTicket(ticketId: number, patch: Partial<TradeTicket>) {
    setTickets((current) => current.map((ticket) => (ticket.id === ticketId ? { ...ticket, ...patch } : ticket)));
  }

  function removeTicket(ticketId: number) {
    setTickets((current) => current.filter((ticket) => ticket.id !== ticketId));
  }

  function requestOpenTrade(ticket: TradeTicket, snapshot: MarketSnapshot | null = null) {
    const exchange = exchanges.find((item) => item.id === ticket.exchangeId);
    const resolvedSymbol = getResolvedTicketSymbol(ticket);
    const price = numberFromInput(ticket.price);
    const size = numberFromInput(ticket.size);
    const notional = getTicketNotional(ticket);
    const margin = getTicketMargin(ticket);
    const leverage = getTicketLeverage(ticket);
    const markPrice = getSnapshotMarkPrice(snapshot, price);
    const freeMargin = exchange ? getFreeMargin(exchange, openPositions) : 0;

    if (!exchange || !resolvedSymbol || !Number.isFinite(price) || price <= 0 || !Number.isFinite(size) || size <= 0) {
      updateTicket(ticket.id, { message: "Заполните биржу, тикер, цену и сайз" });
      return;
    }

    if (margin > freeMargin) {
      updateTicket(ticket.id, { message: "Маржа больше доступного баланса" });
      return;
    }

    setOpenTradeDraft({
      ticket,
      exchange,
      symbol: resolvedSymbol,
      quoteAsset: snapshot?.quoteAsset ?? "USDT",
      entryPrice: price,
      markPrice,
      sizeValue: size,
      notionalUsdt: notional,
      marginUsdt: margin,
      leverage,
      marginMode: ticket.marginMode,
      liquidationPrice: getTicketLiquidationPrice(ticket, exchange, openPositions)
    });
  }

  async function confirmOpenTrade() {
    if (!openTradeDraft) {
      return;
    }

    const { ticket, exchange, symbol, entryPrice, sizeValue, notionalUsdt, marginUsdt, leverage, marginMode } = openTradeDraft;
    setIsSaving(true);
    try {
      const existingGroupId = openPositions.find((position) => position.symbol === symbol)?.groupId;
      const groupId = existingGroupId ?? `${symbol}-${Date.now()}-${nextPositionId}`;
      const createdTrade = await createTrade({
        exchange_id: exchange.id,
        group_id: groupId,
        symbol,
        side: ticket.side,
        entry_price: entryPrice,
        size_value: sizeValue,
        size_unit: ticket.sizeUnit,
        notional_usdt: notionalUsdt,
        margin_usdt: marginUsdt,
        leverage,
        margin_mode: marginMode
      });
      const nextPosition: OpenPosition = {
        id: createdTrade.tradeId,
        groupId,
        tradeId: createdTrade.tradeId,
        exchangeId: exchange.id,
        exchangeSlug: exchange.slug,
        exchangeName: exchange.name,
        symbol,
        side: ticket.side,
        marginMode,
        leverage,
        entryPrice,
        sizeValue,
        sizeUnit: ticket.sizeUnit,
        notionalUsdt,
        marginUsdt,
        realizedPnlUsdt: 0,
        realizedPricePnlUsdt: 0,
        lastFundingAppliedAt: null,
        exitOrders: [],
        openedAt: new Date().toISOString()
      };
      setOpenPositions((current) => [...current, nextPosition]);
      setExpandedSymbols((current) => ({ ...current, [symbol]: true }));
      setNextPositionId((current) => Math.max(current, createdTrade.tradeId + 1));
      removeTicket(ticket.id);
      setOpenTradeDraft(null);
    } catch (caughtError) {
      updateTicket(ticket.id, {
        message: caughtError instanceof Error ? caughtError.message : "Не удалось открыть сделку"
      });
    } finally {
      setIsSaving(false);
    }
  }

  function requestCloseTrade(position: OpenPosition) {
    const percentValue = "100";
    const marketClosePrice = getPositionClosePrice(position, positionSnapshots[position.id] ?? null);
    setCloseTradeDraft({
      position,
      priceMode: "market",
      customExitPrice: String(roundInput(marketClosePrice)),
      percentValue,
      usdtValue: String(roundInput(getPositionCloseNotional(position) * (Number(percentValue) / 100)))
    });
  }

  function requestExitOrder(position: OpenPosition, order: TradeExitOrder | null = null) {
    const marketPrice = getPositionClosePrice(position, positionSnapshots[position.id] ?? null);
    const defaultType: TradeExitOrder["orderType"] = order?.orderType ?? "take_profit";
    const positionNotional = getPositionCloseNotional(position);
    const makeLeg = (orderType: TradeExitOrder["orderType"]): ExitOrderLegDraft => {
      const sourceOrder = order?.orderType === orderType ? order : null;
      const defaultPnlPercent = orderType === "take_profit" ? 25 : -10;
      const pnlPercent = sourceOrder?.pnlPercent ?? defaultPnlPercent;
      const defaultPrice = getPositionPriceForPnlPercent(position, pnlPercent);
      return {
        triggerMode: sourceOrder?.triggerMode ?? "price",
        metricMode: sourceOrder?.triggerMode === "pnl_percent" ? "roe" : "pnl",
        triggerPrice: String(roundInput(sourceOrder?.triggerPrice ?? (Number.isFinite(defaultPrice) && defaultPrice > 0 ? defaultPrice : marketPrice))),
        pnlPercent: String(roundInput(pnlPercent)),
        pnlUsdt: String(roundInput(position.marginUsdt * (pnlPercent / 100))),
        sizeMode: sourceOrder?.sizeMode ?? "percent",
        sizePercent: String(roundInput(sourceOrder?.sizePercent ?? 100)),
        sizeUsdt: String(roundInput(sourceOrder?.sizeUsdt ?? positionNotional))
      };
    };
    const legs = {
      take_profit: makeLeg("take_profit"),
      stop_loss: makeLeg("stop_loss")
    };
    const activeLeg = legs[defaultType];
    setExitOrderDraft({
      position,
      order,
      orderType: defaultType,
      triggerMode: activeLeg.triggerMode,
      triggerPrice: activeLeg.triggerPrice,
      pnlPercent: activeLeg.pnlPercent,
      sizeMode: activeLeg.sizeMode,
      sizePercent: activeLeg.sizePercent,
      sizeUsdt: activeLeg.sizeUsdt,
      positionScope: numberFromInput(activeLeg.sizePercent) >= 100 ? "full" : "partial",
      legs
    });
  }

  async function saveExitOrder() {
    if (!exitOrderDraft) {
      return;
    }
    const position = openPositions.find((item) => item.id === exitOrderDraft.position.id) ?? exitOrderDraft.position;
    const orderTypesToSave: TradeExitOrder["orderType"][] = exitOrderDraft.order || exitOrderDraft.positionScope !== "full"
      ? [exitOrderDraft.orderType]
      : ["take_profit", "stop_loss"];
    const payloads = orderTypesToSave.map((orderType) => {
      const leg = exitOrderDraft.legs[orderType];
      const triggerPrice = numberFromInput(leg.triggerPrice);
      const pnlPercent = numberFromInput(leg.pnlPercent);
      const sizePercent = numberFromInput(leg.sizePercent);
      const sizeUsdt = numberFromInput(leg.sizeUsdt);
      return {
        orderType,
        payload: {
          order_type: orderType,
          trigger_mode: leg.triggerMode,
          trigger_price: triggerPrice,
          pnl_percent: pnlPercent,
          size_mode: leg.sizeMode,
          size_percent: sizePercent,
          size_usdt: sizeUsdt
        } satisfies TradeExitOrderPayload
      };
    });
    if (
      payloads.some(({ payload }) => (
        !Number.isFinite(payload.trigger_price) ||
        payload.trigger_price <= 0 ||
        !Number.isFinite(payload.pnl_percent) ||
        !Number.isFinite(payload.size_percent) ||
        payload.size_percent <= 0 ||
        payload.size_percent > 100 ||
        !Number.isFinite(payload.size_usdt) ||
        payload.size_usdt <= 0
      ))
    ) {
      setError("Введите корректные параметры TP/SL");
      return;
    }
    setIsSaving(true);
    setError(null);
    try {
      for (const { orderType, payload } of payloads) {
        const existingOrder = exitOrderDraft.order?.orderType === orderType
          ? exitOrderDraft.order
          : position.exitOrders.find((order) => order.orderType === orderType && order.sizePercent >= 100);
        if (existingOrder) {
          await updateTradeExitOrder(position.id, existingOrder.id, payload);
        } else {
          await createTradeExitOrder(position.id, payload);
        }
      }
      await loadData();
      setExitOrderDraft(null);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Не удалось сохранить TP/SL");
    } finally {
      setIsSaving(false);
    }
  }

  async function removeExitOrder(order: TradeExitOrder) {
    if (!exitOrderDraft) {
      return;
    }
    setIsSaving(true);
    setError(null);
    try {
      await deleteTradeExitOrder(exitOrderDraft.position.id, order.id);
      await loadData();
      setExitOrderDraft(null);
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Не удалось удалить TP/SL");
    } finally {
      setIsSaving(false);
    }
  }

  async function confirmCloseTrade() {
    if (!closeTradeDraft) {
      return;
    }

    const closePercent = getClosePercent(closeTradeDraft);
    if (closePercent <= 0) {
      return;
    }
    const positionToClose = openPositions.find((position) => position.id === closeTradeDraft.position.id) ?? closeTradeDraft.position;
    const priceSelection = getClosePriceSelection(closeTradeDraft, positionToClose, positionSnapshots[positionToClose.id] ?? null);
    if (!priceSelection.isCustomPriceValid) {
      setError("Введите корректную цену закрытия");
      return;
    }
    const realizedPnlDelta = getTradePricePnlUsdt(
      positionToClose.side,
      positionToClose.entryPrice,
      priceSelection.exitPrice,
      positionToClose.sizeValue,
      positionToClose.sizeUnit
    ) * (closePercent / 100);

    if (closePercent >= 99.999) {
      const totalRealizedPnl = roundInput(positionToClose.realizedPnlUsdt + realizedPnlDelta);
      const closedPosition: ClosedPosition = {
        id: positionToClose.id,
        groupId: positionToClose.groupId,
        tradeId: positionToClose.tradeId,
        exchangeId: positionToClose.exchangeId,
        exchangeSlug: positionToClose.exchangeSlug,
        exchangeName: positionToClose.exchangeName,
        symbol: positionToClose.symbol,
        side: positionToClose.side,
        marginMode: positionToClose.marginMode,
        leverage: positionToClose.leverage,
        entryPrice: positionToClose.entryPrice,
        exitPrice: priceSelection.exitPrice,
        sizeValue: positionToClose.sizeValue,
        sizeUnit: positionToClose.sizeUnit,
        notionalUsdt: positionToClose.notionalUsdt,
        marginUsdt: positionToClose.marginUsdt,
        realizedPnlUsdt: totalRealizedPnl,
        comment: "",
        openedAt: positionToClose.openedAt,
        closedAt: new Date().toISOString()
      };
      setOpenPositions((current) => current.filter((position) => position.id !== positionToClose.id));
      setClosedPositions((current) => [closedPosition, ...current]);
      setPositionSnapshots((current) => {
        const next = { ...current };
        delete next[positionToClose.id];
        return next;
      });
      if (positionToClose.tradeId) {
        setIsSaving(true);
        try {
          await closeTrade(positionToClose.tradeId, {
            exit_price: priceSelection.exitPrice,
            realized_pnl_usdt: totalRealizedPnl,
            group_id: positionToClose.groupId,
            notional_usdt: positionToClose.notionalUsdt,
            leverage: positionToClose.leverage,
            margin_mode: positionToClose.marginMode
          });
          await loadData();
        } catch (caughtError) {
          setError(caughtError instanceof Error ? caughtError.message : "Не удалось закрыть сделку в базе");
          setClosedPositions((current) => current.filter((position) => position.id !== positionToClose.id));
          setOpenPositions((current) => (current.some((position) => position.id === positionToClose.id) ? current : [...current, positionToClose]));
        } finally {
          setIsSaving(false);
        }
      }
    } else {
      const multiplier = (100 - closePercent) / 100;
      if (positionToClose.tradeId) {
        setIsSaving(true);
        try {
          await realizeTradePnl(positionToClose.tradeId, {
            realized_pnl_usdt: realizedPnlDelta,
            size_value: roundInput(positionToClose.sizeValue * multiplier),
            notional_usdt: roundInput(positionToClose.notionalUsdt * multiplier),
            margin_usdt: roundInput(positionToClose.marginUsdt * multiplier)
          });
          await loadData();
          setCloseTradeDraft(null);
          return;
        } catch (caughtError) {
          setError(caughtError instanceof Error ? caughtError.message : "Не удалось зафиксировать частичный PnL");
          setIsSaving(false);
          return;
        } finally {
          setIsSaving(false);
        }
      }
      setOpenPositions((current) =>
        current.map((position) =>
          position.id === positionToClose.id
            ? {
                ...position,
                sizeValue: roundInput(position.sizeValue * multiplier),
                notionalUsdt: roundInput(position.notionalUsdt * multiplier),
                marginUsdt: roundInput(position.marginUsdt * multiplier),
                realizedPnlUsdt: roundInput(position.realizedPnlUsdt + realizedPnlDelta),
                realizedPricePnlUsdt: roundInput(position.realizedPricePnlUsdt + realizedPnlDelta)
              }
            : position
        )
      );
    }
    setCloseTradeDraft(null);
  }

  function deleteOpenPosition(position: OpenPosition) {
    setOpenPositions((current) => current.filter((item) => item.id !== position.id));
    setPositionSnapshots((current) => {
      const next = { ...current };
      delete next[position.id];
      return next;
    });
    if (position.tradeId) {
      void deleteTrade(position.tradeId).catch((caughtError) => {
        setError(caughtError instanceof Error ? caughtError.message : "Не удалось удалить сделку");
      });
    }
  }

  function updateClosedDealComment(groupId: string, comment: string) {
    setClosedPositions((current) => current.map((position) => (position.groupId === groupId ? { ...position, comment } : position)));
    void updateTradeGroupComment(groupId, comment).catch((caughtError) => {
      setError(caughtError instanceof Error ? caughtError.message : "Не удалось сохранить комментарий сделки");
    });
  }

  async function deleteClosedDeal(groupId: string) {
    const positionsToDelete = closedPositions.filter((position) => position.groupId === groupId);
    const tradeIds = positionsToDelete
      .map((position) => position.tradeId)
      .filter((tradeId): tradeId is number => typeof tradeId === "number");

    setIsSaving(true);
    setError(null);
    try {
      for (const tradeId of tradeIds) {
        await revertClosedTrade(tradeId);
      }
      setClosedPositions((current) => current.filter((position) => position.groupId !== groupId));
      await loadData();
    } catch (caughtError) {
      setError(caughtError instanceof Error ? caughtError.message : "Не удалось удалить сделку и откатить PnL");
    } finally {
      setIsSaving(false);
    }
  }

  const handlePositionSnapshot = useCallback((positionId: number, snapshot: MarketSnapshot) => {
    setPositionSnapshots((current) => ({
      ...current,
      [positionId]: snapshot
    }));
  }, []);

  return (
    <main className="app-shell tape-carbon">
      <aside className="side-rail">
        <div className="brand-lockup">
          <div className="brand-symbol">
            <Landmark size={20} />
          </div>
          <div>
            <strong>ProfitsNLosses</strong>
            <span>{"\u041a\u0440\u0438\u043f\u0442\u043e PnL"}</span>
          </div>
        </div>

        <nav className="rail-nav" aria-label="Навигация">
          <button className={activePage === "exchanges" ? "rail-link is-active" : "rail-link"} type="button" onClick={() => setActivePage("exchanges")}>
            <LayoutDashboard size={18} />
            <span>Биржи</span>
          </button>
          <button className={activePage === "trades" ? "rail-link is-active" : "rail-link"} type="button" onClick={() => setActivePage("trades")}>
            <TrendingUp size={18} />
            <span>Позиции</span>
          </button>
          <button className={activePage === "deals" ? "rail-link is-active" : "rail-link"} type="button" onClick={() => setActivePage("deals")}>
            <History size={18} />
            <span>Сделки</span>
          </button>
          <button className={activePage === "situations" ? "rail-link is-active" : "rail-link"} type="button" onClick={() => setActivePage("situations")}>
            <ClipboardList size={18} />
            <span>Ситуации</span>
          </button>
          <a className="rail-link rail-link-home" href="/" title="Вернуться на главную страницу">
            <Home size={18} />
            <span>{"\u0413\u043b\u0430\u0432\u043d\u0430\u044f"}</span>
          </a>
        </nav>
      </aside>

      <section className="workspace">
        {activePage === "exchanges" ? (
          <ExchangesPage
            summary={summary}
            calendar={calendar}
            error={error}
            exchanges={exchanges}
            isLoading={isLoading}
            isRangeSelectionEnabled={isCalendarRangeEnabled}
            range={calendarRange}
            onEditBalance={openBalanceModal}
            onOpenDeposit={openDepositModal}
            onSelectCalendarDate={selectCalendarDate}
            onShiftCalendarMonth={shiftCalendarMonth}
            onToggleCalendarRange={toggleCalendarRangeMode}
          />
        ) : null}

        {activePage === "trades" ? (
          <TradesPage
            exchanges={exchanges}
            tickets={tickets}
            onAddTicket={addTicket}
            onRemoveTicket={removeTicket}
            onUpdateTicket={updateTicket}
            onOpenTrade={requestOpenTrade}
            openPositions={openPositions}
            positionSnapshots={positionSnapshots}
            expandedSymbols={expandedSymbols}
            onToggleSymbol={(symbol) => setExpandedSymbols((current) => ({ ...current, [symbol]: !current[symbol] }))}
            onCloseTrade={requestCloseTrade}
            onExitOrder={requestExitOrder}
            onDeleteTrade={deleteOpenPosition}
            onPositionSnapshot={handlePositionSnapshot}
          />
        ) : null}

        {activePage === "deals" ? (
          <ClosedDealsPage
            closedPositions={closedPositions}
            onDeleteDeal={deleteClosedDeal}
            onUpdateComment={updateClosedDealComment}
          />
        ) : null}

        {activePage === "situations" ? (
          <SituationsPage
            error={error}
            isLoading={isSituationsLoading}
            isSaving={isSaving}
            situations={situations}
            onDelete={requestDeleteSituation}
            onEdit={openEditSituationModal}
            onOpenCreate={openCreateSituationModal}
            onOpenSettings={() => void openSituationSettingsModal()}
            onRefresh={() => void loadSituations()}
          />
        ) : null}
      </section>

      {selectedExchange ? (
        <BalanceModal
          exchange={selectedExchange}
          balanceDraft={balanceDraft}
          isSaving={isSaving}
          onChange={setBalanceDraft}
          onClose={closeModal}
          onSave={() => void handleSaveBalance()}
          onReset={() => void handleResetPnl()}
        />
      ) : null}

      {depositDraft ? (
        <DepositModal
          draft={depositDraft}
          exchanges={exchanges}
          isSaving={isSaving}
          onChange={setDepositDraft}
          onClose={closeDepositModal}
          onSave={() => void handleSaveDeposit()}
        />
      ) : null}

      {situationModal ? (
        <SituationModal
          draft={situationDraft}
          isSaving={isSaving}
          mode={situationModal.mode}
          onChange={setSituationDraft}
          onClose={closeSituationModal}
          onSave={() => void handleSaveSituation()}
        />
      ) : null}

      {situationDeleteDraft ? (
        <SituationDeleteModal
          isSaving={isSaving}
          situation={situationDeleteDraft}
          onClose={closeSituationDeleteModal}
          onConfirm={() => void handleDeleteSituation()}
        />
      ) : null}

      {isSituationSettingsOpen ? (
        <SituationSettingsModal
          checkResult={situationSettingsCheck}
          draft={situationSettingsDraft}
          isLoading={isSituationSettingsLoading}
          isSaving={isSaving}
          settings={situationSettings}
          onChange={setSituationSettingsDraft}
          onClose={closeSituationSettingsModal}
          onSave={() => void handleSaveSituationSettings()}
          onTest={() => void handleTestSituationSettings()}
        />
      ) : null}

      {openTradeDraft ? (
        <OpenTradeConfirmModal
          draft={openTradeDraft}
          isSaving={isSaving}
          onClose={() => !isSaving && setOpenTradeDraft(null)}
          onConfirm={() => void confirmOpenTrade()}
        />
      ) : null}

      {closeTradeDraft ? (
        <CloseTradeConfirmModal
          draft={closeTradeDraft}
          exchange={exchanges.find((exchange) => exchange.id === closeTradeDraft.position.exchangeId)}
          positions={openPositions}
          snapshot={positionSnapshots[closeTradeDraft.position.id] ?? null}
          onChange={setCloseTradeDraft}
          onClose={() => setCloseTradeDraft(null)}
          onConfirm={() => void confirmCloseTrade()}
        />
      ) : null}

      {exitOrderDraft ? (
        <ExitOrderModal
          draft={exitOrderDraft}
          isSaving={isSaving}
          snapshot={positionSnapshots[exitOrderDraft.position.id] ?? null}
          onChange={setExitOrderDraft}
          onClose={() => !isSaving && setExitOrderDraft(null)}
          onDeleteOrder={(order) => void removeExitOrder(order)}
          onSave={() => void saveExitOrder()}
        />
      ) : null}
    </main>
  );
}

type ExchangesPageProps = {
  summary: ExchangeSummary;
  calendar: ProfitCalendarResponse | null;
  isRangeSelectionEnabled: boolean;
  range: CalendarRange;
  error: string | null;
  exchanges: Exchange[];
  isLoading: boolean;
  onEditBalance: (exchange: Exchange) => void;
  onOpenDeposit: () => void;
  onSelectCalendarDate: (date: string) => void;
  onShiftCalendarMonth: (delta: number) => void;
  onToggleCalendarRange: () => void;
};

function ExchangesPage({
  summary,
  calendar,
  isRangeSelectionEnabled,
  range,
  error,
  exchanges,
  isLoading,
  onEditBalance,
  onOpenDeposit,
  onSelectCalendarDate,
  onShiftCalendarMonth,
  onToggleCalendarRange
}: ExchangesPageProps) {
  return (
    <>
      <section className="summary-grid" aria-label="Сводка по биржам">
        <SummaryTile icon={<Wallet size={20} />} label="Баланс" value={formatMoney(summary.totalBalanceUsdt)} tone="neutral" />
        <SummaryTile
          icon={<BarChart3 size={20} />}
          label="PnL со старта"
          value={formatSigned(summary.totalPnlUsdt)}
          tone={summary.totalPnlUsdt >= 0 ? "positive" : "negative"}
        />
        <SummaryTile icon={<Layers3 size={20} />} label="Биржи" value={String(summary.exchangeCount)} tone="neutral" />
        <SummaryTile
          icon={<CalendarDays size={20} />}
          label={getMonthName(calendar)}
          value={formatSigned(calendar?.totalPnlUsdt ?? 0)}
          tone={(calendar?.totalPnlUsdt ?? 0) >= 0 ? "positive" : "negative"}
        />
      </section>

      {error ? <div className="error-banner">{error}</div> : null}

      <section className="content-grid">
        <ExchangePanel exchanges={exchanges} isLoading={isLoading} onEdit={onEditBalance} />
        <div className="calendar-column">
          <RangeCalendarPanel
            calendar={calendar}
            isRangeSelectionEnabled={isRangeSelectionEnabled}
            range={range}
            onSelectDate={onSelectCalendarDate}
            onShiftMonth={onShiftCalendarMonth}
            onToggleRange={onToggleCalendarRange}
          />
          <button className="deposit-button" type="button" onClick={onOpenDeposit}>
            <ArrowRightLeft size={17} />
            <span>Депозит</span>
          </button>
        </div>
      </section>
    </>
  );
}

type TradesPageProps = {
  exchanges: Exchange[];
  tickets: TradeTicket[];
  openPositions: OpenPosition[];
  positionSnapshots: Record<number, MarketSnapshot>;
  expandedSymbols: Record<string, boolean>;
  onAddTicket: () => void;
  onRemoveTicket: (ticketId: number) => void;
  onUpdateTicket: (ticketId: number, patch: Partial<TradeTicket>) => void;
  onOpenTrade: (ticket: TradeTicket, snapshot?: MarketSnapshot | null) => void;
  onCloseTrade: (position: OpenPosition) => void;
  onExitOrder: (position: OpenPosition, order?: TradeExitOrder | null) => void;
  onDeleteTrade: (position: OpenPosition) => void;
  onToggleSymbol: (symbol: string) => void;
  onPositionSnapshot: (positionId: number, snapshot: MarketSnapshot) => void;
};

function TradesPage({
  exchanges,
  tickets,
  openPositions,
  positionSnapshots,
  expandedSymbols,
  onAddTicket,
  onRemoveTicket,
  onUpdateTicket,
  onOpenTrade,
  onCloseTrade,
  onExitOrder,
  onDeleteTrade,
  onToggleSymbol,
  onPositionSnapshot
}: TradesPageProps) {
  return (
    <>
      <section className="trade-board">
        {tickets.map((ticket) => (
          <TradeTicketCard
            exchanges={exchanges}
            key={ticket.id}
            openPositions={openPositions}
            ticket={ticket}
            onRemove={onRemoveTicket}
            onUpdate={onUpdateTicket}
            onOpenTrade={onOpenTrade}
          />
        ))}
        <button className="trade-add-card" type="button" onClick={onAddTicket} aria-label="Добавить окно биржи">
          <Plus size={44} />
        </button>
      </section>

      <OpenPositionsPanel
        exchanges={exchanges}
        positions={openPositions}
        snapshots={positionSnapshots}
        expandedSymbols={expandedSymbols}
        onCloseTrade={onCloseTrade}
        onExitOrder={onExitOrder}
        onDeleteTrade={onDeleteTrade}
        onPositionSnapshot={onPositionSnapshot}
        onToggleSymbol={onToggleSymbol}
      />
    </>
  );
}

function DealsPage({ closedPositions }: { closedPositions: ClosedPosition[] }) {
  const groups = Object.values(
    closedPositions.reduce<Record<string, ClosedPosition[]>>((accumulator, position) => {
      accumulator[position.groupId] = [...(accumulator[position.groupId] ?? []), position];
      return accumulator;
    }, {})
  ).sort((left, right) => {
    const leftClosedAt = Math.max(...left.map((position) => new Date(position.closedAt).getTime()));
    const rightClosedAt = Math.max(...right.map((position) => new Date(position.closedAt).getTime()));
    return rightClosedAt - leftClosedAt;
  });

  return (
    <section className="deals-page panel">
      <div className="open-positions-head">
        <span>Сделки</span>
      </div>

      {groups.length === 0 ? (
        <div className="open-positions-empty">Сделок нет</div>
      ) : (
        <div className="deal-groups">
          {groups.map((positions) => {
            const firstPosition = positions[0];
            const totalPnl = positions.reduce((sum, position) => sum + position.realizedPnlUsdt, 0);
            const totalNotional = positions.reduce((sum, position) => sum + position.notionalUsdt, 0);
            const closedAt = positions.reduce((latest, position) => (new Date(position.closedAt) > new Date(latest) ? position.closedAt : latest), firstPosition.closedAt);
            const exchanges = Array.from(
              new Map(positions.map((position) => [position.exchangeSlug, { slug: position.exchangeSlug, name: position.exchangeName }])).values()
            );
            return (
              <article className="deal-group" key={firstPosition.groupId}>
                <div className="deal-group-head">
                  <div className="deal-symbol">
                    <strong>{firstPosition.symbol}</strong>
                    <span>{formatDateTime(closedAt)}</span>
                  </div>
                  <div className="deal-exchanges">
                    {exchanges.map((exchange) => (
                      <ExchangeIcon exchange={exchange} className="compact" key={exchange.slug} />
                    ))}
                  </div>
                  <div className="deal-meta">
                    <span>{positions.length} поз.</span>
                    <strong>{formatMoney(totalNotional)}</strong>
                  </div>
                  <div className={totalPnl >= 0 ? "deal-pnl positive-text" : "deal-pnl negative-text"}>{formatSigned(totalPnl)}</div>
                </div>

                <div className="deal-legs">
                  {positions.map((position) => (
                    <div className="deal-leg" key={position.id}>
                      <div className="deal-leg-exchange">
                        <ExchangeIcon exchange={{ slug: position.exchangeSlug, name: position.exchangeName }} className="compact" />
                        <strong>{position.exchangeName}</strong>
                      </div>
                      <div>
                        <span>Направление</span>
                        <strong className={position.side === "long" ? "positive-text" : "negative-text"}>{position.side.toUpperCase()}</strong>
                      </div>
                      <div>
                        <span>ТВХ</span>
                        <strong>{formatPrice(position.entryPrice)}</strong>
                      </div>
                      <div>
                        <span>Выход</span>
                        <strong>{formatPrice(position.exitPrice)}</strong>
                      </div>
                      <div>
                        <span>Сайз</span>
                        <strong>{compactFormatter.format(position.sizeValue)} {position.sizeUnit}</strong>
                      </div>
                      <div>
                        <span>Маржа</span>
                        <strong>{formatMoney(position.marginUsdt)} / {position.leverage}x</strong>
                      </div>
                      <div>
                        <span>Режим</span>
                        <strong>{position.marginMode === "isolated" ? "Isolated" : "Cross"}</strong>
                      </div>
                      <div>
                        <span>PnL</span>
                        <strong className={position.realizedPnlUsdt >= 0 ? "positive-text" : "negative-text"}>{formatSigned(position.realizedPnlUsdt)}</strong>
                      </div>
                    </div>
                  ))}
                </div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}

function ClosedDealsPage({
  closedPositions,
  onDeleteDeal,
  onUpdateComment
}: {
  closedPositions: ClosedPosition[];
  onDeleteDeal: (groupId: string) => void;
  onUpdateComment: (groupId: string, comment: string) => void;
}) {
  const [expandedDeals, setExpandedDeals] = useState<Record<string, boolean>>({});
  const groups = Object.values(
    closedPositions.reduce<Record<string, ClosedPosition[]>>((accumulator, position) => {
      accumulator[position.groupId] = [...(accumulator[position.groupId] ?? []), position];
      return accumulator;
    }, {})
  ).sort((left, right) => {
    const leftClosedAt = Math.max(...left.map((position) => new Date(position.closedAt).getTime()));
    const rightClosedAt = Math.max(...right.map((position) => new Date(position.closedAt).getTime()));
    return rightClosedAt - leftClosedAt;
  });

  return (
    <section className="deals-page panel">
      <div className="open-positions-head">
        <span>Сделки</span>
      </div>

      {groups.length === 0 ? (
        <div className="open-positions-empty">Сделок нет</div>
      ) : (
        <div className="deal-groups">
          {groups.map((positions) => {
            const firstPosition = positions[0];
            const groupId = firstPosition.groupId;
            const isExpanded = Boolean(expandedDeals[groupId]);
            const totalPnl = positions.reduce((sum, position) => sum + position.realizedPnlUsdt, 0);
            const totalNotional = positions.reduce((sum, position) => sum + position.notionalUsdt, 0);
            const closedAt = positions.reduce((latest, position) => (new Date(position.closedAt) > new Date(latest) ? position.closedAt : latest), firstPosition.closedAt);
            const exchanges = Array.from(
              new Map(positions.map((position) => [position.exchangeSlug, { slug: position.exchangeSlug, name: position.exchangeName }])).values()
            );

            return (
              <article className={isExpanded ? "deal-group is-open" : "deal-group"} key={groupId}>
                <div className="deal-group-head">
                  <button
                    className="deal-row-toggle"
                    type="button"
                    onClick={() => setExpandedDeals((current) => ({ ...current, [groupId]: !current[groupId] }))}
                  >
                    <ChevronDown className={isExpanded ? "group-chevron is-open" : "group-chevron"} size={17} />
                    <div className="deal-symbol">
                      <strong>{firstPosition.symbol}</strong>
                      <span>{formatDateTime(closedAt)}</span>
                    </div>
                  </button>

                  <label className="deal-comment-field">
                    <span>Комментарий</span>
                    <input
                      maxLength={80}
                      placeholder="Заметка"
                      value={firstPosition.comment}
                      onChange={(event) => onUpdateComment(groupId, event.target.value)}
                    />
                  </label>

                  <div className="deal-exchanges">
                    {exchanges.map((exchange) => (
                      <ExchangeIcon exchange={exchange} className="compact" key={exchange.slug} />
                    ))}
                  </div>
                  <div className="deal-meta">
                    <span>{positions.length} поз.</span>
                    <strong>{formatMoney(totalNotional)}</strong>
                  </div>
                  <div className={totalPnl >= 0 ? "deal-pnl positive-text" : "deal-pnl negative-text"}>{formatSigned(totalPnl)}</div>
                  <button className="deal-delete-button" type="button" onClick={() => onDeleteDeal(groupId)} aria-label="Удалить сделку">
                    <Trash2 size={15} />
                  </button>
                </div>

                {isExpanded ? (
                  <div className="deal-legs">
                    {positions.map((position) => (
                      <div className="deal-leg" key={position.id}>
                        <div className="deal-leg-exchange">
                          <ExchangeIcon exchange={{ slug: position.exchangeSlug, name: position.exchangeName }} className="compact" />
                          <strong>{position.exchangeName}</strong>
                        </div>
                        <div>
                          <span>Направление</span>
                          <strong className={position.side === "long" ? "positive-text" : "negative-text"}>{position.side.toUpperCase()}</strong>
                        </div>
                        <div>
                          <span>ТВХ</span>
                          <strong>{formatPrice(position.entryPrice)}</strong>
                        </div>
                        <div>
                          <span>Выход</span>
                          <strong>{formatPrice(position.exitPrice)}</strong>
                        </div>
                        <div>
                          <span>Сайз</span>
                          <strong>{compactFormatter.format(position.sizeValue)} {position.sizeUnit}</strong>
                        </div>
                        <div>
                          <span>Маржа</span>
                          <strong>{formatMoney(position.marginUsdt)} / {position.leverage}x</strong>
                        </div>
                        <div>
                          <span>Режим</span>
                          <strong>{position.marginMode === "isolated" ? "Isolated" : "Cross"}</strong>
                        </div>
                        <div>
                          <span>PnL</span>
                          <strong className={position.realizedPnlUsdt >= 0 ? "positive-text" : "negative-text"}>{formatSigned(position.realizedPnlUsdt)}</strong>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : null}
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}

function SituationsPage({
  error,
  isLoading,
  isSaving,
  situations,
  onDelete,
  onEdit,
  onOpenCreate,
  onOpenSettings,
  onRefresh,
}: {
  error: string | null;
  isLoading: boolean;
  isSaving: boolean;
  situations: Situation[];
  onDelete: (situation: Situation) => void;
  onEdit: (situation: Situation) => void;
  onOpenCreate: () => void;
  onOpenSettings: () => void;
  onRefresh: () => void;
}) {
  const [searchDraft, setSearchDraft] = useState("");
  const [appliedSearch, setAppliedSearch] = useState("");
  const filteredSituations = useMemo(() => {
    const query = appliedSearch.trim().toLowerCase();
    if (!query) {
      return situations;
    }

    return situations.filter((situation) =>
      [situation.date, situation.token, situation.description, situation.posts]
        .join(" ")
        .toLowerCase()
        .includes(query)
    );
  }, [appliedSearch, situations]);
  const emptyText = isLoading ? "Загрузка ситуаций" : appliedSearch ? "Совпадений нет" : "Ситуаций нет";

  function applySearch() {
    setAppliedSearch(searchDraft);
  }

  function clearSearch() {
    setSearchDraft("");
    setAppliedSearch("");
  }

  return (
    <section className="situations-page panel">
      <div className="panel-heading situations-heading">
        <div>
          <p>Google Sheets</p>
          <h2>Ситуации</h2>
        </div>
        <div className="situations-heading-actions">
          <div className="situation-search-compact">
          <input
              aria-label="Поиск ситуаций"
              placeholder="Поиск"
            value={searchDraft}
            onChange={(event) => setSearchDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                applySearch();
              }
            }}
          />
            {appliedSearch ? (
              <button type="button" onClick={clearSearch} aria-label="Очистить поиск">
                <X size={15} />
              </button>
            ) : null}
            <button type="button" onClick={applySearch} aria-label="Искать">
              <Search size={16} />
            </button>
          </div>
          <button className="ghost-action compact-action icon-only-action" type="button" onClick={onRefresh} disabled={isLoading || isSaving} aria-label="Обновить">
            <RotateCcw size={16} />
          </button>
          <button className="ghost-action compact-action icon-only-action" type="button" onClick={onOpenSettings} disabled={isSaving} aria-label="Настройки ситуаций">
            <Settings2 size={16} />
          </button>
        </div>
      </div>

      {error ? <div className="error-banner situations-error">{error}</div> : null}

      <button className="primary-action situation-add-wide-button" type="button" onClick={onOpenCreate}>
        <Plus size={20} />
        <span>Добавить ситуацию</span>
      </button>

      <div className="situations-list-wrap">
        {filteredSituations.length === 0 ? (
          <div className="open-positions-empty">{emptyText}</div>
        ) : (
          <div className="situations-list">
            {filteredSituations.map((situation) => (
              <article className="situation-row" key={situation.rowNumber}>
                <div className="situation-row-main">
                  <span>{situation.date}</span>
                  <strong>{situation.token}</strong>
                </div>
                <div className="situation-row-text">
                  <span>Описание</span>
                  <p>{situation.description}</p>
                </div>
                <div className="situation-row-text">
                  <span>Посты</span>
                  <p>{situation.posts || "—"}</p>
                </div>
                <button className="situation-edit-button" type="button" onClick={() => onEdit(situation)} disabled={isSaving} aria-label="Редактировать ситуацию">
                  <SquarePen size={16} />
                </button>
                <button className="situation-delete-button" type="button" onClick={() => onDelete(situation)} disabled={isSaving} aria-label="Удалить ситуацию">
                  <Trash2 size={16} />
                </button>
              </article>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

function SituationModal({
  draft,
  isSaving,
  mode,
  onChange,
  onClose,
  onSave
}: {
  draft: SituationDraft;
  isSaving: boolean;
  mode: "create" | "edit";
  onChange: (draft: SituationDraft) => void;
  onClose: () => void;
  onSave: () => void;
}) {
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="trade-confirm-modal situation-modal" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}>
        <button className="modal-close-button" type="button" onClick={onClose} aria-label="Закрыть">
          <X size={18} />
        </button>

        <p className="modal-kicker">Google Sheets</p>
        <h2>{mode === "edit" ? "Редактировать" : "Добавить"}</h2>

        <div className="situation-modal-grid">
          <label className="field">
            <span>Дата</span>
            <input
              type="date"
              value={draft.date}
              onChange={(event) => onChange({ ...draft, date: event.target.value })}
            />
          </label>
          <label className="field">
            <span>Токен</span>
            <input
              value={draft.token}
              onChange={(event) => onChange({ ...draft, token: event.target.value.toUpperCase() })}
            />
          </label>
          <label className="field situation-modal-wide">
            <span>Описание</span>
            <textarea
              value={draft.description}
              onChange={(event) => onChange({ ...draft, description: event.target.value })}
            />
          </label>
          <label className="field situation-modal-wide">
            <span>Посты</span>
            <textarea
              value={draft.posts}
              onChange={(event) => onChange({ ...draft, posts: event.target.value })}
            />
          </label>
        </div>

        <div className="modal-actions situation-modal-actions">
          <button className="ghost-action" type="button" onClick={onClose} disabled={isSaving}>
            <X size={16} />
            <span>Отмена</span>
          </button>
          <button className="primary-action" type="button" onClick={onSave} disabled={isSaving}>
            <Save size={16} />
            <span>{isSaving ? "Сохранение" : "Сохранить"}</span>
          </button>
        </div>
      </section>
    </div>
  );
}

function SituationDeleteModal({
  isSaving,
  situation,
  onClose,
  onConfirm
}: {
  isSaving: boolean;
  situation: Situation;
  onClose: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="trade-confirm-modal situation-delete-modal" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}>
        <button className="modal-close-button" type="button" onClick={onClose} disabled={isSaving} aria-label="Закрыть">
          <X size={18} />
        </button>

        <p className="modal-kicker">Google Sheets</p>
        <h2>Удалить?</h2>
        <div className="delete-confirm-body">
          <span>Ситуация</span>
          <strong>{situation.token}</strong>
          <p>{situation.description}</p>
        </div>

        <div className="modal-actions situation-modal-actions">
          <button className="ghost-action" type="button" onClick={onClose} disabled={isSaving}>
            <X size={16} />
            <span>Отмена</span>
          </button>
          <button className="primary-action danger-action" type="button" onClick={onConfirm} disabled={isSaving}>
            <Trash2 size={16} />
            <span>{isSaving ? "Удаление" : "Удалить"}</span>
          </button>
        </div>
      </section>
    </div>
  );
}

type TradeTicketCardProps = {
  exchanges: Exchange[];
  openPositions: OpenPosition[];
  ticket: TradeTicket;
  onRemove: (ticketId: number) => void;
  onUpdate: (ticketId: number, patch: Partial<TradeTicket>) => void;
  onOpenTrade: (ticket: TradeTicket, snapshot?: MarketSnapshot | null) => void;
};

type ExchangeSelectProps = {
  exchanges: Exchange[];
  selectedExchange: Exchange | undefined;
  selectedExchangeId: number | "";
  onSelect: (exchangeId: number) => void;
};

function ExchangeSelect({ exchanges, selectedExchange, selectedExchangeId, onSelect }: ExchangeSelectProps) {
  const [isOpen, setIsOpen] = useState(false);
  const selectRef = useRef<HTMLDivElement | null>(null);

  function handleBlur(event: FocusEvent<HTMLDivElement>) {
    const nextTarget = event.relatedTarget;
    if (nextTarget instanceof Node && selectRef.current?.contains(nextTarget)) {
      return;
    }
    setIsOpen(false);
  }

  return (
    <div className="field exchange-select-field">
      <span>Биржа</span>
      <div className="exchange-select" ref={selectRef} onBlur={handleBlur}>
        <button
          className="exchange-select-button"
          type="button"
          aria-haspopup="listbox"
          aria-expanded={isOpen}
          onClick={() => setIsOpen((current) => !current)}
        >
          {selectedExchange ? <ExchangeIcon exchange={selectedExchange} className="compact" /> : null}
          <strong className="exchange-name-with-warning">
            <span>{selectedExchange?.name ?? "Выберите биржу"}</span>
            <ExchangeNetworkWarning exchange={selectedExchange} />
          </strong>
          <ChevronDown size={16} />
        </button>

        {isOpen ? (
          <div className="exchange-select-menu" role="listbox" tabIndex={-1}>
            {exchanges.map((exchange) => (
              <button
                className={exchange.id === selectedExchangeId ? "exchange-select-option is-selected" : "exchange-select-option"}
                key={exchange.id}
                type="button"
                role="option"
                aria-selected={exchange.id === selectedExchangeId}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => {
                  onSelect(exchange.id);
                  setIsOpen(false);
                }}
              >
                <ExchangeIcon exchange={exchange} className="compact" />
                <span className="exchange-name-with-warning">
                  <span>{exchange.name}</span>
                  <ExchangeNetworkWarning exchange={exchange} />
                </span>
              </button>
            ))}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function TradeTicketCard({ exchanges, openPositions, ticket, onRemove, onUpdate, onOpenTrade }: TradeTicketCardProps) {
  const exchange = exchanges.find((item) => item.id === ticket.exchangeId);
  const selectedToken = TOKENS.find((token) => token.symbol === ticket.symbol);
  const normalizedTokenQuery = ticket.tokenQuery.trim().toUpperCase();
  const [marketSymbols, setMarketSymbols] = useState<MarketSymbol[]>([]);
  const [marketSnapshot, setMarketSnapshot] = useState<MarketSnapshot | null>(null);
  const [marketStatus, setMarketStatus] = useState<string | null>(null);
  const liveEnabled = isLiveExchange(exchange);
  const suggestions = getTokenSuggestions(ticket.tokenQuery, liveEnabled ? marketSymbols : []);
  const showTokenSuggestions = Boolean(normalizedTokenQuery) && ticket.symbol !== normalizedTokenQuery && suggestions.length > 0;
  const activeMarketSymbol = ticket.symbol || (normalizedTokenQuery.length >= 2 ? normalizedTokenQuery : "");
  const price = numberFromInput(ticket.price);
  const notional = getTicketNotional(ticket);
  const margin = getTicketMargin(ticket);
  const liquidationPrice = getTicketLiquidationPrice(ticket, exchange, openPositions);
  const tokenAmount = Number.isFinite(price) && price > 0 ? notional / price : 0;
  const freeMargin = exchange ? getFreeMargin(exchange, openPositions) : 0;
  const overBalance = exchange ? margin > freeMargin : false;
  const latestPrice = marketSnapshot?.lastPrice ?? selectedToken?.lastPrice ?? 0;

  useEffect(() => {
    setMarketSymbols([]);
    if (!exchange || !liveEnabled || !normalizedTokenQuery) {
      return;
    }

    const timeoutId = window.setTimeout(() => {
      void getMarketSymbols(exchange.slug, normalizedTokenQuery, 20)
        .then((payload) => setMarketSymbols(payload.symbols))
        .catch(() => setMarketSymbols([]));
    }, 160);

    return () => window.clearTimeout(timeoutId);
  }, [exchange?.slug, liveEnabled, normalizedTokenQuery]);

  useEffect(() => {
    setMarketSnapshot(null);
    setMarketStatus(null);
    if (!exchange || !liveEnabled || !activeMarketSymbol) {
      return;
    }

    const exchangeSlug = exchange.slug;
    const marketSymbol = activeMarketSymbol;
    let isClosed = false;
    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;

    function connect() {
      setMarketStatus("Подключение");
      socket = new WebSocket(getMarketWsUrl(exchangeSlug, marketSymbol));

      socket.onmessage = (event) => {
        if (isClosed) {
          return;
        }
        const payload = JSON.parse(event.data) as MarketSnapshot;
        if (payload.type === "error" || payload.type === "status") {
          setMarketStatus(payload.type === "error" ? `error:${payload.message ?? "Ошибка live данных"}` : (payload.message ?? "Ожидание данных"));
          return;
        }
        if (!Array.isArray(payload.bids) || !Array.isArray(payload.asks)) {
          return;
        }
        setMarketStatus(null);
        setMarketSnapshot(payload);
      };

      socket.onerror = () => {
        setMarketStatus("error:Ошибка подключения");
        socket?.close();
      };

      socket.onclose = () => {
        if (isClosed) {
          return;
        }
        reconnectTimer = window.setTimeout(connect, 1500);
      };
    }

    connect();

    return () => {
      isClosed = true;
      if (reconnectTimer) {
        window.clearTimeout(reconnectTimer);
      }
      socket?.close();
    };
  }, [exchange?.slug, liveEnabled, activeMarketSymbol]);

  function setToken(token: TokenMock) {
    onUpdate(ticket.id, {
      tokenQuery: token.symbol,
      symbol: token.symbol,
      price: token.lastPrice > 0 ? String(token.lastPrice) : ticket.price,
      message: null
    });
  }

  function setPercent(percent: number) {
    if (!exchange) {
      return;
    }
    const currentPrice = numberFromInput(ticket.price);
    const marginByPercent = getFreeMargin(exchange, openPositions) * (percent / 100);
    const notionalByPercent = marginByPercent * getTicketLeverage(ticket);
    onUpdate(ticket.id, {
      percent,
      size: ticket.sizeUnit === "USDT" || !Number.isFinite(currentPrice) || currentPrice <= 0
        ? String(roundInput(notionalByPercent))
        : String(roundInput(notionalByPercent / currentPrice)),
      message: null
    });
  }

  function switchSizeUnit(nextUnit: TradeSizeUnit) {
    const currentPrice = numberFromInput(ticket.price);
    const currentNotional = getTicketNotional(ticket);
    if (!Number.isFinite(currentPrice) || currentPrice <= 0 || currentNotional <= 0) {
      onUpdate(ticket.id, { sizeUnit: nextUnit });
      return;
    }
    onUpdate(ticket.id, {
      sizeUnit: nextUnit,
      size: nextUnit === "USDT" ? String(roundInput(currentNotional)) : String(roundInput(currentNotional / currentPrice))
    });
  }

  return (
    <article className="trade-card">
      <div className="trade-card-head">
        <span>Окно биржи</span>
        <button className="ticket-close-button" type="button" onClick={() => onRemove(ticket.id)} aria-label="Закрыть окно биржи">
          <X size={16} />
        </button>
      </div>

      <div className="trade-form-row">
        <ExchangeSelect
          exchanges={exchanges}
          selectedExchange={exchange}
          selectedExchangeId={ticket.exchangeId}
          onSelect={(exchangeId) => onUpdate(ticket.id, { exchangeId, message: null })}
        />

        <div className="balance-readout">
          <span>Доступно</span>
          <strong>{formatMoney(exchange ? freeMargin : 0)}</strong>
        </div>
      </div>

      <label className="field token-field">
        <span>Тикер</span>
        <input
          value={ticket.tokenQuery}
          onChange={(event) => onUpdate(ticket.id, { tokenQuery: event.target.value.toUpperCase(), symbol: "", message: null })}
          placeholder="BTC"
        />
        {showTokenSuggestions ? (
          <div className="token-suggestions">
            {suggestions.map((token) => (
              <button key={token.symbol} type="button" onClick={() => setToken(token)}>
                <strong>{token.symbol}</strong>
                <span>{token.name}</span>
              </button>
            ))}
          </div>
        ) : null}
      </label>

      <div className="side-switch">
        <button
          className={ticket.side === "long" ? "side-button long is-selected" : "side-button long"}
          type="button"
          onClick={() => onUpdate(ticket.id, { side: "long" })}
        >
          <ArrowUp size={16} />
          <span>Long</span>
        </button>
        <button
          className={ticket.side === "short" ? "side-button short is-selected" : "side-button short"}
          type="button"
          onClick={() => onUpdate(ticket.id, { side: "short" })}
        >
          <ArrowDown size={16} />
          <span>Short</span>
        </button>
      </div>

      <div className="margin-mode-switch">
        <button
          className={ticket.marginMode === "isolated" ? "is-selected" : ""}
          type="button"
          onClick={() => onUpdate(ticket.id, { marginMode: "isolated", message: null })}
        >
          Isolated
        </button>
        <button
          className={ticket.marginMode === "cross" ? "is-selected" : ""}
          type="button"
          onClick={() => onUpdate(ticket.id, { marginMode: "cross", message: null })}
        >
          Cross
        </button>
      </div>

      <div className="trade-form-row">
        <label className="field">
          <span>Цена</span>
          <input
            inputMode="decimal"
            value={ticket.price}
            onChange={(event) => onUpdate(ticket.id, { price: event.target.value, message: null })}
          />
        </label>
        <button
          className="last-price-button"
          type="button"
          onClick={() => latestPrice > 0 && onUpdate(ticket.id, { price: String(latestPrice), message: null })}
        >
          Последняя
        </button>
      </div>

      <div className="trade-form-row">
        <label className="field">
          <span>Сайз</span>
          <input
            inputMode="decimal"
            value={ticket.size}
            onChange={(event) => onUpdate(ticket.id, { size: event.target.value, percent: 0, message: null })}
            placeholder={ticket.sizeUnit === "USDT" ? "1000" : "0.25"}
          />
        </label>
        <div className="unit-switch">
          <button className={ticket.sizeUnit === "USDT" ? "is-selected" : ""} type="button" onClick={() => switchSizeUnit("USDT")}>
            USDT
          </button>
          <button className={ticket.sizeUnit === "TOKEN" ? "is-selected" : ""} type="button" onClick={() => switchSizeUnit("TOKEN")}>
            Token
          </button>
        </div>
        <label className="field leverage-field">
          <span>Плечо</span>
          <input
            inputMode="decimal"
            value={ticket.leverage}
            onChange={(event) => onUpdate(ticket.id, { leverage: event.target.value, percent: 0, message: null })}
          />
        </label>
      </div>

      <div className="size-slider">
        <input
          max="100"
          min="0"
          step="1"
          type="range"
          value={ticket.percent}
          onChange={(event) => setPercent(Number(event.target.value))}
        />
        <div className="slider-marks">
          {[25, 50, 75, 100].map((mark) => (
            <button key={mark} type="button" onClick={() => setPercent(mark)}>
              {mark}%
            </button>
          ))}
        </div>
      </div>

      <div className="trade-math">
        <div>
          <span>Notional</span>
          <strong>{formatMoney(notional)}</strong>
        </div>
        <div>
          <span>Маржа</span>
          <strong className={overBalance ? "negative-text" : ""}>{formatMoney(margin)}</strong>
        </div>
        <div>
          <span>Кол-во</span>
          <strong>{compactFormatter.format(tokenAmount)} {ticket.symbol || "TOKEN"}</strong>
        </div>
        <div>
          <span>Est. liq</span>
          <strong>{liquidationPrice ? formatPrice(liquidationPrice) : "—"}</strong>
        </div>
      </div>

      <OrderBook
        symbol={ticket.symbol || ticket.tokenQuery || "—"}
        snapshot={marketSnapshot}
        status={marketStatus}
      />

      {ticket.message ? <div className={ticket.message === "Сделка открыта" ? "ticket-message success" : "ticket-message"}>{ticket.message}</div> : null}

      <button className="open-trade-button" type="button" disabled={overBalance} onClick={() => onOpenTrade(ticket, marketSnapshot)}>
        Открыть сделку
      </button>
    </article>
  );
}

type OpenPositionsPanelProps = {
  exchanges: Exchange[];
  positions: OpenPosition[];
  snapshots: Record<number, MarketSnapshot>;
  expandedSymbols: Record<string, boolean>;
  onCloseTrade: (position: OpenPosition) => void;
  onExitOrder: (position: OpenPosition, order?: TradeExitOrder | null) => void;
  onDeleteTrade: (position: OpenPosition) => void;
  onToggleSymbol: (symbol: string) => void;
  onPositionSnapshot: (positionId: number, snapshot: MarketSnapshot) => void;
};

function OpenPositionsPanel({
  exchanges,
  positions,
  snapshots,
  expandedSymbols,
  onCloseTrade,
  onExitOrder,
  onDeleteTrade,
  onToggleSymbol,
  onPositionSnapshot
}: OpenPositionsPanelProps) {
  const [marketStatuses, setMarketStatuses] = useState<Record<number, string | null>>({});
  const [fundingInfos, setFundingInfos] = useState<Record<number, FundingInfo>>({});
  const groupedPositions = positions.reduce<Record<string, OpenPosition[]>>((groups, position) => {
    groups[position.symbol] = [...(groups[position.symbol] ?? []), position];
    return groups;
  }, {});
  const symbols = Object.keys(groupedPositions).sort();
  const handlePositionStatus = useCallback((positionId: number, status: string | null) => {
    setMarketStatuses((current) => ({ ...current, [positionId]: status }));
  }, []);
  const handleFundingInfo = useCallback((positionId: number, fundingInfo: FundingInfo) => {
    setFundingInfos((current) => ({ ...current, [positionId]: fundingInfo }));
  }, []);

  useEffect(() => {
    const activeIds = new Set(positions.map((position) => position.id));
    setMarketStatuses((current) => {
      const next = Object.fromEntries(Object.entries(current).filter(([positionId]) => activeIds.has(Number(positionId))));
      return next as Record<number, string | null>;
    });
    setFundingInfos((current) => {
      const next = Object.fromEntries(Object.entries(current).filter(([positionId]) => activeIds.has(Number(positionId))));
      return next as Record<number, FundingInfo>;
    });
  }, [positions]);

  return (
    <section className="open-positions-panel">
      {positions.map((position) => (
        <PositionMarketFeed
          key={position.id}
          position={position}
          onSnapshot={onPositionSnapshot}
          onStatus={handlePositionStatus}
        />
      ))}
      {positions.map((position) => (
        <PositionFundingFeed
          fundingInfo={fundingInfos[position.id] ?? null}
          key={`funding-${position.id}`}
          onFundingInfo={handleFundingInfo}
          position={position}
        />
      ))}

      <div className="open-positions-head">
        <span>Открытые позиции</span>
      </div>

      {symbols.length === 0 ? (
        <div className="open-positions-empty">Сделок нет</div>
      ) : (
        <div className="position-groups">
          {symbols.map((symbol) => {
            const symbolPositions = groupedPositions[symbol];
            const totalPnl = symbolPositions.reduce(
              (sum, position) => sum + position.realizedPnlUsdt + getPositionPnl(position, snapshots[position.id] ?? null).pnlUsdt,
              0
            );
            const isExpanded = Boolean(expandedSymbols[symbol]);
            return (
              <article className="position-group" key={symbol}>
                <button className="position-group-row" type="button" onClick={() => onToggleSymbol(symbol)}>
                  <div className="position-symbol-cell">
                    <ChevronDown className={isExpanded ? "group-chevron is-open" : "group-chevron"} size={17} />
                    <strong>{symbol}</strong>
                  </div>
                  <div className="position-exchange-stack">
                    {symbolPositions.map((position) => (
                      <ExchangeIcon
                        exchange={{ slug: position.exchangeSlug, name: position.exchangeName }}
                        className="compact"
                        key={position.id}
                      />
                    ))}
                  </div>
                  <div className={totalPnl >= 0 ? "position-total-pnl positive-text" : "position-total-pnl negative-text"}>
                    {formatSigned(totalPnl)}
                  </div>
                </button>

                {isExpanded ? (
                  <div className="open-position-cards">
                    {symbolPositions.map((position) => (
                      <OpenPositionCard
                        exchange={exchanges.find((exchange) => exchange.id === position.exchangeId)}
                        key={position.id}
                        positions={positions}
                        position={position}
                        fundingInfo={fundingInfos[position.id] ?? null}
                        snapshot={snapshots[position.id] ?? null}
                        status={marketStatuses[position.id] ?? null}
                        onCloseTrade={onCloseTrade}
                        onExitOrder={onExitOrder}
                        onDeleteTrade={onDeleteTrade}
                      />
                    ))}
                  </div>
                ) : null}
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}

type OpenPositionCardProps = {
  exchange: Exchange | undefined;
  positions: OpenPosition[];
  position: OpenPosition;
  fundingInfo: FundingInfo | null;
  snapshot: MarketSnapshot | null;
  status: string | null;
  onCloseTrade: (position: OpenPosition) => void;
  onExitOrder: (position: OpenPosition, order?: TradeExitOrder | null) => void;
  onDeleteTrade: (position: OpenPosition) => void;
};

function PositionMarketFeed({
  position,
  onSnapshot,
  onStatus
}: {
  position: OpenPosition;
  onSnapshot: (positionId: number, snapshot: MarketSnapshot) => void;
  onStatus: (positionId: number, status: string | null) => void;
}) {
  useEffect(() => {
    onStatus(position.id, "Подключение");
    let isClosed = false;
    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;

    function connect() {
      socket = new WebSocket(getMarketWsUrl(position.exchangeSlug, position.symbol));
      socket.onmessage = (event) => {
        if (isClosed) {
          return;
        }
        const payload = JSON.parse(event.data) as MarketSnapshot;
        if (payload.type === "error" || payload.type === "status") {
          onStatus(position.id, payload.type === "error" ? `error:${payload.message ?? "Ошибка live данных"}` : (payload.message ?? "Ожидание данных"));
          return;
        }
        if (!Array.isArray(payload.bids) || !Array.isArray(payload.asks)) {
          return;
        }
        onStatus(position.id, null);
        onSnapshot(position.id, payload);
      };
      socket.onerror = () => {
        onStatus(position.id, "error:Ошибка подключения");
        socket?.close();
      };
      socket.onclose = () => {
        if (!isClosed) {
          reconnectTimer = window.setTimeout(connect, 1500);
        }
      };
    }

    connect();

    return () => {
      isClosed = true;
      if (reconnectTimer) {
        window.clearTimeout(reconnectTimer);
      }
      socket?.close();
    };
  }, [position.exchangeSlug, position.id, position.symbol, onSnapshot, onStatus]);

  return null;
}

function PositionFundingFeed({
  fundingInfo,
  onFundingInfo,
  position
}: {
  fundingInfo: FundingInfo | null;
  onFundingInfo: (positionId: number, fundingInfo: FundingInfo) => void;
  position: OpenPosition;
}) {
  const fundingRef = useRef<FundingInfo | null>(fundingInfo);

  useEffect(() => {
    fundingRef.current = fundingInfo;
  }, [fundingInfo]);

  useEffect(() => {
    let isClosed = false;
    let pollTimer: number | null = null;

    function fetchFunding() {
      void getMarketFunding(position.exchangeSlug, position.symbol)
        .then((payload) => {
          if (isClosed) {
            return;
          }
          fundingRef.current = payload;
          onFundingInfo(position.id, payload);
        })
        .catch(() => undefined);
    }

    fetchFunding();
    pollTimer = window.setInterval(fetchFunding, 30_000);

    return () => {
      isClosed = true;
      if (pollTimer) {
        window.clearInterval(pollTimer);
      }
    };
  }, [onFundingInfo, position.exchangeSlug, position.id, position.symbol]);

  return null;
}

function OpenPositionCard({ exchange, positions, position, fundingInfo, snapshot, status, onCloseTrade, onExitOrder, onDeleteTrade }: OpenPositionCardProps) {
  const [now, setNow] = useState(() => Date.now());
  const pnl = getPositionPnl(position, snapshot);
  const quantity = getPositionQuantity(position);
  const liquidationPrice = getPositionLiquidationPrice(position, positions, exchange);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <article className="trade-card open-position-card">
      <div className="trade-card-head">
        <span>Открытая сделка</span>
        <div className="fixed-exchange-lock">
          <ExchangeIcon exchange={{ slug: position.exchangeSlug, name: position.exchangeName }} className="compact" />
          <strong>{position.exchangeName}</strong>
          <button className="position-delete-button" type="button" onClick={() => onDeleteTrade(position)} aria-label="Удалить сделку">
            <Trash2 size={15} />
          </button>
        </div>
      </div>

      <div className="position-fixed-grid">
        <div>
          <span>Тикер</span>
          <strong>{position.symbol}</strong>
        </div>
        <div>
          <span>Направление</span>
          <strong className={position.side === "long" ? "positive-text" : "negative-text"}>{position.side.toUpperCase()}</strong>
        </div>
        <div>
          <span>ТВХ</span>
          <strong>{formatPrice(position.entryPrice)}</strong>
        </div>
        <div>
          <span>Сайз</span>
          <strong>{compactFormatter.format(position.sizeValue)} {position.sizeUnit}</strong>
        </div>
        <div>
          <span>Кол-во</span>
          <strong>{compactFormatter.format(quantity)} {position.symbol}</strong>
        </div>
        <div>
          <span>Маржа</span>
          <strong>{formatMoney(position.marginUsdt)} / {position.leverage}x</strong>
        </div>
        <div>
          <span>Режим</span>
          <strong>{position.marginMode === "isolated" ? "Isolated" : "Cross"}</strong>
        </div>
        <div>
          <span>Закрытие маркетом</span>
          <strong>{formatPrice(pnl.closePrice)}</strong>
        </div>
        <div>
          <span>Est. liq</span>
          <strong>{liquidationPrice ? formatPrice(liquidationPrice) : "—"}</strong>
        </div>
        <div className="funding-cell">
          <span>Funding</span>
          <strong className={!fundingInfo ? "" : fundingInfo.fundingRate >= 0 ? "positive-text" : "negative-text"}>
            {fundingInfo ? formatFundingRate(fundingInfo.fundingRate) : "—"}
            <small>{formatFundingCountdown(fundingInfo?.nextFundingTime ?? null, now)}</small>
          </strong>
        </div>
      </div>

      <div className="position-pnl-box">
        <span>PnL</span>
        <strong className={pnl.pnlUsdt >= 0 ? "positive-text" : "negative-text"}>
          {formatSigned(pnl.pnlUsdt)} <small>({formatPercent(pnl.pnlPercent)})</small>
          {position.realizedPnlUsdt !== 0 ? <small className="realized-pnl">{formatSigned(position.realizedPnlUsdt)}</small> : null}
        </strong>
      </div>

      <OrderBook symbol={position.symbol} snapshot={snapshot} status={status} />

      <button className="open-trade-button close-trade-button" type="button" onClick={() => onCloseTrade(position)}>
        Закрыть сделку
      </button>
      {SHOW_EXIT_ORDER_CONTROLS ? (
        <button className="open-trade-button exit-order-button" type="button" onClick={() => onExitOrder(position, null)}>
          Добавить TP/SL
        </button>
      ) : null}
      {SHOW_EXIT_ORDER_CONTROLS && position.exitOrders.length > 0 ? (
        <div className="exit-order-list">
          {position.exitOrders.map((order) => (
            <button className="exit-order-pill" type="button" key={order.id} onClick={() => onExitOrder(position, order)}>
              <span>{order.orderType === "take_profit" ? "TP" : "SL"}</span>
              <strong>{formatPrice(order.triggerPrice)}</strong>
              <small>{formatPercent(order.pnlPercent)} · {compactFormatter.format(order.sizePercent)}%</small>
            </button>
          ))}
        </div>
      ) : null}
    </article>
  );
}

function getTokenSuggestions(query: string, marketSymbols: MarketSymbol[] = []): TokenMock[] {
  const normalized = query.trim().toUpperCase();
  if (!normalized) {
    return [];
  }

  if (marketSymbols.length > 0) {
    return marketSymbols.map((symbol) => ({
      symbol: symbol.symbol,
      wireSymbol: symbol.wireSymbol,
      name: symbol.displayName,
      lastPrice: 0
    }));
  }

  return TOKENS.filter((token) => token.symbol.includes(normalized) || token.name.toUpperCase().includes(normalized)).slice(0, 6);
}

function roundInput(value: number): number {
  return Math.round(value * 1000000) / 1000000;
}

function getTicketLeverage(ticket: TradeTicket): number {
  const leverage = numberFromInput(ticket.leverage);
  if (!Number.isFinite(leverage) || leverage <= 0) {
    return 1;
  }
  return Math.min(Math.max(leverage, 1), 125);
}

function getTicketNotional(ticket: TradeTicket): number {
  const price = numberFromInput(ticket.price);
  const size = numberFromInput(ticket.size);
  if (!Number.isFinite(price) || !Number.isFinite(size) || price <= 0 || size <= 0) {
    return 0;
  }
  return ticket.sizeUnit === "USDT" ? size : size * price;
}

function getTicketMargin(ticket: TradeTicket): number {
  const notional = getTicketNotional(ticket);
  const leverage = getTicketLeverage(ticket);
  return leverage > 0 ? notional / leverage : notional;
}

function OrderBook({ symbol, snapshot, status }: { symbol: string; snapshot: MarketSnapshot | null; status: string | null }) {
  const asks = fixedBookLevels(snapshot?.asks.length ? snapshot.asks.slice(0, ORDERBOOK_VISIBLE_LEVELS).reverse() : []);
  const bids = fixedBookLevels(snapshot?.bids.length ? snapshot.bids.slice(0, ORDERBOOK_VISIBLE_LEVELS) : []);
  const visibleAsks = asks.filter((row) => row !== null);
  const visibleBids = bids.filter((row) => row !== null);
  const bestAsk = visibleAsks[visibleAsks.length - 1]?.price ?? null;
  const bestBid = visibleBids[0]?.price ?? null;
  const spread = bestAsk && bestBid ? Math.max(bestAsk - bestBid, 0) : 0;
  const midPrice = bestAsk && bestBid ? (bestAsk + bestBid) / 2 : 0;
  const spreadPercent = midPrice > 0 ? (spread / midPrice) * 100 : 0;
  const centerPrice = snapshot?.lastPrice || midPrice;
  const quoteAsset = snapshot?.quoteAsset || "USDT";

  return (
    <div className="orderbook">
      <div className="orderbook-head">
        <span>Стакан</span>
        <div className="orderbook-symbol">
          <MarketStatusDot hasSnapshot={Boolean(snapshot)} status={status} />
          <strong>{symbol}/{quoteAsset}</strong>
        </div>
      </div>
      <div className="book-columns" aria-hidden="true">
        <span>Price ({quoteAsset})</span>
        <span>Size ({quoteAsset})</span>
      </div>
      <div className="book-rows asks">
        {asks.map((row, index) => (
          <div className={row ? "book-row" : "book-row is-empty"} key={`ask-${row?.price ?? index}`}>
            <span>{row ? formatPrice(row.price) : ""}</span>
            <strong>{row ? sizeUsdtFormatter.format(row.price * row.size) : ""}</strong>
          </div>
        ))}
      </div>
      <div className="book-mid">
        <strong className="book-price">{centerPrice > 0 ? formatPrice(centerPrice) : "—"}</strong>
        {centerPrice > 0 ? <span className="book-spread">{spreadPercent.toFixed(3)}%</span> : null}
      </div>
      <div className="book-rows bids">
        {bids.map((row, index) => (
          <div className={row ? "book-row" : "book-row is-empty"} key={`bid-${row?.price ?? index}`}>
            <span>{row ? formatPrice(row.price) : ""}</span>
            <strong>{row ? sizeUsdtFormatter.format(row.price * row.size) : ""}</strong>
          </div>
        ))}
      </div>
    </div>
  );
}

function MarketStatusDot({ hasSnapshot, status }: { hasSnapshot: boolean; status: string | null }) {
  const normalizedStatus = status?.toLowerCase() ?? "";
  const tone = normalizedStatus.startsWith("error:") ? "error" : hasSnapshot && !status ? "live" : status ? "pending" : "idle";
  const label =
    tone === "live"
      ? "Live данные получены"
      : tone === "pending"
        ? status ?? "Подключение"
        : tone === "error"
          ? status?.replace(/^error:/, "") ?? "Ошибка live данных"
          : "Live данные не запущены";

  return <span className={`market-status-dot ${tone}`} title={label} aria-label={label} />;
}

function fixedBookLevels<T>(rows: T[]): Array<T | null> {
  return Array.from({ length: ORDERBOOK_VISIBLE_LEVELS }, (_, index) => rows[index] ?? null);
}

type SummaryTileProps = {
  icon: ReactNode;
  label: string;
  value: string;
  tone: "neutral" | "positive" | "negative";
};

function SummaryTile({ icon, label, value, tone }: SummaryTileProps) {
  return (
    <article className={`summary-tile tone-${tone}`}>
      <div className="summary-title">
        <div className="summary-icon">{icon}</div>
        <span>{label}</span>
      </div>
      <strong>{value}</strong>
    </article>
  );
}

type ExchangePanelProps = {
  exchanges: Exchange[];
  isLoading: boolean;
  onEdit: (exchange: Exchange) => void;
};

function ExchangePanel({ exchanges, isLoading, onEdit }: ExchangePanelProps) {
  return (
    <section className="panel exchange-panel">
      <div className="panel-heading">
        <div>
          <p>Счета</p>
          <h2>Балансы на биржах</h2>
        </div>
      </div>

      <div className="exchange-list">
        {isLoading ? (
          <div className="empty-state">Загрузка балансов</div>
        ) : (
          exchanges.map((exchange) => (
            <article className="exchange-row" key={exchange.id}>
              <div className="exchange-identity">
                <ExchangeIcon exchange={exchange} />
                <div>
                  <strong className="exchange-name-with-warning">
                    <span>{exchange.name}</span>
                    <ExchangeNetworkWarning exchange={exchange} />
                  </strong>
                </div>
              </div>
              <div className="metric-cell">
                <span>Баланс</span>
                <strong>{formatMoney(exchange.balanceUsdt)}</strong>
              </div>
              <div className={`metric-cell pnl ${exchange.pnlTotalUsdt >= 0 ? "positive" : "negative"}`}>
                <span>PnL</span>
                <strong>{formatSigned(exchange.pnlTotalUsdt)}</strong>
              </div>
              <button className="edit-button" type="button" onClick={() => onEdit(exchange)}>
                <SquarePen size={16} />
                <span>Баланс</span>
              </button>
            </article>
          ))
        )}
      </div>
    </section>
  );
}

function CalendarPanel({ calendar }: { calendar: ProfitCalendarResponse | null }) {
  const leadingOffset = calendar ? new Date(calendar.year, calendar.month - 1, 1).getDay() : 0;
  const mondayOffset = leadingOffset === 0 ? 6 : leadingOffset - 1;
  const placeholders = Array.from({ length: mondayOffset }, (_, index) => index);

  return (
    <section className="panel calendar-panel">
      <div className="panel-heading">
        <div>
          <p>Календарь</p>
          <h2>{getMonthName(calendar)}</h2>
        </div>
        <div className={`calendar-total ${(calendar?.totalPnlUsdt ?? 0) >= 0 ? "positive" : "negative"}`}>
          {formatSigned(calendar?.totalPnlUsdt ?? 0)}
        </div>
      </div>

      <div className="week-row" aria-hidden="true">
        {["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"].map((day) => (
          <span key={day}>{day}</span>
        ))}
      </div>
      <div className="calendar-grid">
        {placeholders.map((item) => (
          <span className="calendar-placeholder" key={`placeholder-${item}`} />
        ))}
        {(calendar?.days ?? []).map((day) => (
          <CalendarCell day={day} key={day.date} />
        ))}
      </div>
    </section>
  );
}

function CalendarCell({ day }: { day: CalendarDay }) {
  const tone = day.pnlUsdt > 0 ? "positive" : day.pnlUsdt < 0 ? "negative" : "neutral";
  return (
    <div className={`calendar-cell ${tone}`} title={`${day.date}: ${formatSigned(day.pnlUsdt)}`}>
      <span>{day.day}</span>
      <strong>{day.pnlUsdt === 0 ? "$0" : compactFormatter.format(day.pnlUsdt)}</strong>
    </div>
  );
}

function getOrderedCalendarRange(range: CalendarRange): { start: string; end: string } | null {
  if (!range.start) {
    return null;
  }
  const end = range.end ?? range.start;
  return range.start <= end ? { start: range.start, end } : { start: end, end: range.start };
}

function getCalendarRangePnl(calendar: ProfitCalendarResponse | null, range: CalendarRange): number | null {
  const orderedRange = getOrderedCalendarRange(range);
  if (!calendar || !orderedRange) {
    return null;
  }
  return calendar.days
    .filter((day) => day.date >= orderedRange.start && day.date <= orderedRange.end)
    .reduce((sum, day) => sum + day.pnlUsdt, 0);
}

function RangeCalendarPanel({
  calendar,
  isRangeSelectionEnabled,
  range,
  onSelectDate,
  onShiftMonth,
  onToggleRange
}: {
  calendar: ProfitCalendarResponse | null;
  isRangeSelectionEnabled: boolean;
  range: CalendarRange;
  onSelectDate: (date: string) => void;
  onShiftMonth: (delta: number) => void;
  onToggleRange: () => void;
}) {
  const leadingOffset = calendar ? new Date(calendar.year, calendar.month - 1, 1).getDay() : 0;
  const mondayOffset = leadingOffset === 0 ? 6 : leadingOffset - 1;
  const placeholders = Array.from({ length: mondayOffset }, (_, index) => index);
  const orderedRange = isRangeSelectionEnabled ? getOrderedCalendarRange(range) : null;
  const rangePnl = isRangeSelectionEnabled ? getCalendarRangePnl(calendar, range) : null;

  return (
    <section className="panel calendar-panel">
      <div className="panel-heading">
        <div>
          <p>Календарь</p>
          <div className="calendar-title-row">
            <button className="calendar-nav-button" type="button" onClick={() => onShiftMonth(-1)} aria-label="Предыдущий месяц">
              <ArrowUp size={15} />
            </button>
            <h2>{getMonthName(calendar)}</h2>
            <button className="calendar-nav-button" type="button" onClick={() => onShiftMonth(1)} aria-label="Следующий месяц">
              <ArrowDown size={15} />
            </button>
          </div>
          {rangePnl !== null && orderedRange ? (
            <div className={`calendar-range-total ${rangePnl >= 0 ? "positive-text" : "negative-text"}`}>
              <span>{orderedRange.start === orderedRange.end ? orderedRange.start : `${orderedRange.start} - ${orderedRange.end}`}</span>
              <strong>{formatSigned(rangePnl)}</strong>
            </div>
          ) : null}
        </div>
        <div className="calendar-tools">
          <button
            className={isRangeSelectionEnabled ? "calendar-mode-button is-active" : "calendar-mode-button"}
            type="button"
            onClick={onToggleRange}
          >
            <CalendarDays size={15} />
            <span>Период</span>
          </button>
          <div className={`calendar-total ${(calendar?.totalPnlUsdt ?? 0) >= 0 ? "positive" : "negative"}`}>
            {formatSigned(calendar?.totalPnlUsdt ?? 0)}
          </div>
        </div>
      </div>

      <div className="week-row" aria-hidden="true">
        {["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"].map((day) => (
          <span key={day}>{day}</span>
        ))}
      </div>
      <div className="calendar-grid">
        {placeholders.map((item) => (
          <span className="calendar-placeholder" key={`placeholder-${item}`} />
        ))}
        {(calendar?.days ?? []).map((day) => {
          const isSelected = Boolean(isRangeSelectionEnabled && orderedRange && day.date >= orderedRange.start && day.date <= orderedRange.end);
          const isRangeEnd = Boolean(isRangeSelectionEnabled && orderedRange && (day.date === orderedRange.start || day.date === orderedRange.end));
          return (
            <RangeCalendarCell
              day={day}
              isRangeEnd={isRangeEnd}
              isRangeSelectionEnabled={isRangeSelectionEnabled}
              isSelected={isSelected}
              key={day.date}
              onSelect={onSelectDate}
            />
          );
        })}
      </div>
    </section>
  );
}

function RangeCalendarCell({
  day,
  isRangeEnd,
  isRangeSelectionEnabled,
  isSelected,
  onSelect
}: {
  day: CalendarDay;
  isRangeEnd: boolean;
  isRangeSelectionEnabled: boolean;
  isSelected: boolean;
  onSelect: (date: string) => void;
}) {
  const tone = day.pnlUsdt > 0 ? "positive" : day.pnlUsdt < 0 ? "negative" : "neutral";
  return (
    <button
      className={`calendar-cell ${tone} ${isSelected ? "is-selected" : ""} ${isRangeEnd ? "is-range-end" : ""}`}
      disabled={!isRangeSelectionEnabled}
      title={`${day.date}: ${formatSigned(day.pnlUsdt)}`}
      type="button"
      onClick={() => onSelect(day.date)}
    >
      <span>{day.day}</span>
      <strong>{day.pnlUsdt === 0 ? "$0" : compactFormatter.format(day.pnlUsdt)}</strong>
    </button>
  );
}

function OpenTradeConfirmModal({
  draft,
  isSaving,
  onClose,
  onConfirm
}: {
  draft: OpenTradeDraft;
  isSaving: boolean;
  onClose: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="trade-confirm-modal" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}>
        <button className="modal-close" type="button" onClick={onClose} aria-label="Закрыть окно">
          <X size={18} />
        </button>
        <div className="modal-kicker">
          <TrendingUp size={17} />
          <span>{draft.exchange.name}</span>
        </div>
        <h2>Открыть сделку?</h2>
        <BinanceTradeSummary
          amount={`${formatMoney(draft.notionalUsdt)} (${compactFormatter.format(draft.sizeValue)} ${draft.ticket.sizeUnit})`}
          entryPrice={draft.entryPrice}
          leverage={draft.leverage}
          liquidationPrice={draft.liquidationPrice}
          marginMode={draft.marginMode}
          markPrice={draft.markPrice}
          marginUsdt={draft.marginUsdt}
          quoteAsset={draft.quoteAsset}
          side={draft.ticket.side}
          symbol={draft.symbol}
        />
        <div className="modal-actions">
          <button className="ghost-action" type="button" onClick={onClose} disabled={isSaving}>
            <X size={16} />
            <span>Отмена</span>
          </button>
          <button className="primary-action" type="button" onClick={onConfirm} disabled={isSaving}>
            <TrendingUp size={16} />
            <span>{isSaving ? "Открытие" : "Открыть"}</span>
          </button>
        </div>
      </section>
    </div>
  );
}

function CloseTradeConfirmModal({
  draft,
  exchange,
  positions,
  snapshot,
  onChange,
  onClose,
  onConfirm
}: {
  draft: CloseTradeDraft;
  exchange: Exchange | undefined;
  positions: OpenPosition[];
  snapshot: MarketSnapshot | null;
  onChange: (draft: CloseTradeDraft) => void;
  onClose: () => void;
  onConfirm: () => void;
}) {
  const priceSelection = getClosePriceSelection(draft, draft.position, snapshot);
  const pnl = getPositionPnlAtPrice(draft.position, priceSelection.exitPrice);
  const closePercent = getClosePercent(draft);
  const positionNotional = getPositionCloseNotional(draft.position);
  const liquidationPrice = getPositionLiquidationPrice(draft.position, positions, exchange);
  const proportionalPnl = priceSelection.isCustomPriceValid ? pnl.pnlUsdt * (closePercent / 100) : 0;
  const proportionalPnlPercent = priceSelection.isCustomPriceValid ? pnl.pnlPercent : 0;
  const isConfirmDisabled = closePercent <= 0 || !priceSelection.isCustomPriceValid;

  function setPercent(percent: number) {
    const clampedPercent = Math.min(Math.max(percent, 0), 100);
    onChange({
      ...draft,
      percentValue: String(roundInput(clampedPercent)),
      usdtValue: String(roundInput(positionNotional * (clampedPercent / 100)))
    });
  }

  function setUsdt(value: string) {
    const usdtValue = numberFromInput(value);
    const percentValue = Number.isFinite(usdtValue) && positionNotional > 0 ? (usdtValue / positionNotional) * 100 : 0;
    onChange({
      ...draft,
      usdtValue: value,
      percentValue: String(roundInput(Math.min(Math.max(percentValue, 0), 100)))
    });
  }

  function setPriceMode(priceMode: CloseTradeDraft["priceMode"]) {
    onChange({
      ...draft,
      priceMode,
      customExitPrice: draft.customExitPrice || String(roundInput(priceSelection.marketPrice))
    });
  }

  function setCustomExitPrice(customExitPrice: string) {
    onChange({
      ...draft,
      customExitPrice
    });
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="trade-confirm-modal" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}>
        <button className="modal-close" type="button" onClick={onClose} aria-label="Закрыть окно">
          <X size={18} />
        </button>
        <div className="modal-kicker">
          <TrendingUp size={17} />
          <span>{draft.position.exchangeName}</span>
        </div>
        <h2>Закрыть сделку?</h2>

        <BinanceTradeSummary
          amount={`${formatMoney(positionNotional)} (${compactFormatter.format(draft.position.sizeValue)} ${draft.position.sizeUnit})`}
          entryPrice={draft.position.entryPrice}
          leverage={draft.position.leverage}
          liquidationPrice={liquidationPrice}
          marginMode={draft.position.marginMode}
          markPrice={getSnapshotMarkPrice(snapshot, priceSelection.marketPrice)}
          marketPrice={priceSelection.marketPrice}
          marginUsdt={draft.position.marginUsdt}
          quoteAsset={snapshot?.quoteAsset ?? "USDT"}
          side={draft.position.side}
          symbol={draft.position.symbol}
        />

        <div className="close-price-controls">
          <button
            className={draft.priceMode === "market" ? "close-price-mode-button is-selected" : "close-price-mode-button"}
            type="button"
            onClick={() => setPriceMode("market")}
          >
            Маркет
          </button>
          <button
            className={draft.priceMode === "custom" ? "close-price-mode-button is-selected" : "close-price-mode-button"}
            type="button"
            onClick={() => setPriceMode("custom")}
          >
            Своя цена
          </button>
          <label className={draft.priceMode === "market" ? "close-price-input is-disabled" : "close-price-input"}>
            <span>Маркет: {formatPrice(priceSelection.marketPrice)}</span>
            <div>
              <strong>Выход:</strong>
              <input
                disabled={draft.priceMode === "market"}
                inputMode="decimal"
                value={draft.priceMode === "market" ? String(roundInput(priceSelection.marketPrice)) : draft.customExitPrice}
                onChange={(event) => setCustomExitPrice(event.target.value)}
              />
            </div>
          </label>
        </div>

        <div className="close-size-controls">
          <label className="field">
            <span>Закрыть, %</span>
            <input
              inputMode="decimal"
              value={draft.percentValue}
              onChange={(event) => setPercent(numberFromInput(event.target.value))}
            />
          </label>
          <label className="field">
            <span>Закрыть, USDT</span>
            <input
              inputMode="decimal"
              value={draft.usdtValue}
              onChange={(event) => setUsdt(event.target.value)}
            />
          </label>
          <div className="size-slider">
            <input max="100" min="0" step="1" type="range" value={closePercent} onChange={(event) => setPercent(Number(event.target.value))} />
            <div className="slider-marks">
              {[25, 50, 75, 100].map((mark) => (
                <button key={mark} type="button" onClick={() => setPercent(mark)}>
                  {mark}%
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="position-pnl-box modal-pnl">
          <span>Текущий PnL</span>
          <strong className={proportionalPnl >= 0 ? "positive-text" : "negative-text"}>
            {formatSigned(proportionalPnl)} <small>({formatPercent(proportionalPnlPercent)})</small>
          </strong>
        </div>

        <div className="modal-actions">
          <button className="ghost-action" type="button" onClick={onClose}>
            <X size={16} />
            <span>Отмена</span>
          </button>
          <button className="primary-action danger-action" type="button" onClick={onConfirm} disabled={isConfirmDisabled}>
            <ArrowDown size={16} />
            <span>Закрыть</span>
          </button>
        </div>
      </section>
    </div>
  );
}

function ExitOrderModal({
  draft,
  isSaving,
  snapshot,
  onChange,
  onClose,
  onDeleteOrder,
  onSave
}: {
  draft: ExitOrderDraft;
  isSaving: boolean;
  snapshot: MarketSnapshot | null;
  onChange: (draft: ExitOrderDraft) => void;
  onClose: () => void;
  onDeleteOrder?: (order: TradeExitOrder) => void;
  onSave: () => void;
}) {
  const [metricMenu, setMetricMenu] = useState<TradeExitOrder["orderType"] | null>(null);
  const positionNotional = getPositionCloseNotional(draft.position);
  const marketPrice = getPositionClosePrice(draft.position, snapshot);
  const activeLeg = draft.legs[draft.orderType];
  const triggerPrice = numberFromInput(activeLeg.triggerPrice);
  const pnlPercent = numberFromInput(activeLeg.pnlPercent);
  const sizePercent = numberFromInput(activeLeg.sizePercent);
  const sizeUsdt = numberFromInput(activeLeg.sizeUsdt);
  const priceIsValid = Number.isFinite(triggerPrice) && triggerPrice > 0;
  const sizeIsValid = Number.isFinite(sizePercent) && sizePercent > 0 && sizePercent <= 100 && Number.isFinite(sizeUsdt) && sizeUsdt > 0;
  const isSaveDisabled = isSaving || !priceIsValid || !Number.isFinite(pnlPercent) || !sizeIsValid;
  const triggerPnl = priceIsValid ? getPositionPnlAtPrice(draft.position, triggerPrice) : null;
  const proportionalPnl = triggerPnl && Number.isFinite(sizePercent) ? triggerPnl.pnlUsdt * (sizePercent / 100) : null;
  const existingOrders = draft.position.exitOrders ?? [];
  const sideLabel = draft.position.side === "long" ? "Лонг" : "Шорт";

  function withActiveLeg(nextDraft: ExitOrderDraft, orderType: TradeExitOrder["orderType"]): ExitOrderDraft {
    const leg = nextDraft.legs[orderType];
    return {
      ...nextDraft,
      orderType,
      triggerMode: leg.triggerMode,
      triggerPrice: leg.triggerPrice,
      pnlPercent: leg.pnlPercent,
      sizeMode: leg.sizeMode,
      sizePercent: leg.sizePercent,
      sizeUsdt: leg.sizeUsdt,
      positionScope: numberFromInput(leg.sizePercent) >= 100 ? "full" : "partial"
    };
  }

  function updateLeg(orderType: TradeExitOrder["orderType"], patch: Partial<ExitOrderLegDraft>) {
    const nextDraft = {
      ...draft,
      legs: {
        ...draft.legs,
        [orderType]: {
          ...draft.legs[orderType],
          ...patch
        }
      }
    };
    onChange(withActiveLeg(nextDraft, orderType));
  }

  function setOrderType(orderType: TradeExitOrder["orderType"]) {
    onChange(withActiveLeg(draft, orderType));
  }

  function setTriggerPrice(value: string, orderType: TradeExitOrder["orderType"]) {
    const nextPrice = numberFromInput(value);
    const nextPnl = Number.isFinite(nextPrice) && nextPrice > 0 ? getPositionPnlAtPrice(draft.position, nextPrice).pnlPercent : pnlPercent;
    const nextPnlUsdt = Number.isFinite(nextPnl) ? draft.position.marginUsdt * (nextPnl / 100) : numberFromInput(draft.legs[orderType].pnlUsdt);
    updateLeg(orderType, {
      triggerMode: "price",
      triggerPrice: value,
      pnlPercent: Number.isFinite(nextPnl) ? String(roundInput(nextPnl)) : draft.legs[orderType].pnlPercent,
      pnlUsdt: Number.isFinite(nextPnlUsdt) ? String(roundInput(nextPnlUsdt)) : draft.legs[orderType].pnlUsdt
    });
  }

  function setMetricMode(orderType: TradeExitOrder["orderType"], metricMode: ExitOrderMetricMode) {
    setMetricMenu(null);
    updateLeg(orderType, {
      metricMode,
      triggerMode: metricMode === "roe" ? "pnl_percent" : "price"
    });
  }

  function setPnlMetric(value: string, orderType: TradeExitOrder["orderType"]) {
    const leg = draft.legs[orderType];
    const rawValue = numberFromInput(value);
    const nextPnlPercent = leg.metricMode === "roe" ? rawValue : draft.position.marginUsdt > 0 ? (rawValue / draft.position.marginUsdt) * 100 : 0;
    const nextPnlUsdt = leg.metricMode === "roe" ? draft.position.marginUsdt * (rawValue / 100) : rawValue;
    const nextPrice = getPositionPriceForPnlPercent(draft.position, nextPnlPercent);
    updateLeg(orderType, {
      triggerMode: leg.metricMode === "roe" ? "pnl_percent" : "price",
      pnlPercent: Number.isFinite(nextPnlPercent) ? String(roundInput(nextPnlPercent)) : leg.pnlPercent,
      pnlUsdt: Number.isFinite(nextPnlUsdt) ? String(roundInput(nextPnlUsdt)) : leg.pnlUsdt,
      triggerPrice: Number.isFinite(nextPrice) && nextPrice > 0 ? String(roundInput(nextPrice)) : draft.triggerPrice
    });
  }

  function setSizePercent(value: string, orderType: TradeExitOrder["orderType"]) {
    const nextPercent = numberFromInput(value);
    const nextUsdt = Number.isFinite(nextPercent) ? positionNotional * (Math.min(Math.max(nextPercent, 0), 100) / 100) : sizeUsdt;
    updateLeg(orderType, {
      sizeMode: "percent",
      sizePercent: value,
      sizeUsdt: Number.isFinite(nextUsdt) ? String(roundInput(nextUsdt)) : draft.sizeUsdt
    });
  }

  function setSizeUsdt(value: string, orderType: TradeExitOrder["orderType"]) {
    const nextUsdt = numberFromInput(value);
    const nextPercent = Number.isFinite(nextUsdt) && positionNotional > 0 ? (nextUsdt / positionNotional) * 100 : sizePercent;
    updateLeg(orderType, {
      sizeMode: "usdt",
      sizeUsdt: value,
      sizePercent: Number.isFinite(nextPercent) ? String(roundInput(Math.min(Math.max(nextPercent, 0), 100))) : draft.sizePercent
    });
  }

  function setPositionScope(positionScope: ExitOrderDraft["positionScope"], orderType?: TradeExitOrder["orderType"]) {
    const targetTypes = orderType ? [orderType] : (["take_profit", "stop_loss"] as TradeExitOrder["orderType"][]);
    const nextLegs = { ...draft.legs };
    for (const type of targetTypes) {
      const legPercent = numberFromInput(nextLegs[type].sizePercent);
      const nextPercent = positionScope === "full" ? 100 : Math.min(Number.isFinite(legPercent) && legPercent > 0 && legPercent < 100 ? legPercent : 50, 99);
      nextLegs[type] = {
        ...nextLegs[type],
        sizeMode: "percent",
        sizePercent: String(roundInput(nextPercent)),
        sizeUsdt: String(roundInput(positionNotional * (nextPercent / 100)))
      };
    }
    const activeType = orderType ?? draft.orderType;
    onChange(withActiveLeg({
      ...draft,
      sizeMode: "percent",
      positionScope,
      legs: nextLegs
    }, activeType));
  }

  function loadOrder(order: TradeExitOrder) {
    const nextLeg: ExitOrderLegDraft = {
      triggerMode: order.triggerMode,
      metricMode: order.triggerMode === "pnl_percent" ? "roe" : "pnl",
      triggerPrice: String(roundInput(order.triggerPrice)),
      pnlPercent: String(roundInput(order.pnlPercent)),
      pnlUsdt: String(roundInput(draft.position.marginUsdt * (order.pnlPercent / 100))),
      sizeMode: order.sizeMode,
      sizePercent: String(roundInput(order.sizePercent)),
      sizeUsdt: String(roundInput(order.sizeUsdt))
    };
    onChange(withActiveLeg({
      ...draft,
      order,
      legs: {
        ...draft.legs,
        [order.orderType]: nextLeg
      }
    }, order.orderType));
  }

  function orderTimeLabel(order: TradeExitOrder) {
    return formatDateTime(order.createdAt ?? order.updatedAt).replace(", ", " ");
  }

  function OrderBlock({ type }: { type: TradeExitOrder["orderType"] }) {
    const leg = draft.legs[type];
    const isActive = draft.orderType === type;
    const title = type === "take_profit" ? "Срабатывание рыночного TP" : "Срабатывание рыночного SL";
    const label = type === "take_profit" ? "TP" : "SL";
    const legTriggerPrice = numberFromInput(leg.triggerPrice);
    const legPnlPercent = numberFromInput(leg.pnlPercent);
    const legSizePercent = numberFromInput(leg.sizePercent);
    const legPnl = Number.isFinite(legTriggerPrice) && legTriggerPrice > 0 ? getPositionPnlAtPrice(draft.position, legTriggerPrice) : null;
    const legProportionalPnl = legPnl && Number.isFinite(legSizePercent) ? legPnl.pnlUsdt * (legSizePercent / 100) : null;

    return (
      <section className={isActive ? "tp-sl-order-block is-active" : "tp-sl-order-block"}>
        <div className="tp-sl-block-head">
          <button type="button" onClick={() => setOrderType(type)}>
            <span>{title}</span>
          </button>
        </div>

        <div className="tp-sl-input-row">
          <div className="tp-sl-field">
            <input
              inputMode="decimal"
              value={leg.triggerPrice}
              onChange={(event) => setTriggerPrice(event.target.value, type)}
              placeholder="Триггер..."
            />
            <span>USDT</span>
          </div>
          <div className="tp-sl-field">
            <input
              inputMode="decimal"
              value={leg.metricMode === "roe" ? leg.pnlPercent : leg.pnlUsdt}
              onChange={(event) => setPnlMetric(event.target.value, type)}
              placeholder={leg.metricMode === "roe" ? "%" : "USDT"}
            />
            <span>{leg.metricMode === "roe" ? "%" : "USDT"}</span>
            <div className="tp-sl-metric-menu">
              <button type="button" onClick={() => { setOrderType(type); setMetricMenu(metricMenu === type ? null : type); }}>
                {leg.metricMode === "roe" ? "ROE" : "PNL"}
                <ChevronDown size={14} />
              </button>
              {metricMenu === type ? (
                <div className="tp-sl-metric-options">
                  <button type="button" onClick={() => setMetricMode(type, "pnl")}>PNL</button>
                  <button type="button" onClick={() => setMetricMode(type, "roe")}>ROE</button>
                </div>
              ) : null}
            </div>
          </div>
        </div>

        <div className="tp-sl-amount">
          <div className="tp-sl-amount-head">
            <span>Кол-во</span>
          </div>
          <div className="tp-sl-wide-field">
            <input
              inputMode="decimal"
              value={leg.sizeUsdt}
              onChange={(event) => setSizeUsdt(event.target.value, type)}
            />
            <span>USDT</span>
            <button type="button" onClick={() => setPositionScope("full", type)}>Все</button>
          </div>
          <div className="size-slider tp-sl-size-slider">
            <input
              max="100"
              min="0"
              step="1"
              type="range"
              value={Number.isFinite(legSizePercent) ? Math.min(Math.max(legSizePercent, 0), 100) : 0}
              onInput={(event) => setSizePercent(event.currentTarget.value, type)}
              onChange={(event) => setSizePercent(event.currentTarget.value, type)}
            />
            <div className="slider-marks">
              {[25, 50, 75, 100].map((mark) => (
                <button key={mark} type="button" onClick={() => setSizePercent(String(mark), type)}>
                  {mark}%
                </button>
              ))}
            </div>
          </div>
        </div>

        {Number.isFinite(legTriggerPrice) && legTriggerPrice > 0 && legPnl ? (
          <p className="tp-sl-hint">
            Когда цена достигнет <strong>{formatPrice(legTriggerPrice)}</strong>, сработает ордер {label} по <strong>рыночной цене</strong>.
            Расчетный PNL составит{" "}
            <strong className={legPnl.pnlUsdt >= 0 ? "positive-text tp-sl-calculated-value" : "negative-text tp-sl-calculated-value"}>
              {legProportionalPnl === null ? "—" : formatSigned(legProportionalPnl)}
            </strong>
            , ROE <strong className={legPnl.pnlPercent >= 0 ? "positive-text tp-sl-calculated-value" : "negative-text tp-sl-calculated-value"}>{formatPercent(legPnl.pnlPercent)}</strong>.
          </p>
        ) : null}
      </section>
    );
  }

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="trade-confirm-modal exit-order-modal tp-sl-modal" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}>
        <button className="modal-close" type="button" onClick={onClose} aria-label="Закрыть окно">
          <X size={18} />
        </button>

        <div className="tp-sl-title">
          <h2>Настройки TP/SL</h2>
          <p>
            {draft.position.symbol} Бессрочный <strong className={draft.position.side === "long" ? "positive-text" : "negative-text"}>{sideLabel} {draft.position.leverage}X</strong>
          </p>
        </div>

        <div className="tp-sl-market-stats">
          <div>
            <span>Ср. цена входа</span>
            <strong>{formatPrice(draft.position.entryPrice)}</strong>
          </div>
          <div>
            <span>Последняя</span>
            <strong>{formatPrice(marketPrice)}</strong>
          </div>
          <div>
            <span>Ориент. цена ликв.</span>
            <strong className="warning-text">—</strong>
          </div>
        </div>

        <div className="tp-sl-tabs" role="tablist" aria-label="Размер позиции TP/SL">
          <button
            className={draft.positionScope === "full" ? "is-selected" : ""}
            type="button"
            onClick={() => setPositionScope("full")}
          >
            Вся позиция
          </button>
          <button
            className={draft.positionScope === "partial" ? "is-selected" : ""}
            type="button"
            onClick={() => setPositionScope("partial")}
          >
            Частичная позиция
          </button>
        </div>

        <div className="tp-sl-blocks">
          <OrderBlock type="take_profit" />
          <OrderBlock type="stop_loss" />
        </div>

        {existingOrders.length > 0 ? (
          <section className="tp-sl-existing">
            <div className="tp-sl-existing-head">
              <h3>Ордер TP/SL</h3>
            </div>
            <div className="tp-sl-order-table">
              {existingOrders.map((order) => (
                <div className="tp-sl-order-row" key={order.id}>
                  <div>
                    <small>{orderTimeLabel(order)}</small>
                    <span className={order.orderType === "take_profit" ? "positive-text" : "negative-text"}>
                      {order.orderType === "take_profit" ? "TP" : "SL"}: Последняя {order.orderType === "take_profit" ? ">=" : "<="}{formatPrice(order.triggerPrice)}
                    </span>
                  </div>
                  <span>{order.orderType === "take_profit" ? "TP" : "SL"}: Рыночная</span>
                  <strong>{formatPrice(order.sizeUsdt)}</strong>
                  <div className="tp-sl-table-actions">
                    <button type="button" onClick={() => loadOrder(order)} aria-label="Изменить TP/SL">
                      <SquarePen size={16} />
                    </button>
                    <button type="button" onClick={() => onDeleteOrder?.(order)} disabled={isSaving} aria-label="Удалить TP/SL">
                      <Trash2 size={16} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </section>
        ) : null}

        <div className="modal-actions tp-sl-actions">
          <button className="ghost-action" type="button" onClick={onClose} disabled={isSaving}>
            Отменить
          </button>
          <button className="primary-action" type="button" onClick={onSave} disabled={isSaveDisabled}>
            {isSaving ? "Сохранение" : "Подтвердить"}
          </button>
        </div>
      </section>
    </div>
  );
}

function BinanceTradeSummary({
  amount,
  entryPrice,
  leverage,
  liquidationPrice,
  marginMode,
  markPrice,
  marketPrice,
  marginUsdt,
  quoteAsset = "USDT",
  side,
  symbol
}: {
  amount: string;
  entryPrice: number;
  leverage: number;
  liquidationPrice: number | null;
  marginMode: "isolated" | "cross";
  markPrice: number;
  marketPrice?: number;
  marginUsdt: number;
  quoteAsset?: string;
  side: TradeSide;
  symbol: string;
}) {
  const sideLabel = side === "long" ? "Buy/Long" : "Sell/Short";
  const priceGap = markPrice > 0 ? ((entryPrice - markPrice) / markPrice) * 100 : 0;

  return (
    <div className="binance-summary">
      <div className="binance-summary-head">
        <div>
          <strong>{symbol}{quoteAsset}</strong>
          <span>Perp</span>
        </div>
        <small className={side === "long" ? "positive-text" : "negative-text"}>{sideLabel}</small>
      </div>
      <div className="binance-summary-rows">
        {marketPrice ? <SummaryRow label="Market" value={`${formatPrice(marketPrice)} ${quoteAsset}`} /> : null}
        <SummaryRow label="Price" value={`${formatPrice(entryPrice)} ${quoteAsset}`} />
        <SummaryRow label="Amount" value={amount} />
        <SummaryRow label="Mark Price" value={`${formatPrice(markPrice)} ${quoteAsset}`} />
        <SummaryRow label="Est. Liq.Price" value={liquidationPrice ? `${formatPrice(liquidationPrice)} ${quoteAsset}` : "—"} />
        <SummaryRow label="Price Gap" value={`${formatPercent(priceGap)} (${formatPrice(entryPrice - markPrice)})`} />
        <SummaryRow label="Margin" value={`${formatMoney(marginUsdt)} · ${marginMode === "isolated" ? "Isolated" : "Cross"}`} />
        <SummaryRow label="Leverage" value={`${leverage}x`} />
      </div>
    </div>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="summary-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function TradeConfirmSummary({
  symbol,
  price,
  side,
  sizeValue,
  sizeUnit,
  marginUsdt,
  priceLabel = "ТВХ"
}: {
  symbol: string;
  price: number;
  side: TradeSide;
  sizeValue: number;
  sizeUnit: TradeSizeUnit;
  marginUsdt: number;
  priceLabel?: string;
}) {
  return (
    <div className="confirm-summary">
      <div>
        <span>Тикер</span>
        <strong>{symbol}</strong>
      </div>
      <div>
        <span>{priceLabel}</span>
        <strong>{formatPrice(price)}</strong>
      </div>
      <div>
        <span>Направление</span>
        <strong className={side === "long" ? "positive-text" : "negative-text"}>{side.toUpperCase()}</strong>
      </div>
      <div>
        <span>Сайз</span>
        <strong>{compactFormatter.format(sizeValue)} {sizeUnit}</strong>
      </div>
      <div>
        <span>Маржа</span>
        <strong>{formatMoney(marginUsdt)}</strong>
      </div>
    </div>
  );
}

type BalanceModalProps = {
  exchange: Exchange;
  balanceDraft: string;
  isSaving: boolean;
  onChange: (value: string) => void;
  onClose: () => void;
  onSave: () => void;
  onReset: () => void;
};

type DepositModalProps = {
  draft: DepositDraft;
  exchanges: Exchange[];
  isSaving: boolean;
  onChange: (draft: DepositDraft) => void;
  onClose: () => void;
  onSave: () => void;
};

function DepositModal({ draft, exchanges, isSaving, onChange, onClose, onSave }: DepositModalProps) {
  const fromExchange = exchanges.find((exchange) => exchange.id === draft.fromExchangeId);
  const toExchange = exchanges.find((exchange) => exchange.id === draft.toExchangeId);

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="balance-modal deposit-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="deposit-modal-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <button className="modal-close" type="button" onClick={onClose} aria-label="Закрыть окно">
          <X size={18} />
        </button>

        <div className="modal-kicker">
          <ArrowRightLeft size={17} />
          <span>Перевод</span>
        </div>

        <h2 id="deposit-modal-title">Депозит</h2>

        <div className="deposit-select-grid">
          <label className="field">
            <span>Откуда</span>
            <select
              value={draft.fromExchangeId}
              onChange={(event) =>
                onChange({
                  ...draft,
                  fromExchangeId: Number(event.target.value)
                })
              }
            >
              {exchanges.map((exchange) => (
                <option key={exchange.id} value={exchange.id}>
                  {exchange.name}
                </option>
              ))}
            </select>
            <small>{fromExchange ? `Доступно: ${formatMoney(fromExchange.balanceUsdt)}` : "Доступно: -"}</small>
          </label>

          <label className="field">
            <span>Куда</span>
            <select
              value={draft.toExchangeId}
              onChange={(event) =>
                onChange({
                  ...draft,
                  toExchangeId: Number(event.target.value)
                })
              }
            >
              {exchanges.map((exchange) => (
                <option key={exchange.id} value={exchange.id}>
                  {exchange.name}
                </option>
              ))}
            </select>
            <small>{toExchange ? `Сейчас: ${formatMoney(toExchange.balanceUsdt)}` : "Сейчас: -"}</small>
          </label>
        </div>

        <label className="balance-field">
          <span>USDT</span>
          <input
            autoFocus
            inputMode="decimal"
            value={draft.amount}
            onChange={(event) => onChange({ ...draft, amount: event.target.value })}
            placeholder="1000"
          />
        </label>

        <div className="modal-actions">
          <button className="ghost-action" type="button" onClick={onClose} disabled={isSaving}>
            <X size={16} />
            <span>Отмена</span>
          </button>
          <button className="primary-action" type="button" onClick={onSave} disabled={isSaving}>
            <Save size={16} />
            <span>{isSaving ? "Перевод" : "Сохранить"}</span>
          </button>
        </div>
      </section>
    </div>
  );
}

function SituationSettingsModal({
  checkResult,
  draft,
  isLoading,
  isSaving,
  settings,
  onChange,
  onClose,
  onSave,
  onTest
}: {
  checkResult: SituationSettingsTestResponse | null;
  draft: SituationSettingsDraft;
  isLoading: boolean;
  isSaving: boolean;
  settings: SituationSettings | null;
  onChange: (draft: SituationSettingsDraft) => void;
  onClose: () => void;
  onSave: () => void;
  onTest: () => void;
}) {
  const checks = checkResult?.checks ?? [
    { key: "credentials", label: "JSON файл", ok: Boolean(settings?.credentialsExists) },
    { key: "spreadsheet", label: "Google Sheet ID", ok: Boolean(settings?.spreadsheetId) },
    { key: "sheet", label: "Вкладка", ok: false },
    { key: "write", label: "Доступ Google Sheets", ok: false }
  ];

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="trade-confirm-modal situation-settings-modal" role="dialog" aria-modal="true" onMouseDown={(event) => event.stopPropagation()}>
        <button className="modal-close-button" type="button" onClick={onClose} disabled={isSaving || isLoading} aria-label="Закрыть">
          <X size={18} />
        </button>

        <p className="modal-kicker">Google Sheets</p>
        <h2>Настройки</h2>

        <div className="situation-settings-grid">
          <label className="field situation-settings-wide">
            <span>Google Sheet ID</span>
            <input
              value={draft.spreadsheetId}
              placeholder="ID таблицы из ссылки"
              onChange={(event) => onChange({ ...draft, spreadsheetId: event.target.value })}
            />
          </label>
          <label className="field">
            <span>Вкладка</span>
            <input
              value={draft.sheetName}
              placeholder="Situations"
              onChange={(event) => onChange({ ...draft, sheetName: event.target.value })}
            />
          </label>
          <label className="field situation-settings-wide">
            <span>Путь к JSON</span>
            <input
              value={draft.credentialsPath}
              placeholder="backend/google-service-account.json"
              onChange={(event) => onChange({ ...draft, credentialsPath: event.target.value })}
            />
          </label>
          <div className="settings-readonly-card">
            <span>Service account</span>
            <strong>{settings?.serviceAccountEmail || "JSON не прочитан"}</strong>
          </div>
          <div className="settings-readonly-card">
            <span>Resolved path</span>
            <strong>{settings?.resolvedCredentialsPath || "—"}</strong>
          </div>
        </div>

        <div className="settings-check-list">
          {checks.map((check) => (
            <div className={check.ok ? "settings-check is-ok" : "settings-check is-bad"} key={check.key}>
              <span>{check.label}</span>
              <strong>{check.ok ? "OK" : "—"}</strong>
            </div>
          ))}
        </div>

        {checkResult?.message ? <div className="error-banner settings-check-error">{checkResult.message}</div> : null}

        <div className="modal-actions situation-modal-actions">
          <button className="ghost-action" type="button" onClick={onTest} disabled={isLoading || isSaving}>
            <RotateCcw size={16} />
            <span>{isLoading ? "Проверка" : "Проверить"}</span>
          </button>
          <button className="primary-action" type="button" onClick={onSave} disabled={isLoading || isSaving}>
            <Save size={16} />
            <span>{isSaving ? "Сохранение" : "Сохранить"}</span>
          </button>
        </div>
      </section>
    </div>
  );
}

function BalanceModal({
  exchange,
  balanceDraft,
  isSaving,
  onChange,
  onClose,
  onSave,
  onReset
}: BalanceModalProps) {
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="balance-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="balance-modal-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <button className="modal-close" type="button" onClick={onClose} aria-label="Закрыть окно">
          <X size={18} />
        </button>

        <div className="modal-kicker">
          <Settings2 size={17} />
          <span>{exchange.name}</span>
        </div>

        <h2 id="balance-modal-title">Баланс</h2>

        <label className="balance-field">
          <span>USDT</span>
          <input
            autoFocus
            inputMode="decimal"
            value={balanceDraft}
            onChange={(event) => onChange(event.target.value)}
            placeholder="10000"
          />
        </label>

        <div className="modal-stats">
          <div>
            <span>PnL</span>
            <strong className={exchange.pnlTotalUsdt >= 0 ? "positive-text" : "negative-text"}>
              {formatSigned(exchange.pnlTotalUsdt)}
            </strong>
          </div>
          <div>
            <span>Старт</span>
            <strong>{formatMoney(exchange.startBalanceUsdt)}</strong>
          </div>
        </div>

        <div className="modal-actions">
          <button className="ghost-action" type="button" onClick={onReset} disabled={isSaving}>
            <RotateCcw size={16} />
            <span>Сбросить PnL</span>
          </button>
          <button className="primary-action" type="button" onClick={onSave} disabled={isSaving}>
            <Save size={16} />
            <span>{isSaving ? "Сохранение" : "Сохранить"}</span>
          </button>
        </div>
      </section>
    </div>
  );
}

export default App;
