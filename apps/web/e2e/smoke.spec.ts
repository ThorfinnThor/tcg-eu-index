import { expect, test } from "@playwright/test";

test("market overview and index exploration", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Market overview" })).toBeVisible();
  await expect(page.getByText("Validation history begins 2026-04-01")).toBeVisible();

  await page.getByRole("link", { name: /One Piece Europe 100/ }).click();
  await expect(page).toHaveURL(/\/index\/OPEU100$/);
  await expect(page.getByRole("heading", { name: "One Piece Europe 100" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Post-inception analytics" })).toBeVisible();
  await expect(page.getByText(/formal MVP inception is 2026-07-20/)).toBeVisible();

  await page.getByRole("button", { name: "Max" }).click();
  await expect(page.getByRole("button", { name: "Max" })).toHaveAttribute("aria-pressed", "true");
  await page.getByLabel("Drawdown").check();
  await expect(page.getByLabel("Drawdown")).toBeChecked();
});

test("constituents, embed, reports, and public CSV remain reachable", async ({ page, request }) => {
  await page.goto("/index/OPEU100/constituents?asOf=2026-07-29&q=Benchmark&inactive=1");
  await expect(page.getByRole("heading", { name: "Constituents" })).toBeVisible();
  await expect(page.getByRole("searchbox", { name: /search/i })).toHaveValue("Benchmark");

  await page.goto("/embed/index/OPEU100");
  await expect(page.getByText("OPEU100", { exact: true })).toBeVisible();

  await page.goto("/reports");
  await expect(page.getByRole("heading", { name: "Weekly reports" })).toBeVisible();

  const csv = await request.get("/api/public/OPEU100/history.csv");
  expect(csv.ok()).toBe(true);
  expect(csv.headers()["content-type"]).toContain("text/csv");
  expect(await csv.text()).toContain("value_date,index_value,daily_return");
});

test("primary pages do not overflow the viewport", async ({ page }) => {
  for (const path of ["/", "/index/PKEU250", "/portfolio", "/data-quality"]) {
    await page.goto(path);
    const dimensions = await page.evaluate(() => ({
      documentWidth: document.documentElement.scrollWidth,
      viewportWidth: document.documentElement.clientWidth
    }));
    expect(dimensions.documentWidth, `${path} has horizontal overflow`).toBeLessThanOrEqual(
      dimensions.viewportWidth + 1
    );
  }
});
