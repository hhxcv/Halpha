import { describe, expect, it } from "vitest";

import type { MarketContext, OrderSchedulePreviewLeg } from "../api/client";
import {
  buildInitialStopRecommendations,
  projectedEntryBasis,
} from "./orderScheduleStopRecommendations";

const market = {
  source: "BINANCE_DEMO_PUBLIC",
  source_cutoff: "2026-08-05T01:00:00Z",
  latest_closed_15m_at: "2026-08-05T00:45:00Z",
  latest_closed_stop_reference_at: "2026-08-05T00:45:00Z",
  stop_reference_interval: "15m",
  atr_14: "100",
  stop_reference_atr_14: "100",
  stop_references: [
    {
      kind: "STRUCTURE_ATR",
      side: "LOWER",
      price: "64800",
      interval: "15m",
      lookback_bars: 20,
      atr_buffer_multiple: "0.2",
      method_version: "STOP_REFERENCE_MULTI_INTERVAL_V1",
    },
    {
      kind: "STRUCTURE_ATR",
      side: "UPPER",
      price: "65200",
      interval: "15m",
      lookback_bars: 20,
      atr_buffer_multiple: "0.2",
      method_version: "STOP_REFERENCE_MULTI_INTERVAL_V1",
    },
    {
      kind: "SWING_OBV",
      side: "LOWER",
      price: "64900",
      interval: "15m",
      lookback_bars: 20,
      atr_buffer_multiple: "0.2",
      volume_bias: "POSITIVE",
      method_version: "STOP_REFERENCE_MULTI_INTERVAL_V1",
    },
    {
      kind: "TREND_ATR",
      side: "LOWER",
      price: "64700",
      interval: "15m",
      lookback_bars: 20,
      atr_buffer_multiple: "0.8",
      trend_slope: "12.5",
      trend_r_squared: "0.82",
      method_version: "STOP_REFERENCE_MULTI_INTERVAL_V1",
    },
  ],
} as MarketContext;

const legs = [
  {
    price: "64900",
    sizing_price: "64900",
    quantity: "0.01",
  },
  {
    price: "65100",
    sizing_price: "65100",
    quantity: "0.01",
  },
] as OrderSchedulePreviewLeg[];

describe("initial stop recommendations", () => {
  it("uses the quantity-weighted preview entry basis", () => {
    expect(projectedEntryBasis(legs)).toBe(65_000);
  });

  it("selects distinct lower-side methods for a long plan", () => {
    const result = buildInitialStopRecommendations({
      direction: "LONG",
      market,
      previewLegs: legs,
    });

    expect(result.map((item) => item.kind)).toEqual([
      "SWING_OBV",
      "STRUCTURE_ATR",
      "TREND_ATR",
    ]);
    expect(result[0]).toMatchObject({
      label: "量价摆动位",
      price: 64_900,
      distanceBpsInput: "15.3846",
    });
    expect(result[0]?.evidence).toContain("OBV 偏正");
    expect(result[0]?.evidenceCutoff).toBe("2026-08-05T00:45:00Z");
  });

  it("uses upper-side evidence and the ATR fallback for a short plan", () => {
    const result = buildInitialStopRecommendations({
      direction: "SHORT",
      market,
      previewLegs: legs,
    });

    expect(result.map((item) => item.kind)).toEqual([
      "STRUCTURE_ATR",
      "ENTRY_ATR",
    ]);
    expect(result[0]?.price).toBe(65_200);
    expect(result[1]?.price).toBe(65_150);
  });

  it("uses the selected closed-bar interval and its ATR evidence", () => {
    const hourlyMarket = {
      ...market,
      stop_reference_interval: "1h",
      latest_closed_stop_reference_at: "2026-08-05T01:00:00Z",
      stop_reference_atr_14: "200",
      stop_references: market.stop_references.map((reference) => ({
        ...reference,
        interval: "1h",
      })),
    } as MarketContext;

    const result = buildInitialStopRecommendations({
      direction: "SHORT",
      market: hourlyMarket,
      previewLegs: legs,
    });

    expect(result[0]?.evidence).toContain("1h Donchian");
    expect(result[1]).toMatchObject({
      kind: "ENTRY_ATR",
      price: 65_300,
      evidenceCutoff: "2026-08-05T01:00:00Z",
    });
    expect(result[1]?.evidence).toContain("1h ATR 200 USDT");
  });

  it("returns no recommendations without a server-normalized entry basis", () => {
    expect(buildInitialStopRecommendations({
      direction: "LONG",
      market,
      previewLegs: [],
    })).toEqual([]);
  });
});
