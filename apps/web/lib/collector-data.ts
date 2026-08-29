import { readAssetText } from "@runtime-data";
import { validateCollectorDataset, validateCollectorPreviewIndex } from "./collector-contracts";
import {
  collectorFixtureDiagnostics,
  collectorFixtureHistory,
  collectorFixtureManifest,
  collectorFixtureRebalances,
  collectorFixtureSummary
} from "./collector-fixtures";
import type {
  CollectorDiagnostics,
  CollectorHistory,
  CollectorIndexCode,
  CollectorIndexSummary,
  CollectorOutputManifest,
  CollectorPreviewIndexPayload,
  CollectorRebalances
} from "./types";

export type CollectorDataset = {
  manifest: CollectorOutputManifest;
  summary: CollectorIndexSummary;
  history: CollectorHistory;
  rebalances: CollectorRebalances;
  diagnostics: CollectorDiagnostics;
};

const methodologyVersion = "1.5.0-preview.2";

function previewIndexPrefix(code: CollectorIndexCode) {
  return `data/collector/${code}`;
}

export async function getCollectorDataset(code: CollectorIndexCode): Promise<CollectorDataset | null> {
  const prefix = previewIndexPrefix(code);
  try {
    const manifest = JSON.parse(await readAssetText(`${prefix}/manifest.json`)) as CollectorOutputManifest;
    const [summary, history, rebalances, diagnostics] = await Promise.all([
      readAssetText(`${prefix}/summary.json`),
      readAssetText(`${prefix}/history.json`),
      readAssetText(`${prefix}/rebalances.json`),
      readAssetText(`${prefix}/diagnostics.json`)
    ]);
    const dataset = {
      manifest,
      summary: JSON.parse(summary) as CollectorIndexSummary,
      history: JSON.parse(history) as CollectorHistory,
      rebalances: JSON.parse(rebalances) as CollectorRebalances,
      diagnostics: JSON.parse(diagnostics) as CollectorDiagnostics
    };
    validateCollectorDataset(dataset);
    return dataset;
  } catch {
    if (process.env.COLLECTOR_SHADOW_FIXTURES_ENABLED === "true" && code === "OPEUCOL") {
      const fixture = {
        manifest: collectorFixtureManifest,
        summary: collectorFixtureSummary,
        history: collectorFixtureHistory,
        rebalances: collectorFixtureRebalances,
        diagnostics: collectorFixtureDiagnostics
      };
      validateCollectorDataset(fixture);
      return fixture;
    }
    return null;
  }
}

export async function getCollectorPreviewIndex(): Promise<CollectorPreviewIndexPayload> {
  try {
    const payload = JSON.parse(await readAssetText("data/collector/index.json"));
    validateCollectorPreviewIndex(payload);
    return payload;
  } catch {
    if (process.env.COLLECTOR_SHADOW_FIXTURES_ENABLED === "true") {
      return {
        schema_version: 1,
        publication_state: "preview_noindex",
        generated_for: collectorFixtureSummary.generated_for,
        methodology_version: methodologyVersion,
        indexes: [{
          code: collectorFixtureSummary.index_code,
          name: collectorFixtureSummary.name,
          game_key: collectorFixtureSummary.game_key,
          status: collectorFixtureSummary.status,
          latest_index_value: collectorFixtureSummary.latest_index_value,
          latest_value_date: collectorFixtureSummary.latest_value_date,
          constituent_count: collectorFixtureSummary.product_metadata.constituent_count
        }]
      };
    }
    return {
      schema_version: 1,
      publication_state: "preview_noindex",
      generated_for: "1970-01-01",
      methodology_version: methodologyVersion,
      indexes: []
    };
  }
}
