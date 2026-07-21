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
  await expect(page.getByText("DEMO", { exact: true })).toBeVisible();
  await expect(page.getByText("真实账户交易", { exact: false })).toHaveCount(0);
  await expect(page.getByText("刷新于", { exact: false })).toBeVisible();
  await assertAccessible(page, testInfo, "overview");

  await page.goto("/plans/new");
  await expect(page.getByRole("heading", { name: "选择策略" })).toBeVisible();
  await expect(page.getByText("DEMO", { exact: true })).toBeVisible();
  await expect(page.getByLabel("筛选策略")).toBeVisible();
  await expect(page.getByLabel("支持方向")).toBeVisible();
  await expect(page.getByRole("combobox", { name: "排序" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "配置策略计划" })).toHaveCount(0);
  await page.getByLabel("筛选策略").fill("Donchian");
  await expect(page.getByText("单次 Donchian 突破与 ATR 风险退出", { exact: true })).toBeVisible();
  await page.getByRole("combobox", { name: "排序" }).click();
  await page.getByRole("option", { name: "策略版本（新到旧）" }).click();
  await page.getByRole("button", { name: "展开介绍" }).click();
  await expect(page.getByText("价值逻辑", { exact: true })).toBeVisible();
  await assertAccessible(page, testInfo, "strategy-selection");
  await page.getByRole("button", { name: "配置策略" }).click();
  await expect(page.getByRole("heading", { name: "配置策略计划" })).toBeVisible();
  await expect(page.getByRole("button", { name: "保存计划" })).toBeVisible();
  await expect(page.getByRole("button", { name: "重新选择策略" })).toBeVisible();
  await expect(page.getByLabel("交易对象")).toHaveValue("BTCUSDT-PERP");
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
  await expect(page.getByRole("tab", { name: /当前计划/ })).toBeVisible();
  await expect(page.getByRole("tab", { name: /历史计划/ })).toBeVisible();
  await expect(page.getByText("了解当前可用策略", { exact: false })).toHaveCount(0);
  await expect(page.getByText("BTCUSDT-PERP").first()).toBeVisible();
  await page.getByText("策略详情", { exact: true }).first().click();
  await expect(page.getByText("价值逻辑", { exact: true }).first()).toBeVisible();

  await page.goto("/operations");
  await expect(page.getByRole("heading", { name: "故障接管" })).toBeVisible();
  await expect(page.getByText("DEMO", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "打开 Binance 官方入口" })).toBeVisible();
  const activation = page.locator("article.activation").filter({ hasText: "WRITER_CONTINUITY_LOST" }).first();
  await expect(activation).toBeVisible();
  const activationId = await activation.getAttribute("data-activation-id");
  expect(activationId).toBeTruthy();
  await expect(activation.getByText(/PAUSED · WRITER_CONTINUITY_LOST/)).toBeVisible();
  await expect(activation.getByText("恢复激活", { exact: false })).toHaveCount(0);
  await assertAccessible(page, testInfo, "operations-before");

  const stopControl = activation.locator(".control").filter({ hasText: "停止新增风险" });
  await stopControl.getByRole("button", { name: "查看后果" }).click();
  const dialog = page.getByRole("dialog", { name: "确认故障控制" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("停止新增风险", { exact: true })).toBeVisible();
  await expect(dialog.getByText("只停止新的开仓和加仓", { exact: false })).toBeVisible();
  await assertAccessible(page, testInfo, "stop-preview");
  await dialog.getByRole("button", { name: "取消" }).click();

  const exitControl = activation.locator(".control").filter({ hasText: "退出策略" });
  await exitControl.getByRole("button", { name: "查看后果" }).click();
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "确认退出策略" }).click();
  await expect(activation.getByRole("status")).toContainText("EFFECTIVE · 回执");
  await expect(activation.getByRole("status")).toContainText("EXIT_WITHOUT_VENUE_RESPONSIBILITY_COMPLETED");
  await page.reload();
  await expect(page.locator(`article.activation[data-activation-id="${activationId}"]`)).toHaveCount(0);
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
