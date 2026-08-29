import { readAssetText } from "@runtime-data";
import { validateCollectorDataset } from "./collector-contracts";
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

function privateIndexPrefix(code: CollectorIndexCode) {
  return `data/derived/indexes/${methodologyVersion}/private_shadow/${code}`;
}

export async function getCollectorDataset(code: CollectorIndexCode): Promise<CollectorDataset | null> {
  const prefix = privateIndexPrefix(code);
  try {
    const manifest = JSON.parse(await readAssetText(`${prefix}/manifest.json`)) as CollectorOutputManifest;
    const [summary, history, rebalances] = await Promise.all([
      readAssetText(`${prefix}/summary.json`),
      readAssetText(`${prefix}/history.json`),
      readAssetText(`${prefix}/rebalances.json`)
    ]);
    const diagnosticsKey = Object.keys(manifest.outputs)
      .find((key) => key.startsWith(`derived/diagnostics/${methodologyVersion}/${code}/daily/`) && key.endsWith(".json"));
    if (!diagnosticsKey) return null;
    const diagnostics = await readAssetText(`data/${diagnosticsKey}`);
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
