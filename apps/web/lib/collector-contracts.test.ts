import { describe, expect, it } from "vitest";
import {
  collectorDataState,
  validateCollectorCompositionIndex,
  validateCollectorCompositionPage,
  validateCollectorDataset,
  validateCollectorHistory,
  validateCollectorPreviewIndex,
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
    const fixtureRebalance = collectorFixtureRebalances.rebalances[0];
    const composition = {
      schema_version: 2 as const,
      series_id: collectorFixtureSummary.series_id,
      index_code: collectorFixtureSummary.index_code,
      methodology_version: collectorFixtureSummary.methodology_version,
      data_state: "private_shadow" as const,
      publication_state: "preview_noindex" as const,
      generated_for: collectorFixtureSummary.generated_for,
      rebalances: [{
        effective_date: fixtureRebalance.effective_date,
        selection_as_of: fixtureRebalance.selection_as_of,
        active_count: fixtureRebalance.active_count,
        page_size: 250,
        page_count: 1,
        pages: [{ page: 1, path: `composition/${fixtureRebalance.effective_date}/0001.json`, sha256: "fixture", bytes: 1 }]
      }]
    };
    const compositionPage = {
      schema_version: 2 as const,
      series_id: collectorFixtureSummary.series_id,
      index_code: collectorFixtureSummary.index_code,
      methodology_version: collectorFixtureSummary.methodology_version,
      data_state: "private_shadow" as const,
      publication_state: "preview_noindex" as const,
      generated_for: collectorFixtureSummary.generated_for,
      effective_date: fixtureRebalance.effective_date,
      page: 1,
      page_count: 1,
      constituents: fixtureRebalance.constituents
    };
    expect(collectorDataState).toBe("private_shadow");
    expect(() => validateCollectorSummary(collectorFixtureSummary)).not.toThrow();
    expect(() => validateCollectorHistory(collectorFixtureHistory)).not.toThrow();
    expect(() => validateCollectorRebalances(collectorFixtureRebalances)).not.toThrow();
    expect(() => validateCollectorCompositionIndex(composition)).not.toThrow();
    expect(() => validateCollectorCompositionPage(compositionPage)).not.toThrow();
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
      diagnostics: collectorFixtureDiagnostics,
      composition,
      compositionPage
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

  it("accepts only singles in the public noindex preview directory", () => {
    const payload = {
      schema_version: 1,
      publication_state: "preview_noindex",
      generated_for: "2026-08-29",
      methodology_version: "1.5.0-preview.2",
      indexes: [{
        code: "OPEUCOL",
        name: "One Piece Europe Collector Index",
        game_key: "onepiece",
        status: "preview",
        base_value: 1000,
        latest_index_value: 1000,
        latest_value_date: "2026-08-29",
        constituent_count: 2126
      }]
    };
    expect(() => validateCollectorPreviewIndex(payload)).not.toThrow();
    expect(() => validateCollectorPreviewIndex({
      ...payload,
      indexes: [{ ...payload.indexes[0], code: "OPEUSCOL" }]
    })).toThrow(/sealed/);
  });
});
