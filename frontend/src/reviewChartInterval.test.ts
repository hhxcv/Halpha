import { describe, expect, it } from "vitest";

import {
  defaultExecutionWindowInterval,
  defaultReviewChartInterval,
  executionWindowEndAt,
  executionWindowFitsInterval,
  reviewWindowFitsInterval,
} from "./reviewChartInterval";

describe("review chart interval selection", () => {
  it("keeps one-minute detail when the padded window fits the market API", () => {
    const start = Date.parse("2026-07-27T00:00:00Z");
    const end = Date.parse("2026-07-27T04:00:00Z");

    expect(reviewWindowFitsInterval(start, end, "1m")).toBe(true);
    expect(defaultReviewChartInterval(start, end)).toBe("1m");
  });

  it("uses fifteen-minute bars for a long trade instead of requesting too many one-minute bars", () => {
    const start = Date.parse("2026-07-26T10:17:58Z");
    const end = Date.parse("2026-07-27T00:44:37Z");

    expect(reviewWindowFitsInterval(start, end, "1m")).toBe(false);
    expect(reviewWindowFitsInterval(start, end, "15m")).toBe(true);
    expect(defaultReviewChartInterval(start, end)).toBe("15m");
  });

  it("does not block the fallback view when timestamps are unavailable", () => {
    expect(defaultReviewChartInterval(Number.NaN, Number.NaN)).toBe("1m");
  });

  it("selects the smallest interval that fits a complete activation window", () => {
    const start = Date.parse("2026-07-26T02:17:57Z");

    expect(defaultExecutionWindowInterval(
      start,
      Date.parse("2026-07-26T03:17:57Z"),
    )).toBe("1m");
    expect(defaultExecutionWindowInterval(
      start,
      Date.parse("2026-07-26T16:44:38Z"),
    )).toBe("15m");
    expect(defaultExecutionWindowInterval(
      start,
      Date.parse("2026-08-15T02:17:57Z"),
    )).toBe("4h");
  });

  it("reports whether a manually selected interval still contains the complete execution", () => {
    const start = Date.parse("2026-07-26T02:17:58Z");
    const end = Date.parse("2026-07-26T16:44:37Z");

    expect(executionWindowFitsInterval(start, end, "1m")).toBe(false);
    expect(executionWindowFitsInterval(start, end, "5m")).toBe(false);
    expect(executionWindowFitsInterval(start, end, "15m")).toBe(true);
    expect(executionWindowFitsInterval(start, end, "1h")).toBe(true);
    expect(executionWindowFitsInterval(Number.NaN, end, "15m")).toBe(false);
  });

  it("adds right-side padding so the closure is not pinned to the chart edge", () => {
    expect(executionWindowEndAt(
      Date.parse("2026-07-27T00:00:00Z"),
      "15m",
      Date.parse("2026-07-27T05:00:00Z"),
    )).toBe("2026-07-27T03:00:00.000Z");
    expect(executionWindowEndAt(Number.NaN, "15m")).toBeNull();
  });

  it("does not request future bars for a plan that just ended", () => {
    expect(executionWindowEndAt(
      Date.parse("2026-07-27T00:59:58Z"),
      "1m",
      Date.parse("2026-07-27T01:00:00Z"),
    )).toBe("2026-07-27T01:00:00.000Z");
  });
});
