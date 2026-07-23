import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type TestInfo } from "@playwright/test";

type JsonRecord = Record<string, unknown>;

function tradeResult({
  entry,
  exit,
  netPnl,
  grossPnl,
  commission,
  firstFillTime,
  lastFillTime,
}: {
  entry: string;
  exit: string;
  netPnl: string;
  grossPnl: string;
  commission: string;
  firstFillTime: string;
  lastFillTime: string;
}) {
  return {
    calculation_complete: true,
    closed: true,
    gross_pnl: grossPnl,
    commission,
    net_pnl: netPnl,
    average_entry_price: entry,
    average_exit_price: exit,
    entry_notional: "100.00",
    holding_duration_seconds: (Date.parse(lastFillTime) - Date.parse(firstFillTime)) / 1000,
    fill_times_complete: true,
    first_fill_time: firstFillTime,
    last_fill_time: lastFillTime,
    fills: [
      {
        trade_id: `entry-${firstFillTime}`,
        action_kind: "ENTRY",
        quantity: "1",
        price: entry,
        notional: "100.00",
        liquidity_side: "2",
        fee: "0.06",
        fee_currency: "USDT",
        fill_time: firstFillTime,
      },
      {
        trade_id: `exit-${lastFillTime}`,
        action_kind: "TAKE_PROFIT",
        quantity: "1",
        price: exit,
        notional: exit,
        liquidity_side: "1",
        fee: "0.04",
        fee_currency: "USDT",
        fill_time: lastFillTime,
      },
    ],
  };
}

const professionalThreeTradeResult = tradeResult({
  entry: "100",
  exit: "102.5",
  netPnl: "2.4",
  grossPnl: "2.5",
  commission: "0.1",
  firstFillTime: "2026-07-21T00:20:00Z",
  lastFillTime: "2026-07-21T00:25:30Z",
});
const externalClosureTradeResult = tradeResult({
  entry: "101",
  exit: "100",
  netPnl: "-0.9",
  grossPnl: "-0.8",
  commission: "0.1",
  firstFillTime: "2026-07-21T00:10:00Z",
  lastFillTime: "2026-07-21T00:15:30Z",
});
externalClosureTradeResult.result_scope = "ACCOUNT_FACTS_WITH_EXTERNAL_CLOSURE";
externalClosureTradeResult.strategy_attribution_complete = false;
externalClosureTradeResult.fills[1].action_kind = "EXTERNAL_ACCOUNT_CLOSURE";
const legacyProfessionalThreeTradeResult = {
  calculation_complete: professionalThreeTradeResult.calculation_complete,
  closed: professionalThreeTradeResult.closed,
  gross_pnl: professionalThreeTradeResult.gross_pnl,
  commission: professionalThreeTradeResult.commission,
  net_pnl: professionalThreeTradeResult.net_pnl,
  average_entry_price: professionalThreeTradeResult.average_entry_price,
};

const reviews: JsonRecord[] = [
  {
    review_id: "review-professional-3",
    review_version: 1,
    activation_id: "activation-professional-3",
    status: "COMPLETE",
    primary_result: "COMPLETED",
    fact_cutoff: "2026-07-21T00:28:00Z",
    content_digest: "3".repeat(64),
    evidence_purpose: "SYSTEM_MECHANISM_EVIDENCE",
    input_refs: { plan_events: [{}], execution_actions: [{}, {}, {}], venue_facts: [{}, {}, {}, {}], commands_and_receipts: [] },
    open_responsibilities: { execution_action_refs: [], unknown_action_refs: [] },
    evaluations: { owner_conclusion: { result: "AS_EXPECTED", reason: "按计划止盈", evidence_refs: [] } },
    trade_context: { plan_name: "AI BTC 突破复核", instrument_ref: "BTCUSDT-PERP", direction: "LONG", strategy_id: "ONE_SHOT_DONCHIAN_ATR_BREAKOUT", trade_amount: "100" },
    account_result: { trade_result: legacyProfessionalThreeTradeResult },
    resolved_trade_result: professionalThreeTradeResult,
  },
  {
    review_id: "review-professional-2",
    review_version: 1,
    activation_id: "activation-professional-2",
    status: "COMPLETE",
    primary_result: "COMPLETED",
    fact_cutoff: "2026-07-21T00:18:00Z",
    content_digest: "2".repeat(64),
    input_refs: {},
    open_responsibilities: {},
    evaluations: { owner_conclusion: { result: "ISSUE_FOUND", reason: "突破后回落", evidence_refs: [] } },
    trade_context: { instrument_ref: "ETHUSDT-PERP", direction: "LONG", strategy_id: "MEAN_REVERSION_TEST", trade_amount: "100" },
    account_result: { trade_result: tradeResult({ entry: "101", exit: "100", netPnl: "-0.9", grossPnl: "-0.8", commission: "0.1", firstFillTime: "2026-07-21T00:10:00Z", lastFillTime: "2026-07-21T00:15:30Z" }) },
    resolved_trade_result: externalClosureTradeResult,
  },
  {
    review_id: "review-professional-1",
    review_version: 1,
    activation_id: "activation-professional-1",
    status: "COMPLETE",
    primary_result: "COMPLETED",
    fact_cutoff: "2026-07-21T00:08:00Z",
    content_digest: "1".repeat(64),
    input_refs: {},
    open_responsibilities: {},
    evaluations: { owner_conclusion: { result: "AS_EXPECTED", reason: "保护退出正常", evidence_refs: [] } },
    trade_context: { instrument_ref: "BTCUSDT-PERP", direction: "SHORT", strategy_id: "ONE_SHOT_DONCHIAN_ATR_BREAKOUT", trade_amount: "100" },
    account_result: { trade_result: tradeResult({ entry: "102", exit: "100", netPnl: "1.8", grossPnl: "1.9", commission: "0.1", firstFillTime: "2026-07-21T00:00:00Z", lastFillTime: "2026-07-21T00:05:30Z" }) },
    resolved_trade_result: tradeResult({ entry: "102", exit: "100", netPnl: "1.8", grossPnl: "1.9", commission: "0.1", firstFillTime: "2026-07-21T00:00:00Z", lastFillTime: "2026-07-21T00:05:30Z" }),
  },
];

async function mockProfessionalReviews(page: Page) {
  await page.route("**/api/v1/market-window**", async (route) => {
    const requestUrl = new URL(route.request().url());
    const interval = requestUrl.searchParams.get("interval") === "15m" ? "15m" : "1m";
    const intervalMs = interval === "15m" ? 15 * 60_000 : 60_000;
    const requestedStart = Date.parse(requestUrl.searchParams.get("start_at") ?? "");
    const startAt = Number.isFinite(requestedStart) ? requestedStart : Date.parse("2026-07-20T23:56:00Z");
    const bars = Array.from({ length: 48 }, (_value, index) => {
      const open = 99.4 + index * 0.07;
      const close = open + (index % 3 === 0 ? -0.12 : 0.16);
      return {
        open_at: new Date(startAt + index * intervalMs).toISOString(),
        close_at: new Date(startAt + (index + 1) * intervalMs).toISOString(),
        open: open.toFixed(2),
        high: (Math.max(open, close) + 0.18).toFixed(2),
        low: (Math.min(open, close) - 0.16).toFixed(2),
        close: close.toFixed(2),
        volume: String(100 + index),
      };
    });
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({
      instrument_ref: "BTCUSDT-PERP",
      interval,
      source: "BINANCE_DEMO_PUBLIC",
      source_cutoff: bars.at(-1)?.close_at,
      bars,
    }) });
  });
  await page.route("**/api/v1/reviews**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/v1/reviews") {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(reviews) });
      return;
    }
    if (path === "/api/v1/reviews/review-professional-3") {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify({ review: reviews[0] }) });
      return;
    }
    await route.fallback();
  });
  await page.route("**/api/v1/activations/activation-professional-3**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/timeline")) {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify([{
        source: "PLAN_EVENT",
        source_ref: "plan-event-entry-3",
        status: "PROPOSED_ACTION_CAP_ACCEPTED",
        at: "2026-07-21T00:19:58Z",
        detail: { rule_id: "ENTRY_BREAKOUT", source_identity: "BTCUSDT 15m 闭合 K 线", source_cutoff: "2026-07-21T00:19:00Z" },
      }]) });
      return;
    }
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({
      activation: { activation_id: "activation-professional-3", updated_at: "2026-07-21T00:28:00Z" },
      plan: { plan_name: "AI BTC 突破复核", creator_kind: "AI", created_at: "2026-07-21T00:00:00Z" },
      strategy: { strategy_ref: "ONE_SHOT_DONCHIAN_ATR_BREAKOUT@1" },
      trade_result: professionalThreeTradeResult,
      execution_actions: [
        { action_kind: "PROTECTION", state: "CLOSED", action_terms: { trigger_price: "98.5" } },
        { action_kind: "TAKE_PROFIT", state: "CLOSED", action_terms: { trigger_price: "102.5" } },
        { action_kind: "TAKE_PROFIT", state: "NOT_SUBMITTED", action_terms: { trigger_price: "104" } },
      ],
    }) });
  });
}

async function mockDirectExecutionReviews(page: Page) {
  const directTradeResult = tradeResult({
    entry: "100",
    exit: "101",
    netPnl: "0.8",
    grossPnl: "1",
    commission: "0.2",
    firstFillTime: "2026-07-23T03:19:21Z",
    lastFillTime: "2026-07-23T03:20:14Z",
  });
  directTradeResult.fills[1].action_kind = "EXIT";
  const incompleteTradeResult = {
    fill_count: 0,
    fills: [],
    position_quantity: "0",
    average_entry_price: null,
    average_exit_price: null,
    entry_notional: "0",
    commission: "0",
    commission_complete: false,
    calculation_complete: false,
    closed: false,
    gross_pnl: null,
    net_pnl: null,
    fill_times_complete: false,
    first_fill_time: null,
    last_fill_time: null,
    holding_duration_seconds: null,
    unresolved_refs: [],
  };
  const directReviews: JsonRecord[] = [
    {
      review_id: "review-direct-complete",
      review_version: 1,
      activation_id: "activation-direct-complete",
      status: "DRAFT",
      primary_result: "COMPLETED",
      fact_cutoff: "2026-07-23T03:20:15Z",
      content_digest: "d".repeat(64),
      input_refs: { plan_events: [{}, {}], execution_actions: [{}, {}], venue_facts: [{}, {}, {}, {}], commands_and_receipts: [] },
      open_responsibilities: { execution_action_refs: [], unknown_action_refs: [] },
      evaluations: { owner_conclusion: { result: "UNKNOWN", reason: "", evidence_refs: [] } },
      trade_context: {
        plan_name: "直接执行完整成交",
        instrument_ref: "BTCUSDT-PERP",
        direction: "LONG",
        decision_basis_ref: "DIRECT_EXECUTION@1",
        strategy_id: null,
        trade_amount: "100",
      },
      account_result: { trade_result: directTradeResult },
      resolved_trade_result: directTradeResult,
    },
    {
      review_id: "review-direct-partial",
      review_version: 1,
      activation_id: "activation-direct-partial",
      status: "DRAFT",
      primary_result: "PARTIAL",
      fact_cutoff: "2026-07-23T03:18:40Z",
      content_digest: "p".repeat(64),
      input_refs: { plan_events: [{}], execution_actions: [{}], venue_facts: [], commands_and_receipts: [] },
      open_responsibilities: { execution_action_refs: ["entry-open"], unknown_action_refs: [] },
      evaluations: { owner_conclusion: { result: "UNKNOWN", reason: "", evidence_refs: [] } },
      trade_context: {
        plan_name: "直接执行责任待闭合",
        instrument_ref: "BTCUSDT-PERP",
        direction: "LONG",
        decision_basis_ref: "DIRECT_EXECUTION@1",
        strategy_id: null,
        trade_amount: "100",
      },
      account_result: { trade_result: incompleteTradeResult },
      resolved_trade_result: incompleteTradeResult,
    },
    {
      review_id: "review-direct-no-action",
      review_version: 1,
      activation_id: "activation-direct-no-action",
      status: "COMPLETE",
      primary_result: "NO_ACTION",
      fact_cutoff: "2026-07-23T03:40:00Z",
      content_digest: "n".repeat(64),
      input_refs: { plan_events: [], execution_actions: [], venue_facts: [], commands_and_receipts: [] },
      open_responsibilities: { execution_action_refs: [], unknown_action_refs: [] },
      evaluations: { owner_conclusion: { result: "NOT_APPLICABLE", reason: "", evidence_refs: [] } },
      trade_context: {
        plan_name: "直接执行未发生交易",
        instrument_ref: "BTCUSDT-PERP",
        direction: "LONG",
        decision_basis_ref: "DIRECT_EXECUTION@1",
        activation_updated_at: "2026-07-23T03:16:00Z",
        strategy_id: null,
        trade_amount: "100",
      },
      account_result: { trade_result: incompleteTradeResult },
      resolved_trade_result: incompleteTradeResult,
    },
  ];
  await page.route("**/api/v1/market-window**", async (route) => {
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({
      instrument_ref: "BTCUSDT-PERP",
      interval: "1m",
      source: "BINANCE_DEMO_PUBLIC",
      source_cutoff: "2026-07-23T03:30:00Z",
      bars: [],
    }) });
  });
  await page.route("**/api/v1/reviews**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/v1/reviews") {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify(directReviews) });
      return;
    }
    if (path === "/api/v1/reviews/review-direct-complete") {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify({ review: directReviews[0] }) });
      return;
    }
    await route.fallback();
  });
  await page.route("**/api/v1/activations/activation-direct-complete**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/timeline")) {
      await route.fulfill({ contentType: "application/json", body: JSON.stringify([0, 1].map((index) => ({
        source: "PLAN_EVENT",
        source_ref: `direct-leg-event-${index}`,
        status: "PROPOSED_ACTION_CAP_ACCEPTED",
        at: "2026-07-23T03:19:20Z",
        detail: {
          rule_id: "DIRECT_ORDER_SCHEDULE_LEG",
          source_identity: `activation-direct-complete:ORDER_SCHEDULE:digest:LEG:${index}`,
          source_cutoff: "2026-07-23T03:19:20Z",
        },
      }))) });
      return;
    }
    await route.fulfill({ contentType: "application/json", body: JSON.stringify({
      activation: {
        activation_id: "activation-direct-complete",
        decision_basis_ref: "DIRECT_EXECUTION@1",
        updated_at: "2026-07-23T03:20:15Z",
      },
      plan: { plan_name: "直接执行完整成交", creator_kind: "AI", created_at: "2026-07-23T03:18:00Z" },
      strategy: null,
      trade_result: directTradeResult,
      execution_actions: [],
    }) });
  });
}

async function assertAccessible(page: Page, testInfo: TestInfo, name: string) {
  const violations = (await new AxeBuilder({ page }).analyze()).violations;
  await testInfo.attach(`${name}-axe.json`, { body: Buffer.from(JSON.stringify(violations, null, 2)), contentType: "application/json" });
  expect(violations).toEqual([]);
}

async function chooseFilter(page: Page, label: string, option: string) {
  await page.getByRole("combobox", { name: label, exact: true }).click();
  await page.getByRole("option", { name: option, exact: true }).click();
  await page.getByRole("listbox").waitFor({ state: "detached" });
  await expect(page.locator('[role="option"]')).toHaveCount(0);
}

test("review records support conjunctive strategy, instrument, direction, pnl, result and conclusion filters", async ({ page }, testInfo) => {
  await mockProfessionalReviews(page);
  await page.goto("/reviews");

  await chooseFilter(page, "决策依据 / 策略", "MEAN_REVERSION_TEST");
  await chooseFilter(page, "交易对象", "ETHUSDT-PERP");
  await chooseFilter(page, "方向", "做多");
  await chooseFilter(page, "盈亏", "亏损");
  await chooseFilter(page, "交易结果", "已完成交易");
  await chooseFilter(page, "人工结论", "发现问题");

  const table = page.getByRole("table", { name: "交易与复盘记录" });
  await expect(table.locator("tbody tr")).toHaveCount(1);
  await expect(table).toContainText("ETHUSDT-PERP");
  await expect(table).toContainText("-0.90 USDT");
  await expect(page.getByText("条件同时满足 · 匹配 1 / 3 条 · 已选 6 项", { exact: true })).toBeVisible();
  const layout = await page.evaluate(() => ({ clientWidth: document.documentElement.clientWidth, scrollWidth: document.documentElement.scrollWidth }));
  expect(layout.scrollWidth).toBe(layout.clientWidth);
  await assertAccessible(page, testInfo, `review-filters-${testInfo.project.name}`);
  const filterScreenshot = testInfo.outputPath(`review-filters-${testInfo.project.name}.png`);
  await page.screenshot({ path: filterScreenshot, fullPage: true });
  await testInfo.attach(`review-filters-${testInfo.project.name}.png`, { path: filterScreenshot, contentType: "image/png" });

  await chooseFilter(page, "方向", "做空");
  await expect(page.getByText("当前筛选下没有复盘记录。")).toBeVisible();
  await expect(table.locator("tbody tr")).toHaveCount(0);

  await page.getByRole("button", { name: "重置筛选" }).click();
  await expect(table.locator("tbody tr")).toHaveCount(3);
  await expect(page.getByText("条件同时满足 · 匹配 3 / 3 条", { exact: true })).toBeVisible();
  const keyboardReviewRow = table.locator("tbody tr").first();
  await keyboardReviewRow.focus();
  await expect(keyboardReviewRow).toBeFocused();
  await page.keyboard.press(" ");
  await expect(page.getByRole("heading", { name: "交易价格回看" })).toBeVisible();
});

test("direct-execution reviews use their authoritative basis and keep incomplete facts distinct from zero", async ({ page }, testInfo) => {
  await mockDirectExecutionReviews(page);
  await page.goto("/reviews");

  const table = page.getByRole("table", { name: "交易与复盘记录" });
  const completeRow = table.getByRole("row", { name: /查看 BTCUSDT-PERP 做多 2026-07-23 11:20:14/ });
  await expect(completeRow.locator("td").nth(2)).toContainText("直接执行订单计划");
  const partialRow = table.getByRole("row", { name: /查看 BTCUSDT-PERP 做多 2026-07-23 11:18:40/ });
  await expect(partialRow.locator("td").nth(2)).toContainText("直接执行订单计划");
  await expect(partialRow.locator("td").nth(3)).toHaveText("未知 / 未知");
  await expect(partialRow.locator("td").nth(7)).toContainText("未知");
  await expect(partialRow.locator("td").nth(7)).toContainText("1 个责任尚未闭合");
  await expect(partialRow.locator("td").nth(7)).not.toContainText("0 秒");

  await page.getByRole("tab", { name: "全部激活（3）" }).click();
  await expect(table.locator("tbody tr").first()).toHaveAttribute(
    "aria-label",
    /查看 BTCUSDT-PERP 做多 2026-07-23 11:20:14/,
  );
  const noActionRow = table.getByRole("row", { name: /查看 BTCUSDT-PERP 做多 2026-07-23 11:16:00/ });
  await expect(noActionRow.locator("td").nth(3)).toHaveText("不适用");
  await expect(noActionRow.locator("td").nth(4)).toHaveText("不适用");
  await expect(noActionRow.locator("td").nth(5)).toHaveText("不适用");
  await expect(noActionRow.locator("td").nth(6)).toHaveText("不适用");

  await completeRow.click();
  await expect(page.getByText("直接执行订单计划 · 闭合于", { exact: false })).toBeVisible();
  await expect(page.getByText("DIRECT_EXECUTION@1", { exact: true })).toBeVisible();
  await expect(page.getByText("操作理由", { exact: true }).locator("..")).toContainText("直接执行订单计划的 2 个入场档位已通过资金检查");
  await expect(page.getByText("触发来源", { exact: true }).locator("..")).toContainText("直接执行订单计划");
  await expect(page.getByText("触发来源", { exact: true }).locator("..")).toContainText("DIRECT_EXECUTION@1");
  await assertAccessible(page, testInfo, `review-direct-${testInfo.project.name}`);
});

test("review workbench exposes full-history performance and one visual trade narrative", async ({ page }, testInfo) => {
  await mockProfessionalReviews(page);
  await page.goto("/reviews");

  await expect(page.getByRole("group", { name: "全部已闭合交易累计净盈亏趋势" })).toBeVisible();
  await expect(page.getByText("+3.30 USDT", { exact: true })).toBeVisible();
  await expect(page.getByRole("table", { name: "交易与复盘记录" })).toContainText("-0.90 USDT");
  await expect(page.getByRole("table", { name: "交易与复盘记录" })).toContainText("按计划止盈");
  await expect(page.getByRole("table", { name: "交易与复盘记录" })).toContainText("AI BTC 突破复核");
  await expect(page.getByRole("table", { name: "交易与复盘记录" })).toContainText("账户结果");
  await expect(page.getByRole("table", { name: "交易与复盘记录" })).toContainText("外部应急平仓");
  const firstTradeRow = page.getByRole("table", { name: "交易与复盘记录" }).locator("tbody tr").first();
  await expect(firstTradeRow.locator("td").nth(3)).toHaveText("100.00 / 102.50");
  await expect(firstTradeRow.locator("td").nth(4)).toHaveText("100.00 USDT");
  const listScreenshot = testInfo.outputPath(`review-list-${testInfo.project.name}.png`);
  await page.screenshot({ path: listScreenshot, fullPage: true });
  await testInfo.attach(`review-list-${testInfo.project.name}.png`, { path: listScreenshot, contentType: "image/png" });

  await page.getByRole("table", { name: "交易与复盘记录" }).locator("tbody tr").first().click();
  await expect(page.getByRole("heading", { name: "AI BTC 突破复核" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "交易价格回看" })).toBeVisible();
  await expect(page.getByRole("group", { name: /1m K 线图/ })).toBeVisible();
  await page.getByRole("button", { name: "15 分钟" }).click();
  await expect(page.getByRole("group", { name: /15m K 线图/ })).toBeVisible();
  await page.getByRole("button", { name: "1 分钟" }).click();
  await expect(page.getByRole("group", { name: /1m K 线图/ })).toBeVisible();
  await expect(page.getByText("平均入场价", { exact: true }).locator("..")).toContainText("100.00 USDT");
  await expect(page.getByText("平均出场价", { exact: true }).locator("..")).toContainText("102.50 USDT");
  await expect(page.getByText("持仓周期", { exact: true }).locator("..")).toContainText("5 分钟 30 秒");
  await expect(page.getByRole("table", { name: "本次复盘成交明细" })).toContainText("吃单");
  await expect(page.getByRole("table", { name: "本次复盘成交明细" })).toContainText("挂单");
  await expect(page.getByRole("heading", { name: "机器为何交易" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "我的结论" })).toBeVisible();
  const layout = await page.evaluate(() => ({ clientWidth: document.documentElement.clientWidth, scrollWidth: document.documentElement.scrollWidth }));
  expect(layout.scrollWidth).toBe(layout.clientWidth);
  await assertAccessible(page, testInfo, `review-detail-${testInfo.project.name}`);
  const detailScreenshot = testInfo.outputPath(`review-detail-${testInfo.project.name}.png`);
  await page.screenshot({ path: detailScreenshot, fullPage: true });
  await testInfo.attach(`review-detail-${testInfo.project.name}.png`, { path: detailScreenshot, contentType: "image/png" });
});
