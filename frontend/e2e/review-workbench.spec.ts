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
        liquidity_side: "TAKER",
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
        liquidity_side: "MAKER",
        fee: "0.04",
        fee_currency: "USDT",
        fill_time: lastFillTime,
      },
    ],
  };
}

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
    trade_context: { instrument_ref: "BTCUSDT-PERP", direction: "LONG", strategy_id: "ONE_SHOT_DONCHIAN_ATR_BREAKOUT", trade_amount: "100" },
    account_result: { trade_result: tradeResult({ entry: "100", exit: "102.5", netPnl: "2.4", grossPnl: "2.5", commission: "0.1", firstFillTime: "2026-07-21T00:20:00Z", lastFillTime: "2026-07-21T00:25:30Z" }) },
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
    trade_context: { instrument_ref: "BTCUSDT-PERP", direction: "LONG", strategy_id: "ONE_SHOT_DONCHIAN_ATR_BREAKOUT", trade_amount: "100" },
    account_result: { trade_result: tradeResult({ entry: "101", exit: "100", netPnl: "-0.9", grossPnl: "-0.8", commission: "0.1", firstFillTime: "2026-07-21T00:10:00Z", lastFillTime: "2026-07-21T00:15:30Z" }) },
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
  },
];

async function mockProfessionalReviews(page: Page) {
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
      strategy: { strategy_ref: "ONE_SHOT_DONCHIAN_ATR_BREAKOUT@1" },
      execution_actions: [
        { action_kind: "PROTECTION", state: "RECONCILED", action_terms: { trigger_price: "98.5" } },
        { action_kind: "TAKE_PROFIT", state: "RECONCILED", action_terms: { trigger_price: "102.5" } },
        { action_kind: "TAKE_PROFIT", state: "NOT_SUBMITTED", action_terms: { trigger_price: "104" } },
      ],
    }) });
  });
}

async function assertAccessible(page: Page, testInfo: TestInfo, name: string) {
  const violations = (await new AxeBuilder({ page }).analyze()).violations;
  await testInfo.attach(`${name}-axe.json`, { body: Buffer.from(JSON.stringify(violations, null, 2)), contentType: "application/json" });
  expect(violations).toEqual([]);
}

test("review workbench exposes recent performance and one visual trade narrative", async ({ page }, testInfo) => {
  await mockProfessionalReviews(page);
  await page.goto("/reviews");

  await expect(page.getByRole("group", { name: "近期已闭合交易累计净盈亏趋势" })).toBeVisible();
  await expect(page.getByText("+3.30 USDT", { exact: true })).toBeVisible();
  await expect(page.getByRole("table", { name: "交易与复盘记录" })).toContainText("-0.90 USDT");
  await expect(page.getByRole("table", { name: "交易与复盘记录" })).toContainText("按计划止盈");
  const listScreenshot = testInfo.outputPath(`review-list-${testInfo.project.name}.png`);
  await page.screenshot({ path: listScreenshot, fullPage: true });
  await testInfo.attach(`review-list-${testInfo.project.name}.png`, { path: listScreenshot, contentType: "image/png" });

  await page.getByRole("table", { name: "交易与复盘记录" }).getByRole("button", { name: "复盘" }).first().click();
  await expect(page.getByRole("heading", { name: "交易价格回看" })).toBeVisible();
  await expect(page.getByRole("group", { name: /1m K 线图/ })).toBeVisible();
  await page.getByRole("button", { name: "15 分钟" }).click();
  await expect(page.getByRole("group", { name: /15m K 线图/ })).toBeVisible();
  await page.getByRole("button", { name: "1 分钟" }).click();
  await expect(page.getByRole("group", { name: /1m K 线图/ })).toBeVisible();
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
