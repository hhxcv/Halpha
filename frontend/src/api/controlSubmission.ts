import {
  previewControl,
  submitActivationControl,
  type ControlIntent,
  type ControlPayload,
} from "./client";

type ControlReceipt = Record<string, unknown>;

type ControlPreviewSnapshot = {
  activation?: {
    lifecycle?: unknown;
    state_version?: unknown;
  };
};

type ControlSubmissionDependencies = {
  preview: (
    activationId: string,
    intent: ControlIntent,
  ) => Promise<ControlPreviewSnapshot>;
  submit: (
    activationId: string,
    intent: ControlIntent,
    payload: ControlPayload,
    idempotencyKey: string,
  ) => Promise<ControlReceipt>;
  createIdempotencyKey: () => string;
};

const defaultDependencies: ControlSubmissionDependencies = {
  preview: previewControl,
  submit: submitActivationControl,
  createIdempotencyKey: () => crypto.randomUUID(),
};

function stringField(source: Record<string, unknown>, field: string): string {
  const value = source[field];
  return typeof value === "string" ? value : "";
}

function versionConflict(receipt: ControlReceipt): boolean {
  return stringField(receipt, "state") === "REJECTED"
    && stringField(receipt, "reason_code") === "PLAN_VERSION_CONFLICT";
}

function retryableRiskReducingIntent(intent: ControlIntent): boolean {
  return intent === "STOP_NEW_RISK" || intent === "EXIT_STRATEGY";
}

export async function submitActivationControlWithFreshRiskReducingRetry(
  activationId: string,
  intent: ControlIntent,
  payload: ControlPayload,
  idempotencyKey: string,
  dependencies: ControlSubmissionDependencies = defaultDependencies,
): Promise<ControlReceipt> {
  const firstReceipt = await dependencies.submit(
    activationId,
    intent,
    payload,
    idempotencyKey,
  );
  if (!retryableRiskReducingIntent(intent) || !versionConflict(firstReceipt)) {
    return firstReceipt;
  }

  const freshPreview = await dependencies.preview(activationId, intent);
  const activation = freshPreview.activation;
  if (!activation || typeof activation !== "object" || Array.isArray(activation)) {
    return firstReceipt;
  }
  const latestActivation = activation as Record<string, unknown>;
  if (stringField(latestActivation, "lifecycle") !== "RUNNING") {
    return firstReceipt;
  }
  const latestVersion = Number(latestActivation.state_version);
  if (!Number.isInteger(latestVersion) || latestVersion <= 0) {
    return firstReceipt;
  }

  return dependencies.submit(
    activationId,
    intent,
    {
      ...payload,
      expected_version: latestVersion,
    },
    dependencies.createIdempotencyKey(),
  );
}
