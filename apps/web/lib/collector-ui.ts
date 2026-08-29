import type {
  CollectorDiagnostics,
  CollectorHistory,
  CollectorIndexSummary,
  CollectorRebalances
} from "./types";

const gameNames: Record<string, string> = {
  magic: "Magic: The Gathering",
  yugioh: "Yu-Gi-Oh!",
  onepiece: "One Piece",
  pokemon: "Pokemon",
  dragonballsuper: "Dragon Ball Super",
  fleshandblood: "Flesh and Blood",
  digimon: "Digimon",
  lorcana: "Disney Lorcana",
  starwarsunlimited: "Star Wars: Unlimited",
  riftbound: "Riftbound"
};

export function collectorGameName(gameKey: string) {
  return gameNames[gameKey] ?? gameKey;
}

export function collectorThreshold(summary: Pick<CollectorIndexSummary, "universe">) {
  return summary.universe === "sealed" ? 30 : 10;
}

export function collectorUniverseLabel(universe: CollectorIndexSummary["universe"]) {
  return universe === "sealed" ? "sealed products" : "single-card variants";
}

export function formatCollectorEur(value: number | null) {
  if (value === null) return "—";
  return new Intl.NumberFormat("en-GB", { style: "currency", currency: "EUR" }).format(value);
}

export function formatCollectorPct(value: number | null) {
  if (value === null) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

export function latestCollectorRecord(history: CollectorHistory) {
  return history.records.at(-1) ?? null;
}

export function latestCollectorRebalance(rebalances: CollectorRebalances) {
  return rebalances.rebalances.at(-1) ?? null;
}

export function collectorDiagnosticSummary(diagnostics: CollectorDiagnostics) {
  const rows = diagnostics.eligibility;
  if (rows.length === 0) {
    return {
      count: 0,
      averageQuality: null,
      averageActivityRatio: null,
      positiveActivityRows: 0
    };
  }
  return {
    count: rows.length,
    averageQuality: rows.reduce((sum, row) => sum + row.data_quality_score, 0) / rows.length,
    averageActivityRatio: rows.reduce((sum, row) => sum + row.activity_ratio, 0) / rows.length,
    positiveActivityRows: rows.filter((row) => row.activity_days > 0).length
  };
}
