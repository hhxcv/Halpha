import { describe, expect, it } from "vitest";

import {
  compactRuntimeMarkerGroupLabel,
  runtimeChartOperationMarkers,
} from "./runtimeChartMarkers";

describe("runtime chart operation markers", () => {
  it("keeps the order operation and the actual fill as distinct chart points", () => {
    const markers = runtimeChartOperationMarkers({
      activationStartedAt: "2026-07-27T01:00:00Z",
      actions: [{
        execution_action_id: "entry-1",
        action_kind: "ENTRY",
        state: "CLOSED",
        call_started_at: "2026-07-27T01:00:01Z",
        action_terms: { quantity: "0.01" },
      }],
      facts: [{
        venue_fact_id: "fill-1",
        kind: "FILL",
        action_ref: "entry-1",
        source_time: "2026-07-27T01:00:02Z",
        payload: {
          trade_id: "trade-1",
          last_price: "65000.1",
          last_quantity: "0.01",
          liquidity_side: "TAKER",
        },
      }],
      timeline: [],
    });

    expect(markers).toMatchObject([
      { label: "计划开始", shortLabel: "起", price: null, category: "PLAN" },
      {
        label: "入场委托",
        shortLabel: "委",
        detail: "数量 0.01 · 已完成",
        price: null,
        category: "ENTRY",
      },
      {
        label: "入场成交",
        shortLabel: "入",
        detail: "成交 0.01 · 约 650.001 USDT · Taker · 成交号 trade-1",
        price: 65000.1,
        priceKind: "TRADE",
        category: "ENTRY",
      },
    ]);
  });

  it("deduplicates reconciliation copies of the same fill", () => {
    const fact = {
      kind: "FILL",
      action_ref: "exit-1",
      source_time: "2026-07-27T02:00:00Z",
      payload: { trade_id: "trade-2", last_price: "65100" },
    };
    const markers = runtimeChartOperationMarkers({
      actions: [{
        execution_action_id: "exit-1",
        action_kind: "EXIT",
        state: "CLOSED",
        call_started_at: "2026-07-27T01:59:59Z",
      }],
      facts: [
        { ...fact, venue_fact_id: "stream-copy" },
        { ...fact, venue_fact_id: "query-copy", source_class: "VENUE_QUERY" },
      ],
      timeline: [],
    });

    expect(markers.filter((marker) => marker.label === "退出成交")).toHaveLength(1);
  });

  it("marks market invalidation and effective user controls without inventing prices", () => {
    const markers = runtimeChartOperationMarkers({
      actions: [],
      facts: [],
      timeline: [
        {
          source: "PLAN_EVENT",
          source_ref: "event-1",
          at: "2026-07-27T03:00:00Z",
          detail: {
            rule_id: "ENTRY_MARKET_INVALIDATION",
            no_action_reason: "ENTRY_MARKET_INVALIDATED",
          },
        },
        {
          source: "CONTROL_COMMAND",
          source_ref: "command-1",
          at: "2026-07-27T03:05:00Z",
          status: "EFFECTIVE",
          detail: { intent: "EXIT_STRATEGY" },
        },
      ],
    });

    expect(markers).toMatchObject([
      { label: "行情失效，取消入场", shortLabel: "失效", price: null, category: "PLAN" },
      { label: "退出计划生效", shortLabel: "控", price: null, category: "CONTROL" },
    ]);
  });

  it("uses the observed mark as an event trigger price when invalidation evidence is available", () => {
    const markers = runtimeChartOperationMarkers({
      actions: [],
      facts: [],
      timeline: [{
        source: "PLAN_EVENT",
        source_ref: "event-with-evidence",
        at: "2026-07-28T05:16:45.188275Z",
        detail: {
          rule_id: "ENTRY_MARKET_INVALIDATION",
          no_action_reason: "ENTRY_MARKET_INVALIDATED",
          capital_decision: {
            evidence: {
              checks: [
                {
                  kind: "INVALIDATION_PRICE",
                  result: "TRUE",
                  direction: "SHORT",
                  configured_price: "63450",
                  observed_mark_price: "63454.07210145",
                },
                {
                  kind: "ADVERSE_MOVE",
                  result: "FALSE",
                  direction: "SHORT",
                  window_seconds: 300,
                  observed_move_bps: "3.069634150763148187266885895",
                  configured_adverse_move_bps: "50",
                },
              ],
            },
          },
        },
      }],
    });

    expect(markers).toMatchObject([{
      label: "行情失效，取消入场",
      shortLabel: "失效",
      detail: "标记价 63,454.0721 已达到失效边界 63,450",
      price: 63454.07210145,
      priceKind: "EVENT",
      category: "PLAN",
    }]);
  });

  it("explains adverse-move invalidation without presenting the candle close as the trigger", () => {
    const markers = runtimeChartOperationMarkers({
      actions: [],
      facts: [],
      timeline: [{
        source: "PLAN_EVENT",
        source_ref: "adverse-move-event",
        at: "2026-07-28T05:20:00Z",
        detail: {
          rule_id: "ENTRY_MARKET_INVALIDATION",
          capital_decision: {
            evidence: {
              checks: [
                {
                  kind: "INVALIDATION_PRICE",
                  result: "FALSE",
                  observed_mark_price: "63420.1",
                },
                {
                  kind: "ADVERSE_MOVE",
                  result: "TRUE",
                  direction: "SHORT",
                  window_seconds: 300,
                  observed_move_bps: "51.25",
                  configured_adverse_move_bps: "50",
                },
              ],
            },
          },
        },
      }],
    });

    expect(markers).toMatchObject([{
      detail: "300 秒 · 逆向上涨 51.25 bps · 已达到 50 bps 失效阈值",
      price: 63420.1,
      priceKind: "EVENT",
    }]);
  });

  it("compacts co-located events into short chart tags", () => {
    const marker = (shortLabel: string) => ({
      id: shortLabel,
      at: "2026-07-27T03:00:00Z",
      label: shortLabel,
      shortLabel,
      detail: "",
      price: null,
      category: "PLAN" as const,
    });
    expect(compactRuntimeMarkerGroupLabel([
      marker("起"),
      marker("委"),
      marker("入"),
    ])).toBe("起·委·入");
    expect(compactRuntimeMarkerGroupLabel([
      marker("委"),
      marker("委"),
      marker("入"),
      marker("损"),
      marker("盈"),
    ])).toBe("委2·入+2");
  });
});
