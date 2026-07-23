import type {
  MarketInterval,
  OrderScheduleDirection,
  OrderSchedulePreviewLeg,
  OrderScheduleSpec,
} from "../api/client";
import type { Period } from "klinecharts";

export const ORDER_CHART_WINDOW_BAR_COUNT = 160;
export const ORDER_CHART_INTERVALS: ReadonlyArray<{
  value: MarketInterval;
  label: string;
}> = [
  { value: "1m", label: "1m" },
  { value: "5m", label: "5m" },
  { value: "15m", label: "15m" },
  { value: "1h", label: "1h" },
  { value: "4h", label: "4h" },
  { value: "1d", label: "1d" },
];

const INTERVAL_MILLISECONDS: Record<MarketInterval, number> = {
  "1m": 60_000,
  "5m": 5 * 60_000,
  "15m": 15 * 60_000,
  "1h": 60 * 60_000,
  "4h": 4 * 60 * 60_000,
  "1d": 24 * 60 * 60_000,
};

const INTERVAL_PERIODS: Record<MarketInterval, Period> = {
  "1m": { type: "minute", span: 1 },
  "5m": { type: "minute", span: 5 },
  "15m": { type: "minute", span: 15 },
  "1h": { type: "hour", span: 1 },
  "4h": { type: "hour", span: 4 },
  "1d": { type: "day", span: 1 },
};

export function chartPeriod(interval: MarketInterval): Period {
  return INTERVAL_PERIODS[interval];
}

export function marketIntervalForPeriod(period: Period): MarketInterval | null {
  return ORDER_CHART_INTERVALS.find(({ value }) => {
    const candidate = INTERVAL_PERIODS[value];
    return candidate.type === period.type && candidate.span === period.span;
  })?.value ?? null;
}

export type OrderChartProjectionState = "PENDING" | "READY" | "BLOCKED";

export type OrderChartPriceAnnotation = {
  id: string;
  role:
    | "REFERENCE"
    | "SINGLE_LIMIT"
    | "RANGE_LOWER"
    | "RANGE_UPPER"
    | "NORMALIZED_LEG"
    | "MARK_CONDITION";
  label: string;
  detail: string;
  price: number;
  authority: "MARKET" | "DRAFT_INPUT" | "SERVER_PREVIEW";
  lineStyle: "solid" | "dashed" | "dotted";
  draggable: boolean;
};

export type OrderChartRelativeRuleAnnotation = {
  id: string;
  label: string;
  detail: string;
  base: "VENUE_DECIDES" | "TOP_OF_BOOK" | "MARK_WINDOW" | "CONFIRMED_FILL";
};

export type OrderScheduleChartAnnotations = {
  priceAnnotations: OrderChartPriceAnnotation[];
  relativeRules: OrderChartRelativeRuleAnnotation[];
};

type BuildOrderScheduleChartAnnotationsInput = {
  direction: OrderScheduleDirection;
  referencePrice: string | null;
  spec: OrderScheduleSpec;
  previewLegs: OrderSchedulePreviewLeg[];
  previewState: OrderChartProjectionState;
};

function finitePositivePrice(value: string | null | undefined): number | null {
  if (value === null || value === undefined || !value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function priceMatchLabel(value: OrderScheduleSpec["venue_policy"]["price_match"]): string {
  const labels = {
    OPPONENT: "对手价",
    OPPONENT_5: "对手价 5 档",
    OPPONENT_10: "对手价 10 档",
    OPPONENT_20: "对手价 20 档",
    QUEUE: "同向队列价",
    QUEUE_5: "同向队列 5 档",
    QUEUE_10: "同向队列 10 档",
    QUEUE_20: "同向队列 20 档",
  } as const;
  return value === null ? "未使用" : labels[value];
}

function movementComparatorLabel(value: "GTE" | "LTE" | "ABS_GTE"): string {
  if (value === "GTE") return "上涨 ≥";
  if (value === "LTE") return "下跌 ≤";
  return "绝对变动 ≥";
}

export function buildOrderScheduleChartAnnotations({
  direction,
  referencePrice,
  spec,
  previewLegs,
  previewState,
}: BuildOrderScheduleChartAnnotationsInput): OrderScheduleChartAnnotations {
  const priceAnnotations: OrderChartPriceAnnotation[] = [];
  const relativeRules: OrderChartRelativeRuleAnnotation[] = [];
  const reference = finitePositivePrice(referencePrice);
  if (reference !== null) {
    priceAnnotations.push({
      id: "halpha-market-reference",
      role: "REFERENCE",
      label: "当前计量参考价",
      detail: "公开行情输入；用于预览计量，不是成交承诺",
      price: reference,
      authority: "MARKET",
      lineStyle: "dotted",
      draggable: false,
    });
  }

  const pricePlan = spec.price_distribution;
  if (
    pricePlan.kind === "SINGLE"
    && spec.venue_policy.order_type === "LIMIT"
    && spec.venue_policy.price_match === null
  ) {
    const limitPrice = finitePositivePrice(pricePlan.limit_price);
    if (limitPrice !== null) {
      priceAnnotations.push({
        id: "halpha-single-limit",
        role: "SINGLE_LIMIT",
        label: "输入限价",
        detail: "计划草稿；桌面可拖动，松开后重新请求服务端预览",
        price: limitPrice,
        authority: "DRAFT_INPUT",
        lineStyle: "solid",
        draggable: true,
      });
    }
  } else if (pricePlan.kind === "LADDER") {
    const lower = finitePositivePrice(pricePlan.lower_price);
    const upper = finitePositivePrice(pricePlan.upper_price);
    if (lower !== null) {
      priceAnnotations.push({
        id: "halpha-range-lower",
        role: "RANGE_LOWER",
        label: "区间下限",
        detail: "计划草稿；桌面可拖动",
        price: lower,
        authority: "DRAFT_INPUT",
        lineStyle: "solid",
        draggable: true,
      });
    }
    if (upper !== null) {
      priceAnnotations.push({
        id: "halpha-range-upper",
        role: "RANGE_UPPER",
        label: "区间上限",
        detail: "计划草稿；桌面可拖动",
        price: upper,
        authority: "DRAFT_INPUT",
        lineStyle: "solid",
        draggable: true,
      });
    }
  }

  const markCondition = spec.entry_conditions.items.find(
    (item) => item.kind === "MARK_PRICE",
  );
  if (markCondition?.kind === "MARK_PRICE") {
    const conditionPrice = finitePositivePrice(markCondition.price);
    if (conditionPrice !== null) {
      const comparator = markCondition.comparator === "GTE" ? "≥" : "≤";
      priceAnnotations.push({
        id: "halpha-mark-condition",
        role: "MARK_CONDITION",
        label: `标记价条件 ${comparator}`,
        detail: `入场条件：MARK_PRICE ${comparator} ${markCondition.price} USDT`,
        price: conditionPrice,
        authority: "DRAFT_INPUT",
        lineStyle: "dashed",
        draggable: false,
      });
    }
  }

  if (previewState === "READY") {
    previewLegs.forEach((leg) => {
      const normalizedPrice = finitePositivePrice(leg.price);
      if (normalizedPrice === null) return;
      const rawDifference = leg.raw_price !== null && leg.raw_price !== leg.price
        ? ` · 输入 ${leg.raw_price}`
        : "";
      priceAnnotations.push({
        id: `halpha-preview-leg-${leg.leg_index}`,
        role: "NORMALIZED_LEG",
        label: `标准化入场 ${leg.leg_index + 1}/${leg.leg_count}`,
        detail: `${leg.price} USDT · 有效 ${leg.effective_notional} USDT${rawDifference}`,
        price: normalizedPrice,
        authority: "SERVER_PREVIEW",
        lineStyle: "dashed",
        draggable: false,
      });
    });
  }

  if (spec.venue_policy.order_type === "MARKET") {
    relativeRules.push({
      id: "halpha-market-order-price",
      label: "市价单 · 成交价未知",
      detail: "图中的参考价只用于数量计量；实际成交价由场所决定",
      base: "VENUE_DECIDES",
    });
  } else if (spec.venue_policy.price_match !== null) {
    relativeRules.push({
      id: "halpha-price-match",
      label: `priceMatch · ${priceMatchLabel(spec.venue_policy.price_match)}`,
      detail: "实际委托价由场所决定；不伪造固定价格线",
      base: "VENUE_DECIDES",
    });
  }

  spec.entry_conditions.items.forEach((condition) => {
    if (condition.kind === "SPREAD_BPS") {
      relativeRules.push({
        id: "halpha-spread-condition",
        label: `价差 ≤ ${condition.maximum_bps || "未填写"} bps`,
        detail: "(卖一 − 买一) ÷ 盘口中间价；随盘口变化，没有固定水平线",
        base: "TOP_OF_BOOK",
      });
    }
    if (condition.kind === "PRICE_MOVE_BPS") {
      relativeRules.push({
        id: "halpha-price-move-condition",
        label: `${condition.window_seconds}s ${movementComparatorLabel(condition.comparator)} ${condition.threshold_bps || "未填写"} bps`,
        detail: "基于标记价格窗口起点动态计算，没有固定水平线",
        base: "MARK_WINDOW",
      });
    }
  });

  const stopDistance = spec.protection_policy.initial_stop.distance_bps;
  relativeRules.push({
    id: "halpha-initial-stop",
    label: `每笔成交后止损 · ${stopDistance || "未填写"} bps`,
    detail: "相对每笔已确认成交价建立；只有场所确认后才是保护事实",
    base: "CONFIRMED_FILL",
  });
  spec.protection_policy.take_profit_ladder?.levels.forEach((level, index) => {
    relativeRules.push({
      id: `halpha-take-profit-${index}`,
      label: `成交后止盈 ${index + 1} · ${level.trigger_r || "未填写"}R`,
      detail: `${level.quantity_fraction || "未填写"} 仓位；相对该笔成交的初始风险计算`,
      base: "CONFIRMED_FILL",
    });
  });

  const shockRule = spec.dynamic_rules.find((rule) => rule.kind === "CANCEL_ON_SHOCK");
  if (shockRule?.kind === "CANCEL_ON_SHOCK") {
    relativeRules.push({
      id: "halpha-shock-cancel",
      label: `不利 ${shockRule.window_seconds}s / ${shockRule.adverse_move_bps || "未填写"} bps 撤余单`,
      detail: direction === "LONG"
        ? "多头只把向下变动视为不利；阈值来自动态标记价窗口"
        : "空头只把向上变动视为不利；阈值来自动态标记价窗口",
      base: "MARK_WINDOW",
    });
  }

  return { priceAnnotations, relativeRules };
}

export function orderedPriceRange(first: number, second: number): [number, number] {
  return first <= second ? [first, second] : [second, first];
}

export function marketWindowBounds(
  sourceCutoff: string,
  interval: MarketInterval,
  barCount = ORDER_CHART_WINDOW_BAR_COUNT,
): { startAt: string; endAt: string } | null {
  const cutoff = Date.parse(sourceCutoff);
  if (!Number.isFinite(cutoff) || barCount < 2) return null;
  const intervalMilliseconds = INTERVAL_MILLISECONDS[interval];
  const endOpen = Math.floor(cutoff / intervalMilliseconds) * intervalMilliseconds
    - intervalMilliseconds;
  const startOpen = endOpen - (barCount - 1) * intervalMilliseconds;
  return {
    startAt: new Date(startOpen).toISOString(),
    endAt: new Date(endOpen).toISOString(),
  };
}

export function chartPriceInput(value: number): string {
  return value.toFixed(8).replace(/(?:\.0+|(\.\d+?)0+)$/, "$1");
}

export function expandedVisiblePriceRange(
  defaultFrom: number,
  defaultTo: number,
  prices: number[],
  minimumPadding: number,
): [number, number] {
  const validPrices = prices.filter((price) => Number.isFinite(price) && price > 0);
  if (
    validPrices.length === 0
    || !Number.isFinite(defaultFrom)
    || !Number.isFinite(defaultTo)
    || defaultTo <= defaultFrom
  ) {
    return [defaultFrom, defaultTo];
  }
  const from = Math.min(defaultFrom, ...validPrices);
  const to = Math.max(defaultTo, ...validPrices);
  if (from === defaultFrom && to === defaultTo) {
    return [defaultFrom, defaultTo];
  }
  const padding = Math.max((to - from) * 0.04, minimumPadding);
  return [Math.max(0, from - padding), to + padding];
}
