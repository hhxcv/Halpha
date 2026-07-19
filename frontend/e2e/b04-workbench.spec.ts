import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type TestInfo } from "@playwright/test";

const fixturePassword = process.env.HALPHA_BROWSER_FIXTURE_PASSWORD;

type Activation = {
  activation_id: string;
  instrument_ref: string;
  lifecycle: string;
};

type PlanSummary = {
  plan_version_id: string | null;
};

async function login(page: Page) {
  await page.goto("/login");
  await page.getByRole("textbox", { name: "本机所有者口令" }).fill(fixturePassword!);
  await page.getByRole("button", { name: "登录" }).click();
  await expect(page).toHaveURL(/\/overview$/);
}

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

test("B04 exposes unknown, protection gap, max loss, exit, takeover, closure and review without collapsing responsibility", async ({ page }, testInfo) => {
  test.skip(!fixturePassword, "HALPHA_BROWSER_FIXTURE_PASSWORD is required for the explicit B04 fixture.");
  await login(page);
  const items = await activations(page);
  const gap = items.find((item) => item.instrument_ref === "BTCUSDT-PERP" && item.lifecycle !== "COMPLETED");
  const exiting = items.find((item) => item.lifecycle === "EXITING");
  const takeover = items.find((item) => item.lifecycle === "USER_TAKEOVER");
  expect(gap).toBeTruthy();
  expect(exiting).toBeTruthy();
  expect(takeover).toBeTruthy();

  await page.goto(`/activations/${gap!.activation_id}`);
  await expect(page.getByRole("heading", { name: "激活运行与控制" })).toBeVisible();
  await expect(page.getByText("场所原生保护尚未证明为 WORKING")).toBeVisible();
  await expect(page.getByText("最大允许损失已经锁存")).toBeVisible();
  await expect(page.getByText("ENTRY · SUBMITTED_UNKNOWN")).toBeVisible();
  await expect(page.getByRole("alert", { name: "" }).filter({ hasText: "B04_BROWSER_UNKNOWN_RESULT" })).toBeVisible();
  await expect(page.getByText("EXIT_ONLY / 50")).toBeVisible();
  await assertAccessible(page, testInfo, "b04-gap-unknown-max-loss");
  await testInfo.attach("b04-gap-unknown-max-loss.png", {
    body: await page.screenshot({ fullPage: true }),
    contentType: "image/png",
  });

  await page.goto(`/activations/${exiting!.activation_id}`);
  await expect(page.getByText("EXITING", { exact: true })).toBeVisible();
  await expect(page.getByText("策略行为只作次要验证")).toBeVisible();

  await page.goto(`/activations/${takeover!.activation_id}`);
  await expect(page.getByText("用户接管已持久化")).toBeVisible();
  await expect(page.getByText("接管或闭合后不再提供机器写恢复或其他控制")).toBeVisible();
  await assertAccessible(page, testInfo, "b04-user-takeover");

  await page.goto("/reviews");
  await expect(page.getByRole("heading", { name: "激活复盘" })).toBeVisible();
  await expect(page.getByText("NO_ACTION · DRAFT")).toBeVisible();
  await page.getByRole("button", { name: "查看证据与评价" }).first().click();
  await expect(page.getByRole("heading", { name: "一次激活复盘" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "系统机制证据" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "策略行为证据" })).toBeVisible();
  await expect(page.getByText("模拟成交质量、收益或胜率不能无条件外推到 LIVE")).toBeVisible();
  await assertAccessible(page, testInfo, "b04-review");

  await page.goto("/operations");
  await expect(page.getByRole("heading", { name: "Recovery operations" })).toBeVisible();
  await page.locator("article.activation").filter({ hasText: "BTCUSDT-PERP" }).getByText("Execution actions and attributed venue facts").click();
  await expect(page.getByText("SUBMITTED_UNKNOWN")).toBeVisible();
  await expect(page.getByText("REACHED", { exact: true })).toBeVisible();
  await expect(page.getByText("GAP", { exact: true })).toBeVisible();
  await expect(page.getByText("EXIT CLOSURE PENDING").first()).toBeVisible();
  await expect(page.getByText("USER_TAKEOVER", { exact: true }).first()).toBeVisible();
  await assertAccessible(page, testInfo, "b04-operations");

  await assertNoDocumentOverflow(page, testInfo, "b04-operations");
});

test("B04 renders the synthetic LIVE authorization target state without opening or exercising the real-write path", async ({ page }, testInfo) => {
  test.skip(!fixturePassword, "HALPHA_BROWSER_FIXTURE_PASSWORD is required for the explicit B04 fixture.");
  await login(page);

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
    build_manifest_status: "VERIFIED",
    build_manifest_digest: "sha256:synthetic-live-target-build-manifest",
    build_manifest_violations: [],
    live_write_build_capability: "QUALIFIED",
    b05_real_capital_eligibility: "AUTHORIZED",
    account_capital_limit_version_ref: "synthetic-live-target-capital-limit",
    machine_authorization_version_ref: null,
    plan_allocation_ref: null,
    configured_runtime_real_write_gate: "CLOSED",
    runtime_real_write_gate: "CLOSED",
    live_write_gate_violations: [],
    user_authorization_ref: "synthetic-owner-authorization-ref",
    authorized_activation_id: null,
    construction_status: "SYNTHETIC_TARGET_STATE_NOT_CURRENT",
  };
  let projectedPreview: Record<string, unknown> | undefined;
  let activationSubmissions = 0;
  page.on("request", (request) => {
    if (request.method() === "POST" && /\/api\/v1\/activations$/.test(request.url())) {
      activationSubmissions += 1;
    }
  });
  await page.route("**/api/v1/settings/status", (route) => route.fulfill({ json: projectedStatus }));
  await page.route("**/api/v1/capital", (route) => route.fulfill({
    json: {
      environment_id: "synthetic-live-target-environment",
      authority_class: "LIVE_REAL_CAPITAL",
      account_ref: "synthetic-live-target-account",
      limits: [{ capital_limit_version_id: "synthetic-live-target-capital-limit" }],
      authorizations: [],
      allocations: [],
      stops: [],
    },
  }));
  await page.route("**/api/v1/plan-versions/*/activation-preview", async (route) => {
    const response = await route.fetch();
    const actualPreview = await response.json() as Record<string, unknown>;
    projectedPreview ??= {
      ...actualPreview,
      environment_kind: "LIVE",
      authority_class: "LIVE_REAL_CAPITAL",
      account_ref: "synthetic-live-target-account",
      live_write_build_capability: "QUALIFIED",
      b05_real_capital_eligibility: "AUTHORIZED",
      account_capital_limit_version_ref: "synthetic-live-target-capital-limit",
      configured_runtime_real_write_gate: "CLOSED",
      runtime_real_write_gate: "CLOSED",
      live_activation_eligible: true,
    };
    await route.fulfill({ response, json: projectedPreview });
  });

  await testInfo.attach("synthetic-live-target-state.json", {
    body: Buffer.from(JSON.stringify({
      fixture_kind: "SYNTHETIC_LIVE_TARGET_STATE",
      current_authorization: false,
      venue_writes: false,
      activation_submission_exercised: false,
      capital_limit_fixture: "SYNTHETIC_NON_SUBMITTED_TARGET_STATE",
      purpose: "UI_AND_GATE_MECHANISM_VALIDATION_ONLY",
    }, null, 2)),
    contentType: "application/json",
  });

  await page.goto(`/plans/${planVersionId}/activate`);
  await expect(page.getByText("REAL WRITE · CLOSED")).toBeVisible();
  await expect(page.getByText("REAL CAPITAL AUTHORIZATION")).toBeVisible();
  await expect(page.getByText("不会调用 Binance，也不会打开运行门", { exact: false })).toBeVisible();
  const realScope = page.getByLabel("我确认这是 REAL 资金授权，范围仅限本次计划、账户、合约和三轴额度");
  const evidenceLimits = page.getByLabel("我已阅读并接受当前证据局限；Demo 与回测表现不等于实盘表现");
  const onlineMonitoring = page.getByLabel("我将在运行门打开期间保持在线监控，并可立即停止、退出或接管");
  const submit = page.getByRole("button", { name: "确认建立 REAL 激活（不打开运行门）" });
  await expect(realScope).toBeVisible();
  await expect(evidenceLimits).toBeVisible();
  await expect(onlineMonitoring).toBeVisible();
  await expect(submit).toBeDisabled();
  await page.getByLabel("重新输入本机所有者口令").fill(fixturePassword!);
  await realScope.check();
  await evidenceLimits.check();
  await onlineMonitoring.check();
  await expect(submit).toBeEnabled();
  await assertAccessible(page, testInfo, "b04-synthetic-live-closed");
  await assertNoDocumentOverflow(page, testInfo, "b04-synthetic-live-closed");
  await page.evaluate(() => window.scrollTo(0, 0));
  await testInfo.attach("b04-synthetic-live-closed.png", {
    body: await page.screenshot({ fullPage: true }),
    contentType: "image/png",
  });

  projectedStatus = {
    ...projectedStatus,
    configured_runtime_real_write_gate: "OPEN",
    runtime_real_write_gate: "OPEN",
    authorized_activation_id: "synthetic-existing-live-activation",
  };
  projectedPreview = {
    ...projectedPreview,
    configured_runtime_real_write_gate: "OPEN",
    runtime_real_write_gate: "OPEN",
    live_activation_eligible: false,
  };
  await page.reload();
  await expect(page.getByText("REAL WRITE · OPEN")).toBeVisible();
  await expect(page.getByText("真实写工程能力、B05 真实资金资格或关闭态预备条件尚未满足；当前不能建立 REAL 激活。")).toBeVisible();
  await page.getByLabel("重新输入本机所有者口令").fill(fixturePassword!);
  await page.getByLabel("我确认这是 REAL 资金授权，范围仅限本次计划、账户、合约和三轴额度").check();
  await page.getByLabel("我已阅读并接受当前证据局限；Demo 与回测表现不等于实盘表现").check();
  await page.getByLabel("我将在运行门打开期间保持在线监控，并可立即停止、退出或接管").check();
  await expect(page.getByRole("button", { name: "确认建立 REAL 激活（不打开运行门）" })).toBeDisabled();
  await assertAccessible(page, testInfo, "b04-synthetic-live-open");
  await assertNoDocumentOverflow(page, testInfo, "b04-synthetic-live-open");
  await page.evaluate(() => window.scrollTo(0, 0));
  await testInfo.attach("b04-synthetic-live-open.png", {
    body: await page.screenshot({ fullPage: true }),
    contentType: "image/png",
  });
  expect(activationSubmissions).toBe(0);
});

test("B04 rejects a stale control submission instead of applying a newer activation version", async ({ page, context }, testInfo) => {
  test.skip(!fixturePassword, "HALPHA_BROWSER_FIXTURE_PASSWORD is required for the explicit B04 fixture.");
  test.skip(testInfo.project.name !== "chromium-desktop", "One state-changing stale-version drill is sufficient.");
  await login(page);
  const items = await activations(page);
  const staleControl = items.find((item) => item.instrument_ref === "XRPUSDT-PERP" && item.lifecycle === "RUNNING");
  expect(staleControl).toBeTruthy();

  const stalePage = await context.newPage();
  await Promise.all([
    page.goto(`/activations/${staleControl!.activation_id}`),
    stalePage.goto(`/activations/${staleControl!.activation_id}`),
  ]);
  await expect(page.getByText("RUNNING", { exact: true })).toBeVisible();
  await expect(stalePage.getByText("RUNNING", { exact: true })).toBeVisible();
  await stalePage.route(
    new RegExp(`/api/v1/activations/${staleControl!.activation_id}$`),
    (route) => route.abort(),
  );

  await page.getByRole("button", { name: "退出策略" }).click();
  await page.getByLabel("本机所有者口令").fill(fixturePassword!);
  await page.getByRole("button", { name: "确认提交 EXIT_STRATEGY" }).click();
  await expect(page.getByText("命令已持久化并返回 PROCESSING Receipt")).toBeVisible();

  await stalePage.getByRole("button", { name: "用户接管" }).click();
  await stalePage.getByLabel("本机所有者口令").fill(fixturePassword!);
  await stalePage.getByRole("button", { name: "确认提交 USER_TAKEOVER" }).click();
  await expect(stalePage.getByText("命令被拒绝：PLAN_VERSION_CONFLICT")).toBeVisible();
  await assertAccessible(stalePage, testInfo, "b04-stale-control-rejected");
  await stalePage.close();
});
