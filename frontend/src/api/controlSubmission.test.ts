import { describe, expect, it, vi } from "vitest";

import type { ControlIntent, ControlPayload } from "./client";
import { submitActivationControlWithFreshRiskReducingRetry } from "./controlSubmission";

const payload: ControlPayload = {
  expected_version: 7,
  takeover_scope: {},
};

function dependencies(
  receipts: Array<Record<string, unknown>>,
  preview: Record<string, unknown> = {
    activation: {
      lifecycle: "RUNNING",
      state_version: 9,
    },
  },
) {
  return {
    submit: vi.fn(async () => receipts.shift() ?? {}),
    preview: vi.fn(async () => preview),
    createIdempotencyKey: vi.fn(() => "retry-key"),
  };
}

describe("submitActivationControlWithFreshRiskReducingRetry", () => {
  it("returns a successful first receipt without refreshing", async () => {
    const deps = dependencies([{ state: "EFFECTIVE" }]);

    const result = await submitActivationControlWithFreshRiskReducingRetry(
      "activation-1",
      "EXIT_STRATEGY",
      payload,
      "initial-key",
      deps,
    );

    expect(result.state).toBe("EFFECTIVE");
    expect(deps.submit).toHaveBeenCalledTimes(1);
    expect(deps.preview).not.toHaveBeenCalled();
  });

  it("refreshes once and retries a risk-reducing command with the latest version", async () => {
    const deps = dependencies([
      { state: "REJECTED", reason_code: "PLAN_VERSION_CONFLICT" },
      { state: "EFFECTIVE" },
    ]);

    const result = await submitActivationControlWithFreshRiskReducingRetry(
      "activation-1",
      "EXIT_STRATEGY",
      payload,
      "initial-key",
      deps,
    );

    expect(result.state).toBe("EFFECTIVE");
    expect(deps.preview).toHaveBeenCalledOnce();
    expect(deps.submit).toHaveBeenNthCalledWith(
      2,
      "activation-1",
      "EXIT_STRATEGY",
      { expected_version: 9, takeover_scope: {} },
      "retry-key",
    );
  });

  it.each<ControlIntent>(["USER_TAKEOVER", "RESUME_ACTIVATION"])(
    "does not retry stale %s commands",
    async (intent) => {
      const deps = dependencies([
        { state: "REJECTED", reason_code: "PLAN_VERSION_CONFLICT" },
      ]);

      await submitActivationControlWithFreshRiskReducingRetry(
        "activation-1",
        intent,
        payload,
        "initial-key",
        deps,
      );

      expect(deps.submit).toHaveBeenCalledTimes(1);
      expect(deps.preview).not.toHaveBeenCalled();
    },
  );

  it("does not reapply a stale command after the activation has left RUNNING", async () => {
    const deps = dependencies(
      [{ state: "REJECTED", reason_code: "PLAN_VERSION_CONFLICT" }],
      {
        activation: {
          lifecycle: "EXITING",
          state_version: 9,
        },
      },
    );

    await submitActivationControlWithFreshRiskReducingRetry(
      "activation-1",
      "EXIT_STRATEGY",
      payload,
      "initial-key",
      deps,
    );

    expect(deps.submit).toHaveBeenCalledTimes(1);
    expect(deps.preview).toHaveBeenCalledOnce();
  });
});
