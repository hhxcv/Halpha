import type { StrategySummary } from "./api/client";

export const TEST_PLAN_PREFIX = "[测试]";

export function defaultStrategyPlanName(
  strategy: Pick<StrategySummary, "display_name" | "economic_scope">,
  formattedAt: string,
): string {
  const prefix = strategy.economic_scope.profitability_evidence
    === "POSITIVE_EXPECTANCY_SUPPORTED"
    ? ""
    : `${TEST_PLAN_PREFIX} `;
  return `${prefix}${strategy.display_name} ${formattedAt}`.slice(0, 80);
}

export function shouldReplaceAutomaticPlanName(
  currentName: string,
  previousAutomaticName: string | null,
): boolean {
  const current = currentName.trim();
  return current.length === 0
    || (
      previousAutomaticName !== null
      && current === previousAutomaticName.trim()
    );
}
