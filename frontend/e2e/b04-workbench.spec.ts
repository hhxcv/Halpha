import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type TestInfo } from "@playwright/test";

const fixturePassword = process.env.HALPHA_BROWSER_FIXTURE_PASSWORD;

type Activation = {
  activation_id: string;
  instrument_ref: string;
  lifecycle: string;
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

  const layout = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
    offenders: [...document.querySelectorAll<HTMLElement>("body *")]
      .filter((element) => !element.closest(".table-scroll"))
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
  await testInfo.attach("b04-operations-layout.json", {
    body: Buffer.from(JSON.stringify(layout, null, 2)),
    contentType: "application/json",
  });
  expect(layout.offenders).toEqual([]);
  expect(layout.scrollWidth).toBe(layout.clientWidth);
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
