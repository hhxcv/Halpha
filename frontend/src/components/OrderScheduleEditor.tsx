import { useEffect, useState, type ReactNode } from "react";
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  FormControlLabel,
  LinearProgress,
  MenuItem,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from "@mui/material";
import { useQuery } from "@tanstack/react-query";

import {
  ApiFailure,
  previewOrderSchedule,
  type MarketInterval,
  type OrderScheduleCondition,
  type OrderScheduleDirection,
  type OrderScheduleDynamicRule,
  type OrderSchedulePriceMatch,
  type OrderScheduleSpec,
} from "../api/client";
import { formatUserVisibleTime, shortDigest } from "../format";
import type { MarketColorScheme } from "../marketColors";
import type {
  MarketStreamBar,
  MarketStreamClientStatus,
} from "../marketStream";
import { surfaceFrameSx } from "../theme";
import OrderScheduleChart from "./OrderScheduleChart";

export type OrderScheduleEditorProps = {
  value: OrderScheduleSpec;
  onChange: (value: OrderScheduleSpec) => void;
  environmentId: string;
  environmentKind: string;
  instrumentRef: string;
  direction: OrderScheduleDirection;
  maxNotional: string;
  referencePrice: string | null;
  liveReferencePrice?: string | null;
  chartInterval: MarketInterval;
  onChartIntervalChange: (interval: MarketInterval) => void;
  liveBar: MarketStreamBar | null;
  streamStatus: MarketStreamClientStatus;
  streamGeneration: number;
  marketProjectionReady: boolean;
  marketColorScheme: MarketColorScheme;
  scheduleRef: string;
  bidPrice?: string | null;
  askPrice?: string | null;
  workspaceHeader?: ReactNode;
  leadingControls?: ReactNode;
  planOptions?: ReactNode;
  footerControls?: ReactNode;
  onValidationChange?: (ready: boolean) => void;
};

type ConditionKind = OrderScheduleCondition["kind"];
type DynamicRuleKind = OrderScheduleDynamicRule["kind"];

const fieldGridSx = {
  display: "grid",
  gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0, 1fr))" },
  gap: 1.5,
} as const;

const compactFieldGridSx = {
  display: "grid",
  gridTemplateColumns: { xs: "1fr", sm: "repeat(3, minmax(0, 1fr))" },
  gap: 1.25,
} as const;

const priceMatchOptions: ReadonlyArray<{
  value: OrderSchedulePriceMatch;
  label: string;
}> = [
  { value: "OPPONENT", label: "对手价" },
  { value: "OPPONENT_5", label: "对手价 5 档" },
  { value: "OPPONENT_10", label: "对手价 10 档" },
  { value: "OPPONENT_20", label: "对手价 20 档" },
  { value: "QUEUE", label: "同向队列价" },
  { value: "QUEUE_5", label: "同向队列 5 档" },
  { value: "QUEUE_10", label: "同向队列 10 档" },
  { value: "QUEUE_20", label: "同向队列 20 档" },
];

const issueLabels: Record<string, string> = {
  GTD_EXPIRY_TOO_SOON: "GTD 到期时间距离场所事实截止点不足 10 分钟。",
  ORDER_SCHEDULE_PRICE_COLLISION: "按价格步进标准化后出现重合档位。",
  ORDER_SCHEDULE_REFERENCE_PRICE_REQUIRED: "市价单或 priceMatch 需要当前参考价格。",
  ORDER_SCHEDULE_TOTAL_EXCEEDS_PLAN_LIMIT: "请求总额超过计划交易金额。",
  ORDER_SCHEDULE_PRICE_OUTSIDE_VENUE_LIMIT: "档位价格超出交易所允许范围。",
  ORDER_SCHEDULE_QUANTITY_BELOW_MINIMUM: "标准化数量低于交易所最小数量。",
  ORDER_SCHEDULE_QUANTITY_ABOVE_MAXIMUM: "标准化数量超过交易所最大数量。",
  ORDER_SCHEDULE_NOTIONAL_BELOW_MINIMUM: "标准化后名义金额低于交易所最小金额。",
};

function EditorSection({
  id,
  title,
  description,
  collapsible = false,
  summary,
  children,
}: {
  id: string;
  title: string;
  description?: string;
  collapsible?: boolean;
  summary?: ReactNode;
  children: ReactNode;
}) {
  if (collapsible) {
    return (
      <Box
        component="details"
        sx={{
          borderBottom: 1,
          borderColor: "divider",
          "&[open] > summary": { bgcolor: "action.hover" },
        }}
      >
        <Box
          component="summary"
          sx={{
            minHeight: 44,
            px: 1.5,
            py: 1.1,
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: 1,
            listStyle: "none",
            "&::-webkit-details-marker": { display: "none" },
            "&::after": {
              content: '"⌄"',
              color: "text.secondary",
              fontSize: 18,
              lineHeight: 1,
              transition: "transform 120ms ease",
            },
            "details[open] > &::after": { transform: "rotate(180deg)" },
          }}
        >
          <Box sx={{ minWidth: 0 }}>
            <Typography id={id} component="h2" variant="subtitle2">{title}</Typography>
            {summary ? (
              <Typography
                component="div"
                variant="caption"
                color="text.secondary"
                noWrap
                sx={{ mt: .15 }}
              >
                {summary}
              </Typography>
            ) : null}
          </Box>
        </Box>
        <Box component="section" aria-labelledby={id} sx={{ px: 1.5, pt: 1.25, pb: 1.5 }}>
          {description ? (
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1.25 }}>
              {description}
            </Typography>
          ) : null}
          {children}
        </Box>
      </Box>
    );
  }
  return (
    <Box
      component="section"
      aria-labelledby={id}
      sx={{ px: 1.5, py: 1.35, borderBottom: 1, borderColor: "divider" }}
    >
      <Typography id={id} component="h2" variant="subtitle2">{title}</Typography>
      {description ? (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: .35, mb: 1.25 }}>
          {description}
        </Typography>
      ) : null}
      <Box sx={{ mt: description ? 0 : 1.25 }}>
        {children}
      </Box>
    </Box>
  );
}

function finiteNumber(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function compactDecimal(value: string, maxFractionDigits = 8): string {
  const match = value.trim().match(/^([+-]?\d+)(?:\.(\d+))?$/);
  if (!match) return value;
  const integer = match[1] ?? "0";
  const fraction = match[2] ?? "";
  const visibleFraction = fraction.slice(0, maxFractionDigits).replace(/0+$/, "");
  const display = visibleFraction ? `${integer}.${visibleFraction}` : integer;
  return fraction.length > maxFractionDigits ? `${display}…` : display;
}

function isPositive(value: string): boolean {
  const parsed = finiteNumber(value);
  return parsed !== null && parsed > 0;
}

function isNonNegative(value: string): boolean {
  const parsed = finiteNumber(value);
  return parsed !== null && parsed >= 0;
}

function evenlyDividedNotional(total: string, count: number): string | null {
  const parsed = finiteNumber(total);
  if (parsed === null || parsed <= 0 || !Number.isInteger(count) || count <= 0) return null;
  return String(Number((parsed / count).toFixed(8)));
}

function approximatelyEqual(left: string, right: string): boolean {
  const leftValue = finiteNumber(left);
  const rightValue = finiteNumber(right);
  if (leftValue === null || rightValue === null) return false;
  return Math.abs(leftValue - rightValue) <= Math.max(1, Math.abs(rightValue)) * 1e-9;
}

function resized(values: string[], count: number, fallback: string): string[] {
  return Array.from({ length: count }, (_, index) => values[index] ?? fallback);
}

function replaceAt(values: string[], index: number, nextValue: string): string[] {
  return values.map((value, currentIndex) => currentIndex === index ? nextValue : value);
}

function conditionByKind<K extends ConditionKind>(
  items: OrderScheduleCondition[],
  kind: K,
): Extract<OrderScheduleCondition, { kind: K }> | undefined {
  return items.find((item) => item.kind === kind) as
    | Extract<OrderScheduleCondition, { kind: K }>
    | undefined;
}

function withCondition(
  items: OrderScheduleCondition[],
  condition: OrderScheduleCondition,
): OrderScheduleCondition[] {
  const existing = items.some((item) => item.kind === condition.kind);
  if (!existing) return [...items, condition];
  return items.map((item) => item.kind === condition.kind ? condition : item);
}

function withoutCondition(
  items: OrderScheduleCondition[],
  kind: ConditionKind,
): OrderScheduleCondition[] {
  return items.filter((item) => item.kind !== kind);
}

const directReadyCondition: OrderScheduleCondition = { kind: "DECISION_BASIS_READY" };

function normalizedDirectConditionItems(
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

function dynamicRuleByKind<K extends DynamicRuleKind>(
  rules: OrderScheduleDynamicRule[],
  kind: K,
): Extract<OrderScheduleDynamicRule, { kind: K }> | undefined {
  return rules.find((rule) => rule.kind === kind) as
    | Extract<OrderScheduleDynamicRule, { kind: K }>
    | undefined;
}

function withDynamicRule(
  rules: OrderScheduleDynamicRule[],
  rule: OrderScheduleDynamicRule,
): OrderScheduleDynamicRule[] {
  const existing = rules.some((item) => item.kind === rule.kind);
  if (!existing) return [...rules, rule];
  return rules.map((item) => item.kind === rule.kind ? rule : item);
}

function withoutDynamicRule(
  rules: OrderScheduleDynamicRule[],
  kind: DynamicRuleKind,
): OrderScheduleDynamicRule[] {
  return rules.filter((rule) => rule.kind !== kind);
}

function localDateTimeValue(value: string | null): string {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "";
  const local = new Date(parsed.getTime() - parsed.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function isoFromLocalDateTime(value: string): string | null {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
}

function previewFailureText(error: unknown): string {
  if (error instanceof ApiFailure) {
    if (error.code.startsWith("INSTRUMENT_RULES_")) {
      return "当前交易所工具规则不可用，无法形成权威预览；请稍后重试。";
    }
    return `服务端预览失败（${error.code}）。输入没有形成可执行档位。`;
  }
  return "服务端预览失败；输入没有形成可执行档位。";
}

function localProblems(
  spec: OrderScheduleSpec,
  instrumentRef: string,
  maxNotional: string,
  referencePrice: string | null,
  scheduleRef: string,
): string[] {
  const problems: string[] = [];
  if (!instrumentRef.trim()) problems.push("缺少交易对象。 ");
  if (!scheduleRef.trim()) problems.push("缺少订单计划标识。 ");
  if (!isPositive(maxNotional)) problems.push("计划交易金额必须大于 0。 ");

  const price = spec.price_distribution;
  const venue = spec.venue_policy;
  if (price.kind === "SINGLE") {
    if (venue.order_type === "MARKET") {
      if (price.limit_price !== null) problems.push("市价单不能设置限价。 ");
    } else if ((price.limit_price === null) === (venue.price_match === null)) {
      problems.push("单笔限价单必须在显式价格与 priceMatch 中二选一。 ");
    } else if (price.limit_price !== null && !isPositive(price.limit_price)) {
      problems.push("限价必须大于 0。 ");
    }
  } else {
    const lower = finiteNumber(price.lower_price);
    const upper = finiteNumber(price.upper_price);
    if (lower === null || lower <= 0 || upper === null || upper <= lower) {
      problems.push("区间上限必须大于下限，且两者都大于 0。 ");
    }
    if (!Number.isInteger(price.level_count) || price.level_count < 2 || price.level_count > 50) {
      problems.push("价格切分数量必须为 2–50 的整数。 ");
    }
    const gapCount = Number.isInteger(price.level_count)
      && price.level_count >= 2
      && price.level_count <= 50
      ? price.level_count - 1
      : 0;
    if (price.spacing_mode === "LINEAR") {
      const start = finiteNumber(price.linear_start_weight);
      const step = finiteNumber(price.linear_step);
      if (
        start === null
        || start <= 0
        || step === null
        || Array.from({ length: gapCount }, (_, index) => start + step * index)
          .some((weight) => weight <= 0)
      ) {
        problems.push("线性间距的每个权重都必须大于 0。 ");
      }
    }
    if (
      price.spacing_mode === "GEOMETRIC"
      && (!isPositive(price.geometric_ratio)
        || Number(price.geometric_ratio) <= 1
        || Number(price.geometric_ratio) > 100)
    ) {
      problems.push("指数间距比例必须大于 1 且不超过 100。 ");
    }
    if (
      price.spacing_mode === "CUSTOM_WEIGHTS"
      && (price.custom_gap_weights.length !== gapCount
        || price.custom_gap_weights.some((weight) => !isPositive(weight)))
    ) {
      problems.push(`自定义间距必须填写 ${gapCount} 个正权重。 `);
    }
    if (venue.order_type !== "LIMIT" || venue.price_match !== null) {
      problems.push("区间档位只支持显式限价。 ");
    }
  }

  const amount = spec.amount_distribution;
  const legCount = price.kind === "SINGLE" ? 1 : price.level_count;
  if (!isPositive(amount.base_notional)) problems.push("基础下单额必须大于 0。 ");
  if (amount.mode === "LINEAR" && !isNonNegative(amount.linear_step)) {
    problems.push("线性下单额步长不能为负。 ");
  }
  if (
    amount.mode === "EXPONENTIAL"
    && (!isPositive(amount.exponential_ratio)
      || Number(amount.exponential_ratio) <= 1
      || Number(amount.exponential_ratio) > 100)
  ) {
    problems.push("指数下单额比例必须大于 1 且不超过 100。 ");
  }
  if (
    amount.mode === "CUSTOM"
    && (amount.custom_notionals.length !== legCount
      || amount.custom_notionals.some((notional) => !isPositive(notional)))
  ) {
    problems.push(`自定义下单额必须填写 ${legCount} 个正数。 `);
  }
  if (price.kind === "SINGLE" && amount.mode !== "FIXED") {
    problems.push("单笔订单只支持固定下单额。 ");
  }

  if (venue.order_type === "MARKET") {
    if (
      venue.time_in_force !== null
      || venue.post_only
      || venue.price_match !== null
      || venue.expire_at !== null
    ) {
      problems.push("市价单不能设置有效方式、maker-only、priceMatch 或到期时间。 ");
    }
  } else {
    if (venue.time_in_force === null) problems.push("限价单必须选择有效方式。 ");
    if (venue.post_only && venue.time_in_force !== "GTC") {
      problems.push("maker-only 只支持 GTC。 ");
    }
    if (venue.post_only && venue.price_match !== null) {
      problems.push("maker-only 与 priceMatch 不能同时使用。 ");
    }
    if (venue.time_in_force === "GTD" && venue.expire_at === null) {
      problems.push("GTD 必须设置带时区的到期时间。 ");
    }
    if (venue.time_in_force !== "GTD" && venue.expire_at !== null) {
      problems.push("只有 GTD 可以设置到期时间。 ");
    }
  }
  if (
    (venue.order_type === "MARKET" || venue.price_match !== null)
    && (referencePrice === null || !isPositive(referencePrice))
  ) {
    problems.push("市价单或 priceMatch 缺少当前参考价格。 ");
  }

  const conditions = spec.entry_conditions.items;
  const hasDirectReady = Boolean(conditionByKind(conditions, "DECISION_BASIS_READY"));
  const optionalConditionCount = conditions.filter(
    (condition) => condition.kind !== "DECISION_BASIS_READY",
  ).length;
  if (spec.entry_conditions.operator === "ALL" && !hasDirectReady) {
    problems.push("ALL 必须包含直接执行准备条件。 ");
  }
  if (
    spec.entry_conditions.operator === "ANY"
    && hasDirectReady
    && optionalConditionCount > 0
  ) {
    problems.push("ANY 不能把恒真的直接执行准备与市场条件并列。 ");
  }
  const mark = conditionByKind(conditions, "MARK_PRICE");
  if (mark && !isPositive(mark.price)) problems.push("标记价格条件必须大于 0。 ");
  const spread = conditionByKind(conditions, "SPREAD_BPS");
  if (spread && !isNonNegative(spread.maximum_bps)) {
    problems.push("最大价差不能为负。 ");
  }
  const move = conditionByKind(conditions, "PRICE_MOVE_BPS");
  if (
    move
    && (!isPositive(move.threshold_bps)
      || !Number.isInteger(move.window_seconds)
      || move.window_seconds < 1
      || move.window_seconds > 300)
  ) {
    problems.push("短时变动条件需要 1–300 秒窗口和正阈值。 ");
  }

  const protection = spec.protection_policy;
  const stopDistance = finiteNumber(protection.initial_stop.distance_bps);
  if (stopDistance === null || stopDistance <= 0 || stopDistance > 5_000) {
    problems.push("初始止损距离必须大于 0 且不超过 5000 bps。 ");
  }
  const takeProfits = protection.take_profit_ladder?.levels ?? [];
  if (protection.take_profit_ladder !== null) {
    const triggers = takeProfits.map((level) => finiteNumber(level.trigger_r));
    const fractions = takeProfits.map((level) => finiteNumber(level.quantity_fraction));
    if (takeProfits.length !== 1 || fractions[0] !== 1) {
      problems.push("当前直接执行只支持单级、100% 成交量止盈。 ");
    }
    if (triggers.some((trigger) => trigger === null || trigger <= 0)) {
      problems.push("止盈目标 R 必须大于 0。 ");
    }
    if (fractions.some((fraction) => fraction === null || fraction <= 0 || fraction > 1)) {
      problems.push("止盈比例必须为 1。 ");
    }
  }
  if (
    protection.time_exit_seconds !== null
    && (!Number.isInteger(protection.time_exit_seconds)
      || protection.time_exit_seconds < 1
      || protection.time_exit_seconds > 2_592_000)
  ) {
    problems.push("时间退出必须为 1–2592000 秒。 ");
  }

  const expiry = dynamicRuleByKind(spec.dynamic_rules, "EXPIRE_REMAINING");
  if (
    expiry
    && (!Number.isInteger(expiry.after_seconds)
      || expiry.after_seconds < 1
      || expiry.after_seconds > 604_800)
  ) {
    problems.push("撤销未成交余量的等待时间必须为 1–604800 秒。 ");
  }
  const shock = dynamicRuleByKind(spec.dynamic_rules, "CANCEL_ON_SHOCK");
  if (
    shock
    && (!Number.isInteger(shock.window_seconds)
      || shock.window_seconds < 1
      || shock.window_seconds > 300
      || !isPositive(shock.adverse_move_bps)
      || shock.max_triggers !== 1)
  ) {
    problems.push("异动撤单需要 1–300 秒窗口、正阈值；当前仅支持触发一次。 ");
  }
  if ((expiry || shock) && venue.order_type !== "LIMIT") {
    problems.push("动态撤余单规则只适用于限价单。 ");
  }
  return [...new Set(problems.map((problem) => problem.trim()))];
}

export function createDefaultOrderScheduleSpec(
  referencePrice: string | null = null,
): OrderScheduleSpec {
  return {
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

export default function OrderScheduleEditor({
  value,
  onChange,
  environmentId,
  environmentKind,
  instrumentRef,
  direction,
  maxNotional,
  referencePrice,
  liveReferencePrice,
  chartInterval,
  onChartIntervalChange,
  liveBar,
  streamStatus,
  streamGeneration,
  marketProjectionReady,
  marketColorScheme,
  scheduleRef,
  bidPrice,
  askPrice,
  workspaceHeader,
  leadingControls,
  planOptions,
  footerControls,
  onValidationChange,
}: OrderScheduleEditorProps) {
  const environmentScope = `${environmentKind}:${environmentId}`;
  const price = value.price_distribution;
  const amount = value.amount_distribution;
  const venue = value.venue_policy;
  const markCondition = conditionByKind(value.entry_conditions.items, "MARK_PRICE");
  const spreadCondition = conditionByKind(value.entry_conditions.items, "SPREAD_BPS");
  const moveCondition = conditionByKind(value.entry_conditions.items, "PRICE_MOVE_BPS");
  const expireRule = dynamicRuleByKind(value.dynamic_rules, "EXPIRE_REMAINING");
  const shockRule = dynamicRuleByKind(value.dynamic_rules, "CANCEL_ON_SHOCK");
  const takeProfitLevels = value.protection_policy.take_profit_ladder?.levels ?? [];
  const localValidation = localProblems(
    value,
    instrumentRef,
    maxNotional,
    referencePrice,
    scheduleRef,
  );
  const [deferredValue, setDeferredValue] = useState(value);
  useEffect(() => {
    if (deferredValue === value) return undefined;
    const timeout = window.setTimeout(() => setDeferredValue(value), 180);
    return () => window.clearTimeout(timeout);
  }, [deferredValue, value]);
  const previewStale = deferredValue !== value;
  const deferredValidation = localProblems(
    deferredValue,
    instrumentRef,
    maxNotional,
    referencePrice,
    scheduleRef,
  );
  const preview = useQuery({
    queryKey: [
      "order-schedule-preview",
      environmentScope,
      scheduleRef,
      instrumentRef,
      direction,
      maxNotional,
      referencePrice,
      deferredValue,
    ],
    queryFn: () => previewOrderSchedule({
      decision_basis_kind: "DIRECT_EXECUTION",
      schedule_ref: scheduleRef,
      venue_ref: "BINANCE_USDM",
      instrument_ref: instrumentRef,
      direction,
      max_notional: maxNotional,
      reference_price: referencePrice,
      spec: deferredValue,
    }),
    enabled: marketProjectionReady && deferredValidation.length === 0,
    retry: false,
  });
  const previewReady = localValidation.length === 0
    && !previewStale
    && !preview.isFetching
    && preview.isSuccess
    && preview.data.valid;

  useEffect(() => {
    onValidationChange?.(previewReady);
  }, [onValidationChange, previewReady]);

  const changePriceKind = (kind: "SINGLE" | "LADDER") => {
    if (kind === "SINGLE") {
      const candidate = price.kind === "LADDER" ? price.lower_price : price.limit_price;
      const ladderWasAutoDivided = price.kind === "LADDER"
        && amount.mode === "FIXED"
        && approximatelyEqual(
          String((finiteNumber(amount.base_notional) ?? 0) * price.level_count),
          maxNotional,
        );
      onChange({
        ...value,
        price_distribution: {
          kind: "SINGLE",
          limit_price: candidate || referencePrice || "",
        },
        amount_distribution: {
          ...amount,
          mode: "FIXED",
          base_notional: ladderWasAutoDivided ? maxNotional : amount.base_notional,
          custom_notionals: [],
        },
      });
      return;
    }
    const candidate = price.kind === "SINGLE" ? price.limit_price : price.lower_price;
    const dividedNotional = amount.mode === "FIXED"
      && approximatelyEqual(amount.base_notional, maxNotional)
      ? evenlyDividedNotional(maxNotional, 5)
      : null;
    onChange({
      ...value,
      price_distribution: {
        kind: "LADDER",
        lower_price: candidate || referencePrice || "",
        upper_price: "",
        level_count: 5,
        spacing_mode: "EQUAL",
        spacing_direction: "LOW_TO_HIGH",
        linear_start_weight: "1",
        linear_step: "1",
        geometric_ratio: "2",
        custom_gap_weights: [],
      },
      venue_policy: {
        ...venue,
        order_type: "LIMIT",
        time_in_force: "GTC",
        price_match: null,
        expire_at: null,
      },
      amount_distribution: {
        ...amount,
        mode: "FIXED",
        base_notional: dividedNotional ?? amount.base_notional,
        custom_notionals: [],
      },
    });
  };

  const changeOrderType = (orderType: "MARKET" | "LIMIT") => {
    if (orderType === "MARKET") {
      onChange({
        ...value,
        price_distribution: { kind: "SINGLE", limit_price: null },
        amount_distribution: amount.mode === "FIXED" ? {
          ...amount,
          base_notional: approximatelyEqual(amount.base_notional, maxNotional)
            ? maxNotional
            : amount.base_notional,
        } : {
          ...amount,
          mode: "FIXED",
          base_notional: maxNotional,
          custom_notionals: [],
        },
        venue_policy: {
          order_type: "MARKET",
          time_in_force: null,
          post_only: false,
          price_match: null,
          display_quantity: null,
          expire_at: null,
        },
        dynamic_rules: [],
      });
      return;
    }
    onChange({
      ...value,
      price_distribution: price.kind === "SINGLE"
        ? { ...price, limit_price: price.limit_price ?? referencePrice ?? "" }
        : price,
      venue_policy: {
        ...venue,
        order_type: "LIMIT",
        time_in_force: "GTC",
        expire_at: null,
      },
    });
  };

  const setConditionEnabled = (kind: Exclude<ConditionKind, "DECISION_BASIS_READY">, enabled: boolean) => {
    let condition: OrderScheduleCondition;
    if (kind === "MARK_PRICE") {
      condition = { kind, comparator: "GTE", price: referencePrice ?? "" };
    } else if (kind === "SPREAD_BPS") {
      condition = { kind, maximum_bps: "10" };
    } else {
      condition = { kind, comparator: "ABS_GTE", threshold_bps: "30", window_seconds: 30 };
    }
    const items = enabled
      ? withCondition(value.entry_conditions.items, condition)
      : withoutCondition(value.entry_conditions.items, kind);
    onChange({
      ...value,
      entry_conditions: {
        ...value.entry_conditions,
        items: normalizedDirectConditionItems(
          value.entry_conditions.operator,
          items,
        ),
      },
    });
  };

  const priceMode = venue.order_type === "MARKET"
    ? "MARKET"
    : price.kind === "LADDER" ? "LADDER" : "LIMIT";
  const marketConditionCount = value.entry_conditions.items.filter(
    (item) => item.kind !== "DECISION_BASIS_READY",
  ).length;
  const conditionSummary = marketConditionCount === 0
    ? "立即执行；事实未知时仍会阻断新增风险"
    : `${value.entry_conditions.operator === "ANY" ? "任一" : "全部"}满足 · ${marketConditionCount} 个市场条件`;
  const dynamicSummary = value.dynamic_rules.length === 0
    ? "未启用"
    : value.dynamic_rules.map((rule) => rule.kind === "EXPIRE_REMAINING"
      ? `首档提交后 ${rule.after_seconds}s 到期`
      : `${rule.window_seconds}s / ${rule.adverse_move_bps}bps 不利异动`).join(" · ");
  const venueSummary = [
    venue.post_only ? "Maker only" : "",
    venue.time_in_force ?? "市价",
    value.submission_order === "HIGH_TO_LOW" ? "高→低" : "低→高",
  ].filter(Boolean).join(" · ");
  const protectionSummary = [
    `止损 ${value.protection_policy.initial_stop.distance_bps} bps`,
    value.protection_policy.take_profit_ladder ? "已启用止盈" : "",
    value.protection_policy.time_exit_seconds !== null
      ? `${value.protection_policy.time_exit_seconds}s 时间退出`
      : "",
  ].filter(Boolean).join(" · ");

  return (
    <Box
      sx={{
        display: "grid",
        gridTemplateColumns: {
          xs: "minmax(0, 1fr)",
          md: "minmax(0, 1fr) minmax(360px, 34%)",
        },
        gridTemplateRows: { xs: "auto auto auto", md: "auto minmax(0, 1fr)" },
        height: { xs: "auto", md: "100%" },
        minHeight: 0,
        overflow: { xs: "visible", md: "hidden" },
        bgcolor: "background.paper",
      }}
    >
      <Box
        sx={{
          minHeight: 54,
          px: { xs: 1.25, sm: 1.75 },
          py: 1,
          display: "flex",
          gap: 1,
          alignItems: "center",
          gridColumn: "1 / -1",
          borderBottom: 1,
          borderColor: "divider",
          overflow: "hidden",
        }}
      >
        {workspaceHeader ?? (
          <>
            <Typography component="h1" variant="subtitle1" sx={{ fontWeight: 750, mr: .5 }}>直接执行</Typography>
            <Chip size="small" variant="outlined" label={instrumentRef || "交易对象未知"} />
            <Chip size="small" variant="outlined" label={direction === "LONG" ? "做多" : "做空"} />
            <Chip size="small" variant="outlined" label={`资金上限 ${maxNotional || "未知"} USDT`} />
            <Typography variant="caption" color="text.secondary" sx={{ ml: { sm: "auto" } }}>
              草稿预览，不提交订单
            </Typography>
          </>
        )}
      </Box>

      <Box
        sx={{
          gridColumn: "1",
          gridRow: "2",
          minWidth: 0,
          minHeight: { xs: 0, md: 0 },
          height: { xs: "auto", md: "100%" },
          p: { xs: 1, md: 1.25 },
          overflow: { xs: "visible", md: "hidden" },
        }}
      >
        <OrderScheduleChart
          key={environmentScope}
          workspaceMode
          environmentId={environmentId}
          environmentKind={environmentKind}
          instrumentRef={instrumentRef}
          direction={direction}
          marketColorScheme={marketColorScheme}
          interval={chartInterval}
          onIntervalChange={onChartIntervalChange}
          liveBar={liveBar}
          streamStatus={streamStatus}
          streamGeneration={streamGeneration}
          priceProjectionReady={marketProjectionReady}
          priceTickSize={preview.data?.instrument_rules.price_tick_size ?? null}
          referencePrice={referencePrice}
          spec={value}
          previewLegs={previewReady ? (preview.data?.normalized_legs ?? []) : []}
          previewState={previewReady
            ? "READY"
            : localValidation.length === 0
              && (previewStale || preview.isPending || preview.isFetching)
              ? "PENDING"
              : "BLOCKED"}
          onRangeChange={(lowerPrice, upperPrice) => {
            if (value.price_distribution.kind !== "LADDER") return;
            onChange({
              ...value,
              price_distribution: {
                ...value.price_distribution,
                lower_price: lowerPrice,
                upper_price: upperPrice,
              },
            });
          }}
          onSingleLimitPriceChange={(limitPrice) => {
            if (value.price_distribution.kind !== "SINGLE") return;
            onChange({
              ...value,
              price_distribution: {
                ...value.price_distribution,
                limit_price: limitPrice,
              },
              venue_policy: {
                ...value.venue_policy,
                order_type: "LIMIT",
                price_match: null,
              },
            });
          }}
        />
      </Box>

      <Box
        component="aside"
        aria-label="直接执行快速配置"
        sx={{
          gridColumn: { xs: "1", md: "2" },
          gridRow: { xs: "3", md: "2" },
          minWidth: 0,
          minHeight: 0,
          display: "flex",
          flexDirection: "column",
          borderLeft: { xs: 0, md: 1 },
          borderTop: { xs: 1, md: 0 },
          borderColor: "divider",
          bgcolor: "background.paper",
        }}
      >
        <Box
          data-testid="direct-order-config-scroll"
          sx={{
            minHeight: 0,
            flex: "1 1 auto",
            overflowY: { xs: "visible", md: "auto" },
            overscrollBehavior: "contain",
          }}
        >
          {leadingControls ? (
            <Box sx={{ minWidth: 0 }}>
              {leadingControls}
            </Box>
          ) : null}

          <EditorSection
        id="order-schedule-price-title"
        title="价格与档位"
      >
        <ToggleButtonGroup
          exclusive
          fullWidth
          size="small"
          value={priceMode}
          aria-label="价格计划"
          onChange={(_event, next: "MARKET" | "LIMIT" | "LADDER" | null) => {
            if (!next || next === priceMode) return;
            if (next === "MARKET") {
              changeOrderType("MARKET");
            } else if (next === "LADDER") {
              changePriceKind("LADDER");
            } else if (price.kind === "LADDER") {
              changePriceKind("SINGLE");
            } else {
              changeOrderType("LIMIT");
            }
          }}
          sx={{
            "& .MuiToggleButton-root": {
              minHeight: 34,
              py: .5,
              textTransform: "none",
              fontWeight: 700,
            },
          }}
        >
          <ToggleButton value="MARKET">市价</ToggleButton>
          <ToggleButton value="LIMIT">单笔限价</ToggleButton>
          <ToggleButton value="LADDER">区间阶梯</ToggleButton>
        </ToggleButtonGroup>

        {price.kind === "SINGLE" ? (
          <Box sx={{ mt: 1.25 }}>
            {venue.order_type === "MARKET" ? (
              <Typography variant="caption" color="text.secondary">
                按场所当时可成交价格执行；当前 {referencePrice ? `参考 ${referencePrice} USDT` : "参考价不可用"}，成交价仍未知。
              </Typography>
            ) : (
              <>
                <TextField
                  fullWidth
                  size="small"
                  type="number"
                  label="限价（USDT）"
                  value={price.limit_price ?? ""}
                  disabled={venue.price_match !== null}
                  onChange={(event) => onChange({
                    ...value,
                    price_distribution: { ...price, limit_price: event.target.value },
                    venue_policy: { ...venue, price_match: null },
                  })}
                  helperText={venue.price_match !== null
                    ? `已使用 ${venue.price_match}，价格由场所决定`
                    : "可输入、拖动图线，或使用下方盘口价"}
                  slotProps={{ htmlInput: { min: 0, step: "any" } }}
                />
                <Stack direction="row" spacing={.75} sx={{ mt: .75 }}>
                  {[
                    { label: "买一", candidate: bidPrice },
                    { label: "中间价", candidate: liveReferencePrice ?? referencePrice },
                    { label: "卖一", candidate: askPrice },
                  ].map(({ label, candidate }) => (
                    <Button
                      key={label}
                      size="small"
                      variant="text"
                      disabled={!candidate}
                      onClick={() => onChange({
                        ...value,
                        price_distribution: { ...price, limit_price: candidate ?? "" },
                        venue_policy: { ...venue, price_match: null },
                      })}
                      sx={{ minWidth: 0, px: .75 }}
                    >
                      {label}
                    </Button>
                  ))}
                </Stack>
              </>
            )}
          </Box>
        ) : (
          <Stack spacing={1.5} sx={{ mt: 1.5 }}>
            <Box sx={compactFieldGridSx}>
              <TextField
                size="small"
                type="number"
                label="下限（USDT）"
                value={price.lower_price}
                onChange={(event) => onChange({ ...value, price_distribution: { ...price, lower_price: event.target.value } })}
                slotProps={{ htmlInput: { min: 0, step: "any" } }}
              />
              <TextField
                size="small"
                type="number"
                label="上限（USDT）"
                value={price.upper_price}
                onChange={(event) => onChange({ ...value, price_distribution: { ...price, upper_price: event.target.value } })}
                slotProps={{ htmlInput: { min: 0, step: "any" } }}
              />
              <TextField
                size="small"
                type="number"
                label="价格档位数"
                value={price.level_count}
                onChange={(event) => {
                  const count = Number(event.target.value);
                  const safeCount = Number.isInteger(count) ? count : 0;
                  const boundedCount = safeCount >= 2 && safeCount <= 50 ? safeCount : 0;
                  onChange({
                    ...value,
                    price_distribution: {
                      ...price,
                      level_count: safeCount,
                      custom_gap_weights: price.spacing_mode === "CUSTOM_WEIGHTS"
                        ? resized(price.custom_gap_weights, Math.max(0, boundedCount - 1), "1")
                        : [],
                    },
                    amount_distribution: amount.mode === "CUSTOM"
                      ? { ...amount, custom_notionals: resized(amount.custom_notionals, boundedCount, amount.base_notional || "10") }
                      : amount,
                  });
                }}
                slotProps={{ htmlInput: { min: 2, max: 50, step: 1 } }}
              />
            </Box>
            <Box
              component="details"
              sx={{
                borderTop: 1,
                borderColor: "divider",
                pt: .75,
                "& > summary": { cursor: "pointer", fontSize: 12, fontWeight: 700 },
              }}
            >
              <Box component="summary">
                高级价格间距 · {price.spacing_mode === "EQUAL"
                  ? "等距"
                  : price.spacing_mode === "LINEAR"
                    ? "线性比例"
                    : price.spacing_mode === "GEOMETRIC" ? "指数比例" : "自定义"}
              </Box>
              <Stack spacing={1.25} sx={{ mt: 1 }}>
              <Box sx={fieldGridSx}>
              <TextField
                select
                size="small"
                label="价格切分间距"
                value={price.spacing_mode}
                onChange={(event) => {
                  const mode = event.target.value as typeof price.spacing_mode;
                  onChange({
                    ...value,
                    price_distribution: {
                      ...price,
                      spacing_mode: mode,
                      custom_gap_weights: mode === "CUSTOM_WEIGHTS"
                        ? resized(
                          price.custom_gap_weights,
                          Number.isInteger(price.level_count)
                            && price.level_count >= 2
                            && price.level_count <= 50
                            ? price.level_count - 1
                            : 0,
                          "1",
                        )
                        : [],
                    },
                  });
                }}
              >
                <MenuItem value="EQUAL">等距</MenuItem>
                <MenuItem value="LINEAR">线性比例</MenuItem>
                <MenuItem value="GEOMETRIC">指数比例</MenuItem>
                <MenuItem value="CUSTOM_WEIGHTS">自定义比例</MenuItem>
              </TextField>
              {price.spacing_mode !== "EQUAL" ? (
                <TextField
                  select
                  size="small"
                  label="间距比例应用方向"
                  value={price.spacing_direction}
                  onChange={(event) => onChange({
                    ...value,
                    price_distribution: {
                      ...price,
                      spacing_direction: event.target.value as typeof price.spacing_direction,
                    },
                  })}
                >
                  <MenuItem value="LOW_TO_HIGH">从低价到高价</MenuItem>
                  <MenuItem value="HIGH_TO_LOW">从高价到低价</MenuItem>
                </TextField>
              ) : <Box />}
            </Box>
            {price.spacing_mode === "LINEAR" ? (
              <Box sx={fieldGridSx}>
                <TextField
                  size="small"
                  type="number"
                  label="首个间距权重"
                  value={price.linear_start_weight}
                  onChange={(event) => onChange({ ...value, price_distribution: { ...price, linear_start_weight: event.target.value } })}
                  slotProps={{ htmlInput: { step: "any" } }}
                />
                <TextField
                  size="small"
                  type="number"
                  label="每档权重增量"
                  value={price.linear_step}
                  onChange={(event) => onChange({ ...value, price_distribution: { ...price, linear_step: event.target.value } })}
                  helperText="可为负，但每个生成权重都必须大于 0"
                  slotProps={{ htmlInput: { step: "any" } }}
                />
              </Box>
            ) : null}
            {price.spacing_mode === "GEOMETRIC" ? (
              <TextField
                size="small"
                type="number"
                label="间距指数比例"
                value={price.geometric_ratio}
                onChange={(event) => onChange({ ...value, price_distribution: { ...price, geometric_ratio: event.target.value } })}
                helperText="大于 1，最大 100"
                slotProps={{ htmlInput: { min: 1, max: 100, step: "any" } }}
                sx={{ maxWidth: 360 }}
              />
            ) : null}
              {price.spacing_mode === "CUSTOM_WEIGHTS" ? (
              <Box>
                <Typography variant="caption" color="text.secondary">
                  依次填写相邻价格之间的比例，例如 5:4:3:2。
                </Typography>
                <Box sx={{ ...compactFieldGridSx, mt: 1 }}>
                  {price.custom_gap_weights.map((weight, index) => (
                    <TextField
                      key={`gap-${index}`}
                      size="small"
                      type="number"
                      label={`间距 ${index + 1} 权重`}
                      value={weight}
                      onChange={(event) => onChange({
                        ...value,
                        price_distribution: {
                          ...price,
                          custom_gap_weights: replaceAt(price.custom_gap_weights, index, event.target.value),
                        },
                      })}
                      slotProps={{ htmlInput: { min: 0, step: "any" } }}
                    />
                  ))}
                </Box>
              </Box>
              ) : null}
              </Stack>
            </Box>
          </Stack>
        )}
      </EditorSection>

      <EditorSection
        id="order-schedule-amount-title"
        title="下单金额"
      >
        <Box sx={fieldGridSx}>
          <TextField
            select
            size="small"
            label="下单额模式"
            value={amount.mode}
            disabled={price.kind === "SINGLE"}
            onChange={(event) => {
              const mode = event.target.value as typeof amount.mode;
              onChange({
                ...value,
                amount_distribution: {
                  ...amount,
                  mode,
                  custom_notionals: mode === "CUSTOM"
                    ? resized(
                      amount.custom_notionals,
                      price.kind === "SINGLE"
                        ? 1
                        : Number.isInteger(price.level_count)
                          && price.level_count >= 2
                          && price.level_count <= 50
                          ? price.level_count
                          : 0,
                      amount.base_notional || "10",
                    )
                    : [],
                },
              });
            }}
          >
            <MenuItem value="FIXED">固定金额</MenuItem>
            <MenuItem value="LINEAR">线性增长</MenuItem>
            <MenuItem value="EXPONENTIAL">指数增长</MenuItem>
            <MenuItem value="CUSTOM">逐档自定义</MenuItem>
          </TextField>
          <TextField
            size="small"
            type="number"
            label={price.kind === "SINGLE"
              ? "下单金额（USDT）"
              : amount.mode === "FIXED" ? "每档金额（USDT）" : "基础金额（USDT）"}
            value={amount.base_notional}
            disabled={amount.mode === "CUSTOM"}
            onChange={(event) => onChange({ ...value, amount_distribution: { ...amount, base_notional: event.target.value } })}
            slotProps={{ htmlInput: { min: 0, step: "any" } }}
          />
        </Box>
        {amount.mode !== "FIXED" && amount.mode !== "CUSTOM" ? (
          <Box sx={{ ...fieldGridSx, mt: 1.5 }}>
            {amount.mode === "LINEAR" ? (
              <TextField
                size="small"
                type="number"
                label="每档金额增量（USDT）"
                value={amount.linear_step}
                onChange={(event) => onChange({ ...value, amount_distribution: { ...amount, linear_step: event.target.value } })}
                slotProps={{ htmlInput: { min: 0, step: "any" } }}
              />
            ) : (
              <TextField
                size="small"
                type="number"
                label="金额指数比例"
                value={amount.exponential_ratio}
                onChange={(event) => onChange({ ...value, amount_distribution: { ...amount, exponential_ratio: event.target.value } })}
                helperText="大于 1，最大 100"
                slotProps={{ htmlInput: { min: 1, max: 100, step: "any" } }}
              />
            )}
            <TextField
              select
              size="small"
              label="金额增长方向"
              value={amount.direction}
              onChange={(event) => onChange({
                ...value,
                amount_distribution: {
                  ...amount,
                  direction: event.target.value as typeof amount.direction,
                },
              })}
            >
              <MenuItem value="LOW_TO_HIGH">从低价到高价</MenuItem>
              <MenuItem value="HIGH_TO_LOW">从高价到低价</MenuItem>
            </TextField>
          </Box>
        ) : null}
        {amount.mode === "CUSTOM" ? (
          <Box sx={{ mt: 1.5 }}>
            <Typography variant="caption" color="text.secondary">按低价到高价顺序逐档填写。</Typography>
            <Box sx={{ ...compactFieldGridSx, mt: 1 }}>
              {amount.custom_notionals.map((notional, index) => (
                <TextField
                  key={`notional-${index}`}
                  size="small"
                  type="number"
                  label={`档位 ${index + 1}（USDT）`}
                  value={notional}
                  onChange={(event) => onChange({
                    ...value,
                    amount_distribution: {
                      ...amount,
                      custom_notionals: replaceAt(amount.custom_notionals, index, event.target.value),
                    },
                  })}
                  slotProps={{ htmlInput: { min: 0, step: "any" } }}
                />
              ))}
            </Box>
          </Box>
        ) : null}
      </EditorSection>

      <EditorSection
        id="order-schedule-venue-title"
        title="交易所模式"
      >
        <Stack direction="row" spacing={1} sx={{ alignItems: "center", justifyContent: "space-between" }}>
          <FormControlLabel
            control={(
              <Switch
                size="small"
                checked={venue.post_only}
                disabled={venue.order_type === "MARKET" || venue.time_in_force !== "GTC"}
                onChange={(event) => onChange({
                  ...value,
                  price_distribution: event.target.checked
                    && price.kind === "SINGLE"
                    && price.limit_price === null
                    ? { ...price, limit_price: referencePrice ?? "" }
                    : price,
                  venue_policy: {
                    ...venue,
                    post_only: event.target.checked,
                    price_match: event.target.checked ? null : venue.price_match,
                  },
                })}
              />
            )}
            label="Maker only"
            sx={{ m: 0 }}
          />
          <Typography variant="caption" color="text.secondary" sx={{ alignSelf: "center" }}>
            {venue.post_only ? "只允许挂单方成交" : "允许按当前订单类型执行"}
          </Typography>
        </Stack>
        <Box
          component="details"
          sx={{
            mt: .75,
            borderTop: 1,
            borderColor: "divider",
            pt: .75,
            "& > summary": { cursor: "pointer", fontSize: 12, fontWeight: 700 },
          }}
        >
          <Box component="summary">高级交易所设置 · {venueSummary}</Box>
          <Stack spacing={1.25} sx={{ mt: 1 }}>
            <Box sx={fieldGridSx}>
              <TextField
                select
                size="small"
                label="有效方式"
                value={venue.time_in_force ?? ""}
                disabled={venue.order_type === "MARKET"}
                onChange={(event) => {
                  const next = event.target.value as "GTC" | "GTD" | "IOC" | "FOK";
                  onChange({
                    ...value,
                    venue_policy: {
                      ...venue,
                      time_in_force: next,
                      post_only: next === "GTC" ? venue.post_only : false,
                      expire_at: next === "GTD" ? venue.expire_at : null,
                    },
                  });
                }}
              >
                <MenuItem value="GTC">GTC · 持续有效</MenuItem>
                <MenuItem value="GTD">GTD · 指定到期</MenuItem>
                <MenuItem value="IOC">IOC · 立即成交余量撤销</MenuItem>
                <MenuItem value="FOK">FOK · 全成或全撤</MenuItem>
              </TextField>
              <TextField
                select
                size="small"
                label="串行提交顺序"
                value={value.submission_order}
                onChange={(event) => onChange({
                  ...value,
                  submission_order: event.target.value as typeof value.submission_order,
                })}
              >
                <MenuItem value="LOW_TO_HIGH">低价 → 高价</MenuItem>
                <MenuItem value="HIGH_TO_LOW">高价 → 低价</MenuItem>
              </TextField>
            </Box>
            {price.kind === "SINGLE" && venue.order_type === "LIMIT" ? (
              <TextField
                select
                fullWidth
                size="small"
                label="priceMatch"
                value={venue.price_match ?? ""}
                disabled={venue.post_only}
                onChange={(event) => {
                  const next = event.target.value as OrderSchedulePriceMatch | "";
                  onChange({
                    ...value,
                    price_distribution: { ...price, limit_price: next ? null : (price.limit_price ?? referencePrice ?? "") },
                    venue_policy: { ...venue, price_match: next || null },
                  });
                }}
                helperText={venue.post_only ? "Maker only 已启用，不能使用 priceMatch" : "使用场所队列价格时，预览成交价仍未知"}
              >
                <MenuItem value="">不使用（显式价格）</MenuItem>
                {priceMatchOptions.map((option) => (
                  <MenuItem key={option.value} value={option.value}>{option.label}</MenuItem>
                ))}
              </TextField>
            ) : null}
            {venue.time_in_force === "GTD" ? (
              <TextField
                size="small"
                type="datetime-local"
                label="GTD 到期时间"
                value={localDateTimeValue(venue.expire_at)}
                onChange={(event) => onChange({
                  ...value,
                  venue_policy: { ...venue, expire_at: isoFromLocalDateTime(event.target.value) },
                })}
                helperText="服务端按交易所事实截止点检查至少 10 分钟提前量"
                slotProps={{ inputLabel: { shrink: true } }}
              />
            ) : null}
            <Typography variant="caption" color="text.secondary">
              当前为串行保护：前一档的成交、撤单竞争和保护责任闭合后，才开放下一档。
            </Typography>
          </Stack>
        </Box>
      </EditorSection>

      <EditorSection
        id="order-schedule-condition-title"
        title="条件与触发"
        collapsible
        summary={conditionSummary}
        description="事实缺失、冲突或过期时结果为未知，不形成新增风险动作。"
      >
        <TextField
          select
          size="small"
          label="条件组合"
          value={value.entry_conditions.operator}
          onChange={(event) => {
            const operator = event.target.value as "ALL" | "ANY";
            onChange({
              ...value,
              entry_conditions: {
                ...value.entry_conditions,
                operator,
                items: normalizedDirectConditionItems(
                  operator,
                  value.entry_conditions.items,
                ),
              },
            });
          }}
          sx={{ width: { xs: "100%", sm: 260 } }}
        >
          <MenuItem value="ALL">全部满足（ALL）</MenuItem>
          <MenuItem value="ANY">任一满足（ANY）</MenuItem>
        </TextField>
        {value.entry_conditions.operator === "ANY" ? (
          <Alert severity="info" variant="outlined" sx={{ mt: 1.25 }}>
            ANY 只在已选择的市场条件之间取“任一满足”；没有选择市场条件时才表示立即执行。
          </Alert>
        ) : null}
        <Box sx={{ mt: 1.25 }}>
          <FormControlLabel
            control={<Checkbox checked={Boolean(conditionByKind(value.entry_conditions.items, "DECISION_BASIS_READY"))} disabled />}
            label={value.entry_conditions.operator === "ANY"
              && value.entry_conditions.items.some((item) => item.kind !== "DECISION_BASIS_READY")
              ? "决策依据已准备（ANY 市场条件中自动排除）"
              : "决策依据已准备"}
          />
        </Box>
        <Stack spacing={1.25} sx={{ mt: .5 }}>
          <Box sx={{ ...surfaceFrameSx, p: 1.25 }}>
            <FormControlLabel
              control={<Checkbox checked={Boolean(markCondition)} onChange={(event) => setConditionEnabled("MARK_PRICE", event.target.checked)} />}
              label="标记价格条件"
            />
            {markCondition ? (
              <Box sx={{ ...fieldGridSx, mt: 1 }}>
                <TextField
                  select
                  size="small"
                  label="比较方式"
                  value={markCondition.comparator}
                  onChange={(event) => onChange({
                    ...value,
                    entry_conditions: {
                      ...value.entry_conditions,
                      items: withCondition(value.entry_conditions.items, {
                        ...markCondition,
                        comparator: event.target.value as "GTE" | "LTE",
                      }),
                    },
                  })}
                >
                  <MenuItem value="GTE">大于等于</MenuItem>
                  <MenuItem value="LTE">小于等于</MenuItem>
                </TextField>
                <TextField
                  size="small"
                  type="number"
                  label="标记价格（USDT）"
                  value={markCondition.price}
                  onChange={(event) => onChange({
                    ...value,
                    entry_conditions: {
                      ...value.entry_conditions,
                      items: withCondition(value.entry_conditions.items, { ...markCondition, price: event.target.value }),
                    },
                  })}
                  slotProps={{ htmlInput: { min: 0, step: "any" } }}
                />
              </Box>
            ) : null}
          </Box>

          <Box sx={{ ...surfaceFrameSx, p: 1.25 }}>
            <FormControlLabel
              control={<Checkbox checked={Boolean(spreadCondition)} onChange={(event) => setConditionEnabled("SPREAD_BPS", event.target.checked)} />}
              label="买卖价差上限"
            />
            {spreadCondition ? (
              <TextField
                size="small"
                type="number"
                label="最大价差（bps）"
                value={spreadCondition.maximum_bps}
                onChange={(event) => onChange({
                  ...value,
                  entry_conditions: {
                    ...value.entry_conditions,
                    items: withCondition(value.entry_conditions.items, { ...spreadCondition, maximum_bps: event.target.value }),
                  },
                })}
                slotProps={{ htmlInput: { min: 0, step: "any" } }}
                sx={{ mt: 1, width: { xs: "100%", sm: 320 } }}
              />
            ) : null}
          </Box>

          <Box sx={{ ...surfaceFrameSx, p: 1.25 }}>
            <FormControlLabel
              control={<Checkbox checked={Boolean(moveCondition)} onChange={(event) => setConditionEnabled("PRICE_MOVE_BPS", event.target.checked)} />}
              label="短时价格变动"
            />
            {moveCondition ? (
              <Box sx={{ ...compactFieldGridSx, mt: 1 }}>
                <TextField
                  select
                  size="small"
                  label="比较方式"
                  value={moveCondition.comparator}
                  onChange={(event) => onChange({
                    ...value,
                    entry_conditions: {
                      ...value.entry_conditions,
                      items: withCondition(value.entry_conditions.items, {
                        ...moveCondition,
                        comparator: event.target.value as "GTE" | "LTE" | "ABS_GTE",
                      }),
                    },
                  })}
                >
                  <MenuItem value="GTE">上涨至少</MenuItem>
                  <MenuItem value="LTE">变动不高于</MenuItem>
                  <MenuItem value="ABS_GTE">绝对变动至少</MenuItem>
                </TextField>
                <TextField
                  size="small"
                  type="number"
                  label="观察窗口（秒）"
                  value={moveCondition.window_seconds}
                  onChange={(event) => onChange({
                    ...value,
                    entry_conditions: {
                      ...value.entry_conditions,
                      items: withCondition(value.entry_conditions.items, { ...moveCondition, window_seconds: Number(event.target.value) }),
                    },
                  })}
                  slotProps={{ htmlInput: { min: 1, max: 300, step: 1 } }}
                />
                <TextField
                  size="small"
                  type="number"
                  label="变动阈值（bps）"
                  value={moveCondition.threshold_bps}
                  onChange={(event) => onChange({
                    ...value,
                    entry_conditions: {
                      ...value.entry_conditions,
                      items: withCondition(value.entry_conditions.items, { ...moveCondition, threshold_bps: event.target.value }),
                    },
                  })}
                  slotProps={{ htmlInput: { min: 0, step: "any" } }}
                />
              </Box>
            ) : null}
          </Box>
        </Stack>
      </EditorSection>

      <EditorSection
        id="order-schedule-protection-title"
        title="初始止损"
      >
        <Box sx={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) auto", gap: 1, alignItems: "center" }}>
          <TextField
            size="small"
            type="number"
            label="初始止损距离（bps）"
            value={value.protection_policy.initial_stop.distance_bps}
            onChange={(event) => onChange({
              ...value,
              protection_policy: {
                ...value.protection_policy,
                initial_stop: {
                  ...value.protection_policy.initial_stop,
                  distance_bps: event.target.value,
                },
              },
            })}
            helperText="1% = 100 bps；最大 5000 bps"
            slotProps={{ htmlInput: { min: 0, max: 5_000, step: "any" } }}
          />
          <Typography variant="caption" color="text.secondary">标记价格触发</Typography>
        </Box>

        <Box
          component="details"
          sx={{
            mt: .75,
            borderTop: 1,
            borderColor: "divider",
            pt: .75,
            "& > summary": { cursor: "pointer", fontSize: 12, fontWeight: 700 },
          }}
        >
          <Box component="summary">止盈与时间退出 · {protectionSummary}</Box>
          <Box sx={{ mt: 1 }}>
          <FormControlLabel
            control={(
              <Checkbox
                checked={value.protection_policy.take_profit_ladder !== null}
                onChange={(event) => onChange({
                  ...value,
                  protection_policy: {
                    ...value.protection_policy,
                    take_profit_ladder: event.target.checked
                      ? { levels: [{ trigger_r: "1.5", quantity_fraction: "1" }] }
                      : null,
                  },
                })}
              />
            )}
            label="启用单级全量止盈"
          />
          </Box>
        {value.protection_policy.take_profit_ladder !== null ? (
          <Box sx={{ mt: .75 }}>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
              R 以该笔成交的初始止损距离为基准。当前直接执行只允许一次性平掉该笔成交量，避免最小数量量化后出现无保护余仓。
            </Typography>
            <Box
              sx={{
                display: "grid",
                gridTemplateColumns: { xs: "1fr", sm: "minmax(0,1fr) minmax(0,1fr)" },
                gap: 1,
                alignItems: "start",
              }}
            >
              <TextField
                size="small"
                type="number"
                label="止盈（R）"
                value={takeProfitLevels[0]?.trigger_r ?? ""}
                onChange={(event) => onChange({
                  ...value,
                  protection_policy: {
                    ...value.protection_policy,
                    take_profit_ladder: {
                      levels: [{ trigger_r: event.target.value, quantity_fraction: "1" }],
                    },
                  },
                })}
                slotProps={{ htmlInput: { min: 0, step: "any" } }}
              />
              <TextField
                size="small"
                label="成交量比例"
                value="100%"
                slotProps={{ htmlInput: { readOnly: true } }}
              />
            </Box>
          </Box>
        ) : null}

          <Box sx={{ mt: 1.25 }}>
          <FormControlLabel
            control={(
              <Checkbox
                checked={value.protection_policy.time_exit_seconds !== null}
                onChange={(event) => onChange({
                  ...value,
                  protection_policy: {
                    ...value.protection_policy,
                    time_exit_seconds: event.target.checked ? 86_400 : null,
                  },
                })}
              />
            )}
            label="启用整次持仓时间退出"
          />
          {value.protection_policy.time_exit_seconds !== null ? (
            <TextField
              size="small"
              type="number"
              label="首笔成交后整组退出（秒）"
              value={value.protection_policy.time_exit_seconds}
              onChange={(event) => onChange({
                ...value,
                protection_policy: {
                  ...value.protection_policy,
                  time_exit_seconds: Number(event.target.value),
                },
              })}
              slotProps={{ htmlInput: { min: 1, max: 2_592_000, step: 1 } }}
              helperText="以本次激活的首笔成交为全局时钟；到期先停止并撤销剩余入场，再按当前持仓退出"
              sx={{ display: "block", mt: 1, maxWidth: 360 }}
            />
          ) : null}
          </Box>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
            每笔确认成交按自身成交价与数量建立保护；是否生效以交易所事实为准。
          </Typography>
        </Box>
      </EditorSection>

      <EditorSection
        id="order-schedule-dynamic-title"
        title="动态撤单"
        collapsible
        summary={dynamicSummary}
        description="到期规则从首档真实提交开始计时；异动事实未知时暂停新档并撤开放档，首次异动触发后终止全部剩余档。撤单可能与成交竞争，不代表成交风险已经消失。"
      >
        <Stack spacing={1.25}>
          <Box sx={{ ...surfaceFrameSx, p: 1.25 }}>
            <FormControlLabel
              control={(
                <Checkbox
                  checked={Boolean(expireRule)}
                  disabled={venue.order_type !== "LIMIT"}
                  onChange={(event) => onChange({
                    ...value,
                    dynamic_rules: event.target.checked
                      ? withDynamicRule(value.dynamic_rules, { kind: "EXPIRE_REMAINING", after_seconds: 300 })
                      : withoutDynamicRule(value.dynamic_rules, "EXPIRE_REMAINING"),
                  })}
                />
              )}
              label="到期撤销未成交余量"
            />
            {venue.order_type !== "LIMIT" ? (
              <Typography variant="caption" color="text.secondary">仅限价单可用。</Typography>
            ) : null}
            {expireRule ? (
              <TextField
                size="small"
                type="number"
                label="首档提交后等待（秒）"
                value={expireRule.after_seconds}
                onChange={(event) => onChange({
                  ...value,
                  dynamic_rules: withDynamicRule(value.dynamic_rules, {
                    ...expireRule,
                    after_seconds: Number(event.target.value),
                  }),
                })}
                slotProps={{ htmlInput: { min: 1, max: 604_800, step: 1 } }}
                helperText="从首个档位真正进入提交开始计时，条件等待不会提前消耗该时长"
                sx={{ mt: 1, display: "block", maxWidth: 320 }}
              />
            ) : null}
          </Box>

          <Box sx={{ ...surfaceFrameSx, p: 1.25 }}>
            <FormControlLabel
              control={(
                <Checkbox
                  checked={Boolean(shockRule)}
                  disabled={venue.order_type !== "LIMIT"}
                  onChange={(event) => onChange({
                    ...value,
                    dynamic_rules: event.target.checked
                      ? withDynamicRule(value.dynamic_rules, {
                        kind: "CANCEL_ON_SHOCK",
                        window_seconds: 30,
                        adverse_move_bps: "50",
                        max_triggers: 1,
                      })
                      : withoutDynamicRule(value.dynamic_rules, "CANCEL_ON_SHOCK"),
                  })}
                />
              )}
              label="短时不利异动撤单"
            />
            {venue.order_type !== "LIMIT" ? (
              <Typography variant="caption" color="text.secondary">仅限价单可用。</Typography>
            ) : null}
            {shockRule ? (
              <Box sx={{ ...compactFieldGridSx, mt: 1 }}>
                <Typography variant="caption" color="text.secondary" sx={{ gridColumn: "1 / -1" }}>
                  当前只允许触发一次：触发会撤销当前开放档并终止尚未提交档；窗口事实不可用时也不会继续增加风险。
                </Typography>
                <TextField
                  size="small"
                  type="number"
                  label="观察窗口（秒）"
                  value={shockRule.window_seconds}
                  onChange={(event) => onChange({
                    ...value,
                    dynamic_rules: withDynamicRule(value.dynamic_rules, { ...shockRule, window_seconds: Number(event.target.value) }),
                  })}
                  slotProps={{ htmlInput: { min: 1, max: 300, step: 1 } }}
                />
                <TextField
                  size="small"
                  type="number"
                  label="不利变动（bps）"
                  value={shockRule.adverse_move_bps}
                  onChange={(event) => onChange({
                    ...value,
                    dynamic_rules: withDynamicRule(value.dynamic_rules, { ...shockRule, adverse_move_bps: event.target.value }),
                  })}
                  slotProps={{ htmlInput: { min: 0, step: "any" } }}
                />
                <TextField
                  size="small"
                  label="最多触发次数"
                  value="1（当前已验证上限）"
                  slotProps={{ htmlInput: { readOnly: true } }}
                />
              </Box>
            ) : null}
          </Box>
        </Stack>
      </EditorSection>

      <EditorSection
        id="order-schedule-preview-title"
        title="服务端预览"
      >
        {localValidation.length > 0 ? (
          <Alert severity="warning" variant="outlined">
            <Typography variant="body2" sx={{ fontWeight: 700 }}>修正以下输入后再生成预览：</Typography>
            <Box component="ul" sx={{ my: .75, pl: 2.5 }}>
              {localValidation.map((problem) => <li key={problem}>{problem}</li>)}
            </Box>
          </Alert>
        ) : null}
        {localValidation.length === 0 && (preview.isPending || previewStale) ? (
          <Box aria-live="polite">
            <LinearProgress aria-label="正在按当前输入生成订单计划预览" />
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
              {previewStale ? "输入已变化，等待当前版本的服务端预览。" : "正在读取交易所规则并标准化全部档位。"}
            </Typography>
          </Box>
        ) : null}
        {localValidation.length === 0 && preview.isError && !previewStale ? (
          <Alert
            severity="error"
            action={<Button color="inherit" size="small" onClick={() => preview.refetch()}>重试预览</Button>}
          >
            {previewFailureText(preview.error)}
          </Alert>
        ) : null}
        {localValidation.length === 0 && preview.data && !previewStale ? (
          <Stack spacing={1.5}>
            {preview.isFetching ? (
              <Alert severity="info" variant="outlined">
                正在刷新交易所规则；下表仍是截止 {formatUserVisibleTime(preview.data.source_cutoff)} 的上次预览。
              </Alert>
            ) : null}
            <Alert severity={preview.data.valid ? "success" : "error"}>
              {preview.data.valid
                ? `预览可保存 · ${preview.data.legs.length} 档 · 标准化总额 ${preview.data.effective_total_notional} USDT`
                : "预览被服务端阻断；标准化结果仅用于定位，不能形成执行档位。"}
            </Alert>
            {preview.data.issues.length > 0 ? (
              <Alert severity="error" variant="outlined">
                <Box component="ul" sx={{ my: 0, pl: 2.5 }}>
                  {preview.data.issues.map((issue, index) => (
                    <li key={`${issue.code}:${issue.leg_index ?? "all"}:${index}`}>
                      {issue.leg_index === null ? "" : `档位 ${issue.leg_index + 1}：`}
                      {issueLabels[issue.code] ?? issue.code}
                      <Typography component="span" variant="caption" color="text.secondary"> · {issue.field}</Typography>
                    </li>
                  ))}
                </Box>
              </Alert>
            ) : null}
            <Box
              component="details"
              sx={{
                borderTop: 1,
                borderColor: "divider",
                pt: .75,
                "& > summary": { cursor: "pointer", fontSize: 12, fontWeight: 700 },
              }}
            >
              <Box component="summary">
                完整标准化明细 · {shortDigest(preview.data.schedule_digest)}
              </Box>
              <Stack spacing={1.25} sx={{ mt: 1 }}>
            <Box
              component="dl"
              sx={{
                m: 0,
                display: "grid",
                gridTemplateColumns: { xs: "1fr", sm: "repeat(2, minmax(0, 1fr))" },
                gap: 1,
              }}
            >
              {[
                ["请求总额", `${preview.data.requested_total_notional} USDT`],
                ["标准化总额", `${preview.data.effective_total_notional} USDT`],
                ["计量参考价", preview.data.reference_price === null ? "未使用" : `${preview.data.reference_price} USDT`],
                ["交易所规则", preview.data.instrument_rules.source],
                ["规则截止", formatUserVisibleTime(preview.data.source_cutoff)],
                ["价格步进", preview.data.instrument_rules.price_tick_size],
                ["最小名义金额", `${preview.data.instrument_rules.min_notional} USDT`],
              ].map(([label, display]) => (
                <Box key={label} sx={{ px: 1.25, py: 1, bgcolor: "action.hover", borderRadius: 1 }}>
                  <Typography component="dt" variant="caption" color="text.secondary">{label}</Typography>
                  <Typography component="dd" className="mono" variant="body2" sx={{ m: 0, mt: .25 }}>{display}</Typography>
                </Box>
              ))}
            </Box>
            <TableContainer
              className="table-scroll"
              role="region"
              aria-label="标准化订单档位"
              tabIndex={0}
              sx={{ ...surfaceFrameSx, overflowX: "auto" }}
            >
              <Table size="small" aria-label="标准化订单档位表" sx={{ minWidth: 860 }}>
                <TableHead>
                  <TableRow>
                    <TableCell>档位</TableCell>
                    <TableCell align="right">原始价格</TableCell>
                    <TableCell align="right">标准化价格</TableCell>
                    <TableCell align="right">计量价格</TableCell>
                    <TableCell align="right">请求金额</TableCell>
                    <TableCell align="right">数量</TableCell>
                    <TableCell align="right">有效金额</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {preview.data.normalized_legs.map((leg) => (
                    <TableRow key={leg.leg_index} hover>
                      <TableCell>{leg.leg_index + 1} / {leg.leg_count}</TableCell>
                      <TableCell
                        className="mono"
                        align="right"
                        title={leg.raw_price ?? undefined}
                      >
                        {leg.raw_price === null ? "场所决定" : compactDecimal(leg.raw_price)}
                      </TableCell>
                      <TableCell className="mono" align="right">{leg.price ?? "场所决定"}</TableCell>
                      <TableCell className="mono" align="right">{leg.sizing_price}</TableCell>
                      <TableCell className="mono" align="right">{leg.requested_notional} USDT</TableCell>
                      <TableCell className="mono" align="right">{leg.quantity}</TableCell>
                      <TableCell className="mono" align="right">{leg.effective_notional} USDT</TableCell>
                    </TableRow>
                  ))}
                  {preview.data.normalized_legs.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={7} align="center">没有可展示的标准化档位。</TableCell>
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>
            </TableContainer>
            <Button
              variant="outlined"
              size="small"
              onClick={() => preview.refetch()}
              disabled={preview.isFetching}
              sx={{ alignSelf: "flex-start" }}
            >
              {preview.isFetching ? "正在刷新…" : "按当前输入重新预览"}
            </Button>
              </Stack>
            </Box>
          </Stack>
        ) : null}
      </EditorSection>
          {planOptions ? (
            <Box sx={{ borderBottom: 1, borderColor: "divider" }}>
              {planOptions}
            </Box>
          ) : null}
        </Box>
        {footerControls ? (
          <Box
            sx={{
              flex: "0 0 auto",
              borderTop: 1,
              borderColor: "divider",
              bgcolor: "background.paper",
              px: 1.5,
              py: 1.25,
            }}
          >
            {footerControls}
          </Box>
        ) : null}
      </Box>
    </Box>
  );
}
