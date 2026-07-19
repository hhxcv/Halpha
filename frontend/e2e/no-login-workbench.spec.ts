import { expect, test } from "@playwright/test";

test("the local workbench opens directly without a login surface", async ({ page }) => {
  const removedLoginRoute = await page.request.get("/login");
  expect(removedLoginRoute.status()).toBe(404);

  await page.goto("/");
  await expect(page).toHaveURL(/\/overview$/);
  await expect(page.getByText("Halpha", { exact: true })).toBeVisible();
  await expect(page.locator('input[type="password"]')).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: /login|log in|sign in|logout|log out|sign out/i }),
  ).toHaveCount(0);

  const overview = await page.request.get("/api/v1/overview");
  expect(overview.status()).toBe(200);
});
