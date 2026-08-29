import { describe, expect, it } from "vitest";
import {
  collectorDiagnosticSummary,
  collectorGameName,
  collectorThreshold,
  collectorUniverseLabel,
  formatCollectorEur,
  formatCollectorPct
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
});
