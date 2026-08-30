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

export type CollectorPriceBand = "all" | "10-100" | "100-1000" | "1000-10000" | "10000-plus";

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

export function matchesCollectorPriceBand(price: number, band: CollectorPriceBand) {
  if (band === "10-100") return price >= 10 && price < 100;
  if (band === "100-1000") return price >= 100 && price < 1_000;
  if (band === "1000-10000") return price >= 1_000 && price < 10_000;
  if (band === "10000-plus") return price >= 10_000;
  return true;
}

export function cardImageDeliveryUrl(value: string | null) {
  if (!value) return null;
  try {
    const url = new URL(value);
    if (url.hostname !== "assets.tcgdex.net") return value;
    const parts = url.pathname.split("/").filter(Boolean).map(decodeURIComponent);
    if (parts.length !== 4 || parts[0] !== "en" || parts[3] !== "high.webp") return value;
    const [, setId, collectorNumber] = parts;
    return `https://images.pokemontcg.io/${encodeURIComponent(setId)}/${encodeURIComponent(collectorNumber)}.png`;
  } catch {
    return value;
  }
}

export function latestCollectorRecord(history: CollectorHistory) {
  return history.records.at(-1) ?? null;
}

export function latestCollectorRebalance(rebalances: CollectorRebalances) {
  return rebalances.rebalances.at(-1) ?? null;
}

export function collectorDiagnosticSummary(diagnostics: CollectorDiagnostics) {
  if (diagnostics.summary) {
    return {
      count: diagnostics.summary.count,
      averageQuality: diagnostics.summary.average_quality,
      averageActivityRatio: diagnostics.summary.average_activity_ratio,
      positiveActivityRows: diagnostics.summary.positive_activity_rows
    };
  }
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
