import { readAssetText } from "@runtime-data";
import {
  validateCollectorCompositionIndex,
  validateCollectorDataset,
  validateCollectorPreviewIndex
} from "./collector-contracts";
import {
  collectorFixtureDiagnostics,
  collectorFixtureHistory,
  collectorFixtureManifest,
  collectorFixtureRebalances,
  collectorFixtureSummary
} from "./collector-fixtures";
import type {
  CollectorCompositionIndex,
  CollectorCompositionPage,
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
  composition: CollectorCompositionIndex;
  compositionPage: CollectorCompositionPage;
};

type CollectorCompositionSelection = {
  effectiveDate?: string;
  page?: number;
};

const methodologyVersion = "1.5.0-preview.2";

function previewIndexPrefix(code: CollectorIndexCode) {
  return `data/collector/${code}`;
}

export async function getCollectorDataset(
  code: CollectorIndexCode,
  selection: CollectorCompositionSelection = {}
): Promise<CollectorDataset | null> {
  const prefix = previewIndexPrefix(code);
  try {
    const manifest = JSON.parse(await readAssetText(`${prefix}/manifest.json`)) as CollectorOutputManifest;
    const [summary, history, rebalances, diagnostics, compositionText] = await Promise.all([
      readAssetText(`${prefix}/summary.json`),
      readAssetText(`${prefix}/history.json`),
      readAssetText(`${prefix}/rebalances.json`),
      readAssetText(`${prefix}/diagnostics.json`),
      readAssetText(`${prefix}/composition.json`)
    ]);
    const composition = JSON.parse(compositionText) as CollectorCompositionIndex;
    validateCollectorCompositionIndex(composition);
    const selectedRebalance = composition.rebalances.find(
      (rebalance) => rebalance.effective_date === selection.effectiveDate
    ) ?? composition.rebalances.at(-1);
    if (!selectedRebalance) return null;
    const requestedPage = Number.isInteger(selection.page) ? Number(selection.page) : 1;
    const selectedPage = Math.min(Math.max(requestedPage, 1), selectedRebalance.page_count);
    const pageMetadata = selectedRebalance.pages[selectedPage - 1];
    if (!pageMetadata) return null;
    const compositionPage = JSON.parse(
      await readAssetText(`${prefix}/${pageMetadata.path}`)
    ) as CollectorCompositionPage;
    const dataset = {
      manifest,
      summary: JSON.parse(summary) as CollectorIndexSummary,
      history: JSON.parse(history) as CollectorHistory,
      rebalances: JSON.parse(rebalances) as CollectorRebalances,
      diagnostics: JSON.parse(diagnostics) as CollectorDiagnostics,
      composition,
      compositionPage
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
        diagnostics: collectorFixtureDiagnostics,
        composition: {
          schema_version: 2 as const,
          series_id: collectorFixtureRebalances.series_id,
          index_code: collectorFixtureRebalances.index_code,
          methodology_version: collectorFixtureRebalances.methodology_version,
          data_state: "private_shadow" as const,
          publication_state: "preview_noindex" as const,
          generated_for: collectorFixtureRebalances.generated_for,
          rebalances: collectorFixtureRebalances.rebalances.map((rebalance) => ({
            effective_date: rebalance.effective_date,
            selection_as_of: rebalance.selection_as_of,
            active_count: rebalance.active_count,
            page_size: 250,
            page_count: 1,
            pages: [{ page: 1, path: `composition/${rebalance.effective_date}/0001.json`, sha256: "fixture", bytes: 1 }]
          }))
        },
        compositionPage: {
          schema_version: 2 as const,
          series_id: collectorFixtureRebalances.series_id,
          index_code: collectorFixtureRebalances.index_code,
          methodology_version: collectorFixtureRebalances.methodology_version,
          data_state: "private_shadow" as const,
          publication_state: "preview_noindex" as const,
          generated_for: collectorFixtureRebalances.generated_for,
          effective_date: collectorFixtureRebalances.rebalances.at(-1)?.effective_date ?? collectorFixtureRebalances.generated_for,
          page: 1,
          page_count: 1,
          constituents: collectorFixtureRebalances.rebalances.at(-1)?.constituents ?? []
        }
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
          base_value: collectorFixtureSummary.base_value,
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
