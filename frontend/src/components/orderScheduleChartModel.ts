import type {
  MarketInterval,
  OrderScheduleDirection,
  OrderSchedulePreviewLeg,
  OrderScheduleSpec,
} from "../api/client";
import {
  compactDecimal,
  fractionDigitsFromIncrement,
  quoteAmount,
  tradingPrice,
} from "../format";
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
    | "MARK_CONDITION"
    | "ENTRY_INVALIDATION"
    | "RUNTIME_ENTRY"
    | "POSITION"
    | "STOP_REFERENCE"
    | "PROTECTION"
    | "TAKE_PROFIT";
  label: string;
  detail: string;
  price: number;
  authority: "MARKET" | "DRAFT_INPUT" | "SERVER_PREVIEW" | "SERVER_FACT";
  lineStyle: "solid" | "dashed" | "dotted";
  draggable: boolean;
  effectiveNotional?: string;
};

export type ChartLabelAnchor = {
  id: string;
  y: number;
};

export type PriceTagAxisLayout = {
  plotEdgeX: number;
  elbowX: number;
  labelLeadX: number;
  labelX: number;
  labelAlign: "left" | "right";
};

/**
 * Keep Halpha tags on the outer edge of the configured price axis so native
 * tick text and plan tags occupy separate columns. The overlay y-axis callback
 * does not reliably expose the rendered side, so callers pass the chart's
 * configured axis position instead of inferring it from `isFromZero()`.
 */
export function priceTagAxisLayout(
  axisPosition: "left" | "right",
  width: number,
): PriceTagAxisLayout {
  const safeWidth = Math.max(0, width);
  return axisPosition === "right"
    ? {
      plotEdgeX: 0,
      elbowX: Math.min(8, safeWidth),
      labelLeadX: Math.max(0, safeWidth - 14),
      labelX: safeWidth,
      labelAlign: "right",
    }
    : {
      plotEdgeX: safeWidth,
      elbowX: Math.max(0, safeWidth - 8),
      labelLeadX: Math.min(14, safeWidth),
      labelX: 0,
      labelAlign: "left",
    };
}

export function spreadChartLabelAnchors(
  anchors: ChartLabelAnchor[],
  height: number,
  requestedGap = 22,
  requestedPadding = 11,
): ChartLabelAnchor[] {
  const safeHeight = Math.max(0, height);
  const padding = Math.min(
    Math.max(0, requestedPadding),
    safeHeight / 2,
  );
  const lowerBound = padding;
  const upperBound = Math.max(lowerBound, safeHeight - padding);
  const sorted = anchors
    .filter((anchor) => Number.isFinite(anchor.y))
    .map((anchor) => ({
      ...anchor,
      sourceY: anchor.y,
      y: Math.min(upperBound, Math.max(lowerBound, anchor.y)),
    }))
    .sort(
      (left, right) =>
        left.sourceY - right.sourceY || left.id.localeCompare(right.id),
    );
  if (sorted.length <= 1) return sorted;

  const gap = Math.min(
    Math.max(0, requestedGap),
    (upperBound - lowerBound) / (sorted.length - 1),
  );
  const positions = [sorted[0]!.y];
  for (let index = 1; index < sorted.length; index += 1) {
    positions.push(Math.max(
      sorted[index]!.y,
      positions[index - 1]! + gap,
    ));
  }

  const desiredMean = sorted.reduce((sum, anchor) => sum + anchor.y, 0)
    / sorted.length;
  const positionMean = positions.reduce((sum, position) => sum + position, 0)
    / positions.length;
  const centered = positions.map(
    (position) => position + desiredMean - positionMean,
  );
  const underflow = lowerBound - centered[0]!;
  if (underflow > 0) {
    centered.forEach((position, index) => {
      centered[index] = position + underflow;
    });
  }
  const overflow = centered.at(-1)! - upperBound;
  if (overflow > 0) {
    centered.forEach((position, index) => {
      centered[index] = position - overflow;
    });
  }

  return sorted.map((anchor, index) => ({
    id: anchor.id,
    y: centered[index]!,
  }));
}

export function groupNearbyPriceAnnotations(
  annotations: OrderChartPriceAnnotation[],
  tolerance: number,
): OrderChartPriceAnnotation[][] {
  const groups: OrderChartPriceAnnotation[][] = [];
  [...annotations]
    .sort((left, right) => left.price - right.price)
    .forEach((annotation) => {
      const group = groups.at(-1);
      const groupAnchor = group?.[0];
      const sameMeaning = groupAnchor
        && groupAnchor.role === annotation.role
        && groupAnchor.authority === annotation.authority;
      const samePrice = groupAnchor
        && Math.abs(annotation.price - groupAnchor.price)
          <= Number.EPSILON * Math.max(1, Math.abs(groupAnchor.price));
      if (
        group
        && groupAnchor
        && annotation.price - groupAnchor.price <= tolerance
        && (sameMeaning || samePrice)
      ) {
        group.push(annotation);
      } else {
        groups.push([annotation]);
      }
    });
  return groups;
}

export function selectPriceAnnotationForTag(
  group: OrderChartPriceAnnotation[],
): OrderChartPriceAnnotation | undefined {
  return group.find((annotation) => annotation.draggable)
    ?? group.find((annotation) => annotation.authority === "SERVER_FACT")
    ?? group.find((annotation) => annotation.authority === "SERVER_PREVIEW")
    ?? group[0];
}

export function priceAnnotationTagMultiplicity(
  group: OrderChartPriceAnnotation[],
  primary: OrderChartPriceAnnotation,
): number {
  return group.filter((annotation) => (
    annotation.role === primary.role
    && annotation.authority === primary.authority
  )).length;
}

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

export function summarizeRelativeRules(
  rules: OrderChartRelativeRuleAnnotation[],
): string {
  const stop = rules.find((rule) => rule.id === "halpha-initial-stop");
  const takeProfits = rules.filter((rule) => rule.id.startsWith("halpha-take-profit-"));
  const otherCount = rules.length - (stop ? 1 : 0) - takeProfits.length;
  const parts: string[] = [];

  if (stop) parts.push(stop.label);
  if (takeProfits.length > 0) {
    const triggerLabels = takeProfits.map(
      (rule) => rule.label.split("·").at(-1)?.trim() || "未填写",
    );
    parts.push(`${takeProfits.length} 级止盈 · ${triggerLabels.join("/")}`);
  }
  if (otherCount > 0) parts.push(`${otherCount} 项入场或动态规则`);

  return parts.length > 0
    ? parts.join(" · ")
    : rules.slice(0, 2).map((rule) => rule.label).join(" · ");
}

type BuildOrderScheduleChartAnnotationsInput = {
  direction: OrderScheduleDirection;
  referencePrice: string | null;
  spec: OrderScheduleSpec;
  previewLegs: OrderSchedulePreviewLeg[];
  previewState: OrderChartProjectionState;
  priceTickSize?: string | null;
};

function finitePositivePrice(value: string | null | undefined): number | null {
  if (value === null || value === undefined || !value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

export type OrderScheduleProjectedPriceBand = {
  lower: number;
  upper: number;
};

export type OrderScheduleProtectionProjection = {
  entry: OrderScheduleProjectedPriceBand;
  stop: OrderScheduleProjectedPriceBand;
  takeProfits: Array<{
    levelIndex: number;
    triggerR: number;
    price: OrderScheduleProjectedPriceBand;
  }>;
};

function priceBand(values: number[]): OrderScheduleProjectedPriceBand | null {
  const validValues = values.filter((value) => Number.isFinite(value) && value > 0);
  if (validValues.length === 0) return null;
  return {
    lower: Math.min(...validValues),
    upper: Math.max(...validValues),
  };
}

export function projectOrderScheduleProtectionPrices(
  direction: OrderScheduleDirection,
  spec: OrderScheduleSpec,
  previewLegs: OrderSchedulePreviewLeg[],
): OrderScheduleProtectionProjection | null {
  const entryPrices = previewLegs.flatMap((leg) => {
    const price = finitePositivePrice(leg.price)
      ?? finitePositivePrice(leg.sizing_price);
    return price === null ? [] : [price];
  });
  const entry = priceBand(entryPrices);
  const stopDistanceBps = Number(
    spec.protection_policy.initial_stop.distance_bps,
  );
  if (
    entry === null
    || !Number.isFinite(stopDistanceBps)
    || stopDistanceBps <= 0
  ) {
    return null;
  }

  const adverseFraction = stopDistanceBps / 10_000;
  const projectedStopPrices = entryPrices.map((entryPrice) => (
    direction === "LONG"
      ? entryPrice * (1 - adverseFraction)
      : entryPrice * (1 + adverseFraction)
  ));
  const stop = priceBand(projectedStopPrices);
  if (stop === null || stop.lower <= 0) return null;

  const takeProfits = (
    spec.protection_policy.take_profit_ladder?.levels ?? []
  ).flatMap((level, levelIndex) => {
    const triggerR = Number(level.trigger_r);
    if (!Number.isFinite(triggerR) || triggerR <= 0) return [];
    const projectedPrices = entryPrices.map((entryPrice) => {
      const movement = entryPrice * adverseFraction * triggerR;
      return direction === "LONG"
        ? entryPrice + movement
        : entryPrice - movement;
    });
    const projectedPrice = priceBand(projectedPrices);
    return projectedPrice === null || projectedPrice.lower <= 0
      ? []
      : [{ levelIndex, triggerR, price: projectedPrice }];
  });

  return { entry, stop, takeProfits };
}

function appendProjectedPriceBand(
  annotations: OrderChartPriceAnnotation[],
  input: {
    id: string;
    role: "PROTECTION" | "TAKE_PROFIT";
    label: string;
    detail: string;
    band: OrderScheduleProjectedPriceBand;
  },
): void {
  const prices = input.band.lower === input.band.upper
    ? [{ suffix: "", price: input.band.lower }]
    : [
      { suffix: "-lower", price: input.band.lower },
      { suffix: "-upper", price: input.band.upper },
    ];
  prices.forEach(({ suffix, price }) => {
    annotations.push({
      id: `${input.id}${suffix}`,
      role: input.role,
      label: input.label,
      detail: input.detail,
      price,
      authority: "SERVER_PREVIEW",
      lineStyle: "dotted",
      draggable: false,
    });
  });
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

function movementComparatorLabel(value: "GTE" | "LTE" | "DROP_GTE" | "ABS_GTE"): string {
  if (value === "GTE") return "上涨 ≥";
  if (value === "DROP_GTE") return "下跌 ≥";
  if (value === "LTE") return "有符号变动 ≤";
  return "绝对变动 ≥";
}

export function buildOrderScheduleChartAnnotations({
  direction,
  referencePrice,
  spec,
  previewLegs,
  previewState,
  priceTickSize,
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
        detail: `入场条件：MARK_PRICE ${comparator} ${tradingPrice(markCondition.price, priceTickSize)} USDT`,
        price: conditionPrice,
        authority: "DRAFT_INPUT",
        lineStyle: "dashed",
        draggable: false,
      });
    }
  }

  const closedBarCondition = spec.entry_conditions.items.find(
    (item) => item.kind === "CLOSED_BAR_PRICE_15M",
  );
  if (closedBarCondition?.kind === "CLOSED_BAR_PRICE_15M") {
    const conditionPrice = finitePositivePrice(closedBarCondition.price);
    if (conditionPrice !== null) {
      const comparator = closedBarCondition.comparator === "GTE" ? "≥" : "≤";
      priceAnnotations.push({
        id: "halpha-closed-bar-15m-condition",
        role: "MARK_CONDITION",
        label: `15m 收盘条件 ${comparator}`,
        detail: `最近完整闭合的 15m K 线收盘 ${comparator} ${tradingPrice(closedBarCondition.price, priceTickSize)} USDT；正在形成的 K 线不参与`,
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
      const effectiveNotionalDisplay = quoteAmount(leg.effective_notional);
      const rawDifference = leg.raw_price !== null && leg.raw_price !== leg.price
        ? ` · 归一化前 ${tradingPrice(leg.raw_price, priceTickSize)}`
        : "";
      priceAnnotations.push({
        id: `halpha-preview-leg-${leg.leg_index}`,
        role: "NORMALIZED_LEG",
        label: `标准化入场 ${leg.leg_index + 1}/${leg.leg_count}`,
        detail: `有效 ${effectiveNotionalDisplay} USDT${rawDifference}`,
        price: normalizedPrice,
        authority: "SERVER_PREVIEW",
        lineStyle: "dashed",
        draggable: false,
        effectiveNotional: leg.effective_notional,
      });
    });

    const protectionProjection = projectOrderScheduleProtectionPrices(
      direction,
      spec,
      previewLegs,
    );
    if (protectionProjection !== null) {
      const projectedBasis = protectionProjection.entry.lower
        === protectionProjection.entry.upper
        ? "服务端标准化入场预览价"
        : "服务端标准化入场预览区间";
      appendProjectedPriceBand(priceAnnotations, {
        id: "halpha-preview-stop",
        role: "PROTECTION",
        label: "预计止损触发价",
        detail: `按${projectedBasis}和当前止损距离估算；实际保护价按每笔确认成交计算，并以交易所工作中事实为准`,
        band: protectionProjection.stop,
      });
      protectionProjection.takeProfits.forEach((level) => {
        appendProjectedPriceBand(priceAnnotations, {
          id: `halpha-preview-take-profit-${level.levelIndex}`,
          role: "TAKE_PROFIT",
          label: `预计止盈 ${level.levelIndex + 1} · ${compactDecimal(level.triggerR)}R`,
          detail: `按${projectedBasis}、当前止损距离和 ${compactDecimal(level.triggerR)}R 估算；实际只减仓委托以每笔成交后的交易所事实为准`,
          band: level.price,
        });
      });
    }
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
        label: `价差 ≤ ${condition.maximum_bps ? compactDecimal(condition.maximum_bps) : "未填写"} bps`,
        detail: "(卖一 − 买一) ÷ 盘口中间价；随盘口变化，没有固定水平线",
        base: "TOP_OF_BOOK",
      });
    }
    if (condition.kind === "PRICE_MOVE_BPS") {
      relativeRules.push({
        id: "halpha-price-move-condition",
        label: `${condition.window_seconds}s ${movementComparatorLabel(condition.comparator)} ${condition.threshold_bps ? compactDecimal(condition.threshold_bps) : "未填写"} bps`,
        detail: "基于标记价格窗口起点动态计算，没有固定水平线",
        base: "MARK_WINDOW",
      });
    }
  });

  const stopDistance = spec.protection_policy.initial_stop.distance_bps;
  relativeRules.push({
    id: "halpha-initial-stop",
    label: `每笔成交后止损 · ${stopDistance ? compactDecimal(stopDistance) : "未填写"} bps`,
    detail: "相对每笔已确认成交价建立；只有场所确认后才是保护事实",
    base: "CONFIRMED_FILL",
  });
  spec.protection_policy.take_profit_ladder?.levels.forEach((level, index) => {
    relativeRules.push({
      id: `halpha-take-profit-${index}`,
      label: `成交后止盈 ${index + 1} · ${level.trigger_r ? compactDecimal(level.trigger_r) : "未填写"}R`,
      detail: `${level.quantity_fraction ? compactDecimal(level.quantity_fraction) : "未填写"} 仓位；相对该笔成交的初始风险计算`,
      base: "CONFIRMED_FILL",
    });
  });
  const steppedProtection = spec.dynamic_rules.find(
    (rule) => rule.kind === "STEPPED_PROTECTION",
  );
  if (steppedProtection?.kind === "STEPPED_PROTECTION") {
    steppedProtection.steps.forEach((step, index) => {
      relativeRules.push({
        id: `halpha-stepped-protection-${index}`,
        label: `移动止损 ${index + 1} · ${compactDecimal(step.trigger_r)}R → ${compactDecimal(step.stop_r)}R`,
        detail: "相对首笔确认成交的初始风险计算；先证明新止损工作，再撤销被替代止损",
        base: "CONFIRMED_FILL",
      });
    });
  }

  const shockRule = spec.dynamic_rules.find((rule) => rule.kind === "CANCEL_ON_SHOCK");
  if (shockRule?.kind === "CANCEL_ON_SHOCK") {
    const invalidationPrice = finitePositivePrice(shockRule.invalidation_price);
    if (invalidationPrice !== null) {
      priceAnnotations.push({
        id: "halpha-entry-invalidation-price",
        role: "ENTRY_INVALIDATION",
        label: direction === "LONG" ? "入场失效下界" : "入场失效上界",
        detail: direction === "LONG"
          ? "标记价跌破后永久取消本次未成交入场"
          : "标记价上破后永久取消本次未成交入场",
        price: invalidationPrice,
        authority: "DRAFT_INPUT",
        lineStyle: "dashed",
        draggable: false,
      });
    }
    const opportunityMissedPrice = finitePositivePrice(
      shockRule.opportunity_missed_price,
    );
    if (opportunityMissedPrice !== null) {
      priceAnnotations.push({
        id: "halpha-entry-opportunity-missed-price",
        role: "ENTRY_INVALIDATION",
        label: direction === "LONG" ? "做多机会错过上界" : "做空机会错过下界",
        detail: direction === "LONG"
          ? "标记价上破后永久取消本次未成交入场，避免高位追多"
          : "标记价下破后永久取消本次未成交入场，避免低位追空",
        price: opportunityMissedPrice,
        authority: "DRAFT_INPUT",
        lineStyle: "dashed",
        draggable: false,
      });
    }
    if (shockRule.window_seconds && shockRule.adverse_move_bps) {
      relativeRules.push({
        id: "halpha-shock-cancel",
        label: `不利 ${shockRule.window_seconds}s / ${compactDecimal(shockRule.adverse_move_bps)} bps 取消入场`,
        detail: direction === "LONG"
          ? "多头只把向下变动视为不利；阈值来自动态标记价窗口"
          : "空头只把向上变动视为不利；阈值来自动态标记价窗口",
        base: "MARK_WINDOW",
      });
    }
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

export function shouldBlockChartSurface(
  _displayMode: "DRAFT" | "RUNTIME",
  marketHistoryReady: boolean,
  _marketDataReady: boolean,
): boolean {
  return !marketHistoryReady;
}

export function chartPriceInput(
  value: number,
  priceTickSize?: string | null,
): string {
  const precision = fractionDigitsFromIncrement(priceTickSize) ?? 8;
  return value.toFixed(precision).replace(/(?:\.0+|(\.\d+?)0+)$/, "$1");
}

export function expandedVisiblePriceRange(
  defaultFrom: number,
  defaultTo: number,
  prices: number[],
  minimumPadding: number,
  includeAnnotations: boolean,
): [number, number] {
  if (!includeAnnotations) {
    return [defaultFrom, defaultTo];
  }
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
