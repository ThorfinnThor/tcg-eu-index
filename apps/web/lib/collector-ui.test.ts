import { describe, expect, it } from "vitest";
import {
  cardImageDeliveryUrl,
  collectorDiagnosticSummary,
  collectorGameName,
  collectorThreshold,
  collectorUniverseLabel,
  formatCollectorEur,
  formatCollectorPct,
  matchesCollectorPriceBand
} from "./collector-ui";
import { collectorFixtureDiagnostics, collectorFixtureSummary } from "./collector-fixtures";

describe("collector UI labels", () => {
  it("keeps the singles threshold and plain-language universe label", () => {
    expect(collectorThreshold(collectorFixtureSummary)).toBe(10);
    expect(collectorUniverseLabel("singles")).toBe("single-card variants");
    expect(collectorGameName("onepiece")).toBe("One Piece");
  });

  it("uses the sealed threshold independently", () => {
    expect(collectorThreshold({ universe: "sealed" })).toBe(30);
    expect(collectorUniverseLabel("sealed")).toBe("sealed products");
  });

  it("assigns boundary prices to one unambiguous display group", () => {
    expect(matchesCollectorPriceBand(10, "10-100")).toBe(true);
    expect(matchesCollectorPriceBand(99.99, "10-100")).toBe(true);
    expect(matchesCollectorPriceBand(100, "10-100")).toBe(false);
    expect(matchesCollectorPriceBand(100, "100-1000")).toBe(true);
    expect(matchesCollectorPriceBand(1_000, "1000-10000")).toBe(true);
    expect(matchesCollectorPriceBand(10_000, "10000-plus")).toBe(true);
    expect(matchesCollectorPriceBand(50_000, "all")).toBe(true);
  });

  it("preserves approved HTTPS image URLs without rewriting provider identities", () => {
    expect(cardImageDeliveryUrl("https://assets.tcgdex.net/en/xy/xy7/97/high.webp"))
      .toBe("https://assets.tcgdex.net/en/xy/xy7/97/high.webp");
    expect(cardImageDeliveryUrl("https://cards.scryfall.io/normal/example.jpg"))
      .toBe("https://cards.scryfall.io/normal/example.jpg");
    expect(cardImageDeliveryUrl("http://assets.tcgdex.net/en/xy/xy7/97/high.webp"))
      .toBeNull();
    expect(cardImageDeliveryUrl("not a URL")).toBeNull();
    expect(cardImageDeliveryUrl(null)).toBeNull();
  });

  it("formats missing diagnostics without inventing values", () => {
    expect(formatCollectorEur(null)).toBe("—");
    expect(formatCollectorPct(null)).toBe("—");
    expect(collectorDiagnosticSummary(collectorFixtureDiagnostics)).toEqual({
      count: 0,
      averageQuality: null,
      averageActivityRatio: null,
      positiveActivityRows: 0
    });
  });

  it("uses the bounded public diagnostic aggregate", () => {
    expect(collectorDiagnosticSummary({
      ...collectorFixtureDiagnostics,
      summary: {
        count: 12,
        average_quality: 0.8,
        average_activity_ratio: 0.4,
        positive_activity_rows: 9
      }
    })).toEqual({
      count: 12,
      averageQuality: 0.8,
      averageActivityRatio: 0.4,
      positiveActivityRows: 9
    });
  });
});
