import type { Constituent, IndexSummary } from "./types";

export const fixtureIndexes: IndexSummary[] = [
  {
    code: "OPEU100",
    slug: "one-piece-europe-100",
    name: "One Piece Europe 100",
    game: "One Piece",
    universe: "singles",
    history_start_date: "2026-04-01",
    history_start_kind: "validation",
    base_date: "2026-07-20",
    status: "accumulating",
    target_size: 100,
    breadth: 0,
    volatility_30d: 0,
    history: []
  },
  {
    code: "PKEU250",
    slug: "pokemon-europe-250",
    name: "Pokemon Europe 250",
    game: "Pokemon",
    universe: "singles",
    history_start_date: "2026-04-01",
    history_start_kind: "validation",
    base_date: "2026-07-20",
    status: "accumulating",
    target_size: 250,
    breadth: 0,
    volatility_30d: 0,
    history: []
  },
  {
    code: "OPEUSLD",
    slug: "one-piece-sealed-pilot",
    name: "One Piece Sealed Pilot",
    game: "One Piece",
    universe: "sealed",
    history_start_date: "2026-04-01",
    history_start_kind: "validation",
    base_date: "2026-07-20",
    status: "accumulating",
    target_size: 25,
    breadth: 0,
    volatility_30d: 0,
    history: []
  }
];

export const fixtureConstituents: Record<string, Constituent[]> = Object.fromEntries(
  fixtureIndexes.map((index) => [index.code, []])
);
