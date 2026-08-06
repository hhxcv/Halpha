import { describe, expect, it } from "vitest";

import { buildPlanPnlTrend, mergePlanPnlPoints } from "./planPnlTrend";

describe("buildPlanPnlTrend", () => {
  it("marks a long plan to market with attributed fees and funding", () => {
    const points = buildPlanPnlTrend({
      startedAt: "2026-08-05T00:00:00Z",
      sourceCutoff: "2026-08-05T00:30:00Z",
      direction: "LONG",
      fills: [
        {
          action_kind: "ENTRY",
          fill_time: "2026-08-05T00:05:00Z",
          order_side: "BUY",
          price: "100",
          quantity: "2",
          fee: "1",
          fee_currency: "USDT",
        },
        {
          action_kind: "TAKE_PROFIT",
          fill_time: "2026-08-05T00:25:00Z",
          order_side: "SELL",
          price: "95",
          quantity: "1",
          fee: "0.5",
          fee_currency: "USDT",
        },
      ],
      fundingFacts: [{
        kind: "FUNDING",
        source_time: "2026-08-05T00:15:00Z",
        payload: { income: "-2" },
      }],
      bars: [
        { close_at: "2026-08-05T00:10:00Z", close: "110" },
        { close_at: "2026-08-05T00:20:00Z", close: "90" },
        { close_at: "2026-08-05T00:30:00Z", close: "100" },
      ],
    });

    expect(points.map((point) => point.value)).toEqual([0, 19, -23, -8.5]);
  });

  it("derives the order side for a short entry when the venue side is absent", () => {
    const points = buildPlanPnlTrend({
      startedAt: "2026-08-05T00:00:00Z",
      sourceCutoff: "2026-08-05T00:10:00Z",
      direction: "SHORT",
      fills: [{
        action_kind: "ENTRY",
        fill_time: "2026-08-05T00:01:00Z",
        price: "100",
        quantity: "1",
        fee: "0.2",
        fee_currency: "USDT",
      }],
      fundingFacts: [],
      bars: [{ close_at: "2026-08-05T00:10:00Z", close: "90" }],
    });

    expect(points.at(-1)?.value).toBeCloseTo(9.8);
  });

  it("does not present a zero curve before the plan has any attributed fill", () => {
    expect(buildPlanPnlTrend({
      startedAt: "2026-08-05T00:00:00Z",
      sourceCutoff: "2026-08-05T00:10:00Z",
      direction: "LONG",
      fills: [],
      fundingFacts: [],
      bars: [{ close_at: "2026-08-05T00:10:00Z", close: "100" }],
    })).toEqual([]);
  });

  it("anchors a closed plan to the authoritative settlement without float drift", () => {
    const points = buildPlanPnlTrend({
      startedAt: "2026-08-05T00:00:00Z",
      sourceCutoff: "2026-08-05T00:03:00Z",
      settledAt: "2026-08-05T00:02:30Z",
      settledNetPnl: "-0.41626789",
      direction: "LONG",
      fills: [
        {
          action_kind: "ENTRY",
          fill_time: "2026-08-05T00:00:30Z",
          order_side: "BUY",
          price: "63710.8",
          quantity: "0.0078",
          fee: "0.19877769",
          fee_currency: "USDT",
        },
        {
          action_kind: "EXIT",
          fill_time: "2026-08-05T00:02:30Z",
          order_side: "SELL",
          price: "63708.4",
          quantity: "0.0078",
          fee: "0.1987702",
          fee_currency: "USDT",
        },
      ],
      fundingFacts: [],
      bars: [
        { close_at: "2026-08-05T00:01:00Z", close: "63710" },
        { close_at: "2026-08-05T00:03:00Z", close: "63708.4" },
      ],
    });

    expect(points.at(-1)).toEqual({
      at: "2026-08-05T00:03:00.000Z",
      value: Number("-0.41626789"),
    });
    expect(points.at(-1)?.value).toBe(Number("-0.41626789"));
  });
});

describe("mergePlanPnlPoints", () => {
  it("fits the chart budget without losing the start, end, gain peak, or drawdown", () => {
    const points = Array.from({ length: 20 }, (_, index) => ({
      at: new Date(Date.UTC(2026, 7, 5, 0, index)).toISOString(),
      value: index === 6 ? 18 : index === 13 ? -12 : index / 10,
    }));

    const merged = mergePlanPnlPoints(points, 8);

    expect(merged.length).toBeLessThanOrEqual(8);
    expect(merged[0]).toEqual(points[0]);
    expect(merged.at(-1)).toEqual(points.at(-1));
    expect(merged.map((point) => point.value)).toContain(18);
    expect(merged.map((point) => point.value)).toContain(-12);
    expect(merged.map((point) => Date.parse(point.at))).toEqual(
      [...merged].map((point) => Date.parse(point.at)).sort((left, right) => left - right),
    );
  });

  it("returns the existing point array when the chart already has enough room", () => {
    const points = [
      { at: "2026-08-05T00:00:00Z", value: 0 },
      { at: "2026-08-05T00:01:00Z", value: 1 },
    ];

    expect(mergePlanPnlPoints(points, 120)).toBe(points);
  });
});
