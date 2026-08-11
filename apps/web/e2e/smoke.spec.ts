import { expect, test } from "@playwright/test";

test("market overview and index exploration", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Market overview" })).toBeVisible();
  await expect(page.getByText("Validation history begins 2026-04-01")).toBeVisible();

  await page.getByRole("link", { name: /One Piece Europe 100/ }).click();
  await expect(page).toHaveURL(/\/index\/OPEU100$/);
  await expect(page.getByRole("heading", { name: "One Piece Europe 100" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Publication pending" })).toBeVisible();
  await expect(page.getByText(/No public index level/)).toBeVisible();
});

test("constituents, embed, reports, and public CSV remain reachable", async ({ page, request }) => {
  await page.goto("/index/OPEU100/constituents?asOf=2026-07-29&q=Benchmark&inactive=1");
  await expect(page.getByRole("heading", { name: "Constituents" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "No cards published yet" })).toBeVisible();
  await expect(page.getByText(/Synthetic development products are not public index members/)).toBeVisible();
  await expect(page.getByRole("searchbox", { name: /search/i })).toHaveCount(0);

  await page.goto("/embed/index/OPEU100");
  await expect(page.getByText("OPEU100", { exact: true })).toBeVisible();
  await expect(page.getByText(/No public value has been published/)).toBeVisible();

  await page.goto("/reports");
  await expect(page.getByRole("heading", { name: "Weekly reports" })).toBeVisible();

  const csv = await request.get("/api/public/OPEU100/history.csv");
  expect(csv.status()).toBe(409);
  expect(await csv.json()).toMatchObject({ error: "Index history has not been published" });
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
