import { describe, expect, it } from "vitest";
import { changes, postInceptionHistory } from "./data";
import type { IndexSummary } from "./types";

const index: IndexSummary = {
  code: "OPEU500",
  slug: "one-piece-europe-500",
  name: "One Piece Europe 500",
  game: "One Piece",
  universe: "singles",
  history_start_date: "2026-07-18",
  history_start_kind: "validation",
  base_date: "2026-07-20",
  status: "accumulating",
  target_size: 500,
  breadth: 0.5,
  volatility_30d: 0.2,
  history: [
    { value_date: "2026-07-18", index_value: 500, daily_return: 0, n_constituents_active: 100 },
    { value_date: "2026-07-20", index_value: 1000, daily_return: 0, n_constituents_active: 100 },
    { value_date: "2026-07-21", index_value: 1100, daily_return: 0.1, n_constituents_active: 100 }
  ]
};

describe("formal inception boundary", () => {
  it("excludes validation rows from public performance changes", () => {
    expect(postInceptionHistory(index).map((row) => row.value_date)).toEqual([
      "2026-07-20",
      "2026-07-21"
    ]);
    expect(changes(index).d30).toBeCloseTo(0.1);
  });
});
