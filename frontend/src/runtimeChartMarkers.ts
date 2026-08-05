export type RuntimeChartOperationCategory =
  | "ENTRY"
  | "EXIT"
  | "PROTECTION"
  | "TAKE_PROFIT"
  | "CANCEL"
  | "CONTROL"
  | "PLAN";

export type RuntimeChartOperationMarker = {
  id: string;
  at: string;
  label: string;
  shortLabel: string;
  detail: string;
  price: number | null;
  priceKind?: "TRADE" | "EVENT";
  category: RuntimeChartOperationCategory;
};

export function compactRuntimeMarkerGroupLabel(
  markers: RuntimeChartOperationMarker[],
): string {
  const counts = new Map<string, number>();
  markers.forEach((marker) => {
    counts.set(marker.shortLabel, (counts.get(marker.shortLabel) ?? 0) + 1);
  });
  const tokens = [...counts].map(([label, count]) => (
    count > 1 ? `${label}${count}` : label
  ));
  return tokens.length <= 3
    ? tokens.join("·")
    : `${tokens.slice(0, 2).join("·")}+${tokens.length - 2}`;
}

type RuntimeMarkerInputs = {
  activationStartedAt?: string;
  actions: Array<Record<string, unknown>>;
  facts: Array<Record<string, unknown>>;
  timeline: Array<Record<string, unknown>>;
};

const QUOTE_AMOUNT_FORMATTER = new Intl.NumberFormat("zh-CN", {
  minimumFractionDigits: 0,
  maximumFractionDigits: 4,
});

function recordOf(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null
    ? value as Record<string, unknown>
    : {};
}

function valueOf(
  record: Record<string, unknown> | undefined,
  key: string,
  fallback = "",
): string {
  const value = record?.[key];
  return value === null || value === undefined ? fallback : String(value);
}

function finitePrice(value: unknown): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function finiteNumber(value: unknown): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function invalidationMarkerEvidence(detail: Record<string, unknown>): {
  detail: string;
  price: number | null;
} {
  const capitalDecision = recordOf(detail.capital_decision);
  const evidence = recordOf(capitalDecision.evidence);
  const checks = Array.isArray(evidence.checks)
    ? evidence.checks.map(recordOf)
    : [];
  const priceCheck = checks.find((check) => valueOf(check, "kind") === "INVALIDATION_PRICE");
  const adverseMoveCheck = checks.find((check) => valueOf(check, "kind") === "ADVERSE_MOVE");
  const observedMarkPrice = finitePrice(priceCheck?.observed_mark_price);
  const configuredPrice = finitePrice(priceCheck?.configured_price);

  if (valueOf(priceCheck, "result").toUpperCase() === "TRUE" && observedMarkPrice !== null) {
    return {
      detail: configuredPrice === null
        ? `标记价 ${QUOTE_AMOUNT_FORMATTER.format(observedMarkPrice)} 已触发入场失效`
        : `标记价 ${QUOTE_AMOUNT_FORMATTER.format(observedMarkPrice)} 已达到失效边界 ${QUOTE_AMOUNT_FORMATTER.format(configuredPrice)}`,
      price: observedMarkPrice,
    };
  }

  if (valueOf(adverseMoveCheck, "result").toUpperCase() === "TRUE") {
    const observedMoveBps = finiteNumber(adverseMoveCheck?.observed_move_bps);
    const configuredMoveBps = finiteNumber(
      adverseMoveCheck?.configured_adverse_move_bps,
    );
    const windowSeconds = finiteNumber(adverseMoveCheck?.window_seconds);
    const direction = valueOf(adverseMoveCheck, "direction");
    const moveDirection = direction === "SHORT"
      ? "逆向上涨"
      : direction === "LONG"
        ? "逆向下跌"
        : "逆向变动";
    const detailParts = [
      windowSeconds === null ? "" : `${QUOTE_AMOUNT_FORMATTER.format(windowSeconds)} 秒`,
      observedMoveBps === null
        ? moveDirection
        : `${moveDirection} ${QUOTE_AMOUNT_FORMATTER.format(observedMoveBps)} bps`,
      configuredMoveBps === null
        ? "已触发入场失效"
        : `已达到 ${QUOTE_AMOUNT_FORMATTER.format(configuredMoveBps)} bps 失效阈值`,
    ].filter(Boolean);
    return {
      detail: detailParts.join(" · "),
      price: observedMarkPrice,
    };
  }

  return {
    detail: "价格已触发计划预设的失效边界",
    price: null,
  };
}

function actionCategory(kind: string): RuntimeChartOperationCategory {
  if (kind === "ENTRY") return "ENTRY";
  if (kind === "PROTECTION") return "PROTECTION";
  if (kind === "TAKE_PROFIT") return "TAKE_PROFIT";
  if (kind === "CANCEL") return "CANCEL";
  return "EXIT";
}

function actionLabel(kind: string, suffix = ""): string {
  const label = {
    ENTRY: "入场",
    CANCEL: "撤单",
    PROTECTION: "止损保护",
    TAKE_PROFIT: "止盈",
    RISK_REDUCTION: "减仓",
    EXIT: "退出",
    EXTERNAL_ACCOUNT_CLOSURE: "外部平仓",
  }[kind] ?? "执行动作";
  return `${label}${suffix}`;
}

function actionShortLabel(kind: string, terminalState = ""): string {
  if (terminalState === "REJECTED") return "拒";
  if (terminalState === "EXPIRED") return "逾";
  if (kind === "ENTRY") return terminalState ? "撤" : "委";
  if (kind === "PROTECTION") return terminalState ? "撤损" : "损";
  if (kind === "TAKE_PROFIT") return terminalState ? "撤盈" : "盈";
  if (kind === "CANCEL") return "撤";
  if (kind === "RISK_REDUCTION") return "减";
  return "出";
}

function shortenedIdentity(value: string): string {
  if (value.length <= 14) return value;
  return `${value.slice(0, 6)}…${value.slice(-5)}`;
}

function cancelTargetDetail(action: Record<string, unknown>): string {
  const target = recordOf(action.cancel_target);
  const clientOrderId = valueOf(target, "client_order_id");
  const endpoint = valueOf(target, "endpoint");
  if (!clientOrderId) return "撤销关联交易所委托";
  return [
    endpoint === "ALGO" ? "撤销条件委托" : "撤销普通委托",
    shortenedIdentity(clientOrderId),
  ].join(" · ");
}

function actionTermsDetail(action: Record<string, unknown>): string {
  const terms = recordOf(action.action_terms);
  if (valueOf(action, "action_kind") === "CANCEL") {
    return cancelTargetDetail(action);
  }
  const quantity = valueOf(terms, "quantity");
  const triggerPrice = valueOf(terms, "trigger_price");
  const price = valueOf(terms, "price");
  return [
    quantity ? `数量 ${quantity}` : "",
    triggerPrice ? `触发价 ${triggerPrice}` : price ? `委托价 ${price}` : "",
    terms.reduce_only === true ? "只减仓" : "",
  ].filter(Boolean).join(" · ");
}

function actionStateDetail(state: string): string {
  return {
    SUBMITTED: "已提交，等待场所结果",
    UNKNOWN: "场所结果待核对",
    HANDED_OVER: "已交由用户接管",
    CLOSED: "已完成",
  }[state] ?? "";
}

function fillDetail(
  payload: Record<string, unknown>,
  price: number | null,
  tradeId: string,
): string {
  const quantity = valueOf(payload, "last_quantity");
  const side = valueOf(payload, "order_side") === "BUY"
    ? "买入"
    : valueOf(payload, "order_side") === "SELL"
      ? "卖出"
      : "成交";
  const quoteAmount = price !== null && quantity
    ? price * Number(quantity)
    : Number.NaN;
  const liquidity = valueOf(payload, "liquidity_side");
  return [
    quantity
      ? [
        `${side} ${quantity}`,
        Number.isFinite(quoteAmount)
          ? `约 ${QUOTE_AMOUNT_FORMATTER.format(quoteAmount)} USDT`
          : "",
      ].filter(Boolean).join(" · ")
      : "",
    liquidity === "MAKER" ? "Maker" : liquidity === "TAKER" ? "Taker" : liquidity,
    tradeId ? `成交号 ${tradeId}` : "",
  ].filter(Boolean).join(" · ");
}

function actionMarkers(
  actions: Array<Record<string, unknown>>,
): RuntimeChartOperationMarker[] {
  return actions.flatMap((action) => {
    const actionId = valueOf(action, "execution_action_id");
    const kind = valueOf(action, "action_kind");
    const state = valueOf(action, "state");
    const at = valueOf(
      action,
      "call_started_at",
      valueOf(action, "created_at", valueOf(action, "updated_at")),
    );
    if (
      !actionId
      || !at
      || ![
        "ENTRY",
        "CANCEL",
        "PROTECTION",
        "TAKE_PROFIT",
        "RISK_REDUCTION",
        "EXIT",
        "EXTERNAL_ACCOUNT_CLOSURE",
      ].includes(kind)
      || ["READY", "NOT_SUBMITTED"].includes(state)
    ) {
      return [];
    }
    return [{
      id: `action:${actionId}`,
      at,
      label: actionLabel(kind, "委托"),
      shortLabel: actionShortLabel(kind),
      detail: [
        actionTermsDetail(action),
        actionStateDetail(state),
      ].filter(Boolean).join(" · "),
      // The action timestamp is the operation point. Its trigger/limit value is
      // already a separate horizontal price annotation, so the point itself is
      // anchored to the contemporaneous candle instead of distorting the scale.
      price: null,
      category: actionCategory(kind),
    }];
  });
}

function fillAndTerminalOrderMarkers(
  facts: Array<Record<string, unknown>>,
  actionsByRef: Map<string, Record<string, unknown>>,
): RuntimeChartOperationMarker[] {
  const markers = new Map<string, RuntimeChartOperationMarker>();
  facts.forEach((fact) => {
    const kind = valueOf(fact, "kind");
    const payload = recordOf(fact.payload);
    const actionRef = valueOf(fact, "action_ref");
    const action = actionsByRef.get(actionRef);
    const actionKind = valueOf(action, "action_kind");
    const sourceTime = valueOf(
      fact,
      "source_time",
      valueOf(fact, "cutoff", valueOf(fact, "received_at")),
    );
    if (!sourceTime) return;

    if (kind === "FILL") {
      const tradeId = valueOf(payload, "trade_id");
      const price = finitePrice(payload.last_price);
      const identity = `fill:${actionRef}:${tradeId || valueOf(fact, "venue_fact_id")}`;
      markers.set(identity, {
        id: identity,
        at: sourceTime,
        label: actionLabel(actionKind, "成交"),
        shortLabel: actionKind === "ENTRY"
          ? "入"
          : actionKind === "PROTECTION"
            ? "损"
            : actionKind === "TAKE_PROFIT"
              ? "盈"
              : actionKind === "RISK_REDUCTION"
                ? "减"
                : "出",
        detail: fillDetail(payload, price, tradeId),
        price,
        priceKind: price === null ? undefined : "TRADE",
        category: actionCategory(actionKind),
      });
      return;
    }

    if (
      kind !== "ORDER_STATE"
      || valueOf(fact, "source_class") !== "VENUE_STREAM"
      || payload.reconciliation === true
    ) {
      return;
    }
    const status = valueOf(payload, "status");
    if (!["CANCELLED", "CANCELED", "REJECTED", "EXPIRED"].includes(status)) return;
    const identity = `order-terminal:${actionRef}:${status}`;
    markers.set(identity, {
      id: identity,
      at: sourceTime,
      label: status === "REJECTED"
        ? `${actionLabel(actionKind)}被拒绝`
        : status === "EXPIRED"
          ? `${actionLabel(actionKind)}已过期`
          : `${actionLabel(actionKind)}已撤销`,
      shortLabel: actionShortLabel(actionKind, status),
      detail: [
        valueOf(payload, "reason"),
        valueOf(payload, "client_order_id")
          ? `委托 ${shortenedIdentity(valueOf(payload, "client_order_id"))}`
          : "",
      ].filter(Boolean).join(" · "),
      price: null,
      category: status === "CANCELLED" || status === "CANCELED"
        ? "CANCEL"
        : actionCategory(actionKind),
    });
  });
  return [...markers.values()];
}

function timelineMarkers(
  timeline: Array<Record<string, unknown>>,
): RuntimeChartOperationMarker[] {
  return timeline.flatMap<RuntimeChartOperationMarker>((item) => {
    const source = valueOf(item, "source");
    const at = valueOf(item, "at");
    const detail = recordOf(item.detail);
    if (!at) return [];
    if (source === "CONTROL_COMMAND" && valueOf(item, "status") === "EFFECTIVE") {
      const intent = valueOf(detail, "intent");
      const label = {
        STOP_NEW_RISK: "停止新增风险",
        EXIT_STRATEGY: "退出计划生效",
        USER_TAKEOVER: "用户接管生效",
      }[intent];
      if (!label) return [];
      return [{
        id: `control:${valueOf(item, "source_ref", at)}`,
        at,
        label,
        shortLabel: "控",
        detail: "控制命令已生效",
        price: null,
        category: "CONTROL" as const,
      }];
    }
    if (
      source === "PLAN_EVENT"
      && (
        valueOf(detail, "rule_id") === "ENTRY_MARKET_INVALIDATION"
        || valueOf(detail, "no_action_reason") === "ENTRY_MARKET_INVALIDATED"
      )
    ) {
      const invalidationEvidence = invalidationMarkerEvidence(detail);
      return [{
        id: `plan:${valueOf(item, "source_ref", at)}`,
        at,
        label: "行情失效，取消入场",
        shortLabel: "失效",
        detail: invalidationEvidence.detail,
        price: invalidationEvidence.price,
        priceKind: invalidationEvidence.price === null ? undefined : "EVENT",
        category: "PLAN" as const,
      }];
    }
    return [];
  });
}

export function runtimeChartOperationMarkers({
  activationStartedAt,
  actions,
  facts,
  timeline,
}: RuntimeMarkerInputs): RuntimeChartOperationMarker[] {
  const actionsByRef = new Map(actions.map((action) => [
    valueOf(action, "execution_action_id"),
    action,
  ]));
  return [
    ...(activationStartedAt ? [{
      id: `plan-start:${activationStartedAt}`,
      at: activationStartedAt,
      label: "计划开始",
      shortLabel: "起",
      detail: "计划已激活，开始按固定条件等待或执行",
      price: null,
      category: "PLAN" as const,
    }] : []),
    ...actionMarkers(actions),
    ...fillAndTerminalOrderMarkers(facts, actionsByRef),
    ...timelineMarkers(timeline),
  ].sort((left, right) => Date.parse(left.at) - Date.parse(right.at));
}
