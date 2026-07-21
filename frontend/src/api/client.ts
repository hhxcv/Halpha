import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

export type Overview = components["schemas"]["OverviewResponse"];
export type SettingsStatus = components["schemas"]["SettingsStatusResponse"];
export type MarketContext = components["schemas"]["MarketContext"];
export type MarketWindow = components["schemas"]["MarketWindow"];
export type PlanCreatePayload = components["schemas"]["PlanCreatePayload"];
export type PlanDraftPayload = components["schemas"]["PlanDraftPayload"];
export type ActivationPayload = components["schemas"]["ActivationPayload"];
export type ControlPayload = components["schemas"]["ControlPayload"];
export type ReviewCompletionPayload = components["schemas"]["ReviewCompletionPayload"];

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
  strategy_id: string;
  instrument_ref: string;
  direction: string;
  parameters: Record<string, unknown>;
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
    strategy_id: string;
    parameters: Record<string, unknown>;
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
  interval: "1m" | "15m",
): Promise<MarketWindow> {
  const { data, error, response } = await api.GET("/api/v1/market-window", {
    params: {
      query: {
        instrument_ref: instrumentRef,
        start_at: startAt,
        end_at: endAt,
        interval,
      },
    },
  });
  if (!data) throw new ApiFailure(response.status, errorCode(error, "MARKET_WINDOW_FAILED"));
  return data;
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
