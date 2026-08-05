import { describe, expect, it } from "vitest";

import type { OrderScheduleSpec } from "../api/client";
import { retargetGeneratedEventCondition } from "./orderScheduleDirectionModel";

function eventSchedule(): OrderScheduleSpec {
  return {
    entry_program: {
      kind: "EVENT_TRIGGERED",
      slice_count: 1,
      first_slice_delay_seconds: 0,
      slice_interval_seconds: 0,
    },
    price_distribution: { kind: "SINGLE", limit_price: null },
    amount_distribution: {
      mode: "FIXED",
      direction: "LOW_TO_HIGH",
      base_notional: "500",
      linear_step: "10",
      exponential_ratio: "2",
      custom_notionals: [],
    },
    venue_policy: {
      order_type: "MARKET",
      time_in_force: null,
      post_only: false,
      price_match: null,
      expire_at: null,
    },
    submission_mode: "SERIAL_PROTECTED",
    submission_order: "LOW_TO_HIGH",
    entry_conditions: {
      operator: "ALL",
      items: [
        { kind: "DECISION_BASIS_READY" },
        {
          kind: "PRICE_MOVE_BPS",
          comparator: "GTE",
          threshold_bps: "30",
          window_seconds: 30,
        },
      ],
    },
    protection_policy: {
      initial_stop: {
        distance_bps: "100",
        trigger_source: "MARK_PRICE",
        coverage: "EACH_CONFIRMED_FILL",
      },
      take_profit_ladder: {
        levels: [{ trigger_r: "2", quantity_fraction: "1" }],
      },
      time_exit_seconds: null,
    },
    dynamic_rules: [],
  };
}

describe("retargetGeneratedEventCondition", () => {
  it("retargets only the generated event default when direction changes", () => {
    const schedule = eventSchedule();

    const next = retargetGeneratedEventCondition(schedule, "LONG", "SHORT");

    expect(next).not.toBe(schedule);
    expect(next.entry_conditions.items).toContainEqual({
      kind: "PRICE_MOVE_BPS",
      comparator: "DROP_GTE",
      threshold_bps: "30",
      window_seconds: 30,
    });
  });

  it("preserves a user-adjusted event condition", () => {
    const schedule = eventSchedule();
    schedule.entry_conditions.items[1] = {
      kind: "PRICE_MOVE_BPS",
      comparator: "GTE",
      threshold_bps: "45",
      window_seconds: 30,
    };

    const next = retargetGeneratedEventCondition(schedule, "LONG", "SHORT");

    expect(next).toBe(schedule);
    expect(next.entry_conditions.items[1]).toMatchObject({
      comparator: "GTE",
      threshold_bps: "45",
    });
  });

  it("does not modify non-event entry programs", () => {
    const schedule = eventSchedule();
    schedule.entry_program = {
      kind: "ONE_TIME",
      slice_count: 1,
      first_slice_delay_seconds: 0,
      slice_interval_seconds: 0,
    };

    expect(
      retargetGeneratedEventCondition(schedule, "LONG", "SHORT"),
    ).toBe(schedule);
  });
});
