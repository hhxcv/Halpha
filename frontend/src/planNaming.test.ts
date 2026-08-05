import { describe, expect, it } from "vitest";

import {
  defaultStrategyPlanName,
  shouldReplaceAutomaticPlanName,
} from "./planNaming";

function strategy(profitabilityEvidence: string) {
  return {
    display_name: "单次 Donchian 突破与 ATR 风险退出",
    economic_scope: {
      profitability_evidence: profitabilityEvidence,
    },
  };
}

describe("plan naming", () => {
  it("marks validation-only strategies as tests", () => {
    expect(defaultStrategyPlanName(
      strategy("NO_POSITIVE_EXPECTANCY_EVIDENCE"),
      "2026-07-28 19:30:00 UTC+8",
    )).toBe("[测试] 单次 Donchian 突破与 ATR 风险退出 2026-07-28 19:30:00 UTC+8");
  });

  it("does not mark a profit-qualified strategy as a test", () => {
    expect(defaultStrategyPlanName(
      strategy("POSITIVE_EXPECTANCY_SUPPORTED"),
      "2026-07-28 19:30:00 UTC+8",
    )).toBe("单次 Donchian 突破与 ATR 风险退出 2026-07-28 19:30:00 UTC+8");
  });

  it("replaces only blank or previously generated names", () => {
    expect(shouldReplaceAutomaticPlanName("", null)).toBe(true);
    expect(shouldReplaceAutomaticPlanName("自动名称", "自动名称")).toBe(true);
    expect(shouldReplaceAutomaticPlanName("我的交易计划", "自动名称")).toBe(false);
  });
});
