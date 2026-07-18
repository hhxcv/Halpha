import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

export type Overview = components["schemas"]["OverviewResponse"];
export type SettingsStatus = components["schemas"]["SettingsStatusResponse"];
export type SessionResult = components["schemas"]["SessionResponse"];
export type PlanDraftPayload = components["schemas"]["PlanDraftPayload"];
export type CapitalLimitPayload = components["schemas"]["CapitalLimitPayload"];
export type ActivationPayload = components["schemas"]["ActivationPayload"];
export type ControlPayload = components["schemas"]["ControlPayload"];
export type ReviewCompletionPayload = components["schemas"]["ReviewCompletionPayload"];

export type StrategySummary = {
  strategy_id: string;
  strategy_version: string;
  display_name: string;
  parameter_schema_version: string;
  supported_directions: string[];
  economic_scope: Record<string, unknown>;
};

export type PlanSummary = {
  plan_id: string;
  draft_version: number;
  draft_content_digest: string;
  updated_at: string;
  strategy_id: string;
  instrument_ref: string;
  direction: string;
  plan_version_id: string | null;
  fixed_at: string | null;
  fixed_content_digest: string | null;
};

export type CapitalSnapshot = {
  environment_id: string;
  authority_class: string;
  account_ref: string;
  limits: Array<Record<string, unknown>>;
  allocations: Array<Record<string, unknown>>;
  authorizations: Array<Record<string, unknown>>;
  stops: Array<Record<string, unknown>>;
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

export async function sendTestEmail(ownerPassword: string): Promise<Record<string, unknown>> {
  const { data, error, response } = await api.POST("/api/v1/settings/test-email", {
    body: { owner_password: ownerPassword },
    headers: csrfHeader(),
  });
  if (!data) throw new ApiFailure(response.status, errorCode(error, "TEST_EMAIL_FAILED"));
  return data;
}

export async function login(password: string): Promise<SessionResult> {
  const { data, error, response } = await api.POST("/api/v1/session/login", {
    body: { password },
    headers: csrfHeader(),
  });
  if (!data) {
    throw new ApiFailure(response.status, errorCode(error, "LOGIN_FAILED"));
  }
  return data;
}

export async function logout(): Promise<SessionResult> {
  const { data, error, response } = await api.POST("/api/v1/session/logout", {
    headers: csrfHeader(),
  });
  if (!data) {
    throw new ApiFailure(response.status, errorCode(error, "LOGOUT_FAILED"));
  }
  return data;
}

export async function getStrategies(): Promise<StrategySummary[]> {
  const { data, error, response } = await api.GET("/api/v1/strategies");
  if (!data) throw new ApiFailure(response.status, errorCode(error, "STRATEGIES_FAILED"));
  return data as StrategySummary[];
}

export async function getStrategySchema(strategyId: string): Promise<Record<string, unknown>> {
  const { data, error, response } = await api.GET("/api/v1/strategies/{strategy_id}/schema", {
    params: { path: { strategy_id: strategyId } },
  });
  if (!data) throw new ApiFailure(response.status, errorCode(error, "STRATEGY_SCHEMA_FAILED"));
  return data;
}

export async function getPlans(): Promise<PlanSummary[]> {
  const { data, error, response } = await api.GET("/api/v1/plans");
  if (!data) throw new ApiFailure(response.status, errorCode(error, "PLANS_FAILED"));
  return data as PlanSummary[];
}

export async function createPlan(payload: PlanDraftPayload): Promise<Record<string, unknown>> {
  const { data, error, response } = await api.POST("/api/v1/plans", {
    body: payload,
    params: { header: { "Idempotency-Key": crypto.randomUUID() } },
    headers: csrfHeader(),
  });
  if (!data) throw new ApiFailure(response.status, errorCode(error, "PLAN_CREATE_FAILED"));
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

export async function getCapital(): Promise<CapitalSnapshot> {
  const { data, error, response } = await api.GET("/api/v1/capital");
  if (!data) throw new ApiFailure(response.status, errorCode(error, "CAPITAL_FAILED"));
  return data as CapitalSnapshot;
}

export async function createCapitalLimit(payload: CapitalLimitPayload): Promise<Record<string, unknown>> {
  const { data, error, response } = await api.POST("/api/v1/capital-limits", {
    body: payload,
    params: { header: { "Idempotency-Key": crypto.randomUUID() } },
    headers: csrfHeader(),
  });
  if (!data) throw new ApiFailure(response.status, errorCode(error, "CAPITAL_LIMIT_CREATE_FAILED"));
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

export async function getTasks(): Promise<Array<Record<string, unknown>>> {
  const { data, error, response } = await api.GET("/api/v1/tasks");
  if (!data) throw new ApiFailure(response.status, errorCode(error, "TASKS_FAILED"));
  return data as Array<Record<string, unknown>>;
}

export async function acknowledgeTask(taskId: string, expectedVersion: number): Promise<Record<string, unknown>> {
  const { data, error, response } = await api.POST("/api/v1/tasks/{task_id}/acknowledge", {
    params: { path: { task_id: taskId } },
    body: { expected_version: expectedVersion },
    headers: csrfHeader(),
  });
  if (!data) throw new ApiFailure(response.status, errorCode(error, "TASK_ACKNOWLEDGE_FAILED"));
  return data;
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
    intent === "RESUME_NEW_RISK" ? await api.POST("/api/v1/activations/{activation_id}/resume-new-risk", options) :
    intent === "RESUME_ACTIVATION" ? await api.POST("/api/v1/activations/{activation_id}/resume", options) :
    intent === "EXIT_STRATEGY" ? await api.POST("/api/v1/activations/{activation_id}/exit", options) :
    await api.POST("/api/v1/activations/{activation_id}/takeover", options);
  if (!result.data) throw new ApiFailure(result.response.status, errorCode(result.error, "CONTROL_SUBMIT_FAILED"));
  return result.data;
}
