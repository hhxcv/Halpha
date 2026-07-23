import { randomUUID } from "node:crypto";

import { expect, test, type Locator, type Page, type TestInfo } from "@playwright/test";

type JsonRecord = Record<string, unknown>;

const allowDemoMutation = process.env.HALPHA_ALLOW_DEMO_MUTATION === "1";
const demoMutationOptInMessage = "Set HALPHA_ALLOW_DEMO_MUTATION=1 to run Demo-mutating qualification.";

type TestDraftRef = {
  planId: string;
  draftVersion: number;
  planName: string;
};

function recordOf(value: unknown): JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as JsonRecord
    : {};
}

function activationLifecycle(snapshot: JsonRecord): string {
  return String(recordOf(snapshot.activation).lifecycle ?? "");
}

function recordsOf(value: unknown): JsonRecord[] {
  return Array.isArray(value) ? value.map(recordOf) : [];
}

function stringOf(record: JsonRecord, key: string): string {
  return String(record[key] ?? "");
}

function actionExecutionContext(action: JsonRecord): JsonRecord {
  return recordOf(recordOf(action.action_terms).execution_context);
}

function actionScheduleIndex(action: JsonRecord): number {
  return Number(recordOf(actionExecutionContext(action).order_schedule).submission_index);
}

function linkedActionRef(action: JsonRecord, key: string): string {
  return stringOf(actionExecutionContext(action), key);
}

function workingFactFor(facts: JsonRecord[], action: JsonRecord): JsonRecord | undefined {
  const actionId = stringOf(action, "execution_action_id");
  return facts.find((fact) => (
    stringOf(fact, "action_ref") === actionId
    && stringOf(fact, "kind") === "ORDER_STATE"
    && stringOf(recordOf(fact.payload), "status") === "WORKING"
  ));
}

function timestampOf(record: JsonRecord, key: string): number {
  return Date.parse(stringOf(record, key));
}

function serialProtectionCausality(snapshot: JsonRecord, expectedLegs: number): boolean {
  const actions = recordsOf(snapshot.execution_actions);
  const facts = recordsOf(snapshot.venue_facts);
  const entries = actions
    .filter((action) => stringOf(action, "action_kind") === "ENTRY")
    .sort((left, right) => actionScheduleIndex(left) - actionScheduleIndex(right));
  const protections = actions.filter((action) => stringOf(action, "action_kind") === "PROTECTION");
  if (entries.length !== expectedLegs || protections.length < expectedLegs) return false;

  for (let index = 0; index < entries.length; index += 1) {
    const entry = entries[index];
    const entryId = stringOf(entry, "execution_action_id");
    if (actionScheduleIndex(entry) !== index || stringOf(entry, "state") !== "CLOSED") return false;

    const entryFills = facts.filter((fact) => (
      stringOf(fact, "kind") === "FILL" && stringOf(fact, "action_ref") === entryId
    ));
    const terminalFill = entryFills.find((fact) => (
      Number(recordOf(fact.payload).leaves_quantity) === 0
    ));
    if (entryFills.length === 0 || !terminalFill) return false;

    const protectionWorkingTimes: number[] = [];
    for (const fill of entryFills) {
      const protection = protections.find((candidate) => (
        linkedActionRef(candidate, "entry_action_ref") === entryId
        && linkedActionRef(candidate, "fill_fact_ref") === stringOf(fill, "venue_fact_id")
      ));
      const workingFact = protection ? workingFactFor(facts, protection) : undefined;
      const workingAt = workingFact ? timestampOf(workingFact, "received_at") : Number.NaN;
      if (!protection || !workingFact || !Number.isFinite(workingAt)) return false;
      protectionWorkingTimes.push(workingAt);
    }

    if (index + 1 < entries.length) {
      const nextCallStartedAt = timestampOf(entries[index + 1], "call_started_at");
      const terminalFillAt = timestampOf(terminalFill, "received_at");
      const causalBoundary = Math.max(terminalFillAt, ...protectionWorkingTimes);
      if (!Number.isFinite(nextCallStartedAt) || nextCallStartedAt <= causalBoundary) return false;
    }
  }
  return true;
}

function canonicalTenth(tenths: number): string {
  return (tenths / 10).toFixed(1).replace(/\.0$/, "");
}

async function choose(page: Page, label: string, option: string) {
  await page.getByRole("combobox", { name: label }).click();
  await page.getByRole("option", { name: option, exact: true }).click();
}

async function revealDisclosure(trigger: Locator, target: Locator) {
  if (await target.isVisible().catch(() => false)) return;
  await trigger.click();
  await expect(target).toBeVisible();
}

async function revealPlanOptions(page: Page) {
  await revealDisclosure(
    page.getByRole("heading", { name: "计划选项", exact: true }),
    page.getByLabel("计划名称"),
  );
}

async function revealAdvancedPriceSpacing(page: Page) {
  await revealDisclosure(
    page.getByText(/^高级价格间距 ·/),
    page.getByRole("combobox", { name: "价格切分间距" }),
  );
}

async function revealAdvancedVenueSettings(page: Page) {
  await revealDisclosure(
    page.getByText(/^高级交易所设置 ·/),
    page.getByRole("combobox", { name: "有效方式" }),
  );
}

async function revealDynamicCancellation(page: Page) {
  await revealDisclosure(
    page.getByRole("heading", { name: "动态撤单", exact: true }),
    page.getByRole("checkbox", { name: "到期撤销未成交余量" }),
  );
}

async function revealProfitAndTimeExit(page: Page) {
  await revealDisclosure(
    page.getByText(/^止盈与时间退出 ·/),
    page.getByRole("checkbox", { name: "启用单级全量止盈" }),
  );
}

async function revealNormalizedDetails(page: Page) {
  await revealDisclosure(
    page.getByText(/^完整标准化明细 ·/),
    page.getByRole("table", { name: "标准化订单档位表" }),
  );
}

async function selectToggle(page: Page, name: "做多" | "做空" | "市价" | "单笔限价" | "区间阶梯") {
  const toggle = page.getByRole("button", { name, exact: true });
  await expect(toggle).toBeVisible();
  if (await toggle.getAttribute("aria-pressed") !== "true") await toggle.click();
  await expect(toggle).toHaveAttribute("aria-pressed", "true");
}

async function startDirectActivation(page: Page) {
  const button = page.getByRole("button", {
    name: "启动直接执行订单计划",
    exact: true,
  });
  for (let attempt = 0; attempt < 3; attempt += 1) {
    await expect(button).toBeEnabled({ timeout: 30_000 });
    await button.click();
    try {
      await expect(page).toHaveURL(/\/activations\/[^/?#]+$/, { timeout: 15_000 });
      return;
    } catch (error) {
      if (!/\/plans\/[^/?#]+\/activate$/.test(new URL(page.url()).pathname)) throw error;
      const staleWarning = page.getByText(
        "启动复核已过期，页面正在刷新服务端订单快照与行情；刷新完成后请重新确认启动。",
        { exact: true },
      );
      if (!await staleWarning.isVisible().catch(() => false)) throw error;
    }
  }
  throw new Error("ACTIVATION_PREVIEW_REMAINED_STALE_AFTER_RETRIES");
}

async function readActivation(page: Page, activationId: string): Promise<JsonRecord> {
  const response = await page.request.get(`/api/v1/activations/${encodeURIComponent(activationId)}`);
  if (!response.ok()) {
    throw new Error(`ACTIVATION_READ_FAILED:${response.status()}`);
  }
  return await response.json() as JsonRecord;
}

async function readPlans(page: Page): Promise<JsonRecord[]> {
  const response = await page.request.get("/api/v1/plans");
  if (!response.ok()) throw new Error(`PLANS_READ_FAILED:${response.status()}`);
  return recordsOf(await response.json());
}

async function waitForActivationEvidence(
  page: Page,
  activationId: string,
  timeoutMs: number,
  predicate: (snapshot: JsonRecord) => boolean,
): Promise<JsonRecord | null> {
  const deadline = Date.now() + timeoutMs;
  let latest: JsonRecord | null = null;
  while (Date.now() < deadline) {
    latest = await readActivation(page, activationId);
    if (predicate(latest)) return latest;
    await page.waitForTimeout(500);
  }
  return latest && predicate(latest) ? latest : null;
}

async function findCreatedDirectPlan(
  page: Page,
  planName: string,
  baselinePlanIds: ReadonlySet<string>,
): Promise<JsonRecord | null> {
  const candidates = (await readPlans(page)).filter((plan) => (
    !baselinePlanIds.has(stringOf(plan, "plan_id"))
    && stringOf(plan, "plan_name") === planName
    && stringOf(plan, "decision_basis_kind") === "DIRECT_EXECUTION"
  ));
  if (candidates.length > 1) {
    throw new Error(`TEST_PLAN_IDENTITY_AMBIGUOUS:${candidates.length}`);
  }
  return candidates[0] ?? null;
}

async function cleanupCreatedDraft(
  page: Page,
  testInfo: TestInfo,
  planName: string,
  baselinePlanIds: ReadonlySet<string>,
  knownDraft: TestDraftRef | null,
) {
  const candidate = knownDraft
    ? (await readPlans(page)).find((plan) => stringOf(plan, "plan_id") === knownDraft.planId) ?? null
    : await findCreatedDirectPlan(page, planName, baselinePlanIds);
  if (!candidate || candidate.plan_version_id !== null) return;

  const planId = stringOf(candidate, "plan_id");
  if (!planId || baselinePlanIds.has(planId)) {
    throw new Error("TEST_DRAFT_DELETE_SCOPE_INVALID");
  }
  const detailResponse = await page.request.get(`/api/v1/plans/${encodeURIComponent(planId)}`);
  if (!detailResponse.ok()) {
    throw new Error(`TEST_DRAFT_READ_FAILED:${detailResponse.status()}`);
  }
  const detail = recordOf(await detailResponse.json());
  const content = recordOf(detail.content);
  const decisionBasis = recordOf(content.decision_basis);
  const draftVersion = Number(detail.draft_version);
  if (
    stringOf(detail, "plan_id") !== planId
    || stringOf(content, "plan_name") !== planName
    || stringOf(decisionBasis, "kind") !== "DIRECT_EXECUTION"
    || !Number.isInteger(draftVersion)
    || (knownDraft !== null && draftVersion !== knownDraft.draftVersion)
  ) {
    throw new Error("TEST_DRAFT_DELETE_IDENTITY_MISMATCH");
  }

  const csrfCookie = (await page.context().cookies()).find((cookie) => cookie.name === "halpha_csrf");
  if (!csrfCookie) throw new Error("CSRF_COOKIE_MISSING_DURING_DRAFT_CLEANUP");
  const currentUrl = new URL(page.url());
  const deletion = await page.request.delete(`/api/v1/plans/${encodeURIComponent(planId)}`, {
    headers: {
      "If-Match": String(draftVersion),
      "X-CSRFToken": decodeURIComponent(csrfCookie.value),
      Origin: currentUrl.origin,
      Referer: page.url(),
    },
  });
  if (!deletion.ok()) {
    throw new Error(`TEST_DRAFT_DELETE_FAILED:${deletion.status()}`);
  }
  const remaining = (await readPlans(page)).filter((plan) => stringOf(plan, "plan_id") === planId);
  expect(remaining, "只能删除本场景刚创建且尚未确认的精确草稿").toEqual([]);
  await testInfo.attach("maker-expiry-draft-cleanup.json", {
    body: Buffer.from(JSON.stringify(await deletion.json(), null, 2)),
    contentType: "application/json",
  });
}

async function waitForCompleted(
  page: Page,
  activationId: string,
  timeoutMs: number,
): Promise<JsonRecord | null> {
  const deadline = Date.now() + timeoutMs;
  let latest: JsonRecord | null = null;
  while (Date.now() < deadline) {
    latest = await readActivation(page, activationId);
    if (activationLifecycle(latest) === "COMPLETED") return latest;
    await page.waitForTimeout(1_000);
  }
  return null;
}

async function submitExitThroughApi(page: Page, activationId: string) {
  const csrfCookie = (await page.context().cookies()).find((cookie) => cookie.name === "halpha_csrf");
  if (!csrfCookie) throw new Error("CSRF_COOKIE_MISSING_DURING_CLEANUP");
  const currentUrl = new URL(page.url());
  const commonHeaders = {
    "X-CSRFToken": decodeURIComponent(csrfCookie.value),
    Origin: currentUrl.origin,
    Referer: page.url(),
  };

  for (let attempt = 0; attempt < 3; attempt += 1) {
    const snapshot = await readActivation(page, activationId);
    if (activationLifecycle(snapshot) === "COMPLETED") return;
    const stateVersion = Number(recordOf(snapshot.activation).state_version);
    if (!Number.isInteger(stateVersion)) throw new Error("ACTIVATION_STATE_VERSION_MISSING");

    const preview = await page.request.post(
      `/api/v1/activations/${encodeURIComponent(activationId)}/control-preview?intent=EXIT_STRATEGY`,
      { headers: commonHeaders },
    );
    if (!preview.ok()) {
      throw new Error(`EXIT_PREVIEW_FAILED:${preview.status()}`);
    }
    const exit = await page.request.post(
      `/api/v1/activations/${encodeURIComponent(activationId)}/exit`,
      {
        headers: { ...commonHeaders, "Idempotency-Key": randomUUID() },
        data: { expected_version: stateVersion, takeover_scope: {} },
      },
    );
    if (exit.ok()) return;
    if (exit.status() !== 409) throw new Error(`EXIT_SUBMIT_FAILED:${exit.status()}`);
  }
  throw new Error("EXIT_SUBMIT_VERSION_CONFLICT_REPEATED");
}

async function cleanupActivation(page: Page, testInfo: TestInfo, activationId: string) {
  const initial = await readActivation(page, activationId);
  if (activationLifecycle(initial) === "COMPLETED") return;

  try {
    await page.goto(`/activations/${encodeURIComponent(activationId)}`);
    const exitButton = page.getByRole("button", { name: "退出订单计划", exact: true });
    await expect(exitButton).toBeVisible({ timeout: 15_000 });
    if (await exitButton.isEnabled()) {
      await exitButton.click();
      const confirmButton = page.getByRole("button", { name: "确认退出订单计划", exact: true });
      await expect(confirmButton).toBeVisible({ timeout: 15_000 });
      await confirmButton.click();
    }
  } catch (error) {
    await testInfo.attach("direct-order-cleanup-ui-error.txt", {
      body: Buffer.from(error instanceof Error ? error.stack ?? error.message : String(error)),
      contentType: "text/plain",
    });
  }

  if (!await waitForCompleted(page, activationId, 30_000)) {
    await submitExitThroughApi(page, activationId);
  }
  const completed = await waitForCompleted(page, activationId, 60_000);
  await testInfo.attach("direct-order-cleanup-final.json", {
    body: Buffer.from(JSON.stringify(completed ?? await readActivation(page, activationId), null, 2)),
    contentType: "application/json",
  });
  expect(completed, "Demo 激活必须在测试结束前完成退出闭合").not.toBeNull();
}

async function assertNoPageOverflow(page: Page, testInfo: TestInfo, name: string) {
  const layout = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
    offenders: [...document.querySelectorAll<HTMLElement>("body *")]
      .filter((element) => !element.closest(".table-scroll"))
      .filter((element) => !element.classList.contains("MuiSwitch-input"))
      .filter((element) => {
        const drawerPaper = element.closest<HTMLElement>(".MuiDrawer-paper");
        if (!drawerPaper) return true;
        const bounds = drawerPaper.getBoundingClientRect();
        return bounds.right > 0 && bounds.left < document.documentElement.clientWidth;
      })
      .map((element) => {
        const bounds = element.getBoundingClientRect();
        return {
          tag: element.tagName,
          className: String(element.className),
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

test("direct order schedules preview a composed ladder and complete a protected Demo market order", async ({ page }, testInfo) => {
  test.skip(!allowDemoMutation, demoMutationOptInMessage);
  test.setTimeout(240_000);
  const planName = `E2E AI 直接订单 ${Date.now()} ${testInfo.project.name}`;
  let activationId: string | null = null;

  try {
    await page.goto("/plans/new");
    await expect(page.getByText("DEMO", { exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "选择执行依据" })).toBeVisible();
    await page.getByRole("button", { name: "配置订单计划", exact: true }).click();
    await expect(page.getByRole("heading", { name: "直接执行", exact: true })).toBeVisible();

    await revealPlanOptions(page);
    await page.getByLabel("计划名称").fill(planName);
    await choose(page, "创建方式", "AI 创建");
    await expect(page.getByRole("combobox", { name: "创建方式" })).toContainText("AI 创建");

    const marketResponse = await page.request.get("/api/v1/market-context", {
      params: { instrument_ref: "BTCUSDT-PERP", channel_lookback_15m: 20 },
    });
    expect(marketResponse.ok(), "LADDER 价格必须来自当前只读公开行情").toBeTruthy();
    const market = await marketResponse.json() as JsonRecord;
    const referencePrice = Number(market.reference_price);
    expect(Number.isFinite(referencePrice) && referencePrice > 0).toBeTruthy();
    const lowerPrice = (Math.floor(referencePrice * 0.97 * 10) / 10).toFixed(1);
    const upperPrice = (Math.floor(referencePrice * 0.99 * 10) / 10).toFixed(1);

    await page.getByLabel("资金上限（USDT）").fill("5000");
    await selectToggle(page, "区间阶梯");
    await page.getByLabel("下限（USDT）", { exact: true }).fill(lowerPrice);
    await page.getByLabel("上限（USDT）", { exact: true }).fill(upperPrice);
    await page.getByLabel("价格档位数").fill("5");
    await revealAdvancedPriceSpacing(page);
    await choose(page, "价格切分间距", "线性比例");
    await page.getByLabel("首个间距权重").fill("5");
    await page.getByLabel("每档权重增量").fill("-1");
    await choose(page, "下单额模式", "指数增长");
    await page.getByLabel("基础金额（USDT）").fill("150");
    await page.getByLabel("金额指数比例").fill("2");
    await choose(page, "金额增长方向", "从高价到低价");
    await revealAdvancedVenueSettings(page);
    await choose(page, "串行提交顺序", "高价 → 低价");
    await page.getByRole("switch", { name: "Maker only" }).check();
    await revealDynamicCancellation(page);
    await page.getByRole("checkbox", { name: "到期撤销未成交余量" }).check();
    await page.getByLabel("首档提交后等待（秒）").fill("120");
    await page.getByRole("checkbox", { name: "短时不利异动撤单" }).check();

    await expect(page.getByText(/^预览可保存 · 5 档/)).toBeVisible({ timeout: 30_000 });
    await revealNormalizedDetails(page);
    const ladderTable = page.getByRole("table", { name: "标准化订单档位表" });
    const ladderRows = ladderTable.getByRole("row");
    await expect(ladderRows).toHaveCount(6);
    const lowerTicks = Math.round(Number(lowerPrice) * 10);
    const upperTicks = Math.round(Number(upperPrice) * 10);
    const cumulativeGapWeights = [0, 5, 9, 12, 14];
    const expectedPrices = cumulativeGapWeights.map((weight) => canonicalTenth(
      Math.floor(lowerTicks + ((upperTicks - lowerTicks) * weight) / 14),
    ));
    const expectedNotionals = ["2400", "1200", "600", "300", "150"];
    for (let index = 0; index < expectedPrices.length; index += 1) {
      const cells = ladderRows.nth(index + 1).getByRole("cell");
      await expect(cells.nth(2), `第 ${index + 1} 档标准化价格必须保持 5:4:3:2 间距映射`)
        .toHaveText(expectedPrices[index]);
      await expect(cells.nth(4), `第 ${index + 1} 档金额必须保持反向指数映射`)
        .toHaveText(`${expectedNotionals[index]} USDT`);
    }
    await expect(page.getByText("4650 USDT", { exact: true })).toBeVisible();
    await testInfo.attach("direct-order-ladder-preview.png", {
      body: await page.screenshot({ fullPage: true }),
      contentType: "image/png",
    });
    await assertNoPageOverflow(page, testInfo, "direct-order-ladder-preview");

    if (testInfo.project.name === "chromium-narrow") return;

    await page.getByLabel("资金上限（USDT）").fill("500");
    await selectToggle(page, "市价");
    await page.getByLabel("下单金额（USDT）").fill("500");
    await page.getByLabel("初始止损距离（bps）").fill("1000");
    await revealProfitAndTimeExit(page);
    await page.getByRole("checkbox", { name: "启用单级全量止盈" }).check();
    await expect(page.getByLabel("止盈（R）")).toHaveValue("1.5");
    await expect(page.getByLabel("成交量比例")).toHaveValue("100%");
    await page.getByRole("checkbox", { name: "启用整次持仓时间退出" }).check();
    await page.getByLabel("首笔成交后整组退出（秒）").fill("30");

    await expect(page.getByText(/^预览可保存 · 1 档/)).toBeVisible({ timeout: 30_000 });
    await expect(page.getByRole("switch", { name: "Maker only" })).not.toBeChecked();
    await revealDynamicCancellation(page);
    await expect(page.getByRole("checkbox", { name: "到期撤销未成交余量" })).toBeDisabled();
    const saveButton = page.getByRole("button", { name: "保存并检查", exact: true });
    await expect(saveButton).toBeEnabled({ timeout: 30_000 });
    await saveButton.click();

    await expect(page).toHaveURL(/\/plans$/);
    const planCard = page.getByRole("article", { name: `计划 ${planName}` });
    await expect(planCard.getByRole("heading", { name: planName })).toBeVisible();
    await expect(planCard.getByText(/直接执行订单计划 · BTCUSDT-PERP/)).toBeVisible();
    await expect(planCard.getByText(/AI 创建 · 创建于 .* UTC\+8/)).toBeVisible();
    await planCard.getByText("计划配置", { exact: true }).click();
    await expect(planCard.getByText("单笔 · 市价", { exact: false })).toBeVisible();
    await planCard.getByRole("button", { name: "确认计划", exact: true }).click();
    const startPlanButton = planCard.getByRole("button", { name: "启动订单计划", exact: true });
    await expect(startPlanButton).toBeVisible({ timeout: 30_000 });
    await startPlanButton.click();

    await expect(page.getByRole("heading", { name: planName })).toBeVisible();
    await expect(page.getByText("DIRECT_EXECUTION@1", { exact: true }).first()).toBeVisible();
    await startDirectActivation(page);
    activationId = new URL(page.url()).pathname.split("/").filter(Boolean).at(-1) ?? null;
    expect(activationId).toBeTruthy();
    if (!activationId) throw new Error("ACTIVATION_ID_MISSING_AFTER_START");

    await expect(page.getByText("直接执行订单计划", { exact: true }).first()).toBeVisible();
    await expect(page.getByText(/^入场 · /).first()).toBeVisible({ timeout: 60_000 });
    await expect(page.getByText(/^保护 · /).first()).toBeVisible({ timeout: 60_000 });
    await expect(page.getByText(/^止盈 · /).first()).toBeVisible({ timeout: 60_000 });
    const completed = await waitForCompleted(page, activationId, 120_000);
    expect(completed, "短时退出必须形成已闭合的 Demo 激活").not.toBeNull();
    const completedActions = Array.isArray(completed?.execution_actions)
      ? completed.execution_actions.map(recordOf)
      : [];
    const completedFacts = recordsOf(completed?.venue_facts);
    const entryActions = completedActions.filter((action) => stringOf(action, "action_kind") === "ENTRY");
    const protectionActions = completedActions.filter((action) => stringOf(action, "action_kind") === "PROTECTION");
    const takeProfitActions = completedActions.filter((action) => stringOf(action, "action_kind") === "TAKE_PROFIT");
    const timeExit = completedActions.find((action) => (
      stringOf(action, "action_kind") === "EXIT"
      && stringOf(action, "state") === "CLOSED"
      && stringOf(recordOf(action.action_terms), "causation_ref").endsWith(":EXIT:DIRECT_TIME_EXIT")
    ));
    expect(entryActions).toHaveLength(1);
    expect(timeExit, "场景必须由预设 DIRECT_TIME_EXIT 闭合，不能由保护缺口紧急退出替代").toBeTruthy();
    const timeExitStartedAt = timestampOf(timeExit ?? {}, "call_started_at");
    expect(Number.isFinite(timeExitStartedAt)).toBeTruthy();
    const entryId = stringOf(entryActions[0] ?? {}, "execution_action_id");
    const entryFills = completedFacts.filter((fact) => (
      stringOf(fact, "kind") === "FILL" && stringOf(fact, "action_ref") === entryId
    ));
    expect(entryFills.length, "市价入场必须保留至少一个真实成交事实").toBeGreaterThan(0);
    for (const fill of entryFills) {
      const fillId = stringOf(fill, "venue_fact_id");
      const protection = protectionActions.find((action) => (
        linkedActionRef(action, "entry_action_ref") === entryId
        && linkedActionRef(action, "fill_fact_ref") === fillId
      ));
      const takeProfit = takeProfitActions.find((action) => (
        linkedActionRef(action, "entry_action_ref") === entryId
        && linkedActionRef(action, "fill_fact_ref") === fillId
        && linkedActionRef(action, "protection_action_ref")
          === stringOf(protection ?? {}, "execution_action_id")
      ));
      const protectionWorking = protection ? workingFactFor(completedFacts, protection) : undefined;
      const takeProfitWorking = takeProfit ? workingFactFor(completedFacts, takeProfit) : undefined;
      expect(protection, `成交 ${fillId} 必须精确关联独立止损动作`).toBeTruthy();
      expect(takeProfit, `成交 ${fillId} 必须精确关联止损后的止盈动作`).toBeTruthy();
      expect(protectionWorking, `成交 ${fillId} 的止损必须收到交易所 WORKING 事实`).toBeTruthy();
      expect(takeProfitWorking, `成交 ${fillId} 的止盈必须收到交易所 WORKING 事实`).toBeTruthy();
      expect(timestampOf(protectionWorking ?? {}, "received_at")).toBeLessThan(timeExitStartedAt);
      expect(timestampOf(takeProfitWorking ?? {}, "received_at")).toBeLessThan(timeExitStartedAt);
    }

    await page.reload();
    const actionsSection = page.getByRole("heading", { name: "动作、部分成交与保护责任" }).locator("..");
    for (let expansion = 0; expansion < 3; expansion += 1) {
      if (await actionsSection.getByText(/^退出 · /).count()) break;
      const showMore = actionsSection.getByRole("button", { name: /^显示更多（剩余 \d+ 条）$/ });
      if (!await showMore.count()) break;
      await showMore.last().click();
    }
    await expect(actionsSection.getByText(/^退出 · 已核对闭合$/).first()).toBeVisible();
    await expect(page.getByText("已闭合", { exact: true }).first()).toBeVisible({ timeout: 10_000 });
    await testInfo.attach("direct-order-activation.json", {
      body: Buffer.from(JSON.stringify(completed, null, 2)),
      contentType: "application/json",
    });
    await testInfo.attach("direct-order-activation-completed.png", {
      body: await page.screenshot({ fullPage: true }),
      contentType: "image/png",
    });
  } finally {
    if (activationId) await cleanupActivation(page, testInfo, activationId);
  }
});

test("maker-only serial ladder expires without a fill and closes its Demo responsibility", async ({ page }, testInfo) => {
  test.skip(!allowDemoMutation, demoMutationOptInMessage);
  test.skip(testInfo.project.name === "chromium-narrow", "Demo 变更场景只在 desktop 串行执行");
  test.setTimeout(240_000);
  const planName = `E2E AI Maker 到期 ${Date.now()} ${randomUUID().slice(0, 8)}`;
  const baselinePlanIds = new Set<string>();
  let baselineCaptured = false;
  let draftRef: TestDraftRef | null = null;
  let activationId: string | null = null;

  try {
    await page.goto("/plans/new");
    await expect(page.getByText("DEMO", { exact: true })).toBeVisible();
    for (const plan of await readPlans(page)) baselinePlanIds.add(stringOf(plan, "plan_id"));
    baselineCaptured = true;

    await page.getByRole("button", { name: "配置订单计划", exact: true }).click();
    await expect(page.getByRole("heading", { name: "直接执行", exact: true })).toBeVisible();
    await revealPlanOptions(page);
    await page.getByLabel("计划名称").fill(planName);
    await choose(page, "创建方式", "AI 创建");
    await selectToggle(page, "做多");

    const marketResponse = await page.request.get("/api/v1/market-context", {
      params: { instrument_ref: "BTCUSDT-PERP", channel_lookback_15m: 20 },
    });
    expect(marketResponse.ok(), "挂单区间必须来自本次只读公开行情").toBeTruthy();
    const market = recordOf(await marketResponse.json());
    const referencePrice = Number(market.reference_price);
    expect(Number.isFinite(referencePrice) && referencePrice > 0).toBeTruthy();
    const lowerPrice = (Math.floor(referencePrice * 0.97 * 10) / 10).toFixed(1);
    const upperPrice = (Math.floor(referencePrice * 0.98 * 10) / 10).toFixed(1);
    expect(Number(upperPrice)).toBeLessThan(referencePrice);

    await page.getByLabel("资金上限（USDT）").fill("500");
    await selectToggle(page, "区间阶梯");
    await page.getByLabel("下限（USDT）", { exact: true }).fill(lowerPrice);
    await page.getByLabel("上限（USDT）", { exact: true }).fill(upperPrice);
    await page.getByLabel("价格档位数").fill("3");
    await revealAdvancedPriceSpacing(page);
    await choose(page, "价格切分间距", "等距");
    await choose(page, "下单额模式", "固定金额");
    await page.getByLabel("每档金额（USDT）").fill("150");
    await revealAdvancedVenueSettings(page);
    await choose(page, "有效方式", "GTC · 持续有效");
    await choose(page, "串行提交顺序", "高价 → 低价");
    await page.getByRole("switch", { name: "Maker only" }).check();
    await revealDynamicCancellation(page);
    await page.getByRole("checkbox", { name: "到期撤销未成交余量" }).check();
    await page.getByLabel("首档提交后等待（秒）").fill("15");

    await expect(page.getByText(/^预览可保存 · 3 档/)).toBeVisible({ timeout: 30_000 });
    await revealNormalizedDetails(page);
    const ladderTable = page.getByRole("table", { name: "标准化订单档位表" });
    await expect(ladderTable.getByRole("row")).toHaveCount(4);
    await expect(ladderTable.getByText("150 USDT", { exact: true })).toHaveCount(3);
    await expect(page.getByRole("switch", { name: "Maker only" })).toBeChecked();
    await expect(page.getByLabel("首档提交后等待（秒）")).toHaveValue("15");

    const saveButton = page.getByRole("button", { name: "保存并检查", exact: true });
    await expect(saveButton).toBeEnabled({ timeout: 30_000 });
    await saveButton.click();
    await expect(page).toHaveURL(/\/plans$/);

    const createdPlan = await findCreatedDirectPlan(page, planName, baselinePlanIds);
    expect(createdPlan, "保存后必须能按新 ID、精确名称和直接执行依据唯一定位草稿").not.toBeNull();
    if (!createdPlan) throw new Error("TEST_DRAFT_NOT_FOUND_AFTER_SAVE");
    const createdDraftVersion = Number(createdPlan.draft_version);
    expect(Number.isInteger(createdDraftVersion)).toBeTruthy();
    draftRef = {
      planId: stringOf(createdPlan, "plan_id"),
      draftVersion: createdDraftVersion,
      planName,
    };

    const planCard = page.getByRole("article", { name: `计划 ${planName}` });
    await expect(planCard.getByText(/直接执行订单计划 · BTCUSDT-PERP/)).toBeVisible();
    await expect(planCard.getByText(/AI 创建 · 创建于 .* UTC\+8/)).toBeVisible();
    await planCard.getByText("计划配置", { exact: true }).click();
    await expect(planCard.getByText("3 档阶梯 · 限价 · Maker only", { exact: true })).toBeVisible();
    await planCard.getByRole("button", { name: "确认计划", exact: true }).click();
    const startPlanButton = planCard.getByRole("button", { name: "启动订单计划", exact: true });
    await expect(startPlanButton).toBeVisible({ timeout: 30_000 });
    await startPlanButton.click();

    await expect(page.getByText("DIRECT_EXECUTION@1", { exact: true }).first()).toBeVisible();
    await expect(page.getByRole("heading", { name: "实际提交复核" })).toBeVisible();
    await expect(page.getByText("串行保护 · 高价 → 低价", { exact: true })).toBeVisible();
    await expect(page.getByText(/首档真实提交后 15 秒终止并撤销剩余入场/)).toBeVisible();
    const activationLadder = page.getByRole("table", { name: "按真实提交顺序排列的订单档位" });
    await expect(activationLadder.getByRole("row")).toHaveCount(4);
    await expect(activationLadder.getByRole("row").nth(1)).toContainText(upperPrice);
    await expect(activationLadder.getByText("首档", { exact: true })).toBeVisible();
    await startDirectActivation(page);
    activationId = new URL(page.url()).pathname.split("/").filter(Boolean).at(-1) ?? null;
    if (!activationId) throw new Error("ACTIVATION_ID_MISSING_AFTER_MAKER_START");

    const working = await waitForActivationEvidence(page, activationId, 12_000, (snapshot) => {
      const actions = recordsOf(snapshot.execution_actions);
      const facts = recordsOf(snapshot.venue_facts);
      const openEntry = actions.find((action) => (
        stringOf(action, "action_kind") === "ENTRY" && stringOf(action, "state") === "OPEN"
      ));
      return Boolean(openEntry && facts.some((fact) => (
        stringOf(fact, "action_ref") === stringOf(openEntry, "execution_action_id")
        && stringOf(fact, "kind") === "ORDER_STATE"
        && stringOf(recordOf(fact.payload), "status") === "WORKING"
      )));
    });
    expect(working, "第一档应在 15 秒到期前形成 OPEN 动作与 WORKING 交易所事实").not.toBeNull();
    if (!working) throw new Error("MAKER_WORKING_EVIDENCE_NOT_OBSERVED");
    const workingActions = recordsOf(working.execution_actions);
    const openEntry = workingActions.find((action) => (
      stringOf(action, "action_kind") === "ENTRY" && stringOf(action, "state") === "OPEN"
    ));
    expect(openEntry).toBeTruthy();
    const firstEntryId = stringOf(openEntry ?? {}, "execution_action_id");
    const firstEntryClientOrderId = stringOf(openEntry ?? {}, "client_order_id");
    const workingEntries = workingActions
      .filter((action) => stringOf(action, "action_kind") === "ENTRY")
      .sort((left, right) => actionScheduleIndex(left) - actionScheduleIndex(right));
    expect(workingEntries).toHaveLength(3);
    expect(stringOf(workingEntries[0] ?? {}, "execution_action_id"), "HIGH_TO_LOW 的运行时首档必须就是当前 OPEN 档")
      .toBe(firstEntryId);
    expect(actionScheduleIndex(openEntry ?? {})).toBe(0);
    expect(stringOf(recordOf(openEntry?.action_terms), "price"), "运行时首档必须精确提交区间最高价")
      .toBe(upperPrice);
    expect(Number(recordOf(actionExecutionContext(openEntry ?? {}).order_schedule).leg_index))
      .toBe(2);
    expect(recordsOf(working.venue_facts).filter((fact) => stringOf(fact, "kind") === "FILL")).toEqual([]);
    const actionsSection = page.getByRole("heading", { name: "动作、部分成交与保护责任" }).locator("..");
    await expect(actionsSection.getByText("入场 · 责任开放", { exact: true })).toBeVisible({ timeout: 10_000 });
    await expect(actionsSection.getByText("交易所事实 · 曾收到订单状态 · WORKING", { exact: true })).toBeVisible();
    await testInfo.attach("maker-expiry-working.json", {
      body: Buffer.from(JSON.stringify(working, null, 2)),
      contentType: "application/json",
    });

    const expired = await waitForActivationEvidence(page, activationId, 75_000, (snapshot) => {
      const actions = recordsOf(snapshot.execution_actions);
      const entries = actions.filter((action) => stringOf(action, "action_kind") === "ENTRY");
      return entries.filter((action) => stringOf(action, "state") === "NOT_SUBMITTED").length === 2
        && entries.some((action) => (
          stringOf(action, "execution_action_id") === firstEntryId
          && stringOf(action, "state") === "CLOSED"
        ))
        && actions.some((action) => (
          stringOf(action, "action_kind") === "CANCEL"
          && stringOf(action, "state") === "CLOSED"
        ));
    });
    expect(expired, "到期后应闭合首档撤单责任并拒绝两个未提交档位").not.toBeNull();
    if (!expired) throw new Error("MAKER_EXPIRY_EVIDENCE_NOT_OBSERVED");

    const expiredActions = recordsOf(expired.execution_actions);
    const expiredFacts = recordsOf(expired.venue_facts);
    const entryActions = expiredActions.filter((action) => stringOf(action, "action_kind") === "ENTRY");
    const remainingEntries = entryActions.filter((action) => stringOf(action, "execution_action_id") !== firstEntryId);
    const closedCancels = expiredActions.filter((action) => (
      stringOf(action, "action_kind") === "CANCEL" && stringOf(action, "state") === "CLOSED"
    ));
    expect(entryActions).toHaveLength(3);
    expect(remainingEntries).toHaveLength(2);
    expect(remainingEntries.every((action) => (
      stringOf(action, "state") === "NOT_SUBMITTED"
      && stringOf(action, "not_submitted_reason") === "DIRECT_ENTRY_REMAINING_EXPIRED"
    ))).toBeTruthy();
    expect(remainingEntries.map(actionScheduleIndex).sort()).toEqual([1, 2]);
    expect(closedCancels).toHaveLength(1);
    expect(stringOf(recordOf(closedCancels[0]?.cancel_target), "client_order_id"), "撤单目标必须精确绑定首档 client_order_id")
      .toBe(firstEntryClientOrderId);
    expect(stringOf(recordOf(closedCancels[0]?.cancel_target), "endpoint")).toBe("ORDINARY");
    expect(stringOf(recordOf(closedCancels[0]?.action_terms), "causation_ref"))
      .toContain("DIRECT_ENTRY_REMAINING_EXPIRED");
    expect(expiredFacts.filter((fact) => stringOf(fact, "kind") === "FILL"), "本场景不得出现任何成交事实")
      .toEqual([]);
    const cancelledEntryFact = expiredFacts.find((fact) => (
      stringOf(fact, "action_ref") === firstEntryId
      && stringOf(fact, "kind") === "ORDER_STATE"
      && stringOf(recordOf(fact.payload), "status") === "CANCELLED"
    ));
    expect(cancelledEntryFact, "首档必须收到交易所 CANCELLED 终态事实").toBeTruthy();
    expect(Number(recordOf(cancelledEntryFact?.payload).cumulative_filled_quantity), "撤单终态累计成交必须为零")
      .toBe(0);

    await page.reload();
    await expect(actionsSection.getByText("撤单 · 已核对闭合", { exact: true })).toBeVisible({ timeout: 15_000 });
    await expect(actionsSection.getByText("入场 · 未提交", { exact: true })).toHaveCount(2);
    await expect(actionsSection.getByText(/^交易所事实 · 成交/)).toHaveCount(0);
    await testInfo.attach("maker-expiry-closed.json", {
      body: Buffer.from(JSON.stringify(expired, null, 2)),
      contentType: "application/json",
    });
    await testInfo.attach("maker-expiry-closed.png", {
      body: await page.screenshot({ fullPage: true }),
      contentType: "image/png",
    });
  } finally {
    if (activationId) {
      await cleanupActivation(page, testInfo, activationId);
      const closed = await readActivation(page, activationId);
      expect(activationLifecycle(closed), "finally 必须经 UI 或 API 退出并由 API 验证激活闭合").toBe("COMPLETED");
      await testInfo.attach("maker-expiry-cleanup-final.json", {
        body: Buffer.from(JSON.stringify(closed, null, 2)),
        contentType: "application/json",
      });
    } else if (baselineCaptured) {
      await cleanupCreatedDraft(page, testInfo, planName, baselinePlanIds, draftRef);
    }
  }
});

test("serial protected ladder fills three Demo legs before the global time exit", async ({ page }, testInfo) => {
  test.skip(!allowDemoMutation, demoMutationOptInMessage);
  test.skip(testInfo.project.name === "chromium-narrow", "Demo 变更场景只在 desktop 串行执行");
  test.setTimeout(240_000);
  const planName = `E2E AI 三档依次成交 ${Date.now()} ${randomUUID().slice(0, 8)}`;
  const baselinePlanIds = new Set<string>();
  let baselineCaptured = false;
  let draftRef: TestDraftRef | null = null;
  let activationId: string | null = null;

  try {
    await page.goto("/plans/new");
    await expect(page.getByText("DEMO", { exact: true })).toBeVisible();
    for (const plan of await readPlans(page)) baselinePlanIds.add(stringOf(plan, "plan_id"));
    baselineCaptured = true;

    await page.getByRole("button", { name: "配置订单计划", exact: true }).click();
    await expect(page.getByRole("heading", { name: "直接执行", exact: true })).toBeVisible();
    await revealPlanOptions(page);
    await page.getByLabel("计划名称").fill(planName);
    await choose(page, "创建方式", "AI 创建");
    await selectToggle(page, "做多");

    const marketResponse = await page.request.get("/api/v1/market-context", {
      params: { instrument_ref: "BTCUSDT-PERP", channel_lookback_15m: 20 },
    });
    expect(marketResponse.ok(), "可成交限价必须来自本次只读公开行情").toBeTruthy();
    const market = recordOf(await marketResponse.json());
    const referencePrice = Number(market.reference_price);
    expect(Number.isFinite(referencePrice) && referencePrice > 0).toBeTruthy();
    const lowerPrice = (Math.ceil(referencePrice * 1.01 * 10) / 10).toFixed(1);
    const upperPrice = (Math.ceil(referencePrice * 1.02 * 10) / 10).toFixed(1);
    expect(Number(lowerPrice)).toBeGreaterThan(referencePrice);

    await page.getByLabel("资金上限（USDT）").fill("500");
    await selectToggle(page, "区间阶梯");
    await page.getByLabel("下限（USDT）", { exact: true }).fill(lowerPrice);
    await page.getByLabel("上限（USDT）", { exact: true }).fill(upperPrice);
    await page.getByLabel("价格档位数").fill("3");
    await revealAdvancedPriceSpacing(page);
    await choose(page, "价格切分间距", "等距");
    await choose(page, "下单额模式", "固定金额");
    await page.getByLabel("每档金额（USDT）").fill("150");
    await revealAdvancedVenueSettings(page);
    await choose(page, "有效方式", "GTC · 持续有效");
    await choose(page, "串行提交顺序", "低价 → 高价");
    await expect(page.getByRole("switch", { name: "Maker only" })).not.toBeChecked();
    await page.getByLabel("初始止损距离（bps）").fill("1000");
    await revealProfitAndTimeExit(page);
    await page.getByRole("checkbox", { name: "启用单级全量止盈" }).uncheck();
    await page.getByRole("checkbox", { name: "启用整次持仓时间退出" }).check();
    await page.getByLabel("首笔成交后整组退出（秒）").fill("45");

    await expect(page.getByText(/^预览可保存 · 3 档/)).toBeVisible({ timeout: 30_000 });
    await revealNormalizedDetails(page);
    const ladderTable = page.getByRole("table", { name: "标准化订单档位表" });
    await expect(ladderTable.getByRole("row")).toHaveCount(4);
    await expect(ladderTable.getByText("150 USDT", { exact: true })).toHaveCount(3);

    const saveButton = page.getByRole("button", { name: "保存并检查", exact: true });
    await expect(saveButton).toBeEnabled({ timeout: 30_000 });
    await saveButton.click();
    await expect(page).toHaveURL(/\/plans$/);

    const createdPlan = await findCreatedDirectPlan(page, planName, baselinePlanIds);
    expect(createdPlan, "保存后必须唯一定位本场景草稿").not.toBeNull();
    if (!createdPlan) throw new Error("TEST_DRAFT_NOT_FOUND_AFTER_SAVE");
    const createdDraftVersion = Number(createdPlan.draft_version);
    expect(Number.isInteger(createdDraftVersion)).toBeTruthy();
    draftRef = {
      planId: stringOf(createdPlan, "plan_id"),
      draftVersion: createdDraftVersion,
      planName,
    };

    const planCard = page.getByRole("article", { name: `计划 ${planName}` });
    await planCard.getByText("计划配置", { exact: true }).click();
    await expect(planCard.getByText(/3 档阶梯 · 限价/)).toBeVisible();
    await planCard.getByRole("button", { name: "确认计划", exact: true }).click();
    const startPlanButton = planCard.getByRole("button", { name: "启动订单计划", exact: true });
    await expect(startPlanButton).toBeVisible({ timeout: 30_000 });
    await startPlanButton.click();

    await expect(page.getByText("DIRECT_EXECUTION@1", { exact: true }).first()).toBeVisible();
    await expect(page.getByRole("heading", { name: "实际提交复核" })).toBeVisible();
    await startDirectActivation(page);
    activationId = new URL(page.url()).pathname.split("/").filter(Boolean).at(-1) ?? null;
    if (!activationId) throw new Error("ACTIVATION_ID_MISSING_AFTER_SERIAL_START");

    const protectedLadder = await waitForActivationEvidence(page, activationId, 90_000, (snapshot) => {
      const actions = recordsOf(snapshot.execution_actions);
      const facts = recordsOf(snapshot.venue_facts);
      const entries = actions.filter((action) => stringOf(action, "action_kind") === "ENTRY");
      const protections = actions.filter((action) => stringOf(action, "action_kind") === "PROTECTION");
      const entryIds = new Set(entries.map((action) => stringOf(action, "execution_action_id")));
      const filledEntryIds = new Set(facts
        .filter((fact) => stringOf(fact, "kind") === "FILL" && entryIds.has(stringOf(fact, "action_ref")))
        .map((fact) => stringOf(fact, "action_ref")));
      return entries.length === 3
        && entries.every((action) => stringOf(action, "state") === "CLOSED")
        && filledEntryIds.size === 3
        && protections.length === 3
        && protections.every((action) => stringOf(action, "state") === "OPEN")
        && stringOf(recordOf(snapshot.activation), "protection_state") === "WORKING"
        && serialProtectionCausality(snapshot, 3);
    });
    expect(
      protectedLadder,
      "三档必须依次成交，且每笔成交都有独立 WORKING 保护后才算完成入场",
    ).not.toBeNull();
    if (!protectedLadder) throw new Error("SERIAL_PROTECTED_LADDER_NOT_OBSERVED");
    await testInfo.attach("serial-ladder-protected.json", {
      body: Buffer.from(JSON.stringify(protectedLadder, null, 2)),
      contentType: "application/json",
    });

    const completed = await waitForCompleted(page, activationId, 120_000);
    expect(completed, "首笔成交的全局时间退出必须闭合三档累计持仓").not.toBeNull();
    if (!completed) throw new Error("SERIAL_LADDER_TIME_EXIT_NOT_COMPLETED");
    const completedActions = recordsOf(completed.execution_actions);
    const completedFacts = recordsOf(completed.venue_facts);
    const completedEntries = completedActions.filter((action) => stringOf(action, "action_kind") === "ENTRY");
    const completedProtections = completedActions.filter((action) => stringOf(action, "action_kind") === "PROTECTION");
    const completedEntryIds = new Set(completedEntries.map((action) => stringOf(action, "execution_action_id")));
    const filledEntryIds = new Set(completedFacts
      .filter((fact) => stringOf(fact, "kind") === "FILL" && completedEntryIds.has(stringOf(fact, "action_ref")))
      .map((fact) => stringOf(fact, "action_ref")));
    expect(completedEntries).toHaveLength(3);
    expect(completedEntries.every((action) => stringOf(action, "state") === "CLOSED")).toBeTruthy();
    expect(filledEntryIds.size).toBe(3);
    expect(completedProtections).toHaveLength(3);
    expect(completedProtections.every((action) => stringOf(action, "state") === "CLOSED")).toBeTruthy();
    expect(serialProtectionCausality(completed, 3), "完成态仍必须保留逐档成交、保护、后档提交的因果证据")
      .toBeTruthy();
    expect(completedActions.some((action) => (
      stringOf(action, "action_kind") === "EXIT"
      && stringOf(action, "state") === "CLOSED"
      && stringOf(recordOf(action.action_terms), "causation_ref").endsWith(":EXIT:DIRECT_TIME_EXIT")
    )), "三档必须由全局首笔成交计时退出闭合，不能由保护缺口退出替代").toBeTruthy();
    expect(stringOf(recordOf(completed.activation), "protection_state")).toBe("CLOSED");
    await testInfo.attach("serial-ladder-completed.json", {
      body: Buffer.from(JSON.stringify(completed, null, 2)),
      contentType: "application/json",
    });
  } finally {
    if (activationId) {
      await cleanupActivation(page, testInfo, activationId);
      const closed = await readActivation(page, activationId);
      expect(activationLifecycle(closed), "finally 必须验证三档场景已闭合").toBe("COMPLETED");
    } else if (baselineCaptured) {
      await cleanupCreatedDraft(page, testInfo, planName, baselinePlanIds, draftRef);
    }
  }
});
