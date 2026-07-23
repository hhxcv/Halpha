import { describe, expect, it } from "vitest";

import {
  closedBarBreakoutGapPercent,
  entryExtensionBoundary,
  estimateImmediateExit,
  formatUserVisibleTime,
  formatUtc,
  gapPercent,
  latestUtc,
  marketVolume,
  notSubmittedReasonText,
  observedOrderStateText,
  pendingBreakoutNote,
  planEventSummary,
  shortDigest,
  USER_VISIBLE_TIME_LOCALE,
  USER_VISIBLE_TIME_ZONE,
  USER_VISIBLE_TIME_ZONE_LABEL,
  venueReasonText,
} from "./format";

describe("deterministic workbench formatting", () => {
  it("uses the global Chinese UTC+8 display configuration", () => {
    expect(USER_VISIBLE_TIME_LOCALE).toBe("zh-CN");
    expect(USER_VISIBLE_TIME_ZONE).toBe("Asia/Shanghai");
    expect(USER_VISIBLE_TIME_ZONE_LABEL).toBe("UTC+8");
  });

  it("converts Z timestamps to the user-visible UTC+8 time zone", () => {
    expect(formatUserVisibleTime("2026-07-17T00:00:00Z"))
      .toBe("2026-07-17 08:00:00 UTC+8");
  });

  it("normalizes timestamp offsets before displaying UTC+8", () => {
    expect(formatUserVisibleTime("2026-07-17T12:34:56+09:00"))
      .toBe("2026-07-17 11:34:56 UTC+8");
    expect(formatUserVisibleTime("2026-07-16T19:30:00-05:00"))
      .toBe("2026-07-17 08:30:00 UTC+8");
  });

  it("keeps missing, unknown, and invalid timestamps explicit", () => {
    expect(formatUserVisibleTime(null)).toBe("未知");
    expect(formatUserVisibleTime(undefined)).toBe("未知");
    expect(formatUserVisibleTime("")).toBe("未知");
    expect(formatUserVisibleTime("UNKNOWN")).toBe("未知");
    expect(formatUserVisibleTime("not-a-date")).toBe("未知");
  });

  it("keeps the temporary formatUtc export aligned with UTC+8 display", () => {
    expect(formatUtc("2026-07-17T00:00:00Z")).toBe("2026-07-17 08:00:00 UTC+8");
  });

  it("shortens digests without implying equality", () => {
    expect(shortDigest("0123456789abcdef0123456789abcdef")).toBe("0123456789ab…cdef");
    expect(shortDigest(null)).toBe("NOT BOUND");
  });

  it("uses the latest valid venue fact cutoff", () => {
    expect(latestUtc([
      null,
      "UNKNOWN",
      "2026-07-20T11:05:01Z",
      "2026-07-20T11:16:28Z",
    ])).toBe("2026-07-20T11:16:28Z");
    expect(latestUtc([null, "UNKNOWN"])).toBeNull();
  });

  it("把 HTML 场所错误压缩为可操作提示", () => {
    expect(venueReasonText("<html><head><title>502 Bad Gateway</title></head></html>"))
      .toBe("Binance Demo 暂时不可用（HTTP 502 Bad Gateway）；本次订单未成交，系统没有自动重复提交。");
    expect(venueReasonText("MIN_NOTIONAL")).toBe("MIN_NOTIONAL");
  });

  it("解释查无原订单后的未提交结论", () => {
    expect(notSubmittedReasonText("VENUE_QUERY_PROVED_ABSENT"))
      .toContain("按原订单 UUID 查询确认 Binance 没有创建订单");
  });

  it("按计划规则显示实际动作含义，而不是把所有事件都写成入场", () => {
    expect(planEventSummary("PROPOSED_ACTION_CAP_ACCEPTED", "ENTRY_BREAKOUT"))
      .toBe("入场意图已通过资金检查");
    expect(planEventSummary("PROPOSED_ACTION_CAP_ACCEPTED", "DIRECT_ORDER_SCHEDULE_LEG"))
      .toBe("直接执行入场档位已通过资金检查");
    expect(planEventSummary("PROPOSED_ACTION_CAP_ACCEPTED", "PROTECTION_AFTER_FILL"))
      .toBe("保护委托已通过资金检查");
    expect(planEventSummary("PROPOSED_ACTION_CAP_ACCEPTED", "TAKE_PROFIT_1_AFTER_PROTECTION"))
      .toBe("止盈一委托已通过资金检查");
    expect(planEventSummary("PROPOSED_ACTION_CAP_ACCEPTED", "REDUCE_OR_CLOSE_POSITION"))
      .toBe("减仓或平仓意图已通过资金检查");
    expect(planEventSummary("PROPOSED_ACTION_CAP_ACCEPTED", "CANCEL_OPEN_RESPONSIBILITY"))
      .toBe("撤单意图已通过资金检查");
  });

  it("明确订单状态是曾收到的交易所事实", () => {
    expect(observedOrderStateText("工作中")).toBe("曾收到订单状态 · 工作中");
    expect(observedOrderStateText("")).toBe("曾收到订单状态");
  });

  it("keeps missing percentages unknown", () => {
    expect(gapPercent("")).toBe("UNKNOWN");
    expect(gapPercent("not-a-number")).toBe("UNKNOWN");
  });

  it("keeps small base-asset volume visible", () => {
    expect(marketVolume("0.00012345")).toBe("0.00012345");
  });

  it("measures the strategy trigger from the latest closed bar", () => {
    expect(Number(closedBarBreakoutGapPercent("LONG", "100", "101"))).toBeCloseTo(1);
    expect(Number(closedBarBreakoutGapPercent("LONG", "102", "101"))).toBeLessThan(0);
    expect(Number(closedBarBreakoutGapPercent("SHORT", "100", "99"))).toBeCloseTo(1);
    expect(Number(closedBarBreakoutGapPercent("SHORT", "98", "99"))).toBeLessThan(0);
    expect(closedBarBreakoutGapPercent("LONG", "", "101")).toBe("");
  });

  it("明确等待突破提示只针对当前计划方向", () => {
    expect(pendingBreakoutNote("LONG")).toContain("通道上沿");
    expect(pendingBreakoutNote("SHORT")).toContain("通道下沿");
  });

  it("calculates the farthest strategy entry price without adding runtime state", () => {
    expect(entryExtensionBoundary("LONG", "100", "2", "0.5")).toBe(101);
    expect(entryExtensionBoundary("SHORT", "100", "2", "0.5")).toBe(99);
    expect(entryExtensionBoundary("LONG", "100", "0", "0.5")).toBeNull();
    expect(entryExtensionBoundary("SHORT", "100", "2", "invalid")).toBeNull();
  });

  it("estimates an immediate long exit from bid after the projected taker fee", () => {
    const estimate = estimateImmediateExit(0.01, -1000, 0.4, 100_100, 100_110, 0.0004);
    expect(estimate?.exitPrice).toBe(100_100);
    expect(estimate?.exitCommission).toBeCloseTo(0.4004);
    expect(estimate?.netResult).toBeCloseTo(0.1996);
  });

  it("estimates an immediate short exit from ask after the projected taker fee", () => {
    const estimate = estimateImmediateExit(-0.01, 1000, 0.4, 99_890, 99_900, 0.0004);
    expect(estimate?.exitPrice).toBe(99_900);
    expect(estimate?.exitCommission).toBeCloseTo(0.3996);
    expect(estimate?.netResult).toBeCloseTo(0.2004);
  });

  it("does not invent an immediate-exit estimate from incomplete inputs", () => {
    expect(estimateImmediateExit(0, 0, 0, 100, 101, 0.0004)).toBeNull();
    expect(estimateImmediateExit(1, -100, 0, 101, 100, 0.0004)).toBeNull();
    expect(estimateImmediateExit(1, -100, 0, 100, 101, Number.NaN)).toBeNull();
  });
});
