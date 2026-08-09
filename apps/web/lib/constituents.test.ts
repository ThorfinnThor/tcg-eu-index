import { describe, expect, it } from "vitest";
import { activeConstituentsAsOf, constituentActions, filterConstituents, latestCompositionDate } from "./constituents";
import type { Constituent } from "./types";

const constituents: Constituent[] = [
  {
    cm_product_id: 1,
    variant_key: "nonfoil",
    name: "Launch Card",
    set: "Launch Set",
    member_since: "2026-07-20",
    removed_at: "2026-08-01",
    action: "removed",
    liquidity_score: 0.8,
    ref_price: 10
  },
  {
    cm_product_id: 2,
    variant_key: "foil",
    name: "New Card",
    set: "Current Set",
    member_since: "2026-08-01",
    action: "added",
    liquidity_score: 0.9,
    ref_price: 20
  }
];

describe("activeConstituentsAsOf", () => {
  it("replays additions and removals at their effective date", () => {
    expect(activeConstituentsAsOf(constituents, "2026-07-31").map((item) => item.cm_product_id)).toEqual([1]);
    expect(activeConstituentsAsOf(constituents, "2026-08-01").map((item) => item.cm_product_id)).toEqual([2]);
  });
});

describe("filterConstituents", () => {
  it("searches names, sets, variants, and product IDs after as-of filtering", () => {
    expect(filterConstituents(constituents, "2026-08-02", "foil")).toHaveLength(1);
    expect(filterConstituents(constituents, "2026-08-02", "1")).toHaveLength(0);
  });

  it("can include inactive members for lifecycle auditing", () => {
    expect(filterConstituents(constituents, "2026-08-02", "", true)).toHaveLength(2);
    expect(filterConstituents(constituents, "2026-08-02", "", false)).toHaveLength(1);
  });
});

describe("constituentActions", () => {
  it("builds an auditable lifecycle for removed members", () => {
    expect(constituentActions(constituents[0])).toEqual([
      { date: "2026-07-20", action: "added" },
      { date: "2026-08-01", action: "removed" }
    ]);
  });
});

describe("latestCompositionDate", () => {
  it("includes rebalance events newer than daily index history", () => {
    expect(latestCompositionDate(constituents, "2026-07-29")).toBe("2026-08-01");
  });
});
