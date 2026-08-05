import type { MarketInterval } from "./api/client";

export type ReviewChartInterval = "1m" | "15m";

const MAX_MARKET_WINDOW_BARS = 300;
const REVIEW_PADDING_BARS: Record<ReviewChartInterval, number> = {
  "1m": 24,
  "15m": 12,
};
const INTERVAL_MS: Record<ReviewChartInterval, number> = {
  "1m": 60_000,
  "15m": 15 * 60_000,
};

const EXECUTION_WINDOW_BAR_COUNT = 160;
const EXECUTION_WINDOW_PADDING_BARS = 12;
const EXECUTION_INTERVAL_MS: Record<MarketInterval, number> = {
  "1m": 60_000,
  "5m": 5 * 60_000,
  "15m": 15 * 60_000,
  "1h": 60 * 60_000,
  "4h": 4 * 60 * 60_000,
  "1d": 24 * 60 * 60_000,
};
const EXECUTION_INTERVALS = Object.keys(
  EXECUTION_INTERVAL_MS,
) as MarketInterval[];

export function reviewWindowFitsInterval(
  startMs: number,
  endMs: number,
  interval: ReviewChartInterval,
): boolean {
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs)) return true;
  const durationMs = Math.max(0, endMs - startMs);
  const requiredBars = Math.ceil(durationMs / INTERVAL_MS[interval])
    + REVIEW_PADDING_BARS[interval] * 2;
  return requiredBars <= MAX_MARKET_WINDOW_BARS;
}

export function defaultReviewChartInterval(
  startMs: number,
  endMs: number,
): ReviewChartInterval {
  return reviewWindowFitsInterval(startMs, endMs, "1m") ? "1m" : "15m";
}

export function defaultExecutionWindowInterval(
  startMs: number,
  endMs: number,
): MarketInterval {
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs)) return "15m";
  return EXECUTION_INTERVALS.find(
    (interval) => executionWindowFitsInterval(startMs, endMs, interval),
  ) ?? "1d";
}

export function executionWindowFitsInterval(
  startMs: number,
  endMs: number,
  interval: MarketInterval,
): boolean {
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs)) return false;
  const durationMs = Math.max(0, endMs - startMs);
  const usableBars = EXECUTION_WINDOW_BAR_COUNT
    - EXECUTION_WINDOW_PADDING_BARS * 2;
  return Math.ceil(durationMs / EXECUTION_INTERVAL_MS[interval]) <= usableBars;
}

export function executionWindowEndAt(
  endMs: number,
  interval: MarketInterval,
  nowMs = Date.now(),
): string | null {
  if (!Number.isFinite(endMs) || !Number.isFinite(nowMs)) return null;
  const paddedEndMs = endMs
    + EXECUTION_WINDOW_PADDING_BARS * EXECUTION_INTERVAL_MS[interval];
  return new Date(Math.min(paddedEndMs, nowMs)).toISOString();
}
