import { describe, expect, it } from "vitest";
import sitemap from "@/app/sitemap";
import { breadcrumbStructuredData, indexDatasetStructuredData } from "./structured-data";
import { getPageDefinition, getPageDefinitions, isIndexable, pageMetadata, reportPageMetadata } from "./seo";

describe("SEO publication registry", () => {
  it("keeps only approved page definitions indexable", () => {
    const definitions = getPageDefinitions();
    const canonicals = definitions.map((definition) => definition.canonical);
    expect(new Set(canonicals).size).toBe(canonicals.length);
    expect(definitions.filter(isIndexable).map((definition) => definition.id)).toEqual([
      "overview",
      "opeu100-index",
      "pkeu250-index",
      "opeusld-index",
      "methodology",
      "data-quality"
    ]);
    expect(getPageDefinition("reports")?.indexable).toBe(false);
  });

  it("applies canonical and noindex metadata from the registry", () => {
    expect(pageMetadata("overview", "Overview", "Description").alternates).toEqual({ canonical: "/" });
    expect(pageMetadata("reports", "Reports", "Description").robots).toEqual({ index: false, follow: true });
    expect(reportPageMetadata("reports/2026-W31", "Report", "Description").robots).toEqual({
      index: false,
      follow: true
    });
  });

  it("builds the sitemap only from published indexable definitions", async () => {
    const entries = await sitemap();
    const urls = entries.map((entry) => entry.url);
    expect(urls).toContain("https://tcg-eu-index.vercel.app/index/OPEU100");
    expect(urls).not.toContain("https://tcg-eu-index.vercel.app/reports");
    expect(urls).not.toContain("https://tcg-eu-index.vercel.app/portfolio");
    expect(urls).not.toContain("https://tcg-eu-index.vercel.app/index/OPEU100/constituents");
  });
});

describe("structured data", () => {
  it("describes index datasets and breadcrumbs without raw price claims", () => {
    const dataset = indexDatasetStructuredData({
      siteUrl: "https://example.com",
      code: "OPEU100",
      name: "One Piece Europe 100",
      description: "Listing-price benchmark",
      startDate: "2026-07-20",
      endDate: "2026-08-01"
    });
    expect(dataset["@type"]).toBe("Dataset");
    expect(dataset.temporalCoverage).toBe("2026-07-20/2026-08-01");
    expect(dataset.distribution.contentUrl).toBe("https://example.com/api/public/OPEU100/history.csv");

    const breadcrumbs = breadcrumbStructuredData("https://example.com", [
      { label: "Overview", href: "/" },
      { label: "Index" }
    ]);
    expect(breadcrumbs.itemListElement).toHaveLength(2);
    expect(breadcrumbs.itemListElement[0].item).toBe("https://example.com/");
  });
});
