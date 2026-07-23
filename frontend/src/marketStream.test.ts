import { describe, expect, it } from "vitest";

import {
  MARKET_STREAM_RECONNECT_MAX_MS,
  MARKET_STREAM_STALE_AFTER_MS,
  expectedMarketSourceForEnvironment,
  isMarketStreamQuoteStale,
  isMarketSourceForEnvironment,
  isUsableExecutionQuote,
  marketEnvironmentScopeKey,
  marketStreamQuoteThrottleDelayMs,
  marketStreamReconnectDelayMs,
  marketStreamWebSocketUrl,
  nextMarketStreamGeneration,
  parseMarketStreamEvent,
  shouldUseMarketStreamBar,
  type MarketStreamBar,
} from "./marketStream";

const quoteEvent = {
  type: "quote",
  instrument_ref: "BTCUSDT-PERP",
  source: "BINANCE_DEMO_PUBLIC",
  source_cutoff: "2026-07-23T10:00:00.100Z",
  received_at: "2026-07-23T10:00:00.120Z",
  bid_price: "65738.2",
  ask_price: "65749",
  reference_price: "65743.6",
};

const barEvent = {
  type: "bar",
  instrument_ref: "BTCUSDT-PERP",
  interval: "15m",
  source: "BINANCE_LIVE_PUBLIC",
  source_cutoff: "2026-07-23T10:00:00.100Z",
  received_at: "2026-07-23T10:00:00.120Z",
  closed: false,
  bar: {
    open_at: "2026-07-23T09:45:00Z",
    close_at: "2026-07-23T10:00:00Z",
    open: "65700",
    high: "65800",
    low: "65650",
    close: "65743.6",
    volume: "42.5",
  },
};

describe("public market stream event parser", () => {
  it("accepts each server event shape", () => {
    expect(parseMarketStreamEvent(JSON.stringify({
      type: "status",
      state: "LIVE",
      source: "BINANCE_DEMO_PUBLIC",
      observed_at: "2026-07-23T10:00:00Z",
      reason: null,
    }))).toMatchObject({ type: "status", state: "LIVE" });

    expect(parseMarketStreamEvent(JSON.stringify(quoteEvent))).toEqual(quoteEvent);
    expect(parseMarketStreamEvent(barEvent)).toEqual(barEvent);
  });

  it("rejects invalid JSON, unknown events, and malformed status values", () => {
    expect(parseMarketStreamEvent("{")).toBeNull();
    expect(parseMarketStreamEvent({ type: "depth", bids: [] })).toBeNull();
    expect(parseMarketStreamEvent({
      type: "status",
      state: "UNKNOWN",
      source: "BINANCE_DEMO_PUBLIC",
      observed_at: "not-a-time",
      reason: null,
    })).toBeNull();
  });

  it("rejects crossed quotes and impossible candle values", () => {
    expect(parseMarketStreamEvent({
      ...quoteEvent,
      bid_price: "65750",
      ask_price: "65749",
    })).toBeNull();
    expect(parseMarketStreamEvent({
      ...barEvent,
      bar: { ...barEvent.bar, high: "65600" },
    })).toBeNull();
    expect(parseMarketStreamEvent({
      ...barEvent,
      interval: "2m",
    })).toBeNull();
  });
});

describe("public market stream selection and recovery helpers", () => {
  it("maps each runtime environment to exactly one accepted source", () => {
    expect(marketEnvironmentScopeKey("DEMO", "demo-primary"))
      .toBe("DEMO:demo-primary");
    expect(marketEnvironmentScopeKey("LIVE", "live-primary"))
      .not.toBe(marketEnvironmentScopeKey("DEMO", "live-primary"));
    expect(expectedMarketSourceForEnvironment("DEMO")).toBe("BINANCE_DEMO_PUBLIC");
    expect(expectedMarketSourceForEnvironment("LIVE")).toBe("BINANCE_LIVE_PUBLIC");
    expect(expectedMarketSourceForEnvironment("UNKNOWN")).toBeNull();
    expect(isMarketSourceForEnvironment("BINANCE_DEMO_PUBLIC", "DEMO")).toBe(true);
    expect(isMarketSourceForEnvironment("BINANCE_LIVE_PUBLIC", "LIVE")).toBe(true);
    expect(isMarketSourceForEnvironment("BINANCE_LIVE_PUBLIC", "DEMO"))
      .toBe(false);
    expect(isMarketSourceForEnvironment("BINANCE_DEMO_PUBLIC", "LIVE")).toBe(false);
  });

  it("selects only the requested instrument and chart interval", () => {
    const parsed = parseMarketStreamEvent(barEvent);
    expect(parsed?.type).toBe("bar");
    const bar = parsed as MarketStreamBar;
    expect(shouldUseMarketStreamBar(bar, "BTCUSDT-PERP", "15m")).toBe(true);
    expect(shouldUseMarketStreamBar(bar, "BTCUSDT-PERP", "1h")).toBe(false);
    expect(shouldUseMarketStreamBar(bar, "ETHUSDT-PERP", "15m")).toBe(false);
    expect(shouldUseMarketStreamBar(
      bar,
      "BTCUSDT-PERP",
      "15m",
      "BINANCE_LIVE_PUBLIC",
    )).toBe(true);
    expect(shouldUseMarketStreamBar(
      bar,
      "BTCUSDT-PERP",
      "15m",
      "BINANCE_DEMO_PUBLIC",
    )).toBe(false);
  });

  it("uses the same host and selects ws or wss from the page protocol", () => {
    expect(marketStreamWebSocketUrl(
      "http://127.0.0.1:8765/plans/new",
      "BTCUSDT-PERP",
    )).toBe(
      "ws://127.0.0.1:8765/api/v1/market-stream?instrument_ref=BTCUSDT-PERP",
    );
    expect(marketStreamWebSocketUrl(
      "https://halpha.local/plans/new",
      "BTCUSDT-PERP",
    )).toBe(
      "wss://halpha.local/api/v1/market-stream?instrument_ref=BTCUSDT-PERP",
    );
    expect(() => marketStreamWebSocketUrl(
      "file:///workbench.html",
      "BTCUSDT-PERP",
    )).toThrow("MARKET_STREAM_PAGE_PROTOCOL_UNSUPPORTED");
  });

  it("caps local reconnect delay and marks a quote stale at five seconds", () => {
    expect(marketStreamReconnectDelayMs(0)).toBe(500);
    expect(marketStreamReconnectDelayMs(1)).toBe(1_000);
    expect(marketStreamReconnectDelayMs(20)).toBe(MARKET_STREAM_RECONNECT_MAX_MS);
    expect(marketStreamReconnectDelayMs(Number.NaN)).toBe(500);
    expect(isMarketStreamQuoteStale(10_000, 10_000 + MARKET_STREAM_STALE_AFTER_MS - 1))
      .toBe(false);
    expect(isMarketStreamQuoteStale(10_000, 10_000 + MARKET_STREAM_STALE_AFTER_MS))
      .toBe(true);
    expect(isMarketStreamQuoteStale(null, 20_000)).toBe(false);
  });

  it("keeps a fresh execution quote independent from the combined route status", () => {
    const quote = parseMarketStreamEvent(quoteEvent);
    expect(quote?.type).toBe("quote");
    const parsedQuote = quote?.type === "quote" ? quote : null;
    const receivedAt = Date.parse(quoteEvent.received_at);
    expect(isUsableExecutionQuote(
      parsedQuote,
      "BINANCE_DEMO_PUBLIC",
      receivedAt + 1_000,
    )).toBe(true);
    expect(isUsableExecutionQuote(
      parsedQuote,
      "BINANCE_LIVE_PUBLIC",
      receivedAt + 1_000,
    )).toBe(false);
    expect(isUsableExecutionQuote(
      parsedQuote,
      "BINANCE_DEMO_PUBLIC",
      receivedAt + MARKET_STREAM_STALE_AFTER_MS,
    )).toBe(false);
    expect(isUsableExecutionQuote(
      parsedQuote ? { ...parsedQuote, source: "BINANCE_LIVE_PUBLIC" } : null,
      null,
      receivedAt + 1_000,
    )).toBe(false);
    expect(isUsableExecutionQuote(
      parsedQuote,
      null,
      receivedAt + 1_000,
    )).toBe(false);
  });

  it("advances the REST recovery generation only on the first fresh quote", () => {
    expect(nextMarketStreamGeneration(0, true)).toBe(1);
    expect(nextMarketStreamGeneration(1, false)).toBe(1);
    expect(nextMarketStreamGeneration(1, true)).toBe(2);
  });

  it("publishes the first quote immediately and caps later updates at four per second", () => {
    expect(marketStreamQuoteThrottleDelayMs(0, 10_000)).toBe(0);
    expect(marketStreamQuoteThrottleDelayMs(10_000, 10_000)).toBe(250);
    expect(marketStreamQuoteThrottleDelayMs(10_000, 10_100)).toBe(150);
    expect(marketStreamQuoteThrottleDelayMs(10_000, 10_250)).toBe(0);
  });
});
