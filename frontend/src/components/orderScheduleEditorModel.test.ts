import { describe, expect, it } from "vitest";

import type { OrderScheduleTransportSpec } from "../api/client";

import {
  createDefaultOrderScheduleSpec,
  generatedOffsetPrice,
  normalizedDirectConditionItems,
  resolvedEntryProgram,
  withoutGeneratedEventCondition,
} from "./orderScheduleEditorModel";

describe("order schedule editor model", () => {
  it("creates a protected one-time limit plan with automatic profit taking", () => {
    const schedule = createDefaultOrderScheduleSpec("64123.456");

    expect(schedule.entry_program?.kind).toBe("ONE_TIME");
    expect(schedule.price_distribution).toEqual({
      kind: "SINGLE",
      limit_price: "64123.456",
    });
    expect(schedule.entry_conditions.items).toEqual([
      { kind: "DECISION_BASIS_READY" },
    ]);
    expect(schedule.protection_policy.take_profit_ladder?.levels).toEqual([
      { trigger_r: "2", quantity_fraction: "1" },
    ]);
  });

  it("keeps the direct-ready condition from bypassing optional ANY conditions", () => {
    expect(normalizedDirectConditionItems("ANY", [
      { kind: "DECISION_BASIS_READY" },
      { kind: "SPREAD_BPS", maximum_bps: "10" },
    ])).toEqual([
      { kind: "SPREAD_BPS", maximum_bps: "10" },
    ]);
  });

  it("removes only the generated event default when leaving event entry", () => {
    expect(withoutGeneratedEventCondition("ALL", [
      { kind: "DECISION_BASIS_READY" },
      {
        kind: "PRICE_MOVE_BPS",
        comparator: "GTE",
        threshold_bps: "30",
        window_seconds: 30,
      },
    ], "LONG")).toEqual([{ kind: "DECISION_BASIS_READY" }]);

    expect(withoutGeneratedEventCondition("ALL", [
      { kind: "DECISION_BASIS_READY" },
      {
        kind: "PRICE_MOVE_BPS",
        comparator: "GTE",
        threshold_bps: "45",
        window_seconds: 30,
      },
    ], "LONG")).toHaveLength(2);
  });

  it("derives legacy entry shape and applies venue tick precision", () => {
    const schedule = createDefaultOrderScheduleSpec();
    const legacySchedule: OrderScheduleTransportSpec = {
      ...schedule,
      entry_program: null,
      price_distribution: {
      kind: "LADDER",
      lower_price: "63000",
      upper_price: "64000",
      level_count: 2,
      spacing_mode: "EQUAL",
      spacing_direction: "LOW_TO_HIGH",
      linear_start_weight: "1",
      linear_step: "1",
      geometric_ratio: "2",
      custom_gap_weights: [],
      },
    };

    expect(resolvedEntryProgram(legacySchedule).kind).toBe("PRICE_LADDER");
    expect(generatedOffsetPrice("64123.456", 0.99, "0.1")).toBe("63482.2");
  });
});
