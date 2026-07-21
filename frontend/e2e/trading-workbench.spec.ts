import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type TestInfo } from "@playwright/test";

type Activation = {
  activation_id: string;
  instrument_ref: string;
  lifecycle: string;
};

type PlanSummary = {
  plan_version_id: string | null;
};

async function activations(page: Page): Promise<Activation[]> {
  return page.evaluate(async () => {
    const response = await fetch("/api/v1/activations", { credentials: "same-origin" });
    if (!response.ok) throw new Error(`ACTIVATIONS_HTTP_${response.status}`);
    return response.json();
  });
}

async function assertAccessible(page: Page, testInfo: TestInfo, name: string) {
  const result = await new AxeBuilder({ page }).analyze();
  const violations = result.violations.map(({ id, impact, nodes }) => ({
    id,
    impact,
    nodeCount: nodes.length,
    nodes: nodes.map((node) => ({
      target: node.target,
      html: node.html,
      failureSummary: node.failureSummary,
    })),
  }));
  await testInfo.attach(`${name}-axe.json`, {
    body: Buffer.from(JSON.stringify({ url: page.url(), violations }, null, 2)),
    contentType: "application/json",
  });
  expect(violations).toEqual([]);
}

async function assertNoDocumentOverflow(page: Page, testInfo: TestInfo, name: string) {
  const layout = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
    offenders: [...document.querySelectorAll<HTMLElement>("body *")]
      .filter((element) => !element.closest(".table-scroll"))
      .filter((element) => getComputedStyle(element).visibility !== "hidden")
      .map((element) => {
        const bounds = element.getBoundingClientRect();
        return {
          tag: element.tagName,
          className: element.className,
          left: bounds.left,
          right: bounds.right,
          text: element.textContent?.trim().slice(0, 120) ?? "",
        };
      })
      .filter(({ left, right }) => left < -0.5 || right > document.documentElement.clientWidth + 0.5),
  }));
  await testInfo.attach(`${name}-layout.json`, {
    body: Buffer.from(JSON.stringify(layout, null, 2)),
    contentType: "application/json",
  });
  expect(layout.offenders).toEqual([]);
  expect(layout.scrollWidth).toBe(layout.clientWidth);
}

test("the workbench exposes unknown, protection gap, max loss, exit, takeover, closure and review without collapsing responsibility", async ({ page }, testInfo) => {
  await page.goto("/overview");
  const items = await activations(page);
  const gap = items.find((item) => item.instrument_ref === "BTCUSDT-PERP" && item.lifecycle !== "COMPLETED");
  const exiting = items.find((item) => item.lifecycle === "EXITING");
  const takeover = items.find((item) => item.lifecycle === "USER_TAKEOVER");
  expect(gap).toBeTruthy();
  expect(exiting).toBeTruthy();
  expect(takeover).toBeTruthy();

  await page.goto(`/activations/${gap!.activation_id}`);
  await expect(page.getByRole("heading", { name: "激活运行与控制" })).toBeVisible();
  await expect(page.getByRole("alert").filter({ hasText: "交易所原生保护尚未证明为工作中" })).toBeVisible();
  await expect(page.getByRole("alert", { name: "" }).filter({ hasText: "WORKBENCH_UNKNOWN_RESULT" })).toBeVisible();
  await expect(page.getByRole("alert").filter({ hasText: "计划已触发停止新增风险" })).toBeVisible();
  await assertAccessible(page, testInfo, "trading-gap-unknown-max-loss");
  await testInfo.attach("trading-gap-unknown-max-loss.png", {
    body: await page.screenshot({ fullPage: true }),
    contentType: "image/png",
  });

  await page.goto(`/activations/${exiting!.activation_id}`);
  await expect(page.getByText("正在退出", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("策略行为只作次要验证")).toBeVisible();

  await page.goto(`/activations/${takeover!.activation_id}`);
  await expect(page.getByRole("alert").filter({ hasText: "用户接管已持久化" })).toBeVisible();
  await expect(page.getByRole("alert").filter({ hasText: "Halpha 不再提交新的待执行动作" })).toBeVisible();
  await assertAccessible(page, testInfo, "trading-user-takeover");

  await page.goto("/reviews");
  await expect(page.getByRole("table", { name: "交易与复盘记录" })).toBeVisible();
  await page.getByRole("tab", { name: /全部激活/ }).click();
  await expect(page.getByText("未发生交易").first()).toBeVisible();
  await expect(page.getByText("待评价").first()).toBeVisible();
  await page.getByRole("table", { name: "交易与复盘记录" }).locator("tbody tr").first().click();
  await expect(page.getByRole("heading", { name: "交易价格回看" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "机器为何交易" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "我的结论" })).toBeVisible();
  await expect(page.getByText("图表不替代持久成交事实", { exact: false })).toBeVisible();
  await assertAccessible(page, testInfo, "trading-review");

  await page.goto("/operations");
  await expect(page.getByRole("heading", { name: "故障接管" })).toBeVisible();
  await expect(page.getByRole("link", { name: "打开 Binance 官方入口" })).toBeVisible();
  await expect(page.locator("article.activation").filter({ hasText: "BTCUSDT-PERP" }).getByText("GAP", { exact: true })).toBeVisible();
  await expect(page.getByText("EXITING", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("USER_TAKEOVER", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("恢复激活", { exact: false })).toHaveCount(0);
  await expect(page.locator("table")).toHaveCount(0);
  await assertAccessible(page, testInfo, "trading-operations");

  await assertNoDocumentOverflow(page, testInfo, "trading-operations");
});

test("the workbench renders the synthetic LIVE strategy-start target state without an exchange-changing request", async ({ page }, testInfo) => {
  await page.goto("/overview");

  const fixtureFacts = await page.evaluate(async () => {
    const [statusResponse, plansResponse] = await Promise.all([
      fetch("/api/v1/settings/status", { credentials: "same-origin" }),
      fetch("/api/v1/plans", { credentials: "same-origin" }),
    ]);
    if (!statusResponse.ok) throw new Error(`SETTINGS_HTTP_${statusResponse.status}`);
    if (!plansResponse.ok) throw new Error(`PLANS_HTTP_${plansResponse.status}`);
    return {
      status: await statusResponse.json() as Record<string, unknown>,
      plans: await plansResponse.json() as PlanSummary[],
    };
  });
  const planVersionId = fixtureFacts.plans.find((plan) => plan.plan_version_id)?.plan_version_id;
  expect(planVersionId).toBeTruthy();

  let projectedStatus: Record<string, unknown> = {
    ...fixtureFacts.status,
    environment_kind: "LIVE",
    environment_id: "synthetic-live-target-environment",
    account_id: "synthetic-live-target-account",
    profile: "BINANCE_LIVE_WRITE",
    authority_class: "LIVE_REAL_CAPITAL",
    product_build_id: "a".repeat(64),
    app_executor_product_build_consistent: true,
    executor_status: "READY",
    executor_status_checked_at: "2026-07-21T00:00:00Z",
    configured_runtime_real_write_gate: "CLOSED",
    runtime_real_write_gate: "CLOSED",
    live_write_gate_violations: [],
  };
  let projectedPreview: Record<string, unknown> | undefined;
  let activationSubmissions = 0;
  page.on("request", (request) => {
    if (request.method() === "POST" && /\/api\/v1\/activations$/.test(request.url())) {
      activationSubmissions += 1;
    }
  });
  await page.route("**/api/v1/settings/status", (route) => route.fulfill({ json: projectedStatus }));
  await page.route("**/api/v1/plan-versions/*/activation-preview", async (route) => {
    const response = await route.fetch();
    const actualPreview = await response.json() as Record<string, unknown>;
    projectedPreview ??= {
      ...actualPreview,
      environment_kind: "LIVE",
      authority_class: "LIVE_REAL_CAPITAL",
      account_ref: "synthetic-live-target-account",
      product_build_id: "a".repeat(64),
      product_build_consistent: true,
      executor_status: "READY",
      executor_status_checked_at: "2026-07-21T00:00:00Z",
      configured_runtime_real_write_gate: "CLOSED",
      runtime_real_write_gate: "CLOSED",
      live_activation_eligible: true,
    };
    await route.fulfill({ response, json: projectedPreview });
  });

  await testInfo.attach("synthetic-live-target-state.json", {
    body: Buffer.from(JSON.stringify({
      fixture_kind: "SYNTHETIC_LIVE_TARGET_STATE",
      venue_writes: false,
      activation_submission_exercised: false,
      purpose: "STRATEGY_START_UI_AND_GATE_VALIDATION_ONLY",
    }, null, 2)),
    contentType: "application/json",
  });

  await page.goto(`/plans/${planVersionId}/activate`);
  await expect(page.getByText("LIVE", { exact: true })).toBeVisible();
  await expect(page.getByText("DEMO", { exact: true })).toHaveCount(0);
  await expect(page.getByText("真实账户交易 · 已关闭")).toBeVisible();
  await expect(page.getByRole("heading", { name: "确认启动策略" })).toBeVisible();
  await expect(page.getByText("策略计划中的交易金额就是本次边界", { exact: false })).toBeVisible();
  const submit = page.getByRole("button", { name: "启动真实账户策略" });
  await expect(submit).toBeEnabled();
  await assertAccessible(page, testInfo, "trading-synthetic-live-closed");
  await assertNoDocumentOverflow(page, testInfo, "trading-synthetic-live-closed");
  await page.evaluate(() => window.scrollTo(0, 0));
  await testInfo.attach("trading-synthetic-live-closed.png", {
    body: await page.screenshot({ fullPage: true }),
    contentType: "image/png",
  });

  projectedStatus = {
    ...projectedStatus,
    executor_status: "STARTING",
    app_executor_product_build_consistent: null,
  };
  projectedPreview = {
    ...projectedPreview,
    executor_status: "STARTING",
  };
  await page.reload();
  await expect(page.getByText("执行器尚未完成连接、启动核对和历史预热", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "执行器未就绪，不能启动" })).toBeDisabled();

  projectedStatus = {
    ...projectedStatus,
    executor_status: "READY",
    app_executor_product_build_consistent: true,
    configured_runtime_real_write_gate: "OPEN",
    runtime_real_write_gate: "OPEN",
  };
  projectedPreview = {
    ...projectedPreview,
    executor_status: "READY",
    configured_runtime_real_write_gate: "OPEN",
    runtime_real_write_gate: "OPEN",
    live_activation_eligible: false,
  };
  await page.reload();
  await expect(page.getByText("真实账户交易 · 已开启")).toBeVisible();
  await expect(page.getByText("当前产品版本或交易所变更请求配置不一致；当前不能启动真实账户策略。")).toBeVisible();
  await expect(page.getByRole("button", { name: "启动真实账户策略" })).toBeDisabled();
  await assertAccessible(page, testInfo, "trading-synthetic-live-open");
  await assertNoDocumentOverflow(page, testInfo, "trading-synthetic-live-open");
  await page.evaluate(() => window.scrollTo(0, 0));
  await testInfo.attach("trading-synthetic-live-open.png", {
    body: await page.screenshot({ fullPage: true }),
    contentType: "image/png",
  });
  expect(activationSubmissions).toBe(0);
});

test("the workbench rejects a stale control submission instead of applying a newer activation version", async ({ page, context }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium-desktop", "One state-changing stale-version drill is sufficient.");
  await page.goto("/overview");
  const items = await activations(page);
  const staleControl = items.find((item) => item.instrument_ref === "XRPUSDT-PERP" && item.lifecycle === "RUNNING");
  expect(staleControl).toBeTruthy();

  const stalePage = await context.newPage();
  await Promise.all([
    page.goto(`/activations/${staleControl!.activation_id}`),
    stalePage.goto(`/activations/${staleControl!.activation_id}`),
  ]);
  await expect(page.getByText("XRPUSDT-PERP / 做多", { exact: true })).toBeVisible();
  await expect(stalePage.getByText("XRPUSDT-PERP / 做多", { exact: true })).toBeVisible();
  await stalePage.route(
    new RegExp(`/api/v1/activations/${staleControl!.activation_id}$`),
    (route) => route.abort(),
  );

  await page.getByRole("button", { name: "退出策略" }).click();
  await page.getByRole("button", { name: "确认退出策略" }).click();
  await expect(page.getByRole("alert").filter({ hasText: "命令已生效，当前执行责任已经核对" })).toBeVisible();

  await stalePage.getByRole("button", { name: "用户接管" }).click();
  await stalePage.getByRole("button", { name: "确认用户接管" }).click();
  await expect(stalePage.getByRole("alert").filter({ hasText: "PLAN_VERSION_CONFLICT" })).toBeVisible();
  await assertAccessible(stalePage, testInfo, "trading-stale-control-rejected");
  await stalePage.close();
});
