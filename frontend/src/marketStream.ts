import { useEffect, useRef, useState } from "react";

import type { MarketInterval } from "./api/client";

export type { MarketInterval } from "./api/client";

export const MARKET_INTERVALS = [
  "1m",
  "5m",
  "15m",
  "1h",
  "4h",
  "1d",
] as const satisfies ReadonlyArray<MarketInterval>;

export const MARKET_STREAM_QUOTE_THROTTLE_MS = 250;
export const MARKET_STREAM_STALE_AFTER_MS = 5_000;
export const MARKET_STREAM_RECONNECT_BASE_MS = 500;
export const MARKET_STREAM_RECONNECT_MAX_MS = 8_000;

export type MarketEnvironmentKind = "DEMO" | "LIVE";

export function marketEnvironmentScopeKey(
  environmentKind: string,
  environmentId: string,
): string {
  return `${environmentKind}:${environmentId}`;
}

export function expectedMarketSourceForEnvironment(
  environmentKind: string,
): string | null {
  if (environmentKind === "DEMO") return "BINANCE_DEMO_PUBLIC";
  if (environmentKind === "LIVE") return "BINANCE_LIVE_PUBLIC";
  return null;
}

export function isMarketSourceForEnvironment(
  source: string | null | undefined,
  environmentKind: string,
): boolean {
  const expectedSource = expectedMarketSourceForEnvironment(environmentKind);
  return expectedSource !== null && source === expectedSource;
}

export type MarketStreamServerStatus = Readonly<{
  type: "status";
  state: "CONNECTING" | "LIVE" | "RECONNECTING" | "FAILED";
  source: string;
  observed_at: string;
  reason: string | null;
}>;

export type MarketStreamQuote = Readonly<{
  type: "quote";
  instrument_ref: string;
  source: string;
  source_cutoff: string;
  received_at: string;
  bid_price: string;
  ask_price: string;
  reference_price: string;
}>;

export type MarketStreamBarValue = Readonly<{
  open_at: string;
  close_at: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
}>;

export type MarketStreamBar = Readonly<{
  type: "bar";
  instrument_ref: string;
  interval: MarketInterval;
  source: string;
  source_cutoff: string;
  received_at: string;
  closed: boolean;
  bar: MarketStreamBarValue;
}>;

export type MarketStreamEvent =
  | MarketStreamServerStatus
  | MarketStreamQuote
  | MarketStreamBar;

export type MarketStreamClientStatus =
  | "DISABLED"
  | "CONNECTING"
  | "LIVE"
  | "RECONNECTING"
  | "STALE"
  | "FAILED";

export type PublicMarketStreamSnapshot = Readonly<{
  environmentScope: string;
  status: MarketStreamClientStatus;
  statusReason: string | null;
  statusSource: string | null;
  statusObservedAt: string | null;
  quote: MarketStreamQuote | null;
  liveBar: MarketStreamBar | null;
  /**
   * Increments once when the first quote arrives after an initial connection,
   * reconnect, or stale period. Consumers can use it to reload REST history and
   * close any gap without tying REST requests to every quote.
   */
  generation: number;
}>;

const MARKET_INTERVAL_SET: ReadonlySet<string> = new Set(MARKET_INTERVALS);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function isTimestamp(value: unknown): value is string {
  return isNonEmptyString(value) && Number.isFinite(Date.parse(value));
}

function decimalNumber(value: unknown): number | null {
  if (!isNonEmptyString(value)) {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function isMarketInterval(value: unknown): value is MarketInterval {
  return typeof value === "string" && MARKET_INTERVAL_SET.has(value);
}

function parseServerStatus(value: Record<string, unknown>): MarketStreamServerStatus | null {
  const state = value.state;
  const reason = value.reason;
  if (
    (state !== "CONNECTING"
      && state !== "LIVE"
      && state !== "RECONNECTING"
      && state !== "FAILED")
    || !isNonEmptyString(value.source)
    || !isTimestamp(value.observed_at)
    || (reason !== null && typeof reason !== "string")
  ) {
    return null;
  }
  return {
    type: "status",
    state,
    source: value.source,
    observed_at: value.observed_at,
    reason,
  };
}

function parseQuote(value: Record<string, unknown>): MarketStreamQuote | null {
  const bid = decimalNumber(value.bid_price);
  const ask = decimalNumber(value.ask_price);
  const reference = decimalNumber(value.reference_price);
  if (
    !isNonEmptyString(value.instrument_ref)
    || !isNonEmptyString(value.source)
    || !isTimestamp(value.source_cutoff)
    || !isTimestamp(value.received_at)
    || bid === null
    || ask === null
    || reference === null
    || bid <= 0
    || ask < bid
    || reference < bid
    || reference > ask
  ) {
    return null;
  }
  return {
    type: "quote",
    instrument_ref: value.instrument_ref,
    source: value.source,
    source_cutoff: value.source_cutoff,
    received_at: value.received_at,
    bid_price: value.bid_price as string,
    ask_price: value.ask_price as string,
    reference_price: value.reference_price as string,
  };
}

function parseBar(value: Record<string, unknown>): MarketStreamBar | null {
  if (
    !isNonEmptyString(value.instrument_ref)
    || !isMarketInterval(value.interval)
    || !isNonEmptyString(value.source)
    || !isTimestamp(value.source_cutoff)
    || !isTimestamp(value.received_at)
    || typeof value.closed !== "boolean"
    || !isRecord(value.bar)
  ) {
    return null;
  }
  const bar = value.bar;
  const open = decimalNumber(bar.open);
  const high = decimalNumber(bar.high);
  const low = decimalNumber(bar.low);
  const close = decimalNumber(bar.close);
  const volume = decimalNumber(bar.volume);
  if (
    !isTimestamp(bar.open_at)
    || !isTimestamp(bar.close_at)
    || Date.parse(bar.close_at) <= Date.parse(bar.open_at)
    || open === null
    || high === null
    || low === null
    || close === null
    || volume === null
    || Math.min(open, high, low, close) <= 0
    || volume < 0
    || high < Math.max(open, close)
    || low > Math.min(open, close)
    || high < low
  ) {
    return null;
  }
  return {
    type: "bar",
    instrument_ref: value.instrument_ref,
    interval: value.interval,
    source: value.source,
    source_cutoff: value.source_cutoff,
    received_at: value.received_at,
    closed: value.closed,
    bar: {
      open_at: bar.open_at,
      close_at: bar.close_at,
      open: bar.open as string,
      high: bar.high as string,
      low: bar.low as string,
      close: bar.close as string,
      volume: bar.volume as string,
    },
  };
}

/**
 * Parses the local relay boundary defensively. Unknown or malformed messages
 * are ignored instead of being allowed to corrupt the visible market state.
 */
export function parseMarketStreamEvent(raw: unknown): MarketStreamEvent | null {
  let value: unknown = raw;
  if (typeof raw === "string") {
    try {
      value = JSON.parse(raw) as unknown;
    } catch {
      return null;
    }
  }
  if (!isRecord(value)) {
    return null;
  }
  if (value.type === "status") {
    return parseServerStatus(value);
  }
  if (value.type === "quote") {
    return parseQuote(value);
  }
  if (value.type === "bar") {
    return parseBar(value);
  }
  return null;
}

export function shouldUseMarketStreamBar(
  event: MarketStreamBar,
  instrumentRef: string,
  interval: MarketInterval,
  expectedSource?: string | null,
): boolean {
  return event.instrument_ref === instrumentRef
    && event.interval === interval
    && (!expectedSource || event.source === expectedSource);
}

export function marketStreamReconnectDelayMs(attempt: number): number {
  const boundedAttempt = Number.isFinite(attempt)
    ? Math.max(0, Math.floor(attempt))
    : 0;
  return Math.min(
    MARKET_STREAM_RECONNECT_BASE_MS * (2 ** boundedAttempt),
    MARKET_STREAM_RECONNECT_MAX_MS,
  );
}

export function nextMarketStreamGeneration(
  generation: number,
  awaitingFreshQuote: boolean,
): number {
  return generation + (awaitingFreshQuote ? 1 : 0);
}

export function marketStreamQuoteThrottleDelayMs(
  lastCommitAt: number,
  now: number,
): number {
  if (lastCommitAt <= 0) {
    return 0;
  }
  return Math.max(
    0,
    Math.min(
      MARKET_STREAM_QUOTE_THROTTLE_MS,
      MARKET_STREAM_QUOTE_THROTTLE_MS - (now - lastCommitAt),
    ),
  );
}

export function isMarketStreamQuoteStale(
  lastQuoteReceivedAt: number | null,
  now: number,
): boolean {
  return lastQuoteReceivedAt !== null
    && now - lastQuoteReceivedAt >= MARKET_STREAM_STALE_AFTER_MS;
}

export function isUsableExecutionQuote(
  quote: MarketStreamQuote | null,
  expectedSource: string | null,
  now: number,
): quote is MarketStreamQuote {
  if (quote === null) return false;
  if (expectedSource === null || quote.source !== expectedSource) return false;
  return !isMarketStreamQuoteStale(Date.parse(quote.received_at), now);
}

export function marketStreamWebSocketUrl(
  pageUrl: string,
  instrumentRef: string,
): string {
  const url = new URL("/api/v1/market-stream", pageUrl);
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new TypeError("MARKET_STREAM_PAGE_PROTOCOL_UNSUPPORTED");
  }
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.searchParams.set("instrument_ref", instrumentRef);
  return url.toString();
}

function initialSnapshot(
  enabled: boolean,
  environmentScope: string,
): PublicMarketStreamSnapshot {
  return {
    environmentScope,
    status: enabled ? "CONNECTING" : "DISABLED",
    statusReason: null,
    statusSource: null,
    statusObservedAt: null,
    quote: null,
    liveBar: null,
    generation: 0,
  };
}

/**
 * Subscribes to Halpha's same-origin, read-only public-market relay.
 *
 * The local socket reconnects with a capped exponential retry schedule. Venue
 * reconnect and resubscription remain owned by the server-side market adapter.
 */
export function usePublicMarketStream(
  enabled: boolean,
  instrumentRef: string,
  selectedInterval: MarketInterval,
  environmentScope: string,
  expectedSource: string | null,
): PublicMarketStreamSnapshot {
  const [snapshot, setSnapshot] = useState<PublicMarketStreamSnapshot>(
    () => initialSnapshot(enabled, environmentScope),
  );
  const selectedIntervalRef = useRef(selectedInterval);
  selectedIntervalRef.current = selectedInterval;

  useEffect(() => {
    setSnapshot((current) => (
      current.liveBar === null || current.liveBar.interval === selectedInterval
        ? current
        : { ...current, liveBar: null }
    ));
  }, [selectedInterval]);

  useEffect(() => {
    if (!enabled) {
      setSnapshot(initialSnapshot(false, environmentScope));
      return undefined;
    }
    if (expectedSource === null) {
      setSnapshot({
        ...initialSnapshot(true, environmentScope),
        status: "FAILED",
        statusReason: "MARKET_STREAM_ENVIRONMENT_UNSUPPORTED",
      });
      return undefined;
    }
    if (typeof window === "undefined" || typeof WebSocket === "undefined") {
      setSnapshot({
        ...initialSnapshot(true, environmentScope),
        status: "FAILED",
        statusReason: "LOCAL_WEBSOCKET_UNAVAILABLE",
      });
      return undefined;
    }

    let disposed = false;
    let socket: WebSocket | null = null;
    let reconnectAttempt = 0;
    let reconnectTimer: number | null = null;
    let quoteTimer: number | null = null;
    let staleTimer: number | null = null;
    let pendingQuote: MarketStreamQuote | null = null;
    let lastQuoteCommitAt = 0;
    let lastQuoteReceivedAt: number | null = null;
    let awaitingFreshQuote = true;

    setSnapshot(initialSnapshot(true, environmentScope));

    const clearTimer = (timer: number | null): void => {
      if (timer !== null) {
        window.clearTimeout(timer);
      }
    };

    const clearPendingQuote = (): void => {
      clearTimer(quoteTimer);
      quoteTimer = null;
      pendingQuote = null;
    };

    const armStaleTimer = (): void => {
      clearTimer(staleTimer);
      const quoteAtWhenArmed = lastQuoteReceivedAt;
      staleTimer = window.setTimeout(() => {
        staleTimer = null;
        if (
          disposed
          || lastQuoteReceivedAt !== quoteAtWhenArmed
          || (
            quoteAtWhenArmed !== null
            && !isMarketStreamQuoteStale(quoteAtWhenArmed, Date.now())
          )
        ) {
          return;
        }
        awaitingFreshQuote = true;
        setSnapshot((current) => ({
          ...current,
          status: "STALE",
          statusReason: "MARKET_STREAM_QUOTE_STALE",
          statusObservedAt: new Date().toISOString(),
        }));
      }, MARKET_STREAM_STALE_AFTER_MS);
    };

    const commitPendingQuote = (): void => {
      quoteTimer = null;
      if (disposed || pendingQuote === null) {
        return;
      }
      const quote = pendingQuote;
      pendingQuote = null;
      const recovered = awaitingFreshQuote;
      awaitingFreshQuote = false;
      reconnectAttempt = 0;
      lastQuoteCommitAt = Date.now();
      setSnapshot((current) => ({
        ...current,
        status: "LIVE",
        statusReason: null,
        statusSource: quote.source,
        statusObservedAt: quote.received_at,
        quote,
        generation: nextMarketStreamGeneration(current.generation, recovered),
      }));
    };

    const receiveQuote = (quote: MarketStreamQuote): void => {
      lastQuoteReceivedAt = Date.now();
      armStaleTimer();
      pendingQuote = quote;
      const remaining = marketStreamQuoteThrottleDelayMs(
        lastQuoteCommitAt,
        Date.now(),
      );
      if (remaining === 0) {
        clearTimer(quoteTimer);
        commitPendingQuote();
      } else if (quoteTimer === null) {
        quoteTimer = window.setTimeout(commitPendingQuote, remaining);
      }
    };

    const applyServerStatus = (event: MarketStreamServerStatus): void => {
      if (event.source !== expectedSource) {
        awaitingFreshQuote = true;
        clearPendingQuote();
        clearTimer(staleTimer);
        staleTimer = null;
        setSnapshot({
          ...initialSnapshot(true, environmentScope),
          status: "FAILED",
          statusReason: "MARKET_STREAM_SOURCE_MISMATCH",
          statusSource: event.source,
          statusObservedAt: event.observed_at,
        });
        return;
      }
      if (event.state === "LIVE") {
        const stale = isMarketStreamQuoteStale(lastQuoteReceivedAt, Date.now());
        setSnapshot((current) => ({
          ...current,
          status: stale ? "STALE" : "LIVE",
          statusReason: stale ? "MARKET_STREAM_QUOTE_STALE" : event.reason,
          statusSource: event.source,
          statusObservedAt: event.observed_at,
        }));
        armStaleTimer();
        return;
      }
      awaitingFreshQuote = true;
      clearPendingQuote();
      clearTimer(staleTimer);
      staleTimer = null;
      setSnapshot((current) => ({
        ...current,
        status: event.state,
        statusReason: event.reason,
        statusSource: event.source,
        statusObservedAt: event.observed_at,
      }));
    };

    const scheduleReconnect = (reason: string): void => {
      if (disposed || reconnectTimer !== null) {
        return;
      }
      awaitingFreshQuote = true;
      clearPendingQuote();
      clearTimer(staleTimer);
      staleTimer = null;
      const delay = marketStreamReconnectDelayMs(reconnectAttempt);
      reconnectAttempt += 1;
      setSnapshot((current) => ({
        ...current,
        status: "RECONNECTING",
        statusReason: reason,
        statusObservedAt: new Date().toISOString(),
      }));
      reconnectTimer = window.setTimeout(() => {
        reconnectTimer = null;
        connect();
      }, delay);
    };

    const connect = (): void => {
      if (disposed) {
        return;
      }
      let nextSocket: WebSocket;
      try {
        nextSocket = new WebSocket(
          marketStreamWebSocketUrl(window.location.href, instrumentRef),
        );
      } catch {
        scheduleReconnect("LOCAL_WEBSOCKET_CONSTRUCTION_FAILED");
        return;
      }
      socket = nextSocket;

      nextSocket.onmessage = (message) => {
        if (disposed || socket !== nextSocket) {
          return;
        }
        const event = parseMarketStreamEvent(message.data);
        if (event === null) {
          return;
        }
        if (event.type === "status") {
          applyServerStatus(event);
        } else if (
          event.type === "quote"
          && event.instrument_ref === instrumentRef
          && event.source === expectedSource
        ) {
          receiveQuote(event);
        } else if (
          event.type === "bar"
          && shouldUseMarketStreamBar(
            event,
            instrumentRef,
            selectedIntervalRef.current,
            expectedSource,
          )
        ) {
          setSnapshot((current) => ({ ...current, liveBar: event }));
        }
      };

      nextSocket.onclose = (event) => {
        if (disposed || socket !== nextSocket) {
          return;
        }
        socket = null;
        awaitingFreshQuote = true;
        clearPendingQuote();
        clearTimer(staleTimer);
        staleTimer = null;
        if (event.code === 1008) {
          setSnapshot((current) => ({
            ...current,
            status: "FAILED",
            statusReason: "LOCAL_WEBSOCKET_POLICY_REJECTED",
            statusObservedAt: new Date().toISOString(),
          }));
          return;
        }
        scheduleReconnect(`LOCAL_WEBSOCKET_CLOSED_${event.code}`);
      };

      nextSocket.onerror = () => {
        if (
          disposed
          || socket !== nextSocket
          || nextSocket.readyState === WebSocket.CLOSING
          || nextSocket.readyState === WebSocket.CLOSED
        ) {
          return;
        }
        nextSocket.close();
      };
    };

    connect();

    return () => {
      disposed = true;
      clearTimer(reconnectTimer);
      clearTimer(quoteTimer);
      clearTimer(staleTimer);
      reconnectTimer = null;
      quoteTimer = null;
      staleTimer = null;
      pendingQuote = null;
      if (socket !== null) {
        const closingSocket = socket;
        socket = null;
        closingSocket.onopen = null;
        closingSocket.onmessage = null;
        closingSocket.onerror = null;
        closingSocket.onclose = null;
        if (
          closingSocket.readyState === WebSocket.CONNECTING
          || closingSocket.readyState === WebSocket.OPEN
        ) {
          closingSocket.close(1000, "MARKET_STREAM_HOOK_DISPOSED");
        }
      }
    };
  }, [enabled, environmentScope, expectedSource, instrumentRef]);

  return snapshot.environmentScope === environmentScope
    ? snapshot
    : initialSnapshot(enabled, environmentScope);
}
