import { describe, expect, it } from "vitest";

import type { OrderScheduleSpec } from "../api/client";
import {
  buildOrderScheduleChartAnnotations,
  chartPeriod,
  chartPriceInput,
  expandedVisiblePriceRange,
  marketIntervalForPeriod,
  marketWindowBounds,
  orderedPriceRange,
} from "./orderScheduleChartModel";

function defaultSpec(limitPrice = "65750"): OrderScheduleSpec {
  return {
    price_distribution: { kind: "SINGLE", limit_price: limitPrice },
    amount_distribution: {
      mode: "FIXED",
      direction: "LOW_TO_HIGH",
      base_notional: "10",
      linear_step: "10",
      exponential_ratio: "2",
      custom_notionals: [],
    },
    venue_policy: {
      order_type: "LIMIT",
      time_in_force: "GTC",
      post_only: false,
      price_match: null,
      display_quantity: null,
      expire_at: null,
    },
    submission_mode: "SERIAL_PROTECTED",
    submission_order: "HIGH_TO_LOW",
    entry_conditions: {
      operator: "ALL",
      items: [{ kind: "DECISION_BASIS_READY" }],
    },
    protection_policy: {
      initial_stop: {
        distance_bps: "100",
        trigger_source: "MARK_PRICE",
        coverage: "EACH_CONFIRMED_FILL",
      },
      take_profit_ladder: null,
      time_exit_seconds: null,
    },
    dynamic_rules: [],
  };
}

describe("order schedule chart model", () => {
  it("orders the same interval for upward and downward drags", () => {
    expect(orderedPriceRange(10, 30)).toEqual([10, 30]);
    expect(orderedPriceRange(30, 10)).toEqual([10, 30]);
  });

  it("requests only closed bars and preserves the inclusive count", () => {
    const range = marketWindowBounds("2026-07-23T08:14:59.999Z", "15m", 160);
    expect(range).toEqual({
      startAt: "2026-07-21T16:00:00.000Z",
      endAt: "2026-07-23T07:45:00.000Z",
    });
    const intervalMilliseconds = 15 * 60_000;
    expect(
      (Date.parse(range!.endAt) - Date.parse(range!.startAt))
        / intervalMilliseconds
        + 1,
    ).toBe(160);

    expect(marketWindowBounds("2026-07-23T08:00:00.000Z", "1h", 3)).toEqual({
      startAt: "2026-07-23T05:00:00.000Z",
      endAt: "2026-07-23T07:00:00.000Z",
    });
    expect(marketWindowBounds("2026-07-23T08:00:00.000Z", "1d", 3)).toEqual({
      startAt: "2026-07-20T00:00:00.000Z",
      endAt: "2026-07-22T00:00:00.000Z",
    });
  });

  it("rejects invalid market cutoffs and unusable window sizes", () => {
    expect(marketWindowBounds("not-a-time", "15m")).toBeNull();
    expect(marketWindowBounds("2026-07-23T08:00:00.000Z", "15m", 1)).toBeNull();
  });

  it("maps every supported timeframe to and from KLineCharts periods", () => {
    expect(chartPeriod("1m")).toEqual({ type: "minute", span: 1 });
    expect(chartPeriod("5m")).toEqual({ type: "minute", span: 5 });
    expect(chartPeriod("15m")).toEqual({ type: "minute", span: 15 });
    expect(chartPeriod("1h")).toEqual({ type: "hour", span: 1 });
    expect(chartPeriod("4h")).toEqual({ type: "hour", span: 4 });
    expect(chartPeriod("1d")).toEqual({ type: "day", span: 1 });
    expect(marketIntervalForPeriod({ type: "hour", span: 4 })).toBe("4h");
    expect(marketIntervalForPeriod({ type: "week", span: 1 })).toBeNull();
  });

  it("writes stable decimal strings without exponential notation", () => {
    expect(chartPriceInput(10)).toBe("10");
    expect(chartPriceInput(10.125)).toBe("10.125");
    expect(chartPriceInput(0.00000001)).toBe("0.00000001");
  });

  it("expands the price axis only when valid preview prices fall outside it", () => {
    expect(
      expandedVisiblePriceRange(65_560, 66_300, [65_000, 65_250, 66_000], 0.4),
    ).toEqual([64_948, 66_352]);
    expect(
      expandedVisiblePriceRange(65_000, 66_000, [65_250, 65_500, 65_750], 0.4),
    ).toEqual([65_000, 66_000]);
    expect(
      expandedVisiblePriceRange(65_000, 66_000, [Number.NaN, -1], 0.4),
    ).toEqual([65_000, 66_000]);
  });

  it("keeps the default single limit, reference price and server leg as distinct annotations", () => {
    const spec = defaultSpec();
    const annotations = buildOrderScheduleChartAnnotations({
      direction: "LONG",
      referencePrice: "65755.5",
      spec,
      previewState: "READY",
      previewLegs: [{
        leg_index: 0,
        leg_count: 1,
        raw_price: "65750",
        price: "65750.0",
        sizing_price: "65750.0",
        requested_notional: "10",
        quantity: "0.0001",
        effective_notional: "6.575",
      }],
    });

    expect(annotations.priceAnnotations.map((item) => item.role)).toEqual([
      "REFERENCE",
      "SINGLE_LIMIT",
      "NORMALIZED_LEG",
    ]);
    expect(annotations.priceAnnotations[1]).toMatchObject({
      label: "输入限价",
      authority: "DRAFT_INPUT",
      draggable: true,
      price: 65750,
    });
    expect(annotations.priceAnnotations[2]?.detail).toContain("有效 6.575 USDT");
  });

  it("hides stale server legs while preserving current draft inputs", () => {
    const spec = defaultSpec();
    const annotations = buildOrderScheduleChartAnnotations({
      direction: "LONG",
      referencePrice: "65755.5",
      spec,
      previewState: "PENDING",
      previewLegs: [{
        leg_index: 0,
        leg_count: 1,
        raw_price: "65750",
        price: "65750",
        sizing_price: "65750",
        requested_notional: "10",
        quantity: "0.0001",
        effective_notional: "6.575",
      }],
    });

    expect(annotations.priceAnnotations.map((item) => item.role)).toEqual([
      "REFERENCE",
      "SINGLE_LIMIT",
    ]);
  });

  it("draws only absolute prices and describes venue or relative thresholds without fake lines", () => {
    const spec = defaultSpec();
    spec.venue_policy.price_match = "OPPONENT_5";
    spec.price_distribution = { kind: "SINGLE", limit_price: null };
    spec.entry_conditions.items.push(
      { kind: "MARK_PRICE", comparator: "LTE", price: "65000" },
      { kind: "SPREAD_BPS", maximum_bps: "10" },
      { kind: "PRICE_MOVE_BPS", comparator: "ABS_GTE", threshold_bps: "30", window_seconds: 20 },
    );
    spec.protection_policy.take_profit_ladder = {
      levels: [{ trigger_r: "2", quantity_fraction: "1" }],
    };
    spec.dynamic_rules.push({
      kind: "CANCEL_ON_SHOCK",
      window_seconds: 15,
      adverse_move_bps: "40",
      max_triggers: 1,
    });

    const annotations = buildOrderScheduleChartAnnotations({
      direction: "SHORT",
      referencePrice: "65755.5",
      spec,
      previewState: "BLOCKED",
      previewLegs: [],
    });

    expect(annotations.priceAnnotations.map((item) => item.role)).toEqual([
      "REFERENCE",
      "MARK_CONDITION",
    ]);
    expect(annotations.relativeRules.map((item) => item.id)).toEqual([
      "halpha-price-match",
      "halpha-spread-condition",
      "halpha-price-move-condition",
      "halpha-initial-stop",
      "halpha-take-profit-0",
      "halpha-shock-cancel",
    ]);
    expect(annotations.relativeRules.at(-1)?.detail).toContain("空头只把向上变动视为不利");
  });
});
