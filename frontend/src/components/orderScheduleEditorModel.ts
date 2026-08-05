import {
  ApiFailure,
  type OrderScheduleCondition,
  type OrderScheduleDynamicRule,
  type OrderScheduleEntryProgram,
  type OrderScheduleSpec,
  type OrderScheduleTransportSpec,
} from "../api/client";
import { fractionDigitsFromIncrement } from "../format";

export type ConditionKind = OrderScheduleCondition["kind"];
type DynamicRuleKind = OrderScheduleDynamicRule["kind"];

export function finiteNumber(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function generatedOffsetPrice(
  referencePrice: string | null | undefined,
  multiplier: number,
  tickSize: string | null,
): string | null {
  const reference = finiteNumber(referencePrice ?? "");
  if (
    reference === null
    || reference <= 0
    || !Number.isFinite(multiplier)
    || multiplier <= 0
  ) {
    return null;
  }
  const precision = fractionDigitsFromIncrement(tickSize) ?? 8;
  return (reference * multiplier)
    .toFixed(precision)
    .replace(/(\.\d*?)0+$/, "$1")
    .replace(/\.$/, "");
}

export function isPositive(value: string): boolean {
  const parsed = finiteNumber(value);
  return parsed !== null && parsed > 0;
}

export function isNonNegative(value: string): boolean {
  const parsed = finiteNumber(value);
  return parsed !== null && parsed >= 0;
}

export function evenlyDividedNotional(total: string, count: number): string | null {
  const parsed = finiteNumber(total);
  if (parsed === null || parsed <= 0 || !Number.isInteger(count) || count <= 0) return null;
  return String(Number((parsed / count).toFixed(8)));
}

export function approximatelyEqual(left: string, right: string): boolean {
  const leftValue = finiteNumber(left);
  const rightValue = finiteNumber(right);
  if (leftValue === null || rightValue === null) return false;
  return Math.abs(leftValue - rightValue) <= Math.max(1, Math.abs(rightValue)) * 1e-9;
}

export function resized(values: string[], count: number, fallback: string): string[] {
  return Array.from({ length: count }, (_, index) => values[index] ?? fallback);
}

export function replaceAt(values: string[], index: number, nextValue: string): string[] {
  return values.map((value, currentIndex) => currentIndex === index ? nextValue : value);
}

export function resolvedEntryProgram(
  spec: OrderScheduleTransportSpec,
): OrderScheduleEntryProgram {
  if (spec.entry_program) return spec.entry_program;
  return {
    kind: spec.price_distribution.kind === "LADDER"
      ? "PRICE_LADDER"
      : "ONE_TIME",
    slice_count: 1,
    first_slice_delay_seconds: 0,
    slice_interval_seconds: 0,
  };
}

export function hydrateOrderScheduleSpec(
  spec: OrderScheduleTransportSpec,
): OrderScheduleSpec {
  const entryProgram = spec.entry_program ?? {
    kind: spec.price_distribution.kind === "LADDER"
      ? "PRICE_LADDER"
      : "ONE_TIME",
    slice_count: 1,
    first_slice_delay_seconds: 0,
    slice_interval_seconds: 0,
  };
  const protectionPolicy = spec.protection_policy ?? {
    initial_stop: {
      distance_bps: "100",
      trigger_source: "MARK_PRICE",
      coverage: "EACH_CONFIRMED_FILL",
    },
    take_profit_ladder: {
      levels: [{ trigger_r: "2", quantity_fraction: "1" }],
    },
    time_exit_seconds: null,
  };
  return {
    ...spec,
    entry_program: entryProgram,
    protection_policy: protectionPolicy,
  };
}

export function conditionByKind<K extends ConditionKind>(
  items: OrderScheduleCondition[],
  kind: K,
): Extract<OrderScheduleCondition, { kind: K }> | undefined {
  return items.find((item) => item.kind === kind) as
    | Extract<OrderScheduleCondition, { kind: K }>
    | undefined;
}

export function withCondition(
  items: OrderScheduleCondition[],
  condition: OrderScheduleCondition,
): OrderScheduleCondition[] {
  const existing = items.some((item) => item.kind === condition.kind);
  if (!existing) return [...items, condition];
  return items.map((item) => item.kind === condition.kind ? condition : item);
}

export function withoutCondition(
  items: OrderScheduleCondition[],
  kind: ConditionKind,
): OrderScheduleCondition[] {
  return items.filter((item) => item.kind !== kind);
}

const directReadyCondition: OrderScheduleCondition = { kind: "DECISION_BASIS_READY" };

export function normalizedDirectConditionItems(
  operator: "ALL" | "ANY",
  items: OrderScheduleCondition[],
): OrderScheduleCondition[] {
  const optional = withoutCondition(items, "DECISION_BASIS_READY");
  if (operator === "ALL" || optional.length === 0) {
    return [directReadyCondition, ...optional];
  }
  // DIRECT_EXECUTION readiness is true whenever this editor's activation can
  // run. Under ANY it would otherwise bypass every selected market condition.
  return optional;
}

export function withoutGeneratedEventCondition(
  operator: "ALL" | "ANY",
  items: OrderScheduleCondition[],
  direction: "LONG" | "SHORT",
): OrderScheduleCondition[] {
  const optional = withoutCondition(items, "DECISION_BASIS_READY");
  if (optional.length !== 1) return items;
  const condition = optional[0];
  if (!condition || condition.kind !== "PRICE_MOVE_BPS") return items;
  const isGeneratedDefault = condition.comparator === (direction === "LONG" ? "GTE" : "DROP_GTE")
    && approximatelyEqual(condition.threshold_bps, "30")
    && condition.window_seconds === 30;
  if (!isGeneratedDefault) return items;
  return normalizedDirectConditionItems(operator, []);
}

export function dynamicRuleByKind<K extends DynamicRuleKind>(
  rules: OrderScheduleDynamicRule[],
  kind: K,
): Extract<OrderScheduleDynamicRule, { kind: K }> | undefined {
  return rules.find((rule) => rule.kind === kind) as
    | Extract<OrderScheduleDynamicRule, { kind: K }>
    | undefined;
}

export function withDynamicRule(
  rules: OrderScheduleDynamicRule[],
  rule: OrderScheduleDynamicRule,
): OrderScheduleDynamicRule[] {
  const existing = rules.some((item) => item.kind === rule.kind);
  if (!existing) return [...rules, rule];
  return rules.map((item) => item.kind === rule.kind ? rule : item);
}

export function withoutDynamicRule(
  rules: OrderScheduleDynamicRule[],
  kind: DynamicRuleKind,
): OrderScheduleDynamicRule[] {
  return rules.filter((rule) => rule.kind !== kind);
}

export function localDateTimeValue(value: string | null): string {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "";
  const local = new Date(parsed.getTime() - parsed.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

export function isoFromLocalDateTime(value: string): string | null {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
}

export function previewFailureText(error: unknown): string {
  if (error instanceof ApiFailure) {
    if (error.code.startsWith("INSTRUMENT_RULES_")) {
      return "当前交易所工具规则不可用，无法形成权威预览；请稍后重试。";
    }
    return `服务端预览失败（${error.code}）。输入没有形成可执行档位。`;
  }
  return "服务端预览失败；输入没有形成可执行档位。";
}

export function createDefaultOrderScheduleSpec(
  referencePrice: string | null = null,
): OrderScheduleSpec {
  return {
    entry_program: {
      kind: "ONE_TIME",
      slice_count: 1,
      first_slice_delay_seconds: 0,
      slice_interval_seconds: 0,
    },
    price_distribution: {
      kind: "SINGLE",
      limit_price: referencePrice && isPositive(referencePrice) ? referencePrice : "",
    },
    amount_distribution: {
      mode: "FIXED",
      direction: "LOW_TO_HIGH",
      base_notional: "500",
      linear_step: "10",
      exponential_ratio: "2",
      custom_notionals: [],
    },
    venue_policy: {
      order_type: "LIMIT",
      time_in_force: "GTC",
      post_only: false,
      price_match: null,
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
      take_profit_ladder: {
        levels: [{ trigger_r: "2", quantity_fraction: "1" }],
      },
      time_exit_seconds: null,
    },
    dynamic_rules: [],
  };
}
