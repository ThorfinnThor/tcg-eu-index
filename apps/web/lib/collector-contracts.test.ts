import { describe, expect, it } from "vitest";
import {
  collectorDataState,
  validateCollectorDataset,
  validateCollectorHistory,
  validateCollectorRebalances,
  validateCollectorSummary
} from "./collector-contracts";
import {
  collectorFixtureDiagnostics,
  collectorFixtureHistory,
  collectorFixtureRebalances,
  collectorFixtureSummary
} from "./collector-fixtures";

describe("v1.5 collector contracts", () => {
  it("accepts the private schema-v2 fixture with uncapped membership", () => {
    expect(collectorDataState).toBe("private_shadow");
    expect(() => validateCollectorSummary(collectorFixtureSummary)).not.toThrow();
    expect(() => validateCollectorHistory(collectorFixtureHistory)).not.toThrow();
    expect(() => validateCollectorRebalances(collectorFixtureRebalances)).not.toThrow();
    expect(() => validateCollectorDataset({
      manifest: {
        schema_version: 2,
        series_id: collectorFixtureSummary.series_id,
        index_code: collectorFixtureSummary.index_code,
        methodology_version: collectorFixtureSummary.methodology_version,
        data_state: "private_shadow",
        public_alias_enabled: false,
        generated_for: "2026-08-21",
        engine_revision: "fixture",
        source_hashes: {},
        outputs: {
          "derived/indexes/1.5.0-preview.2/private_shadow/OPEUCOL/history.json": {
            key: "derived/indexes/1.5.0-preview.2/private_shadow/OPEUCOL/history.json",
            sha256: "a".repeat(64),
            bytes: 1
          }
        }
      },
      summary: collectorFixtureSummary,
      history: collectorFixtureHistory,
      rebalances: collectorFixtureRebalances,
      diagnostics: collectorFixtureDiagnostics
    })).not.toThrow();
  });

  it("rejects a numbered or public collector contract", () => {
    expect(() => validateCollectorSummary({ ...collectorFixtureSummary, index_code: "OPEU500" })).toThrow();
    expect(() => validateCollectorSummary({ ...collectorFixtureSummary, public_alias_enabled: true })).toThrow();
  });

  it("rejects an invalid rebalance cadence and selection ordering", () => {
    expect(() => validateCollectorRebalances({ ...collectorFixtureRebalances, cadence: "daily_preview" })).toThrow();
    expect(() => validateCollectorRebalances({
      ...collectorFixtureRebalances,
      rebalances: [{ ...collectorFixtureRebalances.rebalances[0], selection_as_of: "2026-08-20" }]
    })).toThrow();
  });
});
