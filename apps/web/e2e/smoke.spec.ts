import { expect, test } from "@playwright/test";

test("market overview and index exploration", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Market overview" })).toBeVisible();

  const onePieceIndex = page.getByRole("link", { name: /One Piece Europe 100/ });
  await expect(onePieceIndex).toBeVisible();
  await onePieceIndex.click();
  await expect(page).toHaveURL(/\/index\/OPEU100$/);
  await expect(page.getByRole("heading", { name: "One Piece Europe 100" })).toBeVisible();
  await expect(page.getByText("Preview index · not official", { exact: true })).toBeVisible();
  await expect(page.getByText(/Provisional index based on the Cardmarket history/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Preview analytics" })).toBeVisible();
});

test("constituents, embed, reports, and public CSV remain reachable", async ({ page, request }) => {
  await page.goto("/index/OPEU100/constituents");
  await expect(page.getByRole("heading", { name: "Constituents" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Daily preview composition" })).toBeVisible();
  await expect(page.getByText("100 active / 100 target", { exact: true })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Ref. price" })).toBeVisible();
  await expect(page.getByRole("searchbox", { name: /search/i })).toBeVisible();

  await page.goto("/embed/index/OPEU100");
  await expect(page.getByText("OPEU100", { exact: true })).toBeVisible();
  await expect(page.getByText(/Preview/)).toBeVisible();

  await page.goto("/reports");
  await expect(page.getByRole("heading", { name: "Weekly reports" })).toBeVisible();

  const csv = await request.get("/api/public/OPEU100/history.csv");
  expect(csv.status()).toBe(200);
  expect(csv.headers()["x-index-status"]).toBe("preview");
  expect(await csv.text()).toMatch(/^value_date,index_value,daily_return/);
});

test("sealed indexes describe constituents as products", async ({ page }) => {
  await page.goto("/index/OPEUSLD/constituents");
  await expect(page.getByRole("heading", { name: "Daily preview composition" })).toBeVisible();
  await expect(page.getByText("25 active / 25 target", { exact: true })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Ref. price" })).toBeVisible();
});

test("primary pages do not overflow the viewport", async ({ page }) => {
  for (const path of ["/", "/index/PKEU250", "/index/OPEU100/constituents", "/portfolio", "/data-quality"]) {
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

test("SEO publication rules are visible in rendered output", async ({ page, request }) => {
  await page.goto("/index/OPEU100");
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute("href", /\/index\/OPEU100$/);
  await expect(page.locator('script[type="application\/ld\+json"]')).toHaveCount(1);

  await page.goto("/reports");
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", /noindex/);

  const response = await request.get("/sitemap.xml");
  const xml = await response.text();
  expect(response.ok()).toBe(true);
  expect(xml).not.toContain("/index/OPEU100");
  expect(xml).not.toContain("/portfolio");
  expect(xml).not.toContain("/constituents");
});
