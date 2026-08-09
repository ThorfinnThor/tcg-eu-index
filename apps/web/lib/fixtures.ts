import type { Constituent, IndexSummary } from "./types";

const dates = Array.from({ length: 120 }, (_, index) => {
  const date = new Date(Date.UTC(2026, 3, 1 + index));
  return date.toISOString().slice(0, 10);
});

function curve(seed: number) {
  let value = 1000;
  return dates.map((day, index) => {
    const daily = Math.sin((index + seed) / 8) * 0.006 + Math.cos((index + seed) / 19) * 0.003;
    value *= 1 + daily;
    return {
      value_date: day,
      index_value: Number(value.toFixed(6)),
      daily_return: Number(daily.toFixed(8)),
      n_constituents_active: seed === 3 ? 25 : seed === 2 ? 250 : 100,
      n_capped: index % 41 === 0 ? 1 : 0,
      n_carried_forward: index % 23 === 0 ? 2 : 0,
      calc_version: "1.0.0"
    };
  });
}

export const fixtureIndexes: IndexSummary[] = [
  {
    code: "OPEU100",
    slug: "one-piece-europe-100",
    name: "One Piece Europe 100",
    game: "One Piece",
    universe: "singles",
    base_date: "2026-07-20",
    status: "accumulating",
    target_size: 100,
    breadth: 0.58,
    volatility_30d: 0.31,
    history: curve(1)
  },
  {
    code: "PKEU250",
    slug: "pokemon-europe-250",
    name: "Pokemon Europe 250",
    game: "Pokemon",
    universe: "singles",
    base_date: "2026-07-20",
    status: "accumulating",
    target_size: 250,
    breadth: 0.53,
    volatility_30d: 0.24,
    history: curve(2)
  },
  {
    code: "OPEUSLD",
    slug: "one-piece-sealed-pilot",
    name: "One Piece Sealed Pilot",
    game: "One Piece",
    universe: "sealed",
    base_date: "2026-07-20",
    status: "accumulating",
    target_size: 25,
    breadth: 0.62,
    volatility_30d: 0.18,
    history: curve(3)
  }
];

export const fixtureConstituents: Record<string, Constituent[]> = Object.fromEntries(
  fixtureIndexes.map((index) => [
    index.code,
    Array.from({ length: Math.min(index.target_size, 40) }, (_, row) => ({
      cm_product_id: 750000 + row,
      variant_key: row % 7 === 0 ? "foil" : "nonfoil",
      name: `${index.game} Benchmark Product ${row + 1}`,
      set: row % 2 === 0 ? "Launch Set" : "Current Set",
      member_since: row < 10 ? "2026-07-20" : "2026-08-01",
      action: row < 10 ? "retained" : "added",
      liquidity_score: Number((0.91 - row * 0.006).toFixed(3)),
      ref_price: Number((2 + row * 1.35).toFixed(2))
    }))
  ])
);
