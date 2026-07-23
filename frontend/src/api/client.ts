import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

export type Overview = components["schemas"]["OverviewResponse"];
export type SettingsStatus = components["schemas"]["SettingsStatusResponse"];
export type MarketContext = components["schemas"]["MarketContext"];
export type MarketWindow = components["schemas"]["MarketWindow"];
export type MarketInterval = MarketWindow["interval"];
export type MarketWindowPurpose = "EXECUTION_REVIEW";
export type PlanCreatePayload = components["schemas"]["PlanCreatePayload"];
export type PlanDraftPayload = components["schemas"]["PlanDraftPayload"];
export type DraftDecisionBasis = components["schemas"]["DraftDecisionBasis"];
export type ActivationPayload = components["schemas"]["ActivationPayload"];
export type ControlPayload = components["schemas"]["ControlPayload"];
export type ReviewCompletionPayload = components["schemas"]["ReviewCompletionPayload"];

export type OrderScheduleDirection = "LONG" | "SHORT";
export type OrderScheduleDistributionDirection = "LOW_TO_HIGH" | "HIGH_TO_LOW";
export type OrderSchedulePriceMatch =
  | "OPPONENT"
  | "OPPONENT_5"
  | "OPPONENT_10"
  | "OPPONENT_20"
  | "QUEUE"
  | "QUEUE_5"
  | "QUEUE_10"
  | "QUEUE_20";

export type OrderSchedulePricePlan =
  | {
      kind: "SINGLE";
      limit_price: string | null;
    }
  | {
      kind: "LADDER";
      lower_price: string;
      upper_price: string;
      level_count: number;
      spacing_mode: "EQUAL" | "LINEAR" | "GEOMETRIC" | "CUSTOM_WEIGHTS";
      spacing_direction: OrderScheduleDistributionDirection;
      linear_start_weight: string;
      linear_step: string;
      geometric_ratio: string;
      custom_gap_weights: string[];
    };

export type OrderScheduleAmountDistribution = {
  mode: "FIXED" | "LINEAR" | "EXPONENTIAL" | "CUSTOM";
  direction: OrderScheduleDistributionDirection;
  base_notional: string;
  linear_step: string;
  exponential_ratio: string;
  custom_notionals: string[];
};

export type OrderScheduleVenuePolicy = {
  order_type: "MARKET" | "LIMIT";
  time_in_force: "GTC" | "GTD" | "IOC" | "FOK" | null;
  post_only: boolean;
  price_match: OrderSchedulePriceMatch | null;
  display_quantity: null;
  expire_at: string | null;
};

export type OrderScheduleCondition =
  | { kind: "DECISION_BASIS_READY" }
  | { kind: "MARK_PRICE"; comparator: "GTE" | "LTE"; price: string }
  | { kind: "SPREAD_BPS"; maximum_bps: string }
  | {
      kind: "PRICE_MOVE_BPS";
      comparator: "GTE" | "LTE" | "ABS_GTE";
      threshold_bps: string;
      window_seconds: number;
    };

export type OrderScheduleProtectionPolicy = {
  initial_stop: {
    distance_bps: string;
    trigger_source: "MARK_PRICE";
    coverage: "EACH_CONFIRMED_FILL";
  };
  take_profit_ladder: {
    levels: Array<{ trigger_r: string; quantity_fraction: string }>;
  } | null;
  time_exit_seconds: number | null;
};

export type OrderScheduleDynamicRule =
  | {
      kind: "EXPIRE_REMAINING";
      after_seconds: number;
    }
  | {
      kind: "CANCEL_ON_SHOCK";
      window_seconds: number;
      adverse_move_bps: string;
      max_triggers: number;
    };

export type OrderScheduleSpec = {
  price_distribution: OrderSchedulePricePlan;
  amount_distribution: OrderScheduleAmountDistribution;
  venue_policy: OrderScheduleVenuePolicy;
  submission_mode: "SERIAL_PROTECTED";
  submission_order: "LOW_TO_HIGH" | "HIGH_TO_LOW";
  entry_conditions: {
    operator: "ALL" | "ANY";
    items: OrderScheduleCondition[];
  };
  protection_policy: OrderScheduleProtectionPolicy;
  dynamic_rules: OrderScheduleDynamicRule[];
};

export type OrderSchedulePreviewPayload = {
  decision_basis_kind: "DIRECT_EXECUTION";
  schedule_ref: string;
  venue_ref: "BINANCE_USDM";
  instrument_ref: string;
  direction: OrderScheduleDirection;
  max_notional: string;
  reference_price: string | null;
  spec: OrderScheduleSpec;
};

export type OrderSchedulePreviewLeg = {
  leg_index: number;
  leg_count: number;
  raw_price: string | null;
  price: string | null;
  sizing_price: string;
  requested_notional: string;
  quantity: string;
  effective_notional: string;
};

export type OrderSchedulePreviewIssue = {
  code: string;
  field: string;
  leg_index: number | null;
};

export type OrderSchedulePreview = {
  valid: boolean;
  compiler_version: string;
  schedule_ref: string;
  schedule_digest: string;
  schedule_spec: OrderScheduleSpec;
  preprotected_parallel_supported: boolean;
  venue_ref: string;
  instrument_ref: string;
  direction: OrderScheduleDirection;
  max_notional: string;
  reference_price: string | null;
  instrument_rules: {
    source: string;
    min_price: string;
    max_price: string;
    price_tick_size: string;
    limit_quantity_step: string;
    min_limit_quantity: string;
    max_limit_quantity: string;
    market_quantity_step: string;
    min_market_quantity: string;
    max_market_quantity: string;
    min_notional: string;
    source_cutoff: string;
  };
  instrument_rules_digest: string;
  source_cutoff: string;
  requested_total_notional: string;
  effective_total_notional: string;
  normalized_legs: OrderSchedulePreviewLeg[];
  legs: OrderSchedulePreviewLeg[];
  issues: OrderSchedulePreviewIssue[];
};

export type PlanKeyParameterDefinition = {
  parameter_key: string;
  label: string;
  display_format: "VALUE" | "PERCENT" | "BOOLEAN_LABEL";
  unit: string | null;
  true_label: string | null;
  false_label: string | null;
};

export type StrategySummary = {
  strategy_id: string;
  strategy_version: string;
  display_name: string;
  value_logic: string;
  applicable_scenarios: string;
  execution_behavior: string;
  parameter_schema_version: string;
  supported_directions: string[];
  economic_scope: Record<string, unknown>;
  plan_key_parameters: PlanKeyParameterDefinition[];
};

export type PlanSummary = {
  plan_id: string;
  draft_version: number;
  draft_content_digest: string;
  updated_at: string;
  plan_name: string | null;
  created_at: string | null;
  creator_kind: "HUMAN" | "AI" | null;
  decision_basis: DraftDecisionBasis;
  decision_basis_kind: "STRATEGY_SIGNAL" | "DIRECT_EXECUTION";
  decision_basis_ref: string;
  strategy_id: string | null;
  instrument_ref: string;
  direction: string;
  parameters: Record<string, unknown>;
  order_schedule_spec: OrderScheduleSpec | null;
  max_notional: string;
  valid_from: string;
  valid_until: string;
  plan_version_id: string | null;
  fixed_at: string | null;
  fixed_content_digest: string | null;
  fixed_product_build_id: string | null;
  fixed_valid_until: string | null;
  product_build_consistent: boolean | null;
};

export type PlanDraft = {
  plan_id: string;
  environment_id: string;
  draft_version: number;
  content: {
    plan_name: string | null;
    created_at: string | null;
    creator_kind: "HUMAN" | "AI" | null;
    decision_basis?: DraftDecisionBasis;
    order_schedule_spec: OrderScheduleSpec | null;
    strategy_id?: string;
    parameters?: Record<string, unknown>;
    venue_ref: string;
    instrument_ref: string;
    direction: string;
    target_exposure: string;
    requested_limits: {
      max_margin: string;
      max_notional: string;
      max_allowed_loss: string;
    };
    valid_from: string;
    valid_until: string;
  };
  content_digest: string;
  updated_at: string;
};

export type ActivationSummary = {
  activation_id: string;
  instrument_ref: string;
  direction: string;
  lifecycle: string;
  run_state: string;
  pause_reason: string | null;
  protection_state: string;
  state_version: number;
  updated_at: string;
};

export class ApiFailure extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string) {
    super(code);
    this.name = "ApiFailure";
    this.status = status;
    this.code = code;
  }
}

const api = createClient<paths>({
  baseUrl: "",
  credentials: "same-origin",
  headers: { Accept: "application/json" },
});

export function cookieValue(cookieHeader: string, name: string): string | null {
  for (const part of cookieHeader.split(";")) {
    const [rawName, ...rawValue] = part.trim().split("=");
    if (rawName === name) {
      return decodeURIComponent(rawValue.join("="));
    }
  }
  return null;
}

function csrfHeader(): Record<string, string> {
  const token = cookieValue(document.cookie, "halpha_csrf");
  if (!token) {
    throw new ApiFailure(403, "CSRF_COOKIE_MISSING");
  }
  return { "X-CSRFToken": token };
}

function errorCode(error: unknown, fallback: string): string {
  if (typeof error !== "object" || error === null) return fallback;
  const detail = "detail" in error ? error.detail : null;
  if (typeof detail !== "object" || detail === null) return fallback;
  const code = "code" in detail ? detail.code : null;
  return typeof code === "string" ? code : fallback;
}

export async function getSettingsStatus(): Promise<SettingsStatus> {
  const { data, error, response } = await api.GET("/api/v1/settings/status");
  if (!data) {
    throw new ApiFailure(response.status, errorCode(error, "SETTINGS_STATUS_FAILED"));
  }
  return data;
}

export async function getOverview(): Promise<Overview> {
  const { data, error, response } = await api.GET("/api/v1/overview");
  if (!data) {
    throw new ApiFailure(response.status, errorCode(error, "OVERVIEW_FAILED"));
  }
  return data;
}

export async function sendTestEmail(): Promise<Record<string, unknown>> {
  const { data, error, response } = await api.POST("/api/v1/settings/test-email", {
    headers: csrfHeader(),
  });
  if (!data) throw new ApiFailure(response.status, errorCode(error, "TEST_EMAIL_FAILED"));
  return data;
}

export async function getStrategies(): Promise<StrategySummary[]> {
  const { data, error, response } = await api.GET("/api/v1/strategies");
  if (!data) throw new ApiFailure(response.status, errorCode(error, "STRATEGIES_FAILED"));
  return data as StrategySummary[];
}

export async function getMarketContext(
  instrumentRef: string,
  channelLookback15m: number,
): Promise<MarketContext> {
  const { data, error, response } = await api.GET("/api/v1/market-context", {
    params: {
      query: {
        instrument_ref: instrumentRef,
        channel_lookback_15m: channelLookback15m,
      },
    },
  });
  if (!data) throw new ApiFailure(response.status, errorCode(error, "MARKET_CONTEXT_FAILED"));
  return data;
}

export async function getMarketWindow(
  instrumentRef: string,
  startAt: string,
  endAt: string,
  interval: MarketInterval,
  purpose: MarketWindowPurpose = "EXECUTION_REVIEW",
): Promise<MarketWindow> {
  // Every product chart reads the current runtime environment. A caller cannot
  // opt into a second venue source and accidentally mix Demo and Live bars.
  const query = {
    instrument_ref: instrumentRef,
    start_at: startAt,
    end_at: endAt,
    interval,
    purpose,
  };
  const { data, error, response } = await api.GET("/api/v1/market-window", {
    params: {
      query,
    },
  });
  if (!data) throw new ApiFailure(response.status, errorCode(error, "MARKET_WINDOW_FAILED"));
  return data;
}

export async function previewOrderSchedule(
  payload: OrderSchedulePreviewPayload,
): Promise<OrderSchedulePreview> {
  const { data, error, response } = await api.POST("/api/v1/order-schedules/preview", {
    body: payload,
    headers: csrfHeader(),
  });
  if (!data) {
    throw new ApiFailure(
      response.status,
      errorCode(error, "ORDER_SCHEDULE_PREVIEW_FAILED"),
    );
  }
  return data as OrderSchedulePreview;
}

export async function getPlans(): Promise<PlanSummary[]> {
  const { data, error, response } = await api.GET("/api/v1/plans");
  if (!data) throw new ApiFailure(response.status, errorCode(error, "PLANS_FAILED"));
  return data as PlanSummary[];
}

export async function getPlan(planId: string): Promise<PlanDraft> {
  const { data, error, response } = await api.GET("/api/v1/plans/{plan_id}", {
    params: { path: { plan_id: planId } },
  });
  if (!data) throw new ApiFailure(response.status, errorCode(error, "PLAN_FAILED"));
  return data as PlanDraft;
}

export async function createPlan(payload: PlanCreatePayload): Promise<Record<string, unknown>> {
  const { data, error, response } = await api.POST("/api/v1/plans", {
    body: payload,
    params: { header: { "Idempotency-Key": crypto.randomUUID() } },
    headers: csrfHeader(),
  });
  if (!data) throw new ApiFailure(response.status, errorCode(error, "PLAN_CREATE_FAILED"));
  return data;
}

export async function deletePlan(planId: string, draftVersion: number): Promise<Record<string, unknown>> {
  const { data, error, response } = await api.DELETE("/api/v1/plans/{plan_id}", {
    params: {
      path: { plan_id: planId },
      header: { "If-Match": String(draftVersion) },
    },
    headers: csrfHeader(),
  });
  if (!data) throw new ApiFailure(response.status, errorCode(error, "PLAN_DELETE_FAILED"));
  return data;
}

export async function updatePlan(
  planId: string,
  draftVersion: number,
  payload: PlanDraftPayload,
): Promise<Record<string, unknown>> {
  const { data, error, response } = await api.PUT("/api/v1/plans/{plan_id}", {
    body: payload,
    params: {
      path: { plan_id: planId },
      header: { "If-Match": String(draftVersion) },
    },
    headers: csrfHeader(),
  });
  if (!data) throw new ApiFailure(response.status, errorCode(error, "PLAN_UPDATE_FAILED"));
  return data;
}

export async function fixPlan(planId: string, draftVersion: number): Promise<Record<string, unknown>> {
  const { data, error, response } = await api.POST("/api/v1/plans/{plan_id}/fix", {
    params: { path: { plan_id: planId }, header: { "Idempotency-Key": crypto.randomUUID(), "If-Match": String(draftVersion) } },
    headers: csrfHeader(),
  });
  if (!data) throw new ApiFailure(response.status, errorCode(error, "PLAN_FIX_FAILED"));
  return data;
}

export async function getActivationPreview(planVersionId: string): Promise<Record<string, unknown>> {
  const { data, error, response } = await api.POST("/api/v1/plan-versions/{plan_version_id}/activation-preview", {
    params: { path: { plan_version_id: planVersionId } },
    headers: csrfHeader(),
  });
  if (!data) throw new ApiFailure(response.status, errorCode(error, "ACTIVATION_PREVIEW_FAILED"));
  return data;
}

export async function createActivation(payload: ActivationPayload): Promise<Record<string, unknown>> {
  const { data, error, response } = await api.POST("/api/v1/activations", {
    body: payload,
    params: { header: { "Idempotency-Key": crypto.randomUUID() } },
    headers: csrfHeader(),
  });
  if (!data) throw new ApiFailure(response.status, errorCode(error, "ACTIVATION_CREATE_FAILED"));
  return data;
}

export async function getActivations(): Promise<ActivationSummary[]> {
  const { data, error, response } = await api.GET("/api/v1/activations");
  if (!data) throw new ApiFailure(response.status, errorCode(error, "ACTIVATIONS_FAILED"));
  return data as ActivationSummary[];
}

export async function getActivation(activationId: string): Promise<Record<string, unknown>> {
  const { data, error, response } = await api.GET("/api/v1/activations/{activation_id}", {
    params: { path: { activation_id: activationId } },
  });
  if (!data) throw new ApiFailure(response.status, errorCode(error, "ACTIVATION_FAILED"));
  return data;
}

export async function getActivationTimeline(activationId: string): Promise<Array<Record<string, unknown>>> {
  const { data, error, response } = await api.GET("/api/v1/activations/{activation_id}/timeline", {
    params: { path: { activation_id: activationId } },
  });
  if (!data) throw new ApiFailure(response.status, errorCode(error, "ACTIVATION_TIMELINE_FAILED"));
  return data as Array<Record<string, unknown>>;
}

export async function getReviews(): Promise<Array<Record<string, unknown>>> {
  const { data, error, response } = await api.GET("/api/v1/reviews");
  if (!data) throw new ApiFailure(response.status, errorCode(error, "REVIEWS_FAILED"));
  return data as Array<Record<string, unknown>>;
}

export async function getReview(reviewId: string): Promise<Record<string, unknown>> {
  const { data, error, response } = await api.GET("/api/v1/reviews/{review_id}", {
    params: { path: { review_id: reviewId } },
  });
  if (!data) throw new ApiFailure(response.status, errorCode(error, "REVIEW_FAILED"));
  return data;
}

export async function refreshReview(reviewId: string, expectedVersion: number): Promise<Record<string, unknown>> {
  const { data, error, response } = await api.PUT("/api/v1/reviews/{review_id}", {
    params: { path: { review_id: reviewId } },
    body: { expected_version: expectedVersion },
    headers: csrfHeader(),
  });
  if (!data) throw new ApiFailure(response.status, errorCode(error, "REVIEW_REFRESH_FAILED"));
  return data;
}

export async function completeReview(
  reviewId: string,
  payload: ReviewCompletionPayload,
): Promise<Record<string, unknown>> {
  const { data, error, response } = await api.POST("/api/v1/reviews/{review_id}/complete", {
    params: { path: { review_id: reviewId } },
    body: payload,
    headers: csrfHeader(),
  });
  if (!data) throw new ApiFailure(response.status, errorCode(error, "REVIEW_COMPLETE_FAILED"));
  return data;
}

export type ControlIntent = components["schemas"]["ControlIntent"];

export async function previewControl(activationId: string, intent: ControlIntent): Promise<Record<string, unknown>> {
  const { data, error, response } = await api.POST("/api/v1/activations/{activation_id}/control-preview", {
    params: { path: { activation_id: activationId }, query: { intent } },
    headers: csrfHeader(),
  });
  if (!data) throw new ApiFailure(response.status, errorCode(error, "CONTROL_PREVIEW_FAILED"));
  return data;
}

export async function submitActivationControl(
  activationId: string,
  intent: ControlIntent,
  payload: ControlPayload,
  idempotencyKey: string,
): Promise<Record<string, unknown>> {
  const options = { params: { path: { activation_id: activationId }, header: { "Idempotency-Key": idempotencyKey } }, body: payload, headers: csrfHeader() };
  const result =
    intent === "STOP_NEW_RISK" ? await api.POST("/api/v1/activations/{activation_id}/stop-new-risk", options) :
    intent === "RESUME_ACTIVATION" ? await api.POST("/api/v1/activations/{activation_id}/resume", options) :
    intent === "EXIT_STRATEGY" ? await api.POST("/api/v1/activations/{activation_id}/exit", options) :
    await api.POST("/api/v1/activations/{activation_id}/takeover", options);
  if (!result.data) throw new ApiFailure(result.response.status, errorCode(result.error, "CONTROL_SUBMIT_FAILED"));
  return result.data;
}
