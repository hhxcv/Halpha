import { describe, expect, it } from "vitest";

import {
  tradingAccountLabel,
  tradingContextLabel,
  tradingContextSwitchTarget,
  type TradingContextTarget,
} from "./environmentSwitch";

const copyTarget: TradingContextTarget = {
  venue_account_type: "USDM_COPY_LEAD",
  environment_id: "binance-live-copy-primary",
  account_id: "binance-usdm-copy-lead-primary",
  url: "http://127.0.0.1:8766/plans/live-id?copyFrom=demo-id#orders",
};

describe("tradingContextSwitchTarget", () => {
  it("navigates to the selected context overview without object identity", () => {
    expect(tradingContextSwitchTarget(
      copyTarget,
      "http://127.0.0.1:8765/plans/demo-id/edit?copyFrom=other#chart",
    )).toBe("http://127.0.0.1:8766/overview");
  });

  it("rejects missing, current-origin, non-loopback and non-http targets", () => {
    const current = "http://127.0.0.1:8765/overview";
    expect(tradingContextSwitchTarget(null, current)).toBeNull();
    expect(tradingContextSwitchTarget({ ...copyTarget, url: current }, current)).toBeNull();
    expect(tradingContextSwitchTarget({ ...copyTarget, url: "https://127.0.0.1:8766" }, current)).toBeNull();
    expect(tradingContextSwitchTarget({ ...copyTarget, url: "http://example.test:8766" }, current)).toBeNull();
    expect(tradingContextSwitchTarget({ ...copyTarget, url: "javascript:alert(1)" }, current)).toBeNull();
  });
});

describe("trading context labels", () => {
  it("distinguishes Demo, Copy lead and Personal accounts without color", () => {
    expect(tradingContextLabel("USDM_DEMO")).toBe("Demo");
    expect(tradingContextLabel("USDM_COPY_LEAD")).toBe("实盘 · 带单账户");
    expect(tradingContextLabel("USDM_PERSONAL")).toBe("实盘 · 个人账户");
    expect(tradingAccountLabel("USDM_COPY_LEAD")).toBe("带单员公域合约账户");
    expect(tradingAccountLabel("USDM_PERSONAL")).toBe("个人 USDⓈ-M 合约账户");
  });
});
