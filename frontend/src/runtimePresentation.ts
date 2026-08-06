import { tradingPrice } from "./format";

export type CompactRuntimeTimelineItem = {
  item: Record<string, unknown>;
  fact?: Record<string, unknown>;
  repeatCount: number;
};

export type RuntimeEventCategory =
  | "PLAN"
  | "TRADING"
  | "PROTECTION"
  | "RECONCILIATION";

export type RuntimeTakeProfitGroup = {
  levelIndex: number | null;
  triggerR: string;
  prices: number[];
  workingOrderCount: number;
  orderCount: number;
};

export type RuntimeEntryConditionClause = {
  kind: "MARK_PRICE" | "CLOSED_BAR_PRICE_15M" | "SPREAD_BPS" | "PRICE_MOVE_BPS";
  comparator: string;
  value: string;
  windowSeconds: number | null;
};

export type RuntimeEntryConditionResult = "TRUE" | "FALSE" | "UNKNOWN";

export type RuntimeEntryConditionState = {
  kind: "DECISION_BASIS_READY" | RuntimeEntryConditionClause["kind"];
  comparator: string;
  threshold: string;
  windowSeconds: number | null;
  currentValue: string | null;
  result: RuntimeEntryConditionResult;
};

export type RuntimeEntryConditionEvaluation = {
  operator: "ALL" | "ANY";
  result: RuntimeEntryConditionResult;
  items: RuntimeEntryConditionState[];
};

export type RuntimeExecutorConditionStatus = {
  evaluation: RuntimeEntryConditionEvaluation;
  phase: "INITIAL" | "PRE_SUBMIT_RECHECK" | "LATER_LEG_RECHECK";
  sourceCutoff: string;
  evaluatedAt: string;
  submissionReady: boolean | null;
  blockingReason: string | null;
};

export type RuntimeNoActionPresentation = {
  headline: string;
  detail: string;
};

export type RuntimeNoActionContext = {
  entryOrderAttempted?: boolean;
  priorBlockingReason?: string;
  entryConditionsConfigured?: boolean;
};

export type RuntimeDynamicCancelPresentation = {
  headline: string;
  detail: string;
};

export type RuntimeEntryInterruptionPresentation =
  RuntimeDynamicCancelPresentation & {
    at: string;
  };

export type RuntimeWorkingEntryOrders = {
  count: number;
  complete: boolean;
};

export type RuntimeEntryPolicyRetryState = {
  latestEntryAction: Record<string, unknown> | null;
  latestRejectedFact: Record<string, unknown> | null;
  retryCount: number;
};

export type RuntimeEntryOrderDeadline = {
  submittedAt: string;
  ruleExpiresAt: string;
  effectiveDeadlineAt: string;
  expireAfterSeconds: number;
  limitedByPlanValidity: boolean;
};

export type RuntimeProtectionStepPresentation = {
  stepIndex: number;
  stepCount: number;
  triggerR: string;
  stopR: string;
  triggerPrice: number;
  stopPrice: number;
  crossed: boolean;
};

export type RuntimeProtectionAttention =
  | "NONE"
  | "EXIT_HANDOFF"
  | "UNEXPECTED_GAP";

export function runtimeHasEntryFill({
  projectedHasEntryFill,
  fillCount,
  attributedPositionQuantity,
}: {
  projectedHasEntryFill: boolean;
  fillCount: number;
  attributedPositionQuantity: number;
}): boolean {
  return projectedHasEntryFill
    || (Number.isFinite(fillCount) && fillCount > 0)
    || (
      Number.isFinite(attributedPositionQuantity)
      && attributedPositionQuantity !== 0
    );
}

export function runtimeHasPendingVenueAction(
  actions: ReadonlyArray<Record<string, unknown>>,
): boolean {
  return actions.some((action) =>
    ["SUBMITTING", "UNKNOWN", "OPEN"].includes(String(action.state ?? "")),
  );
}

export function runtimeActionHasCurrentResponsibility(
  action: Record<string, unknown>,
): boolean {
  return ["READY", "SUBMITTING", "UNKNOWN", "OPEN"].includes(
    String(action.state ?? ""),
  );
}

export function runtimeFilledEntryLegCount(
  actions: Array<Record<string, unknown>>,
  facts: Array<Record<string, unknown>>,
  plannedEntryLegCount: number,
): number {
  if (!Number.isInteger(plannedEntryLegCount) || plannedEntryLegCount <= 0) {
    return 0;
  }
  const legKeyByActionId = new Map(
    actions.flatMap((action) => {
      if (valueOf(action, "action_kind") !== "ENTRY") return [];
      const actionId = valueOf(action, "execution_action_id");
      if (!actionId) return [];
      const schedule = recordOf(
        recordOf(recordOf(action.action_terms).execution_context).order_schedule,
      );
      const legIndex = Number(schedule.leg_index);
      return [[
        actionId,
        Number.isInteger(legIndex) && legIndex >= 0
          ? `leg:${legIndex}`
          : `action:${actionId}`,
      ] as const];
    }),
  );
  const filledLegs = new Set(
    facts.flatMap((fact) => {
      if (valueOf(fact, "kind") !== "FILL") return [];
      const legKey = legKeyByActionId.get(valueOf(fact, "action_ref"));
      return legKey ? [legKey] : [];
    }),
  );
  return Math.min(plannedEntryLegCount, filledLegs.size);
}

export type RuntimeEntryConditionFacts = {
  basisReady: boolean | null;
  referencePrice: string | null;
  closedBar15mClose: string | null;
  spreadBps: number | null;
  priceMoveBpsByWindow: Readonly<Record<string, string>>;
};

const exitReasonLabels: Array<[token: string, label: string]> = [
  ["PROTECTION_RESULT_UNKNOWN", "保护结果未知紧急退出"],
  ["PROTECTION_GAP", "保护缺口紧急退出"],
  ["DIRECT_TIME_EXIT", "持仓到期退出"],
  ["ENTRY_CYCLE_CLOSED", "入场周期结束退出"],
  ["PLAN_EXIT", "计划退出"],
];

export function runtimeProtectionAttention({
  hasEntryFill,
  tradeClosed,
  protectionState,
  lifecycle,
  exitActionStarted = false,
  firstFillAt,
  timeExitSeconds,
  nowMs,
}: {
  hasEntryFill: boolean;
  tradeClosed: boolean;
  protectionState: string;
  lifecycle: string;
  exitActionStarted?: boolean;
  firstFillAt: string;
  timeExitSeconds: number | null;
  nowMs: number;
}): RuntimeProtectionAttention {
  if (!hasEntryFill || tradeClosed || lifecycle === "COMPLETED") return "NONE";
  const firstFillMs = Date.parse(firstFillAt);
  const timeExitDue = timeExitSeconds !== null
    && Number.isFinite(timeExitSeconds)
    && timeExitSeconds > 0
    && Number.isFinite(firstFillMs)
    && nowMs >= firstFillMs + timeExitSeconds * 1_000;
  if (lifecycle === "EXITING" || exitActionStarted || timeExitDue) {
    return "EXIT_HANDOFF";
  }
  return ["WORKING", "CLOSED"].includes(protectionState)
    ? "NONE"
    : "UNEXPECTED_GAP";
}

const noActionReasonLabels: Record<string, string> = {
  ENTRY_EXTENSION_LIMIT_EXCEEDED: "执行前价格已超过计划的最大追价边界",
  ENTRY_SPREAD_TOO_WIDE: "当前买卖价差超过入场上限",
  STREAM_FACTS_STALE: "最新盘口或标记价格已经过期",
  STREAM_FACTS_UNKNOWN: "最新盘口或标记价格暂不可确认",
  TOP_OF_BOOK_UNKNOWN: "当前买一卖一暂不可确认",
  TOP_OF_BOOK_INVALID: "当前买一卖一数据无效",
  MARK_PRICE_STALE: "当前标记价格已经过期",
  PROPOSAL_EXPIRED: "本次入场意图已超过有效时间",
  ACCOUNT_FACT_QUERY_STALE: "账户事实已过期",
  ACCOUNT_FACT_QUERY_FAILED_TIMEOUT: "账户事实查询超时",
  ACCOUNT_TRADING_DISABLED: "账户当前不可交易",
  ACCOUNT_MARGIN_MODE_NOT_ISOLATED: "当前交易对不是逐仓保证金模式",
  ACCOUNT_AUTO_ADD_MARGIN_NOT_DISABLED: "当前交易对仍开启自动追加保证金",
  ACCOUNT_LEVERAGE_UNKNOWN: "当前杠杆设置无法确认",
  ACCOUNT_POSITION_MODE_UNSUPPORTED: "当前持仓模式不受本计划支持",
  ACCOUNT_MULTI_ASSET_MODE_UNSUPPORTED: "当前账户仍启用多资产保证金模式",
  ENTRY_OPEN_ORDER_CONFLICT: "当前交易对存在无法归属的开放委托",
  ENTRY_OPEN_ALGO_ORDER_CONFLICT: "当前交易对存在无法归属的条件委托",
  POSITION_ATTRIBUTION_UNKNOWN: "当前持仓无法安全归属到本计划",
  POSITION_DIRECTION_CONFLICT: "当前持仓方向与计划冲突",
  INSTRUMENT_RULES_UNKNOWN: "交易对精度与最小下单规则暂不可确认",
  INSTRUMENT_RULES_DRIFT: "交易对规则已变化，需要按最新规则重新核对",
  ENTRY_SIZING_FACTS_UNKNOWN: "下单金额所需的账户事实暂不可确认",
};

export function currentRuntimeProtectionPrice(
  actions: Array<Record<string, unknown>>,
  direction: string,
): number | null {
  const prices = actions
    .filter((action) =>
      valueOf(action, "action_kind") === "PROTECTION"
      && valueOf(action, "state") === "OPEN"
    )
    .map((action) => Number(recordOf(action.action_terms).trigger_price))
    .filter((price) => Number.isFinite(price) && price > 0);
  if (prices.length === 0) return null;
  return direction === "SHORT" ? Math.min(...prices) : Math.max(...prices);
}

export function nextRuntimeProtectionStep(
  scheduleSpec: Record<string, unknown>,
  ruleState: Record<string, unknown>,
  actions: Array<Record<string, unknown>>,
  facts: Array<Record<string, unknown>>,
  direction: string,
  referencePrice: number,
): RuntimeProtectionStepPresentation | null {
  const steppedRule = (Array.isArray(scheduleSpec.dynamic_rules)
    ? scheduleSpec.dynamic_rules
    : [])
    .map(recordOf)
    .find((rule) => valueOf(rule, "kind") === "STEPPED_PROTECTION");
  const steps = steppedRule && Array.isArray(steppedRule.steps)
    ? steppedRule.steps.map(recordOf)
    : [];
  if (steps.length === 0) return null;

  const acceptedStepIndices = actions.flatMap((action) => {
    if (valueOf(action, "action_kind") !== "PROTECTION") return [];
    const actionId = valueOf(action, "execution_action_id");
    const venueAccepted = valueOf(action, "state") === "OPEN"
      || facts.some((fact) => {
        if (valueOf(fact, "action_ref") !== actionId) return false;
        if (valueOf(fact, "kind") === "FILL") return true;
        if (valueOf(fact, "kind") !== "ORDER_STATE") return false;
        return ["WORKING", "PARTIALLY_FILLED", "FILLED"].includes(
          valueOf(recordOf(fact.payload), "status"),
        );
      });
    if (!venueAccepted) return [];
    const context = recordOf(recordOf(action.action_terms).execution_context);
    const replacement = recordOf(context.protection_replacement);
    const stepIndex = Number(replacement.step_index);
    return Number.isInteger(stepIndex) && stepIndex >= 0 ? [stepIndex] : [];
  });
  const appliedStepIndex = acceptedStepIndices.length > 0
    ? Math.max(...acceptedStepIndices)
    : -1;
  const stepIndex = appliedStepIndex + 1;
  const step = steps[stepIndex];
  if (!step) return null;

  const protectionState = recordOf(ruleState.direct_protection);
  const anchorPrice = Number(protectionState.anchor_price);
  const riskDistance = Number(protectionState.anchor_r);
  const triggerR = valueOf(step, "trigger_r");
  const stopR = valueOf(step, "stop_r");
  const triggerMultiple = Number(triggerR);
  const stopMultiple = Number(stopR);
  if (
    !Number.isFinite(anchorPrice)
    || anchorPrice <= 0
    || !Number.isFinite(riskDistance)
    || riskDistance <= 0
    || !Number.isFinite(triggerMultiple)
    || !Number.isFinite(stopMultiple)
  ) return null;

  const short = direction === "SHORT";
  const triggerPrice = anchorPrice
    + (short ? -1 : 1) * triggerMultiple * riskDistance;
  const stopPrice = anchorPrice
    + (short ? -1 : 1) * stopMultiple * riskDistance;
  return {
    stepIndex,
    stepCount: steps.length,
    triggerR,
    stopR,
    triggerPrice,
    stopPrice,
    crossed: Number.isFinite(referencePrice)
      && (short ? referencePrice <= triggerPrice : referencePrice >= triggerPrice),
  };
}

function runtimeEvidenceNumber(value: unknown): string {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return String(value ?? "");
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: 8,
  }).format(numeric);
}

function runtimeEvidencePrice(
  value: unknown,
  tickSize?: string | null,
): string {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return String(value ?? "");
  return tradingPrice(String(value), tickSize);
}

function entryInvalidationPresentation(
  detail: Record<string, unknown>,
  tickSize?: string | null,
): RuntimeNoActionPresentation | null {
  const capitalDecision = recordOf(detail.capital_decision);
  const evidence = recordOf(capitalDecision.evidence);
  const checks = Array.isArray(evidence.checks)
    ? evidence.checks.map(recordOf)
    : [];
  const triggered = checks.find((check) => valueOf(check, "result") === "TRUE");
  if (!triggered) return null;

  const kind = valueOf(triggered, "kind");
  if (kind === "INVALIDATION_PRICE") {
    const observed = runtimeEvidencePrice(
      triggered.observed_mark_price,
      tickSize,
    );
    const configured = runtimeEvidencePrice(
      triggered.configured_price,
      tickSize,
    );
    if (observed && configured) {
      return {
        headline: "价格已突破失效位，取消入场",
        detail: `标记价 ${observed} USDT 已到达失效边界 ${configured} USDT；未形成交易所风险`,
      };
    }
  }
  if (kind === "OPPORTUNITY_MISSED_PRICE") {
    const observed = runtimeEvidencePrice(
      triggered.observed_mark_price,
      tickSize,
    );
    const configured = runtimeEvidencePrice(
      triggered.configured_price,
      tickSize,
    );
    if (observed && configured) {
      return {
        headline: "价格已错过机会边界，取消入场",
        detail: `标记价 ${observed} USDT 已到达机会错过边界 ${configured} USDT；未形成交易所风险`,
      };
    }
  }
  if (kind === "ADVERSE_MOVE") {
    const windowSeconds = runtimeEvidenceNumber(triggered.window_seconds);
    const observed = runtimeEvidenceNumber(triggered.observed_move_bps);
    const configured = runtimeEvidenceNumber(
      triggered.configured_adverse_move_bps,
    );
    if (windowSeconds && observed && configured) {
      return {
        headline: "短时反向异动触发，取消入场",
        detail: `${windowSeconds} 秒价格变动 ${observed} bps 已达到不利异动阈值 ${configured} bps；未形成交易所风险`,
      };
    }
  }
  return null;
}

export function runtimeNoActionPresentation(
  reason: string,
  detail: Record<string, unknown> = {},
  priceTickSize?: string | null,
  context: RuntimeNoActionContext = {},
): RuntimeNoActionPresentation {
  if (reason === "EXECUTOR_RUNTIME_REATTACHED") {
    return {
      headline: "执行器连接已恢复",
      detail: "实时价格变动窗口从此时重新累计；新增入场暂停不会因本事件自动解除",
    };
  }
  if (reason === "ENTRY_MARKET_INVALIDATED") {
    return entryInvalidationPresentation(detail, priceTickSize) ?? {
      headline: "行情已使入场思路失效",
      detail: "本次入场机会已永久取消；没有形成新的交易所风险",
    };
  }
  if (reason === "ENTRY_WINDOW_EXPIRED") {
    const priorBlockingHeadline = context.priorBlockingReason
      ? noActionReasonLabels[context.priorBlockingReason]
      : "";
    return {
      headline: "入场窗口已结束",
      detail: context.entryOrderAttempted
        ? "此前已有入场订单尝试；窗口结束后，未成交订单与剩余入场已按计划停止"
        : priorBlockingHeadline
          ? `窗口结束前最后一次记录的明确阻断为“${priorBlockingHeadline}”；未形成交易所订单`
        : context.entryConditionsConfigured
          ? "条件未在有效期内同时满足，因此未提交订单"
          : "现有事实未记录订单尝试或明确阻断，无法确定未提交原因",
    };
  }
  if (reason === "ENTRY_REMAINING_EXPIRED") {
    return {
      headline: "未成交委托等待期已结束",
      detail: "入场机会已关闭；开放委托将按计划撤销",
    };
  }
  const knownHeadline = noActionReasonLabels[reason];
  if (knownHeadline) {
    return {
      headline: knownHeadline,
      detail: "未下单；系统会在后续执行周期重新核对",
    };
  }
  if (reason.startsWith("MARK_PRICE_QUERY_FAILED_")) {
    return {
      headline: "标记价格查询暂时失败",
      detail: "未下单；系统会自动重试，不影响已有委托与保护",
    };
  }
  if (reason.startsWith("ACCOUNT_FACT_QUERY_FAILED_")) {
    return {
      headline: "账户与持仓查询暂时失败",
      detail: "未下单；系统会自动重试，不影响已有委托与保护",
    };
  }
  if (reason.startsWith("INSTRUMENT_RULES_QUERY_FAILED_")) {
    return {
      headline: "交易规则查询暂时失败",
      detail: "未下单；系统会自动重试，不影响已有委托与保护",
    };
  }
  return {
    headline: "本次执行条件暂不可确认",
    detail: "未下单；技术原因可在补充诊断中查看",
  };
}

export function runtimeWorkingEntryOrders(
  actions: Array<Record<string, unknown>>,
  facts: Array<Record<string, unknown>>,
): RuntimeWorkingEntryOrders {
  const entryActionIds = new Set(
    actions
      .filter((action) => valueOf(action, "action_kind") === "ENTRY")
      .map((action) => valueOf(action, "execution_action_id"))
      .filter(Boolean),
  );
  const latestByAction = new Map<string, {
    status: string;
    atMs: number;
    order: number;
  }>();
  const fullyFilledActionIds = new Set<string>();

  facts.forEach((fact, order) => {
    const actionRef = valueOf(fact, "action_ref");
    if (!entryActionIds.has(actionRef)) return;
    const payload = recordOf(fact.payload);
    if (valueOf(fact, "kind") === "FILL") {
      const leavesQuantity = Number(payload.leaves_quantity);
      if (Number.isFinite(leavesQuantity) && leavesQuantity <= 0) {
        fullyFilledActionIds.add(actionRef);
      }
      return;
    }
    if (valueOf(fact, "kind") !== "ORDER_STATE") return;
    const status = valueOf(payload, "status");
    if (!status) return;
    const parsedAt = Date.parse(
      valueOf(
        fact,
        "cutoff",
        valueOf(fact, "occurred_at", valueOf(fact, "recorded_at")),
      ),
    );
    const atMs = Number.isFinite(parsedAt) ? parsedAt : Number.NEGATIVE_INFINITY;
    const current = latestByAction.get(actionRef);
    if (
      current
      && (current.atMs > atMs || (current.atMs === atMs && current.order > order))
    ) {
      return;
    }
    latestByAction.set(actionRef, { status, atMs, order });
  });

  return {
    count: [...latestByAction.entries()].filter(([actionRef, { status }]) => (
      !fullyFilledActionIds.has(actionRef)
      && (status === "WORKING" || status === "PARTIALLY_FILLED")
    )).length,
    complete: [...entryActionIds].every(
      (actionRef) => latestByAction.has(actionRef) || fullyFilledActionIds.has(actionRef),
    ),
  };
}

/**
 * Distinguish an entry window that expired before any venue call from one that
 * expired after an entry order had already reached the venue. This prevents a
 * terminal plan event from claiming "no order was submitted" while its own
 * timeline contains an accepted, rejected, or otherwise acknowledged order.
 */
export function runtimeEntryOrderAttemptedBefore(
  actions: Array<Record<string, unknown>>,
  facts: Array<Record<string, unknown>>,
  cutoff: string,
): boolean {
  const cutoffMs = Date.parse(cutoff);
  if (!Number.isFinite(cutoffMs)) return false;
  const entryActionIds = new Set(
    actions
      .filter((action) => valueOf(action, "action_kind") === "ENTRY")
      .map((action) => valueOf(action, "execution_action_id"))
      .filter(Boolean),
  );
  return facts.some((fact) => {
    if (
      valueOf(fact, "kind") !== "ORDER_STATE"
      || !entryActionIds.has(valueOf(fact, "action_ref"))
    ) {
      return false;
    }
    const factAt = Date.parse(
      valueOf(
        fact,
        "cutoff",
        valueOf(fact, "occurred_at", valueOf(fact, "recorded_at")),
      ),
    );
    return Number.isFinite(factAt) && factAt <= cutoffMs;
  });
}

/**
 * A terminal activation can only be presented as "no fill" when every entry
 * action is known not to have reached the venue, or has explicit closure
 * evidence. User handover closes Halpha's responsibility, but it does not
 * resolve the result of a venue call that had already started.
 */
export function terminalEntryResultRequiresReview(
  actions: Array<Record<string, unknown>>,
): boolean {
  return actions.some((action) => {
    if (valueOf(action, "action_kind") !== "ENTRY") return false;
    const state = valueOf(action, "state");
    if (["SUBMITTING", "UNKNOWN", "OPEN"].includes(state)) return true;
    return state === "HANDED_OVER" && Boolean(valueOf(action, "call_started_at"));
  });
}

const ENTRY_POLICY_RETRY_REASONS = new Set([
  "POST_ONLY_WOULD_TAKE_RACE",
  "PRICE_MATCH_TEMPORARILY_UNAVAILABLE",
]);

function runtimeActionSequence(
  action: Record<string, unknown>,
): [number, number, number, string] {
  const createdAt = Date.parse(valueOf(action, "created_at"));
  const schedule = recordOf(
    recordOf(recordOf(action.action_terms).execution_context).order_schedule,
  );
  const legIndex = Number(schedule.leg_index);
  const attemptIndex = Number(schedule.attempt_index);
  return [
    Number.isFinite(createdAt) ? createdAt : Number.NEGATIVE_INFINITY,
    Number.isFinite(legIndex) ? legIndex : -1,
    Number.isFinite(attemptIndex) ? attemptIndex : -1,
    valueOf(action, "execution_action_id"),
  ];
}

function compareRuntimeActionSequence(
  left: Record<string, unknown>,
  right: Record<string, unknown>,
): number {
  const leftSequence = runtimeActionSequence(left);
  const rightSequence = runtimeActionSequence(right);
  for (const index of [0, 1, 2] as const) {
    if (leftSequence[index] !== rightSequence[index]) {
      return leftSequence[index] - rightSequence[index];
    }
  }
  return leftSequence[3].localeCompare(rightSequence[3]);
}

function runtimeFactSequence(fact: Record<string, unknown>): [number, string] {
  const cutoff = Date.parse(valueOf(fact, "cutoff"));
  return [
    Number.isFinite(cutoff) ? cutoff : Number.NEGATIVE_INFINITY,
    valueOf(fact, "venue_fact_id"),
  ];
}

/**
 * Rejection notices describe the latest entry action only. An older normal
 * rejection must disappear after a retry becomes working or reaches a newer
 * terminal result. Retry count intentionally follows the executor's bounded
 * policy across the whole frozen schedule instead of using one leg's attempt
 * index.
 */
export function runtimeEntryPolicyRetryState(
  actions: Array<Record<string, unknown>>,
  facts: Array<Record<string, unknown>>,
): RuntimeEntryPolicyRetryState {
  const entryActions = actions
    .filter((action) => valueOf(action, "action_kind") === "ENTRY");
  const retryCount = entryActions.filter((action) => {
    const schedule = recordOf(
      recordOf(recordOf(action.action_terms).execution_context).order_schedule,
    );
    return ENTRY_POLICY_RETRY_REASONS.has(valueOf(schedule, "retry_reason"));
  }).length;
  const latestEntryAction = entryActions
    .slice()
    .sort(compareRuntimeActionSequence)
    .at(-1) ?? null;
  if (!latestEntryAction) {
    return { latestEntryAction: null, latestRejectedFact: null, retryCount };
  }

  const latestActionId = valueOf(latestEntryAction, "execution_action_id");
  const latestRejectedFact = facts
    .filter((fact) => (
      valueOf(fact, "action_ref") === latestActionId
      && valueOf(fact, "kind") === "ORDER_STATE"
      && valueOf(recordOf(fact.payload), "status") === "REJECTED"
    ))
    .sort((left, right) => {
      const leftSequence = runtimeFactSequence(left);
      const rightSequence = runtimeFactSequence(right);
      if (leftSequence[0] !== rightSequence[0]) {
        return leftSequence[0] - rightSequence[0];
      }
      return leftSequence[1].localeCompare(rightSequence[1]);
    })
    .at(-1) ?? null;
  return { latestEntryAction, latestRejectedFact, retryCount };
}

function recordOf(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
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

/**
 * A generic "cancel" label hides whether the plan behaved as configured.
 * Resolve the persisted execution causation against the frozen schedule so the
 * user can see the economic reason without exposing internal action ids.
 */
export function runtimeDynamicCancelPresentation(
  action: Record<string, unknown>,
  orderSchedule: Record<string, unknown>,
): RuntimeDynamicCancelPresentation | null {
  if (valueOf(action, "action_kind") !== "CANCEL") return null;

  const terms = recordOf(action.action_terms);
  const causationRef = valueOf(
    terms,
    "causation_ref",
    valueOf(action, "source_identity"),
  );
  const spec = recordOf(orderSchedule.schedule_spec);
  const scheduleSpec = Object.keys(spec).length > 0 ? spec : orderSchedule;
  const dynamicRules = Array.isArray(scheduleSpec.dynamic_rules)
    ? scheduleSpec.dynamic_rules.map(recordOf)
    : [];

  if (
    causationRef.includes("DIRECT_ENTRY_INVALIDATION_STATUS_UNKNOWN")
    || causationRef.includes("DIRECT_ENTRY_SHOCK_STATUS_UNKNOWN")
  ) {
    return {
      headline: "行情数据中断，未成交挂单已撤销",
      detail: "入场失效条件暂时无法核对；为避免在失去监控时继续成交，系统撤销了当前挂单",
    };
  }

  if (
    causationRef.includes("DIRECT_ENTRY_SHOCK")
    || causationRef.includes("DIRECT_ENTRY_INVALIDATION_PRICE")
    || causationRef.includes("DIRECT_ENTRY_OPPORTUNITY_MISSED_PRICE")
  ) {
    const shock = dynamicRules.find(
      (rule) => valueOf(rule, "kind") === "CANCEL_ON_SHOCK",
    );
    const windowSeconds = valueOf(shock, "window_seconds");
    const adverseMoveBps = valueOf(shock, "adverse_move_bps");
    const invalidationPrice = valueOf(shock, "invalidation_price");
    const opportunityMissedPrice = valueOf(
      shock,
      "opportunity_missed_price",
    );
    const fixedPriceTriggered = causationRef.includes(
      "DIRECT_ENTRY_INVALIDATION_PRICE",
    );
    const opportunityMissed = causationRef.includes(
      "DIRECT_ENTRY_OPPORTUNITY_MISSED_PRICE",
    );
    return {
      headline: opportunityMissed
        ? "价格已走远，本次入场机会已取消"
        : fixedPriceTriggered
          ? "价格突破失效位，入场已取消"
          : "短时不利异动已触发撤单",
      detail: opportunityMissed && opportunityMissedPrice
        ? `标记价到达机会错过边界 ${opportunityMissedPrice} USDT；已终止未成交入场`
        : fixedPriceTriggered && invalidationPrice
        ? `标记价到达固定失效位 ${invalidationPrice} USDT；已终止未成交入场`
        : windowSeconds && adverseMoveBps
          ? `${windowSeconds} 秒内不利变动达到 ${adverseMoveBps} bps；已终止未成交入场`
          : "行情达到计划失效阈值；已终止未成交入场",
    };
  }

  if (causationRef.includes("DIRECT_ENTRY_REMAINING_EXPIRED")) {
    const expiry = dynamicRules.find(
      (rule) => valueOf(rule, "kind") === "EXPIRE_REMAINING",
    );
    const afterSeconds = valueOf(expiry, "after_seconds");
    return {
      headline: "未成交委托已到期撤销",
      detail: afterSeconds
        ? `首次提交后 ${afterSeconds} 秒仍未成交；已撤销剩余入场委托`
        : "等待时间达到计划上限；已撤销剩余入场委托",
    };
  }

  if (causationRef.includes("DIRECT_ENTRY_REPRICE")) {
    const reprice = dynamicRules.find(
      (rule) => valueOf(rule, "kind") === "REPRICE_ENTRY",
    );
    const triggerDistanceBps = valueOf(reprice, "trigger_distance_bps");
    const state = valueOf(action, "state");
    return {
      headline: state === "CLOSED"
        ? "移动挂单触发，旧委托撤销已核对闭合"
        : state
          ? "移动挂单触发，正在撤销旧委托"
          : "移动挂单触发，准备撤销旧委托",
      detail: triggerDistanceBps
        ? `盘口偏离达到 ${triggerDistanceBps} bps；撤销后重新核对入场条件与重挂上限，不保证一定产生新委托`
        : "盘口已偏离原委托；撤销后重新核对入场条件与重挂上限，不保证一定产生新委托",
    };
  }

  if (causationRef.includes("DIRECT_TIME_SLICE_EXPIRED")) {
    const expiry = dynamicRules.find(
      (rule) => valueOf(rule, "kind") === "EXPIRE_REMAINING",
    );
    const afterSeconds = valueOf(expiry, "after_seconds");
    return {
      headline: "本批未成交委托已到期撤销",
      detail: afterSeconds
        ? `本批提交后 ${afterSeconds} 秒仍未成交；撤单闭合后继续按原计划处理剩余批次`
        : "本批等待时间已到；撤单闭合后继续按原计划处理剩余批次",
    };
  }

  return null;
}

/**
 * A scheduled entry leg can become terminal before it is ever sent to the
 * venue. Present the configured market invalidation instead of the generic
 * "not submitted" state, while keeping already-filled exposure semantics
 * explicit.
 */
export function runtimeNotSubmittedEntryPresentation(
  action: Record<string, unknown>,
  orderSchedule: Record<string, unknown>,
): RuntimeDynamicCancelPresentation | null {
  if (
    valueOf(action, "action_kind") !== "ENTRY"
    || valueOf(action, "state") !== "NOT_SUBMITTED"
  ) {
    return null;
  }

  const reason = valueOf(action, "not_submitted_reason");
  const supportedReasons = [
    "DIRECT_ENTRY_SHOCK",
    "DIRECT_ENTRY_INVALIDATION_PRICE",
    "DIRECT_ENTRY_OPPORTUNITY_MISSED_PRICE",
    "DIRECT_ENTRY_SHOCK_STATUS_UNKNOWN",
    "DIRECT_ENTRY_INVALIDATION_STATUS_UNKNOWN",
  ];
  if (!supportedReasons.includes(reason)) return null;

  const base = runtimeDynamicCancelPresentation({
    action_kind: "CANCEL",
    source_identity: `DIRECT_DYNAMIC:${reason}`,
  }, orderSchedule);
  if (!base) return null;

  const headline = reason.includes("STATUS_UNKNOWN")
    ? "行情数据中断，剩余入场已取消"
    : reason === "DIRECT_ENTRY_SHOCK"
      ? "短时反向异动触发，剩余入场已取消"
      : reason === "DIRECT_ENTRY_INVALIDATION_PRICE"
        ? "价格突破失效位，剩余入场已取消"
        : "价格已走远，剩余入场已取消";
  const detail = reason.includes("STATUS_UNKNOWN")
    ? "入场失效条件暂时无法核对；未释放批次不再提交"
    : base.detail.replace("已终止未成交入场", "未释放批次不再提交");

  return {
    headline,
    detail: `${detail}；已成交仓位继续按原保护与退出计划处理`,
  };
}

export function runtimePlanEventDynamicCancelPresentation(
  detail: Record<string, unknown>,
  orderSchedule: Record<string, unknown>,
): RuntimeDynamicCancelPresentation | null {
  if (valueOf(detail, "rule_id") !== "CANCEL_OPEN_RESPONSIBILITY") {
    return null;
  }
  const sourceIdentity = valueOf(detail, "source_identity");
  if (!sourceIdentity) return null;
  return runtimeDynamicCancelPresentation({
    action_kind: "CANCEL",
    source_identity: sourceIdentity,
  }, orderSchedule);
}

export function runtimeEntryInterruptionPresentation(
  timeline: Array<Record<string, unknown>>,
  orderSchedule: Record<string, unknown>,
): RuntimeEntryInterruptionPresentation | null {
  for (const item of [...timeline].reverse()) {
    if (valueOf(item, "source") !== "PLAN_EVENT") continue;
    const detail = recordOf(item.detail);
    const sourceIdentity = valueOf(detail, "source_identity");
    // A time-slice timeout or reprice closes only the current responsibility;
    // later slices or the replacement order still belong to the same active
    // entry program. Keep those events in history without presenting the
    // whole program as terminally interrupted.
    if (
      sourceIdentity.includes("DIRECT_TIME_SLICE_EXPIRED")
      || sourceIdentity.includes("DIRECT_ENTRY_REPRICE")
    ) continue;
    const presentation = runtimePlanEventDynamicCancelPresentation(
      detail,
      orderSchedule,
    );
    if (!presentation) continue;
    return {
      ...presentation,
      at: valueOf(item, "at"),
    };
  }
  return null;
}

export function reviewExitReason(
  result: Record<string, unknown>,
  actions: Array<Record<string, unknown>> = [],
): string {
  const fills = Array.isArray(result.fills)
    ? result.fills.map(recordOf)
    : [];
  const exitFill = [...fills]
    .reverse()
    .find((fill) => valueOf(fill, "action_kind") !== "ENTRY");
  const kind = valueOf(exitFill, "action_kind", "UNKNOWN");
  if (kind === "TAKE_PROFIT") return "止盈订单成交";
  if (kind === "PROTECTION") return "保护止损";
  if (kind === "EXTERNAL_ACCOUNT_CLOSURE") return "外部应急平仓";
  if (kind === "RISK_REDUCTION") return "风险减仓";
  if (kind !== "EXIT") return "未知";

  const exitAction = [...actions]
    .reverse()
    .find((action) => valueOf(action, "action_kind") === "EXIT");
  const terms = recordOf(exitAction?.action_terms);
  const causationRef = valueOf(terms, "causation_ref");
  return exitReasonLabels.find(([token]) => causationRef.includes(token))?.[1]
    ?? "计划退出";
}

export function activationSummaryCloseReason(
  activation: Record<string, unknown>,
): string {
  const result = recordOf(activation.trade_result);
  const fills = Array.isArray(result.fills)
    ? result.fills.map(recordOf)
    : [];
  const closingFill = [...fills]
    .reverse()
    .find((fill) => valueOf(fill, "action_kind") !== "ENTRY");
  const closingKind = valueOf(closingFill, "action_kind");
  if (closingKind === "TAKE_PROFIT") return "止盈订单成交";
  if (closingKind === "PROTECTION") return "保护止损";
  if (closingKind === "EXTERNAL_ACCOUNT_CLOSURE") return "外部应急平仓";
  if (closingKind === "RISK_REDUCTION") return "风险减仓";

  const reason = valueOf(activation, "closure_reason_code");
  if (reason.includes("ENTRY_MARKET_INVALIDATED")) return "行情失效，取消入场";
  if (reason.includes("ENTRY_WINDOW_EXPIRED")) return "入场窗口结束，未下单";
  if (reason.includes("EXIT_STRATEGY")) return "计划退出";
  if (reason.includes("USER_TAKEOVER")) return "用户接管";
  const knownExit = exitReasonLabels.find(([token]) => reason.includes(token));
  if (knownExit) return knownExit[1];
  if (closingKind === "EXIT") return "计划退出";

  const primaryResult = valueOf(activation, "primary_result");
  if (primaryResult === "NO_ACTION") return "未发生交易";
  if (primaryResult === "HANDED_OVER") return "用户接管";
  if (primaryResult === "RESULT_UNKNOWN") return "结果待核对";
  if (primaryResult === "PARTIAL") return "部分结果";
  if (primaryResult === "COMPLETED") return "计划已闭合";
  return valueOf(activation, "lifecycle") === "COMPLETED"
    ? "关闭原因待核对"
    : "仍在运行";
}

function normalizedDecimalKey(value: string): string {
  if (!/^[+-]?\d+(?:\.\d+)?$/.test(value.trim())) return value.trim();
  const [integer = "", fraction = ""] = value.trim().split(".", 2);
  const normalizedFraction = fraction.replace(/0+$/, "");
  return normalizedFraction ? `${integer}.${normalizedFraction}` : integer;
}

function compactableOrderStateKey(
  item: Record<string, unknown>,
  fact: Record<string, unknown> | undefined,
): string | null {
  const sourceClass = valueOf(fact, "source_class");
  const payload = recordOf(fact?.payload);
  if (
    valueOf(item, "source") !== "VENUE_FACT"
    || valueOf(fact, "kind") !== "ORDER_STATE"
    || (
      sourceClass !== "VENUE_QUERY"
      && !(
        sourceClass === "VENUE_STREAM"
        && valueOf(payload, "event_type") === "OrderUpdated"
      )
    )
  ) {
    return null;
  }
  return [
    sourceClass,
    valueOf(fact, "action_ref"),
    valueOf(payload, "status"),
    valueOf(payload, "event_type"),
    normalizedDecimalKey(valueOf(payload, "venue_order_quantity")),
    valueOf(payload, "venue_order_ref"),
    valueOf(payload, "reason"),
  ].join("|");
}

/**
 * Repeated order queries and unchanged venue-stream updates are preserved by
 * the backend, but a runtime screen should not make them look like separate
 * economic events. Keep only the latest equivalent observation in the
 * user-facing list; accepted, filled, cancelled and rejected transitions remain
 * distinct because their event type or status differs.
 */
export function compactRuntimeTimeline(
  timeline: Array<Record<string, unknown>>,
  facts: Array<Record<string, unknown>>,
): CompactRuntimeTimelineItem[] {
  const factsByRef = new Map(
    facts.map((fact) => [valueOf(fact, "venue_fact_id"), fact]),
  );
  const grouped = new Map<string, { latestRef: string; count: number }>();

  timeline.forEach((item) => {
    const fact = factsByRef.get(valueOf(item, "source_ref"));
    const key = compactableOrderStateKey(item, fact);
    if (!key) return;
    grouped.set(key, {
      latestRef: valueOf(item, "source_ref"),
      count: (grouped.get(key)?.count ?? 0) + 1,
    });
  });

  return timeline.flatMap((item) => {
    const fact = factsByRef.get(valueOf(item, "source_ref"));
    const key = compactableOrderStateKey(item, fact);
    if (!key) return [{ item, fact, repeatCount: 1 }];
    const group = grouped.get(key);
    if (!group || group.latestRef !== valueOf(item, "source_ref")) return [];
    return [{ item, fact, repeatCount: group.count }];
  });
}

export function currentAccountSystemStop(
  stopEvidence: Array<Record<string, unknown>>,
): Record<string, unknown> | undefined {
  const latest = stopEvidence
    .filter((item) => valueOf(item, "scope") === "ACCOUNT")
    .sort((left, right) => (
      Number(valueOf(right, "version", "0"))
      - Number(valueOf(left, "version", "0"))
    ))[0];
  if (!latest || !Array.isArray(latest.categories)) return undefined;
  const categories = latest.categories.map(String);
  return categories.includes("NEW_RISK")
    || categories.includes("ALL_EXCHANGE_CHANGES")
    ? latest
    : undefined;
}

export function runtimeEventCategory(
  entry: CompactRuntimeTimelineItem,
  action?: Record<string, unknown>,
): RuntimeEventCategory {
  const source = valueOf(entry.item, "source");
  const detail = recordOf(entry.item.detail);
  const actionKind = valueOf(
    action,
    "action_kind",
    valueOf(detail, "action_kind"),
  );
  const protectionAction = ["PROTECTION", "TAKE_PROFIT"].includes(actionKind);
  if (source === "VENUE_FACT") {
    const sourceClass = valueOf(entry.fact, "source_class");
    const kind = valueOf(entry.fact, "kind");
    if (sourceClass === "VENUE_QUERY" || kind === "POSITION_STATE") {
      return "RECONCILIATION";
    }
    return protectionAction ? "PROTECTION" : "TRADING";
  }
  if (source === "EXECUTION_ACTION") {
    return protectionAction ? "PROTECTION" : "TRADING";
  }
  const ruleId = valueOf(detail, "rule_id").toUpperCase();
  if (ruleId.includes("RUNTIME_CONTINUITY")) return "RECONCILIATION";
  return ["PROTECTION", "TAKE_PROFIT", "TIME_EXIT", "STEPPED"]
    .some((token) => ruleId.includes(token))
    ? "PROTECTION"
    : "PLAN";
}

/**
 * One configured take-profit level can produce several venue orders when an
 * entry fills in parts. Group those orders by the frozen level metadata so the
 * runtime UI does not misrepresent four venue orders as four profit targets.
 */
export function groupRuntimeTakeProfits(
  actions: Array<Record<string, unknown>>,
  direction: string,
): RuntimeTakeProfitGroup[] {
  const grouped = new Map<string, RuntimeTakeProfitGroup>();

  actions
    .filter((action) => valueOf(action, "action_kind") === "TAKE_PROFIT")
    .forEach((action) => {
      const terms = recordOf(action.action_terms);
      const executionContext = recordOf(terms.execution_context);
      const directTakeProfit = recordOf(executionContext.direct_take_profit);
      const directLevelIndex = Number(directTakeProfit.level_index);
      const profileMatch = valueOf(terms, "action_profile")
        .match(/^TAKE_PROFIT_(\d+)$/);
      const profileLevelIndex = profileMatch
        ? Number(profileMatch[1]) - 1
        : Number.NaN;
      const levelIndex = Number.isInteger(directLevelIndex) && directLevelIndex >= 0
        ? directLevelIndex
        : Number.isInteger(profileLevelIndex) && profileLevelIndex >= 0
          ? profileLevelIndex
          : null;
      const price = Number(terms.trigger_price);
      const key = levelIndex === null
        ? `price:${Number.isFinite(price) ? price : valueOf(action, "action_id")}`
        : `level:${levelIndex}`;
      const current = grouped.get(key) ?? {
        levelIndex,
        triggerR: valueOf(directTakeProfit, "trigger_r"),
        prices: [],
        workingOrderCount: 0,
        orderCount: 0,
      };
      if (Number.isFinite(price) && !current.prices.includes(price)) {
        current.prices.push(price);
      }
      current.orderCount += 1;
      if (valueOf(action, "state") === "OPEN") {
        current.workingOrderCount += 1;
      }
      grouped.set(key, current);
    });

  const priceDirection = direction === "SHORT" ? -1 : 1;
  const groups = [...grouped.values()];
  groups.forEach((group) => group.prices.sort(
    (left, right) => priceDirection * (left - right),
  ));
  return groups.sort((left, right) => {
    if (left.levelIndex !== null && right.levelIndex !== null) {
      return left.levelIndex - right.levelIndex;
    }
    if (left.levelIndex !== null) return -1;
    if (right.levelIndex !== null) return 1;
    return priceDirection * (
      (left.prices[0] ?? Number.POSITIVE_INFINITY)
      - (right.prices[0] ?? Number.POSITIVE_INFINITY)
    );
  });
}

export function runtimeEntryConditionClauses(
  activation: Record<string, unknown>,
): RuntimeEntryConditionClause[] {
  const snapshot = recordOf(activation.order_schedule_snapshot);
  const spec = recordOf(snapshot.schedule_spec);
  const conditions = recordOf(spec.entry_conditions);
  const items = Array.isArray(conditions.items) ? conditions.items : [];
  const clauses: RuntimeEntryConditionClause[] = [];
  items.forEach((rawItem) => {
    const item = recordOf(rawItem);
    const kind = valueOf(item, "kind");
    if (kind === "MARK_PRICE") {
      clauses.push({
        kind,
        comparator: valueOf(item, "comparator"),
        value: valueOf(item, "price"),
        windowSeconds: null,
      });
    } else if (kind === "CLOSED_BAR_PRICE_15M") {
      clauses.push({
        kind,
        comparator: valueOf(item, "comparator"),
        value: valueOf(item, "price"),
        windowSeconds: null,
      });
    } else if (kind === "SPREAD_BPS") {
      clauses.push({
        kind,
        comparator: "LTE",
        value: valueOf(item, "maximum_bps"),
        windowSeconds: null,
      });
    } else if (kind === "PRICE_MOVE_BPS") {
      const windowSeconds = Number(item.window_seconds);
      clauses.push({
        kind,
        comparator: valueOf(item, "comparator"),
        value: valueOf(item, "threshold_bps"),
        windowSeconds: Number.isFinite(windowSeconds) ? windowSeconds : null,
      });
    }
  });
  return clauses;
}

/**
 * Read the latest Executor-owned condition decision persisted on the activation.
 *
 * The page estimate remains useful while the Executor has not evaluated yet,
 * but it must never be presented as the reason an order was or was not sent.
 */
export function runtimeExecutorConditionStatus(
  activation: Record<string, unknown>,
): RuntimeExecutorConditionStatus | null {
  const ruleState = recordOf(activation.rule_state);
  const judgements = recordOf(ruleState.condition_judgements);
  const state = recordOf(judgements.DIRECT_ENTRY);
  const result = valueOf(state, "result") as RuntimeEntryConditionResult;
  const phase = valueOf(state, "phase") as RuntimeExecutorConditionStatus["phase"];
  const sourceCutoff = valueOf(state, "source_cutoff");
  const evaluatedAt = valueOf(state, "evaluated_at");
  const rawItemResults = Array.isArray(state.item_results)
    ? state.item_results.map(String)
    : [];
  const snapshot = recordOf(activation.order_schedule_snapshot);
  const spec = recordOf(snapshot.schedule_spec);
  const group = recordOf(spec.entry_conditions);
  const conditionItems = Array.isArray(group.items) ? group.items : [];
  if (
    !["TRUE", "FALSE", "UNKNOWN"].includes(result)
    || !["INITIAL", "PRE_SUBMIT_RECHECK", "LATER_LEG_RECHECK"].includes(phase)
    || !sourceCutoff
    || !evaluatedAt
    || rawItemResults.length !== conditionItems.length
    || rawItemResults.some((item) => !["TRUE", "FALSE", "UNKNOWN"].includes(item))
  ) {
    return null;
  }

  const facts = recordOf(state.facts);
  const bid = Number(facts.bid_price);
  const ask = Number(facts.ask_price);
  const midpoint = (bid + ask) / 2;
  const spreadBps = Number.isFinite(bid)
    && Number.isFinite(ask)
    && bid > 0
    && ask >= bid
    && midpoint > 0
      ? (ask - bid) / midpoint * 10_000
      : null;
  const moveFacts = recordOf(facts.price_move_bps_by_window);
  const evaluated = evaluateRuntimeEntryConditions(activation, {
    basisReady: typeof facts.basis_ready === "boolean"
      ? facts.basis_ready
      : null,
    referencePrice: valueOf(facts, "mark_price") || null,
    closedBar15mClose: valueOf(facts, "closed_bar_15m_close") || null,
    spreadBps,
    priceMoveBpsByWindow: Object.fromEntries(
      Object.entries(moveFacts).map(([key, value]) => [key, String(value)]),
    ),
  });
  if (evaluated.items.length !== rawItemResults.length) return null;

  const submissionReady = typeof state.submission_ready === "boolean"
    ? state.submission_ready
    : null;
  const blockingReason = valueOf(state, "blocking_reason") || null;
  return {
    evaluation: {
      operator: valueOf(group, "operator") === "ANY" ? "ANY" : "ALL",
      result,
      items: evaluated.items.map((item, index) => ({
        ...item,
        result: rawItemResults[index] as RuntimeEntryConditionResult,
      })),
    },
    phase,
    sourceCutoff,
    evaluatedAt,
    submissionReady,
    blockingReason,
  };
}

export function runtimeSignedMovePresentation(value: string): {
  direction: "上涨" | "下跌" | "持平" | "变动";
  magnitude: string;
} {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return { direction: "变动", magnitude: value };
  }
  if (Math.abs(numeric) < 0.01) {
    return { direction: "持平", magnitude: "0" };
  }
  if (numeric > 0) {
    return { direction: "上涨", magnitude: String(numeric) };
  }
  if (numeric < 0) {
    return { direction: "下跌", magnitude: String(Math.abs(numeric)) };
  }
  return { direction: "持平", magnitude: "0" };
}

export function runtimeConditionPendingPresentation(
  condition: Pick<RuntimeEntryConditionState, "kind" | "windowSeconds">,
): string {
  if (condition.kind === "PRICE_MOVE_BPS") {
    return condition.windowSeconds !== null && condition.windowSeconds > 0
      ? `连续行情正在积累（需 ${condition.windowSeconds} 秒）`
      : "连续行情正在积累";
  }
  if (condition.kind === "CLOSED_BAR_PRICE_15M") {
    return "等待最新完整 15m K 线收盘";
  }
  if (condition.kind === "DECISION_BASIS_READY") {
    return "等待执行依据状态";
  }
  return "等待实时行情";
}

function numericConditionResult(
  currentValue: string | null,
  comparator: string,
  threshold: string,
): RuntimeEntryConditionResult {
  if (currentValue === null || currentValue.trim() === "") return "UNKNOWN";
  const current = Number(currentValue);
  const target = Number(threshold);
  if (!Number.isFinite(current) || !Number.isFinite(target)) return "UNKNOWN";
  const matched = comparator === "GTE"
    ? current >= target
    : comparator === "LTE"
      ? current <= target
      : comparator === "DROP_GTE"
        ? current <= -target
        : comparator === "ABS_GTE"
          ? Math.abs(current) >= target
          : false;
  return matched ? "TRUE" : "FALSE";
}

/**
 * Present a fast, fail-closed UI estimate of frozen entry conditions.
 *
 * Top-of-book and short-window values come from the page's public market
 * stream. They help the user understand why a plan is waiting, but they do not
 * replace the Executor's mark-price facts or authorize an order.
 */
export function evaluateRuntimeEntryConditions(
  activation: Record<string, unknown>,
  facts: RuntimeEntryConditionFacts,
): RuntimeEntryConditionEvaluation {
  const snapshot = recordOf(activation.order_schedule_snapshot);
  const spec = recordOf(snapshot.schedule_spec);
  const group = recordOf(spec.entry_conditions);
  const operator = valueOf(group, "operator") === "ANY" ? "ANY" : "ALL";
  const conditions = Array.isArray(group.items) ? group.items : [];
  const items = conditions.flatMap((rawItem): RuntimeEntryConditionState[] => {
    const item = recordOf(rawItem);
    const kind = valueOf(item, "kind");
    if (kind === "DECISION_BASIS_READY") {
      return [{
        kind,
        comparator: "IS_TRUE",
        threshold: "已确认",
        windowSeconds: null,
        currentValue: facts.basisReady === null
          ? null
          : facts.basisReady ? "已确认" : "未确认",
        result: facts.basisReady === null
          ? "UNKNOWN"
          : facts.basisReady ? "TRUE" : "FALSE",
      }];
    }
    if (kind === "MARK_PRICE") {
      const comparator = valueOf(item, "comparator");
      const threshold = valueOf(item, "price");
      return [{
        kind,
        comparator,
        threshold,
        windowSeconds: null,
        currentValue: facts.referencePrice,
        result: numericConditionResult(
          facts.referencePrice,
          comparator,
          threshold,
        ),
      }];
    }
    if (kind === "CLOSED_BAR_PRICE_15M") {
      const comparator = valueOf(item, "comparator");
      const threshold = valueOf(item, "price");
      return [{
        kind,
        comparator,
        threshold,
        windowSeconds: null,
        currentValue: facts.closedBar15mClose,
        result: numericConditionResult(
          facts.closedBar15mClose,
          comparator,
          threshold,
        ),
      }];
    }
    if (kind === "SPREAD_BPS") {
      const threshold = valueOf(item, "maximum_bps");
      const currentValue = facts.spreadBps === null
        || !Number.isFinite(facts.spreadBps)
        ? null
        : String(facts.spreadBps);
      return [{
        kind,
        comparator: "LTE",
        threshold,
        windowSeconds: null,
        currentValue,
        result: numericConditionResult(currentValue, "LTE", threshold),
      }];
    }
    if (kind === "PRICE_MOVE_BPS") {
      const comparator = valueOf(item, "comparator");
      const threshold = valueOf(item, "threshold_bps");
      const windowSeconds = Number(item.window_seconds);
      const validWindow = Number.isInteger(windowSeconds) ? windowSeconds : null;
      const currentValue = validWindow === null
        ? null
        : facts.priceMoveBpsByWindow[String(validWindow)] ?? null;
      return [{
        kind,
        comparator,
        threshold,
        windowSeconds: validWindow,
        currentValue,
        result: numericConditionResult(currentValue, comparator, threshold),
      }];
    }
    return [];
  });
  const results = items.map((item) => item.result);
  const result: RuntimeEntryConditionResult = operator === "ALL"
    ? results.includes("FALSE")
      ? "FALSE"
      : results.length > 0 && results.every((item) => item === "TRUE")
        ? "TRUE"
        : "UNKNOWN"
    : results.includes("TRUE")
      ? "TRUE"
      : results.length > 0 && results.every((item) => item === "FALSE")
        ? "FALSE"
        : "UNKNOWN";
  return { operator, result, items };
}

export function relativeAgeLabel(
  value: string | null | undefined,
  nowMs: number,
): string {
  const cutoffMs = Date.parse(value ?? "");
  if (!Number.isFinite(cutoffMs)) return "未知";
  const seconds = Math.max(0, Math.floor((nowMs - cutoffMs) / 1_000));
  if (seconds < 5) return "刚刚";
  if (seconds < 60) return `${seconds} 秒前`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  return `${Math.floor(hours / 24)} 天前`;
}

export function elapsedDurationLabel(
  value: string | null | undefined,
  nowMs: number,
): string {
  const startMs = Date.parse(value ?? "");
  if (!Number.isFinite(startMs)) return "未知";
  const minutes = Math.max(0, Math.floor((nowMs - startMs) / 60_000));
  if (minutes < 1) return "不足 1 分钟";
  if (minutes < 60) return `${minutes} 分钟`;
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  if (hours < 24) {
    return `${hours} 小时${remainingMinutes > 0 ? ` ${remainingMinutes} 分钟` : ""}`;
  }
  const days = Math.floor(hours / 24);
  const remainingHours = hours % 24;
  return `${days} 天${remainingHours > 0 ? ` ${remainingHours} 小时` : ""}`;
}

export function boundedProgressPercent(
  start: string | null | undefined,
  end: string | null | undefined,
  nowMs: number,
): number | null {
  const startMs = Date.parse(start ?? "");
  const endMs = Date.parse(end ?? "");
  if (!Number.isFinite(startMs) || !Number.isFinite(endMs) || endMs <= startMs) {
    return null;
  }
  return Math.min(100, Math.max(0, (nowMs - startMs) / (endMs - startMs) * 100));
}

export function runtimeEntryOrderDeadline(
  actions: Array<Record<string, unknown>>,
  schedule: Record<string, unknown>,
  planValidUntil: string | null | undefined,
): RuntimeEntryOrderDeadline | null {
  const submittedEntries = actions.flatMap((action) => {
    if (
      valueOf(action, "action_kind") !== "ENTRY"
      || valueOf(action, "state") === "NOT_SUBMITTED"
    ) {
      return [];
    }
    const callStartedAt = valueOf(action, "call_started_at");
    const createdAt = valueOf(action, "created_at");
    const submittedAt = Number.isFinite(Date.parse(callStartedAt))
      ? callStartedAt
      : valueOf(action, "client_order_id")
        && Number.isFinite(Date.parse(createdAt))
        ? createdAt
        : "";
    if (!submittedAt) return [];
    return [{ action, submittedAt }];
  }).sort(
    (left, right) => Date.parse(left.submittedAt) - Date.parse(right.submittedAt),
  );
  const firstSubmitted = submittedEntries[0];
  if (!firstSubmitted) return null;

  const actionTerms = recordOf(firstSubmitted.action.action_terms);
  const executionContext = recordOf(actionTerms.execution_context);
  const frozenRules = Array.isArray(executionContext.dynamic_rules)
    ? executionContext.dynamic_rules
    : [];
  const scheduleRules = Array.isArray(schedule.dynamic_rules)
    ? schedule.dynamic_rules
    : [];
  const expiry = [...frozenRules, ...scheduleRules]
    .map(recordOf)
    .find((rule) => valueOf(rule, "kind") === "EXPIRE_REMAINING");
  const expireAfterSeconds = Number(expiry?.after_seconds);
  if (!Number.isInteger(expireAfterSeconds) || expireAfterSeconds <= 0) {
    return null;
  }

  const submittedAtMs = Date.parse(firstSubmitted.submittedAt);
  const ruleExpiresAtMs = submittedAtMs + expireAfterSeconds * 1_000;
  const planValidUntilMs = Date.parse(planValidUntil ?? "");
  const limitedByPlanValidity = Number.isFinite(planValidUntilMs)
    && planValidUntilMs < ruleExpiresAtMs;
  const effectiveDeadlineAtMs = limitedByPlanValidity
    ? planValidUntilMs
    : ruleExpiresAtMs;
  return {
    submittedAt: firstSubmitted.submittedAt,
    ruleExpiresAt: new Date(ruleExpiresAtMs).toISOString(),
    effectiveDeadlineAt: new Date(effectiveDeadlineAtMs).toISOString(),
    expireAfterSeconds,
    limitedByPlanValidity,
  };
}

export function remainingTimeLabel(
  end: string | null | undefined,
  nowMs: number,
): string {
  const endMs = Date.parse(end ?? "");
  if (!Number.isFinite(endMs)) return "未知";
  const remainingSeconds = Math.ceil((endMs - nowMs) / 1_000);
  if (remainingSeconds <= 0) return "已到期";
  if (remainingSeconds < 60) return `剩余 ${remainingSeconds} 秒`;
  const minutes = Math.ceil(remainingSeconds / 60);
  if (minutes < 60) return `剩余 ${minutes} 分钟`;
  const hours = Math.floor(minutes / 60);
  const restMinutes = minutes % 60;
  if (hours < 24) return `剩余 ${hours} 小时${restMinutes ? ` ${restMinutes} 分钟` : ""}`;
  const days = Math.floor(hours / 24);
  const restHours = hours % 24;
  return `剩余 ${days} 天${restHours ? ` ${restHours} 小时` : ""}`;
}
