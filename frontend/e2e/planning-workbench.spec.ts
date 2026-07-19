import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type TestInfo } from "@playwright/test";

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

test("planning and limited-control surfaces preserve authority and failure boundaries", async ({ page }, testInfo) => {
  await page.goto("/overview");
  await expect(page).toHaveURL(/\/overview$/);
  await expect(page.getByText("REAL WRITE · CLOSED")).toBeVisible();
  await assertAccessible(page, testInfo, "overview");

  await page.goto("/plans/new");
  await expect(page.getByRole("heading", { name: "新建策略计划" })).toBeVisible();
  await expect(page.getByText("DEMO 主要验证交易闭环和安全机制")).toBeVisible();
  await expect(page.getByRole("button", { name: "保存计划" })).toBeVisible();
  await expect(page.getByLabel("Instrument")).toHaveValue("BTCUSDT-PERP");
  await expect(page.getByLabel("交易金额（USDT）")).toHaveValue("500");
  await expect(page.getByText("高级策略参数（可保持默认）")).toBeVisible();
  await assertAccessible(page, testInfo, "new-plan");
  await testInfo.attach("new-plan.png", {
    body: await page.screenshot({ fullPage: true }),
    contentType: "image/png",
  });
  await page.getByRole("button", { name: "保存计划" }).click();
  await expect(page).toHaveURL(/\/plans$/);
  await expect(page.getByRole("heading", { name: "策略计划" })).toBeVisible();
  await expect(page.getByText("BTCUSDT-PERP").first()).toBeVisible();

  await page.goto("/operations");
  await expect(page.getByRole("heading", { name: "Recovery operations" })).toBeVisible();
  await expect(page.getByText("REAL WRITE · CLOSED")).toBeVisible();
  const activation = page.locator("article.activation").filter({ hasText: "RECOVERY DECISION REQUIRED" }).first();
  await expect(activation).toBeVisible();
  const activationId = await activation.getAttribute("data-activation-id");
  expect(activationId).toBeTruthy();
  await expect(activation.getByText("RECOVERY DECISION REQUIRED")).toBeVisible();
  await assertAccessible(page, testInfo, "operations-before");

  const resumeControl = activation.locator(".control-row").filter({ hasText: "Resume activation" });
  await resumeControl.getByRole("button", { name: "Preview" }).click();
  const dialog = page.getByRole("dialog", { name: "Confirm limited control" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("Resume is denied: no authoritative reconciliation digest")).toBeVisible();
  await expect(dialog.getByRole("button", { name: "Submit RESUME_ACTIVATION" })).toBeDisabled();
  await assertAccessible(page, testInfo, "resume-denied");
  await dialog.getByRole("button", { name: "Cancel" }).click();

  const exitControl = activation.locator(".control-row").filter({ hasText: "Exit strategy" });
  await exitControl.getByRole("button", { name: "Preview" }).click();
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "Submit EXIT_STRATEGY" }).click();
  await expect(activation.getByRole("status")).toContainText("PROCESSING · Receipt");
  await page.reload();
  const exiting = page.locator(`article.activation[data-activation-id="${activationId}"]`);
  await expect(exiting.getByText("EXIT CLOSURE PENDING")).toBeVisible();
  await expect(exiting.getByText("EXIT_STRATEGY")).toBeVisible();
  await assertAccessible(page, testInfo, "operations-after-exit");
  await testInfo.attach("operations-after-exit.png", {
    body: await page.screenshot({ fullPage: true }),
    contentType: "image/png",
  });

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
  await testInfo.attach("operations-layout.json", {
    body: Buffer.from(JSON.stringify(layout, null, 2)),
    contentType: "application/json",
  });
  expect(layout.offenders).toEqual([]);
  expect(layout.scrollWidth).toBe(layout.clientWidth);
});
