import type {
  OrderScheduleCondition,
  OrderScheduleSpec,
} from "../api/client";

function isGeneratedThreshold(value: string): boolean {
  const parsed = Number(value);
  return Number.isFinite(parsed) && Math.abs(parsed - 30) <= 1e-9;
}

export function retargetGeneratedEventCondition(
  schedule: OrderScheduleSpec,
  previousDirection: "LONG" | "SHORT",
  nextDirection: "LONG" | "SHORT",
): OrderScheduleSpec {
  if (
    previousDirection === nextDirection
    || schedule.entry_program?.kind !== "EVENT_TRIGGERED"
  ) {
    return schedule;
  }
  const previousComparator = previousDirection === "LONG" ? "GTE" : "DROP_GTE";
  const nextComparator: "GTE" | "DROP_GTE" = nextDirection === "LONG"
    ? "GTE"
    : "DROP_GTE";
  let changed = false;
  const items = schedule.entry_conditions.items.map<OrderScheduleCondition>((condition) => {
    if (
      condition.kind !== "PRICE_MOVE_BPS"
      || condition.comparator !== previousComparator
      || !isGeneratedThreshold(condition.threshold_bps)
      || condition.window_seconds !== 30
    ) {
      return condition;
    }
    changed = true;
    return { ...condition, comparator: nextComparator };
  });
  if (!changed) return schedule;
  return {
    ...schedule,
    entry_conditions: {
      ...schedule.entry_conditions,
      items,
    },
  };
}
