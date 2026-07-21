export const USER_VISIBLE_TIME_ZONE = "Asia/Shanghai";
export const USER_VISIBLE_TIME_ZONE_LABEL = "UTC+8";
export const USER_VISIBLE_TIME_LOCALE = "zh-CN";

const userVisibleTimeFormatter = new Intl.DateTimeFormat(USER_VISIBLE_TIME_LOCALE, {
  timeZone: USER_VISIBLE_TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
});

export function formatUserVisibleTime(value: string | null | undefined): string {
  if (!value?.trim()) return "未知";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "未知";

  const parts = userVisibleTimeFormatter.formatToParts(parsed);
  const part = (type: Intl.DateTimeFormatPartTypes): string =>
    parts.find((item) => item.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}-${part("day")} ${part("hour")}:${part("minute")}:${part("second")} ${USER_VISIBLE_TIME_ZONE_LABEL}`;
}

/** @deprecated Prefer formatUserVisibleTime for user-visible timestamps. */
export function formatUtc(value: string | null | undefined): string {
  return formatUserVisibleTime(value);
}

export function latestUtc(values: Array<string | null | undefined>): string | null {
  let latest: { value: string; time: number } | null = null;
  for (const value of values) {
    if (!value) continue;
    const time = Date.parse(value);
    if (!Number.isFinite(time)) continue;
    if (latest === null || time > latest.time) latest = { value, time };
  }
  return latest?.value ?? null;
}

export function shortDigest(value: string | null): string {
  if (!value) return "NOT BOUND";
  return value.length > 16 ? `${value.slice(0, 12)}…${value.slice(-4)}` : value;
}

export function marketPrice(value: string): string {
  const parsed = Number(value);
  return Number.isFinite(parsed)
    ? parsed.toLocaleString("zh-CN", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    })
    : value;
}

export function marketVolume(value: string): string {
  const parsed = Number(value);
  return Number.isFinite(parsed)
    ? parsed.toLocaleString("zh-CN", { maximumFractionDigits: 8 })
    : value;
}

export function gapPercent(value: string): string {
  if (!value.trim()) return "UNKNOWN";
  const parsed = Number(value);
  return Number.isFinite(parsed) ? `${parsed.toFixed(3)}%` : "UNKNOWN";
}

export function pendingBreakoutNote(direction: "LONG" | "SHORT"): string {
  return direction === "LONG"
    ? "当前做多计划：本根尚未收于通道上沿之外"
    : "当前做空计划：本根尚未收于通道下沿之外";
}

export function venueReasonText(value: string): string {
  const reason = value.trim();
  if (!reason) return "";
  const htmlStatus = reason.match(/<title>\s*(\d{3})\s*([^<]*)<\/title>/i);
  if (htmlStatus) {
    const code = htmlStatus[1] ?? "UNKNOWN";
    const label = (htmlStatus[2] ?? "").trim();
    const status = label ? ` ${label}` : "";
    return `Binance Demo 暂时不可用（HTTP ${code}${status}）；本次订单未成交，系统没有自动重复提交。`;
  }
  return reason.length > 240 ? `${reason.slice(0, 237)}…` : reason;
}

export function notSubmittedReasonText(value: string): string {
  if (value === "VENUE_QUERY_PROVED_ABSENT") {
    return "交易请求返回未决后，系统按原订单 UUID 查询确认 Binance 没有创建订单；本次未成交，也没有自动重复提交。";
  }
  if (value === "NAUTILUS_ORDER_DENIED") {
    return "订单在发送到 Binance 前被执行框架拒绝；本次未成交。";
  }
  return value ? `订单未提交：${value}` : "订单已确认未提交；本次未成交。";
}

const acceptedPlanEventLabels: Record<string, string> = {
  ENTRY_BREAKOUT: "入场意图已通过资金检查",
  PROTECTION_AFTER_FILL: "保护委托已通过资金检查",
  TAKE_PROFIT_1_AFTER_PROTECTION: "止盈一委托已通过资金检查",
  TAKE_PROFIT_2_AFTER_PROTECTION: "止盈二委托已通过资金检查",
  REDUCE_OR_CLOSE_POSITION: "减仓或平仓意图已通过资金检查",
  CANCEL_OPEN_RESPONSIBILITY: "撤单意图已通过资金检查",
};

const rejectedPlanEventLabels: Record<string, string> = {
  ENTRY_BREAKOUT: "入场意图未通过资金检查",
  PROTECTION_AFTER_FILL: "保护委托未通过资金检查",
  TAKE_PROFIT_1_AFTER_PROTECTION: "止盈一委托未通过资金检查",
  TAKE_PROFIT_2_AFTER_PROTECTION: "止盈二委托未通过资金检查",
  REDUCE_OR_CLOSE_POSITION: "减仓或平仓意图未通过资金检查",
  CANCEL_OPEN_RESPONSIBILITY: "撤单意图未通过资金检查",
};

export function planEventSummary(status: string, ruleId: string): string {
  if (status === "PROPOSED_ACTION_CAP_ACCEPTED") {
    return acceptedPlanEventLabels[ruleId] ?? "动作意图已通过资金检查";
  }
  if (status === "PROPOSED_ACTION_CAP_REJECTED") {
    return rejectedPlanEventLabels[ruleId] ?? "动作意图未通过资金检查";
  }
  if (status === "ENTRY_DEADLINE_EXPIRED") {
    return "入场截止时间已到，未创建交易动作";
  }
  if (status === "DEMO_ORDER_FLOW_CHECK") {
    return "Demo 下单流程验证";
  }
  return status;
}

export function observedOrderStateText(statusLabel: string): string {
  return statusLabel ? `曾收到订单状态 · ${statusLabel}` : "曾收到订单状态";
}

export function closedBarBreakoutGapPercent(
  direction: "LONG" | "SHORT",
  latestClose: string,
  boundary: string,
): string {
  const close = Number(latestClose);
  const breakoutBoundary = Number(boundary);
  if (!Number.isFinite(close) || close <= 0 || !Number.isFinite(breakoutBoundary)) {
    return "";
  }
  const gap = direction === "LONG"
    ? (breakoutBoundary - close) / close * 100
    : (close - breakoutBoundary) / close * 100;
  return String(gap);
}

export function entryExtensionBoundary(
  direction: "LONG" | "SHORT",
  channelBoundary: string,
  atr: string,
  multiple: string,
): number | null {
  const boundary = Number(channelBoundary);
  const atrValue = Number(atr);
  const multipleValue = Number(multiple);
  if (
    !Number.isFinite(boundary)
    || !Number.isFinite(atrValue)
    || atrValue <= 0
    || !Number.isFinite(multipleValue)
    || multipleValue < 0
  ) {
    return null;
  }
  return direction === "LONG"
    ? boundary + atrValue * multipleValue
    : boundary - atrValue * multipleValue;
}

export type ImmediateExitEstimate = {
  exitPrice: number;
  exitCommission: number;
  netResult: number;
};

export function estimateImmediateExit(
  positionQuantity: number,
  fillCashFlow: number,
  attributedCommission: number,
  bidPrice: number,
  askPrice: number,
  takerFeeRate: number,
): ImmediateExitEstimate | null {
  const values = [
    positionQuantity,
    fillCashFlow,
    attributedCommission,
    bidPrice,
    askPrice,
    takerFeeRate,
  ];
  if (
    values.some((value) => !Number.isFinite(value))
    || positionQuantity === 0
    || attributedCommission < 0
    || bidPrice <= 0
    || askPrice <= 0
    || askPrice < bidPrice
    || takerFeeRate < 0
  ) {
    return null;
  }
  const exitPrice = positionQuantity > 0 ? bidPrice : askPrice;
  const exitCommission = Math.abs(positionQuantity) * exitPrice * takerFeeRate;
  return {
    exitPrice,
    exitCommission,
    netResult: fillCashFlow
      + positionQuantity * exitPrice
      - attributedCommission
      - exitCommission,
  };
}
