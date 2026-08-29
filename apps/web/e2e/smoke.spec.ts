import { expect, test } from "@playwright/test";

test("collector overview excludes retired fixed-size and sealed cards", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "European collector card indexes" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Choose a card game" })).toBeVisible();
  await expect(page.getByRole("link", { name: /One Piece Europe Collector Index/ })).toBeVisible();
  await expect(page.getByText("One Piece Europe 500", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Magic Sealed Europe 100", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Latest", { exact: true })).toHaveCount(0);
});

test("constituents, embed, reports, and public CSV remain reachable", async ({ page, request }) => {
  await page.goto("/index/OPEU500/constituents");
  await expect(page.getByRole("heading", { name: "Constituents" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Daily preview composition" })).toBeVisible();
  await expect(page.getByText(/\d+ active \/ 500 target/)).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Price rank" })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Ref. price" })).toBeVisible();
  await expect(page.getByRole("searchbox", { name: /search/i })).toBeVisible();

  await page.goto("/embed/index/OPEU500");
  await expect(page.getByText("OPEU500", { exact: true })).toBeVisible();
  await expect(page.getByText(/Preview/)).toBeVisible();

  await page.goto("/reports");
  await expect(page.getByRole("heading", { name: "Weekly reports" })).toBeVisible();

  const csv = await request.get("/api/public/OPEU500/history.csv");
  expect(csv.status()).toBe(200);
  expect(csv.headers()["x-index-status"]).toBe("preview");
  expect(await csv.text()).toMatch(/^value_date,index_value,daily_return/);
});

test("sealed indexes describe constituents as products", async ({ page }) => {
  await page.goto("/index/OPEUSLD/constituents");
  await expect(page.getByRole("heading", { name: "Daily preview composition" })).toBeVisible();
  await expect(page.getByText(/\d+ active \/ 100 target/)).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Ref. price" })).toBeVisible();
});

test("collector singles expose clear card identity and commerce destinations", async ({ page }) => {
  await page.goto("/collector/OPEUCOL");
  await expect(page.getByRole("heading", { name: "One Piece Europe Collector Index" })).toBeVisible();
  await expect(page.getByText("Preview index", { exact: true })).toBeVisible();
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", /noindex/);
  await expect(page.getByRole("columnheader", { name: "Card" })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Marketplaces" })).toBeVisible();
  await expect(page.getByRole("link", { name: /Open .+ on Cardmarket/ }).first()).toBeVisible();
  await expect(page.getByRole("link", { name: /Open .+ on Cardmarket/ }).first()).toHaveAttribute("href", /idProduct=\d+/);
  await expect(page.getByText(/CM \d+/).first()).toBeVisible();
  await expect(page.getByRole("link", { name: /Search for .+ on eBay/ }).first()).toBeVisible();
  await expect(page.getByRole("link", { name: /Search for .+ on TCGplayer/ }).first()).toBeVisible();
  await expect(page.getByText("Eligible variants", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Data Quality Score" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Trading Activity Proxy" })).toHaveCount(0);

  await page.getByLabel("Price range").selectOption("1000-10000");
  await expect(page.getByText(/cards found/)).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "30-day average price" })).toBeVisible();

  await page.getByLabel("Price range").selectOption("all");
  await page.getByRole("searchbox", { name: "Search the entire index" }).fill("Monkey");
  await expect(page.getByText(/cards found/)).toBeVisible();

  const sealed = await page.request.get("/collector/OPEUSCOL");
  expect(sealed.status()).toBe(404);

  await page.goto("/collector/MTEUCOL");
  const compositionPages = page.getByRole("navigation", { name: "Composition pages" });
  await expect(compositionPages).toContainText(/Page 1 of \d+/);
  await compositionPages.getByRole("link", { name: "Next" }).click();
  await expect(page).toHaveURL(/page=2/);
  await expect(page.getByRole("navigation", { name: "Composition pages" })).toContainText(/Page 2 of \d+/);
});

test("primary pages do not overflow the viewport", async ({ page }) => {
  for (const path of ["/", "/index/PKEU500", "/index/OPEU500/constituents", "/portfolio", "/data-quality"]) {
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
  await page.goto("/index/OPEU500");
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute("href", /\/index\/OPEU500$/);
  await expect(page.locator('script[type="application\/ld\+json"]')).toHaveCount(1);

  await page.goto("/reports");
  await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", /noindex/);

  const response = await request.get("/sitemap.xml");
  const xml = await response.text();
  expect(response.ok()).toBe(true);
  expect(xml).not.toContain("/index/OPEU500");
  expect(xml).not.toContain("/portfolio");
  expect(xml).not.toContain("/constituents");
});

test("legacy singles URLs redirect to the top-500 canonical code", async ({ page }) => {
  await page.goto("/index/OPEU100");
  await expect(page).toHaveURL(/\/index\/OPEU500$/);

  await page.goto("/index/PKEU250/constituents");
  await expect(page).toHaveURL(/\/index\/PKEU500\/constituents(?:\?.*)?$/);
});
